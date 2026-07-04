# Implementation Phases — First-Class Dependency DAG in queue.json

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete
<!-- All 5 phases implemented + validated 2026-07-04 (pytest 1217 passed / 2 sanctioned skips;
     both --test smoke suites green against re-pinned additive-only baselines; parity audit
     exit 0 with the new --sync-deps surface; lint-skills clean). NOT Complete on the SPEC —
     the __mark_complete__ integrity gate owns the SPEC Complete flip + COMPLETED.md receipt. -->

**MCP runtime:** not-required — pure claude-config harness mechanics (Python state scripts +
shared `lazy_core` helpers + docs/skill prose). No Tauri app, no MCP-reachable surface; validation
is `pytest` on `test_lazy_core.py`/`test_lazy_parity.py`, the `lazy-state.py --test` /
`bug-state.py --test` smoke baselines, `lazy_parity_audit.py`, and `lint-skills.py`. This is the
`standalone — no app integration` untestable class → `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** (none)` — substantive dependencies are implemented contracts, not sibling specs
(see the SPEC's dep-block note). Contracts consumed:

- **`dep-block-schema.md` + `parse_dep_block` (`lazy-state.py:1168`):** the prose SSOT this
  feature projects into the queue. The parser MOVES to `lazy_core.py` (D9) with a re-export in
  `lazy-state.py` so Step 4.6 and the skip-ahead branch are untouched.
- **`load_queue` / `load_bug_queue`:** the new `deps` field rides the existing hybrid loaders;
  autodiscovered entries carry no queue deps by construction.
- **Skip-ahead (`lazy_core.skip_ahead_ready`, `lazy-state.py:2243–2325`):** key 1 gains the queue
  deps ∪ SPEC hard deps union (D7); the predicate helper itself is unchanged (caller-side input).
- **Coupled-pair parity (`lazy_parity_audit.py::audit_state_script_parity`):** `--sync-deps`
  becomes the SIXTH audited surface; `test_lazy_parity.py`'s surface-enumerating stubs update in
  lockstep.
- **Sibling-lane merge hygiene (harness-telemetry-ledger touches the same CLI handlers):**
  `compute_state` edits are one contiguous dep-gate block per script; new argparse flags append
  after existing operator-op groups; all fixtures use `feat-dg-*` / `bug-dg-*` ids and their own
  temp roots.
- **Downstream consumer:** `parallel-worktree-batch-execution` reads the `dep_gated` probe key +
  the enforced `deps` field as its readiness predicate — additive keys only, no contract change
  owed here.

---

### Phase 1: Schema + loader + graph validation

**Phase kind:** design

**Scope:** The optional `deps` queue-entry field accepted (and validated) by both loaders; shared
`lazy_core` helpers (`dep_ids`, `detect_dep_cycle`, `validate_queue_deps`, relocated
`parse_dep_block`); cycle → `_die` exit 2 at load; malformed shape / bad id / reserved
`bug:`/`feature:` prefix → `_die` exit 2; byte-identity for dep-less queues.

**Deliverables:**
- [x] `lazy_core.py`: `parse_dep_block` relocated verbatim from `lazy-state.py` (module-level
  `_DEP_BLOCK_ID_RE`); `lazy-state.py` re-exports it (`parse_dep_block = lazy_core.parse_dep_block`)
  so Step 4.6 / skip-ahead callers are unchanged.
- [x] `lazy_core.py`: `dep_ids(queue_entry)` — shape-tolerant read of the optional `deps` field
  (non-dict entry / absent / non-list → `[]`; non-string members dropped).
- [x] `lazy_core.py`: `detect_dep_cycle(entries)` — Kahn's algorithm over queued entries' dep
  edges (edges only between queued ids); returns the sorted cycle-member id list or `None`.
- [x] `lazy_core.py`: `validate_queue_deps(items, queue_path, *, queue_label)` — `_die` exit 2 on:
  `deps` not a list; a non-string / regex-violating id; a reserved `bug:`/`feature:` prefix
  (named as reserved-for-vN in the message, D6); a cycle (naming members, D4).
- [x] `load_queue` (`lazy-state.py`) and `load_bug_queue` (`bug-state.py`) call
  `validate_queue_deps` over the raw queue items before any merge.
- [x] pytest tests in `test_lazy_core.py` (registered in `_TESTS`): parse_dep_block relocation
  behavior; dep_ids shapes; cycle detection (none / 2-cycle / self-loop / chain);
  validate_queue_deps die-cases + clean pass.

**Minimum Verifiable Behavior:** A queue.json whose entries carry valid `deps` loads exactly as
before with the field preserved; `"deps": "x"` (non-list), `"deps": ["Bad_Id"]`,
`"deps": ["bug:x"]`, and an A↔B cycle each exit 2 with a message naming the defect; a queue
without `deps` produces byte-identical `--test` output (baselines untouched this phase).

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Byte-identity without `deps`: both `--test` baselines green with zero diff this phase. *(Evidence: `SKIP_MCP_TEST.md` — baseline tests green, no Phase-1 re-pin.)*
<!-- verification-only -->
- [x] Cycle refusal: A↔B `deps` cycle → exit 2 naming both members. *(Evidence: `test_lazy_core.py` validate_queue_deps cases.)*
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`,
`user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`.

**Testing Strategy:** Pure-function pytest for the helpers (hermetic tmp queue files);
`SystemExit`-capturing die-cases; both smoke suites re-run to prove zero baseline drift.

**Integration Notes for Next Phase:** Phase 2's walk-loop gate consumes `dep_ids` +
`dep_completion_status` (added in Phase 2 — it needs the walk's pipeline context to define
archive-aware resolution) and relies on load-time validation having already excluded
cycles/malformed shapes, so the gate never re-validates.

---

### Phase 2: Dep-gate enforcement

**Phase kind:** design

**Scope:** The dep-gate hold in both `compute_state()` walk loops (D2-A placement: after the
completion/cloud/device/host/research/park/budget skips, before the feature skip-ahead branch /
before bug dispatch); `dep_gated` probe key + per-hold `_diag` (D10); the
`queue-exhausted-dependency-gated` clean terminal (D4); dangling/Superseded (bug: Won't-fix)
`BLOCKED.md` fail-fast (`blocker_kind: unknown-dependency`); transitive-hold and
completion-unlock behavior.

**Deliverables:**
- [x] `lazy_core.py`: `dep_completion_status(dep_id, repo_root, *, pipeline, id_dir_map=None)` →
  `complete | incomplete | unsatisfiable-superseded | unsatisfiable-wont-fix | missing`.
  Feature: `docs/features/<id>/` (queue `spec_dir` hint honored), Complete + valid `COMPLETED.md`
  ⇒ complete; Superseded ⇒ unsatisfiable. Bug: `docs/bugs/<id>/` THEN `docs/bugs/_archive/<id>/`
  (D9 divergence 2), Fixed + valid `FIXED.md` ⇒ complete; Won't-fix ⇒ unsatisfiable. No dir
  anywhere ⇒ missing.
- [x] `lazy_core.py`: `format_unknown_dependency_blocker(item_id, dep_id, status, known_ids)` —
  BLOCKED.md body naming the offending id, why it is unsatisfiable, and the known queued-id set
  (the `format_unknown_host_capability_blocker` shape).
- [x] `lazy_core.py`: `queue-exhausted-dependency-gated` added to `SANCTIONED_STOP_TERMINAL`.
- [x] `lazy-state.py`: `_DEP_GATED` module global (reset per `compute_state`); dep-gate block in
  the walk loop (gated on `dep_ids(entry)` non-empty; runs regardless of
  `--strict-research-halt`); `dep_gated` key in `_state()` ONLY when non-empty; terminal fires
  when the walk exhausts with holds (placed after scoped-id, before all-parked), flush naming each
  held item + its missing deps.
- [x] `bug-state.py`: mirrored `_DEP_GATED` + dep-gate (reading `entry["queue_entry"]`) +
  `dep_gated` key in `_bug_state()` + terminal (same precedence slot).
- [x] Smoke fixtures (both scripts, baselines re-pinned via `_normalize_smoke_output`):
  hold+advance (B `deps:[A]` ahead of A → A dispatched, `dep_gated` names B); transitive
  (C→B→A, B and C held); completion unlock (receipt written → next probe dispatches dependent);
  dangling dep → BLOCKED.md `unknown-dependency` + `terminal_reason=blocked`; Superseded
  (feature) / Won't-fix (bug) dep → same fail-fast; all-gated →
  `queue-exhausted-dependency-gated`; reorder-composes (dependent moved to head via
  `reorder_queue` → next probe still holds it, queue file valid).

**Minimum Verifiable Behavior:** Queue `[B(deps:[A]), A]` with A incomplete: probe dispatches A,
`dep_gated == [{"id": "B", "missing": ["A"]}]`, diagnostics carry the hold line; after A gains
`**Status:** Complete` + `COMPLETED.md`, the next probe dispatches B with no special action.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Dep-gated hold + advance, transitive hold, completion unlock, both fail-fast variants, the
  all-gated terminal, and reorder-composes each pinned by a smoke fixture on BOTH scripts.
  *(Evidence: `SKIP_MCP_TEST.md` — `--test` suites green against re-pinned baselines.)*
<!-- verification-only -->
- [x] Entries without `deps` remain byte-identical on every path (all pre-existing fixture lines
  in both baselines unchanged; diff is purely additive new-fixture lines). *(Evidence: baseline
  re-pin diff inspection.)*
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phase 1 (validated field + helpers).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`,
`user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`,
`user/scripts/tests/baselines/lazy-state-test-baseline.txt`,
`user/scripts/tests/baselines/bug-state-test-baseline.txt`.

**Testing Strategy:** Smoke fixtures are the primary pin (probe JSON assertions inside
`run_smoke_tests`); `dep_completion_status` + blocker formatter get direct pytest coverage
(archive-aware bug resolution, receipt-gated feature completion, Superseded/Won't-fix routing).

**Integration Notes for Next Phase:** Phase 3 reuses the same fixtures' dep shapes; the skip-ahead
branch sits immediately after the dep-gate `continue`, so a dep-gated item never registers as a
gated head (hold wins) — the Phase-3 union only affects candidates evaluated AFTER a
research/BLOCKED gated head was skipped.

---

### Phase 3: Skip-ahead integration (feature pipeline only)

**Phase kind:** integration

**Scope:** `skip_ahead_ready` key 1 evaluates over SPEC hard deps ∪ queue `deps` (queue ids
treated as hard, D7/D1); the skip-ahead audit `_diag` line shows the merged set with a per-dep
source note. Feature-pipeline only — the bug pipeline has no skip-ahead (D9 divergence 1,
documented; no bug-side mirror).

**Deliverables:**
- [x] `lazy-state.py` skip-ahead readiness evaluation: merge
  `parse_dep_block(SPEC)` + `[{feature_id, kind: "hard", source: "queue"} for id in dep_ids(entry)]`
  before calling `lazy_core.skip_ahead_ready` (helper unchanged — extra keys ignored).
- [x] Audit line extension: each dep rendered with its `source` (`spec` | `queue`).
- [x] Smoke fixture extending the `feat-sa-*` suite: the merge seam (`_merged_skip_ahead_deps`)
  pinned directly (SPEC dep source=spec, queue dep source=queue, dedup, key-1 union verdict), PLUS
  the end-to-end contract — a queue-deps-only candidate is NOT dispatched past the gated head
  (the Phase-2 dep-gate holds it first; the union is the defense-in-depth second layer);
  baseline re-pinned.

**Minimum Verifiable Behavior:** With gated head H and candidate C (`independent: true`, SPEC
`**Depends on:** (none)`, queue `deps: ["H"]`), default skip-ahead does NOT dispatch C; the audit
diag shows the merged dep with `source=queue`.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Queue-deps-only downstream candidate never dispatched past the gated head (held by the
  dep-gate; union verdict pinned at the merge seam); pre-existing `feat-sa-*` fixture outcomes
  unchanged. *(Evidence: `SKIP_MCP_TEST.md` — `--test` green against re-pinned
  baseline.)*
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phases 1–2.

**Files likely modified:** `user/scripts/lazy-state.py`,
`user/scripts/tests/baselines/lazy-state-test-baseline.txt`.

**Testing Strategy:** Extend the existing `feat-sa-*` smoke section in place (same fixture style);
no `lazy_core` change ⇒ no new pytest surface beyond the smoke pin.

**Integration Notes for Next Phase:** Phase 4's `--sync-deps` writes the queue field this union
reads, closing the loop: a SPEC authored before sync is still visible to skip-ahead (SPEC side of
the union), and a synced queue field is visible even if the SPEC block is later edited (drift
diag flags the divergence).

---

### Phase 4: Feeder + drift

**Phase kind:** integration

**Scope:** `--sync-deps` on both scripts (cycle-guarded, idempotent, byte-stable no-op);
`--enqueue-adhoc --deps a,b` on both scripts (+ pass-through on the `--type bug` delegation);
probe-time drift `_diag` (gated on the entry carrying a `deps` key); `/spec-phases` skill prose +
`adhoc-enqueue.md` component wiring.

**Deliverables:**
- [x] `lazy_core.py`: `validate_dep_id_list(dep_ids, ...)` (shared by sync/enqueue: regex +
  reserved-prefix `_die`) and `sync_deps(queue_path, item_id, docs_dir, *, queue_label)` — load →
  find entry (missing id → `_die`) → resolve `spec_dir` → `parse_dep_block(SPEC.md)` (missing
  SPEC.md → `_die`) → filter `hard` → dedupe (SPEC order) → write via `_atomic_write`; equal sets
  → `noop: true`, zero write; empty hard-set removes the `deps` key (restores the
  byte-identical no-deps state).
- [x] `lazy-state.py --sync-deps --id <id>`: `refuse_if_cycle_active("--sync-deps")` FIRST
  (exit 3, zero side effects for a cycle subagent), then `sync_deps` against
  `docs/features/queue.json`.
- [x] `bug-state.py --sync-deps --id <id>`: coupled-pair mirror against `docs/bugs/queue.json`.
- [x] `--enqueue-adhoc --deps a,b`: comma-split + validated; stored on the prepended entry (key
  absent when flag omitted — byte-identical); `lazy-state.py --type bug` forwards `--deps` to the
  `bug-state.py` subprocess.
- [x] Probe-time drift `_diag` in both walk loops: when the raw entry HAS a `deps` key, compare
  it (as a set) against the SPEC's parsed hard-dep set (reusing the walk's existing SPEC read);
  mismatch → warning naming both sets; never a halt. Entries without the key: zero new output.
- [x] `user/skills/spec-phases/SKILL.md`: post-baseline step invoking
  `lazy-state.py --sync-deps --id <feature-id>` (bug variant noted).
- [x] `user/skills/_components/adhoc-enqueue.md`: optional `--deps a,b` documented on both
  command forms.
- [x] Lane-local projection + lint after the skill/component edits (`project-skills.py
  --output-dir /tmp/proj-queue-dependency-dag`; `lint-skills.py`).
- [x] Smoke fixtures: sync writes-then-noop (second run `noop: true`, file byte-identical by
  hash); drift diag fires on mismatch and stays silent without the `deps` key; enqueue `--deps`
  lands on the entry; cycle-subagent `--sync-deps` refusal (subprocess, exit 3, zero side
  effects). Baselines re-pinned.

**Minimum Verifiable Behavior:** `--sync-deps --id X` on an entry whose SPEC declares one hard dep
writes `"deps": ["<dep>"]`; a second identical run returns `noop: true` with a byte-identical
file; a probe over an entry whose queue deps ≠ SPEC hard deps emits the drift diagnostic and
still routes normally.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Feeder idempotent (write → noop, file hash equal), drift diagnostic (fires on mismatch,
  silent when key absent), cycle-subagent exit-3 refusal with zero side effects — each pinned by
  a smoke fixture on the owning script(s). *(Evidence: `SKIP_MCP_TEST.md` — `--test` suites
  green.)*
<!-- verification-only -->
- [x] Skill projection + lint clean after the prose edits. *(Evidence: `SKIP_MCP_TEST.md` —
  `project-skills.py` lane-local run + `lint-skills.py` exit 0.)*
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phases 1–2 (field + gate live before the feeder writes it).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`,
`user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`,
`user/skills/spec-phases/SKILL.md`, `user/skills/_components/adhoc-enqueue.md`,
`user/scripts/tests/baselines/*.txt`.

**Testing Strategy:** `sync_deps` pytest (write/noop/missing-id/missing-SPEC/reserved-prefix/
empty-set-removes-key) + smoke pins for the CLI surfaces; the refusal fixture drives the real CLI
via subprocess with a cycle marker in `LAZY_STATE_DIR` (existing bug-state precedent).

**Integration Notes for Next Phase:** Phase 5 audits the `--sync-deps` literal in both scripts —
land the flag string identically (`"--sync-deps"`) so the parity regex is trivially stable.

---

### Phase 5: Parity + docs

**Phase kind:** chore

**Scope:** `lazy_parity_audit.py` sixth state-script surface + `test_lazy_parity.py` lockstep
stub updates; schema/CLI documentation rows; `dep-block-schema.md` queue-projection paragraph;
full gate suite.

**Deliverables:**
- [x] `lazy_parity_audit.py`: `_SYNC_DEPS_RE = re.compile(r'"--sync-deps"')` + finding text in
  `audit_state_script_parity` (queue-dependency-dag coupled-pair parity).
- [x] `test_lazy_parity.py`: every `TestStateScriptParity` stub gains the `--sync-deps` token;
  docstrings/comments updated FIVE → SIX; new fires-when-sync-deps-missing test.
- [x] `user/scripts/CLAUDE.md`: CLI rows for `--sync-deps` + `--enqueue-adhoc --deps`, and a
  contributor note documenting the `deps` field, the dep-gate, the `dep_gated` probe key, the
  terminal, and the two justified divergences.
- [x] Root `CLAUDE.md`: queue-dependency-dag note (scripts section) + `adhoc-enqueue.md`
  component bullet gains `--deps`.
- [x] `docs/features/CLAUDE.md`: `deps` schema note on the queue.json line.
- [x] `user/skills/_components/dep-block-schema.md`: "Queue projection" paragraph (prose block =
  SSOT for kinds/reasons; queue `deps` = script-owned hard-only enforcement projection via
  `--sync-deps`; drift diagnostic; reserved prefixes).
- [x] Full gate suite green (pytest suites + both `--test` + `lazy_coord.py --test` +
  `toolify` + parity audit + lint).

**Minimum Verifiable Behavior:** `lazy_parity_audit.py --repo-root .` exits 0 against the live
tree and exits 1 (naming `--sync-deps`) against a stub tree where one script drops the flag;
`lint-skills.py` clean.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Parity: full fixture suites on both scripts + `lazy_parity_audit.py` green. *(Evidence:
  `SKIP_MCP_TEST.md` — gate-suite tails.)*
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phases 1–4.

**Files likely modified:** `user/scripts/lazy_parity_audit.py`, `user/scripts/test_lazy_parity.py`,
`user/scripts/CLAUDE.md`, `CLAUDE.md`, `docs/features/CLAUDE.md`,
`user/skills/_components/dep-block-schema.md`.

**Testing Strategy:** Parity-audit pytest fixtures (lockstep stubs) + docs lint; final acceptance
is the full gate suite from the lane protocol.
