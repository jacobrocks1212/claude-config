---
kind: adhoc-brief
bug_id: adhoc-subagent-wedge-hook-overfires-globs-all-plans
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: SubagentStop wedge-backstop hook over-fires: globs all repo plans

The subagent-wedge-backstop.sh hook (shipped by feature subagent-wedge-backstop-hook) resolves 'the active plan' by globbing EVERY docs/{features,bugs}/*/plans/*.md and treats any non-terminal plan as pending work (predicate condition 3: unchecked WU checkboxes). In a multi-plan repo like claude-config there is almost always some plan with unchecked WUs, so the hook fires on EVERY legitimate cycle-subagent stop that has a clean tree — a false positive, bounded to one extra stop-retry per agent_id by the loop-guard breadcrumb, but pipeline-wide friction. Root: the SubagentStop hook input carries no way to identify which plan the just-stopped cycle was executing, so the unchecked-WU half of condition 3 over-broadens. Refinement: narrow 'active plan' resolution to the run marker's current item (or rely on the git-dirty half of the predicate alone), so the hook fires only when THIS agent genuinely left uncommitted work. Origin: feature subagent-wedge-backstop-hook (surfaced during its execute-plan real-world exposure, 2026-07-18).
