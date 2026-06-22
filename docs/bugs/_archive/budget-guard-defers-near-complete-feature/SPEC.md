# Budget-guard defers a near-complete feature one validation cycle from done — Investigation Spec

> The per-feature budget guard trips on a raw forward-cycle count with no proximity-to-completion signal, so a feature that did legitimate corrective work (not monopolization) gets deferred to the live-queue tail one `/mcp-test` cycle from `VALIDATED.md`, leaving it parked and a rebuilt runtime idle.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-21
**Fixed:** 2026-06-21
**Fix commit:** 2280ad6
**Placement:** docs/bugs/budget-guard-defers-near-complete-feature
**Related:**
- `docs/features/feature-budget-guard-and-skip-ahead/` (SPEC + RESEARCH + PHASES — the feature that introduced this guard; RESEARCH.md §"False Positives on Complex Work" and §"Prior Art Contradiction (The Single Signal)" pre-flag this exact failure mode)
- `docs/bugs/operator-checkpoint-resume-counter-reset/` (related cycle-counter-semantics bug, Fixed)
- AlgoBooth session `ea0c2bf8-5ac3-4778-ac28-ff47ac055c73.jsonl` (the canonical incident)

---

## Verified Symptoms

1. **[VERIFIED]** In an AlgoBooth `/lazy-batch` run, the budget-guard deferred `d2-sample-import-ui` at its per-feature ceiling of 6 forward cycles — confirmed by the user's report and the session log (line 331, verbatim): *"budget-guard deferred d2-sample-import-ui at its per-feature ceiling (6 cycles) — it remains one mcp-test cycle from validation; the rebuilt runtime stays up (owned) for the next feature that needs it."*
2. **[VERIFIED]** The feature was deferred **one `/mcp-test` cycle from `VALIDATED.md`** — Phase 8 code was fully implemented and the runtime was rebuilt/hot; only the validation re-run remained. The user's intent ("I don't want to leave features almost done") confirms this is the undesired behavior, not the deferral mechanism in general.
3. **[VERIFIED]** The extra cycles were **legitimate corrective work, not monopolization**: a genuine `/mcp-test` gate failure (1/7) forced a corrective Phase 8 (apply-resolution + re-plan + re-implement), which pushed the count over the floor of 6. `retry_count = 1` confirms no validation-escalation — a single concrete failure, cleanly resolved.

## Reproduction Steps

1. Run `/lazy-batch` on a queue where one feature requires a corrective phase after an `/mcp-test` failure (the common "validation fails → fix → re-validate" loop).
2. The corrective work (apply-resolution + write-plan + execute-plan) consumes 2–3 forward cycles on top of the straight-line spec→plan→execute→mcp-test tail.
3. Forward-cycle count for that feature reaches the per-feature ceiling (floor = 6) on the cycle that *implements* the corrective phase — i.e. right before the re-validation cycle.

**Expected:** A feature within one validation cycle of completion is allowed to finish (validate → `__mark_complete__`) before the guard can defer it; and/or any feature deferred while near-complete is auto-resumed at end-of-run rather than left parked.
**Actual:** The guard trips on the raw forward-cycle count, defers the feature to the live-queue tail, and advances to the next item — leaving the feature parked one cycle from done and a freshly-rebuilt runtime owned-but-idle.
**Consistency:** Deterministic — any feature whose legitimate corrective work crosses the ceiling on the pre-validation cycle will be deferred at the worst possible moment.

## Evidence Collected

### Source Code

**Ceiling computation — `user/scripts/lazy_core.py:10132-10182`** (`compute_per_feature_ceiling`):

```python
L_task = max(6, min(c * 4 // 10, (c // q) * 2))   # c = max_cycles, q = ready_queue_depth
```

- `max(6, …)` is a hard floor — a feature *always* gets ≥6 cycles, and on small runs / shallow queues the floor is the operative ceiling. The d2 incident hit exactly this floor.
- The only input is `max_cycles` and `ready_queue_depth`. **There is no proximity-to-completion term and no distinction between forward-progress cycles and corrective cycles.**
- Override exists (`--per-feature-cycle-cap N`) but is a blunt global knob, not a per-feature signal.

**Trip + deferral — `user/scripts/lazy-state.py:1737-1797`**:

```python
_bg_count = int(_bg_per_feature.get(feature_id, 0) or 0)
if _bg_count >= _bg_ceiling:
    prior_defers = int(_bg_deferred_counts.get(feature_id, 0) or 0)
    _bg_action = "defer" if prior_defers < 1 else "evict"
    ...
    _DEFERRED_BUDGET.append(feature_id)
    continue
```

- The trip is evaluated **before** the dispatch decision (Step before skip-ahead), so the guard has no knowledge of *what the next dispatch would be* — it cannot see that the next action is the terminal `/mcp-test` → `__mark_complete__`.
- First trip → defer to tail (run-scoped, `queue.json` untouched, on-disk progress preserved). Second trip same run → terminal eviction (`_bg_evicted`).
- A deferred feature is re-examined each cycle but only picked back up after all non-deferred items ahead of it are processed — and risks a second trip → eviction before it ever validates.

### Runtime Evidence (session log `ea0c2bf8…`)

Chronological reconstruction of d2-sample-import-ui's 6 cycles:

| Cycle | Sub-skill | What happened |
|-------|-----------|---------------|
| 1 | execute-plan (opus) | plan part-3 Complete · Phases 5–6 landed · 7/7 WUs |
| 2 | execute-plan (sonnet) | plan part-4 Complete · WU-1/2/3 reconciled · gates green |
| 3 | write-plan (opus) | no new work — routing reconcile (gate-owned-row misroute in PHASES Phase 7) |
| 4 | mcp-test (sonnet) | **MCP gate FAIL 1/7** — `get_samples_root` wrong dir, file_io sandbox missing `user_samples_dir`, no `import_sample` tool → BLOCKED.md |
| 5 | apply-resolution + write-plan (opus) | corrective Phase 8 authored, BLOCKED.md neutralized, plan part-5 (5 WUs) |
| 6 | execute-plan (opus) | **Phase 8 implemented** — `get_user_samples_dir` + `import_sample` MCP tools, sandbox, samples_core hoist · 5/5 WUs · runtime rebuilt/hot |

Then: `budget-guard deferred d2-sample-import-ui … advancing to d8-signal-flow-viz`. Cycle 7 ran `realign-spec → d8`, which did not obviously reuse the hot runtime — so the rebuild was wasted in the immediate term.

### Git History

Investigation conducted on `main` (claude-config). No prior bug directory covers this; the closest is `operator-checkpoint-resume-counter-reset` (counter semantics, Fixed).

### Related Documentation

The introducing feature's own `RESEARCH.md` **predicted this**:

> **False Positives on Complex Work:** … A static cycle ceiling will trip this feature prematurely, continually deferring it to the tail and preventing it from ever achieving completion, despite it operating exactly as intended.

> **FLAG: Prior Art Contradiction (The Single Signal).** The locked decision utilizes a strictly singular signal — forward-cycles — as the budget guard. … theoretically blind to temporal starvation and silent hangs.

The dynamic formula was chosen to mitigate the first risk, but the single-signal weakness (no proximity/no corrective-vs-monopoly distinction) was knowingly carried forward. This bug is that weakness materializing.

## Theories

### Theory 1: Single-signal ceiling is blind to proximity-to-completion — **CONFIRMED**
- **Hypothesis:** The guard trips on raw forward-cycle count with no term for "how close is this feature to done," so a feature one dispatch from `__mark_complete__` is deferred identically to a feature stuck at phase 1.
- **Supporting evidence:** `compute_per_feature_ceiling` takes only `max_cycles` + `ready_queue_depth`; the trip in `lazy-state.py:1738` is a bare `count >= ceiling`; the trip is evaluated before the dispatch decision so it cannot see the next action is terminal validation.
- **Contradicting evidence:** None.
- **Status:** Confirmed.

### Theory 2: Legitimate corrective cycles are counted identically to monopolization cycles — **CONFIRMED**
- **Hypothesis:** A corrective phase forced by a *real* MCP-validation failure inflates `forward_cycles` the same as a feature looping on the same step, so the anti-monopoly guard punishes legitimate progress.
- **Supporting evidence:** The d2 trip was caused by the corrective Phase 8 (cycles 5–6) on top of the tail (cycles 1–4); `retry_count = 1` proves it was a single clean failure, not a runaway.
- **Contradicting evidence:** Anti-monopoly is the guard's *purpose*; distinguishing "good" from "bad" cycles is exactly the missing signal. Not contradicting — this is the design gap.
- **Status:** Confirmed.

### Theory 3: No end-of-run resume flush for near-complete deferred features — **CONFIRMED**
- **Hypothesis:** Once deferred, a near-complete feature is not auto-resumed before the run terminates; it relies on a *future* run to pick it up, and risks eviction on a 2nd trip first.
- **Supporting evidence:** The terminal `queue-exhausted-budget-deferred` (`lazy-state.py:1937-1950`) surfaces deferred features at the end-of-run flush for *human audit* but does not auto-resume them to validation. The hot runtime was left idle.
- **Contradicting evidence:** None.
- **Status:** Confirmed.

## Proven Findings

1. **Root cause:** The per-feature budget guard is a single-signal mechanism (forward-cycle count vs a queue-derived ceiling) with (a) no proximity-to-completion term and (b) no discrimination between legitimate corrective cycles and monopolization cycles. It fires before the dispatch decision, so it is structurally blind to the fact that the very next action would complete the feature.
2. **Scope of impact:** Feature pipeline only. `bug-state.py` has **no** per-feature ceiling — `compute_per_feature_ceiling` / `budget_deferred` / `_DEFERRED_BUDGET` are referenced solely by `lazy-state.py` + `lazy_core.py` (grep-confirmed). Any fix is feature-pipeline-shaped and owes **no** coupled-pair mirror to `bug-state.py` (justified divergence — confirm against `lazy_parity_audit.py` during planning).
3. **No data loss:** Deferral is run-scoped and preserves on-disk progress; the feature would be picked up on a *subsequent* run. The defect is wasted work (idle rebuilt runtime, parked near-done feature) and the risk of 2nd-trip eviction, not lost code.

## Fix Direction (operator-decided)

Confirmed with the operator via AskUserQuestion (2026-06-21):

- **Approach:** *Both grace + flush.*
  1. **Near-completion grace** — when a feature is within one validation cycle of done (plan + implementation complete; only the Step-9 `/mcp-test` → `__mark_complete__` remains), the guard grants a grace cycle to finish **before** it can defer. Targets the exact incident.
  2. **End-of-run resume flush** — as a safety net, at run end auto-resume deferred features that are near-complete so they validate before the run terminates, rather than leaving them parked.
- **Scope:** *Budget-guard signal quality.* Broaden beyond the narrow near-complete case to address the documented single-signal weakness — consider composite signals (forward-cycles + validation-blocks + completion-distance) so legitimate corrective work is not counted identically to monopolization.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Ceiling computation | `user/scripts/lazy_core.py` (`compute_per_feature_ceiling` ~10132) | Add a completion-distance / composite-signal input, or a proximity exception consulted at the trip site. |
| Trip + deferral | `user/scripts/lazy-state.py:1737-1797` | Add a near-completion grace gate before `count >= ceiling` defers; the trip must be able to see the pending dispatch is terminal validation. |
| End-of-run flush | `user/scripts/lazy-state.py:1937-1950` (`queue-exhausted-budget-deferred`) | Add auto-resume of near-complete deferred features (vs audit-only surfacing). |
| Tests | `user/scripts/test_lazy_core.py`, `lazy-state.py --test` fixtures, baselines | New fixtures for grace, flush, and corrective-vs-monopoly discrimination. |
| Parity | `user/scripts/lazy_parity_audit.py` | Confirm the feature-only divergence (no `bug-state.py` mirror owed). |

## Open Questions

- **Defining "near-complete" precisely.** Candidate signal: PHASES.md has only verification-only (`<!-- verification-only -->`) rows unchecked AND a plan part is Complete AND no `BLOCKED.md` — i.e. `remaining_unchecked_are_verification_only` is already True (the same predicate the mid-feature gate uses to fall through to `/mcp-test`). Reusing that predicate keeps the grace gate consistent with the existing "ready to validate" definition. To be locked in `/plan-bug`.
- **Composite-signal shape.** Should corrective cycles be (a) *not counted* against the ceiling (subtract validation-driven corrective phases), or (b) counted but offset by a larger ceiling when validation-blocks are present? `(a)` is simpler and matches the "don't punish legitimate corrective work" intent; `(b)` is more general. To be locked in `/plan-bug`.
- **Grace bound.** How many grace cycles before the guard re-asserts (1? the corrective-phase count?) — must remain bounded so a genuinely-stuck feature can't exploit the grace to monopolize. To be locked in `/plan-bug`.
