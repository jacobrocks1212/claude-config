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
- [x] Unqueued Fixed-no-receipt bypass closed (uniform receipt gate or diagnostic)
- [x] `MCP_TEST_RESULTS.md` commit-sha freshness check before `__write_validated_from_results__`
- [x] `SKIP_MCP_TEST.md` `granted_by: operator|pipeline`; coverage-audit + `__write_validated_from_skip__` honor it
- [x] D6: LOOP-DETECTED block restricted to NEEDS_INPUT/BLOCKED (all 3 orchestrators) + stale anchor fixed
- [x] Step 1e.4a: no evidence-less verification-box ticking; mismatch → NEEDS_INPUT
- [x] Input-audit runs after needs-input/blocked spec cycles; >4-decision overflow → durable follow-up NEEDS_INPUT
- [x] Standing-directive echo-back protocol; no early stop with budget+queue remaining; non-integer max_cycles rejected with question
- [x] D5: mcp-test inline-fix policy (test-first, disclosed, never self-certifies) in prompt overrides

**Runtime Verification:**
- [x] All three regression gates green
- [x] New fixtures: empty receipt → completion-unverified; cloud deferral → halt not `__mark_fixed__`; stale-sha results → no validation; pipeline-granted skip → NEEDS_INPUT

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

#### Implementation Notes (Phase 2 — Batch 2: WU-3, WU-5, WU-7)
**Completed:** 2026-06-10
**Review verdict:** PASS (orchestrator review; all ground-truth blocks independently re-run; gates green; combined-tree coherence confirmed after a concurrent-edit stash maneuver — see process note)
**Work completed:**
- **WU-3** (`bug-state.py` unqueued Fixed-no-receipt bypass): `_find_open_bug_dirs` previously dropped EVERY dir whose status ∈ `_BUG_DONE_STATUSES` before any receipt check, so an unqueued on-disk bug flipped to Fixed without a `FIXED.md` receipt bypassed the gate entirely. Now special-cased: `Won't-fix` → skip (receipt-exempt); `Fixed` WITH a valid `FIXED.md` (`has_completion_receipt`) → skip (genuinely done); `Fixed` WITHOUT receipt → surfaced (`_diag` + returned) so the queue-walk gate fires `completion-unverified` — uniform with the queued path. Reuses the now-content-validating `has_completion_receipt` (a `touch FIXED.md` won't satisfy it). New fixture `unqueued-fixed-no-receipt-halt` (RED→GREEN); `bug-state-test-baseline.txt` regenerated. `wont-fix-exempt` + `fixed-no-receipt-halt` unregressed.
- **WU-5** (`lazy-state.py` SKIP_MCP_TEST provenance): both `__write_validated_from_skip__` emission sites (cloud Step-9 + workstation Step-9) now parse `SKIP_MCP_TEST.md` and refuse `granted_by: pipeline` → route to `needs-input` (a pipeline-self-granted skip can't vacuously validate; needs operator confirmation). Backward-compatible: absent / `operator` / non-`pipeline` → unchanged validate-from-skip. `granted_by: operator|pipeline` added to the `SKIP_MCP_TEST.md` schema in `sentinel-frontmatter.md`; `mcp-coverage-audit.md` step 2 now treats only `operator` (or absent) grants as a legitimate vacuous-pass, a `pipeline` grant as uncovered → surface. New fixtures `skip-pipeline-granted-needs-input` (RED→GREEN) + `skip-operator-granted-validates` (positive guard); `lazy-state-test-baseline.txt` regenerated.
- **WU-7** (input-audit + standing-directive, prose; FULL on lazy-batch, MINIMAL on lazy-bug-batch): (A) Step 1d.5 now runs after EVERY `/spec`|`plan-feature` cycle before the next state probe — a subsequent `needs-input`/`blocked` routing no longer exempts the cycle's audit (double-fire guard preserved). (B) >4-decision audit overflow now persists as durable follow-up `NEEDS_INPUT.md` sentinels (re-surface via Step 1g) instead of a buried `## Open Questions` body. (C) Standing-directive echo-back: a mid-run operator message implying a budget change / standing resolution mode / early stop must be confirmed via ONE `AskUserQuestion` before the mode takes effect; the orchestrator must never end a run with budget AND queue both remaining without asking. (D) Ambiguous/non-integer `max_cycles` (e.g. "infinity") → ONE clarifying `AskUserQuestion`, never a silent coerce. HARD CONSTRAINT 5 updated to enumerate the two new permitted orchestrator-level `AskUserQuestion` uses. lazy-batch-cloud confirmed already by-reference for Step 1d.5 (no edit needed, no follow-up).
**Ground-truth verification:** All three agents produced GROUND-TRUTH blocks; orchestrator independently re-ran all three regression gates (exit 0), the full `test_lazy_core.py` suite (91/91), `git stash list` (empty — no residue), and read the substantive `_find_open_bug_dirs` and lazy-batch prose edits. No falsified claims.
**Process note:** the WU-3 agent used a transient `git stash`/`stash pop` to isolate the working tree from WU-5's concurrent lazy-state edits. It left no residue (empty stash list) and the combined tree is coherent (all gates green, all eight expected files present + correct). No harm; flagged so future concurrent batches avoid in-agent stashing.
**Follow-up notes (carried from Batch 1 + new):**
- WU-4 producer gap (validated_commit recording by the MCP_TEST_RESULTS.md producer) still open — Phase 6 candidate.
- bug-state.py has its own `__write_validated_from_skip__` skip paths (Step 9, ~704-720) that do NOT yet honor `granted_by` — WU-5 was scoped to lazy-state.py only per the plan. Flagged for the lazy-bug-batch rebuild / a future parity pass (Phase 6).
**Files modified:** `user/scripts/bug-state.py`, `user/scripts/lazy-state.py`, `user/scripts/tests/baselines/bug-state-test-baseline.txt`, `user/scripts/tests/baselines/lazy-state-test-baseline.txt`, `user/skills/_components/sentinel-frontmatter.md`, `user/skills/_components/mcp-coverage-audit.md`, `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`

#### Implementation Notes (Phase 2 — Batch 3: WU-8 + Post-Phase)
**Completed:** 2026-06-10
**Review verdict:** PASS (inline review — 2 files, 30 insertions, ≤150 lines; prose-only, ground-truth verified by grep + reading the inserted D5 block)
**Work completed:**
- **WU-8** (D5 mcp-test inline-fix policy, prose): added the locked-D5 inline-fix policy to the `/mcp-test` per-skill override in both batch SKILLs. A mcp-test cycle MAY fix production code inline ONLY (1) test-first (failing test written + confirmed RED first) and (2) fully disclosed (files/change/pinning-test named in the cycle summary); (3) a cycle that modified production code MUST NOT write `VALIDATED.md` — it ends in a needs-re-verify state (`MCP_TEST_RESULTS.md` flagging the production change, or `BLOCKED.md`); (4) only a SUBSEQUENT clean `/mcp-test` cycle (no production edits) certifies via `VALIDATED.md`. The existing NO-FIRE-AND-FORGET sentinel-contract clause was updated with the matching "VALIDATED.md on full pass UNLESS you modified production code this cycle" exception so it reads coherently. FULL on lazy-batch (numbered 1–4 block); MINIMAL terse suffix on lazy-bug-batch (per Rule 10). Closes the self-certification side-door where one cycle both changes and validates its own un-reviewed code.
**Ground-truth verification:** prose WU (TDD:no) — no test runner applies; verified by independent grep (D5 language present in both files at the expected sites) + reading the inserted block for coherence with the surrounding sentinel contract.

#### Post-Phase (Phase 2 — Integration Verification + part close)
**Integration verification:** the five integrity gates cohere as one system —
(1) content-validated receipts (`has_completion_receipt`, WU-1) feed both the lazy-state Step-2 and bug-state Fixed-receipt completion gates AND `derive_stage`; (2) the bug-state cloud guards (WU-2) + the unqueued-Fixed gate (WU-3) make bug-state's completion enforcement uniform with lazy-state's; (3) the MCP-results sha-freshness gate (WU-4) + SKIP_MCP_TEST `granted_by` provenance (WU-5) close the two "validate from stale/self-granted evidence" side-doors; (4) the loop-breaker sentinel restriction + 1e.4a evidence gate (WU-6) prevent recovery subagents from authoring validation sentinels; (5) the mcp-test inline-fix policy (WU-8) prevents a cycle self-certifying its own code change. The orchestrator-facing WU-6/WU-7/WU-8 skill edits are FULL on lazy-batch + lazy-batch-cloud (cloud's Step 1d.5 is by-reference) and MINIMAL on lazy-bug-batch — Phase 6 rebuilds lazy-bug-batch by-reference and inherits the canonical lazy-batch text (per the plan's accepted "Phase 2 edits text Phase 6 later replaces" risk note).
**Part-end full quality gate (MANDATORY, all exit 0):** `python3 ~/.claude/scripts/lazy-state.py --test` (0), `python3 ~/.claude/scripts/bug-state.py --test` (0), `python3 ~/.claude/scripts/test_lazy_core.py` (91/91, 0). Run + passed as the final chained command before the part-close commit.
**Carried follow-ups (Phase 6 candidates, NOT blocking part close):**
- WU-4 producer gap: the `MCP_TEST_RESULTS.md` producer (`/mcp-test` results writer) must populate `validated_commit` for the freshness gate to be active in production (gate is backward-compatibly inert until then; no regression).
- bug-state.py `__write_validated_from_skip__` paths (Step 9) do not yet honor `granted_by` (WU-5 was lazy-state-scoped per the plan).
- CLAUDE.md review: `user/scripts/CLAUDE.md` testing section already documents the baseline mechanism (Phase 1); no new doc wiring warranted by Phase 2's guard/validation additions (no new public surface).
**Files modified:** `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`

---

## Phase 3 — Routing & parser fixes

**Goal:** Eliminate the state-script blind spots that burn Opus cycles.

**Entry criteria:** Phase 1 baselines green (Phase 2 independent).

**Deliverables:**
- [x] bug-state emits `plan-bug` on concluded investigation (conclusion marker documented in SPEC template); lazy-bug-batch description updated
- [x] Fence-aware `- [ ]` parsing in `count_deliverables` / `remaining_unchecked_are_verification_only` / `_unchecked_wus_in_plan_scope` (+ fixture fix)
- [x] Verification-only heuristic anchored to `## Runtime Verification` heading (no bold-marker clash)
- [x] Verification-row placement convention pinned in write-plan component / PHASES template
- [x] `roadmap_marks_complete` / `upstream_is_complete` / `is_stub_spec` anchored (no substring collisions)
- [x] Stale already-applied plan → inline flip pseudo-action (not execute-plan)
- [x] D3: split forward/meta counters (meta ceiling 2× max_cycles) + cap check at top of every resolution mode; halt-resolution.md claim fixed
- [x] `scoped-id-not-found` terminal; diagnostics for malformed queue entries
- [x] Realign mtime gate → recorded upstream-PHASES hash; `check_stale_upstream` wired to CLI/probe; Step-10 unexpected-state writes its NEEDS_INPUT.md

**Runtime Verification:**
- [x] Regression gates green
- [x] Fixtures: concluded investigation → plan-bug; fenced checkboxes ignored; substring-collision row → no false halt; stale plan → flip; typo'd scope id → scoped-id-not-found

**Implementation Notes:**

#### Implementation Notes (Phase 3 — Batch 1: WU-1, WU-2, WU-3, WU-4)
**Completed:** 2026-06-10
**Review verdict:** PASS-WITH-FIXES → fixes applied → PASS (dedicated Opus reviewer; orchestrator independently re-ran all 3 gates + diffed every subagent GROUND-TRUTH block — all matched, no falsified reports, HEAD unchanged so no rogue commits)
**Work completed:**
- **WU-1** (plan-bug wiring, TDD): `bug-state.py` `compute_state()` Step 4 now reads `spec_status(spec_dir)` (already imported from `lazy_core`, line-anchored `^**Status:**` match) and emits `sub_skill="plan-bug"` (new constant `SKILL_PLAN_BUG`, line 114; emit at ~692) when SPEC `**Status:** Concluded` AND no PHASES.md — instead of looping `spec-bug`. Any other status (e.g. `Investigating`) → unchanged `spec-bug`. Two smoke fixtures (`concluded-investigation-plan-bug` RED→GREEN; `concluded-investigation-guard-still-spec-bug` discriminating guard). `lazy-bug-batch/SKILL.md` frontmatter + body (~454) updated: bug-state now emits `plan-bug` (still never `plan-feature`). **Loop closed end-to-end (review fix):** `spec-bug/SKILL.md` Step 6 now WRITES `**Status:** Concluded` at a proven conclusion (interactive + `--batch` paths); unconcluded batch runs leave `Investigating` + write `NEEDS_INPUT.md` (never falsely Concluded). `plan-bug/SKILL.md` Status gate now lists `Concluded` as a proceed-state. Verified wiring is NOT a dead-end: `lazy-bug-batch` dispatches `{sub_skill}` generically and `/plan-bug` exists.
- **WU-2** (fence-aware + bold-clash parsing, TDD): `lazy_core.py` `count_deliverables`, `remaining_unchecked_are_verification_only`, `_unchecked_wus_in_plan_scope` now track an `in_fence` flag (toggle on `stripped.startswith("```")`, handles ```` ```lang ````) and skip `- [ ]`/`- [x]` lines inside code fences. The verification-only heuristic no longer treats a NON-verification bold (`**Assessment:**`) as a scope boundary — only verification-pattern bolds/headings enter scope; `**Runtime Verification**`/`**MCP Integration Test Assertions:**` bold markers still recognized (backward-compat). 9 unit tests in `test_lazy_core.py` (6 RED→GREEN + 3 backward-compat guards incl. the non-tautological "real task outside → False" discriminator).
- **WU-3** (placement convention, docs): `_components/phases-runtime-verification.md` + `write-plan/SKILL.md` pin the rule that runtime-verification `- [ ]` checkboxes live ONLY under `## Runtime Verification` (or the `**Runtime Verification**`/`**MCP...**` bold subsection), NEVER under a phase's `### Deliverables`; fenced rows are illustrative. This is the convention WU-2's heuristic depends on.
- **WU-4** (substring anchoring, TDD): `lazy-state.py` `roadmap_marks_complete` + `upstream_is_complete` now extract the `~~...~~` strikethrough name (pre-` — ` token, trimmed) and compare for case-insensitive EQUALITY — a feature name that is a substring/prefix of a different completed feature no longer false-matches (`Audio` ≠ `Audio Engine`). `is_stub_spec` anchors the `Draft (pre-Gemini)` match to the `**Status:**` line / `>` blockquote trailer (prose mention no longer false-flags a stub). 3 smoke fixtures (RED→GREEN). Baseline regenerated via `_normalize_smoke_output`; **pre-regen diff confirmed purely additive** — zero pre-existing fixture routing changed (no over-reach; reviewer independently confirmed `all-complete`/`needs-realign` positive-detection fixtures still pass).
**Integration notes:**
- File-ownership reconciliation: the `workstation-verification-only-bold-marker` fixture (WU-2's "fix the fixture") lives INSIDE `lazy-state.py`, which WU-4 also edits → assigned ALL `lazy-state.py` edits to the WU-4 owner; ran WU-4 impl after WU-2 impl so the lazy-state baseline reflects the new `lazy_core` behavior. Confirmed WU-2's fence change does NOT alter any existing lazy-state/bug-state fixture routing (the bold-marker fixture's fenced row is now skipped but its non-fenced verification row keeps it verification-only → Step 8 retro unchanged).
- `plan-bug` is now a live `bug-state.py` emit; Phase 6's lazy-bug-batch by-reference rebuild inherits the description update.
- Byte-pinned baselines pinned to LF via new `tests/baselines/.gitattributes` (`*.txt text eol=lf`) — protects the verbatim-comparison contract (incl. Phase 1/2 baselines) under `core.autocrlf` on Windows.
**Pitfalls & guidance:**
- The marker is `**Status:** Concluded` — a NEW status value (not the plan's alternate `In-progress` suggestion, which is overloaded by plan frontmatter). spec-bug must WRITE it at conclusion; bug-state only READS it. A premature `Concluded` would make `/plan-bug` fabricate phases from incomplete findings — spec-bug's batch guard explicitly prevents this (unconcluded → `NEEDS_INPUT.md`).
- `roadmap_marks_complete`'s equality match assumes ROADMAP grammar `~~<Name> — <desc>~~ … **COMPLETE**` (documented in the function's docstring). A non-`Name — desc` strikethrough shape would require an exact-name match — a latent edge case to watch, not a current regression.
**Part-end gate status:** all three gates exit 0 (lazy-state --test, bug-state --test, test_lazy_core.py 100/100) — confirmed fresh by the orchestrator post-fixes. (NOT the final part gate — Batches 2-4 remain.)
**Files modified:**
- `user/scripts/bug-state.py` — Step 4 plan-bug branch + `SKILL_PLAN_BUG` + 2 fixtures
- `user/scripts/lazy_core.py` — fence tracking (3 fns) + bold-clash fix + comment correction
- `user/scripts/lazy-state.py` — 3 anchored fns + 3 fixtures + ROADMAP-grammar docstring
- `user/scripts/test_lazy_core.py` — 9 new lazy_core unit tests
- `user/scripts/tests/baselines/{bug-state,lazy-state}-test-baseline.txt` — regenerated (normalizer)
- `user/scripts/tests/baselines/.gitattributes` — NEW (LF pin)
- `user/skills/spec-bug/SKILL.md` — Concluded-status writer (Step 5/6) + template doc
- `user/skills/plan-bug/SKILL.md` — Concluded added to Status gate
- `user/skills/lazy-bug-batch/SKILL.md` — description: bug-state now emits plan-bug
- `user/skills/_components/phases-runtime-verification.md`, `user/skills/write-plan/SKILL.md` — placement convention

#### Implementation Notes (Phase 3 — Batch 2: WU-5, WU-6)
**Completed:** 2026-06-10
**Review verdict:** PASS-WITH-FIXES → fixes applied → PASS (dedicated Opus reviewer; reviewer md5-matched the live `~/.claude/scripts/*.py` to the repo and read all 3 SKILL diffs in full; the D3 model independently confirmed COMPLETE + CONSISTENT across all 3 SKILLs + halt-resolution; 5 minor text stragglers fixed)
**Work completed:**
- **WU-5** (stale already-applied plan → inline flip, TDD): `lazy-state.py` `compute_state()` Step 7 — before the cloud-saturated flip and the execute-plan dispatch — now emits `sub_skill="__flip_plan_complete_stale__"` (current_step `Step 7a: flip plan Complete (stale — all referenced deliverables already checked)`) when `_plan_phase_set(plan)` is NON-EMPTY and `_unchecked_wus_in_plan_scope(phases_text, phase_set)` is EMPTY (every WU the Ready/In-progress plan references is already `[x]`). The non-empty phase-set guard is required (a no-`phases:` plan has unknown scope → falls through to execute-plan, never falsely flips). Prevents the `Step 7a: execute plan` no-op loop that burned two Opus dispatches re-verifying already-applied plans. 2 smoke fixtures (`stale-plan-all-refs-checked-flips` RED→GREEN; `ready-plan-unchecked-in-scope-still-executes` non-tautological guard). Baseline regen confirmed purely additive.
- **WU-6** (D3 split counters + cap reachability + halt-resolution fix, prose; LOCKED D3): the single session-global `cycle` counter is replaced in ALL 3 batch orchestrators (`lazy-batch`, `lazy-bug-batch`, `lazy-batch-cloud`) + the shared `halt-resolution.md` by TWO monotonic counters — `forward_cycles` (pipeline work; ceiling `max_cycles`; capped at Step 1c) and `meta_cycles` (resolution/recovery/cleanup; ceiling `2 * max_cycles`; capped at the TOP of every resolution mode 1g/1h/1i + the top of the halt-resolution algorithm). The meta-cap-at-top is the load-bearing fix for the unreachable-cap bug (the `1a→1b→1g/1h/1i→1a` resolution loop previously bypassed the Step 1c cap, so resolution/re-prompt loops were unbounded). Increment classification: real-skill (1e) + pipeline-advancing pseudo-skills (`__mark_complete__`/`__mark_fixed__`, `__write_*__`, `__flip_plan_complete_cloud_saturated__`) → forward; resolution modes + `__flip_plan_complete_stale__` → meta; input-audits increment neither (bounded by the surrounding cycle). Both counters reported in the per-cycle heading (Step 3, uniform `### Cycle fwd {forward_cycles+1}/{max_cycles} · meta {meta_cycles}/{2*max_cycles} · …`) and the final batch report (Step 2). HARD CONSTRAINT 8 rewritten for the two-counter model. `halt-resolution.md` line-199 "max_cycles bounds it regardless" claim corrected to reference the meta-cycle cap (now the true bound).
- **WU-5 orchestrator wiring (folded into WU-6 to keep SKILLs single-writer):** `__flip_plan_complete_stale__` added to the Step 1c.5 inline-handler list in all 3 SKILLs (flip plan frontmatter `status:` → `Complete`, commit `chore(<id>): mark plan part N Complete (stale — already applied)`), classified META, and distinguished from `__flip_plan_complete_cloud_saturated__` (forward + cloud-only). Verified NOT a dead-end: lazy-state emits the exact same string the handlers consume.
**Integration notes:**
- Reviewer flagged the WU-6 impl agent's "already complete from a previous session" claim as FALSE (HEAD had 0 `forward_cycles`; the work was uncommitted current-session). Orchestrator independently re-verified every D3 structural element on disk (inits, forward cap @1c, meta-cap @ top of 1g/1h/1i ×3 SKILLs, stale handler ×3, final-report lines, no leftover bare `cycle`) before accepting — the deliverable was present and correct, only the narrative was mislabeled.
- **Follow-up (Phase 6 candidate, NOT a Batch-2 defect):** `bug-state.py` (~L731 `else: plan = plans[0]` → execute-plan) has the SAME stale-plan vulnerability but WU-5 was scoped to `lazy-state.py` only. `lazy-bug-batch/SKILL.md` now documents the `__flip_plan_complete_stale__` handler (consistent with the pre-existing convention where it also documents `__flip_plan_complete_cloud_saturated__` that bug-state.py never emits) — the bug-pipeline stale gate is a documented-but-unimplemented forward reference until a future phase adds it to `bug-state.py`.
**Pitfalls & guidance:**
- D3 counter consistency across the 3 large SKILLs is the #1 correctness requirement — the heading + final-report formats are byte-identical by design; any future edit to one orchestrator's counter text must mirror the other two (until Phase 6 makes lazy-bug-batch by-reference).
- The shared `halt-resolution.md` meta-cap message was made skill-agnostic (no hardcoded "lazy-batch") since all 3 orchestrators consume it.
**Part-end gate status:** all 3 gates exit 0 (lazy-state --test, bug-state --test, test_lazy_core.py 100/100) — confirmed fresh post-fixes. (NOT the final part gate — Batches 3-4 remain.)
**Files modified:**
- `user/scripts/lazy-state.py` — Step 7 stale-flip branch + 2 fixtures
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt` — regenerated
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — D3 two-counter model + `__flip_plan_complete_stale__` handler
- `user/skills/_components/halt-resolution.md` — meta-cap check + meta_cycles increment + line-199 fix

#### Implementation Notes (Phase 3 — Batch 3: WU-7)
**Completed:** 2026-06-10
**Review verdict:** PASS-WITH-FIXES → fixes applied → PASS (dedicated Opus reviewer; traced flag-placement + terminal-ordering by hand, ran all 3 suites green; caught a real scoped-deliverable gap)
**Work completed:**
- **WU-7** (scoped-id-not-found terminal + queue diagnostics, TDD; BOTH state scripts): a typo'd `--feature-id`/`--bug-id` (scope id matching no queue entry) previously fell through to `all-features-complete`/`all-bugs-fixed` — falsely reporting "all done." Both scripts now track a `scope_id_seen` flag set the instant a queue entry's id EQUALS the scope id (BEFORE any completion/cloud/device/deferred skip can `continue` past it — so a scoped feature that matched but is already complete still routes to its REAL terminal, NOT not-found), and emit a distinct `scoped-id-not-found` terminal (identical literal string in both; `TR_SCOPED_ID_NOT_FOUND` constant in bug-state) immediately before the all-complete fall-through. Added to both `terminal_reason` doc-enums. 2 fixtures RED→GREEN; positive scoping guards (`scoped-feature-id`/`scope-bug-id-two-bugs`) stay green as discriminators.
- **Queue diagnostics:** both scripts now emit a `_diag` when a queue entry is skipped for missing `id`/`name`/`spec_dir` (bug-state's walk-loop skip ~L478 and lazy-state's ~L930 — both previously silent). The diagnostic names the missing fields using the OPERATOR-FACING queue.json keys (`id`/`name`/`spec_dir`, not internal normalized names) so the operator knows which JSON field to fix.
**Integration notes:**
- Reviewer verified terminal ORDERING: when scoping to a not-found id, every skip-list (cloud/device/research/operator-deferred) is provably empty (they populate only post-match), so placing the not-found check right before all-complete cannot shadow `device-queue-exhausted`/`queue-blocked-on-research`/`cloud-queue-exhausted`; conversely when one of those is the real reason `scope_id_seen` is True so the not-found check is bypassed. `queue-missing` intentionally still takes precedence (more specific). Both scripts symmetric.
- Review fixes applied: lazy-state's malformed-entry `_diag` (the explicitly-scoped half that the impl agent initially did only in bug-state) + bug-state's diagnostic now reports `spec_dir` (operator key) not `spec_path` (internal key).
- Downstream note (out of scope): the lazy/lazy-bug single-dispatch skills have no explicit terminal-table row for `scoped-id-not-found`, but their generic clean-stop fallback prints `notify_message` and STOPs — degrades gracefully, no crash. An explicit row is a future nice-to-have.
**Part-end gate status:** all 3 gates exit 0 (lazy-state --test, bug-state --test, test_lazy_core.py 100/100) — confirmed fresh post-fixes. (NOT the final part gate — Batch 4 remains.)
**Files modified:**
- `user/scripts/lazy-state.py` — scope_id_seen flag + scoped-id-not-found terminal + malformed-entry _diag + 1 fixture
- `user/scripts/bug-state.py` — TR_SCOPED_ID_NOT_FOUND + flag + terminal + malformed-entry _diag + 1 fixture
- `user/scripts/tests/baselines/{lazy-state,bug-state}-test-baseline.txt` — regenerated (additive)

#### Implementation Notes (Phase 3 — Batch 4: WU-8 + Post-Phase)
**Completed:** 2026-06-10
**Review verdict:** PASS-WITH-FIXES → fixes applied → PASS (dedicated Opus reviewer; manually reconstructed + `yaml.safe_load`-parsed the realign-spec template to prove the hash round-trip, verified the mtime fallback byte-for-byte, caught a real YAML-coercion bug)
**Work completed:**
- **WU-8a** (realign mtime → hash gate, TDD): `realign_is_fresh` now reads `upstream_phases_hashes` (a YAML map dir-name→sha256 hex) from the newest realign plan's frontmatter (parsed via `parse_sentinel`→`yaml.safe_load`, a real YAML parser) and is fresh iff every hard-complete upstream's current `_phases_sha(ud)` matches its recorded hash — replacing the unreliable mtime comparison (mtimes reset on git checkout/clone). **Legacy plans without the field fall back to the original mtime logic byte-for-byte** (backward-compat preserved). Companion writer: `realign-spec/SKILL.md` Step 4 now records `upstream_phases_hashes:` in the realign plan frontmatter (the reviewer confirmed the writer's YAML shape + key convention round-trip exactly to what the gate reads). Fixture `realign-hash-gate-detects-changed-upstream` (RED→GREEN: a hash mismatch under a newer-mtime plan now correctly routes to Step 4.6, where the old mtime gate said "fresh").
- **WU-8b** (`check_stale_upstream` wired, TDD): `compute_state` now auto-runs `check_stale_upstream(repo_root)` at probe start (after `clear_diagnostics()`, before the queue walk / Step 2.9), guarded by `docs/work/materialized.json` existence — the production trigger the stale-upstream halt previously lacked (it was only called from a smoke test). The common queue-only workflow (no materialized.json) is a byte-for-byte no-op. Fixture `stale-upstream-auto-wired-at-probe` (RED→GREEN end-to-end: seed materialized.json + newer mirror changedDate → auto-run writes STALE_UPSTREAM.md → Step 2.9 halts `stale_upstream`).
- **WU-8c** (Step-10 NEEDS_INPUT writer, TDD): new helper `_write_step10_needs_input(spec_dir, feature_name)` writes a well-formed `NEEDS_INPUT.md` (kind: needs-input, written_by, `## Decision Context` H2 with a 1:1 decisions↔H3 pairing) into the spec dir; the defensive Step-10 `if not entry_ok:` branch now calls it before returning needs-input. (The branch is provably UNREACHABLE via normal compute_state inputs — every workstation Step-9 sub-path returns when `validated_file` is absent — so it is a pure defensive guard; the helper is the honest testable unit, exercised directly by the fixture.) Review fix: the `decisions:` title contained a colon-space → unquoted YAML coerced it to a dict (schema violation breaking Step 1g's decisions↔H3 contract); quoted the value so it parses as a string, and tightened the fixture to assert `all(isinstance(x, str))` so the class can't regress.
**Integration verification (Post-Phase):** the Phase-3 routing fixes cohere as one system — the new terminals/pseudo-actions land at distinct compute_state steps (bug-state Step 4 plan-bug, lazy-state Step 7 stale-flip, queue-walk scoped-id-not-found, Step 2.9 stale-upstream auto-trigger, Step 10 helper) with no conflicts; the full fixture suite passes together (no false halts). Cross-WU wiring verified: WU-5's `__flip_plan_complete_stale__` emit ↔ WU-6 handler use the identical string; WU-2's fence-aware parser feeds WU-5's stale detection + WU-8's nothing; the smoke fixtures are full-stack (compute_state end-to-end → observable routing + sentinel writes). No new untested user-facing surface. CLAUDE.md review: `user/scripts/CLAUDE.md` references the terminal table abstractly (authoritative table = the `compute_state()` docstring/body, which the impl agents updated via the `terminal_reason` doc-enums) — no structural CLAUDE.md update warranted.
**Pitfalls & guidance:**
- The realign hash round-trip is a cross-file contract (`realign-spec/SKILL.md` writer ↔ `realign_is_fresh` reader): the frontmatter KEY must be the upstream DIR NAME and the VALUE `sha256(PHASES.md bytes).hexdigest()`. `parse_sentinel` uses `yaml.safe_load`, so the writer's YAML map must be valid (correct indent). A change to either side must preserve the shape.
- The defensive Step-10 branch is unreachable by design — do not attempt to make it reachable by re-routing the normal "RETRO_DONE + needs MCP test" state (that correctly dispatches /mcp-test); the deliverable is only that IF the guard ever fires it leaves a durable NEEDS_INPUT.md.
**Carried follow-ups (out of Phase 3 scope, future-phase candidates):**
- bug-state.py has the same stale-plan vulnerability (no `__flip_plan_complete_stale__` emit) — WU-5 was lazy-state-scoped (Phase 6 lazy-bug-batch rebuild candidate).
- lazy/lazy-bug single-dispatch skills lack an explicit terminal-table row for `scoped-id-not-found` (degrades gracefully via the generic clean-stop; explicit row is a nice-to-have).
**Part-end full quality gate (MANDATORY — all exit 0):** `python3 ~/.claude/scripts/lazy-state.py --test` (0), `python3 ~/.claude/scripts/bug-state.py --test` (0), `python3 ~/.claude/scripts/test_lazy_core.py` (100/100, 0) — run + passed fresh by the orchestrator post-fixes, immediately before the part-close commit.
**Files modified:**
- `user/scripts/lazy-state.py` — `_phases_sha` + hash-based `realign_is_fresh` (mtime fallback) + `import hashlib` + check_stale auto-wire + `_write_step10_needs_input` + branch call + 3 fixtures
- `user/skills/realign-spec/SKILL.md` — record `upstream_phases_hashes` in realign plan frontmatter
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt` — regenerated (additive)

---

## Phase 4 — Parked-decision protocol + notifications (D1/D2)

**Goal:** Opt-in park-and-continue (`--park` skill flag) with batched flush; two-key
auto-accept (`--park` mode only); push on every park/halt in both modes. **Default (no flag)
behavior stays byte-for-byte the existing halt-and-wait.**

**Entry criteria:** Phase 3 (split counters land first — flush/park reporting uses them).

**Deliverables:**
- [x] `--park` skill invocation flag parsed in all 3 batch orchestrators; recorded in start banner + final report; no flag → existing Step 1g halt behavior unchanged
- [x] Script `--park-needs-input` mode + `parked[]` output array, passed only when skill got `--park` (wrappers keep halt behavior; probe output unchanged without the flag)
- [x] PushNotification at every park / halt / flush / run end (both modes)
- [x] D1 flush protocol (`--park` only): batched AskUserQuestion (≤4/call, Zero-Context Briefing preserved) at first opportunity (operator message / out of unparked work / run end); decision-apply per answer
- [x] D2 two-key auto-accept (`--park` only): `class: mechanical` + input-audit concurrence → recommended option auto-accepted, `resolved_by: auto-two-key`, receipt log + run-end digest; any disagreement → product → park; no auto-accept ever without `--park`
- [x] Cache-boundary note documented in both batch skills

**Runtime Verification:**
- [x] Default-mode regression: without `--park-needs-input`, a NEEDS_INPUT fixture still emits the `needs-input` halt (probe output byte-identical to Phase 1 baseline) — verified by the `park-needs-input-default-halt` / `bug-park-needs-input-default-halt` smoke sub-fixtures (assert `terminal_reason=="needs-input"` AND `parked` key absent) + the byte-pinned `--test` baseline-match tests + the zero-drift `--repo-root <AlgoBooth>` probe (no `parked` key in default output for either script)
- [x] Fixtures: with the flag, `parked[]` populated, parked item skipped not halted, resolved sentinel re-enters — verified by the `park-needs-input-mode-skip` (parked count=1, next entry dispatched) and `park-needs-input-resolved-reenter` (resolved sentinel → item re-dispatched, parked=[]) smoke sub-fixtures in both scripts (all green in `--test`)
- [ ] lazy-batch-retro checklist additions: parks fire notifications; flush count matches parked count; every auto-accept carries two keys + digest entry; zero parks/auto-accepts in no-flag runs — **deferred to Phase 6** (the design plan places the lazy-batch-retro Phase-4 grading-check additions in Phase 6 "lazy-batch-retro grading fixes"; this row is the cross-check that Phase 6 will satisfy, not a Phase-4 WU)

**Implementation Notes:**

#### Implementation Notes (Phase 4 — Batch 1: WU-1, WU-2)
**Completed:** 2026-06-10
**Review verdict:** PASS-WITH-FIXES → fixes applied → PASS (dedicated Opus reviewer; orchestrator independently re-ran every subagent GROUND-TRUTH block and diffed — all matched, HEAD unchanged ec8a4cd so no rogue commits; zero-drift byte-identical default output confirmed for both scripts)
**Work completed:**
- **WU-1** (TDD, `--park-needs-input` script mode + `parked[]`): new shared helper `lazy_core.build_parked_entry(item_id, sentinel_path)` (lazy_core.py ~270) returns `{id, sentinel, decision_count, parked_since}` from a NEEDS_INPUT.md sentinel (reuses `parse_sentinel`; `decision_count`=len of `decisions:` list with `isinstance(list)` defensive guard → 0 on absent/empty/scalar; `parked_since`=`date:` field or None). Both `lazy-state.py` and `bug-state.py` gained: a `--park-needs-input` CLI flag (store_true) threaded as `park_needs_input: bool = False` into `compute_state`; module-level `_PARKED` + `_PARK_MODE` (reset at compute_state top alongside `_DEVICE_DEFERRED`/`clear_diagnostics`); a park-peek in the queue walk that — only under park mode AND when a `NEEDS_INPUT.md` exists AND no co-present `BLOCKED.md` — appends `build_parked_entry(...)` to `_PARKED`, emits a `_diag`, and `continue`s (skip-not-halt, modeled on the existing cloud/device/operator-defer skips), placed AFTER the receipt-gated completion gate so a genuinely-complete item is never parked. **Byte-identical invariant: `"parked"` is included in the output dict ONLY inside `if _PARK_MODE:` — the key is entirely absent in default mode**, verified by the zero-drift probe (`--repo-root <AlgoBooth>` has no `parked` key for either script) + the byte-pinned `--test` baseline-match tests. BLOCKED.md retains precedence under park mode (review fix). Re-entry is automatic (per-invocation `_PARKED.clear()`; no cross-call persistence).
- **WU-2** (prose): all 3 batch orchestrators (`lazy-batch`, `lazy-bug-batch`, `lazy-batch-cloud` SKILLs) parse an opt-in `--park` flag alongside `max_cycles` (position-independent), set `park_mode` (default false), record `Park mode: on|off` in BOTH the start banner and the final report, update the usage string to include `[--park]`, and state explicitly that without the flag behavior is byte-for-byte the existing Step 1g halt-and-wait. Park/flush/auto-accept semantics are cross-referenced to Steps 1g/1h/1i (deferred to Batches 2–4). Single-dispatch wrappers (`lazy`/`lazy-bug`/`lazy-cloud`) intentionally untouched (no `--park` there per Rule 10).
**Review fixes applied (Sonnet fix-agent):** (1) BLOCKED.md exclusion added to the park guard in both scripts (a feature/bug with BOTH BLOCKED.md and NEEDS_INPUT.md must still halt "blocked", not be silently parked) + new `*-blocked-precedence` smoke sub-fixture in both scripts locking it; (2) removed a stale "RED→GREEN" comment in lazy-state.py that didn't match the code; (3) tightened the `build_parked_entry` docstring (handles missing-file/missing-field/scalar defensively, but structurally-corrupt frontmatter still routes through `parse_sentinel`'s `_die`→exit 2, consistent with all sentinel parsing).
**Integration notes:**
- The `--park-needs-input` script flag is the CONSUMER half; WU-2 wired the `--park` SKILL flag that (in later batches) is what causes the orchestrator to PASS `--park-needs-input` to the script. The park/flush/auto-accept ORCHESTRATION (when to flush, PushNotification firing, AskUserQuestion batching, two-key auto-accept) is Batches 2–5 — WU-1/WU-2 are the plumbing.
- `parked[]` entry schema is `{id, sentinel, decision_count, parked_since}` — the WU-4 flush protocol and WU-5 digest consume these fields.
**Pitfalls & guidance:**
- The byte-identical contract hinges entirely on the `if _PARK_MODE:` gate in `_state`/`_bug_state`; any future field added to the parked path must stay inside that gate or it leaks into default output and breaks the baseline pins.
- Baselines were regenerated through `_normalize_smoke_output` (never hand-edited); diffs are purely additive (+4 lines each, 0 removals).
**Files modified:**
- `user/scripts/lazy_core.py` — `build_parked_entry` helper
- `user/scripts/lazy-state.py` — `--park-needs-input` flag + param + `_PARKED`/`_PARK_MODE` + park-peek (BLOCKED-excluded) + 4 park smoke sub-fixtures
- `user/scripts/bug-state.py` — symmetric to lazy-state
- `user/scripts/test_lazy_core.py` — 4 `build_parked_entry` unit tests + symbol-importability assertion (104/104)
- `user/scripts/tests/baselines/{lazy-state,bug-state}-test-baseline.txt` — regenerated (additive)
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — `--park` flag parse + banner + final-report `Park mode:` line

#### Implementation Notes (Phase 4 — Batch 2: WU-3)
**Completed:** 2026-06-10
**Review verdict:** PASS (dedicated Opus reviewer; orchestrator ground-truth verified — diff purely additive +33/-0 across 3 files, HEAD unchanged 35945f4, existing per-terminal PushNotification lines preserved)
**Work completed:**
- **WU-3** (prose, all 3 batch SKILLs): added a consolidating `### 1c.6. PushNotification policy (park / halt / flush / run-end)` subsection enumerating the four orchestrator-fired notification points with correct mode-gating — **park** (`--park` only, per newly-parked item, carries running parked-count), **halt** (BOTH modes), **flush** (`--park` only, forward-ref to WU-4), **run-end** (BOTH modes) — and stating PushNotification is orchestrator-fired (scripts never call it). Also added a "Park mode — processing `parked[]` output" instruction at Step 1g: when `park_mode==true` and the probe returns a non-empty `parked[]`, the orchestrator fires the park notification per newly-parked item (incrementing `parked_count`) and continues the queue walk without halting. Existing per-terminal PushNotification lines preserved (not rewritten). lazy-bug-batch uses `bug_name`; feature variants use `feature_name`; cloud's halt list includes `cloud-queue-exhausted` — per-variant accuracy, gating phrases identical across all three.
**Integration notes:**
- The park-notification point consumes WU-1's `parked[]` script output. The flush point is a forward reference to WU-4 (next batch) — documented now so the four-point policy reads coherently.
**Files modified:**
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — §1c.6 policy + Step 1g parked[] processing

#### Implementation Notes (Phase 4 — Batch 3: WU-4)
**Completed:** 2026-06-10
**Review verdict:** PASS (dedicated Opus reviewer verified all 8 locked requirements present+correct; orchestrator ground-truth verified — new component 201 lines, 3 SKILLs +91/-3, HEAD unchanged a22c526, mount-site satisfied)
**Work completed:**
- **WU-4** (D1 flush protocol, `--park` only): created the shared component `user/skills/_components/parked-flush.md` (the batched, park-mode-only sibling of `decision-resume.md`), referenced by all 3 batch SKILLs via a new `### 1g-flush. Parked-decision flush (--park only)` section with pipeline-binding paragraph (same pattern as the Step 1g `decision-resume.md` include). The component specifies: hard `park_mode==true` gate (never fires without `--park`); the three flush triggers at the FIRST of (a) operator message mid-run, (b) **no-unparked-work guard** — the orchestrator MUST NOT treat an all-complete/queue-exhausted terminal as a real STOP while unresolved parked items remain (flush first — this is the load-bearing anti-abandonment point), (c) run end; meta-cap check FIRST (2× max_cycles); per-item schema validation with malformed-skip-not-abort (surfaces the named writer, continues on well-formed items); **Zero-Context Operator Briefing preserved as a HARD REQUIREMENT** (2a briefing + 2b verbatim `## Decision Context` re-print before each call, options 1:1); batched AskUserQuestion with **≤4 TOTAL questions/call** (greedy pack, sequential follow-up calls, never split one item across calls); apply via REFERENCE to `decision-resume.md` steps 4–6 (no duplication) including the FILENAME rename neutralization (`git mv` → `NEEDS_INPUT_RESOLVED*.md`, never a `kind:` flip); per-applied-decision `meta_cycles++`; continuation returns to Step 1a for (a)/(b) (renamed sentinels re-enter on next probe) and prints the final report for (c).
- The Batch-2 §1c.6 "flush point" forward-references now resolve to the real `§1g-flush` (no dangling reference).
**Integration notes:**
- Architecture matches the existing shared-handler pattern (`decision-resume.md`/`blocked-resolution.md`/`halt-resolution.md`) — flush logic lives once in the component; the 3 SKILLs only bind tokens + reference it, avoiding the triple-drift Phase 6 otherwise has to fix. Per-pipeline vocabulary correct (lazy-bug-batch: bug-state.py/all-bugs-fixed; lazy-batch-cloud: cloud push-after-commit + cloud-queue-exhausted).
- WU-5 (next batch) layers two-key auto-accept ON TOP of this flush (auto-accepted decisions bypass the AskUserQuestion; the rest flush here).
**Files modified:**
- `user/skills/_components/parked-flush.md` — NEW shared flush-protocol component
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — §1g-flush reference + binding; §1c.6 forward-ref fix

#### Implementation Notes (Phase 4 — Batch 4: WU-5)
**Completed:** 2026-06-10
**Review verdict:** PASS (dedicated Opus reviewer confirmed all three auto-accept leak paths structurally closed; orchestrator ground-truth verified — +173/-1 across 5 files, HEAD unchanged 2a2665a, --test suites still green since no .py touched)
**Work completed:**
- **WU-5** (D2 two-key auto-accept, `--park` only):
  - `sentinel-frontmatter.md`: extended the NEEDS_INPUT schema with two OPTIONAL fields — `class: mechanical|product` (**Key 1**, file-level, authored by the cycle subagent; absent ⇒ `product` conservative default) and `audit_concurs: true|false` (**Key 2**, written by Step 1d.5 input-audit; absent ⇒ no-concurrence). Both documented as **`--park`-mode auto-accept signals ONLY** (the non-park decision-resume path ignores them → zero behavior change without `--park`). Documented the `resolved_by: auto-two-key` resolution marker. Existing halting-rule prose preserved intact.
  - `parked-flush.md`: added Step 2.5 two-key auto-accept partition — `auto_acceptable[]` requires ALL THREE (`class==mechanical` AND `audit_concurs==true` AND every decision has a `**Recommendation:**`); single-key explicitly insufficient; everything else → `must_ask[]` (operator AskUserQuestion). Auto-accept takes the recommended option, appends `## Resolution` with `resolved_by: auto-two-key`, applies via decision-resume.md steps 4–6 (incl. `git mv` rename, NOT a `kind:` flip), records to `auto_accepted[]` for the digest, counts each as a meta cycle. Structural `--park`-only guarantee (auto-accept lives only in this park-gated component).
  - Step 1d.5 (`audit_concurs` recording): lazy-batch canonical step 7 instructs the audit subagent to independently re-classify a `class: mechanical` sentinel and write `audit_concurs: true|false` (committed/pushed); AGGRESSIVE bias preserved (when in doubt → false/product). lazy-bug-batch mirror note + lazy-batch-cloud explicit inclusion in the mirrored contract (with cloud-reclaim commit/push safety).
  - Run-end digest: all 3 SKILLs' Step 2 final report gained an "Auto-accepted decisions (`--park` two-key)" table (feature/bug, decision, chosen option, resolved-sentinel link), printed ONLY when `park_mode` AND `auto_accepted[]` non-empty (no change to default reports).
**Integration notes:**
- Load-bearing property verified by review: a decision CANNOT be auto-accepted (a) without `--park` (structural — park-only component), (b) with only one key (AND-gated), or (c) with a product classification (`must_ask` catches product/absent).
- This completes the D1+D2 park machinery: WU-1 script `parked[]`, WU-2 `--park` flag, WU-3 notifications, WU-4 flush, WU-5 auto-accept. WU-6 (next, final batch) adds the cache-boundary note.
**Files modified:**
- `user/skills/_components/sentinel-frontmatter.md` — `class`/`audit_concurs`/`resolved_by: auto-two-key` schema
- `user/skills/_components/parked-flush.md` — Step 2.5 two-key auto-accept partition
- `user/skills/lazy-batch/SKILL.md` — Step 1d.5 step 7 audit_concurs recording + run-end digest table
- `user/skills/lazy-bug-batch/SKILL.md` — Step 1d.5 mirror note + run-end digest table
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — Step 1d.5 mirror inclusion + run-end digest table

#### Implementation Notes (Phase 4 — Batch 5: WU-6 + Post-Phase)
**Completed:** 2026-06-10
**Review verdict:** PASS (inline review — 2 files, 20 insertions ≤150 lines; orchestrator ground-truth verified — wc 1355/842 matches, HEAD unchanged 150c8da, note identical in both files, lazy-bug-batch correctly untouched)
**Work completed:**
- **WU-6** (cache-boundary note, docs): added a "Cache-boundary note" paragraph to the two FEATURE batch SKILLs ONLY (`lazy-batch` + `lazy-batch-cloud`; lazy-bug-batch intentionally NOT touched per the plan) near each file's `### 1g-flush` trigger list. The note states that flush triggers (b) "no unparked work remains" and (c) "run end" coincide with the natural Anthropic prompt-cache rebuild boundaries (≈5-min TTL lapses where the orchestrator was already pausing/stopping), so batching parked decisions to flush there adds no extra cache cost; trigger (a) (operator message) is itself an interaction boundary; consequence — do NOT interleave unrelated long waits/blocking halts between a park and its flush (it would force repeated cache rebuilds for no benefit). Wording identical across the two files.
**Files modified:**
- `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — cache-boundary note

#### Post-Phase (Phase 4 — Integration Verification + CLAUDE.md review + part close)
**Integration verification:** the D1/D2 park machinery coheres end-to-end as ONE opt-in system —
(1) **no-flag path is byte-for-byte unchanged** (the load-bearing invariant): the script `parked`/`class`/`audit_concurs` fields are emitted/read ONLY under `--park` / park-mode; verified by the zero-drift `--repo-root <AlgoBooth>` probe (no `parked` key for either script), the byte-pinned `--test` baseline-match tests (104/104 + both scripts' baselines), and the additive-only baseline diffs. The `--park` SKILL flag (WU-2) defaults off; the `--park-needs-input` script flag (WU-1) is passed by the orchestrator ONLY when `--park` was given; the auto-accept (WU-5) lives exclusively in the park-only `parked-flush.md`. (2) **The flagged path parks + flushes coherently:** a NEEDS_INPUT item is skipped→`parked[]` (WU-1, BLOCKED retains precedence), a park PushNotification fires with running count (WU-3), the batched flush at trigger (a)/(b)/(c) surfaces product decisions via AskUserQuestion with the Zero-Context Briefing preserved (WU-4), two-key-mechanical decisions auto-accept with `resolved_by: auto-two-key` + run-end digest (WU-5), and the cache-boundary discipline (WU-6) keeps flushes at cache/interaction boundaries. The four shared components (`parked-flush.md` new; `decision-resume.md`/`sentinel-frontmatter.md` extended) are referenced by all consuming SKILLs (mount-site verified — no orphans).
**CLAUDE.md review:** `user/scripts/CLAUDE.md` "## CLI surface" lists the state-script flags → added the new `--park-needs-input` line (with the BLOCKED-still-halts + byte-identical-without-flag caveats). No other CLAUDE.md update warranted (the `--park` SKILL flag + park orchestration are documented in the SKILLs themselves; no new directory/structure).
**Part-end full quality gate (MANDATORY — all exit 0):** `python3 ~/.claude/scripts/lazy-state.py --test` (0), `python3 ~/.claude/scripts/bug-state.py --test` (0), `python3 ~/.claude/scripts/test_lazy_core.py` (104/104, 0) — run + passed fresh by the orchestrator as the final chained command before the part-close commit. (`~/.claude/scripts/*.py` resolve to the repo's `user/scripts/*.py` — same inode — so the gate tested the edited code.)
**Carried follow-ups (out of Phase 4 scope):**
- Runtime Verification row 3 (lazy-batch-retro Phase-4 grading checks) is owned by Phase 6 per the design plan ("lazy-batch-retro grading fixes") — left unchecked; not a Phase-4 WU.
- Phase 6 (by-reference rebuild of lazy-bug-batch + componentization) inherits the canonical lazy-batch park text added here; the new `parked-flush.md` shared component already follows the by-reference pattern Phase 6 favors.

---

## Phase 5 — Script-ification of the orchestrator loop

**Goal:** ≤3 orchestrator messages per happy-path cycle.

**Entry criteria:** Phases 1–2 (receipt validation must precede `--apply-pseudo`).

**Deliverables:**
- [x] `--verify-ledger <spec_path>` (replaces 5 prose blocks)
- [x] `--apply-pseudo <name> <spec_path>` for all deterministic sentinel/receipt writes; receipt-write ownership contradiction resolved (script is single author)
- [x] `--neutralize-sentinel <path>` with collision handling
- [x] Persisted probe signature → `repeat_count` in output
- [x] Probe payload includes git-guard results + pre-formatted cycle header
- [x] Both batch skills consume subcommands; superseded prose deleted

**Runtime Verification:**
- [x] Regression gates green
- [x] Fixtures per subcommand: each verify-ledger failing check; apply-pseudo idempotency + gate-absent refusal; neutralize collision; repeat_count increments

**Implementation Notes:**

#### Implementation Notes (Phase 5 — Batch 1: WU-1 `--verify-ledger`)
**Completed:** 2026-06-10
**Review verdict:** PASS (dedicated Opus reviewer; orchestrator independently re-ran the impl agent's full GROUND-TRUTH block and diffed — wc/grep/status/test-counts all matched, HEAD unchanged 0c032d0 so no rogue commits; ground-truth verified: yes)
**Work completed:**
- **WU-1** (TDD): new shared `lazy_core.verify_ledger(repo_root, spec_path) -> dict` (~line 1019) scripts the "completion ledger" guard previously duplicated as 5 prose blocks (lazy Step 4, lazy-bug Step 4, both batch 1e.4a, cloud 1e — those are DELETED in WU-6). Returns `{ok, failing_check, checks:{clean_tree, head_matches_origin, plan_complete, deliverables_done}}`; checks evaluated in that fixed order, `failing_check`=first False key, `ok`=all True, all four keys always populated (no short-circuit pruning).
  - `clean_tree`: `git -C repo_root status --short` empty (subprocess, mirrors `_current_head` style — capture_output/text/timeout, OSError/SubprocessError→False).
  - `head_matches_origin`: `rev-parse HEAD` == `rev-parse @{u}`; no-upstream / mismatch → False.
  - `plan_complete`: `_has_any_complete_plan(spec) AND len(find_implementation_plans(spec))==0` — reuses existing helpers; equivalent to "≥1 plan exists AND all Complete" (find_implementation_plans filters OUT Complete plans). A lone legacy no-frontmatter (Ready) plan correctly → False.
  - `deliverables_done`: REFINED "zero NON-verification `- [ ]`" — `count_deliverables` (returns `(unchecked, checked)`) unchecked==0 OR `remaining_unchecked_are_verification_only(phases)`; missing PHASES.md → False. A blunt `grep -c "- [ ]"` would over-fail legit pending Runtime-Verification rows — the refined check passes them.
- **CLI**: `--verify-ledger SPEC_PATH` added to BOTH `lazy-state.py` (~4646/4686) and `bug-state.py` (~2841/2871), placed among the early-return handlers BEFORE `compute_state`; prints indented JSON and returns exit 0 iff `ok` else 1 (so the orchestrator's `&&` chains short-circuit on a failed ledger). Uses the existing `--repo-root` global for the git checks.
- **Tests**: 6 RED→GREEN unit tests + 2 fixture helpers (`_make_git_repo_with_origin` builds a real temp git repo with a bare-repo upstream so `@{u}` resolves offline; `_write_complete_plan`/`_write_all_checked_phases`) in `test_lazy_core.py`, registered in `_TESTS`. The verification-only-passes test is a genuine non-tautological discriminator (2 unchecked rows under `### Runtime Verification` → pass; the sibling test's 1 real unchecked row → fail with `failing_check=="deliverables_done"`). Each failing-case test asserts the EXACT `failing_check` key + the boolean + that earlier checks are True (pins the ordering).
**Ground-truth verification:** impl-agent GROUND-TRUTH block re-run independently by orchestrator — `git status --short` (4 files M), `wc -l` (lazy_core 1150 / lazy-state 4710 / bug-state 2892), `grep` line numbers, full suite 110/110, both `--test` gates exit 0 — all matched exactly. No falsified claims; no "already complete" claims.
**Integration notes:** `verify_ledger` is a NEW function (no imports added to mocked modules → no propagation risk); CLI wiring is additive and gated behind `is not None` (default `compute_state` path byte-unchanged). WU-6 (separate commit) will delete the 5 prose blocks this subcommand replaces and route the skills to call it.
**Files modified:** `user/scripts/lazy_core.py` (+`verify_ledger`, +`import subprocess`), `user/scripts/lazy-state.py` (CLI handler), `user/scripts/bug-state.py` (CLI handler), `user/scripts/test_lazy_core.py` (6 tests + 2 helpers + registry).

#### Implementation Notes (Phase 5 — Batch 2: WU-2 `--apply-pseudo` + receipt-ownership resolution)
**Completed:** 2026-06-10
**Review verdict:** PASS-WITH-FIXES → fixes applied → PASS (dedicated Opus reviewer; orchestrator independently re-ran impl GROUND-TRUTH block + diffed — wc/grep/status/test-counts matched, HEAD unchanged a5f3d9e so no rogue commits; ground-truth verified: yes. Reviewer caught a Medium plan-flip regex defect + 2 Low items, all fixed by a Sonnet fix-agent and re-verified.)
**Work completed:**
- **WU-2** (TDD): new shared `lazy_core.apply_pseudo(repo_root, name, spec_path, *, plan_path, date, feature_id, reason, deferred_step) -> dict` (~line 1158) is now the SINGLE deterministic author of the lazy pseudo-skills' sentinel/receipt writes. Returns `{name, ok, refused:str|None, wrote:[], deleted:[], noop}`. Dispatches on `name`:
  - `__write_validated_from_skip__` — gate `SKIP_MCP_TEST.md` present (absent→refused); writes `VALIDATED.md` (kind validated, mcp_scenarios:[], result:all-passing); idempotent (existing kind=validated → noop, no overwrite).
  - `__write_validated_from_results__` — gate `MCP_TEST_RESULTS.md` w/ `scenarios` list (absent→refused); copies scenarios → `VALIDATED.md mcp_scenarios` via `yaml.safe_dump(default_flow_style=True)` (YAML-safe — round-trips colons/commas); idempotent.
  - `__write_deferred_non_cloud__` — writes `DEFERRED_NON_CLOUD.md` (kind deferred-non-cloud, deferred_step default 8); idempotent; no gate.
  - `__flip_plan_complete_cloud_saturated__` — flips a plan's frontmatter `status:` In-progress→Complete IN PLACE, **scoped to the `---`…`---` frontmatter fence span** (a body line starting `status:` is never touched); target = `plan_path` or the single non-Complete plan via `find_implementation_plans` (zero/>1/no-frontmatter-status → refused); already-Complete → noop.
  - `__mark_complete__` — gate = `VALIDATED.md` OR `SKIP_MCP_TEST.md` present (else refused, writes nothing); if `COMPLETED.md` exists → noop (no re-flip/re-delete); else writes `COMPLETED.md` (provenance: gated, folds validated_via + mcp_pass/total from MCP_TEST_RESULTS.md, via reused `write_completed_receipt`), flips SPEC.md + PHASES.md first `**Status:**` line → Complete, deletes VALIDATED.md/RETRO_DONE.md/DEFERRED_NON_CLOUD.md (keeps SKIP/RESULTS/receipt). **ROADMAP strikethrough is NOT scripted — stays orchestrator prose** (fuzzy multi-line edit).
  - `__mark_fixed__` — bug analog: `FIXED.md` (kind fixed) + SPEC Status→Fixed + same gate/deletes; `git mv` archive NOT scripted.
  - unknown name → refused (no crash).
- **CLI**: `--apply-pseudo NAME SPEC_PATH` (nargs=2) + `--plan/--apply-date/--reason/--deferred-step` added to BOTH `lazy-state.py` (~4654/4666) and `bug-state.py` (~2851/2872), among early-return handlers BEFORE `compute_state`; prints JSON, exits 0 iff `ok` else 1. No argparse dest collisions.
- **Receipt-ownership resolution** (`completion-integrity-gate.md`): the contradiction (gate-says-it-writes-the-receipt vs consumers-say-they-do) is resolved — the gate now VERIFIES preconditions then DELEGATES the receipt write + SPEC/PHASES flip + sentinel cleanup to `--apply-pseudo __mark_complete__` (the single author); the ROADMAP strikethrough is the consumer's only remaining flip step. Stale "gate writes the receipt" sentences (preamble + return-status bullet) reworded for internal consistency. Consumer SKILL.md files deliberately untouched — that is WU-6 (separate commit).
- **Tests**: 16 RED→GREEN `test_apply_pseudo_*` (14 original + 2 fix-driven: no-frontmatter-status plan refusal proves body byte-unchanged; special-char scenarios prove YAML round-trip). Idempotency tests are non-tautological (assert byte-stable content + that leftover sentinels are NOT deleted on a no-op re-run); refusal test proves no receipt written.
**Ground-truth verification:** impl + fix GROUND-TRUTH blocks re-run independently — `git status --short` (5 files M), `wc -l` (lazy_core 1594 / test 3110 / gate-doc 131), grep line anchors, full suite 126/126, both `--test` gates exit 0 — all matched. No falsified claims.
**Review fixes applied (Sonnet fix-agent, re-verified PASS):** (1) plan-flip `status:` rewrite re-scoped from a whole-file `re.MULTILINE` match to the frontmatter fence span (was a latent body-corruption defect on a malformed plan; dead `if m is None: pass` branch removed); (2) `mcp_scenarios` emitted via `yaml.safe_dump` (was hand-rolled `[a, b]`, broke on colon/comma); (3) two stale doc sentences reconciled.
**Integration notes:** `apply_pseudo` adds only `import datetime` (stdlib, no mock consumers → no propagation risk); CLI additive + gated behind `is not None` (default `compute_state` byte-unchanged). WU-6 (separate commit) routes the SKILL `__mark_complete__`/`__mark_fixed__`/`__write_*__` handler prose to call these subcommands and deletes the now-superseded inline mechanics.
**Files modified:** `user/scripts/lazy_core.py` (+`apply_pseudo`, +`import datetime`), `user/scripts/lazy-state.py` (CLI), `user/scripts/bug-state.py` (CLI), `user/skills/_components/completion-integrity-gate.md` (ownership resolution), `user/scripts/test_lazy_core.py` (16 tests + helpers + registry).

#### Implementation Notes (Phase 5 — Batch 3: WU-3 `--neutralize-sentinel`)
**Completed:** 2026-06-10
**Review verdict:** PASS (dedicated Opus reviewer; orchestrator independently re-ran impl GROUND-TRUTH block + read the full function body — wc/grep/status/test-counts matched, HEAD unchanged 2b61701; ground-truth verified: yes. No issues found.)
**Work completed:**
- **WU-3** (TDD): new shared `lazy_core.neutralize_sentinel(path, date=None) -> dict` (~line 1602) renames a resolved sentinel to the canonical `<stem>_RESOLVED_<date><ext>` form (e.g. `NEEDS_INPUT.md` → `NEEDS_INPUT_RESOLVED_2026-06-10.md`, `BLOCKED.md` → `BLOCKED_RESOLVED_2026-06-10.md`), matching the `git mv … _RESOLVED…` prose in `decision-resume.md`/`blocked-resolution.md`. Returns `{ok, renamed_from(basename)|None, renamed_to(basename)|None, refused:str|None, collision_suffix:int|None}`.
  - **Collision handling** (the load-bearing case — the rename collided once in practice): if the base target already exists, a numeric suffix `_2`, `_3`, … is appended before the extension until a FREE name is found — the pre-existing target is NEVER clobbered (`collision_suffix` records the integer used, else None).
  - Refusals (no filesystem mutation): absent path → `"sentinel not found"`; basename already contains `_RESOLVED_` → `"already neutralized"` (no double-neutralize).
  - Rename mechanism: `git mv` (preserves history for tracked files) with a `Path.rename()` fallback when git returns non-zero / raises (untracked file or non-repo — the unit-test path). Fallback cannot raise on collision because the target was proven free first.
- **CLI**: `--neutralize-sentinel PATH` added to BOTH `lazy-state.py` (~4664/4668) and `bug-state.py` (~2871/2876), among early-return handlers BEFORE `compute_state`; reuses the existing `--apply-date` flag (no duplicate date flag); prints JSON, exits 0 iff `ok` else 1.
- **Tests**: 6 RED→GREEN `test_neutralize_sentinel_*` — basic rename, absent refusal, single collision (`_2`, pre-existing content preserved), double collision (`_3`, both priors untouched), already-resolved refusal (file NOT renamed), BLOCKED form. The collision tests are non-tautological (assert byte-preservation of the pre-existing target + source content in the new file).
**Ground-truth verification:** impl GROUND-TRUTH block re-run independently — `git status --short` (4 files M), `wc -l` (lazy_core 1710), grep anchors, full suite 132/132, both `--test` gates exit 0 — all matched. No falsified claims.
**Integration notes:** new function adds no imports beyond already-present `subprocess`/`datetime`; CLI additive + gated behind `is not None`. WU-6 routes the SKILL neutralization prose (`git mv … _RESOLVED*`) to call this subcommand.
**Files modified:** `user/scripts/lazy_core.py` (+`neutralize_sentinel`), `user/scripts/lazy-state.py` (CLI), `user/scripts/bug-state.py` (CLI), `user/scripts/test_lazy_core.py` (6 tests + registry).

#### Implementation Notes (Phase 5 — Batch 4: WU-4 persisted probe signature → `repeat_count`)
**Completed:** 2026-06-10
**Review verdict:** PASS (dedicated Opus reviewer; orchestrator INDEPENDENTLY re-proved the load-bearing byte-identical-default guarantee — two `--repo-root <AlgoBooth>` runs byte-identical with zero `repeat_count` occurrences, no repo-tree pollution; ground-truth verified: yes. HEAD unchanged c65aa5c. No issues.)
**Work completed:**
- **WU-4** (TDD): new shared `lazy_core.update_repeat_count(repo_root, state, *, signature_path=None) -> int` (~line 1718) persists the probe's dispatch signature `(feature_id, sub_skill, sub_skill_args, current_step)` and returns the CONSECUTIVE-identical-probe count (increments on identical signature, resets to 1 on change/corrupt/absent) — making loop detection mechanical instead of prose. `sub_skill_args` is part of the signature (a multi-part `/execute-plan` part-1→part-2 correctly resets, NOT a false loop). Read is guarded against missing/corrupt/wrong-shape JSON (resets to 1, never raises); persists `{signature, count}` atomically via `_atomic_write`.
- **Signature-file location (design choice):** stored under the OS temp dir keyed by `sha1(repo_root.resolve())[:16]` — deliberately OUTSIDE the repo tree (the design's "e.g. logs/docs dir" is a suggestion; keeping it out of the tree is the stronger constraint — the orchestrator's `git add -A` can never commit it, and no `.gitignore` entry is required). `signature_path` is injectable for test isolation.
- **CRITICAL byte-identical gating:** `repeat_count` is emitted ONLY under a new `--repeat-count` flag (added to BOTH `lazy-state.py` ~4666/4741 and `bug-state.py` ~2875/2937); `update_repeat_count` is called only inside `if args.repeat_count:` in `main()`, AFTER `compute_state` and BEFORE `json.dumps`. WITHOUT the flag: NO field, NO state-file write → output byte-for-byte identical to today. This preserves the Phase-1 byte-pinned `--test` baselines AND the zero-drift `--repo-root` two-run probe (a stateful always-on counter would have broken the second run). Mirrors the Phase-4 `--park-needs-input` opt-in pattern. NO baseline regeneration was needed (baselines unchanged in the diff).
- **Tests**: 5 RED→GREEN `test_update_repeat_count_*` (inject `signature_path` for isolation) — first-call=1; increments 1→2→3 on identical; resets on signature change; **args-distinguish** (part-1→1, part-2→1-not-2 — the non-tautological core proving args is in the signature); corrupt-file → 1 (no raise).
**Ground-truth verification:** impl GROUND-TRUTH re-run independently — full suite 137/137, both `--test` gates exit 0 (baselines unchanged), default two-run `--repo-root` BYTE-IDENTICAL (0 `repeat_count` occurrences), only the 4 source files modified (no repo pollution) — all matched. No falsified claims.
**Integration notes:** added `import hashlib` to lazy_core.py (`tempfile`/`json` already present); CLI additive + flag-gated. WU-5 (next batch) folds git-guard results + a cycle-header block into the probe payload (same flag-gated, byte-identical-default discipline). WU-6 wires the SKILL loop-guard (Step 1d) to consume `repeat_count`.
**Files modified:** `user/scripts/lazy_core.py` (+`update_repeat_count`, +`import hashlib`), `user/scripts/lazy-state.py` (flag+gated call), `user/scripts/bug-state.py` (flag+gated call), `user/scripts/test_lazy_core.py` (5 tests + registry).

#### Implementation Notes (Phase 5 — Batch 5: WU-5 single probe payload — git guards + cycle header)
**Completed:** 2026-06-10
**Review verdict:** PASS-WITH-FIXES → fix applied → PASS (dedicated Opus reviewer; orchestrator INDEPENDENTLY re-proved byte-identical default + verified the fix; ground-truth verified: yes; HEAD unchanged d06848a. One Low contract-divergence caught + fixed.)
**Work completed:**
- **WU-5** (TDD): two new shared functions in `lazy_core.py` —
  - `git_guard_status(repo_root) -> {clean_tree, head_matches_origin, unpushed}` (~1806): `clean_tree` = `git status --short` empty AND returncode 0; `head_matches_origin` = HEAD == `@{u}`; `unpushed` = `git rev-list --count @{u}..HEAD` > 0. Best-effort (git failure / no upstream → safe False).
  - `format_cycle_header(state, *, forward_cycles, max_cycles, meta_cycles) -> str` (~1904): pre-formats the orchestrator's `### Cycle fwd {fwd}/{max} · meta {meta}/{2*max} · {feature} · {sub_skill}` heading line (U+00B7 `·` separators, U+2014 `—` for falsy feature/sub_skill, `?` for None counters incl. `2*max`). Counters use `is not None` (so `forward_cycles=0` renders `0`, not `?`). The orchestrator passes its session counters in; the script pre-formats the ready-to-print line so the happy-path turn is read-payload → dispatch → record.
- **CRITICAL byte-identical gating** (same discipline as WU-4): both fields are emitted ONLY under a new `--probe` flag (+ `--forward-cycles/--meta-cycles/--max-cycles` int flags), wired into BOTH `lazy-state.py` (~4671/4756) and `bug-state.py` (~2882/2960) inside `if args.probe:` AFTER compute_state, composing with `--repeat-count`. WITHOUT `--probe`: no fields → output byte-for-byte identical (baselines + zero-drift probe preserved; independently re-proved by the orchestrator). NO baseline regeneration.
- **Tests**: 6 RED→GREEN (`test_git_guard_status_*` ×4 incl. the fix-driven invalid-repo guard, `test_format_cycle_header_*` ×2). git tests reuse the WU-1 `_make_git_repo_with_origin` bare-origin fixture; the unpushed test is discriminating (HEAD ahead → head_matches_origin False AND unpushed True AND clean_tree True); the header tests pin the exact string incl. the `2*max` arithmetic.
**Ground-truth verification:** impl + fix GROUND-TRUTH re-run independently — full suite 143/143, both `--test` gates exit 0 (baselines unchanged), default two-run `--repo-root` BYTE-IDENTICAL (0 `git_guards`/`cycle_header` occurrences), only the 4 source files modified — all matched.
**Review fix applied (Sonnet fix-agent, re-verified PASS):** `clean_tree` originally trusted empty stdout alone; an invalid/non-git `repo_root` makes `git status --short` exit 128 with empty stdout → false-positive `clean_tree=True`, contradicting the docstring + inconsistent with checks 2/3. Fixed to require `returncode == 0 AND empty stdout`; added `test_git_guard_status_invalid_repo_is_safe_dirty` (discriminating — fails under the old logic).
**Carried follow-up (minor, not blocking):** `verify_ledger`'s own `clean_tree` (WU-1, lazy_core.py ~1083) has the same latent stdout-only logic; harmless in production (always called with a real repo_root) but a candidate for the same one-line `returncode==0` hardening in a future consistency pass.
**Integration notes:** both functions standalone, no new imports (subprocess present); CLI additive + flag-gated. WU-6 wires the SKILL Step-3 cycle-header + git-guard consumption to `--probe`.
**Files modified:** `user/scripts/lazy_core.py` (+`git_guard_status`, +`format_cycle_header`, clean_tree returncode fix), `user/scripts/lazy-state.py` (flags+gated call), `user/scripts/bug-state.py` (flags+gated call), `user/scripts/test_lazy_core.py` (6 tests + registry).

#### Implementation Notes (Phase 5 — Batch 6: WU-6 skill text consumes subcommands; superseded prose deleted)
**Completed:** 2026-06-10
**Review verdict:** PASS (prose WU, TDD:no; inline review — 2 files, ~81 changed lines ≤150 → reviewed the full diff directly. Orchestrator independently re-verified: only the 2 SKILL files modified (scripts untouched → all 3 regression gates exit 0, 143/143), subcommands referenced in both, zero hand-write mechanics remain for supported pseudo-skills, both files mirrored, Rule 10 honored. Ground-truth verified: yes; HEAD unchanged d9c4df1.)
**Work completed (SEPARATE commit from the script WUs per Rule 9 — script subcommands landed first in WU-1..5, skill-text last so a mid-phase interruption left prose fallbacks intact):**
- **WU-6** (prose; `lazy-batch/SKILL.md` + `lazy-batch-cloud/SKILL.md` only — single-dispatch lazy/lazy-bug and lazy-bug-batch are Phase 6 scope):
  - **Step 1c.5 pseudo-skill handlers** now DELEGATE the deterministic WRITES to `--apply-pseudo`: `__write_validated_from_skip__`/`__write_validated_from_results__`/`__write_deferred_non_cloud__` (cloud) → one-line `--apply-pseudo <name> <spec_path>` calls; `__flip_plan_complete_cloud_saturated__` → `--apply-pseudo … --plan <plan>`; `__mark_complete__` keeps ALL gate prose intact (workstation: 2 gates; cloud: hard-guard + MCP-coverage audit + completion-integrity) and replaces ONLY the post-gates WRITE block (COMPLETED.md + SPEC/PHASES status flip + sentinel cleanup) with `--apply-pseudo __mark_complete__ <spec_path>`, followed by the ROADMAP strikethrough (the one remaining orchestrator step) — **Rule 10 honored: gate CHECKS stay, only the WRITES became mechanical.** `__flip_plan_complete_stale__` deliberately KEPT inline (apply-pseudo does not implement stale) with an explicit note.
  - **Post-`/execute-plan` ledger-consistency guard** (lazy-batch Step 1e §4a; cloud guard) now runs `git fetch` + `--verify-ledger {spec_path}` (cloud adds `--cloud`) instead of the inline (a)/(b)/(c) git+grep, with per-`failing_check` reconciliation (clean_tree/head_matches_origin → commit+push residue; plan_complete → re-flip status; deliverables_done → tick-with-evidence-else-NEEDS_INPUT). Notes verify-ledger's verification-only exemption so it won't false-fail on pending Runtime-Verification boxes.
  - **Probe enrichment note** added at the probe step: the orchestrator MAY pass `--repeat-count --probe --forward-cycles/--meta-cycles/--max-cycles` to fold `repeat_count` (mechanical loop-detection corroboration of `prev_cycle_signature`), `git_guards`, and a pre-formatted `cycle_header` into ONE probe payload (read payload → dispatch → record). The existing `prev_cycle_signature` machinery is retained.
  - Net effect: the happy-path cycle is now probe → dispatch (or one-line `--apply-pseudo`) → verify (`--verify-ledger`)/commit — fewer orchestrator messages per pseudo-skill/ledger-guard cycle.
**Ground-truth verification:** grep confirms `apply-pseudo`/`verify-ledger` referenced in both SKILLs; `grep 'first WRITE | write …VALIDATED.md | WRITE …COMPLETED.md'` returns no orchestrator-hand-writes for supported pseudo-skills; the 3 regression gates exit 0 (scripts untouched by this WU); only the 2 SKILL files in `git status`.
**Files modified:** `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.

#### Post-Phase (Phase 5 — Integration Verification + CLAUDE.md review + part close)
**Integration verification:** the five subcommands behave identically to the prose they replaced, and the prose fallbacks are now fully removed from the two batch orchestrators (WU-6) — but ONLY after the subcommands existed (WU-1..5 committed first; Rule 9 separate-commit sequencing held throughout, so any mid-phase interruption left working prose fallbacks). Cross-WU coherence: `--verify-ledger` (WU-1) reuses the same git-clean/HEAD logic family as `git_guard_status` (WU-5); `--apply-pseudo __mark_complete__` (WU-2) is the single receipt author the consumers (WU-6) + the completion-integrity gate now call; `--neutralize-sentinel` (WU-3) is documented in the CLI surface for the decision-resume/blocked-resolution rename sites (those shared components are Phase-6 scope to rewire); `--repeat-count`/`--probe` (WU-4/WU-5) are flag-gated so default output stays byte-identical (Phase-1 baselines + zero-drift probe preserved — independently re-proved each batch). All five subcommands share the same exit-1-on-not-ok convention so the orchestrator's `&&` chains short-circuit correctly.
**CLAUDE.md review:** `user/scripts/CLAUDE.md` "## CLI surface" updated with the five new subcommands (+ the exit-1 ledger/pseudo-skill convention). No other CLAUDE.md / structural doc change warranted (no new directory; the signature file lives in OS-temp, deliberately outside the repo tree).
**Part-end full quality gate (MANDATORY — all exit 0):** `python3 ~/.claude/scripts/lazy-state.py --test` (0), `python3 ~/.claude/scripts/bug-state.py --test` (0), `python3 ~/.claude/scripts/test_lazy_core.py` (143/143, 0) — run + passed fresh as the final chained command before the part-close commit. (`~/.claude/scripts/*.py` resolve to the repo's `user/scripts/*.py` — same inode — so the gate tested the edited code.)
**Carried follow-ups (Phase 6 candidates, NOT blocking part close):**
- `__flip_plan_complete_stale__` is not yet scripted by `--apply-pseudo` (stays inline in both batch skills) — a future `apply_pseudo` name addition could fold it in (trivial — same single-line frontmatter flip as cloud_saturated, different commit message).
- `verify_ledger`'s own `clean_tree` (WU-1) uses stdout-only logic (the `returncode==0` hardening landed only in `git_guard_status`/WU-5) — harmless in production (always real repo_root); a one-line consistency fix candidate.
- The shared rename components (`decision-resume.md`/`blocked-resolution.md`/`parked-flush.md`) still do `git mv … _RESOLVED*` inline rather than calling `--neutralize-sentinel`; rewiring those is Phase-6 contradiction-sweep scope (they are shared components, out of WU-6's two-batch-skill file scope).

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
