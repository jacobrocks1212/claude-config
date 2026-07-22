---
kind: fixed
feature_id: push-guard-classifies-by-session-cwd-not-push-target
date: 2026-07-22
provenance: backfilled-unverified
validated_via: test_hooks.py 293/293 (incl. 7 new target-classification regression tests) + harness-gate.py (gate_weakening pass) + lint-skills.py / lazy-state.py --test / bug-state.py --test / --fsck all OK; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

push-guard-classifies-by-session-cwd-not-push-target marked Fixed on 2026-07-22 during an
inline manual `/harden-harness` round (Round 131). This receipt was written by the harden
round, not the bug pipeline's `__mark_fixed__` gate — provenance is `backfilled-unverified`.

## Notes

Root cause (hook-defect): `block-work-repo-git-push.sh` read the work-repo signal via
`git config user.email` in the PreToolUse payload `cwd` (the session/invocation dir) instead
of the repo the push targets, so a personal-repo push invoked from a work-repo session was
falsely denied. A secondary defect — the trigger `\bgit\s+push\b` required `git`/`push`
adjacency — let `git -C <dir> push` bypass the hook entirely.

Fix (commit `2839ee29`): resolve the effective target dir (leading `cd`/`pushd` prefix and/or
an explicit `git -C <dir>`, over the payload cwd) and read `git config user.email` there;
broaden the trigger to match `git -C <dir> push` / `git -c <kv> push` without false-triggering
on unrelated forms. Hard contract preserved (JSON deny, fail-open on unresolvable dir, bypass
token honored, tool-name-agnostic). Added 7 regression tests to `test_hooks.py`.

Verification: `python user/scripts/test_hooks.py` → 293/293 (7 new); `harness-gate.py`
(HEAD~2..HEAD) `gate_weakening: pass`; lint-skills / lazy-state --test / bug-state --test /
--fsck all green.
