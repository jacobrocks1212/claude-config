---
kind: needs-input
feature_id: lazy-batch-skill-deflation
written_by: spec
decisions:
  - D2 — motivating-incident narratives relocate to a HISTORY sidecar
date: 2026-07-12
next_skill: spec-phases
class: product
divergence: isolated
audit_divergence: isolated
---

# lazy-batch-skill-deflation — Needs Input

Research is integrated (this SPEC's own inline recon — byte counts, section anatomy, hotspot
sizing). One **product-behavior** decision gates finalizing the SPEC beyond auto-acceptable
mechanics: where dated "Motivating incident" narratives currently embedded in
`user/skills/lazy-batch/SKILL.md` go once excised from the resident prompt. D1 (excision
principle), D3 (ratchet lint), and D4 (mirroring strategy) are `mechanical-internal` and are
auto-accepted per their SPEC `**Recommendation:**` lines — see `## Locked Decisions` in SPEC.md.

## Decision Context

### 1. D2 — Motivating-incident narratives relocate to a HISTORY sidecar

**Problem:** The file is dense with dated "Motivating incident (2026-06-XX): ..." paragraphs —
valuable as audit trail, dead weight as resident prompt. Where do they go?

**Options:**
- **A — HISTORY.md sidecar in the skill directory (Recommended):**
  `user/skills/lazy-batch/HISTORY.md`, keyed by rule id/section; the skill keeps the rule +
  `(burned: <slug>)` citation; the sidecar keeps the narrative. Not runtime-loaded; grep-able
  when a rule's provenance is questioned.
- **B — the hardening log / claude-config bug specs:** many incidents already have `docs/bugs/`
  or feature-spec homes; pure pointers from the skill would suffice — but a non-trivial subset
  exists ONLY as in-skill narrative today, and scattering those across retroactive bug docs
  fabricates history.
- **C — delete outright:** loses the audit trail that justifies each hard rule; rules without
  provenance get "simplified" away by future editors — the exact rot the citations prevent.

**Recommendation:** A, with B opportunistically: where a doc already exists, the sidecar entry
is a pointer, not a copy. Needs operator sign-off because it changes where incident provenance
lives for the harness's most safety-critical skill.

## Resolution

resolved_by: auto-provisional
decision_commit: fe6fcd3240e9d2589a2345072b8d0fe5fa65d0c6

**Provisionally accepted** under the operator's overnight park-provisional blanket directive
(2026-07-12). Option A is adopted and this feature's implementation proceeds against it — a
`HISTORY.md` sidecar is created at `user/skills/lazy-batch/HISTORY.md`, keyed by rule id/section,
carrying each relocated dated incident narrative; the canonical skill keeps only the rule plus a
`(burned: <slug> — see HISTORY.md#<anchor>)` citation. SPEC.md's Status stays **Draft** and NO
`COMPLETED.md` is written — completion is mechanically blocked while this unratified
`NEEDS_INPUT_PROVISIONAL.md` exists. The operator ratifies or redirects this choice before the
feature can ever complete.

**Divergence graded `isolated`** — the choice affects only WHERE incident-provenance narrative
text lives (a sidecar file vs. inline vs. deleted); it does not change any rule, gate, terminal
route, or the skill's runtime behavior. A later redirect (e.g. to option B or C) touches only the
relocated-narrative bookkeeping, not the excised rules themselves — the two-key eligibility
predicate (`divergence` + `audit_divergence` both `isolated`) is satisfied, consistent with the
low-risk shape `park-provisional-acceptance` is designed for.

**Choice:** A — HISTORY.md sidecar in the skill directory (with B opportunistically where an
existing doc already covers an incident).
