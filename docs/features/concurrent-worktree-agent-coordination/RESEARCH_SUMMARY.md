# Research Summary — Concurrent multi-agent worktree coordination

**Research status:** SKIPPED by explicit operator decision (2026-07-18). No
external Gemini deep-research pass was run; see `RESEARCH.md` for the basis.

**Planning basis:** the locked SPEC baseline (four resolved design forks, all
reusing existing harness machinery — `lazy_coord.py` leases/lanes, git-as-oracle
conflict classification, commit-message-trailer comm channel).

**Key implementation anchors (from SPEC reuse map):**
- `lazy_coord.py` — per-item leases (`leases.json`), lane ledger (`lanes.json`),
  `merge_lane_branch` (queue-order merge, abort-and-demote on conflict).
- `lazy_core.run_transient_build` — orchestrator-owned transient worktree precedent.
- git auto-merge as the first-pass non-semantic/semantic oracle.

**Open follow-ups (vN, non-blocking):** per-file lock granularity refinement;
cloud/bug-pipeline merge-back path (v1 is workstation + feature-pipeline only).
