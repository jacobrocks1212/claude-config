---
kind: research-summary
feature_id: toolify-auto-promotion
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — toolify-auto-promotion

Codebase survey verifying every surface the SPEC names, at lane HEAD (branch
`lane/toolify-auto-promotion`, base `b5c1021`). All decisions D1–D10 resolved (operator-approved
2026-07-04 — recommended options taken); this summary records what the code actually looks like at
implementation time.

## Verified surfaces (with drift notes)

| SPEC anchor | Actual location | Status |
|-------------|-----------------|--------|
| `enqueue_adhoc()` at `lazy-state.py:582` | `user/scripts/lazy-state.py:582` | ✓ exact. Signature `(repo_root, feature_id, name, brief, spec_dir=None, tier=0)` — the `tier` param exists at line 588 and is CLI-exposed via the pre-existing `--tier` flag (default 0), already threaded into the `args.enqueue_adhoc` handler (`lazy-state.py:9870-9877`). D4's claim "it is just not CLI-exposed" is **stale**: `--tier` is already wired; only `--stub` and `--at {head,tail}` are net-new. |
| `_spec_text_has_stub_marker` at `lazy-state.py:1076` | `lazy-state.py:1086` | ✓ (drifted +10 lines). Matched forms confirmed: legacy `**Status:** Draft (research stub)`, legacy `> Stub generated from advanced feature research`, anchored `^\s*\*\*Status:\*\*\s*.*Draft \(pre-Gemini\)`, anchored `^\s*>.*Draft \(pre-Gemini\)`. |
| `_stub_is_queue_flag_only()` at `lazy-state.py:1137` | `lazy-state.py:1147` | ✓ (drifted +10). Confirmed: queue flag True AND no SPEC-text marker ⇒ post-baseline clear-and-advance (`clear_queue_stub`) — the D5 gate-bypass hazard is real; queue-flag-only stubs skip Step 4.5. |
| Step 4.5 dispatch | `lazy-state.py:2667-2697` | ✓. A SPEC-text stub marker routes `sub_skill: "spec"`, `current_step: "Step 4.5: stub-spec detected"`. NOTE (deferred-empirical check resolved by code reading): the Step-4 `ADHOC_BRIEF.md` brief branch (`lazy-state.py:2648`) is reachable **only when SPEC.md is absent** — once the materializer writes the stub SPEC.md, the probe reads it and fires Step 4.5, so ADHOC_BRIEF.md + stub SPEC.md coexisting routes 4.5 (stub branch), as the SPEC hoped. If the SPEC write fails post-enqueue, the brief branch routes Step 4 → `/spec` (degraded but never wedged). |
| Miner surface | `user/scripts/toolify-miner.py` | ✓. `Candidate` dataclass (`signature/occurrences/run_count/est_tokens_per_occurrence/score/deterministic/above_bar/n_calls/sample_tools`), `signature()` deterministic (values elided, sorted key tuples), `mine()` ranked, `render_markdown()` (columns `rank/above_bar/signature/occurrences/runs/est_tokens/occ/score/deterministic` — no id column yet), `render_json()` (9 keys). Constants `MIN_RUNS=2`, `TOKEN_HEAVY_THRESHOLD=600`, `EST_TOKENS_PER_CALL=120`. |
| Importlib pattern at `test_toolify_miner.py:44-52` | ✓ exact | `spec_from_file_location("toolify_miner", …)` + register in `sys.modules` before `exec_module`. `toolify-promote.py` reuses this for the miner; `lazy_core.py` is un-hyphenated so a plain `sys.path` import works for `_atomic_write` (`lazy_core.py:105`). |
| `test_toolify_miner.py` runner pattern | ✓ | Self-contained `_TESTS` list from `globals()`, `main()` prints PASS/FAIL per test, exit 0/1; also pytest-discoverable. `test_toolify_promote.py` mirrors it. |
| `toolify-bar.md` | `docs/features/unified-pipeline-orchestrator/toolify-ledger.json` sibling target | ✓. Candidate-schema table (9 rows — gains `candidate_id`), promotion checklist steps 1–7 (annotations land per Phase 4), constants table. |
| Parity audit | `user/scripts/lazy_parity_audit.py` | ✓. `audit_state_script_parity()` (line 340) checks five fixed regex surfaces (`set_active_repo_root`, `--reorder-queue`, `--reassert-owner`, host-capability fail-fast, `cycle_prompt_ref`); **nothing audits `--enqueue-adhoc` flag symmetry**, so the feature-only `--stub`/`--at` flags cannot trip it. Confirmed exit 0 pre-change; re-confirmed post-change (justified divergence: the bug pipeline has no stub step and orders by severity — no mirror owed). |
| `--test` baselines | `user/scripts/tests/baselines/` | ✓. `lazy-state-test-baseline.txt` byte-pins `--test` output after `_normalize_smoke_output` (`test_lazy_core.py:40`); new enqueue fixture prints require a baseline regen **only via the helper** (README rule). `bug-state-test-baseline.txt` untouched (no bug-side change). |
| `lazy-batch-retro` skill | `user/skills/lazy-batch-retro/SKILL.md` (user-level, NOT repo-scoped — the root-CLAUDE.md table row saying repo(algobooth) is stale) | ✓. Steps 6c → 7 (commit) → 8 (final bookend); the report-only toolify step lands between 6c and 7 (new Step 6d) so its lines ride the same bookend. No coupled twin (`Notes`: "NOT paired"). |
| Adhoc enqueue component | `user/skills/_components/adhoc-enqueue.md` | ✓. Documents head/tier-0 semantics; unchanged by this feature (the materializer shells the CLI directly and is not an orchestrator ad-hoc flow — the component's default-path docs stay accurate because the new flags are default-off). |

## Integration points

1. **`toolify-miner.py`** — additive `candidate_id` (SHA-256[:12] of `signature`) on `Candidate`,
   threaded through `mine()` and both renderers. Existing tests assert schema keys by inclusion
   (not exact-set), so the additive field passes them unchanged; new tests pin id
   stability/uniqueness/render presence.
2. **`lazy-state.py --enqueue-adhoc`** — net-new `--stub` / `--at {head,tail}` flags (+`stub`,
   `at` params on `enqueue_adhoc()`); `--tier` already exists. Defaults byte-identical (the
   `"stub"` key is written only when true; head insert unchanged). Feature-pipeline-only: the
   handler refuses `--stub`/`--at tail` combined with `--type bug` (loud, not silent-ignore).
3. **`toolify-promote.py`** — new sibling script; shells `lazy-state.py --enqueue-adhoc --tier 2
   --stub --at tail --repo-root …` via `subprocess.run(check=…)`; writes the stub SPEC; appends
   the ledger last (failure-safe ordering per SPEC Technical Design).
4. **Ledger** — `docs/features/unified-pipeline-orchestrator/toolify-ledger.json`, object keyed
   `entries.<candidate_id>`, written via `lazy_core._atomic_write`. Default path derived from the
   script's own resolved location (`Path(__file__).resolve()` → repo root two levels up), with a
   `--ledger` override as the hermetic test seam.
5. **`/lazy-batch-retro`** — new report-only Step 6d printing NEW above-bar candidates with
   ready-to-run promote lines; never invokes the materializer (D3-A). SKILL.md edit ⇒ lane-local
   projection + lint run required.

## Spec assumptions that proved wrong (none load-bearing)

- **`--tier` "not CLI-exposed" (D4-B)** — stale; the flag already exists and threads into
  `enqueue_adhoc()`. Scope shrinks: only `--stub`/`--at` are added.
- **Line anchors 1076/1137** — drifted to 1086/1147 (same functions, same semantics).
- **`lazy-batch-retro` scope** — the root CLAUDE.md skill-family table lists it as repo-scoped
  (algobooth); it actually lives at `user/skills/lazy-batch-retro/` (user-level). The Phase-4 edit
  targets the real path.
- **Deferred empirical check "ADHOC_BRIEF.md + stub SPEC.md routes 4.5"** — resolvable by code
  reading (the brief branch is inside the SPEC.md-absent arm); additionally pinned by a
  scratch-repo probe test in `test_toolify_promote.py`.
- **Deferred empirical check "run the miner over the real workstation corpus"** — NOT possible in
  this cloud container (no `~/.claude/projects` session corpus); remains deferred to a
  workstation session (recorded in PHASES.md).
