# Per-feature cycle cap defers incomplete work instead of completing it — Investigation Spec

> The per-feature budget guard (`L_task` ceiling) is **default-on**: it trips on a per-feature forward-cycle count and defers (then evicts) a feature to the queue tail mid-progress. The operator rejects this behavior outright — a half-done feature parked at the tail is worse than letting it finish. Make the guard **opt-in** (off by default; armed only via `--per-feature-cycle-cap <N>`); rely on the whole-run `max_cycles` ceiling as the sole default budget.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-22
**Fixed:** 2026-06-22
**Fix commit:** a8f9307
**Placement:** docs/bugs/per-feature-cycle-cap-defers-incomplete-work
**Related:**
- `docs/features/feature-budget-guard-and-skip-ahead/` (SPEC + PHASES — the feature that introduced this default-on guard; this bug reverses its default, NOT its skip-ahead half)
- `docs/bugs/_archive/budget-guard-defers-near-complete-feature/` (Fixed 2026-06-21, commit `2280ad6` — the prior *softening* of this same guard: near-complete grace + corrective-cycle discount + end-of-run resume flush. This bug supersedes that softening with full default-off.)
- `docs/bugs/_archive/byref-dispatch-undercounts-forward-cycles/` (the forward-cycle counter the guard reads)

---

## Verified Symptoms

1. **[VERIFIED]** The operator dislikes the per-feature cycle cap because it **leaves work in progress rather than completing it** — confirmed verbatim in the request: *"I don't like the per-feature cycle cap because it leaves work in progress rather than completing it. Please spec a bug to remove that behavior."*
2. **[VERIFIED]** The behavior is still live one day after the prior softening fix. The session screenshot (AlgoBooth `/lazy-batch`, 2026-06-22) shows `d2-sample-import-ui` **budget-evicted** this run — *"d2 was budget-evicted this run (6 forward cycles = L_task cap) — on-disk progress preserved"* and *"budget-guard skip-ahead advanced to the next independent item"* — i.e. the `2280ad6` grace/flush softening did not prevent a second eviction of the same feature at the `L_task=6` floor.
3. **[VERIFIED — operator decisions, 2026-06-22 AskUserQuestion]:**
   - **Scope:** remove the **budget guard only** (the per-feature cap + defer/evict). KEEP the unrelated skip-ahead-past-a-gated-head mechanism that ships in the same feature.
   - **Backstop:** the **whole-run `max_cycles`** ceiling is the sole default budget after removal. A stubborn feature burns run budget and the run stops at `max_cycles`; it is never deferred mid-progress.
   - **Override:** keep `--per-feature-cycle-cap <N>` as an **OFF-by-default opt-in** escape hatch for a known-runaway queue — not a full deletion.

## Reproduction Steps

1. Run `/lazy-batch <N>` (no `--per-feature-cycle-cap`) on a queue where one feature legitimately needs ≥ `L_task` forward cycles (e.g. a corrective `/mcp-test` re-plan/re-implement loop).
2. `compute_per_feature_ceiling(max_cycles, ready_queue_depth)` returns a finite ceiling (floor 6 on small runs / shallow queues), so the budget block at `lazy-state.py:2086` is armed.
3. The feature's `per_feature_forward_cycles` count crosses the ceiling → first trip defers to the queue tail; a second trip evicts (dead-letters) it.

**Expected (post-fix):** With no `--per-feature-cycle-cap`, the guard never arms — no feature is ever deferred or evicted for exceeding a per-feature count. The feature runs to completion (or the whole run stops at `max_cycles`). Supplying `--per-feature-cycle-cap <N>` re-arms the guard with a fixed ceiling `N`.
**Actual (today):** The guard is default-on with a dynamically-computed `L_task`; legitimate long features are deferred/evicted mid-progress, leaving parked work and (per the prior bug) an idle hot runtime.
**Consistency:** Deterministic — any feature exceeding the computed (or floor-6) ceiling trips, regardless of proximity to completion. The prior grace/flush softening narrows but does not eliminate it (symptom 2 is the proof).

## Evidence Collected

### Source Code

**Ceiling computation — `user/scripts/lazy_core.py:10273` (`compute_per_feature_ceiling`):**

```python
if override is not None:
    return int(override)          # --per-feature-cycle-cap path (keep)
...
return max(6, min(c * 4 // 10, (c // q) * 2))   # DEFAULT — always returns a finite ceiling
```

The default branch (no override) **always returns a finite ceiling**, so the guard is always armed under a live run marker. This is the single point that makes the guard default-on.

**Ceiling binding — `user/scripts/lazy-state.py:1650`:**

```python
_bg_ceiling = (
    lazy_core.compute_per_feature_ceiling(_bg_max_cycles, _bg_ready_depth, override=per_feature_cycle_cap)
    if _bg_marker is not None else None
)
```

**Trip + defer/evict gate — `user/scripts/lazy-state.py:2086`:**

```python
if _bg_marker is not None and _bg_ceiling is not None:   # <-- already None-guarded
    ...
    if _bg_signals["should_defer"]:
        _bg_action = "defer" if prior_defers < 1 else "evict"
        ...
```

**Key finding:** the trip gate is already guarded by `_bg_ceiling is not None`. Making the *default* ceiling `None` (only the override returns a number) disables the entire guard with no change to the trip/defer/evict/grace/flush code below it — that machinery simply becomes unreachable unless `--per-feature-cycle-cap` is supplied. The skip-ahead block (gated-head, `feature-budget-guard-and-skip-ahead` Phase 3, `lazy-state.py` ~line 2244+) is a *separate* branch and is untouched.

### Git History

Investigation on `main` (claude-config). The introducing feature is `Complete`; the prior softening bug (`budget-guard-defers-near-complete-feature`) is `Fixed` (commit `2280ad6`). No open bug currently covers the default-on policy itself.

### Related Documentation

- `user/scripts/CLAUDE.md` → the `--per-feature-cycle-cap` CLI block documents the full default-on formula plus the three composite-signal softenings (near-completion grace, corrective-cycle discount, end-of-run resume flush) — all of which become opt-in-only after this fix.
- The introducing feature's own `RESEARCH.md` pre-flagged the single-signal weakness (no proximity/corrective discrimination); the prior bug confirmed it. Default-off is the operator's chosen resolution rather than further signal-tuning.

## Theories

### Theory 1: The guard is default-on by design; the operator wants it default-off — **CONFIRMED**
- **Hypothesis:** Nothing is malfunctioning — the guard does exactly what `feature-budget-guard-and-skip-ahead` Locked Decision 2/4 specified (default-on dynamic ceiling, defer-then-evict). The defect is a **policy mismatch**: the operator prefers completion over starvation-avoidance, so the default should flip to off.
- **Supporting evidence:** Code path is deterministic and matches the SPEC; operator request is explicit; the prior softening (grace/flush) was an attempt to keep default-on *and* avoid the worst case, but symptom 2 shows it still evicts.
- **Contradicting evidence:** None. Starvation-avoidance (the original `d8-live-looping` motivation) is genuinely sacrificed — but the operator accepts that, backstopped by `max_cycles` and the retained opt-in flag.
- **Status:** Confirmed.

## Proven Findings

1. **Root cause:** `compute_per_feature_ceiling` returns a finite ceiling on its default (no-override) branch, arming the per-feature budget guard for every `/lazy-batch` run. The behavior is correct-as-specified but the **default policy** is wrong for the operator's workflow.
2. **Fix shape (operator-decided):** invert the default. The no-override branch of `compute_per_feature_ceiling` returns **`None`** (guard disabled — `_bg_ceiling is not None` short-circuits the whole budget block); the `override` branch is unchanged so `--per-feature-cycle-cap <N>` re-arms a fixed ceiling. Return type widens `int → int | None`; the one call site (`lazy-state.py:1650`) already tolerates `None`. No deletion of the trip/defer/evict/grace/flush/`queue-exhausted-budget-deferred` machinery — it becomes opt-in-only (dead code under the default, live under the flag), which keeps the escape hatch working and minimizes blast radius.
3. **Scope of impact:** **Feature pipeline only.** `bug-state.py` has no per-feature ceiling (grep-confirmed; `compute_per_feature_ceiling` / `_DEFERRED_BUDGET` / `budget_*` are referenced solely by `lazy-state.py` + `lazy_core.py`). No coupled-pair mirror to `bug-state.py` is owed (justified divergence — re-confirm against `lazy_parity_audit.py` during planning). The `/lazy-batch` ↔ `/lazy-batch-cloud` wrapper pair is environment-agnostic for this flag; the cap is `--cloud`-identical, so no wrapper prose diverges.
4. **Skip-ahead is out of scope.** The gated-head skip-ahead (default-on, `--strict-research-halt` opt-out) is a separate mechanism in the same feature and is explicitly preserved (operator decision).
5. **No data loss in flight:** deferral/eviction were always run-scoped with on-disk progress preserved; this change simply stops the run-scoped reorder from happening by default.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Ceiling default | `user/scripts/lazy_core.py` (`compute_per_feature_ceiling` ~10273) | Default (no-override) branch returns `None` instead of the fair-share formula; `override` branch unchanged. Widen return type to `int | None`; update docstring. |
| Trip / defer / evict | `user/scripts/lazy-state.py:2086`+ | No code change required (already `_bg_ceiling is not None`-guarded) — verify it stays unreachable under the default and reachable under the flag. |
| Tests | `user/scripts/test_lazy_core.py`, `lazy-state.py --test` fixtures, `tests/baselines/lazy-state-test-baseline.txt` | Existing fixtures that assert a default-on trip/defer/evict must be re-pinned to pass `--per-feature-cycle-cap` (opt-in arms the guard); add a default-off fixture asserting NO trip with a long feature and no flag. Regenerate the byte-pinned baseline via `_normalize_smoke_output`. |
| Docs | `user/scripts/CLAUDE.md` (`--per-feature-cycle-cap` block), `user/skills/lazy-batch/SKILL.md` (Step that reads the `budget_guard` probe / argument-hint), `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (coupled-pair mirror note) | Reword from "default-on dynamic ceiling, override forces fixed" → "OFF by default; `--per-feature-cycle-cap <N>` opt-in arms a fixed ceiling". The whole-run `max_cycles` is the only default budget. |
| Parity | `user/scripts/lazy_parity_audit.py` | Confirm the feature-only divergence still holds (no `bug-state.py` mirror owed). |

## Open Questions

- **Should the default-off path keep computing `L_task` for the trip notification's reporting only (warn-without-defer), or compute nothing?** Operator chose backstop = "whole-run `max_cycles` only" (not "warn-only soft cap"), so the default path should compute **nothing** — no `L_task`, no `budget_guard` probe field, no notification. To lock in `/plan-bug`.
- **Do the prior softening helpers (`feature_is_near_complete`, `count_validation_corrective_cycles`, `budget_trip_signals`, end-of-run resume flush) stay wired (reachable only under the opt-in flag) or get removed?** Recommendation: keep them wired — they are correct refinements of the *armed* guard and removing them would regress the opt-in path. To confirm in `/plan-bug`.
- **Default-output byte-identity:** with the guard default-off, does a no-marker / no-flag probe stay byte-identical to today? (It should — the budget block is marker-gated AND now ceiling-gated.) Add a baseline-regression fixture to prove it.
