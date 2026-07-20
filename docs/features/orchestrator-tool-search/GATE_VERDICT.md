---
kind: gate-verdict
feature_id: orchestrator-tool-search
gate_version: 1
date: 2026-07-19
scope_hit:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
checks:
  overfit: pass
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: net-new — adds one read-only roster script (`tool-search.py`), one prose rule mirrored across the coupled dispatch skills, and one KPI selector; it retires no existing mechanical rule, but it replaces the orchestrator's informal "improvise or blind-dispatch `/harden-harness`" behavior at the dispatch-time tool-gap decision point with a deterministic search-before-acting step. The added surface pays for itself by preventing duplicate tool proposals (dedup against the toolify ledger) and improvisation past a missing correctness-load-bearing tool; it introduces NO new remediation machinery (reuses the shipped observed-friction harden + `pending_hardening` route-withhold + host-capability defer) and NO new curated index (the corpus is aggregated from the existing registries, so it cannot drift beyond what already gates them).
---

## Adversarial answers

### overfit

No flag (checker `result: pass`). The scoped diff to the two `SKILL.md` files appends no literal to a matcher alternation / list / set / allow-list and adds no incident-shaped literal (no `docs/{features,bugs}/<slug>` id, date, or session id). It is a terse prose rule ("before an abnormal operation that needs a specific tool/CLI, run `--tool-search "<need>"` first; on a hit invoke the match; on a MISS follow the printed suggestion") placed immediately before the harden Trigger-5 block — structural guidance, not a fitted pattern. The mechanical half of the feature (`tool-search.py`) ranks by deterministic keyword/token overlap over the aggregated registries rather than an enumerated need-list, so there is no per-incident literal to overfit to.

### tautology

If this change were BROKEN, the declared KPI alone could still look like success. The KPI `blind-tool-gap-dispatch-rate` (down-is-good) measures the share of tool-gap harden dispatches NOT preceded by a `--tool-search` in the same cycle — i.e. it measures whether a search was *invoked*, not whether the search *worked*. A `tool-search.py` that always returned a false `MISS` (or ranked garbage) would still be invoked before dispatch, so the blind-dispatch-rate would fall to ~0 exactly as it would for a correctly-working search — the failure mode and the success mode share the metric. So the KPI is invocation-tautological on its own.

Independent signal declared (`signal_independence: independent`): the search's *correctness* is asserted by a signal this change does not itself emit or suppress — the `test_tool_search.py` correctness suite (Validation Criteria rows "Search returns real matches" and "Miss is explicit"), which fails deterministically if the ranker MISSes on a need whose tool demonstrably exists in the corpus, plus the dedup-against-double-proposal count read from the `toolify-ledger.json` (an independent ledger written by the offline miner / promotion path, not by this feature's KPI compute). A broken search would drive `blind-tool-gap-dispatch-rate → 0` while the correctness tests went red and duplicate tool proposals kept appearing in the ledger — the divergence between the invocation KPI and these independent observables is what distinguishes "working" from "broken." A future `intervention-efficacy-tracking` verdict / retro finding on realized search hit-precision is the standing independent cross-check the harness already applies to a passed-then-REFUTED change.

### gate_weakening

No hit (checker `result: pass`). The scoped diff deletes no `def test_*`, changes no numeric literal on a gate line, grows no sanction/exemption set, introduces no `*_BYPASS` env-var, and removes no `permissionDecision: deny` / `refuse_*` / `exit 3` branch. The feature only ADDS a deny-free read-only capability and prose; the correctness-load-bearing miss path STRENGTHENS blocking by reusing the shipped `pending_hardening` route-withhold to hold the run at the gap rather than shipping unverified work. No gate is loosened, so no operator sign-off is required.

### complexity

Declared `net-new` (see the `retires:` line). This change does not retire an existing mechanical rule — there is no prior dispatch-time tool-availability lookup to replace — so no retire claim is asserted (nothing would falsely "stop firing"). The added surface is minimal and self-justifying: one read-only stdlib roster script whose corpus is the existing registries (bounded by `cli_surface_gen --check` / `doc-drift-lint` freshness, so no new drift surface), two three-line coupled-pair prose insertions, and one KPI selector. It reuses the entire remediation spine (observed-friction harden, route-withhold, depth-cap, toolify dedup, host-capability defer) instead of forking any of it, so the net complexity added is a single new discoverable capability, not a parallel proposer.
