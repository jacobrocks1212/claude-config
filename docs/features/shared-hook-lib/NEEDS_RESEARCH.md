---
kind: needs-research
feature_id: shared-hook-lib
research_prompt_path: RESEARCH_PROMPT.md
written_by: lazy-batch
date: 2026-07-18
---

# /lazy-batch — Needs Research

Run Gemini deep research against the prompt at `RESEARCH_PROMPT.md`,
then provide the result via any of these upload paths:

① Staged .txt (gemini-sprint workflow): save the output as
  `docs/gemini-sprint/results/shared-hook-lib.txt`. /lazy-batch's Step 0.5
  pre-loop check will auto-dispatch /ingest-research on the next run.

② Direct RESEARCH.md drop: write the result directly to RESEARCH.md
  alongside this file. lazy-state.py Step 5 will route to /spec Phase 3
  on the next /lazy-batch run.

③ One-off file path: if the file lives outside the repo (e.g.
  ~/Downloads/<file>.txt), run /ingest-research <path> before re-invoking
  /lazy-batch. That skill stages and ingests it into the canonical
  location, then /lazy-batch picks it up via path ②.

/lazy-batch waits passively while research is in flight — re-invoke when
ready. The orchestrator does NOT poll the filesystem.

**Prompt file:** `RESEARCH_PROMPT.md`
