# Friction KPI Registry + Scorecards — Feature Specification

> Every friction-reduction system (build-queue, containment hooks, halt handling, and anything
> designed later) declares its canonical KPIs — what friction it exists to reduce, the concrete
> signal sources, direction-of-goodness, baseline, and regression band — in a machine-readable,
> committed registry. A pure-read scorecard renderer computes per-system health from the declared
> signals (telemetry ledger, deny ledger, build-queue results, sentinel scans) and flags
> regressions past the declared band. And `/spec` gains an injected measurability gate: a new
> friction-reduction feature cannot lock its baseline without declaring how its success will be
> measured — un-measurable friction claims become a planning-time halt, not a retro finding.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04 (operator-requested; self-evolution
batch); fleshed out via internal desk research 2026-07-04 (Gemini research skipped by operator
directive — see RESEARCH.md)

**Depends on:**

- harness-telemetry-ledger — hard — KPI rows resolve their signal sources to ledger event streams; the registry schema hinges on the ledger's concrete event vocabulary.

> Substantive (non-block) dependencies are **implemented data contracts**, not sibling specs:
> - `pipeline_visualizer` (pure-read renderer plane; `server.py` `/api/*` + `TtlCache`) — the
>   scorecard's optional browser channel joins it; the renderer discipline ("never re-infers")
>   is inherited either way.
> - `lazy-queue-doc.py` / `LAZY_QUEUE.md` (mobile-queue-control) — the committed-markdown
>   channel precedent: pure-read stdlib generator, no embedded wall-clock, rides the pipeline's
>   existing commit on `main`.
> - The `/spec`-time component-injection mechanism — the skills' `!cat` component injection with
>   per-repo override resolution (`cat .claude/skill-config/<x>.md 2>/dev/null || cat
>   ~/.claude/skills/_components/<x>.md`), precedented by `phases-runtime-validation.md`
>   (planning-time capability audit) and `mcp-coverage-audit.md` (completion-time gate). The
>   measurability gate is a third member of that family.
> - Existing signal sources readable today: `~/.claude/state/build-queue/results/<seq>.json`
>   (`exit_code`, `ended_at`, `hygiene.{result_fidelity,build_fidelity,…}`, `counts`),
>   `lazy-deny-ledger.jsonl` (guard denies + `kind: process-friction`), and the sentinel trail
>   (`BLOCKED.md`/`NEEDS_INPUT.md` + `*_RESOLVED_<date>` renames).

---

## Executive Summary

Friction-reduction systems ship with narrative success criteria and are never measured again. The
build-queue has no wait-time or false-green trend; containment has no runaway-incident rate;
nothing answers "is this system still earning its complexity?" — so a system can silently stop
working (or never have worked) while the harness keeps paying its cost in tokens, latency, and
maintenance. Worse, new systems get designed with no obligation to be measurable at all: the
harness's own gates certify feature *completion* with receipts, but certify harness *efficacy*
with nothing.

This feature is the semantics layer of the self-evolution cluster (ROADMAP: substrate → semantics
→ hypothesis → guardrail). It adds three small, separable pieces: (1) a committed, machine-readable
registry (`docs/kpi/registry.json` in claude-config, per D1) where each friction-reduction system
declares its KPIs — signal source, unit, direction-of-goodness, baseline + capture provenance,
regression band, review-by date; (2) a pure-read, stdlib scorecard renderer
(`user/scripts/kpi-scorecard.py`, sibling of `lazy-queue-doc.py`) that computes current values
from the declared signals and renders per-system health with regression flags — flag-and-render
only, never auto-acting; (3) an injected `/spec`-time gate (sibling of
`phases-runtime-validation.md`) that refuses to lock a friction-reduction feature's baseline until
it declares its KPI rows. Downstream, `intervention-efficacy-tracking` registers hypotheses
against these rows and `harness-change-canary-rollback` consumes the regression flags.

It serves the mission's **effective** criterion (systems must demonstrably work, with evidence,
not narrative) and **best-practice-aligned** (gates that refuse early — at `/spec` — over retros
that catch late). The hard dependency on `harness-telemetry-ledger` is real but partial: several
first-registrant KPIs are computable today from existing artifacts (see the computability table
in Technical Design), so the registry, lint, and scorecard land before the ledger-backed rows do.

## Design Decisions

### D1. Registry residency + granularity

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** One registry file or many, and where does it live? This is the operator's review
  surface for every measurability contract in the harness.
- **Options:**
  - **A — single committed `docs/kpi/registry.json` in claude-config (recommended):** all systems
    in one file; per-row optional `repo_scope` field for signals that only exist in some repos
    (e.g. build-queue is Cognito-scoped). Pros: one `schema_version`, one lint target, one
    `_atomic_write` mutation site, trivially diffable in review — and committed means versioned
    with the harness changes it measures (unlike the untracked state dir). Cons: one file grows
    with every registrant.
  - **B — per-system files `docs/kpi/<system>.json`:** smaller diffs per system; but N files × N
    schema versions, and cross-system rendering must glob and merge.
  - **C — per-repo registries:** matches per-repo `.claude/` layout, but the registrants are
    harness-global systems living in claude-config; scattering their declarations across consumer
    repos inverts ownership.
- **Recommendation:** A — claude-config is "the harness for the autonomous system" and every
  first registrant is a claude-config-owned system; a single file keeps the schema, the lint, and
  the operator's review in one place at negligible size (tens of rows for years). Revisit B only
  if the registry exceeds review-friendly size.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D2. KPI row schema

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What fields must a KPI declaration carry for the scorecard, the `/spec` gate, and
  the downstream efficacy/canary consumers to work against it?
- **Options:**
  - **A — minimal (name + signal + direction):** insufficient — no baseline provenance, no band,
    nothing for the canary sibling to consume.
  - **B — full declaration (recommended):** top-level `{"schema_version": 1, "kpis": [...]}`;
    each row: `id` (kebab-case, `^[a-z0-9][a-z0-9-]*$` like feature ids), `system`, `title`,
    `friction` (one sentence: what friction this measures), `signal` (`{source, selector}` —
    `source` from a closed v1 enum: `telemetry-ledger` | `deny-ledger` | `build-queue-results` |
    `sentinel-scan`), `unit`, `direction` (`down-is-good` | `up-is-good`), `baseline`
    (`{value, captured_at, window, provenance}` — `provenance` ∈ `measured` | `retro-derived` |
    `pending`), `band` (per D4), `review_by` (date — the "is this row still alive?" cadence),
    optional `repo_scope`, optional `notes`.
- **Recommendation:** B — every field is load-bearing for a named consumer: `signal` for the
  scorecard, `direction`/`band`/`baseline` for regression flagging, `review_by` for registry-rot
  detection (a scorecard warning, mirroring the deny ledger's "debt must be visible" posture),
  `provenance` so a retro-derived baseline is honest debt, never silently equal to a measured
  one (the `backfilled-unverified` receipt precedent). The `source` enum is closed like
  `_HOST_CAPABILITY_REGISTRY` — an unknown source is a lint error, not a silent no-data.
- **Resolution:** Auto-accepted B; internal schema shape — the operator-visible choices it feeds
  (bands, channel, residency) are decided in D1/D4/D5.

### D3. Scorecard computation: pure-read stdlib script; the only registry mutations are explicit CLI acts

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Who computes KPI values, and who is allowed to write the registry?
- **Options:**
  - **A — `user/scripts/kpi-scorecard.py` (recommended):** stdlib-only sibling of
    `lazy-queue-doc.py`. Read paths: registry + the four signal sources → current windowed
    values → rendered scorecard (`--stdout` supported). Write paths, each explicit and
    `_atomic_write`-backed: `--capture-baseline <kpi-id>` (stamps `baseline` from the current
    window, `provenance: measured`) and nothing else; `--lint` validates schema, id regex,
    closed source enum, band sanity (warn/breach ordered per `direction`), and flags rows past
    `review_by`. LLM hand-edits of computed fields are out of contract — the same "script-owned,
    never orchestrator hand-edit" rule as `queue.json` (`reorder_queue` precedent).
  - **B — computation inside `pipeline_visualizer`:** couples the registry's committed-markdown
    channel (D5) to a running server; the generator must stay a pure function runnable anywhere.
- **Recommendation:** A — matches the house split exactly (deterministic state in scripts;
  renderers pure-read; mutations explicit CLI primitives). The visualizer can *call* the same
  module later without owning it.
- **Resolution:** Auto-accepted A; helper placement and write-discipline, invisible to the
  operator beyond the CLI surface documented in User Experience.

### D4. Regression-band semantics

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** What does "regression" mean mechanically? This defines when the operator gets a
  flag and when the future canary sibling fires — the core alerting semantics.
- **Options:**
  - **A — static declared bands (recommended):** each row declares `band: {warn, breach}` as
    absolute values in the row's `unit` (or `null` while baseline is `pending`). Status is a
    pure comparison honoring `direction`: OK / WARN / BREACH / NO-DATA / PENDING-BASELINE. Pros:
    deterministic, diffable, arguable in review; zero statistics machinery; a band change is a
    visible commit (which the `anti-overfit-design-gate` sibling can later audit for
    gate-weakening). Cons: bands need manual recalibration as systems evolve — surfaced by
    `review_by`.
  - **B — relative-to-baseline bands (`warn_pct`/`breach_pct`):** auto-scales, but a silently
    drifting baseline re-centers the alarm — the tautology risk the cluster exists to prevent.
  - **C — rolling statistical bands (mean ± k·σ over a trailing window):** self-calibrating, but
    a slow regression walks the band with it, and stdlib-only SPC over sparse, bursty run data
    is noise dressed as rigor.
- **Recommendation:** A — sparse event volumes (a handful of batch runs per week) cannot support
  statistical bands honestly; static declared thresholds with a mandatory review cadence are the
  SLO-style contract that stays auditable. B/C remain documented vN paths requiring only a `band`
  sub-schema addition.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D5. Scorecard rendering channel

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** Where does the operator read per-system health and regression flags?
- **Options:**
  - **A — committed `docs/kpi/SCORECARD.md` in claude-config (recommended):** rendered by
    `kpi-scorecard.py`, regenerated at run boundaries (the orchestrator's run-end commit, the
    `LAZY_QUEUE.md` ride-the-commit precedent) and on demand. No embedded generation wall-clock
    (freshness = git commit time, per the mobile-queue-control operator decision); values are
    windowed + rounded so an unchanged-data regen is byte-identical. Pros: readable on GitHub
    mobile; regression flags reach the operator with no server running; versioned history of
    health for free. Cons: values change across runs, so run-end commits legitimately carry a
    scorecard diff (honest change, one diff per run — not per-cycle noise).
  - **B — `pipeline_visualizer` page only:** richer trends (the telemetry feature's trends page
    is the natural host), but flags are invisible unless the server is up — regressions must not
    require opting in to be seen.
  - **C — both from v1.**
- **Recommendation:** A for v1, with C as the natural follow-up once
  `harness-telemetry-ledger`'s trends page exists (the scorecard module exposes its computation
  as importable functions so the visualizer tab is a rendering add, not a second computer).
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D6. How the `/spec` gate detects a "friction-reduction feature"

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** The measurability gate must know which SPECs it applies to. Misclassification in
  either direction is operator-visible: false positives burden ordinary features with KPI
  ceremony; false negatives let un-measurable friction claims through.
- **Options:**
  - **A — self-declaration + prompted classification (recommended):** the injected component
    instructs `/spec` to classify every feature at Phase 1/Phase 3 (batch mode) — "is reducing
    harness/process friction part of this feature's stated purpose?" — and to record the verdict
    as a mandatory line in the SPEC (`**Friction-reduction feature:** yes|no`). `yes` ⇒ a
    `## KPI Declaration` section is required before finalization (existing registry row ids
    and/or fully-schema'd new-row drafts). Under `--batch`, the classification lands in the
    Decision-Classification Ledger, so the existing Step 1d.5 input-audit subagent
    cross-checks it — a `no` on a SPEC whose Problem section claims efficiency/friction wins is
    auditable, not silent. Pros: deterministic downstream (the gate checks a declared line, the
    way `--gate-coverage` checks the declared `## Locked Decisions` surface); the classification
    itself stays a reviewed judgment. Cons: relies on the classifier prompt + audit, not pure
    mechanics.
  - **B — heuristic keyword scan only:** a lint greps Problem/Summary for friction vocabulary
    ("friction", "wasted cycles", "retry", "efficiency") and demands the section on a hit.
    Mechanical but brittle in both directions; wording games defeat it silently.
  - **C — operator tags `queue.json` entries (`"friction": true`):** unambiguous but manual, and
    absent for on-disk autodiscovered features.
- **Recommendation:** A, with B's keyword scan folded in as a *non-blocking* cross-check inside
  the same component (a keyword hit + a `no` declaration ⇒ the component instructs surfacing the
  contradiction in the NEEDS_INPUT round rather than silently proceeding). This mirrors how the
  harness treats other declared surfaces: declaration is canonical, lint catches drift.
- **Resolution:** OPEN — recommendation is A (+B as advisory cross-check); awaiting operator
  confirmation.

### D7. Gate enforcement mechanics: injected component, refuse-to-finalize, deterministic lint backstop

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Given D6's detection, how is the gate enforced? (The seed constraint is fixed:
  a friction-reduction feature "cannot lock its baseline without declaring how its success will
  be measured" — enforcement strength is not up for redesign, only its mechanics.)
- **Options:**
  - **A — new component `_components/spec-friction-kpi-gate.md` injected into `/spec`
    (recommended):** injected with the standard per-repo override form
    (`cat .claude/skill-config/spec-friction-kpi-gate.md 2>/dev/null || cat
    ~/.claude/skills/_components/spec-friction-kpi-gate.md`), executing at the Phase 3
    finalization checkpoint alongside the existing dep-block validation (which already models
    "fail ⇒ surface and STOP; do not write SPEC.md"). A friction-reduction feature with no valid
    `## KPI Declaration` is treated as an unresolved product-behavior decision: NEEDS_INPUT round
    under `--batch`, refuse-to-finalize interactively — a planning-time halt, never a retro
    finding. Backstop: `kpi-scorecard.py --lint --spec <path>` deterministically validates a
    declaration (row ids resolve to the registry; drafted rows schema-valid), so the prose gate
    has a mechanical check to shell — the same prose-gate-points-at-subcommand promotion path
    `mcp-coverage-audit.md` → `--gate-coverage` established.
  - **B — a state-script step (new `lazy-state.py` gate):** stronger, but the gate's inputs are
    SPEC semantics mid-`/spec`, before the state machine re-probes; the injection point is where
    baseline-lock actually happens.
- **Recommendation:** A — reuses the proven two-layer pattern (prose gate at the authoring
  moment + deterministic validator to shell), costs one component + one lint mode, and follows
  `phases-runtime-validation.md`'s precedent of auditing at planning time what used to fail at
  pipeline end. Re-project + `lint-skills.py` after the skill edit, per house rule.
- **Resolution:** Auto-accepted A; enforcement mechanics implementing the seed's fixed
  constraint — the operator-facing choices live in D6.

### D8. First registrants + baseline capture policy

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Which systems get rows in v1 and how are their baselines captured? (The seed
  fixes the set: build-queue — wait time, false-green rate, raw-invocation deny recurrence;
  containment — runaway trips; halt handling — halt dwell; "retroactively baselined where
  history allows.")
- **Options:**
  - **A — seed set as declared, with per-row honesty about signal availability (recommended):**
    register all six rows now; rows whose signal exists today get `baseline.provenance:
    retro-derived` where history allows (build-queue `results/<seq>.json` archives, deny-ledger
    history) or `measured` after a capture window; rows needing telemetry-ledger events carry
    `provenance: pending` + `signal.source: telemetry-ledger` and render PENDING until the
    upstream lands (never a fabricated zero).
  - **B — register only computable-today rows:** a smaller honest registry, but it erases the
    seed's declared scope and hides the ledger dependency instead of declaring it.
- **Recommendation:** A — the registry's whole point is that a declared-but-not-yet-measurable
  KPI is *visible* debt; option B would re-create the "unmeasured system" problem inside the
  measurement system. The concrete computability analysis is in Technical Design.
- **Resolution:** Auto-accepted A; the registrant set is an operator-set seed constraint — this
  decision only implements its capture mechanics.

## User Experience

- **Reading health (D5 recommendation):** open `docs/kpi/SCORECARD.md` (GitHub mobile renders
  it, like `LAZY_QUEUE.md`):

  ```
  # Friction KPI Scorecard

  ## build-queue
  | KPI | current (30d) | baseline | band (warn/breach) | status |
  |-----|---------------|----------|--------------------|--------|
  | false-green build rate | 0.7% | 1.9% (retro-derived 2026-07) | 3% / 6% | OK ▼ |
  | raw-invocation deny recurrence | 4/30d | 11/30d | 8 / 15 | OK ▼ |
  | queue wait time p50 | — | pending | — | PENDING-SIGNAL |

  ## Regressions
  - (none)  — or —  ⚠ containment/runaway-trip-rate BREACH: 5/30d vs band 3 (baseline 1)

  ## Registry health
  - ⚠ halt-handling/halt-dwell-p50 past review_by 2026-09-01
  ```

- **CLI:**

  ```bash
  python3 user/scripts/kpi-scorecard.py --repo-root . --stdout      # render without writing
  python3 user/scripts/kpi-scorecard.py --repo-root .               # write docs/kpi/SCORECARD.md
  python3 user/scripts/kpi-scorecard.py --lint                      # registry schema + rot check
  python3 user/scripts/kpi-scorecard.py --capture-baseline build-queue-false-green-rate
  ```

- **Authoring a new friction-reduction feature:** `/spec` (batch or interactive) classifies the
  feature (D6); on `yes`, the SPEC must carry a `## KPI Declaration` section naming registry row
  ids or drafting new rows. Missing/invalid declaration under `--batch` ⇒ a `NEEDS_INPUT.md`
  Decision Context entry ("this feature claims friction reduction — how will success be
  measured?") that the orchestrator's AskUserQuestion flow surfaces; interactively ⇒ the
  finalization checkpoint refuses, naming the missing declaration. Ordinary features see one
  classification line and nothing else.
- **On failure/empty states:** an unreadable signal source renders NO-DATA (with the read error
  in a footnote), never a zero; a `pending` baseline renders PENDING-BASELINE; scorecard
  generation failure never blocks any pipeline op (it is invoked at run boundaries, fail-open,
  like the queue-doc generator).

## Technical Design

```
docs/kpi/registry.json  (committed; schema_version; the ONLY declaration surface)
        │ read                                   read │
        ▼                                             ▼
 kpi-scorecard.py (stdlib, pure read + 2 explicit    /spec Phase 3 finalization
 CLI writes: --capture-baseline, SCORECARD.md)        └─ injected _components/spec-friction-
        │ reads declared signals                         kpi-gate.md (per-repo override form)
        ├─ telemetry-ledger  → lazy-telemetry.jsonl      shells: kpi-scorecard.py --lint --spec
        ├─ deny-ledger       → lazy-deny-ledger.jsonl    fail ⇒ NEEDS_INPUT / refuse-to-finalize
        ├─ build-queue-results → ~/.claude/state/build-queue/results/<seq>.json
        └─ sentinel-scan     → docs/{features,bugs}/**/{BLOCKED,NEEDS_INPUT}*, *_RESOLVED_*
        ▼
 docs/kpi/SCORECARD.md (committed at run boundaries; no embedded wall-clock)
        ▼
 future consumers: intervention-efficacy-tracking (hypotheses against rows),
 harness-change-canary-rollback (consumes regression flags — flag-and-enqueue, never auto-act)
```

**Signal computability today vs needs-ledger** (drives Phase ordering; D8):

| KPI row | System | Computable today from | Needs from `harness-telemetry-ledger` |
|---------|--------|-----------------------|----------------------------------------|
| false-green build rate | build-queue | `results/<seq>.json` `hygiene.build_fidelity != "verified"` / `result_fidelity` | — |
| queue wait time | build-queue | not yet — `results/<seq>.json` records `seq`/`exit_code`/`ended_at` but no queued-at/started-at pair (estimated — verify exact fields during Phase 2; may need a runner timestamp add) | — |
| raw-invocation deny recurrence | build-queue | not recorded — `build-queue-enforce.sh` denies are not ledgered today; needs a best-effort hook-side append (fail-OPEN preserved) | — |
| runaway/containment trip rate | containment | `lazy-deny-ledger.jsonl` (guard denies + `kind: process-friction`) | — |
| halt dwell time | halt handling | date-granularity only, via `*_RESOLVED_<date>` sentinel renames | `halt` + `sentinel-resolved` events (D4-B vocabulary) |
| cycles-per-completion | pipeline efficiency | nothing durable — marker counters are deleted at `--run-end` | `run-*`/`cycle-*`/`pseudo-applied` events |

- **Registry:** `docs/kpi/registry.json` per D1/D2; committed, so ordinary git review is the
  change-control surface; all mutations via `kpi-scorecard.py` write paths using
  `lazy_core._atomic_write` semantics (stdlib reimplementation if importing `lazy_core` from a
  docs-tool is undesirable — helper placement decided at implementation; the atomic-replace
  contract is what's binding).
- **Renderer:** pure function of (registry, signal sources, window); byte-stable for unchanged
  inputs (rounding + windowing defined in code, no wall-clock embed); `--repo-root`-addressable;
  never re-infers pipeline state (sentinel-scan reads files, it does not re-derive state-machine
  verdicts — the `lazy-queue-doc.py` discipline).
- **Gate component:** `user/skills/_components/spec-friction-kpi-gate.md`, injected into
  `user/skills/spec/SKILL.md` at the Phase 3 finalization checkpoint (beside the dep-block
  hard checkpoint) and referenced from Phase 1's batch contract for the classification line;
  after editing, re-project (`project-skills.py`) + `lint-skills.py`, per house rule. The
  component shells the deterministic validator (`--lint --spec <path>`), mirroring how
  `mcp-coverage-audit.md` points at `--gate-coverage`.
- **Run-boundary regeneration:** the orchestrator invokes the renderer at the same run-end
  commit point that regenerates `LAZY_QUEUE.md` (claude-config scope; never on the state-script
  compute path, fail-open).
- **House invariants honored:** script-owned deterministic values (an LLM never computes or
  edits a KPI number); pure-read rendering; atomic registry writes; fail-OPEN for anything
  touching hooks or pipeline ops; receipt-style honesty for provenance (`retro-derived` /
  `pending` never masquerade as `measured`); stdlib-only Python; gates that refuse early
  (planning-time) over reviews that catch late.

## Implementation Phases

- **Phase 1 — Registry + lint (~1 session).** `docs/kpi/registry.json` seeded with the D8 rows
  (honest `provenance`/`pending` markers); `kpi-scorecard.py --lint` (schema, id regex, closed
  source enum, band ordering, `review_by` rot); pytest `test_kpi_scorecard.py`. Proven done:
  lint green on the seeded registry, red on each fixture violation.
- **Phase 2 — Scorecard over computable-today signals (~1–2 sessions).** Renderer for
  `deny-ledger`, `build-queue-results`, `sentinel-scan` sources; `SCORECARD.md` +`--stdout`;
  status semantics per D4 resolution; NO-DATA/PENDING honesty; byte-stability test; verify the
  build-queue wait-time field situation and either compute it or leave the row PENDING-SIGNAL
  with a documented runner follow-up. Proven done: fixture-driven value checks + a real render
  over live state.
- **Phase 3 — Ledger-backed rows + regression flags (~1 session; after
  harness-telemetry-ledger Phase 2 lands).** `telemetry-ledger` source (halt dwell,
  cycles-per-completion); Regressions section; run-boundary regeneration wired into the
  orchestrator commit step. Proven done: fixture ledger produces expected values; a
  band-crossing fixture renders a BREACH flag.
- **Phase 4 — `/spec` measurability gate + baselines (~1 session).** Gate component + `/spec`
  injection + projection/lint; `--lint --spec` validator mode; `--capture-baseline` +
  retro-derived baseline capture for rows with history. Proven done: a fixture friction-SPEC
  without a declaration halts at finalization; an ordinary SPEC passes untouched; captured
  baselines carry correct provenance.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Registry lint catches violations | Malformed row (bad id / unknown source / inverted band) | `--lint` exit non-zero naming the row + field | `test_kpi_scorecard.py` |
| Scorecard values correct | Fixture signal files with known contents | Rendered values match hand-computed ones | `test_kpi_scorecard.py` |
| No fabricated data | Missing/unreadable signal source; `pending` baseline | NO-DATA / PENDING-BASELINE rendered, never 0 | fixture render |
| Regression flagging | Fixture crossing `warn` then `breach` honoring `direction` | WARN then BREACH in the Regressions section | fixture render |
| Byte-stable regen | Re-render with unchanged inputs | Byte-identical SCORECARD.md (no wall-clock diff) | diff successive renders |
| Registry rot visible | Row past `review_by` | Registry-health warning in scorecard + `--lint` | fixture render |
| Gate halts un-measurable friction claims | `/spec --batch` on a fixture friction-reduction SPEC with no KPI declaration | NEEDS_INPUT.md Decision Context entry (batch) / refusal (interactive); SPEC not finalized | manual `/spec` run + projected-skill review |
| Gate no-ops ordinary features | `/spec` on a non-friction SPEC | Classification line only; no declaration demanded | manual `/spec` run |
| Baseline provenance honest | `--capture-baseline` vs retro-derived seed | `provenance` field distinguishes `measured`/`retro-derived`/`pending` | registry diff |

## Open Questions

- **D1 — registry residency + granularity:** single `docs/kpi/registry.json` in claude-config vs
  per-system files vs per-repo registries. Recommendation: single committed file with per-row
  `repo_scope`.
- **D4 — regression-band semantics:** static declared warn/breach bands + review cadence vs
  relative-to-baseline percentages vs rolling statistical bands. Recommendation: static declared
  bands (SLO-style; honest at this data volume; band changes are auditable commits).
- **D5 — scorecard channel:** committed `docs/kpi/SCORECARD.md` (mobile-readable, no server) vs
  visualizer page vs both. Recommendation: committed markdown in v1; visualizer tab follows the
  telemetry trends page.
- **D6 — friction-feature detection for the `/spec` gate:** self-declaration with prompted
  classification (+ advisory keyword cross-check) vs heuristic-only vs queue.json tags.
  Recommendation: self-declaration + advisory cross-check, audited by the existing
  input-audit subagent.
- **Deferred empirical checks (implementation, not decisions):** whether `results/<seq>.json`
  (or the runner) can supply queued-at/started-at for the wait-time KPI (Phase 2); the
  best-effort deny-append from `build-queue-enforce.sh` for deny-recurrence (fail-OPEN
  preserved; Phase 2); how far back deny-ledger/build-results history supports retro-derived
  baselines (Phase 4).

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: SRE SLI/SLO band practice for D4; the
  `phases-runtime-validation.md` / `mcp-coverage-audit.md` two-layer gate pattern for D6/D7.
- `docs/features/harness-telemetry-ledger/SPEC.md` — the hard upstream; its D4 event vocabulary
  bounds this registry's `telemetry-ledger` selectors.
- `docs/features/mobile-queue-control/SPEC.md` + `user/scripts/lazy-queue-doc.py` — the
  committed-markdown channel and byte-stability discipline (D5).
- `docs/features/ROADMAP.md` "Self-evolution cluster" — the semantics-layer role, and the
  flag-and-enqueue (never auto-act) guardrail inherited from the canary sibling's charter.
