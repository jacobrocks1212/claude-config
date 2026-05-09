### Subagent D: Runtime Evidence (if available)

**Only launch if** runtime evidence is available (running app, test output, logs).

**Prompt:** Collect runtime evidence related to the issue.

1. If the app is running: query available diagnostic endpoints or APIs for recent errors, state, and events
2. If logs exist: find the most recent log files, read the last 200 lines, look for errors or anomalies
3. If analysis scripts exist: run them and read the output
4. Look for: error events, anomalies, unexpected state, missing expected events

Report format: raw evidence with annotations about what's normal vs abnormal.
