## Pending Runtime Gates — completion-time ledger + summary contract

**Why this component exists.** In manual (non-lazy) workflows and no-MCP repos, unchecked
runtime-verification rows have a named owner but **no mechanism** — the completion headline
semantically overrides the footnote that mentions them. (Subject incident: 57077 — Phase 4
"In-app support view renders retained CP data" was stamped `✅ Complete (backend)` with its
manual Overwatch `:7775` runtime rows never run; the final summary led with "the feature is
complete across all 5 phases" and relegated the pending gates to a trailing footnote. Two days
later the operator's first manual test hit HTTP 500 — `NullReferenceException` in
`PlansService.GetEffectiveSubscription` — and the skipped manual walkthrough was exactly the
step that would have caught it; corrective Phase 8 was required.)

This component does NOT block or delay the `Complete` flip — that flip stays correct (leaving a
plan `In-progress` for a runtime-only remainder loops `lazy-state.py`). It changes the
**completion OUTPUT contract**: pending runtime gates must be enumerated, ledgered, led with,
and explicitly owned.

### MANDATORY behavior at completion time (execute-plan Step 4 / Cognito Part Completion)

1. **Enumerate.** Scan every executed phase for unchecked `<!-- verification-only -->` /
   `**Runtime Verification**` rows. Count = **N**. If N = 0, this component is a no-op —
   complete normally.
2. **Ledger — write/update `RUNTIME_GATES.md` in the feature dir** (beside SPEC.md/PHASES.md).
   One table row per pending gate, columns: **gate row text** (verbatim), **how to run it**
   (the concrete command/URL/walkthrough), **owning phase**, **date deferred**. Idempotent:
   re-running for the same plan REPLACES that plan's section, never duplicates it.
3. **The final summary MUST LEAD with the pending-gate line** — the FIRST substantive line,
   BEFORE any completion language:
   `N MANUAL RUNTIME GATES PENDING — feature not verified end-to-end`
   Anti-pattern (the 57077 failure): "feature is complete…" first, gates as a footnote. The
   gate count leads; completion claims follow it.
4. **Phase status lines carry the count.** Any phase whose runtime rows are pending is stamped
   `✅ Complete — RUNTIME GATES PENDING (N)`, not a bare `✅ Complete`.
5. **No-downstream-owner declaration.** When the plan/repo declares `MCP runtime: not-required`
   (no `/mcp-test` step downstream), the summary MUST state explicitly that `RUNTIME_GATES.md`
   is the **ONLY owner** of these rows — no pipeline gate will hold them; the operator working
   the ledger is the sole remaining mechanism.

### Explicit non-goal

This component does NOT change `_components/completion-integrity-gate.md` or
`lazy_core.remaining_unchecked_are_verification_only()` semantics. The lazy pipeline's
verification-only carve-out stays correct as-is: there, `/mcp-test` + the validation sentinel
own the rows. This contract is additive for the **manual seam only** — the flip still happens;
only the output contract around it changes.

### Consumers / blast radius

- `user/skills/execute-plan/SKILL.md` — Step 4 (Completion), injected via `!cat`.
- `repos/cognito-forms/.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md` —
  Part Completion (feature parts; bug parts already carry the SEAM B symptom gate), referenced
  by read-instruction.

When editing this component, run `grep -rl "pending-runtime-gates.md" ~/.claude/ --include="*.md"`
to confirm the blast radius. This component does not re-teach verification-before-completion or
the symptom-reproduction gate — it owns only the *ledger + summary-ordering* contract for
runtime rows no downstream gate will hold.
