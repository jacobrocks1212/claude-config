## Provisional-ratification mode (shared — ratify / redirect / defer)

**Why this component exists.** Under `--park --park-provisional`
(park-provisional-acceptance), a low-divergence product-class `NEEDS_INPUT.md` is
provisionally accepted on its recommendation at park time: the pipeline keeps
implementing against the recommended option, the sentinel is renamed
`NEEDS_INPUT_PROVISIONAL.md`, and the operator's authority is DEFERRED, not waived —
the feature/bug is completion-blocked (triple-layer backstop, SPEC D6) until the
operator ratifies or redirects each provisionally-taken choice. This component is
the single source for that affordance across both consumers:

- **Step 1g-ratify** — a NON-park probe returned `terminal_reason == "needs-ratification"`.
- **Parked-flush provisional branch** — a park-mode run-end flush found parked
  entries with `sentinel_kind == "provisional"` (the Step-10-equivalent park:
  implementation + validation done, only ratification outstanding).

### Pipeline binding (the consuming skill sets these immediately before the include)

| token | feature pipeline | bug pipeline |
|-------|------------------|--------------|
| `{SKILL}` | `/lazy-batch` (or `/lazy-batch-cloud`) | `/lazy-bug-batch` |
| `{STATE_SCRIPT}` | `lazy-state.py` | `bug-state.py` |
| `{ITEM}` | feature | bug |
| `{ADD_PHASE}` | `/add-phase` | `/add-phase` |
| `{PUSH_RULE}` (apply subagent) | workstation: standard end push · cloud: push immediately per commit | workstation: standard end push |

Runtime placeholders (`{feature_id}`, `{feature_name}`, `{spec_path}`, `{cwd}`) come
from the state-script JSON / the parked entry.

### Algorithm (per `NEEDS_INPUT_PROVISIONAL.md`)

1. **Read and validate the sentinel.** `{spec_path}/NEEDS_INPUT_PROVISIONAL.md` —
   frontmatter (`kind: needs-input` retained; the FILENAME carries the provisional
   state), the `## Decision Context` body, and the appended `## Resolution`
   (`resolved_by: auto-provisional`, `decision_commit: <sha>`, per-decision
   **Choice:**). A file missing its `## Resolution` or `## Decision Context` is
   malformed — surface it as a quality issue (name the writer), do NOT call
   `AskUserQuestion` against it, and leave the sentinel in place (completion stays
   blocked; the operator resolves by hand). Never a silent skip.

2. **Zero-Context Operator Briefing (2a), then verbatim re-print (2b).** Same
   discipline as `decision-resume.md` step 2, with the provisional framing:

   - **2a** covers: what the {ITEM} is, that the run PROVISIONALLY accepted the
     recommended option(s) under `--park-provisional`, what has been BUILT against
     each choice since (summarize `git diff --stat <decision_commit>..HEAD` scoped
     to the {ITEM}'s paths — this is what a redirect would touch), each decision's
     full option set with tradeoffs, the recorded divergence grades, and the
     recommendation to ratify unless the operator disagrees with the choice itself.
   - **2b** re-prints the `## Decision Context` AND `## Resolution` sections
     verbatim.

3. **`AskUserQuestion` per decision** (≤4 questions per call; option set matches the
   briefing 1:1). Options, in this order:

   - **Ratify <chosen option> (Recommended)** — keep the provisionally-applied choice.
   - **Redirect to <option X>** — one option per remaining alternative from the
     H3's `**Options:**` list.
   - **Defer** — leave the provisional sentinel in place; the {ITEM} stays
     completion-blocked and re-surfaces next run. (No apply dispatch.)

4. **Apply the outcome.**

   - **All ratified:** append a `## Ratification` block
     (`*Recorded on <ts>.*`, `ratified_by: operator`, `outcome: ratified`, one
     `### N. <title>` / `**Choice:** <ratified option>` per decision), commit
     (`docs({feature_id}): ratify provisional decision(s)`), then neutralize
     directly: `python3 ~/.claude/scripts/{STATE_SCRIPT} --neutralize-sentinel
     {spec_path}/NEEDS_INPUT_PROVISIONAL.md` (canonical
     `NEEDS_INPUT_PROVISIONAL_RESOLVED_<date>.md` rename). SPEC/PHASES already
     reflect the choice — no apply subagent is needed. The {ITEM} re-enters on the
     next probe and completes normally.
   - **Any redirected:** append the `## Ratification` block
     (`outcome: redirected`, per-decision **Choice:** = the operator's new option,
     ratified/redirected marked per decision), commit
     (`docs({feature_id}): record ratification redirect`), then dispatch the
     apply-resolution subagent via the script:

     ```bash
     python3 ~/.claude/scripts/{STATE_SCRIPT} \
       --emit-dispatch apply-resolution \
       --context item_name="{feature_name}" \
       --context spec_path="{spec_path}" \
       --context sentinel_path="{spec_path}/NEEDS_INPUT_PROVISIONAL.md" \
       --context resolution_summary="<one line: redirected <decision> to <option>>" \
       --context resolution_kind="ratify-redirect" \
       --context chosen_path="<the redirected option label(s)>" \
       --context item_id="{feature_id}" \
       --context cwd="{cwd}"
     ```

     Dispatch `dispatch_prompt` VERBATIM with `dispatch_model`. The subagent
     (per `dispatch-apply-resolution.md`'s ratify-redirect section): propagates the
     CHANGED choice(s) into SPEC.md / PHASES.md, authors a corrective phase
     (`{ADD_PHASE}` conventions, `**Phase kind:** corrective`) scoped by
     `git diff <decision_commit>..HEAD` (the only code that could embody the
     redirected choice — SPEC D7), neutralizes the sentinel via
     `--neutralize-sentinel`, and commits per `{PUSH_RULE}`. The corrective phase's
     unchecked deliverables re-enter the {ITEM} in the queue naturally.
   - **Deferred:** no writes beyond the cycle log. The sentinel stays; the
     completion backstops keep holding.

5. **Accounting + notification.** Each ratification interaction is a META cycle:
   increment `meta_cycles`, `cycle_log` entry
   `{…, "▶ needs-ratification (ratified|redirected|deferred)", "<N> decision(s); <summary>"}`,
   per-cycle block heading `### Cycle {meta_cycles} (meta) · {feature_name} ·
   ratification`, `prev_cycle_signature = (feature_id, "__ratify_provisional__",
   sub_skill_args, current_step)`. Fire one PushNotification:
   `"{SKILL} ratification — {feature_name}: {N} decision(s) {ratified|redirected|deferred}"`.
   Record each outcome in the run-end provisional digest (the
   "Provisionally accepted decisions" table carries a Ratification column when this
   affordance ran).

6. **Continue the loop** (Step 1g-ratify consumer) or proceed with the flush
   (parked-flush consumer). Only an explicit operator "halt" standing-directive
   stops the run — ratification itself never halts.

### Coupling note

Consumed (as Step 1g-ratify) by `user/skills/lazy-batch/SKILL.md` and
`user/skills/lazy-bug-batch/SKILL.md`, and by the provisional branch of
`user/skills/_components/parked-flush.md` (all three bind the pipeline tokens
first). The single-dispatch wrappers (`/lazy`, `/lazy-bug`, `/lazy-cloud`) route
`needs-ratification` through `halt-resolution.md` like other obstacle terminals —
they do one action then stop. When editing this component, run
`grep -rl "provisional-ratification.md" ~/.claude/skills/` to confirm the consumer set.
