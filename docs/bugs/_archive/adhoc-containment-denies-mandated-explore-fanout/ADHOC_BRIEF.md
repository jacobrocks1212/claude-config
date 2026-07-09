---
kind: adhoc-brief
bug_id: adhoc-containment-denies-mandated-explore-fanout
enqueued_by: lazy-adhoc
date: 2026-07-09
---

# Ad-hoc bug: Containment hook denied mandated Explore fan-out in subagent runs

The lazy-cycle-containment.sh D4 arming-free agent_id trip blanket-denied Agent/Task dispatch from ANY subagent, making the touchpoint-audit-gate mandatory Explore fan-out structurally unsatisfiable in every subagent-context planning run (observed live 2026-07-09: a sandboxed /write-plan-cognito Opus subagent had both Explore dispatches denied with no cycle marker present and fell back to inline Read/Grep). The harness itself DOES allow nested dispatch (verified: the subagent Agent tool_use reached the PreToolUse layer). Operator-directed fix already applied in-session 2026-07-09: the Agent/Task recursion deny was removed from the hook (routing/lifecycle, /lazy* Skill, nested-batch, dev-kill and marker-gated commit tripwires all retained), the Agent matcher registration was dropped from user/settings.json, the root CLAUDE.md hooks row updated, and test_hooks.py recursion tests inverted to allow-assertions (130/131 green; the WSL pipe test failure is environmental). Remaining work for this bug item: verify no other doc/prose surface still claims the recursion deny exists (cycle-base-prompt, SPEC/PHASES of hardening-blind-to-process-friction D4, lazy-batch prose, C2/C3 lockstep comments in lazy_core CYCLE_REFUSED_OPS docs), reconcile the touchpoint-audit-gate exit-check wording (every-touchpoint-verified-by-Explore-agent) with contexts where fan-out is legitimately unavailable, and confirm the C3 refuse-by-construction scope comment (which claims lockstep with the C2 deny set) is updated to reflect the narrowed C2 set.
