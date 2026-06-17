# Implementation Phases — Multi-Repo Concurrent Runs

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Draft
<!-- Phases authored 2026-06-16. NOT Complete — the __mark_complete__ integrity gate owns the
     Complete flip + COMPLETED.md receipt after the validation tail. -->

**MCP runtime:** not-required — pure claude-config harness mechanics (Python state-script + bash hooks). No Tauri app, no MCP-reachable surface; validation is `pytest` on `lazy_core.py` / `test_lazy_core.py`, the `test_hooks.py` bash-hook harness, `lazy-state.py --test` / `bug-state.py --test` smoke baselines, and `lint-skills.py`. This is the `standalone — no app integration` untestable class → `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** (none)`. This feature extends already-shipped machinery that lives in `docs/specs/` (not the feature queue), so there is no upstream PHASES.md to integrate against:

- **`turn-routing-enforcement` (Complete spec):** owns the run-marker pattern (`~/.claude/state/lazy-run-marker.json`), the PreToolUse dispatch-guard / route-inject hooks, and the prompt registry. This feature **re-scopes that marker from a global singleton to a per-`repo_root` registry**, and routes the hooks' marker check through the state script instead of a raw file-existence test.
- **`lazy-cycle-containment` (Complete feature):** added the sibling cycle-subagent marker (`lazy-cycle-active.json`) + the `lazy-cycle-containment.sh` hook. That marker is also a singleton; this feature scopes it the same way so a cycle in repo A's run does not contain dispatches in repo B's session.

The existing `read_run_marker` already carries a non-destructive **session-id isolation path** (Phase 8 WU-8.1, path B) and `write_run_marker` already takes `repo_root` — but the three hooks bypass that logic with a raw `[ -f "$STATE_DIR/lazy-run-marker.json" ]` test, and the marker file itself is a singleton. This feature closes both gaps.

---

### Phase 1: Per-repo marker registry core

**Phase kind:** design

**Scope:** Make the run marker a per-`repo_root` file under `~/.claude/state/run-markers/<repo-key>.json` instead of the singleton `lazy-run-marker.json`. Add the single canonical repo-key derivation in `lazy_core.py`; route `write_run_marker` / `read_run_marker` / `delete_run_marker` through it; add `--run-start` same-repo refusal; have `--run-end` clear only the current repo's marker; migrate a legacy singleton on first touch.

**Deliverables:**
- [ ] `lazy_core.py`: `repo_key(repo_root: str) -> str` — the ONE canonical derivation. SHA-1 of the normalized real path (resolve symlinks, forward-slash separators, strip trailing slash, lowercase the Windows drive letter). Documented as the single source of truth; nothing else re-implements it.
- [ ] `lazy_core.py`: `run_marker_path(repo_root: str) -> Path` returns `claude_state_dir()/"run-markers"/f"{repo_key(repo_root)}.json"`. `write_run_marker` / `read_run_marker` / `delete_run_marker` take a `repo_root` argument and use it; the singleton `_MARKER_FILENAME` constant is retained only for the migration path below.
- [ ] `read_run_marker(repo_root, now, session_id)`: staleness paths A (24h age delete-on-read) and B (session-id mismatch, non-destructive) preserved verbatim — only the path resolution changes. A marker for a *different* repo is simply a different file and is never consulted.
- [ ] `--run-start` same-repo refusal: if a live (non-stale) marker exists for this `repo_root`, refuse (exit non-zero) with a diagnostic naming the in-flight run's `started_at` / `forward_cycles`. A stale marker (ended, or age-stale) is reclaimable (overwritten).
- [ ] `--run-end` clears only `run_marker_path(repo_root)` (+ this repo's registry); never touches another repo's marker. `delete_run_marker(repo_root, clear_registry=True)`.
- [ ] Legacy-singleton migration: on first `--run-start` / `read_run_marker`, if `~/.claude/state/lazy-run-marker.json` exists, move it to `run-markers/<repo-key-of-its-repo_root>.json` then remove the singleton; a singleton with no resolvable `repo_root` is treated as stale and removed.
- [ ] Tests (`test_lazy_core.py`): two distinct `repo_root`s → two distinct marker paths, both readable independently; same-repo second `--run-start` refused; `--run-end` for repo A leaves repo B's marker intact; age + session staleness preserved; migration moves a legacy singleton and removes it; corrupt singleton with no repo_root removed.

**Minimum Verifiable Behavior:** `--run-start --repo-root /tmp/A` then `--run-start --repo-root /tmp/B` (different `LAZY_STATE_DIR` fixture) both succeed and produce two files under `run-markers/`; a second `--run-start --repo-root /tmp/A` refuses naming the in-flight run.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Two concurrent repos each hold an independent marker: `--run-start` for A and B both succeed; `read_run_marker(A)` and `read_run_marker(B)` each return their own marker. *(Evidence: `SKIP_MCP_TEST.md` — `test_lazy_core.py` two-repo independence test.)*
- [ ] Same-repo second run refused; `--run-end` clears only its own repo. *(Evidence: `test_lazy_core.py` refusal + isolation tests.)*

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config has no Tauri/MCP app). Verification is `pytest`.

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py` (CLI wiring of `--run-start`/`--run-end` repo_root passthrough + refusal exit), `user/scripts/test_lazy_core.py`, `tests/baselines/lazy-state-test-baseline.txt` (only if `--test` fixtures change).

**Testing Strategy:** Hermetic `LAZY_STATE_DIR` temp-dir fixtures; inject `now` for staleness; two-repo independence is table-driven. Keep `lazy-state.py --test` byte-pinned baseline green (regenerate only via `_normalize_smoke_output` if a fixture legitimately changes).

**Integration Notes for Next Phase:** Phase 2 hooks must resolve the SAME `repo_key`; rather than re-implement it in bash, Phase 2 adds a `--marker-present` query the hooks call. The `repo_key` + `run_marker_path` helpers are the contract Phase 2 consumes.

---

### Phase 2: Hook repo-scoping via a thin script query

**Phase kind:** integration

**Scope:** Replace each hook's raw `[ -f "$STATE_DIR/lazy-run-marker.json" ]` existence test with a call to a new `lazy-state.py --marker-present --repo-root <cwd> [--session-id <id>]` query, so repo-key derivation + staleness + session isolation stay entirely in Python (one implementation) and the hooks stay thin.

**Deliverables:**
- [ ] `lazy-state.py --marker-present [--repo-root <path>] [--session-id <id>]`: resolves the current repo (arg or `git -C <cwd> rev-parse --show-toplevel`), calls `read_run_marker(repo_root, session_id=...)`, prints a one-line verdict (`present` / `absent`) and exits 0/1 (or a JSON `{present: bool}` — pick the form the hooks parse most cheaply). Read-only; never creates state.
- [ ] `lazy-dispatch-guard.sh`: replace the file-existence gate with the `--marker-present` query against the tool-call's cwd; a marker for a *different* repo → `absent` → fast-path allow.
- [ ] `lazy-route-inject.sh`: same substitution for the banner-injection gate.
- [ ] `lazy-cycle-containment.sh`: scope its `lazy-cycle-active.json` lookup to the current repo the same way (per-repo cycle marker path, mirrored from Phase 1's `repo_key`).
- [ ] `test_hooks.py`: a two-repo isolation harness — marker present for repo-key A, hook invoked with cwd in repo B → allow / no-inject; marker present + cwd in repo A → deny/inject as today (no regression).

**Minimum Verifiable Behavior:** With a live marker for repo A, `lazy-dispatch-guard.sh` invoked with a cwd inside repo B allows the dispatch; invoked with a cwd inside repo A it denies a non-script-emitted dispatch exactly as today.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Cross-repo dispatch allowed: marker for A present, guard fired in B → allow. *(Evidence: `SKIP_MCP_TEST.md` — `test_hooks.py` two-repo isolation harness.)*
- [ ] Same-repo enforcement unchanged: marker for A present, guard fired in A on a non-script-emitted prompt → deny. *(Evidence: `test_hooks.py` regression case.)*

**MCP Integration Test Assertions:** N/A — bash hooks; verification is `test_hooks.py`.

**Prerequisites:** Phase 1 (`repo_key`, `run_marker_path`, per-repo `read_run_marker`).

**Files likely modified:** `user/scripts/lazy-state.py` (`--marker-present`), `user/hooks/lazy-dispatch-guard.sh`, `user/hooks/lazy-route-inject.sh`, `user/hooks/lazy-cycle-containment.sh`, `user/scripts/test_hooks.py`.

**Testing Strategy:** `test_hooks.py` pipes fixture hook-input JSON with two distinct cwds against a fixture `LAZY_STATE_DIR`. Assert allow/deny/inject per repo. Cross-platform (git-bash + WSL) per the existing harness.

**Integration Notes for Next Phase:** Phase 3 mirrors the Phase 1 core into `bug-state.py`; the hooks from this phase already key off `repo_key` so a bug run in repo A is isolated identically — no further hook change needed for bugs.

---

### Phase 3: bug-state.py parity

**Phase kind:** integration

**Scope:** Mirror Phase 1's per-repo marker behavior into the bug pipeline. Because the marker helpers live in the shared `lazy_core.py`, `bug-state.py` inherits `repo_key` / `run_marker_path` automatically; this phase wires its `--run-start` / `--run-end` repo_root passthrough + refusal and updates the parity audit.

**Deliverables:**
- [ ] `bug-state.py` `--run-start` / `--run-end` pass `repo_root` into the shared helpers; same-repo refusal + own-marker clear behave identically to `lazy-state.py`. A bug run and a feature run in the SAME repo share the per-repo slot (mutually exclusive — correct, same git tree); cross-repo isolated.
- [ ] `lazy_parity_audit.py`: extend to assert the marker-registry surface (per-repo path, refusal, clear-own) is consistent across the feature/bug state scripts.
- [ ] Tests: `bug-state.py --test` smoke + a `test_lazy_core.py` cross-script case (bug run live in repo A blocks a same-repo feature `--run-start`; does not block a repo-B run).

**Minimum Verifiable Behavior:** `bug-state.py --run-start --repo-root /tmp/A` then `lazy-state.py --run-start --repo-root /tmp/A` → the second refuses (same repo); `lazy-state.py --run-start --repo-root /tmp/B` → succeeds.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Feature + bug runs share the per-repo slot in one repo, isolated across repos. *(Evidence: `SKIP_MCP_TEST.md` — `test_lazy_core.py` cross-script test.)*

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phase 1.

**Files likely modified:** `user/scripts/bug-state.py`, `user/scripts/lazy_parity_audit.py`, `user/scripts/test_lazy_core.py`, `tests/baselines/bug-state-test-baseline.txt` (only if fixtures change).

**Testing Strategy:** Reuse the Phase 1 fixtures across both scripts; run BOTH `lazy-state.py --test` and `bug-state.py --test` plus `test_lazy_core.py` (shared import surface).

**Integration Notes for Next Phase:** Phase 4 is docs/cleanup only — no behavior change.

---

### Phase 4: Cleanup + documentation

**Phase kind:** chore

**Scope:** Document the per-repo registry; update the state-layout notes; ensure no orphaned singleton lingers.

**Deliverables:**
- [ ] `user/scripts/CLAUDE.md`: document the `run-markers/<repo-key>.json` registry, the `repo_key` derivation, the same-repo-refusal / cross-repo-concurrency contract, and the migration.
- [ ] Root `CLAUDE.md` Hooks table note: the three hooks now scope by current repo via `--marker-present`.
- [ ] `docs/specs/turn-routing-enforcement/`: a short note that the marker is now per-repo (the singleton is retired except as a migration source).
- [ ] Confirm the live machine has no stale singleton (the one cleared in hardening Round 26 stays cleared).

**Minimum Verifiable Behavior:** `lint-skills.py --check-projected --check-capabilities` clean; docs reference the registry, not the singleton.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Docs/lint consistency green. *(Evidence: `SKIP_MCP_TEST.md` — `lint-skills.py` clean.)*

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phases 1–3.

**Files likely modified:** `user/scripts/CLAUDE.md`, `CLAUDE.md`, `docs/specs/turn-routing-enforcement/` notes.

**Testing Strategy:** Docs/lint only; full harness gate suite green as the final acceptance.
