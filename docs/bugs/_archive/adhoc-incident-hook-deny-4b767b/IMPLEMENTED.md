---
kind: implemented
feature_id: adhoc-incident-hook-deny-4b767b
date: 2026-07-06
provenance: pipeline-gated
derivation: commit-brackets
commits: [bb8a486, 303989c, c982b94, d4204e6, 19d26e1]
decisions: []
---

# Implementation Ledger

**What shipped:** The `_LAZY_BATCH_RE` recursion trip in `lazy-cycle-containment.sh` matches a `lazy-batch` token ANYWHERE in a subagent's Bash command — including benign file-path references (`cat`/`grep`/`ls`/`git add` on the `lazy-batch*` skill files). In claude-config, the very repo that houses those skill files, a cycle subagent doing legitimate lazy-pipeline investigation trips the containment deny repeatedly. The deny is a false positive; the fix is to anchor the trip to an actual command invocation, mirroring the `_CMD_START` carve-out already proven in `build-queue-enforce.sh`.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
