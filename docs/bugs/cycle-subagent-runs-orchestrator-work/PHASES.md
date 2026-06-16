# Implementation Phases — Cycle Subagent Runs Orchestrator Work

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this repo has no Tauri app and no MCP server (per `.claude/skill-config/quality-gates.md`); all changes are to Python state-machine scripts (`lazy_core.py` / `lazy-state.py` / `bug-state.py`), a Bash PreToolUse hook (`lazy-cycle-containment.sh`), and skill/component prose. Validation is the repo's Python `--test` smoke harnesses + `pytest user/scripts/ -q` + `lazy_parity_audit.py --report` + `project-skills.py` / `lint-skills.py`.

**Status:** Not-started

## Root-cause recap (from the concluded investigation)

A cycle subagent can call `lazy-state.py --cycle-end` (the **KEYSTONE** — Theory 1 / Proven Finding 1). That single call deletes `lazy-cycle-active.json`, the only signal C2's commit tripwires and C3's entire subagent detection can reach today. The marker-clear is guarded by neither C2 (`--cycle-end` absent from `LOOP_FORMATION_FLAGS`) nor C3 (`--cycle-end` absent from `CYCLE_REFUSED_OPS`, and its handler clears before any refusal check). Every prior fix recurred because it keyed on either a marker the contained party can delete or an arming step the orchestrator can skip.

The mechanical fix is two load-bearing parts that must land together:
1. A **positive, marker-independent** subagent signal (`LAZY_ORCHESTRATOR` is already read by `refuse_if_cycle_active` at priority 1, but **no skill exports it today** — confirmed by grep: only `lazy_core.py` reads it, nothing sets it). The orchestrator must export it so containment no longer degrades to the deletable marker.
2. **Guard `--cycle-end`** (and `--cycle-begin`) against subagent callers in both C2 (hook flag set) and C3 (refusal set), keyed on the fix-#1 signal so the marker cannot carry its own protection.

Defense-in-depth and occurrence-rate fixes follow (Skill-tool deny, prompt reshape).

## Cross-feature Integration Notes

- **`lazy-cycle-containment` (the C1–C8 machinery, `COMPLETED.md` `dcf36ba7`):** this bug hardens the SAME three layers that feature built — C2 hook `lazy-cycle-containment.sh`, C3 refusals in `lazy_core.py`, C4 prose in `cycle-base-prompt.md`. The `refuse_if_cycle_active` priority order (LAZY_ORCHESTRATOR → LAZY_CYCLE_SUBAGENT → marker) and `CYCLE_REFUSED_OPS` set are that feature's contract; phases below extend them, they do not redesign them.
- **`hardening-blind-to-process-friction` Phase 1 / D4 (`dd4a9f80`, `3e2fb215`):** retargeted C2's recursion/lifecycle trip onto `agent_id` presence (arming-free) and made C3 `agent_id`-aware via the env-var priority. That fix established the `LAZY_ORCHESTRATOR`-truthy → never-refuse path used by Phase 1 here. Its Open Question (does the Bash PreToolUse payload carry `agent_id`?) is re-raised by Phase 2's C2-hook work and resolved there.

## Coupling / parity contract (applies to every phase)

`lazy-state.py`, `bug-state.py`, and `lazy_core.py` are a coupled set (per `user/scripts/CLAUDE.md` Coupling Rule + `.claude/skill-config/quality-gates.md`). Every state-machine change here:
- lands the shared logic in `lazy_core.py` once (single source of truth), then mirrors any per-script handler edit into **both** `lazy-state.py` (feature) **and** `bug-state.py` (bug) — their `--cycle-end` handlers and refusal call-sites are byte-parallel (lazy-state `5726`/`5743`/`5791`; bug-state `4083`/`4098`/`4141`).
- keeps **both** in-file `--test` suites green (`lazy-state.py --test`, `bug-state.py --test`) plus `lazy_coord.py --test` and `pytest user/scripts/ -q`, and re-pins the byte baselines via the `_normalize_smoke_output` helper (never by hand).
- runs `lazy_parity_audit.py --report` — a new canonical behavioral unit must be mirrored to every twin (lazy-batch ↔ lazy-batch-cloud ↔ lazy-bug-batch) or registered as a per-pair divergence.

**Completion (gate-owned):** the top-level SPEC.md `**Status:**` flip to Fixed, the `FIXED.md` receipt, and any archive move are owned exclusively by the orchestrator's `__mark_fixed__` gate after the validation tail. No phase below authors them.

---

### Phase 1: Export the positive orchestrator signal (`LAZY_ORCHESTRATOR=1`)

**Scope:** Make subagent identity a positive, marker-independent signal. The orchestrator asserts its own identity by exporting `LAZY_ORCHESTRATOR=1` into the persistent session env it runs `lazy-state.py` / `bug-state.py` from, so C3's priority-1 branch (`_env_truthy("LAZY_ORCHESTRATOR")` → never refuse) actually fires for the real orchestrator, and the **absence** of the var is what marks a subagent — independent of the deletable marker. This is the load-bearing precondition for Phase 2's `--cycle-end` guard (which keys on this signal, since the marker can't protect itself).

This phase exports the signal and proves the existing priority logic resolves correctly; it does NOT yet add `--cycle-end` to the refused set (Phase 2).

**Deliverables:**
- [x] In `user/skills/lazy-batch/SKILL.md`, add an orchestrator-startup step (alongside the existing `--run-start` setup) that exports `LAZY_ORCHESTRATOR=1` for the session before any `lazy-state.py` lifecycle/routing call — e.g. `export LAZY_ORCHESTRATOR=1` emitted once at run start, documented as the C3 self-immunity signal.
- [x] Mirror the same export into the two twins: `user/skills/lazy-bug-batch/SKILL.md` and `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (parity contract — the orchestrator-startup shape is shared).
- [x] Confirm `lazy_core.refuse_if_cycle_active` priority-1 (`LAZY_ORCHESTRATOR` truthy → return without refusing) needs no code change — it is already implemented. Added a code comment cross-referencing this bug (the wiring was read-but-never-set until this phase).
- [x] Tests: a `lazy_core` unit test (in `user/scripts/test_lazy_core.py`) asserting `refuse_if_cycle_active("--run-end")` returns silently when `LAZY_ORCHESTRATOR=1` is set **even with a cycle marker present** (structural immunity to a stale marker), and exits 3 (subagent) when it is unset and a marker is present. (Already present: `test_refuse_guard_orchestrator_env_never_refuses_even_with_marker` + `test_refuse_guard_marker_backstop_still_refuses_no_env` cover both arms.)

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -q -k cycle` passes the new immunity test: with `LAZY_ORCHESTRATOR=1` + a written cycle marker, `refuse_if_cycle_active` does NOT raise `SystemExit(3)`; with the var unset + marker present, it raises `SystemExit(3)`.

**Runtime Verification** *(checked by the in-file / pytest harness):*
- [x] `python user/scripts/test_lazy_core.py` (or `pytest user/scripts/test_lazy_core.py -q`) green, including the new immunity/refusal assertions.

**Prerequisites:** None (first phase).

**Implementation Notes (2026-06-16, inline cycle subagent — no Agent tool):**
- All three orchestrators now `export LAZY_ORCHESTRATOR=1` at Step 0.55 immediately before `--run-start`, with a rationale comment naming this bug. The lazy-batch-cloud "Differences" table gained a row registering the export as **MIRRORED (shared)**, not a divergence.
- `lazy_core.refuse_if_cycle_active` priority-1 needed no logic change; added a cross-ref comment marking the export as the now-load-bearing positive carrier (was read-but-never-set).
- **Pre-existing test-isolation defect surfaced + fixed in-cycle (⚖ scope-class):** `lazy-state.py --test` failed under a LIVE cycle marker because the `materialize_wi` bug route shells `bug-state.py --enqueue-adhoc` as a subprocess that inherited the ambient marker → C3 refused (exit 3) → `check=True` raised. This is the orchestrator-side enqueue, so it now passes `env={**os.environ, "LAZY_ORCHESTRATOR": "1"}` to the child, making the call hermetic against an ambient marker. Both `--test` suites green again; baselines unaffected (the materialize output is identical to the no-marker path).
- Verified end-to-end: with `LAZY_ORCHESTRATOR=1` set, the full `lazy-state.py --test` passes even with the live marker — proving the export grants real immunity through the priority-1 branch.

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md` — export `LAZY_ORCHESTRATOR=1` at orchestrator startup.
- `user/skills/lazy-bug-batch/SKILL.md` — twin export (parity).
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — twin export (parity).
- `user/scripts/lazy_core.py` — comment cross-ref only (logic already present at `5736-5778`).
- `user/scripts/test_lazy_core.py` — new env-var immunity/refusal unit tests.

**Testing Strategy:** Unit-test the priority resolution directly against `lazy_core` (hermetic, env-var injectable). No state-machine wiring changes in this phase, so the `--test` baselines should be unaffected; run them to confirm zero drift.

**Integration Notes for Next Phase:**
- After this phase, `LAZY_ORCHESTRATOR` is a *live* positive signal, not dead config. Phase 2's `--cycle-end` guard keys on the SAME `refuse_if_cycle_active` resolution — so once Phase 1 lands, adding `--cycle-end` to the refused set automatically inherits the orchestrator-immunity (priority-1) and subagent-deny (priority-2/3) behavior. The two phases MUST ship together to be load-bearing (Proven Finding 2); do not mark the feature fixed on Phase 1 alone.
- The export must reach the env the orchestrator's Bash `lazy-state.py` calls run in (a `git-bash`/WSL session export), NOT just a one-shot inline prefix on a single command — the orchestrator makes many lifecycle calls across a run.

---

### Phase 2: Guard `--cycle-end` / `--cycle-begin` against subagent callers (KEYSTONE)

**Scope:** Close the marker-clear bootstrap hole — the confirmed root cause. A cycle subagent must be *structurally unable* to clear the containment marker. Two coordinated changes keyed on Phase 1's positive signal:
- **C3 (state script):** add `--cycle-end` (and `--cycle-begin`) protection so a subagent caller is refused **before** `clear_cycle_marker()` runs. Because the orchestrator legitimately owns the bracket, the guard must NOT use the plain `refuse_if_cycle_active` marker-fallback for `--cycle-end` (the orchestrator's own `--cycle-end` runs while the marker is still present). Instead it keys on the **positive** signal: `LAZY_ORCHESTRATOR` truthy → allow the clear; otherwise (subagent) → refuse with zero side effects. This is why Phase 1 is a hard prerequisite.
- **C2 (hook):** add `--cycle-end` and `--cycle-begin` to `LOOP_FORMATION_FLAGS` so the arming-free `agent_id` subagent trip denies a subagent's `lazy-state.py --cycle-end` regardless of marker state (belt-and-suspenders with C3).

**Deliverables:**
- [ ] In `user/scripts/lazy_core.py`, add a marker-clear guard helper (e.g. `refuse_cycle_marker_mutation_if_subagent("--cycle-end")`) that refuses (exit 3, corrective stderr, zero side effects) when `LAZY_ORCHESTRATOR` is NOT truthy AND a subagent context is indicated (explicit `LAZY_CYCLE_SUBAGENT`, OR — the reachable signal — the absence of `LAZY_ORCHESTRATOR` while a cycle marker is present). Document why `--cycle-end` cannot use the plain `refuse_if_cycle_active` (orchestrator clears under a live marker).
- [ ] Wire the guard at the ENTRY of the `--cycle-end` handler in `user/scripts/lazy-state.py` (`5726`) BEFORE `cycle_end_friction_check` / `clear_cycle_marker`, and mirror into `user/scripts/bug-state.py` (`4083`).
- [ ] Apply the same guard to the `--cycle-begin` handler in both scripts (`lazy-state.py:5707`, `bug-state.py:4065`) — a subagent must not arm/re-arm a marker either. Preserve the orchestrator's self-healing overwrite (it asserts `LAZY_ORCHESTRATOR`, so it is never refused).
- [ ] In `user/hooks/lazy-cycle-containment.sh`, add `--cycle-end` and `--cycle-begin` to the `LOOP_FORMATION_FLAGS` tuple (`:102-106`) so the `agent_id` subagent trip (`:258-259`) denies them.
- [ ] Keep `CYCLE_REFUSED_OPS` lockstep: document in the module comment (`lazy_core.py:5705-5712`) that `--cycle-end`/`--cycle-begin` are guarded by the dedicated marker-mutation helper rather than added to `CYCLE_REFUSED_OPS` (whose members use the marker-fallback that `--cycle-end` cannot). The C2/C3 deny *scope* still matches: subagent → cannot clear/arm the marker.
- [ ] Tests: `lazy_core` unit tests for the new guard (orchestrator allowed, subagent refused with exit 3 and marker untouched); new `--test` fixtures in BOTH `lazy-state.py` and `bug-state.py` asserting a subagent-context `--cycle-end` is refused and the marker file still exists afterward; a hook test (in the existing hook test module, if present) asserting the `agent_id`-present payload denies `lazy-state.py --cycle-end`.

**Minimum Verifiable Behavior:** With a cycle marker on disk and `LAZY_ORCHESTRATOR` unset (subagent), `python user/scripts/lazy-state.py --cycle-end` exits 3, prints the corrective message, and the marker file is STILL present (zero side effects). With `LAZY_ORCHESTRATOR=1` (orchestrator), the same call clears the marker and exits 0 — the orchestrator's bracket teardown is unaffected.

**Runtime Verification** *(checked by the harnesses):*
- [ ] `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` green (new refusal fixtures included); byte baselines re-pinned via `_normalize_smoke_output`.
- [ ] `python -m pytest user/scripts/ -q` green (lazy_core guard tests + hook test).
- [ ] Manual hook check: pipe a `{"agent_id":"x","tool_name":"Bash","tool_input":{"command":"python3 lazy-state.py --cycle-end"}}` payload through `lazy-cycle-containment.sh` and confirm a `permissionDecision: deny` is emitted; the same payload WITHOUT `agent_id` emits no decision (allow).

**Prerequisites:**
- Phase 1: `LAZY_ORCHESTRATOR=1` is exported by the orchestrator — the guard's allow-path keys on it. Without Phase 1 the guard would refuse the orchestrator's own legitimate `--cycle-end` and wedge the pipeline.

**Files likely modified:**
- `user/scripts/lazy_core.py` — new marker-mutation guard helper + module comment update.
- `user/scripts/lazy-state.py` — guard at `--cycle-end` (`5726`) and `--cycle-begin` (`5707`) entry; new `--test` fixtures.
- `user/scripts/bug-state.py` — mirror guard at `--cycle-end` (`4083`) and `--cycle-begin` (`4065`); new `--test` fixtures.
- `user/hooks/lazy-cycle-containment.sh` — add `--cycle-end`/`--cycle-begin` to `LOOP_FORMATION_FLAGS`.
- `user/scripts/test_lazy_core.py` (+ hook test module) — guard unit/integration tests.
- `tests/baselines/lazy-state-test-baseline.txt`, `tests/baselines/bug-state-test-baseline.txt` — re-pinned baselines.

**Testing Strategy:** Hermetic env-var + temp-marker fixtures assert refuse-vs-allow and the zero-side-effect invariant (marker still on disk after a refused clear). The hook side is tested by piping a synthetic PreToolUse payload (with/without `agent_id`) through the script and asserting the JSON decision — the hook already supports hermetic testing via `LAZY_CYCLE_STAGED_PATHS`; reuse that harness style.

**Integration Notes for Next Phase:**
- The keystone is now closed: a subagent cannot delete or re-arm the marker, so C2's commit tripwires and C3's marker-fallback can no longer be bootstrapped away. Phases 3–4 are defense-in-depth and occurrence-rate, NOT load-bearing — the feature is mechanically fixed after this phase + Phase 1.
- Resolve the SPEC Open Question while doing the hook work: confirm the Bash PreToolUse payload carries `agent_id` for the subagent's `lazy-state.py` Bash calls. If it does NOT (only `Agent`/`Task` events carry it), record that the C3 env-var guard (Phases 1–2) is the load-bearing carrier and the C2 hook flag-set addition is the secondary layer — do not regress to a marker-only assumption.

---

### Phase 3: Deny the `/lazy*` Skill-tool path for cycle subagents (defense-in-depth)

**Scope:** Close the unintercepted Skill-tool path (Theory 4 / secondary). Today the C2 hook intercepts only `Agent`/`Task`/`Bash` (`lazy-cycle-containment.sh:236-247`) — a subagent can invoke `/lazy-batch` (or any `/lazy*`) via the **Skill** tool, bypassing every Bash/Agent guard. Extend the hook to intercept the `Skill` tool: when `agent_id` is present (subagent) and the skill name matches `^/?lazy(-bug)?(-batch)?(-cloud)?$`, DENY.

**Deliverables:**
- [ ] In `user/hooks/lazy-cycle-containment.sh`, add a `Skill`-tool branch in `main()` (alongside the `Agent`/`Task` branch at `:236`): when `is_subagent` and the resolved skill name matches the `/lazy*` family regex, `_deny(CORRECTIVE)`; main-thread (no `agent_id`) → allow.
- [ ] Define the skill-name regex anchored to the lazy family (`lazy`, `lazy-bug`, `lazy-batch`, `lazy-bug-batch`, `lazy-cloud`, `lazy-batch-cloud`) — read the skill name from the `Skill` tool's payload field (confirm the exact field name from a real `Skill` PreToolUse payload before hardcoding).
- [ ] Preserve fail-OPEN: an unrecognized payload shape / missing skill-name field must allow, never wedge.
- [ ] Tests: hook test asserting `{"agent_id":"x","tool_name":"Skill","tool_input":{"skill":"lazy-batch"}}` denies, the same without `agent_id` allows, and a non-lazy skill (e.g. `commit`) allows even with `agent_id`.

**Minimum Verifiable Behavior:** Piping a subagent `Skill` payload invoking `lazy-batch` through `lazy-cycle-containment.sh` emits `permissionDecision: deny`; a non-lazy skill or a main-thread (no `agent_id`) invocation emits no decision.

**Runtime Verification** *(checked by the hook harness):*
- [ ] `python -m pytest user/scripts/ -q` green (hook Skill-tool tests).

**Prerequisites:**
- Phase 2: the mechanical keystone is closed first; this is layered defense, sequenced after the load-bearing fix.

**Files likely modified:**
- `user/hooks/lazy-cycle-containment.sh` — new `Skill`-tool intercept branch + family regex.
- hook test module — Skill-tool deny/allow assertions.

**Testing Strategy:** Synthetic PreToolUse payloads for the `Skill` tool, asserting the deny JSON. Verify the actual payload field that carries the skill name against a real Claude Code `Skill` PreToolUse event before committing the field reference (the SPEC flags this as an implementation detail to confirm, not assume).

**Integration Notes for Next Phase:**
- The Skill tool now cannot reach `/lazy*` from a subagent. Combined with Phases 1–2, the three reachable orchestrator-emulation paths (Bash routing flags, recursive Agent/Task, Skill-tool `/lazy*`) are all denied for a subagent. Phase 4 is purely occurrence-rate (prompt-side) and changes no enforcement.

---

### Phase 4: Stop teaching the subagent the orchestrator playbook (prompt-side, occurrence-rate — NOT load-bearing)

**Scope:** Lower the *trigger rate* (Theory 5 / Finding 3) by re-shaping `cycle-base-prompt.md` so the cycle prompt reads as a one-shot **worker** brief, not a pipeline-**operator** brief. This is explicitly **complementary and NOT a substitute** for the mechanical guards (a determined model can still read the skills on disk) — it ships only AFTER Phases 1–2 make the "harness will DENY these in-flight" assurance actually true. ⚖ policy: include SPEC fix #4 (complementary) → in-scope as a final phase (scope-class: it lowers occurrence and is fully specified by the concluded SPEC; not shipped as the sole/primary fix).

**Deliverables:**
- [ ] In `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`, soften the operator framing of the opening line (`:72`, and the cloud variant `:88`) — e.g. lead with "Run exactly one skill, then stop" rather than (or alongside) "You are advancing one cycle of the autonomous {pipeline_phrase}." Keep enough context that the worker knows what artifact it owns.
- [ ] In the `TERMINAL STOP` section (`:377-383`), state the boundary WITHOUT enumerating the orchestrator API: replace the explicit `--run-end`/`--run-start`/`--apply-pseudo`/`--enqueue-adhoc`/`dev:kill`/`dev:restart` list with a categorical instruction (e.g. "Do not run pipeline/orchestration or lifecycle commands, and do not invoke any `/lazy*` skill; if you finish, are blocked, or are unsure, write your report and STOP"). Keep the "the harness will DENY these in-flight" assurance (now true after Phases 1–3) — drop the command catalog that doubles as a how-to.
- [ ] Leave the `inline-override` "never invoke another /lazy or /lazy-batch" prohibition (`:137`, `:148`) intact — it is still correct; just ensure it no longer reads as the *only* surviving prohibition now that the categorical TERMINAL STOP language covers lifecycle ops.
- [ ] Re-expand the component and confirm all three orchestrators (lazy-batch, lazy-bug-batch, lazy-batch-cloud) pick up the reshaped prose via projection.
- [ ] Tests: `project-skills.py` re-expansion is clean (no broken `!cat`); `lint-skills.py --check-projected --check-capabilities` passes; a spot-check that the `{pipeline_phrase}` / cloud-variant token substitution still resolves in the projected output.

**Minimum Verifiable Behavior:** `python user/scripts/project-skills.py` re-expands with no circular-include / missing-component error, and the projected `cycle-base-prompt` content shows the reshaped worker framing + the de-enumerated TERMINAL STOP (grep the projected output for the absence of the literal `--run-start`/`--run-end` command list inside the cycle prompt).

**Runtime Verification** *(checked by the skill-lint gates):*
- [ ] `python user/scripts/project-skills.py` clean.
- [ ] `python user/scripts/lint-skills.py --check-projected --check-capabilities` clean.
- [ ] `python user/scripts/lazy_parity_audit.py --report` — no unexplained drift across the three orchestrator twins after the prose reshape.

**Prerequisites:**
- Phases 1–2: the "harness will DENY these in-flight" assurance must be TRUE before the prompt promises it without naming the commands. Sequencing matters — do not ship the prose change ahead of the mechanical guards.

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — opening framing + TERMINAL STOP reshape.
- (projected output regenerated by `project-skills.py` — generated, not hand-edited.)

**Testing Strategy:** Skill-projection + lint gates (this repo's "build"). The change is prose; correctness = clean expansion, clean lint, and parity audit showing the three orchestrators stay in lockstep. No state-machine `--test` impact.

**Integration Notes for Next Phase:** Final phase. When this phase's work lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) and let the state machine route to validation. Do NOT flip SPEC `**Status:**` or write `FIXED.md` — gate-owned.
