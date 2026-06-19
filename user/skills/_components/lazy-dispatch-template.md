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
- **NEVER hand-append to `cycle_prompt`.** Repo-specific instructions (e.g. an audio-INVARIANTS gate) do
  NOT belong splice onto the emitted prompt — they live in `<repo>/.claude/skill-config/cycle-prompt-addenda.md`
  (same `@section` grammar as the base template), which the SCRIPT reads and appends, token-bound and
  residue-checked, as part of `cycle_prompt`. A live orchestrator hand-spliced the AlgoBooth audio gate
  onto the prompt on 2026-06-11 — that path is now closed; if a repo gate is missing, add a section to the
  addenda file, do not edit the dispatch.
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

## Full-probe-JSON read before routing (completeness, not just freshness)

**A routing/dispatch decision MUST be made against the COMPLETE current probe JSON. Never field-extract a
subset of keys (no jq-style / pipe cherry-pick of e.g. `pending_hardening`, `terminal_reason`) and route
on that subset** — any signal OUTSIDE the extracted subset is then invisible to the decision.

At-risk keys that a partial read can silently drop: `terminal_reason`, `notify_message`, `diagnostics`,
`device_deferred_features`, `git_guards`, `self_edit_mode`, `governing_files_touched`,
`route_overridden_by`, `cycle_prompt_refused`, `repeat_count`, `hardening_emit_command`, `cycle_header`,
`cycle_prompt`, `cycle_model`. If any of these carry a live signal and the orchestrator routed on a
hand-picked subset that omitted the key, the signal is silently dropped and the route can be wrong.

**This clause is ADDITIVE to the existing atomicity (provenance) and freshness (same-turn) rules:**
- Atomicity (`lazy-batch/SKILL.md:591`) governs WHERE the prompt came from — only `cycle_prompt` from an
  `--emit-prompt` probe in the SAME turn.
- Freshness (`lazy-batch/SKILL.md:593`) governs WHEN — never dispatch an emission from an earlier turn.
- This clause governs HOW COMPLETELY the probe output is consumed — the whole JSON, not a subset.

**Precedent:** `user/scripts/lazy-state.py:6654–6664` records that a prior live mis-route arose when
an orchestrator field-extracted `cycle_model` over live hardening debt (session e076ed30). The script
now withholds `cycle_prompt`/`cycle_model` on pending hardening debt so "the extractor fails loudly on
the missing key." That is a point-harden for ONE key. This clause is the **general contract** that
prevents the same failure class for every other key — the prose contract the point-fix assumed but
never stated.
