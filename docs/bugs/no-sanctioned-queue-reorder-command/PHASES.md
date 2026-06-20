# Implementation Phases — Sanctioned queue-reorder command

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is harness state-script + skill-prose work (Python CLI subcommands, parity-audit regex, component/SKILL.md/CLI-doc prose). There is no AlgoBooth app surface, store, audio path, UI state, or event reachable via the MCP HTTP server. Validation is the in-file `--test` smoke harnesses (`lazy-state.py --test`, `bug-state.py --test`), `test_lazy_core.py`, and `lazy_parity_audit.py` — never the dev runtime. (mcp-testing SPEC class: build/CLI tooling with no app integration.)

## Validated Assumptions

All load-bearing assumptions here are **code-provable** — they are about the shape of existing Python helpers and argparse/dispatch wiring, fully determinable from source (read during the planning touchpoint audit). No runtime-coupled assumption rides into a later phase; the Runtime Assumption Validation gate is **skipped** for that reason (recorded here per the gate's skip-reason requirement). Ground-truth verified at planning time:

- `lazy_core.py` exposes `_atomic_write`, `_die`, `_diag`, `refuse_if_cycle_active`, `claude_state_dir` (lazy_core docstring lines 14–51; `enqueue_adhoc` consumes `_atomic_write`/`_die` at lazy-state.py:377/357).
- `lazy-state.py::enqueue_adhoc` (line 329) is the canonical `docs/features/queue.json` mutator: load → validate `queue` array is a list → refuse duplicate id (`_die`) → `insert(0, …)` → `_atomic_write`. The reorder primitive mirrors this exact load→mutate→atomic-write shape.
- `--enqueue-adhoc` is gated by `lazy_core.refuse_if_cycle_active("--enqueue-adhoc")` BEFORE any queue mutation (lazy-state.py:7777; bug-state.py:4756). This is the precedent gating model for `--reorder-queue` (operator-only / out-of-cycle, exit 3 for a cycle subagent, zero side effects).
- `bug-state.py::enqueue_adhoc` (line 1237) mutates `docs/bugs/queue.json` via the same load→mutate→`_atomic_write` shape; `load_bug_queue` (line 291) is the read path. The bug side mirrors the feature primitive.
- `lazy_parity_audit.py::audit_state_script_parity` (line 304) iterates `_STATE_SCRIPTS = ("lazy-state.py", "bug-state.py")` and applies a regex per script — the exact insertion point for a `--reorder-queue`-presence assertion.
- The consuming "Defer this {ITEM}" path in `_components/blocked-resolution.md` (lines 147–152) currently instructs the apply-subagent to hand-`Edit` `{SPEC_ROOT}/queue.json`. This shared, `{STATE_SCRIPT}`-tokenized component is the single consumer edit that updates BOTH `/lazy-batch` and `/lazy-bug-batch`.

## Audit Table (planning touchpoint verification — all paths verified `exists: yes` unless stamped net-new)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` | yes | `_atomic_write`, `_die`, `_diag`, `claude_state_dir`, `refuse_if_cycle_active` | refactor (add helper) | NEW `reorder_queue(queue_path, item_id, op, index=None, queue_label="queue")` — reuse `_atomic_write`/`_die`/`_diag`; do NOT write a new file-IO path |
| `user/scripts/lazy-state.py` | yes | `enqueue_adhoc` (329), argparse `--enqueue-adhoc` (6788), dispatch (7774), gate (7777) | refactor (add subcommand) | Add `--reorder-queue` argparse beside `--enqueue-adhoc`; dispatch calls `lazy_core.reorder_queue` on `docs/features/queue.json`; gate with `refuse_if_cycle_active("--reorder-queue")` FIRST |
| `user/scripts/bug-state.py` | yes | `enqueue_adhoc` (1237), argparse (~4033), dispatch (4753), gate (4756), `load_bug_queue` (291) | refactor (mirror) | Mirror `--reorder-queue` on `docs/bugs/queue.json` via the SAME `lazy_core.reorder_queue` helper (coupled-pair parity) |
| `user/scripts/lazy_parity_audit.py` | yes | `audit_state_script_parity` (304), `_STATE_SCRIPTS`, `_ACTIVE_REPO_BINDING_RE` | refactor | Add a `--reorder-queue`-presence regex assertion in `audit_state_script_parity`'s per-script loop |
| `user/skills/_components/blocked-resolution.md` | yes | "Defer this {ITEM}" hand-edit path (147–152), `{STATE_SCRIPT}` / `{SPEC_ROOT}` tokens | refactor | Replace the hand-`Edit` queue.json instruction with an inline `{STATE_SCRIPT} --reorder-queue --id <id> --to tail` Bash call (one shared edit covers both orchestrators) |
| `user/skills/lazy-batch/SKILL.md` | yes | HARD CONSTRAINT 1 (line 22) names "queue reorder" as a dispatched Opus path | refactor | Update prose: reorder is now a deterministic `--reorder-queue` Bash call, not a dispatched subagent; HARD CONSTRAINT 1's no-hand-edit rule PRESERVED |
| `user/skills/lazy-bug-batch/SKILL.md` | yes | HARD CONSTRAINT 1 analog | refactor | Mirror the same prose update (coupled pair) |
| `user/scripts/CLAUDE.md` | yes | "CLI surface" section | refactor | Document `--reorder-queue` operator/out-of-cycle subcommand on both scripts |

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC (bug investigation spec). No hard upstream deps — net-new CLI surface (Evidence Collected → Git History). Section intentionally minimal.

---

### Phase 1: `lazy_core.reorder_queue` primitive (the shared mutation helper)

**Scope:** Add ONE operator-facing queue-mutation helper to `lazy_core.py` that both state scripts call. It loads a queue JSON file, applies a single ordering mutation to existing entries, and atomically writes it back — mirroring `enqueue_adhoc`'s load→mutate→atomic-write shape. All four operations the SPEC enumerates (defer-to-tail, move/reorder, remove/skip, reprioritize) fold into ONE primitive via an operation/position argument (⚖ D7 from SPEC — most-complete). This phase is pure helper logic with no CLI wiring, so it is unit-testable in complete isolation via `test_lazy_core.py`.

**Deliverables:**
- [x] `reorder_queue(queue_path: Path, item_id: str, *, to: str | int, queue_label: str = "queue") -> dict` in `lazy_core.py`. `to` accepts `"tail"`, `"head"`, or an integer index. Loads the queue JSON (reusing the same `json.loads` + `_die("invalid …")` guard `enqueue_adhoc` uses), validates the `queue` field is a list, finds the entry whose `id == item_id`, moves it to the requested position, and `_atomic_write`s the result. `queue_label` parameterizes the `_die`/`_diag` message text ("queue.json" vs "bugs/queue.json") so both callers get correct diagnostics from the shared helper.
- [x] Remove operation: `to="remove"` (or a sibling `remove_from_queue` thin wrapper — implementer's call, but ONE code path) deletes the entry from the array. The SPEC folds remove/skip into the same primitive surface.
- [x] Missing-entry error: an `item_id` not present in the queue calls `_die(f"item not queued: {item_id}", queue_path)` (mirrors `enqueue_adhoc`'s duplicate-id `_die`) — a deterministic non-zero exit, never a silent no-op.
- [x] Idempotent/no-op case: moving an entry already at the requested position rewrites the file to an identical ordering (or short-circuits) and returns `{"reordered": True, "noop": True, …}` — never an error.
- [x] Return dict shape: `{"reordered": bool, "item_id": str, "operation": str, "new_position": int | None, "queue_length": int}` — JSON-serializable, mirroring `enqueue_adhoc`'s return contract so the dispatch sites can `json.dumps` it directly.
- [x] Tests: `test_lazy_core.py` characterizes `reorder_queue` directly — defer-to-tail, move-to-head, move-to-index, remove, the missing-entry `_die`, and the idempotent no-op. (Pure helper; no fixtures/CLI needed — direct function calls on a temp queue file.)

**Implementation Notes (P1 — 2026-06-20):**
- Added `reorder_queue(queue_path, item_id, *, to, queue_label="queue")` in `lazy_core.py` right after `_die` (the infrastructure-helpers section). Reuses `_atomic_write`/`_die`/`_diag`; no new file-IO path. `to` parses `tail`/`head`/`remove` or an int index (string-int form accepted); out-of-range index is clamped, not an error. Missing entry and malformed JSON both `_die` (exit 2, zero mutation). No-op (already at target) is byte-stable (no rewrite) and returns `noop: True`. Return dict adds a `noop` key beyond the planned shape (callers ignore it; JSON-serializable).
- Tests: 7 direct characterization tests in `test_lazy_core.py` (tail/head/index/remove/missing-`_die`/idempotent-byte-stable/malformed-`_die`). Confirmed RED (AttributeError, not import error) before impl; GREEN after. Full suite 700/700.
- Review verdict: PASS (self-review — spec-aligned, edge cases covered, byte-stable no-op verified).

**Minimum Verifiable Behavior:** `python3 -c "from lazy_core import reorder_queue; ..."` — run `reorder_queue` against a temp `queue.json` with 3 entries, request `to="tail"` for the head entry, and assert the on-disk JSON now lists that entry last and the file is valid JSON. (A runnable command; the helper exists after this phase.)

**MCP Integration Test Assertions:** N/A — no runtime-observable AlgoBooth surface in this phase (pure stdlib Python helper). Validated by `test_lazy_core.py`.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — add `reorder_queue` helper (reuse `_atomic_write`/`_die`/`_diag`).
- `user/scripts/test_lazy_core.py` — direct characterization tests for the new helper.

**Testing Strategy:** `python3 user/scripts/test_lazy_core.py` (the helper's direct unit tests). The helper is pure (one file-IO boundary via the injected `queue_path`), so it is exercised against temp queue files with no state machine, no CLI, no marker.

**Integration Notes for Next Phase:**
- The helper takes a `queue_path` (NOT a `repo_root`) so each state script resolves its own queue file (`docs/features/queue.json` vs `docs/bugs/queue.json`) and passes it in. This keeps the helper domain-agnostic per the `lazy_core` contract.
- The return dict is the JSON the dispatch sites print — keep it serializable.
- The `_die`-on-missing-entry path means the CLI dispatch needs NO extra validation; the helper owns the error contract (exit 2 on malformed JSON via `_die`, like `enqueue_adhoc`).

---

### Phase 2: `--reorder-queue` subcommand on `lazy-state.py` (feature pipeline)

**Scope:** Wire the Phase 1 helper as an operator-only, out-of-cycle `--reorder-queue` subcommand on `lazy-state.py`, gated EXACTLY like `--enqueue-adhoc` (`refuse_if_cycle_active("--reorder-queue")` fires FIRST, before any mutation → exit 3 / zero side effects for a cycle subagent). Add `--test` smoke fixtures covering each operation, the cycle-active refusal, the idempotent no-op, and the missing-entry error.

**Deliverables:**
- [ ] argparse: `--reorder-queue` (`action="store_true"`) plus `--to` (string; accepts `tail`/`head`/`remove`/an integer index) added beside the existing `--enqueue-adhoc` block (~line 6788). Reuse the EXISTING `--id` argument (already defined for `--enqueue-adhoc`); do NOT add a second id flag.
- [ ] dispatch branch beside the `--enqueue-adhoc` branch (~line 7774): `lazy_core.refuse_if_cycle_active("--reorder-queue")` FIRST, then `_die("--reorder-queue requires --id and --to")` if either is missing, then call `lazy_core.reorder_queue(Path(args.repo_root) / "docs" / "features" / "queue.json", args.id, to=<parsed --to>, queue_label="queue.json")`, `json.dumps` the result, return 0.
- [ ] `--test` fixture: defer-to-tail — a 3-entry features queue, `--reorder-queue --id <head> --to tail`, assert the entry is now last.
- [ ] `--test` fixture: move-to-head and move-to-index variants.
- [ ] `--test` fixture: remove — `--to remove` drops the entry; assert queue length decremented and entry absent.
- [ ] `--test` fixture: missing-entry → `_die` (SystemExit), mirroring the existing `enqueue_adhoc` duplicate-id refusal fixture (lazy-state.py:5560).
- [ ] `--test` fixture: cycle-active refusal — with the cycle marker present and no `LAZY_ORCHESTRATOR` export, the dispatch refuses (exit 3, queue.json UNCHANGED). Model on the existing `refuse_if_cycle_active` coverage.
- [ ] `--test` fixture: idempotent no-op — reorder an entry already at the target position; assert exit 0 and the file unchanged.
- [ ] Regenerate the byte-pinned baseline (`tests/baselines/lazy-state-test-baseline.txt`) via the `_normalize_smoke_output` helper — never by hand — since `--test` output changed.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --repo-root <tmp> --reorder-queue --id <head-id> --to tail` against a temp repo with a 3-entry `docs/features/queue.json` prints `{"reordered": true, …}` and the on-disk queue now lists `<head-id>` last. (Runnable command; the subcommand exists after this phase.)

**MCP Integration Test Assertions:** N/A — CLI subcommand with no runtime-observable AlgoBooth surface. Validated by `lazy-state.py --test`.

**Prerequisites:**
- Phase 1: `lazy_core.reorder_queue` exists and is characterized.

**Files likely modified:**
- `user/scripts/lazy-state.py` — argparse (`--reorder-queue`, `--to`) + dispatch branch + `--test` fixtures.
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt` — regenerated baseline.

**Testing Strategy:** `python3 user/scripts/lazy-state.py --test` (hermetic temp-dir fixtures). The cycle-active refusal fixture asserts the load-bearing gating invariant (no mutation under a live cycle marker); the no-op + missing-entry fixtures lock the helper's error contract at the CLI boundary.

**Integration Notes for Next Phase:**
- The `--to` parsing (string `tail`/`head`/`remove` vs `int(index)`) is established here — Phase 3 must MIRROR the exact same argparse + parsing on `bug-state.py` for the coupled-pair parity guard to pass.
- The dispatch gate (`refuse_if_cycle_active("--reorder-queue")` FIRST) is the contract `lazy_parity_audit.py` (Phase 4) asserts is present on BOTH scripts.
- Grammar decision (SPEC Open Question, deferred to planning): `--reorder-queue --id <id> --to {tail|head|remove|<index>}`. Chosen over a JSON ordering spec — it reuses the existing `--id` flag, matches `--enqueue-adhoc`'s flag shape, and keeps each invocation a single deterministic mutation (⚖ does not change product end-state; the SPEC authorized resolving this against the real argparse here).

---

### Phase 3: `--reorder-queue` subcommand on `bug-state.py` (bug pipeline — coupled-pair mirror)

**Scope:** Mirror Phase 2's subcommand on `bug-state.py`, operating on `docs/bugs/queue.json`, calling the SAME `lazy_core.reorder_queue` helper with `queue_label="bugs/queue.json"`. Same gating, same `--test` fixture set adapted to bug fixtures. This satisfies the coupled-pair parity requirement (the feature + bug state scripts must carry the same operator-facing surface).

**Deliverables:**
- [ ] argparse: `--reorder-queue` + `--to` on `bug-state.py` (beside its `--enqueue-adhoc` block, ~line 4033), reusing the EXISTING `--id` flag.
- [ ] dispatch branch beside the `--enqueue-adhoc` branch (~line 4753): `lazy_core.refuse_if_cycle_active("--reorder-queue")` FIRST, missing-arg `_die`, then `lazy_core.reorder_queue(Path(args.repo_root) / "docs" / "bugs" / "queue.json", args.id, to=<parsed --to>, queue_label="bugs/queue.json")`, `json.dumps`, return 0.
- [ ] `--test` fixtures mirroring Phase 2: defer-to-tail, move-to-head/index, remove, missing-entry `_die`, cycle-active refusal, idempotent no-op — adapted to `docs/bugs/queue.json` (model on the existing `enqueue-adhoc-writes-entry` / `enqueue-adhoc-idempotent` bug fixtures, bug-state.py:1679/1695).
- [ ] Regenerate the byte-pinned baseline (`tests/baselines/bug-state-test-baseline.txt`) via `_normalize_smoke_output` — never by hand.

**Minimum Verifiable Behavior:** `python3 user/scripts/bug-state.py --repo-root <tmp> --reorder-queue --id <head-id> --to tail` against a temp repo with a 3-entry `docs/bugs/queue.json` prints `{"reordered": true, …}` and the on-disk bug queue lists `<head-id>` last.

**MCP Integration Test Assertions:** N/A — CLI subcommand, no AlgoBooth runtime surface. Validated by `bug-state.py --test`.

**Prerequisites:**
- Phase 1: `lazy_core.reorder_queue` exists.
- Phase 2: the feature-side argparse + `--to` parsing shape is established (mirror it exactly).

**Files likely modified:**
- `user/scripts/bug-state.py` — argparse + dispatch branch + `--test` fixtures.
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` — regenerated baseline.

**Testing Strategy:** `python3 user/scripts/bug-state.py --test`. Because the helper is shared, this phase mostly proves the bug-side WIRING (correct queue path, correct gate, correct dispatch) matches the feature side — the mutation logic is already proven in Phase 1.

**Integration Notes for Next Phase:**
- After this phase BOTH scripts carry an identical `--reorder-queue` surface — Phase 4 makes that parity a guarded invariant.
- Run BOTH suites + the helper tests together after this phase (`lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py`) per the `lazy_core` change discipline — a shared-helper change must keep both state machines green.

---

### Phase 4: Parity-audit assertion (guard the coupled-pair invariant)

**Scope:** Add a `--reorder-queue`-presence assertion to `lazy_parity_audit.py::audit_state_script_parity` so a future silent drop of the subcommand from EITHER state script is a hard finding. This locks the coupled-pair parity the SPEC requires.

**Deliverables:**
- [ ] In `audit_state_script_parity` (line 304), add a regex (e.g. `--reorder-queue` literal presence) checked against EACH script in `_STATE_SCRIPTS`; a script missing it appends a finding naming the script + the missing surface, mirroring the existing `_ACTIVE_REPO_BINDING_RE` finding shape.
- [ ] Verify the audit passes after Phases 2–3 (both scripts carry the subcommand) and fails if either is removed: `python3 user/scripts/lazy_parity_audit.py --repo-root <repo>` exits 0; a manual removal experiment (not committed) exits 1 with the new finding.
- [ ] Tests: extend `test_lazy_parity.py` if it characterizes `audit_state_script_parity` (add a fixture asserting the new finding fires when a script lacks `--reorder-queue`); otherwise the live audit run is the gate.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_parity_audit.py --repo-root <repo>` exits 0 with both scripts carrying `--reorder-queue`; the new finding string is reachable (demonstrated by a throwaway edit removing the subcommand from one script → exit 1).

**MCP Integration Test Assertions:** N/A — static parity audit over Python source. Validated by running the audit + `test_lazy_parity.py`.

**Prerequisites:**
- Phase 2 + Phase 3: both scripts carry `--reorder-queue` (otherwise the new assertion fails immediately).

**Files likely modified:**
- `user/scripts/lazy_parity_audit.py` — extend `audit_state_script_parity` with the `--reorder-queue` regex.
- `user/scripts/test_lazy_parity.py` — assertion-fires test (if the function is characterized there).

**Testing Strategy:** Run the audit live (`lazy_parity_audit.py --repo-root <repo>`, exit 0) and `python3 user/scripts/test_lazy_parity.py`. A negative check (remove the subcommand from one script, confirm exit 1) proves the assertion is load-bearing, not a no-op.

**Integration Notes for Next Phase:**
- With the code surface guarded, Phase 5 updates the CONSUMING contracts (the orchestrator/blocked-resolution prose) to call the new command inline instead of dispatching a subagent — the documentation half of the fix.

---

### Phase 5: Consumer-contract rewire + CLI docs (replace the BLOCKED.md round-trip)

**Scope:** Update the consuming contracts so an operator-directed reorder calls `--reorder-queue` inline instead of writing `BLOCKED.md` + dispatching an apply-resolution subagent. The shared `_components/blocked-resolution.md` "Defer" path is the single load-bearing edit (it drives BOTH `/lazy-batch` and `/lazy-bug-batch` via the `{STATE_SCRIPT}` token). HARD CONSTRAINT 1 prose in both orchestrators is updated to note reorder is now a deterministic command (the no-hand-edit-`queue.json` rule is PRESERVED — the orchestrator calls the script, never hand-edits). Document `--reorder-queue` in `user/scripts/CLAUDE.md` "CLI surface". This is pure prose; correctness is verified by re-reading the edited prose and running the skill-lint/projection.

**Deliverables:**
- [ ] `_components/blocked-resolution.md` — the "Defer this {ITEM}; continue the rest of the queue" path (lines ~147–152) replaces the hand-`Edit {SPEC_ROOT}/queue.json` instruction with an inline `{STATE_SCRIPT} --reorder-queue --id <id> --to tail` Bash call. Keep the "LEAVE BLOCKED.md IN PLACE / do NOT neutralize" semantics (the defer keeps the item blocked, just off the queue head). One edit; the `{STATE_SCRIPT}` token covers both pipelines.
- [ ] `user/skills/lazy-batch/SKILL.md` HARD CONSTRAINT 1 (line 22) — update the "queue reorder" reference: an operator-directed reorder is now a deterministic `--reorder-queue` Bash call (out-of-cycle), NOT a dispatched Opus apply-resolution subagent. Preserve the rule that the orchestrator never hand-edits `queue.json`.
- [ ] `user/skills/lazy-bug-batch/SKILL.md` — mirror the HARD CONSTRAINT 1 prose update (coupled pair; the SKILL.md analog of the same constraint).
- [ ] `user/scripts/CLAUDE.md` "CLI surface" — add a `--reorder-queue --id <id> --to {tail|head|remove|<index>}` entry documenting it as operator-only / out-of-cycle (gated by `refuse_if_cycle_active`), present on BOTH `lazy-state.py` and `bug-state.py`, mirroring the `--enqueue-adhoc` documentation style.
- [ ] Re-run `python3 ~/.claude/scripts/project-skills.py` and `python3 ~/.claude/scripts/lint-skills.py` so the projected output reflects the component edit and the skills lint clean.
- [ ] Reverse-reference: the SPEC already cross-references the consuming contracts; no spin-off legs were created (the fix is fully in-scope).

**Minimum Verifiable Behavior:** `python3 ~/.claude/scripts/lint-skills.py` passes after the component + SKILL.md edits, and `project-skills.py` re-expands `blocked-resolution.md` into both `/lazy-batch` and `/lazy-bug-batch` projections with the new `--reorder-queue` Bash call present. (Runnable commands; verifies the prose edit propagated through the injection system.)

**MCP Integration Test Assertions:** N/A — documentation/contract prose. Validated by the skill lint + projection re-run.

**Prerequisites:**
- Phase 2 + Phase 3: the `--reorder-queue` command exists on both scripts (the prose now references a real command).

**Files likely modified:**
- `user/skills/_components/blocked-resolution.md` — Defer path → inline `--reorder-queue` call.
- `user/skills/lazy-batch/SKILL.md` — HARD CONSTRAINT 1 prose.
- `user/skills/lazy-bug-batch/SKILL.md` — HARD CONSTRAINT 1 prose (mirror).
- `user/scripts/CLAUDE.md` — "CLI surface" entry for `--reorder-queue`.

**Testing Strategy:** Re-read each edited prose block for correctness; run `lint-skills.py` (no broken injections / embedded-pattern violations) and `project-skills.py` (clean expansion). No runtime; this phase is the documentation/contract half of the fix.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed and writes FIXED.md once this bug's validation tail passes. The orchestrator owns that flip — these phases never set it.

**Integration Notes for Next Phase:** Terminal phase. After this lands, the full fix is in place: a deterministic `--reorder-queue` primitive on both scripts, guarded by the parity audit, with the BLOCKED.md + subagent round-trip replaced by an inline Bash call in the shared blocked-resolution consumer.
