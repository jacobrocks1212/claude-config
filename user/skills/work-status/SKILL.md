---
name: work-status
description: Read-only cross-source work dashboard summarizing My queue, In flight, My ADO inbox, Team, and Pool & sync health.
argument-hint: [optional: "--markdown" to write DASHBOARD.md]
model: haiku
plan-mode: never
allowed-tools: ["Bash", "Read"]
---

# Work Status

Read-only dashboard aggregating work state from multiple sources. Runs `work-status.py`, formats its output into five panels, and optionally writes the result to `docs/work/DASHBOARD.md`. **This skill is pure presentation — all aggregation logic lives in the script.**

Do NOT modify any artifact other than `DASHBOARD.md` (only under `--markdown`).

---

## Step 0: Parse Arguments

If `$ARGUMENTS` contains `--markdown`, pass `--markdown` to the script. Otherwise run without it.

The `--markdown` flag causes the script to also write `docs/work/DASHBOARD.md` inside the `cog-docs` repo. Terminal output is produced in both cases.

---

## Step 1: Run work-status.py

```bash
COG_DOCS="C:\Users\JacobMadsen\source\repos\cog-docs"
python "$HOME/.claude/scripts/work-status.py" --repo-root "$COG_DOCS" [--markdown]
```

Capture stdout. If the script exits non-zero, print its error verbatim and STOP — do not try to format malformed output.

The script degrades gracefully when source files (leases, materialized, queue, mirror) are absent — missing sources produce empty panels, not errors.

---

## Step 2: Format and Display the Five Panels

The script output is organized into five panels. Present them in order:

### Panel 1 — My Queue
Items queued or assigned to me. For each item, the script surfaces a self-authored PR link when the branch name matches the regex `^p/(\d+)-` (the leading `p/` + work-item-ID prefix convention). Shows title, WI ID, PR link (if any), and status.

### Panel 2 — In Flight
Active worker leases. Each row shows: `worker_pid`, slot, pipeline stage, heartbeat age, and a `STALE` flag when the heartbeat age exceeds the staleness threshold. Useful for detecting hung or zombie workers.

### Panel 3 — My ADO Inbox
Azure DevOps work items assigned to me that have NOT yet been materialized into the local work mirror. These are the "unacknowledged" incoming items that exist in ADO but are not yet tracked locally.

### Panel 4 — Team
Teammates' work items with their current `pr` link, `prStatus` (e.g. open/merged/draft), and `autotestStatus` from the local work mirror. Gives a quick view of the team's in-progress work without querying ADO live.

### Panel 5 — Pool & Sync Health
Slot occupancy summary, `syncedAt` timestamp, staleness indicator, and last-poll time. Indicates whether the local mirror is fresh or needs a sync.

---

## Step 3: --markdown Behavior

When `--markdown` is passed, the script writes the formatted dashboard to:

```
C:\Users\JacobMadsen\source\repos\cog-docs\docs\work\DASHBOARD.md
```

The terminal still receives the same output. No other files are written.

---

## Read-Only Safety

This tool NEVER mutates ADO work items, PR state, leases, queue files, or the work mirror. The only write side-effect is `DASHBOARD.md` under `--markdown`. If sources are absent or stale, panels degrade to empty/placeholder rows — the skill never blocks on missing data.

**Do NOT execute any sub-skills or modify any files beyond DASHBOARD.md. Report only.**
