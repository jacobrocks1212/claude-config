---
kind: adhoc-brief
bug_id: adhoc-process-friction-detector-counts-concurrent-session-commits
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: process-friction unexpected-commits detector counts concurrent same-branch session commits

detect_cycle_bracket_friction's unexpected-commits check (branch 3) counts ALL commits on HEAD between --cycle-begin (begin_head_sha) and --cycle-end, then compares against the per-sub_skill commit budget. When a SECOND session (e.g. the operator working interactively, or a concurrent /lazy-batch lane) commits to the SAME branch (main) during a cycle's window, those foreign commits inflate the count and trip a FALSE unexpected-commits process-friction — which then becomes pending_hardening debt that withholds the forward route. Live case 2026-07-18: an execute-plan part-1 cycle for shared-hook-lib showed '30 commits since --cycle-begin (budget=8)'; 28 of them were the operator's concurrent session marking-fixed+archiving 28 Concluded/Superseded/Wont-fix bugs (provenance: operator-directed-interactive). Adjacent already-fixed defect: gate-scope-folds-concurrent-harden-commits (same concurrent-commit blind spot in harness-gate scope). Fix: attribute commits to THIS cycle before counting — e.g. count only commits whose author-session/committer matches the cycle, or exclude commits reachable from the run marker's other-session activity, or bound the count by the cycle's own dispatch (a cycle subagent's commits are on its own working tree/agent_id). At minimum, filter commit authorship/session so a concurrent same-branch session's commits don't count against another cycle's budget. Origin: /lazy-batch run 2026-07-18.
