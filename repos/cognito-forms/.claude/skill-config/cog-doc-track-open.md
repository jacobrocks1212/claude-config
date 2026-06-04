Register or refresh work-dashboard tracking for the current item via `python ~/.claude/scripts/track-work.py open` (writes/refreshes a `WIP.md` liveness marker in the item's cog-docs directory and regenerates DASHBOARD.md). Non-fatal: when nothing resolves it exits 0 and writes nothing — never block on its result.

Pass what you know, so resolution works without any lazy-pipeline state:

- If this invocation references a work item (bare number, `#id`, `AB#id`, or an ADO URL), add `--wi-id <id>` — it locates the existing `docs/{features,bugs}/<id>-*/` directory in cog-docs.
- If you already know the item's cog-docs directory name (e.g. you are working against `docs/bugs/56650-save-crash/`), add `--slug <dir-name>` instead.
- Otherwise run it bare — it falls back to the current `p/<id>-` git branch.

Timing:

- Run it now **only if the item's cog-docs directory already exists** (pre-creation it is a pointless no-op — skip it).
- **If this skill creates the item directory** (writing a new spec under `docs/features/` or `docs/bugs/`), run `python ~/.claude/scripts/track-work.py open --slug <created-dir-name>` immediately after creating it — that is the moment tracking begins.
