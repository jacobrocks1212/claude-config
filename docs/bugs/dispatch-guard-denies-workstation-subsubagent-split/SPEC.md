# Dispatch Guard Denies Workstation Sub-Subagent Split — Investigation Spec

> `workstation-recursive-subagent-dispatch` (5ff570b) lifted the cycle-worker inline-override ban in *prose only* — `lazy_guard.py` was never taught the matching allow, so under a live run marker the guard denies every `/execute-plan` (and `/spec-phases`, `/plan-feature`, …) worker's mandated test-agent/impl-agent sub-subagent dispatch, booking one FIFO hardening debt per denial.

**Status:** Concluded
**Fixed:** 2026-07-10 (operator resolved decision 4 same day — see Resolution, below)
**Severity:** P1
**Discovered:** 2026-07-10
**Placement:** docs/bugs/dispatch-guard-denies-workstation-subsubagent-split
**Related:**
- `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` — **decision 4** (the open, ungraded `product`-class fork; this bug is its concrete manifestation and its resolution site)
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` — Rounds 9–13 (five consecutive log-only rounds draining into this gap)
- `docs/features/workstation-recursive-subagent-dispatch/` — the policy lift (`5ff570b`) that created the prose↔guard divergence
- `docs/bugs/adhoc-containment-denies-mandated-explore-fanout/` — the *containment*-hook sibling that WAS fixed the same day; this is the *dispatch*-guard half that was overlooked

<!-- Status lifecycle: Investigating → Concluded. Root cause is `traced` (see Root-Cause
     Trace, below); flip to Concluded once the transition decision is recorded. -->

---

## Verified Symptoms

<!-- Provenance note: these are VERIFIED by direct first-hand observation of the orchestrator
     (this session, AlgoBooth /lazy-batch 30 --park --park-provisional), not by third-party
     user report. The observer IS the affected component. Each is reproduced live below. -->

1. **[VERIFIED]** Under a live per-repo lazy run marker, a cycle worker's `Agent`-tool dispatch of a test-agent or impl-agent sub-subagent is **denied** with the reason string "dispatch prompt not script-emitted this turn — re-run the Step 1a probe (`--emit-prompt`) …". — observed on every `/execute-plan` cycle this run.
2. **[VERIFIED]** Each denial **books a hardening debt** in the deny-ledger (`kind: validate-deny`, `acked: false`) that the advancing probe uses to withhold the forward route (`route_overridden_by: pending-hardening-debt`). — observed: `pending_hardening` rose to 1 (part-1) then 2 (part-2).
3. **[VERIFIED]** The debt is retired **one-per-hardening-dispatch** (FIFO, no dedup), so N identical denials require N full ~90k-token Opus `/harden-harness` rounds — each a **confirmed no-op** (log-append only; no harness change is safe without the operator-owned discriminator). — observed: Rounds 9–13, five consecutive log-only rounds.
4. **[VERIFIED]** The denial rate is **stage- and queue-wide and accelerating**: part-1 booked 1 denial (impl-agent), part-2 booked 2 (test-agent ×2); it also fires on `/spec-phases` planning cycles (Rounds 11–12), not just `/execute-plan`. — observed across 3 features (`key-detection-host-port`, `managed-llm-credits`, and `/spec-phases` items).
5. **[VERIFIED]** Work still **completes correctly** because the worker falls back to inline execution (part-2 landed 49/49 Workers tests) — so this is a *token-cost / progress-throughput* defect, **not** a correctness defect. The cost is the wasted no-op hardening (~1M+ tokens projected across the remaining `managed-llm-credits` parts alone), which forced an operator-authorized run checkpoint at forward 14/30.

## Reproduction Steps

1. On **workstation** (not cloud), start a run that establishes a live per-repo run marker: `/lazy-batch <n> --park` against a repo with at least one feature whose plan has multiple parts.
2. Let the pipeline route a cycle to a skill with a **sub-subagent orchestration model** — `/execute-plan` (test-agent → impl-agent split) is the clearest; `/spec-phases` and `/plan-feature` also qualify.
3. The dispatched cycle worker follows its mandated model and issues an `Agent`-tool call to spawn its test-agent sub-subagent, composing that sub-subagent's prompt itself (it is structurally forbidden from script-emitting a nonce — see step 4).
4. **Observe:** the PreToolUse `Agent|Task` hook (`user/hooks/lazy-dispatch-guard.sh`) hands the prompt to `lazy_guard.py`; the prompt's sha is absent from the prompt registry (only orchestrator `--emit-prompt`/`--emit-dispatch` emissions register a nonce, and `refuse_if_cycle_active` `sys.exit(3)`s a worker that tries to emit one), so the guard falls through every allow branch to the no-match deny at `lazy_guard.py:839`.

**Expected:** A workstation cycle worker whose active cycle marker names a sub-subagent-model skill is ALLOWED to dispatch its in-scope sub-subagents while the marker is live (the `Agent`-tool permission granted by `cycle-base-prompt.md` and `lazy-batch/SKILL.md` should be honored by the guard, not contradicted by it).
**Actual:** Every such dispatch is denied and books a FIFO hardening debt; the worker falls back to inline (losing the structural test-agent/impl-agent separation the lift was meant to restore), and the orchestrator pays one no-op `/harden-harness` round per denial to clear the route.
**Consistency:** Deterministic — fires on every marked-run workstation cycle that exercises a sub-subagent model.

## Evidence Collected

### Source Code — the traced serving path (each hop `file:line`)

```
Agent/Task tool call (worker dispatching test-agent/impl-agent SUB-subagent)
  │  PreToolUse matcher "Agent|Task"
  ▼
user/hooks/lazy-dispatch-guard.sh
  ├─ :119-134  marker-presence gate → marker PRESENT → run full guard
  └─ :149      printf PAYLOAD | python lazy_guard.py
  ▼
user/scripts/lazy_guard.py :: guard()            :571   ← DECISION FUNCTION (fix site)
  ├─ :589-590  no "prompt" key         → allow    [N/A — Agent carries a prompt]
  ├─ :617-626  no run marker           → allow    [N/A — marker present]
  ├─ :651-693  @@lazy-ref by-reference → allow     [N/A — worker prompt is literal text]
  ├─ :710      sha = prompt_sha256(prompt)
  ├─ :713      lookup_emission(prompt) → None      (no registered nonce)
  ├─ :735      _try_auto_readmit(...)  → None      (not a suffix-superset of a cycle entry)
  ├─ :826      find_transcription_slip → None      (not a near-verbatim slip)
  └─ :839-842  return _deny_default(marker, _default_deny_reason(), …)   ← DENY SITE
        ▼  _deny_default()  :526  → bound marker → _deny_and_ledger() :566  (books debt)
        ▼  reason = _default_deny_reason() :238 → _CORRECTIVE_RECIPE :181-197
```

- **Deny site:** `user/scripts/lazy_guard.py:839-842` (the "no matching entry at all" fall-through, section comment `:806`), inside `guard()` (`:571`).
- **Debt-booking branch:** `_deny_default` (`:526`) → `_deny_and_ledger` (`:495`, invoked `:566`) under a **bound** (owner-session) marker.
- **Match key:** `sha = prompt_sha256(prompt)` (`:710`); registry match `lazy_core.lookup_emission()` (`lazy_core.py:12181`) requires sha-equal + `consumed==False` + within `REGISTRY_ENTRY_TTL_SECONDS` (1800s) + `emitted_at >= marker.started_at`.
- **Registry write (only allow-creating path):** `register_emission()` (`lazy_core.py:12105`) reached solely via the orchestrator CLI `--emit-prompt` / `--emit-dispatch`.
- **Worker cannot self-register:** `--emit-dispatch` calls `refuse_if_cycle_active()` (`lazy_core.py:11639`) which `sys.exit(3)`s for a cycle subagent (`:11670-11698`). The emission that would register a nonce is exactly the orchestrator-only routing op the worker's TERMINAL STOP forbids.
- **No exemption covers the case:** every non-trivial allow branch (`:713`, `:651`, `:735`, `:756`) requires a registry hit created by an orchestrator emission; the two silent allows (`no prompt` `:589`, `no marker` `:617`) don't apply during a marked run with a real prompt. There is **no** allow-list, capability predicate, or caller-role/marker-scoped exemption. **This absence is the gap.**

### Git History — the prose↔guard divergence

- **`5ff570b`** `feat(workstation-recursive-subagent-dispatch): lift cycle-subagent inline override on workstation` (Thu Jul 9 2026). Changed **11 files**: `ROADMAP.md`, the feature's `SPEC.md`/`PHASES.md`, the `lazy-batch*` + `lazy-bug-batch` + `restart-windows-claude` SKILL prose, `cycle-base-prompt.md`, `lazy-batch-cloud/SKILL.md`, and `test_lazy_core.py` (+14-line binding-matrix test).
- **Guard touched? NO.** Neither `user/scripts/lazy_guard.py` nor `user/hooks/lazy-dispatch-guard.sh` is in the diff. The policy now *permits* workstation sub-subagent dispatch in prose; the guard was never taught the matching allow. The same-day rollout fixed the *containment* hook (`adhoc-containment-denies-mandated-explore-fanout`) and overlooked the *dispatch* guard.

### Runtime Evidence — this session's ledger

- Deny-ledger (`~/.claude/state/<hash>/lazy-deny-ledger.jsonl`): 3 unacked entries at checkpoint — 2× `kind: validate-deny` (both TEST-WRITING agent, `managed-llm-credits` part-2) + 1× `kind: process-friction` (`unexpected-commits`, benign part-2 resume-safety flip). `pending_hardening()` (`lazy_core.py:15047`) counts all unacked regardless of kind.
- Blanket-cleared via operator-authorized `--run-end --ack-unhardened` → `ack_all_unacked_denies()` (`lazy_core.py:16170`), the only >1-entry ack path.

### Related Documentation

- **Decision 4** (`turn-routing-enforcement/NEEDS_INPUT.md` §4, lines 61–84): `class: product`, `next_skill: harden-harness`, **no `divergence:` grade, not provisional-excluded** — a live unresolved fork. Options: (1) active-cycle-marker exemption scoped to sub-subagent-model skills **[Recommended]**; (2) positive worker-set signal (env/depth marker); (3) register sub-subagent prompts via a new `--emit-sub-dispatch`; (4) orchestrator-session-only scope — *rejected* (`session_id` doesn't discriminate; the sub-subagent shares the orchestrator session). **Round-11 amendment (line 84):** option 1's scope MUST be a **general predicate** ("the active cycle marker's `sub_skill` declares a sub-subagent model"), NOT a hardcoded skill list (which omits `/spec-phases`, `/plan-feature`, `/spec-phases-batch`, `/implement-phase*`).
- **Cloud divergence constraint:** `/lazy-batch-cloud` KEEPS the inline override (`lazy-batch/SKILL.md` execution-model ¶ + `lazy-batch-cloud/SKILL.md` "Differences" table — "CLOUD OVERRIDE — LOAD-BEARING"). A fix MUST be workstation-scoped and MUST NOT allow sub-subagent dispatch under the cloud path.

## Theories

### Theory 1: Incomplete rollout of the policy lift (the guard is a missed edit site)
- **Hypothesis:** `5ff570b` updated every *prose* surface that grants the worker `Agent`-tool permission but missed the *enforcement* surface (`lazy_guard.py`) that must be relaxed in lockstep, leaving policy and guard contradictory.
- **Supporting evidence:** `git show --stat 5ff570b` shows guard files absent; the guard has zero caller-role/marker-scoped exemption branches; the same-day containment-hook fix shows the enforcement layer was being updated piecemeal.
- **Contradicting evidence:** None found. The Round-9 hardening analysis independently reached the same conclusion and opened decision 4 rather than mechanically patching — because the *safe* relaxation (a discriminator that can't be spoofed by a genuinely-improvising orchestrator) is a security-property choice, not a mechanical omission.
- **Status:** **Confirmed** (`traced`).

### Theory 2: `session_id` could discriminate worker from orchestrator (would make the fix trivial)
- **Hypothesis:** The guard could allow when the caller session differs from the orchestrator's.
- **Supporting evidence:** Superficially appealing.
- **Contradicting evidence:** The sub-subagent runs *inside* the orchestrator session (shared `session_id e3ee238d`); Round 9 proved `session_id` is a non-discriminator; decision 4 option 4 is explicitly rejected on this basis.
- **Status:** **Ruled Out.**

## Proven Findings

1. **Root cause (`traced`):** `lazy_guard.py:839` `_deny_default` denies the worker's sub-subagent prompt because no registry entry exists for it, and no allow branch exempts a marked-run workstation cycle worker whose active cycle marker names a sub-subagent-model skill. The prose lift (`5ff570b`) that authorized the dispatch never added that allow branch. **Fix site is ON the traced path** — a new exemption branch inside `guard()` (`:571`), evaluated before the `:839` fall-through.
2. **Why no round auto-fixed it:** the safe exemption is a security-property decision (a discriminator a real improvising orchestrator cannot trip), so Prohibition #2 (never weaken a gate without the operator's chosen discriminator) correctly held. This is the open `product`-class decision 4.
3. **The cost mechanism (`traced`):** FIFO `ack_oldest_deny` (`lazy_core.py:16127`) retires exactly one debt per hardening dispatch (locked decision-4 cadence, no dedup), so every recurrence multiplies full no-op Opus rounds — the throughput drain this bug is really about.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Dispatch guard (enforcement) | `user/scripts/lazy_guard.py` (`guard()` :571; deny :839; `_deny_default` :526) | Missing workstation sub-subagent allow branch — the fix site |
| Guard hook wrapper | `user/hooks/lazy-dispatch-guard.sh` (:119-149) | Entry path; unchanged by fix |
| Cycle-marker state | `user/scripts/lazy_core.py` (cycle-marker read; `register_emission` :12105; `refuse_if_cycle_active` :11639) | Supplies the discriminator (`sub_skill` on the active cycle marker) the fix predicate reads |
| Prompt policy (already lifted) | `user/skills/lazy-batch-prompts/cycle-base-prompt.md`, `user/skills/lazy-batch/SKILL.md` | Grants the permission the guard must honor; no further change |
| Cloud path (must NOT regress) | `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | Fix must be workstation-scoped |
| Hardening cadence (symptom amplifier) | `user/scripts/lazy_core.py` `ack_oldest_deny` :16127 | Per-denial FIFO drain; resolved indirectly once denies stop |

## Open Questions

- **Which discriminator does the operator bless for option 1?** The recommended predicate is "the active cycle marker's `sub_skill` declares a sub-subagent model AND the prompt is not a lifecycle/pipeline op." The operator owns the safety proof that this window cannot be spoofed by a genuinely-improvising orchestrator (the exact integrity property the guard exists to protect). This is decision 4 and is the sole blocker to a mechanical fix. → **Answered — see Resolution.**
- **Predicate source of truth:** where is "declares a sub-subagent model" recorded so the guard can read it without a hardcoded skill list? (Candidate: a skill-frontmatter capability flag the cycle marker copies at `--cycle-begin`.) → **Answered — the frontmatter-flag candidate, exactly; see Resolution.**
- **Should the FIFO ack cadence gain same-signature dedup** independently, to bound blast radius of any *future* recurring-deny class? (Secondary; not required if the deny is eliminated at the source.) → **Answered — DECLINED by the operator; see Resolution.**

## Resolution (2026-07-10 — operator decision + fix shipped)

**Decision 4 resolved by Jacob (interactive session, same day as Round 11):** option 1 as amended by Round 11, with the **consumed fence** as the cycle-marker-window discriminator; FIFO same-signature dedup declined (deny class eliminated at source; the one-debt-per-round cadence is a prior locked decision).

**The shipped predicate** — `lazy_guard.py` `guard()` branch **2b** (evaluated after the registry sha-match branches, before the transcription-slip check) ALLOWS an unregistered `Agent` prompt iff ALL of:

1. **Workstation only:** the run marker's `cloud` flag is falsy. Cloud runs keep the unconditional deny (the `lazy-batch-cloud` "CLOUD OVERRIDE — LOAD-BEARING" inline model is unchanged).
2. **Bound marker:** the run marker carries a non-None `session_id` (pre-bind, no worker can be in flight).
3. **Skill-declared capability (general predicate, no hardcoded list):** the active cycle marker's `subagent_model` field is True. It is stamped at `--cycle-begin` by `lazy_core.write_cycle_marker` via `skill_declares_subagent_model(sub_skill, repo_root=<run marker's repo_root>)`, which reads `subagent-model: true` from the skill's SKILL.md YAML frontmatter (repo-scoped `.claude/skills/` first, then user-level `~/.claude/skills/`; fail-closed on every degraded read). Ten skills declare the flag: `execute-plan`, `spec-phases`, `spec-phases-batch`, `plan-feature`, `plan-bug`, `spec`, `spec-bug`, `retro-feature`, `implement-phase`, `implement-phase-batch` — and any future sub-subagent-model skill joins by declaring the flag, closing the Round-11 allow-list gap.
4. **Consumed fence (the operator-owned safety proof):** the cycle marker's own registered emission is already consumed (`lazy_core.emission_consumed_by_nonce`, TTL-agnostic, fail-closed). `--cycle-begin` writes the marker BEFORE the orchestrator's worker dispatch, but consumption happens only on the guard-ALLOWed worker dispatch and session tool calls are serial — so once (marker active AND emission consumed) holds, an unregistered prompt can only originate INSIDE the in-flight worker. The pre-consume window where the orchestrator itself could improvise stays denied (verified by `test_guard_worker_subdispatch_denied_before_consume`).

**Audit trail:** every exempted allow appends a `worker_subdispatch: true` deny-ledger event (pre-acked — a sanctioned dispatch path owes no hardening debt; `pending_hardening()` unaffected). The containment hook independently continues to police lifecycle/pipeline OPERATIONS inside the worker, and bare `@@lazy-ref` prompts remain hard-denied ahead of the branch.

**Fix surface** (fix commit = the commit introducing this section):
- `user/scripts/lazy_guard.py` — branch 2b (fail-closed: any error falls through to the pre-fix deny paths).
- `user/scripts/lazy_core.py` — `skill_declares_subagent_model`, `emission_consumed_by_nonce`, `append_worker_subdispatch_event`, `write_cycle_marker` `subagent_model` stamping (additive field; legacy markers read falsy → no exemption).
- Ten `user/skills/*/SKILL.md` frontmatter flags (list above).
- Prose: the `lazy-batch`/`lazy-bug-batch` SKILL "unregistered prompt is denied" sentence now names the exemption; decision 4 in `turn-routing-enforcement/NEEDS_INPUT.md` carries the resolution.
- Tests: 4 unit tests (`test_lazy_core.py` — predicate, fence, marker stamping) + 5 end-to-end guard pipe-tests (`test_hooks.py` — allow + audit + zero debt; deny on pre-consume / no-capability / cloud / unbound). Full suites green: test_lazy_core 939/939, test_hooks 149/149, `lazy-state.py --test` + `bug-state.py --test` all-pass (run from a neutral cwd).

**Status effect:** the run-blocking deny class is eliminated at the source — a workstation cycle worker's mandated sub-subagent split now executes as `workstation-recursive-subagent-dispatch` (5ff570b) intended, and no hardening debt is booked for it. Rounds 9–13's log-only drain ends with this commit.
