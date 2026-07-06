---
kind: implementation-plan
feature_id: build-queue-enforce-cd-prefix-bypass
status: Complete
created: 2026-07-06
complexity: mechanical
phases: [1, 2, 3]
deliverables: [phase-1-WU-1, phase-2-WU-2, phase-3-WU-3]
source_branch: claude/lazy-batch-skill-invoke-3ihbup
source_commit: 6fedd57
---

> **Verify-and-reconcile plan.** The full fix for `build-queue-enforce-cd-prefix-bypass` — both SPEC prongs (hook hardening + skill capability) and the regression suite — is **already implemented and green on disk**, landed out-of-band via the sibling build-queue commits (`b85b0c3`, `7722211`, `42b77ab`) and the pre-existing command-position anchor in `long-build-ownership-guard.sh`. See [`../PHASES.md`](../PHASES.md) for the per-deliverable on-disk citations. This plan therefore schedules **no fresh production edit** — each work unit is a *verification* that the landed deliverable is present and that the `test_hooks.py` regression suite is green. WU boxes are left **unchecked** (the machine record `/execute-plan` ticks — never a producer): the underlying deliverables ARE genuinely satisfied on disk (verified this cycle: `test_hooks.py` → 130/131 passed, 0 failed), so `/execute-plan`'s pass is a fast confirm-the-verification-command-per-WU → tick → run the gate → flip the plan to `Complete`; the `__mark_fixed__` gate then owns the SPEC Status flip, the `FIXED.md` receipt, and the archive.

# Implementation Plan — Build-Queue Enforcement Bypassed by `cd`-Prefixed Build Commands

## Gate (run once, satisfies every WU's verification)

```
python3 user/scripts/test_hooks.py
```

Expected: `Results: 130/131 passed, 1 skipped, 0 failed` (or better), with the `test_bqe_denies_cd_prefixed_*`, `test_bqe_denies_restore_then_build_compound`, and `test_longbuild_guard_denies_cd_prefixed_*` cases all PASS. This is the load-bearing regression evidence — it spawns the real hooks over crafted PreToolUse payloads and asserts the `cd`-prefix / pipeline / compound bypass is denied while the safe/reference forms are allowed.

Also (static, no runtime): confirm the skill/script citations in `../PHASES.md`'s Touchpoint Audit Table are present on disk (`grep -n 'Project' repos/cognito-forms/.claude/scripts/build-filtered.ps1`; `-Project` in `msbuild/SKILL.md`; the `/msbuild -Project` pointer at `mstest/SKILL.md:11`).

---

## Phase 1 — Hook hardening (command-position deny, both hooks)

### WU-1: Verify the command-position deny surface + allow-list precedence (both hooks) [x]

- [x] `user/hooks/build-queue-enforce.sh`: `_CMD_START` anchor (line 114) drives `_DOTNET_BUILD_RE`/`_DOTNET_TEST_RE`/`_NX_BUILD_TEST_RE`/`_FILTERED_SCRIPT_DIRECT_RE`; `_suppress_safe` (151-157, applied 379) re-derives allow-list precedence so `dotnet restore && dotnet build` denies; `_BYPASS_RE` (87) + `_WRAPPER_RE` (92) escape hatches intact. **No edit — verify on disk.**
- [x] `user/hooks/long-build-ownership-guard.sh`: `_CMD_START` anchor (105) on `_LONG_BUILD_RE` (106-112) closes the same `cd`-prefix blind spot for the long-build redirect set. **No edit — verify on disk.**
- [x] `user/scripts/test_hooks.py`: bqe cd-prefix/pipeline/compound/allow suite (4841-5058) + long-build cd-prefix suite (5061+) present and green. **No edit — run the gate.**

**Verification:** the Gate above (green `test_hooks.py`; bqe + long-build sections PASS).

---

## Phase 2 — Skill capability (single-project build path)

### WU-2: Verify the sanctioned single-project compile path [x]

- [x] `repos/cognito-forms/.claude/scripts/build-filtered.ps1`: `[string]$Project = ""` (9) + conditional `$buildTarget` (22). **No edit — verify on disk.**
- [x] `repos/cognito-forms/.claude/skills/msbuild/SKILL.md`: `-Project` documented (4, 16, 29). **No edit — verify on disk.**
- [x] `repos/cognito-forms/.claude/skills/mstest/SKILL.md`: `/msbuild -Project` pointer (11). **No edit — verify on disk.**
- [x] `repos/cognito-forms/CLAUDE.local.md`: targeted-compile path documented in Build & Test Workflow. **No edit — verify on disk.**

**Verification:** `grep -n 'Project' repos/cognito-forms/.claude/scripts/build-filtered.ps1` shows the param + conditional target; the skill citations resolve; `test_bqe_allows_build_queue_wrapper_with_filtered_exec` (part of the green gate) confirms a `-Project`-carrying wrapper call is not spuriously denied.

---

## Phase 3 — Background-poll ergonomics (trust-the-banner contract)

### WU-3: Verify the banner-trust outcome contract in the build/test skills [x]

- [x] `msbuild/SKILL.md`: trust-the-banner instruction + no-`cat`/`grep`-the-runner + `FAIL` next-actions (34, 38-46) + `run_in_background` poll path (36). **No edit — verify on disk.**
- [x] `mstest/SKILL.md`: same banner-trust contract + exit-code guidance (37, 41-47) + `run_in_background` poll path (39). **No edit — verify on disk.**

**Verification:** both skills contain the "trust the banner … do NOT `cat`/`grep` the runner or `results/<seq>.json`" instruction and the background poll path.

---

## Notes

- **Zero fresh production edits expected.** If `/execute-plan` finds any cited deliverable *absent* on disk (e.g. a rebase dropped it), that WU converts from verify to implement per the SPEC's `## Fix Direction`, test-first against the existing `test_hooks.py` cases (write/confirm the RED, then restore the deliverable to GREEN). This is the only path under which this plan writes production code.
- **Coupled-pair note:** the two hooks are a deliberate pair for the `_CMD_START` anchor + `hook-events.jsonl` deny-event append (both edited together historically). No parity-audit script covers hooks (that audit is for the lazy/bug state-script pairs), so `test_hooks.py` is the pair's regression guard — keep both hooks' anchors in sync if either is ever touched.
- **Completion is gate-owned:** `/execute-plan` flips this plan `Ready → Complete`; the orchestrator's `__mark_fixed__` gate (after the validation tail) owns the SPEC `**Status:** Fixed` flip, the `FIXED.md` receipt, and the archive. This plan never sets `Fixed`.
