---
kind: adhoc-brief
bug_id: adhoc-write-plan-cognito-planner-contract-read
enqueued_by: lazy-adhoc
date: 2026-07-09
---

# Ad-hoc bug: write-plan-cognito: planner-side lane-contract read is unmandated

During the 2026-07-09 sandboxed v3 verification run, the /write-plan-cognito planner read the full 17.8KB execution-contract-cognito-lanes.md at planning time even though SKILL.md only instructs the EXECUTOR to Read it (the instruction lives inside the pointer-block template). The read was a judgment call and did make the plan-specific notes contract-accurate (they cite L.2 seam semantics and Part-Completion Step 2b), but the cost/benefit is undecided policy: either mandate a scoped planner-side consultation (e.g. section headings or the specific sections the notes will delta) or explicitly state the planner works from the SKILL.md summary alone. Decide, codify in SKILL.md Step 3, and note the expected planner-context cost either way. Evidence: attribute_predispatch --full over the sandbox subagent transcript (contract read = 2nd largest Read at 17.8KB).
