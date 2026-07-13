---
kind: gate-verdict
feature_id: mechanize-prose-only-orchestrator-contracts
gate_version: 1
date: 2026-07-13
scope_hit:
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core.py
  - user/scripts/lazy_guard.py
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: The four hand-followed prose orchestrator contracts (pin-by-rewrite, audit obligations, decision records, notify events) — demoted from SKILL.md prose to script-enforced mechanisms + pointers.
---

## Adversarial answers

Commit range analyzed: `bfdd57a6..8f9adcc2` (the feature's sole `feat(...)` commit).
`harness-gate.py` over that range: overfit=flag, tautology=flag, gate_weakening=hit,
complexity=declaration-required. Findings worked below; unrelated co-changed data files
(`docs/cli/cli-surface.json` regen, `user/scripts/skill-size-baseline.json` ratchet lock-in)
are outside this feature's named scope and mentally subtracted.

### overfit
The checker's overfit flags on the scope files are all non-matcher shapes: new argparse
definitions (`--record-decision`, `--chosen`, `--sentinel`, `--summary`) read as "list element
appended to a membership construct", multi-line docstring prose read as quoted list elements, and
Python type annotations like `"date | None"` tripping the alternation detector. NONE is an
incident-shaped literal (a specific slug / date / session id) appended to a production matcher —
the mechanization added CLI surface and decision-record plumbing, it did not fit a rule to an
observed instance. Nearest recurrence the (non-existent) rule would miss: N/A — there is no
incident-keyed matcher here to reshape. Structural property: the added code keys on generic CLI
arguments and frontmatter-shaped decision records, not on any literal drawn from a past incident.

### tautology
No `## Intervention Hypothesis` block in SPEC.md → checker flags. If this mechanization were
broken it would NOT look identical to working: the four contracts are now backed by
`test_lazy_core.py` fixtures (645 new lines) and by `lazy_parity_audit.py`, so a broken
pin-by-rewrite / decision-record / notify path fails the in-file `--test` suite and the parity
audit deterministically. Independent signal: the state-script `--test` fixture pass/fail and the
coupled-pair parity audit — neither of which this feature's runtime itself emits or suppresses.
`signal_independence: independent`.

### gate_weakening
Verified over the feature's own diff on the scope files: no `def test_*` deletion, no
`permissionDecision: deny` / `refuse_*` / `exit 3` removal, no `*_BYPASS` env-var, and no
addition to any sanction/exemption set (`SANCTIONED_STOP_TERMINAL`, `_NOTIFY_*_TERMINALS`,
`_FAIL_CLOSED_EVIDENCE_SENTINELS`, etc.). The checker's `gate_weakening: hit` over the range is
entirely on out-of-scope data files — a doc `**Last updated:**` date bump and
`skill-size-baseline.json` byte-ceiling LOWERING (a ratchet lock-in improvement, the opposite of
a weakening). Neither is in this feature's scope. No weakening.

### complexity
Retires the four prose contracts that orchestrators previously had to follow by hand — they are
demoted to script-enforced mechanisms with SKILL.md pointers. The retire is real: the SKILL.md
prose is now a pointer, and the enforcement lives in the scripts + tests, so the hand-followed
obligation genuinely stops being the load-bearing surface.
