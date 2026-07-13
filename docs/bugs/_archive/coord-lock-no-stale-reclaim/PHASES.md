# Implementation Phases — lazy_coord global lock has no stale-holder reclamation

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; `lazy_coord.py` is
verified via its own in-file `--test` fixture smoke harness (the repo's established
verification method for this script — see `user/scripts/CLAUDE.md`'s `lazy_coord.py` row and
"Concurrency plane" section). There is no `mcp-tool-catalog.md` in this repo, so the
planning-time MCP tool-existence audit no-ops.

## Validated Assumptions

- **`lazy_coord.py` is stdlib-only and must NOT import `lazy_core`** (module docstring, line
  13). D1 duplicates `kernel_start_time` (+ its two private extractors,
  `_win_process_creation_filetime` / `_posix_boot_time`) verbatim from `lazy_core.py:10158-10269`
  rather than importing it or extracting a shared module — the same deliberate-duplication policy
  `lazy_core.py` documents for its own `_current_head` (`lazy_core.py:5952-5964`, "the two scripts
  are independently importable").
- **The build-queue `active.lock` precedent is the shape to mirror in Python** (SPEC "Fix Scope",
  intro line + D2). `build-queue-hygiene.ps1`'s `Get-ActiveLockStatusFromText` /
  `Test-ShouldReclaimLock` classify a holder `alive` / `dead` / `unknown` and reclaim ONLY on a
  confirmed-dead observation — an unreadable/inaccessible pid is `unknown`, never `dead`
  ("fail-safe to alive" bias). This plan's `_pid_status`/`_confirmed_dead_owner` reproduce that
  three-way classification in Python (there is no PowerShell `Get-Process` equivalent to shell
  out to; the POSIX/Windows liveness probes are native: `os.kill(pid, 0)` and
  `ctypes.OpenProcess` + `GetLastError`).
- **No fencing token exists at the lock layer** (D2) — reclaiming a genuinely-live-but-paused
  holder would be unsafe with no term-token to reject its later write, so this fix is
  deliberately conservative: reclaim ONLY on a confirmed-dead pid or a confirmed pid-reuse
  (mismatched `kernel_start_time`), never on a bare TTL/age heuristic for a *readable* owner
  record. Age (`grace_seconds`) is used ONLY as the fallback for the narrow metadata-less crash
  window (Fix Scope item 2's last paragraph), where no pid claim exists yet to evaluate.

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC (only `**Related:**` siblings sharing the
crash-consistency theme, not a hard queue dependency). This bug touches ONLY
`user/scripts/lazy_coord.py` (+ its in-file `--test` harness) — no other file in the repo reads
or writes the lock dir's contents beyond `acquire_lock`/`release_lock` themselves (verified:
`pipeline_visualizer/leases.py` and `test_pipeline_visualizer.py` depend only on
`lazy_coord._parse_iso`, never on lock-dir internals). Fix Scope item 5 (a `user/scripts/CLAUDE.md`
doc row) is folded into this phase rather than split out — it is a small addition alongside the
same commit.

---

### Phase 1: Owner metadata + confirmed-dead reclamation on `acquire_lock`

**Scope:** Give the `os.mkdir` global lock the same dead-holder liveness handling the lease layer
already has, per SPEC Fix Scope items 1–4: write holder metadata on acquire; reclaim (atomic
rename-then-rmtree) only a CONFIRMED-dead holder on a losing `mkdir`; preserve `TimeoutError` as
the terminal for a genuinely live contended lock; add the five named test scenarios to the
in-file `--test` fixture harness. Plus the doc row (item 5).

**TDD:** yes. The new fixtures were written first and confirmed RED against the pre-fix
`acquire_lock` (verbatim git-HEAD copy), then the implementation was added and the fixtures
turned GREEN — see Implementation Notes for the RED/GREEN evidence.

**Status:** Complete

**Deliverables:**
- [x] `kernel_start_time` (+ `_win_process_creation_filetime`, `_posix_boot_time`,
  `_FILETIME_EPOCH_OFFSET`/`_FILETIME_TICKS_PER_SEC`) duplicated into `lazy_coord.py` from
  `lazy_core.py`, identical contract (best-effort, never raises, hermetic injection seams).
- [x] `_pid_status(pid)` — three-way `'alive' | 'dead' | 'unknown'` classification
  (POSIX: `os.kill(pid, 0)`; Windows: `ctypes.OpenProcess` + `GetLastError` — `ERROR_INVALID_PARAMETER`
  (87) = dead, `ERROR_ACCESS_DENIED` (5) = alive, anything else = unknown). Fails safe toward
  `'unknown'`, never `'dead'`, on any ambiguity.
- [x] `_confirmed_dead_owner(owner)` — True iff the recorded pid is dead, OR alive but its live
  `kernel_start_time` mismatches the recorded one (pid reuse). Any other combination (alive +
  matching start-time, alive + unreadable start-time, `'unknown'` status, malformed metadata)
  returns False — never reclaim on a guess.
- [x] `_write_lock_owner(lock_dir)` — writes `owner.json` `{pid, kernel_start_time, acquired_at}`
  via write-temp-then-`os.replace` (matching `_write_leases`) immediately after a successful
  `mkdir`; wrapped fully best-effort (never raises — a metadata-write failure must not strand the
  lock unreleased, since the caller already returned from `mkdir`).
- [x] `_rename_then_remove(lock_dir)` — the atomic rename-then-`shutil.rmtree` reclaim; returns
  `True` iff THIS call won the rename race, `False` on any `OSError` (lost race / already gone) so
  exactly one racing reclaimer ever proceeds.
- [x] `_maybe_reclaim_stale_lock(lock_dir)` — on a losing `mkdir`: reads `owner.json`; if present,
  reclaims iff `_confirmed_dead_owner`; if absent/unreadable, reclaims only once the lock dir's
  mtime is older than `grace_seconds` (default 2.0s) — the crash-window fallback for a holder that
  died between `mkdir` and its metadata write.
- [x] `acquire_lock` calls `_write_lock_owner` after `mkdir` and, on `FileExistsError`, calls
  `_maybe_reclaim_stale_lock` before falling through to the unchanged timeout/backoff logic — a
  reclaim retries `mkdir` immediately (same call, no caller-visible change); a live/ambiguous lock
  still raises `TimeoutError` within the same budget. New params
  (`now`, `grace_seconds`, `pid_status_fn`, `kernel_start_time_fn`) are keyword-only with defaults
  — every existing call site (`acquire_lease`, `heartbeat`, `reclaim_expired`, `release_lease`,
  `provision_pool`, `scrub_slot`, `_mutate_lanes`) is byte-identical (`acquire_lock(lock_dir)`).
- [x] `release_lock` now removes `owner.json` (best-effort) before `os.rmdir` — required because
  the lock dir is no longer empty on release (previously a bare `os.rmdir`).
- [x] Five new `--test` fixtures (16–21) covering the SPEC's Fix Scope item 4 (a)–(e) + the
  metadata-write contract: `lock-owner-metadata-written`, `stale-lock-dead-holder-reclaimed` (a),
  `live-holder-lock-still-times-out` (b), `pid-reuse-reclaimed` (c),
  `metadata-less-stale-dir-grace-age` (e), `racing-reclaimers-exactly-one-acquisition` (d, via two
  real `threading.Thread`s racing a confirmed-dead lock — mutual exclusion asserted throughout via
  a shared max-concurrency counter, not just "no exception").
- [x] `user/scripts/CLAUDE.md`'s `lazy_coord.py` table row updated to document the holder-metadata
  + reclamation contract (parity with the lease layer's TTL reclamation description already there).

**Implementation Notes (2026-07-12):** Implemented in `user/scripts/lazy_coord.py` only (this
bug's sole owned file, per the concurrent-lane split with the sibling agent owning
`lazy_core.py`/`lazy-state.py`/`bug-state.py`). RED confirmed by loading a `git show
HEAD`-extracted **pre-fix** copy of the file as a separate module and driving it directly: a
seeded dead-holder lock raised `TimeoutError` (no reclaim existed) and a fresh `acquire_lock` call
never wrote `owner.json` — both the exact defects the SPEC describes. GREEN confirmed by running
the full in-file harness against the fixed file: **21/21 fixtures PASS** (`python
user/scripts/lazy_coord.py --test`), including the pre-existing `mkdir-mutual-exclusion` fixture
(5), which now exercises the REAL (non-injected) Windows `kernel_start_time`/`_pid_status`
implementation against this process's own live pid — proving the production ctypes path works,
not just the hermetic fakes used in fixtures 17/18/19/21.

**Minimum Verifiable Behavior:** `python user/scripts/lazy_coord.py --test` exits 0 with all 21
fixtures PASS, including the six new/reworked ones exercising: metadata written on acquire,
dead-holder reclaim within one call, a live holder still timing out, pid-reuse reclaim,
metadata-less grace-age gating, and racing-reclaimer mutual exclusion.

**Runtime Verification** *(checked by the in-file `--test` harness — no app runtime; this IS the
repo's runtime for this script):*
- [x] <!-- verification-only --> A lock dir held by a CONFIRMED-dead pid is reclaimed and
  acquired within one `acquire_lock` call. **Verified 2026-07-12:**
  `stale-lock-dead-holder-reclaimed` — PASS.
- [x] <!-- verification-only --> A lock dir held by a live pid (matching recorded
  `kernel_start_time`) still raises `TimeoutError` — never reclaimed. **Verified 2026-07-12:**
  `live-holder-lock-still-times-out` — PASS.
- [x] <!-- verification-only --> A recorded pid that is alive but whose live `kernel_start_time`
  mismatches the recorded one (pid reuse) is reclaimed. **Verified 2026-07-12:**
  `pid-reuse-reclaimed` — PASS.
- [x] <!-- verification-only --> Two racing reclaimers against the same confirmed-dead lock never
  crash and never both hold the lock concurrently. **Verified 2026-07-12:**
  `racing-reclaimers-exactly-one-acquisition` — PASS (max_concurrent == 1 across two real threads).
- [x] <!-- verification-only --> A metadata-less lock dir (crash between `mkdir` and the owner.json
  write) reclaims only once older than the grace age; a fresh one does not. **Verified
  2026-07-12:** `metadata-less-stale-dir-grace-age` — PASS (both the past-grace and
  within-grace legs).

**MCP Integration Test Assertions:** N/A — no app runtime; the in-file `--test` harness IS this
script's verification surface (documented convention, `user/scripts/CLAUDE.md`).

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/scripts/lazy_coord.py` — owner-metadata write, confirmed-dead reclaim helpers,
  `acquire_lock`/`release_lock` changes, six new/reworked `--test` fixtures.
- `user/scripts/CLAUDE.md` — `lazy_coord.py` table-row doc addition (the holder-metadata +
  reclamation contract, parity with the existing lease-layer description).

**Testing Strategy:** Pure in-process fixture testing against the file's own `run_smoke_tests()`
harness (`python user/scripts/lazy_coord.py --test`) — the established convention for this
script (no separate pytest file exists or is warranted; `user/scripts/CLAUDE.md` documents the
gate as `python lazy_coord.py --test`). RED-for-the-right-reason was proven by driving a
`git show HEAD`-extracted pre-fix copy of the module directly (see Implementation Notes) rather
than by reverting the working tree, since this bug's fix and its tests land in the same file and
the same commit.

**Integration Notes for Next Phase:** None — final phase. The `__mark_fixed__` gate
(orchestrator-owned) flips the SPEC/PHASES top-level `**Status:**` and writes `FIXED.md`; this
plan does not flip status or write `FIXED.md` from within the phase itself — done as the
immediately-following close-out step per this run's operator protocol (no unresolved fork was
found, so this closes normally rather than parking a `NEEDS_INPUT_PROVISIONAL.md`).

**Completion:** `**Status:**` flipped to `Fixed` in `SPEC.md` and this file, and `FIXED.md`
written, as part of this same interactive pass (operator-directed-interactive provenance — not
pipeline-gated `__mark_fixed__`, mirroring the sibling bug
`legacy-tool-input-env-hooks-dead`'s FIXED.md provenance for a claude-config script bug fixed
outside the autonomous pipeline).

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_
