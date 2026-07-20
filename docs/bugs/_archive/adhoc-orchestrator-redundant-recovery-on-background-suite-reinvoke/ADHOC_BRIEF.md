---
kind: adhoc-brief
bug_id: adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke
enqueued_by: lazy-adhoc
date: 2026-07-19
---

# Ad-hoc bug: Cycle backgrounds long suite + returns 'holding, will re-invoke'; orchestrator dispatches redundant recovery (one-writer risk)

Twice this run an /execute-plan cycle subagent backgrounded its long verification suite and returned a non-result ('suite at 44%, the background waiter will re-invoke me, holding') instead of foreground-awaiting it, violating the turn-end foreground-await contract in cycle-base-prompt.md. In the process-friction case the harness DID re-invoke the agent on suite completion and it finished cleanly — but the orchestrator, seeing the 'holding' return with a dirty tree, could not distinguish a will-re-invoke hold from a genuine resultless return, and dispatched a redundant --emit-dispatch recovery cycle that overlapped the re-invoked execute-plan agent on the same files (one-writer violation; the recovery had to be TaskStop-ped). Two coupled gaps to trace/fix: (1) cycle subagents are still backgrounding long gates despite the contract's 'run under-cap sub-components in the foreground' mandate; (2) there is no signal that lets the orchestrator tell a 'holding, will re-invoke' return apart from a resultless return, so recovery dispatch races the re-invocation. Fix should either enforce foreground gate-running mechanically or give the orchestrator a deterministic 'this agent will re-invoke' vs 'this is terminal' signal before it dispatches recovery.
