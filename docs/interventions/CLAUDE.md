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

## Backfill (D9 — manual opt-in only)

No bulk backfill. To measure an already-shipped change:

```bash
python3 ~/.claude/scripts/lazy-state.py --record-intervention --id <slug> \
  --shipped-commit <sha> --shipped-date <YYYY-MM-DD> \
  --target-signal event:<type> --expected-direction decrease --repo-root .
```

The record is stamped `provenance: backfilled`; a pre-ledger baseline honestly records
`unavailable`.
