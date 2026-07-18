# Bug: First `/lazy-batch-parallel` run surfaced seven harness gaps (lease-blind merged-head withhold, self-locking claim snippet, missing `--set-independent`, lane run-end gate refusals, grouped/multi-feature containment misparse)

**Status:** Concluded
**Reported via:** `/harden-harness` discovered-defect-batch dispatch (2026-07-18, item in flight `parallel-run-harness-gaps`, AlgoBooth first `/lazy-batch-parallel` run, parent marker `2026-07-18T03:38:27Z`, blocking=true). Gap 1 is run-blocking (lanes wt-01/wt-02 withheld).
**Root-cause class:** batch — `script-defect` (gaps 1, 4, 5, 6), `ambiguous-prose` (gap 2), `missing-contract` (gaps 3, 7).
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage); `user/skills/lazy-batch-parallel/SKILL.md` (the parallel coordinator contract); the concluded bug `docs/bugs/lazy-cycle-containment-misparses-grouped-feature-paths` (gap 6 is a regression class of it); `docs/bugs/dispatch-probe-and-inject-bypass-merged-head` (gap 1 touches the guard that bug introduced).

## Context

The first real `/lazy-batch-parallel` run sharded three independent feature items across worktree
lanes on `main`-based branches. Seven distinct harness defects surfaced, all in
`claude-config` scripts/skills/hooks. They are batched here because they were discovered in one
run and share the parallel-coordinator surface; each has its own verified symptom, root cause,
and fix scope below. Gap 1 stalled two lanes (run-blocking); the rest are correctness/contract
gaps that either refuse legitimate lane lifecycle operations or force a never-hand-edit contract
violation.

---

## Gap 1 — merged-head override is lease-blind / lane-blind (RUN-BLOCKING)

**Symptom (verified).** For every `/lazy-batch-parallel` lane whose assigned `--feature-id` is
not the global merged worklist head, the dispatch-bound `--emit-prompt` probe returns
`route_overridden_by: merged-head-diverged` and WITHHOLDS the forward route — so lanes 2..N can
never emit their registered cycle prompts. Live probe JSON (lane wt-01):
`{"route_overridden_by": "merged-head-diverged", "merged_head": {"item_id": "hydra-overlay",
"type": "feature"}, "lanes_withheld": ["polyphonic-parameter-modulation",
"managed-llm-credits"]}`. `hydra-overlay` was the queue head, held serial (not sharded, so it
holds no lease); the two lanes worked lower-priority independent items and were withheld behind
it.

**Root cause (`script-defect`).** `lazy_core.dispatch.merged_head_override` (`user/scripts/
lazy_core/dispatch.py:358`) is a SERIAL-run priority-inversion guard: it withholds when the
merged head differs from the item the per-pipeline probe would emit for. In a parallel run the
premise ("only one item is active and it must be the global head") is void BY DESIGN — the
coordinator's `claim_shardable` already applied the queue-order + `independent:true` + lease
arbitration when it assigned the lane its `--feature-id`. The emit path
(`user/scripts/lazy-state.py:13751-13816`) runs the override whenever a run marker is present,
with no awareness that a **lane marker** (`parent_run` set) is a coordinator-authorized child.
The evidence's alternative remedy — also excluding LIVE-leased items from the merged-head
exclusion set — is INSUFFICIENT: the divergent head here (`hydra-overlay`) is a serial-held item
that holds **no** lease, so lease-exclusion would not remove it and the withhold would persist.

**Fix scope.** Exempt the lane probe form: when the emit-path run marker carries a non-null
`parent_run` (a coordinator-armed lane marker), skip `merged_head_override` entirely (leave
`_merged_override = None`) with a diagnostic. Serial runs (`parent_run: null`) stay
byte-identical. Mirror into `bug-state.py`'s twin emit block (coupled pair) for parity.

---

## Gap 2 — Step 1 canonical claim snippet self-deadlocks

**Symptom (verified).** `lazy-batch-parallel/SKILL.md` Step 1's canonical claim snippet wraps
`lazy_coord.reclaim_expired(...)` + `lazy_coord.claim_shardable(...)` inside
`lazy_coord.acquire_lock(lock)` / `release_lock(lock)`, and the prose (line 192) says to take
`acquire_lease(...)` "under the same lock hold." `acquire_lease`
(`user/scripts/lazy_coord.py:540`) and `reclaim_expired` (`:645`) each call `acquire_lock`
INTERNALLY on the same `global.lock.d`. The lock is a non-reentrant `os.mkdir` directory lock —
the inner `mkdir` fails (dir exists, held by this live process → not stale → not reclaimed),
backs off, and raises `TimeoutError` after 10s. The claim step cannot complete.

**Root cause (`ambiguous-prose` / documented-snippet defect).** The snippet treats the
primitives as lock-free helpers to be composed under one outer lock, but `reclaim_expired` and
`acquire_lease` are self-locking; only `claim_shardable` is lock-free (READ-ONLY,
`user/scripts/lazy_coord.py:862`). The primitives are individually atomic and tolerate
interleaving (`acquire_lease` re-checks liveness under its own lock and returns `None` on a
double-claim), so the outer lock is both wrong and unnecessary.

**Fix scope.** Drop the outer `acquire_lock`/`release_lock` wrapper in the Step 1 snippet; call
`reclaim_expired` → `claim_shardable` → per-item `acquire_lease` directly (each self-locks).
Fix the line-192 prose to stop asserting "under the same lock hold." Prose-only; no
`lazy_coord.py` behavior change. No bug-side mirror (there is no `lazy-bug-batch-parallel`
skill — parallel mode is feature-only v1).

---

## Gap 3 — no sanctioned mutator for the `independent:true` marker

**Symptom (verified).** Setting or clearing a queue item's `independent: true` shard-eligibility
marker requires hand-editing `queue.json`, which violates the never-hand-edit-queue contract
(the same contract `--set-tier` / `--add-deps` / `--reorder-queue` exist to satisfy). There is
no CLI path.

**Root cause (`missing-contract`).** `parse_independent_marker`
(`user/scripts/lazy_core/docmodel.py:2707`) READS the marker from either the SPEC frontmatter or
the queue entry, but no mutator WRITES it. `--set-tier` (`lazy-state.py:13398`, backed by
`depdag.set_queue_priority`) is the exact analog for the `tier` field.

**Fix scope.** Add `lazy_core.set_independent_marker` (a queue-entry mutator in `depdag.py`, sib
of `mutate_queue_deps` — no repositioning, since `independent` is an isolation marker, not a
priority) and a cycle-guarded `--set-independent <id> <true|false> --operator-authorized` CLI in
`lazy-state.py`, modeled on `--set-tier` (refuse-if-cycle-active FIRST, then require
`--operator-authorized`). Feature-only (bugs are not sharded in v1) — parallels `--set-tier`'s
feature-only surface, so no bug-side CLI mirror.

---

## Gap 4 — lane `--run-end` park terminals are refused as non-sanctioned

**Symptom (verified).** P6 lane retirement on a needs-input/blocked park does
`--run-end --reason terminal --terminal-reason <reason>`; a `--feature-id`-scoped lane probe
emits the SCOPED park terminals (`needs-input-scoped` / `blocked-scoped`). Neither those nor
their bare forms are in `lazy_core.SANCTIONED_STOP_TERMINAL` (`markers.py:650`), so the
terminal-reason gate (`lazy-state.py:12885`) REFUSES the lane retirement unless
`--operator-authorized` is passed — but P6 park is the parallel mode's DEFINING failure
isolation (SKILL P6), not an operator exception.

**Root cause (`script-defect`).** The terminal-reason gate has no awareness that a lane marker
(`parent_run` set) may legitimately retire on a park-class terminal. The sanctioned set is
correctly serial-scoped (a serial run parking would be a real halt needing authorization), but a
lane child is coordinator-managed.

**Fix scope.** Add a lane-scoped `SANCTIONED_LANE_PARK_TERMINAL` frozenset in `markers.py`
(`needs-input`, `needs-input-scoped`, `blocked`, `blocked-scoped`, `needs-ratification`,
`needs-ratification-scoped`, `budget-deferred`). In the terminal-reason gate, when the marker's
`parent_run` is non-null AND the reason is in that set, sanction it without
`--operator-authorized`. Mirror into `bug-state.py` (coupled pair). Serial runs unchanged.

---

## Gap 5 — per-lane `--run-end` demands the efficacy/canary/incident trio

**Symptom (verified).** The efficacy-coverage gate (`lazy-state.py:12781`) refuses `--run-end`
(exit 1, marker kept) unless the end-of-run efficacy/canary/incident trio dropped its breadcrumb.
For a parallel run this fires on EVERY lane marker's `--run-end` (P6 park, MCP-gate stop), but
the trio is owed ONCE by the PARENT marker at the coordinator flush (SKILL Step 6.3), not per
lane. Lanes cannot flush the trio (they retire before the coordinator's serial tail).

**Root cause (`script-defect`).** The efficacy gate treats every `--run-end` as a top-level run
boundary. A lane marker (`parent_run` set) is a child retirement — the parent owes the trio.

**Fix scope.** In the efficacy gate, skip the check when the marker's `parent_run` is non-null
(the parent coordinator owes the trio at its own flush). Mirror into `bug-state.py`. The parent
`--run-end` (`parent_run: null`) still owes it — byte-identical for serial.

---

## Gap 6 — containment second-feature tripwire misparses deep grouped spec dirs

**Symptom (verified).** `_path_under_feature` in `lazy-cycle-containment.sh` (`:434`) anchors the
feature slug with `docs/(?:features|bugs)/(?:[^/]+/)?<slug>/` — AT MOST ONE grouping segment
before the slug. A path with a multi-level group like
`docs/features/ui/secondary-ui-v2/domains/<slug>/` (three segments before the slug) does not
match, so a legitimate same-feature commit is denied as a second-feature commit.

**Root cause (`script-defect`, regression class).** This is the concluded bug
`lazy-cycle-containment-misparses-grouped-feature-paths` recurring for DEEPER grouping. The prior
fix generalized single-level grouping (`(?:[^/]+/)?`) and explicitly scoped multi-level out ("the
queue does not produce it") — but the queue now does.

**Fix scope.** Change the optional single group segment `(?:[^/]+/)?` to zero-or-more
`(?:[^/]+/)*` so the slug is anchored as a full segment at ANY grouping depth. Update the
docstring (multi-level grouping is now in scope). Add a `test_hooks.py` regression case for a
3-segment grouped path.

---

## Gap 7 — cycle marker is single-`feature_id`; ingest-research batch spans N features

**Symptom (verified).** `/ingest-research` runs in batch mode and writes `RESEARCH.md` across N
features in one commit, but the cycle it is bracketed under carries a single `feature_id`. The
second-feature tripwire (`lazy-cycle-containment.sh:744`) then denies the ingest cycle's own
commit for the 2nd/3rd features' `docs/features/<slug>/` paths.

**Root cause (`missing-contract`).** The tripwire polices a runaway cycle wandering into a
DIFFERENT feature than its dispatch. `/ingest-research` is a SANCTIONED batch docs-writer whose
entire job is to write `RESEARCH.md` / `RESEARCH_SUMMARY.md` and clear stub markers across all
pending-research features — legitimately multi-feature, and it only touches
`docs/features/<slug>/` research artifacts (never source). No contract recognizes a sanctioned
batch cycle.

**Fix scope.** Exempt the `ingest-research` sub_skill from the second-feature tripwire, keyed on
the cycle marker's `sub_skill` field (already set by the `--cycle-begin --sub-skill
ingest-research` bracket — zero orchestrator change). Keep the commit-count backstop. This is the
smallest fix that closes the reproduced symptom without forcing the orchestrator to pre-enumerate
the batch's feature ids. (A general `feature_ids` marker-list schema is the broader
generalization; deferred unless a second non-ingest batch cycle recurs — first occurrence, no
spin-off.)

---

## Verification

All symptoms reproduced from the live run state (withheld probes at `AlgoBooth-lanes/wt-01` +
`wt-02` for gap 1; the denied ingest commit reconciled by the coordinator at the main root for
gap 7) and from direct reading of the cited script lines. Fix scopes are contained to the named
files plus their coupled `bug-state.py` twins (gaps 1/4/5) and hook/skill/test additions.
