# Implementation Phases — Multi-Repo Concurrent Runs

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete
<!-- All 4 phases implemented + validated 2026-06-16 (pytest 412 + hooks 69 + visualizer 65 +
     parity 23 green; live-validated isolating a concurrent AlgoBooth run). NOT Complete on the
     SPEC — the __mark_complete__ integrity gate owns the SPEC Complete flip + COMPLETED.md
     receipt. -->

**MCP runtime:** not-required — pure claude-config harness mechanics (Python state-script + bash hooks). No Tauri app, no MCP-reachable surface; validation is `pytest` on `lazy_core.py` / `test_lazy_core.py`, the `test_hooks.py` bash-hook harness, `lazy-state.py --test` / `bug-state.py --test` smoke baselines, and `lint-skills.py`. This is the `standalone — no app integration` untestable class → `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** (none)`. This feature extends already-shipped machinery that lives in `docs/specs/` (not the feature queue), so there is no upstream PHASES.md to integrate against:

- **`turn-routing-enforcement` (Complete spec):** owns the run-marker pattern (`~/.claude/state/lazy-run-marker.json`), the PreToolUse dispatch-guard / route-inject hooks, and the prompt registry. This feature **re-scopes that marker from a global singleton to a per-`repo_root` registry**, and routes the hooks' marker check through the state script instead of a raw file-existence test.
- **`lazy-cycle-containment` (Complete feature):** added the sibling cycle-subagent marker (`lazy-cycle-active.json`) + the `lazy-cycle-containment.sh` hook. That marker is also a singleton; this feature scopes it the same way so a cycle in repo A's run does not contain dispatches in repo B's session.

The existing `read_run_marker` already carries a non-destructive **session-id isolation path** (Phase 8 WU-8.1, path B) and `write_run_marker` already takes `repo_root` — but the three hooks bypass that logic with a raw `[ -f "$STATE_DIR/lazy-run-marker.json" ]` test, and the state dir itself is a single global. This feature closes both gaps **at the `claude_state_dir()` chokepoint** (24 call sites in `lazy_core.py` all resolve their paths through it), so the marker, prompt registry, deny-ledger, cycle marker, and checkpoint all become per-repo with no per-call-site threading.

---

### Phase 1: Repo-scoped `claude_state_dir()` core

**Phase kind:** design

**Scope:** Scope the entire run-scoped state directory per repo at the single `claude_state_dir()` chokepoint. Add `repo_key` derivation + a module-level active-repo, set once at `main()`. Preserve `LAZY_STATE_DIR`-set semantics exactly (hermetic tests/hook-fixtures), key only when unset (production). Add `--run-start` same-repo refusal. Migrate legacy base-dir files once.

**Deliverables:**
- [ ] `lazy_core.py`: `repo_key(repo_root: str) -> str` — the ONE canonical derivation. SHA-1 of the normalized real path (resolve symlinks, forward-slash separators, strip trailing slash, lowercase the Windows drive letter). Single source of truth; nothing else re-implements it.
- [ ] `lazy_core.py`: module-level `_active_repo_root` + `set_active_repo_root(path)`; `active_repo_root()` returns it, falling back to the cwd git-toplevel. Set once at each script's `main()` from `--repo-root` (or cwd).
- [ ] `lazy_core.py`: `claude_state_dir()` — when `LAZY_STATE_DIR` env is **set**, return it EXACTLY as today (no keying — preserves every existing test's path semantics byte-for-byte). When **unset**, return `Path.home()/".claude"/"state"/repo_key(active_repo_root())`, created on demand for write paths. The 24 internal callers are unchanged.
- [ ] `--run-start` same-repo refusal: `refuse_run_start_clobber` already refuses clobbering a different-pipeline live marker; extend the contract so a live (non-stale) marker in THIS repo's subdir refuses a second `--run-start` with a diagnostic naming `started_at` / `forward_cycles`. A different repo = different subdir = no refusal. Age staleness (path A, 24h) makes a stale marker reclaimable.
- [ ] Legacy base-dir migration (`migrate_legacy_state_dir()`): on first production `claude_state_dir()` resolution, if base-dir files exist (`lazy-run-marker.json`, `lazy-prompt-registry.json`, `lazy-deny-ledger.jsonl`, `lazy-cycle-active.json`, `lazy-run-checkpoint.json`), move them into the keyed subdir for the marker's recorded `repo_root`, then remove the base copies. Idempotent; a marker with no resolvable `repo_root` is treated as stale and removed. NEVER touches a `LAZY_STATE_DIR`-overridden dir.
- [ ] Tests (`test_lazy_core.py`, NEW — registered in a `_TESTS` list): `repo_key` stability + normalization-invariance + distinctness; `claude_state_dir` returns env-exact when set and keyed-subdir when unset (use a temp `HOME`); two distinct active repos → two distinct subdirs; `--run-start` same-repo refusal; migration moves base-dir files + removes them + handles unresolvable repo_root. Existing `LAZY_STATE_DIR` marker tests remain green unchanged.

**Minimum Verifiable Behavior:** With `LAZY_STATE_DIR` unset and a temp `HOME`, `set_active_repo_root("/repoA")` → `claude_state_dir()` is `…/state/<keyA>/`; `set_active_repo_root("/repoB")` → `…/state/<keyB>/`; the two are distinct dirs, each holding its own marker independently.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Per-repo state dirs are independent: two active repos resolve to distinct subdirs, each with its own marker; neither read sees the other. *(Evidence: `SKIP_MCP_TEST.md` — `test_lazy_core.py` per-repo state-dir tests.)*
- [ ] `LAZY_STATE_DIR`-set semantics unchanged (all prior marker tests green). *(Evidence: `test_lazy_core.py` full suite 403+/N green.)*

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config has no Tauri/MCP app). Verification is `pytest`.

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py` + `user/scripts/bug-state.py` (`set_active_repo_root` at `main()`), `user/scripts/test_lazy_core.py`, `tests/baselines/*` (only if `--test` fixtures change — expected NOT to, since `--test` sets `LAZY_STATE_DIR`).

**Testing Strategy:** Hermetic temp-`HOME` fixtures for the keyed path (env unset); existing `LAZY_STATE_DIR` fixtures prove the unchanged path. Inject `now` for staleness. Keep `lazy-state.py --test` / `bug-state.py --test` byte-pinned baselines green (regenerate only via `_normalize_smoke_output` if a fixture legitimately changes — not expected).

**Integration Notes for Next Phase:** Phase 2 hooks resolve their repo via a new `--marker-present` query (Python owns `repo_key`; bash never re-derives). The `active_repo_root()` / `claude_state_dir()` keying is the contract Phase 2 + 3 consume.

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

### Phase 3: bug-state.py parity + pipeline_visualizer

**Phase kind:** integration

**Scope:** Confirm the bug pipeline inherits the keyed state dir (it imports `claude_state_dir` from the shared `lazy_core.py`), wire its `main()` active-repo set, update the parity audit, and update `pipeline_visualizer` (which reads the marker for display) to enumerate per-repo subdirs.

**Deliverables:**
- [ ] `bug-state.py`: `set_active_repo_root(args.repo_root or cwd)` at `main()` (mirrors `lazy-state.py`); same-repo refusal + own-state clear behave identically. A bug run and a feature run in the SAME repo share the subdir (mutually exclusive — correct, same git tree); cross-repo isolated.
- [ ] `lazy_parity_audit.py`: extend to assert the active-repo + keyed-state-dir surface is consistent across the feature/bug state scripts.
- [ ] `pipeline_visualizer`: enumerate `~/.claude/state/<repo-key>/` subdirs (or accept a repo arg) instead of reading the base-dir marker; show the marker for the visualized repo.
- [ ] Tests: `bug-state.py --test` smoke + a `test_lazy_core.py` cross-script case (bug run live in repo A blocks a same-repo feature `--run-start`; does not block a repo-B run); `test_pipeline_visualizer.py` updated for the keyed layout.

**Minimum Verifiable Behavior:** `bug-state.py --run-start --repo-root /repoA` then `lazy-state.py --run-start --repo-root /repoA` → the second refuses (same repo); `lazy-state.py --run-start --repo-root /repoB` → succeeds.

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
