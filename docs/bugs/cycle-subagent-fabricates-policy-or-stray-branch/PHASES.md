# Implementation Phases — Cycle subagents fabricate ungrounded artifacts (policy / stray branch)

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure harness change (prompt-template prose, a bash PreToolUse hook, Python state-script marker field + CLI query, settings/doc wiring). No AlgoBooth app surface, store, audio path, or UI state is touched; verification is via `project-skills.py` residue-check + `lazy_core`/hook pytest, not the Tauri+MCP dev runtime.

## Validated Assumptions

These are the load-bearing assumptions this plan rests on. All are **code-provable** from the touchpoint audit (no runtime-coupled assumption — this is harness plumbing, not running-app behavior):

- **The cycle prompt is script-assembled, not SKILL.md prose.** `lazy_core.emit_cycle_prompt` (cycle-base-prompt.md `@section` grammar, selected by `(pipeline, mode, sub_skill)`, residue-checked by `_PROMPT_RESIDUE_RE = \{[a-z0-9_]+\}`) is the surface. Confirmed: the two `hard-contract` blocks are at cycle-base-prompt.md lines **348–373 (modes=workstation)** and **375–403 (modes=cloud)**; items 2 & 3 are at **357–362 (ws)** / **384–392 (cloud)**. (SPEC line numbers ~357–362/384–392 verified against disk.)
- **The run marker does NOT currently store a work-branch.** `write_run_marker` (`lazy_core.py:7645`) writes `pipeline/cloud/repo_root/session_id/started_at/max_cycles/nonce_seed/forward_cycles/meta_cycles/per_feature_forward_cycles/last_advance_consume_count/attended` — **no `work_branch` field**. `_emit_work_branch(repo_root)` (`lazy_core.py:5101`) already resolves the branch via `git -C <root> rev-parse --abbrev-ref HEAD`. So the new write-time hook has no reference branch to compare HEAD against until one is captured at run-start. **This is the one scope expansion beyond the SPEC's literal Affected Area** (the SPEC assumed "the run marker's work branch" exists) — it is mechanical/scope-class (D7), taken in-plan, see Phase 2.
- **`--marker-present` is the exact template for a read-only marker query.** `lazy-state.py:7217` — `set_active_repo_root(args.repo_root)` runs first (repo-keyed state dir), then `read_run_marker(session_id=...)`, exit 0/1. A new `--marker-work-branch` mirrors this and additionally prints the stored branch.
- **`block-noncanonical-blocker-write.sh` is the exact model for the new hook.** Verified structure: python3→python resolution, inline `-c` python body (NOT heredoc — heredoc would swallow stdin), `_deny`/`_allow` helpers emitting `permissionDecision: deny` JSON, `try/except Exception: sys.exit(0)` fail-OPEN, terminal `exit 0`. It is registered in `settings.json` under a `"matcher": "Write|Edit"` PreToolUse block (lines 104–112) — the new hook joins that same block as a second command.

## SPEC-example capability audit

The SPEC carries no runtime code examples consuming app/engine API surfaces — its "examples" are git commands (`git rev-parse --abbrev-ref HEAD`, `git checkout -b`) and shell-hook shapes, all confirmed-available primitives. No negative-evidence grep needed; nothing the plan consumes is an explicitly-rejected capability.

---

### Phase 1: Prompt prose hardening — read-before-cite + branch re-assertion (both mode variants)

**Scope:** Close the two prose seams in the `hard-contract` section of `cycle-base-prompt.md`, in BOTH the `modes=workstation` and `modes=cloud` variants, kept in lockstep. This is the primary control for symptom 1 (fabricated commit policy) and a reinforcing control for symptom 2 (stray branch). Pure section-template prose; no `{token}` added (residue-safe).

**Deliverables:**
- [x] Item 3 (workstation ~360–362 + cloud ~388–392): add a **read-before-cite obligation** — the subagent MUST `Read` `.claude/skill-config/commit-policy.md` and observe it on disk before asserting ANY rule from it; never assert its contents from memory; an ABSENT file is NOT a policy.
- [x] Item 3 (both variants): state the **positive standing default explicitly** — absent the file, the standing rule is commit + push; never skip a required commit on the basis of an unread or absent policy.
- [x] Item 2 (workstation ~357–359 + cloud ~384–386): add a **pre-commit branch re-assertion** — re-confirm `git rev-parse --abbrev-ref HEAD == {work_branch}` immediately BEFORE every commit/push, not only at cycle entry.
- [x] Item 2 (both variants): **forbid branch creation by name** — explicitly ban `git checkout -b`, `git switch -c`, and `git branch <new>` mid-cycle.
- [x] Both `hard-contract` variants edited in lockstep (workstation + cloud carry the identical two changes; only surrounding cloud-push prose differs).
- [x] Re-run `python ~/.claude/scripts/project-skills.py` and confirm the section still assembles + residue-checks clean (no unbound `{token}`) for every `(pipeline, mode)` selection.

**Implementation Notes (2026-06-20, P1 / WU-1):**
- Edited both `hard-contract` `@section` blocks of `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` in lockstep. Item 2 (both variants) now adds an explicit ban on `git checkout -b` / `git switch -c` / `git branch <new>` plus a pre-commit HEAD==`{work_branch}` re-assertion before every commit/push. Item 3 (workstation) and item 3's commit-policy clause (cloud — folded into the COMMIT+PUSH EACH BATCH item) now require `Read`-ing `.claude/skill-config/commit-policy.md` and observing it on disk before citing it, declare an absent file is not a policy, and state the positive default (commit+push; never skip on an unread/absent policy).
- Reused only the existing `{work_branch}` token; no new `{token}` introduced (residue-safe per MANDATORY RULE #13).
- Verified: `lazy-state.py --test` (emit_cycle_prompt smoke — all `(pipeline,mode,sub_skill)` selections assembled, no residue refusal) and `project-skills.py` both exit 0.

**Minimum Verifiable Behavior:** `python ~/.claude/scripts/project-skills.py` exits 0 and the projected `cycle-base-prompt.md` (and any skill that injects it) shows the new item-2/item-3 prose with `{work_branch}` resolved and zero residual `{token}` markers; `python ~/.claude/scripts/lazy-state.py --test` (emit_cycle_prompt smoke harness) still assembles every selection without a residue refusal.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — items 2 & 3 of both `hard-contract` `@section` blocks (refactor; reuse the existing `{work_branch}` token, add no new token).

**Testing Strategy:**
Verified in isolation by the projection residue-check (`project-skills.py`) and the `emit_cycle_prompt` smoke harness — both are deterministic, run offline, and exercise the `(pipeline, mode, sub_skill)` selection + residue refusal that the prose edit must not break. No app runtime needed.

**Integration Notes for Next Phase:**
- The prose now NAMES the work branch via `{work_branch}` and forbids branch creation. Phase 2/3 add the *mechanical* enforcement the prose alone proved insufficient to guarantee (symptom 2 recurred despite a prose `never create a branch` clause already present at entry-check time).
- Do NOT edit `lazy-batch/SKILL.md` prose for these items — the cycle prompt is script-assembled from this section and copied verbatim; SKILL.md prose edits would not reach the subagent.

---

### Phase 2: Capture the work-branch into the run marker + expose it via a read-only CLI query

**Scope:** Give the write-time hook (Phase 3) a reference branch to compare HEAD against. Capture `work_branch` into the run marker at run-start (the branch the orchestrator is on when the run begins), and expose it through a new read-only `--marker-work-branch` query mirroring `--marker-present`, in BOTH state scripts. This is the scope-class (D7) expansion disclosed in Validated Assumptions — mechanical plumbing with no user-visible behavior change.

**Deliverables:**
- [x] `write_run_marker` (`lazy_core.py:7645`) writes a new `work_branch` field, resolved via the existing `_emit_work_branch(repo_root)` (`lazy_core.py:5101`). Legacy markers lacking the field read as `None` (back-compat, same pattern as `attended`/`per_feature_forward_cycles`).
- [x] A `lazy_core` read helper returns the marker's `work_branch` (or `None`) from `read_run_marker()` output — the CLI and hook share it; no re-derivation of branch identity outside this helper.
- [x] `lazy-state.py` gains `--marker-work-branch`: `set_active_repo_root(args.repo_root)` first (repo-keyed), then read the marker; print the stored `work_branch` to stdout and exit 0 if a live marker with a branch is present, exit 1 if absent/stale/no-branch. Read-only (no state-dir creation), mirroring the `--marker-present` handler (`lazy-state.py:7217`).
- [x] `bug-state.py` gains the identical `--marker-work-branch` query (parity — both pipelines write sentinels and both can strand on a stray branch).
- [x] Tests in `test_lazy_core.py`: marker now carries `work_branch`; `--marker-work-branch` prints it when present and exits 1 when absent; legacy marker (no field) degrades to exit 1 / `None`, not a crash.

**Implementation Notes (2026-06-20, P2 / WU-2 + WU-3):**
- `lazy_core.write_run_marker` now stamps `"work_branch": _emit_work_branch(Path(repo_root))` into the marker dict (a non-git root yields the documented fallback string, never raises). New read helper `lazy_core.marker_work_branch(now, session_id)` returns the marker's `work_branch` or `None` (legacy/absent/empty/stale → `None`); branch identity is owned in this ONE helper.
- `lazy-state.py` gained `--marker-work-branch` (handler right after `--marker-present`): prints the branch + exit 0 when present, exit 1 otherwise; read-only (routes through `read_run_marker → claude_state_dir(create=False)` — an absent probe never creates the state dir; asserted by the CLI test). `bug-state.py` gained the identical `--marker-work-branch` PLUS a `--session-id` flag it previously lacked (its handler honors it; lazy-state.py already had `--session-id`).
- TDD: 6 failing tests written FIRST (RED confirmed: field/helper absent, argparse rejected the flag), then GREEN. `test_lazy_core.py` 693/693; `lazy-state.py --test` + `bug-state.py --test` smoke harnesses pass; `lazy_parity_audit.py --repo-root .` exit 0 (no divergence).
- Marker schema changed → re-verified the byte-pinned smoke baselines via the in-suite `_normalize_smoke_output` comparison test (part of the 693). The new `work_branch` field is in `write_run_marker`'s dict, not surfaced in `--test` probe output, so baselines were unaffected.

**Minimum Verifiable Behavior:** `python ~/.claude/scripts/lazy-state.py --repo-root <root> --marker-work-branch` prints the run-start branch (e.g. `main`) and exits 0 under a live marker; exits 1 with no marker; never creates the state dir on an absent probe — asserted by the new `test_lazy_core.py` cases (run via the existing `python user/scripts/test_lazy_core.py` harness).

**Prerequisites:**
- Phase 1: not a hard code dependency, but land prose first so the mechanical layer reinforces a prompt that already forbids the action.

**Files likely modified:**
- `user/scripts/lazy_core.py` — add `work_branch` to the `write_run_marker` marker dict (capture via `_emit_work_branch`); add a read helper.
- `user/scripts/lazy-state.py` — `--marker-work-branch` arg + handler (mirror `--marker-present`).
- `user/scripts/bug-state.py` — same `--marker-work-branch` arg + handler (parity).
- `user/scripts/test_lazy_core.py` — marker-field + CLI-query tests.

**Testing Strategy:**
Deterministic Python unit tests under the repo's existing `test_lazy_core.py` harness — hermetic (injectable `now`, `LAZY_STATE_DIR` override), no git network, no app runtime. Cover: field present after `write_run_marker`; CLI prints/exits correctly present vs. absent; legacy-marker back-compat; read-only (no dir creation) on absent probe.

**Integration Notes for Next Phase:**
- Phase 3's hook calls `lazy-state.py --marker-work-branch --repo-root <cwd>` (and `bug-state.py` is the bug-pipeline twin) to get the reference branch — bash NEVER re-derives branch identity; Python owns it (same contract as `--marker-present`).
- A `None`/exit-1 result (no marker, or legacy marker) MUST make the hook fail-OPEN (allow) — absent a known work branch there is nothing to enforce against; do not guess.

---

### Phase 3: Write-time mechanical backstop — `block-sentinel-write-on-stray-branch.sh` + registration

**Scope:** The deterministic detector for symptom 2: a PreToolUse(Write,Edit) hook that DENIES writing a pipeline sentinel while `HEAD != the run marker's work_branch`, closing the invisible-sentinel-on-stray-branch class. Modeled verbatim on `block-noncanonical-blocker-write.sh`. Fail-OPEN; the deny message names the correct work branch.

**Deliverables:**
- [x] New `user/hooks/block-sentinel-write-on-stray-branch.sh`: on a Write/Edit whose resolved target basename is a pipeline sentinel (`NEEDS_INPUT.md`, `BLOCKED.md`, `FIXED.md`, `COMPLETED.md`, `VALIDATED.md` — the canonical receipt/halt set), query `lazy-state.py --marker-work-branch` (and `bug-state.py` twin) for the reference branch; resolve `git rev-parse --abbrev-ref HEAD`; DENY if they differ.
- [x] The deny message NAMES the work branch and instructs: switch back to `<work_branch>` and write the sentinel there (a deny without the corrective branch just loops the retry — mirrors the noncanonical-blocker deny's corrective-name discipline).
- [x] **Fail-OPEN on every error path:** no python / no marker / exit-1 (no known work branch) / non-sentinel target / branch-query failure / malformed payload → ALLOW (emit nothing, exit 0). Terminal `exit 0` (a PreToolUse non-zero is a hard error; deny is JSON only).
- [x] Python resolution python3→python (WSL vs. Windows git-bash); inline `-c` body (NOT heredoc — stdin-binding hazard); same skeleton as the model hook.
- [x] Register in `user/settings.json` as a second command inside the EXISTING `"matcher": "Write|Edit"` PreToolUse block (lines 104–112), alongside `block-noncanonical-blocker-write.sh` (timeout 5).
- [x] Tests in `test_hooks.py`: deny when HEAD is a stray branch under a live marker; allow when HEAD == work branch; fail-OPEN when no marker / no python / non-sentinel target / malformed JSON; deny message contains the work-branch name.

**Implementation Notes (2026-06-20, P3 / WU-4 + WU-5):**
- Created `user/hooks/block-sentinel-write-on-stray-branch.sh` modeled verbatim on `block-noncanonical-blocker-write.sh` (python3→python resolution; inline `-c` body NOT heredoc; `_allow`/`_deny` JSON helpers; `try/except Exception: sys.exit(0)` fail-OPEN; terminal `exit 0`). The bash wrapper resolves `STATE_PY="$SCRIPT_DIR/../scripts/lazy-state.py"` via builtins (no `dirname`) and threads it to the inline python body via env `_BSW_STATE_PY` (NOT argv — keeps the PreToolUse payload as python's sole stdin). The python body reads the payload's `cwd`, shells `lazy-state.py --marker-work-branch --repo-root <cwd>` for the reference branch and `git -C <cwd> rev-parse --abbrev-ref HEAD` for HEAD, and denies on mismatch for a sentinel basename. Deny names BOTH the stray branch and the corrective work branch.
- Registered as the SECOND command in the existing `"matcher": "Write|Edit"` PreToolUse block in `user/settings.json` (alongside `block-noncanonical-blocker-write.sh`, timeout 5). settings.json remains valid JSON.
- TDD: 8 hook tests in `test_hooks.py` (file-exists, deny-on-stray-branch with reason-naming assertion, allow-on-work-branch, fail-OPEN-no-marker, allow-non-sentinel, fail-OPEN-malformed, allow-non-Write-tool, registered-in-settings). The registration test was the RED gate before WU-5 landed; all 93 hook tests now pass.
- Hook tests use a real temp git repo (`git init` + branch checkout) for HEAD control and a forced-`work_branch` marker in `LAZY_STATE_DIR`; the subprocess `--marker-work-branch` query and the in-process marker write resolve the SAME dir because `LAZY_STATE_DIR` set → `claude_state_dir()` returns it exactly (no repo-keying under the test override).

**Minimum Verifiable Behavior:** Under a live marker with `work_branch=main`, a Write to `.../NEEDS_INPUT.md` while `HEAD=audit/foo` returns a `permissionDecision: deny` whose reason names `main`; the same Write while `HEAD=main` emits nothing (allow); with no marker the Write is always allowed — all asserted by the new `test_hooks.py` cases (run via the repo's hook test harness, which already pipes synthetic PreToolUse JSON through the hooks).

**Prerequisites:**
- Phase 2: the `--marker-work-branch` query and the marker `work_branch` field must exist — the hook is fail-OPEN without them but only *enforces* once they ship.

**Files likely modified:**
- `user/hooks/block-sentinel-write-on-stray-branch.sh` — net-new (create), modeled on `block-noncanonical-blocker-write.sh`.
- `user/settings.json` — add the hook command to the existing `Write|Edit` PreToolUse block.
- `user/scripts/test_hooks.py` — hook behavior tests (deny/allow/fail-open).

**Testing Strategy:**
The repo's existing `test_hooks.py` harness pipes synthetic PreToolUse JSON through each hook script and asserts the emitted decision — deterministic, offline, git-state controlled via temp repos. Cover the deny path (stray branch + live marker + sentinel target), the three allow paths (work branch / no marker / non-sentinel), and fail-OPEN on malformed input and missing python. No app runtime.

**Integration Notes for Next Phase:**
- The hook is the WRITE-TIME complement to Phase 1's prose ban — exactly the two-layer pattern `block-noncanonical-blocker-write.sh` (write-time) + `lazy_core.detect_noncanonical_blocker` (read-time) already establish for the mis-named-blocker class. Keep BOTH layers; neither alone is load-bearing-complete.
- The fabricated-commit-policy skip (symptom 1) has NO mechanical write-time detector (it is a non-event — a commit that did not happen). Its controls are Phase 1's read-before-cite + positive-default prose plus the EXISTING `--verify-ledger` clean-tree turn-end gate (an uncommitted skip leaves a dirty tree the verify gate refuses). Phase 4 documents this division.

---

### Phase 4: Documentation + projection verification

**Scope:** Keep the harness's authoritative surfaces in sync with the new hook and marker field, and re-verify the end-to-end projection after all prose/script edits. Docs-only + verification; no new behavior.

**Deliverables:**
- [ ] Add a `block-sentinel-write-on-stray-branch.sh` row to the `CLAUDE.md` Hooks table (sibling of the `block-noncanonical-blocker-write.sh` row at line ~187): PreToolUse(Write,Edit); denies a pipeline-sentinel Write while HEAD != the run marker's `work_branch`; fail-OPEN; deny names the work branch; write-time complement to the prose ban.
- [ ] Note the new marker `work_branch` field + `--marker-work-branch` query in `user/scripts/CLAUDE.md` (alongside the `--marker-present` "Hooks gate via" note), so the marker schema doc stays authoritative.
- [ ] Final `python ~/.claude/scripts/project-skills.py` run — confirm the fully-resolved `cycle-base-prompt.md` projection (both `_default/` and any per-repo projection) reflects the Phase-1 prose with zero residue.
- [ ] Confirm the full hook + state-script test suites pass (`test_hooks.py`, `test_lazy_core.py`).

**Minimum Verifiable Behavior:** `python ~/.claude/scripts/project-skills.py` exits 0 with the hardened prose in the projected output; `python user/scripts/test_hooks.py` and `python user/scripts/test_lazy_core.py` both report all-pass; `CLAUDE.md` Hooks table contains the new row.

**Prerequisites:**
- Phases 1–3: docs describe the shipped prose, hook, and marker field.

**Files likely modified:**
- `CLAUDE.md` — Hooks table row.
- `user/scripts/CLAUDE.md` — marker `work_branch` / `--marker-work-branch` note.

**Testing Strategy:**
Verification-only phase. The projection script and the two pytest suites are the gate; all run offline. No app runtime.

**Integration Notes for Next Phase:**
- Final phase. Once the projection is residue-clean and both suites pass, implementation is complete; the `__mark_fixed__` gate (orchestrator-owned, after the validation tail) flips status — never this plan.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md top-level `**Status:**` and writes `FIXED.md` once the validation tail passes. This plan never flips top-level status or writes the receipt.
