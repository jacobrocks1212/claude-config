# CLAUDE.md — user/skills/

User-level skills available in every repo. Each skill is a Markdown dispatcher at
`<name>/SKILL.md`; Claude Code reads the frontmatter to register it and runs the body when
invoked as `/<name>`. Skills are **prose, not code** — behavior that must be deterministic
belongs in a script (see `../scripts/CLAUDE.md`), not in a skill.

## Frontmatter contract

```yaml
---
name: skill-name              # kebab-case, matches the dir name, invoked as /skill-name
description: One-line purpose  # shown in the picker — make it trigger-rich
argument-hint: <what to pass>  # optional
plan-mode: never | required | flag
model: opus | sonnet | haiku  # optional override
allowed-tools: [...]          # optional restriction
---
```

## Component injection

Shared logic lives in `_components/` and is pulled into a skill at runtime with:

```
!`cat ~/.claude/skills/_components/<name>.md`
```

Claude Code expands this inline when the skill runs. See `_components/CLAUDE.md` for the
extract-vs-inline rule.

**After editing any `SKILL.md` or `_components/` file, re-project and lint:**

```bash
python ~/.claude/scripts/project-skills.py     # expand !cat refs → skills-projected/
python ~/.claude/scripts/lint-skills.py        # broken injections, embedded patterns
```

An unresolved `!cat` or a circular include only shows up in the projected output — spot-check it.

## Coupled pairs — edit BOTH or break the invariant

Some skills share a state machine with a sibling. Editing one without the other silently
desyncs them.

| Pair | Sibling location | Rule |
|------|-----------------|------|
| `/lazy` ↔ `/lazy-cloud` | `repos/algobooth/.claude/skills/lazy-cloud/` | Thin wrappers around `lazy-state.py`; only intended divergence is `--cloud`. |
| `/lazy-batch` ↔ `/lazy-batch-cloud` | `repos/algobooth/.claude/skills/lazy-batch-cloud/` | Orchestrators; cloud divergences are tabulated in the cloud skill's "Differences" block. |
| lazy-bug family | `user/skills/lazy-bug*` | Mirrors the base lazy trio over `bug-state.py`. **Run the parity audit before editing** — see `../scripts/CLAUDE.md`. |

When editing either half, diff the sibling immediately afterward and confirm it matches intent.
**State-machine changes go in the script, not the wrapper prose.**

## User-level vs repo-scoped

Skills here load everywhere. Repo-specific skills live in `repos/<name>/.claude/skills/` and
only load in that repo (e.g. `lazy-cloud`, `csharp-cognito`). Put a skill here only if it's
genuinely repo-agnostic.
