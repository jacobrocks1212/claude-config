---
kind: implemented
feature_id: plan-structure-authoring-gate
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [03993c0, 3c15b7e, 7678b5f, fe6fcd3]
decisions: [K1, K2, K3, K4, K5, K6]
---

# Implementation Ledger

**What shipped:** Add emit-time structural validation to plan-part and PHASES.md authoring: when `/write-plan` or `/spec-phases` write these files, a deterministic validator refuses structural defects the harness itself currently permits — missing per-WU `- [ ] WU-N` checklists, verification rows outside a recognized Runtime Verification subsection, unfilled template/boilerplate rows counted as work, and plan-part series that contradict declared dependency order. Every one of these defect classes today survives authoring and is caught only downstream, as a recovery or coherence-recovery meta-dispatch mid-run — the gate moves the refusal to the moment of authorship.

**Decisions that drove it:**
- K1 — **Per-WU checklist (plan parts, ERROR):** a `## Work Units` flat checklist with ≥1
- K2 — **Verification-row placement (plans + PHASES, ERROR):** every checkbox whose text matches
- K3 — **Template-row rejection (plans + PHASES, ERROR):** unfilled placeholders (`{…}` /
- K4 — **Gate-owned-row ban (plans + PHASES, ERROR):** `- [ ]` rows for Status flips / receipt
- K5 — **Dependency-ordered plan series (plan parts, ERROR):** every part carries a `-part-K`
- K6 — **Frontmatter sanity (WARN):** parseable frontmatter, `phases:` values numeric-ish (the

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
