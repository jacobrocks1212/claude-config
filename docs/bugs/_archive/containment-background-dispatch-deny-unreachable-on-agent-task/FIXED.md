---
kind: fixed
feature_id: containment-background-dispatch-deny-unreachable-on-agent-task
date: 2026-07-19
provenance: backfilled-unverified
validated_via: test_hooks.py 287/287 (incl. new test_containment_registered_on_agent_task_matcher wiring-regression) + test_lazy_core pytest package 1336 passed + lazy-state/bug-state --test smoke + doc-drift-lint clean; harden(hook) commit 0c2ccb0b, NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

`containment-background-dispatch-deny-unreachable-on-agent-task` marked Fixed on 2026-07-19 via
hardening Round 117 — an OUT-OF-PIPELINE `harden(hook)` fix (commit `0c2ccb0b`), not the bug
pipeline's gated `__mark_fixed__` path. Provenance is `backfilled-unverified` accordingly.

## Fix

Registered `user/hooks/lazy-cycle-containment.sh` on the `Agent|Task` PreToolUse matcher in
`user/settings.json`, making the Round-28 (`a43808e`) `background-dispatch` deny branch reachable
in production. The branch was dead code because the hook was registered only on `Bash|PowerShell`
and `Skill` — a PreToolUse hook only fires for its registered tool matchers, so it never received
the `Agent`/`Task` tool calls its deny inspects. Root cause class: `hook-defect` (registration gap).

Foreground subagent Agent/Task dispatch and main-thread background dispatch stay ALLOWED; only a
`run_in_background: true` dispatch from a cycle subagent (`agent_id` present) is denied with the
corrective redirecting to synchronous dispatch-and-await — closing the planning-fan-out deadlock
(a child→parent message that can never arrive).

## Verification

- NEW wiring-regression meta-test `test_containment_registered_on_agent_task_matcher`
  (`user/scripts/test_hooks.py`) — non-vacuous: before the settings.json edit the covered matcher
  set is {Bash, PowerShell, Skill}, missing {Agent, Task} → the assertion fails; GREEN after. This
  is the durable half the Round-28 branch tests lacked (they invoked the script directly and never
  asserted wiring).
- Existing `test_containment_denies_background_subagent_dispatch` /
  `test_containment_allows_foreground_subagent_dispatch` /
  `test_containment_allows_main_thread_background_dispatch` remain GREEN (behavior unchanged; now
  reachable).
- Full gate battery green: test_hooks.py 287/287, test_lazy_core 1336 passed, lazy-state/bug-state
  `--test` smoke pass, lint-skills OK, doc-drift-lint 0 drift, bug-state `--fsck` ok.
