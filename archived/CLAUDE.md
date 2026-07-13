# CLAUDE.md — archived/

Deprecated config kept for audit trail and git archaeology — **not loaded by anything**. Safe to
read; don't revive in place.

| Archived | Replaced by | When |
|----------|-------------|------|
| `user-skills/implement-phase`, `user-skills/implement-phase-batch` | The canonical v2 skills of the same name now in `user/skills/` | `fd3ef2f` — "canonicalize v2 skills, archive old versions, rename mobile to write-plan" |
| `cognito-pr-review-v1-agents/` (six v1 agents: `cognito-architecture`, `cognito-frontend`, `cognito-api-design`, `cognito-behavior`, `cognito-test-coverage`, `review-synthesizer`) | The v2 pipeline agents in `user/plugins/local-tools/plugins/cognito-pr-review/agents/` (`investigation`, `sweep`, `triage`, `journey-planner`, `synthesizer-v2`, the two consistency checkers) — no pipeline command dispatched the v1 set, and session logs showed them causing misrouting | 2026-07-09 — feature `pr-review-plugin-repo-scoping-and-orphan-purge` |
| `cognito-pr-review-v1-agents/code-review-rules.md` | `user/plugins/local-tools/plugins/cognito-pr-review/knowledge/rules/*.yaml` (the per-category rule corpus) | 2026-07-09 — same feature |
| `calibrate-weights.ts` (bulk artifact-vs-ADO-comment calibration) | `user/plugins/local-tools/plugins/cognito-pr-review/scripts/disposition-calibration.ts` (the single surgical, comment-preserving calibration writer) — the bulk script was orphaned, destroyed YAML comments via `yaml.dump`, hardcoded machine paths, and its artifact parser predated the Standardized Issue Block format | 2026-07-09 — bug `pr-review-ema-calibration-statistical-design-drives-lane-death` (fix 6) |
| `block-work-repo-git-writes.sh` | `user/hooks/block-work-repo-git-push.sh` (the live successor covers the work-repo push case; the commit-blocking half was never registered) | 2026-07-12 — bug `legacy-tool-input-env-hooks-dead` (SPEC D1). Shared the `$TOOL_INPUT_command` dead-code defect and was already unregistered by documented decision; retired to `archived/` rather than given a third stdin-JSON rewrite |
| `user-skills/_components/interview-relevance.md` | No replacement — no consumer | 2026-07-12 — bug `skills-plane-hygiene-debris` (SPEC D1). Orphaned — no `!cat` reference from any `SKILL.md`/`skill-config` since at least the SPEC's 2026-07-11 grep sweep (zero hits across `user/`, `docs/`, `plugins/`, `repos/*/.claude/`) |
| `user-skills/_components/parallel-implementation.md` | No replacement — no consumer | 2026-07-12 — bug `skills-plane-hygiene-debris` (SPEC D1). Orphaned — no `!cat` reference from any `SKILL.md`/`skill-config` since at least the SPEC's 2026-07-11 grep sweep (zero hits across `user/`, `docs/`, `plugins/`, `repos/*/.claude/`) |
| `user-skills/_components/post-compact-reread.md` | No replacement — no consumer | 2026-07-12 — bug `skills-plane-hygiene-debris` (SPEC D1). Orphaned — no live `!cat` reference from any shipped `SKILL.md` (only historical mentions survive: `docs/features/plan-skills-redesign/IMPLEMENTATION_NOTES.md` records it as a past notes-mining sweep target, and `docs/specs/spec-buddy/SPEC.md` names it as a planned-reuse row the shipped `spec-buddy/SKILL.md` never adopted) |

When you deprecate a skill, **move it here (don't delete)** and add a row above with its
replacement, so the supersession stays traceable.
