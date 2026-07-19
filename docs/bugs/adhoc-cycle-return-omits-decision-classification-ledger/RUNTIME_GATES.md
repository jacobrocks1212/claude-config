# Pending Runtime Gates — adhoc-cycle-return-omits-decision-classification-ledger

Ledger of unchecked `<!-- verification-only -->` PHASES.md rows at plan completion, per
`~/.claude/skills/_components/pending-runtime-gates.md`. This repo declares `MCP runtime:
not-required` for this bug (no `/mcp-test` step downstream) — see the note below on ownership.

## Phase 1 — Add the ledger to the authoritative return contract (root fix)

| Gate row text | How to run it | Owning phase | Date deferred |
|---|---|---|---|
| "A dispatched decision-bearing cycle subagent (`/spec`, `/plan-feature`, `/spec-bug`, or `/plan-bug`) under `--batch`, following the assembled cycle prompt, includes the `### Decision-Classification Ledger` section in its return summary (or the empty-ledger line), so the Step 1d.5 input-audit runs the stronger diff-vs-ledger cross-check (algorithm step 3a/3b) instead of the diff-only fallback (step 3c)." | Observe a live `/lazy-batch` or `/lazy-bug-batch` run: dispatch a decision-bearing cycle (`/spec`, `/plan-feature`, `/spec-bug`, or `/plan-bug`) under `--batch` and confirm its return summary carries the `### Decision-Classification Ledger` section (or the empty-ledger fallback line). The deterministic proxy — `grep -c "Decision-Classification Ledger" user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` returning ≥2 — is already satisfied; this row is the live-runtime confirmation that a real cycle subagent actually follows the updated prompt contract. | Phase 1 | 2026-07-19 |

**Ownership:** this bug's PHASES.md declares `MCP runtime: not-required` — no `/mcp-test` step will ever tick this row. The bug pipeline's `__mark_fixed__` gate (coverage audit + `remaining_unchecked_are_verification_only()`) recognizes this row's `<!-- verification-only -->` marker and will still route the bug to `Fixed`/archive without it being ticked — but no pipeline mechanism actively RUNS the observation described above. This `RUNTIME_GATES.md` ledger is the only record of that pending observation; the next live decision-bearing `--batch` cycle (on any repo running this harness) is the natural opportunity to confirm it, and the operator may tick this row by hand once observed.
