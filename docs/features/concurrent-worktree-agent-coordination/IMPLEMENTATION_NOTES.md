# Concurrent Multi-Agent Worktree Coordination — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 1 — Awareness injection + reconcile "One writer per file"

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-18
**Work completed:**
- Chose the canonical awareness phrase (WU-1, reused verbatim everywhere else): "other agents may be working this same worktree/branch concurrently — an unexpected commit / moved HEAD is expected, not a defect. Genuine write contention is resolved by the coordination layer (git safety + the FIFO file-lock + conflict-routing) — not by halting." Taken directly from SPEC Requirement 1's canonical wording.
- Injected the note into `cycle-base-prompt.md`'s turn-end sections (both `modes=workstation` and `modes=cloud` variants), placed right after the R5 ATOMIC GATE+COMMIT item (per the plan's "R5 chain region" pointer) as an unnumbered paragraph so the existing numbered turn-end checklist (items 1/2/3) stayed intact.
- Added a new HARD CONSTRAINT (`/lazy-batch` #11, `/lazy-batch-parallel` P8, `/lazy-batch-cloud` #12) plus an appended sentence on the existing sub-subagent/lane dispatch-policy prose in each of `lazy-batch/SKILL.md`, `lazy-batch-parallel/SKILL.md`, and the AlgoBooth mirror `lazy-batch-cloud/SKILL.md`. `lazy-cloud/SKILL.md` (a thin single-item wrapper with no HARD CONSTRAINTS/dispatch-policy block) got the note as a new paragraph beside its existing `HARD REQUIREMENT` bullets.
- Reconciled `user/CLAUDE.md`'s `<orchestration>` "One writer per file" block: re-scoped the existing rule to "within a run you control" and added a new paragraph carving out sanctioned concurrent writers outside that tree (parallel lanes, a second session, a background harden), pointing at the coordination layer as arbiter instead of treating an unexpected commit/moved HEAD as a defect.
**Integration notes:**
- The canonical phrase is grep-anchored (`an unexpected commit / moved HEAD is expected`) in all 6 injection points named by the Deliverables list — verified via a single `grep -rl` across all 6 files before ticking checkboxes.
- Phase 6 (R7 — retiring `self_edit_mode` foreground-await defensiveness) will cite this phrase as the documented trust contract; do not reword it there — extend the surrounding prose instead.
**Pitfalls & guidance:**
- `lazy-batch-parallel/SKILL.md`'s Step 3 preamble sentence ends with a colon introducing a numbered list (`... unaffected):` → `1. **Probe:** ...`). Inserting a new sentence before that colon requires re-homing the colon onto the new final sentence, not leaving a stray `.:`. Caught and fixed during this batch — re-read the surrounding numbered-list-intro punctuation before finalizing an insert like this in list-generating prose.
- `lazy-batch-cloud/SKILL.md`'s HARD CONSTRAINTS preamble ("Constraints 1-9 mirror /lazy-batch's HARD CONSTRAINTS 1-9; constraint 10 is cloud-only") was already stale before this batch (constraint 11 existed undocumented); the new constraint 12 is consistent with that pre-existing gap and was left as-is (out of this phase's scope).
- This feature's `PHASES.md` template has no per-phase `**Status:**` line (unlike some other features' PHASES.md); left that convention alone rather than introducing a new field shape only for Phase 1.
**Files modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — awareness note in both turn-end variants.
- `user/skills/lazy-batch/SKILL.md` — new HARD CONSTRAINT 11 + dispatch-policy paragraph appendix.
- `user/skills/lazy-batch-parallel/SKILL.md` — new HARD CONSTRAINT P8 + Step 3 lane-loop paragraph appendix.
- `user/CLAUDE.md` — `<orchestration>` "One writer per file" reconciliation.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — new HARD CONSTRAINT 12 + Cloud-specific paragraph appendix.
- `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` — new paragraph beside the HARD REQUIREMENT list.
- `docs/features/concurrent-worktree-agent-coordination/PHASES.md` — Phase 1 deliverables ticked.
- `docs/features/concurrent-worktree-agent-coordination/plans/all-phases-concurrent-worktree-agent-coordination-part-1.md` — WU-1..4 checkboxes ticked, frontmatter flipped to `Complete`.

## Phase 2 — Git safety (fetch+ff-before-push, bounded non-ff retry, pathspec commits, friction carve-out)

#### Implementation Notes (Phase 2 — Batch 1: WU-1 + WU-2)
**Completed:** 2026-07-18 (Batch 1; WU-3 prose is Batch 2)
**Work completed (Batch 1, file-disjoint parallel dispatch — 2 test + 2 impl Sonnet sub-subagents):**
- **WU-1** `git_safe_push(repo_root, *, branch=None, remote="origin", run=None, sleep=None, max_retries=3) -> dict` added to `lazy_core/runtimeplane.py` (@2488), registered in the PEP-562 facade map `lazy_core/__init__.py` (@560, `"git_safe_push": "runtimeplane"`). Each attempt: `fetch <remote>` → `merge --ff-only <remote>/<branch>` → `push <remote> <branch>`; on a non-ff push rejection it re-fetches+re-ffs and retries, bounded at `max_retries` push attempts total; returns `{"status": "pushed"|"conflict", "retried": n}`. NEVER composes `--force`/`-f`/`--force-with-lease` (asserted across every composed argv by `test_git_safe_push_never_composes_force`). Best-effort/never-raises, injected `run`/`sleep` seam for hermetic tests (`_FakeGitCompleted` fakes, no real git/network).
- **WU-2** `detect_cycle_bracket_friction` (`lazy_core/markers.py`) gained optional kwarg `concurrent_writer_commits: int | None = None` (@1707). In the signal-(b) `unexpected-commits` branch ONLY, a non-negative int makes the budget comparison use `max(0, commits_since - concurrent_writer_commits)`; `None`/absent ⇒ byte-identical to pre-WU-2 (the fail-safe/ambiguous path — an unknown concurrent count never suppresses a runaway). Guarded with `isinstance(...,int) and not isinstance(...,bool) and >=0`.
**Integration notes / ⚖ scope disclosure (READ BEFORE Phase 4):**
- **The WU-2 carve-out is a CAPABILITY in Phase 2, DORMANT in production.** The caller `cycle_end_friction_check` does NOT yet compute/pass a `concurrent_writer_commits` value (it defaults to `None`), so the 2026-07-18 same-machine/same-identity false-friction incident is NOT yet suppressed end-to-end. This is deliberate + honest: on a single machine every session shares one git identity, so there is no sound deterministic committer-based signal to attribute a begin..HEAD commit to a concurrent writer vs. this cycle's own work. The sanctioned-concurrent-writer IDENTITY that feeds this arrives with the lane/lease machinery in the conflict-routing (Phase 4) + merge-back (Phase 5) phases — wire the caller there, off the lane's own commit provenance, NOT off committer email. The plan's "reuse WU-1's fetch context" pointer is the intended eventual signal source. Validation row 1 is satisfied at the `lazy_core` friction-detector-test level (the detector suppresses when told); production activation is a Phase-4/5 wiring item.
- **TERTIARY descoped:** the plan listed an optional `lazy-state.py` in-file `--test` `[process-friction]` fixture. Descoped this batch (would force a byte-pinned baseline regen for coverage the deterministic `test_markers.py` unit tests already provide) — `lazy-state.py` + `tests/baselines/` left untouched.
**Verification (independent orchestrator re-run):** `pytest test_runtimeplane.py test_markers.py` 347 passed; full `pytest tests/test_lazy_core/` 1261 passed; `lazy-state.py --test` + `bug-state.py --test` PASS; `lazy_parity_audit.py --repo-root .` exit 0.
**Files modified (Batch 1):** `user/scripts/lazy_core/runtimeplane.py`, `user/scripts/lazy_core/__init__.py`, `user/scripts/lazy_core/markers.py`, `user/scripts/tests/test_lazy_core/test_runtimeplane.py`, `user/scripts/tests/test_lazy_core/test_markers.py`.
