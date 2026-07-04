---
kind: implemented
feature_id: code-doc-provenance-linkage
date: 2026-07-04
provenance: pipeline-gated
derivation: message-grep
commits: [941fc16, 02b7051, 95451a7, 839465c, '8827965', '6087595', 3d9c283, 4e0faf6, 74e345d,
  65b340f]
decisions: []
---

# Implementation Ledger

**What shipped:** Make the linkage between documentation and the code it governs a **byproduct of the agentic workflow**: at `__mark_complete__`/`__mark_fixed__`, distill each feature/bug into a small durable artifact (`IMPLEMENTED.md`: what shipped, which Locked Decisions drove it, why) and record the touched-file set from the cycle commits into a repo-level reverse index (file path → feature/bug slugs). Skills and cycle subagents consult the index before editing — "you're touching `lazy_core.py`; these 4 decision records govern it" — turning the docs corpus from a write-only archive into working memory. One deterministic producer, two triggers: the automatic completion-gate path and an operator-invocable manual path for out-of-pipeline work.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
