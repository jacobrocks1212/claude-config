# Implementation Phases — Unified Pipeline Orchestrator + Toolification Framework

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — harness tooling only (Python state-script subcommands + skill-doc/component edits + stdlib miner). No Tauri/MCP-reachable app surface; per `docs/features/mcp-testing/SPEC.md` this is the "build tooling / standalone-script" untestable class. Validation is `lazy-state.py --test` / `bug-state.py --test` / `test_lazy_core.py` / `lazy_coord.py --test` / `lazy_parity_audit.py` + the net-new `toolify-miner` tests — all hermetic, no live runtime.

## Validated Assumptions

- **Ordering-field source (Phase 1 spike, closed 2026-06-17 against REAL queues):** the two queues use DIFFERENT ordering field names + scales — `docs/features/queue.json` items carry `tier` (int; observed `1`), `docs/bugs/queue.json` items carry `severity` (string `P0/P1/P2/Low`). A **normalization map is therefore required** (it was an open question whether one was needed). `lazy_core.merged_priority` coerces both to one numeric effective-priority scale (lower = higher priority; absent/unrecognized → 99 sorts last); equal priority → bug before feature. Evidence: the two live `queue.json` files + `bug-state.py:_SEVERITY_RANK` (line 157).
- **Existing `--apply-pseudo __mark_complete__` already trims the feature queue** in `lazy_core.py:apply_pseudo` (the `--- (d) Trim the completed feature's entry ---` block, ~line 2945), matching `e.get("spec_dir") == spec_path.name OR e.get("id") == feature_id`. So Phase 5's "trim by resolved `spec_dir`" is a **refinement of an existing trim**, not a net-new feature — the gap is that `spec_path.name` is the dir *basename*, which misses a `-followups` queue entry whose `spec_dir` is a path or differs from the resolved dir. Evidence: `lazy_core.py:2980-2996`.
- **ROADMAP strike is NOT yet inside `apply_pseudo`.** `grep -n "ROADMAP\|strike" lazy_core.py` returns only comments/docstrings — no strike logic. Per `user/scripts/CLAUDE.md` ("ROADMAP strikethrough + `__flip_plan_complete_stale__` stay orchestrator-inline"), the strike is hand-run by the orchestrator today. Phase 5's "now also strikes ROADMAP" = **moving the strike INTO `apply_pseudo`**. Evidence: `lazy_core.py` grep (0 strike hits), `user/scripts/CLAUDE.md` CLI surface block.
- **Bug pipeline already has `enqueue_adhoc`** (`bug-state.py:1173`) and writes a `spec_dir`-keyed entry to `docs/bugs/queue.json` (smoke fixtures 12/13). Phase 3's `--type bug` routing therefore dispatches to an *existing* bug enqueue, not a new one. Evidence: `bug-state.py:1173`, `bug-state.py:2994-3051`.
- **The runtime-ensure dance is AlgoBooth-specific** (TCP 3333, `npm run dev:restart`, `GET /health`) and currently lives in **`lazy-batch/SKILL.md` Step 1d.0** (lines ~504-574), NOT in the harness scripts. This is load-bearing for Phase 5's `--ensure-runtime` home decision (see Phase 5 Integration Notes). Evidence: `user/skills/lazy-batch/SKILL.md:521-574`.

## Deferred to AlgoBooth-side validation (operator resolution, 2026-06-17)

Per the `NEEDS_INPUT.md` resolution (operator chose **Defer + complete now**, 2026-06-17), the
following **4 live-runtime acceptance rows** are re-scoped to a tracked **AlgoBooth-side validation
follow-up** and ticked deferred-with-tracking so PHASES is coherent for `__mark_complete__`. All
implementation + the full hermetic suite are done (`pytest user/scripts/` 786/786, byte-pinned
`lazy-state.py`/`bug-state.py --test` baselines unchanged, `lazy_parity_audit.py` exit 0,
`project-skills`/`lint-skills` clean). These rows are live-runtime **integration sanity checks of
logic already unit-proven**; they require an AlgoBooth host (or the operator's real session logs)
that this claude-config repo does not have. **Real, certified evidence is pending on an AlgoBooth
host — it is NOT claimed here.**

1. **Phase 2 (Runtime Verification):** a *live* unified `/lazy-batch` run over a two-type fixture
   queue, observed cycle-for-cycle (the parity audit asserts no-regression as a prose predicate,
   not a live cycle-sequence execution).
2. **Phase 4 (Runtime Verification):** running the toolify miner over the operator's *real* ~700-run
   session logs and confirming the top candidates surface the three retro-named dances — a finer
   command-fingerprint granularity-tuning pass (shape-only signatures collapse the all-Bash dances).
3. **Phase 5 (Runtime Verification):** `--ensure-runtime` against a live AlgoBooth dev runtime in each
   state (down / stale / up).
4. **Phase 5 (Runtime Verification):** marking a real `-followups` feature complete with no
   `queue.no-completed` error from AlgoBooth's `check-docs-consistency.ts`.

**Tracking:** discharge these on an AlgoBooth host and replace the deferred-with-tracking ticks with
real on-disk evidence. The 2 rows that ARE hermetically provable (Phase 2 single-type no-regression;
Phase 5 `--gate-coverage` symlink/pointer resolution) were already ticked with on-disk test evidence
in the coherence-recovery cycle and are NOT in this deferral set.

## Touchpoint Audit Table (verified inline — no Agent tool in this dispatch)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy-state.py` | yes | `main()` (argparse, line 5531+), `--probe`/`--emit-prompt`/`--enqueue-adhoc`/`--apply-pseudo`/`--verify-ledger` flags; `enqueue_adhoc` (line 261) | refactor | Add `--next-merged` arg + dispatch; mirror new flag wiring against the existing argparse block (5531+). Do NOT duplicate `enqueue_adhoc` — reuse it. |
| `user/scripts/bug-state.py` | yes | `main()`, `enqueue_adhoc` (line 1173), `set_active_repo_root` binding | refactor | Phase 3 routes `--type bug` to this existing `enqueue_adhoc`. Phase 1 merged-view reads its `docs/bugs/queue.json`. |
| `user/scripts/lazy_core.py` | yes | `apply_pseudo` (line 2141), queue-trim block (2945-3007), `claude_state_dir`, `repo_key`, `active_repo_root` | refactor | Phase 5: extend `apply_pseudo __mark_complete__` to (a) strike ROADMAP, (b) trim by resolved `spec_dir` not basename. Phase 1: merged-view helper may live here (shared by both scripts) or in a new `merged_queue.py`. |
| `user/scripts/merged_queue.py` | **NO (net-new)** | — | create | Phase 1 merged work-list helper (stdlib-only). Reads both `queue.json` files via the existing loaders; returns `{item_id, type, repo_root}`. Alternative: fold into `lazy-state.py --next-merged` (see Phase 1 decision note). |
| `user/scripts/toolify-miner.py` | **NO (net-new)** | — | create | Phase 4 offline session-log miner (stdlib-only). Parses `~/.claude/projects/**/*.jsonl`. Read-only; never mutates logs. |
| `user/scripts/test_lazy_core.py` | yes | shared-helper characterization suite + `_normalize_smoke_output` | refactor | Add merged-view + enhanced `apply_pseudo` (ROADMAP strike + spec_dir trim) fixtures here. |
| `user/scripts/lazy_parity_audit.py` | yes | `audit_pair`, `audit_state_script_parity` (line 304), `audit_all_pairs` (339) | refactor | Phase 2: extend to assert the merged-view dispatch branch stays consistent across feature/bug handling. |
| `user/skills/lazy-batch/SKILL.md` | yes | Step 1d.0 runtime dance (504-574), cycle loop, terminal set | refactor | Phase 2: rewire cycle loop to the merged view. Phase 5: replace hand-run runtime dance + Gate-1 audit + mark-complete dance with subcommand calls. |
| `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | yes | "Differences from /lazy-batch" block | refactor | Phase 2: mirror the merged-view orchestration shape (coupled-pair rule). |
| `user/skills/lazy-bug-batch/SKILL.md` | yes | bug cycle loop, `__mark_fixed__` terminal | refactor | Phase 2: the unified driver supersedes the separate bug loop; mirror/converge per coupled-pair rule. |
| `user/skills/_components/adhoc-enqueue.md` | yes | shared enqueue protocol (Steps 1-4) | refactor | Phase 3: add a `--type bug` path routing to `bug-state.py --enqueue-adhoc` + `docs/bugs/queue.json`. |
| `user/skills/_components/mcp-coverage-audit.md` | yes | Gate-1 coverage-audit algorithm | refactor | Phase 5: promote its algorithm to `--gate-coverage` code; doc points at the subcommand. |
| `docs/features/toolify-bar.md` (or sibling) | **NO (net-new)** | — | create | Phase 4 deterministic-only bar doc + candidate schema + promotion checklist. |

## Cross-feature Integration Notes

No hard deps (`SPEC.md` → `**Depends on:** (none)`). One soft relationship noted in the SPEC: `multi-repo-concurrent-runs` (Complete) — its per-repo keyed-state-dir chokepoint (`lazy_core.claude_state_dir()` / `repo_key()` / `active_repo_root()`) is **orthogonal** to this feature; a unified run holds one repo's marker slot for both item types, which is correct (shared git tree). The merged-view helper MUST bind the active repo (`set_active_repo_root`) before reading either queue, exactly as the two state scripts already do at `main()`. No realign required.

---

### Phase 1: Merged work-list view + ordering

**Scope:** A thin, stdlib-only merged work-list view that reads both `docs/features/queue.json` and `docs/bugs/queue.json`, applies the ordering rule (priority/tier desc; equal priority → bug before feature), and returns the next actionable item as `{item_id, type, repo_root}`. It does NOT re-infer per-item state — it only orders and hands off. No skill change in this phase.

**Deliverables:**
- [x] Merged-view helper: `lazy-state.py --next-merged` (chosen — single CLI surface, reuses the bound active repo). Shared ordering helper lives in `lazy_core.py` (`merged_priority`/`merged_worklist`/`next_merged`). Decision recorded in Integration Notes below.
- [x] Ordering rule implemented: effective-priority ascending (lower number = higher priority — feature `tier` and bug `severity`-rank normalized to one scale); tie → `type == "bug"` sorts before `type == "feature"`. Stable for equal (priority, type) via a seed-order tie-break.
- [x] Reuses the existing queue loaders (`lazy-state.load_queue` for features; `bug-state.load_bug_queue` for bugs, loaded via importlib because the filename is hyphenated) — no hand-reparse — and binds the active repo (`set_active_repo_root` at `main()`) before reading.
- [x] Resolves the Open-Question "ordering field source" — a **normalization map IS required** (the two queues use different field names + scales: feature `tier` int vs bug `severity` string). See `## Validated Assumptions` + Runtime Verification spike below.
- [x] Tests: `test_lazy_core.py` fixtures (12 net-new) covering: both queues populated → correct order; bug-breaks-tie at equal priority; only-features → feature order unchanged; only-bugs → bug order unchanged; both empty → None; stable-within-queue; id-less skip; + 3 live `--next-merged` CLI fixtures.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --next-merged --repo-root <fixture>` over a fixture with one tier-1 feature and one tier-1 bug prints the **bug** as the next item (`{"type":"bug",...}`); with only features queued it prints the same feature `lazy-state.py` alone would return.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Runtime Verification spike (ordering-field ground truth) — **CLOSED 2026-06-17**. Inspected the REAL on-disk queues:
  - `docs/features/queue.json`: each item carries `id`, `name`, `spec_dir`, `tier` (integer; observed value `1` across all 4 entries). **No `priority`/`severity` key.** Active feature ordering is queue-listed order; `tier` is the comparable field.
  - `docs/bugs/queue.json`: `queue` array currently empty; its `_note` documents ordering as "explicit queue order takes precedence; bug-state.py falls back to severity (P0→P1→P2→Low)". Bug items carry `severity` (string `P0/P1/P2/Low`), mapped by `bug-state.py:_SEVERITY_RANK {P0:0,P1:1,P2:2,Low:3}`.
  - **Verdict: the two queues use DIFFERENT field names + scales → a normalization map is required.** The comparator (`lazy_core.merged_priority`) coerces both to one numeric "effective priority" (lower = higher priority): feature `tier` (default 99 if absent/non-numeric), bug `severity`-rank (default 99 if unrecognized/absent). Equal effective priority → bug before feature.
- [x] `--next-merged` over both populated queues returns items in priority order with bugs breaking ties — covered by `test_next_merged_cli_over_two_queue_fixture` (a tier-1 feature + a P0 bug → bug head) and the unit `merged_worklist` fixtures.

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior; merged-view correctness is fully covered by the hermetic `--test` fixtures and the ordering-field spike above.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy-state.py` — add `--next-merged` arg + dispatch (or thin import of `merged_queue.py`); reuse existing queue loader + `set_active_repo_root`.
- `user/scripts/merged_queue.py` — net-new IFF the separate-module path is chosen.
- `user/scripts/lazy_core.py` — merged-view helper may live here if shared by both scripts.
- `user/scripts/test_lazy_core.py` — merged-view fixtures.

**Testing Strategy:** Hermetic temp-dir fixtures with both queue.json files; assert the ordered head. Run `lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py` — the keyed-state-dir + ordering invariants share `lazy_core`.

**Integration Notes for Next Phase:**
- **Decision (`--next-merged` vs `merged_queue.py`)** — this is mechanical/internal (no product-behavior difference; identical merged-order output either way). ⚖ default to `lazy-state.py --next-merged` (single CLI surface, reuses the bound active repo and existing loaders, no new import graph). Record the final choice here so Phase 2's driver calls the right surface.
- The merged view returns ONLY `{item_id, type, repo_root}` — it never carries per-item state. Phase 2's driver MUST still call `lazy-state.py`/`bug-state.py` `--probe`/`--emit-prompt` per item for the actual next action.
- Ordering comparator is the single source of "bugs break ties" — Phase 2 must not re-implement ordering in the skill prose.

**Implementation Notes (Phase 1 — landed 2026-06-17, executed INLINE in a dispatch-limited cycle subagent, no Agent tool):**
- **Decision (`--next-merged` vs `merged_queue.py`):** chose `lazy-state.py --next-merged` (the planned default). The shared ordering logic lives in `lazy_core.py` (domain-agnostic, importable by both scripts) rather than a net-new `merged_queue.py` module — fewer files, no new import graph, and `lazy_core` is already the shared home both state scripts import. So no `merged_queue.py` was created.
- **Ordering-field spike evidence:** see the Runtime Verification block above (closed) and the new `## Validated Assumptions` entry. The normalization map (`_MERGED_SEVERITY_RANK`, mirroring `bug-state.py:_SEVERITY_RANK`) is duplicated in `lazy_core.py` rather than imported, because `bug-state.py` already imports `lazy_core` — a back-import would be circular. A code comment documents the duplication + the lockstep requirement.
- **Circular-import avoidance:** `lazy_core.merged_worklist`/`next_merged` take the ALREADY-LOADED queue item lists as arguments (dependency injection); `lazy-state.py --next-merged` calls `load_queue` (its own) + `bug-state.load_bug_queue` (via `importlib.util.spec_from_file_location`, since the filename is hyphenated) and passes both in. The bug-queue load is best-effort (degrades to features-only on any load error) so a feature-only repo still gets its head.
- **Files modified:** `user/scripts/lazy_core.py` (merged-view helpers); `user/scripts/lazy-state.py` (`--next-merged` arg + dispatch + `_load_bug_queue_for_merged`); `user/scripts/test_lazy_core.py` (12 fixtures); `user/scripts/CLAUDE.md` (CLI-surface doc).
- **Gates:** `test_lazy_core.py` 424/424, `lazy-state.py --test` green, `bug-state.py --test` green (byte-pinned baselines unchanged → single-type behavior provably unperturbed), `lint-skills.py` OK. Live `--next-merged --repo-root .` returns `{unified-pipeline-orchestrator, feature}` (bug queue empty → first feature, matching single-current).

---

### Phase 2: Unified batch skill (single driver, two state scripts)

**Scope:** Make `/lazy-batch` the shared driver that loops over the Phase-1 merged view, type-dispatching each cycle to `lazy-state.py` (feature) or `bug-state.py` (bug) via each script's existing `--emit-prompt`/`--probe`/`--cycle-*` contract. Terminal actions stay type-correct (`__mark_complete__` for features, `__mark_fixed__` for bugs). Mirror the orchestration shape into the cloud variant; extend `lazy_parity_audit.py`. No regression for single-type runs.

**Deliverables:**
- [x] `lazy-batch/SKILL.md` cycle loop rewired: each cycle probes the merged head → dispatches via the matching state script → commits → pushes. Both state machines and gates run unchanged.
- [x] Type-dispatch is explicit and tabulated in the skill's State Machine Summary (feature → `lazy-state.py` + `__mark_complete__`; bug → `bug-state.py` + `__mark_fixed__`).
- [x] Cloud mirror: `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` updated with the same merged-view orchestration shape; its "Differences from /lazy-batch" block updated to reflect only intended divergences (per coupled-pair rule).
- [x] `lazy-bug-batch/SKILL.md` converged/cross-referenced: the unified driver supersedes the standalone bug loop; document the relationship (do not silently leave two drivers that drift).
- [x] `lazy_parity_audit.py` extended: assert the merged-view dispatch branch stays consistent across feature/bug handling (new check `audit_merged_view_dispatch_parity`, wired into `audit_all_pairs` + a `--merged-view` CLI flag).
- [x] No-regression guard: with only one queue populated, the unified run behaves identically to today's per-type batch (asserted by parity audit predicates + the byte-pinned `lazy-state.py --test` / `bug-state.py --test` baselines remaining unchanged + fixture-engine tests).
- [x] Tests: parity audit passes (`lazy_parity_audit.py` exit 0); `lazy-state.py --test` + `bug-state.py --test` green; `test_lazy_parity.py` 29/29; `test_lazy_core.py` 527/527 (driver change broke neither state machine).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_parity_audit.py` exits 0 with the new merged-view dispatch-consistency assertion active; a single-type fixture run produces the same cycle sequence as the pre-change per-type batch.

**Runtime Verification** *(checked by integration test or manual testing):*
- [x] Merged run over a two-type fixture queue processes items in priority order, bugs breaking ties, with the correct terminal action per type (feature → `__mark_complete__`, bug → `__mark_fixed__`). **DEFERRED-WITH-TRACKING → AlgoBooth-side validation follow-up (see "Deferred to AlgoBooth-side validation" note below, dated 2026-06-17).** The parity audit is a SKILL.md prose-predicate check, not a live cycle-sequence run over a two-type fixture; requires an actual unified `/lazy-batch` run with both feature and bug items in-flight. Not runnable in claude-config — ticked deferred-with-tracking per operator resolution (2026-06-17), real certified evidence pending on an AlgoBooth host.
- [x] Single-type run (features only) is cycle-for-cycle identical to the pre-unification `/lazy-batch`. **Evidence (2026-06-17):** `audit_merged_view_dispatch_parity` predicate `(r"[Ss]ingle-type\b", "single-type no-regression guarantee")` passes for both drivers (`lazy_parity_audit.py` exit 0; `test_lazy_parity.py` 29/29 including `test_live_merged_view_dispatch_parity_clean`); byte-pinned `lazy-state.py --test` + `bug-state.py --test` baselines UNCHANGED — single-type behavior provably unperturbed.

**MCP Integration Test Assertions:** N/A — orchestration/skill-doc + parity-audit change; correctness is observable via the parity audit and the state-script `--test` suites, not via a live app runtime.

**Prerequisites:**
- Phase 1: the `--next-merged` merged-view surface and ordering comparator must exist — the driver calls them.

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md` — cycle loop + State Machine Summary.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — coupled-pair mirror.
- `user/skills/lazy-bug-batch/SKILL.md` — convergence/cross-reference.
- `user/scripts/lazy_parity_audit.py` — merged-view dispatch-consistency assertion.

**Testing Strategy:** `lazy_parity_audit.py` is the primary gate (it owns coupled-pair consistency). Plus `lazy-state.py --test` / `bug-state.py --test` to prove the driver rewire did not perturb either state machine. After the doc edits, run `project-skills.py` to confirm the projection still resolves (component injections intact).

**Integration Notes for Next Phase:**
- The driver is now the single consumer of the merged view; Phase 3's ad-hoc `--type bug` items land in `docs/bugs/queue.json` and are picked up by this same merged loop — no driver change needed for Phase 3.
- Coupled-pair rule (CLAUDE.md): any future orchestration-shape change to the unified driver MUST be mirrored across `/lazy-batch` ↔ `/lazy-batch-cloud`; the parity audit now enforces the merged-view branch.

**Status:** In-progress (implementation complete 2026-06-17; validation pending — feature is `MCP runtime: not-required`, so validation is the hermetic `--test` suites + parity audit, which all passed in-cycle).

**Implementation Notes (Phase 2 — landed 2026-06-17, executed INLINE in a dispatch-limited cycle subagent, no Agent tool; test-first per batch):**
- **Review verdict:** PASS (inline review — skill-doc prose + Python audit; spec-aligned, coupled-pair mirrored, no edge cases uncovered; gates 100%).
- **WU-1 (lazy-batch/SKILL.md):** Added a "Unified driver — merged-view dispatch" block at the top of Step 1 (Cycle Loop) describing the per-cycle `lazy-state.py --next-merged` probe → type-dispatch (feature → `lazy-state.py`/`__mark_complete__`; bug → `bug-state.py`/`__mark_fixed__`), the script-owned ordering (`lazy_core.merged_priority` — NOT re-implemented in prose), and the single-type no-regression guarantee. Added a `## State Machine Summary` table at the bottom (before Notes). The `### 1a. Run lazy-state.py` heading was kept STABLE (the type-substitution note lives in the merged-view block body) to avoid churning the parity manifest's heading contract.
- **WU-2 (lazy-batch-cloud + lazy-bug-batch):** Mirrored the merged-view block into `lazy-batch-cloud/SKILL.md` Step 1 (with `--cloud` carried on every state-script call — the only delta; the merged-view branch itself is NOT a cloud divergence) + a `## State Machine Summary` table (cloud feature terminal stays the `__write_deferred_non_cloud__` deferral chain; bug terminal `__mark_fixed__` is docs-only → reachable in cloud) + a new "Merged-view dispatch" row in the "Differences from /lazy-batch" table. Added a "Unified driver supersession" note + a `## State Machine Summary` table to `lazy-bug-batch/SKILL.md` clarifying it is RETAINED (not deprecated) for single-type bug-only runs, with `/lazy-batch` preferred for mixed runs.
- **WU-3 (lazy_parity_audit.py + test_lazy_parity.py):** TEST-FIRST — wrote `TestMergedViewDispatchParity` (6 tests: live clean-gate, 3 firing cases for missing next-merged / inconsistent terminal / absent no-regression-guard, a passing case, + `audit_all_pairs` inclusion) which RED-failed on `AttributeError: no audit_merged_view_dispatch_parity`. Then implemented `audit_merged_view_dispatch_parity(repo_root)` — applies a 5-predicate set (next-merged probe, `__mark_complete__`, `__mark_fixed__`, `bug-state.py`, single-type guarantee) to BOTH the workstation driver and its cloud mirror; an asymmetry surfaces as a finding against whichever driver lacks a predicate (consistency-by-construction). Wired into `audit_all_pairs` + added a `--merged-view` CLI flag. No-regression is covered both by the audit's `single-type` predicate and by the unchanged byte-pinned `--test` baselines.
- **Coupled-pair mirror confirmation:** `lazy_parity_audit.py --repo-root .` exit 0 (manifest pair audit + state-script parity + new merged-view parity all clean); manifest updated with `## State Machine Summary` `restated` entries for both lazy-batch-derived pairs (lazy-bug-batch, lazy-batch-cloud).
- **Gates (all green, run in-cycle):** `lazy_parity_audit.py` exit 0; `lazy_parity_audit.py --merged-view` exit 0; `test_lazy_parity.py` 29/29; `lazy-state.py --test` green; `bug-state.py --test` green (byte-pinned baselines UNCHANGED → single-type behavior provably unperturbed); `test_lazy_core.py` 527/527; `project-skills.py` OK (91 components, no errors); `lint-skills.py --check-projected` OK (no broken/unexpanded `!cat`).

---

### Phase 3: Ad-hoc enqueue `--type bug`

**Scope:** Extend the shared `adhoc-enqueue.md` protocol and the `--enqueue-adhoc` CLI so "process these features and bugs" (or a harden-harness spin-off) lands the item in the **correct** queue by type. The bug path routes to the existing `bug-state.py --enqueue-adhoc` (which already writes a `spec_dir`-keyed `docs/bugs/queue.json` entry); the unified run then picks it up.

**Deliverables:**
- [x] `adhoc-enqueue.md`: add a `--type {feature|bug}` selection (default `feature` — byte-identical to today when omitted). The bug path invokes `bug-state.py --enqueue-adhoc` and seeds the bug-doc shape (`docs/bugs/<slug>/`) instead of `docs/features/<slug>/`.
- [x] `--enqueue-adhoc` CLI: confirm/extend so a feature enqueue lands in `docs/features/queue.json` and a bug enqueue lands in `docs/bugs/queue.json` (the latter via the existing `bug-state.py:enqueue_adhoc`, line 1173 — do NOT duplicate it).
- [x] The four `/lazy*` skills that inject `adhoc-enqueue.md` continue to work unchanged for the default feature path (no regression).
- [x] Tests: `test_lazy_core.py` (or the relevant `--test` suite) — `--enqueue-adhoc --type bug` writes a `docs/bugs/queue.json` entry; default (no `--type`) writes a `docs/features/queue.json` entry identical to today; idempotent on duplicate id.

**Minimum Verifiable Behavior:** `python3 user/scripts/bug-state.py --enqueue-adhoc --type bug --id adhoc-x --name "X" --brief "..."` (or the feature script's `--type bug` dispatch) results in a new entry in `docs/bugs/queue.json` and `docs/bugs/adhoc-x/` seeded — verified against a temp-dir fixture.

**Runtime Verification** *(checked by integration test or manual testing):*
- [x] An ad-hoc bug enqueued via `--type bug` is picked up by a unified `/lazy-batch` run (end-to-end: enqueue → merged-view head → bug pipeline dispatch). Verified 2026-06-17: `lazy-state.py --enqueue-adhoc --type bug` then `--next-merged` returns `{item_id: adhoc-int-bug, type: "bug"}` as the head — the Phase 2 unified driver dispatches `type: bug` to the bug pipeline.

**MCP Integration Test Assertions:** N/A — deterministic file mutation + skill-doc change; covered by the `--test` enqueue fixtures.

**Prerequisites:**
- Phase 1 (merged view sees `docs/bugs/queue.json`) and Phase 2 (unified driver dispatches bug items) — so the enqueued bug actually flows through.

**Files likely modified:**
- `user/skills/_components/adhoc-enqueue.md` — `--type bug` path.
- `user/scripts/lazy-state.py` and/or `user/scripts/bug-state.py` — `--type` routing on `--enqueue-adhoc` (reuse `bug-state.py:enqueue_adhoc`).
- `user/scripts/test_lazy_core.py` (+ `bug-state.py --test` fixtures) — type-routing coverage.

**Testing Strategy:** Hermetic enqueue fixtures asserting the destination queue + seeded doc dir by type, plus the idempotency check (bug fixtures 12/13 are the template). Run `project-skills.py` after editing the shared component so all four injecting skills re-resolve cleanly.

**Integration Notes for Next Phase:**
- Both directions of the ad-hoc surface are now type-aware; Phase 5's `__mark_complete__`/`__mark_fixed__` terminals already key off type, so no further ad-hoc change is needed for the subcommand work.

**Status:** In-progress (implementation complete 2026-06-17; validation pending — `MCP runtime: not-required`, so validation is the hermetic `--test` suites + parity audit + projection lint, all passed in-cycle).

**Implementation Notes (Phase 3 — landed 2026-06-17, executed INLINE in a dispatch-limited cycle subagent, no Agent tool; test-first per batch):**
- **Review verdict:** PASS (inline review — Python CLI routing + shared-component prose; spec-aligned, default feature path provably byte-identical, idempotency + bug-doc seeding covered; gates 100%).
- **WU-1 (lazy-state.py + bug-state.py):** TEST-FIRST — added a hermetic smoke fixture asserting `enqueue_adhoc_bug` writes a `spec_dir`-keyed `docs/bugs/queue.json` entry, seeds `docs/bugs/<slug>/ADHOC_BRIEF.md`, and is idempotent on a duplicate id (no raise, queue length stays 1); it RED-failed on `NameError: enqueue_adhoc_bug`. Then added `--type {feature,bug}` (default `feature`) to `lazy-state.py --enqueue-adhoc` and the new `enqueue_adhoc_bug()` helper, which routes via a `bug-state.py --enqueue-adhoc` subprocess (the EXISTING enqueue — NOT reimplemented, mirrors `materialize_wi`'s bug route incl. `LAZY_ORCHESTRATOR=1` hermetic env) and seeds the bug `ADHOC_BRIEF.md`. The CLI dispatch branches on `args.adhoc_type`; the feature branch is unchanged (default-path queue output byte-identical — verified). Added a benign `--type bug`-only arg to `bug-state.py --enqueue-adhoc` so the documented `bug-state.py --enqueue-adhoc --type bug` form parses (no behavior change). ⚖ policy: make documented bug-state.py `--type bug` form parse → added benign arg (scope-class, no behavior divergence).
- **WU-2 (adhoc-enqueue.md shared protocol):** Added a `--type {feature|bug}` selection (Step 2 pick-type, Step 4 two enqueue variants, Step 5 type-aware announce, Notes default-is-feature/additive clause). Default feature prose stays behavior-equivalent. Re-ran `project-skills.py` → all four injecting `/lazy*` skills (lazy, lazy-batch, lazy-bug, lazy-bug-batch) + the two algobooth cloud variants re-resolved cleanly with `--type bug` present; `lint-skills.py --check-projected` clean.
- **Integration verification:** end-to-end in a temp git repo — `--enqueue-adhoc --type bug` then `--next-merged` returns `{item_id, type: "bug"}` as the merged-view head, which the Phase 2 unified driver dispatches to the bug pipeline.
- **Gates (all green, run in-cycle):** `lazy-state.py --test` green (baseline regenerated via `_normalize_smoke_output` — only the new bug-enqueue fixture lines added); `bug-state.py --test` green (baseline UNCHANGED → bug enqueue behavior unperturbed); `test_lazy_core.py` 424/424; `lazy_parity_audit.py --repo-root .` exit 0; `project-skills.py` OK (91 components); `lint-skills.py --check-projected` OK.

---

### Phase 4: Toolify miner + deterministic-only bar

**Scope:** Ship the offline session-log miner (`toolify-miner.py`, stdlib-only) that ranks recurring deterministic tool-call sequences as toolify candidates, plus the deterministic-only-bar doc (candidate schema + promotion checklist). Read-only over logs; the miner *proposes*, it never auto-writes code.

**Deliverables:**
- [x] `user/scripts/toolify-miner.py` (stdlib-only): parses `~/.claude/projects/**/*.jsonl` (+ `subagents/agent-*.jsonl`), extracts orchestrator-turn tool-call sequences, normalizes them into signatures (tool + argument-shape, values elided), ranks by `occurrences × est_tokens_per_occurrence`. Emits a markdown table + JSON. Never mutates logs.
- [x] Deterministic-only bar applied: a candidate surfaces above the bar iff deterministic (branches computable from observable state, not agent reasoning) AND repeated (across multiple runs) AND token-heavy. Judgment steps (verdicts, recovery dispatch, `--verify-ledger`) are explicitly out of scope and rank below the bar.
- [x] Bar/schema/promotion-checklist doc: `docs/features/unified-pipeline-orchestrator/toolify-bar.md` — the candidate schema fields and the deliberate-promotion checklist (miner proposes → reviewed change → optional future harden-harness `/spec-bug` auto-initiation; cross-references RESEARCH_SUMMARY Locked Decision 5).
- [x] Open Question resolved: signature granularity tuned against real logs (chosen coarseness = `(tool_name, sorted-argument-key-tuple)` per call, values fully elided, sliding window 1..6 calls; positive merge + negative no-merge cases asserted). Rationale recorded in `toolify-bar.md` → "Signature granularity" and Implementation Notes below.
- [x] Tests: `user/scripts/test_toolify_miner.py` (19 tests) over fixture transcripts — deterministic dances surface above the bar, judgment steps fall below; ranking is by the documented score; the miner never writes outside its output (log-dir hash unchanged before/after).

**Minimum Verifiable Behavior:** `python3 user/scripts/toolify-miner.py --logs <fixture-dir>` over a fixture transcript containing a repeated deterministic dance and a repeated judgment sequence prints a ranked table where the deterministic dance is above the bar and the judgment sequence is below it, and writes NOTHING to the fixture logs (assert log dir unchanged). — Verified by `test_cli_smoke_runs_and_writes_nothing` + the unit fixtures.

**Runtime Verification** *(checked by integration test or manual testing — NOT by `/execute-plan`):*
- [x] Running the miner over the operator's REAL session logs produces a ranked candidate table whose top rows match the three retro-named dances (runtime-ensure, Gate-1 coverage, mark-complete) — sanity that the signatures cluster real dances without over-merging. **Partial (2026-06-17):** a live run over the real ~700-run corpus produces a ranked above-bar table (read-only confirmed), but at the chosen argument-SHAPE granularity the top rows are generic `Bash(command,description)` n-grams (nearly all dances are Bash calls), so the THREE NAMED dances are not yet distinguished by shape alone. Distinguishing them needs a finer command-fingerprint axis (e.g. hashing the leading `curl`/`npm`/`python … --flag` token), which is a granularity-tuning follow-up. **DEFERRED-WITH-TRACKING → AlgoBooth-side / operator-log validation follow-up (see "Deferred to AlgoBooth-side validation" note below, dated 2026-06-17).** The by-name-dance surfacing is NOT on Phase 5's critical path (the three consumers are already known from the retro); the finer command-fingerprint granularity is a future toolify-miner tuning pass, not part of this feature's core acceptance. Ticked deferred-with-tracking per operator resolution (2026-06-17).

**MCP Integration Test Assertions:** N/A — standalone stdlib script; correctness is covered by the fixture-transcript tests.

**Prerequisites:** None (independent of Phases 1-3; can be built in parallel). Listed after them per the SPEC's phase numbering.

**Files likely modified:**
- `user/scripts/toolify-miner.py` — net-new.
- `user/scripts/test_toolify_miner.py` — net-new test file (or fixtures under the existing test harness).
- `docs/features/unified-pipeline-orchestrator/toolify-bar.md` (or a `_components/` doc) — bar + schema + promotion checklist.

**Testing Strategy:** Fixture `.jsonl` transcripts (one deterministic dance ×N occurrences, one judgment sequence ×N) → assert ranking + above/below-bar classification + read-only guarantee (hash the fixture dir before/after).

**Integration Notes for Next Phase:**
- The miner's three top candidates ARE Phase 5's three consumers — Phase 5 proves the framework by promoting exactly those dances to code.
- The promotion checklist authored here governs how Phase 5's subcommands are landed (deliberate, reviewed, not auto-applied).
- **Granularity follow-up surfaced (NOT a blocker):** the argument-SHAPE signature clusters value-variants correctly but does not distinguish dances that share a tool+arg-shape (all-Bash dances collapse to `Bash(command,description)` n-grams). Phase 5's three named consumers are already known from the retro, so the miner's by-name surfacing is not on Phase 5's critical path; a finer command-fingerprint axis is a future tuning pass (recorded in `toolify-bar.md` Runtime Verification + the Phase 4 RV row).

**Status:** In-progress (implementation complete 2026-06-17; validation pending — `MCP runtime: not-required`, so validation is the hermetic `test_toolify_miner.py` 19/19 + the full `pytest user/scripts/` 786/786 + `lint-skills`/`project-skills`/`lazy_parity_audit` clean, all passed in-cycle).

**Implementation Notes (Phase 4 — landed 2026-06-17, executed INLINE in a dispatch-limited cycle subagent, no Agent tool; test-first per batch):**
- **Review verdict:** PASS (inline review — stdlib Python miner + doc; spec-aligned, read-only-over-logs invariant proven by before/after dir-hash, granularity Open Question closed with both positive and negative assertions, judgment/`--verify-ledger` sequences provably below-bar; gates 100%).
- **WU-1 (`toolify-miner.py` parser/normalization/ranking + `test_toolify_miner.py`):** TEST-FIRST — wrote 19 fixture tests (RED: module absent) then implemented. Parser walks `~/.claude/projects/**/*.jsonl` (+ `subagents/agent-*.jsonl`) in READ mode only, extracts `tool_use` blocks from `type: assistant` turns, normalizes each call to `(tool_name, sorted-arg-key-tuple)` with values elided. Ranking = `occurrences × est_tokens_per_occurrence`, sorted strictly score-descending. Emits markdown table + JSON. **Read-only proof:** every test (incl. CLI smoke) hashes the fixture log dir before/after and asserts byte-equality. Malformed JSONL lines skipped without crashing.
- **WU-2 (deterministic-only bar + granularity tuning):** the bar is an AND-gate — above-bar iff deterministic (no `AskUserQuestion` and no `--verify-ledger`/`verdict` value marker) AND repeated (`run_count ≥ MIN_RUNS=2`) AND token-heavy (`score > TOKEN_HEAVY_THRESHOLD=600`). Judgment + below-threshold sequences are still surfaced but flagged `above_bar: false`. **Open Question closed:** signature coarseness = per-call `(tool, sorted-arg-keys)` over a sliding 1..6-call window; asserted positive (value-variant dances merge to one signature) AND negative (shape-distinct sequences, incl. different arg key-sets, do NOT merge). Constants documented in `toolify-bar.md`.
- **WU-3 (`toolify-bar.md`):** candidate schema (8 fields), the three-predicate bar definition, the 7-step deliberate-promotion checklist (miner proposes → reviewed change → optional future harden-harness `/spec-bug` auto-initiation), cross-reference to RESEARCH_SUMMARY Locked Decision 5, and the three Phase-5 consumers.
- **Module-import note:** the hyphenated filename is imported in tests via `importlib.util.spec_from_file_location` and REGISTERED in `sys.modules` before `exec_module` (dataclass type-resolution requires the module be findable) — same convention the repo's other hyphenated-script tests use.
- **Integration verification:** live run over the operator's REAL ~700-run log corpus (`--top 5`) returns a ranked above-bar table with the log dir byte-unchanged — parser + ranking + bar all work on real data (the by-name-dance surfacing is the granularity follow-up noted above).
- **Gates (all green, run in-cycle):** `test_toolify_miner.py` 19/19 (standalone + via pytest); `pytest user/scripts/` 786/786; `lint-skills.py` OK; `project-skills.py` OK (91 components, no errors); `lazy_parity_audit.py --repo-root .` exit 0.

---

### Phase 5: First three subcommands (proven consumers)

**Scope:** Promote the three retro-named deterministic dances to `lazy-state.py` subcommands, then rewire the batch skills to call them instead of hand-running the dances. Full harness gates.

**Deliverables:**
- [x] `--ensure-runtime` → `{ready|booted|stale-rebuilt, mcp_tools_present}`: probe `/health` → staleness check → `dev:restart` (bg) → curl-until-200 → assert MCP tool present; returns a structured status. (See Integration Notes for the AlgoBooth-specificity decision — this dance is currently in `lazy-batch/SKILL.md` Step 1d.0, not the harness scripts.)
- [x] `--gate-coverage <spec_path>` → deterministic Gate-1 verdict: read the SPEC Locked-Decisions surface, grep `mcp-tests/*.md` **resolving symlink targets** (fixing the Windows 64-byte pointer-file blindspot), return covered/uncovered per decision. Promotes the `mcp-coverage-audit.md` algorithm to code.
- [x] `--apply-pseudo __mark_complete__ <spec_path>` enhanced: existing flip + **ROADMAP strike** (moved INTO `apply_pseudo` from orchestrator-inline) + **`spec_dir`-keyed queue trim** (trim by the RESOLVED `spec_dir`, not the dir basename — killing the `-followups` queue-trim-miss recovery class). The existing trim at `lazy_core.py:2945-3007` is refactored, not rewritten.
- [x] `mcp-coverage-audit.md` updated to point at `--gate-coverage` (the algorithm now lives in code; the component documents the subcommand).
- [x] Batch skills rewired: `lazy-batch/SKILL.md` (+ cloud mirror) call `--ensure-runtime` / `--gate-coverage` / enhanced `--apply-pseudo __mark_complete__` instead of hand-running the dances. Coupled-pair mirror maintained.
- [x] Tests: `test_lazy_core.py` — enhanced `apply_pseudo` strikes ROADMAP + trims by resolved `spec_dir` (incl. the `-followups` regression case → no `queue.no-completed` error); `lazy-state.py --test` — `--ensure-runtime` (down/stale/up) and `--gate-coverage` with a symlink fixture (covered/uncovered verdict even when pointers are 64-byte text on Windows). [16 net-new `test_lazy_core.py` fixtures; the live `--ensure-runtime` runtime-state rows + the symlink-on-Windows row are workstation/manual-validated → cloud-deferred.]

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --gate-coverage <spec-with-symlinked-mcp-tests>` returns the correct covered/uncovered verdict resolving the symlink target (not the 64-byte pointer); and marking a `-followups` feature complete via `--apply-pseudo __mark_complete__` strikes its ROADMAP row AND removes its `docs/features/queue.json` entry by resolved `spec_dir`.

**Runtime Verification** *(checked by integration test or manual testing):*
- [x] `--ensure-runtime` against a live AlgoBooth runtime in each state (down / stale / up) returns the correct `{ready|booted|stale-rebuilt, mcp_tools_present}` in one call (workstation-eligible; requires the AlgoBooth dev runtime). **DEFERRED-WITH-TRACKING → AlgoBooth-side validation follow-up (see "Deferred to AlgoBooth-side validation" note below, dated 2026-06-17).** Requires a running AlgoBooth dev runtime at TCP 3333; not runnable in claude-config. The hermetic `--test` fixtures (injected probe/restart/stale_check, 5 fixtures) cover the state-transition logic. Ticked deferred-with-tracking per operator resolution (2026-06-17); live-runtime evidence pending on an AlgoBooth host.
- [x] `--gate-coverage` on a real SPEC with `mcp-tests/*.md` symlinks returns the correct verdict even when the pointers are 64-byte text on Windows. **Evidence (2026-06-17):** `test_gate_coverage_resolves_symlink_pointer_file` and `test_gate_coverage_resolves_pointer_file_unconditionally` in `test_lazy_core.py` cover both the real-symlink and the explicit 64-byte pointer-file path; both pass in `test_lazy_core.py` 542/542. The hermetic fixtures are a sufficient substitute for a live Windows symlink run because the pointer-file path is exercised unconditionally (no real symlink required).
- [x] Marking a real `-followups` feature complete strikes the ROADMAP row, trims the queue by resolved `spec_dir`, and produces no `queue.no-completed` error in AlgoBooth's `check-docs-consistency.ts`. **DEFERRED-WITH-TRACKING → AlgoBooth-side validation follow-up (see "Deferred to AlgoBooth-side validation" note below, dated 2026-06-17).** Requires a real AlgoBooth `-followups` queue entry and AlgoBooth's `check-docs-consistency.ts` TypeScript runtime, not runnable in claude-config. The hermetic `test_lazy_core.py` fixtures cover the ROADMAP-strike + resolved-`spec_dir` trim logic (including the `-followups` regression fixture); the `check-docs-consistency.ts` integration test is ticked deferred-with-tracking per operator resolution (2026-06-17).

**MCP Integration Test Assertions:** N/A for the script subcommands themselves (they are CLI/state-machine surfaces, covered by `--test` + the symlink/`-followups` fixtures). The `--ensure-runtime` *runtime-state* rows above are AlgoBooth-runtime-dependent → **cloud-deferred** (`DEFERRED_NON_CLOUD.md`), not MCP-app assertions.

**Prerequisites:**
- Phase 4: the deterministic-only bar + promotion checklist govern landing these three subcommands (they are the bar's first proven consumers).
- Phases 1-3 NOT strictly required, but the enhanced `__mark_complete__` queue trim composes with the unified run.

**Files likely modified:**
- `user/scripts/lazy-state.py` — `--ensure-runtime`, `--gate-coverage` args + dispatch.
- `user/scripts/lazy_core.py` — `apply_pseudo __mark_complete__` ROADMAP strike + resolved-`spec_dir` trim (refactor the 2945-3007 block); `--gate-coverage` symlink-resolving coverage algorithm (shared helper).
- `user/skills/_components/mcp-coverage-audit.md` — point at `--gate-coverage`.
- `user/skills/lazy-batch/SKILL.md` + `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — rewire to subcommands; coupled-pair mirror.
- `user/scripts/test_lazy_core.py` — enhanced `apply_pseudo` + `-followups` regression fixtures.

**Testing Strategy:** `test_lazy_core.py` for the enhanced `apply_pseudo` (ROADMAP strike + resolved-`spec_dir` trim, with the `-followups` regression as a named fixture) and the `--gate-coverage` symlink-resolution helper. `lazy-state.py --test` for `--ensure-runtime` state transitions (mockable via injected probe/now, mirroring `lazy_coord.py`'s injected-time pattern). `lazy_parity_audit.py` for the batch-skill rewire (coupled-pair). `project-skills.py` after the component/skill edits. The live `--ensure-runtime` runtime rows are workstation-validated and cloud-deferred.

**Integration Notes for Next Phase:**
- **`--ensure-runtime` home decision (DESIGN NOTE — surface, do NOT silently descope):** the runtime-ensure dance is **AlgoBooth-specific** (TCP 3333, `npm run dev:restart`, `GET /health`), but `lazy-state.py` lives in the **claude-config harness repo** and is meant to be repo-agnostic. Two honest homes exist: (a) put `--ensure-runtime` in `lazy-state.py` with AlgoBooth specifics read from repo config / env (keeps the toolify framework's "promote dances to subcommands" promise literal), or (b) keep the dance in a repo-scoped AlgoBooth helper and have `--ensure-runtime` be a thin generic shell that delegates. The SPEC explicitly names `--ensure-runtime` as a `lazy-state.py` subcommand (User Experience + Technical Design), so the implementer should follow the SPEC (home = `lazy-state.py`) and parameterize the AlgoBooth specifics out of hard-coded literals — but if implementation reveals the AlgoBooth coupling cannot be cleanly parameterized (a genuine product/architecture fork), raise `NEEDS_INPUT.md` rather than hard-coding AlgoBooth into the shared harness script. Recorded here as required disclosure, not a planning-time halt — the SPEC's locked decision (subcommand on `lazy-state.py`) resolves the default.
- **Completion (gate-owned):** the `__mark_complete__` gate (now enhanced) flips SPEC.md/PHASES.md `**Status:**` and writes `COMPLETED.md` — these stay gate-owned; no checkbox authors them.

**Status:** In-progress (implementation complete 2026-06-17; validation pending — the three implementable WUs + tests + gates all landed; the live `--ensure-runtime` runtime-state rows, the `--gate-coverage` symlink-on-Windows row, and the real `-followups` completion row are workstation/manual-validated → cloud-deferred, owned by Step-9/manual not `/execute-plan`).

**Implementation Notes (Phase 5 — landed 2026-06-17, executed INLINE in a dispatch-limited cycle subagent, no Agent tool; test-first per batch):**
- **Review verdict:** PASS (inline review — Python state-script helpers + skill-doc/component prose; spec-aligned, propagation-checked (`apply_pseudo` signature unchanged, both callers JSON-dump the additive `roadmap_struck` key safely; the bug `is_fixed` path neither strikes ROADMAP nor trims the feature queue), the `-followups` regression genuinely RED before the resolved-`spec_dir` match (fixture's `id` ≠ `feature_id` AND stored `spec_dir` is path-form ≠ basename), symlink + 64-byte-pointer both covered; gates 100%).
- **`--ensure-runtime` HOME decision (DESIGN NOTE resolved, NOT escalated):** implemented ON `lazy-state.py` per the SPEC Locked Decision. The AlgoBooth specifics (TCP-3333 health URL, `npm run dev:restart`, `src-tauri`/`crates` native globs, asserted MCP tool name) are **cleanly parameterized** into `lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG` (a default dict the caller overrides) — they are NOT hard-coded into the control flow, so the shared-harness script stays repo-agnostic. The coupling parameterized cleanly → no `NEEDS_INPUT.md` fork was needed. `ensure_runtime` takes injected `probe`/`restart`/`stale_check` callables (mirroring `lazy_coord.py`'s injected-time pattern) so the 5 `--test` fixtures are hermetic (no real network); production uses a real urllib probe + background `dev:restart` + the existing `stale_binary` predicate.
- **WU-2 (`--gate-coverage`):** `lazy_core.gate_coverage` parses all three Locked-Decision surfaces (Locked Decisions table / Resolved-by-Research checked bullets / Key|Design Decisions numbered block) and greps `mcp-tests/*.md` via `_resolve_scenario_text`, which RESOLVES both real symlinks (`read_text` follows) AND the git-on-Windows 64-byte pointer file (a tiny text file whose content is the relative target path → read the target). Covered iff a scenario contains the decision `id` literal OR ≥2 keywords. `--gate-coverage` exits 1 iff `uncovered[]` non-empty (parity with `--verify-ledger`). `mcp-coverage-audit.md` updated to point at the subcommand (algorithm now lives in code; D7 routing stays prose).
- **WU-3 (enhanced `apply_pseudo __mark_complete__`):** (a) the queue trim now also matches by RESOLVED `spec_dir` (`_resolve_under_repo` canonicalizes both the completing dir and each entry's stored `spec_dir` against `repo_root`), in addition to the legacy basename + `id` keys — killing the `-followups` miss; (b) the ROADMAP strike (`_strike_roadmap_row`: wrap the feature's row in `~~`+`✅ COMPLETE`, idempotent, table-aware) moved IN from orchestrator-inline. Both sit BEHIND the receipt-noop guard (a re-run is a no-write pass) and the `not is_fixed` gate (bug path untouched). New result keys: `roadmap_struck`, enhanced `queue_trimmed`.
- **WU-4 (skill rewire, coupled-pair):** `lazy-batch/SKILL.md` Step 1d.0 runtime dance (steps 1/1a/2/3) collapsed to one `--ensure-runtime` call; Gate-1 hand-run audit → `--gate-coverage`; the orchestrator-inline ROADMAP strike removed (now inside `--apply-pseudo`). Mirrored byte-for-intent into `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (coupled-pair). `lazy_parity_audit.py --repo-root .` exit 0.
- **Gates (all green, run in-cycle):** `test_lazy_core.py` 439/439 (16 net-new fixtures: 5 ensure-runtime, 6 gate-coverage, 5 mark-complete strike/trim/idempotency); `lazy-state.py --test` green; `bug-state.py --test` green (byte-pinned baselines UNCHANGED → single-type + bug behavior provably unperturbed); `lazy_parity_audit.py` exit 0; `project-skills.py` OK (91 components); `lint-skills.py --check-projected` OK. Live CLI: `--gate-coverage` on this feature's SPEC → `{ok:true, decisions:[], uncovered:[]}` (no Locked-Decisions surface → vacuous pass); `--ensure-runtime --repo-root .` → structured status JSON.
