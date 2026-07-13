# Fixed bugs never archived — out-of-pipeline fixes strand dirs outside `_archive/` and no fsck asserts the invariant — Investigation Spec

> 18 directories under `docs/bugs/` carry `**Status:** Fixed` but sit OUTSIDE `docs/bugs/_archive/`.
> The archive-on-fix contract (`__mark_fixed__` receipt → `--archive-fixed` git mv) only fires on the
> pipeline path; out-of-pipeline fixes (harden-harness batch commits, in-session manual fixes) mint
> `Status: Fixed` and stop. 13 of the 18 have valid `FIXED.md` receipts and were simply never moved;
> 5 (`subagent-baseline-*`) are Fixed WITHOUT receipts, which autodiscovery re-surfaces as an anomaly
> on every scan. No gate or lint asserts either invariant, so the debris only accumulates.

**Status:** Fixed
**Priority:** P2
**Last updated:** 2026-07-12
**Related:** `user/scripts/lazy_core.py` `archive_fixed()` (~line 6126 — the script-owned archive mechanics); `user/scripts/bug-state.py` `--archive-fixed` (CLI, help ~line 6793: "Run AFTER `--apply-pseudo __mark_fixed__`") and `_find_open_bug_dirs()` (~lines 533–590 — the autodiscovery skip/surface logic); `user/skills/lazy-bug-batch/SKILL.md` lines 42, 438–439 (the in-pipeline archive step); `user/skills/harden-harness/SKILL.md` (authors bug specs — lines ~119–129 — but carries NO archive/mark-fixed contract); `docs/features/claude-config-ci/` (Draft — the mechanical home for a commit-time fsck lane); `docs/bugs/CLAUDE.md` (lifecycle contract).

## Verified Symptom

Re-verified live 2026-07-11 (`grep -l "Status:.*Fixed" docs/bugs/*/SPEC.md`, receipt check per dir):

**18 dirs are `Status: Fixed` outside `_archive/`.** Split by receipt:

- **13 with a valid `FIXED.md` receipt (`kind: fixed`)** — the move never happened:
  `build-queue-hygiene-dot-source-discarded-in-child-scope`, `build-queue-recycle-kills-concurrent-worktree-build`,
  `operator-checkpoint-resume-counter-reset`, `pr-review-artifact-format-drift-breaks-lifespan-parsers`,
  `pr-review-ema-calibration-statistical-design-drives-lane-death`, `pr-review-pending-calibration-marker-unconsumable-nonbuddy`,
  `pr-review-plugin-cache-split-brain-freezes-weights`, `pr-review-postprocess-dedup-scope-filter-silent-drops`,
  `pr-review-source-weights-drift-zeroes-opus-lane`, `sh-exe-crash-masks-successful-build-queue-run`,
  `subagent-backgrounds-verification-ends-turn-before-green`, `worktree-claude-doc-drift`,
  `write-plan-plans-bypass-build-queue-skills`.
- **5 Fixed WITHOUT any receipt** — the `subagent-baseline-*` family (`claude-md-diet`, `cognito-mcp-hygiene`,
  `cognito-plugin-scoping`, `dispatch-guidance`, `skill-surface-bloat`). Their SPEC headers say it outright:
  `**Fixed:** 2026-07-09 (in-session, outside the bug-pipeline queue — no FIXED.md receipt by design)`.

Downstream consequences, each verified:

1. **Autodiscovery anomaly on every scan.** `bug-state.py::_find_open_bug_dirs` (docstring + code,
   ~lines 540–582): a Fixed dir WITH receipt is skipped as "genuinely done" — *wherever it sits*;
   a Fixed dir WITHOUT receipt is deliberately NOT skipped — it emits
   `_diag("unqueued Fixed-without-receipt dir surfaced for receipt gate: …")` and is returned so the
   queue-walk receipt gate fires `TR_COMPLETION_UNVERIFIED`. The 5 receipt-less dirs re-trigger this
   on every load.
2. **`docs/bugs/queue.json` still carries 3 of the Fixed dirs** (`build-queue-recycle-kills-concurrent-worktree-build`,
   `write-plan-plans-bypass-build-queue-skills`, `worktree-claude-doc-drift`) — `archive_fixed` step 6
   is the queue trim, and it never ran.
3. **Open-backlog views are polluted:** any `docs/bugs/` enumeration (incident-scan dedup, the
   reconsider/canary once-ever guards, future spec authors checking for prior art, the `LAZY_QUEUE.md`
   bug table's source scan) walks 18 dirs that are actually done. A future author greps, sees a live-looking
   dir, and re-files or re-investigates a fixed defect.

## Root Cause

**Classification: `missing-contract` (out-of-pipeline fix paths) + `missing-gate` (no fsck asserts the invariants).**

The archive contract is real but **only wired into the pipeline path**. `bug-state.py` line 17 states it:
`__mark_fixed__ (FIXED.md receipt → Status: Fixed + git mv → _archive/)` — mechanically that is TWO
separate CLI acts: `--apply-pseudo __mark_fixed__` (sole author of the receipt + status flip) followed by
`--archive-fixed <spec_path>` (`lazy_core.archive_fixed`: evidence header, `git mv` with retry, inbound-ref
repoint, queue trim, commit). `/lazy-bug-batch` runs both (SKILL.md lines 42, 438–439). Everything else runs
neither:

1. **Batch/out-of-pipeline fix commits hand-write the receipt and stop.** Verified via `git log` on the
   receipts: `00b210a` ("… 5 bugs fixed") minted `worktree-claude-doc-drift` + `subagent-backgrounds-…`
   receipts; `36fa9b4` (pr-review v3.0.0, "+ 6 bug fixes") minted the six `pr-review-*` receipts;
   `c90e2db` minted `build-queue-hygiene-…`. These sessions (harden-harness and kin) honored the
   receipt discipline but had no contract telling them the archive step exists —
   `user/skills/harden-harness/SKILL.md` covers spec authoring (~lines 119–129) and never mentions
   `--archive-fixed`, `_archive/`, or `__mark_fixed__`.
2. **In-session manual fixes flip `Status: Fixed` with no receipt at all** — the 5 `subagent-baseline-*`
   dirs, explicitly annotated "no FIXED.md receipt by design". That "design" collides with the
   machine's contract: Fixed-without-receipt is precisely the state `_find_open_bug_dirs` treats as a
   completion-integrity violation, forever.
3. **No gate asserts the end state.** `_find_open_bug_dirs` *silently skips* Fixed+receipt dirs rather than
   flagging their location; nothing lints `Fixed ⇒ (receipt ∨ Won't-fix)` or `Fixed+receipt ⇒ under _archive/`;
   nothing flags queue.json rows pointing at Fixed dirs. The debris is invisible until someone greps.

## Fix Scope (Concluded)

1. **One-time reconcile sweep (script-owned, per bug):** for each of the 13 receipted dirs run
   `python3 user/scripts/bug-state.py --repo-root . --archive-fixed docs/bugs/<id>` — `archive_fixed`
   already handles everything (receipt gate, `**Fixed:**`/`**Fix commit:**` evidence header, `git mv`
   with Windows retry/backoff, inbound-ref repoint via `git grep`, queue trim for the 3 stale
   queue.json rows, one commit per bug). No new code needed for this half.
2. **Resolve the 5 receipt-less `subagent-baseline-*` dirs** per D1: mint honest backfilled receipts
   (`kind: fixed`, with an explicit out-of-pipeline/backfilled provenance note — the
   `backfilled-unverified` receipt precedent) and archive them, or flip to `Won't-fix` (receipt-exempt;
   `archive_fixed` accepts it) where the fix claim cannot be evidenced.
3. **`bug-state.py --fsck` (new read-only lint mode)** failing on: (a) `Status: Fixed` + valid receipt
   outside `_archive/`; (b) `Status: Fixed` without receipt (and not Won't-fix); (c) a queue.json entry
   whose `spec_dir` is Fixed or archived. Read-only, exit non-zero with named violations — runnable
   standalone, at `--run-end`, and as a lane in `docs/features/claude-config-ci/` when that Draft lands
   (cross-linked there rather than re-building CI here). Pytest coverage per violation class.
4. **Contract fix for the out-of-pipeline path:** `harden-harness` (and the manual-fix guidance in
   `docs/bugs/CLAUDE.md`) gains the rule: a session that fixes a `docs/bugs/` defect out-of-pipeline
   MUST either finish with receipt + `--archive-fixed`, or leave `**Status:**` untouched and let the
   bug pipeline drive completion — never a bare `Status: Fixed` flip. Re-project skills + `lint-skills.py`
   after the edit, per house rule.

## Decisions

- **D1 — Disposition of the 5 receipt-less dirs (SURFACE to operator):** backfill honest receipts + archive
  (recommended — the fixes demonstrably landed 2026-07-09 and the dirs self-document it) vs `Won't-fix`
  re-disposition vs re-open. Recommendation: backfilled receipt carrying an explicit
  `out-of-pipeline fix, receipt backfilled <date>` note — honesty over ceremony, mirroring the
  `backfilled-unverified` receipt precedent.
- **D2 — fsck home:** new `--fsck` flag on `bug-state.py` (recommended — the invariants are
  bug-pipeline-owned and the parsing helpers `spec_status`/`has_completion_receipt` already live there)
  vs a `doc-drift-lint.py` rule. Either way the mechanical trigger rides `claude-config-ci`.
- **D3 — Sweep commit granularity:** keep `archive_fixed`'s per-bug commit design (13 small commits) —
  it is idempotent, resumable after partial failure, and each commit is the bug's terminal audit record.
  Do not batch.
