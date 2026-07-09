# Subagent Baseline: Skill-Surface Bloat — Investigation Spec

> Every session and subagent in every repo carries the full 89-entry user-level skill list (~24KB of descriptions ≈ ~6k tokens), including skills whose subject projects no longer exist locally.

**Status:** Fixed
**Fixed:** 2026-07-09 (in-session, outside the bug-pipeline queue — no FIXED.md receipt by design)
**Severity:** P2
**Discovered:** 2026-07-09
**Placement:** docs/bugs/subagent-baseline-skill-surface-bloat
**Related:** docs/bugs/subagent-baseline-cognito-plugin-scoping, docs/bugs/subagent-baseline-claude-md-diet (same incident: Cognito subagent 50–70k token baseline)

---

## Verified Symptoms

1. **[VERIFIED]** Cognito Forms sessions start at 63–74k input tokens; subagents median 36k, max 64k — measured from `~/.claude/projects/*Cognito*Forms*/**/*.jsonl` first-turn `usage` blocks (n=48 subagents, n=12 mains, CC v2.1.205). Reported by operator as "~50–70k baseline"; measurement corroborates.
2. **[VERIFIED]** The user-level skills tree contributes 89 skill entries totaling 23,855 description bytes (≈6k tokens with names/formatting) to every system prompt, including all subagents that carry the Skill tool — measured by frontmatter inventory over `user/skills/*/SKILL.md`.
3. **[VERIFIED]** A large fraction of those skills target projects that no longer exist on this machine: the live `algobooth` repo was deleted (manifest.psd1:25–29 documents this deliberately), and there is no local `maestro`, `work-dashboard`, `strudel`, `scene-remixer`, or `mixmi` repo (`ls ~/source/repos` — workspace is now almost entirely Cognito work repos). Skills like `mixmi-mixer-architecture`, `build-js`, `restart-windows-claude`, `web-audio`, `tauri-patterns`, `rust-*` are injected into every Cognito subagent regardless.
4. **[VERIFIED]** `local-site` (454-byte description) is Cognito-specific but lives at user scope, so it is injected into non-Cognito repos too.

## Reproduction Steps

1. Open any Claude Code session in `~/source/repos/Cognito Forms` (or -B/-C/-D).
2. Run `/context` (or inspect the session `.jsonl` first assistant turn's `usage`).
3. Observe ~63–74k input tokens before any work; the skills list section enumerates all 89 user skills + 27 repo skills + plugin skills.

**Expected:** Only skills relevant to the current repo (or at least, compact descriptions) consume baseline context.
**Actual:** Full verbose skill list injected everywhere, including into every subagent.
**Consistency:** Always (structural).

## Evidence Collected

- Description-size inventory (top offenders): `lazy` 824B, `mermaid-diagrams` 731B, `lazy-bug` 723B, `lazy-batch-parallel` 599B, `lazy-bug-batch` 589B, `lazy-batch` 587B, `plan-bug` 564B, `lazy-batch-retro` 563B, `retro` 497B, `harden-harness` 496B, `human-writing` 464B, `local-site` 454B, `architecture-patterns` 447B, `plugin-structure` 433B, `monorepo-management` 431B, `ingest-research` 429B, `code-review-excellence` 420B, `typescript-advanced-types` 408B, `investigate` 397B, `tailwind-design-system` 396B, … (89 skills, 23,855B total).
- Both `~/.claude/skills` and `~/.claude-personal/skills` are **directory symlinks to `claude-config/user/skills`** (verified with `os.path.islink`) — a single shared tree. The workspace CLAUDE.md claim that they are "hardlinked" files is stale (fixed under the claude-md-diet sibling bug). Consequence: a naive "move personal skills to the personal tree" split is impossible without restructuring the Personal manifest scope — the personal profile would lose all shared skills.
- The `/lazy*` family descriptions are the fattest, yet these skills are only ever invoked explicitly by name (slash command or orchestrator `Skill` dispatch) — their descriptions are not a routing surface, so they compress safely. Their SKILL.md **bodies** are parity-audited (`lazy_parity_audit.py`), so any frontmatter edit must be followed by a parity-audit run.

## Proven Findings

**Cause (traced):** skill-list token cost is a direct function of `user/skills/<name>/SKILL.md` frontmatter `description:` bytes and of skill placement (user scope = injected everywhere; `repos/<name>/.claude/skills/` = injected only in that repo).
Serving path: `user/skills/*/SKILL.md` frontmatter → `~/.claude/skills` symlink (manifest.psd1:4) → harness system-prompt "available skills" list (present in main sessions and all subagents carrying the Skill tool) → measured first-turn `usage.input_tokens`. Fix sites (description text; skill directory placement) are both on this path.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Skill descriptions | `user/skills/*/SKILL.md` (top ~35 verbose) | ~10–13KB of injected text removable with no availability change |
| Cognito-only skill at user scope | `user/skills/local-site/` | Injected into all repos; belongs in `repos/cognito-forms/.claude/skills/` (manifest DotClaudeDirs already links `skills`) |
| Dead-project skills | `mixmi-mixer-architecture`, `build-js`, `restart-windows-claude`, `web-audio`, `three-best-practices`, `remotion`, `tauri-patterns`, `rust-*` | Candidates for archival — **not executed here** (cloud AlgoBooth sessions bootstrap user skills via `setup.py --target User`, so archival could break active nightly runs; needs operator decision backed by `skill-usage-miner.py`) |

## Fix Scope

1. Compress the descriptions of the ~35 most verbose skills to ≤ ~180 bytes each, preserving trigger keywords ("USE WHEN…", key nouns) so auto-invoke recall survives.
2. `git mv user/skills/local-site repos/cognito-forms/.claude/skills/local-site` (repo-scoping; symlinks already cover all four worktrees).
3. Post-edit validation: `lint-skills.py`, `project-skills.py`, `lazy_parity_audit.py --repo-root .` must stay clean.
4. Archival of dead-project skills: **deferred to operator** — run `python user/scripts/skill-usage-miner.py --markdown` and review its propose-only archival blocks.

## Open Questions

- Whether cloud AlgoBooth nightly runs actually consume `web-audio`/`tauri-patterns`/`rust-*` (miner's cloud-usage blind spot) — blocks the archival follow-up, not this fix.

## Fix Applied

1. **41 skill descriptions compressed**: 16,290 → 7,520 bytes (−8,770B, −54% across the edited set; skill-list description total 23,855 → 15,085B). Trigger keywords ("USE WHEN", key nouns/phrases) preserved in every rewrite; `/lazy*` family compressed most aggressively since they are only ever invoked explicitly by name.
2. **`local-site` moved to repo scope**: `git mv user/skills/local-site repos/cognito-forms/.claude/skills/local-site` — now injected only in Cognito worktrees.
3. **Validation green**: `lazy_parity_audit.py` exit 0, `lint-skills.py` OK, `doc-drift-lint.py` 0 findings, `project-skills.py` regenerated (skill count now 88 at user scope).
4. Archival of dead-project skills deliberately **not** executed — deferred to operator with `skill-usage-miner.py` evidence, per Affected Area.
