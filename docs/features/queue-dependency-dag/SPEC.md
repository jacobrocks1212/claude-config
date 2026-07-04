# First-Class Dependency DAG in queue.json — Feature Specification

> Dependency knowledge today lives in prose (SPEC `**Depends on:**` blocks, ROADMAP hard-dep notes)
> and is consulted by the state machine in exactly one place — the skip-ahead branch. This feature
> makes `deps: [...]` an optional, machine-enforced queue-entry field on BOTH pipelines: an item
> whose declared dependency is not Complete is held as not-ready by `compute_state()` (the same
> readiness-predicate shape skip-ahead already uses), cycles and dangling ids are caught
> deterministically, a script-owned feeder syncs SPEC dep-blocks into the queue field so prose and
> machine state cannot silently drift, and the readiness signal becomes the foundation the
> `parallel-worktree-batch-execution` coordinator shards on. Entries without `deps` behave
> byte-identically to today.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:** (none)

> Formally no dep-block entries. Substantive dependencies are **implemented contracts**, not
> sibling specs:
> - The SPEC `**Depends on:**` block schema (`user/skills/_components/dep-block-schema.md`) and its
>   parser `parse_dep_block` (`user/scripts/lazy-state.py` ~line 1158) — the prose SSOT this
>   feature projects into the queue, never replaces.
> - `load_queue` / `load_bug_queue` (`lazy-state.py` / `bug-state.py`) — the hybrid queue loaders
>   the new field rides on, including the opt-in `autodiscover` merge.
> - The default-on dependency-aware skip-ahead (`--strict-research-halt` disables) and its
>   `independent: true` queue/frontmatter flag (`lazy_core.parse_independent_marker`,
>   `lazy_core.skip_ahead_ready`) — the existing two-key readiness predicate this feature extends.
> - Coupled-pair parity via `lazy_parity_audit.py` — the deps field and its enforcement land on
>   both state scripts and are parity-audited.

---

## Executive Summary

The lazy pipelines enforce work order by queue position alone. Dependency knowledge exists — every
SPEC carries a machine-parseable `**Depends on:**` block, and ROADMAP rows note hard-deps in prose
— but `compute_state()` only reads it inside the skip-ahead branch (`skip_ahead_ready`'s key 1),
and only *after* a gated head has already been skipped. Outside that narrow window the state
machine is dependency-blind: an operator `--reorder-queue` that moves a downstream item ahead of
its hard dep, an `--enqueue-adhoc` prepend, or a budget-guard deferral of an upstream item can all
cause the pipeline to spec, plan, and implement a feature against an upstream contract that does
not exist yet. Nothing refuses early; the failure surfaces late as rework or a realign cycle.

The fix is a first-class, optional `deps` field on queue entries (both `docs/features/queue.json`
and `docs/bugs/queue.json`), enforced at the one place the machine already decides "what is
workable" — the `compute_state()` walk loop. An item with an incomplete declared dep is
**dep-gated**: held (never dispatched), surfaced in the probe JSON, and skipped past so the walk
naturally lands on the dependency first. Completion is the existing receipt-gated predicate
(`**Status:** Complete` + `COMPLETED.md`/`FIXED.md` receipt), so enforcement is deterministic and
script-owned, never LLM-inferred. Cycle detection runs at queue load; a dangling dep id fails fast
via the same `BLOCKED.md` mechanism the host-capability axis uses for unregistered ids. A feeder
op (`--sync-deps`) projects each SPEC's hard deps into the queue field so the prose block stays
the human/design SSOT while the queue field is the enforcement projection, with a probe-time drift
diagnostic between the two.

This serves the **effective** mission criterion directly — a gate that refuses early instead of a
realign that catches late — and is the explicit prerequisite for
`parallel-worktree-batch-execution`, whose coordinator needs a mechanical, provable "these two
items are safe to work concurrently" signal. Absent-field behavior is byte-identical to today
(guarded by the `--test` baselines), keeping every other repo unaffected until it opts in.

## Design Decisions

### D1. Queue `deps` field shape: flat hard-only id list vs kind-annotated records

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** SPEC dep-blocks carry three kinds (`hard`/`soft`/`composes`). Does the queue field
  replicate kinds, or carry only what the machine enforces? The operator reads and (via CLI) edits
  this schema, and every future consumer (parallel coordinator, visualizer, LAZY_QUEUE.md) binds
  to it.
- **Options:**
  - **A — Flat hard-only list:** `"deps": ["<id>", ...]` — the field means "hard, enforced
    dependencies" by definition. Pros: minimal schema; matches the only enforcement semantics that
    exist (`skip_ahead_ready` already ignores `soft`/`composes` by design — they need the upstream
    to *exist*, not be Complete); drift detection is a set comparison; the parallel coordinator's
    readiness predicate is a set-subset check. Cons: `soft`/`composes` stay prose-only (they
    already are — no machine consumer needs them at queue level).
  - **B — Kind-annotated records:** `"deps": [{"id": "...", "kind": "hard|soft|composes"}, ...]`.
    Pros: full-fidelity mirror of the SPEC block. Cons: duplicates prose the machine never acts
    on; two representations of kinds to keep in sync; every consumer must filter to `hard` anyway;
    a larger drift surface for zero enforcement gain.
- **Recommendation:** A. The queue field is an enforcement projection, not a second copy of the
  design document. The SPEC dep-block remains the SSOT for kinds and reasons (consumed prose-side
  by `/spec-phases`, `/write-plan`, `/realign-spec` per `dep-block-schema.md`); the queue carries
  exactly the set the state machine gates on. If a future consumer needs kinds mechanically, Form
  B is an additive migration (a list of strings upgrades to a list of objects behind one parse
  helper).
- **Resolution:** RESOLVED — A (flat hard-only `"deps": ["<id>"]`). Operator-approved 2026-07-04
  — recommended option taken.

### D2. Enforcement point and dep-gate semantics in `compute_state()`

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Where in the walk loop does the not-ready predicate run, and what does "held" mean
  relative to the existing gated-head skip-ahead machinery?
- **Options:**
  - **A — Independent dep-gate `continue`, placed before the skip-ahead branch:** an item whose
    `deps` contain an incomplete id is recorded in a `dep_gated` probe list and skipped with a
    `_diag` audit line; the walk advances to the next candidate **without** requiring the
    successor to pass the two-key `skip_ahead_ready` predicate.
  - **B — Reuse the gated-head machinery:** add dep-gated ids to `gated_ids`/`_GATED_HEADS` so
    successors must pass `skip_ahead_ready` (hard-dep check + `independent: true`).
- **Recommendation:** A. The two skips have different meanings. Skip-ahead jumps *past workable
  but halted* work (research-pending/BLOCKED heads), so it demands the shared-state-isolation rail
  (`independent: true`) before letting anything leapfrog. A dep-gate is an *order correction*: the
  most common successor of a dep-gated item is its own dependency, and requiring the dependency to
  carry `independent: true` before it may be worked first would be self-defeating. Transitivity
  falls out for free — if C deps B and B deps A (A incomplete), B is incomplete-because-queued, so
  C's own check holds it; no graph traversal at dispatch time. The dep-gate also runs regardless
  of `--strict-research-halt`: that flag's documented contract is "disable skip-ahead / restore
  halt-on-first-gated-head", and the dep-gate is a correctness gate on a new opt-in field, not a
  throughput optimization — there is no legacy behavior to restore for entries that carry `deps`.
  Entries without `deps` are untouched on every path (byte-identical, baseline-guarded).
- **Resolution:** Auto-accepted A; predicate placement inside the walk loop is invisible
  implementation structure — the operator-visible behavior (held items, probe surface, terminals)
  is decided in D1/D5. Locked by operator 2026-07-04 (dep-gate `continue` before the skip-ahead
  branch; transitivity emergent; runs regardless of `--strict-research-halt`).

### D3. Dep-completion predicate: reuse receipt-gated completion

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What makes a declared dep "complete" for gating purposes?
- **Options:**
  - **A — Receipt-gated on-disk check:** a dep id is complete iff it is NOT present in the current
    merged in-memory work-list AND its dir resolves with `**Status:** Complete` plus a valid
    receipt (`lazy_core.has_completion_receipt` — `COMPLETED.md` for features, `FIXED.md` under
    `docs/bugs/_archive/<id>/` for bugs). Still-queued ⇒ incomplete, by construction.
  - **B — ROADMAP strikethrough check** (the `dep-block-schema.md` "Completion check" allows
    either). Cons: ROADMAP is a human-facing doc; the state machine treating it as truth inverts
    the "script-owned state" invariant.
- **Recommendation:** A — it reuses the exact completion definition the pipeline already enforces
  ("a `Complete` status with no receipt is a hard error"), adds zero new state, and is what
  `__mark_complete__` already produces. `Superseded` upstreams are NOT treated as complete (the
  work never happened); they route to the D5 fail-fast surface so the dependent gets operator
  attention instead of silently building on a dropped design.
- **Resolution:** Auto-accepted A; an internal predicate choice with one observable rule (receipt
  or held) that follows the existing completion-integrity contract. Locked by operator 2026-07-04
  (dep-completion = receipt-gated completion via `has_completion_receipt`; `Superseded` — and its
  bug-side analog `Won't-fix` — is NOT complete).

### D4. Graph-error surface: cycles, dangling ids, Superseded upstreams, all-gated terminal

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** What does the operator see when the declared graph is broken? Four sub-cases:
  a dependency cycle; a dep id that resolves nowhere; a dep on a `Superseded` item; and a queue
  where every remaining item is dep-gated.
- **Options:**
  - **A — Fail-fast, precedent-aligned (recommended):**
    - *Cycle* → `_die` exit 2 at queue load, naming the cycle members — consistent with the
      existing malformed-`queue.json` handling ("`queue` field must be an array" → `_die`). The
      queue is script-owned state; a cycle means the feeder or an operator CLI call produced
      corrupt machine state, and every probe should refuse loudly until it is fixed.
    - *Dangling id / Superseded upstream* → canonical `BLOCKED.md` on the DEPENDENT item
      (`blocker_kind: unknown-dependency`, body naming the offending id and the known-id set) —
      the exact `unknown-host-capability` fail-fast pattern, for the same reason: a silent hold on
      an unsatisfiable dep is infinite queue starvation.
    - *All remaining items dep-gated* → a distinct clean terminal `queue-exhausted-dependency-gated`
      in `lazy_core.SANCTIONED_STOP_TERMINAL` (the shape of `host-capability-saturated` /
      `queue-exhausted-all-parked`), with the flush naming each held item and its incomplete deps.
  - **B — Degrade-and-continue:** cycle → `_diag` + deterministically ignore the cycle-closing
    edge (the edge from the later-queued entry); dangling → `_diag` + treat as satisfied. Pros:
    one bad edit never halts the repo's whole pipeline. Cons: a typo'd dep id silently un-gates
    (the exact drift-to-silence failure the harness mission forbids); an "ignored" edge is a lie
    the operator never sees on mobile.
- **Recommendation:** A. "Gates that refuse early over reviews that catch late" is the repo's
  stated efficiency criterion, and both fail-fast shapes already exist in the codebase
  (`_die` for malformed queue JSON; `format_unknown_host_capability_blocker` for unregisterable
  ids). The blast radius concern in B is real but small: the `deps` writer is script-owned
  (`--sync-deps`, D6), so cycles/danglings indicate a feeder bug or a hand-edit — both things the
  operator wants surfaced immediately.
- **Resolution:** RESOLVED — A (cycle → `_die` exit 2 at load via Kahn's; dangling/Superseded dep
  → `BLOCKED.md` `blocker_kind: unknown-dependency` on the dependent; all-gated → new clean
  terminal `queue-exhausted-dependency-gated` in `SANCTIONED_STOP_TERMINAL`). Operator-approved
  2026-07-04 — recommended option taken.

### D5. Feeder: who writes the queue `deps` field, and how drift is detected

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** The SPEC dep-block is authored at `/spec`; the queue field must track it without
  hand-edits (HARD CONSTRAINT: `queue.json` mutations go through the state script). Who calls the
  writer, when, and what catches divergence?
- **Options:**
  - **A — `--sync-deps` op wired at `/spec-phases`, plus probe-time drift diagnostic
    (recommended):** a new orchestrator-only CLI op `lazy-state.py --sync-deps --id <id>`
    (mirrored on `bug-state.py`) parses the SPEC dep-block via `parse_dep_block`, filters to
    `hard`, and writes the id set into the queue entry via the shared load → mutate →
    `lazy_core._atomic_write` shape (`reorder_queue`/`clear_queue_stub` precedents — script-owned
    queue mutation). `/spec-phases` invokes it once the SPEC baseline is locked (deps are settled
    by then; planning is where cross-feature integration is already read per
    `dep-block-schema.md`). Drift: `compute_state()` already reads the current candidate's SPEC.md
    during the walk, so comparing its parsed hard-dep set against the queue field is one extra
    in-memory comparison — a mismatch emits a `_diag` warning naming both sets (never a halt;
    lint-grade signal).
  - **B — Sync at `__mark_complete__` reconciliation:** too late — the dependent's gate must be
    live from planning onward, and mark-complete runs on the *upstream*, not the dependent.
  - **C — Manual CLI only:** honest but guarantees drift; the field decays into the same
    prose-only state ROADMAP hard-deps are in today.
- **Recommendation:** A. It puts the write at the moment deps become load-bearing (planning),
  reuses the existing script-owned queue-mutation chokepoints, is idempotent/byte-stable on re-run
  (no-op when the sets match, like `reorder_queue`'s `noop: true`), and the drift diagnostic costs
  no new I/O. `--enqueue-adhoc` additionally accepts an optional `--deps a,b` so an ad-hoc item
  can declare deps at enqueue time without waiting for `/spec-phases`.
- **Resolution:** RESOLVED — A (`--sync-deps` CLI op on both scripts, wired at `/spec-phases` +
  probe-time drift `_diag`; `--enqueue-adhoc` gains optional `--deps a,b`). Operator-approved
  2026-07-04 — recommended option taken.

### D6. Cross-pipeline deps (feature ↔ bug): v1 or reserved for vN

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** May a feature declare a dep on a bug id (or vice versa)? The merged work-list
  (`--next-merged`) exists, so the queues already interleave for ordering.
- **Options:**
  - **A — v1 same-pipeline only, prefix syntax reserved:** a bare id resolves within the item's
    own queue/docs tree; the schema reserves `bug:<id>` / `feature:<id>` prefixes (rejected with a
    clear `_die` in v1) so v1 ids are forward-compatible and unambiguous. Pros: dep resolution
    stays inside one state script (no `importlib` seam on the gating path); the concrete
    downstream consumer (`parallel-worktree-batch-execution`) shards within one pipeline run at a
    time; no observed demand — zero cross-pipeline dep exists in prose today (checked: no SPEC
    dep-block in this repo references a bug slug). Cons: a real feature-fixes-after-bug ordering
    need would wait for vN.
  - **B — v1 with prefixes:** full generality now. Cons: the feature gate must resolve bug
    completion (`docs/bugs/_archive/<id>/FIXED.md`) via a cross-script read, and `--next-merged`'s
    "ordering only, never re-infers state" contract shows how carefully cross-queue reads are
    scoped today; building that seam for a hypothetical is speculative complexity.
- **Recommendation:** A. Same-pipeline covers the driving use case, and the reserved-prefix rule
  makes vN additive instead of a migration. The `unified-pipeline-orchestrator` merged work-list
  is the natural future home for cross-queue resolution if demand appears.
- **Resolution:** RESOLVED — A (v1 same-pipeline only; `bug:`/`feature:` prefixes reserved and
  rejected with a clear `_die`). Operator-approved 2026-07-04 — recommended option taken.

### D7. Skip-ahead integration: queue deps feed `skip_ahead_ready` key 1

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Skip-ahead currently parses the candidate's SPEC dep-block prose at probe time.
  Should the queue field also feed that predicate?
- **Options:**
  - **A — Union:** key 1 evaluates over `parse_dep_block(SPEC)` hard deps ∪ queue `deps` (queue
    ids treated as hard, per D1's field semantics). Cons: none of substance — the audit `_diag`
    line gains a `source` note per dep.
  - **B — Queue-only once synced:** simpler, but a SPEC authored before `/spec-phases` runs the
    sync would be invisible to skip-ahead (a regression vs today).
- **Recommendation:** A — strictly-additive safety; both sources are deterministic on-disk reads
  the branch already performs. The skip-ahead audit line (`gated_heads=... candidate=... deps=...`)
  extends to show the merged set.
- **Resolution:** Auto-accepted A; an internal predicate-input choice with no operator-visible
  mode. Locked by operator 2026-07-04 (skip-ahead readiness = union of SPEC hard deps ∪ queue
  deps).

### D8. `--reorder-queue` interaction: no reorder-time validation

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Must `--reorder-queue` refuse a move that puts a dependent ahead of its dep?
- **Options:**
  - **A — No validation; enforcement is probe-time:** any order is storable; the next
    `compute_state()` simply holds the dependent and works the dep first.
  - **B — Refuse dependency-violating reorders:** duplicate enforcement at a second site, and
    wrong — "dependent ahead of dep" is a legal, sometimes-intended priority statement ("work B
    the moment A completes, ahead of everything else").
- **Recommendation:** A. Probe-time enforcement makes queue order pure preference and the DAG pure
  constraint — the two compose instead of conflicting. One fixture pins it: reorder a dependent to
  head → next probe dispatches its dep, `dep_gated` names the head, nothing corrupts.
- **Resolution:** Auto-accepted A; not a product call — observable behavior is fully determined by
  D2's enforcement semantics. Locked by operator 2026-07-04 (no reorder-time validation).

### D9. Parity mirroring to `bug-state.py`

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How much of this lands on the bug pipeline?
- **Recommendation / shape:** The `deps` field, the dep-gate in the walk loop, D4's error
  surfaces, and the `--sync-deps` CLI mirror onto `bug-state.py` (the stub's "both pipelines;
  parity-guarded" constraint), with the shared predicate helpers in `lazy_core` (helper-placement
  convention) and a `lazy_parity_audit.py::audit_state_script_parity` check added. Two justified
  divergences are preserved and documented: (1) the bug pipeline has NO skip-ahead
  (`--strict-research-halt` is a parity-only arg there — `bug-state.py` ~line 631 discards it), so
  D7 is feature-only; (2) bug dep resolution must additionally look under `docs/bugs/_archive/`
  because `__mark_fixed__` archives on fix (features keep their dirs). `parse_dep_block` moves
  from `lazy-state.py` into `lazy_core.py` so both scripts share one parser (domain-agnostic
  helper placement).
- **Resolution:** Auto-accepted; the mirroring rule is the repo's standing coupled-pair
  convention, not a new product choice. Locked by operator 2026-07-04 (parity mirror to
  `bug-state.py`; `parse_dep_block` moves to `lazy_core`; the two documented divergences — no
  bug-side skip-ahead, archive-aware bug dep resolution — preserved).

### D10. Probe surface: `dep_gated` key + per-item detail

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How do orchestrators and read-only consumers see held items?
- **Recommendation / shape:** A `dep_gated` probe key — a list of
  `{id, missing: [<incomplete dep ids>]}` — emitted whenever the walk held at least one item this
  probe, mirroring the `gated_heads` / `host_deferred_features` key conventions, plus a `_diag`
  audit line per hold. Pure-read consumers (`pipeline_visualizer`, `lazy-queue-doc.py`) can then
  render a "waiting on <dep>" state without re-inferring anything; wiring those renderers is a
  follow-up, not v1 scope.
- **Resolution:** Auto-accepted; probe-key naming follows the established convention and the
  orchestrator contract is unchanged (keys are additive). Locked by operator 2026-07-04
  (`dep_gated` probe key + per-hold `_diag`).

## User Experience

The operator's day-to-day surface is three things: the queue entry, the probe output, and the
error states.

**Declaring (normally automatic via D5's feeder):**

```json
{
  "id": "parallel-worktree-batch-execution",
  "name": "Sanctioned Parallel-Worktree Batch Execution",
  "spec_dir": "parallel-worktree-batch-execution",
  "tier": 3,
  "deps": ["queue-dependency-dag"]
}
```

```bash
# Script-owned sync (invoked by /spec-phases; idempotent, byte-stable no-op when in sync):
python3 user/scripts/lazy-state.py --sync-deps --id parallel-worktree-batch-execution \
    --repo-root ~/source/repos/claude-config

# Ad-hoc enqueue with deps:
python3 user/scripts/lazy-state.py --enqueue-adhoc ... --deps queue-dependency-dag
```

**Observing a hold (probe JSON, additive keys only):**

```json
{
  "sub_skill": "spec-phases",
  "sub_skill_args": "queue-dependency-dag",
  "dep_gated": [
    {"id": "parallel-worktree-batch-execution", "missing": ["queue-dependency-dag"]}
  ],
  "diagnostics": [
    "dep-gate: 'parallel-worktree-batch-execution' held — dep 'queue-dependency-dag' not Complete (queued); advancing."
  ]
}
```

The run keeps moving — it works the dependency. When the dep completes (receipt written by
`__mark_complete__`), the next probe dispatches the dependent with no special action.

**Error states (D4, operator-approved 2026-07-04):** a cycle refuses every probe with exit 2 naming the
cycle members (fix via `--sync-deps` after correcting the SPEC blocks, or `--reorder-queue --to
remove`); a dangling/Superseded dep writes `BLOCKED.md` (`blocker_kind: unknown-dependency`) on
the dependent, entering the normal blocked-resolution flow; a fully dep-gated queue ends the run
with the clean `queue-exhausted-dependency-gated` terminal and a flush listing each held item.

## Technical Design

```
SPEC.md **Depends on:** block ──/spec-phases──▶ lazy-state.py --sync-deps ──_atomic_write──▶ queue.json deps:[...]
        (prose SSOT: kinds+reasons)                    (hard ids only, idempotent)                  │
                                                                                                    ▼
                             compute_state() walk loop:  completion/park/budget skips
                                        → DEP-GATE (new): all deps Complete+receipt? ──no──▶ hold, _diag,
                                        → skip-ahead branch (unchanged; key 1 now       dep_gated[] += item
                                          reads queue deps ∪ SPEC hard deps)
                                        → dispatch
```

- **Loader (`load_queue` / `load_bug_queue`).** Accept the optional `deps` array (list of strings
  matching `^[a-z0-9][a-z0-9-]*$`, the dep-block id regex); malformed shapes `_die` exit 2 like
  other queue-schema violations. Cycle detection (D4) runs once per load over queued entries'
  `deps` edges (Kahn's algorithm over ≤ tens of nodes — negligible). Autodiscovered entries
  (claude-config's `"autodiscover": true` merge) carry no queue `deps` by construction; their SPEC
  prose still feeds skip-ahead via D7, and `--sync-deps` after `/spec-phases` writes the field
  when the item is (or becomes) a queue entry.
- **Predicate helpers (in `lazy_core.py`, shared).** `dep_ids(queue_entry)` (shape-tolerant read),
  `dep_is_complete(dep_id, repo_root, *, pipeline)` (D3 receipt-gated check; bug pipeline also
  consults `docs/bugs/_archive/`), `detect_dep_cycle(entries)`. `parse_dep_block` moves to
  `lazy_core` (D9). All queue writes go through `lazy_core._atomic_write`; all breadcrumbs through
  `lazy_core._diag` — never `print()`.
- **Enforcement (`compute_state()`, both scripts).** The dep-gate `continue` sits after the
  completion/cloud/device/park/budget skips and before the skip-ahead branch (`lazy-state.py`
  ~line 2254 region), per D2. It runs regardless of `--strict-research-halt` and is a no-op for
  entries without `deps` (byte-identity guarded by the pinned `--test` baselines in
  `tests/baselines/`).
- **Feeder (`--sync-deps`).** Orchestrator-only (`refuse_if_cycle_active("--sync-deps")` first,
  exit 3 for a cycle subagent — the `--reorder-queue`/`--enqueue-adhoc` contract), load → parse
  SPEC → filter hard → mutate entry → `_atomic_write`; `noop: true` when already in sync. Present
  on both scripts (coupled pair).
- **House invariants honored:** script-owned deterministic state (the gate reads only on-disk
  receipts/status — no LLM judgment); atomic writes; per-repo keyed state untouched (this feature
  adds no run-scoped state); coupled-pair parity (D9, parity-audited); read-only consumers stay
  read-only (probe key only); receipt-gated completion is *reused* as the readiness oracle, not
  duplicated.

## Implementation Phases

- **Phase 1 — Schema + loader + graph validation.** `deps` accepted by both loaders; shared
  `lazy_core` helpers (`dep_ids`, `detect_dep_cycle`, relocated `parse_dep_block`); cycle `_die`;
  malformed-shape `_die`; `--test` fixtures incl. byte-identity baseline re-pin (no-deps queues
  produce identical output). Proves: loading, validation, zero regression.
- **Phase 2 — Dep-gate enforcement.** The walk-loop hold in both `compute_state()`s; `dep_gated`
  probe key + `_diag` audit; `queue-exhausted-dependency-gated` terminal; dangling/Superseded
  `BLOCKED.md` fail-fast; transitive-hold and completion-unlock fixtures. Proves: an out-of-order
  queue is corrected, never dispatched wrong.
- **Phase 3 — Skip-ahead integration.** `skip_ahead_ready` key 1 consumes queue deps ∪ SPEC hard
  deps; audit-line extension; fixtures extending the existing `feat-sa-*` skip-ahead suite
  (`lazy-state.py` ~line 7100). Feature-pipeline only (justified divergence, documented).
- **Phase 4 — Feeder + drift.** `--sync-deps` on both scripts (cycle-guarded, idempotent);
  `--enqueue-adhoc --deps`; `/spec-phases` wiring (skill prose + `adhoc-enqueue.md` component
  touch); probe-time drift `_diag`. Proves: prose→queue projection is script-owned and byte-stable.
- **Phase 5 — Parity + docs.** `lazy_parity_audit.py` check for the new CLI/enforcement surface;
  `user/scripts/CLAUDE.md` + root `CLAUDE.md` + `docs/features/CLAUDE.md` schema notes;
  `dep-block-schema.md` gains a "queue projection" paragraph. Full gate: `lazy-state.py --test`,
  `bug-state.py --test`, `test_lazy_core.py`, parity audit.

Estimate: ~3 sessions (Phases 1–2 one, 3–4 one, 5 folds into the second or a short third).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Byte-identity without `deps` | Full `--test` on both scripts, no fixture carries `deps` | Output matches pinned baselines | `tests/baselines/*.txt` via `_normalize_smoke_output` |
| Dep-gated hold + advance | Queue: B(`deps:[A]`) ahead of A, A not Complete | B held, A dispatched, `dep_gated` names B/missing A | Probe JSON fixture |
| Transitive hold | C→B→A chain, A incomplete | B and C both held, no traversal special-case | Probe JSON fixture |
| Completion unlock | A flips Complete + `COMPLETED.md` | Next probe dispatches B normally | Fixture after receipt write |
| Cycle refusal | A↔B cycle in `deps` | Exit 2, message names cycle members | CLI exit + stderr |
| Dangling/Superseded fail-fast | B `deps` a nonexistent / Superseded id | `BLOCKED.md` with `blocker_kind: unknown-dependency` on B | On-disk sentinel + fixture |
| All-gated clean terminal | Only dep-gated items remain | `queue-exhausted-dependency-gated`, flush lists holds | Probe JSON terminal |
| Reorder composes | `--reorder-queue` dependent to head | Next probe holds it; queue file valid | Fixture + `queue.json` diff |
| Feeder idempotent | `--sync-deps` twice on synced entry | Second run `noop: true`, file byte-identical | CLI JSON + file hash |
| Drift diagnostic | Queue deps ≠ SPEC hard deps for current candidate | `_diag` warning naming both sets, no halt | Probe `diagnostics` |
| Cycle-subagent refusal | `--sync-deps` under cycle marker, no orchestrator env | Exit 3, zero side effects | CLI fixture |
| Parity | Same fixtures on `bug-state.py` (archive-aware resolution) | Both suites + `lazy_parity_audit.py` green | Test run |

## Open Questions

None remaining — every open decision (D1, D4, D5, D6) was operator-approved 2026-07-04 at its
recommended option, and the auto-accepted decisions (D2, D3, D7, D8, D9, D10) were locked at the
same review. See each decision's **Resolution** line above.

- **Deferred empirical checks (implementation-time, not decisions):** confirm relocating
  `parse_dep_block` to `lazy_core` keeps both pinned `--test` baselines green; count live SPEC
  dep-blocks across lazy-enabled repos to size the initial `--sync-deps` backfill (estimated —
  verify during Phase 4); confirm the walk loop's existing SPEC read for the current candidate is
  reusable for the drift check without a second file read.

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: the in-repo skip-ahead predicate + host-capability
  fail-fast precedents; build-system dependency semantics (Make/Bazel-style "constraint, not
  order") for the D8 order-vs-constraint separation.
- `user/skills/_components/dep-block-schema.md` — the prose schema this feature projects.
- `docs/features/mobile-queue-control/SPEC.md` — the implemented-contracts dep-block convention
  and pure-read consumer pattern (`dep_gated` rendering follow-up).
- `docs/features/parallel-worktree-batch-execution/SPEC.md` — the downstream consumer whose
  readiness predicate this feature supplies.
