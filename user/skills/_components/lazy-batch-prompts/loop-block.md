# lazy-batch — LOOP DETECTED block

<!-- Appended to the assembled cycle prompt by the emitter
     (`lazy_core.emit_cycle_prompt`) when repeat_count >= 2 (the state script
     returned the same (item_id, sub_skill, sub_skill_args, current_step) tuple
     on the previous cycle as well) — NOT by orchestrator hand-binding.
     Tokens bound by the emitter: {item_id}, {sub_skill}, {sub_skill_args},
     {current_step}, {spec_path}.
     The emitter omits this block entirely on the first cycle (no prior
     signature) or when the signature differs from the previous cycle. -->

```
⚠️  LOOP DETECTED: The state script returned this exact
(item_id={item_id}, sub_skill={sub_skill}, sub_skill_args={sub_skill_args}, current_step={current_step})
tuple on the PREVIOUS cycle as well. This usually means a terminal sentinel
(VALIDATED.md / DEFERRED_NON_CLOUD.md / SKIP_MCP_TEST.md) is
missing — the skill that was supposed to write it on the prior cycle did not.
(The streak is HEAD-aware: commits landing between probes reset it — this block
firing means NO commits landed between identical probes: a genuine stall.)

Before invoking {sub_skill} again, DIAGNOSE THE MISSING SENTINEL:
  1. Read the canonical schemas in
     ~/.claude/skills/_components/sentinel-frontmatter.md.
  2. Inspect {spec_path}/ for existing sentinels and plan files.
  3. Determine which sentinel SHOULD exist given the item's current state
     (e.g. all phases complete + MCP validated → VALIDATED.md should exist;
     if it doesn't, the previous mcp-test round failed to write it).
  4. The only sentinels a loop-breaker may author are `NEEDS_INPUT.md` and
     `BLOCKED.md`. Do NOT directly write `VALIDATED.md`, `SKIP_MCP_TEST.md`,
     `COMPLETED.md`, `FIXED.md`, or any other completion or
     validation receipt — those sentinels must be earned through their proper
     gate (the skill that owns them). If you diagnose that such a sentinel is
     missing, your permitted moves are: (a) re-run {sub_skill} so the sentinel
     is earned through its proper gate (item 5), or (b) if genuinely stuck or
     ambiguous, write `BLOCKED.md` (item 6) or `NEEDS_INPUT.md` describing the
     gap. Then commit the sentinel you DID write and report the loop-break.
  5. If the preconditions for the correct terminal sentinel are NOT unambiguously
     met via a direct write, run {sub_skill} as instructed but explicitly emit
     the appropriate terminal sentinel as part of its completion (e.g. /mcp-test
     writes VALIDATED.md on a full pass). Report which sentinel you emitted.
  6. If no sentinel applies (genuine ambiguity), write BLOCKED.md with
     blocker_kind: loop-detected and a clear description so the next cycle
     surfaces it as a terminal halt.

The orchestrator will halt on the next cycle's max-cycles cap if this loop
persists — your job here is to break it.
```
