---
kind: implemented
feature_id: friction-kpi-registry
date: 2026-07-12
provenance: operator-directed-interactive
derivation: message-grep
commits: [72e9c5bd, a982af72, b56e8431, b3698b1d, dde89eac, fdaee97d, 92d7ee12, 6f43d0eb,
  b5a1ef69, 075756f3, 6af45a56, c9a0e506, 303989cb]
decisions: [D1, D2, D3, D4, D5, D6, D7, D8]
---

# Implementation Ledger

**What shipped:** A committed, machine-readable KPI registry (`docs/kpi/registry.json`) where
every friction-reduction system in the harness declares its signal source, unit,
direction-of-goodness, baseline + capture provenance, regression band, and review cadence; a
pure-read stdlib scorecard renderer (`user/scripts/kpi-scorecard.py`, sibling of
`lazy-queue-doc.py`) that computes current values from the declared signals
(`build-queue-results`, `deny-ledger`, `sentinel-scan`, `telemetry-ledger`) and renders per-system
health with regression flags (OK/WARN/BREACH/NO-DATA/PENDING-BASELINE, never a fabricated zero)
into a byte-stable `docs/kpi/SCORECARD.md`; and an injected `/spec`-time measurability gate
(`_components/spec-friction-kpi-gate.md`, Phase 3 Step 8.5) that refuses to lock a
friction-reduction feature's baseline until it declares its KPI rows (`--lint --spec` backstop).
`--capture-baseline <kpi-id>` is the sole computed-field registry writer
(`provenance: measured`, refuses on no-data). All four phases (registry+lint, computable-today
signals, ledger-backed rows + regen wiring, the `/spec` gate + baseline capture) landed across
prior checkpointed sessions; this session verified the full gate suite green, confirmed zero
remaining unchecked PHASES/plan deliverables, closed the one open gap (this feature's own SPEC
lacked the self-referential classification + `## KPI Declaration` its own gate would demand of
any other friction-reduction feature), and regenerated the committed scorecard against live
workstation signal history.

**Decisions that drove it:** D1 (single committed `docs/kpi/registry.json`, not per-system or
per-repo files) · D2 (full row schema: id/system/title/friction/signal/unit/direction/
baseline/band/review_by, closed `source` enum) · D3 (pure-read stdlib `kpi-scorecard.py`;
registry mutations only via explicit `_atomic_write`-backed CLI acts) · D4 (static declared
`band: {warn, breach}` absolute thresholds, not relative or statistical) · D5 (committed
byte-stable `docs/kpi/SCORECARD.md`, GitHub-mobile-readable) · D6 (self-declaration classification
line + B-advisory keyword cross-check for detecting a "friction-reduction feature") · D7 (injected
component + refuse-to-finalize + deterministic `--lint --spec` backstop) · D8 (full six-row seed
set with per-row provenance honesty — `pending` where signal history doesn't exist yet, never a
fabricated zero).

**Receipt: COMPLETED.md (provenance: operator-directed-interactive).**
