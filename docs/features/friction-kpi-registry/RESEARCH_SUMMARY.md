---
kind: research-summary
feature_id: friction-kpi-registry
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — friction-kpi-registry

Codebase survey verifying every surface the SPEC names, performed against the lane base
(post-`harness-telemetry-ledger`). One SPEC assumption drifted (regen commit point — see
"Assumptions that proved wrong/drifted"); everything else verified.

## Verified surfaces

### Telemetry ledger (hard upstream — LANDED on this base)

- `user/scripts/lazy_core.py` — `append_telemetry_event` (~L13248), `read_telemetry_events`
  (~L13308), `flush_cloud_telemetry_segment` (~L13367), `_TELEMETRY_LEDGER_FILENAME =
  "lazy-telemetry.jsonl"` (~L13168), rotation `.1`–`.4` (`_TELEMETRY_ROTATED_SEGMENTS = 4`),
  `TELEMETRY_HALT_TERMINAL_REASONS` (~L13175).
- **D4-B event vocabulary confirmed against live emit sites** (21 `append_telemetry_event`
  call sites across `lazy-state.py` / `bug-state.py` / `lazy_core.py`): `run-start`, `run-end`,
  `cycle-begin`, `cycle-end`, `pseudo-applied`, `dispatch`, `halt`, `sentinel-resolved`,
  `gate-refusal`, `containment-refusal`. KPI `telemetry-ledger` selectors bind to exactly these
  names.
- Event envelope: `{"v":1, "ts": <epoch float>, "run_id": <marker started_at>, "pipeline",
  "event", "item_id", "data":{…}}`. `halt` carries `data.terminal_reason`; `cycle-begin`
  carries `data.kind` (`real`/`meta`); `pseudo-applied` carries `data.pseudo`.
- `user/scripts/pipeline_visualizer/trends.py` — pure-read aggregation ALREADY implements the
  three ledger-backed KPI computations this feature needs: `halt_dwell` (halt →
  next same-item `sentinel-resolved` pairing), `cycles_per_completion` (`cycle-begin` vs
  `pseudo-applied` with `data.pseudo ∈ {__mark_complete__, __mark_fixed__}`),
  `refusal_counts` (`containment-refusal` count). `load_events(repo_root)` merges the state-dir
  ledger + committed `docs/telemetry/cloud/*.jsonl` segments with dedupe. **Design consequence:**
  `kpi-scorecard.py` imports and reuses these functions (the D5 "importable computation"
  intent, inverted — the scorecard consumes trends rather than re-implementing).

### Deny ledger

- `lazy_core._DENY_LEDGER_FILENAME = "lazy-deny-ledger.jsonl"` (L6447);
  `read_deny_ledger()` (L13088) — tolerant JSONL reader, per-repo keyed state dir.
- Entry shapes verified: guard denies `{ts, tool_use_id, denied_sha12, reason_head (≤200),
  prompt_head (≤200), acked}` (`append_deny_ledger_entry`, L12633); process-friction entries
  `{ts, kind: "process-friction", …}` (~L12703–12727). `trends.refusal_counts` partitions
  guard-deny / process-friction / auto-readmit as the house precedent.
- **`build-queue-enforce.sh` denies are NOT ledgered today** (SPEC computability table
  confirmed): the raw-invocation deny-recurrence selector filters `reason_head` for the
  build-queue signature and will read 0-recorded until the workstation-deferred hook-side
  append lands. The registry row carries `provenance: pending` + a notes entry; the deny-ledger
  FILE being absent in this container renders NO-DATA (never a fabricated zero).

### Build-queue results (read-only survey of the .ps1s — NOT modified, per operator direction)

- `results/<seq>.json` fields confirmed (`build-queue-runner.ps1` L19/L246–254,
  `build-queue.ps1` L432–443): `seq`, `exit_code`, `ended_at` (ISO-8601 `(Get-Date).ToString('o')`),
  `hygiene.build_fidelity ∈ {log-failure-override, no-output, verified, n/a}`,
  `hygiene.result_fidelity`, test `counts`.
- **False-green rate is computable**: flagged = `build_fidelity ∈ {log-failure-override,
  no-output}` over records whose `build_fidelity` is present and not `n/a`.
- **Queue wait time is NOT computable from results/<seq>.json** (SPEC "estimated — verify
  during Phase 2" resolved: `started_at` exists only in the transient `active.lock`, never in
  the persisted result). The wait-time row stays honest-pending with the runner timestamp add
  recorded as a workstation follow-up; the selector returns no-data with a footnote.
- Residency: `~/.claude/state/build-queue/` is MACHINE-GLOBAL (not per-repo keyed). Absent in
  this container → build-queue rows render NO-DATA here by design.

### Sentinel trail

- `*_RESOLVED_<date>` renames via `--neutralize-sentinel`; `BLOCKED.md` / `NEEDS_INPUT.md`
  canonical names enforced by `block-noncanonical-blocker-write.sh`. Date-granularity only —
  which is why halt-dwell binds to the telemetry `halt`/`sentinel-resolved` events instead
  (second-granularity), exactly as the SPEC's computability table planned. The `sentinel-scan`
  source is still implemented (closed-enum member) with an `open-halt-count` selector.

### Committed-markdown channel precedent

- `user/scripts/lazy-queue-doc.py` (mobile-queue-control): pure `render_doc()` function, no
  embedded wall-clock, `--repo-root`/`--stdout`, `_SCRIPTS_DIR`-on-`sys.path` import of the
  `pipeline_visualizer` package, dash-named module loaded in tests via `importlib.util`
  (`test_lazy_queue_doc.py`). `kpi-scorecard.py` mirrors all of this.

### Gate-injection family

- `/spec` SKILL.md (`user/skills/spec/SKILL.md`): Phase 3 finalization checkpoint is **Step 8
  (Depends-on Finalization Checkpoint, BLOCKING)** at ~L582 — models "fail ⇒ surface and STOP;
  do not write SPEC.md". The per-repo override injection form is used at L18/L181/L345/L580.
  The Phase 1 `--batch` contract (L57–75) + Decision-Classification Ledger (L107) +
  Step 1d.5 input-audit are all present as D6 assumed.
- `mcp-coverage-audit.md` → `--gate-coverage` confirms the prose-gate-shells-subcommand
  promotion path D7 reuses (`kpi-scorecard.py --lint --spec <path>`).

### Run-boundary regeneration wiring (drift found)

- The `LAZY_QUEUE.md` regen precedent is wired at the **per-cycle commit point** (a blockquote
  in `user/skills/lazy-batch/SKILL.md` before Step 1c.5, ~L491, + a bullet in claude-config's
  `.claude/skill-config/commit-policy.md`), NOT a run-end-only commit. It is NOT mirrored into
  `/lazy-batch-cloud` (no `LAZY_QUEUE` reference exists there; the workstation blockquote
  documents the AlgoBooth/cloud handling inline). The scorecard regen joins the SAME blockquote
  + commit-policy bullet, and this feature ADDS the coupled-pair record (a "Differences from
  `/lazy-batch`" table row) that the queue-doc wiring omitted.

## Integration points (implementation map)

| Piece | Integrates with |
|-------|-----------------|
| `docs/kpi/registry.json` | committed; read by `kpi-scorecard.py` + the `/spec` gate validator |
| `user/scripts/kpi-scorecard.py` | imports `pipeline_visualizer.trends` (ledger math) + `lazy_core` (`read_deny_ledger`, `claude_state_dir`, `set_active_repo_root`, `_atomic_write`); build-queue dir read directly (env-overridable for hermetic tests) |
| `docs/kpi/SCORECARD.md` | committed at the per-cycle commit step beside `LAZY_QUEUE.md` |
| `user/skills/_components/spec-friction-kpi-gate.md` | injected into `/spec` Phase 3 (new Step 8.5) with per-repo override form; referenced from the Phase 1 `--batch` contract |
| `user/skills/lazy-batch/SKILL.md` + `.claude/skill-config/commit-policy.md` + `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | regen wiring + coupled-pair divergence row |
| `test_kpi_scorecard.py` | pytest, hermetic fixtures (`LAZY_STATE_DIR`, temp registry/build-queue dirs) |

## SPEC assumptions that proved wrong / drifted

1. **"Run-end commit" regen point** — the actual `LAZY_QUEUE.md` precedent regenerates at the
   *per-cycle* commit point (each cycle's commit on `main`), which subsumes the run boundary.
   The scorecard is wired at the same per-cycle point (operator-locked "same orchestrator
   commit step that regenerates LAZY_QUEUE.md"). Byte-stability makes the extra regens free.
2. **Halt-dwell via sentinel-scan** — superseded at implementation: the telemetry ledger landed
   first, so the halt-dwell row binds `telemetry-ledger`/`halt`+`sentinel-resolved` directly
   (second-granularity) instead of the date-granularity `*_RESOLVED_<date>` fallback.
3. Everything else (schema surfaces, deny-ledger shapes, `results/<seq>.json` fields, injection
   points) verified as specified.
