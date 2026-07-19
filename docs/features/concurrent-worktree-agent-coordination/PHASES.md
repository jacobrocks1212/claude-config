# Implementation Phases — Concurrent Multi-Agent Worktree Coordination

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — the entire deliverable is claude-config harness surface (Python state-machine helpers, a PowerShell lock, skill/component prose, and docs). It crosses none of the AlgoBooth MCP boundary taxonomy (no sidecar↔Rust, capnp/N-API, Tauri command, or audio-callback surface); it is validated by the in-file `--test` smoke harnesses, `pytest tests/test_lazy_core/`, PowerShell Pester, and the 7-command gate battery — never the Tauri+MCP HTTP runtime. (Per `docs/features/mcp-testing/SPEC.md`, this is the "no app integration / build-tooling / docs" untestable class.)

## Cross-feature Integration Notes

Phase-level dependencies on completed upstream features, extracted from each upstream's PHASES.md during /spec-phases Step 1.5. Phase plans below MUST honor these.

- **parallel-worktree-batch-execution (kind=hard, Complete):** the FIFO file-lock and the temp-worktree merge-back both reuse this feature's concurrency plane VERBATIM — `lazy_coord.py`'s `acquire_lock`/`release_lock` (`os.mkdir` global lock + `owner.json` `_confirmed_dead_owner` reclamation), `acquire_lease`/`heartbeat`/`verify_fencing` (fencing tokens monotonic across reclaim via `lease-token-watermarks.json`), `lane_branch`/`lane_pool_dir` (`lane/<item-id>`, sibling `<repo_root>-lanes/wt-NN`), the `lanes.json` ledger (`ledger_record_claim/_merge/_demotion`), `merge_order` (queue-order), and `merge_lane_branch` (abort-and-demote, lane branch preserved). Lock granularity is per-queue-item (Locked Decision 1) → it reuses the lease keying by `wi_id` unchanged. Phases 3 and 5 consume these. `lazy_coord.py` MUST NOT import `lazy_core` (documented separation — its atomic write is a justified duplication).
- **park-provisional-acceptance (kind=hard, Complete):** the semantic-conflict halt (Phase 4) extends `lazy_core.provisional_eligibility` (`docmodel.py:2551`) — a deterministic FAIL-CLOSED predicate. The new carve-out mirrors the existing `written_by == "spike"` / `spike_verdict: fail` / `stub_origin` exclusions exactly (a frontmatter-keyed early `return (False, reason)` before the divergence two-key), so a semantic-conflict `NEEDS_INPUT.md` is never auto-accepted under `--park-provisional`. Both callers (the park-mode routing peek and `--provisionalize-sentinel`) re-run this predicate, so one carve-out is airtight.
- **generalized-build-test-runner-skills (kind=composes, Complete):** the cross-platform FIFO lock (Phase 3) conforms to the runner-outcome **two-implementation, documented-grammar-not-shared-code** pattern — a PowerShell workstation plane (`build-queue*.ps1` precedent) and a stdlib-Python plane (`gate-battery.py` precedent) conforming independently to a contract documented once. The lock contract is authored the same way (`user/skills/_components/runner-outcome-contract.md` is the sibling precedent).
- **multi-repo-concurrent-runs (kind=soft, Complete):** the awareness + git-safety layer composes with the per-repo keyed state dir (`lazy_core.claude_state_dir` / `repo_key`) and run-marker arbitration (`refuse_run_start_clobber`, `marker_owner_status`) — this feature does NOT re-derive concurrency detection; it makes the ALREADY-detected concurrent-writer case non-panicking.
- **build-queue-generalization (kind=soft, Complete) / long-build-and-runtime-ownership (kind=soft, Complete):** the FIFO-serializer precedent (`build-queue.ps1` `active.lock` + seq + confirmed-dead reclaim) and the transient-worktree takeover precedent (`lazy_core.run_transient_build`) are borrowed patterns; no direct code dependency.

## Validated Assumptions

Load-bearing assumptions for this plan, classified per the Step 2.7 gate. This feature has **no user-facing runtime surface** (no MCP tool, IPC command, or UI) — the reachability axiom is satisfied by the harness's own test surface — so every load-bearing assumption below is **code-provable** and was confirmed by the touchpoint audit (grep/read, cited):

- **`provisional_eligibility` is a frontmatter-keyed fail-closed predicate with early-return carve-outs** — confirmed at `docmodel.py:2551` (the `written_by == "spike"` / `spike_verdict` / `stub_origin` early returns precede the divergence two-key). Code-provable; the new carve-out is the identical shape.
- **`lazy_coord.py` exposes the lock/lease/lane/merge surface named in the reuse map** — confirmed (`acquire_lock`@448, `acquire_lease`@505, `merge_lane_branch`@1096, `lane_branch`@827, `ledger_record_*`@987+). Code-provable.
- **The `self_edit_mode` foreground-await coupling (R7 retirement target) is distinct from the governing-file RELOAD discipline** — confirmed: the foreground/await coupling lives at lazy-batch/SKILL.md:899 (Concurrency EXCEPTION) + lazy-bug-batch:709 + lazy-batch-cloud; the governing-file reload (self-edit C8, lazy-batch:666) is a SEPARATE mechanic that MUST be retained (a self-edit commit still staleifies the in-context copy). Retiring the former must not touch the latter. Code-provable (prose read).
- **The cycle-commit path uses `git add -A` in the R5 atomic chain** — confirmed at cycle-base-prompt.md:654,698 (and a pre-existing network push-retry at :606). Git-safety wires fetch+ff-before-push + non-ff retry + pathspec scoping HERE. Code-provable.
- **SPEC-example capability audit:** the SPEC carries no code examples consuming a target-system API surface (it describes prose contracts + reuse of existing Python/PowerShell symbols, all grep-confirmed above). No rejected-capability risk. **MCP tool-existence audit:** no `.claude/skill-config/mcp-tool-catalog.md` in claude-config → the MCP audit is a no-op (`no mcp-tool-catalog.md configured for this repo`).

---

### Phase 1: Awareness injection + reconcile "One writer per file"

**Scope:** Bake the concurrent-writer awareness note — "OTHER agents may be committing to this same worktree/branch concurrently from parallel sessions; an unexpected commit / moved HEAD is EXPECTED, not a defect to panic on" — into every agent-context surface, and reconcile the single-writer `<orchestration>` block with sanctioned concurrent writers. Mechanical text (Requirement 1); establishes the trust contract Phase 6 (R7) relies on so a future orchestrator does not reintroduce defensiveness.

**Deliverables:**
- [x] Awareness note added to `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (cycle-subagent context).
- [x] Awareness note added to the HARD CONSTRAINTS of `user/skills/lazy-batch/SKILL.md` and `user/skills/lazy-batch-parallel/SKILL.md`.
- [x] Awareness note added to the sub-subagent dispatch policy prose (the dispatch-policy block reused across the cycle prompts).
- [x] `user/CLAUDE.md` `<orchestration>` "One writer per file" block reconciled: keep the single-writer default for a run's OWN dispatched agents, but explicitly carve out sanctioned CONCURRENT writers on a shared worktree/branch (a second interactive/scheduled session) and point at the coordination layer (git-safety + FIFO lock + conflict-routing) as the arbiter — NOT panic.
- [x] AlgoBooth mirrors updated: `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` and `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` carry the same awareness note.
- [x] Tests: `python3 ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities` and `python3 ~/.claude/scripts/doc-drift-lint.py --repo-root .` stay exit 0; `python3 ~/.claude/scripts/project-skills.py` re-projects cleanly.

**Minimum Verifiable Behavior:** `python3 ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities && python3 ~/.claude/scripts/doc-drift-lint.py --repo-root .` exits 0 after the edits, and a `grep -rl "unexpected commit"` (or the chosen canonical awareness phrase) resolves in every injection point named above.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior (prose-only phase).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — awareness note near the branch/commit contract.
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-batch-parallel/SKILL.md` — HARD CONSTRAINTS awareness note.
- `user/CLAUDE.md` — `<orchestration>` reconciliation.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` — mirror.

**Testing Strategy:** Lint + projection + doc-drift gates (deterministic, in-process). A committed grep-anchor check that the awareness phrase is present in each injection point guards against a future silent drop.

**Integration Notes for Next Phase:** The awareness phrase chosen here is the canonical string; Phase 6 references it as the documented trust contract. Do NOT weaken the "One writer per file" default for a run's OWN agents — the carve-out is ONLY for cross-session concurrent writers.

---

### Phase 2: Git safety — fetch+ff-before-push, bounded non-ff retry, pathspec-scoped commits, friction carve-out

**Scope:** Make every cycle git operation safe under an open shared worktree (Requirement 2 + Validation rows 1–2). Add a fetch+fast-forward-before-push helper with bounded non-ff retry (never `--force`), prefer pathspec-scoped commits over blanket `git add -A` so a concurrent writer's staged files are never absorbed, and carve the sanctioned-concurrent-writer commit out of the `unexpected-commits` process-friction detector so it stops firing a false `process-friction` deny-ledger entry (the motivating 2026-07-18 incident).

**Deliverables:**
- [x] New git-safety helper in `user/scripts/lazy_core/runtimeplane.py` alongside `_git`/`_current_head`/`git_guard_status`: fetch + fast-forward + bounded non-ff push retry (attempt cap, never `--force`), returning a structured result (pushed / retried-n / conflict). Injected `run`/`sleep` seam so `--test` is hermetic.
- [x] `detect_cycle_bracket_friction` (`user/scripts/lazy_core/markers.py`) carve-out: a HEAD advance attributable to a CONCURRENT writer (a commit whose author/session is not this cycle's, distinguishable from a runaway's own extra commits) does NOT append a `process-friction` `unexpected-commits` deny-ledger entry. Conservative + fail-closed toward the EXISTING behavior for a genuine runaway (an ambiguous case still counts as friction — the fail-safe direction is "keep detecting runaways").
- [ ] Cycle-commit prose (`cycle-base-prompt.md`) updated: the R5 `git add -A` chain (@654,698) becomes fetch+ff-then-push with pathspec-scoped staging guidance (stage the agent's own changed files, not a blanket `-A` that absorbs a concurrent writer's work); the pre-existing network-retry (@606) is subsumed by the non-ff retry contract.
- [x] Tests: `lazy-state.py --test`, `bug-state.py --test`, and `pytest tests/test_lazy_core/test_runtimeplane.py test_markers.py` cover: (a) push succeeds after one non-ff race via fetch+ff+retry with no `--force`; (b) a concurrent-writer commit does NOT append a `process-friction` entry; (c) a genuine runaway's extra commit STILL does.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test && python3 user/scripts/bug-state.py --test && python3 -m pytest tests/test_lazy_core/test_runtimeplane.py tests/test_lazy_core/test_markers.py` exits 0 with the three new fixtures green.

**MCP Integration Test Assertions:** N/A — validated by the hermetic `--test`/pytest suites (no MCP surface).

**Prerequisites:**
- Phase 1: the awareness note establishes that a concurrent commit is expected (the friction carve-out is the mechanical enforcement of that prose).

**Files likely modified:**
- `user/scripts/lazy_core/runtimeplane.py` — git-safety push helper.
- `user/scripts/lazy_core/markers.py` — friction-detector carve-out.
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — commit-chain prose.
- `user/scripts/lazy-state.py`, `user/scripts/bug-state.py` — new `--test` fixtures (coupled pair; run `lazy_parity_audit.py --repo-root .` after — the friction detector is shared `lazy_core`, so no CLI mirror is owed, but keep both suites green).
- `tests/test_lazy_core/test_runtimeplane.py`, `tests/test_lazy_core/test_markers.py` — pytest coverage.

**Testing Strategy:** Hermetic — inject the git `run`/`sleep` seam and a fake commit-authorship signal so the non-ff race and the concurrent-vs-runaway discrimination are deterministic without a real remote. Assert `--force` is NEVER in any composed argv.

**Integration Notes for Next Phase:** The concurrent-writer discriminator (authorship/session signal) established here is the same signal the conflict router (Phase 4) uses to decide whether a HEAD move is a sanctioned concurrent writer vs. this cycle's own work. Keep it in one helper; Phase 4 consumes it. The friction carve-out is shared `lazy_core` (both pipelines inherit it) — a coupled-pair `--test` mirror, not a CLI mirror.

---

### Phase 3: Cross-platform FIFO file-lock (per-queue-item grain, two conforming implementations)

**Scope:** Agents DETECT write contention and coordinate via a FIFO/queue lock so each proceeds in turn (Requirement 3, Locked Decision 1). Built on `lazy_coord.py`'s global-lock + fencing-lease machinery; **per-queue-item granularity** (one lock per feature/bug item, reusing the `lazy_coord` lease keying by `wi_id` verbatim — two agents on the same item serialize, two on different items never block). Two conforming implementations per the runner-outcome two-implementation contract: PowerShell (workstation) + stdlib-Python (cloud/AlgoBooth), conforming to a lock contract documented ONCE.

**Deliverables:**
- [ ] Lock contract component `user/skills/_components/concurrent-lock-contract.md` — the documented grammar (acquire = wait-for-unlock FIFO; per-item key; fencing-token release; stale-holder reclaim via `_confirmed_dead_owner`; authoritative acquire/timeout outcome), authored the same way as `runner-outcome-contract.md`. Names the two conforming implementations.
- [ ] Stdlib-Python FIFO-lock wiring in `lazy_coord.py` (or a thin sibling): a per-queue-item FIFO acquire built on `acquire_lock` + `acquire_lease`/`verify_fencing`, waiting on the item's lease to unlock before proceeding, with the existing confirmed-dead-holder reclamation. Reuses `wi_id` keying — no new locking substrate.
- [ ] PowerShell workstation implementation `user/scripts/concurrent-lock.ps1` conforming to the same contract (mirrors the `build-queue.ps1` `active.lock` + seq + confirmed-dead-reclaim precedent). Thin skill `/concurrent-lock` optional (defer if not needed for v1).
- [ ] `.claude/skill-config/gate-battery.json` / script tables in root `CLAUDE.md` + `user/scripts/CLAUDE.md` updated to document the new script(s) (doc-drift-lint requires the script table to match disk).
- [ ] Tests: `lazy_coord.py --test` fixtures — two agents contending on the SAME item serialize (second waits, then proceeds in turn); two agents on DIFFERENT items never block; a confirmed-dead holder is reclaimed. PowerShell Pester tests for the `.ps1` plane (FIFO order, timeout banner, stale reclaim).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_coord.py --test` exits 0 with the same-item-serialize and different-item-no-block fixtures green; the PowerShell Pester suite for `concurrent-lock.ps1` passes on the workstation.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Two real concurrent processes acquiring the SAME per-item lock proceed in FIFO order (second blocks until first releases), observed on the workstation via the PowerShell plane. (Cross-platform two-implementation parity — workstation-eligible.)

**MCP Integration Test Assertions:** N/A — no MCP surface; the lock is validated by `--test`/Pester + the live two-process observation above.

**Prerequisites:**
- Phase 1 (awareness prose references the lock as the contention arbiter).

**Files likely modified:**
- `user/scripts/lazy_coord.py` — Python FIFO-lock wiring + `--test` fixtures.
- `user/scripts/concurrent-lock.ps1` — net-new PowerShell implementation.
- `user/skills/_components/concurrent-lock-contract.md` — net-new documented grammar.
- `CLAUDE.md`, `user/scripts/CLAUDE.md` — script-table + component doc entries.

**Testing Strategy:** Python plane hermetic via `lazy_coord.py`'s injected-`now` reclamation harness (21-fixture precedent); PowerShell plane via Pester with a temp state root. The two implementations conform to the ONE contract independently — no shared code (the documented-grammar pattern).

**Integration Notes for Next Phase:** Per-file granularity is an explicit vN refinement (Locked Decision 1) — do NOT add it now. The FIFO lock is the FIRST conflict route (retry/queue in turn); Phase 4 layers the git-mergeability discriminator on top for conflicts that slip past the lock.

---

### Phase 4: Conflict routing — write-conflict (non-halting) + semantic-conflict halt + provisional carve-out

**Scope:** Consistent handling for a conflict that slips past the FIFO lock (Requirements 4–6, Locked Decision 2). A WRITE conflict is non-halting (retry/queue via the lock, log, continue — NEVER halts a `/lazy-batch` run). A SEMANTIC conflict HALTS: write `NEEDS_INPUT.md` (class `product`) and add the semantic-conflict carve-out to `provisional_eligibility`'s fail-closed set so it is NEVER auto-accepted under `--park-provisional`. The discriminator is LOCKED to the **git-mergeability + coupled-surface heuristic**: NON-semantic when git auto-merges (no conflict markers) OR the conflicting hunks touch disjoint logical surfaces; SEMANTIC when git reports an un-auto-resolvable conflict on the SAME logical artifact (same function / Locked-Decision row / sentinel). Deterministic; ambiguous → SEMANTIC/halt (fail-safe).

**Deliverables:**
- [ ] Conflict-discriminator helper in `lazy_core` (shared, both pipelines): `classify_conflict(...) -> {"write" | "semantic", reason}` implementing the git-mergeability + coupled-surface heuristic (git auto-merge check → conflict-marker presence → disjoint-surface check → fail to SEMANTIC on ambiguity). Pure/injectable git seam for hermetic `--test`.
- [ ] Semantic-conflict carve-out in `provisional_eligibility` (`user/scripts/lazy_core/docmodel.py`): a `NEEDS_INPUT.md` carrying the semantic-conflict marker (e.g. `conflict_kind: semantic` frontmatter, or `written_by: conflict-router` with a semantic verdict) returns `(False, "semantic conflict — never auto-accepted (park, do not provisionally accept)")` — placed with the Spike-FAIL / `stub_origin` early returns, before the divergence two-key. Both callers re-run the predicate (airtight).
- [ ] Sentinel schema: register the semantic-conflict `NEEDS_INPUT.md` shape (`class: product`, the conflict marker field) in `user/skills/_components/sentinel-frontmatter.md` and, in lockstep, AlgoBooth's `scripts/check-docs-consistency.ts` `SENTINEL_SCHEMAS` (schema coupling rule).
- [ ] Conflict-routing prose in `cycle-base-prompt.md` / the dispatch policy: on a write conflict, retry/queue via the FIFO lock, log, continue (no halt); on a semantic conflict, write the class-`product` `NEEDS_INPUT.md` and halt.
- [ ] Tests: `pytest tests/test_lazy_core/test_docmodel.py` — a semantic-conflict `NEEDS_INPUT.md` is `provisional_eligibility` INELIGIBLE even with `isolated/isolated` divergence grades; a write-conflict path never writes `NEEDS_INPUT.md`. `classify_conflict` fixtures for each branch (auto-merge → write; conflict-marker-on-shared-function → semantic; disjoint-surface conflict → write; ambiguous → semantic).

**Minimum Verifiable Behavior:** `python3 -m pytest tests/test_lazy_core/test_docmodel.py` exits 0 with the carve-out + discriminator fixtures green; a manual `python3 -c "from lazy_core.docmodel import provisional_eligibility; ..."` on a fixture semantic-conflict sentinel returns `(False, ...)`.

**MCP Integration Test Assertions:** N/A — the classifier and carve-out are pure/hermetic-tested.

**Prerequisites:**
- Phase 2 (the concurrent-writer discriminator signal), Phase 3 (the FIFO lock is the write-conflict retry/queue mechanism).

**Files likely modified:**
- `user/scripts/lazy_core/docmodel.py` — `provisional_eligibility` carve-out + `classify_conflict`.
- `user/skills/_components/sentinel-frontmatter.md`, AlgoBooth `scripts/check-docs-consistency.ts` — schema lockstep.
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — routing prose.
- `tests/test_lazy_core/test_docmodel.py` — coverage.

**Testing Strategy:** Hermetic — inject a git seam into `classify_conflict` so each discriminator branch is deterministic; assert the fail-safe (ambiguous → semantic). The provisional carve-out is a pure predicate test mirroring the existing Spike-FAIL exclusion tests.

**Integration Notes for Next Phase:** The `classify_conflict` verdict is the input to Phase 5's merge-back decision: `write` + large/complex → temp-worktree merge-back; `semantic` → the halt authored here (never reaches merge-back). The semantic marker field chosen here is what the carve-out keys on — keep the field name in one SSOT constant.

---

### Phase 5: Temp-worktree merge-back + cross-agent commit-message-trailer channel

**Scope:** For a large/complex but NON-semantic conflict, the orchestrator completes the work in a temporary worktree and merges it back in queue order, resolving conflicts (Requirement 6, Locked Decisions 3–4). LOCKED to reusing the `lazy_coord.py` lane machinery: spin the temp worktree as a coordinator lane (`lane/<item-id>` + lane marker + fencing lease), do the work there, merge back via `merge_lane_branch` (abort-and-demote on conflict, lane branch preserved, `lanes.json` audit ledger). If this agent beats the conflicting agent to the merge, it COMMUNICATES via a structured `Concurrent-Merge-Back:` commit-message trailer (affected paths + resolution guidance) that the conflicting agent reads in the incoming history it must fetch/rebase to push. Does NOT halt the run. Workstation-only v1 (cloud/bug path documented as a follow-up).

**Deliverables:**
- [ ] Merge-back orchestration wiring (prose in `lazy-batch-parallel/SKILL.md` + any shared helper in `lazy_coord.py`/`lazy_core`): on a `classify_conflict == write` verdict that is large/complex, spin a lane via `lane_branch`/`lane_pool_dir` + `acquire_lease`, complete the work, and `merge_lane_branch` in `merge_order`. Reuse the EXISTING abort-and-demote-on-conflict path — no new merge engine.
- [ ] `Concurrent-Merge-Back:` trailer grammar authored (a documented trailer format: affected paths + one-line resolution guidance) + a helper that composes it into the merging commit's message and a reader that parses it from incoming history. Zero new contended state (Locked Decision 4).
- [ ] Conflict-router prose: the merging agent writes the trailer; the conflicting agent, on the fetch/rebase it must perform to push (Phase 2 git-safety), reads the trailer and applies the guidance — no halt.
- [ ] Tests: `lazy_coord.py --test` — a lane spun for merge-back merges back in queue order; a conflict aborts-and-demotes with the lane branch preserved + a `lanes.json` demotion record. `pytest` for the trailer compose/parse round-trip (compose → parse recovers the affected paths + guidance).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_coord.py --test` exits 0 with the merge-back-in-queue-order + abort-and-demote fixtures green; the trailer compose→parse round-trip test passes.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> A real large non-semantic conflict on the workstation: the temp worktree is created, work merges back, the run CONTINUES (no halt), and the conflicting agent's next fetch/rebase surfaces the `Concurrent-Merge-Back:` trailer. (Workstation-eligible integration observation.)

**MCP Integration Test Assertions:** N/A — no MCP surface.

**Prerequisites:**
- Phase 3 (lane/lease machinery), Phase 4 (the `classify_conflict` verdict gates this path; a `semantic` verdict halts and never reaches here).

**Files likely modified:**
- `user/scripts/lazy_coord.py` — merge-back lane wiring + `--test` fixtures.
- `user/scripts/lazy_core/*.py` — trailer compose/parse helper (if shared) + git-safety fetch/rebase read of the trailer.
- `user/skills/lazy-batch-parallel/SKILL.md` — merge-back orchestration prose + trailer contract.
- `tests/test_lazy_core/` — trailer round-trip coverage.

**Testing Strategy:** Reuse `lazy_coord.py`'s hermetic lane/merge fixtures (the abort-and-demote path is already characterized) + a pure trailer compose/parse round-trip. The live workstation observation is the runtime-verification row (owned by manual/integration testing).

**Integration Notes for Next Phase:** The merge-back path is the concrete demonstration that concurrent work resolves WITHOUT pre-serialization — Phase 6 retires the foreground-await defensiveness precisely because this path (plus the FIFO lock and conflict-routing) now owns conflict correctness. Cloud/bug merge-back is explicitly OUT of v1 scope (documented follow-up).

---

### Phase 6: Orchestrator parallel-dispatch trust — retire the self_edit_mode foreground-await coupling

**Scope:** The orchestrator MUST rely on the coordination layer (Phases 2–5) to resolve write conflicts, not prevent parallel work by pre-serializing dispatches (Requirement 7, Validation row 6). Retire the `self_edit_mode → foreground/await` coupling: a background harden (or any dispatch) that touches claude-config while the run is itself editing claude-config now runs CONCURRENTLY on the shared tree, trusting the FIFO lock + conflict-routing to serialize genuine contention and to halt only on a true semantic conflict. Retire the coupling at `/lazy-batch` §1d.1 (the Concurrency EXCEPTION @899) and its coupled twins `lazy-bug-batch` (@709) and `lazy-batch-cloud`. The awareness note (Phase 1) documents the new trust contract so the defensiveness is not reintroduced.

**Deliverables:**
- [ ] `user/skills/lazy-batch/SKILL.md` §1d.1 Concurrency EXCEPTION (@899): the `self_edit_mode → force foreground/await` serialization is REMOVED and replaced with coordination-layer-trusted concurrent dispatch prose ("no monsters-in-the-closet serialization"; the FIFO lock + conflict-routing own conflict correctness). **The governing-file RELOAD discipline (self-edit C8, @666) is RETAINED UNCHANGED** — a self-edit commit still staleifies the in-context copy; only the pre-serialization is retired.
- [ ] `user/skills/lazy-bug-batch/SKILL.md` (@709) — mirror the retirement (coupled twin; keep the governing-file reload).
- [ ] `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — mirror (coupled twin; keep the reload discipline).
- [ ] Cross-check the coupled-pair prose parity: `python3 user/scripts/lazy_parity_audit.py --repo-root .` stays exit 0; diff each twin after editing (the Coupled Skill Pairs discipline).
- [ ] Tests: lint + doc-drift + projection green; a grep-anchor that the `self_edit_mode → foreground/await` phrasing is GONE from all three sites AND the governing-file reload phrasing is still PRESENT.

**Minimum Verifiable Behavior:** `python3 ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities && python3 ~/.claude/scripts/doc-drift-lint.py --repo-root . && python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0; a grep confirms the foreground-await coupling is removed from lazy-batch/lazy-bug-batch/lazy-batch-cloud while the governing-file reload discipline remains.

**MCP Integration Test Assertions:** N/A — prose-only phase validated by lint/parity/doc-drift.

**Prerequisites:**
- Phases 2–5 (the coordination layer the orchestrator now trusts MUST exist before the defensiveness is retired — retiring it first would leave concurrent conflicts unhandled).

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — retire the foreground-await coupling; keep the reload discipline.

**Testing Strategy:** Deterministic lint/parity/doc-drift gates + a grep-anchor asserting BOTH the removal (foreground-await) and the retention (governing-file reload). Diff each coupled twin against its canonical after editing (Coupled Skill Pairs rule).

**Integration Notes for Next Phase:** Final phase. When this lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) and let the state machine route forward. **Completion (gate-owned):** the `__mark_complete__` gate flips SPEC.md **Status:** to Complete and writes COMPLETED.md once the validation tail passes — never authored as a checkbox here.

---

## KPI note

Both friction KPIs (`concurrent-worktree-false-friction`, `concurrent-worktree-conflict-halts`) declared in SPEC `## KPI Declaration` are `pending` baseline at the stub stage; baselines are captured post-ship via `kpi-scorecard.py --capture-baseline`. Phase 2 (the friction carve-out) is the primary lever for `concurrent-worktree-false-friction`; Phase 4 (non-halting write-conflict routing) is the lever for `concurrent-worktree-conflict-halts`.
