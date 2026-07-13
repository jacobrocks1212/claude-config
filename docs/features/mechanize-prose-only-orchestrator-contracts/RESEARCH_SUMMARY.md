# RESEARCH_SUMMARY — mechanize-prose-only-orchestrator-contracts

**Purpose:** fresh gap inventory at implementation time (2026-07-12/13), re-verified against HEAD
since the SPEC's four contracts (a)-(d) predate this session and the repo mechanizes prose-only
contracts frequently. Per-contract verdict: already-mechanized-at (commit/mechanism) vs
still-prose-only (residual gap this feature closes).

## Gap inventory

| Contract | SPEC-cited evidence | HEAD-verified status at session start | Verdict |
|----------|---------------------|----------------------------------------|---------|
| (a) Model-tier pinning | `register_emission` has no `model` field (~13684); guard ALLOW paths (`lazy_guard.py` fresh-consumption ~715-729, F2a by-ref ~650-693, idempotent re-fire ~756-767, F1b auto-readmit `_try_auto_readmit`) never touch `model:` | Confirmed via direct read of `lazy_core.register_emission` and all `lazy_guard.py` `_allow_json`/`_allow_with_updated_input` return sites — no `model` field anywhere in the registry entry schema or any guard ALLOW path | **Still prose-only** — mechanized this session (Phase 1) |
| (b) Post-cycle input-audit obligation | `--emit-dispatch input-audit` exists as a registered class (SKILL.md §1d.5 dispatch mechanics); no `audit_obligation` marker field, no withhold branch alongside the pending-hardening-debt withhold at `lazy-state.py` `--emit-prompt` (~13216-13243) | Confirmed via grep for `audit_obligation`/`input-audit` across `lazy_core.py`/`lazy-state.py` — the dispatch mechanism exists but nothing *obligates* running it; the withhold precedent (`route_overridden_by: "pending-hardening-debt"`) has no audit-obligation sibling | **Still prose-only** — mechanized this session (Phase 2) |
| (c) Decision write-back | No `--record-decision` subcommand exists (verified: `grep -n "record-decision"` — zero hits pre-session); `dispatch-apply-resolution.md` header explicitly states "the orchestrator sets resolution_kind and chosen_path from probe output + user answer before calling emit_dispatch_prompt" | Confirmed — `chosen_path`/`resolution_summary` are `--context` args typed by the orchestrator at both Step 1g (decision-resume) and Step 1h (blocked-resolution) dispatch sites in `lazy-batch/SKILL.md`, `lazy-batch-cloud/SKILL.md`, `lazy-bug-batch/SKILL.md` | **Still prose-only** — mechanized this session (Phase 3) |
| (d) Push-notification policy | `notify_halt` exists (~19536 pre-session), wired at both state scripts' `main()`; no `notify_event`/generalized seam; §1c.6 names park/budget-trip/flush/provisional-accept as orchestrator-only `PushNotification` calls | Confirmed — `notify_halt` covers only `state["terminal_reason"]`-keyed halts; no equivalent for the four other event points | **Still prose-only** — mechanized this session (Phase 4) |

**Cross-check against "recently mechanized" examples cited in the dispatch prompt** (seam-enumeration
mandate, receipt-exempt terminal disposition, plan-structural pickup backstop, `hosts=` dialect
filter, commit-cadence frontmatter, `--ack-deny`, `--fsck`, cli-surface registry, size ratchet,
`--marker-status`): none of these ten items overlap with (a)-(d) — they mechanize unrelated
contracts (hardening dispatch classification, receipt exemptions, environment dialects, commit
budgets, deny acknowledgement, bug-archive fsck, CLI introspection, skill-size ratchet, marker
status queries). The SPEC's four contracts were genuinely still prose-only at session start; the
prompt's list is evidence of the general "mechanization keeps happening" trend, not a hit against
this feature's specific scope.

## Locked decisions (per SPEC recommendations)

- **D1 (model pinning: rewrite vs deny) — `product-behavior`.** Recommendation A (pin-by-rewrite)
  adopted and **implemented**, but per the operator's park-provisional protocol this is a
  product-behavior fork requiring ratification, not an auto-accept — see
  `NEEDS_INPUT_PROVISIONAL.md`. The feature proceeds against option A; SPEC Status stays Draft and
  no `COMPLETED.md` is written until ratified.
- **D2 (audit-obligation mechanics) — `mechanical-internal`, auto-accepted.** Recommendation A
  (run-marker obligation + route withhold, mirroring `pending-hardening-debt`) implemented verbatim.
- **D3 (decision-record surface) — `mechanical-internal`, auto-accepted.** Recommendation A
  (`--record-decision` → sibling state file, `--emit-dispatch apply-resolution` reads from it)
  implemented verbatim. Open Question 2 (marker vs sibling file) resolved toward the sibling file
  per the SPEC's own bias — `lazy-decisions.json` survives `--run-end` (not part of the run marker's
  scoped-key schema), so the answered-decisions ledger outlives the run for retro evidence.
- **D4 (notification coverage) — `mechanical-internal`, auto-accepted.** Recommendation A
  (`notify_event` generalizing the `notify_halt` seam) implemented. Event-point interpretation
  decisions made during implementation (not specified in the SPEC's Technical Design beyond naming
  the four sites):
  - **park** — fired at each `_PARKED.append(...)` call site in the queue walk (4 sites per state
    script: canonical BLOCKED, mis-named blocker, NEEDS_INPUT, unratified provisional).
  - **budget-trip** — fired at the FIRST budget-guard trip surfaced per probe (mirrors the existing
    `_BUDGET_GUARD is None` rich-audit-metadata gate). Budget-guard "extension"/grace is NOT wired to
    a distinct notify_event call — v1 scope is the trip only (the SPEC names "budget-guard
    trip/extension" as one combined bullet without separately specifying grace-event wording); this
    is a documented, deliberate v1 scope-narrowing, not a missed contract.
  - **flush** — interpreted as the `--run-end` state transition itself (immediately before the
    marker is deleted), since no dedicated "flush protocol" function exists in code — the SKILL.md's
    "end-of-run flush" is an orchestrator-prose sequence (incident-scan + efficacy-eval + `--run-end`),
    not a single state-transition site. `--run-end` is the one mechanical event that closes out every
    flush sequence, so it is the natural, defensible notify_event site.
  - **provisional-accept** — fired at `--provisionalize-sentinel`'s success path.
- **D5 (scope guard) — `mechanical-internal`, auto-accepted.** No redesign; all four (a)-(d)
  mechanizations reuse existing precedent shapes (`register_emission`/guard ALLOW paths,
  `pending-hardening-debt` withhold, `notify_halt` seam) rather than inventing new policy.

## Bug-pipeline parity note (discovered during implementation, not in the original SPEC)

The SPEC's Technical Design states "(a) and (b) land pipeline-symmetric via
`lazy_parity_audit.py`" but does not enumerate the bug pipeline's exact audited `sub_skill` set for
(b). `lazy-bug-batch/SKILL.md`'s EXISTING (pre-session) Step 1d.5 skip-condition prose is explicit:
*"`sub_skill` is NOT in {`spec-bug`, `spec-phases`}... `plan-bug` is a planning step, not a
SPEC/PHASES-authoring cycle — skip audit for `plan-bug`."* This directly contradicts a naive
`plan-feature`/`plan-bug` pairing. Per SPEC D5 ("a discovered ambiguity resolves in favor of
existing prose semantics"), `AUDITED_CYCLE_KINDS` is `{spec, plan-feature, spec-bug, spec-phases}`
— `plan-bug` is deliberately excluded, matching the documented (if slightly confusingly-worded)
existing bug-pipeline contract. `spec-phases` is carried for prose fidelity even though
`bug-state.py`'s live routing never emits it today (`SKILL_SPEC_PHASES` is defined but unused) —
harmless if it never fires, pre-covered if the bug pipeline ever starts emitting it.
