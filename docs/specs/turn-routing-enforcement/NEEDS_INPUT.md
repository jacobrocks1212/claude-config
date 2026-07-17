---
kind: needs-input
feature_id: turn-routing-enforcement
written_by: harden-harness
decisions:
  - "Dispatch-preference contract for Agent dispatches: keep `dispatch_prompt_ref` (@@lazy-ref) PREFERRED, or flip to verbatim `dispatch_prompt`?"
  - "Partial-VALIDATED → `__mark_complete__` oscillation: route back to `mcp-test` when the PHASES verification matrix is incomplete, or change what mints VALIDATED.md? (harden Round 45)"
  - "forward_cycles under-count in interleaved real+meta by-ref dispatch: reopen the archived `byref-dispatch-undercounts-forward-cycles` bug, or accept the low-impact under-count? (harden Round 45)"
  - "Dispatch-guard contract for WORKSTATION sub-subagent dispatches: how should `lazy_guard.py` distinguish a cycle worker's now-authorized test-agent/impl-agent split from an orchestrator improvising an unregistered cycle prompt, without weakening the integrity guard? (harden Round 9, 2026-07)"
  - "Completion-gate treatment of un-migrated + host-blocked verification rows: add a per-row host-capability deferral so a feature blocked only on host-unavailable backend verification can complete-modulo-deferral instead of all-or-nothing, and/or converge the completion recognizer with the routing bypass? (harden Round 22, 2026-07)"
  - "Corrective-coverage dispatch: add a registered `--emit-dispatch corrective-coverage` class (or a Step-10→mcp-test re-route) to author NEW mcp-test coverage for a genuinely-untested-but-testable row discovered at completion, since coherence-recovery correctly refuses implementation work and no legitimate dispatch path exists? (harden Round 22, 2026-07)"
  - "GATE_VERDICT.md authoring route: no sanctioned emit-dispatch class authors GATE_VERDICT.md for a genuinely-in-scope control-surface feature at __mark_complete__ — add a `gate-verdict` emit class, make it interactive-only, or move the gate to planning-time? (harden Round 36, 2026-07)"
  - "Provisional gate at the ship seam: should gate_verdict_ok (D3, STRUCTURALLY PROVISIONAL/unratified) hard-block completion before anti-overfit-design-gate is ratified, or degrade to advisory/planning-time until then? (harden Round 36, 2026-07)"
  - "Consumed-fence robustness under a re-emit after `--cycle-begin`: the operator-blessed sub-subagent exemption fence (decision 4) binds ONE nonce at `--cycle-begin`, but the freshness-rule re-emit makes the worker consume a DIFFERENT emission → fence dead → sub-subagent denied. Re-derive the fence at guard time, re-bind at re-emit, or enforce emit-before-cycle-begin — without weakening the integrity guard? (harden Round 46, 2026-07)"
  - "Operator per-feature host-defer not machine-enforced over a VALIDATED feature: an operator's 'defer whole feature' resolution (apply-resolution writes DEFERRED_REQUIRES_HOST.md, deferred_by: operator) drives NO skip because (a) the named capability ids are unregistered → unknown-capability BLOCKED.md fail-fast, and (b) the host-defer branch is `not VALIDATED.md`-gated but the feature has a validated-modulo-observation-gaps VALIDATED.md → re-routes to __mark_complete__ → gate re-refuses → re-writes NEEDS_INPUT, re-asking an answered decision. Register the service capabilities + honor an operator DEFERRED_REQUIRES_HOST.md over a validated-modulo feature, or add a per-feature host-defer of verification rows — without weakening the completion gate or false-greening? Bundles with #5/#6. (harden Round 47, 2026-07)"
  - "Turn-end verify-ledger mis-scoped for PLANNING cycles: the cycle-subagent `@section turn-end` TERMINAL VERIFY GATE injects `--verify-ledger` reconcile-until-ok:true with `skills=all`, but verify-ledger is the COMPLETION gate — a planning cycle (spec-phases/write-plan/plan-bug/plan-feature/spec/spec-bug) authors a Ready plan with unchecked deliverables → structurally ok:false → the reconcile loop is unsatisfiable without fabricating completion (Status-honesty forbids). Scope the verify-ledger substep to completion-capable skills only (mirror the orchestrator's already-shipped guardrail-D scope), or add a 'planning-ok' verdict mode to verify_ledger — which terminal guarantee should planning cycles carry? (harden Round 51, 2026-07)"
  - "forward_cycles OVER-count on non-dispatch inject-hook turns: the inject-hook `--repeat-count` probe advances forward_cycles via the consume-INDEPENDENT state-change trigger on notification turns (route changes, no dispatch), ballooning forward_cycles and false-hitting max_cycles so overnight runs end early. The evidence's consume-only fix reverses the 2026-07-16 `byref-forward-cycles-frozen-on-multicycle-same-step` + Theory-1b decisions and their pinned tests (symmetric under-count catastrophe). Move the forward-advance OFF banner-emission to actual dispatch time (subsuming decision #3's under-count too), or accept? (harden Round 55, 2026-07)"
  - "Operator recovery of a CRASHED run's orphaned markers is under-served: the containment guards (`refuse_if_cycle_active` / `refuse_cycle_marker_mutation_if_subagent`) key ONLY on marker-presence + env, consulting neither the marker's recorded session_id/started_at nor process liveness, so an operator tearing down a dead run's corpse from a fresh session is refused as a 'single cycle subagent' and must climb a 4-gate cascade (containment → efficacy-flush → terminal-reason) with no chain-aware guidance and no crash/disconnect terminal reason. Add a session-liveness/ownership teardown path, a first-class `--recover-stale-marker`/`--force-run-end` op, chain-aware messages, and/or a `crashed-run` sanctioned terminal reason — all authority/gate-semantics changes? (harden Round 58, 2026-07)"
  - "A `partial` MCP_TEST_RESULTS.md whose only uncovered rows are all documented-test-exempt/build-deferred has no AUTHORABLE path to VALIDATED.md: the `observation_gap_exemptions`→scoped-VALIDATED mechanism EXISTS (gates.py/pseudo.py, wired to 3 sites) but (a) the `mcp-test` SKILL never surfaces it so the producer invents a non-promoting `carve_outs` block, (b) the results file is engine-written and 'the model NEVER authors sentinels' so no shipped path emits the spec_class-bearing exemptions block, and (c) 'build-artifact-deferred' is not the documented observation-gap class. Bless model-authored exemptions / add an emit path, and classify build-artifact-deferred? Bundles with #2 and #9. (harden Round 59, 2026-07)"
date: 2026-06-16
class: product
divergence: structural
next_skill: harden-harness
---

## Decision Context

### 1. Dispatch-preference contract for Agent dispatches: keep `dispatch_prompt_ref` (@@lazy-ref) PREFERRED, or flip to verbatim `dispatch_prompt`?

**Problem:** Hardening defect D-C exposed that a bare `@@lazy-ref nonce=<hex>` token reached a subagent unresolved, and the subagent silently improvised an off-task `/lazy` run (which then caused the D-B run-marker clobber). The *mechanical* hole is now closed — `lazy_guard.py` denies a bare `@@lazy-ref` token whenever it cannot resolve+consume it (including the previously-silent marker-absent fast-path), with a corrective reason that prescribes the verbatim `dispatch_prompt` (Round 19 mechanical fix, this dispatch). So a bare ref token can never again reach a subagent.

What remains is a **contract-preference fork** that is NOT mechanical to decide. Today the skill prose actively makes the by-reference token the PREFERRED dispatch form:
- `lazy-batch/SKILL.md:619` — "F2a dispatch-by-reference (PREFERRED when available) … use it as the `prompt:` field instead of the full `cycle_prompt` text."
- `lazy-batch/SKILL.md:621` — "Meta-dispatch by-reference — PREFER `dispatch_prompt_ref` at ALL `--emit-dispatch` sites … PREFER `dispatch_prompt_ref` over the verbatim `dispatch_prompt`."
- Mirrored in `lazy-bug-batch/SKILL.md` (coupled pair).

This preference was introduced deliberately in Phase 7 / lazy-validation-readiness to eliminate the **transcription-slip** failure class (a verbatim prompt hand-copied with a drifted byte gets denied). D-C is the opposite failure class: by-ref is *fragile to context loss* — it resolves ONLY inside the PreToolUse guard while the owning run marker is live, so any condition that hides/breaks the marker (a clobber, a session-id mismatch, a stale/consumed nonce) degrades the by-ref token to a bare unresolvable string. The two failure classes pull in opposite directions, so which form to PREFER is a genuine design tradeoff an operator should own — not something to flip silently in a hardening cycle.

**Options:**
- **Keep `dispatch_prompt_ref` PREFERRED (Recommended)** — Leave the contract as-is. Rationale: the by-ref token's only failure modes (unresolvable nonce, no live marker) are now HARD-DENIED at the guard with an actionable corrective, so the silent-improvisation hole is closed regardless of which form is preferred. By-ref still buys the transcription-slip immunity it was added for, and D-C's trigger condition (a clobbered marker) is itself independently fixed by D-B (`refuse_run_start_clobber`). Cost: by-ref remains the recommended form, so a future context-loss bug would surface as a deny (noisy but safe) rather than transparently working. Low risk, fully reversible (it is prose).
- **Flip to verbatim `dispatch_prompt` PREFERRED for Agent dispatches** — Change `lazy-batch` + `lazy-bug-batch` (+ `lazy-batch-cloud`) prose so the orchestrator dispatches the verbatim `dispatch_prompt` text and uses `dispatch_prompt_ref` only as a fallback / never. Rationale: a verbatim prompt is self-contained and portable — it cannot degrade to a meaningless token under marker loss. Cost: re-opens the transcription-slip class the by-ref preference was specifically introduced to close (the 2026-06-14 incident's 2 guard denials were transcription drift on a verbatim meta-dispatch); the F2c transcription-slip detector + F2b hash-fold remain as the backstop, but the preference would now lean on a weaker guarantee. This is a reversal of a prior locked design choice and touches three coupled SKILL files.
- **Make `@@lazy-ref` resolvable in more contexts** — Extend resolution so a by-ref token survives marker loss (e.g. resolve from the registry by nonce even without a live marker, gated by TTL only). Rejected as the recommended path: it would weaken the run-start gate (an entry must be dispatchable only within the owning run), which is load-bearing for the validate-deny model — exactly the kind of gate-softening the hardening prohibitions forbid. Listed for completeness.

**Recommendation:** Keep `dispatch_prompt_ref` PREFERRED — the mechanical guard deny (Round 19) already closes the silent-improvisation hole, D-B independently removes the clobber that triggered D-C, and the by-ref preference retains its transcription-slip immunity. Only flip to verbatim if the operator judges context-loss fragility a worse risk than transcription drift for the AlgoBooth fleet.

### 2. Partial-VALIDATED → `__mark_complete__` oscillation: route back to `mcp-test` when the PHASES verification matrix is incomplete, or change what mints VALIDATED.md?

*(harden Round 45 — 2026-06-29, from the AlgoBooth `algorithmic-fill-buffer` `/lazy-batch` run.)*

**Problem:** `VALIDATED.md` attests "the scenarios listed in `MCP_TEST_RESULTS.md` passed," but a SPEC/PHASES verification matrix can enumerate MORE runtime-verification assertions than the scenarios that were run. Observed loop: the Step-9 `/mcp-test` cycle found+fixed a real production bug (capture-ordering), so per D5 it wrote a PARTIAL `MCP_TEST_RESULTS.md` — `result: all-passing`, `pass_count: 4`, `total_count: 4` for the 2 scenarios it ran. `__write_validated_from_results__` correctly accepted it (its gate checks `result == all-passing` AND `pass_count == total_count`, both true for the subset) and minted `VALIDATED.md`. `lazy-state.py` then treats validation as DONE (VALIDATED.md present) and routes to `__mark_complete__` — but the completion-integrity mechanical third gate (`--apply-pseudo`) REFUSES because 13 of ~15 PHASES `Runtime Verification` rows were never exercised. `coherence-recovery` honestly ticked only the 2 evidenced rows and re-opened the phases to In-progress, yet the very next probe STILL routed to `__mark_complete__` (VALIDATED.md still present) → refuse → loop. `step_repeat_count` reached 3 (the oscillation tripwire fired); I broke the loop MANUALLY by dropping the marker and dispatching a comprehensive validation cycle (which exercised the remaining matrix → 31/31, then mark-complete passed). There is NO auto-route back to `mcp-test` to finish the matrix when `VALIDATED.md` exists but is matrix-incomplete.

**Options:**
- **Route to `mcp-test` when the matrix is incomplete (Recommended)** — Before routing to `__mark_complete__`, if phases are In-progress with unchecked `Runtime Verification` rows that the existing validation evidence does not cover, route to `mcp-test` (finish the matrix) instead. Pro: self-healing, no loop, no semantics change to VALIDATED.md. Con: needs a row↔scenario coverage check (which unchecked rows are NOT covered by the recorded `MCP_TEST_RESULTS.md` scenarios) — non-trivial to compute mechanically; the simplest conservative form is "any unchecked non-verification-exempt row + VALIDATED.md present → re-route to mcp-test," accepting that a genuinely-complete-but-unticked matrix would re-run mcp-test once.
- **Make `__write_validated_from_results__` require full-matrix coverage** — Refuse to mint `VALIDATED.md` unless the results cover every PHASES verification row, not just "the scenarios that ran passed." Pro: `VALIDATED.md` becomes a true matrix-complete attestation; routing stays as-is. Con: a `/mcp-test` cycle that legitimately runs a subset (e.g. after fixing a bug, per D5's partial-results discipline) can NEVER mint VALIDATED.md — it forces a single comprehensive run and changes the established partial-results contract.
- **Accept the operator-surfaced tripwire** — Leave it: the `step_repeat_count >= 3` oscillation tripwire fires, the orchestrator STOPs and runs a comprehensive validation cycle manually (as I did). Pro: no code change. Con: relies on manual intervention every time; the loop burns 2–3 cycles before the tripwire fires, and a less-careful orchestrator could mechanically re-dispatch `__mark_complete__` past the tripwire.

**Recommendation:** Route to `mcp-test` when the matrix is incomplete (option 1) — it is self-healing and preserves the partial-results contract. But the row↔scenario coverage check is the load-bearing detail (false-positives re-run mcp-test, false-negatives re-loop), so the operator should own the approach + the conservatism dial. This is a gate-semantics / routing fork, not a mechanical fix.

### 3. forward_cycles under-count in interleaved real+meta by-ref dispatch: reopen `byref-dispatch-undercounts-forward-cycles`, or accept the low-impact under-count?

*(harden Round 45 — 2026-06-29, from the same run.)*

**Problem:** During the `algorithmic-fill-buffer` run the marker's `forward_cycles` stalled at 2 across THREE consecutive by-ref `execute-plan` cycles (plan part-1 / part-2 / part-3 — the `cycle_header` read `fwd 2/10` each time) interleaved with meta dispatches (input-audit, apply-resolution, hardening). The bug `byref-dispatch-undercounts-forward-cycles` is ARCHIVED-FIXED (`docs/bugs/_archive/`) with a Phase-2 consume-watermark clamp, but this observation suggests a residual gap: `advance_meta_cycle` bumps `last_advance_consume_count` by +1 to ABSORB the meta dispatch's own forthcoming guard-ALLOW consume (`lazy_core.py` ~11954), and when a real `execute-plan` by-ref dispatch's consume then lands, the strict-greater gate (`current_consume <= prior_consume → no advance`) appears to mask the forward advance — i.e. the meta +1 over-absorbs into the next forward cycle. Impact is LOW: an under-counted `forward_cycles` means the `forward_cycles >= max_cycles` cap (Step 1c) trips late or never, so a run goes slightly longer than the nominal budget; the attended budget-and-queue guard + operator oversight are the real backstop. But `forward_cycles` IS the budget signal, and an unbounded under-count silently defeats `max-cycles`.

**Options:**
- **Reopen + investigate before any fix (Recommended)** — Reopen `byref-dispatch-undercounts-forward-cycles` with this evidence (3 consecutive masked forward advances in an interleaved real+meta by-ref run) and reproduce the meta-absorb-then-forward path with a fixture BEFORE patching. Rationale: counter accounting has a regression history — a prior fix (ISSUE 5) over-corrected into premature INFLATION (a false `max-cycles` halt at 11/25 mid-run), so the inverse failure (this under-count) must not be patched blind. Investigate-first, then a tested fix.
- **Accept as low-impact known behavior** — Document the interleaved-run under-count as known; the `max-cycles` cap is a soft cost backstop, not a hard correctness gate, and attended runs have operator oversight + the budget-and-queue guard. No code change. (Unattended/cron runs are the risk case — there `max-cycles` is the only stop, so under-count there is more serious.)
- **Add an independent forward-advance cross-check** — Advance `forward_cycles` when a real-skill probe observes HEAD advanced + a new commit since the last advance, independent of the consume oracle. Rejected as the recommended path: it reintroduces exactly the multi-signal accounting that caused the ISSUE-5 inflation, and risks double-counting.

**Recommendation:** Reopen + investigate (option 1) — but gated on the operator judging budget-signal accuracy worth the regression risk; otherwise accept (option 2), especially noting the unattended-run exposure. I deliberately did NOT attempt an autonomous fix: the archived bug's inflation-regression history makes a blind counter patch higher-risk than the low-impact under-count it would address.

### 4. Dispatch-guard contract for WORKSTATION sub-subagent dispatches: how should `lazy_guard.py` distinguish a cycle worker's authorized test-agent/impl-agent split from an orchestrator improvising an unregistered cycle prompt?

*(harden Round 9 — 2026-07-09, from the AlgoBooth `key-detection-host-port` `/lazy-batch` run, session `e3ee238d`, Step 7a execute-plan, `pending_hardening=1`.)*

**Problem:** The `workstation-recursive-subagent-dispatch` feature (commit `5ff570b`, 2026-07-09) lifted the workstation cycle-subagent inline-override ban: a dispatched skill's own sub-subagent orchestration model is authoritative again, so a workstation `/execute-plan` cycle worker now FOLLOWS the structural test-agent → impl-agent split (`cycle-base-prompt.md` `@section workstation-dispatch`, lines 183–205). That feature changed ONLY prose + one test file — its commit touched `cycle-base-prompt.md`, the `lazy-batch` family SKILLs, and `test_lazy_core.py`; it did **not** touch `lazy_guard.py` or `lazy-dispatch-guard.sh`. The SPEC's guardrails name only "the containment hook" as the mechanical backstop (SPEC D3(a); prompt line 198) — the same-day `adhoc-containment-denies-mandated-explore-fanout` fix removed the *containment* hook's blanket recursive-dispatch deny. But the **dispatch guard is a separate hook**: under a live per-repo run marker it denies EVERY `Agent` prompt that is not a registered emission or a resolvable `@@lazy-ref` (`lazy_guard.py:839` `_deny_default`, the "no matching entry" branch). A cycle worker's test-agent prompt is composed by the worker and is not — and cannot be — a script-emitted registry entry (the state script has no knowledge of `/execute-plan`'s internal batch structure). So the very first workstation cycle to exercise the newly-restored split had its test-writer sub-subagent DENIED.

**Forensic evidence** (per-repo keyed state dir `~/.claude/state/37850b6e…/`, the AlgoBooth run):
- Registry entry 1 (`nonce 6f9b4993…`, `class: cycle`, `consumed: true`) IS the script-emitted Step-7a `/execute-plan` cycle prompt — legitimately dispatched by-reference (ledger `dispatch_by_reference: true, resolved_sha12 749fadf668aa, acked: true`). That prompt carries the `WORKSTATION DISPATCH — LOAD-BEARING` policy verbatim ("You MAY use the `Agent` tool … FOLLOW /execute-plan's Sonnet test-agent + impl-agent split … including its structural test-first agent separation").
- A SECOND, separate `Agent` call — prompt head `"You are a TEST-WRITING agent (TDD) … You write FAILING tests plus the minimal module scaffold needed for them to COMPILE and fail at ru…"`, exactly `/execute-plan`'s test-agent role — was DENIED and ledgered (`denied_sha12: 3d662cb4514c`, `reason_head` = the canonical corrective recipe). `3d662cb4514c` matches no registry `prompt_sha256`.
- The deny fired because the dispatcher's session_id matched the marker's bound session (`e3ee238d`): a sub-subagent shares the parent session, so the guard's session-mismatch fast-path allow (`read_run_marker` returns None on a non-owner session) does NOT distinguish a cycle worker from the orchestrator. The deny withheld the forward route (`pending_hardening=1`) and routed THIS hardening dispatch.

The instance is NOT hard-blocked — the worker's documented fallback ("When you judge a small mechanical batch cheaper inline, keep the same discipline manually: failing tests first") lets it proceed inline. But that silently defeats the feature's core deliverable: the STRUCTURAL agent separation the lift was built to restore is nullified by the guard on every workstation `/execute-plan`, `/retro-feature`, and Explore-fan-out cycle. No `BLOCKED.md` (the run proceeds degraded).

**Why this is a fork and not a mechanical fix:** the fix is a gate-semantics change to a security-critical integrity guard whose entire purpose is to deny unregistered `Agent` prompts under a live marker. To allow a cycle worker's sub-subagent dispatch while STILL denying an orchestrator improvising an off-script cycle prompt, the guard needs a distinguishing signal — and choosing the wrong one re-opens the exact hole the guard closes (Prohibition #2: never weaken a gate). Session_id is not a discriminator (forensically established above), so no obviously-safe mechanical signal exists. Operator-ownable.

**Options:**
- **Active-cycle-marker exemption, scoped to sub-subagent-model skills (Recommended)** — Under a live run marker, when a cycle marker is active whose `sub_skill` names a skill with a defined sub-subagent model (`execute-plan`, `retro-feature`, spec Explore fan-outs) AND the dispatched prompt is not itself a lifecycle/pipeline op (the containment hook still polices operations), the guard ALLOWS the unregistered prompt as a sub-subagent dispatch. Pro: narrow; keys off the existing cycle-marker `sub_skill` the harness already writes; the containment hook remains the operations backstop; restores the feature's structural guarantee. **Load-bearing detail the operator owns:** whether "cycle marker active" is a safe discriminator given the orchestrator writes the cycle marker BEFORE its own by-reference worker dispatch — is there a window where the orchestrator itself could improvise an unregistered dispatch under an active cycle marker, and if so how is it fenced (e.g. only after the worker's by-reference dispatch is consumed)?
- **Positive worker-set signal (env var / dispatch-depth marker)** — Require the cycle worker to stamp a signal the guard reads (an env var propagated into every sub-subagent `Agent` call, or a depth/parent-tool_use_id field). Pro: explicit, cannot be spoofed by an orchestrator that isn't inside a worker. Con: requires plumbing a signal through the `Agent` dispatch path the harness may not fully control; a worker that forgets to stamp it re-denies.
- **Register sub-subagent prompts via a new emit path** — Give the cycle worker a `--emit-sub-dispatch` analog so each sub-subagent prompt is registered before dispatch, preserving the guard's "everything registered" invariant. Con: heavyweight, and granting a non-orchestrator worker registry-write authority is itself a boundary change that partially re-opens what the marker/registry ownership model closes.
- **Scope the guard to the orchestrator session only** — Rejected: session_id does not distinguish orchestrator from sub-subagent (the denied dispatch shared the orchestrator session), so this degenerates into a blanket allow of all in-session dispatches, leaning entirely on the containment hook.

**Recommendation:** Active-cycle-marker exemption scoped to sub-subagent-model skills (option 1), with the operator owning the discriminator's safety proof (the cycle-marker-window fencing). This is a gate-semantics fork on the integrity guard; the correct fix restores a just-shipped feature but must not re-open the unregistered-dispatch hole, so it is surfaced here rather than baked silently. Cross-reference: origin is `workstation-recursive-subagent-dispatch` (5ff570b) — its rollout addressed the containment hook but overlooked the dispatch guard; the guard is owned by `turn-routing-enforcement`.

**RESOLVED (2026-07-10, operator — Jacob, interactive session):** Option 1 as amended by Round 11, with the consumed fence as the window discriminator. The blessed predicate — the guard ALLOWS an unregistered `Agent` prompt iff ALL of: (a) the run marker's `cloud` flag is falsy (workstation only; cloud keeps the unconditional deny); (b) the run marker is BOUND; (c) an active cycle marker's `subagent_model` field is True — a GENERAL skill-declared capability (`subagent-model: true` in SKILL.md frontmatter, copied onto the cycle marker at `--cycle-begin` by `skill_declares_subagent_model`), never a hardcoded skill list; (d) **consumed fence**: the cycle marker's own registered emission is already consumed (`emission_consumed_by_nonce`). The fence is the safety proof for the option-1 open question: `--cycle-begin` writes the marker BEFORE the worker dispatch, but consumption happens only on the guard-ALLOWed worker dispatch and session tool calls are serial, so once (marker active AND emission consumed) holds, an unregistered prompt can only originate inside the in-flight worker. Every exempted allow is audited to the deny ledger (`worker_subdispatch: true`, pre-acked — no hardening debt). The secondary FIFO same-signature dedup was explicitly DECLINED (the deny class is eliminated at the source; the one-debt-per-round cadence is a prior locked decision). Implemented in `lazy_guard.py` (guard() branch 2b), `lazy_core.py` (`skill_declares_subagent_model`, `emission_consumed_by_nonce`, `append_worker_subdispatch_event`, `write_cycle_marker` stamping), and ten SKILL.md frontmatter flags; fix commit is the commit introducing this paragraph. See `docs/bugs/dispatch-guard-denies-workstation-subsubagent-split/SPEC.md` (Resolution section) for the full trace.

**Corroborating evidence (harden Round 11 — 2026-07-10, AlgoBooth `inspector-effect-chain-editor` `/lazy-batch` run, session `e3ee238d`, `pending_hardening=2`):** the SAME `_deny_default` wall was hit a THIRD time, but on a DIFFERENT skill and a DIFFERENT pipeline stage than Rounds 9/10 — the denied prompt was a **`/spec-phases`** sub-subagent (Step 5 "Launch Subagent to Write Phases File", red-flag/phase authoring — `~/.claude/skills/spec-phases/SKILL.md:254-267`), fired at the **planning** stage (probe `step=Step 3.5: needs-input`), not the Step-7a `/execute-plan` test-agent split of Rounds 9/10. This BROADENS the affected class and carries one decision-relevant consequence for option 1: **its scope must NOT be a hardcoded skill list.** As written, option 1 enumerates only "`execute-plan`, `retro-feature`, spec Explore fan-outs" — that list omits `/spec-phases` (and its callers/kin `/plan-feature`, `/spec-phases-batch`, `/implement-phase*`), so an implementation that keys off the literal list would STILL deny this exact prompt. The discriminator the operator picks must be a GENERAL predicate — "the active cycle marker's `sub_skill` declares a sub-subagent model" (a skill-declared capability flag), not an allow-list of skill names — or every new sub-subagent-model skill re-opens this same gap. The blast radius is therefore confirmed **queue-wide and stage-wide** (any feature reaching either planning `/spec-phases` OR implementation `/execute-plan` under a live marker), not run-local as Round 9 first characterized. This raises the priority of resolving this decision: three hardening rounds across two features and two pipeline stages have now been spent on the one open fork.

### 5. Completion-gate treatment of un-migrated + host-blocked verification rows

**Problem:** At `__mark_complete__`, the mechanical completion-coherence gate REFUSES on ANY unchecked box in a non-Superseded phase — the deliberate "verification carve-out does not apply at completion time" strictness (`_phase_completion_plan`, `lazy_core.py:2740,2786`). Canonically `<!-- verification-only -->`-marked rows are auto-ticked first (`autotick_verification_rows`), but that recognizer honors ONLY the canonical marker, while the routing-stage `remaining_unchecked_are_verification_only` ALSO honors the legacy `_VERIFICATION_SECTION_RE` subsection shim. So an un-migrated verification row (under a "Runtime Verification" header, no canonical marker) is TOLERATED at routing but BLOCKS at completion — observed on managed-llm-credits (5 of 7 blocking rows). Worse, migrating such a row to the canonical marker makes autotick TICK it, which ASSERTS validation ran — a FALSE-GREEN for a row that genuinely could not run on THIS host (Phase 1 JWT-shape live capture: no Supabase config; Phase 4 reachability smoke: no running credits-proxy). The pipeline models deferral only at the FEATURE level (DEFERRED_REQUIRES_DEVICE / DEFERRED_REQUIRES_HOST — both BLOCK the whole feature); there is NO per-row deferral, so a feature blocked ONLY on host-unavailable backend verification is stuck all-or-nothing. The Round-22 mechanical fix (commit 62fdba2) made the refusal ACTIONABLE (splits shim vs genuine blocking rows) but deliberately did NOT change the gate — this resolution is a gate-semantics fork. Bundles with decision #2 (both govern partial-coverage completion).

**Options:**
- **Per-row host-capability deferral marker** — Add a `<!-- requires-host: <cap> -->` row marker the completion gate treats as legitimately-deferred (NOT ticked, NOT blocking), folded into a DEFERRED_REQUIRES_HOST receipt and re-opened on a capability-bearing host — the row-level analog of the existing feature-level host-capability deferral. Lets a feature complete on validated scope while honestly tracking host-blocked rows; no false-green. Con: new marker + gate branch + receipt-folding; interacts with the cardinality lock.
- **Converge the completion recognizer with routing** — Make the completion gate tolerate legacy-shim verification rows unchecked (as routing already does) instead of requiring them ticked. Con: WEAKENS the intentional completion strictness (prohibition #2) and still tolerates host-blocked rows on VALIDATED.md's broad strength without per-row evidence (the same laxness decision #2 questions).
- **Require every verification row to carry a per-row disposition before completion** — No row completes unchecked; each must be scenario-covered (ticked), a declared exemption, or explicitly host-deferred. Strictest/most honest; largest blast radius (many existing features have un-dispositioned verification rows) and likely a migration.

**Recommendation:** The per-row host-capability deferral marker — it directly resolves the observed managed-llm-credits block (backend rows deferred, feature completes on validated scope) without weakening the gate or false-greening, and mirrors an existing feature-level pattern.

### 6. Corrective-coverage dispatch for newly-discovered coverage at completion

**Problem:** When Gate 1 / Gate 2 at Step 10 reveal a genuinely-untested but MCP-testable-HERE behavior needing a NEW scenario authored + run (managed-llm-credits Purchase-CTA `ui_action` + auto-refill toggle-persistence), there is NO legitimate dispatch path. The `coherence-recovery` dispatch CORRECTLY refuses implementation work (its contract is PHASES reconciliation, not scenario authoring); a hand-composed mcp-test/implementation prompt is DENIED by the validate-deny guard (no registered emission); and the state machine will not re-route Step 10 → mcp-test while VALIDATED.md + MCP_TEST_RESULTS.md already exist. So authoring newly-discovered coverage at completion is stranded — the operator had to choose between deferring or a manual out-of-band cycle. Resolve together with decisions #2 and #5.

**Options:**
- **New `--emit-dispatch corrective-coverage` class** — A registered dispatch whose contract is: author the missing `mcp-tests` scenario(s), run them, reconcile PHASES / MCP_TEST_RESULTS, re-mint VALIDATED via the proper gate. Guard-allowed like every other emit class; parallels `coherence-recovery` but sanctioned for implementation-of-coverage. Con: a new dispatch class + template to maintain.
- **Step-10 → mcp-test re-route on uncovered non-exempt verification rows** — Have the state machine route Step 10 BACK to `mcp-test` when PHASES has an unchecked, non-exempt, non-host-deferred verification row (instead of `__mark_complete__`). Reuses the shipped mcp-test dispatch; no new class. Con: needs a stale/insufficient-coverage predicate that does not re-trigger on already-exempt rows (interacts with decision #2 and the observation_gap path), and must terminate (not loop).
- **Leave it manual** — Rejected: a stranded coverage gap forces an out-of-band manual cycle every time, defeating the pipeline's dispatch-for-discovered-work contract.

**Recommendation:** The Step-10 → mcp-test re-route (option 2) IF a clean "uncovered non-exempt verification row remains" predicate can be defined (it reuses the shipped mcp-test dispatch); otherwise the dedicated `corrective-coverage` emit class.

### 7. GATE_VERDICT.md has no in-pipeline authoring route + a provisional gate is live-blocking the ship seam

*(harden Round 36 — 2026-07-13, from the claude-config `state-cli-contract-registry` `/lazy-batch` run.)*

Round 36 mechanically fixed the **run-blocking** half of this dispatch — the completion-gate scope
derivation was folding a concurrent harden workstream's commits into the active feature's scope
(`docs/bugs/gate-scope-folds-concurrent-harden-commits/`), so a feature whose OWN commits touch
zero control surfaces is no longer dragged into `gate_verdict_ok` scope. The two forks below are the
**latent** half the mechanical fix deliberately does NOT close — they bite a feature whose OWN
commits genuinely touch a control surface, and they are operator-owned, not mechanical defects.

**Fork 7a — No route authors `GATE_VERDICT.md` in-pipeline.** `gate_verdict_ok` (anti-overfit-design-gate
D3 ship seam, `lazy_core.py`) refuses `__mark_complete__` for a genuinely-in-scope control-surface
feature lacking a `GATE_VERDICT.md`, but there is no automated path to author one under a marked run:
the emit-dispatch classes (`apply-resolution`, `input-audit`, `investigation`, `recovery`,
`coherence-recovery`, `needs-*`, `hardening`) NONE author it; `coherence-recovery` is hard-scoped to
PHASES.md reconciliation; the orchestrator's Write/Edit is sentinel-scoped (HARD CONSTRAINT 1) and
`GATE_VERDICT.md` is not a sentinel; and the dispatch guard denies a hand-composed unregistered
`Agent`. Net: a `gate_verdict_ok` refusal for a legitimately-in-scope feature has no in-pipeline
recovery.

- **Option A — new `gate-verdict` emit-dispatch class** authoring `GATE_VERDICT.md` (running the
  adversarial `_components/harness-change-gate.md` questions), analogous to `coherence-recovery` but
  scoped to the verdict file. Un-blocks in-pipeline.
- **Option B — interactive-only authoring**: the batch orchestrator halts a genuinely-in-scope
  control-surface feature to `NEEDS_INPUT.md` for operator authoring. Preserves the human-judgment
  intent; blocks autonomous completion of control-surface features.
- **Option C — planning-time only**: move the verdict requirement to the `/spec` planning seam and
  REMOVE the completion-time hard block (a present-and-clean `GATE_VERDICT.md` becomes an
  authoring-time artifact, not a ship-seam gate).

**Fork 7b — A structurally-provisional gate is live-blocking at the ship seam.** `anti-overfit-design-gate`
is STRUCTURALLY PROVISIONAL (`docs/features/anti-overfit-design-gate/NEEDS_INPUT_PROVISIONAL.md`,
D1/D3/D4/D7 auto-accepted-not-ratified, `divergence: structural`), yet its D3 ship seam
(`gate_verdict_ok`) hard-blocks `__mark_complete__` across every control-surface feature. Should a
provisional, unratified gate hard-block the ship seam before ratification — or degrade to
advisory/planning-time (Fork-7a option C) until the operator ratifies (or redirects) the provisional
sentinel? Resolving 7b toward "advisory until ratified" would MOOT 7a's in-pipeline authoring need.

**Recommendation (non-binding):** Fork 7a option A (a `gate-verdict` emit class) if the gate stays a
completion-time block; OR Fork 7b "advisory until ratified" + Fork 7a option C if the operator
prefers to defer hard enforcement until anti-overfit-design-gate is ratified. Either path removes the
no-route dead-end for a genuinely-in-scope feature without weakening the gate's intent. This is a
gate-semantics / authority fork, surfaced rather than baked silently (Round 36 did NOT self-dispatch
a second hardening stage — depth-1 cap; the run-blocking half is already fixed mechanically).

### 8. Consumed-fence robustness under a re-emit after `--cycle-begin`

*(harden Round 46 — 2026-07-16, from the AlgoBooth `d8-signal-flow-viz` `/lazy-batch` run,
session `40e929ed`, part-8 `/execute-plan` cycle; background observed-friction harden.)*

**Problem:** Decision 4 (RESOLVED 2026-07-10, implemented hardening Round 16 `e3f5702`) blessed
the **consumed fence** as the safety proof for the workstation sub-subagent exemption: the guard
ALLOWs an unregistered worker-composed prompt only once `emission_consumed_by_nonce(cycle.nonce)`
holds (the cycle's own registered dispatch is consumed ⇒ the worker is in flight ⇒ an unregistered
prompt can only come from inside it). Round 16 wired this by having `--cycle-begin`
(`resolve_cycle_worker_nonce`) bind the fence nonce to "the newest UNCONSUMED `class==cycle`
emission then present," on the documented assumption that "`--emit-prompt` registers the cycle
emission IMMEDIATELY before `--cycle-begin`."

That assumption is VIOLATED by `/lazy-batch`'s own freshness rule (SKILL.md §1d, ~690/742:
"Continuation cycles re-emit"; a by-reference dispatch is dispatchable only on the turn its
emission was registered, else RE-PROBE `--emit-prompt` in-turn and dispatch THAT fresh ref). When
a turn boundary/staleness intervenes between `--cycle-begin` and the actual worker dispatch, the
orchestrator RE-EMITS — and that re-emission is registered AFTER `--cycle-begin`. The fence was
bound at `--cycle-begin` to a stale/fresh nonce; the worker consumes the RE-EMITTED nonce; the two
never match; `emission_consumed_by_nonce(cycle.nonce)` reads False for the whole cycle; the
exemption never fires; every worker-composed test-agent/impl-agent dispatch is denied as false
hardening debt.

**Forensic evidence** (per-repo keyed state dir `~/.claude/state/37850b6e…/`; ledger + registry +
telemetry, quoted in `docs/bugs/consumed-fence-dies-on-reemit-after-cycle-begin/SPEC.md`):
- The exemption is LIVE and works: **108** `worker_subdispatch: true` (pre-acked) allows across the
  run, all `execute-plan`, the last for `d8` at `ts 1784197418` inside the immediately-preceding
  part-7 cycle.
- Part-8 anomaly: ONE denied hand-composed test-agent (`denied_sha12 8ecb32c73a97`, `ts 1784198590`,
  `prompt_head` "You are a TEST-AGENT for one work unit … (d8-signal-flow-viz, Phase 7, WU-2)…"),
  the canonical corrective-recipe deny.
- It falls INSIDE a `sub_skill=execute-plan` cycle (telemetry `cycle-begin ts 1784197993`,
  `cycle-end ts 1784199546`) → condition 3 (`subagent_model True`) held; conditions 1–2
  (workstation, bound) held. Only condition 4 (the fence) failed.
- The smoking gun: the part-8 worker emission `nonce 5e508da3…` (`class cycle`, `consumed True`,
  `consumed_by toolu_01AKox…`) has **`emitted_at 1784198002` — 9 s AFTER `--cycle-begin`
  (1784197993)**, and the prior cycle emission `b4b15231` (`emitted_at 1784194061`) was already
  consumed. So at `--cycle-begin` there was NO unconsumed cycle emission to bind; `resolve_cycle_
  worker_nonce` fell to its "safe pre-fix degradation" branch and preserved the fresh hex, which is
  absent from the registry → `emission_consumed_by_nonce(fresh_hex)` = False all cycle.

This is the **2nd occurrence of the Round-16 shipped-exemption-mis-wiring class at the same symbol**
(`resolve_cycle_worker_nonce` / the consumed fence). Round 16 fixed the fresh-hex-with-emission-
already-present case; this is the re-emit-after-cycle-begin case. Round 16's regression test
`_arm_worker_in_flight` (`test_hooks.py`) hard-codes the emit-BEFORE-`write_cycle_marker` order,
masking this case exactly as the pre-Round-16 test masked the fresh-hex case.

**Why this is a fork and not a mechanical fix:** a **write-side-only** fix is impossible — at
`--cycle-begin` the worker's eventual re-emitted nonce does not exist yet, so no smarter binding at
that moment can point the fence at it. The robust fix must either RE-DERIVE the fence at guard time
or RE-BIND at re-emit/dispatch time — either modifies the **operator-blessed integrity-guard allow
computation** (`lazy_guard.py` §2b condition 4 / the consumed-fence security window that decision 4
explicitly reserved). Round 16 already made one unilateral mechanical change to this exact fence and
it proved incomplete; a second unilateral re-wire of a security fence, without operator sign-off, is
precisely what the hardening prohibitions (#2, never weaken/re-wire a gate to clear a denial) and the
Round 9–13 precedent ("touches the security fence → surface, don't bake") counsel against.

**Options:**
- **Re-derive the fence at guard time (Recommended)** — Replace condition 4's single-nonce check with:
  the NEWEST `class==cycle` registry emission is consumed AND its `emitted_at >= cycle.started_at`.
  Pro: robust to any re-emit / ordering; keys off data the guard already reads; preserves the exact
  pre-dispatch-window closure the operator blessed (before the worker dispatch, no cycle emission
  registered-since-cycle-begin is consumed → fence closed). Con: changes the guard's allow
  computation — the operator owns the soundness proof (does the "newest-cycle-emission-consumed-
  since-begin" predicate admit any window where the orchestrator itself, not the worker, consumes a
  re-emitted cycle emission before dispatching the worker? By construction the by-reference worker
  dispatch IS the consume, so the invariant appears preserved — but "appears" on a security fence is
  the operator's call). Requires a regression test that registers the consumed emission AFTER
  `write_cycle_marker`.
- **Re-bind the fence nonce at re-emit/dispatch time** — Have the re-emit path (or the guard's own
  by-reference consume of a `class==cycle` entry) update the active cycle marker's fence nonce to the
  emission actually consumed. Pro: keeps condition 4's single-nonce shape. Con: adds a marker write
  from the re-emit/guard path (a new writer of the cycle marker), and must fence against the
  orchestrator re-binding to its own improvised emission.
- **Enforce/keep emit-before-cycle-begin and make a violation self-announcing** — Keep Round 16's
  binding but detect at `--cycle-begin` (for a `subagent_model` cycle) that no bindable unconsumed
  cycle emission exists, and emit a loud diagnostic/breadcrumb ("exemption fence will be DEAD this
  cycle") so the silent 108:1 flake becomes observable. Pro: no gate-semantics change; pure
  observability. Con: does NOT fix the deny — the re-emit is a legitimate, freshness-mandated move,
  so a warning that fires on every such cycle is noisy and the sub-subagent still gets denied.

**Recommendation:** Re-derive the fence at guard time (option 1) — it is the only option that both
FIXES the deny AND stays faithful to the operator-blessed pre-dispatch-window closure, and it removes
the fragile snapshot-nonce coupling at the root (so a 3rd variant cannot recur). The operator owns the
soundness proof of the `emitted_at >= cycle.started_at` predicate on the integrity guard. Cross-
reference: `docs/bugs/consumed-fence-dies-on-reemit-after-cycle-begin/SPEC.md` (Concluded); origin
is decision 4 / hardening Round 16 (`e3f5702`), owned by `turn-routing-enforcement`.

### 9. Operator per-feature host-defer not machine-enforced over a VALIDATED feature

*(harden Round 47 — 2026-07-16, from the AlgoBooth `managed-llm-credits` `/lazy-batch` run;
blocking observed-friction harden. Bundles with OPEN decisions #5 and #6 — all three name the
SAME four rows.)*

**Problem:** At the completion-integrity `NEEDS_INPUT.md` halt (the terminal hardening Round 44
added), the operator answered "defer the whole feature to a capability-bearing host" for
`managed-llm-credits` (4 unchecked Runtime-Verification rows: Phase 1 live-OAuth JWT-shape live
capture, Phase 4 credits-proxy reachability smoke, Phase 7 Purchase CTA `ui_action`, Phase 8
auto-refill toggle persistence). The apply-resolution subagent authored
`docs/features/managed-llm-credits/DEFERRED_REQUIRES_HOST.md`
(`missing_capabilities: [credits-proxy-host, live-oauth-host]`, `deferred_by: operator`). But that
sentinel drives NO state-machine skip, for TWO independent reasons:

1. **Unregistered capability ids.** `credits-proxy-host` and `live-oauth-host` are absent from the
   closed `lazy_core.hostcaps._HOST_CAPABILITY_REGISTRY` (`hostcaps.py:74-110`). Declaring them in a
   `requires_host:` set trips the Phase-4 unknown-capability fail-fast
   (`lazy-state.py:2045-2078` → `blocker_kind: unknown-host-capability` BLOCKED.md) — a HARD blocked
   terminal, the opposite of a clean defer. Unlike the registered hardware/OS capabilities, these are
   SERVICE-REACHABILITY / configuration capabilities with no deterministic workstation self-probe.
2. **The host-defer branch is `not VALIDATED.md`-gated.** `lazy-state.py:2087-2091` runs the
   capability-miss defer only `if not host_validated and _phases_effectively_complete(...)`. This
   feature carries a `VALIDATED.md` (`result: validated-modulo-observation-gaps` — the intended
   output of the observation-gap path: MCP-driveable scope passed, some rows host-unobservable), so
   the branch is skipped. With `VALIDATED.md` present the router goes straight to Step 10
   `__mark_complete__` (the Step 9-pre re-open guard at `lazy-state.py:3520` checks only
   `DEFERRED_REQUIRES_DEVICE.md`, never the host sentinel).

So the deferral is documentation-only: the mechanical `--apply-pseudo` completion gate
(`verify_ledger`, which never consults `DEFERRED_REQUIRES_HOST.md`) re-refuses on the 4 unchecked
rows, the Round-44 `coherence-recovery` terminal reconciles 0 rows (they never ran on THIS host) and
re-writes `NEEDS_INPUT.md` — re-asking a decision the operator already made. `DEFERRED_REQUIRES_HOST.md`
is additionally a WRITE-ONLY sentinel on the routing side: the Step-2 branch re-derives
`missing = required_host - host.present` each probe and never READS a pre-existing operator-authored
sentinel as a skip driver.

**Why this is a fork and not a mechanical fix:** the feature pipeline DELIBERATELY has NO
operator-defer branch (`lazy-state.py:353-356`: "the feature side … has NO operator-DEFERRED.md
branch (bug-pipeline-only — JUSTIFIED divergence)"; mirror note `bug-state.py:980-988`). Honoring the
operator's "defer whole feature" answer therefore requires ADDING an operator-defer authority to the
feature side AND either registering un-probeable service capabilities or teaching the completion gate
to treat host-deferred rows as legitimately-deferred. Every path changes gate/authority semantics —
and letting a sentinel waive the completion gate's unchecked-row refusal is exactly the gate-weakening
Prohibition #2 reserves for the operator. Round 44 gave the loop a terminal; this decision gives the
terminal's RESOLUTION a machine-honored home. This is the 3rd distinct round on the managed-llm-credits
honest-stuck class (Round 22 #5/#6, Round 44 terminal, Round 47 resolution) — over-fit signal 2 is met.

**Options:**
- **Register the service capabilities (constant-False, no self-probe) + honor an operator
  `DEFERRED_REQUIRES_HOST.md` over a validated-modulo feature (Recommended)** — Add `credits-proxy-host`
  and `live-oauth-host` to the registry with a constant-False placeholder (mirroring `link-multi-peer`
  — no workstation self-probe, so they re-open only under an explicit operator/env signal), AND relax
  the completion path so an operator-authored `DEFERRED_REQUIRES_HOST.md` (`deferred_by: operator`)
  routes the feature to the host-capability-saturated (Deferred) terminal instead of `__mark_complete__`,
  even when a `validated-modulo-observation-gaps` VALIDATED.md is present. Pro: honors the operator's
  answer with a clean Deferred terminal; no false-green (rows are deferred, not ticked); re-opens on a
  capability host. **Load-bearing detail the operator owns:** the completion path (Step 9-pre and/or
  `verify_ledger`) must recognize the host sentinel as a legitimate deferral without opening a
  side-door that lets the PIPELINE (not the operator) waive the gate — the `deferred_by: operator`
  provenance is the discriminator, and its trust model is the operator's call.
- **General per-feature host-defer of specific verification ROWS** — The whole-feature analog of
  decision #5's per-row `<!-- requires-host: <cap> -->` marker: the operator's deferral scopes to the
  named rows, the feature completes-modulo-deferral on the validated scope, host-deferred rows are
  tracked (not ticked, not blocking) and re-open on a capability host. Pro: finishes the feature on
  validated scope rather than parking it whole; unifies with #5. Con: larger surface (per-row marker +
  gate branch + receipt folding); the operator must confirm "complete-modulo-deferral" is the desired
  disposition vs. a whole-feature Deferred park.
- **Add an operator-DEFERRED authority branch to the FEATURE pipeline** — Give the feature side the
  operator-defer affordance `lazy-state.py:353-356` currently reserves to the bug pipeline, reading an
  operator-authored `DEFERRED_REQUIRES_HOST.md` as a skip driver. Pro: closest to what the
  apply-resolution subagent already attempted. Con: reverses a JUSTIFIED parity divergence — the
  operator owns whether the feature side SHOULD gain this authority, and how it fences against the
  pipeline authoring its own defer.

**Recommendation:** Option 1 (register service capabilities + honor the operator sentinel over a
validated-modulo feature) — it directly ends the re-ask loop with a clean Deferred terminal and no
false-green, keys off the existing `deferred_by: operator` provenance, and mirrors the `link-multi-peer`
no-self-probe precedent. Resolve jointly with #5/#6 (all four managed-llm-credits rows): #6 authors the
2 genuinely-MCP-testable-HERE rows (Phase 7 CTA, Phase 8 toggle), leaving the 2 truly host-blocked rows
(Phase 1 live-OAuth, Phase 4 credits-proxy) for this decision's operator host-defer. Cross-reference:
`docs/bugs/feature-operator-host-defer-not-honored-over-validated/SPEC.md` (Concluded).

### 10. Turn-end verify-ledger mis-scoped for PLANNING cycles: scope the substep, or add a "planning-ok" verdict?

*(harden Round 51 — 2026-07-16, observed-friction from the AlgoBooth `/lazy-batch` bug pipeline, item `adhoc-hydra-load-code-mcp-tool`, a `/plan-bug` cycle. Bug: `docs/bugs/verify-ledger-planning-scope-and-file-arg/` (Concluded). The sibling ARG-ambiguity half of that bug was fixed mechanically this round — `harden(script)` `3d2311ce`; only this SCOPE half is escalated.)*

**Problem:** `--verify-ledger` is the COMPLETION gate — it checks `plan_complete` (a plan is `status: Complete`) and `deliverables_done` (zero unchecked deliverable/WU rows). The cycle-subagent turn-end contract `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` injects the "TERMINAL VERIFY GATE" (item 3ii/iii: run `--verify-ledger`, then "RECONCILE ... RE-RUN the verifier until `ok` is true") via the two `@section turn-end` blocks (workstation line ~618, cloud line ~663), BOTH marked `skills=all`. A PLANNING cycle (`spec-phases`, `write-plan`, `plan-bug`, `plan-feature`, `spec`, `spec-bug`) authors a `Ready` plan with intentionally-unchecked deliverables, so `verify_ledger` STRUCTURALLY returns `ok:false`. The "reconcile until ok:true" instruction is then unsatisfiable without fabricating completion (flip `Ready`→`Complete`, tick unimplemented rows) — both forbidden by the `@section status-honesty` contract. This bites the CYCLE-SUBAGENT turn-end path specifically: the ORCHESTRATOR already scopes its OWN guardrail-D verify-ledger (`lazy-batch/SKILL.md` Step 1e.4a) to fire only "When the cycle that just returned was `/execute-plan` or `/mcp-test`" — so the two enforcement sites of the same gate DISAGREE, and the cycle-prompt site over-fires on planning cycles the orchestrator would never verify.

**Why not mechanical:** the turn-end contract's UNIVERSAL conditions — (a) no background job still running, (b) `git status --short` empty, (c) branch pushed, (d) owed result sentinel on disk — DO apply to planning cycles (a planning cycle must still commit+push its Ready plan and write its sentinel). The current prose makes verify-ledger's `ok:true` the MECHANISM that certifies those four. So this is not a "delete the section for planning skills" edit — it is a gate-semantics choice about what terminal guarantee planning cycles carry, and which mechanism certifies it. That is operator-owned.

**Options:**
- **Scope the verify-ledger substep to completion-capable skills (Recommended)** — Split each `@section turn-end` into a universal part (`skills=all`: the four conditions, self-asserted / lighter scripted check) and a completion part scoped to the completion-capable skills — `execute-plan`, `mcp-test`, `retro-feature` (feature) and the bug-pipeline analogs (`execute-plan`, `mcp-test`/mark-fixed) — mirroring the orchestrator's already-shipped guardrail-D scope. Pro: brings the two enforcement sites of the SAME gate into agreement with an ALREADY-decided scoping (not new policy); no verify_ledger code change; planning cycles stop hitting an unsatisfiable loop. Con: planning cycles lose the SCRIPTED `clean_tree`/`head_matches_origin` certification that verify-ledger currently provides (checks 1+2 DO apply to them) and fall back to self-asserting clean-tree/pushed — a small reduction in scripted rigor for planning cycles. The load-bearing detail is the completion-capable skill LIST (a planning skill wrongly included re-introduces the false-fail; a completion skill wrongly omitted skips real verification).
- **Add a "planning-ok" verdict mode to `verify_ledger`** — For a planning cycle, evaluate checks 1+2 (clean_tree, head_matches_origin — the universal push/commit conditions) but treat checks 3+4 (plan_complete, deliverables_done) as N/A → a `planning-ok` verdict (`ok:true`, `mode: planning`). Keeps a SINGLE scripted terminal gate for ALL skills, just with the completion checks relaxed when the cycle is planning. Pro: planning cycles KEEP scripted clean-tree/pushed certification; no cycle-prompt section split; one gate to reason about. Con: `verify_ledger` must learn the caller's cycle KIND (a new arg/flag threaded from the cycle prompt), enlarging the gate's contract and adding a "planning" verdict surface that retro/telemetry must understand; risk of a completion cycle mislabeled `planning` self-granting a pass (the new flag becomes security-relevant).
- **Accept the friction (status quo)** — Leave `skills=all`; rely on the planning subagent recognizing the gate is completion-only and returning without forcing ok:true. Pro: no change. Con: the injected prose literally says "RE-RUN the verifier until `ok` is true ... a return without it is a resultless return" — a compliant subagent is told to do the impossible or fabricate; this IS the observed friction, and it recurs every planning cycle.

**Recommendation:** Option 1 (scope the substep to completion-capable skills, mirroring guardrail-D) — it harmonizes an already-decided scoping across the two enforcement sites and needs no gate code change. The operator should own the completion-capable skill LIST (the load-bearing detail) and confirm whether the small loss of scripted clean-tree/pushed certification for planning cycles is acceptable, or whether Option 2's "planning-ok" verdict is preferred to retain it. This is a gate-semantics / cycle-prompt-contract fork, not a mechanical fix — surfaced here rather than baked silently.

### 11. forward_cycles OVER-counts on non-dispatch inject-hook turns: gate the advance on consume (reversing two 2026-07-16 decisions), or move the advance off banner-emission to dispatch time?

*(harden Round 55 — 2026-07-17, observed-friction from the AlgoBooth overnight `/lazy-batch 25 --park --park-provisional` run, item `adhoc-hydra-sidecar-dist-esm-no-frames`. Bug: `docs/bugs/lazy-run-marker-park-arm-and-forward-cycle-inflation/SPEC.md` (Concluded, DEFECT 1). The sibling park-arm half of that bug was fixed mechanically this round — `harden(skill-prose)`/`harden(script)`; only this forward-cycle-counting half is escalated. This is the OVER-count MIRROR of OPEN decision #3's UNDER-count — both name the `forward_cycles` counting oracle.)*

**Problem:** After ONE real dispatch (cycle 1, `/execute-plan hydra-overlay`) the run marker showed `forward_cycles=3`, with `per_feature_forward_cycles = {hydra-overlay: 2 (dispatched once), adhoc-hydra-sidecar-dist-esm-no-frames: 1 (never dispatched)}`. The increments line up 1:1 with `lazy-route-inject.sh` LAZY-ROUTE banner emissions (turns 2+4 routed hydra → hydra=2; turn 5 routed the bug → bug=1) — i.e. forward_cycles advanced at banner-EMISSION time on turns where NO dispatch occurred (background-agent-completion NOTIFICATION turns). On a long overnight run with many notification turns this balloons forward_cycles and FALSE-hits `max_cycles`, ending the run early — the opposite of intended.

**Mechanism (root cause located):** the inject hook (`lazy_inject.py::_run_probe`) runs the full probe `--repeat-count --probe --emit-prompt` on EVERY UserPromptSubmit turn while a marker is present. `--repeat-count` calls `lazy_core.advance_forward_cycle(state, consume_gate=True)` (`lazy-state.py` ~line 13538). `advance_forward_cycle` advances on `state_changed OR consume_rose`. On a notification turn the routed `(feature_id, current_step, sub_skill)` tuple CHANGES (a completed background dispatch flipped queue state), so `state_changed` is true with NO consume → a false forward advance. This is systematic: notification turns are exactly the turns where the route changes without a this-turn dispatch.

**Why this is a fork and not a mechanical fix:** the evidence's prescribed fix (gate the advance on consume; drop the bare state-change trigger on the `consume_gate=True` inject path) DIRECTLY conflicts with two deliberate, one-day-old prior decisions, each with a pinned test:
- `test_advance_forward_cycle_consume_gate_advances_multicycle_same_step` (`byref-forward-cycles-frozen-on-multicycle-same-step`, **2026-07-16**) asserts that on the `consume_gate=True` path the FIRST probe advances via the state-change trigger at census 0 / no consume (`test_markers.py` ~line 5724-5726).
- `test_advance_forward_cycle_verbatim_real_skill_theory_1b` (Theory-1b) asserts a real-skill state change advances even on a consume-MISSED (verbatim) dispatch.

The two named failure modes are SYMMETRIC catastrophes: DEFECT 1 (over-count → false EARLY halt) vs. byref-forward-cycles-frozen / Theory-1b (under-count → `max_cycles` never trips → UNBOUNDED overnight run). Neither the consume oracle (under-counts under ring-cap eviction / consume-missed verbatim dispatch) nor the state-change oracle (over-counts on notification turns) alone distinguishes "first probe of a genuine dispatch cycle" from "notification turn" — both present as `state_changed AND no consume`. Choosing consume-only REVERSES the 2026-07-16 decision and requires inverting/retargeting its pinned tests — precisely the "invert a deliberate prior decision to make a symptom pass" a hardening cycle must not do silently (Prohibition #2). Bundles with decision #3 (the under-count mirror; one root fix should resolve both).

**Options:**
- **Move the forward-advance OFF banner-emission to actual DISPATCH time (Recommended)** — Stop advancing forward_cycles in the inject-hook `--repeat-count` probe path entirely (make that path PEEK). Advance exactly once at the real dispatch bracket — at the guard-ALLOW consume of the cycle emission, or at `--cycle-begin` for the in-flight cycle — so the counter counts DISPATCHES, not banner emissions. Pro: kills BOTH the DEFECT-1 over-count (notification turns emit a banner but never dispatch → no advance) AND decision #3's under-count (every real dispatch advances exactly once, no consume-oracle non-monotonicity, no meta-absorb masking); the state-change and consume oracles are both retired as forward-advance triggers on the probe path. This is the "most general within reason" fix — it removes the fragile probe-time advance at its structural root rather than re-tuning which OR-trigger fires. Con: relocates WHERE the advance happens (a routing-contract change the operator owns) and needs the pinned-test suite retargeted (the multicycle-same-step + Theory-1b tests move from asserting probe-time advance to asserting dispatch-time advance); must preserve within-cycle idempotence and the `--apply-pseudo` forward-advancing-pseudo-skill path (which emits no consume — it would advance at its own apply bracket, as today).
- **Gate the probe-path advance on consume only (drop the state-change trigger when `consume_gate=True`)** — Minimal change: on the inject path require `consume_rose`, never bare `state_changed`. Pro: smallest diff; directly implements the evidence's fixture (N bare probes → 0 advance). Con: reverses the 2026-07-16 decision and re-opens Theory-1b / the census-non-monotonicity under-count that the state-change trigger was ADDED to fix — trading the early-halt catastrophe for the never-halt catastrophe unless the consume clamp is proven sufficient. Requires inverting two pinned tests.
- **Accept the over-count (status quo)** — Leave it; rely on the operator noticing an overnight run ended early and re-invoking. Con: on an UNATTENDED overnight `--park` run (the exact case observed) `max_cycles` is the only stop, and a false-early halt silently truncates the roadmap; the friction recurs every run with notification turns.

**Recommendation:** Option 1 (move the advance to dispatch time) — it is the only option that resolves BOTH the DEFECT-1 over-count AND the decision-#3 under-count at the shared root (the counter should count dispatches, and the reliable dispatch bracket — not the every-turn banner probe — is where to count them), without leaving a residual oracle to re-tune. The operator owns the routing-contract change (advance relocates off the probe path) and the pinned-test retargeting. This is a gate/counter-semantics fork, surfaced rather than baked silently. Cross-reference: `docs/bugs/lazy-run-marker-park-arm-and-forward-cycle-inflation/SPEC.md` (DEFECT 1, Concluded); origin is `byref-forward-cycles-frozen-on-multicycle-same-step` (2026-07-16) + Theory-1b, owned by `turn-routing-enforcement`; bundles with decision #3.

### 12. Operator recovery of a CRASHED run's orphaned markers is under-served: add a liveness/ownership teardown path, a first-class recovery op, chain-aware messages, and/or a crash terminal reason?

*(harden Round 58 — 2026-07-17, manual invocation. Firsthand friction: a `/lazy-batch` session died on a remote-control disconnect, leaving `lazy-run-marker.json` + `lazy-cycle-active.json` orphaned; an operator in a later session hit a cascade of misleading refusals tearing the corpse down. Bug: `docs/bugs/operator-recovery-of-crashed-run-orphaned-markers-underserved/` (Concluded).)*

**Problem:** The two containment guards decide subagent-vs-orchestrator using ONLY cycle-marker PRESENCE + two env signals (`LAZY_ORCHESTRATOR`, `LAZY_CYCLE_SUBAGENT`), and consult NEITHER ownership NOR liveness. `refuse_if_cycle_active` (`markers.py:2171`, guards `--run-end`/`--run-start`/`--apply-pseudo`/`--enqueue-adhoc`/`--emit-dispatch`) and `refuse_cycle_marker_mutation_if_subagent` (`markers.py:2233`, guards `--cycle-end`/`--cycle-begin`) both branch on `read_cycle_marker()` being present → refuse. So an operator in a FRESH session (no `LAZY_ORCHESTRATOR`, no dispatch in flight) cleaning up a DEAD run's markers is indistinguishable from a live contained subagent, and is refused as "a single cycle subagent." The signals to tell them apart already exist on disk — the cycle marker records `session_id`/`started_at`/`run_started_at` (`write_cycle_marker`, `markers.py:1486-1513`), the run marker records `session_id`/`started_at`, and the owning process's liveness is probeable — but no guard reads them. The dead run's `session_id` (61489c4f…) was plainly foreign to the operator's session and its task-watcher parent PIDs were all gone. The harness even HAS non-destructive ownership machinery it does not apply here (`marker_owner_status` → `absent|owned-by-me|foreign-stamped`, `markers.py:1022`; `read_run_marker` staleness path A age>24h + path B session-mismatch), but path A does not fire on a freshly-crashed run (<24h) and `read_cycle_marker` has NO staleness logic at all. Once containment is bypassed (`export LAZY_ORCHESTRATOR=1`), the `--run-end` handler (`lazy-state.py:12613`) layers three more gates the operator must satisfy one-by-one — pending-hardening (`--ack-unhardened`), efficacy-flush (`--efficacy-skip-authorized`), and the terminal-reason gate against `SANCTIONED_STOP_TERMINAL` (`markers.py:650`, which has NO crash/disconnect reason). The only working teardown was `LAZY_ORCHESTRATOR=1` + `--cycle-end`, then `--run-end --efficacy-skip-authorized --operator-authorized --terminal-reason <borrowed-sanctioned-reason>`. No single refusal pointed at this sequence.

**Why not mechanical:** every candidate grants NEW authority or changes gate semantics. (a) A liveness/ownership teardown path CHANGES the deny decision (a foreign+dead owner would now be allowed to tear down) and must not reintroduce the 2026-06-12 silent-disarm-by-delete a non-owner could trigger against a LIVE run — the exact hazard path B's non-destructive rule and `marker_owner_status` exist to prevent. (b) A first-class `--recover-stale-marker`/`--force-run-end` op is a NEW operator authority surface. Adding `crashed-run`/`remote-control-disconnect` to `SANCTIONED_STOP_TERMINAL` lets such a reason end a run WITHOUT `--operator-authorized` — a gate-semantics change (that set is the "authoritative list of reasons that allow an unattended or operator-authorized terminal stop"). Even (c) chain-aware refusal messages should point at whichever recovery UX the operator picks, so baking a message ahead of the decision risks enshrining the awkward current path. Operator-owned.

**Options:**
- **(a) Session-liveness/ownership teardown path (Recommended, composed with the crash terminal reason)** — When the marker's `session_id` is present, differs from the caller, AND the owning session is provably stale/dead (a process-liveness probe, or an age threshold shorter than the 24h path-A window), let an operator teardown proceed. Reuse `marker_owner_status`'s non-destructive `foreign-stamped` detect + a liveness check; require an explicit operator opt-in so a mere session mismatch never auto-tears a LIVE foreign run. Pro: keys recovery on the real signal (dead + foreign), collapses the containment refusal at its root. Con: needs a reliable cross-platform liveness probe and a careful "provably dead" definition; must preserve the non-destructive-on-live-mismatch invariant.
- **(b) First-class `--recover-stale-marker` / `--force-run-end` op** — One sanctioned, audited step that cycle-ends + run-ends + records a crash/disconnect terminal reason, gated on `--operator-authorized` + a provable-staleness precondition. Pro: collapses the 4-gate cascade into one discoverable command; leaves an explicit audit trail. Con: a new authority surface to design + test; overlaps (a)'s staleness precondition.
- **(c) Chain-aware refusal messages only (minimum)** — Make each refusal in the cascade name the full recovery invocation. Pro: cheap, no authority change. Con: does not remove the cascade; points at whichever recovery UX is chosen, so it follows (a)/(b) rather than leading.
- **New sanctioned terminal reason** (orthogonal, composes with any above) — Add `crashed-run` / `remote-control-disconnect` to `SANCTIONED_STOP_TERMINAL` so an honest operator teardown need not borrow an unrelated sanctioned reason.

**Recommendation:** (a) + the crash terminal reason, with (b) as the ergonomic wrapper if the operator wants a single command; (c) folded into whichever lands. The operator owns the "provably dead" definition (liveness probe vs. a short age threshold) and whether a crash reason may end a run without `--operator-authorized`. Surfaced rather than baked — this is an authority-model fork.

**HARD-PARK (harden Round 60, 2026-07-17, park-provisional protocol).** Assessed under the park-provisional default and DELIBERATELY NOT implemented — this decision hits BOTH hard-park carve-outs. (1) **Gate-weakening (Prohibition #2):** the recommended option (a) softens the containment deny decision (`refuse_if_cycle_active` / `refuse_cycle_marker_mutation_if_subagent` would now ALLOW a foreign+dead-owner teardown they currently refuse), and the composed `crashed-run`/`remote-control-disconnect` sanctioned terminal reason lets a run END WITHOUT `--operator-authorized` (removing an authorization requirement) — both are softenings of an existing denial/validation, never provisional-eligible. (2) **`divergence: structural`:** it forks the operator recovery workflow and the containment/terminal-reason authority model, and the "provably dead" cross-platform liveness definition is exactly the expensive-to-redirect wrong-pick the structural carve-out reserves for the operator. A purely-additive `--recover-stale-marker` op gated on `--operator-authorized` (no new no-auth terminal reason) would be provisional-eligible in isolation, but it does not resolve the recommended fix and would pre-empt the operator's authority-model choice, so the whole decision stays a blocking park for operator sign-off. Nothing implemented.

### 13. A `partial` MCP_TEST_RESULTS.md whose only uncovered rows are all test-exempt/build-deferred has no AUTHORABLE path to VALIDATED.md: bless model-authored exemptions + classify build-artifact-deferred?

*(harden Round 59 — 2026-07-17, manual invocation. Surfaced by the AlgoBooth `/lazy-bug-batch` run in two `NEEDS_INPUT.md` docs flagged "for a future claude-config harden": `sidecar-integrity-gate-blocks-user-modified-sidecar` (this class) and `adhoc-hydra-load-code-mcp-tool` (adjacent). Bug: `docs/bugs/partial-mcp-results-all-exempt-rows-no-authorable-validated-path/` (Concluded). Bundles with #2 (Round 45) and #9 (Round 47).)*

**Problem:** A fully-implemented, Rust-validated AlgoBooth bug fix with coherent PHASES.md produced a `result: partial` `MCP_TEST_RESULTS.md` (pass 4/4) whose ONLY two uncovered verification rows are both legitimately un-MCP-drivable this cycle — row 1 a Tauri command with no registered MCP-tool mirror ("Cannot Prove" class), row 2 a `Mismatch` branch reachable only against a packaged build ("build-artifact-deferred"). `__write_validated_from_results__` refuses a non-`all-passing` result, so the state machine loops on mcp-test forever and the item never reaches `__mark_fixed__`. A scoped-validated escape hatch ALREADY EXISTS — `observation_gap_promotable` (`gates.py:608`) promotes a `partial` to a `validated-modulo-observation-gaps` VALIDATED.md when its `observation_gap_exemptions` list is non-empty with a `spec_class` on every entry AND `pass_count == total_count`, wired to the apply gate (`pseudo.py:631`), the completion gate, and Step-9, documented in `sentinel-frontmatter.md:538-552`. But three things block reaching it: (a) the `mcp-test` SKILL never surfaces it — it teaches `partial` = "does NOT complete" (SKILL.md:338) and "the model NEVER authors sentinels — the engine writes them" (SKILL.md:248) — so the agent invented a `carve_outs:` block (`kind: host-artifact`), which SOFTENS an otherwise-all-passing run and does NOT promote a partial (sentinel-frontmatter.md:532-537), and the gate correctly refused; (b) `MCP_TEST_RESULTS.md` is written by the deterministic engine (`scripts/mcp-test/run.ts`, in the AlgoBooth target repo — out of harness scope), and the engine cannot make the `spec_class` judgment the exemptions block requires, so NO shipped path ever emits it — it can only appear if the model amends the engine's file, contradicting the "model NEVER authors sentinels" invariant; and (c) "build-artifact-deferred" is not the documented observation-gap class ("no MCP tool exists AND SPEC-locked to the unit/WDIO tier") — the assertion IS MCP-driveable, it just needs a packaged build, making it a deferral (closer to `DEFERRED_REQUIRES_DEVICE/HOST`) not a structural observation gap.

**Why not mechanical:** the core asks reverse an invariant and set gate semantics. Blessing a model-authored/model-amended `observation_gap_exemptions` block deliberately carves out the "engine writes sentinels" rule (the invariant that keeps a model from hand-forging a passing attestation) — a workflow-contract decision. Deciding whether "build-artifact-deferred" qualifies for observation-gap promotion (vs. needing its own partial-completable disposition) is a gate-semantics decision. And the file's writer is `run.ts` in the target repo, which this harness must not touch. Surfacing the escape hatch in the `mcp-test` SKILL prose is the only near-mechanical piece, but it is only actionable once (a) is decided (it is contradictory to tell the model to author a block it is told never to author).

**Scope note:** the two AlgoBooth bugs are DIFFERENT classes. `sidecar-integrity-gate-blocks-user-modified-sidecar` IS this write-validated deadlock. `adhoc-hydra-load-code-mcp-tool` already HAS a `VALIDATED.md` (all-passing reachability); its blocker is the COMPLETION gate refusing an unchecked row (row 3) genuinely blocked on an EXTERNAL sibling bug (a broken hydra `dist` ESM build) — a true dependency block, correctly escalated by its own NEEDS_INPUT, not a write-validated defect. The fix must not be mis-scoped to cover it.

**Options:**
- **(1) Bless a model-authored `observation_gap_exemptions` amendment + document it in the `mcp-test` SKILL (Recommended)** — Explicitly permit the model, when the engine writes a `result: partial` whose uncovered rows are all documented-untestable, to amend the results file's `observation_gap_exemptions` block (each entry `spec_class`-cited) — a NARROW carve-out of "engine writes sentinels" scoped to the exemptions block only (the counts + result literal stay engine-owned; the gate still refuses a provenance-less or genuine-failure partial). Surface the hatch + the `carve_outs`-vs-`observation_gap_exemptions` distinction in `mcp-test/SKILL.md`. Pro: reuses the shipped promotion gate; unblocks the D7-test-exempt-completable class without touching the AlgoBooth engine. Con: relaxes the model-never-authors invariant (mitigated: the spec_class provenance + pass==total cross-check + the gate's existing refusals bound the blast radius).
- **(2) Add a claude-config-side emit path** that stamps `observation_gap_exemptions` from a structured input (e.g. an `--emit-observation-gap` state-script op the cycle drives after the engine run), keeping the model out of the file. Pro: preserves "engine writes sentinels." Con: a new emit surface + the model still supplies the spec_class judgment as input, so it re-introduces the same trust question one layer out.
- **(3) Teach the AlgoBooth engine (`run.ts`) to emit exemptions** — OUT of harness scope (target-repo change); listed only to note the boundary.
- **Build-artifact-deferred classification** (orthogonal): either admit it as an observation-gap `spec_class`, or route it to a distinct partial-completable deferral disposition (a `DEFERRED_REQUIRES_BUILD.md`-style sentinel) so a dev-session partial can complete-modulo-deferral and re-open on a packaged build.

**Recommendation:** (1) for the authoring path (narrow, reuses the shipped gate) plus a decision on build-artifact-deferred — most cleanly, admit it as an observation-gap `spec_class` given it is already Rust-covered and PHASES pre-classifies it. The operator owns whether the model may amend the exemptions block and how build-artifact-deferred is classified. Surfaced rather than baked — a workflow-contract + gate-semantics fork that bundles with #2 and #9.

**PROVISIONALLY RESOLVED + RELOCATED (harden Round 61, 2026-07-17, park-provisional protocol).** Re-graded `divergence: contained` (the promotion gate `observation_gap_promotable` and its refusals are UNCHANGED; `spec_class` is a free-form provenance string so `build-artifact-deferred` is already admissible with no gate code change; the only change is making a SHIPPED mechanism reachable via `mcp-test/SKILL.md` prose + a narrow scoped carve-out of the "engine writes sentinels" discipline) and therefore IMPLEMENTED provisionally per option 1 rather than parked. Because this shared file bundles 13 decisions (over the 4-cap) and is graded `divergence: structural` (fail-closed / non-provisionalizable), this decision was relocated to its own provisional-eligible sentinel to be accepted independently: `docs/bugs/partial-mcp-results-all-exempt-rows-no-authorable-validated-path/NEEDS_INPUT_PROVISIONAL.md` (`resolved_by: auto-provisional`, ratification-pending). The `mcp-test/SKILL.md` "Scoped-validated partial" subsection + the `build-artifact-deferred` regression lock (`test_gates.py::test_observation_gap_promotable_admits_build_artifact_deferred_class`) are the shipped change.

## Why this is surfaced and not auto-applied

Per the hardening prohibitions and decision-class tiering: D-A and D-B were applied mechanically under full gates (Round 19). D-C's mechanical half (guard deny) was ALSO applied mechanically — a bare unresolved ref token now hard-denies. The ONLY thing escalated here is the dispatch-preference contract flip, which reverses a deliberate Phase 7 design decision and trades one real failure class for another. That is a `product`-class fork, so it is surfaced via this file rather than baked silently.
