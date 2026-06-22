# Implementation Phases — Lazy Queue Status Doc (GitHub-Mobile Readable)

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is a docs/Python-script harness repo with no Tauri app, no MCP HTTP server, and no audio surface; the deliverable is a stdlib Python generator + its pytest suite + a pipeline-wiring doc edit. This is the "no app integration / build-tooling-and-docs" untestable class per `docs/features/mcp-testing/SPEC.md` (MCP reaches the AlgoBooth dev runtime, which this repo does not have). Validation is the generator's own `--test`/pytest suite + a real `python lazy-queue-doc.py --repo-root .` run diffed against `lazy-state.py`/`bug-state.py` JSON — observable on the workstation, not via MCP.

## Validated Assumptions

Grounded inline during /spec-phases Step 2 (touchpoint audit) — these are code-provable (no runtime spike needed; the generator is a pure read renderer over an already-proven peer):

- **The state-script read contract the SPEC names exists and is `--repo-root`-addressable.** Verified in `lazy-state.py`: `--probe` (line 7997), `--feature-id` (7907), `--next-merged` (8067), `--marker-present` (8036), `--marker-work-branch` (8053), `--repo-root` (7855). The generator never re-implements inference — it shells these (or reuses the peer wrapper below).
- **A proven peer already wraps "shell the state scripts, never re-infer."** `user/scripts/pipeline_visualizer/probe.py::probe_state(repo_root)` returns the exact aggregate this generator needs — `{features, bugs, leases, roadmap, server_time}` — by shelling `lazy-state.py --feature-id` / `bug-state.py --bug-id` per queue item, parsing each JSON, and attaching a display-only `curated_stage` via `curated_stage.curated_stage(current_step, terminal_reason, pipeline)`. The generator is a NEW markdown output channel onto this same aggregate (the desktop visualizer is the HTML/graph channel). REUSE it; do not re-shell.
  - ⚖ policy: SPEC says "shell the state scripts"; peer already does → reuse `probe_state()`. Mechanical grounding improvement (same data, byte-stable, one writer of the shell-contract), not a behavior change — recorded here per D7.
- **Run-active/idle signal source.** `lazy-state.py --marker-present --repo-root <root>` (read-only, exit 0 present / 1 absent, per-repo keyed) is the honest freshness/run-active marker source. The generator shells it (it does NOT import `lazy_core.read_run_marker` internals — the CLI is the public read contract). `--marker-work-branch` is available if the doc later wants to show the active work branch.
- **queue.json schemas.** Feature entries carry `id`/`name`/`spec_dir`/`tier`/`adhoc`/`stub`; bug entries carry `id`/`name`/`spec_dir`/`severity`/`adhoc` (verified against `docs/features/queue.json`, `docs/bugs/queue.json`, and `probe.py`'s `queue_meta` reads). `spec_dir` (fallback `id`) resolves the SPEC link target; the state script's own `spec_path` is authoritative when present (`probe._item_dir`).

## Cross-feature Integration Notes

The SPEC's `**Depends on:** (none)` block carries no hard deps (this repo's specs have no `queue.json` dependency graph — sibling `lazy-pipeline-visualizer` SPEC convention). Substantive (non-block) data-contract dependencies and their grounding:

- **`pipeline_visualizer` package (peer, not a dep) — Complete, in-repo.** Its `probe_state()` + `curated_stage()` are the reuse anchors above. The visualizer is the desktop channel onto the same on-disk state; this feature is the GitHub-mobile read channel. They coexist (SPEC Decision: peer). No upstream PHASES reality-check owed (no hard dep).
- **`lazy-state.py` / `bug-state.py` CLI read ops — Complete, in-repo.** The implemented data contract (not a sibling spec). The generator is a pure read renderer over it.
- **Writes are out of scope (already solved).** Reorder/remove/enqueue run through `--reorder-queue` / `--enqueue-adhoc` from chat. This feature builds NO write path — no phase below touches a write op.

---

### Phase 1: Pure-read generator → per-repo grouped `LAZY_QUEUE.md`

**Scope:** A stdlib Python generator (`user/scripts/lazy-queue-doc.py`) that, given `--repo-root`, reads the repo's full lazy state via the proven peer (`pipeline_visualizer.probe.probe_state`) and emits the per-repo grouped `LAZY_QUEUE.md`: a Features table and a Bugs table (one row per queue item: reorder index, item name, curated state, tier/severity), a "Needs attention" triage section mirroring Blocked / Needs-Input items, and a freshness header (generated-at timestamp + run-active/idle marker from `--marker-present`). Idempotent and **byte-stable**: re-running with unchanged state produces a byte-identical doc (no spurious diff/commit). Output is written to `<repo-root>/LAZY_QUEUE.md` (root-level, per Decision 6 doc-path note); `--stdout` prints without writing (for tests/dry-run).

**Deliverables:**
- [ ] `user/scripts/lazy-queue-doc.py` — new stdlib-only generator. Imports the sibling `pipeline_visualizer` package using the `_SCRIPTS_DIR`-on-`sys.path` pattern from `pipeline_visualizer/__main__.py` (lines 18-20), calls `probe_state(repo_root)`, and renders markdown.
- [ ] Argument surface: `--repo-root` (default cwd, matching `__main__.py`), `--stdout` (print, don't write), `--test` (in-file fixture smoke harness, mirroring the `lazy-state.py --test` convention) OR a pytest sibling (see Testing Strategy — choose pytest sibling for consistency with `test_pipeline_visualizer.py`).
- [ ] Renderer: Features table (`# | item | state | tier`), Bugs table (`# | item | state | sev`), grouped under `## Features (N)` / `## Bugs (M)` headers with live counts. Each item name is a markdown link to its SPEC.md (relative path `docs/{features,bugs}/<spec_dir>/SPEC.md`, resolved from the state script's `spec_path` when present, else `spec_dir`/`id`).
- [ ] "Needs attention" section: enumerate items whose `curated_stage` ∈ {Blocked, Needs-input} (the `/lazy-status` triage signal), one bullet each; omit the section entirely when none (byte-stability: an empty triage section must not emit an empty header).
- [ ] Freshness header: `# Lazy Queue — <repo>   (updated <ts> · run active 🔒 | idle)`. The run-active/idle token comes from shelling `lazy-state.py --marker-present --repo-root <root>` (exit 0 → active, exit 1 → idle). **Timestamp byte-stability caveat:** the generated-at timestamp inherently changes every run, which would defeat byte-stability for the commit-no-op goal. Resolve this with the deterministic-doc-body approach below (Integration Notes) — the timestamp lives on a line the byte-stability check excludes, OR the doc carries no embedded wall-clock and derives freshness from git commit time. (See Integration Notes — this is the one design point Phase 1 must nail for Phase 3's no-op-commit goal.)
- [ ] Tests: pytest sibling `user/scripts/test_lazy_queue_doc.py` (see Testing Strategy).

**Minimum Verifiable Behavior:** `python user/scripts/lazy-queue-doc.py --repo-root . --stdout` prints a `LAZY_QUEUE.md` whose Features table lists the one queue entry (`mobile-queue-control`) with a curated state matching `python user/scripts/lazy-state.py --repo-root . --feature-id mobile-queue-control` JSON's `current_step` rolled through `curated_stage`, and whose Bugs table is `## Bugs (0)` (empty bug queue). Running it twice with no state change produces byte-identical stdout.

**Runtime Verification** *(checked by the pytest suite / a real workstation run — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Generator run against this repo emits a doc whose every feature/bug row's `state` cell equals the `curated_stage` of that item's `lazy-state.py`/`bug-state.py` JSON (state fidelity — SPEC Validation row 1).
- [ ] <!-- verification-only --> Two successive generations with no intervening state change produce byte-identical output (byte-stability — SPEC Validation row 2; the timestamp-exclusion / git-time approach holds).
- [ ] <!-- verification-only --> A repo fixture with a Blocked or Needs-Input item surfaces that item under "Needs attention"; a repo with none omits the section (triage accuracy — SPEC Validation row 4).

**MCP Integration Test Assertions:** N/A — no MCP-reachable runtime in claude-config (see header **MCP runtime: not-required**). Validation is the pytest suite + a real `--stdout` run diffed against state-script JSON, both workstation-observable.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy-queue-doc.py` — NET-NEW. The generator. Reuses `pipeline_visualizer.probe.probe_state` (probe.py:158) + `pipeline_visualizer.curated_stage.curated_stage` (curated_stage.py:122); shells `lazy-state.py --marker-present` for the run-active token.
- `user/scripts/test_lazy_queue_doc.py` — NET-NEW. Pytest sibling, mirrors `test_pipeline_visualizer.py`.

**Testing Strategy:**
Pytest sibling at `user/scripts/test_lazy_queue_doc.py` (consistency with the 8 existing `test_*.py` siblings; `test_pipeline_visualizer.py` is the direct template). Build temp-dir repo fixtures (a `docs/features/queue.json` + `docs/bugs/queue.json` + minimal SPEC dirs), monkeypatch or inject the `probe_state` result (or shell the real scripts against the fixture), and assert: (1) the rendered tables match the fixture's items + states, (2) two renders of an unchanged fixture are byte-identical, (3) a Blocked/Needs-Input fixture surfaces in "Needs attention" and a clean fixture omits the section, (4) SPEC links resolve to `docs/{features,bugs}/<spec_dir>/SPEC.md`. Verify with `python -m pytest user/scripts/test_lazy_queue_doc.py`.

**Integration Notes for Next Phase:**
- **Byte-stability vs. the freshness timestamp is the load-bearing design point.** The SPEC wants both a generated-at timestamp (freshness signal) AND byte-stable output (no spurious commit when state is unchanged). These conflict if the wall-clock timestamp is embedded verbatim. Resolve in Phase 1 by EITHER (a) deriving freshness from the doc's own git commit time (no embedded wall-clock at all — the run-active marker still distinguishes live vs. idle, and "last updated" reads from `git log -1 LAZY_QUEUE.md`), OR (b) embedding the timestamp on a single trailing line the byte-stability self-check and the Phase-3 no-op detector both ignore. Recommendation: (a) — a doc with no embedded wall-clock is trivially byte-stable, and GitHub mobile shows the file's last-commit time natively. Phase 3 depends on whichever choice Phase 1 makes; record it in Phase 1's output and carry it forward.
- The generator must REUSE `probe_state()` — it must not re-shell `lazy-state.py`/`bug-state.py` per item independently (one writer of the shell-contract; the visualizer already owns it). If `probe_state`'s aggregate is missing a field the doc needs, extend `probe.py` (with a `test_pipeline_visualizer.py` test) rather than forking the shell logic.
- Curated state literals come from `curated_stage` — do NOT invent a parallel step→state map. The doc's `state` column is `curated_stage` verbatim (Pending/Spec/Research/Plan/Implement/Validate/Complete + Blocked/Needs-input/Deferred), optionally with a leading glyph (▶/◷/⬡) chosen purely for display.
- `spec_path` from the state script is authoritative for the link target (`probe._item_dir` already prefers it); fall back to `docs/{features,bugs}/<spec_dir or id>/SPEC.md`.

---

### Phase 2: Per-item drill-in — inline curated summary + SPEC.md link

**Scope:** Enrich each item row (Phase 1 emits name + state + tier/sev) with the curated summary the SPEC's Decision 7 specifies: status, phase N/M, next action, and a one-line exec summary — inlined under or beside the row — alongside the SPEC.md link (which GitHub mobile renders on tap). The summary fields are read from data already in `probe_state()`'s per-item dict (`current_step`, `terminal_reason`, `curated_stage`) plus the item's SPEC.md (one-line exec summary = the SPEC's lead blockquote / Executive Summary first sentence). Confirm the SPEC-link relative-path behavior on GitHub mobile (the one empirical check deferred from research), with the absolute-URL fallback.

**Deliverables:**
- [ ] Extend the renderer: each item row gains an inline curated summary line — `status · phase N/M · next: <action> · <one-line exec summary>`. Derive `status`/`next-action` from `curated_stage` + `current_step`; derive `phase N/M` from the item's PHASES.md (count `### Phase` headings vs. checked-off phases) when present, else omit that token; derive the one-line exec summary from the item's SPEC.md lead blockquote / `## Executive Summary` first sentence (read the SPEC file the link already points at — the path is already resolved in Phase 1).
- [ ] SPEC.md link: the item name links to its SPEC.md (relative path from Phase 1). Add a generator option / constant for the absolute-URL fallback form (`github.com/<owner>/<repo>/blob/<branch>/docs/.../SPEC.md`) so that if the GitHub-mobile relative-link check (Open Question) fails, switching is a one-line config change, not a rewrite. Derive `<owner>/<repo>`/`<branch>` from `git remote get-url origin` + the marker work-branch (default `main`) when the absolute form is selected.
- [ ] Phase-progress reader: a small helper that, given an item's PHASES.md path, returns `(checked_phases, total_phases)` for the `phase N/M` token. REUSE the existing PHASES parsing in `lazy_core` if a public helper exists (grep `lazy_core` for phase-heading / deliverable counting — e.g. `remaining_unchecked_*`); only add a new helper if none is reusable, and keep it display-only (never re-infer pipeline state).
- [ ] Tests: extend `test_lazy_queue_doc.py` — assert a fixture item with a 3-phase PHASES.md (1 checked) renders `phase 1/3`; assert the exec-summary line is the SPEC's first sentence; assert the absolute-URL fallback form is emitted when the fallback option is set.

**Minimum Verifiable Behavior:** Against this repo, `python user/scripts/lazy-queue-doc.py --repo-root . --stdout` renders the `mobile-queue-control` row with an inline summary showing its curated status, `phase N/M` derived from this very `PHASES.md` (3 phases), `next:` action, and a one-line exec summary lifted from `SPEC.md`'s lead blockquote — and the name links to `docs/features/mobile-queue-control/SPEC.md`.

**Runtime Verification** *(checked by the pytest suite / a real workstation run + one manual GitHub-mobile check):*
- [ ] <!-- verification-only --> An item with a multi-phase PHASES.md renders the correct `phase N/M` token (progress fidelity — derived from on-disk PHASES, not invented).
- [ ] <!-- verification-only --> The item-name link, when the doc is committed + pushed, navigates to the item's SPEC.md on the GitHub mobile app (SPEC-link resolution — SPEC Validation row 3; the one empirical relative-link check deferred from research). If relative links misbehave on GitHub mobile, set the absolute-URL fallback option and re-verify — both forms are implemented, so this is a config flip, not a code change.
- [ ] <!-- verification-only --> The inline curated summary's status/next-action match the item's `lazy-state.py` JSON (`current_step`/`terminal_reason` → `curated_stage`), i.e. the drill-in summary is faithful to live state.

**MCP Integration Test Assertions:** N/A — no MCP runtime (see header). The one runtime-coupled check (GitHub-mobile relative-link rendering) is a manual mobile-app observation, not MCP; the absolute-URL fallback is pre-built so a failed check is a config flip.

**Prerequisites:**
- Phase 1: the generator, the resolved per-item SPEC path, and the byte-stability approach must exist — Phase 2 enriches the rows Phase 1 emits and reuses Phase 1's link-target resolution.

**Files likely modified:**
- `user/scripts/lazy-queue-doc.py` — extend the renderer with the curated-summary line, the phase-progress reader, and the absolute-URL fallback option.
- `user/scripts/test_lazy_queue_doc.py` — extend with phase-progress, exec-summary, and fallback-form assertions.

**Testing Strategy:**
Extend the Phase 1 pytest sibling. Fixtures gain a multi-phase PHASES.md and a SPEC.md with a known lead blockquote so the `phase N/M` and exec-summary tokens are deterministically assertable. The GitHub-mobile relative-link behavior is the one assertion that is NOT unit-testable (it is a property of the GitHub mobile app, not this code) — it is a manual mobile observation recorded in the Runtime Verification rows, with the absolute-URL fallback implemented so the outcome is a config flip either way.

**Integration Notes for Next Phase:**
- Phase 3 wires the generator into the pipeline commit. The exec-summary read opens each item's SPEC.md — keep that read cheap and failure-tolerant (a missing/short SPEC yields an empty summary token, never an exception), because Phase 3 runs the generator on every cycle boundary.
- The phase-progress and exec-summary tokens are derived purely from on-disk SPEC/PHASES — they remain byte-stable when those files are unchanged, preserving Phase 1's no-op-commit property for Phase 3.
- The relative-vs-absolute link decision is config, defaulting to relative (Decision 7 / Open Question); Phase 3's wired runs use the default unless the mobile check forces the fallback.

---

### Phase 3: Pipeline-integrated trigger — generate + stage `LAZY_QUEUE.md` on the cycle's existing commit

**Scope:** Wire the generator to run at each lazy cycle boundary in claude-config + AlgoBooth (Decision 6 scope: both are `main`-based + pushed), so `LAZY_QUEUE.md` is regenerated and staged to ride the cycle's EXISTING commit on `main` — no extra commits, no separate process. Byte-stable generation (Phase 1) means an unchanged doc produces no diff and adds nothing to the commit. Verify the honest freshness/run-active marker and the no-op-when-unchanged behavior end-to-end.

**Deliverables:**
- [ ] Identify and wire the cycle-boundary hook point. Per the SPEC Open Question, the exact point is a `/spec-phases` integration detail; the grounded candidates are (a) the orchestrator's per-cycle commit step in `/lazy-batch` (where `git add -A` already stages residue — see `lazy_core.py` ~line 4694 and the `/lazy-batch` recovery-cycle commit at SKILL.md:813), or (b) a state-script post-transition side-effect. **Recommendation (D7 scope-class — same end-state, differs only in wiring locus): (a)** the orchestrator commit step, because it already owns staging + commit + push on `main` and runs once per cycle, so the doc rides the existing commit with zero new infrastructure; a state-script side-effect would mutate a file during a read-path probe (violating the "pure read" / one-writer discipline). Wire it as: before/at the per-cycle `git add -A`, run `python user/scripts/lazy-queue-doc.py --repo-root <repo>` so the regenerated `LAZY_QUEUE.md` is staged by the existing `git add -A`.
- [ ] claude-config wiring: add the generator invocation to claude-config's own commit cadence (this repo works on + pushes to `main`), so this repo's `LAZY_QUEUE.md` lands on the default branch. AlgoBooth wiring: the equivalent in the AlgoBooth `/lazy-batch`(-cloud) cycle commit — but only on the workstation/`main` path (cloud defers push; the SPEC scopes the pushed-doc guarantee to `main`-based repos, so the cloud variant generates the doc locally and it rides whatever commit the cloud session makes without a special push step).
- [ ] Document the wiring in the relevant SKILL.md / commit-policy prose (one writer per file — edit only the orchestrator's commit step prose, not the state-machine logic). No change to `lazy-state.py`/`bug-state.py` state machine (the generator is invoked BY the orchestrator, not by the state script's compute path).
- [ ] Byte-stable no-op verification: after wiring, a cycle that does not change lazy state must produce NO `LAZY_QUEUE.md` diff (so the cycle's commit is unaffected). A cycle that advances an item must produce exactly the row/state diff for that item.
- [ ] Tests: a test (pytest sibling or the generator's own harness) asserting the no-op-commit property — generate, capture bytes; generate again with no state change; assert identical bytes (this is the Phase-1 byte-stability test re-asserted as the Phase-3 acceptance gate). The actual git-staging wiring is prose in a SKILL/commit-policy doc (not unit-testable Python) — its verification is the real workstation cycle observation below.

**Minimum Verifiable Behavior:** A real claude-config `/lazy-batch` (or manual commit) cycle that advances `mobile-queue-control` one stage results in `LAZY_QUEUE.md` showing the new state, staged and committed within that cycle's existing commit on `main`; a subsequent cycle with no state change leaves `LAZY_QUEUE.md` byte-identical and adds nothing to the commit (verified via `git diff --stat` showing no `LAZY_QUEUE.md` entry).

**Runtime Verification** *(checked by a real workstation cycle observation — NOT by the implementation agent):*
- [ ] <!-- verification-only --> After a lazy cycle that advances an item, `LAZY_QUEUE.md` on `main` reflects the new state and was committed within the cycle's existing commit (no separate commit) — staying-current property (SPEC Validation row 5).
- [ ] <!-- verification-only --> A cycle with no lazy-state change produces no `LAZY_QUEUE.md` diff (`git diff --stat` lists no `LAZY_QUEUE.md`), confirming byte-stable no-op commits (SPEC Validation rows 2 + 5).
- [ ] <!-- verification-only --> The doc's run-active/idle marker matches reality: `🔒`/active during a live run (run marker present per `--marker-present`), idle otherwise (freshness-marker honesty — SPEC Validation row 6).

**MCP Integration Test Assertions:** N/A — no MCP runtime (see header). Acceptance is the byte-stable-no-op unit test + a real workstation `/lazy-batch` cycle observation (state-advance diff + no-op-commit + run-active marker), all workstation-observable.

**Prerequisites:**
- Phase 1: byte-stable generator + run-active marker (the no-op-commit property depends entirely on Phase 1's byte-stability design choice).
- Phase 2: the full drill-in renderer (the wired runs generate the complete doc, not the Phase-1 skeleton).

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md` — document/wire the generator invocation at the per-cycle commit step (orchestrator prose; the state machine is untouched). If AlgoBooth's `/lazy-batch`(-cloud) is the wiring locus there, that edit lands in the AlgoBooth repo's repo-scoped skill (out of this repo's tree — note it as a cross-repo follow-up in the Integration Notes / a spun-off item if it cannot land here).
- claude-config commit-policy / cadence prose (e.g. `.claude/skill-config/commit-policy.md` if present, else the `/lazy-batch` commit step) — add the generator invocation to this repo's own commit cadence.
- `user/scripts/test_lazy_queue_doc.py` — the no-op-commit byte-stability acceptance test.

**Completion (gate-owned):** the `__mark_complete__` gate flips SPEC.md **Status:** to Complete and writes COMPLETED.md once this phase's runtime verification passes (the orchestrator owns the flip + receipt; this plan never authors a status-flip checkbox).

**Testing Strategy:**
The Python-testable slice (byte-stable no-op) is unit-tested in `test_lazy_queue_doc.py`. The git-staging-on-cycle wiring is prose in a SKILL/commit-policy doc; its verification is a real workstation `/lazy-batch` cycle observation (the Runtime Verification rows). AlgoBooth-side wiring, if it cannot be authored from this repo, is surfaced as a cross-repo follow-up (see Integration Notes) — the generator itself is fully `--repo-root`-addressable and proven against this repo, so AlgoBooth adoption is a one-line invocation add in that repo's cycle, not new generator work.

**Integration Notes for Next Phase:**
- **Cross-repo wiring caveat (one-writer / repo-boundary).** This repo's tree cannot edit AlgoBooth's repo-scoped `/lazy-batch-cloud` skill. If the AlgoBooth wiring must be authored, it is a separate edit in `~/source/repos/algobooth/.claude/...` (or its mirror under `repos/algobooth/` in this config repo). If that edit is out of scope for this feature's commit, spin it off as a follow-up feature/bug and REVERSE-REFERENCE it here — but the generator is already AlgoBooth-ready (pure `--repo-root` function), so adoption is trivial and may simply be documented as a manual one-liner for the operator to add to AlgoBooth's cycle.
- No state-machine change: the generator is orchestrator-invoked, never called from `lazy-state.py`/`bug-state.py` compute paths — this keeps the "pure read, never writes during a probe" discipline intact and avoids a coupled-pair edit to the two state scripts.
- A cross-repo aggregate index doc (SPEC Open Question) is explicitly v1-out-of-scope — per-repo only.
