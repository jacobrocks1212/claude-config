---
kind: needs-input
feature_id: mobile-queue-control
written_by: lazy-batch-input-audit
decisions:
  - Freshness marker — embed a generated-at timestamp in LAZY_QUEUE.md, or drop it and rely on GitHub's last-commit time
date: 2026-06-22
next_skill: spec
---

# Input Audit — Needs Input

## Decision Context

### 1. Freshness marker — embed a generated-at timestamp in LAZY_QUEUE.md, or drop it and rely on GitHub's last-commit time

**Problem:** The SPEC's User Experience section bakes an in-doc freshness stamp into the
document the user reads on GitHub mobile — the header line `# Lazy Queue — <repo>   (updated
<ts> · run active 🔒 | idle)` (SPEC.md line 49) and "the doc carries a generated-at timestamp
and a run-active/idle marker so a stale read is self-evident" (SPEC.md line 69). PHASES.md
Phase 1 then hits a conflict: an embedded wall-clock timestamp changes every run, which defeats
the byte-stability / no-spurious-commit goal the SPEC also requires (Validation row 2, Phase 3's
no-op-commit gate). The PHASES.md "Integration Notes for Next Phase" resolves this **on the
user's behalf**, recommending option (a) — derive freshness from the file's git commit time and
embed **no** wall-clock timestamp in the doc body at all (PHASES.md Phase 1 Integration Notes;
echoed in the Runtime Verification row "the timestamp-exclusion / git-time approach holds").
That changes what the user actually sees on their mobile read surface relative to the SPEC's
explicit mockup, so it is a product-behavior call (freshness UX / data-the-user-sees), not a
mechanical-internal one — surfacing it rather than letting the plan bake it in.

**Options:**
- **(a) No embedded timestamp — derive "last updated" from git commit time (Recommended)** —
  The doc body carries no wall-clock line; the run-active/idle (`🔒`/idle) marker stays. "Last
  updated" is whatever GitHub mobile shows natively for the file's last commit. Pro: trivially
  byte-stable (an unchanged-state regen is byte-identical → no spurious commit, satisfying the
  Phase 3 no-op gate with zero special-casing); GitHub mobile already surfaces commit time
  prominently. Con: the freshness signal lives in GitHub chrome, not in the rendered markdown —
  a reader who only screenshots/copies the doc body loses it; diverges from the SPEC's explicit
  `(updated <ts> …)` mockup. Reversible (re-add later).
- **(b) Keep the embedded `updated <ts>` line, exclude it from the byte-stability check** —
  Honor the SPEC mockup verbatim: the doc body shows `(updated <ts> · run active 🔒 | idle)`.
  Make the timestamp live on a single line that both the byte-stability self-check and the
  Phase 3 no-op-commit detector deliberately ignore (compare doc bytes modulo that one line).
  Pro: matches the SPEC's stated UX exactly; freshness is visible in the rendered doc itself on
  mobile. Con: the "byte-stable" property becomes "byte-stable modulo the timestamp line," a
  weaker invariant that needs a careful diff-exclusion in both the generator self-test and the
  Phase 3 commit detector — more surface for a stale-doc-but-no-commit or spurious-commit bug.
- **(c) Embed a state-derived freshness token, not a wall-clock** — Show a freshness signal in
  the body that only changes when state changes (e.g. "as of <latest item-advance event>" or a
  short state hash), so the doc stays genuinely byte-stable AND carries an in-body freshness cue.
  Pro: keeps an in-doc signal without breaking byte-stability. Con: "freshness" then tracks
  last-state-change, not last-generation — subtly different semantics the user must understand;
  more renderer logic than either (a) or (b).

**Recommendation:** (a) — it is the cleanest path to the SPEC's hard byte-stability/no-op-commit
requirement and GitHub mobile already shows last-commit time, but because it drops an element the
SPEC's UX mockup explicitly draws, the operator should confirm rather than have the plan silently
remove the visible timestamp.

## Resolution

*Recorded on 2026-06-22 14:21:36 UTC.*

### 1. Freshness marker — embed a generated-at timestamp in LAZY_QUEUE.md, or drop it and rely on GitHub's last-commit time

**Choice:** (a) No embedded timestamp — derive "last updated" from git commit time
**Notes:** Operator confirmed the recommended path. The doc body carries no wall-clock line; the
run-active/idle (`🔒`/idle) marker stays. Freshness is read from GitHub's native last-commit time.
SPEC's `(updated <ts> …)` mockup is superseded by this resolution — the visible wall-clock element
is intentionally dropped to preserve byte-stable regeneration (Phase 3 no-op-commit gate).
