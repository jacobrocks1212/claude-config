## Parked-decision flush (shared — `--park` mode only)

**Why this component exists.** In `--park` mode the orchestrator defers `NEEDS_INPUT.md`
decisions instead of resolving them inline (Step 1g parks each item rather than halting).
At certain checkpoints the run must collect all unresolved parked decisions and present them
to the operator in one batched interaction — the flush. This component is the single source
for that logic across all three batch orchestrators; it was factored out here to prevent
triple-copy drift (the same failure mode that necessitated `decision-resume.md`). The flush
is the batched, `--park`-mode-only sibling of `decision-resume.md`'s single-decision handler.

**Gating:** this entire component is active ONLY when `park_mode == true` (`--park`). It
MUST NOT fire if `park_mode == false`. No-op when `park_mode == false`; the caller must
guard with `if park_mode:`.

### Pipeline binding (the consuming skill sets these immediately before the include)

| token | feature pipeline | bug pipeline | cloud pipeline |
|-------|------------------|--------------|----------------|
| `{SKILL}` | `/lazy-batch` | `/lazy-bug-batch` | `/lazy-batch-cloud` |
| `{STATE_SCRIPT}` | `lazy-state.py` | `bug-state.py` | `lazy-state.py --cloud` |
| `{ITEM}` | feature | bug | feature |
| `{PUSH_RULE}` (apply subagent) | workstation: standard end push | workstation: standard end push | **cloud: push IMMEDIATELY after each commit (container-reclaim durability)** |

Runtime placeholders (`{feature_id}`, `{feature_name}`, `{spec_path}`, `{cwd}`,
`{written_by}`, `{cycle}`, `{max_cycles}`) are filled from the state-script JSON — note
all pipelines use the JSON field name `feature_id` (the bug id rides in it for the bug
pipeline).

### Flush triggers

The orchestrator fires a flush at the **FIRST** of the following three trigger points:

**(a) Operator message mid-run.** Any mid-run operator message that arrives while
`park_mode == true` and `parked_count > 0` (at least one `NEEDS_INPUT.md` whose sentinel
is still unresolved) triggers an immediate flush. This is distinct from the standing-directive
echo-back — the echo-back protocol applies first if the message implies a budget/mode change;
if the message triggers neither an echo-back nor an early stop, the flush runs before
processing the message's intent further. The flush algorithm below runs in full; afterward
the orchestrator resumes the loop (or processes any standing-directive effect).

**(b) No unparked work remains (queue-exhausted-with-parked guard).** When `park_mode == true`
and the `{STATE_SCRIPT}` probe returns a queue-exhausted or all-complete terminal
(`all-features-complete`, `all-bugs-fixed`, `cloud-queue-exhausted`, `device-queue-exhausted`,
or any equivalent terminal signalling the active queue is empty), the orchestrator MUST check
whether any parked items remain unresolved (i.e., their sentinel is still named `NEEDS_INPUT.md`).
If unresolved parked items exist, the orchestrator MUST NOT treat the all-complete signal as a
real STOP. Instead, run the flush algorithm below first. After the flush completes and the
apply-resolution subagents rename each sentinel to `NEEDS_INPUT_RESOLVED*.md`, return to Step
1a — the state script will now see the resolved sentinels and emit the genuine all-complete
terminal on the next probe.

**(c) Run end.** When the orchestrator is about to print the final batch report and stop for
any reason (max-cycles cap, all-complete confirmed after trigger (b) flush, research halt,
operator-chosen halt, etc.) and `parked_count > 0` with unresolved sentinels still present,
run the flush algorithm below before printing the final report. The final report is printed
after the flush (this IS a run-end; the loop genuinely ends after the flush completes).

### Algorithm

**Meta-cap check (FIRST — before any other action in the flush).** Check
`if meta_cycles >= 2 * max_cycles:` before flushing. If the cap is reached, skip the flush:
emit a warning to chat (`"⚠ meta-cycle cap (2× max_cycles) reached — skipping parked-decision
flush; {N} parked item(s) left unresolved. Restart from a fresh session to resolve them."`),
fire a PushNotification with the same message, and proceed directly to the final report (or
resume the loop, if trigger (a) — but without flushing). Do NOT increment `meta_cycles` for
this guard check itself.

**Step 1 — Collect unresolved parked items.** Build the set `pending_flush`: all items whose
sentinel file is still named `{spec_path}/NEEDS_INPUT.md` (i.e., not yet renamed to
`NEEDS_INPUT_RESOLVED*.md`). These are the decisions that were parked during the run.
Already-resolved items (renamed sentinels) are excluded — they re-enter the queue naturally
on the next state-script probe and require no action here. If `pending_flush` is empty,
the flush is a no-op (proceed to run-end report or resume loop).

**Step 2 — Validate each sentinel.** For each item in `pending_flush`, read its
`{spec_path}/NEEDS_INPUT.md` and apply the SAME schema check as `decision-resume.md` step 1:

  - Parse the YAML frontmatter (`kind`, `feature_id`, `written_by`, `decisions`, `date`).
  - Read the markdown body.
  - **Schema check:** the body MUST contain a `## Decision Context` H2 with one H3 subsection
    per `decisions[i]` (matching titles, 1:1). Each H3 MUST carry `**Problem:**`,
    `**Options:**`, and `**Recommendation:**` blocks per the rich-body convention in
    `sentinel-frontmatter.md`.
  - **If malformed** — missing `## Decision Context`, mismatched H3 count, or missing required
    subsections — do NOT flush that item. Instead emit to chat:

    ```
    ⚠️  NEEDS_INPUT.md missing required '## Decision Context' section (or subsections do not
    match decisions: 1:1). Writer skill: {written_by}.
    Skipping this item in the flush — fix the skill so future sentinels emit the rich body,
    or supply input manually.

    File: {spec_path}/NEEDS_INPUT.md
    ```

    Fire a PushNotification with the same message. Remove the malformed item from
    `pending_flush` and continue processing the remaining well-formed items. Do NOT abort
    the entire flush for one malformed sentinel.

After step 2, `pending_flush` contains only well-formed sentinels. If `pending_flush` is now
empty (all were malformed), skip to the post-flush cycle accounting step.

**Step 3 — Print the Zero-Context Operator Briefing, then flush via batched `AskUserQuestion`
calls.** This is a HARD REQUIREMENT: assume the operator has been away for hours and has zero
session context. Before issuing any `AskUserQuestion` call, print to chat:

  - **(3a) Zero-Context Operator Briefing** for ALL decisions in the upcoming call (synthesized
    by the orchestrator; the same shape as `decision-resume.md` step 2a): where the run is,
    what each {ITEM} is in plain terms, why each decision was parked and what is at stake,
    and every option with pros/cons, fit assessment, and recommendation. One briefing block
    per `AskUserQuestion` call (covering all decisions in that call). The briefing explains
    each sentinel; it never replaces it.
  - **(3b) Verbatim `## Decision Context` re-print** for each item in the upcoming call,
    exactly as `decision-resume.md` step 2b specifies: the full sentinel context, no
    summarization.

  **Batching rule (≤4 questions per call — HARD CONSTRAINT).** `AskUserQuestion` accepts at
  most 4 questions per call. This limit counts TOTAL questions across all parked items
  combined in one call — not 4 questions per item. Pack decisions from `pending_flush` into
  `AskUserQuestion` calls greedily: fill each call up to 4 questions before opening a new
  call. A single {ITEM}'s decisions MUST NOT be split across two calls unless that {ITEM}
  alone carries more than 4 decisions (which would itself be a schema violation — `sentinel-
  frontmatter.md` caps decisions per sentinel at 4). In practice, one call may contain
  decisions from multiple {ITEM}s; the briefing block for that call covers all of them.

  Issue the `AskUserQuestion` calls SEQUENTIALLY (not in parallel — each call may inform
  context for the next, and the operator must answer in order). Build each call's `questions`
  array exactly as `decision-resume.md` step 3 specifies: `question` = H3 title verbatim,
  `header` = 8-12 char chip, `options` from the H3's `**Options:**` list (`label` = bold
  name, `description` = first sentence), `multiSelect: false` unless the H3 explicitly says
  "select all that apply".

  The option set in each `AskUserQuestion` call MUST exactly match the options presented in
  the step-3a briefing (same labels, same count, recommendation listed first with
  `(Recommended)` marker).

**Step 4 — Apply each resolved decision.** After each `AskUserQuestion` call returns (do not
wait for all calls before applying — apply immediately after each call so partial results are
persisted even if a later call is interrupted):

For each decision in the just-answered call, apply via the SAME machinery as
`decision-resume.md` steps 4–6. Do NOT re-implement this machinery here — reference and
follow `~/.claude/skills/_components/decision-resume.md` steps 4–6 exactly:

  - **Step 4 (append `## Resolution`):** append the Resolution block to `NEEDS_INPUT.md`
    using `Edit` (or `Write` as fallback). Same format as `decision-resume.md` step 4.
  - **Step 5 (commit):** stage `NEEDS_INPUT.md` (with the new `## Resolution`) and commit:
    `docs({feature_id}): record decision resolution`. Do NOT push (workstation pipelines);
    for the cloud pipeline, {PUSH_RULE} applies.
  - **Step 6 (dispatch the Sonnet apply-resolution subagent):** dispatch exactly as
    `decision-resume.md` step 6 specifies — same subagent prompt shape, same
    `Agent({ description: "{SKILL} decision-apply: {feature_name}", subagent_type:
    "general-purpose", model: "sonnet", prompt: <step-6-prompt> })` dispatch. The subagent
    propagates the choice into SPEC.md / PHASES.md and renames `NEEDS_INPUT.md` →
    `NEEDS_INPUT_RESOLVED*.md` (FILENAME rename via `git mv` — NOT a `kind:` flip, which
    leaves the halt firing on the next state-script call; see `decision-resume.md` step 6
    for the exact rename rule and the "kind-flip is a real bug" note).

**Step 5 — Fire the flush PushNotification.** After all `AskUserQuestion` calls and their
apply-resolution dispatches are issued, fire one PushNotification per §1c.6 flush policy:

  - `/lazy-batch`: `"lazy-batch flush — {N} parked decision(s) ready for your input"`
    (where `{N}` is `len(pending_flush)` items flushed, i.e., the item count, not the question
    count — clarify as "N item(s) flushed" if ambiguous in context).
  - `/lazy-bug-batch`: `"lazy-bug-batch flush — {N} parked decision(s) ready for your input"`.
  - `/lazy-batch-cloud`: `"lazy-batch-cloud flush — {N} parked decision(s) ready for your
    input"`.

**Step 6 — Cycle accounting.** Each flushed decision's apply dispatch is a META cycle:

  - For each dispatched apply-resolution subagent: increment `meta_cycles` by 1, check
    `if meta_cycles >= 2 * max_cycles:` (mid-flush meta-cap check — if hit, stop flushing
    remaining items, emit the cap warning, and proceed to post-flush continuation).
  - Record one `cycle_log` entry per dispatched apply: `{forward_cycles + meta_cycles,
    feature_name, "▶ parked-flush (resolved + applied)", "<N> decision(s); <first-line-of-subagent-summary>"}`.
  - Emit the canonical per-cycle update block (Step 3 of the consuming skill): heading
    `### Cycle {meta_cycles}/{2*max_cycles} (meta) · {feature_name} · parked-flush`,
    `**Result:**` = `"parked decision(s) flushed + applied — {first-line-of-subagent-summary}"`.
    One block per apply dispatch.
  - Update `prev_cycle_signature = (feature_id, "__parked_flush__", sub_skill_args, current_step)`
    — the 4-tuple, matching every other signature. The synthetic sub_skill token distinguishes
    this from any real-skill cycle.

**Step 7 — Post-flush continuation.** After all items in `pending_flush` are processed:

  - If this flush was triggered by **(a) operator message** or **(b) queue-exhausted-with-parked
    guard**: return to Step 1a. The now-renamed sentinels mean the previously-parked items re-enter
    naturally on the next probe. DO NOT halt; DO NOT print the final report (the loop continues).
  - If this flush was triggered by **(c) run end**: proceed to print the final batch report.
    The run genuinely ends after the flush.

### Coupling note

Consumed (as Step 1g-flush) by the three batch orchestrators:
`user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`,
`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.
The single-dispatch wrappers (`/lazy`, `/lazy-bug`, `/lazy-cloud`) do NOT consume this
component — they dispatch once then stop and have no `--park` flag.

When editing this component, run
`grep -rl "parked-flush.md" ~/.claude/skills/` to confirm the consumer set.
