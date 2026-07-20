# verify_ledger mis-scoped for planning cycles + ambiguous dir-vs-file arg

**Status:** Concluded
**Discovered:** 2026-07-16 (observed-friction, AlgoBooth `/lazy-batch` bug pipeline, item `adhoc-hydra-load-code-mcp-tool`; a plan-bug cycle)
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage + the completion `--verify-ledger` gate); `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`; coupled pair `lazy-batch` ↔ `lazy-bug-batch`.

## Summary

Two independent latent inconsistencies in the completion-ledger gate `lazy_core.verify_ledger`
(exposed via `lazy-state.py --verify-ledger` and `bug-state.py --verify-ledger`), surfaced by a
plan-authoring (`/plan-bug`) cycle:

1. **SCOPE (design fork → NEEDS_INPUT).** `--verify-ledger` is the COMPLETION gate: it checks
   `plan_complete` (a plan is `status: Complete`) and `deliverables_done` (zero unchecked
   deliverable/WU rows). The cycle-subagent turn-end contract in
   `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (the `@section turn-end`
   blocks at the workstation copy and the cloud copy) injects the "TERMINAL VERIFY GATE" —
   run `--verify-ledger` and "RECONCILE ... RE-RUN the verifier until `ok` is true" — with
   `skills=all`. A PLANNING cycle (`spec-phases` / `write-plan` / `plan-bug` / `plan-feature` /
   `spec` / `spec-bug`) authors a `Ready` plan with intentionally-unchecked deliverables, so
   `verify_ledger` STRUCTURALLY returns `ok:false` (`plan_complete=false` and/or
   `deliverables_done=false`). The "reconcile until ok:true" instruction is then UNSATISFIABLE
   without fabricating completion (flipping `Ready`→`Complete` and ticking unimplemented
   deliverables — both forbidden by the `@section status-honesty` contract).

2. **ARG AMBIGUITY (mechanical).** `verify_ledger(repo_root, spec_path, ...)` treats `spec_path`
   as the feature/bug **directory** (it computes `spec_path / 'PHASES.md'`, scans the dir for
   plans). But the cycle-prompt metavar reads as the SPEC.md **file**
   (`--verify-ledger <spec_path>`), so a caller can pass `.../SPEC.md`. Passing the FILE yields a
   MISLEADING verdict rather than an error: `spec_path` becomes `.../SPEC.md`, so
   `spec_path/'PHASES.md'` = `.../SPEC.md/PHASES.md` (never exists), the plan scan finds nothing,
   and the four checks evaluate against a phantom directory — a false `plan_complete` (absent
   plans are treated as absent-by-design → True) or a false `deliverables_done=false`
   ("PHASES.md absent"), depending on tree state. The verdict is silently wrong in a
   direction that depends on the tree.

## Verified symptom / reconstruction

- **Route.** Bug pipeline cycle-subagent runs a planning sub-skill (`/plan-bug`), authoring a
  `Ready` plan. At turn-end the injected `@section turn-end` "TERMINAL VERIFY GATE" (item 3ii/iii)
  directs it to run `bug-state.py --verify-ledger <spec_path>` and reconcile until `ok:true`.
- **Divergence.** `verify_ledger` returns `ok:false` by construction for a `Ready` plan → the
  reconcile loop cannot terminate honestly → friction (the orchestrator observed it mid-run).
- **Corroborating asymmetry (ARG).** `lazy-state.py` ALREADY normalizes a `.md` arg to its parent
  dir (`_vl_path.parent if _vl_path.suffix == ".md" else _vl_path`, lazy-state.py ~13273-13274),
  but `bug-state.py` passes `Path(args.verify_ledger)` RAW to `verify_ledger` and uses
  `Path(args.verify_ledger).resolve().name` as the `gate-refusal` telemetry `item_id`
  (bug-state.py ~8910-8919) — a coupled-pair drift. A file-arg to `bug-state.py` thus both
  misleads the verdict AND stamps a wrong `item_id` (`"SPEC.md"`).
- **Precedent for SCOPE.** The ORCHESTRATOR already scopes its OWN guardrail-D verify-ledger
  (`lazy-batch/SKILL.md` Step 1e.4a) to run "When the cycle that just returned was `/execute-plan`
  or `/mcp-test`". The cycle-subagent turn-end path (`skills=all`) is INCONSISTENT with that
  already-shipped scoping — it fires the same gate on cycles the orchestrator would not.

## Root cause

- **SCOPE:** `ambiguous-prose` / gate-semantics — the `@section turn-end` completion-gate substep
  is injected `skills=all`, applying a completion-only gate to planning skills that have no
  Complete ledger to verify. Two viable designs (scope the verify-ledger substep to
  completion-capable skills, mirroring guardrail-D; OR add a "planning-ok" verdict mode to
  `verify_ledger`) with differing terminal-guarantee tradeoffs → operator-owned fork.
- **ARG:** `script-defect` + coupled-pair drift — `verify_ledger` and its callers disagree on
  whether `spec_path` is a dir or a file; the normalization exists in one caller
  (`lazy-state.py`) but not the source function or the coupled `bug-state.py`.

## Fix scope

- **ARG (mechanical, this round):** normalize `.md`→parent INSIDE `verify_ledger` (gates.py) so
  the function and EVERY caller agree by construction (fixes direct callers + any future one);
  mirror `bug-state.py` to `lazy-state.py`'s wrapper so its `gate-refusal` `item_id` is the
  bug-dir name, not `"SPEC.md"`; add a regression test that a file-arg produces the same verdict
  as its parent dir. Land under `harden(script):` with full gates.
- **SCOPE (fork, this round):** surface via `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md`
  decision 11 with the two designs, the completion-capable skill list, and a recommendation.
  No cycle-prompt semantics changed silently.
