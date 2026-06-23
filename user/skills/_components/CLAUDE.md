# CLAUDE.md — _components/

Shared building blocks injected into skills. A component is a Markdown fragment that one or
more skills pull in verbatim at runtime via:

```
!`cat ~/.claude/skills/_components/<name>.md`
```

This is the DRY layer for the skill system — a protocol several skills must follow lives here
once instead of being copy-pasted into each `SKILL.md`.

## Extract vs inline

- **Extract** a component when the same multi-step protocol is needed by 2+ skills
  (`commit-and-push.md`, `claude-md-review.md`, `adhoc-enqueue.md`) or when a block is large
  enough to dominate the skill.
- **Inline** a step unique to one skill — a component used once is indirection with no payoff.

## After editing

Components expand at runtime, but the projection must be regenerated for validation:

```bash
python ~/.claude/scripts/project-skills.py    # re-expand into skills-projected/
python ~/.claude/scripts/lint-skills.py       # catches broken / circular injections
```

A component may `!cat` another component — `project-skills.py` resolves recursively and flags
cycles. Check the projected `SKILL.md` (not just the component) to confirm the expansion reads
correctly in context.

## Parameterized components

Some components take a `{placeholder}` the consuming skill substitutes (e.g. `{feature_id}` /
`{bug_id}` in `mcp-coverage-audit.md`). The placeholder contract is documented in the component
itself — keep consumers and the component in sync.

## Per-repo overrides

A few components have per-repo variants under `repos/<name>/.claude/skill-config/` (e.g.
`phases-runtime-validation.md`). The generic version here is the fallback; the repo version wins
when present. See `repos/CLAUDE.md`.
