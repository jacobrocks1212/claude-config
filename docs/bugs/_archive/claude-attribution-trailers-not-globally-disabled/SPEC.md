# Claude commit/PR attribution trailers not globally disabled

**Status:** Fixed
**Discovered:** 2026-07-19
**Fixed:** 2026-07-19
**Fix commit:** 50938bc0
**Severity:** P2
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage); `user/skills/commit/SKILL.md`, `user/skills/push/SKILL.md`, `.claude/skill-config/commit-policy.md`

> Claude Code's automatic Co-Authored-By / "Generated with Claude Code" byline is still enabled
> at the platform level because `includeCoAuthoredBy` is absent from `user/settings.json`. The
> operator wants attribution OFF universally across ALL repos. The repo's own commit/PR skills and
> policies already mandate "no AI attribution," so the gap is a single missing platform setting,
> not prose drift.

## Symptom (verified)

The operator observes Claude attribution trailers (`Co-Authored-By: Claude ...`, `🤖 Generated
with Claude Code`, and the session `Claude-Session:` line) being appended to commits / PR bodies
and wants them OFF for every repo, universally.

The Claude Code platform injects the `Co-Authored-By: Claude <noreply@anthropic.com>` byline and
the "Generated with Claude Code" line automatically unless the `includeCoAuthoredBy` setting is
set to `false`. This is a settings-controlled PLATFORM behavior, independent of skill prose — the
harness's own commit instructions surface these trailers regardless of what `/commit`'s body says.

## Root cause (Concluded)

**Class: missing-contract.** The harness never carried a config contract asserting that Claude's
automatic attribution is globally off. `user/settings.json` (projected to `~/.claude/settings.json`,
the user-level scope that applies to every repo) has **no `includeCoAuthoredBy` key**, so the
platform default (`true` — attribution ON) is in force everywhere.

Evidence:
- `user/settings.json` — no `includeCoAuthoredBy` key present (verified by grep across the repo:
  zero occurrences outside generated `skills-projected/`).
- The repo's behavioral commit/PR surfaces ALREADY forbid AI attribution, so they are not the
  source of the trailers:
  - `user/skills/commit/SKILL.md` lines 77-81: "Do NOT add Co-Authored-By headers ... The commit
    should look like any human-written commit."
  - `user/skills/push/SKILL.md` lines 68, 76: "Do NOT add Co-Authored-By attribution."
  - `.claude/skill-config/commit-policy.md` lines 5-7: "No AI attribution. Do NOT append
    `Co-Authored-By: Claude` or any 'Generated with' footer."
  - `repos/algobooth/.claude/skill-config/commit-policy.md` line 9: "no AI attribution."
  - `repos/cognito-forms/.claude/skill-config/commit-policy.md`, `user/skills/write-pr-description/`,
    `user/skills/write-pr-comments/` — no attribution mandate present (clean).

Because the prose surfaces are already aligned, the trailers can only be arriving from the
platform's default-on `includeCoAuthoredBy`. The durable universal fix is to set it `false` at the
user scope; a per-skill prose tweak cannot suppress the platform byline.

## Fix scope

1. **Primary (universal enforcement):** add `"includeCoAuthoredBy": false` to `user/settings.json`
   (→ `~/.claude/settings.json`). The user-level scope applies to every repo, so this disables the
   Co-Authored-By / Generated-with-Claude-Code byline globally — the single mechanism the operator
   directive names as PRIMARY.
2. **Secondary sweep (no changes required):** the grep sweep of skills / components /
   `commit-policy.md` files / PR-body templates found NO active surface that MANDATES an attribution
   trailer — every behavioral surface already forbids it (see Evidence above). The remaining repo
   hits are archived plans / historical bug specs / a research prompt that merely MENTION the
   strings and drive no live behavior. Nothing to neutralize.

## Verification

- `includeCoAuthoredBy: false` present in `user/settings.json`; file is valid JSON.
- Zero `Co-Authored-By` / `Generated with Claude Code` mandate remains on any live commit/PR
  behavioral surface (grep-confirmed).

## Platform-behavior note

The exact key (`includeCoAuthoredBy`, boolean, user-scope `settings.json`, default `true`) is a
stable, long-documented Claude Code setting that controls the Co-Authored-By / Generated-with
byline on commits and PRs. Per the dispatch, `claude-code-guide` verification was requested; this
round runs during a marked pipeline run where the Agent tool is registry-gated (subagent dispatch
prohibited), so the setting is applied on high-confidence knowledge of the documented key rather
than a fresh `claude-code-guide` pass. If a later operator review finds the key name has changed,
it is a one-line settings edit.
