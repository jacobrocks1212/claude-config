# Implementation Phases — /execute-plan trusts a green test run without asserting the expected files are actually DIRTY

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Fixed

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; this is a skill/component **prose** contract change (`user/skills/**`), verified via the repo's skill-authoring gates (`lint-skills.py --check-projected --check-capabilities`, `project-skills.py`, `lazy_parity_audit.py`), the "build-tooling / repo-config, no app integration" untestable class. There is no `mcp-tool-catalog.md` in this repo, so the planning-time MCP tool-existence audit no-ops.

## Validated Assumptions

- **The Ground-Truth Verification Gate (`subagent-review.md` Step 1.5 / `execution-contract.md`'s Per-WU verification gate) is a self-consistency check (subagent's self-report vs. the orchestrator's fresh re-run), not a ground-truth-vs-plan check.** Confirmed by reading both files in full pre-fix — neither references the plan's per-WU `Files to create/modify:` field (`write-plan/SKILL.md:307`). Static/prose-readable, not runtime-coupled — see SPEC.md "Investigation" for the full trace.
- **`execute-plan/SKILL.md` needs no direct edit.** It delegates the gate's mechanics entirely to `subagent-review.md` (Step 3 item 4, `execute-plan/SKILL.md:164`) and to `execution-contract.md` (Step B.2, `execution-contract.md:116-122`) via `!cat`/`Read`-from-disk — fixing the two shared components fixes every consumer.

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC (only a `**Related:**` line to the `verification-before-completion` family and `execute-plan/SKILL.md`) — no upstream PHASES.md look-back applies. `subagent-review.md` and `execution-contract.md`'s Per-WU verification gate section are not a formally registered coupled pair in `lazy-parity-manifest.json` (that registry covers the `/lazy*`-family skills, not this internal SKILL.md/`_components/` duplication) — they are edited together here as an ordinary DRY-duplication fix, and `lazy_parity_audit.py` is run as a gate only because it is cheap and touches nothing it doesn't already cover (expected: no findings, since neither file is in its manifest).

---

### Phase 1: Add the dirty-tree assertion to both copies of the ground-truth gate

**Scope:** Close the git-stash false-green gap by adding a WU-declared-files dirty-tree assertion, independent of the subagent's self-report, to `user/skills/_components/subagent-review.md` Step 1.5 and to `user/skills/_components/execution-contract.md`'s "Per-WU verification gate" section. This is the load-bearing (and only) phase — after it, a WU whose declared files show no change against the pre-batch baseline fails the gate automatically, even if the subagent's self-report agrees with the (wrongly reverted) tree.

**TDD:** no — these are Markdown skill-contract files (prose, not executable code); there is no test runner for skill prose in this repo. The verification method is the repo's own skill-authoring gate chain (lint + projection + parity audit) plus a manual before/after excerpt comparison, per `docs/bugs/_archive/legacy-tool-input-env-hooks-dead/PHASES.md`'s precedent for docs/prose-only phases in this repo.

**Status:** Complete

**Deliverables:**
- [x] `user/skills/_components/subagent-review.md` Step 1.5: inserted a new item 2 ("Dirty-tree assertion against the WU's DECLARED files") between the existing items 1 and 2 (renumbering old items 2-6 to 3-7); updated the internal cross-references ("item 4 below" → "item 5 below"; "item 1/2 disagrees" → "item 1/2/3 disagrees"); extended the "Any mismatch is a falsified report" bullet list with the new failure mode; extended the `Ground-truth verified: yes`/`no` outcome definitions to name the new check explicitly.
- [x] `user/skills/_components/execution-contract.md`'s "Per-WU verification gate" → "Default per WU" list: inserted the same dirty-tree assertion as item 2 (old item 2 "assertion-vs-intent read" renumbered to item 3), pointing at `subagent-review.md` Step 1.5 item 2 for the full mechanics; updated "These two together are the default gate" → "These three together..."; extended the "Conditional full-suite re-run" trigger list and its "clean ... is sufficient" sentence to include the new check.
- [x] Both edits reference the SAME plan-declared source of truth (`write-plan/SKILL.md`'s per-WU `Files to create/modify:` template field, `write-plan/SKILL.md:307`) with a documented fallback to the subagent's own prose `Files created\modified:` line (`implementation-agent.md:96-97`) for plans that don't enumerate that granularly.
- [x] Gate: `python user/scripts/lint-skills.py --check-projected --check-capabilities` exit 0.
- [x] Gate: `python user/scripts/project-skills.py` runs clean (no errors; projected output for both files spot-checked to confirm the new item expanded correctly with no circular includes).
- [x] Gate: `python user/scripts/lazy_parity_audit.py --repo-root .` exit 0 (neither touched file is in the parity manifest; audit is a no-op-clean pass, run as a backstop per the bug-subagent workflow).

**Implementation Notes (2026-07-12):** Root cause (SPEC.md "Root Cause"): the gate's two existing checks (fresh re-run of `git status --short`/`wc -l`/`grep -n`, diffed against the subagent's own pasted `GROUND-TRUTH OUTPUT` block) only assert *self-consistency* — that two readings of current git state agree with each other. They never assert that the WU's plan-declared files actually appear as changes at all, so a tree silently reverted (un-popped `git stash`) before the subagent's capture produces two readings that trivially agree on "clean" and passes as `Ground-truth verified: yes`. Fix: added an independent dirty-tree assertion (new item 2 in both files) that cross-references the WU's plan-declared `Files to create/modify:` list against `git status --short` / `git show --stat HEAD -- <file>` — a declared file clean in both is now an automatic gate failure regardless of self-report agreement. Files: `user/skills/_components/subagent-review.md`, `user/skills/_components/execution-contract.md`. No hook/state-script/test-file change required (skills-lane-only fix); no cross-lane edits needed.

**Minimum Verifiable Behavior:** Before the fix, a hypothetical WU whose subagent stashed its edit before capturing its `GROUND-TRUTH OUTPUT` block would read `Ground-truth verified: yes` (both readings of the reverted tree agree). After the fix, the same scenario is caught: the WU's plan-declared file(s) show clean in `git status --short` and absent from any commit, tripping the new item 2 check → `Ground-truth verified: no` → verdict `NEEDS-REWORK`, regardless of the subagent's self-report. Concretely verifiable by reading the pre-fix vs post-fix excerpts of `subagent-review.md` Step 1.5 (see FIXED.md's symptom-reproduction section for the literal before/after).

**Runtime Verification:** N/A — no runtime/MCP surface for this repo's skill-prose contracts; the "verification" is the gate chain below plus the manual excerpt read.

**MCP Integration Test Assertions:** N/A — no MCP tool surface touched.

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/skills/_components/subagent-review.md` — Step 1.5, items 1-6 → renumbered 1-7 with the new item 2 inserted (verified exists; edited in this pass).
- `user/skills/_components/execution-contract.md` — "Per-WU verification gate" → "Default per WU" list, items 1-2 → renumbered 1-3 with the new item 2 inserted (verified exists; edited in this pass).

**Testing Strategy:** `lint-skills.py --check-projected --check-capabilities` (broken/embedded-injection + capability checks), `project-skills.py` (clean re-projection, spot-checked), `lazy_parity_audit.py --repo-root .` (backstop; neither file is in the manifest, so a clean pass is expected and confirms the edit introduced no parity regression elsewhere).

**Integration Notes for Next Phase:** None — final phase. The bug-pipeline `__mark_fixed__` gate (orchestrator-owned) flips the SPEC/PHASES top-level `**Status:**` and writes `FIXED.md` after the validation tail; per this run's OPERATOR PROTOCOL (park-provisional, no design fork encountered — this bug closes normally), this pass performs that close-out directly rather than leaving it to a separate gate invocation, since there is no `__mark_fixed__` pipeline run active for this standalone bug-subagent dispatch.

**Completion:** the SPEC.md / PHASES.md top-level `**Status:**` is flipped to `Fixed` and `FIXED.md` is written as part of this same pass (see FIXED.md for the receipt) — Status Investigating → Concluded → Fixed, no provisional halt encountered.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews. This bug was investigated, planned, and fixed in a single bug-subagent dispatch — no separate /spec-phases or /execute-plan invocation ran; the review discipline above (self-review against the Ground-Truth gate protocol itself) substitutes.)_
