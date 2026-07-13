---
kind: gate-verdict
feature_id: lazy-batch-skill-deflation
gate_version: 1
date: 2026-07-13
scope_hit:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: net-new — adds the per-file skill-size ratchet gate (`skill-size-ratchet.py` + `skill-size-baseline.json`). Retires 4 stale `lint-skill-config.py` SUPPRESSIONS (their references were fixed by follow-up (i)) and the unbounded skill-file accretion posture (+57%/4wk pre-gate).
---

## Adversarial answers

Commit range analyzed: `651acc63..664d9a7c` (the feature's sole `feat(...)` commit).
`harness-gate.py` over that range: overfit=flag, tautology=flag, gate_weakening=hit,
complexity=declaration-required. Findings worked below.

### overfit
The overfit flags are on the new `skill-size-baseline.json` per-file ceiling entries (a list of
`{file, byte_ceiling, long_line_ceiling}` records reading as membership elements) and docstrings.
The baseline is the ratchet's DATA, keyed on file PATHS (structural, opt-in per file), not on any
incident literal. The two scope SKILL.md files got a leaner description field and a prose excision.
No incident-shaped literal appended to a production matcher. Nearest recurrence a literal-keyed rule
would miss: N/A — the ratchet keys on `byte-count(file) <= ceiling` for any listed file. Structural
property: per-file size measurement, not any observed slug/date.

### tautology
No `## Intervention Hypothesis` block → checker flags. If the deflation were broken (files kept
growing), the metric would NOT look identical to working: `skill-size-ratchet.py --check` fails
naming any file over its byte or long-line ceiling, and the raw byte sizes are directly measurable.
Independent signal: the ratchet's mechanical `--check` verdict + the measured file sizes — external
to the SKILL.md content itself. `signal_independence: independent`.

### gate_weakening
Verified over the feature's own diff: no `def test_*` deletion (161 lines of NEW tests added), no
`permissionDecision: deny` / `refuse_*` / `exit 3` removal, no `*_BYPASS`. The `lint-skill-config.py`
`-11` lines REMOVE 4 entries from a SUPPRESSIONS allowlist — removing suppressions is a
STRENGTHENING (fewer exemptions), not a weakening; the references were fixed by follow-up (i). The
`skill-size-baseline.json` numbers are SEED ceilings for a brand-new ratchet gate (net-new gate
machinery), not a relaxation of an existing threshold — and the ratchet's `--lock-in` can only lower
ceilings, never raise them. No weakening. Pass.

### complexity
Net-new size-ratchet gate. Real retires: 4 stale `lint-skill-config.py` SUPPRESSIONS (they stop
being needed once their references are fixed) and the unbounded-accretion posture (the ratchet caps
further growth immediately). PROVISIONAL (D2 parked; 3 hotspot excisions deferred with a method plan
per `NEEDS_INPUT_PROVISIONAL.md`).
