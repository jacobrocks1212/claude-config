# Platform confirmation — `updatedInput` on Agent dispatches (2026-07-18)

Operator-authorized read-only `claude-code-guide` confirmation, run at the 2026-07-18
overnight-run wind-down per this bug's `## Resolution` (option a).

## Findings

1. **`updatedInput` is documented generically** (hooks.md → "PreToolUse Decision Control":
   "Modified tool input object that replaces the original before the tool runs") with NO
   tool-specific carve-out — but it is **confirmed BROKEN for the Agent tool** in current
   Claude Code: GitHub issue **anthropics/claude-code#39814** ("PreToolUse hook `updatedInput`
   silently ignored for Agent tool") reproduces our exact symptom (allow honored,
   `additionalContext` honored, `updatedInput` silently dropped, subagent gets the original
   prompt) and is **closed as "not planned"**. Companion: #44412 (same drop for a `model`
   override on Agent, closed duplicate), #44385 (subagent frontmatter `model:` ignored).
2. **Background vs foreground is NOT the axis.** The docs say nothing about background
   dispatch and `updatedInput` (tools-reference.md notes subagents run in the background by
   default as of v2.1.198); #39814 shows the drop for the Agent tool as a CLASS. Our
   "background dispatch" framing was incidental — the rewrite never works for Agent.
3. Documented limitations for `updatedInput` mention only the multi-hook race
   (last-writer-wins, non-deterministic); nothing about tools or async paths. Related:
   #30770 (replace-not-merge semantics), #15897 (multi-hook breakage), #20243 (Task* tools
   bypassing Pre/PostToolUse entirely).

## Implication for the parked decisions

- This bug's fix fork (b)/(c): **(c) is dead on arrival** as designed — no hook path can
  rewrite an Agent prompt, so a subagent-side fallback would become the PRIMARY path, not a
  fallback, atop a permanently-broken mechanism.
- `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` decision #1: with the rewrite
  confirmed broken for the Agent class (closed not-planned upstream), the by-reference
  dispatch pattern (`@@lazy-ref` as the Agent `prompt:`) cannot deliver prompts on ANY Agent
  dispatch. The evidence supports flipping the preference to **verbatim `cycle_prompt` /
  `dispatch_prompt` for all Agent dispatches**, retaining the guard's verbatim hash-validation
  (`lookup_emission` ALLOW+consume — unaffected by the bug) as the integrity mechanism, and
  demoting `@@lazy-ref` until the upstream issue is fixed.

Sources: hooks.md §PreToolUse Decision Control + §Limitations; tools-reference.md §Agent tool
behavior; github.com/anthropics/claude-code issues #39814, #44412, #44385, #30770, #15897,
#20243. Full guide transcript in the 2026-07-18 session log.
