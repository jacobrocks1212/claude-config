---
kind: gate-verdict
feature_id: adhoc-unify-merged-head-coordinator-exemptions
gate_version: 1
date: 2026-07-19
scope_hit: [user/scripts/bug-state.py, user/scripts/lazy-state.py, user/scripts/lazy_core/dispatch.py]
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: the duplicated per-script exemption booleans `_emit_is_lane` / `_emit_is_lease_held` (mirrored verbatim across `lazy-state.py` and `bug-state.py`), replaced by the single shared predicate `coordinator_arbitrated_emission` in `lazy_core/dispatch.py`.
override: absent
---

## Adversarial answers

### overfit

The checker's flagged literals are the diagnostic-string elements appended to
`_COORDINATOR_EXEMPTION_DIAGS` in `lazy_core/dispatch.py` (the `"lane"` / `"lease"` reason-map
message text) plus the new module docstring line. These are not incident-shaped literals (no
`docs/{features,bugs}/<slug>` id, date, or session id was appended to a matcher) — they are the
VERBATIM relocation of the two diagnostic messages that already existed, unchanged, at both
callers before this refactor. The structural property the reshaped rule keys on: a
**reason-string → diagnostic-text map**, not a hardcoded conditional per exemption. Nearest
recurrence this rule does NOT catch: a genuinely NEW coordinator-arbitration exemption type (the
anticipated demoted-serial-rerun carve-out) — under the old shape that would have required a THIRD
ad-hoc boolean re-accreted independently at both callers (exactly the R56/R57/R101/R102 drift
pattern this bug fixes); under the new shape it is a one-line reason branch in
`coordinator_arbitrated_emission` plus one `_COORDINATOR_EXEMPTION_DIAGS` entry, in ONE place. The
literal-append shape the checker detects is therefore the anti-accretion win itself, not overfit to
a single observed incident.

### tautology

**Intervention Hypothesis:** Unifying the two duplicated per-script merged-head
emission-exemption booleans into one shared `lazy_core.dispatch` predicate
(`coordinator_arbitrated_emission`) eliminates the cross-script exemption DRIFT that caused the
per-signal supplement to be re-added across rounds (R56/R57/R101/R102 churn) WITHOUT changing
emission behavior (byte-identical `--test` baselines, verified this cycle).

If this change were BROKEN — the two callers drifted again, or the predicate mis-arbitrated an
exemption — the metric would look like: (a) renewed per-signal exemption re-additions appearing in
the hardening log (a new ad-hoc boolean reappearing at one or both callers instead of a reason
branch inside the shared predicate), OR (b) a `--test` baseline diff (the byte-identical
`lazy-state.py --test` / `bug-state.py --test` outputs this phase's Minimum Verifiable Behavior
proved would move). Both are distinguishable from "working" — a broken unification would show up
as EITHER renewed drift in an independent log OR a concrete baseline regression, not as silence.

**Independent signal:** the count of merged-head exemption re-addition / drift-fix rounds recorded
in `docs/specs/turn-routing-enforcement/hardening-log/` — a log this change does not itself emit
or suppress (it is written by unrelated hardening rounds observing the harness in the field).
Expected to drop to ~0 post-unification, since any future exemption now has a single one-line home
instead of requiring an independent re-add at each caller.

`signal_independence: independent` — the hardening-log round count is emitted by a separate
process (retro/hardening observation) from this change's own test suite or diagnostics, so it
cannot trivially read "identical to working" the way a self-emitted pass/fail would.

### gate_weakening

No weakening: `harness-gate.py --json` returned `gate_weakening_hit: false` /
`checks.gate_weakening.result: "pass"` with empty evidence. This diff deletes no `def test_*`
(6 new unit tests were ADDED to `test_dispatch.py`, and both state scripts' existing test suites —
`test_markers.py`, `test_lazy_core/`, `lazy_parity_audit.py` — all remained green), changes no
numeric literal on a gate line, grows no sanction/exemption *set* (the two exemption booleans
already existed and already granted a bypass of the merged-head guard; this change relocates their
evaluation into one predicate, it does not add a third exemption or widen either existing one),
introduces no `*_BYPASS` env-var, and removes no `permissionDecision: deny` / `refuse_*` / `exit 3`
branch. It is a behavior-preserving refactor, proven by byte-identical `--test` baselines and a
clean `lazy_parity_audit.py` run. No operator sign-off required; `override: absent`.

### complexity

**Retires:** the duplicated per-script booleans `_emit_is_lane` / `_emit_is_lease_held` (plus
their inline AND and the two per-caller observability `elif` branches), previously mirrored
verbatim across `lazy-state.py` (~14803-14965) and `bug-state.py` (~10062-10225). Confirmed the
retire claim is real: Phase 2's Implementation Notes record both booleans, the inline AND, and the
two `elif` branches removed from BOTH callers and replaced by one
`coordinator_arbitrated_emission(...)` call + one `elif _emit_exempt_reason is not None:` branch
each; the now-orphaned top-level `import lazy_coord` was also removed from both scripts (its sole
consumer moved into the predicate's local import in `dispatch.py`). The added surface — one new
predicate function + one reason→diag map + 6 unit tests in `lazy_core/dispatch.py` — pays for
itself by collapsing two independently-maintained per-caller exemption computations into one
shared, single-home definition, which is the anti-accretion outcome this bug was scoped to
deliver.
