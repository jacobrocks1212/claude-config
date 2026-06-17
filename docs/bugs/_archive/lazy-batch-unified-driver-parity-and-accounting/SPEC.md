# /lazy-batch unified-driver parity & cycle-accounting gaps — Investigation Spec

> Three harness defects surfaced in the 2026-06-17 `/lazy-batch` run on `claude-config`: (1) the run-marker cycle counters undercount because pseudo-skill cycles produce no advance signal; (2) the unified driver never archives/trims fixed bugs (it omits the `--archive-fixed` call `/lazy-bug-batch` chains); (3) `/lazy-batch` fails to pick up an on-disk bug that is absent from `queue.json` the way `/lazy-bug-batch` does — defeated by ordering-only merged heads masked by stale untrimmed entries, plus a silent exception-swallow in the merged bug-load bridge.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-17
**Fixed:** 2026-06-17
**Fix commit:** 092a0d7
**Placement:** docs/bugs/lazy-batch-unified-driver-parity-and-accounting
**Related:** `docs/features/unified-pipeline-orchestrator/` (Phase 1 merged-view, Phase 2 unified driver, Phase 5 `--apply-pseudo`); `user/scripts/CLAUDE.md` → "CLI surface" (`--next-merged`, `--apply-pseudo`, `--archive-fixed`); `user/skills/_components/mark-fixed-archive.md`; `user/skills/lazy-batch/SKILL.md` (Step 1 unified driver, Step 1c.5 pseudo-skills); `docs/bugs/operator-checkpoint-resume-counter-reset/` (the bug whose run exposed all three)

---

## Verified Symptoms

<!-- All three confirmed by direct observation during the 2026-06-17 /lazy-batch run that fixed operator-checkpoint-resume-counter-reset. -->

1. **[VERIFIED — item 1]** The run-marker cycle counters undercount. After 2 real-skill cycles (`plan-bug`, `execute-plan`) + 3 pseudo-skill cycles (`__grant_skip_no_mcp_surface__`, `__write_validated_from_skip__`, `__mark_fixed__`), the probe's `cycle_header` showed `fwd 1/20 · meta 1` — the three pseudo-skill cycles and at least one real cycle were never counted. Confirmed by reading the live `cycle_header` field each cycle.
2. **[VERIFIED — item 2]** `bug-state.py --apply-pseudo __mark_fixed__ <spec_path>` returned `"queue_trimmed": false` and `"roadmap_struck": false`, and the bug dir was NOT moved to an archive location. The fixed bug's entry remained in `docs/bugs/queue.json` (it had to be hand-trimmed). Confirmed by the JSON return + post-fix `cat docs/bugs/queue.json`.
3. **[VERIFIED — item 3]** `/lazy-batch` did not surface the on-disk bug (`docs/bugs/operator-checkpoint-resume-counter-reset/`, `Status: Concluded`) while `docs/bugs/queue.json` was `"queue": []`. The feature probe returned `all-features-complete` and the run stopped; `lazy-state.py --next-merged` returned a (stale, already-Complete) feature head. `bug-state.py` run directly DID find and route the same bug. Only after the stale Complete features were hand-trimmed from `docs/features/queue.json` did `--next-merged` return the bug. Confirmed by the probe outputs at each step.
4. **[VERIFIED — operator intent]** Desired end-state: `/lazy-batch` picks up on-disk bugs not in `queue.json` the same way `/lazy-bug-batch` does (bugs-only — features stay strictly queue.json-driven); and `/lazy-batch` archives fixed bugs with full parity to `/lazy-bug-batch` (`git mv` to `docs/bugs/_archive/` + queue trim + commit). Confirmed via AskUserQuestion 2026-06-17.

## Reproduction Steps

**Item 1 (counter undercount):**
1. `/lazy-batch <N>` over a queue whose item runs any pseudo-skill cycle (`__grant_skip_no_mcp_surface__`, `__write_validated_*`, `__mark_complete__`/`__mark_fixed__`).
2. Observe the probe `cycle_header` counter after each pseudo-skill cycle.
- **Expected:** each forward-advancing pseudo-skill increments `forward_cycles`.
- **Actual:** pseudo-skill cycles do not advance the marker counter; the displayed budget undercounts.
- **Consistency:** always, for pseudo-skill cycles and for any real-skill cycle dispatched verbatim that the guard does not consume.

**Item 2 (archive/trim not firing):**
1. Drive a bug to `__mark_fixed__` under `/lazy-batch` (the unified driver).
2. Observe `queue_trimmed: false` and the bug dir still at `docs/bugs/<slug>/` (not `_archive/`), entry still in `queue.json`.
- **Expected:** fixed bug archived + de-queued, matching `/lazy-bug-batch`.
- **Actual:** neither happens; `/lazy-batch` never calls `--archive-fixed`.
- **Consistency:** always under `/lazy-batch` (the unified driver omits the chained call).

**Item 3 (on-disk bug not picked up):**
1. Have an on-disk `docs/bugs/<slug>/SPEC.md` (`Status: Investigating` or `Concluded`) with `docs/bugs/queue.json` = `"queue": []`.
2. Also have ≥1 stale, already-Complete feature still listed in `docs/features/queue.json` (untrimmed — see item 2).
3. Run `/lazy-batch <N>`.
- **Expected:** the bug is picked up and routed (as `/lazy-bug-batch` would).
- **Actual:** the merged head is a stale Complete feature; the feature pipeline returns `all-features-complete`; the bug is never reached.
- **Consistency:** always when a stale-Complete entry sits ahead of the bug in the merged order, or when the merged bug-load silently fails.

## Evidence Collected

### Source Code

**Item 1 — `advance_run_counters` gates on the registry consume-count only.**
- `user/scripts/lazy_core.py:7590–7669` (`advance_run_counters`): the advance gate is `if current_consume <= prior_consume: return marker` (lines ~7645–7655), where `current_consume = consumed_emission_count()`. It advances `forward_cycles` (non-`__` sub_skill) or `meta_cycles` (`__`-prefixed) ONLY when the consume-count rose.
- `user/scripts/lazy_core.py:7136–7158` (`consumed_emission_count`): counts registry entries with `consumed: True`. The count rises ONLY when the validate-deny guard calls `consume_nonce()` on an ALLOWed `Agent` dispatch (by-reference path `lazy_guard.py:~607`, verbatim hash-match path `~667`).
- `user/scripts/lazy_core.py:7672–7700` (`advance_meta_cycle`): the EXISTING counterpart for `--emit-dispatch` meta calls — it bumps `meta_cycles` and pre-absorbs the next consume via `last_advance_consume_count = consumed_emission_count() + 1`. **There is no `advance_forward_cycle()` equivalent**, so forward-advancing pseudo-skills (which run inline via `--apply-pseudo`, dispatch no Agent, trigger no guard ALLOW, increment no consume-count) never advance `forward_cycles`.

**Item 2 — `--apply-pseudo __mark_fixed__` deliberately does not trim/archive; that lives in a separate `--archive-fixed` call the unified driver never makes.**
- `user/scripts/lazy_core.py:~3201–3242` (`apply_pseudo`, `__mark_complete__`/`__mark_fixed__` branch): the feature queue-trim block is gated `if not is_fixed:` (line ~3203). For the bug/fixed path `queue_trimmed`/`roadmap_struck` are returned `False` BY DESIGN — the docstring (`~2390`) states "Always False for the bug/fixed path (whose queue trim lives in `archive_fixed` step 6)."
- `user/scripts/lazy_core.py:3812` (`archive_fixed`) + step-6 trim at `~4060–4081` (`e.get("spec_dir") == bug_id or e.get("id") == bug_id`): the complete archive (`git mv` → `docs/bugs/_archive/`, queue trim, commit). Invoked ONLY by `bug-state.py --archive-fixed <spec_path>` (`bug-state.py:~4463–4468`) — a separate CLI call.
- `user/skills/_components/mark-fixed-archive.md:~29–68`: documents that the CONSUMER skill chains `--apply-pseudo __mark_fixed__` THEN `--archive-fixed`. `/lazy-bug-batch` chains both; `/lazy-batch`'s Step 1c.5 pseudo-skill handling (`user/skills/lazy-batch/SKILL.md`) documents only the feature `__mark_complete__` and never wires the `--archive-fixed` follow-up for the bug `__mark_fixed__` path. **The trim predicate itself is correct** — a missing `spec_dir` falls back to the `id` arm — so no `lazy_core.py` change is needed for trimming; the gap is purely the missing chained call in the unified driver.

**Item 3 — the on-disk bug fallback IS plumbed through the merged view, but two seams defeat it.**
- `user/scripts/bug-state.py:~303, 352–377` (`load_bug_queue`): unconditionally appends `_find_open_bug_dirs(...)` results to the queue.json entries; `user/scripts/bug-state.py:~416–473` (`_find_open_bug_dirs`): returns open on-disk bug dirs not already queued, skipping only `_archive/`, queued ids, dirs without `SPEC.md`, `Won't-fix`, and `Fixed`-with-receipt. A `Concluded`/`Investigating` dir passes through. So the standalone bug walk picks up on-disk bugs.
- `user/scripts/lazy-state.py:~256–282` (`_load_bug_queue_for_merged`): the importlib bridge `--next-merged` uses to load the bug side. It wraps the dynamic `load_bug_queue` call in a **bare `except Exception: return []`** (line ~281) — any error silently degrades the merged view to features-only with NO diagnostic. Latent silent-failure risk.
- `user/scripts/lazy_core.py:~5302–5369` (`merged_priority`/`merged_worklist`/`next_merged`): pure ORDERING — it does NOT re-infer per-item state, so it returns already-Complete/Fixed items as heads. Combined with the item-2 untrimmed stale entries, a Complete feature sits at the merged head and masks the actionable bug. The unified driver acts on the HEAD only; when the head's type-state-script returns `all-features-complete`, the run stops before reaching the bug.
- `user/scripts/lazy-state.py:~240–253` (`load_queue`, features): strictly queue.json-driven — no on-disk fallback. This is intentional (features are actionable only when enqueued) and per operator decision STAYS this way; the fix is bugs-only.

### Runtime Evidence
The 2026-06-17 run transcript: feature probe → `all-features-complete`; `--next-merged` → `{"item_id":"lazy-pipeline-visualizer","type":"feature",...}` (a feature whose `SPEC.md` is `Status: Complete` with a `COMPLETED.md` receipt); after hand-trimming both Complete features from `docs/features/queue.json`, `--next-merged` → `{"item_id":"operator-checkpoint-resume-counter-reset","type":"bug",...}`. The bug then ran the full tail; `__mark_fixed__` returned `queue_trimmed:false`; the queue entry + bug dir were hand-reconciled.

### Git History
`docs/bugs/operator-checkpoint-resume-counter-reset/` was fixed across commits `15ce2bf` (plan) → `42b327d` (P4) → `f943bcc` (skip grant) → `5428b48` (validated) → `48215c5` (mark-fixed) → `9ece294` (hand queue trim). The hand trims of both `queue.json` files this run are the workaround this spec exists to remove.

### Related Documentation
`user/scripts/CLAUDE.md` documents `--next-merged` as "Read-only ORDERING ONLY ... NEVER re-infers per-item state (the unified driver still calls --probe/--emit-prompt per item)" — confirming the ordering-only behavior is intended at the `--next-merged` layer, so the resolved-item filtering / masking fix belongs in the driver loop or a new merged-view filter, not by making `--next-merged` infer state.

## Theories

### Theory 1 (item 1): forward-advancing pseudo-skills have no counter-advance path — CONFIRMED
- **Hypothesis:** Because `advance_run_counters` advances only on a registry consume-count rise, and pseudo-skills run inline (no Agent, no guard ALLOW, no consume), the `forward_cycles` counter never advances for them. `meta_cycles` has `advance_meta_cycle()` for the `--emit-dispatch` path but `forward_cycles` has no inline counterpart.
- **Supporting evidence:** `lazy_core.py:7645–7655` gate; `consumed_emission_count` only rising on guard ALLOW; `advance_meta_cycle` exists but no `advance_forward_cycle`; observed `fwd 1` after 3 pseudo + 2 real cycles.
- **Contradicting evidence:** None for pseudo-skills. (For real-skill verbatim dispatch the guard's hash-match path DOES consume when byte-identical, so a correctly-matched verbatim real cycle should count — see Theory 1b.)
- **Status:** Confirmed (pseudo-skill path).

### Theory 1b (item 1, secondary): verbatim real-skill dispatch can also miss a consume — LIKELY
- **Hypothesis:** A real cycle dispatched with verbatim `cycle_prompt` (not `cycle_prompt_ref`) only consumes a nonce if the guard ALLOWs on an exact byte hash-match; any drift → guard deny → no consume → no advance. Dispatching by-reference (`cycle_prompt_ref` / `@@lazy-ref`) makes the consume deterministic.
- **Supporting evidence:** guard consume only on ALLOW; the displayed `fwd 1` after 2 real cycles suggests one real cycle also went uncounted; SKILL Step 1d already PREFERS `cycle_prompt_ref`.
- **Status:** Likely — the Fix-A "advance on step/feature change" option (below) makes the counter robust regardless of dispatch style.

### Theory 2 (item 2): the unified driver omits the chained `--archive-fixed` call — CONFIRMED
- **Hypothesis:** `--apply-pseudo __mark_fixed__` is half the bug terminal; archive+trim live in `--archive-fixed`. `/lazy-bug-batch` chains both; `/lazy-batch` does not.
- **Supporting evidence:** `lazy_core.py:3203` `if not is_fixed:` gate; `archive_fixed` is a separate function/CLI; `mark-fixed-archive.md` names the consumer-skill chaining responsibility; lazy-batch SKILL Step 1c.5 documents only `__mark_complete__`.
- **Status:** Confirmed.

### Theory 3 (item 3): merged head is ordering-only and masked by stale untrimmed heads; bridge swallows errors — CONFIRMED
- **Hypothesis:** The on-disk bug fallback flows through `load_bug_queue`, but (a) `--next-merged` returns resolved items as heads (no state filter), so item-2 stale-Complete features mask the bug and the driver stops on `all-features-complete`; and (b) `_load_bug_queue_for_merged`'s bare `except Exception: return []` can silently drop the entire bug side.
- **Supporting evidence:** bug surfaced only after stale features were trimmed (proving it was loadable but outranked/masked); the bare-except at `lazy-state.py:281`; `merged_*` being pure ordering.
- **Contradicting evidence:** In this run the bare-except did NOT fire (the bug loaded fine once features were trimmed), so masking was the operative mechanism here; the bare-except remains a latent risk to fix defensively.
- **Status:** Confirmed (masking primary; bare-except latent).

## Proven Findings

- **Item 1:** Add `advance_forward_cycle()` to `lazy_core.py` (mirroring `advance_meta_cycle()`), and call it from the `--apply-pseudo` handler for forward-advancing pseudo-skills (`__mark_complete__`, `__mark_fixed__`, `__write_validated_from_skip__`, `__write_validated_from_results__`, `__grant_skip_no_mcp_surface__`, `__flip_plan_complete_cloud_saturated__`). Strongly consider the more robust **Fix-A** variant: advance on a change in `(feature_id, current_step, sub_skill)` recorded in the marker — independent of the consume oracle — which also closes Theory 1b. (`/plan-bug` to settle Fix-B vs Fix-A; Fix-A preferred for robustness.) Both `lazy-state.py` and `bug-state.py` share `lazy_core`, so the counter fix is pipeline-agnostic; keep both `--test` suites green.
- **Item 2:** Wire the `--archive-fixed` follow-up into the unified `/lazy-batch` (and mirror into `/lazy-batch-cloud` per the coupling rule): after a successful `__mark_fixed__` for a `type==bug` cycle, the orchestrator runs `bug-state.py --archive-fixed <spec_path>` (the same call `/lazy-bug-batch` makes) — `git mv` to `docs/bugs/_archive/`, queue trim, commit. No `lazy_core.py` change required (the trim predicate + archive function are correct); the fix is SKILL-prose + orchestration wiring in `user/skills/lazy-batch/SKILL.md` Step 1c.5 (and the cloud twin). Confirm `/lazy-bug-batch` already chains it (parity reference). The two stale Complete FEATURE entries that lingered this run are a separate pre-existing residue (completed before/outside the `__mark_complete__` trim, or with a wrong `--repo-root`) — a one-time hand trim suffices; not a code defect.
- **Item 3 (bugs-only, per operator):**
  1. Harden `_load_bug_queue_for_merged` (`lazy-state.py:~281`): replace the bare `except Exception: return []` with a guard that emits a `_diag(...)` breadcrumb before degrading, so a silent bug-side load failure becomes visible in the merged-view diagnostics (and consider catching `SystemExit` from a `_die()` separately, or making `_die` raise a typed exception).
  2. Stop stale/resolved items masking the merged head: either (a) have `merged_worklist`/`next_merged` SKIP items whose per-item state is terminal (Complete/Fixed) — note this requires a cheap resolved-check, weighed against the "ordering-only, no state inference" contract — OR (b) have the unified-driver loop advance past a type whose state script returns a queue-exhausted terminal (e.g. `all-features-complete`) to probe the OTHER type before declaring the whole run done. Option (b) keeps `--next-merged` pure and is the lighter change; `/plan-bug` to settle (a) vs (b).
  3. Features stay strictly queue.json-driven (no on-disk fallback) — explicitly out of scope per operator decision.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Counter advance (item 1) | `user/scripts/lazy_core.py` (`advance_run_counters`, new `advance_forward_cycle`), `user/scripts/lazy-state.py` (`--apply-pseudo` handler call site), `user/scripts/test_lazy_core.py` | New forward-advance path for inline pseudo-skills (Fix-B) or change-of-state advance (Fix-A) |
| Fixed-bug archive (item 2) | `user/skills/lazy-batch/SKILL.md` (Step 1c.5 — wire `--archive-fixed` after `__mark_fixed__`), `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (mirror) | Unified driver chains `--archive-fixed`; no `lazy_core.py` change |
| Merged-view bug pickup (item 3) | `user/scripts/lazy-state.py` (`_load_bug_queue_for_merged` bare-except), `user/scripts/lazy_core.py` (`merged_worklist`/`next_merged` resolved-filter OR the driver-loop fallthrough) + `user/skills/lazy-batch/SKILL.md` Step 1 driver loop, `test_lazy_core.py`/`lazy-state.py --test` | On-disk bugs reliably surface; resolved heads no longer mask actionable items |
| Coupling/parity | `user/scripts/lazy_parity_audit.py` | Extend to assert `/lazy-batch` chains `--archive-fixed` for bug cycles (parity with `/lazy-bug-batch`) |

## Open Questions

- **Item 1 fix shape:** Fix-A (advance on `(feature_id, current_step, sub_skill)` change, consume-independent — robust, closes Theory 1b) vs Fix-B (targeted `advance_forward_cycle()` called from `--apply-pseudo`). Recommend Fix-A; `/plan-bug` to settle.
- **Item 3 masking fix:** (a) resolved-item filter inside `merged_worklist`/`next_merged` (departs from "ordering-only, no state inference") vs (b) unified-driver-loop fallthrough past a single-type queue-exhausted terminal to probe the other type (keeps `--next-merged` pure). Recommend (b); `/plan-bug` to settle.
- **Item 2 scope:** confirm during planning that `/lazy-bug-batch` already chains `--apply-pseudo __mark_fixed__` → `--archive-fixed` (parity reference) and that the unified driver should fire `--archive-fixed` for the `type==bug` terminal only (features use `__mark_complete__`'s built-in trim, no archive).
