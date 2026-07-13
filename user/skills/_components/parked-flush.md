## Parked-decision flush (shared — `--park` mode only)

**Why this component exists.** In `--park` mode the orchestrator defers `NEEDS_INPUT.md`
decisions AND feature/bug-local `BLOCKED.md` blocks instead of resolving them inline (Step 1g
parks each item rather than halting; the `--park-blocked` flag parks blocked items the same way).
At certain checkpoints the run must collect all unresolved parked items and present them
to the operator in one batched interaction — the flush. This component is the single source
for that logic across all three batch orchestrators; it was factored out here to prevent
triple-copy drift (the same failure mode that necessitated `decision-resume.md`). The flush
is the batched, `--park`-mode-only sibling of `decision-resume.md`'s single-decision handler
(for needs-input items) and `blocked-resolution.md`'s single-block handler (for blocked items).

**Two parked kinds — partitioned by `sentinel_kind` (bug park-mode-halts-on-blocked, D4).**
The state script's `parked[]` entries each carry a `sentinel_kind` field (`needs-input` |
`blocked`), set by `lazy_core.build_parked_entry` from the sentinel filename. A **needs-input**
parked item is a deferred decision (rich `## Decision Context` body) → resolved via the
`decision-resume.md` / `AskUserQuestion` machinery (Steps 2–5 below). A **blocked** parked item
is a deferred block (`BLOCKED.md` frontmatter body — NO `## Decision Context`) → resolved via
the SAME affordance as `{SKILL}` Step 1h / `blocked-resolution.md` (Step 2.6 below). A blocked
item MUST NOT be run through the needs-input `## Decision Context` schema check — its body has
none, so that check would wrongly drop it as "malformed". The two kinds are partitioned at Step 1
and processed by their respective branches.

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
(`all-features-complete`, `all-bugs-fixed`, `queue-exhausted-all-parked`, `cloud-queue-exhausted`,
`device-queue-exhausted`, or any equivalent terminal signalling the active queue is empty), the
orchestrator MUST check whether any parked items remain unresolved (i.e., their sentinel is still
named `NEEDS_INPUT.md` OR `BLOCKED.md`). If unresolved parked items exist, the orchestrator MUST
NOT treat the signal as a real STOP. Instead, run the flush algorithm below first. After the flush
completes and the apply-resolution subagents rename each sentinel to `NEEDS_INPUT_RESOLVED*.md` /
`BLOCKED_RESOLVED*.md`, return to Step 1a — the state script will now see the resolved sentinels
and emit the genuine terminal on the next probe. (`queue-exhausted-all-parked` is the dedicated
terminal the state script returns when the queue advanced past every workable item and ONLY
parked items remain — its natural pairing with this trigger.)

**(c) Run end.** When the orchestrator is about to print the final batch report and stop for
any reason (max-cycles cap, all-complete confirmed after trigger (b) flush, research halt,
operator-chosen halt, etc.) and `parked_count > 0` with unresolved sentinels still present,
run the flush algorithm below before printing the final report. The final report is printed
after the flush (this IS a run-end; the loop genuinely ends after the flush completes).

### Algorithm

**No meta-cap check.** `meta_cycles` is uncapped (operator decision 2026-06-14) — there is
no meta-cycle ceiling, so the flush is never skipped for a meta-cap reason. Proceed directly
to Step 1. (`meta_cycles` is still incremented per flushed item below and displayed as a bare
count; the run's only hard stop remains the forward-cycle cap, `forward_cycles >= max_cycles`.)

**Step 1 — Collect unresolved parked items, partitioned by kind.** Build the set
`pending_flush` from ALL parked sentinel kinds (read each item's `sentinel_kind` from the
probe's `parked[]` entry, or — if reconstructing from disk — from the live sentinel filename):

  - **needs-input** items: sentinel still named `{spec_path}/NEEDS_INPUT.md` (not yet renamed
    to `NEEDS_INPUT_RESOLVED*.md`). These are deferred decisions.
  - **blocked** items: sentinel still named `{spec_path}/BLOCKED.md` (not yet renamed to
    `BLOCKED_RESOLVED*.md`). These are deferred blocks.
  - **provisional** items (park-provisional-acceptance): sentinel named
    `{spec_path}/NEEDS_INPUT_PROVISIONAL.md` (not yet renamed to
    `NEEDS_INPUT_PROVISIONAL_RESOLVED*.md`). These are provisionally-accepted decisions
    awaiting ratification — the probe parks such an item once its implementation +
    validation are done (`VALIDATED.md` present), and the probe's park-mode
    `provisional[]` key lists every one observed mid-pipeline; the flush processes the
    PARKED (ratification-ready) ones and MAY also offer ratification for still-in-flight
    `provisional[]` entries at trigger (c) run-end (early ratification is always safe —
    the choice is already applied).

Already-resolved items (renamed sentinels) are excluded — they re-enter the queue naturally
on the next state-script probe and require no action here. Partition `pending_flush` into
`pending_needs_input[]` (kind `needs-input`), `pending_blocked[]` (kind `blocked`), and
`pending_provisional[]` (kind `provisional`). If ALL are empty, the flush is a no-op (proceed
to run-end report or resume loop). The needs-input items flow through Steps 2–5; the blocked
items are handled by Step 2.6; the provisional items by Step 2.7 (each counted in the Step
5/6 digest alongside the decision flushes).

**Step 2 — Validate each needs-input sentinel (needs-input items ONLY).** This step processes
`pending_needs_input[]` ONLY — blocked items are NOT run through the `## Decision Context`
rich-body schema check (a `BLOCKED.md` body has no decision context; that check would wrongly
drop it). Blocked items are validated and resolved in Step 2.6. For each item in
`pending_needs_input[]`, read its `{spec_path}/NEEDS_INPUT.md` and apply the SAME schema check as
`decision-resume.md` step 1:

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
    `pending_needs_input` and continue processing the remaining well-formed items. Do NOT abort
    the entire flush for one malformed sentinel.

After step 2, `pending_needs_input` contains only well-formed needs-input sentinels. If it is now
empty (all were malformed), skip the needs-input branch (Steps 2.4–4) and proceed to Step 2.6
(blocked items), then the post-flush cycle accounting step.

**Step 2.4 — Completeness-policy scope resolution (D7 — runs BEFORE the two-key partition).**
Same precedence as `decision-resume.md` step 1b: scope-class decisions are resolved by standing
policy, NOT asked, before any batching. Apply the scope test from
`~/.claude/skills/_components/completeness-policy.md` to each decision in each
`pending_needs_input` sentinel: any decision that is `class: scope` — or scope-shaped (options differ only in
effort / sizing / sequencing / completeness, same end-state product behavior) regardless of
declared class — is auto-resolved to the **most complete option**: append the `## Resolution`
block carrying `resolved_by: completeness-policy`, emit the
`⚖ policy: {decision, ≤8 words} → {chosen path}` chat line, record a D7-digest entry
(NOT an `auto_accepted[]` entry — the digests are separate), and run the same commit +
apply-resolution-subagent + meta-cycle accounting machinery as the auto-accept processing in
Step 2.5 below. A sentinel whose every decision was scope-class drops out of `pending_needs_input`
here; a mixed sentinel continues into Step 2.5 with only its remaining decisions. Scope-class
decisions should normally NEVER reach the flush at all — Step 1g / probe-time D7 resolution
handles them first — this step is the backstop for any that slipped through (e.g. parked by
the probe before any classification ran).

**Step 2.5 — Two-key auto-accept partition (`--park` mode only — this step runs only here).**

**No D2 two-key auto-accept path exists outside this park-only component.** The two-key
auto-accept logic below is structurally gated inside this `--park`-only flush component; it
cannot fire in the standard decision-resume path (Step 1g without `--park`). The structural
guarantee: `class: mechanical` and `audit_concurs: true` in a sentinel are inert outside
`--park` — they are read and acted on ONLY here. (Distinct from the D7 completeness-policy
scope resolution in Step 2.4 / `decision-resume.md` step 1b, which IS both-modes by design —
its authorization is the standing policy itself, not the two-key mechanism.)

Partition `pending_needs_input` into two sets:

**`auto_acceptable[]` — auto-accept iff ALL of the following hold for a given sentinel:**
1. `park_mode == true` (always true here — this step is park-only).
2. The sentinel's frontmatter carries `class: mechanical`.
3. The sentinel's frontmatter carries `audit_concurs: true`.
4. Every decision in the file (every H3 under `## Decision Context`) carries a `**Recommendation:**` block.

A single-key classification (`class: mechanical` without `audit_concurs: true`, or vice versa)
is NOT sufficient. On ANY disagreement, missing key, or missing recommendation — the sentinel
falls into `must_ask` regardless of any other field values.

**`must_ask[]` (product/park) — everything else:** any sentinel where `class` is `product` or
absent, `audit_concurs` is `false` or absent, or any decision lacks a `**Recommendation:**`.
These are processed by the existing batched `AskUserQuestion` flow in Step 3.

**Auto-accept processing — for each item in `auto_acceptable[]`:**

  1. **For EACH decision in the sentinel's `## Decision Context`:** read the `**Recommendation:**`
     line, extract the recommended option label (the bold `<option>` name at the start of the
     recommendation sentence).

  2. **Append `## Resolution` block** to `NEEDS_INPUT.md` using `Edit` (or `Write` as fallback):

     ```markdown

     ## Resolution

     *Recorded on <YYYY-MM-DD HH:MM:SS UTC>. Auto-accepted via two-key mechanical classification (`--park` mode).*

     resolved_by: auto-two-key

     ### 1. <decision[0] title>

     **Choice:** <recommended option label>
     **Notes:** Auto-accepted — both keys (cycle-subagent `class: mechanical` + audit `audit_concurs: true`) agreed this decision is mechanical-internal with a single defensible answer.

     ### 2. <decision[1] title>

     **Choice:** ...
     ```

     One `### N.` subsection per decision, in the same order as the `decisions:` frontmatter list.

  3. **Commit** the resolved sentinel: stage `NEEDS_INPUT.md` and commit with message
     `docs({feature_id}): auto-accept mechanical decision(s) [two-key, --park]`. Apply
     `{PUSH_RULE}` (for the cloud pipeline: push immediately after this commit for
     container-reclaim durability).

  4. **Dispatch the Sonnet apply-resolution subagent** — SAME machinery as `decision-resume.md`
     steps 4–6. The subagent propagates each auto-accepted choice into SPEC.md / PHASES.md,
     neutralizes the sentinel via `python3 ~/.claude/scripts/{STATE_SCRIPT} --neutralize-sentinel
     {spec_path}/NEEDS_INPUT.md` (canonical `NEEDS_INPUT_RESOLVED_<date>.md` rename with
     collision handling — a FILENAME rename, NOT a `kind:` flip; see `decision-resume.md` step 6
     for the exact rename rule and the "kind-flip is a real bug" note), and then applies the
     promote-on-resolve rule (`decision-resume.md` step 6 prompt step 3b): if any
     `NEEDS_INPUT_FOLLOWUP_*.md` exists in the spec dir, `git mv` the lowest-numbered one to
     `NEEDS_INPUT.md` and note it in the cycle summary — the next probe re-surfaces it. The
     subagent prompt is the same shape as `decision-resume.md` step 6, with the additional note
     that the choices were auto-accepted via the two-key mechanical path and the operator was
     not asked. Use:

     ```
     Agent({
       description: "{SKILL} auto-accept-apply: {feature_name}",
       subagent_type: "general-purpose",
       model: "sonnet",
       prompt: <decision-resume.md step 6 prompt, with `resolved_by: auto-two-key` noted>
     })
     ```

  5. **Record in `auto_accepted[]`** (in-memory list for the run-end digest):
     `{ feature_id, feature_name, decision_titles: [<one-line titles>], chosen_options: [<labels>], resolved_sentinel_path: <new NEEDS_INPUT_RESOLVED*.md path> }`

  6. **Cycle accounting** — same as Step 6 of the flush (one `meta_cycles` increment per
     dispatched apply, one `cycle_log` entry, one per-cycle update block with heading
     `### Cycle {meta_cycles} (meta) · {feature_name} · auto-accept [two-key]`).
     Each auto-accepted item counts as a meta cycle, matching the standard flush accounting.

After processing all `auto_acceptable[]` items, assign `pending_needs_input = must_ask[]` and continue
to Step 3 (the batched `AskUserQuestion` flow for the remaining `must_ask` items). If `must_ask`
is empty after the partition, Steps 3–5 are no-ops (no `AskUserQuestion` calls are issued) —
proceed directly to Step 2.6 (blocked items), then Step 6 cycle accounting (already done above
for auto-accepted items) then Step 7 post-flush continuation.

**Step 2.6 — Flush blocked-parked items (`pending_blocked[]` — blocked kind ONLY).** For each
item in `pending_blocked[]` (sentinel still named `{spec_path}/BLOCKED.md`), run the SAME
resolution affordance as `{SKILL}` Step 1h — do NOT invent a new resolution path. Bind the same
pipeline tokens this component already bound (`{SKILL}`, `{STATE_SCRIPT}`, `{ITEM}`,
`{PUSH_RULE}`, plus `{SPEC_ROOT}` and `{ADD_PHASE}` per the consuming skill's Step 1h binding)
and apply `~/.claude/skills/_components/blocked-resolution.md` for each blocked item:

  - **Validate against the BLOCKED.md schema, NOT `## Decision Context`.** Read
    `{spec_path}/BLOCKED.md`, parse its YAML frontmatter (`kind`, `feature_id`, `phase`,
    `blocked_at`, `retry_count`, `blocker_kind` if present). A `BLOCKED.md` has NO mandated
    rich body — a thin body is NOT a malformation; never drop a blocked item as "missing
    `## Decision Context`" (that check is needs-input-only, Step 2). Honor the `blocked-resolution.md`
    step 1a seam-batched corrective-phase policy (`blocker_kind: mcp-validation`, ANY `retry_count` →
    the corrective phase is scoped to the FULL enumerated seam set; `retry_count >= 2` ADDITIONALLY →
    investigate-first) exactly as Step 1h would.
  - **Classify FIRST, then resolve** (blocked-resolution.md step 1b): a sequencing-only blocker
    auto-resolves per `completeness-policy.md` §3 (add-phase + fix now, or `/spec-bug` /
    `--enqueue-adhoc` spin-off + dependency-gate + requeue-to-tail) — logged + push-notified, no
    question, `resolved_by: completeness-policy`. Only a genuine product fork re-prints the
    `BLOCKED.md` body VERBATIM (blocked-resolution.md step 2) and runs `AskUserQuestion` for the
    path (add a phase / defer to queue tail / halt-for-manual / custom).
  - **Neutralize on `BLOCKED.md`, NOT `NEEDS_INPUT.md`.** After resolution, the apply-resolution
    subagent neutralizes the sentinel via
    `python3 ~/.claude/scripts/{STATE_SCRIPT} --neutralize-sentinel {spec_path}/BLOCKED.md`
    (canonical `BLOCKED_RESOLVED_<date>.md` rename, collision-safe) — exactly as
    `blocked-resolution.md` step 6 specifies. A dependency-gated requeue-to-tail leaves
    `BLOCKED.md` in place (the operator "Defer" path), like Step 1h.
  - **Cycle accounting + digest:** each blocked-item resolution dispatch is a META cycle
    counted identically to the needs-input flushes in Step 6 (one `meta_cycles` increment, one
    `cycle_log` entry — use `"▶ parked-flush (blocked — resolved + applied)"`, one per-cycle
    block heading `### Cycle {meta_cycles} (meta) · {feature_name} · parked-flush [blocked]`).
    Record the resolution in the run-end digest alongside the decision flushes; the
    `## Auto-accepted decisions` / D7 digest tables in the consuming skill carry blocked
    auto-resolutions in their `⚖ policy:` rows like any other completeness-policy application.

The `halt-for-manual` choice for a blocked item behaves as in Step 1h — it preserves
`BLOCKED.md` and STOPs the run (the lone stopping exception). Otherwise the loop continues after
the flush per Step 7.

**Step 2.7 — Ratify provisional-parked items (`pending_provisional[]` — provisional kind ONLY;
park-provisional-acceptance).** For each item in `pending_provisional[]` (sentinel still named
`{spec_path}/NEEDS_INPUT_PROVISIONAL.md`), run the shared ratification affordance — do NOT
invent a new resolution path and do NOT run these through the Step-2 needs-input schema check
(a provisional file legitimately carries an appended `## Resolution`; its validation rules are
the component's own). Bind the same pipeline tokens this component already bound (`{SKILL}`,
`{STATE_SCRIPT}`, `{ITEM}`, `{PUSH_RULE}`, plus `{ADD_PHASE}` per the consuming skill's Step 1h
binding) and apply, per item:

`~/.claude/skills/_components/provisional-ratification.md`

Cycle accounting per that component's step 5 (one META cycle per ratification interaction;
`cycle_log` action `"▶ parked-flush (provisional — ratified|redirected|deferred)"`). A
**Ratify** outcome neutralizes the sentinel and the {ITEM} re-enters at the next probe (its
only remaining route is the now-unblocked completion); a **Redirect** dispatches the
ratify-redirect apply subagent (corrective phase scoped by the recorded `decision_commit`);
a **Defer** leaves the sentinel — the {ITEM} stays completion-blocked and re-surfaces next
run. Record every outcome in the run-end provisional digest table.

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
  combined in one call — not 4 questions per item. Pack decisions from `pending_needs_input` into
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
    propagates the choice into SPEC.md / PHASES.md and neutralizes the sentinel via
    `python3 ~/.claude/scripts/{STATE_SCRIPT} --neutralize-sentinel {spec_path}/NEEDS_INPUT.md`
    (canonical `NEEDS_INPUT_RESOLVED_<date>.md` rename with collision handling — a FILENAME
    rename, NOT a `kind:` flip, which leaves the halt firing on the next state-script call;
    see `decision-resume.md` step 6 for the exact rename rule and the "kind-flip is a real
    bug" note). After the neutralization, the same promote-on-resolve rule applies
    (`decision-resume.md` step 6 prompt step 3b): if any `NEEDS_INPUT_FOLLOWUP_*.md` exists
    in the spec dir, `git mv` the lowest-numbered one to `NEEDS_INPUT.md` and note it in the
    cycle summary — the next probe re-surfaces it.

**Step 5 — Fire the flush PushNotification.** After all `AskUserQuestion` calls and their
apply-resolution dispatches are issued, fire one PushNotification per §1c.6 flush policy:

  - `/lazy-batch`: `"lazy-batch flush — {N} parked item(s) flushed (decisions + blocks + ratifications) ready for your input"`
    (where `{N}` is `len(pending_needs_input) + len(pending_blocked) + len(pending_provisional)`
    items flushed, i.e., the item count across ALL kinds, not the question count).
  - `/lazy-bug-batch`: `"lazy-bug-batch flush — {N} parked decision(s) ready for your input"`.
  - `/lazy-batch-cloud`: `"lazy-batch-cloud flush — {N} parked decision(s) ready for your
    input"`.

**Step 6 — Cycle accounting.** Each flushed decision's apply dispatch is a META cycle:

  - For each dispatched apply-resolution subagent: increment `meta_cycles` by 1. There is NO
    mid-flush meta-cap check — `meta_cycles` is uncapped (operator decision 2026-06-14); flush
    every item.
  - Record one `cycle_log` entry per dispatched apply: `{forward_cycles + meta_cycles,
    feature_name, "▶ parked-flush (resolved + applied)", "<N> decision(s); <first-line-of-subagent-summary>"}`.
  - Emit the canonical per-cycle update block (Step 3 of the consuming skill): heading
    `### Cycle {meta_cycles} (meta) · {feature_name} · parked-flush`,
    `**Result:**` = `"parked decision(s) flushed + applied — {first-line-of-subagent-summary}"`.
    One block per apply dispatch.
  - Update `prev_cycle_signature = (feature_id, "__parked_flush__", sub_skill_args, current_step)`
    — the 4-tuple, matching every other signature. The synthetic sub_skill token distinguishes
    this from any real-skill cycle.

**Step 7 — Post-flush continuation.** After all items in `pending_needs_input`,
`pending_blocked`, and `pending_provisional` are processed:

  - If this flush was triggered by **(a) operator message** or **(b) queue-exhausted-with-parked
    guard**: return to Step 1a. The now-renamed sentinels (`NEEDS_INPUT_RESOLVED*.md` /
    `BLOCKED_RESOLVED*.md` / `NEEDS_INPUT_PROVISIONAL_RESOLVED*.md`) mean the previously-parked
    items re-enter naturally on the next probe.
    DO NOT halt; DO NOT print the final report (the loop continues). (Exception: a blocked item
    resolved as `halt-for-manual` STOPs per Step 2.6, like Step 1h.)
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
