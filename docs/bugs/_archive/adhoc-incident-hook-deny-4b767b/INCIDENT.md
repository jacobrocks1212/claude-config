---
kind: incident-capture
incident_key: claude-config|hook-deny|lazy-cycle-containment|lazy-batch-invocation
signal_class: hook-deny
occurrences: 8
window: 24h
first_ts: 2026-07-04T18:10:15Z
last_ts: 2026-07-04T18:37:27Z
---

# Incident Evidence

Raw matching ledger/event lines (verbatim, newest last; capped at 20):

```
{"ts": 1783188615.2017124, "kind": "deny", "hook": "lazy-cycle-containment", "repo_root": "/home/user/claude-config", "signature": "lazy-batch-invocation", "detail": "you are a single cycle subagent \u2014 STOP after your commit+push+report; routing the next cycle is the orchestrator's job. This op (lazy-state.py routing/lifecycle, dev:kill/restart, recursive Agent dispatch, or a second-feature/over-ceiling commit) is DENIED in-flight while a cycle dispatch is active."}
{"ts": 1783189127.5638914, "kind": "deny", "hook": "lazy-cycle-containment", "repo_root": "/home/user/claude-config", "signature": "lazy-batch-invocation", "detail": "you are a single cycle subagent \u2014 STOP after your commit+push+report; routing the next cycle is the orchestrator's job. This op (lazy-state.py routing/lifecycle, dev:kill/restart, recursive Agent dispatch, or a second-feature/over-ceiling commit) is DENIED in-flight while a cycle dispatch is active."}
{"ts": 1783189147.3000813, "kind": "deny", "hook": "lazy-cycle-containment", "repo_root": "/home/user/claude-config", "signature": "lazy-batch-invocation", "detail": "you are a single cycle subagent \u2014 STOP after your commit+push+report; routing the next cycle is the orchestrator's job. This op (lazy-state.py routing/lifecycle, dev:kill/restart, recursive Agent dispatch, or a second-feature/over-ceiling commit) is DENIED in-flight while a cycle dispatch is active."}
{"ts": 1783189801.352221, "kind": "deny", "hook": "lazy-cycle-containment", "repo_root": "/home/user/claude-config", "signature": "lazy-batch-invocation", "detail": "you are a single cycle subagent \u2014 STOP after your commit+push+report; routing the next cycle is the orchestrator's job. This op (lazy-state.py routing/lifecycle, dev:kill/restart, recursive Agent dispatch, or a second-feature/over-ceiling commit) is DENIED in-flight while a cycle dispatch is active."}
{"ts": 1783189826.53144, "kind": "deny", "hook": "lazy-cycle-containment", "repo_root": "/home/user/claude-config", "signature": "lazy-batch-invocation", "detail": "you are a single cycle subagent \u2014 STOP after your commit+push+report; routing the next cycle is the orchestrator's job. This op (lazy-state.py routing/lifecycle, dev:kill/restart, recursive Agent dispatch, or a second-feature/over-ceiling commit) is DENIED in-flight while a cycle dispatch is active."}
{"ts": 1783189834.4206944, "kind": "deny", "hook": "lazy-cycle-containment", "repo_root": "/home/user/claude-config", "signature": "lazy-batch-invocation", "detail": "you are a single cycle subagent \u2014 STOP after your commit+push+report; routing the next cycle is the orchestrator's job. This op (lazy-state.py routing/lifecycle, dev:kill/restart, recursive Agent dispatch, or a second-feature/over-ceiling commit) is DENIED in-flight while a cycle dispatch is active."}
{"ts": 1783190231.5843563, "kind": "deny", "hook": "lazy-cycle-containment", "repo_root": "/home/user/claude-config", "signature": "lazy-batch-invocation", "detail": "you are a single cycle subagent \u2014 STOP after your commit+push+report; routing the next cycle is the orchestrator's job. This op (lazy-state.py routing/lifecycle, dev:kill/restart, recursive Agent dispatch, or a second-feature/over-ceiling commit) is DENIED in-flight while a cycle dispatch is active."}
{"ts": 1783190247.338311, "kind": "deny", "hook": "lazy-cycle-containment", "repo_root": "/home/user/claude-config", "signature": "lazy-batch-invocation", "detail": "you are a single cycle subagent \u2014 STOP after your commit+push+report; routing the next cycle is the orchestrator's job. This op (lazy-state.py routing/lifecycle, dev:kill/restart, recursive Agent dispatch, or a second-feature/over-ceiling commit) is DENIED in-flight while a cycle dispatch is active."}
```

Captured by `incident-scan.py` (incident-auto-capture). The collector proposes evidence; `/spec-bug` owns root cause. Severity is the enqueue default — the collector never sets it.
