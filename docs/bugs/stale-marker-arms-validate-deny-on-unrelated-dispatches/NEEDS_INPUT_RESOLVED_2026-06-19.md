---
kind: needs-input
feature_id: stale-marker-arms-validate-deny-on-unrelated-dispatches
written_by: spec-phases
class: product
decisions:
  - Discriminator mechanism for pipeline-vs-unrelated dispatches
  - Disposition of an unrelated (non-pipeline) deny
  - Under-fire single-slot ownership fix — in-scope or split to follow-up
date: 2026-06-19
next_skill: plan-bug
---

# /spec-phases --batch — Needs Input

These three decisions are the load-bearing design fork the SPEC explicitly deferred
to the planning step (Proven Finding #4: "Distinguishing pipeline from unrelated is
the load-bearing design decision and is left to /plan-bug"; the three `## Open
Questions`). They are PRODUCT-class: the options diverge in **enforcement semantics**
— what the guard polices, what it allows, and what accrues as hardening debt — not in
effort or sequencing. Authoring a PHASES.md that silently picks one mechanism would
bake a wrong-enforcement design into the plan; per the spec-phases red-flag protocol
(unclear/undecided scope) this halts for the operator. Decisions 1 and 2 are coupled
(the mechanism largely determines the available dispositions); decision 3 is the
scope boundary between this bug and a possible follow-up.

## Decision Context

### 1. Discriminator mechanism for pipeline-vs-unrelated dispatches

**Problem:** The over-fire root cause is that the dispatch-guard has no way to tell a
real pipeline cycle from an ordinary, unrelated Agent dispatch (a hand-composed "spec
this feature" prompt) made in the same session/repo while a `/lazy-batch` run marker is
live. The guard's gate is **session-blind** — `lazy-dispatch-guard.sh` queries
`lazy-state.py --marker-present` with NO `--session-id`, so within a repo every
in-session dispatch is policed while any non-stale marker is present
(`lazy_core.read_run_marker` staleness-path-B fires ONLY when both caller and marker
carry a session_id; the gate passes `None` → path B disabled). The marker DOES carry an
owning `session_id` slot (bound at allow-time by `_bind_marker_on_allow`), so the
information needed to scope by owning session already exists — the gate just doesn't
consult it. Which mechanism cleanly separates pipeline cycles from unrelated work
without weakening enforcement is the load-bearing call. The fix must preserve the sacred
invariants: fail-OPEN on any error, never DESTROY the owning run's marker from a
non-owner read (Phase 8 WU-8.1), never weaken the depth-1 hardening cap.

**Options:**
- **A. Owning-session scoping at the gate (Recommended)** — Pass `--session-id` from
  `lazy-dispatch-guard.sh` into `--marker-present`, and have the handler treat the marker
  as "present" ONLY when the caller's session is the marker's bound owner (re-enable
  staleness-path-B at the gate). Effect: a dispatch from the OWNING orchestrator session
  runs the full guard (pipeline cycles policed exactly as today); a dispatch from any
  OTHER session — including an interactive operator typing an unrelated spec prompt in the
  same repo — sees "no marker for me" → fast-path allow, never policed, never ledgered.
  Cost: bash hook change + handler change + path-B re-enable at the gate; symmetric with
  the guard's existing `read_run_marker(session_id=…)` call so the two reads agree. Risk:
  an UNBOUND marker (run started, no allow yet) has `session_id: None` → path B can't fire
  → it would still police every dispatch in that pre-bind window. Reversible. This is the
  mechanism the SPEC's Finding #4 and Affected-Area table both lead with ("gate the guard
  on owning session, not mere repo-presence").
- **B. Explicit orchestrator/agent provenance signal** — Have the orchestrator stamp a
  signal on its own dispatches (e.g. a `LAZY_ORCHESTRATOR`/`agent_id` env marker or a
  prompt-envelope tag, mirroring the existing C3 `refuse_if_cycle_active` env discipline),
  and let the guard police ONLY dispatches carrying that signal; everything else fast-path
  allows. Effect: provenance is explicit rather than inferred from session identity, so it
  is robust to the unbound-marker window and to session-id churn. Cost: the orchestrator
  must reliably set the signal on EVERY pipeline dispatch (a missed stamp = a policed
  cycle wrongly allowed — fails toward under-enforcement, the opposite risk of A). Risk:
  the PreToolUse hook cannot read an Agent-call env var the way it reads cwd; a
  prompt-envelope tag is forgeable by a bystander unless tied to the registry. Larger
  surface than A.
- **C. Non-debt ledger discriminator only (no gate change)** — Leave the gate as-is
  (still policing every in-session dispatch) but tag a denied dispatch that fails the
  pipeline test with a discriminator the debt count skips — i.e. continue to DENY unrelated
  work but stop charging it as hardening debt. This addresses ONLY the run-end-gating
  symptom, not the over-fire itself (unrelated work is still blocked mid-session). Smallest
  change; keeps the most enforcement. Worst fit for the SPEC's stated Expected behavior
  ("an unrelated, non-pipeline dispatch is not policed by a pipeline run's guard").

**Recommendation:** A (owning-session scoping at the gate) — it directly realizes the
SPEC's Expected outcome, reuses the existing owning-session slot and the guard's own
`read_run_marker(session_id=…)` semantics for a symmetric two-read design, and is the
mechanism the SPEC's findings explicitly lead with. The unbound-marker pre-bind window is
a narrow, separately-addressable residual (and decision 2 governs what happens to a deny
inside it).

### 2. Disposition of an unrelated (non-pipeline) deny

**Problem:** Once a dispatch is classified non-pipeline, what does the guard DO with it?
This is partly determined by decision 1 (option A scopes the GATE out, so most unrelated
dispatches never reach a deny at all), but a residual remains for any dispatch that does
reach the guard yet is provably unrelated — e.g. the unbound-marker pre-bind window under
option A, or every unrelated dispatch under option C. The codebase already has BOTH
patterns as precedent: `_deny_no_ledger` (transcription-slip path — deny but no debt) and
the excluded ledger event kinds (`auto_readmit`, `dispatch_by_reference` — recorded but
skipped by `pending_hardening()`).

**Options:**
- **A. Allow-through (gate scoped out) (Recommended)** — When decision 1 = option A, an
  unrelated dispatch from a non-owning session never reaches the guard's deny logic at all
  (the gate fast-path-allows it). No deny, no ledger entry, no debt — the cleanest match to
  the SPEC's Expected ("not policed by a pipeline run's guard"). For the residual unbound-
  marker window, pair with a `_deny_no_ledger`-style path (below) so even a pre-bind deny
  carries no debt. Lowest operator friction; stops policing unrelated work entirely.
- **B. Deny-but-no-ledger (mirror `_deny_no_ledger`)** — Keep denying the unrelated
  dispatch (so unrelated work is still blocked mid-session) but route it through the
  existing no-debt deny path so it never gates `--run-end`. Fixes the run-end-gating
  symptom while preserving a hard stop on non-pipeline work during a live run. Matches the
  in-codebase transcription-slip precedent exactly.
- **C. Ledger-with-skip discriminator** — Record the deny in `lazy-deny-ledger.jsonl` with
  a new discriminator field (e.g. `kind: unrelated-dispatch`) that `pending_hardening()`
  excludes from the debt count — mirroring how `process-friction` / `auto_readmit` entries
  are tracked-but-classified. Preserves a full audit trail of every unrelated deny without
  gating run-end. Requires extending the entry shape + the `pending_hardening` filter.

**Recommendation:** A (allow-through via the gate) for the common case, PAIRED with B
(`_deny_no_ledger`) for the narrow unbound-marker residual — together they realize the
SPEC's Expected behavior (unrelated work not policed) while keeping a no-debt deny as the
safety net for the pre-bind window. Both reuse existing in-codebase patterns.

### 3. Under-fire single-slot ownership fix — in-scope or split to follow-up

**Problem:** The SPEC documents a SECOND, opposite-direction defect (Symptom 2/3,
"under-fire"): marker ownership is a single mutable `session_id` slot, so an overwrite or
wrong-session bind makes the TRUE owner's dispatches read "owned by someone else → None →
fast-path allow" — silently disarming enforcement mid-run. The over-fire (decisions 1-2)
and under-fire share the marker but have largely independent fixes and OPPOSITE failure
directions. The SPEC's third Open Question asks whether closing the residual single-slot
race is in-scope for THIS bug or split to a dedicated follow-up. (Per D7 completeness
this would default to most-complete = include it; it is surfaced because the under-fire
fix is itself an architectural product-class change to the ownership model — not mere
effort — and it interacts with decision 1: option A re-enables path-B mismatch at the
gate, which is the very mechanism the under-fire defect abuses, so the two fixes must be
designed coherently rather than independently sequenced.)

**Options:**
- **A. Split the under-fire to a dedicated follow-up bug (Recommended)** — Scope THIS
  bug to the over-fire only (decisions 1-2: session-blind gate + no pipeline
  discriminator). Spin off a separate `docs/bugs/` item for the single-slot ownership
  race, cross-referenced in both directions. Rationale: the two have opposite failure
  directions and independent fixes; the under-fire is already partially mitigated
  (Phase 9 WU-9.2 allow-time bind) and intermittent; bundling a marker-ownership redesign
  (e.g. multi-owner or fence-token ownership) into an over-fire fix risks a large,
  hard-to-validate change. Keeps each fix independently testable. The /plan-bug cycle that
  resolves this would author the spin-off and the reverse-references.
- **B. Include the under-fire fix in this bug's PHASES.md** — One bug, all phases:
  redesign the ownership slot (or harden the bind/overwrite race) alongside the over-fire
  fix. Most complete in a single pass; honors D7 most-complete by default. Cost/risk: a
  larger, multi-axis change with a harder validation story (the intermittent race is hard
  to fixture deterministically), and the ownership redesign may interact with decision 1's
  chosen mechanism in ways that warrant their own investigation.

**Recommendation:** A (split to a follow-up) — the over-fire is deterministic, has a
clean fix, and is the documented run-blocking symptom; the under-fire is intermittent,
partially mitigated, and a marker-ownership redesign deserves its own scoped investigation
+ deterministic fixture rather than riding a different-direction fix. If the operator
prefers a single complete pass, choose B and the plan will phase the ownership change
behind the over-fire fix.

## Resolution

*Recorded on 2026-06-19 18:40:00 UTC.*

### 1. Discriminator mechanism for pipeline-vs-unrelated dispatches

**Choice:** A. Owning-session scoping at the gate
**Notes:** Pass `--session-id` from `lazy-dispatch-guard.sh` into `--marker-present`; treat the marker as present ONLY when the caller's session is the marker's bound owner (re-enable staleness-path-B at the gate). Preserve sacred invariants: fail-OPEN, never destroy the owning run's marker from a non-owner read, never weaken the depth-1 hardening cap.

### 2. Disposition of an unrelated (non-pipeline) deny

**Choice:** A. Allow-through (gate scoped out)
**Notes:** Under D1=A, a non-owning-session dispatch never reaches deny logic (gate fast-path allows it). For the narrow unbound-marker pre-bind window, pair with a `_deny_no_ledger`-style no-debt deny path so even a pre-bind deny carries no hardening debt.

### 3. Under-fire single-slot ownership fix — in-scope or split to follow-up

**Choice:** A. Split the under-fire to a dedicated follow-up bug
**Notes:** Scope THIS bug to the over-fire only (decisions 1-2). Spin off a separate `docs/bugs/` item for the single-slot marker-ownership race, cross-referenced in both directions (origin names the spin-off in PHASES.md Implementation Notes; spin-off names this origin). The spin-off gets its own scoped investigation + deterministic fixture.
