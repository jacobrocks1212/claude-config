# Implementation Phases — Unqueued Fixed-without-receipt dirs perpetual diagnostic noise

**Status:** Fixed

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; this bug's Fix Scope is
pure data remediation via an existing script-owned writer, verified with a live read-only CLI run.

## Validated Assumptions

- **All 7 dirs the SPEC names are now receipted AND archived**, mooting both the receipt debt and
  the diagnostic's re-emission. Verified live 2026-07-12: `efficacy-future-check-unenforced-
  orchestrator-prose`, `no-mid-run-observed-friction-harden-dispatch`, and all 5
  `subagent-baseline-*` dirs are present under `docs/bugs/_archive/` (not `docs/bugs/`), each
  carrying a `FIXED.md`. This happened as part of the SAME reconciliation sweep
  (`fixed-bugs-unarchived-fsck`, commit `efaf93b3`) that this sibling bug's Phase 1 also cites —
  that sweep's `--backfill-receipts` step is the exact remediation this bug's own Fix Scope
  prescribes.
- **`_find_open_bug_dirs` no longer surfaces any of the 7** — they are one level BELOW `docs/bugs/`
  no longer (moved to `_archive/`, which the scan explicitly skips), so the diagnostic-emission
  code path (`_diag("unqueued Fixed-without-receipt dir surfaced for receipt gate: …")`) has no
  input to fire on for these dirs.
- **`python3 user/scripts/bug-state.py --backfill-receipts --repo-root .` on the current tree
  returns `{"backfilled": [], "count": 0}`** — confirming there is no remaining receipt debt of
  this class anywhere in the repo (archived or not).

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC. This bug is explicitly the sibling/scoped-narrower cousin
of `fixed-bugs-unarchived-fsck` (its own `**Related:**` line cross-links it) — both were remediated
by the same underlying sweep commit; this bug's closure is purely a confirmation that the SPEC's
own prescribed Fix Scope (data remediation, no code change, no signal suppression) was in fact
carried out, with zero net-new work required in this pass.

---

### Phase 1: Confirm the data-remediation Fix Scope's own prescription was executed; no residual work

**Status:** Complete — moot by a prior sweep (commit `efaf93b3`), re-verified this pass.

**Scope:** The SPEC's Fix Scope is exactly one action: run `--backfill-receipts` and commit the
receipts, with an explicit "no suppression, no threshold change, no diagnostic removal" guard-rail.
That action landed as part of the `fixed-bugs-unarchived-fsck` reconciliation sweep before this
bug's own pickup. This phase re-verifies the prescription was actually carried out (not merely
claimed) and that the diagnostic genuinely no longer fires for these 7 dirs.

**TDD:** no (a one-time data-remediation confirmation; no new code, per the SPEC's own explicit
"no code change" framing).

**Deliverables:**
- [x] Re-verified all 7 named dirs (`efficacy-future-check-unenforced-orchestrator-prose`,
  `no-mid-run-observed-friction-harden-dispatch`, `subagent-baseline-claude-md-diet`,
  `subagent-baseline-cognito-mcp-hygiene`, `subagent-baseline-cognito-plugin-scoping`,
  `subagent-baseline-dispatch-guidance`, `subagent-baseline-skill-surface-bloat`) each carry a
  `FIXED.md` and sit under `docs/bugs/_archive/`.
- [x] Re-ran `python3 user/scripts/bug-state.py --backfill-receipts --repo-root .` — confirmed
  `{"backfilled": [], "count": 0}` (no remaining debt of this class).
- [x] No diagnostic-suppression, threshold change, or signal removal was made anywhere in
  `_find_open_bug_dirs` — the honest completion-integrity signal remains fully intact for any
  FUTURE Fixed-without-receipt dir; only the 7 already-adjudicated dirs' underlying debt was paid.

**Implementation Notes:** No files were touched by THIS phase in this pass — the prescribed
remediation was already executed by a prior session's sweep, and this phase is a verification-only
re-confirmation that closes the bug honestly (per the "close as fixed-by-sweep with the SPEC's own
reasoning if nothing remains" instruction).

**Minimum Verifiable Behavior:** `find docs/bugs/_archive -maxdepth 1 -iname
"subagent-baseline-*" -o -iname "efficacy-future-check-unenforced-orchestrator-prose" -o -iname
"no-mid-run-observed-friction-harden-dispatch"` under `docs/bugs/_archive/` lists all 7 dirs;
`python3 user/scripts/bug-state.py --backfill-receipts --repo-root .` reports `count: 0`.

**Runtime Verification:** N/A — data remediation, no app runtime.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** None (first phase).

**Files likely modified:** None (verification-only; the remediation itself landed in the
`fixed-bugs-unarchived-fsck` sweep commit `efaf93b3`).

**Testing Strategy:** Live read-only CLI confirmation (`--backfill-receipts` dry-count) + a
filesystem existence check against `docs/bugs/_archive/`.

**Integration Notes for Next Phase:** None — final phase. The `__mark_fixed__` gate (applied here
directly per the operator-directed-interactive protocol) flips `**Status:**` and writes `FIXED.md`,
whose body honestly records this as a fixed-by-sweep closure with zero net-new code.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews — N/A
for this operator-directed-interactive close-out.)_
