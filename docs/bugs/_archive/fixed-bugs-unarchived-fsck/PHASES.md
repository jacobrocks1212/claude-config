# Implementation Phases — Fixed bugs never archived — reconciliation sweep + fsck invariant

**Status:** Fixed

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; verified via
`python user/scripts/bug-state.py --test` (the repo's in-file smoke harness for `bug-state.py`) and
a live read-only CLI run against the real repo tree.

## Validated Assumptions

- **The reconciliation half (Fix Scope items 1–2) landed in a PRIOR run, before this bug's fsck-lint
  half was picked up.** Verified live 2026-07-12: `git log --oneline -1 efaf93b3` = "archive 20
  Fixed+receipted bug dirs, drop 3 stale queue rows — mechanical reconciliation half; fsck lint
  remains queued". Re-verified the SPEC's own claims are now STALE in the good direction: `grep -l
  "^\*\*Status:\*\* Fixed" docs/bugs/*/SPEC.md` (outside `_archive/`) returns **zero** matches (the
  SPEC's own header block matches literal "Status:.*Fixed" prose in blockquotes, not an actual
  `**Status:**` field); all 13 receipted dirs + all 5 `subagent-baseline-*` dirs are now under
  `docs/bugs/_archive/`, each carrying a `FIXED.md` (the 5 baseline dirs carry
  `provenance: backfilled-unverified` receipts, confirming D1's backfill+archive choice was already
  applied); `docs/bugs/queue.json` no longer references any of the 3 previously-stale rows.
- **`bug-state.py --fsck` on the CURRENT repo tree returns `{"ok": true, "violations": []}`** —
  confirming the reconciliation sweep is complete and self-consistent before this bug's new lint
  code is even asked to certify it.

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC. D2 (fsck home) is resolved per the SPEC's own recommendation
— `bug-state.py --fsck` (not a new `doc-drift-lint.py` rule) — because the invariants are
bug-pipeline-owned and the parsing helpers (`spec_status`/`has_completion_receipt`) already live
there. The mechanical CI trigger (`docs/features/claude-config-ci/`) remains a separate Draft
feature; this phase only builds the deterministic checker itself.

---

### Phase 1: One-time reconciliation sweep (13 receipted dirs + 5 receipt-less `subagent-baseline-*` dirs)

**Status:** Complete — landed in a prior session (commit `efaf93b3`), re-verified this pass.

**Scope:** Archive every `Status: Fixed` dir outside `_archive/`; backfill honest receipts for the
5 receipt-less `subagent-baseline-*` dirs per D1 (backfilled + archived, not `Won't-fix`
re-disposition — the fixes demonstrably landed 2026-07-09 and the dirs self-documented it).

**TDD:** no (a one-time data-remediation sweep via the existing `archive_fixed`/`backfill_receipts`
script-owned writers — no new code was needed for this half, per the SPEC's own Fix Scope §1).

**Deliverables:**
- [x] All 13 receipted Fixed dirs (`build-queue-hygiene-dot-source-discarded-in-child-scope`,
  `build-queue-recycle-kills-concurrent-worktree-build`, `operator-checkpoint-resume-counter-reset`,
  `pr-review-artifact-format-drift-breaks-lifespan-parsers`,
  `pr-review-ema-calibration-statistical-design-drives-lane-death`,
  `pr-review-pending-calibration-marker-unconsumable-nonbuddy`,
  `pr-review-plugin-cache-split-brain-freezes-weights`,
  `pr-review-postprocess-dedup-scope-filter-silent-drops`,
  `pr-review-source-weights-drift-zeroes-opus-lane`,
  `sh-exe-crash-masks-successful-build-queue-run`,
  `subagent-backgrounds-verification-ends-turn-before-green`, `worktree-claude-doc-drift`,
  `write-plan-plans-bypass-build-queue-skills`) archived via `--archive-fixed`, each carrying its
  evidence header + git-mv history. Re-verified 2026-07-12: all 13 present under
  `docs/bugs/_archive/`, none remain outside it.
- [x] The 3 stale `docs/bugs/queue.json` rows (`build-queue-recycle-kills-concurrent-worktree-build`,
  `write-plan-plans-bypass-build-queue-skills`, `worktree-claude-doc-drift`) trimmed by the same
  `--archive-fixed` queue-trim step. Re-verified: none of the 3 ids appear in the current
  `queue.json`.
- [x] The 5 `subagent-baseline-*` dirs (D1: backfilled receipt + archive) each carry a `FIXED.md`
  with `provenance: backfilled-unverified` and an explicit out-of-pipeline/backfilled note, and sit
  under `docs/bugs/_archive/`. Re-verified: all 5 present with the expected receipt shape.

**Implementation Notes:** This phase's mechanics were entirely pre-existing (`archive_fixed` +
`backfill_receipts` in `lazy_core.py`/`bug-state.py`); the sweep itself ran in a session prior to
this bug's fsck-lint pickup and is cited here as evidence, not re-executed. No files were touched by
THIS phase in this pass — it is a verification-only re-confirmation.

**Minimum Verifiable Behavior:** `grep -l "^\*\*Status:\*\* Fixed" docs/bugs/*/SPEC.md` (outside
`_archive/`) returns zero paths; `git log --oneline -1 efaf93b3` shows the sweep commit.

**Runtime Verification:** N/A — data remediation, no app runtime.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** None (first phase, already complete at pickup).

**Files likely modified:** None in this pass (prior-session sweep; re-verified only).

---

### Phase 2: `bug-state.py --fsck` (read-only invariant checker) + out-of-pipeline contract doc

**Status:** Complete

**Scope:** Build the deterministic, read-only `--fsck` lint mode (Fix Scope §3) asserting the three
archive-on-fix invariants, and add the out-of-pipeline manual-fix contract to `docs/bugs/CLAUDE.md`
(Fix Scope §4's STATE-lane half — the `harden-harness` SKILL.md prose half is out of lane, see
Implementation Notes).

**TDD:** yes — the `--fsck` bespoke fixture block in `bug-state.py`'s in-file `--test` harness is
written and run before being relied upon below.

**Deliverables:**
- [x] `fsck(repo_root)` (`user/scripts/bug-state.py`) — read-only, walks every on-disk `SPEC.md`
  (archived + unarchived) plus `docs/bugs/queue.json`, returning
  `{"ok": bool, "violations": [{"kind", "bug_id", "detail"}, ...]}` for three violation classes:
  `unarchived-fixed` (Fixed+receipted dir outside `_archive/`), `fixed-without-receipt` (Fixed with
  no valid receipt), `stale-queue-entry` (a queue row pointing at a Fixed/archived dir). Never
  mutates.
- [x] `--fsck` CLI flag wired in `bug-state.py`'s `main()`: exit 0 clean / 1 with named violations
  (JSON to stdout).
- [x] Bespoke fixture block in `run_smoke_tests()` (`fsck-violations` — all three classes fire
  independently + a properly-archived control bug is NOT flagged; `fsck-clean-tree` — a clean tree
  returns `ok: true, violations: []`).
- [x] `docs/bugs/CLAUDE.md`: new "Fixing a bug OUT-OF-PIPELINE (harden-harness, manual in-session
  fixes)" section — the two sanctioned outcomes (finish the contract via `--archive-fixed`, or leave
  `**Status:**` untouched) and a `bug-state.py --fsck` usage/violation reference.
- [x] `user/scripts/CLAUDE.md`: `bug-state.py` row updated to mention `--fsck` (+ the `--ack-deny`
  CLI from the sibling meta-dispatch bug, landed in the same session).
- [x] Live-repo confirmation: `python user/scripts/bug-state.py --repo-root . --fsck` on the real
  claude-config tree returns `{"ok": true, "violations": []}` (Phase 1's sweep left the tree clean).

**Implementation Notes (2026-07-12):** The `harden-harness` SKILL.md prose half of Fix Scope §4 (a
skill-authoring rule telling a harden-harness session to run `--archive-fixed` or leave `Status`
untouched) is `user/skills/**` — explicitly out of this session's STATE lane — and is deferred to a
skills-lane follow-up; the mechanical enforcement (the `--fsck` checker itself) and the
`docs/bugs/CLAUDE.md` contract doc (not a skill file) are both in-lane and landed here. Files:
`user/scripts/bug-state.py`, `docs/bugs/CLAUDE.md`, `user/scripts/CLAUDE.md`.

**Minimum Verifiable Behavior:** `python user/scripts/bug-state.py --test` is GREEN (incl. the new
`fsck-violations`/`fsck-clean-tree` fixtures); `python user/scripts/bug-state.py --repo-root . --fsck`
on the real repo tree exits 0 with `{"ok": true, "violations": []}`.

**Runtime Verification:** N/A — pure Python state-script logic; verified by the in-file smoke
harness (the established verification method for `bug-state.py`, per `user/scripts/CLAUDE.md`).

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phase 1 (the checker is meaningfully tested against a tree that is ALREADY clean;
Phase 1's sweep is why the live-repo confirmation above returns a clean verdict rather than 18
violations).

**Files likely modified:**
- `user/scripts/bug-state.py` — `fsck()`, the `--fsck` CLI flag + handler, the bespoke fixture block.
- `docs/bugs/CLAUDE.md` — the out-of-pipeline contract section.
- `user/scripts/CLAUDE.md` — the `bug-state.py` table row.

**Testing Strategy:** In-file `--test` smoke harness (bug-state.py's established convention — not
pytest); a bespoke block builds a synthetic `docs/bugs/` tree with all three violation classes plus
a clean control bug, asserting the returned dict shape.

**Integration Notes for Next Phase:** None — final phase. The `__mark_fixed__` gate (applied here
directly per the operator-directed-interactive protocol) flips `**Status:**` and writes `FIXED.md`,
citing BOTH phases (the already-landed reconciliation sweep and this pass's fsck lint).

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews — N/A
for this operator-directed-interactive close-out.)_
