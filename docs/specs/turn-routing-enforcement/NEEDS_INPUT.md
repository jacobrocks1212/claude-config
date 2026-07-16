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
date: 2026-06-16
class: product
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

## Why this is surfaced and not auto-applied

Per the hardening prohibitions and decision-class tiering: D-A and D-B were applied mechanically under full gates (Round 19). D-C's mechanical half (guard deny) was ALSO applied mechanically — a bare unresolved ref token now hard-denies. The ONLY thing escalated here is the dispatch-preference contract flip, which reverses a deliberate Phase 7 design decision and trades one real failure class for another. That is a `product`-class fork, so it is surfaced via this file rather than baked silently.
