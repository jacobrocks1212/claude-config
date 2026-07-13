---
kind: gate-verdict
feature_id: bug-queue-aging-backpressure
gate_version: 1
date: 2026-07-13
scope_hit:
  - user/scripts/bug-state.py
  - user/scripts/lazy_core.py
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: The manual `docs/bugs/queue.json` `"severity": null` hand-edit defer and the never-expiring explicit pin — replaced by mechanical age-escalation past expired pins + the expiring `--pin` CLI.
---

## Adversarial answers

Commit range analyzed: `8f9adcc2..337e41de` (the feature's sole `feat(...)` commit).
`harness-gate.py` over that range: overfit=flag, tautology=flag, gate_weakening=hit,
complexity=declaration-required. Out-of-scope co-changed data files
(`docs/cli/cli-surface.json`, `docs/kpi/*`) are subtracted.

### overfit
Overfit flags on the scope files are new argparse definitions (`--pin`, `--until`,
`--record-decision`, `--chosen`, `--sentinel`, `--summary`) reading as membership-construct
elements, docstring prose, and the `9999-99-99` far-future sentinel matching the incident-date
regex `\d{4}-\d{2}-\d{2}`. The `9999-99-99` is a structural "never expires" placeholder, not an
incident date; the rest are new CLI surface. No incident-shaped literal was appended to a
production matcher. Nearest recurrence a literal-keyed rule would miss: N/A — the aging logic keys
on `today - discovered_date` arithmetic against the pin's `expires` field, not on any specific
bug id or date. Structural property: age-relative comparison over per-entry timestamps.

### tautology
No `## Intervention Hypothesis` block → checker flags. If the age-escalation were broken, aged
bugs would silently stall behind expired pins and look "quiet", but that is NOT identical to
working: the feature shipped two sentinel-scan KPIs (in `docs/kpi/registry.json`, rendered by
`kpi-scorecard.py`) that measure pin-expiry backlog and aging dwell, plus `bug-state.py --test`
fixtures asserting escalation ordering. A broken escalation shows up as a rising KPI backlog and
failing fixtures — signals external to the escalation code itself. `signal_independence: independent`.

### gate_weakening
Verified over the feature's own diff: no `def test_*` deletion, no `permissionDecision: deny` /
`refuse_*` / `exit 3` removal, no `*_BYPASS`, no sanction/exemption-set growth. The `--pin` CLI is
gated by the existing `refuse_if_cycle_active` (a REFUSAL added, not removed). The checker's
`gate_weakening: hit` over the range is on out-of-scope data files only. No weakening. Pass.

### complexity
Retires the operator's manual `queue.json` `severity: null` defer hack and the never-expiring pin.
The retire is real: the SPEC replaces both with mechanical age-escalation + an expiring `--pin`
that the aging pass overrides once stale, so the hand-edit is no longer the mechanism. PROVISIONAL
(D1 parked, ratification pending per `NEEDS_INPUT_PROVISIONAL.md`).
