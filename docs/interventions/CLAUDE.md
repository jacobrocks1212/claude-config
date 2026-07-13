# docs/interventions/ — the intervention hypothesis ledger

One committed frontmatter-sentinel markdown file per shipped harness change
(`<intervention_id>.md`), recording the hypothesis ("this change moves friction signal X in
direction D"), a baseline **frozen at ship time**, and the post-ship verdict. Feature:
`docs/features/intervention-efficacy-tracking/SPEC.md`.

## Lifecycle (three script-owned moments)

1. **Capture** — written by `lazy_core.record_intervention`, invoked from:
   - the `--apply-pseudo __mark_complete__` / `__mark_fixed__` completion gate (repo-opt-in:
     top-level `"interventions": true` in `docs/features/queue.json`, OR a present
     `## Intervention Hypothesis` SPEC block; otherwise completions are byte-identical and no
     record is written). Fail-open — capture can never fail a completion.
   - the orchestrator-only `--record-intervention` CLI on BOTH state scripts (manual capture,
     `/harden-harness` mechanical-fix rounds via `--pipeline hardening`, and the D9 opt-in
     backfill: `--shipped-commit`/`--shipped-date` stamp `provenance: backfilled`).
2. **Evaluation** — `user/scripts/efficacy-eval.py` (read-only over the telemetry ledger; the
   SOLE post-capture writer of these records). Run-count windows (D5 defaults 20/20/5/±20%,
   per-record overridable): review k is due after `(k+1) × review_after_runs` post-ship runs;
   verdicts CONFIRMED / REFUTED / INCONCLUSIVE append a `## Review <date>` section + update the
   frontmatter atomically. Confounders (other overlapping interventions) are always annotated;
   a same-signal overlap caps the verdict at `INCONCLUSIVE (confounded)`. Invoked once per
   `/lazy-batch(-cloud)` run at the §1c.6 end-of-run flush + on demand; `/lazy-batch-retro`
   Step 6e cites verdicts `--dry-run`.
3. **Consequence** — REFUTED auto-enqueues `reconsider-<id>` through the shipped
   `--enqueue-adhoc --type bug` path, guarded two ways (an existing open/archived
   `docs/bugs/reconsider-<id>` dir; the `reconsideration_enqueued` stamp — once stamped, never
   again). INCONCLUSIVE past 2 reviews sets `escalated: true` (passive needs-triage surfacing,
   never a halt). CONFIRMED closes the hypothesis.

**Do not hand-edit record frontmatter.** Capture and the evaluator are the only writers; both
serialize through `lazy_core._render_intervention_record` (stable field order).

## Record schema (kind: intervention)

`intervention_id` (item slug or `harden-<YYYY-MM>-r<N>`) · `pipeline: feature|bug|hardening` ·
`provenance: gated|manual|backfilled` · `shipped_date` · `shipped_commit` · `commit_set` (v1 =
capture commit) · `target_signal` (`kpi:<system>.<kpi-id>` preferred / `event:<ledger-event-type>`
accepted / `undeclared`) · `expected_direction: decrease|increase` ·
`signal_independence: independent|self-emitted|mixed` (justification in body; consumed by
`anti-overfit-design-gate`) · nested `baseline:` map (`status: frozen|unavailable|not-computable`,
`runs`, `events`, `value` (events/run), `window_start_run`, `window_end_run`, `last_run_id` — the
post-window boundary) · `review_after_runs` / `min_sample` / `band_pct` (per-record D5 overrides) ·
`review_count` · `status: open|confirmed|refuted|inconclusive` · `escalated` ·
`reconsideration_enqueued`.

## The `canary:` sub-map (harness-change-canary-rollback)

A shipped change whose touched-file set intersects the control-surface manifest gains a nested
`canary:` sub-map at capture (an unknown key the serializer appends in insertion order — no
field-order edit). It carries the change into an observation window watched **every run** (more
aggressive than the efficacy review's ~20-run cadence). The watcher —
`efficacy-eval.py --canary` — is the SOLE writer of `canary.*` and reads every signal read-only;
it never mutates an efficacy verdict field, and a clean canary does NOT pre-judge the efficacy
verdict (a change can be non-damaging yet ineffective).

Frozen sub-map fields (written by `lazy_core.record_intervention`; do not hand-edit):

- `opened` — ship date; the window's lower time bound + the 30-day-ceiling anchor.
- `window_runs` — window size in completed runs (default `CANARY_WINDOW_RUNS_DEFAULT` = 10;
  per-record overridable via the hypothesis block's `- canary_window_runs:`).
- `surfaces` — the matched touched files (repo-relative POSIX); the D3 attribution identity set.
- `commit_set` — the change's commit set (the revert target on a trip).
- `pair_scope` — coupled-pair scope: if the commit set touches one half of a parity-guarded pair
  (`lazy-parity-manifest.json` + the root CLAUDE.md pairs table), BOTH halves are listed so a
  revert covers the whole pair and ends with a green `lazy_parity_audit.py`.
- `degraded_revert_note` — a static note when the change is known revert-unsafe (migrated on-disk
  state/schema); `null` otherwise. No `git revert` dry-run machinery in v1.
- `status` — the lifecycle field (below).

Top-level companion field: `canary_revert_enqueued` (the trip date, once stamped — the once-ever
recurrence guard, mirroring `reconsideration_enqueued`).

### Canary lifecycle (`status` transitions — open → terminal, never re-opened)

1. **open** (at capture) — the watcher's wake predicate. Each run boundary it accrues the window
   (next `window_runs` completed runs after ship, 30-day wall-clock ceiling), applies the D2
   tripwire (targeted-signal regression past the KPI band / else ≥25% relative with ≥3 post-ship
   occurrences, OR ≥2 attributable fresh incidents) and D3 surface-based attribution.
2. **tripped** — the tripwire fired: the watcher flags-and-enqueues an evidence-bearing
   `canary-revert-<id>` bug stub (never a silent revert — D4), writes `EVIDENCE.md` into the
   seeded bug dir, and stamps `status: tripped` + `canary_revert_enqueued` (once ever). A tripped
   canary does NOT skip the later efficacy verdict.
3. **closed-clean** — the window matured with no trip: the watcher stamps `status: closed-clean`
   and appends a `## Canary <date>` record-body section (runs observed, signal movement, incidents
   attributed none/list). Monitoring drops back to the normal KPI-registry cadence.
4. **closed-clean (no-data)** — matured with ZERO observable runs (a rarely-run repo hitting the
   30-day ceiling): the same close + section, stamped honestly `(no-data)` rather than a false
   clean bill.

A `tripped` / `closed-clean` / `closed-clean (no-data)` record is never re-woken (the watcher's
wake predicate is `status: open` only). `/lazy-batch-retro` Step 6e cites canary outcomes
(`--canary --dry-run`) alongside the efficacy verdicts; the canary's own **trip-precision** KPI
(`canary-trip-precision`, `docs/kpi/registry.json`) measures the fraction of trips whose revert
item was NOT closed-as-noise.

## Authoring surface — the `## Intervention Hypothesis` SPEC block

A harness-change SPEC declares its hypothesis in one short parseable block
(`lazy_core.parse_intervention_hypothesis`; absent block → the record degrades to
`target_signal: undeclared`, completion is NEVER blocked):

```markdown
## Intervention Hypothesis

- target_signal: event:containment-refusal
- expected_direction: decrease
- signal_independence: independent — trips are counted by the containment hook's deny
  ledger, which this change does not touch
- review_after_runs: 20
```

Optional per-record D5 overrides: `- baseline_runs: N` · `- min_sample: N` · `- band_pct: N`.
`event:<type>` names a `harness-telemetry-ledger` D4-B event (`run-start`, `run-end`,
`cycle-begin`, `cycle-end`, `pseudo-applied`, `dispatch`, `halt`, `sentinel-resolved`,
`gate-refusal`, `containment-refusal`); `kpi:` targets resolve through the
`friction-kpi-registry` (until wired into `efficacy-eval.py::_resolve_target_signal`, a kpi
target reviews as `INCONCLUSIVE (kpi-unresolvable)` — honest, never an error).

### Sub-signal targets (`efficacy-signal-integrity` D1) — `event:<type>/<signature>`

`event:gate-refusal` targets may additionally declare a **sub-signal** —
`event:gate-refusal/<signature>` where `<signature>` matches the emitted event's
`data.gate` value (the closed set every `append_telemetry_event("gate-refusal", data=
{"gate": ...})` call site passes: `gate-coverage`, `unacked-hardening`,
`efficacy-coverage-missing`, `checkpoint-auth`, `apply-pseudo`, `verify-ledger` — v1 scope
is `gate-refusal` only, the one event type with both a verified signature field and a
confounding population). The evaluator (`efficacy-eval.py::_resolve_target_signal` +
`_target_signature` + `_event_matches_target`) counts only ledger events whose `event`
type AND `data.gate` both match. The D6 same-signal confounder cap
(`efficacy-eval.py::_same_signal`) then treats two DIFFERENT sub-signals of the same type
as **disjoint** (each grades its own co-shipped hardening round conclusively), while a
bare, undivided `event:gate-refusal` declaration still **conservatively confounds every
sub-signal of its type** (an undivided declaration cannot rule out overlap).

> **Capture-side seam (not yet closed):** `lazy_core.validate_intervention_target_signal`
> and `lazy_core._intervention_signal_event` do not yet parse the `/<signature>` suffix —
> a sub-signal `target_signal` declared in a SPEC's `## Intervention Hypothesis` block or a
> `--record-intervention --target-signal` CLI call is degraded to `undeclared` at capture
> time (the closed-vocabulary check rejects the unsplit `gate-refusal/<signature>` string).
> Until that STATE-lane seam is closed, a sub-signal record must be captured under a plain
> `event:gate-refusal` (or any valid target) and then have its `target_signal` field
> corrected and its baseline re-frozen via `efficacy-eval.py --rebaseline <id>` (the
> evaluator's own sub-signal-aware re-freeze path) before its sub-signal counting takes
> effect. See `docs/features/efficacy-signal-integrity/`.

### Canary staleness alarm (`efficacy-signal-integrity` D2)

`efficacy-eval.py --canary` additionally computes a **continuous staleness gauge** over
every still-open canary after this run's trips/closes are applied: open count, oldest age
(days since `opened`), and a **projected no-data-close count** — open canaries within
`CANARY_STALENESS_LOOKAHEAD_DAYS` (7) of the 30-day wall-clock ceiling
(`CANARY_WINDOW_DAYS_CEILING`) that have accrued **zero** observable post-ship runs so far.
Surfaced as `staleness` (`{open_count, oldest_age_days, projected_no_data_close_count,
lookahead_days}`) and a one-line `staleness_notify` (`"⚠ N canaries open, oldest Xd, M
will no-data-close within 7d"`, rendered whenever `open_count > 0`) in both the `--json`
payload and the plain-text flush output — reaching the operator **before** the 30-day
ceiling silently launders an unwatched canary into `closed-clean (no-data)`, not after.
`docs/kpi/SCORECARD.md`'s `## Canary health` section (`kpi-scorecard.py::
_canary_health_summary`) mirrors the same three numbers as a committed channel the
operator can read without a live run.

## Backfill (D9 — manual opt-in only)

No bulk backfill. To measure an already-shipped change:

```bash
python3 ~/.claude/scripts/lazy-state.py --record-intervention --id <slug> \
  --shipped-commit <sha> --shipped-date <YYYY-MM-DD> \
  --target-signal event:<type> --expected-direction decrease --repo-root .
```

The record is stamped `provenance: backfilled`; a pre-ledger baseline honestly records
`unavailable`.
