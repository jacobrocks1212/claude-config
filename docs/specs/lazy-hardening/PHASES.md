# PHASES — Lazy System Hardening

> Tracking surface for `user/scripts/plans/lazy-hardening.md`. This is the **persistent
> memory** the executing `/execute-plan` session checks off (`- [ ]` → `- [x]`) and annotates
> with Implementation Notes after each batch. The plan body stays read-only during execution
> per the execute-plan contract — all progress tracking lands here.
>
> **Feature:** Harden the lazy skill family against the 2026-06-10 audit findings: close
> integrity side-doors (model-authored validation sentinels, content-blind receipts), move
> deterministic orchestrator mechanics into the state scripts, fix routing/parser cycle-burn,
> add the parked-decision protocol (park-and-continue + two-key auto-accept + batched flush),
> rebuild lazy-bug-batch by-reference, and add environment/compaction preflights.
>
> **Repo:** claude-config only (`user/skills/**`, `user/scripts/**`,
> `repos/algobooth/.claude/skills/**`). AlgoBooth is used for verification probes only.
>
> **Operator decisions D1–D6 are locked in the plan's Decision Record — do not re-litigate.**

---

## Phase 1 — Test safety net (zero behavior change)

**Goal:** Byte-pinned `--test` baseline + missing fixtures for `bug-state.py` before any
behavior changes land.

**Entry criteria:** None — first phase.

**Deliverables:**
- [x] `user/scripts/tests/baselines/bug-state-test-baseline.txt` + durable matching test
- [x] Cloud-mode fixtures (currently zero `cloud=True` coverage)
- [x] Device re-open fixture (`STEP_DEVICE_REOPEN`)
- [x] Step-9 `SKIP_MCP_TEST.md` / `MCP_TEST_RESULTS.md` fixtures
- [x] `backfill_receipts` fixture; severity-ordering fixture (multiple unlisted bugs)
- [x] Stale harness docstrings cleaned (both scripts)
- [x] AlgoBooth `--repo-root` JSON baseline for bug-state.py

**Runtime Verification:**
- [x] `python3 ~/.claude/scripts/lazy-state.py --test` exits 0
- [x] `python3 ~/.claude/scripts/bug-state.py --test` exits 0 and matches baseline
- [x] `python3 ~/.claude/scripts/test_lazy_core.py` exits 0

**Implementation Notes:**

#### Implementation Notes (Phase 1 — Batch 1: WU-1, WU-2)
**Completed:** 2026-06-10
**Review verdict:** PASS (independent Opus reviewer; ground-truth verified clean, zero-drift byte-identical both scripts)
**Work completed:**
- WU-1 (`bug-state-test-baseline.txt` + durable matching test): bug-state.py already had a `--test`/`run_smoke_tests` mode (the plan's "add/confirm" — confirmed present). Added `test_bug_state_test_output_matches_baseline` to `test_lazy_core.py` and captured the golden baseline. bug-state `--test` output is naturally platform-neutral (no temp paths emitted).
- WU-1 (folded-in preexisting defect): the existing `test_lazy_state_test_output_matches_baseline` was RED on this Windows host — the committed baseline was Linux-captured + stale (missing newer fixtures), and the normalization only handled the random tempdir suffix, not the OS temp-root prefix or `\`-vs-`/` separators. Added a shared `_normalize_smoke_output()` helper (3-step, idempotent, canonicalizes suffix + temp-root → `<TMP>/` + separators), refactored the lazy-state test to use it, regenerated `lazy-state-test-baseline.txt` in canonical form, and added `test_normalize_smoke_output_is_platform_neutral` (proves Windows/POSIX forms canonicalize identically — cross-platform is now a TESTED contract, not a design claim).
- WU-2 (`bug-state-algobooth.json`): captured the `bug-state.py --repo-root <AlgoBooth>` reference snapshot + README section. Per the lazy-state-algobooth.json precedent (README: drift-tolerant same-session reference, deliberately NOT value-asserted), the durable test `test_bug_state_algobooth_baseline_wellformed` asserts only structural well-formedness (parses + 6 core keys), and the byte-identical *value* check is the orchestrator's phase-time zero-drift probe — not a rotting pytest. This reconciles the plan's "a test asserting current output matches it" against the precedent it told us to mirror.
**Integration notes:**
- `_normalize_smoke_output` is the shared canonicalizer for BOTH scripts' baselines — WU-3 (Batch 2) regenerates `bug-state-test-baseline.txt` through it after adding fixtures.
- Full suite is 82/82; the 3 new tests are registered in `_TESTS` (lines ~1480/1482/1484).
- Zero-behavior-change confirmed: `lazy-state.py`/`bug-state.py` unmodified in the working tree; `--repo-root` output byte-identical to phase-start for both.
**Pitfalls & guidance:**
- The lazy-state baseline can only be regenerated correctly by piping live `--test` output through `_normalize_smoke_output` (never hand-edit) — otherwise byte-identity breaks subtly on the temp-path line.
- Two new test docstrings still carry stale "intentionally RED until baseline created" narrative (now GREEN). Deferred to WU-4 (Batch 3 — "stale harness docstrings cleaned") rather than an extra dispatch.
**Files modified:**
- `user/scripts/test_lazy_core.py` — `_normalize_smoke_output` helper + lazy-state test refactor + 3 new tests + registry entries
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt` — regenerated (canonical, platform-neutral)
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` — new golden capture
- `user/scripts/tests/baselines/bug-state-algobooth.json` — new reference snapshot
- `user/scripts/tests/baselines/README.md` — new `bug-state-algobooth.json` section

#### Implementation Notes (Phase 1 — Batch 2: WU-3)
**Completed:** 2026-06-10
**Review verdict:** PASS (independent Opus reviewer; each fixture's tree→branch→assertion traced; additive-only below banner; baseline byte-identical + deterministic + date-free)
**Work completed:**
- Added 7 smoke fixtures to `bug-state.py`'s SMOKE FIXTURES section (below the line-853 test-agent banner), covering all 4 PHASES checkboxes: `cloud-defer-mcp` + `cloud-skip-mcp` (first-ever `cloud=True` coverage → `STEP_CLOUD_DEFER_MCP`/`__write_deferred_non_cloud__` and `STEP_MCP_SKIP`/`__write_validated_from_skip__`); `device-reopen` (`STEP_DEVICE_REOPEN`/`mcp-test`, real-device twin of the no-device `device-deferred` fixture); `step9-skip-mcp` + `step9-mcp-results` (workstation Step-9 sentinel paths → skip and `Step 9b: write validated`/`__write_validated_from_results__`); `severity-ordering` (unlisted on-disk P0 picked before P2 by `_SEVERITY_RANK`); `backfill-receipts-direct` (bespoke block: Fixed-without-FIXED.md backfilled, Won't-fix exempt).
- Regenerated `bug-state-test-baseline.txt` through `_normalize_smoke_output` to absorb the 7 new PASS lines.
**Integration notes:**
- These fixtures characterize CURRENT `compute_state` behavior. Phase 2's cloud Step-9 hard-halt / receipt-content-validation changes WILL legitimately shift `cloud-defer-mcp` and the receipt fixtures — that is the intended early-warning (regenerate the baseline as part of those phases).
- RED→GREEN was demonstrated for `cloud-defer-mcp` and `device-reopen` (deliberately-wrong expectation → captured FAIL → corrected to GREEN).
- `severity-ordering` is deliberately constructed so the higher-severity bug has the LATER Discovered date — a date-only (severity-blind) sort would flip the result, so the test is non-tautological.
**Pitfalls & guidance:**
- `backfill_receipts` uses `datetime.now()`; the fixture asserts only the return dict + FIXED.md existence and prints no date, so the baseline does not rot daily.
- Zero behavior change verified: diff is purely additive (+343/-0), all hunks below the line-853 banner; `--repo-root` zero-drift probe byte-identical to phase-start for both scripts.
**Files modified:**
- `user/scripts/bug-state.py` — 7 new smoke fixtures (SMOKE FIXTURES section only)
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` — regenerated

#### Implementation Notes (Phase 1 — Batch 3: WU-4 + Post-Phase)
**Completed:** 2026-06-10
**Review verdict:** PASS (inline review — comment/docstring-only diff fully visible + mechanically verified; zero-drift byte-identical both scripts; baselines still match; suite 82/82)
**Work completed:**
- WU-4 (stale harness docstrings cleaned, both scripts): rewrote the `run_smoke_tests()` docstring in `bug-state.py` (dropped the "compute_state() is a stub / expected RED state for WU-2.1" narrative — compute_state is fully implemented) and updated 4 stale `#` comments there + 2 in `lazy-state.py` (scope_feature_id "does not exist yet" / "RED") to describe the now-implemented state and label the surviving `except NotImplementedError`/`except TypeError` clauses as dead defensive guards. Also cleaned the 2 deferred Batch-1 test docstrings + their inline read-comments in `test_lazy_core.py` ("intentionally RED until baseline created" → GREEN steady-state contract).
- **Comment/docstring-only**: every changed line is a `#` comment or `"""docstring"""`; NO executable line, printed string literal (the `failures.append(... "stub not yet implemented" ...)` f-strings were left verbatim), or `except` branch was touched. Verified mechanically (no `failures.append`/`print`/`def`/`return`/assignment lines in the diff) and by byte-identical zero-drift.
- **Post-Phase docs**: updated `user/scripts/CLAUDE.md` Testing section and `user/scripts/tests/baselines/README.md` to document the new `bug-state-test-baseline.txt` byte-pin and the shared cross-platform `_normalize_smoke_output` mechanism (temp-suffix + temp-root + separator canonicalization → platform-neutral baselines across Windows/WSL).
**Integration notes:**
- Integration verification: no module wiring occurred (this phase adds only test data, a baseline mechanism, and comment cleanup) — nothing previously isolated was connected. The baseline tests ARE full-stack (subprocess → script → observable stdout → byte assertion), so external-output coverage exists for the only "user-facing API" touched (`--test`/`--repo-root`).
- Final phase gate: all 3 regression gates exit 0; both scripts' `--repo-root` output byte-identical to phase-start (zero behavior change); full `test_lazy_core.py` suite 82/82.
**Pitfalls & guidance:**
- The `except NotImplementedError`/`except TypeError` guards in both smoke harnesses are dead code (compute_state/enqueue_adhoc/scope kwargs are implemented) but were RETAINED — WU-4 was scoped to comments only, so removing executable branches was out of scope.
**Files modified:**
- `user/scripts/bug-state.py` — docstring + 4 stale comments (comments/docstring only)
- `user/scripts/lazy-state.py` — 2 stale scope comments (comments only)
- `user/scripts/test_lazy_core.py` — 3 stale test docstrings + 2 inline comments (docstring/comments only)
- `user/scripts/CLAUDE.md` — Testing section (bug-state baseline + cross-platform normalization)
- `user/scripts/tests/baselines/README.md` — bug-state-test-baseline.txt section + shared normalization note

---

## Phase 2 — Integrity side-doors (P0)

**Goal:** No model-authorable path to VALIDATED/SKIP/receipts; content-validated receipts;
cloud gates in bug-state; standing-directive confirmation.

**Entry criteria:** Phase 1 baselines green.

**Deliverables:**
- [x] `lazy_core.has_completion_receipt()` validates frontmatter (`kind:`, `provenance:`); malformed → treated missing + diagnostic
- [x] bug-state cloud Step-2 skip + Step-10 hard-halt (mirror lazy-state); dead terminals resolved
- [ ] Unqueued Fixed-no-receipt bypass closed (uniform receipt gate or diagnostic)
- [x] `MCP_TEST_RESULTS.md` commit-sha freshness check before `__write_validated_from_results__`
- [ ] `SKIP_MCP_TEST.md` `granted_by: operator|pipeline`; coverage-audit + `__write_validated_from_skip__` honor it
- [x] D6: LOOP-DETECTED block restricted to NEEDS_INPUT/BLOCKED (all 3 orchestrators) + stale anchor fixed
- [x] Step 1e.4a: no evidence-less verification-box ticking; mismatch → NEEDS_INPUT
- [ ] Input-audit runs after needs-input/blocked spec cycles; >4-decision overflow → durable follow-up NEEDS_INPUT
- [ ] Standing-directive echo-back protocol; no early stop with budget+queue remaining; non-integer max_cycles rejected with question
- [ ] D5: mcp-test inline-fix policy (test-first, disclosed, never self-certifies) in prompt overrides

**Runtime Verification:**
- [ ] All three regression gates green
- [ ] New fixtures: empty receipt → completion-unverified; cloud deferral → halt not `__mark_fixed__`; stale-sha results → no validation; pipeline-granted skip → NEEDS_INPUT

**Implementation Notes:**

#### Implementation Notes (Phase 2 — Batch 1: WU-1, WU-2, WU-4, WU-6)
**Completed:** 2026-06-10
**Review verdict:** PASS-WITH-FIXES (orchestrator review; all subagent ground-truth blocks independently re-run and diffed; one falsified subagent claim caught + corrected — see below)
**Work completed:**
- **WU-1** (`lazy_core.has_completion_receipt`): replaced the bare `.exists()` with content validation — a present receipt now counts ONLY if `parse_sentinel` yields `kind ∈ {completed, fixed}` AND a non-empty `provenance:`. Absent file → `False` silently; present-but-malformed → `_diag(...)` loud diagnostic + treated as missing (so `completion-unverified` still halts). Closes the `touch COMPLETED.md` side-door. 9 new unit tests in `test_lazy_core.py` (7 RED→GREEN + 2 positive guards incl. the `FIXED.md`/`kind: fixed` variant); existing `test_has_completion_receipt_present` updated to write a valid receipt.
- **WU-2** (`bug-state.py` cloud guards + dead terminals): mirrored lazy-state's two cloud guards — (1) Step-2 cloud-saturated skip (`cloud` + RETRO_DONE.md + DEFERRED_NON_CLOUD.md + no VALIDATED.md → `cloud_saturated_skipped` + continue) and (2) Step-10 defensive cloud hard-halt — so a cloud bug with DEFERRED_NON_CLOUD.md and no VALIDATED.md HALTS (`cloud-queue-exhausted`) instead of falling through to `__mark_fixed__` (archive-with-zero-validation). Both previously-dead terminals are now WIRED: `TR_CLOUD_QUEUE_EXHAUSTED` (cloud-saturated terminal + Step-10 halt) and `TR_QUEUE_MISSING` (emitted when `docs/bugs/queue.json` is entirely absent, distinct from all-bugs-fixed). New fixtures `cloud-defer-no-validate-halts` (RED→GREEN) and `queue-json-missing`; `bug-state-test-baseline.txt` regenerated via `_normalize_smoke_output`.
- **WU-4** (`lazy-state.py` MCP-results sha freshness): added best-effort `_current_head(repo_root)` (git `rev-parse HEAD`, `None` on non-repo) and a freshness gate in the workstation Step-9 all-passing branch — when HEAD is known AND `MCP_TEST_RESULTS.md`'s `validated_commit` differs, route to `sub_skill: mcp-test` ("Step 9: stale MCP results — re-verify") instead of `__write_validated_from_results__`. Backward-compatible: head unknown OR `validated_commit` absent → check skipped (preserves all other fixtures). `validated_commit` field added to the `MCP_TEST_RESULTS.md` schema in `sentinel-frontmatter.md`. New git-initialized fixture `stale-mcp-results-reverify` (RED→GREEN); `lazy-state-test-baseline.txt` regenerated (two-run determinism confirmed — no sha leakage).
- **WU-6** (D6 LOOP-DETECTED + Step 1e.4a, prose): in all 3 batch SKILLs the LOOP-DETECTED loop-breaker's "write the missing sentinel directly" license was removed and replaced with the locked-D6 allow-list — a loop-breaker may author ONLY `NEEDS_INPUT.md`/`BLOCKED.md`, never `VALIDATED.md`/`SKIP_MCP_TEST.md`/`RETRO_DONE.md`/receipts. The stale base-prompt anchor in lazy-batch (`"follow the skill's internal subagent-vs-orchestrator rules."` — no longer present) was repointed to the base prompt's real closing sentence. Step 1e.4a recovery now forbids evidence-less verification-box ticking: a box may be ticked only with on-disk evidence (`VALIDATED.md`/`MCP_TEST_RESULTS.md`); on mismatch the recovery writes `NEEDS_INPUT.md`. FULL treatment on lazy-batch + lazy-batch-cloud; MINIMAL inline patch on lazy-bug-batch (per Rule 10 — Phase 6 rebuilds it).
**Ground-truth verification:** All four agents produced GROUND-TRUTH blocks; orchestrator independently re-ran every block's commands and diffed (LOC/grep/status/test-counts all matched). **One falsified claim caught:** the WU-4 impl-agent reported 3 failing `test_derive_stage_done_*` tests as "pre-existing WIP." `git show HEAD:` proved they were committed and part of the 82/82 green baseline — they were broken by WU-1's tightening (`derive_stage` consumes `has_completion_receipt`). This is a propagation failure WU-1 should have caught; fixed via a dedicated Sonnet fix-agent that updated the 3 derive_stage fixtures to write VALID receipts (intent-preserving) → suite now 91/91.
**Fixes applied by orchestrator:** removed two untracked junk files (`...Temprun1.txt`/`run2.txt`) the WU-4 agent accidentally created via a redirect mishap.
**Integration / follow-up notes:**
- **WU-4 producer gap (follow-up):** the freshness gate is the CONSUMER half. It stays backward-compatibly inert until the `MCP_TEST_RESULTS.md` PRODUCER (the `/mcp-test` results writer / mcp-integration-test path) populates `validated_commit`. Per the plan WU-4 file-list (`lazy-state.py` + `sentinel-frontmatter.md` only) the producer-wiring was deliberately NOT done here — flagged for a follow-up (natural fit for the Phase 6 contradiction sweep). No regression: absent-field path == prior behavior.
- All three regression gates exit 0 after this batch.
**Files modified:** `user/scripts/lazy_core.py`, `user/scripts/bug-state.py`, `user/scripts/lazy-state.py`, `user/scripts/test_lazy_core.py`, `user/scripts/tests/baselines/bug-state-test-baseline.txt`, `user/scripts/tests/baselines/lazy-state-test-baseline.txt`, `user/skills/_components/sentinel-frontmatter.md`, `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`

---

## Phase 3 — Routing & parser fixes

**Goal:** Eliminate the state-script blind spots that burn Opus cycles.

**Entry criteria:** Phase 1 baselines green (Phase 2 independent).

**Deliverables:**
- [ ] bug-state emits `plan-bug` on concluded investigation (conclusion marker documented in SPEC template); lazy-bug-batch description updated
- [ ] Fence-aware `- [ ]` parsing in `count_deliverables` / `remaining_unchecked_are_verification_only` / `_unchecked_wus_in_plan_scope` (+ fixture fix)
- [ ] Verification-only heuristic anchored to `## Runtime Verification` heading (no bold-marker clash)
- [ ] Verification-row placement convention pinned in write-plan component / PHASES template
- [ ] `roadmap_marks_complete` / `upstream_is_complete` / `is_stub_spec` anchored (no substring collisions)
- [ ] Stale already-applied plan → inline flip pseudo-action (not execute-plan)
- [ ] D3: split forward/meta counters (meta ceiling 2× max_cycles) + cap check at top of every resolution mode; halt-resolution.md claim fixed
- [ ] `scoped-id-not-found` terminal; diagnostics for malformed queue entries
- [ ] Realign mtime gate → recorded upstream-PHASES hash; `check_stale_upstream` wired to CLI/probe; Step-10 unexpected-state writes its NEEDS_INPUT.md

**Runtime Verification:**
- [ ] Regression gates green
- [ ] Fixtures: concluded investigation → plan-bug; fenced checkboxes ignored; substring-collision row → no false halt; stale plan → flip; typo'd scope id → scoped-id-not-found

**Implementation Notes:**

---

## Phase 4 — Parked-decision protocol + notifications (D1/D2)

**Goal:** Opt-in park-and-continue (`--park` skill flag) with batched flush; two-key
auto-accept (`--park` mode only); push on every park/halt in both modes. **Default (no flag)
behavior stays byte-for-byte the existing halt-and-wait.**

**Entry criteria:** Phase 3 (split counters land first — flush/park reporting uses them).

**Deliverables:**
- [ ] `--park` skill invocation flag parsed in all 3 batch orchestrators; recorded in start banner + final report; no flag → existing Step 1g halt behavior unchanged
- [ ] Script `--park-needs-input` mode + `parked[]` output array, passed only when skill got `--park` (wrappers keep halt behavior; probe output unchanged without the flag)
- [ ] PushNotification at every park / halt / flush / run end (both modes)
- [ ] D1 flush protocol (`--park` only): batched AskUserQuestion (≤4/call, Zero-Context Briefing preserved) at first opportunity (operator message / out of unparked work / run end); decision-apply per answer
- [ ] D2 two-key auto-accept (`--park` only): `class: mechanical` + input-audit concurrence → recommended option auto-accepted, `resolved_by: auto-two-key`, receipt log + run-end digest; any disagreement → product → park; no auto-accept ever without `--park`
- [ ] Cache-boundary note documented in both batch skills

**Runtime Verification:**
- [ ] Default-mode regression: without `--park-needs-input`, a NEEDS_INPUT fixture still emits the `needs-input` halt (probe output byte-identical to Phase 1 baseline)
- [ ] Fixtures: with the flag, `parked[]` populated, parked item skipped not halted, resolved sentinel re-enters
- [ ] lazy-batch-retro checklist additions: parks fire notifications; flush count matches parked count; every auto-accept carries two keys + digest entry; zero parks/auto-accepts in no-flag runs

**Implementation Notes:**

---

## Phase 5 — Script-ification of the orchestrator loop

**Goal:** ≤3 orchestrator messages per happy-path cycle.

**Entry criteria:** Phases 1–2 (receipt validation must precede `--apply-pseudo`).

**Deliverables:**
- [ ] `--verify-ledger <spec_path>` (replaces 5 prose blocks)
- [ ] `--apply-pseudo <name> <spec_path>` for all deterministic sentinel/receipt writes; receipt-write ownership contradiction resolved (script is single author)
- [ ] `--neutralize-sentinel <path>` with collision handling
- [ ] Persisted probe signature → `repeat_count` in output
- [ ] Probe payload includes git-guard results + pre-formatted cycle header
- [ ] Both batch skills consume subcommands; superseded prose deleted

**Runtime Verification:**
- [ ] Regression gates green
- [ ] Fixtures per subcommand: each verify-ledger failing check; apply-pseudo idempotency + gate-absent refusal; neutralize collision; repeat_count increments

**Implementation Notes:**

---

## Phase 6 — Fork rebuild + contradiction sweep (D4)

**Goal:** One source of truth per rule; lazy-bug-batch by-reference; lazy-batch componentized.

**Entry criteria:** Phases 2, 4, 5 (rebuild inherits their canonical lazy-batch text).

**Deliverables:**
- [ ] D4: lazy-bug-batch rebuilt by-reference (cloud pattern) — ports Step 1d.0 pre-boot + NO-FIRE-AND-FORGET, `__mark_fixed__` gate parity (wrapper too), Step 1.5 exclusion parity, 1d.5 dual-trigger wording; six `!cat`s → path references
- [ ] lazy-batch prompt templates + announcement templates extracted to `_components/lazy-batch-prompts/` (read on demand); Step 1f/Step 4 announcement deduped
- [ ] sentinel-frontmatter.md no longer `!cat` in thin wrappers; mark-fixed-archive nested-`!cat` fixed; batch-skill frontmatter descriptions trimmed
- [ ] Contradiction sweep: cloud constraint renumbering + Step 8/9 drift + lazy-status rows; lazy-batch stale Notes/refs + HARD CONSTRAINT 5 exceptions; sentinel lifecycle table rename-not-delete; component coupling notes include bug consumers; plan-feature artifact; lazy step-label collision
- [ ] lazy-batch-retro: workstation inline-override branch; R-O-3 exceptions; R-O-6 fix; Step 3 scan list; Notes path; Phase-4 park/auto-accept checks

**Runtime Verification:**
- [ ] Regression gates green
- [ ] Grep: every path reference resolves; zero sentinel-frontmatter `!cat` in wrappers
- [ ] Compliance read of rebuilt lazy-bug-batch against a dry-run (retro-style checklist)

**Implementation Notes:**

---

## Phase 7 — Environment & compaction hardening

**Goal:** Runs never die on preconditions; post-compact dispatch fidelity.

**Entry criteria:** None (independent; can run any time after Phase 1).

**Deliverables:**
- [ ] Step 0 preflight (symlink, python3, scripts, node) before banner in batch skills + wrappers; failure prints setup recipe, zero cycles consumed
- [ ] Windows node path (`/c/nvm4w/nodejs`) baked into preflight/skill-config
- [ ] Compaction protocol: on-disk canonical dispatch template re-read after compact; Read-before-Edit rule
- [ ] Long-build ownership rule (orchestrator-owned harness-tracked) + `cargo check --release` pre-flight
- [ ] `interview_work_log_append` purged from all dispatch templates; canonical-sentinel-filename + work-branch clauses added to base dispatch prompt

**Runtime Verification:**
- [ ] Simulated DOA conditions (missing symlink / shadowed python3) caught by preflight with recipe
- [ ] `grep -r interview_work_log_append user/skills/` returns nothing

**Implementation Notes:**
