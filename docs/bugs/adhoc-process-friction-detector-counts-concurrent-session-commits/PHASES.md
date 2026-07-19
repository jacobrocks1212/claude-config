# Implementation Phases — Process-friction detector counts concurrent same-identity session commits

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure stdlib Python state-machine logic (git-log + deny-ledger commit attribution in `lazy_core`); claude-config has no Tauri/MCP surface, and this fix touches no MCP-reachable behavior.

## Touchpoint Audit (verified inline — dispatch-cheaper-inline for a bounded fix with exact file:line refs from the concluded SPEC)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core/ledgers.py` | yes | `append_deny_ledger_entry` (84 — stamps live-run identity, fail-open jsonl append via `claude_state_dir()`), `flush_commit_artifacts` (3951; commits at 4025), `claude_state_dir`, `_atomic_write` | create + refactor | CREATE `append_concurrent_commit_sha` / `read_concurrent_commit_entries` next to `append_deny_ledger_entry`, REUSING its exact `claude_state_dir() / <FILENAME>` fail-open append pattern (do NOT re-implement). REFACTOR `flush_commit_artifacts` to append its produced sha after a successful commit. |
| `user/scripts/lazy_core/markers.py` | yes | `_count_concurrent_writer_commits` (2077–2134; returns `sum(email != own_email)`), `cycle_end_friction_check` (2137; computes `current_run_started_at` at 2178, calls the counter at 2226), `detect_cycle_bracket_friction` (consumes the count at 1932, budget-compares at 1935) | refactor | EXTEND `_count_concurrent_writer_commits` with a ledger-read arm; widen its signature to accept the current run identity; the caller `cycle_end_friction_check` passes the already-computed `current_run_started_at`. Preserve the `None`-on-degraded-read fail-safe contract verbatim. |
| `user/scripts/lazy_core/gates.py` | yes | `archive_fixed` (1991; commits at 2296, captures short sha at 2308) | refactor | After the successful `commit_proc`, append the produced sha to the concurrent-activity ledger (best-effort; NEVER fail the archive on a ledger-write error). |
| `user/scripts/tests/test_lazy_core/test_markers.py` | yes | `test_detect_friction_concurrent_writer_commits_suppressed` (4008), `..._genuine_runaway_still_flags_with_zero_concurrent` (4046) | refactor | Add detector-side fixtures (see Phase 1 Runtime Verification / assertions). |
| `user/scripts/tests/test_lazy_core/test_ledgers.py` | yes | ledger-helper suite | refactor | Add substrate + producer fixtures for `append_concurrent_commit_sha` / `read_concurrent_commit_entries` and `flush_commit_artifacts` instrumentation. |
| `user/scripts/tests/test_lazy_core/test_gates.py` | yes | `archive_fixed` suite | refactor | Add a fixture asserting `archive_fixed` appends its produced sha (with run identity) on a real commit and appends nothing on the no-op re-run path. |

**Contradictions:** none (anchor- or premise-grade). The concluded SPEC's serving-path trace matches the live code exactly (`markers.py:1932/1935/2132`). All planned paths are `exists: yes`.

## Chosen approach (SPEC Open Questions resolved — recorded as scope decisions, not product forks)

- **Approach B (script-owned concurrent-mutation sha ledger)** — the SPEC's recommendation; A (nonce-trailer on every commit) has a broad blast radius the SPEC explicitly cautions against, and B fails SAFE relative to A (an un-instrumented foreign commit over-reports friction = self-announcing, never a silently-broken gate).
- **Ledger scope = ALL script-owned direct-commit sites, both pipelines** (not bug-only). The same blind spot exists for feature-pipeline concurrent script-owned commits; instrumenting every direct-commit site in shared `lazy_core` is bounded (a small enumerable set) and is the most-complete path (D7). The two direct-commit sites confirmed on disk are `archive_fixed` (bug pipeline) and `flush_commit_artifacts` (shared, both pipelines). `--apply-pseudo`/`--reorder-queue`/`--sync-deps` mutate files but do NOT themselves `git commit` (the orchestrator commits their output) — Phase 2 includes a grep audit to confirm no other direct `_git(..., "commit", ...)` site was missed.

## Fail-safe invariant every phase MUST preserve (from SPEC Proven Findings)

An unknown/ambiguous attribution must NEVER suppress a genuine runaway. The extension may only ADD positive same-identity subtraction; it must never turn a degraded/ambiguous ledger read into over-subtraction. A ledger sha is subtracted ONLY when its recorded run identity is present AND differs from this cycle's run identity; an absent/malformed identity is treated conservatively (NOT subtracted). A ledger-read failure degrades to the existing email-only count (byte-identical to today).

---

### Phase 1: Concurrent-activity ledger substrate + detector consumption

**Scope:** Introduce the concurrent-activity commit-sha ledger in the shared per-repo-keyed state dir and teach `_count_concurrent_writer_commits` to subtract window commits recorded in it by a DISTINCT run identity — closing the same-identity blind spot at the detector. This phase delivers the full read/consume mechanism with the producer side stubbed (tests seed the ledger directly), so the fix is verifiable before the commit sites are wired.

**Status:** Fixed

**Deliverables:**
- [x] `lazy_core.ledgers.append_concurrent_commit_sha(sha, *, run_started_at)` — appends one compact JSON line `{sha, run_started_at, ts}` to `claude_state_dir() / lazy-concurrent-activity.jsonl`, reusing `append_deny_ledger_entry`'s exact fail-open plain-append pattern (identity stamped from the live run marker exactly as that helper does; `None`/interactive → `run_started_at: null`). Never raises; returns True/False.
- [x] `lazy_core.ledgers.read_concurrent_commit_entries()` — returns a `{sha: run_started_at}` map from the ledger; tolerant of a torn final line and a missing file (empty result), never raises.
- [x] `_count_concurrent_writer_commits(repo_root, begin_head_sha, current_run_started_at)` extended: after the existing email-inequality count, UNION in window shas (from `git log --no-merges --format=%H%x1f%ae <begin>..HEAD`, merges excluded, de-duplicated against the email-attributed set via a shared `set`) that appear in the ledger with a recorded `run_started_at` that is present AND `!= current_run_started_at`. Returns `None` on ANY degraded read (unchanged contract); a ledger-read failure degrades to the email-only count.
- [x] `cycle_end_friction_check` passes its already-computed `current_run_started_at` (markers.py:2178) into the extended counter call.
- [x] Tests: `test_ledgers.py` WU-1 substrate (6) + `test_markers.py` WU-2 detector fixtures (5); GREEN.

**Implementation Notes (2026-07-19):**
- WU-1 helpers + `_CONCURRENT_ACTIVITY_FILENAME = "lazy-concurrent-activity.jsonl"` added to `lazy_core/ledgers.py` beside the deny-ledger helpers; three symbols registered in the `lazy_core/__init__.py` PEP-562 facade map (`append_concurrent_commit_sha`, `read_concurrent_commit_entries`, `_count_concurrent_writer_commits`).
- WU-2 widened `_count_concurrent_writer_commits` to 3 args (back-compat default `current_run_started_at=None`); the ledger arm is a function-local `from .ledgers import read_concurrent_commit_entries` (markers→ledgers is acyclic). Fail-safe held: null/same-identity/degraded reads never over-subtract (proven by the stash-RED test-first check).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test && python3 user/scripts/bug-state.py --test` stay green, and the new `test_markers.py` / `test_ledgers.py` fixtures pass: a same-identity concurrent commit seeded into the ledger with a distinct `run_started_at` is subtracted from `chargeable_commits`, so a window that would trip `unexpected-commits` no longer does.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior (pure `lazy_core` state-machine logic; verified by the hermetic pytest + in-file `--test` harness).

**Testing Strategy (hermetic — verified by pytest fixtures):**
- Same-identity concurrent subtraction: seed `lazy-concurrent-activity.jsonl` with N in-window shas stamped `run_started_at = "OTHER"`; assert `_count_concurrent_writer_commits(..., current_run_started_at="MINE")` returns N (email-only would return 0), and `detect_cycle_bracket_friction` no longer emits `unexpected-commits` when `commits_since - N <= budget`.
- This-run shas NOT subtracted: a ledger sha stamped `run_started_at = "MINE"` (== current) is NOT counted → this run's own automated commits still charge against the budget.
- Genuine runaway still trips: commits in-window NOT in the ledger and same-email still produce `unexpected-commits` (regression of `test_detect_friction_genuine_runaway_still_flags_with_zero_concurrent`).
- Fail-safe on degraded ledger read: a missing/unreadable/torn ledger degrades to the email-only count (no new suppression); an entry with absent/malformed `run_started_at` is NOT subtracted (conservative).
- De-dup: a window commit that is BOTH a distinct committer email AND ledger-recorded is counted once, not twice.

**Integration Notes for Next Phase:**
- The producer contract Phase 2 must honor: append the sha ONLY after a confirmed successful commit, stamped with the SAME live-run identity `append_deny_ledger_entry` reads (so this run's own script-owned commits carry `run_started_at == MINE` and are correctly excluded from subtraction).
- The ledger filename/schema (`lazy-concurrent-activity.jsonl`, `{sha, run_started_at, ts}`) is fixed here; Phase 2 producers write through `append_concurrent_commit_sha` only — never a bare `open().write()`.
- `_count_concurrent_writer_commits` is shared (serves both pipelines via `cycle_end_friction_check`); the signature widening is a shared-helper change (parity-audited, not a hand-mirrored coupled-pair edit). Run `lazy_parity_audit.py --repo-root .` after the change.

---

### Phase 2: Instrument the script-owned commit sites to record their shas

**Scope:** Wire every script-owned DIRECT-commit site in `lazy_core` to append its produced sha to the concurrent-activity ledger via `append_concurrent_commit_sha`, so a concurrent session's automated archive/mark/flush commits become subtractable at the detector. Best-effort at every site — a ledger-write error can NEVER fail or partial-abort a commit.

**Status:** Complete

**Deliverables:**
- [x] Grep audit: `grep -rn '"commit"' user/scripts/lazy_core/*.py` (excluding tests) returns EXACTLY two direct-commit sites — `gates.py:2296` (`archive_fixed`) and `ledgers.py` `flush_commit_artifacts` (the commit line shifted from 4025→4124 as WU-1 added helper lines above it). No additional direct-commit site exists; `apply_pseudo`/`reorder_queue`/`sync_deps` make no direct commit (the orchestrator commits their output). The instrumentation set is complete.
- [x] `archive_fixed` (gates.py): after the short-sha capture, appends the produced full sha via `append_concurrent_commit_sha(<git rev-parse HEAD>, run_started_at=_raw_marker_started_at())`, best-effort (function-local import — ledgers imports gates). A ledger failure leaves the archive committed and `ok: True`.
- [x] `flush_commit_artifacts` (ledgers.py): after its successful commit resolves `commit_sha`, appends it the same way; the no-op / "nothing to commit" branches (commit_sha=None) append nothing.
- [x] Tests: `test_pseudo.py` WU-3 (3: appends / noop-appends-nothing / ledger-failure-doesn't-change-verdict) + `test_ledgers.py` WU-4 (3: flush appends / flush noop / end-to-end seam); GREEN.

**Implementation Notes (2026-07-19):**
- Both producers stamp `run_started_at=_raw_marker_started_at()` — the SAME live-run identity source `append_deny_ledger_entry` reads — so THIS run's own archive/flush commits carry `run_started_at == MINE` and are correctly EXCLUDED from subtraction; a concurrent session's commits carry that session's distinct identity and subtract.
- The end-to-end seam test (`test_concurrent_session_commits_seam_no_false_friction`) drives the real producer + the WU-2 detector through `cycle_end_friction_check`: `budget + M` window commits with `M` recorded under a distinct identity → chargeable = budget → NO `unexpected-commits` friction; one more own commit → trips (genuine runaway preserved).

**Minimum Verifiable Behavior:** in a hermetic temp-repo fixture, `archive_fixed` (and `flush_commit_artifacts`) leave exactly one new entry in `lazy-concurrent-activity.jsonl` whose `sha` equals the commit they just made; a no-op re-run leaves the ledger unchanged.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior (hermetic `lazy_core` git-fixture tests).

**Testing Strategy (hermetic — verified by pytest fixtures):**
- `archive_fixed` producer: a real archive commit appends one ledger entry with `sha == HEAD` and `run_started_at` matching the seeded live-run identity; the no-op re-run path (nothing staged) appends nothing; a forced ledger-write failure does NOT change the `archive_fixed` verdict (`ok: True`, `committed` present).
- `flush_commit_artifacts` producer: a real flush commit appends its `commit_sha`; the "no flush artifacts present" / "nothing to commit" paths append nothing.
- End-to-end seam (the motivating incident, hermetic): simulate a concurrent second identity making M archive commits into a cycle window (append via the real producer with a DISTINCT `run_started_at`), then run `cycle_end_friction_check` for a cycle whose `commits_since` includes them — assert NO `process-friction` `unexpected-commits` entry is appended to the deny ledger when `commits_since - M <= budget`, and that a genuine same-run runaway still trips.

**Prerequisites:**
- Phase 1: `append_concurrent_commit_sha` + the extended detector must exist (producers write through the Phase-1 helper; the end-to-end seam test consumes the Phase-1 detector).

**Integration Notes for Next Phase:**
- After both phases land, run the full state-machine gate: `lazy-state.py --test`, `bug-state.py --test`, `pytest user/scripts/tests/test_lazy_core/`, and `lazy_parity_audit.py --repo-root .`.
- **Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed, writes `FIXED.md`, and archives once the validation tail passes — this plan never flips it.

---

## Red-flag detection (spec-phases Step 3 — `--batch`)

- **Circular dependencies:** none — Phase 2 depends on Phase 1 only (linear).
- **Unclear scope:** no — the SPEC concluded with a traced root cause, exact fix site, and a recommended approach; scope decisions (B; both-pipeline ledger) are recorded above.
- **Integration explosion:** no — three source files + three test files, all in `user/scripts/lazy_core` / its test tree.
- **Testing impossible:** no — fully hermetic (temp git repos + seeded state dir); no runtime/MCP dependency.
- **Platform/variant expansion:** none.

Clean — no `NEEDS_INPUT.md`.
