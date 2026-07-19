---
kind: fixed
feature_id: claude-attribution-trailers-not-globally-disabled
date: 2026-07-19
provenance: backfilled-unverified
validated_via: settings.json JSON-validity check + grep-confirmed no residual attribution mandate on any live commit/PR surface; NOT pipeline-gated
auto_ticked_rows: 0
---

# Fixed

`claude-attribution-trailers-not-globally-disabled` marked Fixed on 2026-07-19 by a dispatched
`/harden-harness` round (observed-friction trigger). Fixed OUT-OF-PIPELINE via a `harden(...)`
commit, not the bug pipeline's gated `__mark_fixed__` path — provenance is deliberately
`backfilled-unverified`.

## What shipped

`"includeCoAuthoredBy": false` was added to `user/settings.json` (→ `~/.claude/settings.json`,
the user-level scope applying to every repo), disabling Claude Code's automatic Co-Authored-By /
"Generated with Claude Code" byline globally on commits and PRs — the PRIMARY mechanism the
operator directive named.

The secondary sweep found NO active behavioral surface mandating an attribution trailer to
neutralize: `/commit`, `/push`, `.claude/skill-config/commit-policy.md`, and both
`repos/*/.claude/skill-config/commit-policy.md` files already forbid AI attribution; the PR-writing
skills (`write-pr-description`, `write-pr-comments`) carry no attribution mandate. The remaining
repo hits are archived plans / historical bug specs / a research prompt that only MENTION the
strings and drive no live behavior.

## Verification

- `python -c "import json; json.load(open('user/settings.json'))"` → valid JSON; key present at
  line 246 (`git show origin/main:user/settings.json` confirms it landed on the remote).
- Full gate battery green: pytest `tests/test_lazy_core/` 1300/1300; `lazy-state.py --test` and
  `bug-state.py --test` all smoke passing; `test_hooks.py` 277/277;
  `lint-skills.py --check-projected --check-capabilities` OK; `bug-state.py --fsck` clean.
- `harness-gate.py` over the change: `gate_weakening: pass`; the `includeCoAuthoredBy` line
  appears in zero overfit evidence entries (the flag on the commit belongs to a concurrent lane's
  own feature that shared the commit).

## Provenance note

The one-line `user/settings.json` edit was absorbed into concurrent execute-plan lane commit
`8dded98a` (its `git add -A` swept the uncommitted working-tree change). The change is correct,
committed, and pushed. The clean `harden(docs):` investigation-spec commit is `aef06e32`.
