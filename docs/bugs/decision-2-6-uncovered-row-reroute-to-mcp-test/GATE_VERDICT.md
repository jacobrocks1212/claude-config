---
kind: gate-verdict
feature_id: decision-2-6-uncovered-row-reroute-to-mcp-test
gate_version: 1
date: 2026-07-19
scope_hit: [user/scripts/lazy_core/docmodel.py, user/scripts/lazy_core/gates.py, user/scripts/lazy_core/__init__.py, user/scripts/lazy-state.py, user/scripts/bug-state.py]
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: "the Step-10 completion path's BLINDNESS to uncovered non-exempt verification rows (the false-complete gap decisions 2+6 name) — replaced by the net-new shared predicate `uncovered_verification_rows_remain` (composing the Phase-1 `row_requires_host` recognizer) that is called once, at the same Step-10 seam, by BOTH `lazy-state.py` and `bug-state.py` (coupled-pair mirror, not a duplicated implementation). No prior rule is deleted; this closes a gap the completion path previously had no coverage for."
override: absent
---

## Adversarial answers

### overfit

`harness-gate.py` flags a long run of "literal appended to a membership construct" hits across
`bug-state.py` / `lazy-state.py` / `gates.py` / `docmodel.py`. Inspecting each: the large majority
are the new `--test` smoke-fixture bodies (`step10-uncovered-reroute[-bug]`,
`step10-covered-terminates[-bug]`, `step10-host-deferred-terminates[-bug]`,
`step10-no-mcp-surface-no-reroute[-bug]`) and their fixture literal PHASES.md/VALIDATED.md text —
test data, not matcher rules; they do not gate anything. The two checker hits that DO matter are
production additions: `_REQUIRES_HOST_ROW_RE` (`docmodel.py`) and the `gates.py` reroute-reason
strings (`"re-route to /mcp-test to finish the matrix"` /
`"remaining uncovered verification row(s) are all host-deferred — no re-route..."`).

**Nearest recurrence this rule does NOT catch:** both new primitives key on the STRUCTURAL shape
of a PHASES.md row, not on any specific bug's literal text — `_REQUIRES_HOST_ROW_RE` matches the
generic `<!-- requires-host: <cap> -->` HTML-comment marker syntax (mirroring
`_VERIFICATION_ONLY_MARKER` / `_DESCOPED_MARKER` byte-for-byte, including reuse of the same
`^[a-z0-9][a-z0-9-]*$` capability-id shape as `parse_requires_host`), and
`uncovered_verification_rows_remain` composes the EXISTING row-walk/evidence primitives
(`remaining_unchecked_are_verification_only`, `observation_gap_promotable`,
`evaluate_completion_evidence`) rather than hand-rolling a new checkbox scanner. The genuinely-new
recurrence this rule does NOT catch is a **new row TYPE this bug never anticipated** — e.g. a
future row-annotation convention distinct from `verification-only` / `requires-host` /
`descoped` — which is exactly the class the marker structure is designed to absorb by adding
another sibling marker + recognizer, not by teaching this predicate a one-off literal. No
incident-shaped literal (a `docs/bugs/<slug>` id, a date, a session id) was appended to any
matcher/allow-list in production code; the checker's remaining hits are test fixtures.

**Structural property the rule keys on:** presence of a specific HTML-comment marker syntax on a
PHASES.md row (`<!-- requires-host: <cap> -->`), evaluated the same way the pre-existing
`_VERIFICATION_ONLY_MARKER`/`_DESCOPED_MARKER` markers are — never a bug-id or literal row string.

### tautology

**Intervention Hypothesis:** Re-routing a Step-10 item that still has uncovered non-exempt
verification rows to `/mcp-test` (instead of completing) closes the false-complete gap (decisions
2+6) WITHOUT blocking legitimate completions (exempt / host-deferred / no-MCP-surface rows still
complete via the existing guards).

**If this change were BROKEN (over-firing),** the observable signature is distinguishable from
success: legitimate no-MCP-surface or exempt items would STOP completing — a completion-rate DROP
at `__mark_complete__`/`__mark_fixed__`, or an infinite re-route loop (Step 10 → `/mcp-test` →
Step 10 → ...) visible as a repeated `current_step` value across cycles for the same item. That is
NOT what "working" looks like (working = the re-route fires once on a genuine subset, then
terminates), so the metric is not tautological.

**Independent signal declared:** the count of items reaching `__mark_complete__` / `__mark_fixed__`
while still carrying uncovered non-exempt verification rows — an independent completion-ledger
observable this change does not itself emit or suppress (it is read off `VALIDATED.md`/receipt
state after the fact, not off the re-route branch's own execution). Expected to drop to ~0 once
this change ships; a persistently nonzero count post-ship would REFUTE the hypothesis.
`signal_independence: independent`.

### gate_weakening

No weakening: the diff adds a re-route branch that sends an item with uncovered non-exempt
verification rows to `/mcp-test` instead of letting it fall through to
`__mark_complete__`/`__mark_fixed__` — this STRENGTHENS the completion gate by closing a false-
complete path, the inverse of weakening. No `def test_*` was deleted, no numeric literal on a gate
line was changed, no exemption/sanction set was grown, no `*_BYPASS` env-var was introduced, and no
`permissionDecision: deny` / `refuse_*` / `exit 3` branch was removed. `harness-gate.py` itself
reports `gate_weakening: pass` with empty evidence. No operator sign-off required; `override:
absent`.

### complexity

**Retires:** the Step-10 completion path's blindness to uncovered non-exempt verification rows —
the false-complete gap decisions 2+6 name (a matrix-incomplete `VALIDATED.md` previously forced an
unconditional dispatch to the terminal pseudo-skill with no coverage-completeness check).

**Net-new justification:** one shared pure predicate, `uncovered_verification_rows_remain`
(`gates.py`), plus its one new input primitive `row_requires_host` (`docmodel.py`), called from
BOTH `lazy-state.py` (before `__mark_complete__`) and `bug-state.py` (before `__mark_fixed__`) as a
byte-mirrored coupled-pair branch (parity-audited, not a duplicated implementation). The added
surface pays for itself by closing the same gap once for both pipelines instead of twice, and by
composing existing row-walk/evidence helpers rather than adding a parallel PHASES-parsing path.
