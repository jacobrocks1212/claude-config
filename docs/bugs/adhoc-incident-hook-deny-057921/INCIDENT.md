---
kind: incident-capture
incident_key: claude-config|hook-deny|lazy-cycle-containment|second-feature-commit
signal_class: hook-deny
occurrences: 3
window: 24h
first_ts: 2026-07-19T03:38:49Z
last_ts: 2026-07-19T08:17:57Z
---

# Incident Evidence

Raw matching ledger/event lines (verbatim, newest last; capped at 20):

```
{"ts": 1784432329.2730925, "kind": "deny", "hook": "lazy-cycle-containment", "repo_root": "C:\\Users\\Jacob\\source\\repos\\claude-config", "signature": "second-feature-commit", "detail": "second-feature commit tripwire: staged path(s) ['docs/bugs/adhoc-decision-key-relative-absolute-mismatch/FIXED.md', 'docs/bugs/adhoc-decision-key-relative-absolute-mismatch/SPEC.md', 'docs/bugs/adhoc-subagent-wedge-hook-overfires-globs-all-plans/FIXED.md', 'docs/bugs/adhoc-subagent-wedge-hook-overfires-globs-all-plans/SPEC.md'] are under a different feature than the active dispatch ('concurrent-worktree-agent-coordination'). you are a single cycle subagent \u2014 STOP after your commit+push+report; r"}
{"ts": 1784448777.8712733, "kind": "deny", "hook": "lazy-cycle-containment", "repo_root": "C:\\Users\\Jacob\\source\\repos\\claude-config", "signature": "second-feature-commit", "detail": "second-feature commit tripwire: staged path(s) ['docs/bugs/merged-head-oracle-deadlocks-on-unreached-parked-same-pipeline-head/FIXED.md', 'docs/bugs/merged-head-oracle-deadlocks-on-unreached-parked-same-pipeline-head/GATE_VERDICT.md', 'docs/bugs/merged-head-oracle-deadlocks-on-unreached-parked-same-pipeline-head/SPEC.md'] are under a different feature than the active dispatch ('byref-updatedinput-unapplied-on-background-agent-dispatch'). you are a single cycle subagent \u2014 STOP after your commit+p"}
{"ts": 1784449077.4805324, "kind": "deny", "hook": "lazy-cycle-containment", "repo_root": "C:\\Users\\Jacob\\source\\repos\\claude-config", "signature": "second-feature-commit", "detail": "second-feature commit tripwire: staged path(s) ['docs/bugs/merged-head-oracle-deadlocks-on-unreached-parked-same-pipeline-head/FIXED.md', 'docs/bugs/merged-head-oracle-deadlocks-on-unreached-parked-same-pipeline-head/GATE_VERDICT.md', 'docs/bugs/merged-head-oracle-deadlocks-on-unreached-parked-same-pipeline-head/SPEC.md'] are under a different feature than the active dispatch ('byref-updatedinput-unapplied-on-background-agent-dispatch'). you are a single cycle subagent \u2014 STOP after your commit+p"}
```

Captured by `incident-scan.py` (incident-auto-capture). The collector proposes evidence; `/spec-bug` owns root cause. Severity is the enqueue default — the collector never sets it.
