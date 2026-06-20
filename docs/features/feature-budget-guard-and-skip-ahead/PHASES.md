# Implementation Phases — Feature Budget Guard + Skip-Ahead

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this feature is entirely `lazy-state.py` / `lazy_core.py` state-machine logic plus thin markdown-wrapper prose (`/lazy-batch`, `/lazy-batch-cloud`, `/lazy`, `/lazy-cloud`). It has NO Tauri/MCP-reachable app surface (no stores, audio, UI state, IPC commands, or events). Per `docs/features/mcp-testing/SPEC.md` it falls in the "build tooling / no app integration" untestable class. Validation is the hermetic in-file `lazy-state.py --test` / `bug-state.py --test` smoke harness + the byte-pinned baselines + `lazy_parity_audit.py` — NOT the dev runtime. The Step-9 `/mcp-test` gate is expected to grant a structural MCP-skip (`__grant_skip_no_mcp_surface__`).

## Cross-feature Integration Notes

Phase-level dependencies on completed upstream features. The SPEC's `**Depends on:**` block lists two upstreams; neither is a `hard` dep, so per `/spec-phases` Step 1.5 there is no settled upstream PHASES.md to read against. They are recorded here for integration context:

- **unified-pipeline-orchestrator (kind=composes):** this feature extends that feature's run-marker counter infrastructure (`forward_cycles` / `meta_cycles` / `max_cycles`, the marker written by `--run-start` and advanced by `advance_run_counters` / `advance_forward_cycle`) and its merged-worklist ordering (`lazy_core.merged_priority` / `merged_worklist`). The new `per_feature_forward_cycles` map is added ALONGSIDE the existing run-level counters in the SAME marker (`lazy_core` run-marker writer). Phases 1–2 below consume this. A `composes` dep needs the upstream to *exist* (it does, Complete), not to be re-integrated phase-by-phase.
- **multi-repo-concurrent-runs (kind=soft):** the new per-feature counter and deferral state live in the per-repo keyed state dir via `lazy_core.claude_state_dir()` / `repo_key` — inherited automatically because the run marker already resolves through that chokepoint. No new path code; Phases 1–2 reuse the existing marker read/write helpers. A `soft` dep needs the upstream to exist, not to be Complete.

## Phase 1: Per-feature forward-cycle counter

**Scope:** Add a `per_feature_forward_cycles: {feature_id: int}` map to the run marker and advance it on the same two forward-advance triggers that already drive the run-level `forward_cycles`, keyed on the current `feature_id`. This is the data-collection slice — it observes and records per-feature cycle consumption but takes NO guard action yet (the trip lands in Phase 2). It crosses the existing counter-advance seam (`lazy_core.advance_run_counters` consume-oracle + `lazy_core.advance_forward_cycle` state-change) so the per-feature increment rides the exact triggers that move the run-level counter — no new oracle.

**Deliverables:**
- [ ] `lazy_core` run-marker writer (`write_run_marker` / the marker dict built in `--run-start`, ~`lazy_core.py:6660`) initializes `per_feature_forward_cycles: {}` alongside `forward_cycles: 0` / `meta_cycles: 0`. Legacy markers lacking the key default to `{}` on read (mirror the `last_advance_state_key` legacy-tolerance pattern).
- [ ] In BOTH forward-advance triggers — `advance_run_counters(state)` (consume-oracle, `lazy_core.py` ~line 7860) and `advance_forward_cycle(state)` (state-change, the `byref-dispatch-undercounts-forward-cycles` Phase-1 real-skill path) — when the advance fires AND the advancing `sub_skill` is a real (non-`__`) skill OR a member of `_FORWARD_ADVANCING_PSEUDO_SKILLS`, also increment `per_feature_forward_cycles[state["feature_id"]]` by 1. Reuse the EXACT same gate that advances the run-level counter (no second oracle); per-feature increment is a sibling write inside the same marker mutation, NOT a new advance path.
- [ ] Marker read helper exposes `per_feature_forward_cycles` so the probe/`compute_state` path can read it (defaults `{}` when absent).
- [ ] Tests: `lazy-state.py --test` fixture asserting that after ≥2 forward cycles on one fixture feature, the marker's `per_feature_forward_cycles[<id>]` equals the run-level advance count for that feature; a meta-only cycle does NOT increment it; a second feature gets its own independent key.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` passes a new fixture asserting `per_feature_forward_cycles[<feature_id>]` increments per forward cycle (and not on meta cycles), with the run marker round-tripped through `claude_state_dir()`.

**Runtime Verification** *(checked by integration test or manual testing):*
- [ ] `lazy-state.py --test` shows the per-feature-counter fixture PASS <!-- verification-only -->
- [ ] `bug-state.py --test` stays green (shared `lazy_core` advance helpers unbroken) <!-- verification-only -->

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — run-marker writer (`per_feature_forward_cycles` init), `advance_run_counters` + `advance_forward_cycle` (sibling per-feature increment), marker read helper.
- `user/scripts/lazy-state.py` — new `--test` fixture (per-feature counter).
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt` — regenerated via `_normalize_smoke_output` (NOT by hand).

**Testing Strategy:**
Hermetic `--test` fixture only — no runtime. Drive a fixture feature through ≥2 forward-advancing cycles (real-skill dispatch + a forward-advancing pseudo-skill apply), assert the marker map. Because the increment lives in shared `lazy_core` advance helpers, run BOTH `lazy-state.py --test` and `bug-state.py --test` to confirm the run-level counter semantics are unchanged (`test_lazy_core.py` characterizes the helpers directly).

**Integration Notes for Next Phase:**
- The marker map keyed by `feature_id` is the SINGLE input Phase 2's trip evaluation reads — Phase 2 adds NO new counter, only a comparison against the computed ceiling.
- Keep the per-feature increment gated by the SAME `_FORWARD_ADVANCING_PSEUDO_SKILLS` classifier the run-level counter uses, so "what counts as a forward cycle" stays defined in exactly one place.
- Legacy-marker tolerance (`{}` default) is load-bearing: a run resumed from a pre-feature marker must not KeyError.

---

## Phase 2: Guard trip + dynamic ceiling + defer-to-tail

**Scope:** Compute the dynamic per-feature ceiling `L_task`, evaluate the trip in `compute_state()` queue selection, and on trip defer the feature to the live-queue tail (run-scoped reorder, on-disk progress untouched) with bounded re-trip escalation (max 1 requeue → terminal eviction on 2nd trip). Add the `--per-feature-cycle-cap <N>` override flag, a new probe field surfacing the trip action + computed ceiling, and the rich audit metadata (cycle-count-at-trip, sub-skill phase, commit hash). This is the guard's automatic action — the thing `step_repeat_count`'s warning lacked.

**Deliverables:**
- [ ] `lazy_core.compute_per_feature_ceiling(max_cycles, ready_queue_depth, override=None) -> int` — pure function returning `override` when supplied (the `--per-feature-cycle-cap` path), else `max(6, min(C//... ))` per Locked Decision 4: `L_task = max(6, min(C_global * 4 // 10, (C_global // Q_depth) * 2))` with integer floor division (`⌊⌋`). Guards `Q_depth <= 0` → returns the 6 floor (no div-by-zero). Pure + side-effect-free for direct `test_lazy_core.py` characterization.
- [ ] `--per-feature-cycle-cap <N>` arg on `lazy-state.py` (and mirrored on `bug-state.py` for parity even if bug pipeline does not yet trip — audited by `lazy_parity_audit.py`); threaded into `compute_state()` as a new appended keyword param `per_feature_cycle_cap: int | None = None` (positional callers unbroken, mirroring the `--park-*` flag wiring).
- [ ] Trip evaluation in `compute_state()` queue-selection loop: for the candidate `current` feature, read `per_feature_forward_cycles[feature_id]` from the marker and compare against `compute_per_feature_ceiling(max_cycles, ready_queue_depth, override)`. `ready_queue_depth` = count of ready (non-gated, non-parked) queue features the loop already enumerates. On trip (count >= ceiling), append to a new `_DEFERRED_BUDGET` run-scoped skip-list and `continue` — analogous to the existing `--park-*` skip branches at `lazy-state.py:1387`+ (run-scoped reorder; does NOT write `queue.json`).
- [ ] Bounded re-trip escalation per RESEARCH_SUMMARY (max-1-requeue ladder): a marker field records each feature's deferral count. First trip → defer to tail (re-enters once). Second trip on the SAME feature in the SAME run → terminal eviction: mark dead-letter (a `budget_evicted[]` marker list + diagnostic), removed from the live queue for the rest of the run, on-disk progress preserved for human audit. No interactive halt.
- [ ] New probe field surfacing the guard action: `budget_guard: {feature_id, count_at_trip, computed_ceiling, action: "defer"|"evict", next_id, sub_skill_phase, commit_hash}` folded into the probe JSON (the orchestrator translates it into a PushNotification reporting the COMPUTED ceiling, not a fixed number). Rich audit metadata (count-at-trip, sub-skill phase, git HEAD short sha) per the RESEARCH_SUMMARY "rich audit metadata" recommendation.
- [ ] When the queue exhausts and only budget-deferred/evicted items remain, return an honest terminal (reuse / parallel the `queue-exhausted-all-parked` pattern) — NOT a false `all-features-complete`.
- [ ] Tests: `lazy-state.py --test` fixtures — (a) ceiling-formula across varying `max_cycles`×`Q_depth` (floor-of-6 honored on small runs, ≤40% cap honored on deep queues, `--per-feature-cycle-cap` overrides); (b) guard trips at computed ceiling and the next ready item is dispatched with the feature reordered to tail; (c) bounded re-trip → eviction on 2nd trip (does NOT loop indefinitely).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` passes fixtures asserting: the computed `L_task` equals the formula, a fixture feature exceeding the ceiling yields `budget_guard.action == "defer"` with the next ready item dispatched, and a 2nd trip yields `action == "evict"` (terminal eviction, no infinite loop).

**Runtime Verification** *(checked by integration test or manual testing):*
- [ ] `lazy-state.py --test` shows the ceiling/trip/defer/evict fixtures PASS <!-- verification-only -->
- [ ] `compute_per_feature_ceiling` characterized directly in `test_lazy_core.py` (boundary cases: `Q_depth==0`, `max_cycles<15` forcing the 6 floor, deep queue forcing the 40% cap) <!-- verification-only -->

**Prerequisites:**
- Phase 1: the `per_feature_forward_cycles` marker map (the trip's only data input).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `compute_per_feature_ceiling` (new pure fn), deferral/eviction marker fields + helpers, `_FORWARD_ADVANCING_PSEUDO_SKILLS` neighborhood untouched.
- `user/scripts/lazy-state.py` — `--per-feature-cycle-cap` arg, `compute_state()` trip-eval skip branch + `_DEFERRED_BUDGET`/`budget_evicted` lists, probe `budget_guard` field, exhaustion terminal, new fixtures.
- `user/scripts/bug-state.py` — mirror `--per-feature-cycle-cap` arg for parity (param threaded; bug-side trip is out of v1 scope but the flag must parse — matches the `--type bug` benign-parse precedent).
- `user/scripts/test_lazy_core.py` — characterize `compute_per_feature_ceiling`.
- `user/scripts/tests/baselines/{lazy-state,bug-state}-test-baseline.txt` — regenerated.

**Testing Strategy:**
Hermetic `--test` fixtures + direct `test_lazy_core.py` characterization of the pure ceiling fn. The trip-eval branch mirrors the proven `--park-*` skip-list shape, so its fixture mirrors the existing park fixtures (assert `current` advanced past the tripped feature, the tripped feature in the deferred list, the next ready item dispatched). The eviction fixture asserts a 2nd trip on the same feature does NOT re-defer indefinitely.

**Integration Notes for Next Phase:**
- The `--per-feature-cycle-cap` arg-threading pattern (appended `compute_state()` kwarg, mirrored on `bug-state.py`) is the EXACT pattern Phase 3's `--strict-research-halt` will follow — keep them consistent.
- The run-scoped reorder writes NO `queue.json` — Phase 4's wrapper notification glue must report the deferral as a run-scoped event, not a persisted queue change.
- The `budget_guard` probe field is the contract the Phase-4 wrapper prose consumes for the PushNotification — finalize its shape here so Phase 4 only adds glue.

---

## Phase 3: Dependency-aware skip-ahead (two-key readiness predicate)

**Scope:** Generalize the all-or-nothing `--skip-needs-research` skip into a default-on, dependency-aware skip-ahead past a gated (research-pending or BLOCKED) head. A queue item is "skip-ahead-ready" iff BOTH keys hold: (1) none of its `hard` deps resolve to a currently-gated item, AND (2) it carries an explicit `independent: true` (a.k.a. `no_shared_state`) marker in its SPEC frontmatter / queue entry. Add the `--strict-research-halt` opt-out flag restoring the legacy halt-on-first-gated-head. Surface the gated head (notification + end-of-run flush). Default absent-marker items degrade to today's strict halt (safe degradation).

**Deliverables:**
- [ ] `lazy_core` (or `lazy-state.py`) helper `parse_independent_marker(spec_text, queue_entry) -> bool` — reads an explicit `independent: true` / `no_shared_state: true` from the SPEC frontmatter OR the `queue.json` entry; default `False` when absent. Deterministic on-disk read, no LLM judgment.
- [ ] `skip_ahead_ready(candidate, gated_ids, repo_root, spec_dir) -> bool` — two-key predicate: reuse `parse_dep_block` (`lazy-state.py:831`) to get the candidate's deps, filter `kind == "hard"`, return `False` if any hard dep `feature_id` is in `gated_ids` (currently research-pending or BLOCKED); else require `parse_independent_marker` truthy. `soft`/`composes` deps do NOT block (they need the upstream to exist, not be Complete). Resolves dep ids via the existing `resolve_upstream_dir` only insofar as needed to test membership in `gated_ids` (id-set membership is sufficient — no Complete check).
- [ ] `--strict-research-halt` arg on `lazy-state.py` (mirrored on `bug-state.py` for parity); threaded as appended `compute_state()` kwarg `strict_research_halt: bool = False`. When set, restore the legacy halt-on-first-gated-head (the pre-feature `--skip-needs-research`-style halt). Default (flag absent) = the new dependency-aware skip-ahead is ON.
- [ ] Wire skip-ahead into the `compute_state()` queue-selection loop: when the head candidate is gated (research-pending per the existing `research_pending` peek at `lazy-state.py:1369`, OR BLOCKED), and `--strict-research-halt` is NOT set, add the gated head to a `gated_ids` set + a surfaced `_GATED_HEADS` skip-list and continue to the next candidate; dispatch the first candidate that passes `skip_ahead_ready`. An unmarked or downstream candidate is NOT dispatched (it degrades to today's strict behavior for that item).
- [ ] All-gated terminal: when every remaining item is gated, downstream of a gated item, or lacks the `independent: true` marker, return a clean terminal (reuse/parallel `queue-blocked-on-research`) with the gated heads surfaced — NOT a false completion. Log the skip-ahead audit (gated-head id + skipped-to id + the evaluated dep array) per RESEARCH_SUMMARY.
- [ ] Tests: fixtures for — skip-ahead advances onto an independent item (no hard dep on head AND `independent: true`); unmarked item NOT skipped onto (degrades to halt); downstream item (hard dep on head, even if marked) NOT skipped onto; all-gated clean terminal; `--strict-research-halt` restores legacy halt-on-first-gated-head.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` passes fixtures asserting the two-key predicate: an independent ready item IS dispatched past a gated head, while an unmarked-but-dep-free item and a downstream item are NOT — and `--strict-research-halt` reproduces the legacy halt.

**Runtime Verification** *(checked by integration test or manual testing):*
- [ ] `lazy-state.py --test` shows all five skip-ahead fixtures PASS <!-- verification-only -->
- [ ] `parse_independent_marker` + `skip_ahead_ready` characterized in `test_lazy_core.py` (marker present/absent/`no_shared_state` alias; hard vs soft/composes dep on a gated id) <!-- verification-only -->

**Prerequisites:**
- Phase 2: the appended-kwarg flag-threading pattern (`--strict-research-halt` follows the `--per-feature-cycle-cap` shape). Independent of the budget-guard logic otherwise.

**Files likely modified:**
- `user/scripts/lazy_core.py` — `parse_independent_marker`, `skip_ahead_ready` (or co-located in lazy-state.py if they need the local `parse_dep_block`; prefer lazy_core if the dep parser is moved/shared).
- `user/scripts/lazy-state.py` — `--strict-research-halt` arg, `compute_state()` skip-ahead branch + `gated_ids`/`_GATED_HEADS`, all-gated terminal, new fixtures.
- `user/scripts/bug-state.py` — mirror `--strict-research-halt` arg for parity (benign parse; bug pipeline has no research gate, so the flag is a no-op there — documented).
- `user/scripts/test_lazy_core.py` — characterize the two predicates.
- `user/scripts/tests/baselines/{lazy-state,bug-state}-test-baseline.txt` — regenerated.

**Testing Strategy:**
Hermetic `--test` fixtures building multi-feature queues with a gated head + downstream/independent/unmarked candidates, plus direct `test_lazy_core.py` characterization of the two predicates. The skip-ahead branch mirrors the existing `skip_needs_research` peek (`lazy-state.py:1362`), so its fixtures extend the existing research-skip fixtures (the `needs-research` fixture at `lazy-state.py:2642`+ is the template).

**Integration Notes for Next Phase:**
- The default-on behavior change (skip-ahead ON by default) is the single most operator-visible behavior delta — Phase 4 wrapper prose must document it AND the `--strict-research-halt` opt-out in BOTH batch wrappers' flag tables.
- A separate Phase-N (NOT in v1) can backfill the `independent: true` marker across existing queue items to widen reach; note this as a follow-up, do not author it here.
- The `_GATED_HEADS` surfaced list feeds the Phase-4 end-of-run flush — finalize its shape here.

---

## Phase 4: Wrapper lockstep + parity audit

**Scope:** Mirror the new flags, terminals, probe fields, and notification glue into the four thin wrappers in lockstep, register the new mechanic sets in the parity manifest, and confirm `lazy_parity_audit.py` is green and all baselines regenerated. This is the COUPLED-PAIR lockstep slice — no new state-machine logic, only the orchestrator-facing glue and the parity contract.

**Deliverables:**
- [ ] `/lazy-batch` (`user/skills/lazy-batch/SKILL.md`) — add the `--per-feature-cycle-cap` and `--strict-research-halt` flags to its flag/CLI surface; add the `budget_guard` trip → PushNotification glue (reporting the COMPUTED ceiling + next-id); add the skip-ahead default-on note + gated-head end-of-run flush; update the State Machine Summary / terminal table with the new budget-exhaustion + all-gated terminals.
- [ ] `/lazy-batch-cloud` (`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`) — mirror the above; update its "Differences from /lazy-batch" block ONLY where a genuine divergence exists (none expected — both pass the same flags; the budget guard + skip-ahead are environment-agnostic).
- [ ] `/lazy` (`user/skills/lazy/SKILL.md`) ↔ `/lazy-cloud` (`repos/algobooth/.claude/skills/lazy-cloud/SKILL.md`) — mirror any wrapper prose that surfaces the new flags/terminals (single-step variants; they pass the flags through but do not loop). Diff one against the other immediately after editing per the Coupling Rule.
- [ ] `lazy-parity-manifest.json` — register the new flags/CLI args as a mechanic set so `lazy_parity_audit.py` asserts both state scripts carry the `--per-feature-cycle-cap` and `--strict-research-halt` parse surface (and the mirrored param threading).
- [ ] `user/CLAUDE.md` (`user/scripts/CLAUDE.md`) — document the new CLI flags in the CLI-surface block and the per-feature budget guard + skip-ahead behavior, matching the existing `--park-*` / `--skip-needs-research` doc style.
- [ ] Tests: `lazy_parity_audit.py` green; `lazy-state.py --test`, `bug-state.py --test`, `lazy_coord.py --test` all green; `test_lazy_core.py` green; baselines match.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_parity_audit.py` exits 0 (both scripts carry the new mechanic set) AND `python3 user/scripts/lazy-state.py --test` + `python3 user/scripts/bug-state.py --test` both pass with baselines matching.

**Runtime Verification** *(checked by integration test or manual testing):*
- [ ] `lazy_parity_audit.py` green (new mechanic set asserted on both scripts) <!-- verification-only -->
- [ ] `python3 user/scripts/project-skills.py` re-run; the four wrappers' projected output expands cleanly (no broken `!cat` injections, no divergence the audit flags) <!-- verification-only -->
- [ ] `lint-skills.py --check-projected --check-capabilities` clean <!-- verification-only -->

**Prerequisites:**
- Phases 1–3: the state-machine flags, probe fields, and terminals the wrappers surface.

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — coupled pair (orchestrator glue + terminal table).
- `user/skills/lazy/SKILL.md`, `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` — coupled pair (flag pass-through prose).
- `user/scripts/lazy-parity-manifest.json` — new mechanic set.
- `user/scripts/CLAUDE.md` — CLI-surface + behavior docs.
- `user/scripts/tests/baselines/*.txt` — final regeneration if any earlier phase shifted them.

**Testing Strategy:**
Run the FULL gate set per the Coupling Rule: `lazy-state.py --test`, `bug-state.py --test`, `lazy_coord.py --test`, `test_lazy_core.py`, `lazy_parity_audit.py`, then `project-skills.py` + `lint-skills.py --check-projected --check-capabilities`. Diff each coupled-pair file against its partner immediately after editing to confirm only the intended divergence (the `--cloud` flag) differs. Green parity audit + green smoke suites + matching baselines is the acceptance gate.

**Integration Notes for Next Phase:**
- This is the terminal phase. When the last deliverable lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) and let the state machine route to the Step-9 MCP gate, which is expected to grant a structural MCP-skip (no app surface). Do NOT flip to Complete — that is the `__mark_complete__` gate's job.
- Phase-N follow-ups noted but OUT of v1 scope (record in Implementation Notes if hit): (a) composite trip signal (cycles + validation-blocks + corrective-phase-count); (b) `independent: true` marker backfill across the existing queue; (c) priority-inversion mitigation (recursively degrade priority of a deferred feature's downstream dependents); (d) file-touch-target validation / per-skip Git-branch isolation for skip-ahead hardening.

## Completion (gate-owned)

The top-level `**Status:**` flip to Complete, the `COMPLETED.md` receipt, the ROADMAP completion mark, and the `queue.json` trim are owned EXCLUSIVELY by the `__mark_complete__` gate (fires after the validation tail: Step-9 MCP gate → coverage audit). They are NOT authored as deliverable checkboxes in any phase above.
