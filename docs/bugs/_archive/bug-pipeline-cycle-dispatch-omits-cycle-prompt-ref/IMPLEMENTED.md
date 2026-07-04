---
kind: implemented
feature_id: bug-pipeline-cycle-dispatch-omits-cycle-prompt-ref
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [17c1fee, 99293d6, 3201bac, e08c7a9, 447ce6a]
decisions: []
---

# Implementation Ledger

**What shipped:** `bug-state.py --emit-prompt` registers the cycle prompt in the by-reference registry but never surfaces the `@@lazy-ref` token, so `/lazy-bug` and `/lazy-bug-batch` dispatch every real-skill cycle by value — re-inlining 9.5–12K-char prompts the feature pipeline passes as a 49-char reference.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
