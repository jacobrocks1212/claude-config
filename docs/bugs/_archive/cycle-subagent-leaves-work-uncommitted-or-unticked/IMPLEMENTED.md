---
kind: implemented
feature_id: cycle-subagent-leaves-work-uncommitted-or-unticked
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [cc820af, 0d28bd3, b1e1f76, d0d66d3, 63dec27, ec97782, c4b141a, f29cc48]
decisions: []
---

# Implementation Ledger

**What shipped:** Across multiple `/lazy-batch` runs, cycle subagents do the real work but fail to finish the turn cleanly: deliverables are left uncommitted (HEAD unchanged), PHASES.md/plan-file checkboxes are left unticked, and SPEC/plan frontmatter is flipped to Complete without the body ledger being reconciled. The `verify-ledger` step catches these every time, but each catch forces an extra recovery-cycle dispatch — pure meta overhead. This was the most consistent cross-session friction pattern in the audit.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
