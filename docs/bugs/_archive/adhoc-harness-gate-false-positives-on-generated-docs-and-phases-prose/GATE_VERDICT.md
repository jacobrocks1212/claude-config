---
kind: gate-verdict
feature_id: adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose
gate_version: 1
date: 2026-07-19
scope_hit:
  - user/scripts/harness-gate.py
checks:
  overfit: pass
  tautology: pass
  gate_weakening: pass
  complexity: declared
retires: net-new precision — scopes `run_checker`'s detector input to manifest control-surface hunks (off-manifest docs no longer scanned) and adds `_SHELL_PIPE_SHAPE_RE` so a shell `||` breadcrumb in a hook is not mistaken for a regex-alternation append. No rule retired; the gate is made MORE precise (fewer false positives) while every positive control still fires.
---

## Adversarial answers

### overfit
The now-fixed detector reports `flags: null` over its own fix (`8447b3da..HEAD`) — the fix does not overfit. It keys on STRUCTURAL properties: manifest membership (`h.file ∈ scope_hits`, the existing control-surface SSOT) for scoping, and shell-pipe shape (`||`/`$( )`/`Nd>`/` | ` outside a quoted matcher body) for the alternation exclusion. No incident literal was added; the named regression fixtures (`_VERIFICATION_SECTION_RE` alternation append, on-manifest `*_BYPASS`) still flag, so the class boundary is preserved.

### tautology
Not applicable (defect fix, not a self-observing gate). If broken, the metric would diverge from working: an over-scoped detector re-flags off-manifest docs (caught by the +4 Phase-1 fixtures), and an over-tightened alternation heuristic misses a genuine append (caught by the retained `_VERIFICATION_SECTION_RE` positive control). Independent signal: `test_harness_gate.py` 38 passed.

### gate_weakening
No gate-weakening hit (`gate_weakening_hit: false`). No `def test_*` deleted (+6 fixtures added), no gate numeric literal changed, no sanction/exemption set grown, no `*_BYPASS` introduced, no deny/refuse branch removed. This is a precision tightening of a checker that was over-firing — it strengthens signal quality, and every positive control (real overfit, real gate-weakening) still fires.

### complexity
`retires: net-new precision` (frontmatter). The added surface — a manifest-hunk filter + one shell-shape exclusion regex — pays for itself by eliminating the false-positive class that was forcing spurious operator gate-weakening sign-offs on legitimate doc/prose/dead-code diffs (observed repeatedly this run). Bounded: one filter at the single `run_checker` detector-input site, one exclusion regex in `detect_overfit` case (a).
