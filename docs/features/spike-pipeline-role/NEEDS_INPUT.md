---
kind: needs-input
feature_id: spike-pipeline-role
written_by: write-plan
decisions:
  - Promote SPIKE_VERDICT.md to a recognized sentinel (Open Question 1)?
date: 2026-07-18
next_skill: write-plan
class: product
divergence: contained
partial_artifacts: []
---

## Decision Context

### 1. Promote SPIKE_VERDICT.md to a recognized sentinel (Open Question 1)?

**Problem:** Phases 1–5 of the Spike role are Complete. The ONLY phase with unchecked
deliverables is Phase 6 ("(Cross-repo, NON-harden-harness) recognized-sentinel promotion —
IF wanted"), whose `**Status:**` is literally "Not started — surfaced only" and whose single
actionable deliverable is gated on **Open Question 1**: does the operator want full lint/gate
coverage of the Spike verdict schema? The SPEC deliberately CHOSE a plain audit markdown doc
(`SPIKE_VERDICT.md`) for the verdict — see the SPEC's `## Non-goals` — precisely to keep the
whole role inside claude-config, because promoting `SPIKE_VERDICT.md` to a *recognized* sentinel
requires editing AlgoBooth's `scripts/check-docs-consistency.ts SENTINEL_SCHEMAS`, a target-repo
edit harden-harness/claude-config sessions may NOT make (harden-harness Prohibition #1; the
deliverable itself says "**AlgoBooth repo — outside harden-harness scope; a normal AlgoBooth
session must make this edit**"). Phase 6's second deliverable ("Until then, the verdict rides on
a plain audit doc … which is fully functional") is a *descriptive statement of the current
design*, not `/execute-plan`-closable work. Consequently there is no plannable work unit here
without an operator decision to pursue promotion — and even a "yes" leaves half the work in a
different repo that this cycle cannot touch. `/write-plan` cannot pick a side of an
explicitly-open, out-of-scope-spanning product question, so it halts.

**Options:**
- **Keep the plain audit doc (Recommended)** — Close Phase 6 with no action. The Spike role
  stays fully functional on a plain `SPIKE_VERDICT.md` audit doc plus already-recognized
  sentinels (`BLOCKED.md` with `blocker_kind: runtime-spike-verdict-pending` on entry,
  `NEEDS_INPUT.md` on FAIL). This is the SPEC's locked design (its `## Non-goals` explicitly
  bans the recognized-sentinel filename to respect Prohibition #1) and the ONLY path entirely
  inside claude-config scope. Cost: the verdict header schema gets no automated lint enforcement
  — a malformed verdict header could ship undetected. Fully reversible: promotion can be done
  later as a separate AlgoBooth-scoped change. Under this option Phase 6 needs no plan; the
  feature routes toward completion with Phase 6 recorded as an intentionally-unbuilt "IF wanted"
  design phase (operator may mark it Won't-do / Superseded, or leave it surfaced).
- **Promote to a recognized sentinel** — Add the `SPIKE_VERDICT` schema to claude-config's
  `sentinel-frontmatter.md` AND to AlgoBooth's `scripts/check-docs-consistency.ts
  SENTINEL_SCHEMAS`, giving the verdict schema full lint/gate coverage. Two blocking problems:
  (1) the AlgoBooth half is explicitly OUTSIDE harden-harness/claude-config scope (Prohibition
  #1) and must be authored by a normal AlgoBooth session, so any plan written here is inherently
  partial and cross-repo — this claude-config cycle can only author the claude-config half;
  (2) it directly contradicts the SPEC's `## Non-goals` as written, so choosing it also requires
  a SPEC amendment. Higher coordination cost; correct only if the operator now wants the lint
  coverage and accepts the cross-repo follow-up.

**Recommendation:** Keep the plain audit doc — it is the SPEC's locked design and the only
fully in-scope path, the role is already fully functional without promotion, and promotion
remains available later as an AlgoBooth-scoped follow-up (exactly as Open Question 1 frames it).
