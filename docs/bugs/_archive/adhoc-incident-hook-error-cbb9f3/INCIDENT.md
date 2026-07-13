---
kind: incident-capture
incident_key: claude-config|hook-error|long-build-ownership-guard
signal_class: hook-error
occurrences: 2
window: 7d
first_ts: 2026-07-12T04:30:07Z
last_ts: 2026-07-13T03:17:13Z
---

# Incident Evidence

Raw matching ledger/event lines (verbatim, newest last; capped at 20):

```
{"ts": 1783830607.902566, "kind": "error", "hook": "long-build-ownership-guard", "repo_root": "C:/Users/Jacob/source/repos/claude-config", "signature": "", "detail": "Expecting ',' delimiter: line 1 column 57 (char 56)"}
{"ts": 1783912633.425099, "kind": "error", "hook": "long-build-ownership-guard", "repo_root": "C:/Users/Jacob/source/repos/claude-config", "signature": "", "detail": "Expecting value: line 1 column 1 (char 0)"}
```

Captured by `incident-scan.py` (incident-auto-capture). The collector proposes evidence; `/spec-bug` owns root cause. Severity is the enqueue default — the collector never sets it.
