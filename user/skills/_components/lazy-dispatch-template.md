# Lazy Family — Canonical Cycle Dispatch Template (compaction-survivable)

**Re-read this file after ANY compaction boundary, before composing the next cycle dispatch.**
Compaction wipes the orchestrator's working memory of the exact dispatch shape. In the 2026-06-10 WSL
run, 41% of post-compaction spawns silently dropped the `model:` parameter (downgrading the cycle
subagent to the wrong model) and 13 `Edit`-without-`Read` errors accumulated because the orchestrator
"remembered" reading a file it had only read in a pre-compaction turn. This file is the on-disk source
of truth for both the dispatch skeleton and the post-compaction discipline.

## Read-before-Edit rule (compaction wipes read-state)
A successful `Read` is only valid within the SAME context window. After any compaction boundary the
harness's read-state is reset: an `Edit`/`Write` against a file you "already read" before the boundary
fails (or, worse, edits against a stale mental model). **After any compaction, re-`Read` every file
before you `Edit`/`Write` it** — even if you read it earlier this session. This applies to PHASES.md,
plan files, SKILLs, and every `_components/*.md`.

## Canonical cycle dispatch skeleton
Every real-work cycle is exactly ONE `Agent` call. Compose it with ALL of these fields — `model:` is
the field most often dropped post-compaction, so verify it is present on every dispatch:

    Agent({
      description: "<feature_id> cycle <N>: <sub_skill>",   // short statement of intent
      subagent_type: "general-purpose",                     // or the value lazy-state.py/the skill specifies
      model: "opus",                                        // REQUIRED — never omit. Normal cycles run Opus;
                                                            //   use "sonnet" ONLY on the LOOP-DETECTED branch.
      prompt: "<cycle base prompt from _components/lazy-batch-prompts/cycle-base-prompt.md, with
                {feature_id} / {spec_path} / {sub_skill} / {sub_skill_args} / {current_step}
                substituted, plus any per-skill override block>"
    })

- `model:` is **mandatory and explicit** on every dispatch. Do NOT rely on an inherited default — the
  post-compaction failure mode is precisely an omitted `model:` that silently mis-tiers the cycle.
- This file is the *envelope* (which fields, which model). The prompt *contents* are NOT inlined here —
  they live in `_components/lazy-batch-prompts/cycle-base-prompt.md`, read on demand.
- One cycle = one dispatch (HARD CONSTRAINT 4). Never chain sub-skills in a single dispatch.

## Manual-compact-during-dispatch cadence (sanctioned)
The operator's observed pattern — **manually triggering compaction at a cycle boundary, between the
end of one dispatch and the start of the next** — is the SANCTIONED cadence, not a hazard. Compacting
at a cycle boundary (rather than mid-dispatch) keeps task state + PHASES.md as the durable recovery
surface and avoids losing a half-composed dispatch. After such a compact, the recovery sequence is:
re-read THIS template → re-read the plan / PHASES.md → re-`Read` any file before editing it → resume at
the first non-`completed` task.
