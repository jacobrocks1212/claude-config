# Push-hook bypass token `^`-anchored (false-blocks composed push) — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 1 — Regression coverage for composed approved pushes

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-18
**Work completed:**
- Added `test_push_allows_with_bypass_token_after_cd_prefix` to `user/scripts/test_hooks.py`
  (immediately after `test_push_allows_with_bypass_token`), asserting the composed command
  `cd "<repo>" && CLAUDE_PUSH_APPROVED=1 git push origin main` is ALLOWED by
  `block-work-repo-git-push.sh` in a work-email (`jacob@cognitoforms.com`) repo. Reuses the
  existing harness helpers (`_init_email_repo`, `_run_bash`, `_hook_payload`, `_base_env`,
  `_hook_decision`, `_PUSH_HOOK_SH`) verbatim — no new scaffolding.
- Registered the test in a dedicated `_TESTS = _TESTS + [...]` block placed immediately after
  the new function (before `test_push_allows_in_non_work_repo`), following this file's
  established pattern for later topical additions.
- No production code changed. The hook's fix (unanchored `_BYPASS_RE.search`) was already on
  `main` at commit `365df0b9`; this phase supplies only the missing regression coverage named
  in SPEC.md "Confirmed scope" item 2.

**Integration notes:**
- This is the only phase in this bug's PHASES.md — no next phase.
- The test is a regression LOCK, not a red→green TDD case: it passes immediately against the
  current (already-fixed) hook. Verified this is not vacuous by static reasoning over the
  before/after regex (pre-`365df0b9` `re.match(r"^CLAUDE_PUSH_APPROVED=1\b", …)` would fail to
  match a `cd "…" && `-prefixed command and fall through to the work-email deny; the current
  `_BYPASS_RE.search(...)` matches the token anywhere and allows) — deliberately did NOT
  temporarily edit/revert the hook file to prove this, per the plan's own guidance
  (risk of leaving the hook in a bad state outweighs the marginal proof value).

**Pitfalls & guidance:**
- Mid-verification, the dispatched subagent ran `git stash` to compare pre/post behavior and it
  briefly stashed its own uncommitted edit; caught immediately and `git stash pop`'d — file
  confirmed intact via `wc -l`/`grep -n` + a full clean re-run. The reviewing orchestrator
  independently repeated this exact stash/pop cycle during review (comparing pre-existing vs.
  post-change failure sets) and popped cleanly. No data was lost either time, but future
  reviewers should prefer a `git diff`/`git show` read over `git stash` when a stash is not
  strictly required, to avoid this footgun.
- The suite has 22 pre-existing, unrelated `test_containment_*` (and one `test_events_*`)
  failures in `lazy-cycle-containment.sh` coverage — confirmed identical (same 22 test names)
  with and without this change (`git stash`/`stash pop` A-B compare), so they are OUT OF SCOPE
  for this bug. Not filed as a new bug this session (flagged for a possible future
  `/harden-harness` sweep, but not investigated — root cause unknown).

**Files modified:**
- `user/scripts/test_hooks.py` — added `test_push_allows_with_bypass_token_after_cd_prefix`
  (lines 7944-7960) + its `_TESTS` registration block (lines 7962-7966).
