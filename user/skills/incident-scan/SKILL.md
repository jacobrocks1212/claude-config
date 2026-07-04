---
name: incident-scan
description: On-demand incident collector — runs incident-scan.py over this repo's deny ledger, hook-events, and breadcrumbs; clusters recurring friction and enqueues bug stubs with INCIDENT.md evidence capsules via the sanctioned ad-hoc path.
argument-hint: [optional "--dry-run" to report proposals without enqueueing]
model: haiku
plan-mode: never
allowed-tools: ["Bash", "Read"]
---

# Incident Scan

On-demand front end for the **incident-auto-capture** collector (`~/.claude/scripts/incident-scan.py`). The script is the source of truth — deterministic clustering (per-signal recurrence bars, dedup against open + archived `incident_key`s, ≤2-per-scan enqueue cap) all live in its top-of-file config, never in this prose. **This skill is pure presentation — run the script, relay its report.**

The `/lazy-batch` family already runs this scan once per run at the end-of-run flush (§1c.6, before `--run-end`); this skill is the between-runs / on-demand path. Scheduling is deferred to `scheduled-autonomous-runs`.

---

## Step 1: Run the collector

If `$ARGUMENTS` contains `--dry-run`, pass it through (report-only, zero writes). Otherwise run the real scan:

```bash
python3 ~/.claude/scripts/incident-scan.py --repo-root . [--dry-run]
```

The script is read-only over its inputs; its only mutations are the sanctioned `lazy-state.py --enqueue-adhoc --type bug` subprocess and the `INCIDENT.md` capsule it seeds beside `ADHOC_BRIEF.md`. Exit 0 with a bare summary line (`incident-scan: 0 clusters observed, …`) is the normal empty-state outcome, not an error.

## Step 2: Relay the report

Print the script's output verbatim:

- the summary line — `incident-scan: {N} clusters observed, {M} cleared the bar, {K} enqueued|would-enqueue, {D} deduped`;
- one `➕ Enqueued ad-hoc bug …` announce line per stub (the adhoc-enqueue component's format);
- any `⚠ over enqueue cap — reported-only:` lines.

For each enqueued stub, optionally `Read` its `docs/bugs/<slug>/INCIDENT.md` and add a one-line gloss (signal class + occurrence count). Do NOT edit the capsule, the queue, or any SPEC — the next bug-pipeline probe routes the stub to `/spec-bug`, which owns root cause.

If the script exits non-zero, print its stderr verbatim and STOP — do not retry or hand-compose an enqueue.

## Notes

- **Never invoked from a cycle subagent.** The enqueue subprocess inherits this session's environment unchanged, so the C3 cycle-containment guard's verdict applies to the real caller; a dispatched subagent must not run this skill to launder an `--enqueue-adhoc` past containment.
- To drop a capture you disagree with: `python3 ~/.claude/scripts/bug-state.py --reorder-queue --id <slug> --to remove` — the collector will not re-enqueue while the dir (and its `incident_key`) exists.
- Thresholds/cap are the D3 config block at the top of `incident-scan.py` (numbers, not judgment); tune there.
