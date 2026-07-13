# Planning-time capability audit is blind to INBOUND literal-path loaders of a moved module — Investigation Spec

> When a plan moves/renames a module, the planning-time audits enumerate the moved module's own
> OUTBOUND dependencies (its `__file__`-relative lookups) but nothing forces enumeration of
> INBOUND consumers that load the OLD path by literal file path (`spec_from_file_location`,
> hardcoded path strings). The lazy-core-package-decomposition Phase 1 plan enumerated all six
> outbound `__file__`-relative lookups as explicit WUs — and both inbound flat-file loaders
> (`validate-plan.py::_load_lazy_core`, `test_validate_plan.py:28-38` module-scope
> `spec_from_file_location`) broke at execution, one of them silently disarming a gate.

**Status:** Concluded
**Priority:** P2
**Last updated:** 2026-07-13
**Related:** `docs/features/lazy-core-package-decomposition/` (the motivating move);
`docs/bugs/plan-structural-backstop-silent-disarm-on-infrastructure-failure/` (the worst
downstream consequence of the miss); `user/skills/_components/phases-runtime-validation.md`
(the planning-time audit family this extends); `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Round 37.

## Verified Symptom

The Phase 1 plan (`docs/features/lazy-core-package-decomposition/plans/`) carried explicit WUs
for every OUTBOUND `__file__`-relative lookup inside the moved module (six enumerated). No WU
covered inbound loaders of the moved module itself. Two existed in the repo:

1. `user/scripts/validate-plan.py::_load_lazy_core` — loaded the flat
   `<scripts>/lazy_core.py` by literal path via `spec_from_file_location`. Broke
   (`FileNotFoundError`) the moment the flat file was deleted; consequence documented in the
   sibling bug (silent gate disarm).
2. `user/scripts/test_validate_plan.py` (module scope, ~L34-38 pre-fix) — same literal-path
   `spec_from_file_location` of the flat file. Broke at collection.

Both were found and fixed reactively DURING execution (they now import the package via
`sys.path` + `importlib.import_module("lazy_core")`), not enumerated at planning time.

## Root Cause

**Classification: `missing-contract`.** The planning-time capability-audit component
(`user/skills/_components/phases-runtime-validation.md`, injected at `/spec-phases` Step 2.7)
carries audits for SPEC-example capabilities, MCP tool existence, and data reach — all of the
enumerate→grep→record-ledger-row shape — but has NO audit for the module-move seam. The
outbound direction was covered by the feature's own research; the inbound direction has no
owner, and it is exactly the direction a module's author cannot see from inside the module.
A repo-wide grep for literal-path loads of the OLD path is deterministic, cheap, and would
have enumerated both hits as deliverables up front.

## Fix Scope

Add a **Module-move inbound-seam audit** to the planning-time audit family, same
enumerate→grep→record shape as its siblings:

- `user/skills/_components/phases-runtime-validation.md` (generic): MANDATORY when the plan
  moves/renames/deletes a module or file other code may load — grep the repo for literal-path
  loads of the OLD path (`spec_from_file_location`, `importlib` file loads, `runpy`,
  `open`/`read_text` of the module path, subprocess invocations of the file, hardcoded path
  strings — including tests' module-scope loaders) and enumerate EACH hit as an explicit
  `- [ ]` migration deliverable, one ledger row per hit.
- `repos/algobooth/.claude/skill-config/phases-runtime-validation.md` (the per-repo override,
  which WINS over the generic when present): mirror as a compact section so AlgoBooth planning
  is not blind to the same seam.
- Re-project + lint skills after the component edit.

Fix lands in hardening Round 37 (this session); remaining pipeline work is receipt-gated
`__mark_fixed__` verification.
