# Implementation Phases — Lazy Cycle Containment

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure claude-config harness mechanics (Python state-script + bash hook + skill prose + projected components). No Tauri app, no MCP-reachable surface; validation is `pytest` on `lazy_core.py`, a bash hook-test harness, `project-skills.py` projection lint, and docs-consistency greps. This is the `standalone — no app integration` untestable class per `docs/features/mcp-testing/SPEC.md`.

## Cross-feature Integration Notes

No hard deps on Complete upstream *features* (`**Depends on:** (none)`). This feature extends already-shipped machinery that lives in `docs/specs/` (not the feature queue), so there is no upstream PHASES.md to integrate against:

- **`turn-routing-enforcement` (Complete spec, not a queued feature):** the run-marker pattern (`~/.claude/state/lazy-run-*.json`), the PreToolUse dispatch-guard / route-inject hooks, and the prompt registry. This feature **reuses that pattern at dispatch-window scope** — the cycle-subagent marker (C1) is the run-marker's sibling; the containment hook (C2) is the dispatch-guard's sibling; the fail-OPEN-on-hook-error breadcrumb mirrors `lazy-route-inject.sh`.
- **`lazy-validation-readiness` Phase 7 (Complete spec):** orchestrator-side stop-authorization on `--run-end`. This feature adds the **subagent-side** analog that left open.

These are live code on disk now; nothing is blocked on a queued upstream. Phase plans below cite the existing patterns they mirror.

---

### Phase 1: Self-edit reload discipline (C8)

**Phase kind:** design

**Scope:** Add the self-edit detection predicate to `lazy_core.py` (surfaced as `self_edit_mode` on the probe JSON) and the orchestrator governing-file reload discipline + new-hook-registration restart surfacing in the orchestrator skill prose. Lands FIRST (per the SPEC phase-ordering rationale) so that this very spec's later governing-prose edits — Phase 5 (`lazy-batch/SKILL.md`) and Phase 9 (`orchestrator-voice.md`) — take effect on the running orchestrator when this spec is built in-repo.

**Deliverables:**
- [x] `lazy_core.py` self-edit predicate: returns true iff `~/.claude/skills`, `~/.claude/scripts`, AND `~/.claude/hooks` all resolve (after symlink resolution) under the run's `git rev-parse --show-toplevel`. Semantically-correct (robust to the repo cloned elsewhere); NOT a cwd-basename match.
- [x] `--probe` / `emit_cycle_prompt` carry `self_edit_mode: true|false` (and optionally `governing_files_touched` derived from the last commit's `git diff --name-only`).
- [x] Orchestrator governing-file reload discipline (prose in `user/skills/lazy-batch/SKILL.md`, mirrored to bug/cloud twins in Phase 5's coupled-trio work — here author the prose pattern): when `self_edit_mode` is true, after every cycle intersect the cycle's commit with the **governing-file set** (`user/skills/lazy-batch/SKILL.md` + bug/cloud twins, `user/skills/_components/{orchestrator-voice,completeness-policy,lazy-dispatch-template}.md`); re-`Read` any hit via its `~/.claude/...` path before composing the next dispatch. Keep this set in lockstep with the compaction re-read list.
- [x] New-hook-registration surfacing: if a cycle's commit added/removed a hook ENTRY in `settings.json` (not merely edited an already-wired script body), the orchestrator emits `⚠ settings.json hook wiring changed — restart the session to (de)register; the running session still uses the old wiring` (T6) — it does NOT claim the change is live.
- [x] Auto-refresh-boundary documentation (in `lazy_core.py` and/or orchestrator prose): `lazy_core.py`/`lazy-state.py`, `cycle-base-prompt.md`/addenda/`loop-block.md`, hook `.sh` bodies, and downstream skill prose are ALREADY live on the next probe/dispatch — they MUST NOT be flagged for reload (they were never stale).
- [x] Tests: `pytest` on the predicate — symlink fixtures where `~/.claude/{skills,scripts,hooks}` resolve UNDER the git toplevel (true) vs. outside it (false); a normal-repo fixture (false); governing-file-set membership tests (a `lazy-batch/SKILL.md` edit IS in the set; a `lazy_core.py` / `cycle-base-prompt.md` / hook-body edit is NOT).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --probe <repo>` run inside claude-config emits `self_edit_mode: true`; the same probe run in a non-harness repo emits `self_edit_mode: false`. (Runtime-observable proof the predicate is wired end-to-end through the probe surface.)

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] `self_edit_mode` true only in-harness: probe in claude-config → `true`; probe in a normal repo → `false` (matches SPEC Validation Criteria row "self_edit_mode true only in-harness").
- [ ] auto-refreshing surfaces NOT flagged: a cycle editing `lazy_core.py` / `cycle-base-prompt.md` / a hook body does not appear in the governing-file reload set (no false "reload").

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior reaches an MCP surface (claude-config has no Tauri/MCP app). Verification is `pytest` + manual probe.

**Prerequisites:** None (first phase, per SPEC ordering rationale).

**Files likely modified:**
- `user/scripts/lazy_core.py` — self-edit predicate + probe enrichment.
- `user/scripts/lazy-state.py` — surface `self_edit_mode` on the CLI probe (thin wrapper).
- `user/skills/lazy-batch/SKILL.md` — governing-file reload discipline + new-hook-registration `⚠ restart` surfacing prose.
- `user/scripts/test_lazy_core*.py` (or the repo's existing lazy_core test module) — predicate + membership tests.

**Testing Strategy:** Pure unit tests on the predicate via symlink fixtures (tmp dirs symlinked in/out of a fake git toplevel). Governing-file-set membership is a table-driven test. Orchestrator prose is verified by docs-consistency grep in Phase 5 (and a spot grep here that the reload-discipline block exists).

**Integration Notes for Next Phase:**
- The `self_edit_mode` probe field and `governing_files_touched` list are now available — later phases that touch governing prose rely on this being live first.
- Establishes the `lazy_core.py` ↔ `lazy-state.py` CLI-surface pattern (core logic in `lazy_core.py`, thin CLI flag in `lazy-state.py`) that Phases 2/3 reuse.
- The governing-file set MUST stay in lockstep with the compaction re-read list — Phase 9's `orchestrator-voice.md` edit and Phase 5's dispatch wiring both feed this list.

**Implementation Notes (2026-06-15 — Phase 1 implemented, validation pending):**
- `lazy_core.py`: added `self_edit_mode(repo_root)` (realpath-resolves `~/.claude/{skills,scripts,hooks}` and asserts all three live under `git rev-parse --show-toplevel` via `os.path.commonpath`; False on non-git/missing/outside/error), a `GOVERNING_FILE_SET` frozenset constant (the 3 orchestrator SKILLs + the 3 `_components` files; auto-refresh surfaces excluded by construction), `governing_files_touched(repo_root)` (last-commit `git diff --name-only HEAD~1 HEAD` ∩ the set, root-commit fallback), and a documented AUTO-REFRESH BOUNDARY comment block.
- `lazy-state.py`: `--probe` now folds `self_edit_mode` (always) + `governing_files_touched` (only when self-edit) into the probe JSON. Default (non-`--probe`) output stays byte-identical — smoke baselines unaffected.
- `lazy-batch/SKILL.md`: added the governing-file reload discipline block (self-edit-triggered analog of the compaction re-read), the auto-refresh-boundary no-op list, and the new-hook-registration `⚠ restart` T6 surfacing under Step 1d. Bug/cloud twins are deliberately deferred to Phase 5's coupled-trio dispatch-wiring cycle (per plan WU-2 coupled-pair note) — only the canonical pattern is authored here.
- Design choice (D7 scope-class, ⚖ governing-file set as Python constant): made the governing set a testable `lazy_core` constant rather than prose-only, addressing the SPEC Open Question's "single shared definition both disciplines consume so they cannot drift."
- Tests: 10 new `test_lazy_core.py` cases (predicate true-inside / false-outside / normal-repo / non-git / partial-missing; set includes/excludes membership; `governing_files_touched` intersection; SKILL prose presence). Symlink fixtures use a host-capability probe (skip-as-pass if symlinks unavailable; this host supports them — positive path exercised). Full suite: 410 passed. Integration probe inside claude-config emits `self_edit_mode: true`.

---

### Phase 2: Cycle-subagent marker (C1)

**Phase kind:** design

**Scope:** Add the cycle-subagent context marker (`~/.claude/state/lazy-cycle-active.json`) read/write to `lazy_core.py` plus the `--cycle-begin` / `--cycle-end` CLI on `lazy-state.py` (and `bug-state.py`). Script-owned; the orchestrator never hand-writes it. The on/off switch every later layer keys on.

**Deliverables:**
- [ ] `lazy_core.py` marker read/write helpers (`read_cycle_marker()`, `write_cycle_marker(...)`, `clear_cycle_marker()`). Marker carries: `feature_id`, dispatch `nonce`, `kind` (`real`|`meta`), `started_at`, parent `session_id`, `commit_tally`.
- [ ] `lazy-state.py --cycle-begin --feature-id <id> --nonce <hex> [--kind real|meta]` writes the marker. Self-healing staleness: if a marker already exists (a prior dispatch crashed without `--cycle-end`), overwrite it and log the event (orchestrator is single-threaded — only one dispatch in flight).
- [ ] `lazy-state.py --cycle-end` clears the marker; idempotent (no-op if already absent), zero error on a missing marker.
- [ ] Mirror `--cycle-begin` / `--cycle-end` onto `bug-state.py` (shared `lazy_core.py` backing).
- [ ] Tests: `pytest` for set → marker file appears with all fields; clear → file deleted; idempotent re-clear is a no-op; staleness (a `--cycle-begin` over an existing marker overwrites + logs).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --cycle-begin --feature-id x --nonce abc` then `ls ~/.claude/state/lazy-cycle-active.json` shows the file with `feature_id: x`; `--cycle-end` deletes it; a second `--cycle-end` exits 0 with no error.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Marker set/clear brackets a dispatch: `--cycle-begin` then `--cycle-end` → marker file appears then is deleted; idempotent re-clear is a no-op (SPEC Validation row "Marker set/clear brackets a dispatch").

**MCP Integration Test Assertions:** N/A — state-file mechanics, no MCP surface. Verified by `pytest`.

**Prerequisites:**
- Phase 1: the `lazy_core.py` ↔ `lazy-state.py` CLI-surface pattern and the `~/.claude/state/` marker conventions (sibling of the existing run marker).

**Files likely modified:**
- `user/scripts/lazy_core.py` — marker read/write/clear helpers + staleness logic.
- `user/scripts/lazy-state.py` — `--cycle-begin` / `--cycle-end` CLI flags.
- `user/scripts/bug-state.py` — mirror the two CLI flags.
- `user/scripts/test_lazy_core*.py` — set/clear/idempotence/staleness tests.

**Testing Strategy:** Unit tests against a temp `HOME`/state dir so the real `~/.claude/state/` is untouched. Assert file contents (all required fields) on begin, absence on end, no-op on double-end, overwrite+log on stale-begin.

**Integration Notes for Next Phase:**
- The marker's `commit_tally` field is written here at 0 and incremented by the C2 hook (Phase 4) — author the field now so the hook has something to increment.
- `read_cycle_marker()` is the single predicate Phase 3's refusals and Phase 4's hook both consult (`test -f` for the hook fast-path; structured read for the refusals).
- The allow-list ops a legitimately-dispatched subagent needs (`--neutralize-sentinel`, `--verify-ledger`) must NOT be entangled with the marker — they stay callable with the marker present.

---

### Phase 3: Refuse-by-construction (C3)

**Phase kind:** design

**Scope:** `lazy_core.py` refuses the orchestrator-only state-script operations when the cycle marker is present — the belt-and-suspenders backstop if the C2 hook is disabled/bypassed. Lands BEFORE the hook (Phase 4) so the backstop exists first.

**Deliverables:**
- [ ] `--run-end`, `--run-start`, `--apply-pseudo`, `--enqueue-adhoc`, `--emit-dispatch` REFUSE (exit non-zero, ZERO side effects, corrective message) when `lazy-cycle-active.json` is present.
- [ ] Safe-for-orchestrator by construction: the orchestrator sets the marker → dispatches → clears on return → only then runs these ops, so the refusal bites ONLY a subagent calling them mid-dispatch. Document this invariant in code comments.
- [ ] The allow-listed ops (`--neutralize-sentinel`, `--verify-ledger`) and all read/probe ops continue to work with the marker present (no over-broad refusal).
- [ ] Tests: `pytest` — each refused op with marker present → non-zero exit + zero side effects (assert no file written / queue unchanged) + corrective message on stderr; same ops with marker absent → normal success; allow-listed ops succeed with marker present.

**Minimum Verifiable Behavior:** with `lazy-cycle-active.json` present, `python3 user/scripts/lazy-state.py --run-end <run>` exits non-zero, prints a corrective message, and leaves the run marker untouched; with the cycle marker absent, the same call succeeds.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Orchestrator-only op refuses under marker: `--run-end`/`--apply-pseudo`/`--enqueue-adhoc` with marker present → exit non-zero, zero side effects, corrective message (SPEC Validation row).
- [ ] Same ops allowed without marker: same ops, marker absent → normal success — orchestrator flow unaffected (SPEC Validation row).

**MCP Integration Test Assertions:** N/A — state-script refusal logic, no MCP surface. Verified by `pytest`.

**Prerequisites:**
- Phase 2: `read_cycle_marker()` — the predicate the refusals consult.

**Files likely modified:**
- `user/scripts/lazy_core.py` — refusal guards at the entry of each orchestrator-only op + invariant comments.
- `user/scripts/lazy-state.py` / `user/scripts/bug-state.py` — ensure the refusal fires on the corresponding CLI flags (the guard lives in `lazy_core.py`, surfaced through both).
- `user/scripts/test_lazy_core*.py` — refuse-with-marker / allow-without / allow-listed-ops tests.

**Testing Strategy:** Unit tests with a temp state dir: write a cycle marker, assert each guarded op refuses with zero side effects; clear it, assert success. Assert the allow-listed ops are NOT caught by the guard.

**Integration Notes for Next Phase:**
- The set of refused ops here MUST match the C2 hook's deny-set for loop-formation/lifecycle (Phase 4) — they are intentionally redundant (defense-in-depth). Keep the two lists in lockstep; a divergence is a coverage hole.
- The corrective message wording can be shared/echoed by the hook so the subagent sees a consistent reason whether the hook or the script catches it.

---

### Phase 4: PreToolUse containment hook (C2)

**Phase kind:** design

**Scope:** New `user/hooks/lazy-cycle-containment.sh` + `settings.json` wiring under `PreToolUse` for `Bash` (and `Agent`). While the cycle marker is present, DENY in-flight the tool calls a runaway needs; fast-path-exit when the marker is absent. Fail-OPEN on hook error (the C3 refusal is the backstop).

**Deliverables:**
- [ ] `user/hooks/lazy-cycle-containment.sh`: fast-path `test -f ~/.claude/state/lazy-cycle-active.json` exit (ALLOW) when the marker is absent — interactive sessions and orchestrator-between-cycles untouched.
- [ ] Loop-formation deny: `lazy-state.py`/`bug-state.py` with `--probe`, `--emit-prompt`, `--repeat-count`, `--repeat-count-peek`, `--run-start`, `--run-end`, `--apply-pseudo`, `--enqueue-adhoc`, `--emit-dispatch` → `permissionDecision: deny` + corrective `permissionDecisionReason`. ALLOW the narrow ops (`--neutralize-sentinel`, `--verify-ledger`).
- [ ] Runtime-lifecycle deny: `npm run dev:kill`, `npm run dev:restart`, `dev:kill`, `dev:restart`, `kill-port 3333`, `kill-port 1420`.
- [ ] Second-feature commit tripwire: on `git commit`, resolve staged feature dir(s) from `git diff --cached --name-only`; DENY if any staged path is under a DIFFERENT feature dir than the marker's `feature_id`. Carve-outs (always allowed): `docs/features/queue.json`, `docs/features/ROADMAP.md`, repo-root `CLAUDE.md`, the feature's own dir.
- [ ] Commit-count backstop: read `commit_tally` from the marker; DENY beyond a generous absolute ceiling (default 25/dispatch). Increment `commit_tally` on each ALLOWED `git commit`.
- [ ] Recursive-dispatch deny: an `Agent` tool call while the marker is present is DENIED (future-proofs even though cycle subagents have no `Agent` tool today).
- [ ] Fail-OPEN on hook error: log a breadcrumb and ALLOW (mirror `lazy-route-inject.sh`) — a broken hook must never wedge the pipeline.
- [ ] `settings.json` `PreToolUse` wiring for `Bash` and `Agent` matchers → `bash ~/.claude/hooks/lazy-cycle-containment.sh`.
- [ ] Tests: hook-test harness driving crafted JSON payloads — deny next-route probe, deny lifecycle, deny 2nd-feature commit, ALLOW same-feature commit, ALLOW allow-listed ops, fast-path ALLOW when marker absent, fail-OPEN on malformed input.

**Minimum Verifiable Behavior:** with the marker present, piping a Bash `lazy-state.py --probe` payload into `lazy-cycle-containment.sh` emits `permissionDecision: deny`; with the marker absent the same payload emits an ALLOW (or empty/no-deny) — provable from a shell harness without the full pipeline.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Hook denies the next-route probe: Bash `lazy-state.py --probe` while marker present → `permissionDecision: deny` + corrective reason (SPEC Validation row).
- [ ] Hook denies lifecycle/runtime commands: Bash `--run-end` / `dev:kill` while marker present → deny (SPEC Validation row).
- [ ] Hook denies a 2nd-feature commit: `git commit` staging a different feature dir → deny; same-feature commit allowed (SPEC Validation row — staged-path fixture).
- [ ] Hook is inert without marker: any Bash, marker absent → fast-path allow, no deny (SPEC Validation row).
- [ ] new-hook entry surfaces restart warning: adding this hook entry to `settings.json` is surfaced as `⚠ … restart the session to (de)register`, not "live" (SPEC Validation row — Phase 1's T6 mechanism applied to THIS phase's own settings.json edit).

**MCP Integration Test Assertions:** N/A — PreToolUse hook + state-file mechanics, no MCP surface. Verified by a bash hook-test harness.

**Prerequisites:**
- Phase 2: the marker file the fast-path keys on + `commit_tally`.
- Phase 3: the C3 refusal backstop exists (so a hook fail-OPEN is safe).

**Files likely modified:**
- `user/hooks/lazy-cycle-containment.sh` — NEW.
- `user/settings.json` — `PreToolUse` hook wiring (Bash + Agent matchers).
- `user/hooks/test_lazy_cycle_containment*` (or the repo's hook-test harness) — payload-driven deny/allow tests.

**Testing Strategy:** Bash-level harness that constructs PreToolUse JSON payloads (tool name + command) and asserts the hook's stdout JSON decision. Use a temp state dir + temp marker. The 2nd-feature tripwire uses a staged-path fixture (a fake `git diff --cached` output or a temp git repo). Assert fail-OPEN on malformed JSON.

**Integration Notes for Next Phase:**
- The deny-set here MUST stay in lockstep with Phase 3's C3 refusal set (the two are intentionally redundant).
- Because this phase ADDS a hook entry to `settings.json` (not merely a script body), Phase 1's new-hook-registration `⚠ restart` surfacing applies to the cycle that lands THIS phase — the wiring is not live until the session restarts; the C3 refusal covers the gap meanwhile.
- The corrective `permissionDecisionReason` text should align with the Phase 6 cycle-prompt terminal-stop wording so the subagent gets a consistent message from both the prompt and the deny.

---

### Phase 5: Orchestrator dispatch wiring (C1 callers)

**Phase kind:** design

**Scope:** Add the `--cycle-begin` / `--cycle-end` bracket around EVERY dispatch in `/lazy-batch`, `/lazy-bug-batch`, `/lazy-batch-cloud` (the coupled trio — mirror per CLAUDE.md). `--cycle-begin` immediately before every `Agent` dispatch (real-skill AND meta-dispatches: input-audit, apply-resolution, recovery, hardening, coherence-recovery, needs-runtime-redispatch); `--cycle-end` immediately after the `Agent` returns on EVERY return path (success, halt, error).

**Deliverables:**
- [ ] `user/skills/lazy-batch/SKILL.md`: `--cycle-begin --feature-id <id> --nonce <hex> [--kind real|meta]` before each dispatch; `--cycle-end` after each return on all three return paths (success, halt, error).
- [ ] `user/skills/lazy-bug-batch/SKILL.md`: same bracket, mirrored (bug pipeline twin).
- [ ] `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`: same bracket, mirrored (cloud twin); update its "Differences from /lazy-batch" block only if cloud genuinely diverges (it should not — the bracket is identical).
- [ ] Update each file's State Machine Summary / orchestration-shape block at the bottom so the dispatch table reflects the new begin/end bracket (per CLAUDE.md coupled-pair rule).
- [ ] Tests: docs-consistency grep that all three orchestrators set `--cycle-begin` before AND clear `--cycle-end` after each dispatch on all return paths (no orphan begin without a matching end on any path).

**Minimum Verifiable Behavior:** `grep -c -- '--cycle-begin'` and `grep -c -- '--cycle-end'` across each of the three SKILLs return matching, non-zero counts, and each `--cycle-end` is paired to a return path (success/halt/error) — verifiable by a docs-consistency script without running the pipeline.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] All three orchestrators bracket every dispatch: grep the coupled SKILLs → `--cycle-begin` before + `--cycle-end` after each dispatch on all return paths (SPEC Validation row — docs-consistency test).
- [ ] governing-prose edit triggers re-read: committing to `lazy-batch/SKILL.md` here (with `self_edit_mode` on from Phase 1) is itself a governing-prose edit — the running orchestrator re-reads it before the next dispatch (SPEC Validation row; closes the loop on Phase 1's discipline).

**MCP Integration Test Assertions:** N/A — orchestrator skill prose, no MCP surface. Verified by docs-consistency grep.

**Prerequisites:**
- Phase 2: the `--cycle-begin` / `--cycle-end` CLI must exist before the orchestrators call them.
- Phase 1: lands the reload discipline so THIS phase's `lazy-batch/SKILL.md` edit is picked up by the running orchestrator (the SPEC's explicit phase-ordering payoff).

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md` — dispatch bracket + State Machine Summary update.
- `user/skills/lazy-bug-batch/SKILL.md` — mirrored bracket + summary.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — mirrored bracket + "Differences" block + summary.
- A docs-consistency test (repo's existing skill-lint or a new check) asserting the begin/end pairing across the trio.

**Testing Strategy:** Pure docs-consistency: a grep/parse asserting each dispatch site has a preceding `--cycle-begin` and that every return path (success/halt/error) carries a `--cycle-end`. Cross-check the three files are mirrored (same bracket count + shape) per the coupled-pair rule.

**Integration Notes for Next Phase:**
- This is the highest-coupling phase — the trio MUST stay mirrored. Any reviewer must diff all three after the edit (CLAUDE.md coupling rule).
- The nonce/kind passed at `--cycle-begin` flows into the marker (Phase 2) which the hook (Phase 4) reads — verify the `--feature-id` the orchestrator passes matches the feature the dispatch is for (the 2nd-feature tripwire depends on it being correct).

---

### Phase 6: Cycle-prompt terminal stop condition (C4)

**Phase kind:** design

**Scope:** A new `@section` (terminal stop) appended to every cycle prompt via the shared template `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`, telling the subagent its dispatch ends at commit+push+report. Mirrored across feature/bug/cloud prompt variants.

**Deliverables:**
- [ ] New `@section` (terminal stop) in `cycle-base-prompt.md`: "Your dispatch is exactly ONE cycle. After your single skill returns and you have committed + pushed + written your report, STOP. Do NOT run `lazy-state.py`/`bug-state.py` to find or route a next action. Do NOT begin a second feature. Do NOT run `--run-end`/`--run-start`/`--apply-pseudo`/`--enqueue-adhoc`/`dev:kill`/`dev:restart` — those are orchestrator-only and the harness will DENY them in-flight. Routing the next cycle is the orchestrator's job; your job ends at the report."
- [ ] Verify the section is picked up by `emit_cycle_prompt` (it re-reads `cycle-base-prompt.md` from disk every probe — already-live, no reload needed).
- [ ] Mirror to bug/cloud prompt variants (shared template — confirm the section appears in every projected variant).
- [ ] Tests: `project-skills.py` projection lint asserting the terminal-stop `@section` is present in every cycle-prompt variant; a size check the addition stays within prompt-size budget.

**Minimum Verifiable Behavior:** `python3 user/scripts/project-skills.py` followed by a grep for the terminal-stop section text in each projected cycle-prompt variant returns a hit for every variant.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Cycle prompt carries the terminal stop section: `project-skills.py` projection → the stop `@section` present in every cycle-prompt variant (SPEC Validation row — projection lint).

**MCP Integration Test Assertions:** N/A — prompt-component prose, no MCP surface. Verified by projection lint.

**Prerequisites:**
- None hard-coupled, but pairs naturally with Phase 4 — the prompt's terminal-stop wording should align with the hook's `permissionDecisionReason` text so the subagent gets a consistent message.

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — new `@section`.
- (Verify bug/cloud variants inherit via the shared template; edit their addenda only if they carry separate prompt bodies.)
- A projection-lint assertion (in `lint-skills.py` or `project-skills.py` checks) for the section's presence across variants.

**Testing Strategy:** Run `project-skills.py` and assert the terminal-stop text projects into every cycle-prompt variant. Size check: the addition does not push any projected prompt past its budget.

**Integration Notes for Next Phase:**
- `cycle-base-prompt.md` is an AUTO-REFRESHING surface (re-read by `emit_cycle_prompt` every probe) — it is NOT in Phase 1's governing-file reload set and must NOT be flagged for reload (it was never stale). This phase is a good cross-check of Phase 1's auto-refresh-boundary exclusion.

---

### Phase 7: Recovery-dispatch scope hardening (C5)

**Phase kind:** design

**Scope:** Make the recovery subagent's "tick ONLY with on-disk evidence" prose self-enforcing in `user/skills/_components/lazy-batch-prompts/dispatch-recovery.md` (and the recovery emit): the recovery subagent MUST `grep` for `VALIDATED.md` / `MCP_TEST_RESULTS.md` covering a Runtime-Verification row before ticking it; if absent, leave the box unticked and report it. Closes the cycle-3 over-tick observed in the AlgoBooth run.

**Deliverables:**
- [ ] `dispatch-recovery.md`: require a grep-and-cite before ticking any Runtime-Verification row — the recovery subagent greps for `VALIDATED.md` / `MCP_TEST_RESULTS.md` (or the equivalent on-disk evidence) covering the row; ticks ONLY on a hit; otherwise leaves it unticked and reports the absence.
- [ ] Reflect the grep-and-cite requirement in the recovery emit prose (wherever the recovery prompt is composed) so the dispatched recovery subagent receives it.
- [ ] Tests: docs-consistency grep that `dispatch-recovery.md` contains the grep-and-cite gate (the prose self-enforcement is on disk).

**Minimum Verifiable Behavior:** a grep of `dispatch-recovery.md` finds the grep-and-cite gate text (recovery subagent must cite on-disk evidence before ticking) — verifiable statically.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] dispatch-recovery prose carries the grep-and-cite gate: a grep of the component finds the "grep for VALIDATED.md / MCP_TEST_RESULTS.md before ticking" requirement (docs-consistency).

**MCP Integration Test Assertions:** N/A — recovery-prompt component prose, no MCP surface. Verified by docs-consistency grep.

**Prerequisites:** None (independent prose hardening).

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/dispatch-recovery.md` — grep-and-cite gate.
- The recovery-emit prose (in `lazy_core.py`'s emit path or the orchestrator SKILL, wherever the recovery prompt is assembled) — reflect the requirement.

**Testing Strategy:** Docs-consistency grep for the gate text. If the recovery prompt is assembled in `lazy_core.py`, a `pytest` asserting the emitted recovery prompt contains the grep-and-cite instruction.

**Integration Notes for Next Phase:**
- `dispatch-recovery.md` is a prompt component re-read at emit time (auto-refreshing) — NOT in Phase 1's reload set.

---

### Phase 8: R-O-9 retro rule + force-cap (C6)

**Phase kind:** design

**Scope:** Add **R-O-9 (single-cycle containment)** to `user/skills/lazy-batch-retro/SKILL.md` §4a and a hard force-cap to §5c. From git (`git log <window>`) + the parent jsonl dispatch list (both always available even when `/tmp` transcripts are reclaimed), compute commits-per-dispatch and features-per-dispatch; force-cap any run where a single dispatch touches >1 feature OR calls a run-lifecycle command. This is the detection layer R-EP-1/2 cannot provide (they invert under the inline-override branch).

**Deliverables:**
- [ ] §4a: add R-O-9 (single-cycle containment) — define the metric (commits-per-dispatch, features-per-dispatch) computed from `git log <window>` + the parent jsonl dispatch list.
- [ ] §5c: hard force-cap when a single dispatch touches >1 feature OR calls a run-lifecycle command (`--run-end`/`--apply-pseudo`/`--enqueue-adhoc`/`dev:kill`) → grade `fail` + force-cap.
- [ ] Document that R-O-9 is the git+jsonl-keyed detection (always available) that complements (does not replace) R-EP-1/2.
- [ ] Tests: a retro self-test / fixture over a multi-feature single dispatch → grade `fail` + force-cap from git+jsonl evidence.

**Minimum Verifiable Behavior:** running the retro (or its self-test fixture) over a fixture run whose git+jsonl shows one dispatch touching 2 features produces a `fail` grade with the R-O-9 force-cap cited.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] R-O-9 force-caps a runaway: retro over a multi-feature single dispatch → grade `fail` + force-cap from git+jsonl (SPEC Validation row — retro self-test / fixture).

**MCP Integration Test Assertions:** N/A — retro skill prose + a fixture-driven grading check, no MCP surface.

**Prerequisites:** None (independent retro-rule addition).

**Files likely modified:**
- `user/skills/lazy-batch-retro/SKILL.md` — R-O-9 in §4a + force-cap in §5c.
- A retro self-test fixture (multi-feature single-dispatch git+jsonl sample) + the assertion that it force-caps.

**Testing Strategy:** Fixture-driven: a synthetic git log + jsonl dispatch list where one dispatch spans 2 features (and/or calls `--run-end`); assert the retro's R-O-9 logic flags it `fail` + force-cap. Docs-consistency grep that R-O-9 is present in §4a and §5c.

**Integration Notes for Next Phase:**
- R-O-9 is the always-available detection backstop to the in-flight prevention (C1–C4). Its evidence base (git + jsonl) is deliberately independent of transcripts so it survives transcript reclamation.

---

### Phase 9: Secondary voice/ledger fixes (C7)

**Phase kind:** design

**Scope:** Two folded-in fixes from the claude-config `lazy-pipeline-visualizer` retro: (a) the R-V-1 mechanics-silent reinforcement in `user/skills/_components/orchestrator-voice.md`; (b) the missing `plan-feature` Decision-Classification Ledger in `user/skills/plan-feature/SKILL.md`.

**Deliverables:**
- [ ] `orchestrator-voice.md`: tighten the silent-mechanics rule at the observed recurring seams — run-start narration, "Running the {ledger} guard." post-return lines, marker-confirm ("the marker confirms forward_cycles=…"), narrated file reads ("Reading the resolution handler"). Add these to the hard-bans list WITH examples.
- [ ] `plan-feature/SKILL.md`: require the cycle to emit the structured `### Decision-Classification Ledger` that `/spec --batch` mandates, so the Step 1d.5 input-audit is not the only safety net (its absence let a SPEC-locked state-collapse slip past prose self-classification).
- [ ] Tests: docs-consistency grep that `orchestrator-voice.md` hard-bans list carries the four new seams with examples; that `plan-feature/SKILL.md` requires the `### Decision-Classification Ledger` in its return summary.

**Minimum Verifiable Behavior:** a grep of `orchestrator-voice.md` finds the four new hard-banned seams with examples; a grep of `plan-feature/SKILL.md` finds the `### Decision-Classification Ledger` requirement — both verifiable statically.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] plan-feature emits the ledger: a `plan-feature --batch` cycle includes the `### Decision-Classification Ledger` in its return summary (SPEC Validation row — docs-consistency / skill-lint over the requirement prose).
- [ ] R-V-1 hard-bans carry the new seams: grep `orchestrator-voice.md` for the four reinforced seams with examples (docs-consistency).

**MCP Integration Test Assertions:** N/A — component + skill prose, no MCP surface.

**Prerequisites:**
- Phase 1: `orchestrator-voice.md` is in the governing-file reload set — landing this edit with `self_edit_mode` on means the running orchestrator re-reads it before the next dispatch (the SPEC's payoff for sequencing C8 first).

**Files likely modified:**
- `user/skills/_components/orchestrator-voice.md` — R-V-1 reinforcement (four seams + examples in the hard-bans list).
- `user/skills/plan-feature/SKILL.md` — require the `### Decision-Classification Ledger` in the return summary.
- A docs-consistency / skill-lint assertion for both requirements.

**Testing Strategy:** Docs-consistency greps over both files for the new requirements. If `lint-skills.py` validates skill structure, extend it (or add a check) for the `plan-feature` ledger requirement.

**Integration Notes for Next Phase:**
- This is the LAST phase. When its work lands, the implementation of all 9 phases is done — set the top-level PHASES `**Status:**` to `In-progress` (NOT Complete — validation pending; the `__mark_complete__` gate owns the Complete flip after the validation tail).
- `orchestrator-voice.md` being in the governing-file set means this edit (Phase 9) and Phase 5's `lazy-batch/SKILL.md` edit are the two governing-prose edits whose mid-run pickup motivated sequencing C8 (Phase 1) first.

---

**Completion (gate-owned):** the `__mark_complete__` integrity gate flips SPEC.md and PHASES.md top-level `**Status:**` to Complete and writes `COMPLETED.md` once all phases' runtime verification passes through the validation tail. No phase authors a status-flip / receipt / archive checkbox row (per the gate-owned-row ban).
