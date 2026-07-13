---
kind: implemented
feature_id: lazy-batch-skill-deflation
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [03993c0, 664d9a7, 7678b5f, fe6fcd3]
decisions: []
---

# Implementation Ledger

**What shipped:** `user/skills/lazy-batch/SKILL.md` is 251,832 B / 1,597 lines (re-measured 2026-07-11) and growing ~30KB/week: 160KB (06-13) → 188KB (06-16) → 224KB (06-24) → 252KB (07-11), +57% in four weeks across 126 commits. 146 single-line paragraphs over 500 chars carry 144KB — 57% of the file (longest line 3,976 chars) — and an estimated ~25–35% (~65–85KB) is driftable RESTATEMENT of script behavior the state scripts already own and emit as verdict JSON. Excise mechanism narration down to verdict-field routing rules, relocate dated "Motivating incident" narratives to a HISTORY sidecar, and add a size + long-line lint ratchet so re-bloat fails a gate instead of accreting silently. The dispatcher tier proves the target shape: `/lazy` is 292 lines of pure dispatch glue over the same state machine.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
