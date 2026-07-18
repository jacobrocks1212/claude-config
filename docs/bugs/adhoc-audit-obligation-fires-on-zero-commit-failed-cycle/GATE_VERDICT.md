---
kind: gate-verdict
feature_id: adhoc-audit-obligation-fires-on-zero-commit-failed-cycle
gate_version: 1
date: 2026-07-18
scope_hit: [user/scripts/lazy_core/markers.py, user/scripts/lazy_core/ledgers.py, user/scripts/lazy_core/__init__.py, user/scripts/lazy-state.py, user/scripts/bug-state.py]
checks:
  overfit: flag-justified
  tautology: pass
  gate_weakening: pass
  complexity: declared
retires: the unconditional cycle-kind-based audit-obligation arming rule (arm-on-every-spec-kind-close) — replaced by the commit-delta-gated arming (`begin_sha != end_sha`), and the positional `HEAD~1` binding in `build_input_audit_emit_command` — replaced by the bracket's recorded end sha + subject
override: absent
---

## Adversarial answers

Checker run: `harness-gate.py --range ea3b7006~1..ea3b7006 --feature-dir docs/bugs/adhoc-audit-obligation-fires-on-zero-commit-failed-cycle`
(fix-commit-scoped; the broad run-range scan additionally flagged only run-machinery churn —
KPI SCORECARD telemetry-number regen and provenance-index rows — none of it part of this fix).

### overfit

Flag evidence is exclusively TEST-FIXTURE literals (`"feat-a"`, `"bug-1"`, `"bbb222"`,
fixture paths like `/repo/docs/features/feat-a`) and a docstring `"""` delimiter — the
documented false-positive class recorded identically in hardening Rounds 91, 92, and 93.
Nearest-recurrence test: the PRODUCTION change appends no literal to any matcher — it removes
a condition-free arming call and replaces it with a structural predicate
(`begin_sha != end_sha`) plus a recorded-sha binding. The nearest recurrence (a zero-commit
close of any OTHER cycle kind, or a future emit class binding positionally) is caught by the
same structural predicate and the same recorded-end-sha rule, not by any instance literal.
The final rule keys on the structural property "the closed bracket produced a non-empty
commit delta", not on any observed slug/date/sha.

### tautology

No flag. The item carries the standard `__mark_fixed__`-recorded intervention with a
countable target signal (mis-fired input-audit dispatches — observable as audit meta-cycles
whose bound commit does not touch the audited item's dir); the signal is produced by future
runs' dispatch machinery, not by this change itself. If this change were broken (obligation
still arming on zero-commit closes), the signal would look exactly like this run's live
incidents (meta-11 and the cycle-27 aftermath) — distinguishable from working.

### gate_weakening

Pass — no test deleted (5 tests ADDED across test_markers.py/test_ledgers.py + a subprocess
e2e), no gate-line numeric changed, no exemption set grown, no deny/refusal branch removed.
The change NARROWS when an audit fires; the audit itself is untouched.

### complexity

Retires the unconditional kind-based arming rule and the positional `HEAD~1`/latest-subject
binding (both named in `retires:` above); the retired behaviors provably stop firing — the
new pytest cases assert a zero-commit close arms nothing and the emit command binds the
bracket's recorded end sha.
