# lazy_coord global lock has no stale-holder reclamation — Investigation Spec

> `lazy_coord.acquire_lock` is an `os.mkdir` spin lock with a ~10s timeout — but the lock
> directory carries NO holder metadata (no pid, no timestamp) and there is NO reclamation
> path. A holder that dies between `mkdir` and `rmdir` deadlocks ALL worktree-pool
> coordination forever; the only recovery is a human running `rmdir`. The same file's lease
> layer already solves this exact problem (TTL reclamation + fencing tokens + watermarks) —
> the lock layer beneath it never got the same treatment.

**Status:** Fixed
**Priority:** P3
**Last updated:** 2026-07-12
**Related:** `docs/bugs/mark-complete-partial-apply-noop-unrecoverable/` + `docs/bugs/production-sentinel-writes-bypass-atomic-write/` (siblings — shared theme: crash-consistency of script-owned state); `docs/features/parallel-worktree-batch-execution/` (the feature `lazy_coord.py` serves; consumer skill `lazy-batch-parallel`); `docs/features/long-build-and-runtime-ownership/` (owns `lazy_core.kernel_start_time`, the PID-reuse defense the fix reuses).

## Verified Defect

**Code-proven, not field-observed** — no run has yet been observed wedged on a stale lock;
the trace below is a line-level read of the live tree (2026-07-11, uncommitted working
copy — cited line numbers are what the current file actually shows).

**The lock (`user/scripts/lazy_coord.py:146–166`):**

```python
def acquire_lock(lock_dir, timeout=10.0, *, poll=0.05) -> None:
    ...
    while True:
        try:
            os.mkdir(str(lock_dir))
            return  # acquired
        except FileExistsError:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                raise TimeoutError(...)
            time.sleep(min(delay, timeout - elapsed))
            delay = min(delay * 2, 1.0)
```

`release_lock` (169–174) is a bare `os.rmdir`. The lock directory is created EMPTY:
no pid, no start-time, no heartbeat — an observer who finds it held has no way to
distinguish "live holder mid-critical-section" from "holder SIGKILLed three hours ago".
There is no reclamation branch anywhere in the file: the only exit from a stale lock is
`TimeoutError` after 10s, on every call, forever, until a human deletes the directory.

**Blast radius: every coordination mutation serializes through this one lock.** Verified
call sites — `acquire_lease` (212), `heartbeat` (264), `reclaim_expired` (317),
`release_lease` (350), `scrub_slot` (467), and `_mutate_lanes` (607, through which all the
`ledger_record_*` lane-ledger operations at 617–678 route). A dead holder therefore does
not stall one work item — it deadlocks lease acquisition, heartbeating, lane bookkeeping,
AND the reclamation machinery itself (`reclaim_expired` needs the very lock that is
wedged), for every worker in the pool.

**Death-between-mkdir-and-rmdir is a normal event in this system's threat model.** Callers
do wrap the critical section in `try/finally release_lock` (e.g. 212–213ff), which covers
Python exceptions — but the surrounding harness explicitly plans for SIGKILL-class
termination (killed-mid-link builds, operator `dev:kill`, power loss, OOM), and `finally`
does not run under SIGKILL. The lease layer's whole reclamation design exists BECAUSE
workers die ungracefully; the lock under it assumes they never do.

**The in-repo precedent that proves the standard.** The SAME FILE's lease layer is
well-engineered against exactly this failure:
- TTL-based reclamation — `_reclaim` (120–139) removes entries whose
  `heartbeat_timestamp + ttl_seconds < now` and scrubs their slots.
- Fencing tokens — `term_token`, `FencingError` (33), `verify_fencing` (279): a zombie
  holder that wakes after reclamation is rejected on its stale token.
- Monotonic watermarks — `_record_watermarks` (102–117): reclaimed entries' tokens are
  persisted so a re-claim mints a STRICTLY greater token (fencing survives reclamation).

The lock layer beneath it has none of these. This is not a disagreement about design
philosophy within the file — it is one layer finished and the other not.

## Root Cause

**Classification: `missing-mechanism` (liveness hole in the mutual-exclusion layer).**
`acquire_lock` implements only the safety half of a lock (at most one holder, via atomic
`mkdir` — correct and portable) and omits the liveness half (a dead holder must be
detectable and evictable). Because the lock dir carries zero holder metadata, no
reclamation is even POSSIBLE without a protocol change — timeout-and-raise is the only
option the data structure permits, and that punts recovery to a human. The lease layer
above it shows the authors knew the required pattern; it was simply never applied one
level down.

## Fix Scope (Concluded)

Mirror the lease layer's dead-holder handling at the lock layer:

1. **Holder metadata inside the lock dir:** after a successful `mkdir`, write
   `owner.json` into it — `{pid, kernel_start_time, acquired_at}` — using the
   write-temp-then-`os.replace` pattern the file already uses for leases/watermarks.
   `kernel_start_time` is the PID-reuse defense: reuse `lazy_core.kernel_start_time`
   (`lazy_core.py:9797` — Windows `GetProcessTimes` / POSIX `/proc/[pid]/stat` field 22,
   best-effort, never raises). NOTE the module constraint (see D1): `lazy_coord.py`'s
   header (line 13) declares "stdlib-only and must NOT import lazy_core".
2. **Reclamation on confirmed-dead holder:** when `mkdir` fails, read `owner.json`;
   holder is confirmed dead iff its pid no longer exists OR the pid's live
   `kernel_start_time` mismatches the recorded one (PID reuse). On confirmed-dead:
   reclaim via **rename-then-remove** — `os.rename(lock_dir, lock_dir + '.stale-<unique>')`
   then `shutil.rmtree` the renamed dir, then retry `mkdir`. The atomic rename arbitrates
   racing reclaimers (exactly one wins; losers get `FileNotFoundError`/`FileExistsError`
   and re-enter the spin). A metadata-less or unreadable `owner.json` inside the window
   where the holder wrote it is NOT confirmed-dead — fall back to a bounded grace age
   (`acquired_at`-based or dir mtime) before treating a metadata-less lock as stale, so a
   holder killed between `mkdir` and the metadata write cannot wedge the pool either.
   Ambiguous states (pid alive, start-time unreadable) never reclaim — safety over
   liveness, preserving today's behavior as the worst case.
3. **Timeout semantics unchanged:** `TimeoutError` remains the terminal for a genuinely
   LIVE contended lock; reclamation only consumes attempts within the same
   timeout/backoff budget. Existing callers need no signature changes.
4. **Tests (in the file's own `--test` fixture harness, matching lines 992/1001 which
   already exercise `acquire_lock` timeout behavior):** (a) stale lock with a dead pid is
   reclaimed and acquired within one call; (b) live-holder lock still times out;
   (c) PID-reuse — recorded start-time ≠ live start-time → reclaimed; (d) two racing
   reclaimers → exactly one acquisition, no crash; (e) metadata-less stale dir → reclaimed
   only past the grace age.
5. **Doc row:** `user/scripts/CLAUDE.md`'s lazy_coord entry gains the holder-metadata +
   reclamation contract so future edits keep the lock and lease layers at parity.

## Decisions

- **D1 — kernel_start_time sourcing vs the no-lazy_core constraint:** duplicate the
  helper into `lazy_coord.py` rather than import it or extract a shared module. Precedent:
  `lazy_core.py:5670–5673` documents the identical deliberate-duplication policy for
  `_current_head` ("the two scripts are independently importable"); a new shared module
  for one function is heavier than the duplication it avoids. (If the sibling bug
  `production-sentinel-writes-bypass-atomic-write` lands an F811/lint gate, an
  intentional cross-FILE duplicate remains lint-clean — only in-file redefinition trips
  F811.)
- **D2 — Reclaim vs TTL-expire the lock:** reclaim on confirmed-dead holder (pid +
  start-time), NOT a bare TTL. Lock hold times are milliseconds (JSON read-modify-write),
  but a TTL short enough to give liveness could evict a live-but-paused holder without
  fencing; the lock layer has no term_token to make that safe. Dead-holder confirmation
  is conservative and needs no fencing.
- **D3 — Priority P3:** the window requires SIGKILL-class death inside a
  milliseconds-long critical section AND only bites parallel-lane runs
  (`lazy-batch-parallel`); single-lane pipelines never touch `lazy_coord`. Latent but
  real; cheap to close while the lease-layer patterns are fresh.
