---
kind: needs-input
feature_id: anti-overfit-design-gate
written_by: spec
decisions:
  - D1 — scope trigger — which changed paths arm the gate
  - D3 — where the gate runs — which seam(s) host it
  - D4 — override protocol — the shape of operator sign-off
  - D7 — blocking semantics per check class for autonomous runs
date: 2026-07-04
next_skill: spec
class: product
divergence: structural
audit_divergence: structural
---

# /spec --batch (Phase 3) — Needs Input

Research is integrated (`RESEARCH.md` + `RESEARCH_SUMMARY.md` on disk). Four **product-behavior**
decisions gate finalizing SPEC.md — they change what you (the operator) experience: which changes
arm the gate, where it runs, how you sign off on a gate-weakening, and what halts an autonomous
run. Each has a strong research-backed recommendation, but the Phase-3 always-halt rule reserves
final authority over product behavior to you. The three mechanical-internal decisions (D2 detector
split, D5 verdict residency, D6 self-audit KPI/record) are auto-accepted per their SPEC resolutions.

## Decision Context

### 1. D1 — scope trigger — which changed paths arm the gate

**Problem:** The gate only reviews a change when the change touches a "control surface" — harness
code that enforces the pipeline's integrity (hooks, the state scripts, `lazy_core`, gate-bearing
skill components, hook registrations, and the gate's own files). Too narrow and a gate-weakening
edit ships ungated; too broad and ordinary feature work pays a review tax the stub explicitly
exempts it from. How is the scoped set of paths defined? This is a product call because the set
determines which of your changes incur the gate's friction, and you own its initial contents.

**Options:**
- **A — committed glob manifest, self-included (Recommended)** — a diffable
  `docs/gate/control-surfaces.json` lists the scoped globs (initial set: `user/hooks/**`,
  `lazy-state.py`, `bug-state.py`, `lazy_core.py`, `lazy_guard.py`, `lazy_inject.py`,
  `lazy-parity-manifest.json`, `build-queue*.ps1`, `user/skills/lazy*/**`,
  `user/skills/harden-harness/**`, the gate-bearing `_components/*` files, hook registrations in
  `user/settings.json` + `repos/*/.claude/settings.json`, and the gate's own three files). A diff is
  in scope iff it touches ≥1 matching path. The manifest is itself on the manifest, so widening or
  narrowing it is a control-surface change the gate reviews. Cost: a manifest can go stale (mitigated
  by the gate's KPI row tracking misses found in retro). Fully reversible — edit the JSON.
- **B — heuristic path classification in code** — no manifest to maintain, but the trigger becomes
  invisible, untestable prose-in-code, and editing the heuristic would not self-trigger the gate.
  Higher long-term risk, harder to audit.

**Recommendation:** A — auditable, diffable, self-referential by construction; the initial glob set
above is the starting point and you own additions/removals thereafter (each a gated change).

### 2. D3 — where the gate runs — which seam(s) host it

**Problem:** The checker can be wired at several seams — the planning stage, a pre-commit/PreToolUse
hook, the cycle review, or the completion gate. Where it runs decides when you feel it and whether
its blocking authority respects the repo's fail-OPEN-hook / fail-closed-completion-gate convention.
This is a product call because it changes where and how the gate surfaces to you during a run.

**Options:**
- **A — two pipeline seams + harden-harness delegation, one shared checker (Recommended)** — (1) a
  *design seam* component injected at planning time for claude-config items runs the checker, works
  the adversarial questions, and drafts `GATE_VERDICT.md` before implementation (the
  `phases-runtime-validation.md` precedent); (2) a *ship seam* where `__mark_complete__` /
  `__mark_fixed__` refuse a scoped item whose verdict is missing, failing, or carries an unsigned
  gate-weakening hit (fail-closed where fail-closed already lives); (3) `/harden-harness` Step 3
  delegates its smell detection to the same checker, keeping its own never-block-the-run + spin-off
  protocol unchanged. Blocking authority lives ONLY at the completion gate.
- **B — blocking pre-commit / PreToolUse hook** — rejected as the blocking layer: hooks here are
  fail-OPEN by convention, so a blocking design gate at the hook layer is either a convention
  violation or silently skippable, and adversarial prose cannot run in a deny hook. (A WARN-only
  advisory hook is a possible later addition, out of v1.)
- **C — harden-harness step only (status quo, generalized in place)** — misses the primary shipping
  path: most control-surface changes arrive through pipeline items, not hardening rounds.

**Recommendation:** A — one checker, three consumers; blocking authority only at the completion gate,
which is already the repo's fail-closed layer.

### 3. D4 — override protocol — the shape of operator sign-off

**Problem:** A gate-weakening hit (loosening a threshold, broadening an exemption, deleting a passing
gate test) — or a contested overfit/tautology fail — must not ride an ordinary cycle; it needs your
explicit sign-off. What form does that sign-off take? This is a product call because it defines the
workflow you use to approve a weakening and the durability of that approval record.

**Options:**
- **A — NEEDS_INPUT.md decision round; approval transcribed to a verdict `override:` field; per-change
  only (Recommended)** — the cycle writes `NEEDS_INPUT.md` (`written_by: harness-change-gate`, rich
  body quoting the exact flagged diff hunks) into the item dir; the pipeline halts on the existing
  Step-3 sentinel machinery; your answer is transcribed into `GATE_VERDICT.md` as
  `override: operator-approved <date> — <rationale>`. Reuses the shipped halt/resume mechanism and
  the exact shape `/harden-harness` already uses for contract forks; the sign-off is durable and
  auditable. By design a halt — gate-weakening should not be frictionless. An approved override is
  per-change, never standing (it does not exempt the file or pattern from future review).
- **B — a standalone hand-written `GATE_OVERRIDE.md` sentinel** — hand-written sentinels are the exact
  anti-pattern the write hooks (`block-noncanonical-blocker-write.sh` class) exist to reject; a new
  hand-authored sentinel family invites that confusion.
- **C — an env-var bypass (`HARNESS_GATE_BYPASS=1`)** — the detector would have to flag its own bypass
  mechanism as gate-weakening; unauditable after the fact.

**Recommendation:** A — reuses the durable, structured decision-round record (who approved what) and
keeps the override per-change, never standing.

### 4. D7 — blocking semantics per check class for autonomous runs

**Problem:** When a check fails mid-autonomous-run, what happens — halt, justify-and-proceed, or
warn-and-log? This is a product call because it decides when an autonomous run stops to ask you
versus proceeding with a recorded justification, trading run-continuity against gate strength.

**Options:**
- **A — tiered (Recommended)** — *gate-weakening* → always the D4 sign-off halt (the one class where
  a wrong pass silently disarms a defense). *Overfit / tautology / complexity* → justify-or-halt: the
  cycle may proceed by recording a concrete adversarial justification in `GATE_VERDICT.md` (naming
  the structural property the rule keys on, or the independent observable); a flag with no recorded
  justification fails the ship seam and surfaces as NEEDS_INPUT. In `/harden-harness` context the
  existing protocol is preserved verbatim — the mechanical fix always lands first, the run is never
  blocked, and a tripped smell spins off the generalization; the gate adds recording, not blocking.
- **B — everything halts** — turns every flagged literal into an operator interrupt; the
  harden-harness never-block-the-run principle exists precisely because that is unworkable.
- **C — everything warns** — a gate that cannot refuse is a dashboard; gate-weakening specifically
  must not ride an ordinary cycle.

**Recommendation:** A — authority proportional to irreversibility: weakening an existing gate is the
one class where a wrong pass is silently catastrophic; the softer checks self-announce on recurrence.

## Resolution

resolved_by: auto-provisional
decision_commit: 3c15b7ef78200b1f2dee5438ed7699d917df4d14

**Provisionally accepted** under the operator's overnight park-provisional blanket directive
(2026-07-12). For each product decision the stated `**Recommendation:**` (option A in every case)
is adopted and propagated into `SPEC.md`; the feature is implemented against these choices but its
`SPEC.md` **Status stays Draft** and NO `COMPLETED.md` is written — completion is mechanically
blocked while this unratified `NEEDS_INPUT_PROVISIONAL.md` exists, per the park-provisional
contract. The operator ratifies or redirects each choice before the feature can ever complete.

> **DIVERGENCE GRADED `structural` — ratification is LOUD (honest grade, not the eligibility
> path).** These four are the PRODUCT decisions `/spec` Phase 3 held for the operator precisely
> because each forks product behavior: D1 forks the scope-trigger data model (committed manifest
> vs in-code heuristic), D3 forks where blocking authority lives (completion gate vs hook vs
> harden-harness-only), D4 forks the operator's sign-off workflow, and D7 forks autonomous-run
> blocking behavior. A later redirect on any of them is significant rework, so the honest
> file-level grade is `structural` (most-severe rule). This does NOT satisfy the normal
> `provisional_eligibility` two-key predicate (which fail-closes on `structural`); the sentinel was
> hand-authored under the operator's explicit blanket directive, and the structural grade is
> recorded here so the ratification step scrutinizes these choices rather than rubber-stamping them.

Per-decision choices (recommended option A, verbatim label from each Decision Context block):

- **D1 — scope trigger — which changed paths arm the gate:** **Choice:** A — committed glob
  manifest, self-included (`docs/gate/control-surfaces.json` with the listed initial glob set; a
  diff is in scope iff it touches ≥1 matching path; the manifest is itself on the manifest).
- **D3 — where the gate runs — which seam(s) host it:** **Choice:** A — two pipeline seams +
  harden-harness delegation, one shared checker (planning-time *design seam* drafts
  `GATE_VERDICT.md`; completion-gate *ship seam* refuses a scoped item with a missing/failing/
  unsigned verdict; `/harden-harness` Step 3 delegates smell detection to the same checker;
  blocking authority lives ONLY at the completion gate).
- **D4 — override protocol — the shape of operator sign-off:** **Choice:** A — NEEDS_INPUT.md
  decision round; approval transcribed to a verdict `override:` field; per-change only (reuses the
  shipped halt/resume mechanism; an approved override never exempts the file/pattern from future
  review).
- **D7 — blocking semantics per check class for autonomous runs:** **Choice:** A — tiered
  (gate-weakening → always the D4 sign-off halt; overfit/tautology/complexity → justify-or-halt
  via a recorded adversarial justification; `/harden-harness` never blocked — the gate adds
  recording, not blocking, there).
