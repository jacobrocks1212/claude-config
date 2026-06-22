# Implementation Phases — Per-feature cycle cap defers incomplete work instead of completing it

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is a docs/scripts harness repo with no Tauri app, no MCP HTTP server, and no audio/UI surface; this fix touches `lazy_core.py` / `lazy-state.py` / their docs only. Validation is the hermetic Python `--test` smoke harness (`lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py`) + the byte-pinned baseline regeneration — the only acceptance gate this repo has. (Per `docs/features/mcp-testing/SPEC.md`'s untestable classes: "build tooling / non-app script with no runtime app integration".)

## Cross-feature Integration Notes

- **feature-budget-guard-and-skip-ahead (kind=soft, Complete):** introduced `compute_per_feature_ceiling` (`lazy_core.py` ~10273, Locked Decision 4) and the marker-gated trip/defer/evict block (`lazy-state.py` ~2086, Phase 2). This bug reverses ONLY that feature's **default policy** (default-on → default-off); its **skip-ahead** half (gated-head advance, Phase 3, `lazy-state.py` ~2244+, `--strict-research-halt` opt-out) is explicitly out of scope and untouched (operator decision, SPEC §Verified Symptoms 3 + Proven Finding 4). No realign needed — the feature is Complete and this is a deliberate policy supersession, recorded in the SPEC `**Related:**` block.
- **budget-guard-defers-near-complete-feature (Fixed, commit `2280ad6`):** the prior *softening* (near-completion grace + corrective-cycle discount + end-of-run resume flush, all in `lazy-state.py` ~2096+ and `lazy_core.budget_trip_signals` / `feature_is_near_complete` / `count_validation_corrective_cycles`). This bug supersedes that softening with full default-off. The softening helpers are KEPT WIRED — they become live only under the `--per-feature-cycle-cap` opt-in (dead code under the default). Removing them would regress the opt-in path (SPEC Open Question 2 resolution).

## Validated Assumptions

All load-bearing assumptions are **code-provable** (pure-function return value + a single None-tolerant call site + doc text) — no runtime-coupled assumption exists, so the Step-2.7 runtime-validation gate is skipped with that reason recorded. Verified at planning time against ground truth:

- **`compute_per_feature_ceiling` default branch is the SINGLE arming point** — `lazy_core.py:10307` (`if override is not None: return int(override)`) then the formula at 10321–10323. Making the no-override path return `None` short-circuits the whole guard. (grep-confirmed: the symbol is referenced only at `lazy-state.py:1651` + its own definition + `test_lazy_core.py`.)
- **The one call site already tolerates `None`** — `lazy-state.py:1650-1656` binds `_bg_ceiling`, and the trip gate at `lazy-state.py:2086` is `if _bg_marker is not None and _bg_ceiling is not None:`. A `None` ceiling makes the entire budget block (defer/evict/grace/flush) unreachable with zero changes below it. (Read-confirmed.)
- **Feature-pipeline-only — no `bug-state.py` mirror owed** — `lazy_parity_audit.py` does not reference `compute_per_feature_ceiling` / `budget` / `per_feature` (grep-confirmed: zero matches), so the justified divergence holds and the audit stays green. (SPEC Proven Finding 3.)

## SPEC-example capability audit

The SPEC's only code example is the existing `compute_per_feature_ceiling` body and the call site — both real, present, and read at planning time (no rejected/unimplemented capability consumed). The change uses ordinary Python (`return None`, a widened `int | None` annotation). No external API surface. Audit clean.

## MCP tool-existence audit

No-op — `repos/claude-config/.claude/skill-config/mcp-tool-catalog.md` is absent (this repo declares no MCP tool surface). Recorded skip reason: `no mcp-tool-catalog.md configured for this repo`.

---

### Phase 1: Invert the default — `compute_per_feature_ceiling` returns `None` when no override

**Scope:** Flip the per-feature budget guard to OFF-by-default. The no-override (default) branch of `compute_per_feature_ceiling` returns `None` (guard disabled — `_bg_ceiling is not None` short-circuits the entire budget block); the `override` branch is unchanged so `--per-feature-cycle-cap <N>` re-arms a fixed ceiling. This is the whole behavioral fix — a single source change plus its tests. No change to the trip/defer/evict/grace/flush machinery below the gate (it becomes opt-in-only dead code under the default).

**Deliverables:**
- [x] `lazy_core.py` `compute_per_feature_ceiling`: replace the default-branch fair-share formula return (`return max(6, min(forty_percent_arm, fair_share_arm))` at ~10323, plus the `q <= 0` early `return 6` at ~10320) so that **all** no-override paths return `None`. The `override is not None: return int(override)` branch (incl. the deliberate `override=0`) stays byte-identical. Widen the signature/return annotation `int` → `int | None` and rewrite the docstring to describe default-off (guard disabled unless `--per-feature-cycle-cap` supplied; `max_cycles` is the sole default budget).
- [x] Re-pin the existing `test_compute_per_feature_ceiling_*` formula characterization tests in `test_lazy_core.py` (~21315-21376): the override test stays as-is; the four formula tests (`_six_floor_small_run`, `_deep_queue_six`, `_forty_percent_cap_arm`, `_zero_queue_no_div_by_zero`) and `_pure_no_side_effects` must now assert the **no-override default returns `None`** (e.g. `assert compute_per_feature_ceiling(12, 2) is None`) AND that supplying `override=N` still returns `N` verbatim. Keep `_pure_no_side_effects`'s purity assertion (two identical no-override calls both `None`).
- [x] Tests: a new `lazy-state.py --test` fixture asserting **default-off** — a live run marker + a feature whose `per_feature_forward_cycles` count exceeds the old floor-6 ceiling produces NO budget trip (no `defer`/`evict`, `budget_guard` probe field absent/null), proving the guard never arms without the flag.
- [x] Tests: re-pin any existing `lazy-state.py --test` fixture that asserts a default-on trip/defer/evict to pass `--per-feature-cycle-cap <N>` (opt-in arms the guard), so the opt-in path stays characterized. (Locate via the `--test` harness; if none assert a default-on trip, record that and rely on the new opt-in-arms fixture instead.)
- [x] Tests: a baseline-regression fixture asserting a no-marker / no-flag probe stays byte-identical to today (the budget block is marker-gated AND now ceiling-gated → default output unchanged).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/test_lazy_core.py` both pass with the re-pinned + new fixtures, AND `python3 -c "import sys; sys.path.insert(0,'user/scripts'); import lazy_core; assert lazy_core.compute_per_feature_ceiling(12, 2) is None; assert lazy_core.compute_per_feature_ceiling(12, 2, override=4) == 4"` exits 0 — the default returns `None`, the override re-arms.

**Runtime Verification** *(checked by the hermetic --test harness — NOT by the implementation agent):*
- [ ] <!-- verification-only --> `python3 user/scripts/lazy_core.py`-importing assertion above passes (default `None`, override verbatim).
- [ ] <!-- verification-only --> `lazy-state.py --test` default-off fixture: long-running feature under a live marker, no flag → no budget trip.
- [ ] <!-- verification-only --> `lazy-state.py --test` opt-in fixture: same feature WITH `--per-feature-cycle-cap N` → trip/defer fires (guard re-arms).

**MCP Integration Test Assertions:** N/A — no runtime-observable MCP behavior in this repo; validation is the Python `--test` harness (see header `**MCP runtime:** not-required`).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `compute_per_feature_ceiling` (~10273): default branch returns `None`; widen return type to `int | None`; rewrite docstring. (verified: exists; symbol referenced only at the one call site + tests.)
- `user/scripts/test_lazy_core.py` — re-pin the `test_compute_per_feature_ceiling_*` block (~21315-21376) for default-`None`. (verified: exists.)
- `user/scripts/lazy-state.py` — NO source change (the `_bg_ceiling is not None` gate at 2086 already short-circuits); add `--test` fixtures only (default-off, opt-in-arms, baseline-regression). (verified: exists; gate already None-guarded.)

**Testing Strategy:** Pure-function characterization (`test_lazy_core.py`) proves the default/override branch split directly. State-machine fixtures (`lazy-state.py --test`) prove end-to-end: default = no trip, opt-in = trip. The baseline-regression fixture proves default-output byte-identity. All hermetic, no runtime.

**Integration Notes for Next Phase:**
- The trip/defer/evict/grace/flush block (`lazy-state.py` ~2086+) and the softening helpers (`feature_is_near_complete`, `count_validation_corrective_cycles`, `budget_trip_signals`, end-of-run resume flush) are KEPT WIRED — they are correct refinements of the *armed* guard and live only under `--per-feature-cycle-cap`. Do NOT delete them in Phase 2 (SPEC Open Question 2 resolution).
- After regenerating fixtures, the byte-pinned baselines (`tests/baselines/lazy-state-test-baseline.txt`, and `bug-state-test-baseline.txt` if it shifts — it should NOT, bug pipeline untouched) must be regenerated via `_normalize_smoke_output`, never by hand (see Phase 2).

#### Phase 1 Implementation Notes

- **2026-06-22 — plan part 1 (WU-1 + WU-2), executed INLINE (no-Agent dispatch override), test-first.** Review verdict: PASS.
- **WU-1 (`lazy_core.py` + `test_lazy_core.py`):** Inverted `compute_per_feature_ceiling`'s no-override branch to `return None` (removed the dead `q<=0 → 6` / `max(6, min(forty_percent_arm, fair_share_arm))` formula). The `override is not None: return int(override)` branch is byte-identical (incl. `override=0`). Return annotation widened `int → int | None`; docstring rewritten for default-off. Re-pinned the five formula tests to assert `is None` by default (confirmed RED against the un-flipped source first, then GREEN); `_forty_percent_cap_arm` adds `override=20 → 20` to keep the opt-in fixed-ceiling characterized. The override test is unchanged.
- **WU-2 (`lazy-state.py --test` fixtures, NO production-code edit):** the trip gate at `lazy-state.py:2086` (`_bg_ceiling is not None`) already short-circuits on a `None` ceiling — no logic edit needed. Re-pinned every existing default-on-trip fixture (budget-guard cases a/b/d, ncg-grace f/g/h, ncg-flush j/k/l) to pass `per_feature_cycle_cap=8` (the exact ceiling the old default formula produced for C=20, Q=2) so the opt-in trip machinery stays characterized. Added three new fixtures: (e2) baseline-regression byte-identity (no-marker/no-flag probe carries no budget-block keys), (f1) default-off (live marker + over-ceiling count + NO flag → no trip, no deferral recorded), (f2) opt-in-arms (same marker + `per_feature_cycle_cap=8` → defer fires).
- **Files modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`, `user/scripts/lazy-state.py`.
- **Gates:** `test_lazy_core.py` 766/767 (the lone fail is `test_lazy_state_test_output_matches_baseline` — EXPECTED, the baseline regen is deferred to Phase 2/part 2; the single diff is the bg fixture's print-line suffix `+ default-off + opt-in-arms`, no logic regression). `lazy-state.py --test` exit 0. `bug-state.py --test` green. `lazy_parity_audit.py` green (feature-pipeline-only, no bug mirror owed). `lint-skills.py` green.

---

### Phase 2: Update the documentation surfaces + regenerate byte-pinned baselines

**Scope:** Reword every doc surface that describes the guard as "default-on" to "OFF by default; `--per-feature-cycle-cap <N>` opt-in arms a fixed ceiling; whole-run `max_cycles` is the sole default budget." Regenerate the byte-pinned `--test` baselines so the new/re-pinned fixtures land canonically. Re-confirm the parity audit stays green.

**Deliverables:**
- [ ] `user/scripts/CLAUDE.md` — the `--per-feature-cycle-cap` CLI block (the long line describing the default formula + the three composite softenings): reword the OPENING from "override the dynamically-computed per-feature ceiling / Default (flag absent): L_task = …" to "OFF by default — the guard never arms; `--per-feature-cycle-cap N` opt-in arms a fixed ceiling N. The whole-run `max_cycles` is the sole default budget." Keep the softening-behavior description but re-frame it as "under the opt-in flag the armed guard applies these three composite-signal refinements …". (verified: block present.)
- [ ] `user/skills/lazy-batch/SKILL.md` — the `--per-feature-cycle-cap <N>` flag description (~line 66) and any `budget_guard`-probe / argument-hint references: reword "overriding the dynamically-computed per-feature ceiling … Default (flag absent): lazy-state.py computes L_task = …" → "arms the per-feature budget guard with a fixed ceiling N; **OFF by default** (the guard never arms without this flag — the whole-run `max-cycles` is the sole default budget)." (verified: present at lines 4, 66, 72; budget-trip notification §1c.6/479 stays — it only fires under the now-opt-in guard.)
- [ ] `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — the coupled-pair mirror of the `--per-feature-cycle-cap` flag description (~line 84) + argument-hint (line 4) + usage line (89): mirror the lazy-batch reword exactly, preserving the "NO cloud divergence — identical semantics to /lazy-batch" note. (verified: present; `--cloud`-identical per SPEC Proven Finding 3.)
- [ ] Regenerate `tests/baselines/lazy-state-test-baseline.txt` by piping live `lazy-state.py --test` output through `_normalize_smoke_output` (never by hand) so the new default-off / opt-in-arms / baseline-regression fixtures are captured canonically. (verified: baseline path documented in `user/scripts/CLAUDE.md` → Testing.)
- [ ] Confirm `tests/baselines/bug-state-test-baseline.txt` is UNCHANGED (bug pipeline is untouched — if it shifts, that is a regression to investigate, not regenerate).
- [ ] Re-confirm `python3 user/scripts/lazy_parity_audit.py` stays green (no `bug-state.py` mirror owed — the budget machinery is feature-only; grep-confirmed at planning time).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` matches the regenerated `lazy-state-test-baseline.txt` byte-for-byte (via `_normalize_smoke_output`), `python3 user/scripts/bug-state.py --test` matches its UNCHANGED baseline, and `python3 user/scripts/lazy_parity_audit.py` exits 0.

**Runtime Verification** *(checked by the hermetic --test harness):*
- [ ] <!-- verification-only --> `lazy-state.py --test` output == regenerated `lazy-state-test-baseline.txt` (normalized).
- [ ] <!-- verification-only --> `bug-state.py --test` output == its UNCHANGED baseline (proves zero bug-pipeline drift).
- [ ] <!-- verification-only --> `lazy_parity_audit.py` exits 0 (feature-only divergence preserved).

**MCP Integration Test Assertions:** N/A — docs + baseline regeneration, no runtime-observable MCP behavior.

**Prerequisites:**
- Phase 1: the source change + new/re-pinned fixtures must exist before the baselines are regenerated (the baseline captures the fixture output).

**Files likely modified:**
- `user/scripts/CLAUDE.md` — `--per-feature-cycle-cap` CLI block reword. (verified: exists.)
- `user/skills/lazy-batch/SKILL.md` — flag description + argument-hint reword (lines 4, 66, 72). (verified: exists.)
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — coupled-pair mirror (lines 4, 84, 89). (verified: exists.)
- `tests/baselines/lazy-state-test-baseline.txt` — regenerated via `_normalize_smoke_output`. (verified: path documented.)
- `tests/baselines/bug-state-test-baseline.txt` — asserted UNCHANGED, not edited. (verified: path documented.)

**Testing Strategy:** Baseline byte-equality is the regression net for the state machine. The parity audit is the regression net for the coupled-pair / feature-bug divergence invariant. Doc rewording is verified by re-reading the changed surfaces against the new default-off contract.

**Integration Notes for Next Phase:** None — Phase 2 is terminal. When the last deliverable lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending); the state machine routes to the validation tail. The `__mark_fixed__` gate (orchestrator-owned) flips SPEC `**Status:**` to `Fixed` and writes `FIXED.md` after the tail.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to `Fixed` and writes `FIXED.md` once the validation tail passes. This plan never flips it.

#### Implementation Notes

- **Spin-off legs:** none. This bug's scope is self-contained (no discovered out-of-scope work). The SPEC `**Related:**` block already cross-references the superseded prior softening bug (`budget-guard-defers-near-complete-feature`) and the introducing feature.
- ⚖ policy: default-off computes L_task or nothing → **nothing** (operator chose `max_cycles`-only backstop, not warn-only soft cap; SPEC Open Question 1 — scope-class, no product divergence beyond the already-locked operator decision).
- ⚖ policy: softening helpers removed or kept wired → **kept wired** (live only under the `--per-feature-cycle-cap` opt-in; removing them would regress the opt-in path; SPEC Open Question 2 — scope-class).
