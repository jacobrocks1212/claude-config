---
kind: implemented
feature_id: claude-md-maintenance-v2
date: 2026-07-17
provenance: pipeline-gated
derivation: message-grep
commits: []
decisions: [L1, L2, L3, L4, L5, L6]
---

# Implementation Ledger

**What shipped:** Two coupled bodies of work: (1) trim ~16.5 KB of non-durable bloat out of the 12 Cognito Forms `CLAUDE.local.md` files, and (2) fix the skill prescription that produced it — by inverting the post-implementation default from "review-and-usually-write" to "no-update-unless-it-passes-the-bar" and importing `/retro`'s existing generalization test into the shared `claude-md-review.md` component.

**Decisions that drove it:**
- L1 — **Prescription fix = invert default + import `/retro`'s test** (not: add another durability rule — that already exists and lost; not: delete the prescription and route via `/retro` only — loses in-the-moment capture of durable gotchas; not: byte-budget lint — byte count can't distinguish durable from bloat).
- L2 — **AGENTS.md ↔ CLAUDE.local.md build-command contradiction left as-is** — not resolved in this spec. Field evidence: agents have been reliably choosing `/msbuild`/`/mstest` over the raw `dotnet` commands AGENTS.md prescribes. Recorded here so it is not "rediscovered" and mistakenly fixed later; AGENTS.md is correct for teammates/Copilot who have neither the skills nor the hook.
- L3 — **`.agents/agent-docs/` overlap → pointers.** Where agent-docs covers a topic equal-or-better, the `CLAUDE.local.md` replaces its restatement with a one-line pointer. Cuts auto-loaded tokens every session and kills the divergent testing-conventions advice.
- L4 — **Cleanup scope = all 12 files, one trim pass** (not just the 6 offenders — leaves the root file's actively-wrong inventories; not scratch-rewrite — 67% is already durable and incident-earned). Plus standardize the `Maintenance:` footer onto all 12.
- L5 — **"Key Files" / API-catalog inventory tables → delete** (largest bloat class, ~9 KB; they go stale silently — all three current inventories already omit real dirs; recoverable via Glob/tree-sitter).
- L6 — **Success KPI = auto-loaded corpus bytes** (mechanical `wc -c`; baseline 50,182 B; down-is-good; band on regrowth). Durable-ratio deferred — needs a model pass every measurement.

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
