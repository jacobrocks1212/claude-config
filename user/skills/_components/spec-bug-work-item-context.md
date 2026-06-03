### Subagent F: Work Item Context (if a tracker is in use)

**Only launch if** the project uses an issue/work-item tracker AND the user's description references (or is) a work-item id.

**Prompt:** Fetch the referenced work item and its related items to ground the investigation in what was actually reported.

1. Parse the user's description for a work-item id (a bare number, `#123`, `AB#123`, or a tracker URL)
2. Fetch the work item: title, description/repro steps, state, severity/priority, acceptance criteria, and the full discussion/comment history
3. Follow the work item's relations (parent, children, linked bugs/PRs/commits) and fetch each related item's title + state for surrounding context
4. Extract: reported symptoms, expected vs actual behavior, repro steps, and prior triage notes

Report format: a structured work-item summary (id, title, state, reported symptoms, repro) plus a short list of related items with their relevance, and the resolved id for downstream directory naming.
