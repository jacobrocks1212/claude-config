# Bug-Queue Aging Backpressure — Feature Specification

> The harness bug backlog only accumulates. Inflow has mechanical caps (incident-scan's
> `ENQUEUE_CAP = 2`, the run-end refusal on unacked hardening debt) but outflow has NO forcing
> function: hand-pinned `severity: null` queue entries sort to merged priority 99 — "after every
> feature" — forever, `_SEVERITY_DEFAULT = 99` makes absent severity a permanent tail, and
> Concluded-but-never-fixed investigations pile up (23 on disk as of 2026-07-11). This feature adds
> age-driven backpressure: aged bugs escalate in the merged view (or are drained by a per-N-runs
> quota), hand-pinned deprioritizations expire instead of living forever, and queue age becomes
> visible in `LAZY_QUEUE.md`.

**Status:** Complete
**Priority:** P2
**Last updated:** 2026-07-13
**Source:** repo-exploration proposal session 2026-07-11
**Friction-reduction feature:** yes

**Depends on:**

- friction-kpi-registry — soft — the KPI rows below register two new `sentinel-scan` selectors in
  `kpi-scorecard.py`'s closed `_SOURCES` enum (Phase 3); the registry/lint/scorecard machinery this
  rides on is Complete, so this is a follow-the-precedent edit, not a blocker. (Complete — soft dep
  satisfied.)

---

## Locked Decisions

Research integrated (`RESEARCH_SUMMARY.md` — inline recon of `bug-state.py`'s ordering + the merged
comparator against HEAD at implementation time, 2026-07-13). Per SPEC recommendations:

- **D2 — Expiry on hand-pinned null-severity entries** (`mechanical-internal`): **LOCKED as
  recommended** — Option A. Queue entries gain optional `pinned_at`/`pinned_until`/`pin_reason`
  fields, script-stamped ONLY by the new sanctioned `bug-state.py --pin --id <id> --until <date>
  --reason <text>` mutation (never hand-edited). Past `pinned_until` (or, absent it, past a
  90-day default max pin age from `pinned_at`), the merged view falls back to the SPEC's own
  `**Severity:**` line. Implemented (`lazy_core.pin_is_active`, `bug-state.py::pin_bug_severity`).
- **D3 — Age signal** (`mechanical-internal`): **LOCKED as recommended** — Option A,
  `**Discovered:**` wall-clock age, 7-day quantum per notch. Implemented
  (`lazy_core.age_escalated_rank`).
- **D4 — Queue-age surfacing in `LAZY_QUEUE.md`** (`mechanical-internal`): **LOCKED as
  recommended** — Option A, render the Discovered date + a pin/escalation marker (stable facts,
  not a computed age-in-days). The byte-stability contract is restated as "byte-identical for
  unchanged (state, date)" per the SPEC's own honest wrinkle. Implemented
  (`lazy_core.bug_priority_marker`, `lazy-queue-doc.py::_bug_aging_cell`).
- **D1 — Backpressure mechanism: comparator escalation vs run quota** (`product-behavior`):
  implemented against the recommended Option A (age-escalation in the merged comparator) under the
  operator's park-provisional protocol — **PROVISIONALLY accepted, not ratified**. See
  `NEEDS_INPUT_PROVISIONAL.md`. SPEC Status stays Draft; no `COMPLETED.md` until the operator
  ratifies or redirects.

**V1 scope narrowing (implementation-time, non-redirecting):** age-escalation is **bug-axis only**
— `lazy_core.merged_priority`'s `feature` branch is untouched (feature `tier` has no `**Discovered:**`
analog). A bare `"severity": null` queue entry with **no** `pinned_at` (every entry committed before
this feature shipped) is **byte-identical to before** — `MERGED_PRIORITY_DEFAULT`, no fallback, no
escalation — so shipping this feature does not retroactively re-prioritize any already-committed
queue entry (notably the two Windows-only build-queue bugs the 2026-07-04 pin was protecting from
dispatch on a non-Windows host — Open Question 3, below). Only bugs newly pinned via the sanctioned
`--pin` mutation age out. This is the safe default; migrating the real queue's legacy null-severity
rows to explicit pins (with a host-capability `pin_reason`) is a deliberate follow-up operator action,
not automated here.

## Executive Summary

Every mechanism in the bug pipeline's ordering layer was verified live before drafting:

- **The merged view has no age input.** `lazy_core.merged_priority()` (~line 7770) normalizes
  feature `tier` / bug `severity` to one effective priority; a missing or `null` severity yields
  `MERGED_PRIORITY_DEFAULT = 99` (~line 7766) — sorts last, unconditionally, with no time term.
  `merged_worklist()` (~7801) is pure ordering over that number. `bug-state.py` mirrors it:
  `_SEVERITY_RANK {P0:0, P1:1, P2:2, Low:3}` + `_SEVERITY_DEFAULT = 99` (lines 214–215), and
  autodiscovered dirs sort by `(severity rank, **Discovered:** ascending)` (`_find_open_bug_dirs`).
- **The hand-pin has no expiry.** `docs/bugs/queue.json`'s `_note` documents the arrangement: the
  build-queue/harness bugs were pinned to `severity: null` → merged priority 99 ("AFTER every
  feature") on 2026-07-04, with restore-by-removal as the only exit ("Restore a bug's priority by
  removing its queue entry … or setting an explicit severity here"). Nothing mechanizes that exit.
  The note is itself already stale: the P0 HEAD it names (`skip-mcp-test-frontmatter-unquoted-colon`)
  was fixed and archived, and ALL 11 remaining queue entries are `severity: null` — the entire
  committed bug queue is permanent-tail. Oldest pinned entry: Discovered 2026-06-24 (17 days at
  tail as of 2026-07-11).
- **Concluded is a roach motel.** 23 on-disk bugs sit at `**Status:** Concluded` (investigated,
  root-caused, fix-scoped — never fixed); 12+ of them landed as untracked specs on 2026-07-11 alone
  (the harden-harness spec-first discipline is working, and more were still arriving from a
  concurrent hardening session during authoring), while fix outflow that day was zero.
- **Inflow is capped; outflow is not.** `incident-scan.py` enforces `ENQUEUE_CAP: int = 2` per scan
  (line 65); `--run-end` refuses on unacked deny-ledger hardening debt unless `--ack-unhardened`
  (`lazy_core.py` ~7559–7561). Both are inflow/debt guards. Nothing ever promotes, drains, or
  expires an aged bug.
- **Age is invisible.** `lazy-queue-doc.py`'s bug table renders severity badge (`—` for null),
  curated status, phase progress, and next action (`_badge`/`_inline_summary`, ~240–268) — no age,
  no Discovered date, no pinned marker. The operator cannot see stagnation from `LAZY_QUEUE.md`.

The fix is backpressure on the outflow side, script-owned and deterministic: age-escalation in the
merged comparator and/or an every-Nth-run aged-bug quota, expiry on hand-pinned null-severity
entries, and queue-age surfacing in the queue doc. The `_note` already describes the intended
restore semantics in prose — this feature mechanizes them.

## Design Decisions

### D1. Backpressure mechanism: comparator escalation vs run quota

- **Classification:** `product-behavior (operator decision required)`
- **Question:** What forces an aged bug to actually get worked?
- **Options:**
  - **A — age-escalation in the merged comparator (recommended):** `merged_priority()` gains an age
    term: each age quantum at tail (per D3) bumps effective priority one notch toward 0, capped
    (e.g. never past P1-equivalent rank 1, so a genuine P0 always outranks escalation). Pure
    function of (queue entry, SPEC `**Discovered:**`, today) — deterministic given a date,
    testable with injected `today`, zero orchestrator prose. A pinned-null entry therefore climbs
    back into contention by itself.
  - **B — every-Nth-run aged-bug quota in the merged driver:** the `/lazy-batch` unified driver
    works one aged harness bug every N runs (or N cycles) regardless of merged order. Simple to
    reason about ("one bug per N"), but it lives in SKILL prose + marker counters (a new
    orchestrator obligation of exactly the skippable-prose class `docs/bugs/efficacy-future-check-unenforced-orchestrator-prose/`
    documents), and it needs new run-count state.
  - **C — both:** comparator escalation as the floor, quota as a stronger drain when the backlog
    exceeds a threshold.
- **Recommendation:** A. It is the only shape that stays entirely inside the script-owned ordering
  layer (the house invariant: deterministic state in scripts, never orchestrator hand-arithmetic).
  B/C remain documented vN escalations if measured drain (see KPI rows) proves too slow.

### D2. Expiry on hand-pinned null-severity entries

- **Classification:** `mechanical-internal (recommended-option default)`
- **Question:** How does a 2026-07-04-style deprioritization stop being permanent?
- **Options:**
  - **A — pin metadata + expiry (recommended):** queue entries gain optional `pinned_at`
    (date, script-stamped when severity is nulled) and optional `pinned_until`; past
    `pinned_until` — or past a default max pin age when only `pinned_at` exists — the merged view
    falls back to the SPEC's `**Severity:**` line (which the `_note` already declares as the real
    severity). A sanctioned `bug-state.py` mutation stamps/clears pins — never hand-edits
    (the `reorder_queue` / script-owned-queue.json precedent).
  - **B — expiry via D1 escalation only:** no new fields; the age term simply out-climbs the null
    pin. Fewer moving parts but conflates "deprioritized deliberately" with "absent severity", and
    the pin's intent (host-capability mismatch: PowerShell/Pester bugs untestable off a Windows
    workstation) is lost.
- **Recommendation:** A, with the pin fields also carrying the pin *reason* — the 2026-07-04 pin was
  really a host-capability statement, and `deferred-device-vs-host-capability-loop` taught that
  mis-encoding capability constraints as bare deprioritization causes loops.

### D3. Age signal: Discovered-date wall-clock vs runs-at-tail counter

- **Classification:** `mechanical-internal (recommended-option default)`
- **Options:**
  - **A — `**Discovered:**` wall-clock age (recommended):** already on disk, already parsed
    (`bug-state.py::bug_discovered()`), needs zero new state; quantum = 7 days per notch (capped
    per D1). Deterministic given `today` (tests inject the date — the `kpi-scorecard.py --lint`
    pattern).
  - **B — runs-at-tail counter:** counts actual pipeline runs the bug spent unworked; more faithful
    to "starvation" but requires new durable per-bug state (marker counters are deleted at
    `--run-end` — the exact gap the cycles-per-completion KPI hit).
- **Recommendation:** A now; B only if telemetry-ledger-backed run counts later make it free.

### D4. Queue-age surfacing in `LAZY_QUEUE.md`

- **Classification:** `mechanical-internal (recommended-option default)`
- **Question:** How does age render without breaking `lazy-queue-doc.py`'s byte-stability contract
  (unchanged state ⇒ byte-identical render; no embedded wall-clock — the mobile-queue-control
  operator decision)?
- **Options:**
  - **A — render stable facts, not computed age (recommended):** the bug table gains the
    `**Discovered:**` date and a pin marker (`📌 pinned 2026-07-04` / `⏫ escalated` when the
    effective priority differs from the declared severity). Dates are state, not wall-clock —
    byte-stability holds.
  - **B — render computed age-in-days:** most readable but embeds `today` — every render differs,
    violating the byte-stability contract.
- **Recommendation:** A. Note the honest wrinkle: under D1-A the *escalated* marker is itself a
  function of `today`, so a render CAN legitimately change across days with no state change — the
  contract becomes "byte-identical for unchanged (state, date)", which must be stated in the
  generator's docstring and tests.

## User Experience

- **Nothing new to run.** The merged view (`--next-merged` consumers, `/lazy-batch`'s unified
  driver) simply starts surfacing aged bugs; the operator sees a bug cycle where previously only
  features dispatched.
- **`LAZY_QUEUE.md`** bug rows gain Discovered date + pin/escalation markers (D4-A) — stagnation is
  visible from GitHub mobile.
- **Pinning is explicit:** deprioritizing a bug becomes
  `bug-state.py --pin <id> --until <date> --reason <text>` (D2-A) instead of a hand-edited `null` +
  a prose `_note`; expiry needs no action at all.
- **Failure/empty states:** a bug dir with no parseable `**Discovered:**` gets no escalation
  (sorts as today's `9999-99-99` fallback already does — never a crash, never a fabricated age);
  an unparseable pin field is ignored fail-open with a diagnostic.

## Technical Design

Touch points (all verified against current sources):

| Mechanism | Site | Change |
|-----------|------|--------|
| Effective priority | `user/scripts/lazy_core.py` `merged_priority()` (~7770), `MERGED_PRIORITY_DEFAULT` (~7766) | age term per D1-A/D3-A: `max(floor, base_rank - age_weeks_capped)`; signature gains the already-loaded queue entry's SPEC path or a precomputed age (keep the function pure — caller supplies `today`) |
| Bug-side mirror | `user/scripts/bug-state.py` `_SEVERITY_RANK`/`_SEVERITY_DEFAULT` (214–215), `_find_open_bug_dirs` sort key | same age term so autodiscovered-dir ordering agrees with the merged view (the two are deliberately mirrored today — comment at `lazy_core.py` ~7760) |
| Pin lifecycle | `docs/bugs/queue.json` entries + a `bug-state.py` mutation subcommand | `pinned_at`/`pinned_until`/`pin_reason` fields; expiry = SPEC-severity fallback (D2-A); `_note` rewritten to describe the mechanized contract |
| Rendering | `user/scripts/lazy-queue-doc.py` `_badge()`/`_render_table` (~240–290) | Discovered date column + pin/escalation markers (D4-A), byte-stability contract restated as (state, date)-stable |
| KPI selectors | `user/scripts/kpi-scorecard.py` `_SOURCES["sentinel-scan"]` (~65–92) + `docs/kpi/registry.json` | register `oldest-open-bug-age-days` and `concluded-unfixed-count`; compute = the same `docs/bugs/` scan `_find_open_bug_dirs` does (status + Discovered parse), windowless point-in-time values |

House invariants honored: ordering stays a pure script-owned function (LLM never computes
priorities); queue.json mutations only via sanctioned CLI acts; fail-open on unparseable fields;
no new orchestrator prose obligations in the recommended shape (D1-A); coupled-pair parity — any
`lazy-*` SKILL text touched runs `lazy_parity_audit.py` + re-projection.

## KPI Declaration

Primary KPIs are the two rows below. **Phase 3 shipped** — both `sentinel-scan` selectors
(`oldest-open-bug-age-days`, `concluded-unfixed-count`) are registered in `kpi-scorecard.py`'s
closed `_SOURCES` enum with live compute (`_sel_oldest_open_bug_age_days`,
`_sel_concluded_unfixed_count`), and both rows are promoted into `docs/kpi/registry.json` (fences
flipped `jsonc` → `json` below, matching the promoted rows verbatim). `kpi-scorecard.py --lint` and
`--lint --spec docs/features/bug-queue-aging-backpressure/SPEC.md` both exit 0; the live scorecard
renders both PENDING-BASELINE with current values (13d oldest-open, 5 concluded-unfixed as of
2026-07-13 — down from the 2026-07-11 baselines below, consistent with same-day bug-fix throughput).

Machine-visible declaration — the existing registry row this feature must NOT regress (the quota /
escalation spends pipeline cycles on bugs; success is backlog drain without wrecking pipeline
efficiency):

- kpi: cycles-per-completion

Promoted rows (full D2 schema; baselines hand-measured 2026-07-11 over the committed tree at
`7d49490`, excluding the same-day untracked spec inflow — `provenance: measured`, not re-captured at
Phase-3 implementation time, so the registry's baseline is honestly dated to its ORIGINAL
measurement):

```json
{
  "id": "bug-backlog-oldest-open-age-days",
  "system": "bug-pipeline",
  "title": "Age in days of the oldest open docs/bugs/ item",
  "friction": "Null-severity pins and priority-99 defaults make the bug backlog accumulate-only; the oldest open bug ages without bound because no outflow forcing function exists.",
  "signal": { "source": "sentinel-scan", "selector": "oldest-open-bug-age-days" },
  "unit": "days",
  "direction": "down-is-good",
  "baseline": { "value": 17, "captured_at": "2026-07-11", "window": "1d", "provenance": "measured" },
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "claude-config",
  "notes": "Point-in-time scan of docs/bugs/ (non-_archive dirs whose Status is not Fixed/Won't-fix), age = today - min(**Discovered:**). Baseline: build-queue-orphaned-result-on-wrapper-kill, Discovered 2026-06-24, 17d on 2026-07-11. Dirs without a parseable Discovered are excluded (13 of 24 open dirs on capture day — mostly same-day specs); band declared after the reconcile sweep in docs/bugs/fixed-bugs-unarchived-fsck lands, so the scan denominator is honest."
}
```

```json
{
  "id": "bug-backlog-concluded-unfixed-count",
  "system": "bug-pipeline",
  "title": "Count of docs/bugs/ items at Status: Concluded (investigated, never fixed)",
  "friction": "Investigations conclude with root cause + fix scope and then sit forever; 23 Concluded-but-unfixed specs on capture day while same-day outflow was zero.",
  "signal": { "source": "sentinel-scan", "selector": "concluded-unfixed-count" },
  "unit": "count",
  "direction": "down-is-good",
  "baseline": { "value": 23, "captured_at": "2026-07-11", "window": "1d", "provenance": "measured" },
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "claude-config",
  "notes": "Point-in-time count of non-_archive docs/bugs/ dirs with **Status:** Concluded (11 committed at 7d49490 + 12 same-day untracked at capture; more inflow was arriving during the session). Deliberately counts the untracked inflow — the KPI measures backlog reality, not commit state. Success shape: this number goes DOWN over runs (fix outflow) or at minimum stops being monotonic."
}
```

## Implementation Phases

- **Phase 1 — Age-escalation + severity-default aging (~1 session).** D1-A age term in
  `lazy_core.merged_priority()` + the `bug-state.py` mirror; injected-`today` unit tests in
  `test_lazy_core.py` / bug-state's suite (escalation caps, P0 dominance, no-Discovered fail-open);
  coupled-pair parity audit. Proven done: fixture queue where a 3-week-old null-severity bug
  outranks a tier-2 feature but never a P0.
- **Phase 2 — Pin lifecycle + queue-doc surfacing (~1 session).** `pinned_at`/`pinned_until`/`pin_reason`
  fields + sanctioned pin/unpin subcommand + expiry fallback to SPEC severity (D2-A); rewrite the
  `_note` to the mechanized contract; `lazy-queue-doc.py` Discovered/pin/escalation rendering with
  the (state, date)-stability test (D4-A). Proven done: expired-pin fixture re-sorts by SPEC
  severity; render is byte-identical across two same-day runs on unchanged state.
- **Phase 3 — KPI selectors + registry rows (~0.5 session).** Register `oldest-open-bug-age-days` /
  `concluded-unfixed-count` under `sentinel-scan` in `kpi-scorecard.py` with the docs/bugs-scan
  compute; promote the two drafted rows into `docs/kpi/registry.json` (flip this SPEC's `jsonc`
  fences to `json`); `--lint` green; scorecard renders both with honest values.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Aged bug escalates | Fixture: null-severity bug, Discovered 21d ago, vs tier-2 feature | Bug is merged head; a P0 bug still beats it | `test_lazy_core.py` merged-view tests |
| Escalation is capped | Fixture: 52-week-old Low bug | Effective rank never passes the declared floor | same |
| Pin expiry | Fixture entry `pinned_until` in the past, SPEC `**Severity:** P1` | Merged priority 1, not 99 | bug-state tests |
| No fabricated age | Bug dir without `**Discovered:**` | No escalation, no crash, diagnostic emitted | bug-state tests |
| Queue-doc stability | Two renders, same state, same date | Byte-identical `LAZY_QUEUE.md` | queue-doc test |
| Age visible | Real render over live state | Discovered date + pin marker present on pinned rows | manual `LAZY_QUEUE.md` review |
| KPI rows live | Phase 3 `--lint` + scorecard run | Both rows lint clean and render measured values | `kpi-scorecard.py` |

## Open Questions

- **Escalation floor and quantum (D1-A tuning):** one notch per 7 days capped at rank 1 is the
  starting proposal; confirm against real drain rate after two weeks of runs (the KPI rows are the
  measurement).
- **Does D1-A alone drain Concluded specs?** Escalation surfaces them to the merged head, but a
  Concluded bug still needs `/plan-bug` → fix cycles; if measured drain stalls, revisit D1-C (quota).
- **Interaction with `deferred-device-vs-host-capability-loop` (RESOLVED for v1, see Locked
  Decisions):** pinned PowerShell/Pester bugs escalating on a non-workstation host would loop.
  Resolved at implementation time by the V1 scope narrowing: a bare `"severity": null` entry with
  no `pinned_at` (the CURRENT state of both real Windows-only build-queue bugs) never falls back
  to SPEC severity or ages — byte-identical to today, so the loop risk does not materialize for
  the entries that actually carry it. The risk would resurface ONLY if an operator explicitly
  `--pin`s a genuinely host-gated bug with a `pinned_until` date (the pin's `pin_reason` records
  the host-capability statement, but nothing YET gates escalation on the live host-capability
  registry post-expiry) — flagged as a vN follow-up, not solved here: a future revision should
  either wire the host-capability registry into `pin_is_active`/`merged_priority`, or teach
  `--pin` to accept `--until never` for a genuinely-indefinite host-gated pin.
