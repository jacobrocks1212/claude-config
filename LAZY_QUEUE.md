# Lazy Queue — claude-config   (run active 🔒)

## Features (0)


## Bugs (1)

| # | item | state | sev |
|---|------|-------|------|
| 1 | [adhoc-derive-cycle-commit-budget](docs/bugs/adhoc-derive-cycle-commit-budget/SPEC.md) | Validate | — |
| | status: Validate · next: run mcp-test · The hand-maintained `_CYCLE_COMMIT_BUDGET` allow-list in `lazy_core.py` silently defaults any unenumerated multi-commit sub_skill to budget 1, false-positiving `unexpected-commits` at `--cycle-end`. | | |
