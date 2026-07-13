---
kind: fixed
feature_id: setup-py-windows-extended-path-prefix-mismatch
date: 2026-07-13
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

setup-py-windows-extended-path-prefix-mismatch marked fixed on 2026-07-13 by the interactive
subagent orchestration Jacob directed (a repo-wide cleanup pass driving `test_setup_py.py` failures
to green). This receipt was written by the orchestrator, not the pipeline's `__mark_fixed__` gate —
provenance is deliberately operator-directed-interactive.

## Notes

Production fix in `setup.py` (`_strip_extended_prefix` helper + one call site in `_readlink`).
Verified: `python -m pytest user/scripts/test_setup_py.py -q` went from 58 passed / 8 failed to
66 passed / 0 failed on this Windows workstation (before/after commands + counts recorded in the
session). No test-side change was needed — the symptom was a genuine cross-platform bug.
