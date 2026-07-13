---
kind: fixed
feature_id: coord-lock-no-stale-reclaim
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: python user/scripts/lazy_coord.py --test (21/21 fixtures PASS); NOT
  pipeline-gated (__mark_fixed__)
auto_ticked_rows: 0
---

# Completion Receipt

`coord-lock-no-stale-reclaim` marked fixed on 2026-07-12. Root cause: `lazy_coord.py`'s
`os.mkdir`-based global lock created an empty lock directory with no holder metadata (no pid, no
timestamp) and had no reclamation path — a holder that died between `mkdir` and `release_lock`
(SIGKILL, OOM, power loss — all explicitly in this system's threat model) deadlocked every
coordination mutation in the `/lazy-batch-parallel` concurrency plane (lease acquisition,
heartbeat, lane bookkeeping, and the reclamation machinery itself) forever, with the only
recovery being a human manually deleting the lock directory.

## What shipped

`acquire_lock` now writes `owner.json` (`{pid, kernel_start_time, acquired_at}`) into the lock
dir immediately after a successful `mkdir`, via the same write-temp-then-`os.replace` pattern
`_write_leases` already uses. On a losing `mkdir`, it reads `owner.json` and reclaims the lock
(atomic rename-then-`shutil.rmtree`, so exactly one racing reclaimer ever wins) **only** when the
recorded holder is CONFIRMED dead:

- the recorded pid no longer exists, **or**
- the recorded pid is alive but was reused — its live `kernel_start_time` (the kernel-reported
  process-creation time, duplicated from `lazy_core.kernel_start_time` since this module must not
  import `lazy_core`) mismatches the one recorded at acquire time.

Every ambiguous case — a genuinely live holder, an unreadable/inaccessible pid, or a metadata-less
lock still inside a small grace window (the crash window between `mkdir` and the metadata write)
— is **never** reclaimed; a live/ambiguous lock still raises `TimeoutError` within the same
timeout/backoff budget as before. This mirrors the build-queue `active.lock` precedent
(`Get-ActiveLockStatusFromText`/`Test-ShouldReclaimLock`: an unreadable pid classifies `'unknown'`,
never `'dead'` — only a confirmed-dead observation reclaims), per the SPEC's D2 decision
(dead-holder confirmation, not a bare TTL — the lock layer has no fencing token to make a wrong
evict safe).

All five of the SPEC's Fix Scope items landed in one pass, in `user/scripts/lazy_coord.py` only
(this bug's sole owned file under the run's concurrent-lane split): holder metadata (item 1),
confirmed-dead reclamation with the metadata-less grace-age fallback (item 2), unchanged timeout
semantics for a live lock (item 3), the five named test scenarios plus a metadata-write-contract
fixture (item 4), and the `user/scripts/CLAUDE.md` doc-row update (item 5). `release_lock` was
also updated to remove `owner.json` before `os.rmdir` (the lock dir is no longer empty on
release). No genuine design fork remained open — the SPEC's D1/D2/D3 decisions were already fully
resolved, so this closes normally rather than parking a `NEEDS_INPUT_PROVISIONAL.md`.

## Symptom reproduction — evidence the defect is gone

**Original symptom (code-proven per the SPEC, not field-observed):** a lock dir left behind by a
dead holder had no way to be distinguished from a live one, and no reclamation path existed at
all — every subsequent `acquire_lock` call against it would spin for its full timeout and raise
`TimeoutError`, forever, until a human ran `rmdir`.

**RED confirmed (2026-07-12):** loaded a `git show HEAD`-extracted **pre-fix** copy of
`lazy_coord.py` as an isolated module and drove it directly against a seeded dead-holder lock —
`acquire_lock(lock_dir, timeout=1.0)` raised `TimeoutError` (no reclaim existed), and a fresh
`acquire_lock` call never wrote any owner metadata. Both are exactly the defects the SPEC
describes.

**GREEN confirmed (2026-07-12):** the same scenario against the fixed file now succeeds within one
`acquire_lock` call (no `TimeoutError`, a fresh `owner.json` is written by the reclaiming call).
Full regression:

```
python user/scripts/lazy_coord.py --test
-> 21/21 fixtures PASS, including:
   lock-owner-metadata-written
   stale-lock-dead-holder-reclaimed        (SPEC Tests (a))
   live-holder-lock-still-times-out        (SPEC Tests (b))
   pid-reuse-reclaimed                     (SPEC Tests (c))
   metadata-less-stale-dir-grace-age       (SPEC Tests (e))
   racing-reclaimers-exactly-one-acquisition (SPEC Tests (d))
```

`racing-reclaimers-exactly-one-acquisition` drives two real `threading.Thread`s racing a
confirmed-dead lock and asserts mutual exclusion held throughout (a shared max-concurrency counter
never exceeds 1), not merely "no exception raised." The pre-existing `mkdir-mutual-exclusion`
fixture (unchanged) also now exercises the REAL (non-injected) Windows `kernel_start_time`/pid
implementation against this process's own live pid — proving the production `ctypes` path works,
not just the hermetic fakes used by the new dead/reused-pid fixtures.

## Gates run

- `python user/scripts/lazy_coord.py --test` → 21/21 PASS.
- `python user/scripts/doc-drift-lint.py --repo-root .` → exit 1, but the 3 findings + 2
  exemptions are all **pre-existing and unrelated** to this bug (hook-matcher documentation drift
  for `build-queue-enforce.sh`/`lazy-cycle-containment.sh`/`long-build-ownership-guard.sh`, plus
  the pre-existing `block-work-repo-git-writes.sh` and `algobooth` manifest exemptions) — none
  touch `lazy_coord.py` or its `user/scripts/CLAUDE.md` row, which this fix updated cleanly.

## Files touched

- `user/scripts/lazy_coord.py` — owner-metadata write, confirmed-dead reclaim helpers
  (`kernel_start_time` + extractors duplicated from `lazy_core.py`, `_pid_status`,
  `_confirmed_dead_owner`, `_read_lock_owner`, `_write_lock_owner`, `_rename_then_remove`,
  `_maybe_reclaim_stale_lock`), `acquire_lock`/`release_lock` changes, six new/reworked `--test`
  fixtures (16–21).
- `user/scripts/CLAUDE.md` — `lazy_coord.py` table-row doc addition (the holder-metadata +
  reclamation contract) and the stale `--test` fixture-count reference, both updated to 21.
- `docs/bugs/coord-lock-no-stale-reclaim/PHASES.md` — new (this bug had no plan file yet; bugs
  skip `/write-plan`).
- `docs/bugs/coord-lock-no-stale-reclaim/SPEC.md` — `**Status:**` flipped to `Fixed`.
- `docs/bugs/coord-lock-no-stale-reclaim/FIXED.md` — this receipt (new).

No `lazy_core.py`, `lazy-state.py`, or `bug-state.py` edit was needed or made — this fix is fully
contained to `lazy_coord.py` (its stated stdlib-only, no-`lazy_core`-import contract holds).
