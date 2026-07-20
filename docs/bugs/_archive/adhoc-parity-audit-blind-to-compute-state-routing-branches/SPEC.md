# Parity audit blind to compute_state routing-branch asymmetry — Investigation Spec

> `lazy_parity_audit.py` audits SKILL.md-pair prose and a fixed list of named CLI-surface
> literals, but has NO check over `compute_state` ROUTING-BRANCH symmetry between `lazy-state.py`
> and `bug-state.py` — so an unmirrored routing fix passes the audit clean and surfaces as a live
> run stall weeks later.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-19
**Fixed:** 2026-07-19
**Fix commit:** 2cd4a3e9
**Placement:** docs/bugs/adhoc-parity-audit-blind-to-compute-state-routing-branches
**Related:** `docs/bugs/_archive/bug-state-verification-only-remainder-loops-write-plan` (Round 93 instance), the coupled-pairs contract in root `CLAUDE.md`, `user/scripts/CLAUDE.md` → "Coupling Rule"

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

<!-- No live operator round this cycle (unattended --batch park-mode run). Symptoms are marked
     [REPORTED] from the enqueuing brief's cited field recurrences (Rounds 92 + 93 of a real run)
     and [PROVEN] where confirmed directly against the code in this investigation. -->

1. **[PROVEN]** `lazy_parity_audit.py`'s state-script check (`audit_state_script_parity`,
   lazy_parity_audit.py:384–499) asserts ONLY the *presence of a fixed list of named
   literals* (`--reorder-queue`, `--sync-deps`, `set_active_repo_root(args.repo_root)`,
   `lazy_core.notify_halt(`, `state["cycle_prompt_ref"]`, …). It never inspects the internal
   routing structure of either `compute_state` — confirmed by reading the whole function: every
   check is a `re.compile(<literal>)` membership test, none parse branch predicates. — verified by code read
2. **[REPORTED]** Round 92: a `compute_state` research-pending exclusion shipped flag-gated
   feature-only, with no bug-state.py consideration, and passed the audit clean. — enqueuing brief (field run)
3. **[REPORTED]** Round 93: the Step-7 verification-only bypass in `bug-state.py` kept an
   over-narrow conjunct (`_has_any_complete_plan`) that the feature side had DROPPED on
   2026-06-15, *despite a bug-state.py comment claiming to mirror it* — producing an infinite
   write-plan loop on an out-of-pipeline fix; the audit never flagged the divergence. — enqueuing brief (field run)
4. **[PROVEN]** The Round 93 fix is now documented in-code at bug-state.py:1755–1758 ("This
   parity-completes the feature-side fix that bug-state.py's prior comment CLAIMED to mirror but
   did not"), confirming a mirror-claiming comment is not a mechanically enforced contract. — verified by code read

## Reproduction Steps

1. In `lazy-state.py::compute_state`, add or narrow a routing conjunct on a shared branch (e.g.
   change the workstation verification-only bypass predicate) WITHOUT mirroring it into
   `bug-state.py::compute_state`.
2. Run the full parity gate: `python3 user/scripts/lazy_parity_audit.py --repo-root .`
3. Observe: exit 0, no findings — the asymmetry is invisible to the audit.

**Expected:** an unmirrored (non-divergence-tabulated) `compute_state` routing branch fails the
parity audit, in the same commit that introduces the asymmetry.
**Actual:** the audit passes; the asymmetry surfaces only when a live run routes into the
diverged branch and stalls (write-plan loop / silent skip), often weeks later.
**Consistency:** always (deterministic — the audit has no routing-branch census at all).

## Evidence Collected

### Source Code

- **`user/scripts/lazy_parity_audit.py`** — three audit layers, none covering routing branches:
  - `audit_pair` (C1–C6, lines 96–290): SKILL.md-prose pairs, driven by
    `lazy-parity-manifest.json`. Operates on markdown headings + evidence regexes — not the
    Python state machines.
  - `audit_state_script_parity` (lines 384–499): the only layer that reads the two `.py` scripts.
    A hardcoded sequence of `_<NAME>_RE.search(text) is None` literal-presence checks
    (`_ACTIVE_REPO_BINDING_RE` … `_EXECUTE_PLAN_LIVENESS_RE`). Each guards ONE named CLI-surface
    or call-site token. **No structural inspection of `compute_state` branch predicates,
    exclude-set members, or step-routing conjuncts.**
  - `audit_merged_view_dispatch_parity` (lines 548–583): SKILL.md prose again (the unified-driver
    pair), not the routing branches.
  - `audit_all_pairs` (lines 590–619) composes all three → the whole-repo verdict.
- **`bug-state.py::compute_state`** verification-only bypass (lines 1729–1762) vs.
  **`lazy-state.py`** (`_feature_past_implementation` mirror, lines 1747–1752): the exact branch
  whose 2026-06-15 asymmetry (Round 93) went undetected. The divergence lived in a boolean
  conjunct (`not cloud and not plans and verification_only` vs. the prior combined form requiring
  `_has_any_complete_plan`) — precisely the shape a literal-presence audit cannot see.

### Git History

Recent commits are unrelated (`adhoc-unify-merged-head-coordinator-exemptions`). The two cited
recurrences predate this dir; the Round 93 fix is archived under
`docs/bugs/_archive/bug-state-verification-only-remainder-loops-write-plan`.

### Related Documentation

- Root `CLAUDE.md` → Coupled Skill Pairs + `user/scripts/CLAUDE.md` → "Coupling Rule (HARD
  REQUIREMENT)": *"A change to one state script usually must be mirrored to the other; run the
  parity audit."* The audit is the mechanical enforcement of this rule — but it enforces it only
  for named CLI/call-site surfaces, not for `compute_state` routing logic, which is the highest-churn
  coupled surface.
- The two scripts carry MANY documented **justified divergences** (7 markers in `lazy-state.py`, 4
  in `bug-state.py`: cloud-saturated flip, feature-only skip-ahead, per-feature budget guard,
  archive-aware bug resolution, no stub step, …). Any routing-branch symmetry check MUST tolerate
  these via a tabulated-divergence allowlist, or it drowns in false positives — this is the core
  design constraint the fix inherits (and the brief's proposed "tabulated deliberate divergences").

## Theories

### Theory 1: The audit's contract scope stops at named literals; routing logic is uncovered
- **Hypothesis:** `audit_state_script_parity` was grown incrementally, one `_<NAME>_RE` per
  coupled CLI/call-site surface as features landed. `compute_state`'s internal routing branches
  were never in scope, so an unmirrored branch fix is structurally invisible.
- **Supporting evidence:** every check in lines 411–498 is a single-literal `search`; the module
  docstring (C1–C6) describes only heading/evidence/mechanic coverage; no function reads branch
  structure. The two field recurrences (Rounds 92, 93) both slipped through.
- **Contradicting evidence:** none found.
- **Status:** **Confirmed.**

## Proven Findings

- **Root cause (`traced`).** The false "parity holds" verdict is produced by
  `audit_state_script_parity` (lazy_parity_audit.py:384–499) returning `[]` for any asymmetry
  that lives inside a `compute_state` routing branch — because the function's entire check-set is
  named-literal presence tests, with zero routing-branch census. The fix site (adding a per-branch
  structural symmetry check with a tabulated-divergence allowlist) lies directly ON this serving
  path: `audit_all_pairs` (line 611) calls `audit_state_script_parity`, whose empty return IS the
  clean exit; a census added here (or in a sibling called from `audit_all_pairs`) is exactly what
  converts an unmirrored branch into a finding.
- **Serving-path trace** (surface → source):
  ```
  parity gate exits 0 despite a compute_state routing asymmetry
    → audit_all_pairs()                       lazy_parity_audit.py:590,611
    → audit_state_script_parity()             lazy_parity_audit.py:384
    → fixed literal-presence checks only       lazy_parity_audit.py:411-498   ← the value the fix changes
      (no branch-predicate / exclude-set / step-conjunct census over compute_state)
  ```
- **Label:** `traced` — the claim is a static-analysis property (the audit is a pure static
  checker; no runtime coupling), confirmed by reading the serving code, and the fix site is on the
  traced path.
- **Design constraint carried into `/plan-bug`:** the census must be divergence-aware — a
  tabulated allowlist of the 11+ documented justified `compute_state` divergences (or it produces
  false positives on every legitimate feature-only branch). Fix-shape choice (AST-based branch
  extraction vs. a declared routing-predicate manifest vs. structural-token census) is a planning
  decision, not locked here.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Parity audit engine | `user/scripts/lazy_parity_audit.py` (`audit_state_script_parity` / `audit_all_pairs`) | Add a routing-branch symmetry check + a tabulated-divergence allowlist |
| Coupled state machines (read-only inputs) | `user/scripts/lazy-state.py`, `user/scripts/bug-state.py` (`compute_state`) | The audited surface — the census reads their routing branches; no behavior change |
| Audit tests | `user/scripts/test_lazy_parity.py` (or the in-file harness) | New fixtures: an unmirrored branch fails; a tabulated divergence passes |
| Docs | `user/scripts/CLAUDE.md` (Coupling Rule), root `CLAUDE.md` | Document the new coverage + the divergence allowlist location |

## Open Questions

- **Census granularity (fix-shape, → `/plan-bug`):** AST-based branch/predicate extraction vs. a
  declared routing-predicate manifest vs. a structural-token census. All achieve the same product
  behavior (unmirrored branch → finding); they differ in false-negative surface and maintenance
  cost — a planning decision, deliberately not locked in this investigation.
- **Round 92 branch — mirror-owed vs. correct-divergence?** The research-pending exclusion may be
  a legitimate feature-only divergence (bugs have no research step). The fix's allowlist must
  classify it explicitly either way; confirming its correct classification is planning-scope.
