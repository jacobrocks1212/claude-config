## Investigation dispatch (shared — on-demand `/investigate` cycle)

**Why this component exists.** Root-cause investigation is a dispatched cycle, not orchestrator
inline work and not a `lazy-state` cycle emission. This is the single dispatch template for it —
the same **ad-hoc dispatch class** as blocked-resolution's apply-resolution subagent and the
Step 1e.4a recovery dispatch: the orchestrator fills the placeholders from state-script JSON +
its own context and dispatches directly. The state scripts are deliberately untouched (no
routing step, no `--emit-prompt` section); dispatch is orchestrator judgment under the three
triggers below.

### Triggers (when an orchestrator dispatches this)

1. **Validation escalation:** the state script flags `validation_escalation: true`
   (`blocker_kind: mcp-validation` + `retry_count >= 2`) AND no `INVESTIGATION.md` in
   `{spec_path}` is current for the symptom (freshness: `investigated_commit` == HEAD, or only
   that investigation's own `diag(...)` commits since). The investigation runs BEFORE any
   corrective `{ADD_PHASE}` is enacted — it executes the seam audit the corrective phase
   consumes.
2. **Failed fix:** a fix cycle landed and the post-fix live/validation check shows the symptom
   unchanged. The next dispatch for that issue is `/investigate`, not another fix cycle (a
   headless-green fix built to an unverified hypothesis once burned ~266k tokens and seeded the
   next bug).
3. **Inline-diagnosis budget:** the orchestrator has spent more than ~8 of its own diagnostic
   tool calls (source reads, log greps, live probes) on one issue. STOP probing inline and
   dispatch — quick checks stay inline; sustained diagnosis does not.

**Workstation-class work:** `/investigate` needs the live runtime. Cloud orchestrators record
the trigger (one line in the cycle log + the BLOCKED.md/notes) and DEFER dispatch to a
workstation run instead of dispatching cloud-side.

### The no-narrative-as-fact rule (binding on every consumer)

Orchestrators MUST NOT author causal narratives as fact in ANY dispatch prompt. A dispatch
prompt either cites a current `INVESTIGATION.md` (artifact path + the specific ledger rows) or
states "cause unknown — investigation pending." Unproven hunches are passed to `/investigate`
in `{inherited_hypotheses}` explicitly labeled `unproven` — never as "strong hypothesis" /
"solid evidence" headers to a FIX cycle. (Three documented leak incidents in one live run; one
produced a wrong-variant fix.)

### Dispatch

```
Agent({
  description: "investigate: {feature_name}",
  subagent_type: "general-purpose",
  model: "opus",
  prompt: <the prompt below, placeholders filled>
})
```

Prompt template (placeholders from state-script JSON — `{feature_id}`, `{feature_name}`,
`{spec_path}`, `{cwd}`, `{work_branch}` — and orchestrator context — `{trigger}`, `{symptom}`,
`{inherited_hypotheses}`):

```
You are running an on-demand root-cause INVESTIGATION cycle for the autonomous
pipeline. Invoke the /investigate skill (via the Skill tool) and follow it
exactly. You may NOT spawn subagents (no Agent tool). You MAY use the Skill
tool for /investigate, and Read/Grep/Glob/Bash/Edit/Write for the
investigation itself.

Feature: {feature_name} ({feature_id})
Working directory: {cwd}
Feature dir:       {spec_path}
Work branch:       {work_branch}   (WORK-BRANCH-ONLY: commit/push to this
                   branch only; never create a branch; never --force)
Trigger:           {trigger}
Symptom:           {symptom}

Inherited hypotheses (ALL status: unproven — these are hypotheses to TEST, not
evidence; refute them as readily as you confirm them):
{inherited_hypotheses or "— none —"}

Contract reminders (the skill carries the full rules — these are the ones that
void the cycle if violated):
- NO production fixes. Allowed commits: INVESTIGATION.md, `diag({feature_id}):`
  off-hot-path instrumentation (revert or disclose-retained), tests driving
  REAL components.
- NO fire-and-forget: blocking foreground waits; INVESTIGATION.md is on disk
  before you return, whatever the status.
- Verify binary freshness before trusting any observation.
- Every hypothesis verdict cites an evidence artifact; `inconclusive` with an
  honest seam table beats a confident guess.

Return the skill's structured summary (status, seam-table delta, hypothesis
verdicts, instrumentation disposition, artifact path).
```

### Consuming the artifact (downstream)

- **blocked-resolution / halt-resolution:** at trigger 1, dispatch this FIRST; the subsequent
  corrective `{ADD_PHASE}` description cites the artifact (seam table + confirmed rows) instead
  of restating the blocker narrative.
- **`/add-phase`:** confirmed Hypothesis-Ledger rows are citable as `runtime` evidence in the
  corrective phase's Validated Assumptions ledger (evidence column cites the artifact AND its
  underlying evidence artifact); `## Recommended Fix Scope` seeds Files-likely-modified. Stale
  artifacts are cited only as `(stale — re-verify)`.
- **`/write-plan`:** plans cite the repro recipe + fix scope; spike WUs duplicating
  already-confirmed ledger rows are skipped (cite the row instead).

### Coupling note

Consumed by: `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`,
`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (defer-to-workstation variant),
`user/skills/_components/blocked-resolution.md`, `user/skills/_components/halt-resolution.md`.
When editing this component, `grep -rl "investigation-dispatch.md" ~/.claude/skills/` to
confirm the consumer set. The prompt lives HERE only — consumers reference, never inline-copy
(Phase-8 lesson: hand-synced copies drift).
