## Spike dispatch (shared — runtime-proof `/spike` cycle)

**Why this component exists.** A Spike is a dispatched runtime-proof cycle — it definitively
PROVES something about the running system (a runtime measurement, a GO/NO-GO verdict, a
confirm/deny of real behavior) instead of dead-ending into a manual operator block. This is the
single dispatch template for it — a **registered dispatch class** (`spike`, always Opus): the
orchestrator emits via `--emit-dispatch spike` (which registers the prompt in the prompt registry
so the validate-deny guard will allow it) and dispatches the returned `dispatch_prompt` VERBATIM.

**Origin.** `hydra-overlay` blocked on `blocker_kind: runtime-spike-verdict-pending`: a runtime
FPS measurement was needed to choose an architecture, but the pipeline had no stage to run the
proof. Spike fills exactly that gap. See `docs/specs/spike-pipeline-role/SPEC.md`.

**Runtime is ORCHESTRATOR-OWNED** — exactly like `/mcp-test`. Before dispatching a `spike` cycle
on a workstation, the orchestrator boots/owns the dev runtime via the same
`lazy-state.py --ensure-runtime` readiness gate mcp-test uses (route on the full
`{state, health_code, mcp_tools_present}` JSON); the Spike subagent DRIVES the runtime but never
boots a background runtime of its own (it would not survive the subagent's turn boundary).

### Triggers (when an orchestrator dispatches this)

1. **Prescribed** — a phase carries a `**Spike:** required — <proof goal>` declaration line
   (analogous to `**MCP runtime:**`), so the phase's completion rests on a runtime proof. The
   state machine routes that phase's completion through a `spike` cycle. (Routing wiring is phased
   — see `docs/specs/spike-pipeline-role/PHASES.md` Phase 2.)
2. **Ad-hoc / blocked** — a `BLOCKED.md` carries `blocker_kind: runtime-spike-verdict-pending`,
   naming Spike as its resolver. The state machine routes to a `spike` cycle rather than the
   generic manual-block terminal.
3. **Manual / operator** — the operator invokes a spike directly when a situation needs such a
   proof.

**Workstation-class work:** a runtime spike needs the live runtime. Cloud orchestrators record the
trigger (one line in the cycle log + the results-doc/BLOCKED.md notes) and DEFER the proof to a
workstation run instead of dispatching cloud-side (same discipline as `/investigate`).

### The honesty rule (binding on every consumer)

A Spike verdict MUST be backed by REAL OBSERVED evidence — a runtime number actually read, a test
result that actually ran, an `/investigate` ledger row actually confirmed. NEVER inferred,
NEVER fabricated, NEVER a static-trace substitute for the real measurement. A cycle that cannot
obtain real evidence returns `PENDING` (with `NEEDS_RUNTIME` or the tooling-gap signal), never a
confident fabricated verdict. This mirrors the discipline `SPIKE_PROJECTOR_FPS.md` states.

### Dispatch

**Operative path — `--emit-dispatch spike` (registry-validated, guard allows it).** The
orchestrator emits the dispatch via the script and uses the returned `dispatch_prompt` VERBATIM.
Hand-composing the prompt bypasses the registry and will be denied by the validate-deny guard on
any marked run:

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch spike \
  --context item_name="{feature_name}" \
  --context spec_path="{spec_path}" \
  --context spike_goal="{what must be proven — the **Spike:** line goal}" \
  --context next_on_pass="{what the SPEC/plan prescribes on PASS}" \
  --context item_id="{feature_id}" \
  --context cwd="{cwd}"
```

Use the returned `dispatch_prompt` VERBATIM as the `Agent` `prompt:` and `dispatch_model`
(`opus`) as the `model:`. The emit registers the prompt in the prompt registry; the guard will
allow it.

### The tooling-existence loop (bounded)

Spike checks the tooling it needs exists BEFORE running the proof (reusing the tool-existence
audit `/spec-phases` runs). On a gap it returns `tooling_ok: false` + the named missing tooling;
the orchestrator routes to the `/add-phase` corrective path (a corrective phase, tagged
`**Phase kind:** corrective`, carrying a `**Spike:**` line so control RETURNS here once the
tooling phase completes). This LOOPs if a further gap is found — with a HARD CAP
(`spike_tooling_rounds`, default 3): on exceeding it, Spike writes `NEEDS_INPUT.md` instead of
looping again, so the loop can NEVER spin forever.

### PASS/FAIL branching (what the orchestrator does with the verdict)

- **PASS** → the Spike recorded the verdict + evidence in the results doc and ticked the gated
  phase's spike deliverable (scoped reconcile; never top-status/receipt). Continue to the
  prescribed next cycle.
- **FAIL** → the Spike updated the results doc + the gated phase and wrote `NEEDS_INPUT.md`
  (`written_by: spike`, `spike_verdict: fail`). HALT and present to the operator.
  **NO provisional auto-accept** — this is a deliberate carve-out enforced in TWO places:
  `lazy_core.provisional_eligibility` rejects a Spike-authored NEEDS_INPUT (so the park-mode
  routing peek and `--provisionalize-sentinel` both refuse it), AND the Spike handler PARKS the
  feature under `--park --park-provisional` rather than accepting on recommendation.

### Consuming the artifact (downstream)

- **`/add-phase`:** a `tooling_ok: false` spike seeds a corrective tooling phase; a Spike FAIL's
  results doc + NEEDS_INPUT.md seed the operator decision. Where multiple corrective phases have
  already churned against the same runtime-coupled assumption, prescribe a Spike to definitively
  prove the assumption instead of another blind corrective.
- **completion gate:** a prescribed Spike's PASS is the runtime evidence the gated phase's
  completion rests on; the verdict doc is a permanent audit artifact.

### Coupling note

Consumed by: `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`,
`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (defer-to-workstation variant). The
dispatch template lives at `user/skills/_components/lazy-batch-prompts/dispatch-spike.md` — the
prompt lives THERE only; consumers reference via `--emit-dispatch spike`, never inline-copy. When
editing this component, `grep -rl "spike-dispatch.md" ~/.claude/skills/` to confirm the consumer
set. Orchestrator-loop wiring is phased — see `docs/specs/spike-pipeline-role/PHASES.md`.
