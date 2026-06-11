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
      model: <the probe's cycle_model>,                     // REQUIRED — never omit. Copy the value VERBATIM
                                                            //   from the probe's cycle_model field; do NOT
                                                            //   hand-choose. Script-owned: "opus" normally,
                                                            //   "sonnet" only when it appended the loop block.
      prompt: <the probe's cycle_prompt, VERBATIM>          // the fully-assembled, token-bound cycle prompt
                                                            //   from --emit-prompt (sections selected, all
                                                            //   {tokens} bound, loop block already appended
                                                            //   when warranted). Do NOT reconstruct by hand.
    })

- `model:` is **mandatory and explicit** on every dispatch. Do NOT rely on an inherited default — the
  post-compaction failure mode is precisely an omitted `model:` that silently mis-tiers the cycle. Copy
  the probe's `cycle_model` value; never omit it.
- The prompt *contents* are **script-assembled** — the probe's `cycle_prompt` (the `--emit-prompt` field)
  is the fully-bound prompt; the orchestrator copies it VERBATIM and never hand-binds `{tokens}` or reads
  `cycle-base-prompt.md`/`loop-block.md` by hand (the sole exception is the documented `cycle_prompt`-refused
  fallback). This file is the *envelope* (which fields, which model + Read-before-Edit) — the prompt
  contents are NOT inlined here; they live in `_components/lazy-batch-prompts/cycle-base-prompt.md`, which
  the SCRIPT reads to assemble `cycle_prompt`.
- One cycle = one dispatch (HARD CONSTRAINT 4). Never chain sub-skills in a single dispatch.

## Manual-compact-during-dispatch cadence (sanctioned)
The operator's observed pattern — **manually triggering compaction at a cycle boundary, between the
end of one dispatch and the start of the next** — is the SANCTIONED cadence, not a hazard. Compacting
at a cycle boundary (rather than mid-dispatch) keeps task state + PHASES.md as the durable recovery
surface and avoids losing a half-composed dispatch. After such a compact, the recovery sequence is:
re-read THIS template → re-read the plan / PHASES.md → re-`Read` any file before editing it → resume at
the first non-`completed` task.

**Post-compaction, the discipline protects the ENVELOPE — never reconstruct the prompt from memory.**
Because the prompt contents are now script-assembled, compaction can no longer drop a hand-typed prompt
binding — but it CAN still drop the `model:` field or leave a stale read-state. So after any compaction
the protected surface is: (a) the dispatch ENVELOPE (`description` / `subagent_type` / the REQUIRED
`model:` field) and (b) the Read-before-Edit rule. **Do NOT reconstruct the cycle prompt from memory** —
re-run the probe WITH `--emit-prompt` and copy the fresh `cycle_prompt` / `cycle_model` verbatim. A
prompt rebuilt from a pre-compaction memory is exactly the stale-mental-model failure this file exists to
prevent.
