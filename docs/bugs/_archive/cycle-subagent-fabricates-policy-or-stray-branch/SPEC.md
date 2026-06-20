# Cycle subagents fabricate ungrounded artifacts — a non-existent commit policy, a stray git branch — Investigation Spec

> `/lazy-batch` cycle subagents produced artifacts grounded in nothing they actually read. One subagent hallucinated a "manual-only" commit policy from a `commit-policy.md` that does not exist and skipped a required commit; another committed a halt sentinel (NEEDS_INPUT.md) to a self-invented `audit/...` branch off the work branch instead of on `main`, so the resume path would not have found it. Both required manual orchestrator recovery. Root cause: the **cycle-base prompt template** (`_components/lazy-batch-prompts/cycle-base-prompt.md`) — the script-assembled prompt every cycle subagent receives — pins neither read-before-cite grounding for `commit-policy.md` nor a forbid-branch-creation clause; and there is no mechanical detector for either failure.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-19
**Fixed:** 2026-06-20
**Fix commit:** 2f444bc
**Placement:** docs/bugs/cycle-subagent-fabricates-policy-or-stray-branch
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` `hard-contract` section (items 2 + 3 — the artifact every cycle subagent actually receives); `user/skills/lazy-batch/SKILL.md` cycle-subagent prompt (consumer); `user/skills/_components/lazy-dispatch-template.md` (dispatch envelope); HARD CONSTRAINT 9 (no fabricated features — the sibling fabrication class already hardened)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; root cause not yet proven.
  - Concluded     → root cause identified, affected area + fix scope understood; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

<!-- Both symptoms are log-OBSERVED (not interactively re-confirmed — this is a batch-mode investigation of a harness defect captured in session logs; the logs ARE the primary evidence). -->

1. **[VERIFIED — log-observed]** A subagent hallucinated a non-existent "manual-only" commit policy and skipped a required commit — session `28de16b3` @ `2026-06-08T23:21:25.750Z`: "The commit-policy.md **does not exist** — the sidecar-watchdog subagent hallucinated a 'manual-only' policy and wrongly skipped its commit." Run-end note @ `01:08:29`: "one mcp-test subagent hallucinated a non-existent 'manual-only commit policy' and skipped."
2. **[VERIFIED — log-observed]** A subagent committed a halt sentinel to a self-invented stray branch off the work branch — session `8ae22371` @ `~2026-06-10 00:13`: "The audit subagent deviated — it created a stray `audit/...` branch and committed NEEDS_INPUT.md there instead of on the work branch (main)"; recovery: "main now carries NEEDS_INPUT.md (6d6b4f6c); stray branch deleted local+remote."

## Reproduction Steps

The failure is non-deterministic (an LLM grounding/discipline lapse), so the repro is a *latency* demonstration — the prompt permits the failure rather than guaranteeing it:

1. Dispatch any cycle subagent in a repo that has **no** `.claude/skill-config/commit-policy.md` (e.g. AlgoBooth — its `skill-config/` contains `quality-gates.md`, `cycle-prompt-addenda.md`, etc. but no `commit-policy.md`).
2. The `hard-contract` section the subagent receives reads, item 3: *"AFTER THE SKILL RETURNS — if .claude/skill-config/commit-policy.md exists, follow it; else commit per the standard pattern and push."* Nothing requires the subagent to actually `Read` the file (or confirm its absence) before asserting its contents.
3. A subagent that "remembers" or infers a policy can cite a `manual-only` rule it never read and skip its commit. (Symptom 1.)
4. Separately, item 2 forbids the subagent from STARTING on a non-work branch (`If git rev-parse --abbrev-ref HEAD is not {work_branch}, STOP`) but does NOT forbid the subagent from itself `git checkout -b`-ing a new branch mid-cycle and committing there. (Symptom 2.)

**Expected:** A cycle subagent NEVER asserts a config policy it did not read; NEVER skips a required commit on the basis of an unread/absent policy; NEVER creates or switches to any branch other than the named work branch; the orchestrator can detect either deviation mechanically rather than discovering it during manual recovery.
**Actual:** Both occurred and both required manual orchestrator recovery (one uncommitted-work recovery; one stray-branch deletion + sentinel re-commit onto `main`).
**Consistency:** Intermittent (LLM discipline lapse under a permissive prompt), each observed once in a 19-session window.

## Evidence Collected

### Source Code

The cycle subagent does **not** receive its instructions from `lazy-batch/SKILL.md` prose directly. The prompt is **script-assembled**: `lazy_core.emit_cycle_prompt` (`user/scripts/lazy_core.py`, ~line 5286) parses the `@section` grammar in `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`, selects sections by `(pipeline, mode, sub_skill)`, binds 14 tokens, residue-checks (`_PROMPT_RESIDUE_RE = \{[a-z0-9_]+\}` — any unbound `{token}` refuses the emit), and returns `cycle_prompt`. The orchestrator copies it VERBATIM (`lazy-dispatch-template.md` forbids hand-appending). **So the fix surface is the section file, not the SKILL.md prose.** Both defects live in the `hard-contract` section (cycle-base-prompt.md lines 348–373, the `modes=workstation` variant; lines 375–403 the `modes=cloud` variant — both carry the same two items):

- **Item 3 (lines 360–362, workstation; 388–392, cloud) — the fabricated-policy seam.** "*if .claude/skill-config/commit-policy.md exists, follow it; else commit per the standard pattern*" reads as a conditional the subagent may resolve from belief. There is no *read-before-cite* obligation ("you MUST `Read` the file — and observe it on disk — before asserting any rule from it; never assert its contents from memory; an absent file is NOT a policy") and no positive default ("absent the file, the standing rule is: commit + push — never skip").
- **Item 2 (lines 357–359, workstation; 384–386, cloud) — the stray-branch seam.** "*Work branch: {work_branch}. Every commit/push goes to {work_branch} only; never create a branch, never --force. If `git rev-parse --abbrev-ref HEAD` is not {work_branch}, STOP and report.*" The `never create a branch` clause IS present in prose, but the only mechanical check is the **entry-time** branch assertion (am I already on the wrong branch at dispatch?). It does not re-assert the branch immediately BEFORE each commit/push, where a mid-cycle `git checkout -b` would be caught. The recovery note confirms the subagent created `audit/...` AFTER passing the entry check.

`commit-policy.md` existence audit (glob `**/commit-policy.md`): present ONLY in `repos/cognito-forms/.claude/skill-config/commit-policy.md` and this repo's own `.claude/skill-config/commit-policy.md`. **Absent in AlgoBooth** (`repos/algobooth/.claude/skill-config/` — confirmed: no `commit-policy.md`), which is exactly where both incidents occurred. So the file is sometimes-present, sometimes-absent — the prompt's `if … exists` branch is real, and the absent branch is the one that was fabricated over.

### Runtime Evidence

- session `28de16b3` @ `2026-06-08T23:21:25.750Z`: "The commit-policy.md **does not exist** — the sidecar-watchdog subagent hallucinated a 'manual-only' policy and wrongly skipped its commit." — cited a config file it never read; used the fabricated policy to skip a required commit, leaving work uncommitted.
- session `28de16b3` run-end @ `01:08:29`: "one mcp-test subagent hallucinated a non-existent 'manual-only commit policy' and skipped." — same fabrication restated at run-end summary level.
- session `8ae22371` @ `~2026-06-10 00:13`: "The audit subagent deviated — it created a stray `audit/...` branch and committed NEEDS_INPUT.md there instead of on the work branch (main)" + recovery "main now carries NEEDS_INPUT.md (6d6b4f6c); stray branch deleted local+remote." — the halt sentinel landed where the resume path could not see it; manual recovery required.

### Git History

No recent commit caused this — the permissive prompt phrasing predates the audit window. The investigation is forward-looking (hardening the template), not a regression bisect.

### Related Documentation

- `user/skills/_components/lazy-dispatch-template.md` — establishes that the cycle prompt is script-assembled and copied VERBATIM (never hand-edited), so a prompt-grounding fix MUST go in the section template, not the dispatch envelope or SKILL.md prose.
- `user/scripts/CLAUDE.md` — confirms the file-driven contract: a mis-placed sentinel (stray branch) is "invisible to the machine's view of the world." A NEEDS_INPUT.md on a non-work branch is exactly such an invisible sentinel.
- `lazy-batch/SKILL.md` HARD CONSTRAINT 9 — the **sibling** fabrication class (a hallucinated *feature slug* causing a subagent to fabricate an entire feature) is already hardened with a dedicated constraint + a state-script dangling-entry skip. This bug is the same *fabricate-ungrounded-artifact* failure class applied to (a) a config policy and (b) a git branch — both currently UN-hardened.
- `block-noncanonical-blocker-write.sh` hook (project CLAUDE.md) — precedent for a **write-time** mechanical backstop against an invisible-sentinel failure (a mis-named `BLOCKED*.md`). A git-branch-aware analog (deny a sentinel Write while HEAD is not the work branch) is the natural mechanical detector for symptom 2.

## Theories

### Theory 1: Permissive `if-exists` policy phrasing invites fabrication (fabricated commit policy)
- **Hypothesis:** Item 3's "*if commit-policy.md exists, follow it; else commit*" lets the subagent resolve the conditional from belief instead of from disk. With no read-before-cite obligation and no positive "absent → commit, never skip" default, a subagent can assert a `manual-only` policy it never read (the file does not even exist in AlgoBooth) and skip its commit.
- **Supporting evidence:** Both run-log entries name a "manual-only commit policy" that "does not exist"; AlgoBooth `skill-config/` confirmed to lack `commit-policy.md`; the prompt phrasing is a bare conditional with no grounding clause.
- **Contradicting evidence:** None. The phrasing is the proximate cause.
- **Status:** Confirmed.

### Theory 2: Entry-only branch check leaves a mid-cycle branch-creation hole (stray branch)
- **Hypothesis:** Item 2's mechanical check (`git rev-parse --abbrev-ref HEAD` != work branch → STOP) fires only at cycle entry. A subagent that `git checkout -b audit/...` AFTER the entry check passes is not re-checked before it commits, so a halt sentinel can land on a stray branch the resume path never inspects.
- **Supporting evidence:** Recovery note explicitly says the subagent "created a stray `audit/...` branch and committed NEEDS_INPUT.md there"; the prose `never create a branch` clause was present but unenforced past entry.
- **Contradicting evidence:** The prose ban exists — so this is an enforcement/timing gap, not a missing instruction. (Strengthens, not weakens, the fix: prose alone proved insufficient; a pre-commit re-assertion + a write-time hook backstop is warranted.)
- **Status:** Confirmed.

### Theory 3: No mechanical detector for either deviation
- **Hypothesis:** Both failures were caught only by the operator during manual recovery. There is no script/hook that flags a skipped-commit-citing-an-unread-policy or a sentinel-on-a-non-work-branch, so the pipeline loops/strands until a human notices.
- **Supporting evidence:** Both incidents required manual orchestrator recovery; `block-noncanonical-blocker-write.sh` proves a write-time backstop is the established pattern for invisible-sentinel classes but no branch-aware analog exists; the `--cycle-end` friction detector (process-friction ledger) tracks torn brackets / unexpected commits but not branch identity at commit time.
- **Status:** Confirmed (the gap is real); the *mechanical detector* design is the largest fix lever and is carried into Affected Area / fix scope below.

## Proven Findings

1. **The fix surface is `cycle-base-prompt.md`'s `hard-contract` section, NOT `lazy-batch/SKILL.md` prose.** The cycle prompt is script-assembled by `lazy_core.emit_cycle_prompt` and copied verbatim; editing SKILL.md prose would not change what the subagent receives. Both prose hardening edits land in the `hard-contract` section's items 2 and 3, in BOTH the `modes=workstation` and `modes=cloud` variants (they are separate section blocks carrying the same two items — keep them in lockstep).
2. **Fabricated commit policy (symptom 1) is a read-before-cite + positive-default gap in item 3.** Fix: require the subagent to actually `Read` `commit-policy.md` (and observe its presence) before asserting ANY rule from it; never assert its contents from memory; an ABSENT file is not a policy; and state the positive standing default explicitly — *absent the file, commit + push; never skip a required commit on the basis of an unread or absent policy.*
3. **Stray branch (symptom 2) is an enforcement-timing gap in item 2 plus a missing write-time backstop.** Prose fix: re-assert `git rev-parse --abbrev-ref HEAD == {work_branch}` immediately BEFORE every commit/push (not only at entry), and forbid `git checkout -b` / `git switch -c` / `git branch` explicitly. Mechanical backstop: a PreToolUse(Write,Edit) hook — modeled on `block-noncanonical-blocker-write.sh` — that DENIES writing a pipeline sentinel (`NEEDS_INPUT.md` / `BLOCKED.md` / receipts) while HEAD is not the run marker's work branch (fail-OPEN; the deny names the work branch). This is the cheapest deterministic detector for the invisible-sentinel-on-stray-branch class.
4. **All open questions resolve from evidence with no product-class divergence (D7).** None of the three stub Open Questions admit options that diverge in user-visible behavior — they are all "harden the harness more vs. less," i.e. scope-class. The completeness-first path is to do all three legs (read-before-cite prose, branch-guard prose, write-time mechanical hook), so NO NEEDS_INPUT.md is written; see the ⚖ disclosure in the cycle report.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Cycle prompt template — fabricated-policy seam | `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — `hard-contract` section, item 3 (workstation lines ~360–362 + cloud lines ~388–392) | Add read-before-cite obligation for `commit-policy.md` + a positive "absent → commit, never skip" default. Keep both mode variants in lockstep. Residue-safe (no new `{token}`). |
| Cycle prompt template — stray-branch seam | `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — `hard-contract` section, item 2 (workstation lines ~357–359 + cloud lines ~384–386) | Re-assert the work-branch check immediately before each commit/push; forbid `checkout -b` / `switch -c` / `branch` by name. Both mode variants. |
| Mechanical detector (new write-time hook) | new `user/hooks/block-sentinel-write-on-stray-branch.sh` (modeled on `user/hooks/block-noncanonical-blocker-write.sh`); registration in `user/settings.json` PreToolUse(Write,Edit) | Deny writing a pipeline sentinel while HEAD != the run marker's work branch; fail-OPEN; deny message names the work branch. Closes the invisible-sentinel-on-stray-branch class deterministically. |
| Projection / lint verification | `user/scripts/project-skills.py` (re-run after section edit); `lazy-state.py --test` (emit_cycle_prompt residue/assembly is exercised by the smoke harness) | Confirm the section still assembles + residue-checks clean after the prose edits, in every (pipeline, mode) selection. |
| Docs | `CLAUDE.md` Hooks table (add the new hook row) | Keep the harness hooks table authoritative. |

## Open Questions

<!-- All three stub Open Questions are RESOLVED from evidence (see Proven Findings #2–#4); none remain product-class. Recorded here for traceability. -->

- ~~Should the cycle-subagent prompt require read-before-cite grounding?~~ **Resolved: YES** (Proven Finding #2) — required for `commit-policy.md` (and the same discipline generalizes to any cited config).
- ~~Should the prompt pin the work branch and forbid other branches?~~ **Resolved: YES** (Proven Finding #3) — prose already bans branch creation but only checks at entry; add a pre-commit re-assertion + explicit `checkout -b`/`switch -c`/`branch` ban.
- ~~How should these be detected mechanically rather than after the fact?~~ **Resolved** (Proven Finding #3) — a PreToolUse(Write,Edit) hook denies a sentinel Write while HEAD is off the work branch (modeled on `block-noncanonical-blocker-write.sh`). The fabricated-policy skip is harder to detect mechanically (a non-event — a commit that did NOT happen); the prose read-before-cite + positive-default is the primary control there, with the existing `--verify-ledger` clean-tree check as the backstop (an uncommitted skip leaves a dirty tree the turn-end verify gate refuses).
