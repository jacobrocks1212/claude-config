# Efficacy Signal Integrity — Feature Specification

> The measurement plane of the self-improving harness, layered on the two 2026-07-11 capture/scope
> bug fixes: (a) sub-signal targets (`event:gate-refusal/<signature>`) so co-shipped hardening
> rounds measure disjoint signals instead of being confounder-capped INCONCLUSIVE by construction;
> (b) a canary staleness alarm so 19 open canaries cannot silently mass-expire into
> `closed-clean (no-data)`; (c) scorecard freshness + per-row signal VANTAGE so NO-DATA
> distinguishes "wrong repo/machine to observe this" from "signal genuinely absent", and the
> scorecard regenerates where its registry actually lives.

**Status:** In-progress
**Priority:** P2
**Last updated:** 2026-07-12
**Source:** repo-exploration proposal session 2026-07-11

> **Finalization note (2026-07-12):** D1/D3 (`mechanical-internal (proposed)`) auto-accepted per
> their SPEC recommendations. D2/D4 (`product-behavior`) provisionally adopted per the overnight
> park-provisional protocol — see `NEEDS_INPUT_PROVISIONAL.md` for the ratify-or-redirect record.
> All three phases are implemented and gated green (see `PHASES.md`); the feature is NOT flipped
> to Complete pending D2/D4 ratification.

**Friction-reduction feature:** yes — it is the measurement plane itself: every KPI below measures
whether the efficacy loop produces usable verdicts instead of structurally-guaranteed INCONCLUSIVEs.

**Depends on:**

- interventions-telemetry-repo-scope-split-brain (docs/bugs/) — hard — no signal-integrity work
  matters while the evaluator cannot see the telemetry that grades the records; this feature's
  KPIs are computed over the verdicts/canary-closes that fix unblocks. (Cross-pipeline dep: the
  dep lives in the bug pipeline, so `--sync-deps` projection into `queue.json` is deferred to
  spec-finalization — do not hand-edit `deps`.)

> Substantive (non-block) cross-links: `docs/bugs/_archive/hardening-intervention-records-unmeasurable-or-missing/`
> (capture-side validation — sub-signal targets only pay off if records are vocabulary-valid);
> `docs/bugs/efficacy-future-check-unenforced-orchestrator-prose/` (the run-end breadcrumb gate,
> shipped `7d49490`, guarantees the flush this feature's signals ride on);
> `docs/features/friction-kpi-registry/` (registry/scorecard substrate this feature extends);
> `docs/features/harness-change-canary-rollback/` + `docs/features/intervention-efficacy-tracking/`
> (the systems whose output this feature makes honest).

---

## Executive Summary

The efficacy loop's two bug fixes make verdicts *possible*; this feature makes them *meaningful*.
Three verified integrity gaps remain even after the bugs are fixed:

1. **Signal granularity.** 6 of the 8 measurable intervention records (r14, r15, r16, r18, r20,
   r21) all target `event:gate-refusal` with overlapping post-ship windows. The D6 confounder rule
   (`efficacy-eval.py:268` `_confounders_for`; same-signal cap at `:~410-425`) then caps every one
   of them at `INCONCLUSIVE (confounded)` **by construction** — co-shipped hardening rounds on the
   same busy signal can never be individually graded. But `gate-refusal` events already carry a
   signature: every emit site attaches `data={"gate": "gate-coverage" | "apply-pseudo" | …}`
   (`lazy-state.py:11618-11622`, `:12282-12285`). Supporting `event:gate-refusal/<signature>`
   sub-signal targets (matched against `data.gate`) lets each round declare the disjoint signal its
   fix actually touches. Today `_intervention_signal_event` (`lazy_core.py:16104`) strips the
   `event:` prefix verbatim, so a sub-signal target would silently match nothing — the resolver,
   the event-count filter, and the D6 same-signal comparison all need the sub-signal seam.
2. **Canary staleness.** 19 canary blocks are open (verified), none has ever closed or tripped
   (zero telemetry visible at their evaluation vantage — the split-brain bug). The 30-day
   wall-clock ceiling (`efficacy-eval.py:883` `_canary_ceiling_matured`) will eventually mature
   ALL of them into `closed-clean (no-data)` (`:1035`) — mass-laundering unwatched harness changes
   into "observed, clean". A staleness alarm (open-canary count + oldest-age + projected
   no-data-close count) must reach the operator BEFORE the ceiling fires, and a no-data close must
   stay visually distinct from an observed clean close everywhere the operator reads.
3. **Scorecard freshness + vantage.** `docs/kpi/SCORECARD.md` is stale: its last commit
   (`b3698b1`, 2026-07-04) predates its own registry's last update (`b3bc241`, the
   `canary-trip-precision` row — absent from the committed scorecard, verified by grep). The
   per-cycle regen is registry-gated to the repo the run happens in ("only when
   `<repo_root>/docs/kpi/registry.json` exists … a no-op in repos without a KPI registry, e.g.
   AlgoBooth today" — `lazy-batch/SKILL.md:~518`), i.e. it never fires where runs actually happen,
   and nothing regenerates it on the claude-config commit path where the registry lives. Registry
   rows carry `repo_scope` but no signal **vantage** — from claude-config, a telemetry-ledger row
   renders NO-DATA whether the signal is absent or simply unobservable from this repo/machine.

Everything stays inside the house invariants the substrate established: script-owned deterministic
values, pure-read rendering, closed enums extended deliberately, fail-open on every pipeline path,
flag-and-render (never auto-act), honest NO-DATA over fabricated zeros.

## Design Decisions

### D1. Sub-signal target syntax and matching

- **Classification:** `mechanical-internal (proposed)`
- `event:<type>/<signature>` where `<signature>` matches the event's `data.gate` (v1: `gate-refusal`
  only — the one event type with both a verified signature field and a confounding population).
  Resolver: `_intervention_signal_event` returns `(type, signature|None)`; counting filters on both;
  D6 same-signal comparison treats `gate-refusal/gate-coverage` and `gate-refusal/apply-pseudo` as
  DISJOINT but treats bare `event:gate-refusal` as overlapping every sub-signal of the same type
  (conservative: an undivided declaration still confounds). The vocabulary check from the
  capture-defects bug validates `<type>` against the closed D4-B set and `<signature>` against the
  emit sites' known `data.gate` values (closed, greppable set — same single-source-of-truth constant).
- Alternative (rejected): free-form `data`-predicate selectors — unbounded, unlintable, invites
  post-hoc target gerrymandering (the anti-overfit concern).

### D2. Canary staleness alarm channel

- **Classification:** `product-behavior (needs operator ratification at finalization)`
- Recommended: a **Registry health / Canary health** section in the scorecard (committed channel,
  reaches the operator with no server, mirrors the `review_by` rot warnings) + a one-line
  `⚠ N canaries open, oldest Xd, M will no-data-close within Yd` in the run-end flush output
  (rides the existing efficacy-eval JSON `notify` surface). Thresholds declared as a registry row
  band, not hardcoded. No new notification machinery; never blocks a run.
- `closed-clean (no-data)` is retained as an honest terminal (the ceiling exists so records don't
  accumulate forever) but is ALWAYS rendered distinctly and counted by the
  `canary-nodata-close-count` signal — a mass no-data expiry becomes a visible KPI breach, not a
  silent laundering.

### D3. Signal vantage on registry rows

- **Classification:** `mechanical-internal (proposed)`
- Optional per-row `vantage: {repo: <name>|any, host: workstation|cloud|any}` (default `any`/`any`,
  fully backward-compatible; `kpi-scorecard.py --lint` validates the closed field values). The
  status engine gains `WRONG-VANTAGE` (rendered instead of `NO-DATA` when the current
  repo-root/host cannot observe the row's signal) — pure classification, no new data access. This
  also gives the split-brain fix a declaration surface: telemetry-ledger rows can say WHICH keyed
  ledger(s) they read.

### D4. Scorecard regeneration point

- **Classification:** `product-behavior (needs operator ratification at finalization)`
- Recommended: regenerate on the **claude-config commit path** — the run-end flush already commits
  `docs/interventions/` updates to claude-config (SKILL §1c.6); the scorecard regen joins that same
  commit step (registry lives there, so the regen is registry-gated TRUE exactly where it should
  be). Byte-stability discipline unchanged. The AlgoBooth-side per-cycle regen prose stays as-is
  (correctly a no-op until AlgoBooth grows a registry).

## User Experience

- Operator reads `docs/kpi/SCORECARD.md`: fresh on every run-end that touches claude-config; new
  **Canary health** block (open count, oldest age, projected no-data closes) and per-row
  `WRONG-VANTAGE` in place of misleading `NO-DATA`.
- Hardening author declares `--target-signal event:gate-refusal/gate-coverage`; capture validates
  it; the evaluator later grades that round WITHOUT being confounded by a sibling round that
  targeted `event:gate-refusal/apply-pseudo`.
- Run-end flush output gains at most two lines (canary staleness warning; scorecard regen note).
  Everything fail-open; no new halt paths.

## Technical Design (delta only)

- `lazy_core.py`: sub-signal resolver + closed signature registry (shared with the capture
  validation from the sibling bug); `efficacy-eval.py`: sub-signal counting + D6 disjointness +
  canary-health computation; `kpi-scorecard.py`: `vantage` lint + `WRONG-VANTAGE` status + Canary
  health section + the three selector computations below (over `docs/interventions/*.md`
  frontmatter — a new pure-read `intervention-records` source, closed-enum extension registered at
  spec-finalization exactly like the `session-log-mining` source precedent); coupled-trio SKILL
  §1c.6 prose for the regen point. Tests for each seam; full gates.

## Implementation Phases

- **Phase 1 — Sub-signal seam** (resolver, counting, D6 disjointness, capture validation hookup,
  re-declared r14-r21 targets post-backfill). Proven done: fixture ledger with two signatures
  grades two same-day records conclusively.
- **Phase 2 — Canary health** (staleness computation, scorecard block, flush notify line,
  distinct no-data rendering + count). Proven done: fixture with an over-age canary renders the
  alarm; a ceiling close renders as no-data, never clean.
- **Phase 3 — Vantage + freshness** (registry `vantage` field + lint + `WRONG-VANTAGE`;
  claude-config commit-path regen; registry rows below registered + baselines captured where
  computable). Proven done: claude-config render shows `WRONG-VANTAGE` for an AlgoBooth-vantage
  fixture row; scorecard commit lands with the flush commit.

## KPI Declaration

Existing registry row this feature directly serves (its canary-integrity work is a precondition
for trip precision ever being computable):

- kpi: canary-trip-precision

Three new rows were drafted below with **pending** baselines (`band: null` — never a fabricated
zero). Their signal source (`intervention-records`, a pure-read scan of committed
`docs/interventions/*.md` frontmatter) and selectors are now REGISTERED in `kpi-scorecard.py`
(`_SOURCES`), per the `canary-trip-precision` / `session-log-mining` precedent — landed this
session (Phase 3). The three rows below are committed as full-schema entries in
`docs/kpi/registry.json` (lint-clean, verified via `kpi-scorecard.py --lint`); the fenced blocks
here are retained verbatim as the historical draft record.

```jsonc
{
  "id": "efficacy-verdicts-produced",
  "system": "efficacy-loop",
  "title": "Conclusive efficacy verdicts produced",
  "friction": "An intervention ledger that never yields a CONFIRMED/REFUTED verdict is measurement theater; every ungraded record is a harness change whose effect is assumed, not observed. Verified 2026-07-11: zero verdicts across 25 records after 22 hardening rounds.",
  "signal": { "source": "intervention-records", "selector": "conclusive-verdict-count" },
  "unit": "count/90d",
  "direction": "up-is-good",
  "baseline": { "value": null, "captured_at": null, "window": "90d", "provenance": "pending" },
  "band": null,
  "review_by": "2026-10-01",
  "notes": "Counts ## Review sections whose verdict is CONFIRMED or REFUTED. Baseline pending until the split-brain fix lands and the first reviews come due."
}
```

```jsonc
{
  "id": "confounded-verdict-ratio",
  "system": "efficacy-loop",
  "title": "Confounded-verdict ratio",
  "friction": "When co-shipped interventions share one target signal, the D6 cap turns every due review into INCONCLUSIVE (confounded) — attribution is impossible by construction, not by data. Verified 2026-07-11: 6 of 8 measurable records share event:gate-refusal with overlapping windows.",
  "signal": { "source": "intervention-records", "selector": "confounded-verdict-ratio" },
  "unit": "percent",
  "direction": "down-is-good",
  "baseline": { "value": null, "captured_at": null, "window": "90d", "provenance": "pending" },
  "band": null,
  "review_by": "2026-10-01",
  "notes": "Share of due reviews capped INCONCLUSIVE (confounded) over all due reviews in the window. The sub-signal seam (Phase 1) is the lever that moves it."
}
```

```jsonc
{
  "id": "canary-closure-latency-p50",
  "system": "harness-canary",
  "title": "Canary closure latency p50",
  "friction": "A canary that cannot close is dead weight that will eventually mass-expire as closed-clean (no-data), laundering unwatched changes as observed. Verified 2026-07-11: 19 canaries open, zero ever closed or tripped.",
  "signal": { "source": "intervention-records", "selector": "canary-closure-latency-p50-days" },
  "unit": "days",
  "direction": "down-is-good",
  "baseline": { "value": null, "captured_at": null, "window": "90d", "provenance": "pending" },
  "band": null,
  "review_by": "2026-10-01",
  "notes": "Median opened-to-closed days over canaries closed in the window, EXCLUDING closed-clean (no-data) ceiling closes (those are counted separately by the canary-health alarm — a no-data close must never improve this KPI)."
}
```

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Sub-signals grade disjointly | Fixture ledger, two records on `gate-refusal/<a>` and `/<b>` | Both conclusive; no confounder cap | evaluator tests |
| Bare target still confounds sub-signals | Record on `event:gate-refusal` + one on a sub-signal | Cap applies (conservative overlap) | evaluator tests |
| Staleness alarm precedes ceiling | Fixture canary older than threshold, younger than 30d | Alarm rendered; no close | scorecard fixture render |
| No-data close never launders | Ceiling-matured fixture canary | `closed-clean (no-data)` distinct + counted | scorecard + record diff |
| WRONG-VANTAGE vs NO-DATA | claude-config render of a workstation-vantage row | `WRONG-VANTAGE`, not `NO-DATA` | scorecard fixture render |
| Scorecard freshness | Registry row added, then run-end flush | SCORECARD.md regen rides the flush commit | git log ordering |

## Open Questions

- **D2/D4 operator ratification** — provisionally adopted per `NEEDS_INPUT_PROVISIONAL.md`
  (2026-07-12); pending ratify-or-redirect before this feature completes. D2 (alarm channel) is
  fully implemented; D4 (regen commit point)'s orchestrator-prose wiring is a reported SKILLS-lane
  cross-lane seam, not yet landed.
- Whether the `intervention-records` source should also feed the visualizer trends page once the
  telemetry trends work lands (rendering add only — the computation stays in `kpi-scorecard.py`).
- **Cross-lane seam (new, 2026-07-12):** `lazy_core.validate_intervention_target_signal` /
  `_intervention_signal_event` do not yet parse `event:<type>/<signature>` — a sub-signal
  `target_signal` degrades to `undeclared` at capture time until that STATE-lane gate is
  extended. Reported for the STATE lane; the evaluation-side seam (this feature's Phase 1) is
  fully landed and tested via the `--rebaseline` workaround.
