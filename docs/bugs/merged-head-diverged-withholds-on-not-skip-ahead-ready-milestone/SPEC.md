# merged-head-diverged withholds the route pointing at a not-skip-ahead-ready (dep-blocked) item → no-route

**Status:** Concluded
**Severity:** P0 (immediate blocker — the probe returns NO forward route: null `cycle_prompt`
AND null `terminal_reason`)
**Discovered:** 2026-07-17 (observed live during a `/lazy-batch` run on AlgoBooth, item in
flight `inspector-sample-clip-view`)
**Related:** `docs/bugs/merged-head-diverged-stalls-on-gated-head` (Round 64 — introduced
`probe_skipped_ids`, which this bug extends); `docs/bugs/research-gated-head-buried-by-skip-ahead-and-merged-fallthrough`
(Round 65 — `research_halt_head` surfacing + `research_gated_heads`); `feature-budget-guard-and-skip-ahead`
(the default-on skip-ahead readiness predicate); `docs/features/unified-pipeline-orchestrator/`
(merged-view / type-dispatch driver).

## Trigger

Orchestrator-observed friction on a live `/lazy-batch` default (non-strict, non-park) probe.
`lazy-state.py --emit-prompt` skip-ahead correctly walked to `candidate=hydra-overlay
independent=True deps=[] → DISPATCH`, but then set `route_overridden_by='merged-head-diverged'`
with `merged_head={'item_id':'prerelease-complete-milestone','type':'feature'}` and returned
`cycle_prompt=null`, `cycle_prompt_ref=null`, `cycle_prompt_refused=null`, `terminal_reason=null`.
The orchestrator was left with NO forward route. Meanwhile `lazy-state.py --next-merged` returned
`{item_id: inspector-sample-clip-view}` — a third, different head. Three surfaces, three answers.

## Reconstructed route (divergence point)

The `--emit-prompt` merged-head-divergence guard (`lazy-state.py` merged-override block, feeding
`lazy_core.dispatch.merged_head_override`) builds its exclude set as
`nondispatchable_item_ids ∪ probe_skipped_ids(state, feats)`, discards the current dispatch
target, and withholds the route when the resulting merged head diverges from the item the probe
would emit for. Its documented contract (docstring): the withhold "fires ONLY for a genuine
DISPATCHABLE-item divergence (a P0 bug jumping the queue), never behind a gated head the probe
already skipped."

Reproduced live (AlgoBooth queue, default probe):

```
skip-ahead audit: gated_heads=['inspector-sample-clip-view','inspector-track-dashboard']
  candidate='prerelease-complete-milestone' independent=False
  deps=[7 hard spec deps] → SKIP (not skip-ahead-ready)
...
skip-ahead audit: ... candidate='hydra-overlay' independent=True deps=[] → DISPATCH

compute_state.feature_id       = hydra-overlay        (the probe's real target)
probe_skipped_ids              = {inspector-sample-clip-view, inspector-track-dashboard,
                                  cross-platform-distribution, inspector-effect-chain-editor,
                                  agpl-sidecar-publication, non-windows-audio-hardening,
                                  foot-switch-injectors}      # 5 gated + 2 host-deferred
merged_head_override(embedded) = {route_overridden_by: merged-head-diverged,
                                  merged_head: prerelease-complete-milestone}
--next-merged head             = inspector-sample-clip-view
```

`prerelease-complete-milestone` (queue index 2, ahead of `hydra-overlay` at index 8) was skipped
by the skip-ahead walk as **"SKIP (not skip-ahead-ready)"** — it has 7 unmet hard deps
(`independent=False`). But it is NOT in `probe_skipped_ids`, so it survived as the highest-priority
item in the embedded merged view and the guard withheld the route pointing at it — an item the
probe CANNOT dispatch (unmet deps). Because it is neither a real dispatch target (no
`cycle_prompt`) nor a terminal (no `terminal_reason`), the result is a hard no-route.

**Divergence point:** `--emit-prompt` merged-head-divergence guard — the withhold fired on a
non-dispatchable, dependency-unready item (`prerelease-complete-milestone`) that the skip-ahead
walk had already skipped but recorded ONLY in `diagnostics`, not in any structured list
`probe_skipped_ids` consumes.

## Root cause

**`root_cause_class: script-defect`.** The skip-ahead readiness gate in `compute_state`
(`lazy-state.py` ~2728) records a candidate that FAILS the two-key readiness predicate
(`skip_ahead_ready` — no hard dep on a skipped gated id AND `independent: true`) into a LOCAL
variable `skip_ahead_blocked` that is **never surfaced into the state dict** (declared, commented,
appended — never read, never emitted). Every OTHER same-cycle skip IS surfaced via a module global
(`_GATED_HEADS` → `gated_heads`, `_HOST_DEFERRED` → `host_deferred_features`, `_DEP_GATED` →
`dep_gated`, `_DEVICE_DEFERRED` → `device_deferred_features`) and consumed by
`lazy_core.dispatch.probe_skipped_ids`. The dependency-unready skip is the one gap.

Consequently `probe_skipped_ids` — which Round 64 built precisely so the merged-head exclude set
equals the probe's OWN skip decisions — is INCOMPLETE: it misses the not-skip-ahead-ready skips.
The merged-head-diverged guard can therefore withhold the route pointing at an item that is not in
the probe's dispatchable set, producing a no-route (null `cycle_prompt` AND null
`terminal_reason`) — the exact stall class Round 64 (`merged-head-diverged-stalls-on-gated-head`)
set out to eliminate, one skip-list short.

## Fix scope (mechanical — this round)

Surface the not-skip-ahead-ready skips and fold them into the shared skip set, mirroring the
established `_GATED_HEADS` pattern EXACTLY (byte-identity discipline — absent-when-empty):

1. `lazy-state.py`: promote `skip_ahead_blocked` to a surfaced module global
   `_SKIP_AHEAD_BLOCKED` (reset at the top of `compute_state`; appended at the readiness-fail skip;
   cleared in the `gated_head_fallback` branch alongside `_GATED_HEADS` since no skip is realized
   there). Surface it in `_state()` under the `skip_ahead_blocked` key, present ONLY when non-empty.
2. `lazy_core/dispatch.py` `probe_skipped_ids`: fold `state["skip_ahead_blocked"]` (id-keyed, used
   directly) into the returned skip set. Shared helper → both feature (`lazy-state.py`) and bug
   (`bug-state.py`) `--emit-prompt` merged-override paths get the fix; bug state simply lacks the
   key (`.get` → `None` → empty), so bug behavior is byte-identical.
3. Extend `test_probe_skipped_ids_collects_all_skip_lists_and_resolves_names` to assert the new
   `skip_ahead_blocked` id is folded in.

Verified: with `prerelease-complete-milestone` folded into the exclude set, the embedded merged
head becomes `hydra-overlay` (== the probe's current target) → `merged_head_override` returns
`None` → the guard does NOT withhold → the probe emits a valid `cycle_prompt` for `hydra-overlay`
(the item the operator expected next).

## Out of scope — coupled DESIGN FORK (hard-parked, NEEDS_INPUT)

Three coupled observations from the same friction are a routing-SEMANTICS design fork the operator
must ratify, because implementing them contradicts the operator's own stated expectation
(`hydra-overlay` next). Parked in `docs/specs/turn-routing-enforcement/NEEDS_INPUT_<date>-*.md`
(not implemented this round):

- **Gated-head classifier is too coarse (defect 2).** `_gated_head_kind` labels
  `inspector-sample-clip-view` / `inspector-track-dashboard` `research` (RESEARCH_PROMPT.md present,
  no RESEARCH.md), but BOTH actually route to `sub_skill=realign-spec` (`Step 4.6: upstream realign
  needed`) under `--strict-research-halt` — an ACTIONABLE non-research route. Correcting the
  classifier so a head with an actionable resolved route is NOT `research`-gated would make
  `inspector-sample-clip-view` DISPATCH to realign-spec as the queue head — NOT skip to
  `hydra-overlay`. That contradicts the operator's stated expectation (hydra-overlay next).
- **Truly-research-gated skip-vs-halt policy (defect 3).** Operator directive: a truly
  research-gated head (actual resolved route `terminal_reason=needs-research`) that is the
  merged/queue head must HALT and surface its RESEARCH_PROMPT.md, not be silently skipped. There is
  NO truly-research-gated head in the current AlgoBooth queue (all "research_gated_heads" resolve to
  realign-spec; the 3 BLOCKED heads resolve to `blocked`), so this policy has no live instance to
  validate against here. Additionally, the existing `research_halt_head` surfacing is gated on
  `_park_marker is not None` (park-mode only) — un-gating it to fire on default runs is itself a
  policy change.
- **Queue ordering (defect 4).** Operator hypothesis of a queue-ordering mistake. Verified: the 5
  gated + `prerelease-complete-milestone` (unmet deps) + 2 host-deferred sitting ahead of
  `hydra-overlay` are all higher-priority-but-currently-undispatchable pre-release items;
  skip-ahead correctly advances past them. The ordering is NOT the defect — the no-route was. This
  is `queue.json` (AlgoBooth target-repo DATA), out of the harness's edit scope regardless.

## Coupled-pair / parity note

`probe_skipped_ids` is the shared `lazy_core.dispatch` helper consumed by both `lazy-state.py` and
`bug-state.py` `--emit-prompt` merged-override paths — the fold is a single change benefiting both.
The `skip_ahead_blocked` surfacing itself is a feature-pipeline mechanic; bug state has no
skip-ahead readiness predicate, so no bug-state surfacing is added (documented parity, not a gap).
No SKILL prose contract changes; no sentinel schema touched.
