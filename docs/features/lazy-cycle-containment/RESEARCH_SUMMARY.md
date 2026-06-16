# Research Summary — Lazy Cycle Containment

> Research waived (internal harness mechanics, 2026-06-16). This summary gates downstream
> workflow (`/spec-phases`, `/write-plan`). Evidence base: `RESEARCH.md` (the two 2026-06-16
> retros + the live enforcement machinery this feature extends).

## Key findings

1. **The one-cycle boundary (HARD CONSTRAINT 4) is prose-only — there is no mechanical, in-flight
   enforcement.** A dispatched cycle subagent has `Bash`/`Edit`/`Write` + can run `lazy-state.py`,
   so it can reproduce the batch loop inline. Demonstrated live: one dispatch → 14 commits / 4
   features / ~40 min, including orchestrator-only `--run-end` + `dev:kill`.
2. **Every existing guard is post-return.** `--verify-ledger`, the retro force-cap, and R-EP-1/2
   all run after the dispatch returns; R-EP-1/2 additionally invert under the inline-override
   branch, so the rubric's only hard cap cannot even *see* a runaway.
3. **The loop needs the next-route probe.** The inline loop's formation primitive is the
   subagent calling `lazy-state.py` to get its next route. Denying that one call in-flight is the
   highest-leverage chokepoint.
4. **The machinery to do this already exists** (run marker + PreToolUse hooks + state-script
   refusals from `turn-routing-enforcement` / `lazy-validation-readiness` Phase 7) — this feature
   reuses the pattern at *dispatch-window* scope.

## Adopted into the spec

- **Defense-in-depth, 4 layers** (operator-chosen): cycle-subagent context marker (C1) →
  PreToolUse in-flight deny of next-route probe + lifecycle ops + 2nd-feature commit (C2) →
  refuse-by-construction in `lazy_core.py` (C3) → explicit cycle-prompt terminal stop (C4).
- **Detection layer:** R-O-9 retro rule keyed on git+jsonl (C6) — always available.
- **Secondary fixes folded in (operator-chosen "include all"):** recovery-dispatch scope
  hardening (C5), R-V-1 mechanics-silent reinforcement, and the `plan-feature`
  Decision-Classification Ledger (C7).

## Pitfalls to address during implementation

- **Fail-open the hook.** A broken containment hook must never wedge the pipeline — the C3
  state-script refusal is the backstop. Mirror the existing route-inject fail-open breadcrumb.
- **Clear the marker on EVERY return path.** A `--cycle-begin` without a matching `--cycle-end`
  on a halt/error path would leave the marker set and block the orchestrator's own next ops.
  Self-healing staleness on the next `--cycle-begin` covers a crash, but the skills must clear
  explicitly on success/halt/error.
- **Coupled-trio mirror.** The `--cycle-begin`/`--cycle-end` bracket and the cycle-prompt stop
  section must land identically in `/lazy-batch`, `/lazy-bug-batch`, `/lazy-batch-cloud`
  (CLAUDE.md coupling rule).
- **Allow-list the narrow ops meta-dispatches need** (`--neutralize-sentinel`, `--verify-ledger`)
  so apply-resolution / recovery subagents are not falsely denied.

## No baseline decisions need revisiting

The baseline SPEC was authored with this evidence already in hand (research waived up front), so
there are no research-driven reversals. The two Open Questions (commit-count ceiling default;
per-`kind` deny-set split) are tuning, not design forks.
