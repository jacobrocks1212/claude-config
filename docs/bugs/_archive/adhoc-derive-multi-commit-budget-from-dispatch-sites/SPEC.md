---
kind: investigation-spec
bug_id: adhoc-derive-multi-commit-budget-from-dispatch-sites
---

# Derive multi-commit cycle-commit budget from dispatch sites, not a hand-maintained registry — Investigation Spec

> `_MULTI_COMMIT_DISPATCH_SKILLS` (`lazy_core.py`) is a hand-maintained `frozenset` a human/hardening-agent must remember to append every time a new multi-commit dispatch identity is introduced. This missing-row class has recurred 6+ times (Rounds 15, 16/17, 23, 31, 38 per the brief) and the registry has ALREADY drifted from ground truth in the opposite direction too: it still lists `retro-feature` as a member even though `retro-feature` is dead/unwired and dispatched from NOWHERE in either state script.

**Status:** Fixed
**Severity:** Medium
**Discovered:** 2026-07-12
**Placement:** docs/bugs/adhoc-derive-multi-commit-budget-from-dispatch-sites
**Related:** `docs/bugs/adhoc-align-cycle-commit-count-with-budget-population` (sibling spin-off — POPULATION alignment, explicitly out of scope here); harden-harness hardening-log Round 38 (2026-06-25, commit `0ece589` — introduced the frozenset SSOT this bug targets) and Round 39 (`dcfeb0ba`/`1736bd73` — the orthogonal MAGNITUDE override for `mcp-test`)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug
                    (which authors PHASES.md from this concluded spec).
-->

**Line numbers below are cited against `user/scripts/lazy_core.py` / `user/scripts/lazy-state.py` / `user/scripts/bug-state.py` at HEAD commit `0e899e305c803a13c480da5b23fb9a78eb19a2ef` (2026-07-12), read via `git show HEAD:<path>` for a stable snapshot while sibling agents were editing the working tree.**

---

## Verified Symptoms

<!-- Harness self-defect spin-off: the "user" is the pipeline's own process-friction ledger /
     the hardening-agent maintaining the registry. No UI/runtime symptom — the mechanism is a
     static Python frozenset consulted by a pure function, so the causal chain is verifiable by
     static code read alone. -->

1. **[VERIFIED]** `_MULTI_COMMIT_DISPATCH_SKILLS` (`lazy_core.py:11628-11657`) is a literal `frozenset` of 10 string identities (`execute-plan`, `retro-feature`, `mcp-test`, `write-plan`, `plan-feature`, `plan-bug`, `spec`, `spec-bug`, `__mark_complete__`, `__mark_fixed__`) that a human/agent must edit by hand. Its own comment block (11610-11620) documents the missing-row history it replaced: "the prior reactive literal `_CYCLE_COMMIT_BUDGET` table, whose five dated per-row provenance comments each recorded a production `unexpected-commits` false-positive that was patched AFTER the fact (Round 15 `execute-plan`; Rounds 16/17 the pseudo-skills; a later round `mcp-test`; 2026-06-22 `write-plan`/`plan-feature`/`plan-bug`)." Round 38 (`0ece589`) added `spec`/`spec-bug` as the SIXTH such after-the-fact patch (confirmed via `git show 5636fe39`, the commit adding them to the set).
2. **[VERIFIED]** The frozenset SSOT introduced by Round 38 (`0ece589`) did NOT close the class — it only relocated the enumeration from a per-row literal budget dict to a still-literal, still-hand-maintained set. No mechanism connects this set to the actual dispatch call sites; adding a new `sub_skill="..."` literal to `lazy-state.py` or a new `SKILL_*` constant to `bug-state.py` has ZERO effect on `_MULTI_COMMIT_DISPATCH_SKILLS` unless a human/agent separately edits `lazy_core.py`.
3. **[VERIFIED]** The registry has ALREADY drifted from dispatch-site ground truth, in the opposite ("stale extra entry") direction: `retro-feature` is a member (`lazy_core.py:11631`) but is dispatched from **nowhere**. Confirmed by exhaustive grep of both state scripts at HEAD: `bug-state.py:180` defines `SKILL_RETRO = "retro-feature"  # DORMANT (retro unwired 2026-06) — kept for restore path  # noqa: F841` — the `# noqa: F841` marker is Python's own "unused variable" suppression, i.e. the codebase itself documents this constant is unreferenced. `grep -n "SKILL_RETRO" bug-state.py` returns only the definition line — it is never passed as `sub_skill=`. `grep -n "sub_skill=\"retro-feature\""` across both scripts returns zero matches. `retro-feature`'s only other mentions (`lazy-state.py:3356,4465,6103`; `bug-state.py:1561,2159`) are all negative-form comments ("NOT to retro-feature", "never … retro-feature") documenting that the Step-8 retro phase was unwired 2026-06 and the pipeline routes DIRECTLY to `mcp-test` instead. A mechanical, dispatch-site-derived budget would have caught and removed this stale entry automatically; the hand-maintained set carries it indefinitely.
4. **[VERIFIED]** A working precedent for skill-declared-capability derivation already exists in the SAME file for a structurally identical problem: `skill_declares_subagent_model()` (`lazy_core.py:11191-11256`) reads a `subagent-model: true` YAML-frontmatter flag from the dispatched skill's own `SKILL.md` (repo-scoped then user-level resolution order, lines 11230-11238) instead of maintaining a hardcoded skill list — its own docstring (11178-11185) explicitly frames the prior hardcoded-list approach as "re-opens the gap for every new sub-subagent-model skill," the exact class this bug describes for commit budgets.
5. **[VERIFIED]** None of the 7 real (non-pseudo) member skills currently declare any commit-cadence-related frontmatter field: `user/skills/execute-plan/SKILL.md`, `user/skills/write-plan/SKILL.md`, `user/skills/spec/SKILL.md`, `user/skills/spec-bug/SKILL.md`, `user/skills/plan-feature/SKILL.md`, `user/skills/plan-bug/SKILL.md` (all inspected, frontmatter blocks shown in Evidence below), and the repo-scoped `repos/algobooth/.claude/skills/mcp-test/SKILL.md` — none carry a field analogous to `subagent-model: true`. A frontmatter-based derivation is therefore purely additive, not a retrofit of conflicting data.

## Reproduction Steps

<!-- Deterministic/static reproduction of the missing-row class: no live git mutation performed
     (HARD RULE). Traced through the actual registry + dispatch-site code. -->

1. Hypothetically, a new dispatch identity — e.g. a future `/consolidate-plan` skill whose SKILL.md contract legitimately commits 3 times per cycle — is added to `lazy-state.py` as `sub_skill="consolidate-plan"` at a new dispatch site.
2. `detect_cycle_bracket_friction`'s branch-B budget derivation (`lazy_core.py:11944-11958`) evaluates `"consolidate-plan" in _MULTI_COMMIT_DISPATCH_SKILLS` → **False** (the frozenset was never told about this new identity) → `budget = _CYCLE_COMMIT_BUDGET_DEFAULT = 1` (line 11957-11958, 11546).
3. The cycle's 3 legitimate commits trip `commits_since (3) > budget (1)` (line 11959) → a false-positive `unexpected-commits` entry — the EXACT recurrence pattern documented for Rounds 15, 16/17, 23, 31, and 38 (each: a new/overlooked dispatch identity defaults to budget 1 and false-positives on its first real multi-commit cycle).
4. **Complementary, already-live reproduction (no hypothetical needed):** `retro-feature` sits in the registry as a stale member. If the Step-8 retro phase were ever re-wired (the DORMANT comments at `lazy-state.py:3356` / `bug-state.py:1561` explicitly name "git history is the restore path"), a restored `/retro-feature` dispatch would inherit whatever budget the frozenset happened to carry from BEFORE the unwiring — with no mechanism to verify that budget still matches `/retro-feature`'s current (possibly since-changed) SKILL.md contract. The registry does not track staleness in either direction.

**Expected (post-fix):** a new multi-commit dispatch identity's budget is derived from a declaration the skill ITSELF owns (its SKILL.md frontmatter), so adding the dispatch site is sufficient — no separate `lazy_core.py` registry edit is required, and a skill that stops being dispatched (or changes its cadence) cannot leave a stale/inaccurate row behind unnoticed.
**Actual:** today, a new dispatch identity silently defaults to budget 1 until a human/hardening-agent remembers to append it to `_MULTI_COMMIT_DISPATCH_SKILLS`; conversely, a retired identity (`retro-feature`) keeps its stale membership indefinitely.
**Consistency:** Deterministic — the frozenset lookup at line 11956 is a pure membership test; the outcome is unconditional given the identity string.

## Evidence Collected

### Source Code

**Serving path traced surface → source (each hop `file:line`, HEAD `0e899e30`):**

1. **Dispatch-site surface — where a sub_skill identity is born.**
   `lazy-state.py` bare literals: `sub_skill="spec"` (2984, 2993, 3023, 3117, 3128), `sub_skill="realign-spec"` (3047), `sub_skill="plan-feature"` (3159), `sub_skill="execute-plan"` (3343), `sub_skill="mcp-test"` (3409, 3557, 3592), `sub_skill="__mark_complete__"` (3655), plus several single-commit pseudo-ops (`__provisional_accept__` 2197, `__flip_plan_complete_stale__` 3321, `__flip_plan_complete_cloud_saturated__` 3337, `__write_deferred_non_cloud__` 3445, `__write_validated_from_skip__` 3469/3494, `__write_validated_from_results__` 3567, `__grant_skip_no_mcp_surface__` 3585). `bug-state.py` mirrors via named constants: `SKILL_INVESTIGATE = "spec-bug"` (175), `SKILL_PLAN_BUG = "plan-bug"` (176), `SKILL_WRITE_PLAN = "write-plan"` (178), `SKILL_EXECUTE_PLAN = "execute-plan"` (179), `SKILL_RETRO = "retro-feature"` (180, **unused** — see below), `SKILL_MCP_TEST = "mcp-test"` (181), `SKILL_MARK_FIXED = "__mark_fixed__"` (182), consumed at dispatch sites 1458, 1464, 1492, 1552, 1581/1714/1746, 1789.
2. **Registry surface — the hand-maintained SSOT, disconnected from hop 1.**
   `_MULTI_COMMIT_DISPATCH_SKILLS: frozenset[str] = frozenset({...})` (`lazy_core.py:11628-11657`) lists 10 literal strings. Nothing in either state script IMPORTS from or WRITES to this set based on its own dispatch sites — it is authored independently, by hand, in a different module.
3. **Consumption surface — the false-positive site.**
   `detect_cycle_bracket_friction` (`lazy_core.py:11944-11958`): `ss in _MULTI_COMMIT_DISPATCH_SKILLS` gates between the multi-commit ceiling and `_CYCLE_COMMIT_BUDGET_DEFAULT = 1`. A dispatch identity present at hop 1 but absent from hop 2's set falls to the single-commit default regardless of its true cadence.
4. **The working precedent for a structural fix.**
   `skill_declares_subagent_model` (`lazy_core.py:11191-11256`) resolves `<repo_root>/.claude/skills/<name>/SKILL.md` then `~/.claude/skills/<name>/SKILL.md` (lines 11230-11238), extracts only the leading YAML frontmatter block (11245-11251), and regex-matches a boolean flag (`_SUBAGENT_MODEL_FLAG_RE`, 11186-11188) — fail-closed on any missing file/flag (11212-11214, 11255-11256). This is invoked from `write_cycle_marker` (line ~11418) at `--cycle-begin` time, i.e. the marker ALREADY carries a per-dispatch, skill-declared capability computed this exact way — the commit-budget membership question is structurally identical and could reuse the same resolution order and fail-closed posture.

**Fix-site-on-path confirmation:** the proposed fix (a new `skill_declares_multi_commit`-shaped helper, modeled on hop 4, consulted at hop 3 instead of the hop-2 frozenset) sits directly on the traced consumption path (`detect_cycle_bracket_friction` line ~11956), the exact site the frozenset lookup occupies today.

### Git History

- `0ece589` (Round 38, 2026-06-25) — introduced `_MULTI_COMMIT_DISPATCH_SKILLS` as the "SSOT," replacing a prior literal per-row budget dict. Confirmed via `git show 5636fe39` ("harden(script): add spec + spec-bug to multi-commit dispatch registry"), which is the ADD-A-ROW commit for this very set — proving the pattern (edit `lazy_core.py` by hand whenever a new identity needs multi-commit treatment) continued unchanged after Round 38's relocation.
- `dcfeb0ba` / `1736bd73` (Round 39) — added the ORTHOGONAL `_MULTI_COMMIT_CEILING_OVERRIDE` for `mcp-test`'s magnitude (out of scope here per the brief; cited only to distinguish membership from magnitude).
- `12f514ad` / `b1c53e3d` (Round 31) — added `write-plan`/`plan-feature`/`plan-bug` budget rows (pre-frozenset era, same missing-row shape).
- `fbf00fbe` / `47ca8d99` (earlier round) — added the first `mcp-test` row (same shape).
- `3892c9f9` / `d9c0f855` / `72d0b672` (Rounds 16/17) — added the pseudo-skill budget rows (same shape).
- No commit found (via `git log --all --grep="dispatch.sites\|multi-commit.*registry\|derive.*budget"`) that connects the registry to the dispatch sites mechanically — every historical change to `_MULTI_COMMIT_DISPATCH_SKILLS` (or its predecessor table) is a manually-authored literal edit.

### Related Documentation

- `_MULTI_COMMIT_CEILING_OVERRIDE`'s comment (`lazy_core.py:11584-11589`) explicitly frames the sibling bug's boundary: "that bug targets MEMBERSHIP derivation (which skills are multi-commit)... This map is the orthogonal MAGNITUDE dimension (how many commits a member legitimately makes)." This SPEC's fix must NOT touch `_MULTI_COMMIT_CEILING_OVERRIDE` — magnitude stays a separate, per-skill-declared concern (a natural frontmatter extension, e.g. `commit-cadence: multi` vs. a numeric `max-commits: N`, could unify both dimensions later, but this bug's brief scopes OUT any change to "the friction-detection thresholds or the runaway ceiling").

## Theories

### Theory 1: Dispatch-site-derived membership (grep `lazy-state.py`/`bug-state.py` at runtime)
- **Hypothesis:** derive membership by having `lazy_core.py` parse the two state scripts' source for `sub_skill="..."` literals / `SKILL_*` assignments at runtime or via a generation step.
- **Supporting evidence:** the dispatch sites ARE the ground truth for which identities EXIST.
- **Contradicting evidence:** dispatch sites only tell you an identity is DISPATCHED, not whether its cycle is multi-commit — that information does not live at the call site (a `sub_skill="mcp-test"` literal carries no cadence data). Parsing source text at runtime is also fragile (a dynamic/computed sub_skill argument, of which several exist per the pseudo-skill dispatch sites above, would not be grep-able) and introduces a script-parsing-script dependency with no precedent in this codebase.
- **Status:** Refuted as the primary mechanism — dispatch sites answer WHICH identities exist, not their cadence; this theory conflates the two.

### Theory 2: Per-skill frontmatter declaration, consulted the way `skill_declares_subagent_model` already is
- **Hypothesis:** each real dispatched skill declares its own commit cadence in its SKILL.md frontmatter (e.g. `commit-cadence: multi`); `lazy_core.py` adds a sibling helper to `skill_declares_subagent_model` that reads it, replacing frozenset membership for every identity that HAS a SKILL.md. The 2 pseudo-skill identities with no SKILL.md (`__mark_complete__`, `__mark_fixed__` — orchestrator-computed terminal ops, not real dispatched Agent skills) keep a small explicit dict, since they are fixed, state-script-owned terminal identities that can never be "newly dispatched" from elsewhere (the missing-row class does not apply to them the same way).
- **Supporting evidence:** the exact precedent already exists in the same file (`skill_declares_subagent_model`, hop 4 above) for a structurally identical "skill declares its own capability" problem; none of the current 7 real-skill members' frontmatter conflicts with adding a new field (hop/finding 5); the fix stays additive and skill-owned, so a skill's own commit cadence is documented WHERE the skill's author would naturally look and edit it, rather than in a separate module 3 hops away.
- **Contradicting evidence:** none found. This does not by itself explain HOW MANY commits (magnitude) — but the brief explicitly scopes magnitude out (it is `_MULTI_COMMIT_CEILING_OVERRIDE`'s job, Round 39, sibling concern), so membership-only derivation (multi vs. single) is sufficient to satisfy this bug's boundary.
- **Status:** Confirmed as the recommended mechanism — it closes the missing-row class (a skill's own frontmatter travels WITH it; forgetting to flag a new multi-commit skill is a review-visible omission in the skill's own file, not a silent cross-module gap) and would have caught the `retro-feature` staleness too (its SKILL.md still exists at `user/skills/retro-feature/SKILL.md`; whatever it currently declares — or a frontmatter audit surfacing it as still-flagged-but-never-dispatched — is a visible, fixable signal instead of silent registry rot).

## Proven Findings

- **Root cause (traced):** `_MULTI_COMMIT_DISPATCH_SKILLS` (`lazy_core.py:11628-11657`) is a hand-maintained literal registry with NO structural connection to the dispatch sites (`lazy-state.py`'s bare `sub_skill="..."` literals, `bug-state.py`'s `SKILL_*` constants) that create the identities it is supposed to track. This produces defects in BOTH directions: (a) missing-row — a newly-dispatched multi-commit identity silently defaults to `_CYCLE_COMMIT_BUDGET_DEFAULT = 1` and false-positives `unexpected-commits` on its first legitimate multi-commit cycle (recurred 6+ times per the brief, confirmed via git history for Rounds 15/16/17/23/31/38); (b) stale-row — a retired identity (`retro-feature`, confirmed dead/unwired via `# noqa: F841` + exhaustive grep showing zero dispatch sites) keeps indefinite membership with no staleness check.
- **Recommended fix (for `/plan-bug`):** replace `_MULTI_COMMIT_DISPATCH_SKILLS` frozenset-membership consultation (`lazy_core.py:11956`) with a new helper — e.g. `skill_declares_multi_commit(sub_skill, repo_root=...)` — modeled DIRECTLY on `skill_declares_subagent_model` (11191-11256): same repo-scoped-then-user-level SKILL.md resolution order, same leading-frontmatter-only extraction, same fail-closed posture (missing file/flag → not multi-commit → conservative default budget, never a crash and never a false negative on the safe side). Add a `commit-cadence: multi` (or equivalently-named boolean) frontmatter flag to the 7 real skills currently in the set (`execute-plan`, `write-plan`, `plan-feature`, `plan-bug`, `spec`, `spec-bug`, `mcp-test` — the repo-scoped AlgoBooth copy too) — each addition is a 1-line frontmatter edit the skill's own author makes alongside any future cadence change. Retain a small explicit dict (or inline check) for the 2 pseudo-skill identities (`__mark_complete__`, `__mark_fixed__`) since they have no SKILL.md — document explicitly that this residual is bounded (exactly 2, both terminal/state-script-owned, never independently "newly dispatched") and is NOT the missing-row class this bug closes. Remove `retro-feature` from the registry (or, if `skill_declares_multi_commit` is skill-md-driven, its removal falls out naturally once the flag is added only to the 7 currently-live skills — `retro-feature`'s own SKILL.md is left unflagged, so it correctly reverts to the single-commit default, matching its DORMANT/unwired status).
  - ⚖ **Design fork — frontmatter shape:** a boolean (`commit-cadence: multi`) is sufficient for THIS bug's membership-only scope; a numeric (`max-commits: N`) would additionally subsume Round 39's `mcp-test` magnitude override, unifying both dimensions — but the brief explicitly scopes magnitude OUT ("the budget MEMBERSHIP/MAGNITUDE derivation" is named as a single bounded-out phrase, and `_MULTI_COMMIT_CEILING_OVERRIDE`'s own comment frames magnitude as orthogonal). **Recommendation:** ship the boolean now (satisfies this bug's stated boundary with the smallest diff); leave a numeric unification as a natural, separately-scoped follow-up if a future spin-off targets magnitude derivation too.
- **Regression coverage the fix must add:** a `test_lazy_core.py` case for `skill_declares_multi_commit` mirroring `skill_declares_subagent_model`'s existing test shape (flagged skill → True; unflagged → False; missing file → False; malformed frontmatter → False); an end-to-end `detect_cycle_bracket_friction` case proving a NEW skill with the frontmatter flag gets the multi-commit ceiling with zero `lazy_core.py` edits beyond the helper itself; a case proving `retro-feature` (unflagged post-fix) now correctly defaults to budget 1.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| New derivation helper | `user/scripts/lazy_core.py` (new function near `skill_declares_subagent_model`, ~11191-11256) | `skill_declares_multi_commit(sub_skill, repo_root=...)` — SKILL.md-frontmatter-driven, modeled on the existing helper |
| Registry consumption site | `user/scripts/lazy_core.py` — `detect_cycle_bracket_friction` (~11944-11958) | Replace `ss in _MULTI_COMMIT_DISPATCH_SKILLS` with the new helper call; retain a small explicit dict for the 2 pseudo-skill identities only |
| Frontmatter additions | `user/skills/execute-plan/SKILL.md`, `user/skills/write-plan/SKILL.md`, `user/skills/spec/SKILL.md`, `user/skills/spec-bug/SKILL.md`, `user/skills/plan-feature/SKILL.md`, `user/skills/plan-bug/SKILL.md`, `repos/algobooth/.claude/skills/mcp-test/SKILL.md` | Add `commit-cadence: multi` (naming TBD at implementation) to each; re-run `project-skills.py` + `lint-skills.py` after editing |
| Registry retirement | `user/scripts/lazy_core.py` — `_MULTI_COMMIT_DISPATCH_SKILLS` (11628-11657) | Remove once the helper fully replaces its consumption site; `retro-feature`'s removal falls out naturally (its SKILL.md stays unflagged) |
| Bug pipeline | `user/scripts/bug-state.py` | No direct edit — shared `lazy_core` helper; inherited automatically (same coupling pattern as the sibling bug) |
| Tests | `user/scripts/test_lazy_core.py` | New regression cases per "Regression coverage" above |
| Docs | `user/skills/CLAUDE.md` / `user/skills/_components/CLAUDE.md` frontmatter contract table | Document the new field alongside `subagent-model` |

**Lane:** STATE (lazy_core.py / state-script surface) + a small SKILLS-lane frontmatter sweep — schedule the `lazy_core.py` helper + consumption-site edit alongside the sibling bug (same lane, same file), with the SKILL.md frontmatter additions as a lightweight companion WU.

## Open Questions

- None blocking. The premise is TRUE: the registry is hand-maintained, structurally disconnected from dispatch sites, and has already drifted stale in the `retro-feature` direction as well as historically missing-row 6+ times. **Won't-fix is NOT recommended** — a working precedent (`skill_declares_subagent_model`) for the recommended fix already exists in the same file, making this a low-risk, well-modeled structural fix rather than a speculative redesign.
