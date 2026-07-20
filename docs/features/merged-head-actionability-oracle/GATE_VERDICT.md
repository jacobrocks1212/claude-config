---
kind: gate-verdict
feature_id: merged-head-actionability-oracle
gate_version: 1
date: 2026-07-18
scope_hit:
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core/dispatch.py
checks:
  overfit: flag-justified
  tautology: pass
  gate_weakening: pass
  complexity: declared
retires: nondispatchable_item_ids — the 5/6-facet file-predicate merged-head exclude helper (lazy_core/depdag.py) + its lazy-facade entry, replaced outright by the dispatch.merged_head_nondispatchable_ids actionability oracle (compute_state is the sole dispatch oracle now).
---

# Gate Verdict — merged-head-actionability-oracle

`harness-gate.py --range HEAD~3..HEAD` → `verdict_required: true` (exit 0, `gate_weakening_hit: false`).
Adversarial judgment per flagged check:

## overfit → flag-justified (FALSE POSITIVE — no production matcher fitted to an incident)

The checker's "appended literal / alternation literal" evidence lines are **not** production
matcher / allow-list / set appends. Every flagged line is one of:

- **New function type-annotations** on the net-new oracle in `dispatch.py`
  (`def is_dispatchable(scoped_state: "dict | None")`, `same_pipeline: "str | None" = None`,
  `same_pipeline_state: "dict | None" = None`, `today: "datetime.date | None" = None`) — Python
  parameter annotations the shape-detector reads as `A | B` alternations. They add no runtime
  matching branch.
- **Docstring `"""` delimiters** on the new oracle docstrings — the detector's "literal element
  appended to a membership construct" false-positive on triple-quote lines (a known
  harness-gate imprecision, documented in prior rounds).
- **Test-fixture string literals** in `test_dispatch.py` / `test_misc.py` — a BLOCKED.md
  frontmatter body written by a fixture, and the `is_dispatchable` predicate-table's terminal-reason
  set (`{"cloud-deferred-scoped", "device-deferred-scoped", ...}`). These are TEST assertion data,
  not a production allow-list.

**"Construct the nearest recurrence this rule does NOT catch":** the whole POINT of this feature is
that no literal enumeration is added — the oracle keys on the STRUCTURAL property
`is_dispatchable(scoped_state)` (a real forward `sub_skill` AND a falsy `terminal_reason`), so the
NEXT non-dispatchable `terminal_reason` category is auto-covered with zero code change. The
production diff REMOVED an enumerated file predicate (`nondispatchable_item_ids`, 5/6 hand-maintained
facets) and replaced it with one structural predicate — the exact opposite of fitting a matcher to
an observed instance. The terminal-reason set in the test is DERIVED from `lazy_core`'s existing
`SANCTIONED_STOP_TERMINAL` / `TELEMETRY_HALT_TERMINAL_REASONS` / notify sets (not hand-listed) plus
the scoped per-item terminal literals the oracle's own scoped probe emits.

## complexity → declared (retires: nondispatchable_item_ids)

See the `retires:` line above. The retire is REAL: `nondispatchable_item_ids` is deleted outright
(definition + facade map entry + all live callers migrated), grep-confirmed zero live callers, and
the retirement is asserted by `test_nondispatchable_item_ids_helper_is_retired`. Net surface change
is a REDUCTION: one enumerated file predicate (+ its five accreted facets) retired for one
structural oracle.

## gate_weakening → pass · tautology → pass

No `def test_*` deleted-net (5 dead helper tests removed, 3 new oracle/parked/retirement tests added —
coverage strictly increased), no numeric gate literal changed, no exemption/sanction set grown, no
`*_BYPASS` / `permissionDecision: deny` / `refuse_*` / `exit 3` branch removed. Not a
friction-reduction feature (SPEC header `Friction-reduction feature: no`), so no
`## Intervention Hypothesis` block is owed.
