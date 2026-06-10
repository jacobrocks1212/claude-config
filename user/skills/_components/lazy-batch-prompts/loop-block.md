# lazy-batch — LOOP DETECTED block

<!-- Verbatim LOOP DETECTED block appended to the cycle dispatch prompt
     when the loop-guard fires (prev_cycle_signature == current signature).
     Bind {feature_id}, {sub_skill}, {sub_skill_args}, {current_step},
     {spec_path} before appending.
     Append this block AFTER the final paragraph of cycle-base-prompt.md
     (i.e. after "that you wrote the failing tests before implementing
     (test-first discipline).").
     Do NOT include this block on the first cycle (prev_cycle_signature is None)
     or when the signature differs from the previous cycle. -->

```
⚠️  LOOP DETECTED: The state script returned this exact
(feature_id={feature_id}, sub_skill={sub_skill}, sub_skill_args={sub_skill_args}, current_step={current_step})
tuple on the PREVIOUS cycle as well. This usually means a terminal sentinel
(RETRO_DONE.md / VALIDATED.md / DEFERRED_NON_CLOUD.md / SKIP_MCP_TEST.md) is
missing — the skill that was supposed to write it on the prior cycle did not.

Before invoking {sub_skill} again, DIAGNOSE THE MISSING SENTINEL:
  1. Read the canonical schemas in
     ~/.claude/skills/_components/sentinel-frontmatter.md.
  2. Inspect {spec_path}/ for existing sentinels and plan files.
  3. Determine which sentinel SHOULD exist given the feature's current state
     (e.g. all phases complete + validated + retro plan present with no
     significant divergences → RETRO_DONE.md should already exist; if it
     doesn't, the previous retro round failed to write it).
  4. The only sentinels a loop-breaker may author are `NEEDS_INPUT.md` and
     `BLOCKED.md`. Do NOT directly write `VALIDATED.md`, `SKIP_MCP_TEST.md`,
     `RETRO_DONE.md`, `COMPLETED.md`, `FIXED.md`, or any other completion or
     validation receipt — those sentinels must be earned through their proper
     gate (the skill that owns them). If you diagnose that such a sentinel is
     missing, your permitted moves are: (a) re-run {sub_skill} so the sentinel
     is earned through its proper gate (item 5), or (b) if genuinely stuck or
     ambiguous, write `BLOCKED.md` (item 6) or `NEEDS_INPUT.md` describing the
     gap. Then commit the sentinel you DID write and report the loop-break.
  5. If the preconditions for the correct terminal sentinel are NOT unambiguously
     met via a direct write, run {sub_skill} as instructed but explicitly emit
     the appropriate terminal sentinel as part of its completion (e.g. /retro
     Step 6c writes RETRO_DONE.md when no significant divergences). Report
     which sentinel you emitted.
  6. If no sentinel applies (genuine ambiguity), write BLOCKED.md with
     blocker_kind: loop-detected and a clear description so the next cycle
     surfaces it as a terminal halt.

The orchestrator will halt on the next cycle's max-cycles cap if this loop
persists — your job here is to break it.
```
