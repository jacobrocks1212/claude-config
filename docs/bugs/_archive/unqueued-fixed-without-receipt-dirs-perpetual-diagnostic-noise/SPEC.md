# Unqueued Fixed-without-receipt bug dirs surface as perpetual per-probe diagnostic noise — Investigation Spec

> `bug-state.py`'s `compute_state` surfaces ~7 unqueued `Status: Fixed` bug dirs that lack a
> FIXED.md receipt as a `_diag` on EVERY probe. These were fixed inline (outside the bug pipeline,
> "no receipt by design"), so the honest completion-integrity signal never clears and drowns real
> diagnostics. The sanctioned resolution is to pay the debt via `--backfill-receipts`, not to
> suppress the signal.

**Status:** Fixed
**Severity:** P3
**Discovered:** 2026-07-12
**Placement:** docs/bugs/unqueued-fixed-without-receipt-dirs-perpetual-diagnostic-noise
**Related:** `bug-state.py::_find_open_bug_dirs` (the diagnostic emit site, ~line 577); `bug-state.py::backfill_receipts` (~line 1720, the sanctioned grandfather writer); the receipt-gated-completion contract (`user/scripts/CLAUDE.md` → "Completion is receipt-gated"); `docs/bugs/fixed-bugs-unarchived-fsck` (the adjacent unarchived-fixed-bugs concern — out of scope here).

---

## Verified Symptom

`_find_open_bug_dirs` emits, for each unqueued `Status: Fixed` dir lacking a valid FIXED.md
receipt, a `_diag("unqueued Fixed-without-receipt dir surfaced for receipt gate: …")`. Seven such
dirs currently exist:

- `efficacy-future-check-unenforced-orchestrator-prose`
- `no-mid-run-observed-friction-harden-dispatch`
- `subagent-baseline-claude-md-diet`
- `subagent-baseline-cognito-mcp-hygiene`
- `subagent-baseline-cognito-plugin-scoping`
- `subagent-baseline-dispatch-guidance`
- `subagent-baseline-skill-surface-bloat`

Each SPEC states the bug was fixed in-session, outside the bug-pipeline queue — "no FIXED.md
receipt by design." Because they are terminal-by-intent yet unreceipted, they re-emit their
diagnostic on every probe and never clear.

## Root Cause

**Not a code defect — the diagnostic is working as designed.** The Fixed-without-receipt diagnostic
is a correct, honest completion-integrity signal: a `Fixed` claim with no gated receipt is real
debt the operator should see. The friction is that seven dirs are genuinely done (fixed outside the
pipeline) and the debt was never paid, so the signal is permanently ON. Suppressing the diagnostic
for "terminal-by-intent" dirs would hide a genuine integrity signal (gate-weakening-adjacent) and is
rejected. The harness already provides the sanctioned resolution: `--backfill-receipts`, which
grandfathers pre/out-of-gate completions as `provenance: backfilled-unverified` — honest debt
recorded, not silenced.

## Fix Scope

Data remediation via the existing script-owned writer (no code change, no signal suppression):

- Run `python3 user/scripts/bug-state.py --backfill-receipts --repo-root .`, which writes a
  `FIXED.md` (`provenance: backfilled-unverified`, with a grandfather body note) for every
  Fixed-without-receipt dir. These dirs then carry a receipt → `_find_open_bug_dirs` skips them as
  genuinely done → the perpetual diagnostic clears. The receipt honestly records that the fix was
  NOT gate-verified (re-validate if load-bearing) — it does not fabricate verification.
- Commit the receipts. No suppression, no threshold change, no diagnostic removal.
