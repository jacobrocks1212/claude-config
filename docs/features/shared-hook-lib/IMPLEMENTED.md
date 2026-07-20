---
kind: implemented
feature_id: shared-hook-lib
date: 2026-07-18
provenance: pipeline-gated
derivation: commit-brackets
commits: [5d1f950, baf07a6, 560d5eb, d2db402, '9069465', 70caf70, 9f715c3, e4fd093, 962c06a,
  f7a7a9e, 33cafa0, f1095e0, e5d9dba, b4308f0, 6ec23c1, 6c2e970, ca8ca8b, f157bca,
  3d69974, b88fc5a, cb940ef, e04753f, e66c02f, beae3aa, 2be204c, 716dfd3, b82bf97,
  a78845f, 5e0f4d7, 5dee2ed, ed37a2d, 79070c7, b8b2259, 0b6051e, f4cf28f, 0c56616,
  becaea6, f7f9493, 65f709e, 64bf865, f08f83b, 0dc1da2, c800431, ff83d28, 247b897]
decisions: []
---

# Implementation Ledger

**What shipped:** Extract the ~470 duplicated scaffolding lines (~20% of the 2,411-line `user/hooks/` plane) into a shared, fail-open-guarded pair — `hook-prelude.sh` (sourced bash: python resolution, SCRIPT_DIR derivation, no-python fallback breadcrumb) and `hook_lib.py` (allow/deny emitters, `_append_hook_event`, `_breadcrumb`, the shared `_ENV_PREFIX`/`_CMD_START` anchor regexes) — then migrate the seven python-bearing hooks one at a time, re-running the full 157-test `test_hooks.py` suite after each. Copy-drift in this scaffolding has already produced real bugs; a matcher-semantics change today must be hand-landed in three places.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
