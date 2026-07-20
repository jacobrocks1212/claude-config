---
kind: gate-verdict
feature_id: gate-verdict-dispatch-derives-scope-from-empty-range-for-merged-item
gate_version: 1
date: 2026-07-19
scope_hit:
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/dispatch.py
  - user/scripts/lazy_core/gates.py
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: net-new — adds the completion-time item-scoped checker (`item_scoped_gate_report` + `_item_commit_derivation` + `_diff_from_commits`), the `--gate-verdict-check` CLI on both state scripts, and a `{state_script}` dispatch-template token. No rule/surface is retired; the added surface makes the authoring seam AGREE with the pre-existing ship seam (`gate_verdict_ok`) by REUSING its exact commit derivation — the two can no longer drift.
---

## Adversarial answers

### overfit
`gate_weakening_hit: false`; the two flagged detectors are `overfit` and `tautology`, both `flag`,
neither a `hit`. Every `overfit` evidence item is a quoted-STRING DATA line — an argparse
`help=(...)` multi-line continuation on `lazy-state.py` / `bug-state.py`, a Python docstring
delimiter, or a return-dict string VALUE (`"reason": "no control-surface manifest"`). **Structural
property:** NONE is a literal appended to a matcher construct — no regex alternation, keyword set,
or allow-list gains an element. These strings are inert data the harness never pattern-matches
against; the change adds no incident-shaped literal (no `docs/{features,bugs}/<slug>`, dated, or
session token). The nearest-recurrence-not-caught question is moot: there is no matcher being fitted
to observed data. The flags are a KNOWN precision gap in `detect_overfit` case (b), which matches any
quoted-string line sitting near a `[`/`{`/`(` — its sibling `detect_gate_weakening` guards the same
class with `_TRIPLE_QUOTE_RE` + `_exemption_opens_collection`, but `detect_overfit` case (b) does not.
Spun off as `/spec-bug harness-gate-overfit-case-b-flags-quoted-string-data-near-braces` (see the
hardening round's over-fit spin-off line).

### tautology
`flag` because this bug's SPEC.md carries no `## Intervention Hypothesis` block (the fix is a
mechanical scope-derivation correction, not a self-observing metric-gate). Independent signal
(`signal_independence: independent`): the regression test
`test_item_scoped_gate_report_agrees_with_ship_seam_for_merged_item` constructs a MERGED-item git
fixture (`origin/main..HEAD` empty) and asserts `item_scoped_gate_report`'s `in_scope`/`scope_hit`
EQUAL the ship seam's own commit-derived scope. If this fix were broken or tautological (e.g. the
authoring seam silently re-derived scope from the same empty range), that test would fail — a signal
the change neither emits nor suppresses. Live evidence: `test_lazy_core` 1337 passed (incl. the new
pin), `lazy-state/bug-state --test` OK, parity clean.

### gate_weakening
No gate-weakening hit (`gate_weakening_hit: false`). No `def test_*` deleted (+2 fixtures added), no
gate numeric literal changed, no sanction/exemption set grown, no `*_BYPASS` env-var introduced, no
`permissionDecision: deny` / `refuse_*` / `exit 3` refusal removed. The change ADDS a completion-time
check path (a report the authoring subagent reads) and STRENGTHENS the design gate: an already-merged
control-surface item can now be honestly authored and completed instead of deadlocking — the ship
seam `gate_verdict_ok` is byte-unchanged and still refuses a missing/failing/unsigned verdict.

### complexity
`retires: net-new` (frontmatter). The added surface is one shared derivation helper
(`_item_commit_derivation`, which `_item_commit_touched_files` now also routes through — so the file
COUNT of item-scope logic does not grow, it consolidates), one diff builder (`_diff_from_commits`,
the `git show` analog of the existing `_files_from_commits`), one pure-read report
(`item_scoped_gate_report`) reusing the imported `harness_gate.run_checker` (no new checker engine),
a coupled-pair CLI action, and one deterministic dispatch token. It pays for itself by eliminating
the permanent completion deadlock for any previously-parked control-surface item driven to
completion on a later run (observed: the repro's `BLOCKED.md` records this as the 6th occurrence in
a single run). Bounded: no change to `harness-gate.py`, no change to `gate_verdict_ok`, no new
manifest.
