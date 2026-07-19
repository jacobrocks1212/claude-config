# plan-bug Step 0.4 lacks a guard for Fixed-annotated / already-implemented SPECs — Investigation Spec

> `/plan-bug`'s Step 0.4 status gate (and `bug-state.py`'s Concluded→plan-bug routing) key ONLY on the literal `**Status:**` line, so a `Concluded` SPEC whose fix already landed out-of-pipeline burns a full plan-bug dispatch re-planning work that is already done.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-18
**Placement:** docs/bugs/adhoc-plan-bug-no-guard-for-fixed-annotated-specs
**Related:** Round 90 harden-side reconciliation contract (commit 38144ada — `harden-rounds-skip-docs-bugs-reconciliation-contract`); `docs/bugs/CLAUDE.md` → "Fixing a bug OUT-OF-PIPELINE"; `bug-state.py --fsck` (`fixed-bugs-unarchived-fsck`); this run's 6-bug reconciliation sweep

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

<!-- No human is attending this batch run (park-mode). Symptoms are corroborated from the
     ADHOC_BRIEF (the operator-authored capture) + on-disk code evidence, and labeled
     [REPORTED] where they rest on the brief's field observation rather than a live re-run. -->

1. **[REPORTED]** Five pipeline cycles across two runs burned full `/plan-bug` dispatches (~100–200k tokens each) discovering that a `Concluded` SPEC's fix scope was already fully implemented out-of-pipeline. — source: `ADHOC_BRIEF.md` (operator field observation).
2. **[VERIFIED]** `/plan-bug`'s Step 0.4 status gate treats `Concluded` as plannable purely on the literal `**Status:**` line and does NOT inspect the `**Fixed:**` evidence-header annotation or any on-disk fix-scope signal. — confirmed by reading `user/skills/plan-bug/SKILL.md:63`.
3. **[VERIFIED]** `bug-state.py::compute_state` Step 4 routes a `Concluded` SPEC with no `PHASES.md` to `plan-bug` on the sole basis of `spec_status(spec_dir) == "Concluded"`, with no fix-scope / `**Fixed:**`-annotation pre-check. — confirmed by reading `user/scripts/bug-state.py:1702-1714`.
4. **[VERIFIED]** `spec_status()` reads ONLY the first `**Status:**` line and never consults `**Fixed:**`. — confirmed by reading `user/scripts/lazy_core/docmodel.py:418-421`.

## Reproduction Steps

1. Take a bug dir `docs/bugs/<slug>/` whose SPEC is `**Status:** Concluded` and whose fix was implemented OUT-OF-PIPELINE (e.g. a `/harden-harness` round or a manual in-session fix) but only PARTIALLY reconciled — the fix landed and a `**Fixed:** <date> - implemented out-of-pipeline` evidence line was added, but `**Status:**` was left at `Concluded` and `--archive-fixed` never ran (so no `FIXED.md` receipt, dir not archived). No `PHASES.md` exists.
2. Run the bug pipeline over that repo: `python3 user/scripts/bug-state.py --repo-root . --probe` (or a `/lazy-bug-batch` cycle).
3. Observe: Step 4 routes to `plan-bug` (`sub_skill: plan-bug`), because `spec_status` returns `Concluded` and `PHASES.md` is absent.
4. `/plan-bug` Step 0.4 passes the status gate (`Concluded` is allowed) and proceeds to Step 1 (`/spec-phases --batch`) + Step 2 (`/write-plan`) — a full ~100–200k-token planning dispatch.

**Expected:** the pipeline recognizes the already-implemented fix cheaply (before any planning dispatch) and routes to the `docs/bugs/CLAUDE.md` reconciliation contract (write the `FIXED.md` receipt + `--archive-fixed`) instead of re-planning.
**Actual:** a full `plan-bug` dispatch is burned authoring `PHASES.md` + a plan for a fix that is already on disk; the item then re-enters execution/validation for no-op work.
**Consistency:** deterministic given the partially-reconciled `Concluded` + no-`PHASES.md` + already-implemented-fix state (observed 5× across two runs).

## Evidence Collected

### Source Code

- **`user/skills/plan-bug/SKILL.md:59-73` (Step 0.4 — the primary fix site).** The status gate: "the SPEC's `**Status:**` line is `Investigating`, `Open`, or `Concluded`… `Concluded` is the canonical status when `bug-state.py` routes here." It branches ONLY on the literal status string. There is no `**Fixed:**`-annotation check and no cheap on-disk fix-scope pre-check. The `If it is already In-progress, Fixed, or Won't-fix` short-circuit only catches a status that was actually flipped — a partially-reconciled out-of-pipeline fix leaves `Concluded`, so it slips through.
- **`user/scripts/bug-state.py:1701-1714` (Step 4 — the earlier fix site).** `if not phases_file.exists(): _status = spec_status(spec_dir); if _status == "Concluded": return _bug_state(..., sub_skill=SKILL_PLAN_BUG, ...)`. The routing decision consults only `spec_status`. A probe-time diagnostic / route-diversion here would prevent the item from ever reaching `plan-bug`.
- **`user/scripts/lazy_core/docmodel.py:403-424` (`spec_status`).** Matches the first `^\*\*Status:\*\*\s*(.+?)$` line and returns it. The `**Fixed:**` evidence line is invisible to it.
- **`user/skills/_components/mark-fixed-archive.md:71`.** Documents the `**Fixed:** <date>` + `**Fix commit:** <short sha>` evidence-header lines — the annotation whose presence (alongside a non-`Fixed` status) is the load-bearing signal of an already-implemented-but-unreconciled fix.

### Runtime Evidence

None captured (park-mode batch; no live re-run performed). Symptom 1 rests on the ADHOC_BRIEF field observation of 5 burned cycles across two runs.

### Git History

- **38144ada** (2026-07-18) — wired the `docs/bugs/` reconciliation contract into `/harden-harness` + the orchestrator honor-step and added `bug-state.py --fsck`. That change made the RECONCILIATION path exist and be enforceable; it did NOT add a PRE-GATE in the routing/planning path, so a partially-reconciled SPEC still routes to `plan-bug` and pays the dispatch before any reconciliation is considered. This bug closes that remaining gap.

### Related Documentation

- **`docs/bugs/CLAUDE.md` → "Fixing a bug OUT-OF-PIPELINE".** Defines the exact partial-reconciliation state this bug exploits: `**Status:** Fixed` + receipt + `--archive-fixed` is the full contract; a bare status flip (or, symmetrically, a fix that landed with a `**Fixed:**` annotation but no receipt/archive and status still `Concluded`) is the debt state. Also documents `--fsck` (`unarchived-fixed` / `fixed-without-receipt`) — the invariant checker for the same class, but it runs at `--run-end`, AFTER a wasted plan-bug cycle could already have fired.
- **`docs/bugs/CLAUDE.md` → archive-awareness** and the `queue-dependency-dag` `dep_completion_status` (archive-aware bug resolution) show the codebase already distinguishes "genuinely resolved" from "still open" using receipts — the pre-gate should reuse that vocabulary, not invent a new one.

## Theories

### Theory 1: Status-line-only gate is blind to the already-implemented signal
- **Hypothesis:** both the routing decision (`bug-state.py` Step 4) and the planning gate (`plan-bug` Step 0.4) decide "is this plannable?" purely from the `**Status:**` string, so a `Concluded` SPEC whose fix already landed out-of-pipeline (marked by a `**Fixed:**` annotation and/or fully-satisfied fix-scope anchors, but with status un-flipped) is treated as fresh fix-planning work.
- **Supporting evidence:** `spec_status` reads only the Status line (docmodel.py:418-421); Step 0.4 branches only on that string (SKILL.md:63); Step 4 routes only on it (bug-state.py:1704); the `**Fixed:**` annotation is a real, documented evidence line (mark-fixed-archive.md:71) that neither path reads.
- **Contradicting evidence:** none found. `--fsck` catches the same class but only post-hoc at run-end, confirming (not contradicting) that the routing/planning path itself has no such guard.
- **Status:** Confirmed — cause is **`traced`** (serving path below).

## Proven Findings

**Root cause (traced).** The pipeline decides a `Concluded` bug is fix-planning work from the literal `**Status:**` line alone, with no cheap on-disk check for an already-implemented fix. Serving path, surface → source:

```
surface: /plan-bug burns a full spec-phases + write-plan dispatch on an already-fixed bug
  → bug-state.py compute_state Step 4      user/scripts/bug-state.py:1702  (not phases_file.exists())
  → routes Concluded → plan-bug            user/scripts/bug-state.py:1704  (if _status == "Concluded")
  → status read consults ONLY **Status:**  user/scripts/lazy_core/docmodel.py:418-421  (spec_status)
  → /plan-bug Step 0.4 status gate passes  user/skills/plan-bug/SKILL.md:63  (Concluded is allowed)
  → proceeds to Step 1/2 full dispatch     user/skills/plan-bug/SKILL.md:81-108
data source Y (never read on this path): the SPEC's `**Fixed:**` evidence annotation + on-disk
  fix-scope / receipt signals — the value that would divert to reconciliation.
```

**Fix sites are ON the traced path (both consume the status decision this trace follows):**
- **Primary — `/plan-bug` Step 0.4** (`user/skills/plan-bug/SKILL.md:59-73`): add a mechanical pre-gate. When the SPEC carries a `**Fixed:**` annotation (status not yet `Fixed`) OR the fix-scope grep-anchors all resolve present, REFUSE the planning round with a distinct `fixed-unreconciled` outcome that instructs the orchestrator to run the `docs/bugs/CLAUDE.md` reconciliation contract (write `FIXED.md` + `--archive-fixed`) instead of planning.
- **Earlier / more complete — `bug-state.py` Step 4** (`user/scripts/bug-state.py:1701-1714`): a probe-time diagnostic (and/or route diversion) for the same `Concluded` + `**Fixed:**`-annotation signature, so the item never routes to `plan-bug` at all — the cheapest possible catch. This is a completeness (belt-and-suspenders) leg, not a distinct product behavior; the planning stays deterministic-script-owned per the harness mission.

The fix must reuse the existing receipt/archive vocabulary (`--fsck` semantics, `dep_completion_status` archive-awareness) rather than inventing a new "is-fixed" heuristic. The exact split (Step 0.4 only vs. Step 0.4 + bug-state.py pre-gate) and the anchor-resolution mechanics are a **planning-stage** decision for `/plan-bug`, not a product fork — both options end in "already-implemented bug is routed to reconciliation, no wasted dispatch."

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| plan-bug planning gate (primary) | `user/skills/plan-bug/SKILL.md` (Step 0.4, ~L59-73) | Add a `**Fixed:**`-annotation / fix-scope pre-gate that refuses with a distinct `fixed-unreconciled` outcome routing to the reconciliation contract. |
| bug-state routing (earlier catch) | `user/scripts/bug-state.py` (Step 4, ~L1701-1714) | Optional probe-time diagnostic / route-diversion so a Fixed-annotated Concluded SPEC never routes to plan-bug. Coupled-pair / parity implications to check vs. `lazy-state.py`. |
| shared status/receipt vocabulary | `user/scripts/lazy_core/docmodel.py` (`spec_status`, `**Fixed:**` reader) | Likely needs a small helper to read the `**Fixed:**` annotation and/or a fix-scope/receipt presence check, reused by both fix sites. |
| reconciliation contract (destination) | `docs/bugs/CLAUDE.md`; `bug-state.py --fsck`; `--archive-fixed` | Already exist — the fix ROUTES to them; it does not reimplement them. |

## Open Questions

- Exact detection predicate for "already implemented": is a `**Fixed:**` annotation sufficient on its own, or must the fix-scope grep-anchors also all resolve present (belt-and-suspenders vs. annotation-trust)? — a planning/implementation detail; both converge on the same product outcome, resolved by the `/plan-bug` → `/write-plan` stage.
- Whether the `bug-state.py` pre-gate should DIVERT the route (emit a reconciliation-directed action) or merely DIAGNOSE (surface a probe key and let `/plan-bug`'s Step 0.4 refuse) — the ADHOC_BRIEF suggests "consider" the probe-time diagnostic; the completeness-maximal choice is to do both, sequenced in planning.
