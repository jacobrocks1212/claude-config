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


def _reclaim(data: dict, pool_dir, now: float) -> None:
	"""Mutate data in-place, removing expired entries and scrubbing their slot dirs."""
	expired_ids = [
		wi_id for wi_id, entry in data.items()
		if _parse_iso(entry["heartbeat_timestamp"]) + entry["ttl_seconds"] < now
	]
	for wi_id in expired_ids:
		entry = data.pop(wi_id)
		slot = entry.get("worktree_slot")
		if slot:
			shutil.rmtree(str(Path(pool_dir) / slot), ignore_errors=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def acquire_lock(lock_dir, timeout=10.0, *, poll=0.05) -> None:
	"""Acquire the global directory lock via atomic os.mkdir.

	Retries with exponential backoff until timeout, then raises TimeoutError.
	Never uses fcntl/flock/LockFileEx.
	"""
	lock_dir = Path(lock_dir)
	start = time.monotonic()
	delay = poll
	while True:
		try:
			os.mkdir(str(lock_dir))
			return  # acquired
		except FileExistsError:
			elapsed = time.monotonic() - start
			if elapsed >= timeout:
				raise TimeoutError(
					f"Could not acquire lock {lock_dir!r} within {timeout}s"
				)
			time.sleep(min(delay, timeout - elapsed))
			delay = min(delay * 2, 1.0)


def release_lock(lock_dir) -> None:
	"""Release the global directory lock via os.rmdir."""
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
		# Inline reclaim expired entries
		_reclaim(data, leases_path.parent, ts_now)

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
		for wi_id in expired_ids:
			entry = data.pop(wi_id)
			slot = entry.get("worktree_slot")
			if slot:
				shutil.rmtree(str(pool_dir / slot), ignore_errors=True)
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
		del data[key]
		_write_leases(leases_path, data)
	finally:
		release_lock(lock_dir)


def provision_pool(cognito_root, pool_dir, k) -> list:
	"""Provision k worktree slots in pool_dir, returning a list of slot paths.

	Creates git worktrees (via git worktree add) for each slot that does not
	already exist. Returns the list of Path objects for all k slots.
	"""
	cognito_root = Path(cognito_root)
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
				["git", "-C", str(cognito_root), "worktree", "add", str(slot_path)],
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


def scrub_slot(cognito_root, pool_dir, slot, wi_id, slug, *, lock_dir=None) -> None:
	"""Clean up a worktree slot after a work-item completes or is reclaimed.

	Removes the git worktree, resets the branch, and removes the slot directory.
	Optionally acquires the global lock (lock_dir) around destructive git ops.
	"""
	cognito_root = Path(cognito_root)
	pool_dir = Path(pool_dir)
	slot_path = pool_dir / slot

	# (1) Remove index.lock with exponential backoff retry
	index_lock = cognito_root / ".git" / "worktrees" / slot / "index.lock"
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

	# (3) checkout --detach origin/main
	subprocess.run(
		["git", "-C", str(slot_path), "checkout", "--detach", "origin/main"],
		check=False,
	)
	# (4) reset --hard origin/main
	subprocess.run(
		["git", "-C", str(slot_path), "reset", "--hard", "origin/main"],
		check=False,
	)
	# (5) clean -fdx
	subprocess.run(
		["git", "-C", str(slot_path), "clean", "-fdx"],
		check=False,
	)
	# (6) checkout new branch
	branch_name = f"p/{wi_id}-{slug}"
	subprocess.run(
		["git", "-C", str(slot_path), "checkout", "-b", branch_name],
		check=False,
	)


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
