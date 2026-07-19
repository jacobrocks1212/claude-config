---
kind: gate-verdict
feature_id: adhoc-process-friction-detector-counts-concurrent-session-commits
gate_version: 1
date: 2026-07-19
scope_hit:
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/gates.py
  - user/scripts/lazy_core/ledgers.py
  - user/scripts/lazy_core/markers.py
checks:
  overfit: pass
  tautology: pass
  gate_weakening: pass
  complexity: declared
retires: net-new — a shared per-repo concurrent-activity sha ledger (`append_concurrent_commit_sha`/`read_concurrent_commit_entries`) + a ledger-read subtraction arm on the existing `_count_concurrent_writer_commits`. No rule retired; the added surface is the second (identity-independent) attribution signal the committer-email heuristic could never provide.
---

## Adversarial answers

### overfit
`harness-gate.py` reported `flags: null` over `14840da9..5e2fc37f`. No literal appended to a matcher; no incident-shaped literal. The fix keys on the STRUCTURAL property "a commit produced by a script-owned direct-commit site under a distinct run identity, in-window" (recorded by instrumenting the only two `_git(...,"commit",...)` sites in `lazy_core/**`), not on any specific session/date/id. The nearest recurrence — a concurrent session committing through a NON-script-owned site — is out of scope by design (only automated pipeline commits are ledgered), and the fail-safe (never over-subtract) means an un-ledgered concurrent commit degrades to the pre-fix conservative behavior, not a wrong suppression.

### tautology
No tautology flag. If broken, the metric would NOT look like working: a broken subtraction either over-subtracts (a genuine runaway's commits masked → caught by the retained `test_...runaway_still_trips` control) or under-subtracts (the false `unexpected-commits` persists → caught by the SEAM-B regression `test_concurrent_session_commits_seam_no_false_friction`, RED-before/GREEN-after on the real `cycle_end_friction_check` serving path). Independent signal: the deterministic pytest regressions (1297 passed).

### gate_weakening
No gate-weakening hit. No `def test_*` deleted, no gate numeric literal changed, no sanction/exemption set grown, no `*_BYPASS`, no deny/refuse branch removed. The friction detector is made MORE precise (fewer false positives) while the fail-safe preserves its runaway-catching strength — a correctness tightening.

### complexity
`retires: net-new` (frontmatter). The added ledger + subtraction arm is the identity-independent attribution the email heuristic structurally cannot provide (the motivating incident: 28 concurrent commits under one git identity). The surface is bounded — two instrumented commit sites (grep-audited as the only two), a small append/read ledger pair, fail-safe on every degraded read — and paid for by eliminating the false-friction class that was mis-charging cycle budgets.
