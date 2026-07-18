# bug-state.py Step-7 routing loops write-plan forever on a verification-only-only PHASES remainder

**Status:** Fixed

**Severity:** P1

**Discovered:** 2026-07-18

**Origin:** harden-harness Round 93 (no-route trigger) — live write-plan routing loop on the
in-flight bug `dispatched-harden-record-intervention-refused-by-containment`.

## Symptom (verified)

The bug pipeline loops `probe → write-plan → no-op → probe → write-plan` forever on a bug whose
implementation deliverables are all checked but whose PHASES.md still carries at least one
unchecked **verification-only** row and has **no plan file on disk**.

Concrete live case (`docs/bugs/dispatched-harden-record-intervention-refused-by-containment/`):

- PHASES.md (authored cycle 25) has all 6 implementation deliverables `- [x]` — the fix landed
  OUT-OF-PIPELINE in commit `1cb997e0`, and the PHASES author ticked the impl rows to reflect it.
- Line 33 is the sole unchecked row: `- [ ] <!-- verification-only --> …` in the `**Runtime
  Verification**` section (the SEAM-B serving-path regression test, owned by the validation tail).
- **No `plans/` dir exists** (the fix never went through `/write-plan` / `/execute-plan`).

`bug-state.py compute_state` Step-7 routes `sub_skill=write-plan`. The dispatched `/write-plan`
cycle (cycle 26) CORRECTLY refuses to author a plan: its Step 1c queues only phases with unchecked
IMPLEMENTATION deliverables, Step 1c.5 excludes verification-only rows, and the Step 4.5 structural
gate requires ≥1 WU — so a plan would be fabrication. Result: zero plannable WUs, no file changes,
probe re-returns write-plan → a guaranteed step-repeat loop.

## Root cause (proven)

**script-defect** — a coupled-pair PARITY GAP. `bug-state.py::compute_state`'s Step-7
plan-needed predicate carries the OLD combined bypass form:

```python
if not plans and _has_any_complete_plan(spec_dir) and \
        remaining_unchecked_are_verification_only(phases_text):
    pass                       # fall through to the validation tail
elif not plans:
    return _bug_state(... write-plan ...)
```

The `_has_any_complete_plan(spec_dir)` conjunct is the defect. When the fix landed
out-of-pipeline there is NO plan file at all, so `_has_any_complete_plan` is `False`, the bypass
is skipped, and control falls to `elif not plans:` → write-plan → loop.

The **feature-side** `lazy-state.py::compute_state` fixed this exact class on 2026-06-15 (the
"mcp-testing deadlock", `lazy-state.py:3391-3428`) by splitting the bypass into two
discriminators and DROPPING `_has_any_complete_plan` from the workstation path:

```python
cloud_bypass = cloud and not plans and _has_any_complete_plan(spec_path)
workstation_bypass = not cloud and not plans and verification_only
if cloud_bypass or workstation_bypass:
    pass
```

A verification-only remainder is ITSELF proof that no implementation work remains (write-plan is
banned by its Step 1c.5 from emitting a verification-only re-run WU), so there is nothing to plan
— the Complete-plan receipt is not needed to prove "impl done" on the workstation path. That fix
was never mirrored into `bug-state.py`, whose comment even claims it "Mirrors the identical
bypass in lazy-state.py" — but it mirrors the PRE-fix combined form, not the post-fix split.

The routing predicate and the completion-gate's `remaining_unchecked_are_verification_only()`
semantics disagree: the completion gate exempts a verification-only remainder, but the routing
predicate treats it as plannable work whenever no Complete plan exists.

## Fix scope

In `bug-state.py::compute_state`'s Step-7 plan-needed predicate, mirror the feature-side split
byte-faithfully: `cloud_bypass = cloud and not plans and _has_any_complete_plan(spec_dir)`;
`workstation_bypass = not cloud and not plans and remaining_unchecked_are_verification_only(
phases_text)`; bypass when either holds. This drops `_has_any_complete_plan` from the
(workstation) verification-only path while preserving the legacy Complete-plan-exists case (a
subset of the verification-only predicate). Reuse the existing
`remaining_unchecked_are_verification_only()` / `_VERIFICATION_SECTION_RE` machinery — never
re-implement.

**Regression fixture** (`bug-state.py --test`): a PHASES with all impl rows `[x]` + one unchecked
`<!-- verification-only -->` row + NO plan file must route to the validation tail
(`sub_skill == mcp-test`, Step 9), NOT write-plan.

## Impact class

Any bug whose fix lands out-of-pipeline (a `harden(...)` commit, a teammate hotfix, a manual fix)
and whose PHASES carries a validation-tail-owned verification-only row is stranded in an infinite
write-plan loop — it can never reach the Step-9 MCP/validation gate. Feature-pipeline items were
immune since 2026-06-15; the bug pipeline was not.
