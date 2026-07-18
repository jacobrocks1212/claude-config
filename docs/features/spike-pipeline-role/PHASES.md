# Spike — Runtime-Proof Pipeline Role — Phases

**Status:** In-progress (Phase 1 landed 2026-07-17; Phases 2–6 surfaced)

This is a harness spec now under lazy-pipeline management (relocated to
`docs/features/spike-pipeline-role/`, enqueued 2026-07-17). Phase 1 was hand-implemented as the
FOUNDATIONAL round (harden Round 80); Phases 2–6 are driven by the autonomous pipeline. Phase 1: the
self-contained, fully-tested primitives that make Spike dispatchable and parseable WITHOUT
destabilizing the live `compute_state` state machine. Phases 2–6 are the routing/orchestration
surgery, phased because each changes what the live pipeline returns for real features and must
carry its own TDD + coupled-pair mirroring.

---

### Phase 1: Foundational primitives (dispatch class + parse + carve-out + prescription)
**Status:** Complete

The mechanical core — inert with respect to live routing (nothing in `compute_state` calls the
new parse yet), so it ships safely in one round under full gates.

- [x] `spike` added to `DISPATCH_CLASSES` (before `hardening`, keeping it last), `DISPATCH_MODELS`
  (`"spike": "opus"`), `DISPATCH_STEP_NAMES` (`"spike": "Spike"`) — `lazy_core/dispatch.py`
- [x] `dispatch-spike.md` template authored — the Opus subagent contract (honesty discipline,
  tooling-existence loop, structured report, PASS/FAIL, orchestrator-owned runtime)
- [x] `spike-dispatch.md` orchestrator component authored (emit-reference, like
  `investigation-dispatch.md`)
- [x] `phases_spike_required(spec_path)` + `_read_spike_decision(spec_path)` parse primitives in
  `docmodel.py`, exported via `__init__.py` — anchored regex mirroring
  `phases_mcp_runtime_not_required` (INERT — the parse primitive routing will consume in Phase 2)
- [x] Provisional-eligibility carve-out: Spike FAIL (`written_by: spike` / `spike_verdict: fail`)
  never provisional-eligible — `provisional_eligibility` in `docmodel.py`
- [x] AlgoBooth-scoped prescription addenda updated (`/spec`, `/spec-phases`, `/add-phase` know
  about + prescribe Spike) — `repos/algobooth/.claude/skill-config/`
- [x] Tests: `test_dispatch.py` class-list updates (len 9→10, spike present, hardening still last);
  new tests for the spike-parse primitive + the provisional carve-out
- [x] Full gate battery green (test_lazy_core, test_hooks, lint-skills, lazy-state.py --test,
  bug-state.py --test, parity, generate-coupled-skills --check, project-skills, doc-drift-lint)

---

### Phase 2: State-machine routing (`compute_state` Step 9.5)
**Status:** Complete
**Phase kind:** design

Wire the parse primitive into live routing. RISK: changes what the live state machine returns.

- [x] `compute_state` Step 9.5 (`lazy-state.py`, between the Step 9 MCP-gate returns and the
  Step 10 `entry_ok` check): emit `sub_skill="spike"` when a phase declares `**Spike:** required`
  and the spike verdict is not yet PASS; gate Step 10 `entry_ok` on the spike verdict doc
- [x] `blocker_kind: runtime-spike-verdict-pending` routes to a `spike` cycle (not the generic
  manual-block terminal); a `runtime-spike-verdict-pending` escalation branch beside
  `validation_escalation` (`gates.py` / `lazy-state.py:~3055`)
- [x] **Coupled mirror into `bug-state.py`** (the `lazy-state.py` ↔ `bug-state.py` pair; run
  `lazy_parity_audit.py`)
- [x] TDD: state-machine tests for both entry signals (prescribed header + blocked resolver) and
  the Step-10 gate

**Implementation Notes (2026-07-18, plan part 1):**
- **New shared helper** `spike_verdict_is_pass(spec_path)` in `lazy_core/docmodel.py` (exported via
  `__init__.py`), beside the Phase-1 `phases_spike_required`/`_read_spike_decision`. Tolerant frontmatter
  read of `{spec_dir}/SPIKE_VERDICT.md` — True only on `verdict: PASS` (case-insensitive); absent/unreadable
  ⇒ False ⇒ route to spike. No new recognized sentinel (SPEC non-goal preserved).
- **New predicate** `spike_escalation(meta)` in `lazy_core/gates.py` (exported) — faithful shape-mirror of
  `validation_escalation` (bool-reject, str-digit tolerance, `>= 2` threshold) gated to
  `blocker_kind == "runtime-spike-verdict-pending"`. Standalone/unit-tested; its CONSUMPTION (tooling-round
  cap) is deferred to Part 3. The Step-3 routing itself fires UNCONDITIONALLY on the blocker_kind (not gated
  on escalation).
- **Two routing seams, both state scripts (coupled pair, byte-identical routing):**
  Step 9.5 header gate (`lazy-state.py` ~3806 / `bug-state.py` ~1976, between the Step-9 MCP returns and
  Step-10) → `current_step="Step 9.5: spike verdict pending"`; Step-3 blocked-resolver
  (`lazy-state.py` ~3053 / `bug-state.py` ~1520, before the generic `blocked` terminal) →
  `current_step="Step 3: spike verdict pending (blocked resolver)"`, non-terminal. Only the builder
  (`_state`/`_bug_state`) + Step-10 terminal (`__mark_complete__`/`__mark_fixed__`) diverge.
- **Tests:** new `user/scripts/test_spike_state_routing.py` (14 pytest cases, feature+bug axes) + in-file
  `--test` fixtures on both scripts (spike-required-no-verdict, spike-required-pass-verdict,
  spike-blocker-resolver) with both baselines regenerated + `spike_escalation` units in
  `tests/test_lazy_core/test_pseudo.py` (7). `lazy_parity_audit.py --repo-root .` exits 0 — no parity-manifest
  change needed (spike routing is not yet a registered surface token; the `--test` scenarios driving both
  scripts to identical routing are the real body-parity guard).

---

### Phase 3: Orchestrator-loop wiring (lazy-batch + coupled mirrors)
**Status:** Complete
**Phase kind:** design

- [x] A Spike Step in `lazy-batch/SKILL.md`: ensure-runtime pre-boot for `spike` cycles (reuse
  `--ensure-runtime`, orchestrator-owned), PASS→continue / FAIL→NEEDS_INPUT+halt branching, the
  `--park --park-provisional` PARK-not-accept path for FAIL
- [x] Emit the spike dispatch via `--emit-dispatch spike` (the registered class from Phase 1) using
  the `spike-dispatch.md` component
- [x] **Coupled mirror into `lazy-bug-batch` + `lazy-batch-cloud`** via the overlay generator
  (`generate-coupled-skills.py --write`; then `--check`). Cloud defers the runtime spike to
  workstation (like `/investigate` / `/mcp-test`)

**Implementation Notes (2026-07-18, plan part 2):** Added a new **§1c.7 "Spike cycle handling"**
section to the canonical `user/skills/lazy-batch/SKILL.md` (between §1c.5 pseudo-skill handling and
§1d), intercepting a probe `sub_skill == "spike"` (routed by Phase-2 `compute_state` Step 9.5 /
Step 3): Step A pre-boots the orchestrator-owned runtime via `lazy-state.py --ensure-runtime`
(reusing §1d.0's exact conjunction `state==READY AND health_code==200 AND mcp_tools_present`);
Step B emits `--emit-dispatch spike` and dispatches the returned prompt VERBATIM (Opus, cycle-marker
bracketed, `dispatch_prompt_ref`-preferred); Step C branches PASS→continue / FAIL→halt (spike wrote
`NEEDS_INPUT.md` `written_by: spike`), with the explicit **PARK-not-accept** rule for a Spike FAIL
under `--park --park-provisional` (agreeing with the already-implemented `lazy_core.provisional_
eligibility` fail-closed carve-out). Tooling-gap routing is deferred to Phase 4 (referenced, not
implemented). Added a matching **State Machine Summary** bullet. **Coupled mirror (WU-2):** authored
the axis-appropriate §1c.7 into both derived skills — `lazy-bug-batch` (bug vocab: `bug-state.py` /
`bug_id` / `bug_name` / mark-fixed gate; `--ensure-runtime` correctly kept on `lazy-state.py`, the
feature-hosted subcommand) and `lazy-batch-cloud` (**defer-to-workstation** divergence: record trigger
+ PENDING `SPIKE_VERDICT.md`, never boot a runtime / dispatch / fabricate a verdict) — then
`generate-coupled-skills.py --extract` → `--write` → `--check` (byte-identical, exit 0). Registered
§1c.7 in `lazy-parity-manifest.json` `headings[]` (bug=restated, cloud=divergence+reason). Raised the
three `skill-size-baseline.json` ceilings for the deliberate legitimate growth. Docs-only orchestrator
contract (no runtime rows / no MCP gate for this phase).

---

### Phase 4: Tooling-existence loop + bound
**Status:** Complete
**Phase kind:** design

- [x] Spike asserts required tooling exists before the proof (reuse the `mcp-tool-catalog.md`
  tool-existence audit); on a gap, route to `/add-phase` corrective (tagged `corrective`, carrying
  a `**Spike:**` line so control returns)
- [x] `spike_tooling_rounds` counter on the entry sentinel/feature state; hard cap (default 3) →
  `NEEDS_INPUT.md` instead of another loop. Loop can NEVER spin forever
- [x] TDD: the loop fires, returns to Spike, and the cap halts

**Implementation Notes (2026-07-18, plan part 3):**
- **WU-1 (add-phase authoring):** `/add-phase` (`user/skills/add-phase/SKILL.md`, Step 4) now carries
  a HARD "Spike return line for a tooling-gap corrective phase" block: when the corrective route is
  taken because a Spike's required tooling did not exist, the drafted phase tags `corrective` AND
  carries a `**Spike:** required — <original goal verbatim>` return line, so Part-1's
  `phases_spike_required`/`_read_spike_decision` header gate re-routes to a spike cycle once the
  tooling phase completes. The tool-existence audit itself is NOT re-authored (the Spike subagent
  already greps the live registry via `phases-runtime-validation.md` + the per-repo
  `mcp-tool-catalog.md`); this WU only wires the return line. Prose-only (no unit test — validated by
  `project-skills.py` + `lint-skills.py`).
- **WU-2 (machine-enforced bound):** the loop can NEVER spin forever. New shared helpers in
  `lazy_core`: `_SPIKE_TOOLING_ROUNDS_CAP = 3` + `spike_tooling_cap_exceeded(meta, cap=None)`
  (`gates.py`, immediately after `spike_escalation`, identical int/digit-string/bool-reject/missing
  tolerances; NOT gated on `blocker_kind` — a pure count check reused across both routing seams) and
  `write_spike_tooling_cap_needs_input(spec_dir, item_name, rounds)` (`docmodel.py`, writes a
  `written_by: spike` NEEDS_INPUT.md so the Part-1 provisional carve-out refuses auto-accept under
  `--park --park-provisional`); both exported via `__init__.py`'s `_SUBMODULE_BY_NAME`. Wired at BOTH
  spike-routing seams — Step 3 blocked-resolver (reads `BLOCKED.md` meta) and Step 9.5 header gate
  (reads `SPIKE_VERDICT.md` meta) — in `lazy-state.py` AND coupled-mirrored into `bug-state.py`
  (shared helpers, zero per-script divergence; `lazy_parity_audit.py --repo-root .` exit 0). At
  `spike_tooling_rounds >= 3` the seam writes NEEDS_INPUT.md and returns `terminal_reason: needs-input`
  instead of routing to another spike loop. The counter is stamped by the Spike subagent (prose
  contract, the `retry_count`-on-sentinel pattern); the machine READS + caps + halts.
- **Files:** `user/skills/add-phase/SKILL.md`, `user/scripts/lazy_core/{gates,docmodel,__init__}.py`,
  `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/test_spike_tooling_loop.py` (31 tests, both axes × both seams).
- **Gotcha (environmental, NOT a regression):** running `pytest user/scripts/tests/test_lazy_core/`
  from inside a live `/lazy-batch` cycle yields ~82 `SystemExit(3)` failures — `apply_pseudo` hits
  `refuse_if_cycle_active()` against the real live `lazy-cycle-active.json` marker because those tests
  don't isolate `LAZY_STATE_DIR`. Reproduced identically on unmodified `main`; cleared by running with
  an isolated `LAZY_STATE_DIR` (test_pseudo.py: 1-fail-fast → 141 passed). Pre-existing test-isolation
  gap, out of this WU's scope.

---

### Phase 5: Verdict machinery reuse (optional engine)
**Status:** Not started
**Phase kind:** design

- [ ] Where a spike has a deterministic scenario, reuse the mcp-test `run.ts`/`verdict.ts` shape
  (compact verdict + sibling raw-payload artifact). For `/investigate`- or manual-measurement-form
  spikes, the results doc + INVESTIGATION.md ledger is the evidence — no engine
- [ ] Note: any engine code that lives in the AlgoBooth repo is an AlgoBooth-repo deliverable
  (outside harden-harness scope) — this phase scopes only the claude-config-side contract

---

### Phase 6: (Cross-repo, NON-harden-harness) recognized-sentinel promotion — IF wanted
**Status:** Not started — surfaced only
**Phase kind:** design

- [ ] IF the operator wants full lint/gate coverage of the verdict schema (Open Question 1),
  promote `SPIKE_VERDICT.md` to a recognized sentinel: add its schema to
  `sentinel-frontmatter.md` (claude-config) AND to AlgoBooth's
  `scripts/check-docs-consistency.ts SENTINEL_SCHEMAS` (**AlgoBooth repo — outside harden-harness
  scope; a normal AlgoBooth session must make this edit**)
- [ ] Until then, the verdict rides on a plain audit doc + already-recognized sentinels (Phase 1
  design), which is fully functional
