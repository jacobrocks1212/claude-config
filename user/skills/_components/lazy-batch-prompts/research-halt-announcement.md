# lazy-batch — research halt announcement templates

<!-- Canonical announcement templates for both research-halt sites in /lazy-batch.
     Two variants share the same per-feature prompt block and upload instructions:
       - Variant A (Step 4, needs-research strict halt): single feature, prominent
         FASTEST RESUME inline. Bind: {feature_name}, {feature_id}, {spec_path},
         {RESEARCH_PROMPT content}, {NNNN chars}, {within|over},
         {max_cycles}.
       - Variant B (Step 1f, queue-blocked-on-research): multiple features, looped
         per-feature blocks then unified upload instructions. Bind: {N},
         {comma-separated feature_ids from research_pending}, per-feature
         {feature_id}, {feature_name}, {spec_path}, {RESEARCH_PROMPT content},
         {NNNN chars}, {within|over}, {max_cycles},
         [--allow-research-skip] (Step 1f always runs under --allow-research-skip).

     Placeholder note for the length indicator line:
       {within | over} is chosen by comparing measured char count to 24,000
       (Gemini's practical web-UI character cap; see ~/.claude/skills/spec/SKILL.md
       Phase 2 for source notes). When over, append "(may need manual trimming
       before paste)" to that line — informational only, do NOT refuse to print.

     POINTER-RESOLUTION note for {RESEARCH_PROMPT content} (both variants):
       The {…RESEARCH_PROMPT content…} token is the EFFECTIVE (resolved) prompt,
       NOT necessarily the literal bytes of {spec_path}/RESEARCH_PROMPT.md. When
       that file is a POINTER doc (a short file whose body mostly links to another
       feature's RESEARCH_PROMPT.md — e.g. "Combined with <other> research (they
       ship as a unit)" + a [link](../<other>/RESEARCH_PROMPT.md), often with a
       focus note like "Sections 4 and 7 are most relevant"), the caller (lazy-batch
       Step 4 step 1 / lazy-batch-cloud Step 4) resolves it ONE level: follows the
       link, surfaces the referenced prompt's named focus sections (+ its Context /
       identity preamble) — or the whole referenced file if no sections are named —
       and PREPENDS the focus note verbatim. Surface the resolved content here so
       the operator can paste a real prompt into Gemini, never a 3-line pointer.
       Pointer resolution changes WHAT is surfaced; it NEVER waives the halt — the
       feature still requires its OWN RESEARCH.md (anti-exemption rule, lazy-batch
       Step 4). Burned on d8-effect-chains, 2026-06-14. -->

---

## Variant A — Step 4 (single feature, `needs-research` strict halt)

Print the block below verbatim, binding all {tokens}:

```
⏸  /lazy-batch paused — {feature_name} needs Gemini research.

Feature: {feature_id}
Prompt file: `{spec_path}/RESEARCH_PROMPT.md`

**Research prompt** (copy this entire block into Gemini Deep Research):

```text
{full RESEARCH_PROMPT.md content, verbatim, including the `## Project context` identity prepend if present}
```

[length: {NNNN} chars — {within | over} Gemini's 24,000-char practical web-UI limit]

FASTEST RESUME — upload the research in your NEXT MESSAGE in this
conversation (file attachment, pasted text, or absolute path). I will
dispatch /ingest-research IN-SESSION (writing the tracked RESEARCH.md +
RESEARCH_SUMMARY.md into the feature directory) and re-invoke /lazy-batch
automatically. No manual re-run required. See Step 5: In-Session Resume
Protocol.

Alternative upload paths (use these if you prefer to stage and resume
later):
  ① Save as docs/gemini-sprint/results/{feature_id}.txt. The next
     /lazy-batch run auto-ingests via Step 0.5. NOTE: this path is
     gitignored — a bare .txt stage is non-durable across cloud-container
     reclaim. Use the in-session path above or path ② if cloud durability
     matters.
  ② Drop directly as {spec_path}/RESEARCH.md (skips ingestion;
     lazy-state.py routes to /spec Phase 3 on next run). This file IS
     tracked, so it survives cloud reclaim.
  ③ /ingest-research <path> for a one-off file outside the repo
     (workstation only — cloud cannot see file paths outside the
     container's repo working tree). Then re-run /lazy-batch.

Re-invoke with /lazy-batch {max_cycles} when ready (only required if you
did NOT use the in-session resume path above).
```

---

## Variant B — Step 1f (multiple features, `queue-blocked-on-research`)

<!-- Only reachable when allow_research_skip == true. -->

Print the opening block, then iterate over each pending feature, then the
unified upload instructions:

**Opening block:**

```
⏸  /lazy-batch paused — {N} feature(s) awaiting Gemini research.

Pending: {comma-separated feature_ids from research_pending}

───────────────────────────────────────────────────────────────────────────
```

**Per-feature block (repeat for EACH pending feature in order):**

```
### {feature_id} — {feature_name}

Prompt file: `{spec_path}/RESEARCH_PROMPT.md`

**Research prompt** (copy this entire block into Gemini Deep Research):

```text
{full RESEARCH_PROMPT.md content, verbatim, including the `## Project context` identity prepend if present}
```

[length: {NNNN} chars — {within | over} Gemini's 24,000-char practical web-UI limit]

───────────────────────────────────────────────────────────────────────────
```

**Unified upload instructions (print once, after all per-feature blocks):**

```
When you have research result(s), the fastest path is to upload them in your
NEXT MESSAGE in this conversation — I will dispatch /ingest-research
IN-SESSION and re-invoke /lazy-batch automatically (see Step 5: In-Session
Resume Protocol). You do NOT need to re-run /lazy-batch manually.

Supported upload shapes for your next message:
  • File attachment (Claude Code path or chat-uploaded file)
  • Pasted text — the research content in a fenced code block or quoted
  • An absolute file path on the machine running this session (e.g.
    ~/Downloads/<file>.txt or a phone-synced folder)

Or, if you prefer to stage the file and resume later, any of these paths
still work:

  ① Staged (gemini-sprint workflow):
     Save each Gemini output as docs/gemini-sprint/results/<feature-id>.txt
     (one file per feature). NOTE: this path is gitignored in AlgoBooth —
     fine for a workstation session that resumes locally, but a bare .txt
     stage WILL NOT persist across a cloud-container reclaim. Path ② is
     durable; the in-session resume above is durable AND immediate.

  ② Canonical drop (skip ingestion, durable):
     Write the research directly as
     docs/features/.../<feature-id>/RESEARCH.md
     On your next /lazy-batch run, lazy-state.py routes straight to Step 5
     (integrate research → /spec Phase 3) — no ingestion step needed.

  ③ One-off file path (workstation only):
     Run /ingest-research <absolute-or-relative-path-to-the-file> first.
     That skill copies the file into the staging dir, correlates it, and
     writes RESEARCH.md + RESEARCH_SUMMARY.md. Then re-run /lazy-batch
     to resume the pipeline.

Re-invoke with /lazy-batch {max_cycles} [--allow-research-skip] when ready
(only required if you did NOT use the in-session resume path above).
```
