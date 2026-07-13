# Hardening intervention records are unmeasurable or unverifiably exempt — Investigation Spec

> The `/harden-harness` Step-4 capture contract produces records the evaluator can never grade:
> two records name telemetry event types that do not exist in the emit vocabulary (accepted
> silently — `record_intervention` validates nothing), 17 of 25 records are
> `target_signal: undeclared`, and round-vs-record coverage is prose-only self-attestation —
> a round's "Intervention record: none" exemption line is checked by no one.

**Status:** Fixed
**Fixed:** 2026-07-12
**Fix commit:** 74e2c121
**Priority:** P1
**Last updated:** 2026-07-11
**Related:** `docs/bugs/_archive/interventions-telemetry-repo-scope-split-brain/` (the evaluation-side
starvation on the SAME records — fix both or the loop stays open);
`docs/bugs/efficacy-future-check-unenforced-orchestrator-prose/` (sibling, fixed 2026-07-11
`7d49490` — its D2 already directed hardening records toward measurable signals, prose-only);
`docs/bugs/no-mid-run-observed-friction-harden-dispatch/` (sibling, fixed 2026-07-11 `c46ed80` —
its fix-scope §6 makes the observed-friction dispatch PROMPT for a measurable signal; this bug adds
the mechanical validation that prompt lacks); `user/skills/harden-harness/SKILL.md:311-332` (the
prose-only capture contract); `docs/interventions/CLAUDE.md` (the D4-B event vocabulary).

## Verified Symptom

Three capture-side defects, each verified against the live tree:

- **(a) Vocabulary-invalid target signals accepted silently.** `harden-2026-07-r5.md` declares
  `target_signal: event:no-route` and `harden-2026-07-r7.md` declares `event:route-loop`. Neither
  type exists: the D4-B vocabulary (`docs/interventions/CLAUDE.md:~115-118`) is `run-start`,
  `run-end`, `cycle-begin`, `cycle-end`, `pseudo-applied`, `dispatch`, `halt`, `sentinel-resolved`,
  `gate-refusal`, `containment-refusal`, and a grep of every `append_telemetry_event(` call site
  across `lazy_core.py` / `lazy-state.py` / `bug-state.py` emits exactly that set — `no-route` and
  `route-loop` appear nowhere as events (only as hardening *trigger kinds*). `record_intervention`
  (`lazy_core.py:16429`) performs NO vocabulary check — `target_signal = hyp.get("target_signal")
  or "undeclared"` (`:~16518`) accepts any string, and `_intervention_signal_event`
  (`lazy_core.py:16104`) blindly strips the `event:` prefix. Both records froze
  `baseline: events: 0` (corroborating: the signal has never occurred and never can), yet they
  LOOK measurable — the evaluator will forever count zeros against them instead of surfacing them
  as `undeclared` for triage.
- **(b) 17 of 25 records cannot be graded at all.** Verified frontmatter sweep: 17 records carry
  `target_signal: undeclared` / `baseline: not-computable` — including hardening records r6, r17,
  r19, and **r22, captured 2026-07-11, the same day as the measurability push** (siblings' D2/§6
  landed that day) — an intervention shipped into the ledger already ungradeable. Only 8 of 25 are
  measurable, and 6 of those 8 share one signal (see the efficacy-signal-integrity feature).
- **(c) Round-vs-record coverage is self-attested prose.** `docs/specs/turn-routing-enforcement/
  hardening-log/2026-07.md` has 22 rounds; 12 records exist (r5-r7, r14-r22). The gap decomposes —
  verified round-by-round — into rounds 1-3 (mechanical fixes shipped BEFORE the capture contract
  landed in `42d662b`, 2026-07-04; never backfilled) and rounds 4, 8-13 (self-declared exempt via
  an "Intervention record: none — a no-harness-change / NEEDS_INPUT round…" line). Every
  post-contract mechanical-fix round DOES have a record — but only by discipline: the Step-4
  contract is prose ("ALSO capture", `harden-harness/SKILL.md:311-332`), nothing mechanically
  verifies that a `Mechanical fix applied:` round has a matching
  `docs/interventions/harden-<YYYY-MM>-rN.md`, and the exemption line is unverifiable
  self-attestation. One undisciplined round silently breaks coverage with no signal anywhere.

## Root Cause

**Classification: `missing-contract` (authoring-time validation gap).** The capture path was built
deliberately fail-open for the *completion gate* (a capture failure must never block a feature
completion — D2-A), and that posture was carried over wholesale to the *CLI hardening path*, where
it is unjustified: a hardening round is an interactive, claude-config-scoped act with no completion
to protect. So the CLI accepts unknown event vocabularies without a warning, accepts `undeclared`
on `pipeline: hardening` without resistance, and the round↔record coverage contract exists only as
skill prose plus per-round self-attestation.

## Fix Scope (Concluded)

1. **Authoring-time vocabulary validation in `record_intervention`.** A closed-set check of
   `event:<type>` targets against the D4-B vocabulary (single source of truth: a
   `lazy_core` constant the emit sites and the check both use — the `_HOST_CAPABILITY_REGISTRY`
   closed-registry precedent). Unknown type → **reject on the CLI path** (exit 1, name the valid
   set); the completion-gate path stays fail-open but degrades the record to
   `target_signal: undeclared` with a loud diagnostic (never a silently-frozen zero baseline).
2. **Hard-fail undeclared hardening records on the CLI path.** `--record-intervention --pipeline
   hardening` with no `--target-signal` refuses with the sibling-D2 guidance (declare the friction's
   own recurrence signal; fall back to an explicit `--target-signal undeclared` flag for the
   genuinely-immeasurable diagnostic — deliberate, typed, retro-visible). Completion-gate path
   unchanged (fail-open, D2-A).
3. **Mechanical round-vs-record coverage check.** A lint (new `--lint-interventions` mode or a
   doc-drift-lint rule) parses the current month's hardening-log: every `## Round N` whose Action
   is the `Mechanical fix applied:` form must have `docs/interventions/harden-<YYYY-MM>-rN.md`;
   exemption forms (`No harness change`, `NEEDS_INPUT.md written`, recurrence) are recognized
   mechanically from the round's own `**Intervention record:** none` line so the existing honest
   exemptions keep linting clean. Runnable standalone and at the `--run-end` flush (fail-open
   there, per house posture).
4. **Backfill decision for r1-r3** (pre-contract mechanical rounds): backfill via the D9 manual
   path where a measurable signal exists, or record them explicitly `undeclared` so the coverage
   lint sees a record rather than a hole. Cross-reference: re-baselining the poisoned r14-r21
   records belongs to the split-brain sibling, not here.
5. **Repair r5/r7:** re-declare their targets onto real vocabulary (`event:gate-refusal`
   sub-signals once the efficacy-signal-integrity feature lands, or the closest real event today)
   via the same explicit re-declaration act as D3 of the split-brain sibling — never a silent edit.
6. **Tests + gates:** `test_lazy_core.py` coverage for the vocabulary check (reject/degrade paths),
   the hardening-CLI hard-fail, and the coverage lint (fixture log with a covered round, an exempt
   round, and a hole); full gates; harden-harness SKILL prose updated to state the now-mechanical
   contract (re-project + lint-skills per house rule).

## Decisions

- **D1 — Reject vs flag unknown vocabulary on the CLI:** reject (exit 1). The CLI author is
  interactive and can correct immediately; a warning would reproduce exactly the r5/r7 outcome.
  The completion-gate path keeps fail-open-with-degrade (never blocks a pipeline completion).
- **D2 — Where the coverage check lives:** prefer extending doc-drift-lint (it already owns
  committed-doc coherence) over a new standalone script; if its architecture resists a
  cross-file (log ↔ records dir) rule, a `lazy-state.py --lint-interventions` mode is the
  fallback. Either way the check must be runnable both standalone and from the run-end flush.
- **D3 — Exemption verifiability:** v1 trusts the round's explicit `**Intervention record:**
  none` line as the machine-readable exemption marker (it already exists in every exempt round,
  verified) — the lint enforces PRESENCE of either a record or that marker, not the truth of the
  self-attestation. Auditing exemption truthfulness (did a "no-harness-change" round really ship
  nothing?) needs commit-diff forensics; surface as a retro concern, not a v1 gate.
