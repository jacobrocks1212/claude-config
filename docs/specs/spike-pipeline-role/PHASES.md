# Spike — Runtime-Proof Pipeline Role — Phases

**Status:** In-progress (Phase 1 landed 2026-07-17; Phases 2–6 surfaced)

This is a hand-implemented harness spec (`docs/specs/`, outside the autonomous lazy pipeline).
Phases are worked directly. Phase 1 is the FOUNDATIONAL round (harden Round 80): the
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
**Status:** Not started
**Phase kind:** design

Wire the parse primitive into live routing. RISK: changes what the live state machine returns.

- [ ] `compute_state` Step 9.5 (`lazy-state.py`, between the Step 9 MCP-gate returns and the
  Step 10 `entry_ok` check): emit `sub_skill="spike"` when a phase declares `**Spike:** required`
  and the spike verdict is not yet PASS; gate Step 10 `entry_ok` on the spike verdict doc
- [ ] `blocker_kind: runtime-spike-verdict-pending` routes to a `spike` cycle (not the generic
  manual-block terminal); a `runtime-spike-verdict-pending` escalation branch beside
  `validation_escalation` (`gates.py` / `lazy-state.py:~3055`)
- [ ] **Coupled mirror into `bug-state.py`** (the `lazy-state.py` ↔ `bug-state.py` pair; run
  `lazy_parity_audit.py`)
- [ ] TDD: state-machine tests for both entry signals (prescribed header + blocked resolver) and
  the Step-10 gate

---

### Phase 3: Orchestrator-loop wiring (lazy-batch + coupled mirrors)
**Status:** Not started
**Phase kind:** design

- [ ] A Spike Step in `lazy-batch/SKILL.md`: ensure-runtime pre-boot for `spike` cycles (reuse
  `--ensure-runtime`, orchestrator-owned), PASS→continue / FAIL→NEEDS_INPUT+halt branching, the
  `--park --park-provisional` PARK-not-accept path for FAIL
- [ ] Emit the spike dispatch via `--emit-dispatch spike` (the registered class from Phase 1) using
  the `spike-dispatch.md` component
- [ ] **Coupled mirror into `lazy-bug-batch` + `lazy-batch-cloud`** via the overlay generator
  (`generate-coupled-skills.py --write`; then `--check`). Cloud defers the runtime spike to
  workstation (like `/investigate` / `/mcp-test`)

---

### Phase 4: Tooling-existence loop + bound
**Status:** Not started
**Phase kind:** design

- [ ] Spike asserts required tooling exists before the proof (reuse the `mcp-tool-catalog.md`
  tool-existence audit); on a gap, route to `/add-phase` corrective (tagged `corrective`, carrying
  a `**Spike:**` line so control returns)
- [ ] `spike_tooling_rounds` counter on the entry sentinel/feature state; hard cap (default 3) →
  `NEEDS_INPUT.md` instead of another loop. Loop can NEVER spin forever
- [ ] TDD: the loop fires, returns to Spike, and the cap halts

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
