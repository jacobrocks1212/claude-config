#!/usr/bin/env python3
"""
lazy_coord.py — Worktree pool coordination primitives for parallel /lazy orchestration.

Provides:
  - Global directory-lock (NTFS atomic mkdir) for lease-file mutation
  - leases.json acquisition, heartbeat, fencing, reclamation, and release
  - Worktree pool provisioning and slot scrubbing

Usage:
    python lazy_coord.py --test    # run fixture smoke tests

This module is stdlib-only and must NOT import lazy_core.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class FencingError(ValueError):
	"""Raised when a lease operation detects a term-token mismatch or missing entry."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _now_iso(now) -> str:
	"""Return ISO-8601 UTC 'Z' string from epoch float (or time.time() if None)."""
	if now is None:
		now = time.time()
	return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(ts) -> float:
	"""Parse ISO-8601 UTC 'Z' string to epoch float."""
	return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def _read_leases(path) -> dict:
	"""Read leases.json, returning an empty dict if the file does not exist."""
	p = Path(path)
	if not p.exists():
		return {}
	return json.loads(p.read_text(encoding="utf-8"))


def _write_leases(path, data) -> None:
	"""Atomically write data to leases.json via a temp file + os.replace."""
	p = Path(path)
	tmp = p.with_suffix(".tmp")
	tmp.write_text(json.dumps(data), encoding="utf-8")
	os.replace(str(tmp), str(p))


# ---------------------------------------------------------------------------
# Fencing-token watermarks (parallel-worktree-batch-execution Phase 3 fix).
#
# term_token monotonicity previously lived ONLY on the live leases.json entry:
# once a reclaim (or a release) DELETED the entry, the next acquire_lease saw
# no prior entry and restarted at token 1 — so a zombie holding the ORIGINAL
# token 1 still passed verify_fencing after its lease was reclaimed and
# re-claimed (the exact corruption fencing exists to prevent; surfaced by the
# `zombie-lane-fenced` fixture).  The watermark file — a SIBLING of
# leases.json, `{wi_id: last_token}` — preserves per-item monotonicity across
# entry deletion.  leases.json's own schema is UNTOUCHED (the
# pipeline_visualizer iterates its top-level items and must keep parsing).
# Read errors fail open to {} (legacy behavior).
# ---------------------------------------------------------------------------

_WATERMARKS_SUFFIX = "lease-token-watermarks.json"


def _watermarks_path(leases_path) -> Path:
	return Path(leases_path).parent / _WATERMARKS_SUFFIX


def _read_watermarks(leases_path) -> dict:
	p = _watermarks_path(leases_path)
	if not p.exists():
		return {}
	try:
		data = json.loads(p.read_text(encoding="utf-8"))
	except (ValueError, OSError):
		return {}
	return data if isinstance(data, dict) else {}


def _record_watermarks(leases_path, entries: dict) -> None:
	"""Persist the retired entries' term_tokens (monotonic high-water marks)."""
	if not entries:
		return
	marks = _read_watermarks(leases_path)
	for wi_id, entry in entries.items():
		try:
			token = int(entry.get("term_token", 0))
		except (TypeError, ValueError):
			continue
		if token > int(marks.get(str(wi_id), 0) or 0):
			marks[str(wi_id)] = token
	p = _watermarks_path(leases_path)
	tmp = p.with_suffix(".tmp")
	tmp.write_text(json.dumps(marks), encoding="utf-8")
	os.replace(str(tmp), str(p))


def _reclaim(data: dict, pool_dir, now: float, *, leases_path=None) -> None:
	"""Mutate data in-place, removing expired entries and scrubbing their slot dirs.

	When ``leases_path`` is provided, the removed entries' term_tokens are
	recorded as watermarks so a later re-claim mints a STRICTLY GREATER token
	(zombie fencing survives reclamation).
	"""
	expired_ids = [
		wi_id for wi_id, entry in data.items()
		if _parse_iso(entry["heartbeat_timestamp"]) + entry["ttl_seconds"] < now
	]
	retired: dict = {}
	for wi_id in expired_ids:
		entry = data.pop(wi_id)
		retired[wi_id] = entry
		slot = entry.get("worktree_slot")
		if slot:
			shutil.rmtree(str(Path(pool_dir) / slot), ignore_errors=True)
	if leases_path is not None:
		_record_watermarks(leases_path, retired)


# ---------------------------------------------------------------------------
# Lock owner metadata + stale-holder reclamation (coord-lock-no-stale-reclaim)
#
# acquire_lock's os.mkdir lock previously carried NO holder metadata and had
# NO reclamation path — a holder that dies between mkdir and release_lock
# (e.g. SIGKILL) deadlocked every coordination mutation forever. This mirrors
# the lease layer's dead-holder handling one level down: a successful mkdir
# writes owner.json {pid, kernel_start_time, acquired_at} (write-temp-then-
# os.replace, matching _write_leases); a losing mkdir reads owner.json and
# reclaims (atomic rename-then-rmtree) ONLY on a CONFIRMED-dead holder (pid
# gone, or pid reused — live kernel_start_time mismatches the recorded one).
# Ambiguous states (pid alive, start-time unreadable, or a metadata-less lock
# still inside its grace window — the crash window between mkdir and the
# metadata write) NEVER reclaim: safety over liveness, mirroring the
# build-queue active.lock precedent (Get-ActiveLockStatusFromText /
# Test-ShouldReclaimLock: an unreadable pid classifies 'unknown', never
# 'dead' — only a confirmed-dead observation reclaims).
#
# kernel_start_time is DUPLICATED from lazy_core.py rather than imported —
# lazy_coord.py is stdlib-only and must NOT import lazy_core (module
# docstring). Same deliberate-duplication policy lazy_core.py documents for
# its own _current_head ("the two scripts are independently importable" —
# lazy_core.py's _current_head docstring).
# ---------------------------------------------------------------------------

_LOCK_OWNER_FILENAME = "owner.json"
_LOCK_STALE_GRACE_SECONDS_DEFAULT = 2.0

_FILETIME_EPOCH_OFFSET = 116444736000000000
_FILETIME_TICKS_PER_SEC = 10_000_000


def kernel_start_time(
	pid,
	*,
	platform=None,
	read_stat=None,
	get_process_times=None,
	boot_time=None,
	clk_tck=None,
):
	"""Return the kernel-reported absolute start time of ``pid`` as a Unix
	epoch float, or ``None`` on any error (best-effort, NEVER raises).

	Duplicated from ``lazy_core.kernel_start_time`` (identical contract and
	implementation — see the module-level note above). The PID-reuse defense:
	a reused pid held by a foreign process reports a DIFFERENT start_time, so
	a stale-lock reclaim can tell "same holder, still running" from "pid
	recycled to an unrelated process" apart from mere pid-existence.

	  - Windows — ``ctypes`` -> ``kernel32.GetProcessTimes`` (creation FILETIME,
	    100ns intervals since 1601-01-01, converted to a Unix epoch float).
	  - POSIX/WSL — ``/proc/[pid]/stat`` field 22 (``starttime``, clock ticks
	    since boot) -> epoch via ``boot_time + ticks / SC_CLK_TCK``.

	Injection (hermetic ``--test``): ``read_stat`` / ``get_process_times`` /
	``boot_time`` / ``clk_tck`` — mirrors lazy_core.kernel_start_time's seams.
	"""
	if platform is None:
		platform = sys.platform
	is_windows = str(platform).startswith("win")

	try:
		if is_windows:
			if get_process_times is None:
				get_process_times = _win_process_creation_filetime
			filetime = get_process_times(pid)
			if filetime is None:
				return None
			return (filetime - _FILETIME_EPOCH_OFFSET) / _FILETIME_TICKS_PER_SEC

		if read_stat is None:
			def read_stat(p):
				return Path(f"/proc/{p}/stat").read_text(encoding="utf-8", errors="replace")
		if clk_tck is None:
			clk_tck = os.sysconf("SC_CLK_TCK")
		if boot_time is None:
			boot_time = _posix_boot_time()
		if boot_time is None or not clk_tck:
			return None

		raw = read_stat(pid)
		# Field 2 (comm) may contain spaces/parens; split off through the LAST
		# ')' so the remaining fields are whitespace-delimitable. Field 22
		# (starttime) is tail index 19 (tail starts at field 3 = state).
		rparen = raw.rfind(")")
		if rparen < 0:
			return None
		tail = raw[rparen + 1:].split()
		if len(tail) < 20:
			return None
		ticks = int(tail[19])
		return boot_time + (ticks / clk_tck)
	except Exception:  # noqa: BLE001 - best-effort, never raises
		return None


def _win_process_creation_filetime(pid):
	"""Windows creation-FILETIME extractor via ctypes -> GetProcessTimes.
	Returns the creation FILETIME int, or None on any error."""
	try:
		import ctypes
		from ctypes import wintypes

		PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
		kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
		handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
		if not handle:
			return None
		try:
			creation = wintypes.FILETIME()
			exit_t = wintypes.FILETIME()
			kernel_t = wintypes.FILETIME()
			user_t = wintypes.FILETIME()
			ok = kernel32.GetProcessTimes(
				handle, ctypes.byref(creation), ctypes.byref(exit_t),
				ctypes.byref(kernel_t), ctypes.byref(user_t),
			)
			if not ok:
				return None
			return (creation.dwHighDateTime << 32) | creation.dwLowDateTime
		finally:
			kernel32.CloseHandle(handle)
	except Exception:  # noqa: BLE001
		return None


def _posix_boot_time():
	"""Read system boot time (Unix epoch sec) from /proc/stat ``btime``.
	Returns None on any error."""
	try:
		for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
			if line.startswith("btime "):
				return float(line.split()[1])
	except Exception:  # noqa: BLE001
		pass
	return None


def _pid_status(pid, *, platform=None) -> str:
	"""Classify pid liveness as ``'alive'`` | ``'dead'`` | ``'unknown'``
	(best-effort, NEVER raises). Fails safe TOWARD 'unknown' on any
	ambiguity — an inaccessible/unreadable pid must never classify 'dead'
	(the build-queue active.lock precedent: Get-ActiveLockStatusFromText
	treats an unreadable/unparsable observation as 'unknown', never 'dead')."""
	if platform is None:
		platform = sys.platform
	try:
		pid = int(pid)
	except (TypeError, ValueError):
		return "unknown"
	if pid <= 0:
		return "unknown"
	if str(platform).startswith("win"):
		return _win_pid_status(pid)
	return _posix_pid_status(pid)


def _posix_pid_status(pid) -> str:
	try:
		os.kill(pid, 0)
	except ProcessLookupError:
		return "dead"
	except PermissionError:
		return "alive"  # exists, just not signalable by us
	except OSError:
		return "unknown"
	return "alive"


def _win_pid_status(pid) -> str:
	try:
		import ctypes

		PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
		ERROR_INVALID_PARAMETER = 87
		ERROR_ACCESS_DENIED = 5
		kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
		handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
		if handle:
			kernel32.CloseHandle(handle)
			return "alive"
		err = ctypes.get_last_error()
		if err == ERROR_INVALID_PARAMETER:
			return "dead"
		if err == ERROR_ACCESS_DENIED:
			return "alive"
		return "unknown"
	except Exception:  # noqa: BLE001
		return "unknown"


def _confirmed_dead_owner(owner, *, pid_status_fn=None, kernel_start_time_fn=None) -> bool:
	"""True iff ``owner`` (a parsed owner.json dict) is a CONFIRMED-dead
	holder: its pid no longer exists, OR the pid was reused (a live
	kernel_start_time that mismatches the recorded one). Ambiguous states
	(pid alive with a matching/unreadable start_time, or malformed metadata)
	return False — never reclaim on a guess (D2 — dead-holder confirmation,
	not a bare TTL; the lock has no fencing to make a wrong evict safe)."""
	if not isinstance(owner, dict):
		return False
	pid_status_fn = pid_status_fn or _pid_status
	kernel_start_time_fn = kernel_start_time_fn or kernel_start_time
	try:
		pid_int = int(owner.get("pid"))
	except (TypeError, ValueError):
		return False
	status = pid_status_fn(pid_int)
	if status == "dead":
		return True
	if status != "alive":
		return False  # 'unknown' -> ambiguous, never reclaim
	recorded_start = owner.get("kernel_start_time")
	if recorded_start is None:
		return False  # incomplete metadata -> ambiguous
	live_start = kernel_start_time_fn(pid_int)
	if live_start is None:
		return False  # can't verify -> ambiguous, never reclaim
	return live_start != recorded_start  # mismatch -> PID reuse, confirmed dead


def _read_lock_owner(lock_dir):
	"""Read+parse owner.json from a lock dir. None on missing/unreadable/
	malformed (a metadata-less lock is handled by the grace-age fallback,
	not treated as confirmed-dead here)."""
	p = Path(lock_dir) / _LOCK_OWNER_FILENAME
	try:
		data = json.loads(p.read_text(encoding="utf-8"))
	except (OSError, ValueError):
		return None
	return data if isinstance(data, dict) else None


def _write_lock_owner(lock_dir, *, now=None, kernel_start_time_fn=None) -> None:
	"""Best-effort: write owner.json {pid, kernel_start_time, acquired_at}
	into a freshly-mkdir'd lock_dir via write-temp-then-os.replace (the
	_write_leases pattern). NEVER raises — the caller already succeeded at
	mkdir, so a metadata-write failure must not strand the lock unreleased
	(the crash-window grace-age fallback in _maybe_reclaim_stale_lock covers
	a lock left without owner.json, including one that never gets one)."""
	try:
		kernel_start_time_fn = kernel_start_time_fn or kernel_start_time
		pid = os.getpid()
		data = {
			"pid": pid,
			"kernel_start_time": kernel_start_time_fn(pid),
			"acquired_at": _now_iso(now),
		}
		p = Path(lock_dir) / _LOCK_OWNER_FILENAME
		tmp = p.with_suffix(".tmp")
		tmp.write_text(json.dumps(data), encoding="utf-8")
		os.replace(str(tmp), str(p))
	except Exception:  # noqa: BLE001 - best-effort, see docstring
		pass


def _lock_dir_age_seconds(lock_dir, now):
	try:
		mtime = os.stat(str(lock_dir)).st_mtime
	except OSError:
		return None
	return max(0.0, now - mtime)


def _rename_then_remove(lock_dir) -> bool:
	"""Atomic rename-then-rmtree reclaim (D2/Fix Scope item 2). Returns True
	iff THIS call won the race (renamed the dir away, then removed it);
	False if the rename lost (a racing reclaimer got there first, or the dir
	is already gone) — the caller falls back to its normal mkdir spin, exactly
	one reclaimer ever wins."""
	lock_dir = Path(lock_dir)
	stale_target = lock_dir.parent / f"{lock_dir.name}.stale-{os.getpid()}-{time.time_ns()}"
	try:
		os.rename(str(lock_dir), str(stale_target))
	except OSError:
		return False  # lost the race (or the dir is already gone)
	shutil.rmtree(str(stale_target), ignore_errors=True)
	return True


def _maybe_reclaim_stale_lock(
	lock_dir, *, grace_seconds=_LOCK_STALE_GRACE_SECONDS_DEFAULT, now=None,
	pid_status_fn=None, kernel_start_time_fn=None,
) -> bool:
	"""Reclaim lock_dir iff its recorded holder is CONFIRMED dead — or, absent
	readable owner.json, the lock dir is older than ``grace_seconds`` (the
	crash window between mkdir and the metadata write; a metadata-less lock
	INSIDE the grace window is ambiguous, not stale). Returns True iff THIS
	call performed the reclaim; the caller should retry ``mkdir`` immediately."""
	ts_now = time.time() if now is None else now
	owner = _read_lock_owner(lock_dir)
	if owner is None:
		age = _lock_dir_age_seconds(lock_dir, ts_now)
		if age is None or age <= grace_seconds:
			return False  # vanished already (race), or still inside grace
	elif not _confirmed_dead_owner(
		owner, pid_status_fn=pid_status_fn, kernel_start_time_fn=kernel_start_time_fn,
	):
		return False
	return _rename_then_remove(lock_dir)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def acquire_lock(
	lock_dir, timeout=10.0, *, poll=0.05, now=None,
	grace_seconds=None, pid_status_fn=None, kernel_start_time_fn=None,
) -> None:
	"""Acquire the global directory lock via atomic os.mkdir.

	Retries with exponential backoff until timeout, then raises TimeoutError.
	Never uses fcntl/flock/LockFileEx. On acquisition, writes ``owner.json``
	(pid / kernel_start_time / acquired_at) into the lock dir. On a losing
	mkdir, reclaims the lock first if its recorded holder is CONFIRMED dead
	(see ``_maybe_reclaim_stale_lock``) — a holder that dies between ``mkdir``
	and ``release_lock`` (e.g. SIGKILL) no longer deadlocks the pool forever
	(docs/bugs/coord-lock-no-stale-reclaim). A genuinely live contended lock
	still times out exactly as before; reclamation only consumes attempts
	within the same timeout/backoff budget — callers need no signature changes.
	"""
	lock_dir = Path(lock_dir)
	if grace_seconds is None:
		grace_seconds = _LOCK_STALE_GRACE_SECONDS_DEFAULT
	start = time.monotonic()
	delay = poll
	while True:
		try:
			os.mkdir(str(lock_dir))
			_write_lock_owner(lock_dir, now=now, kernel_start_time_fn=kernel_start_time_fn)
			return  # acquired
		except FileExistsError:
			if _maybe_reclaim_stale_lock(
				lock_dir, grace_seconds=grace_seconds, now=now,
				pid_status_fn=pid_status_fn, kernel_start_time_fn=kernel_start_time_fn,
			):
				continue  # reclaimed a confirmed-dead holder — retry mkdir now
			elapsed = time.monotonic() - start
			if elapsed >= timeout:
				raise TimeoutError(
					f"Could not acquire lock {lock_dir!r} within {timeout}s"
				)
			time.sleep(min(delay, timeout - elapsed))
			delay = min(delay * 2, 1.0)


def release_lock(lock_dir) -> None:
	"""Release the global directory lock: remove ``owner.json`` (if present)
	then ``os.rmdir`` the lock dir."""
	lock_dir = Path(lock_dir)
	try:
		(lock_dir / _LOCK_OWNER_FILENAME).unlink()
	except FileNotFoundError:
		pass
	except OSError:
		pass  # best-effort; a genuine problem surfaces at rmdir below
	try:
		os.rmdir(str(lock_dir))
	except FileNotFoundError:
		pass


def acquire_lease(leases_path, wi_id, worker_pid, slot, ttl_seconds, *, now=None) -> dict | None:
	"""Acquire a worktree lease for wi_id, writing to leases.json.

	Reclaims expired leases first. If wi_id already has a live (non-expired)
	lease, returns None (no double-claim). Otherwise writes a new entry with
	term_token = prev+1 (prev=0 if none) and returns the entry dict.

	All mutations happen under the global lock
	(lock_dir = leases_path.parent / "global.lock.d") via atomic os.replace.

	Lease entry shape:
	  {
	    "worker_pid": int,
	    "worktree_slot": str,
	    "term_token": int,
	    "heartbeat_timestamp": "<ISO-8601 UTC 'Z' str>",
	    "ttl_seconds": int,
	  }

	Args:
	    leases_path: Path to leases.json.
	    wi_id: Work-item ID (int or str).
	    worker_pid: PID of the claiming worker.
	    slot: Worktree slot identifier string.
	    ttl_seconds: Lease TTL in seconds.
	    now: Optional epoch float override for deterministic testing.

	Returns:
	    The new lease entry dict, or None if already held.
	"""
	leases_path = Path(leases_path)
	lock_dir = leases_path.parent / "global.lock.d"
	ts_now = now if now is not None else time.time()
	key = str(wi_id)

	acquire_lock(lock_dir)
	try:
		data = _read_leases(leases_path)
		# Inline reclaim expired entries (records term_token watermarks so a
		# re-claim after reclamation mints a strictly greater fencing token).
		_reclaim(data, leases_path.parent, ts_now, leases_path=leases_path)

		# Check for existing live lease
		if key in data:
			entry = data[key]
			heartbeat_epoch = _parse_iso(entry["heartbeat_timestamp"])
			if heartbeat_epoch + entry["ttl_seconds"] >= ts_now:
				# Live lease — no double-claim
				return None
			# Expired but wasn't reclaimed (shouldn't happen after _reclaim, but be safe)
			prev_token = entry.get("term_token", 0)
		else:
			prev_token = 0

		# Fencing-token monotonicity floor: never mint at-or-below a retired
		# token for this wi_id (zombie-lane fencing survives entry deletion).
		try:
			watermark = int(_read_watermarks(leases_path).get(key, 0) or 0)
		except (TypeError, ValueError):
			watermark = 0
		prev_token = max(int(prev_token), watermark)

		term_token = prev_token + 1
		new_entry = {
			"worker_pid": int(worker_pid),
			"worktree_slot": str(slot),
			"term_token": term_token,
			"heartbeat_timestamp": _now_iso(ts_now),
			"ttl_seconds": int(ttl_seconds),
		}
		data[key] = new_entry
		_write_leases(leases_path, data)
		return new_entry
	finally:
		release_lock(lock_dir)


def heartbeat(leases_path, wi_id, expected_token, *, now=None) -> None:
	"""Refresh the heartbeat_timestamp of an existing lease.

	Calls verify_fencing first; raises FencingError if the lease is absent or
	the term_token has changed. Updates heartbeat_timestamp to now.
	"""
	leases_path = Path(leases_path)
	lock_dir = leases_path.parent / "global.lock.d"
	key = str(wi_id)

	acquire_lock(lock_dir)
	try:
		data = _read_leases(leases_path)
		if key not in data or data[key]["term_token"] != expected_token:
			raise FencingError(
				f"Fencing token mismatch for wi_id={wi_id}: "
				f"expected {expected_token}, "
				f"got {data.get(key, {}).get('term_token', '<absent>')}"
			)
		data[key]["heartbeat_timestamp"] = _now_iso(now)
		_write_leases(leases_path, data)
	finally:
		release_lock(lock_dir)


def verify_fencing(leases_path, wi_id, expected_token) -> None:
	"""Assert that leases.json[str(wi_id)].term_token == expected_token.

	Raises FencingError if the entry is absent or the token does not match.
	Returns None on success.
	"""
	data = _read_leases(leases_path)
	key = str(wi_id)
	if key not in data or data[key]["term_token"] != expected_token:
		raise FencingError(
			f"Fencing token mismatch for wi_id={wi_id}: "
			f"expected {expected_token}, "
			f"got {data.get(key, {}).get('term_token', '<absent>')}"
		)


def reclaim_expired(leases_path, pool_dir, *, now=None) -> list:
	"""Remove expired leases and best-effort scrub their worktree slots.

	A lease is expired iff:
	    heartbeat_epoch + ttl_seconds < now

	where heartbeat_epoch is derived from parsing heartbeat_timestamp (ISO-8601
	UTC 'Z' string). Expired entries are removed from leases.json; their
	pool_dir/<slot> directories are scrubbed (errors tolerated — do NOT
	hard-fail on non-git or missing dirs). Returns a list of reclaimed wi_id
	strings.

	Args:
	    leases_path: Path to leases.json.
	    pool_dir: Path to the worktree pool directory.
	    now: Optional epoch float override for deterministic testing.
	"""
	leases_path = Path(leases_path)
	pool_dir = Path(pool_dir)
	lock_dir = leases_path.parent / "global.lock.d"
	ts_now = now if now is not None else time.time()

	acquire_lock(lock_dir)
	try:
		data = _read_leases(leases_path)
		expired_ids = [
			wi_id for wi_id, entry in data.items()
			if _parse_iso(entry["heartbeat_timestamp"]) + entry["ttl_seconds"] < ts_now
		]
		retired = {}
		for wi_id in expired_ids:
			entry = data.pop(wi_id)
			retired[wi_id] = entry
			slot = entry.get("worktree_slot")
			if slot:
				shutil.rmtree(str(pool_dir / slot), ignore_errors=True)
		# Record term_token watermarks BEFORE the entries vanish, so a later
		# re-claim can never mint a token a zombie still holds.
		_record_watermarks(leases_path, retired)
		_write_leases(leases_path, data)
		return expired_ids
	finally:
		release_lock(lock_dir)


def release_lease(leases_path, wi_id, expected_token, *, now=None) -> None:
	"""Release a lease after verifying fencing token.

	Calls verify_fencing first; raises FencingError on mismatch. Removes the
	entry from leases.json via atomic os.replace under the global lock.
	"""
	leases_path = Path(leases_path)
	lock_dir = leases_path.parent / "global.lock.d"
	key = str(wi_id)

	acquire_lock(lock_dir)
	try:
		data = _read_leases(leases_path)
		if key not in data or data[key]["term_token"] != expected_token:
			raise FencingError(
				f"Fencing token mismatch for wi_id={wi_id}: "
				f"expected {expected_token}, "
				f"got {data.get(key, {}).get('term_token', '<absent>')}"
			)
		# Watermark on voluntary release too: a re-claimed item must never
		# mint a token equal to one a prior (released) holder carried.
		_record_watermarks(leases_path, {key: data[key]})
		del data[key]
		_write_leases(leases_path, data)
	finally:
		release_lock(lock_dir)


class ItemLockTimeout(TimeoutError):
	"""Raised when acquire_item_lock cannot claim the per-queue-item lock within
	its timeout budget (Leg 5 — a timeout is NEVER a successful acquire)."""


def acquire_item_lock(
	leases_path, wi_id, worker_pid, slot, ttl_seconds,
	*, timeout=10.0, poll=0.05, now=None, clock=None, sleep=None,
) -> dict:
	"""Acquire the per-queue-item FIFO lock for wi_id (concurrent-lock-contract.md).

	The stdlib-Python plane of the ONE documented concurrent-lock grammar. Built
	on the existing lease layer — a polling mutex over ``acquire_lease`` keyed by
	``wi_id`` verbatim, inventing NO new locking substrate:

	- **Per-item grain (Leg 1):** two workers contending on the SAME wi_id
	  serialize; two workers on DIFFERENT wi_ids never block each other.
	- **Wait-for-unlock FIFO (Leg 2):** while a live holder holds the item's
	  lease, ``acquire_lease`` returns None; this waits (bounded exponential
	  backoff) and retries until the holder releases (or its lease expires), then
	  proceeds in turn.
	- **Fencing token (Leg 3):** returns the lease entry dict — the caller carries
	  ``entry["term_token"]`` to ``verify_fencing`` / ``release_item_lock``.
	- **Confirmed-dead reclaim (Leg 4):** ``acquire_lease``'s inline TTL-expiry
	  ``_reclaim`` (a holder that stopped heart-beating) plus the global lock's
	  ``_confirmed_dead_owner`` reclaim it; an ambiguous/live holder is NEVER
	  falsely reclaimed and still times out within the budget.
	- **Authoritative timeout (Leg 5):** on budget exhaustion raises
	  ``ItemLockTimeout`` — never a false ACQUIRED.

	Time is injected (the module convention): ``now`` is the lease-expiry epoch
	float threaded into ``acquire_lease``; ``clock``/``sleep`` (default
	``time.monotonic``/``time.sleep``) drive the timeout budget so ``--test``
	fixtures are hermetic.

	Returns the acquired lease entry dict. Raises ItemLockTimeout on timeout.
	"""
	clock = clock or time.monotonic
	sleep = sleep or time.sleep
	start = clock()
	delay = poll
	while True:
		entry = acquire_lease(leases_path, wi_id, worker_pid, slot, ttl_seconds, now=now)
		if entry is not None:
			return entry  # acquired (carries the fencing term_token)
		elapsed = clock() - start
		if elapsed >= timeout:
			raise ItemLockTimeout(
				f"Could not acquire item lock for wi_id={wi_id!r} within {timeout}s"
			)
		sleep(min(delay, timeout - elapsed))
		delay = min(delay * 2, 1.0)


def release_item_lock(leases_path, wi_id, expected_token, *, now=None) -> None:
	"""Release the per-queue-item FIFO lock (Leg 3 — fencing-token release).

	Thin alias over ``release_lease``: verifies the fencing token first, so a
	superseded holder (its ``term_token`` changed underneath it) raises
	``FencingError`` and MUST NOT release someone else's lock."""
	release_lease(leases_path, wi_id, expected_token, now=now)


def provision_pool(repo_root, pool_dir, k) -> list:
	"""Provision k worktree slots in pool_dir, returning a list of slot paths.

	Creates git worktrees (via git worktree add) for each slot that does not
	already exist. Returns the list of Path objects for all k slots.

	Repo-agnostic (parallel-worktree-batch-execution D10): ``repo_root`` was
	historically named ``cognito_root`` — positional call sites are unchanged
	by the rename. Works for any git repo (Cognito worker pools and
	/lazy-batch-parallel lane pools alike).
	"""
	repo_root = Path(repo_root)
	pool_dir = Path(pool_dir)
	pool_dir.mkdir(parents=True, exist_ok=True)

	# Global lock for network git ops
	lock_dir = pool_dir / "global.lock.d"

	slots = []
	for n in range(k):
		slot_name = f"wt-{n:02d}"
		slot_path = pool_dir / slot_name
		slots.append(slot_path)
		if slot_path.exists():
			continue
		# Add worktree under global lock
		acquire_lock(lock_dir)
		try:
			subprocess.run(
				["git", "-C", str(repo_root), "worktree", "add", str(slot_path)],
				check=True,
			)
		finally:
			release_lock(lock_dir)

	# Apply git config to each slot
	for slot_path in slots:
		for key, val in [
			("gc.auto", "0"),
			("core.filemode", "false"),
			("core.autocrlf", "input"),
		]:
			try:
				subprocess.run(
					["git", "-C", str(slot_path), "config", key, val],
					check=True,
				)
			except subprocess.CalledProcessError:
				pass  # non-fatal config errors

	return slots


def scrub_slot(
	repo_root, pool_dir, slot, wi_id, slug, *, lock_dir=None,
	branch_template="p/{wi_id}-{slug}", detach_target="origin/main",
) -> None:
	"""Reset a worktree slot to a clean state and cut its work branch.

	Ordered reset (unchanged): index.lock removal (backoff retry) → fetch
	under the global lock → ``checkout --detach <detach_target>`` →
	``reset --hard <detach_target>`` → ``clean -fdx`` → ``checkout -b`` the
	templated branch.

	Repo-agnostic parameterization (parallel-worktree-batch-execution D10) —
	the DEFAULTS are byte-identical to the historical Cognito behavior:

	  * ``repo_root`` — renamed from ``cognito_root`` (positional call sites
	    unchanged).
	  * ``branch_template`` — ``str.format``-ed with ``wi_id``/``slug``.
	    Default ``p/{wi_id}-{slug}`` (the lazy-worker/Cognito PR-discovery
	    convention — never squatted by lanes); /lazy-batch-parallel lanes pass
	    ``lane/{wi_id}`` (with wi_id = the queue item id → ``lane/<item-id>``).
	  * ``detach_target`` — default ``origin/main``; lanes pass the run's base
	    branch.
	"""
	repo_root = Path(repo_root)
	pool_dir = Path(pool_dir)
	slot_path = pool_dir / slot

	# (1) Remove index.lock with exponential backoff retry
	index_lock = repo_root / ".git" / "worktrees" / slot / "index.lock"
	delay = 0.05
	for attempt in range(8):
		try:
			if index_lock.exists():
				index_lock.unlink()
			break
		except OSError as e:
			print(
				f"scrub_slot: index.lock removal attempt {attempt+1} failed: {e}",
				file=sys.stderr,
			)
			time.sleep(delay)
			delay = min(delay * 2, 2.0)

	_lock_dir = Path(lock_dir) if lock_dir else pool_dir / "global.lock.d"

	# (2) Under global lock: git fetch origin
	acquire_lock(_lock_dir)
	try:
		subprocess.run(
			["git", "-C", str(slot_path), "fetch", "origin"],
			check=False,
		)
	finally:
		release_lock(_lock_dir)

	# (3) checkout --detach <detach_target>
	subprocess.run(
		["git", "-C", str(slot_path), "checkout", "--detach", str(detach_target)],
		check=False,
	)
	# (4) reset --hard <detach_target>
	subprocess.run(
		["git", "-C", str(slot_path), "reset", "--hard", str(detach_target)],
		check=False,
	)
	# (5) clean -fdx
	subprocess.run(
		["git", "-C", str(slot_path), "clean", "-fdx"],
		check=False,
	)
	# (6) checkout new branch (templated — default is the Cognito p/ convention)
	branch_name = str(branch_template).format(wi_id=wi_id, slug=slug)
	subprocess.run(
		["git", "-C", str(slot_path), "checkout", "-b", branch_name],
		check=False,
	)


def lane_branch(item_id) -> str:
	"""The lane branch convention: ``lane/<item-id>`` (D10 — the ``p/...``
	namespace stays lazy-worker/Cognito's PR-discovery contract)."""
	return f"lane/{item_id}"


def lane_pool_dir(repo_root) -> Path:
	"""The lane pool location: the SIBLING dir ``<repo_root>-lanes`` (D10 —
	git-worktree-conventional; keeps worktrees out of the repo tree and out of
	repo_key ambiguity; slots are ``wt-NN`` under it)."""
	root = Path(repo_root)
	return root.parent / (root.name + "-lanes")


# ---------------------------------------------------------------------------
# Parallel-worktree lanes (parallel-worktree-batch-execution)
#
# The /lazy-batch-parallel coordinator composes THIS module (locks, leases,
# worktree pool, and the lane ledger below) with lazy_core's deterministic
# reads (dep_completion_status, parse_independent_marker).  The two modules
# NEVER import each other: lazy_coord stays stdlib-only and MUST NOT import
# lazy_core (its stated contract), so the dep-readiness / independence
# booleans arrive PRE-COMPUTED on each candidate dict and the lanes.json
# writer below carries its OWN temp-file + os.replace atomic write (the
# _write_leases pattern) — a deliberate, justified duplication of
# lazy_core._atomic_write, kept tiny on purpose.
# ---------------------------------------------------------------------------

# Hold reasons emitted by claim_shardable (stable strings — the shard report
# and the flush's marker-audit lines print them verbatim).
HOLD_DEP_UNREADY = "dep-unready"
HOLD_NO_INDEPENDENT_MARKER = "no-independent-marker"
HOLD_LIVE_LEASE = "live-lease"


def claim_shardable(candidates, leases_path, *, now=None) -> dict:
	"""Compute the conservative shard set (D3-A) over pre-computed candidates.

	Each candidate is a dict ``{"id": str, "dep_ready": bool, "independent":
	bool}`` where the two booleans were derived by the CALLER from lazy_core's
	deterministic reads (queue ``deps`` receipt-gated completion via
	``dep_completion_status``; the ``independent: true`` isolation marker via
	``parse_independent_marker``).  This function adds the third rail — no
	LIVE lease in ``leases_path`` — and composes the three conservatively:

	  * missing / falsy ``dep_ready``      → held (``dep-unready``)
	  * missing / falsy ``independent``    → held (``no-independent-marker``)
	  * live (non-expired) lease for id    → held (``live-lease``)

	READ-ONLY: never mutates leases.json (run ``reclaim_expired`` first for
	the sweep).  Input order (queue order) is preserved in both lists.

	Returns:
	    {"claimed": [id, ...], "held": [{"id": id, "reason": reason}, ...]}
	"""
	ts_now = now if now is not None else time.time()
	leases = _read_leases(leases_path)
	claimed: list = []
	held: list = []
	for cand in candidates:
		cid = str(cand.get("id")) if isinstance(cand, dict) else str(cand)
		if not isinstance(cand, dict) or not cand.get("dep_ready"):
			held.append({"id": cid, "reason": HOLD_DEP_UNREADY})
			continue
		if not cand.get("independent"):
			held.append({"id": cid, "reason": HOLD_NO_INDEPENDENT_MARKER})
			continue
		entry = leases.get(cid)
		if entry is not None:
			try:
				live = _parse_iso(entry["heartbeat_timestamp"]) + entry["ttl_seconds"] >= ts_now
			except (KeyError, TypeError, ValueError):
				live = True  # unreadable lease entry → assume live (conservative)
			if live:
				held.append({"id": cid, "reason": HOLD_LIVE_LEASE})
				continue
		claimed.append(cid)
	return {"claimed": claimed, "held": held}


def has_live_lease(leases_path, wi_id, *, now=None) -> bool:
	"""Return True iff ``wi_id`` holds a LIVE (non-expired) lease in
	``leases_path`` — the same liveness predicate ``claim_shardable`` applies as
	its third rail, factored out for the merged-head divergence exemption.

	READ-ONLY (never mutates leases.json; run ``reclaim_expired`` first for a
	sweep). Fail-safe by construction:

	  * missing file / missing ``wi_id`` key        → False (no lease held)
	  * present key, unreadable heartbeat/ttl fields → True  (conservative —
	    mirrors ``claim_shardable``: an unreadable entry is assumed live so a
	    genuinely-held item is never treated as free)

	Used by the ``--emit-prompt`` merged-head divergence guard
	(lazy-batch-parallel-run-harness-gaps round-2 gap 8): a serial-tail probe
	whose OWN ``feature_id`` holds a live lease is discharging the coordinator's
	in-flight (lane-merged, lease-held) obligation, so the guard must NOT withhold
	its forward route behind a freshly-dispatchable global head — the exact analog
	of a lane probe (``parent_run`` set) being exempted. Distinct from that lane
	exemption: a lane exempts on the coordinator-arbitrated claim (``parent_run``);
	the serial tail exempts on the probed item's OWN live lease.

	Args:
	    leases_path: Path to the coordinator leases.json (``claude_state_dir() /
	        "leases.json"`` in production).
	    wi_id: Work-item ID (int or str) to test.
	    now: Optional epoch float override for deterministic testing.

	Returns:
	    True iff a live lease for ``wi_id`` exists.
	"""
	ts_now = now if now is not None else time.time()
	entry = _read_leases(leases_path).get(str(wi_id))
	if entry is None:
		return False
	try:
		return _parse_iso(entry["heartbeat_timestamp"]) + entry["ttl_seconds"] >= ts_now
	except (KeyError, TypeError, ValueError):
		# Unreadable entry → assume live (conservative), exactly as claim_shardable.
		return True


def read_lanes(lanes_path) -> dict:
	"""Read lanes.json, returning the empty ledger shape if absent."""
	p = Path(lanes_path)
	if not p.exists():
		return {"lanes": {}, "merge_order": []}
	data = json.loads(p.read_text(encoding="utf-8"))
	data.setdefault("lanes", {})
	data.setdefault("merge_order", [])
	return data


def _write_lanes(lanes_path, data) -> None:
	"""Atomically write lanes.json via a temp file + os.replace.

	Justified duplication of lazy_core._atomic_write (same pattern as
	_write_leases above): lazy_coord MUST NOT import lazy_core, and the
	ledger is coordinator-owned state living beside leases.json.
	"""
	p = Path(lanes_path)
	tmp = p.with_suffix(".tmp")
	tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
	os.replace(str(tmp), str(p))


def _mutate_lanes(lanes_path, mutate) -> dict:
	"""Read-mutate-write lanes.json under the sibling global lock."""
	lanes_path = Path(lanes_path)
	lock_dir = lanes_path.parent / "global.lock.d"
	acquire_lock(lock_dir)
	try:
		data = read_lanes(lanes_path)
		mutate(data)
		_write_lanes(lanes_path, data)
		return data
	finally:
		release_lock(lock_dir)


def ledger_record_claim(lanes_path, item_id, slot, branch, *, now=None) -> dict:
	"""Record a lane claim: item → slot + lane branch, status ``claimed``."""
	def mutate(data):
		data["lanes"][str(item_id)] = {
			"slot": str(slot),
			"branch": str(branch),
			"status": "claimed",
			"claimed_at": _now_iso(now),
		}
	return _mutate_lanes(lanes_path, mutate)


def ledger_record_lane_complete(lanes_path, item_id, *, now=None) -> dict:
	"""Mark a lane's front-half done (ready for the queue-order merge wave)."""
	def mutate(data):
		lane = data["lanes"].setdefault(str(item_id), {})
		lane["status"] = "lane-complete"
		lane["lane_complete_at"] = _now_iso(now)
	return _mutate_lanes(lanes_path, mutate)


def ledger_record_merge(lanes_path, item_id, *, now=None) -> dict:
	"""Record a landed lane merge; appends the id to merge_order."""
	def mutate(data):
		lane = data["lanes"].setdefault(str(item_id), {})
		lane["status"] = "merged"
		lane["merged_at"] = _now_iso(now)
		data["merge_order"].append(str(item_id))
		lane["merge_index"] = len(data["merge_order"]) - 1
	return _mutate_lanes(lanes_path, mutate)


def ledger_record_demotion(lanes_path, item_id, reason, *, now=None) -> dict:
	"""Record a merge-conflict demotion: ``demoted: serial`` (D4).

	The lane branch recorded at claim time is deliberately PRESERVED on the
	entry (salvage/reference + the retro's false-`independent` audit feed).
	"""
	def mutate(data):
		lane = data["lanes"].setdefault(str(item_id), {})
		lane["status"] = "demoted"
		lane["demoted"] = "serial"
		lane["demoted_at"] = _now_iso(now)
		lane["demotion_reason"] = str(reason)
	return _mutate_lanes(lanes_path, mutate)


def ledger_record_park(lanes_path, item_id, sentinel_kind, *, ported_to=None, now=None) -> dict:
	"""Record a parked lane (D5-A): sentinel halt; siblings unaffected.

	``ported_to`` is filled at end-of-run flush when the sentinel is copied
	verbatim onto the canonical docs tree; branch/slot/worktree fields from
	the claim record are preserved (nothing is lost).
	"""
	def mutate(data):
		lane = data["lanes"].setdefault(str(item_id), {})
		lane["status"] = "parked"
		lane["sentinel_kind"] = str(sentinel_kind)
		lane["parked_at"] = _now_iso(now)
		lane["sentinel_ported_to"] = ported_to
	return _mutate_lanes(lanes_path, mutate)


def merge_order(lanes_data, queue_ids) -> list:
	"""Deterministic queue-order merge sequence (D4 — queue-order merge).

	Pure function of the ledger + the queue's id order: the lane-complete
	items, in QUEUE order — never in completion order.  Re-running with the
	same inputs always yields the same sequence, so the work-branch history
	is reproducible regardless of lane timing.
	"""
	lanes = (lanes_data or {}).get("lanes", {})
	return [
		qid for qid in queue_ids
		if lanes.get(str(qid), {}).get("status") == "lane-complete"
	]


def flush_summary(lanes_data) -> dict:
	"""Deterministic end-of-run flush grouping over the lane ledger (D5/D4).

	Returns ``{"merged", "demoted", "parked", "claimed"}`` — merged in the
	ledger's recorded merge order; the rest in ledger (claim) order.
	``claimed`` collects still-in-flight lanes (``claimed``/``lane-complete``)
	so a coordinator-death flush names what was left mid-air.  Consumed by
	the /lazy-batch-parallel flush report and /lazy-status lane rows.
	"""
	lanes = (lanes_data or {}).get("lanes", {})
	recorded_order = (lanes_data or {}).get("merge_order", [])
	out = {
		"merged": [
			iid for iid in recorded_order
			if lanes.get(str(iid), {}).get("status") == "merged"
		],
		"demoted": [],
		"parked": [],
		"claimed": [],
	}
	for iid, lane in lanes.items():
		status = lane.get("status") if isinstance(lane, dict) else None
		if status == "demoted":
			out["demoted"].append(iid)
		elif status == "parked":
			out["parked"].append(iid)
		elif status in ("claimed", "lane-complete"):
			out["claimed"].append(iid)
	return out


def merge_lane_branch(repo_root, branch, *, no_ff=True) -> dict:
	"""Merge a lane branch into the CURRENT branch (the work branch) — D4.

	Coordinator-only; callers hold the global lock and have verified fencing
	for the item first.  On ANY merge failure the merge is ABORTED so the
	work branch is never left with a half-merged/conflicted tree, and the
	lane branch is NEVER deleted (preserved for salvage / the demotion
	record / the retro's false-`independent` audit).

	Returns ``{"merged": bool, "conflict": bool, "aborted": bool}`` (+ a
	trailing ``detail`` excerpt on failure).  ``no_ff=True`` (default) keeps
	one merge commit per lane so the queue-order landing is auditable in
	``git log --merges --first-parent``.
	"""
	args = ["git", "-C", str(repo_root), "merge"]
	if no_ff:
		args.append("--no-ff")
	args += ["--no-edit", str(branch)]
	r = subprocess.run(args, capture_output=True, text=True)
	if r.returncode == 0:
		return {"merged": True, "conflict": False, "aborted": False}
	# Conflict (or any failure): abort back to a clean tree. `merge --abort`
	# exits non-zero when no merge is in progress (e.g. the merge failed
	# before starting) — tolerated, the tree is already clean in that case.
	subprocess.run(
		["git", "-C", str(repo_root), "merge", "--abort"],
		capture_output=True, text=True,
	)
	return {
		"merged": False,
		"conflict": True,
		"aborted": True,
		"detail": (r.stdout + r.stderr)[-400:],
	}


def effective_lanes(requested, shardable_count, pool_size) -> int:
	"""D6: effective lanes = min(requested N, shardable count, pool_size)."""
	return max(0, min(int(requested), int(shardable_count), int(pool_size)))


def lane_budget_slice(remaining_parent, max_cycles, lanes) -> int:
	"""D6: per-lane ceiling slice = min(remaining_parent, ceil(max_cycles/lanes)).

	The parent ``max_cycles`` is the aggregate SSOT; the slice rides each lane
	marker's own ``max_cycles`` so a runaway lane self-limits even if the
	coordinator dies.  Zero/exhausted inputs floor at 0 (never divide by 0).
	"""
	remaining_parent = int(remaining_parent)
	lanes = int(lanes)
	if lanes <= 0 or remaining_parent <= 0:
		return 0
	ceil_share = -(-int(max_cycles) // lanes)
	return max(0, min(remaining_parent, ceil_share))


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

def run_smoke_tests() -> int:
	"""Build fixtures in a temp dir and assert coordination contracts.

	Each fixture is wrapped in try/except so a contract violation records FAIL
	rather than crashing the harness.
	"""
	import tempfile

	failures: list[str] = []

	with tempfile.TemporaryDirectory(prefix="lazy-coord-fixtures-") as td:
		td_path = Path(td)

		# -------------------------------------------------------------------
		# Fixture 1: lease-ops-dont-perturb-queue
		#
		# Lease operations must touch ONLY leases.json — a sibling queue.json
		# must be byte-for-byte unchanged after acquire_lease.
		# -------------------------------------------------------------------
		fix1_name = "lease-ops-dont-perturb-queue"
		fix1_ok = True
		try:
			fix1_dir = td_path / "fix1"
			fix1_dir.mkdir()
			leases_path_1 = fix1_dir / "leases.json"
			leases_path_1.write_text(json.dumps({}), encoding="utf-8")
			queue_path_1 = fix1_dir / "queue.json"
			queue_sentinel = '{"queue": [{"id": "feat-x", "name": "X", "spec_dir": "feat-x"}]}\n'
			queue_path_1.write_text(queue_sentinel, encoding="utf-8")
			now_1 = 1_000_000.0
			try:
				acquire_lease(leases_path_1, 500, os.getpid(), "wt-00", 300, now=now_1)
			except NotImplementedError:
				failures.append(f"[{fix1_name}] FAIL: acquire_lease raised NotImplementedError")
				fix1_ok = False
			after_bytes = queue_path_1.read_text(encoding="utf-8")
			if fix1_ok and after_bytes != queue_sentinel:
				failures.append(
					f"[{fix1_name}] FAIL: queue.json was mutated by acquire_lease "
					f"(got {after_bytes!r})"
				)
				fix1_ok = False
		except Exception as exc:
			failures.append(f"[{fix1_name}] FAIL: unexpected exception: {exc}")
			fix1_ok = False
		print(f"  {'PASS' if fix1_ok else 'FAIL'} [{fix1_name}]")

		# -------------------------------------------------------------------
		# Fixture 2: no-double-claim
		#
		# If wi_id already has a live (non-expired) lease in leases.json,
		# acquire_lease must return None.
		# -------------------------------------------------------------------
		fix2_name = "no-double-claim"
		fix2_ok = True
		try:
			fix2_dir = td_path / "fix2"
			fix2_dir.mkdir()
			leases_path_2 = fix2_dir / "leases.json"
			now_2 = 2_000_000.0
			ts_2 = datetime.fromtimestamp(now_2, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
			seed_2 = {
				"501": {
					"worker_pid": 9999,
					"worktree_slot": "wt-00",
					"term_token": 1,
					"heartbeat_timestamp": ts_2,
					"ttl_seconds": 300,
				}
			}
			leases_path_2.write_text(json.dumps(seed_2), encoding="utf-8")
			try:
				result_2 = acquire_lease(
					leases_path_2, 501, os.getpid(), "wt-00", 300, now=now_2
				)
				if result_2 is not None:
					failures.append(
						f"[{fix2_name}] FAIL: expected None (no double-claim), "
						f"got {result_2!r}"
					)
					fix2_ok = False
			except NotImplementedError:
				failures.append(f"[{fix2_name}] FAIL: acquire_lease raised NotImplementedError")
				fix2_ok = False
		except Exception as exc:
			failures.append(f"[{fix2_name}] FAIL: unexpected exception: {exc}")
			fix2_ok = False
		print(f"  {'PASS' if fix2_ok else 'FAIL'} [{fix2_name}]")

		# -------------------------------------------------------------------
		# Fixture 3: reclamation
		#
		# A lease whose heartbeat is old (heartbeat_epoch + ttl < now) must be
		# reclaimed: removed from leases.json and its slot dir scrubbed.
		# -------------------------------------------------------------------
		fix3_name = "reclamation"
		fix3_ok = True
		try:
			fix3_dir = td_path / "fix3"
			fix3_dir.mkdir()
			pool_dir_3 = fix3_dir / "pool"
			pool_dir_3.mkdir()
			leases_path_3 = fix3_dir / "leases.json"
			old_epoch_3 = 1_000_000.0
			ttl_3 = 60
			ts_old_3 = datetime.fromtimestamp(old_epoch_3, tz=timezone.utc).strftime(
				"%Y-%m-%dT%H:%M:%SZ"
			)
			seed_3 = {
				"502": {
					"worker_pid": 8888,
					"worktree_slot": "wt-01",
					"term_token": 2,
					"heartbeat_timestamp": ts_old_3,
					"ttl_seconds": ttl_3,
				}
			}
			leases_path_3.write_text(json.dumps(seed_3), encoding="utf-8")
			slot_dir_3 = pool_dir_3 / "wt-01"
			slot_dir_3.mkdir()
			now_3 = old_epoch_3 + 9999  # well past expiry
			try:
				reclaimed_3 = reclaim_expired(leases_path_3, pool_dir_3, now=now_3)
				# Must include "502"
				if "502" not in reclaimed_3:
					failures.append(
						f"[{fix3_name}] FAIL: '502' not in reclaimed list {reclaimed_3!r}"
					)
					fix3_ok = False
				# leases.json must no longer have "502"
				remaining_3 = json.loads(leases_path_3.read_text(encoding="utf-8"))
				if "502" in remaining_3:
					failures.append(
						f"[{fix3_name}] FAIL: '502' still present in leases.json after reclaim"
					)
					fix3_ok = False
				# slot dir must have been scrubbed
				if slot_dir_3.exists():
					failures.append(
						f"[{fix3_name}] FAIL: slot dir {slot_dir_3} still exists after reclaim"
					)
					fix3_ok = False
			except NotImplementedError:
				failures.append(f"[{fix3_name}] FAIL: reclaim_expired raised NotImplementedError")
				fix3_ok = False
		except Exception as exc:
			failures.append(f"[{fix3_name}] FAIL: unexpected exception: {exc}")
			fix3_ok = False
		print(f"  {'PASS' if fix3_ok else 'FAIL'} [{fix3_name}]")

		# -------------------------------------------------------------------
		# Fixture 4: fencing
		#
		# verify_fencing with the wrong term_token must raise FencingError.
		# -------------------------------------------------------------------
		fix4_name = "fencing"
		fix4_ok = True
		try:
			fix4_dir = td_path / "fix4"
			fix4_dir.mkdir()
			leases_path_4 = fix4_dir / "leases.json"
			now_4 = 3_000_000.0
			ts_4 = datetime.fromtimestamp(now_4, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
			seed_4 = {
				"503": {
					"worker_pid": 7777,
					"worktree_slot": "wt-02",
					"term_token": 5,
					"heartbeat_timestamp": ts_4,
					"ttl_seconds": 300,
				}
			}
			leases_path_4.write_text(json.dumps(seed_4), encoding="utf-8")
			try:
				# expected_token=4, but lease has term_token=5 → must raise FencingError
				verify_fencing(leases_path_4, 503, 4)
				# If we get here, no exception was raised — that's a failure
				failures.append(
					f"[{fix4_name}] FAIL: verify_fencing did not raise FencingError "
					"for wrong term_token"
				)
				fix4_ok = False
			except FencingError:
				pass  # correct: the exception was raised as expected
			except NotImplementedError:
				failures.append(f"[{fix4_name}] FAIL: verify_fencing raised NotImplementedError")
				fix4_ok = False
		except Exception as exc:
			failures.append(f"[{fix4_name}] FAIL: unexpected exception: {exc}")
			fix4_ok = False
		print(f"  {'PASS' if fix4_ok else 'FAIL'} [{fix4_name}]")

		# -------------------------------------------------------------------
		# Fixture 5: mkdir-mutual-exclusion
		#
		# The second acquire_lock call must raise TimeoutError because the
		# lock directory is already held (exists from the first call).
		# -------------------------------------------------------------------
		fix5_name = "mkdir-mutual-exclusion"
		fix5_ok = True
		try:
			fix5_dir = td_path / "fix5"
			fix5_dir.mkdir()
			lock_dir_5 = fix5_dir / "global.lock.d"
			# First acquire — must succeed (creates the dir)
			try:
				acquire_lock(lock_dir_5)
			except NotImplementedError:
				failures.append(
					f"[{fix5_name}] FAIL: first acquire_lock raised NotImplementedError"
				)
				fix5_ok = False
			if fix5_ok:
				# Second acquire — lock dir is still held; must raise TimeoutError
				try:
					acquire_lock(lock_dir_5, timeout=0.3)
					failures.append(
						f"[{fix5_name}] FAIL: second acquire_lock did not raise TimeoutError"
					)
					fix5_ok = False
				except TimeoutError:
					pass  # correct
				except NotImplementedError:
					failures.append(
						f"[{fix5_name}] FAIL: second acquire_lock raised NotImplementedError"
					)
					fix5_ok = False
		except Exception as exc:
			failures.append(f"[{fix5_name}] FAIL: unexpected exception: {exc}")
			fix5_ok = False
		print(f"  {'PASS' if fix5_ok else 'FAIL'} [{fix5_name}]")

		# -------------------------------------------------------------------
		# Fixture 6: claim-shardable-conservative
		# (parallel-worktree-batch-execution Phase 1, D3-A)
		#
		# Only dep-ready ∧ independent:true ∧ lease-free candidates are claimed;
		# every hold is named with its reason; a missing/falsy key is HELD
		# (conservative by construction); input (queue) order is preserved; the
		# predicate is READ-ONLY (leases.json byte-unchanged).
		# -------------------------------------------------------------------
		fix6_name = "claim-shardable-conservative"
		fix6_ok = True
		try:
			fix6_dir = td_path / "fix6"
			fix6_dir.mkdir()
			leases_path_6 = fix6_dir / "leases.json"
			now_6 = 4_000_000.0
			ts_6 = datetime.fromtimestamp(now_6, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
			seed_6 = {
				"feat-leased": {
					"worker_pid": 1111,
					"worktree_slot": "wt-00",
					"term_token": 1,
					"heartbeat_timestamp": ts_6,
					"ttl_seconds": 300,
				}
			}
			leases_path_6.write_text(json.dumps(seed_6), encoding="utf-8")
			leases_bytes_6 = leases_path_6.read_bytes()
			candidates_6 = [
				{"id": "feat-a", "dep_ready": True, "independent": True},
				{"id": "feat-depwait", "dep_ready": False, "independent": True},
				{"id": "feat-unmarked", "dep_ready": True, "independent": False},
				{"id": "feat-leased", "dep_ready": True, "independent": True},
				{"id": "feat-b", "dep_ready": True, "independent": True},
				{"id": "feat-nokeys"},  # missing keys ⇒ held (conservative)
			]
			result_6 = claim_shardable(candidates_6, leases_path_6, now=now_6)
			if result_6.get("claimed") != ["feat-a", "feat-b"]:
				failures.append(
					f"[{fix6_name}] FAIL: claimed must be exactly ['feat-a', 'feat-b'] "
					f"in queue order, got {result_6.get('claimed')!r}"
				)
				fix6_ok = False
			held_6 = {h["id"]: h["reason"] for h in result_6.get("held", [])}
			expect_held_6 = {
				"feat-depwait": "dep-unready",
				"feat-unmarked": "no-independent-marker",
				"feat-leased": "live-lease",
				"feat-nokeys": "dep-unready",
			}
			if held_6 != expect_held_6:
				failures.append(
					f"[{fix6_name}] FAIL: held reasons wrong: {held_6!r} != {expect_held_6!r}"
				)
				fix6_ok = False
			if leases_path_6.read_bytes() != leases_bytes_6:
				failures.append(
					f"[{fix6_name}] FAIL: claim_shardable must be READ-ONLY over leases.json"
				)
				fix6_ok = False
			# An expired lease is NOT a live lease — the candidate is claimable.
			result_6b = claim_shardable(
				[{"id": "feat-leased", "dep_ready": True, "independent": True}],
				leases_path_6, now=now_6 + 9999,
			)
			if result_6b.get("claimed") != ["feat-leased"]:
				failures.append(
					f"[{fix6_name}] FAIL: expired lease must not hold the candidate, "
					f"got {result_6b!r}"
				)
				fix6_ok = False
		except Exception as exc:
			failures.append(f"[{fix6_name}] FAIL: unexpected exception: {exc!r}")
			fix6_ok = False
		print(f"  {'PASS' if fix6_ok else 'FAIL'} [{fix6_name}]")

		# -------------------------------------------------------------------
		# Fixture 7: lanes-ledger-lifecycle
		# (parallel-worktree-batch-execution Phase 1, D7)
		#
		# lanes.json (sibling of leases.json, coordinator-owned) records claims,
		# parks, demotions, and merges atomically under the global lock; a
		# sibling queue.json is byte-unchanged by every ledger write; the lane
		# branch is preserved on the demoted entry.
		# -------------------------------------------------------------------
		fix7_name = "lanes-ledger-lifecycle"
		fix7_ok = True
		try:
			fix7_dir = td_path / "fix7"
			fix7_dir.mkdir()
			lanes_path_7 = fix7_dir / "lanes.json"
			queue_path_7 = fix7_dir / "queue.json"
			queue_sentinel_7 = '{"queue": [{"id": "feat-a"}, {"id": "feat-b"}]}\n'
			queue_path_7.write_text(queue_sentinel_7, encoding="utf-8")
			now_7 = 5_000_000.0
			ledger_record_claim(lanes_path_7, "feat-a", "wt-00", "lane/feat-a", now=now_7)
			ledger_record_claim(lanes_path_7, "feat-b", "wt-01", "lane/feat-b", now=now_7)
			ledger_record_park(
				lanes_path_7, "feat-b", "needs-input",
				ported_to="docs/features/feat-b/NEEDS_INPUT.md", now=now_7 + 60,
			)
			ledger_record_lane_complete(lanes_path_7, "feat-a", now=now_7 + 90)
			ledger_record_merge(lanes_path_7, "feat-a", now=now_7 + 120)
			ledger_record_demotion(
				lanes_path_7, "feat-a", "merge-conflict: src/mixer.rs", now=now_7 + 150,
			)
			data_7 = read_lanes(lanes_path_7)
			lane_a = data_7["lanes"].get("feat-a", {})
			lane_b = data_7["lanes"].get("feat-b", {})
			if lane_b.get("status") != "parked" or lane_b.get("sentinel_kind") != "needs-input":
				failures.append(f"[{fix7_name}] FAIL: parked lane wrong: {lane_b!r}")
				fix7_ok = False
			if lane_b.get("branch") != "lane/feat-b" or lane_b.get("slot") != "wt-01":
				failures.append(
					f"[{fix7_name}] FAIL: park must preserve branch+slot: {lane_b!r}"
				)
				fix7_ok = False
			if lane_a.get("status") != "demoted" or lane_a.get("demoted") != "serial":
				failures.append(f"[{fix7_name}] FAIL: demoted lane wrong: {lane_a!r}")
				fix7_ok = False
			if lane_a.get("branch") != "lane/feat-a":
				failures.append(
					f"[{fix7_name}] FAIL: demotion must preserve the lane branch: {lane_a!r}"
				)
				fix7_ok = False
			if data_7.get("merge_order") != ["feat-a"]:
				failures.append(
					f"[{fix7_name}] FAIL: merge_order must record the merge: "
					f"{data_7.get('merge_order')!r}"
				)
				fix7_ok = False
			if queue_path_7.read_text(encoding="utf-8") != queue_sentinel_7:
				failures.append(
					f"[{fix7_name}] FAIL: ledger writes must NEVER touch queue.json"
				)
				fix7_ok = False
			if (fix7_dir / "global.lock.d").exists():
				failures.append(
					f"[{fix7_name}] FAIL: ledger writes must release the global lock"
				)
				fix7_ok = False
		except Exception as exc:
			failures.append(f"[{fix7_name}] FAIL: unexpected exception: {exc!r}")
			fix7_ok = False
		print(f"  {'PASS' if fix7_ok else 'FAIL'} [{fix7_name}]")

		# -------------------------------------------------------------------
		# Fixture 8: merge-order-deterministic
		# (parallel-worktree-batch-execution Phase 1, D4 queue-order merge)
		#
		# Lanes completing OUT of queue order still merge IN queue order —
		# merge_order() is a pure function of the ledger + queue ids, never of
		# completion timing.
		# -------------------------------------------------------------------
		fix8_name = "merge-order-deterministic"
		fix8_ok = True
		try:
			fix8_dir = td_path / "fix8"
			fix8_dir.mkdir()
			lanes_path_8 = fix8_dir / "lanes.json"
			now_8 = 6_000_000.0
			for iid, slot in (("feat-a", "wt-00"), ("feat-b", "wt-01"), ("feat-c", "wt-02")):
				ledger_record_claim(lanes_path_8, iid, slot, f"lane/{iid}", now=now_8)
			# Completion order: c, then a (b still running) — queue order: a, b, c.
			ledger_record_lane_complete(lanes_path_8, "feat-c", now=now_8 + 10)
			ledger_record_lane_complete(lanes_path_8, "feat-a", now=now_8 + 20)
			order_8 = merge_order(read_lanes(lanes_path_8), ["feat-a", "feat-b", "feat-c"])
			if order_8 != ["feat-a", "feat-c"]:
				failures.append(
					f"[{fix8_name}] FAIL: merge order must be queue order over "
					f"lane-complete items, got {order_8!r}"
				)
				fix8_ok = False
			# b completes later → order recomputes to full queue order.
			ledger_record_lane_complete(lanes_path_8, "feat-b", now=now_8 + 30)
			order_8b = merge_order(read_lanes(lanes_path_8), ["feat-a", "feat-b", "feat-c"])
			if order_8b != ["feat-a", "feat-b", "feat-c"]:
				failures.append(
					f"[{fix8_name}] FAIL: full merge order wrong: {order_8b!r}"
				)
				fix8_ok = False
		except Exception as exc:
			failures.append(f"[{fix8_name}] FAIL: unexpected exception: {exc!r}")
			fix8_ok = False
		print(f"  {'PASS' if fix8_ok else 'FAIL'} [{fix8_name}]")

		# -------------------------------------------------------------------
		# Fixture 9: budget-arithmetic
		# (parallel-worktree-batch-execution Phase 1, D6 — locked formulas)
		#
		# effective_lanes = min(requested, shardable_count, pool_size);
		# lane_budget_slice = min(remaining_parent, ceil(max_cycles / lanes)),
		# floored at 0; zero/negative lanes never divide.
		# -------------------------------------------------------------------
		fix9_name = "budget-arithmetic"
		fix9_ok = True
		try:
			checks_9 = [
				(effective_lanes(3, 4, 8), 3, "requested bound"),
				(effective_lanes(5, 2, 8), 2, "shardable bound"),
				(effective_lanes(5, 9, 4), 4, "pool bound"),
				(effective_lanes(3, 0, 8), 0, "nothing shardable"),
				(lane_budget_slice(20, 24, 3), 8, "ceil(24/3)=8 <= remaining"),
				(lane_budget_slice(5, 24, 3), 5, "remaining_parent caps the slice"),
				(lane_budget_slice(20, 25, 3), 9, "ceil(25/3)=9"),
				(lane_budget_slice(0, 24, 3), 0, "exhausted parent → 0"),
				(lane_budget_slice(20, 24, 0), 0, "zero lanes → 0 (no division)"),
			]
			for got, want, label in checks_9:
				if got != want:
					failures.append(
						f"[{fix9_name}] FAIL: {label}: got {got!r}, want {want!r}"
					)
					fix9_ok = False
		except Exception as exc:
			failures.append(f"[{fix9_name}] FAIL: unexpected exception: {exc!r}")
			fix9_ok = False
		print(f"  {'PASS' if fix9_ok else 'FAIL'} [{fix9_name}]")

		# -------------------------------------------------------------------
		# Fixture 10: worktree-pool-generalization
		# (parallel-worktree-batch-execution Phase 2, D10)
		#
		# provision_pool/scrub_slot are repo-agnostic: the default scrub keeps
		# the Cognito `p/<wi_id>-<slug>` branch + `origin/main` detach target
		# byte-identically; the lane parameterization produces `lane/<item-id>`
		# and honors an alternate detach target.  lane_branch/lane_pool_dir
		# encode the lane conventions.  Real git repos — no mocks.
		# -------------------------------------------------------------------
		fix10_name = "worktree-pool-generalization"
		fix10_ok = True
		try:
			if lane_branch("feat-a") != "lane/feat-a":
				failures.append(
					f"[{fix10_name}] FAIL: lane_branch wrong: {lane_branch('feat-a')!r}"
				)
				fix10_ok = False
			if lane_pool_dir("/x/repo") != Path("/x/repo-lanes"):
				failures.append(
					f"[{fix10_name}] FAIL: lane_pool_dir must be the sibling "
					f"<repo_root>-lanes dir: {lane_pool_dir('/x/repo')!r}"
				)
				fix10_ok = False

			fix10_dir = td_path / "fix10"
			fix10_dir.mkdir()
			_git_env = dict(os.environ)
			_git_env.update({
				"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "f@x",
				"GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "f@x",
			})

			def _git(cwd, *args):
				return subprocess.run(
					["git", "-C", str(cwd)] + list(args),
					check=True, capture_output=True, env=_git_env,
				)

			import contextlib

			@contextlib.contextmanager
			def _quiet_fds():
				"""Silence inherited-fd subprocess chatter (git checkout/reset)
				so the smoke output stays deterministic (no commit hashes)."""
				sys.stdout.flush()
				sys.stderr.flush()
				saved_out, saved_err = os.dup(1), os.dup(2)
				devnull = os.open(os.devnull, os.O_WRONLY)
				try:
					os.dup2(devnull, 1)
					os.dup2(devnull, 2)
					yield
				finally:
					os.dup2(saved_out, 1)
					os.dup2(saved_err, 2)
					os.close(devnull)
					os.close(saved_out)
					os.close(saved_err)

			origin_10 = fix10_dir / "origin"
			origin_10.mkdir()
			_git(fix10_dir, "init", "-q", "-b", "main", str(origin_10))
			(origin_10 / "f.txt").write_text("one\n", encoding="utf-8")
			_git(origin_10, "add", "f.txt")
			_git(origin_10, "commit", "-q", "-m", "c1")
			_git(origin_10, "branch", "base")
			repo_10 = fix10_dir / "repo"
			_git(fix10_dir, "clone", "-q", str(origin_10), str(repo_10))
			pool_10 = fix10_dir / "repo-lanes"

			with _quiet_fds():
				slots_10 = provision_pool(repo_10, pool_10, 1)
			slot_path_10 = slots_10[0]
			if not (slot_path_10.exists() and slot_path_10.name == "wt-00"):
				failures.append(f"[{fix10_name}] FAIL: provision_pool slot missing")
				fix10_ok = False

			# Default scrub — Cognito conventions byte-identical (p/<wi_id>-<slug>).
			with _quiet_fds():
				scrub_slot(repo_10, pool_10, "wt-00", 42, "fix")
			head_default = subprocess.run(
				["git", "-C", str(slot_path_10), "rev-parse", "--abbrev-ref", "HEAD"],
				capture_output=True, text=True, env=_git_env,
			).stdout.strip()
			if head_default != "p/42-fix":
				failures.append(
					f"[{fix10_name}] FAIL: default scrub branch must be p/42-fix, "
					f"got {head_default!r}"
				)
				fix10_ok = False

			# Lane scrub — branch template + detach target parameterized.
			with _quiet_fds():
				scrub_slot(
					repo_10, pool_10, "wt-00", "feat-x", "ignored-slug",
					branch_template="lane/{wi_id}", detach_target="origin/base",
				)
			head_lane = subprocess.run(
				["git", "-C", str(slot_path_10), "rev-parse", "--abbrev-ref", "HEAD"],
				capture_output=True, text=True, env=_git_env,
			).stdout.strip()
			if head_lane != "lane/feat-x":
				failures.append(
					f"[{fix10_name}] FAIL: lane scrub branch must be lane/feat-x, "
					f"got {head_lane!r}"
				)
				fix10_ok = False
			lane_head_commit = subprocess.run(
				["git", "-C", str(slot_path_10), "rev-parse", "HEAD"],
				capture_output=True, text=True, env=_git_env,
			).stdout.strip()
			base_commit = subprocess.run(
				["git", "-C", str(slot_path_10), "rev-parse", "origin/base"],
				capture_output=True, text=True, env=_git_env,
			).stdout.strip()
			if not lane_head_commit or lane_head_commit != base_commit:
				failures.append(
					f"[{fix10_name}] FAIL: lane scrub must detach from the "
					f"parameterized target origin/base"
				)
				fix10_ok = False
		except Exception as exc:
			failures.append(f"[{fix10_name}] FAIL: unexpected exception: {exc!r}")
			fix10_ok = False
		print(f"  {'PASS' if fix10_ok else 'FAIL'} [{fix10_name}]")

		# -------------------------------------------------------------------
		# Fixture 11: zombie-lane-fenced
		# (parallel-worktree-batch-execution Phase 3 — the zombie-lane
		# fail-safe.)  A lane whose lease was reclaimed and RE-claimed holds a
		# stale term_token: its heartbeat AND its pre-contended-write
		# verify_fencing both raise FencingError, and the zombie's attempts
		# mutate NOTHING (leases.json / lanes.json / a sibling queue.json all
		# byte-unchanged).
		# -------------------------------------------------------------------
		fix11_name = "zombie-lane-fenced"
		fix11_ok = True
		try:
			fix11_dir = td_path / "fix11"
			fix11_dir.mkdir()
			(fix11_dir / "pool").mkdir()
			leases_path_11 = fix11_dir / "leases.json"
			lanes_path_11 = fix11_dir / "lanes.json"
			queue_path_11 = fix11_dir / "queue.json"
			queue_sentinel_11 = '{"queue": [{"id": "feat-z"}]}\n'
			queue_path_11.write_text(queue_sentinel_11, encoding="utf-8")
			now_11 = 7_000_000.0
			# Original lane claims (token 1) and records its claim.
			entry_11 = acquire_lease(leases_path_11, "feat-z", 1234, "wt-00", 60, now=now_11)
			zombie_token = entry_11["term_token"]
			ledger_record_claim(lanes_path_11, "feat-z", "wt-00", "lane/feat-z", now=now_11)
			# The lane goes silent; TTL expires; the coordinator reclaims and
			# the item is re-claimed (token 2).
			reclaim_expired(leases_path_11, fix11_dir / "pool", now=now_11 + 9999)
			entry_11b = acquire_lease(
				leases_path_11, "feat-z", 5678, "wt-01", 60, now=now_11 + 10000,
			)
			if entry_11b is None or entry_11b["term_token"] == zombie_token:
				failures.append(
					f"[{fix11_name}] FAIL: re-claim must mint a NEW term_token, "
					f"got {entry_11b!r}"
				)
				fix11_ok = False
			leases_bytes_11 = leases_path_11.read_bytes()
			lanes_bytes_11 = lanes_path_11.read_bytes()
			# Zombie wakes up with the stale token: heartbeat must raise…
			try:
				heartbeat(leases_path_11, "feat-z", zombie_token, now=now_11 + 10001)
				failures.append(
					f"[{fix11_name}] FAIL: zombie heartbeat with a stale token "
					f"must raise FencingError"
				)
				fix11_ok = False
			except FencingError:
				pass
			# …and the pre-contended-write fencing check must raise too.
			try:
				verify_fencing(leases_path_11, "feat-z", zombie_token)
				failures.append(
					f"[{fix11_name}] FAIL: zombie verify_fencing with a stale "
					f"token must raise FencingError"
				)
				fix11_ok = False
			except FencingError:
				pass
			# Zero shared-state mutation by the zombie's attempts.
			if leases_path_11.read_bytes() != leases_bytes_11:
				failures.append(
					f"[{fix11_name}] FAIL: the zombie's attempts must not mutate "
					f"leases.json"
				)
				fix11_ok = False
			if lanes_path_11.read_bytes() != lanes_bytes_11:
				failures.append(
					f"[{fix11_name}] FAIL: the zombie's attempts must not mutate "
					f"lanes.json"
				)
				fix11_ok = False
			if queue_path_11.read_text(encoding="utf-8") != queue_sentinel_11:
				failures.append(
					f"[{fix11_name}] FAIL: the zombie's attempts must not mutate "
					f"queue.json"
				)
				fix11_ok = False
		except Exception as exc:
			failures.append(f"[{fix11_name}] FAIL: unexpected exception: {exc!r}")
			fix11_ok = False
		print(f"  {'PASS' if fix11_ok else 'FAIL'} [{fix11_name}]")

		# -------------------------------------------------------------------
		# Fixture 12: queue-order-merge-determinism
		# (parallel-worktree-batch-execution Phase 4, D4 — queue-order merge.)
		# Two lanes with DISJOINT edits complete OUT of queue order; the
		# coordinator merges them IN queue order (merge_order over the ledger),
		# and the work-branch history records the merges in queue order —
		# independent of completion timing.
		# -------------------------------------------------------------------
		fix12_name = "queue-order-merge-determinism"
		fix12_ok = True
		try:
			fix12_dir = td_path / "fix12"
			fix12_dir.mkdir()
			_git_env_12 = dict(os.environ)
			_git_env_12.update({
				"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "f@x",
				"GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "f@x",
			})

			def _git12(cwd, *args, check=True):
				return subprocess.run(
					["git", "-C", str(cwd)] + list(args),
					check=check, capture_output=True, text=True, env=_git_env_12,
				)

			work_12 = fix12_dir / "work"
			work_12.mkdir()
			_git12(fix12_dir, "init", "-q", "-b", "main", str(work_12))
			(work_12 / "a.txt").write_text("base-a\n", encoding="utf-8")
			(work_12 / "b.txt").write_text("base-b\n", encoding="utf-8")
			_git12(work_12, "add", ".")
			_git12(work_12, "commit", "-q", "-m", "base")
			# Lane branches with disjoint edits.
			_git12(work_12, "checkout", "-q", "-b", "lane/feat-a")
			(work_12 / "a.txt").write_text("lane-a\n", encoding="utf-8")
			_git12(work_12, "commit", "-q", "-am", "feat-a work")
			_git12(work_12, "checkout", "-q", "main")
			_git12(work_12, "checkout", "-q", "-b", "lane/feat-b")
			(work_12 / "b.txt").write_text("lane-b\n", encoding="utf-8")
			_git12(work_12, "commit", "-q", "-am", "feat-b work")
			_git12(work_12, "checkout", "-q", "main")
			# Ledger: lanes complete OUT of queue order (b first).
			lanes_path_12 = fix12_dir / "lanes.json"
			now_12 = 8_000_000.0
			ledger_record_claim(lanes_path_12, "feat-a", "wt-00", "lane/feat-a", now=now_12)
			ledger_record_claim(lanes_path_12, "feat-b", "wt-01", "lane/feat-b", now=now_12)
			ledger_record_lane_complete(lanes_path_12, "feat-b", now=now_12 + 10)
			ledger_record_lane_complete(lanes_path_12, "feat-a", now=now_12 + 20)
			order_12 = merge_order(read_lanes(lanes_path_12), ["feat-a", "feat-b"])
			if order_12 != ["feat-a", "feat-b"]:
				failures.append(
					f"[{fix12_name}] FAIL: merge order must be queue order, "
					f"got {order_12!r}"
				)
				fix12_ok = False
			for iid in order_12:
				res = merge_lane_branch(work_12, f"lane/{iid}")
				if not res.get("merged") or res.get("conflict"):
					failures.append(
						f"[{fix12_name}] FAIL: disjoint lane {iid} must merge "
						f"cleanly, got {res!r}"
					)
					fix12_ok = False
				else:
					ledger_record_merge(lanes_path_12, iid, now=now_12 + 30)
			# Work-branch history: merge commits in queue order.
			log_12 = _git12(
				work_12, "log", "--merges", "--first-parent", "--reverse",
				"--pretty=%s",
			).stdout.strip().splitlines()
			if len(log_12) != 2 or "lane/feat-a" not in log_12[0] \
					or "lane/feat-b" not in log_12[1]:
				failures.append(
					f"[{fix12_name}] FAIL: work-branch merge history must land "
					f"feat-a then feat-b (queue order), got {log_12!r}"
				)
				fix12_ok = False
			if read_lanes(lanes_path_12).get("merge_order") != ["feat-a", "feat-b"]:
				failures.append(
					f"[{fix12_name}] FAIL: ledger merge_order must record queue "
					f"order"
				)
				fix12_ok = False
			# Both files carry both lanes' edits (nothing lost).
			if (work_12 / "a.txt").read_text() != "lane-a\n" \
					or (work_12 / "b.txt").read_text() != "lane-b\n":
				failures.append(f"[{fix12_name}] FAIL: merged tree must carry both edits")
				fix12_ok = False
		except Exception as exc:
			failures.append(f"[{fix12_name}] FAIL: unexpected exception: {exc!r}")
			fix12_ok = False
		print(f"  {'PASS' if fix12_ok else 'FAIL'} [{fix12_name}]")

		# -------------------------------------------------------------------
		# Fixture 13: conflict-demotes-preserves-lane-branch
		# (parallel-worktree-batch-execution Phase 4, D4 — abort-and-demote.)
		# A manufactured overlapping edit conflicts at merge: the merge is
		# ABORTED (clean tree, no MERGE_HEAD), the item is recorded
		# `demoted: serial` in the ledger, and the lane branch still resolves
		# (preserved for salvage + the false-`independent` marker audit).
		# -------------------------------------------------------------------
		fix13_name = "conflict-demotes-preserves-lane-branch"
		fix13_ok = True
		try:
			fix13_dir = td_path / "fix13"
			fix13_dir.mkdir()
			_git_env_13 = dict(os.environ)
			_git_env_13.update({
				"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "f@x",
				"GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "f@x",
			})

			def _git13(cwd, *args, check=True):
				return subprocess.run(
					["git", "-C", str(cwd)] + list(args),
					check=check, capture_output=True, text=True, env=_git_env_13,
				)

			work_13 = fix13_dir / "work"
			work_13.mkdir()
			_git13(fix13_dir, "init", "-q", "-b", "main", str(work_13))
			(work_13 / "c.txt").write_text("base\n", encoding="utf-8")
			_git13(work_13, "add", ".")
			_git13(work_13, "commit", "-q", "-m", "base")
			_git13(work_13, "checkout", "-q", "-b", "lane/feat-x")
			(work_13 / "c.txt").write_text("lane-x\n", encoding="utf-8")
			_git13(work_13, "commit", "-q", "-am", "feat-x work")
			_git13(work_13, "checkout", "-q", "main")
			(work_13 / "c.txt").write_text("mainline\n", encoding="utf-8")
			_git13(work_13, "commit", "-q", "-am", "overlapping mainline edit")
			res_13 = merge_lane_branch(work_13, "lane/feat-x")
			if res_13.get("merged") or not res_13.get("conflict") \
					or not res_13.get("aborted"):
				failures.append(
					f"[{fix13_name}] FAIL: overlapping merge must report "
					f"conflict+aborted, got {res_13!r}"
				)
				fix13_ok = False
			status_13 = _git13(work_13, "status", "--porcelain").stdout.strip()
			if status_13:
				failures.append(
					f"[{fix13_name}] FAIL: abort must leave a CLEAN tree, got "
					f"{status_13!r}"
				)
				fix13_ok = False
			if (work_13 / ".git" / "MERGE_HEAD").exists():
				failures.append(
					f"[{fix13_name}] FAIL: abort must remove MERGE_HEAD"
				)
				fix13_ok = False
			lanes_path_13 = fix13_dir / "lanes.json"
			ledger_record_claim(lanes_path_13, "feat-x", "wt-00", "lane/feat-x",
			                    now=9_000_000.0)
			ledger_record_demotion(lanes_path_13, "feat-x",
			                       "merge-conflict: c.txt", now=9_000_060.0)
			lane_x = read_lanes(lanes_path_13)["lanes"]["feat-x"]
			if lane_x.get("demoted") != "serial" or lane_x.get("status") != "demoted":
				failures.append(
					f"[{fix13_name}] FAIL: ledger must record demoted: serial, "
					f"got {lane_x!r}"
				)
				fix13_ok = False
			branch_check_13 = _git13(
				work_13, "rev-parse", "--verify", "lane/feat-x", check=False,
			)
			if branch_check_13.returncode != 0:
				failures.append(
					f"[{fix13_name}] FAIL: the lane branch must be PRESERVED "
					f"after demotion"
				)
				fix13_ok = False
		except Exception as exc:
			failures.append(f"[{fix13_name}] FAIL: unexpected exception: {exc!r}")
			fix13_ok = False
		print(f"  {'PASS' if fix13_ok else 'FAIL'} [{fix13_name}]")

		# -------------------------------------------------------------------
		# Fixture 14: park-isolates-siblings
		# (parallel-worktree-batch-execution Phase 5, D5-A.)  One lane parks
		# on a sentinel while its sibling proceeds to merged; flush_summary
		# groups both correctly and the parked lane's branch/slot fields are
		# preserved (nothing lost — the sentinel port target is recorded).
		# -------------------------------------------------------------------
		fix14_name = "park-isolates-siblings"
		fix14_ok = True
		try:
			fix14_dir = td_path / "fix14"
			fix14_dir.mkdir()
			lanes_path_14 = fix14_dir / "lanes.json"
			now_14 = 10_000_000.0
			ledger_record_claim(lanes_path_14, "feat-a", "wt-00", "lane/feat-a", now=now_14)
			ledger_record_claim(lanes_path_14, "feat-b", "wt-01", "lane/feat-b", now=now_14)
			ledger_record_claim(lanes_path_14, "feat-c", "wt-02", "lane/feat-c", now=now_14)
			# feat-b halts on NEEDS_INPUT.md → parked; siblings continue.
			ledger_record_park(
				lanes_path_14, "feat-b", "needs-input",
				ported_to="docs/features/feat-b/NEEDS_INPUT.md", now=now_14 + 30,
			)
			ledger_record_lane_complete(lanes_path_14, "feat-a", now=now_14 + 60)
			ledger_record_merge(lanes_path_14, "feat-a", now=now_14 + 90)
			data_14 = read_lanes(lanes_path_14)
			summary_14 = flush_summary(data_14)
			if summary_14.get("merged") != ["feat-a"] \
					or summary_14.get("parked") != ["feat-b"] \
					or summary_14.get("demoted") != [] \
					or summary_14.get("claimed") != ["feat-c"]:
				failures.append(
					f"[{fix14_name}] FAIL: flush groups wrong: {summary_14!r}"
				)
				fix14_ok = False
			lane_b_14 = data_14["lanes"]["feat-b"]
			if lane_b_14.get("branch") != "lane/feat-b" \
					or lane_b_14.get("slot") != "wt-01" \
					or lane_b_14.get("sentinel_ported_to") != \
					"docs/features/feat-b/NEEDS_INPUT.md":
				failures.append(
					f"[{fix14_name}] FAIL: park must preserve branch/slot and "
					f"record the port target: {lane_b_14!r}"
				)
				fix14_ok = False
		except Exception as exc:
			failures.append(f"[{fix14_name}] FAIL: unexpected exception: {exc!r}")
			fix14_ok = False
		print(f"  {'PASS' if fix14_ok else 'FAIL'} [{fix14_name}]")

		# -------------------------------------------------------------------
		# Fixture 15: coordinator-death-recovery
		# (parallel-worktree-batch-execution Phase 5.)  The coordinator dies
		# mid-run: lane leases stop heartbeating.  On the next invocation,
		# reclaim_expired (TTL) clears the leases and scrubs the slot dirs —
		# while lanes.json (the audit trail) is left INTACT, and a re-claim
		# mints a strictly-greater fencing token (no manual queue repair).
		# -------------------------------------------------------------------
		fix15_name = "coordinator-death-recovery"
		fix15_ok = True
		try:
			fix15_dir = td_path / "fix15"
			fix15_dir.mkdir()
			pool_15 = fix15_dir / "pool"
			pool_15.mkdir()
			leases_path_15 = fix15_dir / "leases.json"
			lanes_path_15 = fix15_dir / "lanes.json"
			now_15 = 11_000_000.0
			for iid, slot in (("feat-a", "wt-00"), ("feat-b", "wt-01")):
				acquire_lease(leases_path_15, iid, 4242, slot, 60, now=now_15)
				ledger_record_claim(lanes_path_15, iid, slot, f"lane/{iid}", now=now_15)
				(pool_15 / slot).mkdir()
			lanes_bytes_15 = lanes_path_15.read_bytes()
			# Coordinator dead: TTLs lapse; next invocation reclaims.
			reclaimed_15 = sorted(
				reclaim_expired(leases_path_15, pool_15, now=now_15 + 9999)
			)
			if reclaimed_15 != ["feat-a", "feat-b"]:
				failures.append(
					f"[{fix15_name}] FAIL: both dead lanes must reclaim, got "
					f"{reclaimed_15!r}"
				)
				fix15_ok = False
			if (pool_15 / "wt-00").exists() or (pool_15 / "wt-01").exists():
				failures.append(
					f"[{fix15_name}] FAIL: reclaim must scrub the slot dirs"
				)
				fix15_ok = False
			if json.loads(leases_path_15.read_text(encoding="utf-8")) != {}:
				failures.append(
					f"[{fix15_name}] FAIL: leases.json must be empty after reclaim"
				)
				fix15_ok = False
			if lanes_path_15.read_bytes() != lanes_bytes_15:
				failures.append(
					f"[{fix15_name}] FAIL: reclaim must leave the lanes.json "
					f"audit trail INTACT"
				)
				fix15_ok = False
			# Recovery continues: a fresh claim fences out the dead lane.
			entry_15 = acquire_lease(
				leases_path_15, "feat-a", 4343, "wt-00", 60, now=now_15 + 10000,
			)
			if entry_15 is None or entry_15["term_token"] <= 1:
				failures.append(
					f"[{fix15_name}] FAIL: post-recovery re-claim must mint a "
					f"strictly greater token, got {entry_15!r}"
				)
				fix15_ok = False
		except Exception as exc:
			failures.append(f"[{fix15_name}] FAIL: unexpected exception: {exc!r}")
			fix15_ok = False
		print(f"  {'PASS' if fix15_ok else 'FAIL'} [{fix15_name}]")

		# -------------------------------------------------------------------
		# Fixture 16: lock-owner-metadata-written
		# (coord-lock-no-stale-reclaim, Fix Scope item 1.)  A successful
		# acquire_lock writes owner.json {pid, kernel_start_time, acquired_at}
		# into the lock dir; release_lock removes it (rmdir succeeds — the
		# dir is genuinely empty again, not left non-empty by the metadata file).
		# -------------------------------------------------------------------
		fix16_name = "lock-owner-metadata-written"
		fix16_ok = True
		try:
			fix16_dir = td_path / "fix16"
			fix16_dir.mkdir()
			lock_dir_16 = fix16_dir / "global.lock.d"
			acquire_lock(lock_dir_16, now=12_000_000.0)
			owner_path_16 = lock_dir_16 / "owner.json"
			if not owner_path_16.exists():
				failures.append(
					f"[{fix16_name}] FAIL: acquire_lock must write owner.json"
				)
				fix16_ok = False
			else:
				owner_16 = json.loads(owner_path_16.read_text(encoding="utf-8"))
				if owner_16.get("pid") != os.getpid():
					failures.append(
						f"[{fix16_name}] FAIL: owner.json pid must be os.getpid(), "
						f"got {owner_16!r}"
					)
					fix16_ok = False
				if "kernel_start_time" not in owner_16 or "acquired_at" not in owner_16:
					failures.append(
						f"[{fix16_name}] FAIL: owner.json must carry "
						f"kernel_start_time + acquired_at, got {owner_16!r}"
					)
					fix16_ok = False
				if owner_16.get("acquired_at") != _now_iso(12_000_000.0):
					failures.append(
						f"[{fix16_name}] FAIL: acquired_at must reflect the "
						f"injected now, got {owner_16!r}"
					)
					fix16_ok = False
			release_lock(lock_dir_16)
			if lock_dir_16.exists():
				failures.append(
					f"[{fix16_name}] FAIL: release_lock must remove the lock dir "
					f"(owner.json must not block rmdir)"
				)
				fix16_ok = False
		except Exception as exc:
			failures.append(f"[{fix16_name}] FAIL: unexpected exception: {exc!r}")
			fix16_ok = False
		print(f"  {'PASS' if fix16_ok else 'FAIL'} [{fix16_name}]")

		# -------------------------------------------------------------------
		# Fixture 17: stale-lock-dead-holder-reclaimed
		# (coord-lock-no-stale-reclaim, Fix Scope item 2 + Tests (a).)  A lock
		# dir held by a CONFIRMED-dead pid is reclaimed and re-acquired within
		# one acquire_lock call — no TimeoutError, no manual rmdir.
		# -------------------------------------------------------------------
		fix17_name = "stale-lock-dead-holder-reclaimed"
		fix17_ok = True
		try:
			fix17_dir = td_path / "fix17"
			fix17_dir.mkdir()
			lock_dir_17 = fix17_dir / "global.lock.d"
			lock_dir_17.mkdir()
			(lock_dir_17 / "owner.json").write_text(
				json.dumps({
					"pid": 999_017, "kernel_start_time": 111.0,
					"acquired_at": "2026-01-01T00:00:00Z",
				}),
				encoding="utf-8",
			)

			def _dead_status_17(pid):
				return "dead"

			try:
				acquire_lock(
					lock_dir_17, timeout=2.0, poll=0.01,
					pid_status_fn=_dead_status_17,
				)
			except TimeoutError:
				failures.append(
					f"[{fix17_name}] FAIL: acquire_lock must reclaim a "
					f"confirmed-dead holder within one call, got TimeoutError"
				)
				fix17_ok = False
			if fix17_ok:
				new_owner_17 = json.loads(
					(lock_dir_17 / "owner.json").read_text(encoding="utf-8")
				)
				if new_owner_17.get("pid") != os.getpid():
					failures.append(
						f"[{fix17_name}] FAIL: the reclaiming call must stamp its "
						f"OWN pid into a fresh owner.json, got {new_owner_17!r}"
					)
					fix17_ok = False
				release_lock(lock_dir_17)
		except Exception as exc:
			failures.append(f"[{fix17_name}] FAIL: unexpected exception: {exc!r}")
			fix17_ok = False
		print(f"  {'PASS' if fix17_ok else 'FAIL'} [{fix17_name}]")

		# -------------------------------------------------------------------
		# Fixture 18: live-holder-lock-still-times-out
		# (coord-lock-no-stale-reclaim, Fix Scope item 3 + Tests (b).)  A lock
		# whose owner.json pid is alive with a MATCHING kernel_start_time is a
		# genuinely live holder — acquire_lock must still raise TimeoutError,
		# never reclaim it.
		# -------------------------------------------------------------------
		fix18_name = "live-holder-lock-still-times-out"
		fix18_ok = True
		try:
			fix18_dir = td_path / "fix18"
			fix18_dir.mkdir()
			lock_dir_18 = fix18_dir / "global.lock.d"
			lock_dir_18.mkdir()
			(lock_dir_18 / "owner.json").write_text(
				json.dumps({
					"pid": 999_018, "kernel_start_time": 222.0,
					"acquired_at": "2026-01-01T00:00:00Z",
				}),
				encoding="utf-8",
			)

			def _alive_status_18(pid):
				return "alive"

			def _matching_start_18(pid):
				return 222.0

			try:
				acquire_lock(
					lock_dir_18, timeout=0.3, poll=0.02,
					pid_status_fn=_alive_status_18,
					kernel_start_time_fn=_matching_start_18,
				)
				failures.append(
					f"[{fix18_name}] FAIL: acquire_lock must NOT reclaim a live "
					f"holder — expected TimeoutError"
				)
				fix18_ok = False
			except TimeoutError:
				pass  # correct
			if not (lock_dir_18 / "owner.json").exists():
				failures.append(
					f"[{fix18_name}] FAIL: the live holder's owner.json must "
					f"survive an ambiguous/live observation"
				)
				fix18_ok = False
		except Exception as exc:
			failures.append(f"[{fix18_name}] FAIL: unexpected exception: {exc!r}")
			fix18_ok = False
		print(f"  {'PASS' if fix18_ok else 'FAIL'} [{fix18_name}]")

		# -------------------------------------------------------------------
		# Fixture 19: pid-reuse-reclaimed
		# (coord-lock-no-stale-reclaim, D2 + Tests (c).)  The recorded pid is
		# ALIVE but its live kernel_start_time does not match the recorded
		# one (the pid was reused by an unrelated process) — CONFIRMED dead,
		# reclaimed.
		# -------------------------------------------------------------------
		fix19_name = "pid-reuse-reclaimed"
		fix19_ok = True
		try:
			fix19_dir = td_path / "fix19"
			fix19_dir.mkdir()
			lock_dir_19 = fix19_dir / "global.lock.d"
			lock_dir_19.mkdir()
			(lock_dir_19 / "owner.json").write_text(
				json.dumps({
					"pid": 999_019, "kernel_start_time": 111.0,
					"acquired_at": "2026-01-01T00:00:00Z",
				}),
				encoding="utf-8",
			)

			def _alive_status_19(pid):
				return "alive"

			def _mismatched_start_19(pid):
				return 333.0  # different process now holds this (reused) pid

			try:
				acquire_lock(
					lock_dir_19, timeout=2.0, poll=0.01,
					pid_status_fn=_alive_status_19,
					kernel_start_time_fn=_mismatched_start_19,
				)
			except TimeoutError:
				failures.append(
					f"[{fix19_name}] FAIL: a reused (mismatched-start-time) pid "
					f"must be reclaimed, got TimeoutError"
				)
				fix19_ok = False
			if fix19_ok:
				release_lock(lock_dir_19)
		except Exception as exc:
			failures.append(f"[{fix19_name}] FAIL: unexpected exception: {exc!r}")
			fix19_ok = False
		print(f"  {'PASS' if fix19_ok else 'FAIL'} [{fix19_name}]")

		# -------------------------------------------------------------------
		# Fixture 20: metadata-less-stale-dir-grace-age
		# (coord-lock-no-stale-reclaim, Fix Scope item 2 grace-age fallback +
		# Tests (e).)  A lock dir with NO owner.json (holder died between
		# mkdir and the metadata write) is reclaimed only once it is OLDER
		# than the grace age; a fresh metadata-less dir is ambiguous and must
		# NOT be reclaimed.
		# -------------------------------------------------------------------
		fix20_name = "metadata-less-stale-dir-grace-age"
		fix20_ok = True
		try:
			fix20_dir = td_path / "fix20"
			fix20_dir.mkdir()

			# (i) Old bare dir (backdated mtime) past a tiny grace -> reclaimed.
			lock_dir_20a = fix20_dir / "old.lock.d"
			lock_dir_20a.mkdir()
			old_ts = time.time() - 100.0
			os.utime(str(lock_dir_20a), (old_ts, old_ts))
			try:
				acquire_lock(lock_dir_20a, timeout=2.0, poll=0.01, grace_seconds=0.1)
			except TimeoutError:
				failures.append(
					f"[{fix20_name}] FAIL: a metadata-less dir past its grace "
					f"age must be reclaimed, got TimeoutError"
				)
				fix20_ok = False
			else:
				release_lock(lock_dir_20a)

			# (ii) Fresh bare dir (just created) inside a generous grace ->
			# ambiguous, must NOT be reclaimed (TimeoutError expected).
			lock_dir_20b = fix20_dir / "fresh.lock.d"
			lock_dir_20b.mkdir()
			try:
				acquire_lock(
					lock_dir_20b, timeout=0.3, poll=0.02, grace_seconds=30.0,
				)
				failures.append(
					f"[{fix20_name}] FAIL: a FRESH metadata-less dir must NOT "
					f"be reclaimed — expected TimeoutError"
				)
				fix20_ok = False
			except TimeoutError:
				pass  # correct
		except Exception as exc:
			failures.append(f"[{fix20_name}] FAIL: unexpected exception: {exc!r}")
			fix20_ok = False
		print(f"  {'PASS' if fix20_ok else 'FAIL'} [{fix20_name}]")

		# -------------------------------------------------------------------
		# Fixture 21: racing-reclaimers-exactly-one-acquisition
		# (coord-lock-no-stale-reclaim, Fix Scope item 2 + Tests (d).)  Two
		# concurrent reclaimers racing a confirmed-dead lock: no crash, and
		# mutual exclusion holds throughout (never more than one concurrent
		# holder) even across the reclaim.
		# -------------------------------------------------------------------
		fix21_name = "racing-reclaimers-exactly-one-acquisition"
		fix21_ok = True
		try:
			import threading

			fix21_dir = td_path / "fix21"
			fix21_dir.mkdir()
			lock_dir_21 = fix21_dir / "global.lock.d"
			lock_dir_21.mkdir()
			(lock_dir_21 / "owner.json").write_text(
				json.dumps({
					"pid": 999_021, "kernel_start_time": 111.0,
					"acquired_at": "2026-01-01T00:00:00Z",
				}),
				encoding="utf-8",
			)

			def _pid_status_21(pid):
				# Only the seeded zombie pid is dead; a real (our-own) pid,
				# stamped by whichever thread wins, must read alive so the
				# LOSER can't also reclaim the winner's live lock.
				return "dead" if pid == 999_021 else "alive"

			guard_21 = threading.Lock()
			state_21 = {"concurrent": 0, "max_concurrent": 0, "errors": []}

			def _worker_21():
				try:
					acquire_lock(
						lock_dir_21, timeout=5.0, poll=0.01,
						pid_status_fn=_pid_status_21,
					)
					with guard_21:
						state_21["concurrent"] += 1
						state_21["max_concurrent"] = max(
							state_21["max_concurrent"], state_21["concurrent"]
						)
					time.sleep(0.05)
					with guard_21:
						state_21["concurrent"] -= 1
					release_lock(lock_dir_21)
				except Exception as exc:  # noqa: BLE001
					state_21["errors"].append(repr(exc))

			t1 = threading.Thread(target=_worker_21)
			t2 = threading.Thread(target=_worker_21)
			t1.start()
			t2.start()
			t1.join(timeout=10)
			t2.join(timeout=10)

			if state_21["errors"]:
				failures.append(
					f"[{fix21_name}] FAIL: no crash expected, got "
					f"{state_21['errors']!r}"
				)
				fix21_ok = False
			if state_21["max_concurrent"] != 1:
				failures.append(
					f"[{fix21_name}] FAIL: mutual exclusion violated, "
					f"max_concurrent={state_21['max_concurrent']!r}"
				)
				fix21_ok = False
			if lock_dir_21.exists():
				failures.append(
					f"[{fix21_name}] FAIL: both racing acquirers must have "
					f"released the lock by the end"
				)
				fix21_ok = False
		except Exception as exc:
			failures.append(f"[{fix21_name}] FAIL: unexpected exception: {exc!r}")
			fix21_ok = False
		print(f"  {'PASS' if fix21_ok else 'FAIL'} [{fix21_name}]")

		# -------------------------------------------------------------------
		# Fixture 22: has-live-lease-predicate
		#
		# has_live_lease mirrors claim_shardable's third-rail liveness check
		# (lazy-batch-parallel-run-harness-gaps round-2 gap 8 — the serial-tail
		# merged-head exemption). Assert: a live lease → True; an expired lease
		# → False; a missing key → False; a missing file → False; an
		# unreadable-entry key → True (conservative, as claim_shardable).
		# -------------------------------------------------------------------
		fix22_name = "has-live-lease-predicate"
		fix22_ok = True
		try:
			fix22_dir = td_path / "fix22"
			fix22_dir.mkdir()
			leases_path_22 = fix22_dir / "leases.json"
			now_22 = 3_000_000.0
			live_ts = datetime.fromtimestamp(now_22, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
			# expired: heartbeat + ttl strictly before now.
			expired_ts = datetime.fromtimestamp(
				now_22 - 1000, tz=timezone.utc
			).strftime("%Y-%m-%dT%H:%M:%SZ")
			seed_22 = {
				"live-item": {
					"worker_pid": 1234,
					"worktree_slot": "wt-00",
					"term_token": 1,
					"heartbeat_timestamp": live_ts,
					"ttl_seconds": 300,
				},
				"expired-item": {
					"worker_pid": 1235,
					"worktree_slot": "wt-01",
					"term_token": 1,
					"heartbeat_timestamp": expired_ts,
					"ttl_seconds": 300,
				},
				# Present key but unreadable fields → conservative True.
				"broken-item": {"worker_pid": 1236},
			}
			leases_path_22.write_text(json.dumps(seed_22), encoding="utf-8")
			checks_22 = [
				("live lease → True", has_live_lease(leases_path_22, "live-item", now=now_22) is True),
				("expired lease → False", has_live_lease(leases_path_22, "expired-item", now=now_22) is False),
				("missing key → False", has_live_lease(leases_path_22, "absent-item", now=now_22) is False),
				("unreadable entry → True", has_live_lease(leases_path_22, "broken-item", now=now_22) is True),
				("missing file → False", has_live_lease(fix22_dir / "nope.json", "live-item", now=now_22) is False),
				("int wi_id coerced → True", has_live_lease(leases_path_22, "live-item", now=now_22) is True),
			]
			for label, ok in checks_22:
				if not ok:
					failures.append(f"[{fix22_name}] FAIL: {label}")
					fix22_ok = False
		except Exception as exc:  # noqa: BLE001
			failures.append(f"[{fix22_name}] FAIL: unexpected exception: {exc!r}")
			fix22_ok = False
		print(f"  {'PASS' if fix22_ok else 'FAIL'} [{fix22_name}]")

		# -------------------------------------------------------------------
		# Fixture 23: item-lock-same-key-serializes (concurrent-lock Leg 1/2/5)
		#
		# Two agents on the SAME item key serialize: while the holder is live a
		# bounded acquire TIMES OUT (waits, never steals); after the holder
		# releases, the contender proceeds in turn with a STRICTLY GREATER
		# fencing token (watermark monotonicity on release).
		# -------------------------------------------------------------------
		fix23_name = "item-lock-same-key-serializes"
		fix23_ok = True
		try:
			fix23_dir = td_path / "fix23"
			fix23_dir.mkdir()
			leases_23 = fix23_dir / "leases.json"
			leases_23.write_text(json.dumps({}), encoding="utf-8")
			now_23 = 4_000_000.0
			holder = acquire_item_lock(leases_23, "item-K", 111, "wt-00", 300, timeout=1.0, now=now_23)
			if holder is None or holder["term_token"] != 1:
				failures.append(f"[{fix23_name}] FAIL: holder did not acquire token 1")
				fix23_ok = False
			t1 = holder["term_token"] if holder else 0
			# Contender: bounded acquire while the holder is live -> ItemLockTimeout.
			jumped_23 = {"n": 0}
			def _clock_23():
				jumped_23["n"] += 1
				return 0.0 if jumped_23["n"] == 1 else 999.0
			timed_out_23 = False
			try:
				acquire_item_lock(
					leases_23, "item-K", 222, "wt-01", 300,
					timeout=1.0, now=now_23, clock=_clock_23, sleep=lambda _s: None,
				)
			except ItemLockTimeout:
				timed_out_23 = True
			if not timed_out_23:
				failures.append(f"[{fix23_name}] FAIL: contender did not time out while holder live")
				fix23_ok = False
			# Holder releases; contender proceeds in turn with a greater token.
			release_item_lock(leases_23, "item-K", t1, now=now_23)
			h2 = acquire_item_lock(leases_23, "item-K", 222, "wt-01", 300, timeout=1.0, now=now_23)
			if h2 is None or h2["term_token"] <= t1:
				failures.append(f"[{fix23_name}] FAIL: contender did not proceed with a greater token after unlock")
				fix23_ok = False
		except Exception as exc:  # noqa: BLE001
			failures.append(f"[{fix23_name}] FAIL: unexpected exception: {exc!r}")
			fix23_ok = False
		print(f"  {'PASS' if fix23_ok else 'FAIL'} [{fix23_name}]")

		# -------------------------------------------------------------------
		# Fixture 24: item-lock-different-keys-no-block (concurrent-lock Leg 1)
		#
		# Two agents on DIFFERENT item keys never block each other — both
		# acquire immediately and hold live leases simultaneously.
		# -------------------------------------------------------------------
		fix24_name = "item-lock-different-keys-no-block"
		fix24_ok = True
		try:
			fix24_dir = td_path / "fix24"
			fix24_dir.mkdir()
			leases_24 = fix24_dir / "leases.json"
			leases_24.write_text(json.dumps({}), encoding="utf-8")
			now_24 = 5_000_000.0
			a = acquire_item_lock(leases_24, "item-A", 111, "wt-00", 300, timeout=1.0, now=now_24)
			b = acquire_item_lock(leases_24, "item-B", 222, "wt-01", 300, timeout=1.0, now=now_24)
			if a is None or b is None:
				failures.append(f"[{fix24_name}] FAIL: a different-key acquire blocked")
				fix24_ok = False
			data_24 = json.loads(leases_24.read_text(encoding="utf-8"))
			if "item-A" not in data_24 or "item-B" not in data_24:
				failures.append(f"[{fix24_name}] FAIL: both leases not held simultaneously")
				fix24_ok = False
		except Exception as exc:  # noqa: BLE001
			failures.append(f"[{fix24_name}] FAIL: unexpected exception: {exc!r}")
			fix24_ok = False
		print(f"  {'PASS' if fix24_ok else 'FAIL'} [{fix24_name}]")

		# -------------------------------------------------------------------
		# Fixture 25: item-lock-confirmed-dead-reclaimed (concurrent-lock Leg 4)
		#
		# A dead holder's EXPIRED lease is reclaimed (lease TTL-expiry _reclaim)
		# and the waiter proceeds, minting a STRICTLY GREATER fencing token than
		# the reclaimed holder's (watermark survives reclamation).
		# -------------------------------------------------------------------
		fix25_name = "item-lock-confirmed-dead-reclaimed"
		fix25_ok = True
		try:
			fix25_dir = td_path / "fix25"
			fix25_dir.mkdir()
			leases_25 = fix25_dir / "leases.json"
			now_25 = 6_000_000.0
			expired_25 = datetime.fromtimestamp(now_25 - 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
			leases_25.write_text(json.dumps({
				"item-D": {
					"worker_pid": 9999,
					"worktree_slot": "wt-00",
					"term_token": 5,
					"heartbeat_timestamp": expired_25,
					"ttl_seconds": 300,
				}
			}), encoding="utf-8")
			w = acquire_item_lock(leases_25, "item-D", 222, "wt-01", 300, timeout=1.0, now=now_25)
			if w is None or w["term_token"] <= 5:
				failures.append(f"[{fix25_name}] FAIL: dead holder not reclaimed with a greater token")
				fix25_ok = False
		except Exception as exc:  # noqa: BLE001
			failures.append(f"[{fix25_name}] FAIL: unexpected exception: {exc!r}")
			fix25_ok = False
		print(f"  {'PASS' if fix25_ok else 'FAIL'} [{fix25_name}]")

		# -------------------------------------------------------------------
		# Fixture 26: item-lock-live-holder-times-out (concurrent-lock Leg 4/5)
		#
		# A genuinely LIVE holder is NEVER falsely reclaimed: a bounded acquire
		# times out and the holder's lease is left untouched (no false reclaim).
		# -------------------------------------------------------------------
		fix26_name = "item-lock-live-holder-times-out"
		fix26_ok = True
		try:
			fix26_dir = td_path / "fix26"
			fix26_dir.mkdir()
			leases_26 = fix26_dir / "leases.json"
			now_26 = 7_000_000.0
			live_26 = datetime.fromtimestamp(now_26, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
			leases_26.write_text(json.dumps({
				"item-L": {
					"worker_pid": 9999,
					"worktree_slot": "wt-00",
					"term_token": 3,
					"heartbeat_timestamp": live_26,
					"ttl_seconds": 300,
				}
			}), encoding="utf-8")
			jumped_26 = {"n": 0}
			def _clock_26():
				jumped_26["n"] += 1
				return 0.0 if jumped_26["n"] == 1 else 999.0
			timed_out_26 = False
			try:
				acquire_item_lock(
					leases_26, "item-L", 222, "wt-01", 300,
					timeout=1.0, now=now_26, clock=_clock_26, sleep=lambda _s: None,
				)
			except ItemLockTimeout:
				timed_out_26 = True
			if not timed_out_26:
				failures.append(f"[{fix26_name}] FAIL: acquire did not time out against a live holder")
				fix26_ok = False
			data_26 = json.loads(leases_26.read_text(encoding="utf-8"))
			if data_26.get("item-L", {}).get("term_token") != 3:
				failures.append(f"[{fix26_name}] FAIL: live holder's lease was mutated (false reclaim)")
				fix26_ok = False
		except Exception as exc:  # noqa: BLE001
			failures.append(f"[{fix26_name}] FAIL: unexpected exception: {exc!r}")
			fix26_ok = False
		print(f"  {'PASS' if fix26_ok else 'FAIL'} [{fix26_name}]")

	if failures:
		print("\nFAILURES:")
		for f in failures:
			print(f"  - {f}")
		return 1
	print("\nAll smoke tests passed.")
	return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
	parser.add_argument(
		"--test",
		action="store_true",
		help="Run fixture smoke tests instead of normal operation",
	)
	args = parser.parse_args()

	if args.test:
		return run_smoke_tests()

	parser.print_help()
	return 0


if __name__ == "__main__":
	sys.exit(main())
