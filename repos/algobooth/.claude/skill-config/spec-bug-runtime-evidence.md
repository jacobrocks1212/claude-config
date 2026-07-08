### Subagent D: Runtime Evidence (if available)

**Only launch if** session logs exist or the app is running.

**Prompt:** Collect runtime evidence related to the issue.

1. If app is running (`localhost:3333/health` responds): query `get_session_meta`, `get_session_events`, `get_console_errors`
2. If session logs exist in `logs/session-*/`: find the most recent session directory (NEVER use a cached path — always re-resolve via filesystem: `ls logs/session-* | sort | tail -1`), read the last 200 lines of `session.jsonl`
3. If the analysis script exists: run `npx tsx scripts/analyze-session.ts <session_dir>/` and read the summary
4. Look for: error events, anomalies, unexpected state, missing expected events

Report format: raw evidence with annotations about what's normal vs abnormal.
