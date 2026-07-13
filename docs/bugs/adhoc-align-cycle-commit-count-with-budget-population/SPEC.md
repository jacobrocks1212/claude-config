---
kind: investigation-spec
bug_id: adhoc-align-cycle-commit-count-with-budget-population
---

# Align the unexpected-commits count numerator with the budget denominator's commit population — Investigation Spec

> The process-friction `unexpected-commits` detector compares an authored-commit COUNT (`git rev-list --count --no-merges begin..HEAD`, uniform across every dispatch identity) against a per-cycle commit BUDGET that is modeled DIFFERENTLY per identity — a work-scaled, slack-and-bookend-cushioned formula for `execute-plan` alone, versus a bare flat ceiling with ZERO cushion for every other multi-commit dispatch identity. Round 42 and Round 46 each patched one concrete instance of the mismatch (both on `execute-plan`) without generalizing the fix, so the same commit categories that tripped `execute-plan` twice (an in-cycle revert/self-correction, an off-plan/unrelated commit landing on the branch, an unmodeled status-flip) remain fully exposed for the other 8 multi-commit dispatch identities — most acutely `mcp-test`, whose ceiling equals its exact documented worst case with no headroom at all.

**Status:** Concluded
**Severity:** Medium
**Discovered:** 2026-07-12
**Placement:** docs/bugs/adhoc-align-cycle-commit-count-with-budget-population
**Related:** `docs/bugs/adhoc-derive-multi-commit-budget-from-dispatch-sites` (sibling spin-off — MEMBERSHIP/MAGNITUDE derivation, explicitly out of scope here); `docs/bugs/_archive/adhoc-cycle-begin-real-requires-sub-skill` (a different sub_skill-indeterminacy class on the same detector); harden-harness hardening-log `docs/specs/turn-routing-enforcement/hardening-log/2026-06.md` Round 42 (commit `65a262e9`/`b91b268` region — numerator merge-exclusion) and Round 46 (commit `37ab3563`/`9bd61f7` — denominator bookend term, and `fdc564c7` — this bug's own enqueue)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug
                    (which authors PHASES.md from this concluded spec).
-->

**Line numbers below are cited against `user/scripts/lazy_core.py` at HEAD commit `0e899e305c803a13c480da5b23fb9a78eb19a2ef` (2026-07-12), read via `git show HEAD:user/scripts/lazy_core.py` for a stable snapshot while sibling agents were editing the working tree.**

---

## Verified Symptoms

<!-- Harness self-defect spin-off: the "user" is the pipeline's own process-friction ledger.
     No UI/runtime symptom exists — the mechanism is deterministic git-count arithmetic plus a
     fixed-table lookup, so the causal chain is verifiable by static code read alone (no
     runtime-coupled claim is made; see Root-Cause Trace Gate discussion below). -->

1. **[VERIFIED]** Two independent production `unexpected-commits` false-positives already recurred against the SAME structural gap: Round 42 (2026-06-29, AlgoBooth `algorithmic-fill-buffer`) — a merge commit inflated the count for an `execute-plan` cycle; Round 46 (2026-06-30, AlgoBooth `audio-engine-clippy-warnings-fail-rust-gate`) — two deterministic bookend status-flip commits + an in-cycle revert inflated the count for a DIFFERENT `execute-plan` cycle, past a budget that had already absorbed Round 42's fix. Confirmed via `git show fdc564c7` (the Round-46 hardening-log entry, which states verbatim: *"2nd occurrence (Round 42 merge-numerator + Round 46 bookend-denominator) of the count-vs-budget population mismatch class, which Round 42 explicitly predicted would warrant this spin-off"*).
2. **[VERIFIED]** Both fixes landed as point patches scoped to `execute-plan` specifically: Round 42's `--no-merges` exclusion (`lazy_core.py:12057-12060`) is applied UNIFORMLY to every sub_skill (good — it is skill-agnostic), but Round 46's bookend term (`_EXECUTE_PLAN_BOOKEND_COMMITS`, `lazy_core.py:11698`) is wired ONLY into `_execute_plan_commit_budget` (`lazy_core.py:11701-11760`), which returns `None` (no effect) for every sub_skill other than the literal string `"execute-plan"` (`lazy_core.py:11731-11732`).
3. **[VERIFIED]** Every OTHER multi-commit dispatch identity (`write-plan`, `plan-feature`, `plan-bug`, `spec`, `spec-bug`, `mcp-test`, `retro-feature`, `__mark_complete__`, `__mark_fixed__` — `_MULTI_COMMIT_DISPATCH_SKILLS`, `lazy_core.py:11628-11657`) still receives a bare flat ceiling with NO bookend/revert/off-plan-noise cushion: `_CYCLE_COMMIT_MULTI = 3` (`lazy_core.py:11551`) for most members, or the `mcp-test`-specific `_MULTI_COMMIT_CEILING_OVERRIDE = {"mcp-test": 4}` (`lazy_core.py:11591-11593`) — a ceiling the code's own comment (`lazy_core.py:11563-11577`) states is set to the EXACT documented worst-case cadence (self-heal + 2-part PHASES reconcile + sentinel correction = 4 commits), i.e. **zero slack**, the identical shape of the pre-Round-46 `execute-plan` gap (budget == exact expected cadence).
4. **[VERIFIED]** The numerator (`_count_authored_commits_since`, `lazy_core.py:12016-12065`) counts the SAME broad population — "every authored (non-merge) commit in the cycle window" — for ALL of these identities; its own docstring (`lazy_core.py:12042-12047`) documents that unrelated off-plan commits landing on the branch mid-window are DELIBERATELY still counted ("filtering those would require per-cycle path scoping and risk masking a real runaway"). So the numerator's population is uniform and broad across every skill, while only ONE skill's denominator (`execute-plan`) was widened to match it.

## Reproduction Steps

<!-- Deterministic/static reproduction: the entire mechanism is pure functions over git-count
     arithmetic and a fixed-table lookup — no live git mutation performed (HARD RULE: no
     git-state-mutating commands from this investigation agent). Traced through the actual
     code paths at the cited lines; a live run would reproduce these exact code paths verbatim. -->

1. A `--cycle-begin` dispatch is armed with `sub_skill="mcp-test"` (`lazy_core.write_cycle_marker`, `lazy_core.py:11322-11486`), snapshotting `begin_head_sha`.
2. The dispatched `/mcp-test` cycle legitimately lands its documented worst-case 4 commits (self-heal + PHASES-reconcile-part-1 + PHASES-reconcile-Complete-flip + sentinel-schema-correction — the exact cadence `_MULTI_COMMIT_CEILING_OVERRIDE`'s comment, `lazy_core.py:11563-11577`, cites from the real 2026-06-26 `pattern-abstractions` incident) **plus one incidental non-merge commit** of a kind the codebase already recognizes as legitimate noise for `execute-plan` — e.g. an in-cycle `revert(...)` self-correction (the exact category Round 46 observed, `lazy_core.py:11684-11685`) or an unrelated `docs:` commit landing on the branch during the window (the exact category Round 42's own docstring says is deliberately NOT filtered, `lazy_core.py:12044-12046`).
3. At `--cycle-end`, `cycle_end_friction_check` (`lazy_core.py:12068-12170`) computes `commits_since = _count_authored_commits_since(root, begin_head_sha)` (line 12120) = **5** (merges excluded, but the incidental commit is non-merge so it counts).
4. `_execute_plan_commit_budget("mcp-test", ...)` (line 12144) returns `None` at line 11732 (`sub_skill != "execute-plan"`) — no override.
5. `detect_cycle_bracket_friction` (`lazy_core.py:11763-11971`) falls to the registry-derived branch (lines 11944-11958): `"mcp-test" in _MULTI_COMMIT_DISPATCH_SKILLS` → `budget = _MULTI_COMMIT_CEILING_OVERRIDE.get("mcp-test", 3) = 4` (line 11955).
6. `commits_since (5) > budget (4)` (line 11959) → an `unexpected-commits` friction descriptor is returned and appended to the deny ledger (`cycle_end_friction_check` line 12166) — a **false positive**, structurally identical in shape to the pre-Round-46 `execute-plan` recurrence, just on a different dispatch identity.

**Expected (post-fix):** the same incidental-commit categories (revert/self-correction, off-plan noise, an undocumented bookend-like flip) that are cushioned for `execute-plan` are cushioned — via one shared model — for every multi-commit (and, symmetrically, single-commit) dispatch identity, so this reproduction does not trip.
**Actual:** it trips today, for `mcp-test` and, with progressively more headroom, for every other non-`execute-plan` member of `_MULTI_COMMIT_DISPATCH_SKILLS`.
**Consistency:** Deterministic — the code paths above are pure functions of `sub_skill` + commit counts; the outcome is unconditional given these inputs.

## Evidence Collected

### Source Code

**Serving path traced surface → source (each hop `file:line`, HEAD `0e899e30`):**

1. **Numerator surface — the uniform authored-commit count.**
   `_count_authored_commits_since` (`lazy_core.py:12016-12065`) runs `git rev-list --count --no-merges {begin_head_sha}..HEAD` (lines 12057-12060) for EVERY sub_skill alike — no skill-specific scoping. Its own docstring (12042-12047) states the merge exclusion is deliberately narrow: unrelated non-merge commits (off-plan docs, unrelated fixes) are NOT filtered, "removing a category error without lowering the runaway ceiling."
2. **Denominator surface, branch A — `execute-plan`'s work-scaled + cushioned model.**
   `_execute_plan_commit_budget` (`lazy_core.py:11701-11760`) fires ONLY when `sub_skill == "execute-plan"` (line 11731-11732 — an early `return None` for every other identity). Its formula (line 11760): `scale_count + _EXECUTE_PLAN_PHASE_BUDGET_SLACK(2) + _EXECUTE_PLAN_BOOKEND_COMMITS(2)`, where `scale_count = max(phase_count, WU_checkbox_count)`. This is the ONLY budget path in the file that models bookend status-flip commits and carries generous headroom.
3. **Denominator surface, branch B — the flat registry-derived ceiling for every other identity.**
   `detect_cycle_bracket_friction`'s signal-(b) else-branch (`lazy_core.py:11944-11958`) is reached whenever `budget_override` is `None` (i.e., for every sub_skill except `execute-plan`) and `sub_skill` is non-empty: `budget = _MULTI_COMMIT_CEILING_OVERRIDE.get(ss, _CYCLE_COMMIT_MULTI) if ss in _MULTI_COMMIT_DISPATCH_SKILLS else _CYCLE_COMMIT_BUDGET_DEFAULT` (lines 11954-11958). None of `_CYCLE_COMMIT_MULTI = 3` (11551), `_MULTI_COMMIT_CEILING_OVERRIDE = {"mcp-test": 4}` (11591-11593), or `_CYCLE_COMMIT_BUDGET_DEFAULT = 1` (11546) carry ANY bookend/revert/off-plan-noise term — they are bare worst-case (or default) counts.
4. **Comparison — the false-positive site.**
   `commits_since > budget` (`lazy_core.py:11959`) — the numerator (uniform, broad population per hop 1) is compared against whichever denominator model applied (hop 2 for `execute-plan`, hop 3 for everyone else). The mismatch is structural: hop 1's population is skill-agnostic; hop 3's model has no term for the same noise categories hop 2 now absorbs.

**Fix-site-on-path confirmation:** the mismatch's fix site — a shared cushion term applied inside the branch-B budget derivation (`lazy_core.py:11944-11958`) — sits directly on the traced comparison path (hop 4), the same path both Round 42 (hop 1) and Round 46 (hop 2, but scoped to branch A only) already edited.

### Git History

- `65a262e9` / `b91b268` (Round 42, 2026-06-29): `_count_authored_commits_since` added — the numerator's `--no-merges` fix. Applied uniformly (skill-agnostic) — no residual gap on this side.
- `37ab3563` / `9bd61f7` (Round 46, 2026-06-30): `_EXECUTE_PLAN_BOOKEND_COMMITS` added — the denominator's bookend fix, scoped ONLY to `_execute_plan_commit_budget` (branch A). Verified via `git show 37ab3563`: the diff touches only `_execute_plan_commit_budget` and its constants; branch B (`detect_cycle_bracket_friction`'s else-clause) is untouched by this commit.
- `fdc564c7` (Round 46 companion, same day): the hardening-log entry that enqueues THIS bug, explicitly naming both prior commits as "point patches to the SAME structural gap" and predicting a 3rd occurrence without generalization.
- No commit after `fdc564c7` (verified via `git log --oneline --all --grep="population\|bookend\|commit budget"` and a scan of `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`, which reaches Round 34 by 2026-07-12 with no further entry naming this class) touches branch B's cushioning. The only later related entry (`e84207d3`/`d650926`, "Round 3" in the July log) fixes a DIFFERENT defect — a `sub_skill=None` real cycle falling to the single-commit default — by disabling signal (b) entirely for that input, not by cushioning branch B's budgets.

### Related Documentation

- `_MULTI_COMMIT_CEILING_OVERRIDE`'s own comment (`lazy_core.py:11584-11589`) explicitly distinguishes "MAGNITUDE" (how many commits a member's own worst case makes — Round 39's concern, and this bug's sibling `adhoc-derive-multi-commit-budget-from-dispatch-sites`'s concern) from the orthogonal dimension this bug targets: whether the numerator and denominator model the SAME commit population (noise categories), independent of which skill or how many commits its "real work" makes.

## Theories

### Theory 1: The Round-46 fix generalized the POPULATION MODEL, not just execute-plan's number
- **Hypothesis:** perhaps `_EXECUTE_PLAN_BOOKEND_COMMITS` or an equivalent term is already applied to every multi-commit skill via some shared helper, and the brief's premise no longer holds.
- **Supporting evidence:** none found — `_execute_plan_commit_budget`'s early return (line 11731-11732) makes it a hard `sub_skill == "execute-plan"` gate; `detect_cycle_bracket_friction`'s else-branch (11944-11958) has no bookend/revert term of any kind.
- **Contradicting evidence:** the traced code above (hops 2-3) shows two textually and semantically DIFFERENT budget models with no shared cushion term.
- **Status:** Refuted (traced) — the premise holds; the fix was NOT generalized.

### Theory 2: The residual gap is real but inert (no non-`execute-plan` multi-commit skill has ever produced the noise categories that would trip it)
- **Hypothesis:** even though branch B lacks a cushion, in practice no `write-plan`/`plan-feature`/`plan-bug`/`spec`/`spec-bug`/`mcp-test`/`retro-feature`/`__mark_complete__`/`__mark_fixed__` cycle has ever landed a bookend-like flip, revert, or off-plan commit within its budget window, so the gap is theoretical.
- **Supporting evidence:** `mcp-test`'s ceiling (Round 39) was itself raised in reaction to a REAL 4-commit worst-case incident (the 2026-06-26 `pattern-abstractions` recurrence cited at `lazy_core.py:11563-11577`) — i.e. this identity is ALREADY operating at its documented ceiling with no margin, which is exactly the pre-condition Round 46 proved trips on one extra incidental commit.
- **Contradicting evidence:** none — the `mcp-test` ceiling sits at its exact known worst case, meaning the NEXT incidental commit (revert, off-plan doc, or an as-yet-undocumented status flip in `/mcp-test`'s own Step 5.2 reconcile cadence) reproduces Round 46's exact shape.
- **Status:** Confirmed as a live, not merely theoretical, residual risk — `mcp-test` is one incidental commit away from repeating the recurrence on a different skill, which is the exact 3rd occurrence Round 46's hardening-log entry predicted.

## Proven Findings

- **Root cause (traced):** The `unexpected-commits` numerator (`_count_authored_commits_since`, `lazy_core.py:12016-12065`) models ONE uniform commit population — every authored non-merge commit in the cycle window, for any sub_skill — while the budget denominator models this population with TWO structurally different formulas: a work-scaled, slack-and-bookend-cushioned model for `execute-plan` alone (`_execute_plan_commit_budget`, `lazy_core.py:11701-11760`), and a bare flat ceiling with zero noise cushion for every other dispatch identity (`detect_cycle_bracket_friction` lines 11944-11958, backed by `_CYCLE_COMMIT_MULTI`/`_MULTI_COMMIT_CEILING_OVERRIDE`/`_CYCLE_COMMIT_BUDGET_DEFAULT`). Round 42 and Round 46 each closed one concrete instance of this mismatch (both surfaced via `execute-plan`) without closing the class — the fix was applied to ONE skill's denominator model, not to the shared population definition the numerator actually enforces.
- **Recommended fix (for `/plan-bug`):** add ONE small, uniform cushion term — e.g. `_CYCLE_COMMIT_NOISE_ALLOWANCE = 1` — representing "a small revert/self-correction allowance" (the brief's own phrasing) applied inside `detect_cycle_bracket_friction`'s branch-B budget derivation (lines 11944-11958), on top of `_CYCLE_COMMIT_MULTI` / `_MULTI_COMMIT_CEILING_OVERRIDE` / `_CYCLE_COMMIT_BUDGET_DEFAULT` alike. This directly implements the brief's second class-boundary option ("declare the full deterministic per-cycle commit cadence... once in a single model both sides derive from") for the piece of that model that is genuinely skill-agnostic (reverts/self-corrections/off-plan noise), while leaving `execute-plan`'s own WU-scaling and bookend terms untouched (they model a DIFFERENT, skill-specific piece — the deterministic status-flip cadence unique to `/execute-plan`'s Step 4e/4f).
  - ⚖ **Design fork — where the allowance applies:**
    - **Option A (recommended):** apply the allowance ONLY to the registry-derived branch (multi-commit AND single-commit defaults), leaving `execute-plan`'s `budget_override` path untouched — no risk of double-cushioning, minimal diff, and it does not touch `_MULTI_COMMIT_DISPATCH_SKILLS` membership or any skill's MAGNITUDE override (both explicitly out of scope per the brief, and owned by the sibling bug).
    - **Option B:** fold the allowance into `execute-plan`'s formula too (replacing its bespoke slack with the shared allowance) for maximal unification — rejected as first cut: it would require re-deriving Round 20's `_EXECUTE_PLAN_PHASE_BUDGET_SLACK` sizing rationale (a WITHIN-phase test+impl split, not the same category as the noise allowance) and risks silently loosening the execute-plan ceiling as a side effect of an unrelated change, when the brief's fix-scope explicitly excludes touching "the friction-detection threshold semantics" or "the runaway ceiling KIND."
  - **Recommendation:** Option A. It is the minimal, narrowly-scoped structural fix that satisfies the brief's stated goal without perturbing membership, magnitude, or `execute-plan`'s already-correct model.
  - **What Option A explicitly does NOT touch (out of scope, confirmed unaffected):** `_MULTI_COMMIT_DISPATCH_SKILLS` membership; any skill's per-skill MAGNITUDE override (`_MULTI_COMMIT_CEILING_OVERRIDE`); the `--no-merges` numerator exclusion; the meta-cycle exemption; the branch-divergence / cycle-bracket-break signals.
- **Regression coverage the fix must add:** a `test_lazy_core.py` case reproducing this SPEC's Reproduction Steps for `mcp-test` (budget 4, 5 non-merge commits inc. 1 incidental → clean post-fix, still-trips at 6+); a symmetry case for a single-commit-default skill (budget 1 → 1+allowance) confirming a genuine runaway beyond the allowance still trips for every branch-B identity.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Registry-derived commit budget (branch B) | `user/scripts/lazy_core.py` — `detect_cycle_bracket_friction` (~11944-11958) | Add shared `_CYCLE_COMMIT_NOISE_ALLOWANCE` term to the multi-commit and single-commit-default budget computation |
| New shared constant | `user/scripts/lazy_core.py` (co-located near `_CYCLE_COMMIT_MULTI`/`_CYCLE_COMMIT_BUDGET_DEFAULT`, ~11546-11593) | Document provenance (this SPEC) mirroring the `_EXECUTE_PLAN_PHASE_BUDGET_SLACK`/`_EXECUTE_PLAN_BOOKEND_COMMITS` comment style |
| Bug pipeline | `user/scripts/bug-state.py` | No direct edit — `cycle_end_friction_check`/`detect_cycle_bracket_friction` are SHARED `lazy_core` helpers both pipelines call; the fix is inherited automatically (same coupling Round 46 documented, `fdc564c7`) |
| Tests | `user/scripts/test_lazy_core.py` | New regression cases per "Regression coverage" above; audit existing `_MULTI_COMMIT_*` budget tests for the new term |
| Docs | none required beyond the new constant's own comment — no sentinel schema, no SKILL.md prose change (this is a runtime cycle-budget denominator, not a doc contract) |

**Lane:** STATE (lazy_core.py / state-script surface) — schedule alongside other `lazy_core.py`/state-script work per the orchestrator's lane-scheduling convention (both bug dirs in this batch land in the same lane).

## Open Questions

- None blocking. The premise is TRUE and the fix is narrowly scoped per the brief's stated boundary (population alignment only — membership/magnitude/threshold-kind changes are explicitly out of scope and belong to `adhoc-derive-multi-commit-budget-from-dispatch-sites`). **Won't-fix is NOT recommended** — evidence (`mcp-test`'s zero-slack ceiling) shows the residual gap is a live, not theoretical, risk of a 3rd occurrence.
