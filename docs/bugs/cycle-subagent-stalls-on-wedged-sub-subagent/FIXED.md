---
kind: fixed
bug_id: cycle-subagent-stalls-on-wedged-sub-subagent
provenance: backfilled-unverified
fixed_by: harden-harness
fix_commits:
  - e7c2b89e
date: 2026-07-18
---

# Fixed — cycle subagent falls back to inline on a wedged sub-sub-agent

Fixed OUT-OF-PIPELINE by harden-harness Round 100 (`e7c2b89e`, `harden(skill-prose):`).

**Fix:** added a `WEDGE RESILIENCE` guardrail to
`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` `@section
workstation-dispatch` — a dispatched sub-sub-agent that returns a total tool-execution
wedge (every tool call erroring before executing, e.g. the depth-2 `No tools needed for
summary` platform limitation) is NOT waited on and NOT re-dispatched; the cycle subagent
performs that work INLINE with its own depth-1 Read/Grep/Glob/Bash and still produces the
skill's deliverable (PHASES.md / plan / tested code).

**Evidence (green gates at fix time):**
- test_lazy_core (pytest package): 1255/1255 passed
- test_hooks.py: 268/268 passed
- lint-skills.py --check-projected --check-capabilities: OK
- lazy-state.py --test / bug-state.py --test: OK
- bug-state.py --fsck: OK (no violations)
- harness-gate.py --staged: in_scope false (prose edit, no control-surface glob touched)

**provenance: backfilled-unverified** — the fix is a cycle-dispatch prose contract; its
runtime effect (a future cycle subagent falling back to inline on a real wedge) is not
mechanically reproducible in a unit test. Verified by the gate battery + emitter
residue/token acceptance, not by a live wedge reproduction.

Archive + provenance-link handed back to the orchestrator (`--archive-fixed` /
`--link-provenance` are cycle-refused for a dispatched harden meta-cycle) — see the Round
100 `Reconciliation` block.
