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
- [ ] Cloud-mode fixtures (currently zero `cloud=True` coverage)
- [ ] Device re-open fixture (`STEP_DEVICE_REOPEN`)
- [ ] Step-9 `SKIP_MCP_TEST.md` / `MCP_TEST_RESULTS.md` fixtures
- [ ] `backfill_receipts` fixture; severity-ordering fixture (multiple unlisted bugs)
- [ ] Stale harness docstrings cleaned (both scripts)
- [x] AlgoBooth `--repo-root` JSON baseline for bug-state.py

**Runtime Verification:**
- [ ] `python3 ~/.claude/scripts/lazy-state.py --test` exits 0
- [ ] `python3 ~/.claude/scripts/bug-state.py --test` exits 0 and matches baseline
- [ ] `python3 ~/.claude/scripts/test_lazy_core.py` exits 0

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

---

## Phase 2 — Integrity side-doors (P0)

**Goal:** No model-authorable path to VALIDATED/SKIP/receipts; content-validated receipts;
cloud gates in bug-state; standing-directive confirmation.

**Entry criteria:** Phase 1 baselines green.

**Deliverables:**
- [ ] `lazy_core.has_completion_receipt()` validates frontmatter (`kind:`, `provenance:`); malformed → treated missing + diagnostic
- [ ] bug-state cloud Step-2 skip + Step-10 hard-halt (mirror lazy-state); dead terminals resolved
- [ ] Unqueued Fixed-no-receipt bypass closed (uniform receipt gate or diagnostic)
- [ ] `MCP_TEST_RESULTS.md` commit-sha freshness check before `__write_validated_from_results__`
- [ ] `SKIP_MCP_TEST.md` `granted_by: operator|pipeline`; coverage-audit + `__write_validated_from_skip__` honor it
- [ ] D6: LOOP-DETECTED block restricted to NEEDS_INPUT/BLOCKED (all 3 orchestrators) + stale anchor fixed
- [ ] Step 1e.4a: no evidence-less verification-box ticking; mismatch → NEEDS_INPUT
- [ ] Input-audit runs after needs-input/blocked spec cycles; >4-decision overflow → durable follow-up NEEDS_INPUT
- [ ] Standing-directive echo-back protocol; no early stop with budget+queue remaining; non-integer max_cycles rejected with question
- [ ] D5: mcp-test inline-fix policy (test-first, disclosed, never self-certifies) in prompt overrides

**Runtime Verification:**
- [ ] All three regression gates green
- [ ] New fixtures: empty receipt → completion-unverified; cloud deferral → halt not `__mark_fixed__`; stale-sha results → no validation; pipeline-granted skip → NEEDS_INPUT

**Implementation Notes:**

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
