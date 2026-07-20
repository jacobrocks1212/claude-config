---
kind: incident-capture
auto_generated: true
auto_generated_origin: incident-capture
incident_key: claude-config|hook-deny|cycle-subagent-bg-gate-guard|CYCLE-BG-GATE-FOREGROUND
signal_class: hook-deny
occurrences: 3
window: 24h
first_ts: 2026-07-19T15:20:09Z
last_ts: 2026-07-20T03:32:07Z
---

# Incident Evidence

Raw matching ledger/event lines (verbatim, newest last; capped at 20):

```
{"ts": 1784474409.4708984, "kind": "deny", "hook": "cycle-subagent-bg-gate-guard", "repo_root": "C:\\Users\\Jacob\\source\\repos\\claude-config", "signature": "CYCLE-BG-GATE-FOREGROUND", "detail": "cd C:/Users/Jacob/source/repos/claude-config && python -m pytest user/scripts/tests/test_lazy_core/ -q 2>&1 | tail -6; echo \"LAZYCORE_EXIT=${PIPESTATUS[0]}\""}
{"ts": 1784474697.512333, "kind": "deny", "hook": "cycle-subagent-bg-gate-guard", "repo_root": "C:\\Users\\Jacob\\source\\repos\\claude-config", "signature": "CYCLE-BG-GATE-FOREGROUND", "detail": "cd C:/Users/Jacob/source/repos/claude-config/user/scripts && python -m pytest tests/test_lazy_core/ -q 2>&1 | tail -8"}
{"ts": 1784518327.259714, "kind": "deny", "hook": "cycle-subagent-bg-gate-guard", "repo_root": "C:\\Users\\Jacob\\source\\repos\\claude-config", "signature": "CYCLE-BG-GATE-FOREGROUND", "detail": "cd \"C:/Users/Jacob/source/repos/claude-config\" && python3 user/scripts/gate-battery.py > /tmp/gate-battery-final.log 2>&1; echo \"EXIT:$?\" >> /tmp/gate-battery-final.log"}
```

Captured by `incident-scan.py` (incident-auto-capture). The collector proposes evidence; `/spec-bug` owns root cause. Severity is the enqueue default — the collector never sets it.
