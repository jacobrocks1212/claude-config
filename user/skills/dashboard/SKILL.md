---
name: dashboard
description: Regenerate the work-status markdown dashboard from the local ADO mirror. Pass --refresh to live-poll ADO first; pass --all-team to include older terminal items.
argument-hint: "[--refresh] [--all-team] [--feature <id>] [--out <path>]"
plan-mode: never
---

# Dashboard — Render Work-Status Dashboard

Renders a markdown dashboard from the local ADO mirror at `cog-docs` and writes it to `DASHBOARD.md`. Default (no `--refresh`) is fast and offline — it just re-renders from the existing mirror. Pass `--refresh` to live-poll ADO before rendering.

Scripts live at `C:/Users/JacobMadsen/source/repos/claude-config/user/scripts/`.
Mirror + rendered doc live under `C:/Users/JacobMadsen/source/repos/cog-docs/`.

---

## Step 1: Parse Arguments

Tokenize `$ARGUMENTS` on whitespace:

- `--refresh` → run a live ADO poll before rendering (see Step 3).
- `--all-team` → pass through to `work-status.py` (includes terminal items older than 5 days).
- `--feature <id>` → pass through to `work-status.py`; overrides the config `active_feature_id` and pins that feature's children as the priority queue.
- `--out <path>` → pass through to `work-status.py` (overrides the default output path).

Unknown tokens are an error: report them and STOP.

---

## Step 2: Set Environment

Always set `PYTHONUTF8=1` before running any Python command. On Windows the default cp1252 encoding will crash on Unicode characters in ADO titles or comments.

```
export PYTHONUTF8=1
```

All subsequent `python` calls in this session inherit this setting.

---

## Step 3: Refresh Mirror (only if `--refresh` was passed)

Run the live ADO poll:

```
cd "C:/Users/JacobMadsen/source/repos/claude-config/user/scripts"
python ado-sync.py --once --repo-root "C:/Users/JacobMadsen/source/repos/cog-docs"
```

Notes:
- This is a **read-only** live call to Azure DevOps — it requires the keyring PAT to be present.
- If it exits non-zero or prints an error, **surface the error verbatim and STOP**. Do not silently fall through to rendering a stale doc.
- If `--refresh` was NOT passed, skip this step entirely.

---

## Step 4: Render Dashboard

Run the renderer from the scripts directory:

```
cd "C:/Users/JacobMadsen/source/repos/claude-config/user/scripts"
python work-status.py --markdown --repo-root "C:/Users/JacobMadsen/source/repos/cog-docs" [--all-team] [--feature <id>] [--out <path>]
```

Pass through `--all-team`, `--feature <id>`, and/or `--out <path>` exactly as received from `$ARGUMENTS`. Omit flags that were not supplied.

The script writes `DASHBOARD.md` atomically and also prints a terminal summary to stdout.

---

## Step 5: Report

Report:
- **Output path**: `C:/Users/JacobMadsen/source/repos/cog-docs/docs/work/DASHBOARD.md` (or the `--out` path if overridden).
- **One-line summary**: extract the synced timestamp and item count from the script's stdout and include them in the report (e.g. "Synced 2026-06-02 14:32 · 12 items").
