# probe→emit→dispatch atomicity does not mandate reading the FULL probe JSON — Investigation Spec

> The orchestrators' `probe→emit→dispatch atomicity` rule mandates a *fresh* re-probe before every dispatch but never says to consume the **whole** probe JSON. An orchestrator can field-extract a subset of keys (e.g. `pending_hardening`, `terminal_reason`) and route on that, risking a missed routing signal — `diagnostics`, `git_guards`, `self_edit_mode`, `route_overridden_by`, `cycle_prompt_refused`, `device_deferred_features`, etc. Observed as a self-corrected near-miss in a live AlgoBooth run.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/probe-full-read-before-dispatch
**Related:** `user/skills/lazy-batch/SKILL.md:591` (atomicity rule) + `:593` (freshness rule); coupled twins `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` and `user/skills/lazy-bug-batch/SKILL.md`; single-item `lazy`/`lazy-cloud`/`lazy-bug`; `user/scripts/lazy-state.py:6654-6664` (existing field-extraction hazard comment for `cycle_model`); sibling bug `docs/bugs/_archive/mcp-test-legacy-md-routes-to-haiku/`.

---

## Verified Symptoms

1. **[VERIFIED]** In a live AlgoBooth `/lazy-batch` run, the orchestrator self-corrected before the mcp-test dispatch: "I should have read the full probe JSON rather than field-extracting — pending_hardening=0, terminal_reason=null, no loop, so routing is clean." — confirmed by operator screenshot (2026-06-19). No mis-route resulted *this time* (routing was in fact clean), making it a near-miss, not a live failure.
2. **[VERIFIED]** The operator wants this filed and fixed as a harness-hardening item rather than dismissed as a one-off. — confirmed via AskUserQuestion (scope: "Bug 1 + Bug 2 routing").

## Reproduction Steps

1. Orchestrator brings the dev runtime up, then re-probes fresh before the mcp-test dispatch to honor probe→emit→dispatch atomicity (`SKILL.md:591`).
2. Instead of reading the complete probe JSON, the orchestrator field-extracts a subset of keys (a "compact" read piping/jq-style cherry-pick of `pending_hardening` / `terminal_reason`).
3. It makes the routing decision (set cycle marker, dispatch) from that subset.

**Expected:** the routing decision is made against the COMPLETE current probe JSON, so no emitted routing signal can be silently dropped.
**Actual:** the decision is made from a hand-chosen subset of keys; any signal outside that subset (`diagnostics`, `git_guards`, `self_edit_mode`, `route_overridden_by`, `cycle_prompt_refused`, …) is invisible to the decision. Harmless when those happen to be empty; a latent mis-route when they are not.
**Consistency:** Latent — manifests only when a non-extracted key carries a live signal; otherwise silent.

## Evidence Collected

### Source Code

- **The atomicity + freshness rules** — `user/skills/lazy-batch/SKILL.md:591` ("probe→emit→dispatch atomicity"): a real-skill dispatch is valid only when its prompt is the `cycle_prompt` from an `--emit-prompt` probe in the SAME turn; `:593` (freshness) forbids dispatching an emission from an earlier turn. **Neither rule says the orchestrator must read the full probe JSON** — they govern prompt provenance and turn-freshness, not how completely the probe output is consumed.
- **The probe emits many routing-relevant keys** — a `lazy-state.py --probe` payload carries ~15 top-level keys: `terminal_reason`, `notify_message`, `diagnostics`, `device_deferred_features`, `git_guards`, `self_edit_mode`, `governing_files_touched`, `cycle_header`, plus (under `--emit-prompt`/`--repeat-count`) `route_overridden_by`, `hardening_emit_command`, `cycle_prompt`, `cycle_model`, `cycle_prompt_refused`, `repeat_count`. Field-extracting any subset can drop a signal the orchestrator is contractually required to act on (e.g. `route_overridden_by: pending-hardening-debt`, a `diagnostics` dangling-entry, an unclean `git_guards`).
- **Prior art — the hazard is already known** — `user/scripts/lazy-state.py:6654-6664`: a comment records that "an orchestrator that field-extracted `cycle_model` dispatched a forward route over live debt (session e076ed30)," and the script now withholds `cycle_prompt`/`cycle_model` on pending hardening debt so "the extractor now fails loudly on the missing key." That fix hardened ONE key against extraction; this bug is the general contract gap — the SKILL prose still permits field-extraction for every other key.

### Runtime Evidence

Operator screenshot (2026-06-19): orchestrator's self-correction note quoted in Symptom 1, immediately before `Set cycle marker for mcp-test dispatch` and the haiku dispatch.

### Related Documentation

`user/scripts/CLAUDE.md` documents the probe as the deterministic source of truth the thin wrappers consume; the wrappers "carry no state-machine logic of their own," which means they MUST faithfully consume the script's full output rather than re-deriving a routing decision from a subset.

## Theories

### Theory 1: contract gap — atomicity covers freshness, not completeness
- **Hypothesis:** the atomicity/freshness rules guarantee the prompt is fresh and verbatim but never require the orchestrator to consume the full probe JSON, leaving field-extraction permitted by omission.
- **Supporting evidence:** `SKILL.md:591`/`:593` text; the `lazy-state.py:6661` comment showing a real prior incident from exactly this class.
- **Contradicting evidence:** none — the prior fix is point-hardening for one key, confirming the general rule is absent.
- **Status:** Confirmed.

## Proven Findings

- The orchestrator contract does not require full-probe-JSON consumption before a routing decision; field-extraction is permitted by omission and has caused at least one prior live mis-route (`cycle_model` over hardening debt). **Confirmed.**

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Atomicity contract | `user/skills/lazy-batch/SKILL.md` (~591–593) | Add a full-read clause to the atomicity rule. |
| Coupled twins | `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md` | Mirror the clause (per CLAUDE.md coupling rule). |
| Single-item wrappers | `user/skills/lazy/SKILL.md`, `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md`, `user/skills/lazy-bug/SKILL.md` | Same dispatch contract; mirror where the dispatch protocol is described. |
| Shared dispatch prose | `user/skills/_components/lazy-dispatch-template.md` (+ `orchestrator-voice.md` if it describes the probe read) | Single best place to state the clause once if injected. |

## Open Questions

- **Prose-only vs. enforceable.** The cleanest fix is a contract clause (read the full probe JSON; never route from a field-extracted subset). A stronger, optional follow-on: have the dispatch-guard hook / `--emit-prompt` path detect a routing decision that ignores a live signal (mirroring the `cycle_model` "fail loudly on missing key" pattern). `/plan-bug` should decide whether to scope only the prose clause (cheap, mirrors-across-pair) or also a mechanical guard. Recommendation: prose clause across all wrappers in this pass; note the mechanical guard as a candidate follow-up.
- **Where to state it once.** Prefer adding the clause to the shared dispatch component so the coupled pair + single-item wrappers inherit it, rather than hand-mirroring into each SKILL.md, if the injection points line up.
