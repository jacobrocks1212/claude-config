# Implementation Phases — Code↔Doc Provenance Linkage (Implementation Ledger)

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In Progress

**MCP runtime:** not-required — pure claude-config harness mechanics (Python state scripts +
skill/component prose). No Tauri app, no MCP-reachable surface; validation is `pytest` on
`lazy_core.py` / `test_lazy_core.py`, the `lazy-state.py --test` / `bug-state.py --test` smoke
baselines, `lazy_parity_audit.py`, and `lint-skills.py`. This is the `standalone — no app
integration` untestable class → `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** (none)`. Substantive dependencies are implemented data contracts, all verified
in `RESEARCH_SUMMARY.md`:

- **`lazy_core.apply_pseudo`** (`__mark_complete__`/`__mark_fixed__` branch) — the single scripted
  completion author this feature extends. The provenance write slots AFTER the receipt write +
  queue trim + ROADMAP strike (the completion's core is already durable) and degrades to a
  `warnings[]` entry on failure (the malformed-queue-trim policy).
- **`write_completed_receipt`** — already supports `completed_commit:`; the mark-complete call
  site finally passes it.
- **Cycle markers** — `--cycle-begin` snapshots `begin_head_sha`; `--cycle-end` resolves HEAD for
  the friction detector. The bracket ledger appends alongside (coupled pair, both state scripts).
- **`lazy_core._parse_locked_decisions`** — the distillate's decision enumeration; zero new
  parsing.
- **Siblings:** `harness-telemetry-ledger` and `queue-dependency-dag` lanes touch the same
  scripts' CLI blocks — edits here are kept tight (contiguous new blocks, no reflow).

---

### Phase 1: Commit-bracket ledger + receipt anchor

**Phase kind:** design

**Scope:** Record per-cycle commit brackets deterministically at `--cycle-end` (both state
scripts; fail-open) and stamp `completed_commit` into the completion receipt.

**Deliverables:**
- [x] `lazy_core.py`: `append_commit_bracket(...)` + `record_cycle_commit_bracket(repo_root)` —
  reads the live cycle marker, resolves `begin_head_sha` → current HEAD, and appends
  `{feature_id, begin_sha, end_sha, ts}` to `lazy-commit-brackets.jsonl` in `claude_state_dir()`
  (append-only, fail-open — identical contract to `append_friction_ledger_entry`; a write failure
  never blocks the marker clear; an empty bracket `begin == end` is skipped).
- [x] `lazy_core.py`: `read_commit_brackets(item_id)` — pure read of the ledger, filtered by id.
- [x] `--cycle-end` handlers in BOTH `lazy-state.py` and `bug-state.py` call
  `record_cycle_commit_bracket` BEFORE `clear_cycle_marker()` (coupled pair; mirrored).
- [x] `apply_pseudo` mark-complete/mark-fixed branch passes
  `completed_commit=_current_head(repo_root)` at the existing `write_completed_receipt` call site.
- [x] Tests (`test_lazy_core.py`, registered in `_TESTS`): bracket append + read round-trip;
  fail-open on unwritable state dir; empty-bracket skip; `completed_commit` stamped in a git
  fixture and absent in a non-git fixture; cycle-end handler integration (marker cleared AND
  bracket recorded).
- [x] In-file `--test` fixture (both scripts, mirrored): `--cycle-end` with an unwritable
  state-dir ledger still clears the marker (fail-open). Baselines re-pinned ONLY via
  `_normalize_smoke_output`.

**Minimum Verifiable Behavior:** With a hermetic `LAZY_STATE_DIR` and a git fixture repo,
`--cycle-begin` → commit → `--cycle-end` leaves `lazy-commit-brackets.jsonl` holding one record
whose `begin_sha`/`end_sha` bracket the commit; an unwritable ledger still exits 0 with
`cycle_marker_cleared: true`.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Bracket append is fail-open: unwritable state dir at `--cycle-end` → marker still cleared, no exception. *(Evidence: in-file `--test` fixture + `test_lazy_core.py`.)* <!-- verification-only -->
- [x] `completed_commit` lands on a gated receipt in a git repo fixture. *(Evidence: `test_lazy_core.py`.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config has no Tauri/MCP app). Verification is `pytest`.

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`,
`user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`,
`user/scripts/tests/baselines/*-test-baseline.txt` (re-pinned via `_normalize_smoke_output`).

**Testing Strategy:** Hermetic `LAZY_STATE_DIR` temp dirs + throwaway git fixture repos
(`git init` + commits) in `test_lazy_core.py`; fail-open proven by pointing the ledger at a
read-only path. Both `--test` harnesses re-run; parity audit exit 0.

**Integration Notes for Next Phase:** Phase 2's producer unions
`git diff --name-only begin..end` over `read_commit_brackets(item_id)`; when no brackets exist it
falls back to message-grep with an honest `derivation:` label.

---

### Phase 2: Producer + completion-gate wiring

**Phase kind:** design

**Scope:** `lazy_core.write_provenance` (the ONE writer); distillate + index emission from the
`__mark_complete__`/`__mark_fixed__` branch; `warnings[]` degradation; schema registration.

**Deliverables:**
- [x] `lazy_core.py`: `write_provenance(repo_root, item_dir, item_id, kind, commits, files, ...)`
  — stdlib-only; writes `IMPLEMENTED.md` (frontmatter: `kind: implemented`, `feature_id`, `date`,
  `provenance` (D9), `derivation` (D4), `commits:`, `decisions:`; optional `linked_by:`) with a
  deterministic body (SPEC leading `>` summary verbatim; Locked-Decision id — title rows via
  `_parse_locked_decisions`; receipt facts line), and merges per-file rows into
  `docs/provenance-index.json` (load → replace-this-item's-rows → `_atomic_write`; POSIX
  repo-relative keys, sorted for byte-stability). `dry_run` mutates nothing. Manual `body`
  override supported (D8) — the producer still owns frontmatter + index.
- [x] `lazy_core.py`: derivation helpers — `derive_touched_from_brackets` (union
  `git rev-list`/`git diff --name-only` over recorded brackets), `derive_touched_from_range`,
  `derive_touched_from_grep` (message-grep fallback, `-F --grep=<slug>`).
- [x] `apply_pseudo` `__mark_complete__`/`__mark_fixed__`: after receipt + queue trim + ROADMAP
  strike, derive (brackets primary, message-grep fallback) and call `write_provenance`
  (`provenance: pipeline-gated`); result carries `provenance_written`; any failure degrades to a
  `warnings[]` entry — completion is never blocked by its own bookkeeping.
- [x] `user/skills/_components/sentinel-frontmatter.md`: register `IMPLEMENTED.md` /
  `kind: implemented` (+ lifecycle row).
- [x] Tests: fixture completion produces byte-stable `IMPLEMENTED.md` + index rows matching
  `git diff` union; refused gate writes neither; induced index-write failure still completes with
  `warnings[]`; receipt-noop re-run writes nothing; no-Locked-Decision SPEC → `decisions: []` +
  body note.

**Minimum Verifiable Behavior:** A fixture `__mark_complete__` with recorded brackets emits
`IMPLEMENTED.md` (`provenance: pipeline-gated`, `derivation: commit-brackets`, correct decision
ids + shas) and index rows whose keys equal the bracket-diff union; re-running is a receipt-noop
that writes nothing.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Completion never blocked by bookkeeping: induced index-write failure → receipt + flips land, result carries `warnings[]`. *(Evidence: `test_lazy_core.py`.)* <!-- verification-only -->
- [x] Refused gate writes nothing: `__mark_complete__` with no evidence sentinel → no distillate, no index change. *(Evidence: `test_lazy_core.py`.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (bracket ledger, `read_commit_brackets`).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`,
`user/skills/_components/sentinel-frontmatter.md`.

**Testing Strategy:** Hermetic git fixture repos with a SPEC.md carrying a `## Locked Decisions`
table; byte-diff assertions on the distillate and index; failure injection via read-only index
path.

**Integration Notes for Next Phase:** Phase 3's `--link-provenance` calls the SAME
`write_provenance` with `provenance: manual` + `linked_by:` — entry shape must be byte-identical
except `provenance`/`derivation` (pytest compares both outputs).

**Deferred (cross-repo — not reachable from this claude-config lane):**
- [ ] *(deferred)* AlgoBooth `scripts/check-docs-consistency.ts` `SENTINEL_SCHEMAS` mirror of
  `kind: implemented` (D2 lockstep rule). **Reason:** the AlgoBooth repo is a different repository
  not present in this lane's worktree; the mirror must land as an AlgoBooth-side change (route via
  the AlgoBooth queue or a manual follow-up). Recorded per the skip-vs-defer honesty rule.

---

### Phase 3: Manual path — `--link-provenance` CLI + `/link-provenance` skill

**Phase kind:** design

**Scope:** The second trigger of the one writer: operator/manual linking of out-of-pipeline work.

**Deliverables:**
- [x] `lazy_core.py`: `link_provenance(repo_root, item_id, commit_range=None, pr=None,
  body_file=None, dry_run=False, linked_by=None)` — resolves the item dir
  (`docs/features/<id>` / `docs/bugs/<id>` / `docs/bugs/_archive/<id>`, creating a minimal
  `docs/features/<id>/` decision-record dir when none exists per D8), resolves `--pr` via
  `gh pr view --json baseRefOid,headRefOid` to a range (clean refusal when `gh` absent),
  derives commits+files from the range, and writes THROUGH `write_provenance`
  (`provenance: manual`, `derivation: commit-range`, `linked_by:`).
- [x] CLI on BOTH scripts: `--link-provenance` with `--id`, `--commits <A..B>`, `--pr <n>`,
  `--body-file <path>`, `--dry-run` (thin handlers; mirrored; parity audit green).
- [x] `user/skills/link-provenance/SKILL.md` — NEW user-level skill: `--dry-run` first (show the
  derived touched-file set), draft the body from the PR description/diff, `AskUserQuestion`
  approval, then write through the producer CLI with `--body-file`. Failure modes explicit
  (unresolvable range aborts with the producer's refusal text).
- [x] Tests: manual link of a historical range produces `provenance: manual` entries
  byte-identical in shape to pipeline entries (except `provenance`/`derivation`/`linked_by`);
  `--dry-run` mutates nothing (index bytes + mtime unchanged); re-linking the same range replaces
  rather than duplicates rows; unresolvable range refuses with no writes.

**Minimum Verifiable Behavior:** `lazy-state.py --link-provenance --id <slug> --commits A..B
--body-file body.md` on a fixture repo writes `IMPLEMENTED.md` (`provenance: manual`) + index
rows for exactly the range's touched files; `--dry-run` prints the same derivation and writes
nothing.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] One writer, two triggers: manual entry shape byte-identical to pipeline entries except `provenance`/`derivation`. *(Evidence: `test_lazy_core.py` comparing both outputs.)* <!-- verification-only -->
- [x] Idempotency: re-link same range → no duplicate rows. *(Evidence: `test_lazy_core.py` byte-diff.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 2 (`write_provenance`).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`,
`user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`,
`user/skills/link-provenance/SKILL.md`.

**Testing Strategy:** Fixture git repos with named commit ranges; subprocess CLI tests on both
scripts (parity); `gh`-absent refusal simulated by PATH control.

**Integration Notes for Next Phase:** Phase 4's lookup reads the index this phase's two triggers
populate; the lookup output cites `IMPLEMENTED.md` paths + decision ids.

---

### Phase 4: Consumption — `--provenance-lookup` + skill-step wiring (D6-A)

**Phase kind:** integration

**Scope:** The read side: a pure-read CLI + one lookup step wired into the edit-adjacent surfaces.

**Deliverables:**
- [x] `lazy_core.py`: `provenance_lookup(repo_root, path)` — pure read over
  `docs/provenance-index.json`; normalizes the query path to a repo-relative POSIX key; returns
  `{path, governed_by: [{id, type, doc, decisions, provenance}]}` (decisions read from each
  distillate's frontmatter; `doc` resolves archive residency). Never mutates; missing index →
  empty `governed_by` (degrades to a no-op).
- [x] CLI on BOTH scripts: `--provenance-lookup <path>` (mirrored; parity green).
- [x] `_components/lazy-batch-prompts/cycle-base-prompt.md`: lookup step before first edit to a
  file — read the cited `IMPLEMENTED.md` ONLY if the decision ids are unfamiliar.
- [x] `/spec-phases` SKILL.md: lookup step alongside the existing capability audit (governing
  decisions consulted while drafting phases).
- [x] Coupled `/lazy*` wrapper prose: the same short lookup note added to `lazy` ↔ `lazy-cloud`
  and `lazy-batch` ↔ `lazy-batch-cloud` (mirrors diffed; parity audit green).
- [x] Projection + lint: `project-skills.py` to a lane-local output dir + `lint-skills.py` clean.
- [x] Tests: lookup returns correct rows for a seeded index; lookup leaves index bytes + mtime
  unchanged; unknown path / missing index → empty result, exit 0.

**Minimum Verifiable Behavior:** With a seeded index, `--provenance-lookup user/scripts/lazy_core.py`
prints the governing `{id, type, doc, decisions, provenance}` rows and mutates nothing.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Lookup is a pure read: correct rows; index unchanged. *(Evidence: `test_lazy_core.py`.)* <!-- verification-only -->
- [ ] A cycle-subagent transcript shows the lookup step firing. *(Deferred-to-live: no cycle subagent runs inside this lane; the prompt step is projection-linted and the CLI is pytest-proven — first live `/lazy-batch` run observes it. Recorded per skip-vs-defer honesty.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 2-3 (populated index).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`,
`user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`,
`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`,
`user/skills/spec-phases/SKILL.md`, `user/skills/lazy/SKILL.md`,
`user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md`,
`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.

**Testing Strategy:** Seeded-index fixtures; mtime/byte assertions for purity; skill edits
verified by projection into a lane-local dir + `lint-skills.py`; coupled-pair diffs eyeballed +
parity audit.

**Integration Notes for Next Phase:** Phase 5's lint reuses the same index reader; backfill
populates the index the lookup serves.

---

### Phase 5: Backfill + maintenance lint

**Phase kind:** design

**Scope:** Day-one usefulness (backfill claude-config) + the honesty loop (`--lint-provenance`).

**Deliverables:**
- [x] `lazy_core.py`: `backfill_provenance(repo_root)` — walks items with a valid
  `COMPLETED.md`/`FIXED.md` (features, bugs, `docs/bugs/_archive/`), skips items already carrying
  `IMPLEMENTED.md` (idempotent), derives via message-grep, writes through `write_provenance`
  (`provenance: backfilled`, `derivation: message-grep`); zero-hit items get a distillate with
  `commits: []` + a body note and no index rows (honest, never silent).
- [x] `lazy_core.py`: `lint_provenance(repo_root, churn_days=90, churn_threshold=5)` — report
  only, never mutates: (a) dead rows (path gone from the working tree); (b) churn hotspots with
  no rows (`git log --since` aggregation over the threshold); (c) cross-orphans (distillate with
  no rows / rows citing a missing distillate).
- [x] CLI on BOTH scripts: `--backfill-provenance`, `--lint-provenance` (mirrored; parity green).
- [x] Tests: backfilled entries carry `provenance: backfilled` + `derivation: message-grep`;
  backfill idempotent; lint catches a planted dead row, a planted hot un-provenanced file, and a
  planted cross-orphan; lint mutates nothing.
- [x] Run `--backfill-provenance` for claude-config (this repo) as validation — commits the index
  + `IMPLEMENTED.md` distillates for already-completed items (SPEC estimated 10 features + 39
  archived bugs; actual counts recorded in the commit).
- [x] Docs: `user/scripts/CLAUDE.md` CLI quick-reference rows for the four new subcommands
  (tight, no reflow).

**Minimum Verifiable Behavior:** `--backfill-provenance --repo-root <claude-config>` emits
`provenance: backfilled` distillates for every receipted item and index rows for message-grep
hits; `--lint-provenance` on a fixture with a planted dead row + hot file reports both and
mutates nothing.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Backfill honesty: receipted item → `provenance: backfilled`, `derivation: message-grep`. *(Evidence: `test_lazy_core.py` + the live claude-config backfill run.)* <!-- verification-only -->
- [x] Lint catches rot: planted dead row + churned non-indexed file both flagged; nothing mutated. *(Evidence: `test_lazy_core.py` + manual run.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 2 (producer).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`,
`user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`, `user/scripts/CLAUDE.md`,
`docs/provenance-index.json` (generated), `docs/features/*/IMPLEMENTED.md` +
`docs/bugs/**/IMPLEMENTED.md` (generated).

**Testing Strategy:** Fixture repos with receipted items + planted rot for the lint; the live
backfill run over this repo is the acceptance demo (inspected by hand, committed).

**Integration Notes for Next Phase:** None (final phase). Follow-ups live in the deferred rows:
AlgoBooth `SENTINEL_SCHEMAS` mirror + AlgoBooth automatic-wiring validation (D11) on a lane with
that repo present.
