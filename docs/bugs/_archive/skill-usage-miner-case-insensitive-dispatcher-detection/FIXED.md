---
kind: fixed
feature_id: skill-usage-miner-case-insensitive-dispatcher-detection
date: 2026-07-13
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

skill-usage-miner-case-insensitive-dispatcher-detection marked fixed on 2026-07-13 by the
interactive subagent orchestration Jacob directed (a repo-wide cleanup pass driving
`test_skill_usage_miner.py` failures to green). This receipt was written by the orchestrator, not
the pipeline's `__mark_fixed__` gate — provenance is deliberately operator-directed-interactive.

## Notes

Production fix in `skill-usage-miner.py` (`hygiene_sweep`'s dir branch: exact-case membership
check over `entry.iterdir()` replaces the case-insensitive `(entry / "SKILL.md").is_file()` test).
Test-side fix in `test_skill_usage_miner.py` for an unrelated separator-assumption bug in the same
test. Verified: `python -m pytest user/scripts/test_skill_usage_miner.py -q` went from 26 passed /
1 failed to 27 passed / 0 failed on this Windows workstation.
