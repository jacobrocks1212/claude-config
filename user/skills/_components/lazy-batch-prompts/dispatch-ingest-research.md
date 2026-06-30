<!-- @requires item_name,spec_path,staged_files,item_id,cwd -->
<!-- dispatch-ingest-research.md — emitted by emit_dispatch_prompt("ingest-research", ...)
     Derived from lazy-batch/SKILL.md Step 0.5 (pre-loop staged-research ingest) and Step 5
     (in-session resume protocol). This template is the script-emitted, registry-registered form
     of the /ingest-research dispatch the orchestrator previously had NO emit path for. Step 0.5
     dispatches /ingest-research as an UN-MARKED pre-loop cycle (before Step 0.55 writes the run
     marker), so the hand-composed prompt was allowed; but when the run marker is already present
     — Step 5 in-session resume (research arrives mid-run), or any ordering where --run-start ran
     first — the validate-deny guard denies the hand-composed ingest prompt and there was no
     registry alternative, forcing a marker teardown (harden Round 44, 2026-06-29). With this class
     the ingest is dispatchable marker-active: --emit-dispatch ingest-research.
     TOKENS: standard pipeline tokens + @requires keys above. -->

<!-- @section role pipelines=feature,bug modes=workstation,cloud -->
You are advancing one cycle of the autonomous pipeline by INGESTING staged Gemini deep-research
into the {item_label}'s tracked docs. Research result file(s) have already been materialized into
the staging dir; your job is to run /ingest-research so the durable, git-tracked RESEARCH.md +
RESEARCH_SUMMARY.md exist (and any pre-Gemini stub markers are cleared) before any container
reclaim or the next state probe.

{item_label}: {item_name} ({item_id})
Working directory: {cwd}
Spec path:        {spec_path}
Staged research file(s): {staged_files}

<!-- @section job-steps pipelines=feature,bug modes=workstation,cloud -->
Ingest algorithm:

1. Invoke the /ingest-research skill (batch mode is implicit). It scans `docs/gemini-sprint/results/`
   for every staged `.txt`, correlates each to its {item_label} (by the prompt symlinks under
   `docs/gemini-sprint/prompts/`, or by the `.txt` basename matching the item id when no symlink
   exists), and per item: writes `RESEARCH.md` (the durable, git-tracked research artifact) +
   `RESEARCH_SUMMARY.md` (a concise summary cross-referenced to the open questions in
   RESEARCH_PROMPT.md), drops any `> Draft (pre-Gemini)` / pre-Gemini stub trailer in SPEC.md,
   clears `queue.json "stub": true` for the entry if set, neutralizes any stale `NEEDS_RESEARCH.md`,
   moves the consumed `.txt` to `docs/gemini-sprint/results/_consumed/`, and commits per item.

2. The staged file(s) for THIS dispatch are listed above. The correct target dir is the spec path
   shown above. If /ingest-research cannot auto-correlate a file (no prompt symlink AND ambiguous
   basename), ingest it MANUALLY following the same contract (write RESEARCH.md + RESEARCH_SUMMARY.md
   into that spec path, clear NEEDS_RESEARCH.md, move the .txt to _consumed/, commit) — do NOT leave
   the research un-ingested.

3. Cloud-durability note: `docs/gemini-sprint/results/` is gitignored, so a staged `.txt` does NOT
   persist across container reclaim — but the RESEARCH.md + RESEARCH_SUMMARY.md /ingest-research
   writes into the item dir ARE tracked and DO persist. That durability is the whole point of
   running the ingest in-session rather than just staging.

<!-- @section constraints pipelines=feature,bug modes=workstation,cloud -->
CONSTRAINTS:
- WORK-BRANCH-ONLY: commit + push to the CURRENT branch only (`git rev-parse --abbrev-ref HEAD` at
  start); NEVER create a branch, NEVER --force.
- You MAY NOT spawn further subagents (no Agent tool). Use Read/Grep/Glob/Bash/Edit/Write directly.
- Scope is STRICTLY research ingestion. Do not perform implementation work, do not flip SPEC/PHASES
  Status beyond what /ingest-research's stub-clearing does, do not write the {receipt_name} receipt.
- The {forbidden_status} status must NOT be set on any {item_label} doc.

<!-- @section push-rule-workstation pipelines=feature,bug modes=workstation -->
Push the work branch after the ingest commit(s): git push origin $(git rev-parse --abbrev-ref HEAD).
(If the orchestrator owns the push backstop, "Everything up-to-date" is a fine result.)

<!-- @section push-rule-cloud pipelines=feature,bug modes=cloud -->
Push IMMEDIATELY after each ingest commit (container-reclaim durability): git push origin $(git rev-parse --abbrev-ref HEAD) after every commit.

<!-- @section return-format pipelines=feature,bug modes=workstation,cloud -->
GROUND-TRUTH OUTPUT — return a one-paragraph summary (under 6 lines) covering:
- The /ingest-research final summary (or your manual-ingest summary).
- Confirm RESEARCH.md now exists on disk for each ingested item (in the spec path shown above).
- Confirm any stale NEEDS_RESEARCH.md was neutralized.
- Any ambiguous correlations (NEEDS_INPUT.md sentinels written) — the next probe will surface them.
- The landed commit hash(es).
