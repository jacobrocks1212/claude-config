---
kind: incident-capture
auto_generated: true
auto_generated_origin: incident-capture
incident_key: claude-config|friction|unexpected-commits
signal_class: friction
occurrences: 2
window: all
first_ts: 2026-07-18T22:56:29Z
last_ts: 2026-07-19T18:13:20Z
---

# Incident Evidence

Raw matching ledger/event lines (verbatim, newest last; capped at 20):

```
{"ts": 1784415389.6054602, "kind": "process-friction", "reason_head": "unexpected-commits", "detail": "HEAD advanced 30 commits since --cycle-begin (begin_head_sha=70caf70f94e7, sub_skill='execute-plan', budget=8)", "acked": true, "run_started_at": "2026-07-18T16:50:52Z", "acked_ts": 1784415869.9805994, "ack_method": "manual-ack", "resolution": "FALSE POSITIVE (operator-confirmed same session): the 30-commit count was the operator's CONCURRENT session marking-fixed/archiving 28 Concluded/Superseded/Wont-fix bugs on main (provenance: operator-directed-interactive), interleaved with shared-hook-lib execute-plan Phase 1/2 \u2014 NOT a runaway cycle. The --cycle-end process-friction detector counts ALL commits on HEAD since --cycle-begin, including a concurrent same-branch session's, over-counting one cycle's budget. Real fix tracked in adhoc-process-friction-detector-counts-concurrent-session-commits."}
{"ts": 1784484800.167909, "kind": "process-friction", "reason_head": "unexpected-commits", "detail": "HEAD advanced 11 commits since --cycle-begin (begin_head_sha=6cd9be290bc3, sub_skill='execute-plan', budget=7)", "acked": true, "run_started_at": "2026-07-19T14:30:33Z", "acked_ts": 1784485074.4997869}
```

Captured by `incident-scan.py` (incident-auto-capture). The collector proposes evidence; `/spec-bug` owns root cause. Severity is the enqueue default — the collector never sets it.
