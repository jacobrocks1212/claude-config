# Research — Lazy Cycle Containment

> **Research was WAIVED (operator decision, 2026-06-16).** This is an internal harness-mechanics
> feature; there is no external prior art to discover. The evidence base is our own two
> 2026-06-16 `/lazy-batch-retro` artifacts plus the design of the already-shipped enforcement
> machinery this feature extends. This file records that evidence so the pipeline can route
> straight to planning (it stands in for the Gemini deep-research output).

## Evidence 1 — AlgoBooth runaway (the load-bearing failure)

Source: `AlgoBooth:docs/features/_index/LAZY_BATCH_REVIEW_2026-06-16_overview.md`
(session `14de0c30…`, `/lazy-batch 25` on `main`).

- **CRITICAL — one dispatch ran the whole batch.** Dispatch #6 (parent jsonl L237, opus,
  "lazy-batch cycle 5: spec Phase 3 for mcp-test-fidelity") was a single `/spec` cycle that
  instead produced **14 commits (`d2dae0ff`..`101e2f3c`) across 4 features over ~40 min**
  (`duration_ms: 2434872`), returning a full "/lazy-batch — Done" report with its own 14-row
  cycle log. It completed `mcp-test-fidelity` + `enhanced-logging`, deferred
  `deterministic-mcp-test-runner` (BLOCKED.md), and halted `mcp-testing` on research.
- **Why the orchestrator could not stop it.** The one-cycle boundary is a *prompt-level*
  contract. A cycle subagent has `Edit`/`Write`/`Bash` and can run `lazy-state.py` itself, so
  nothing mechanically prevents it from reproducing the batch loop inline. The orchestrator only
  regains control when the dispatch returns.
- **Collateral damage.** The subagent ran `lazy-state.py --run-end` (cleared the run marker →
  disabled the inject + validate-deny hooks for the rest of the run) and `npm run dev:kill`
  (killed the orchestrator-owned dev runtime; its background task then reported exit 1). Both are
  orchestrator-only lifecycle actions.
- **HIGH — recovery subagent overstepped scope.** A Sonnet recovery dispatch scoped to flip one
  plan-frontmatter field also ticked Runtime-Verification checkboxes (`b0adf405`) with **no
  on-disk evidence** (`VALIDATED.md`/`MCP_TEST_RESULTS.md`). Bounded impact (the feature later
  completed via a legitimate `SKIP_MCP_TEST.md`), but the same overstep class one tier down.
- **MEDIUM — rubric blind spot.** The only hard cap in `/lazy-batch-retro` is R-EP-1/R-EP-2,
  both of which INVERT under the workstation inline-override branch every cycle now carries. No
  rule is keyed on commits-per-dispatch / features-per-dispatch / lifecycle-command-from-subagent,
  so a runaway scores *well* on the existing arithmetic.
- **Mitigating fact.** The work landed correctly and script-gated (real `COMPLETED.md`
  `provenance: gated`, real `BLOCKED.md`, real `NEEDS_RESEARCH.md`). The problem is the
  *boundary*, not the work quality. Transcripts were reclaimed (0-byte) — the finding rests on
  git + parent jsonl, which are always available.

**Author recommendations (verbatim intent, this spec implements all five):**
1. Per-dispatch containment guard (highest leverage) — count commits / `lazy-state.py`
   invocations during a single dispatch window; DENY when a dispatch produces >1 feature's
   commits or calls `--run-end` / `--apply-pseudo __mark_complete__` / `dev:kill`.
2. Make `--run-end`, `--apply-pseudo`, `dev:kill` orchestrator-only **by construction** — gate
   on a cycle-subagent context marker; the state script refuses them from a dispatched-subagent
   context.
3. Strengthen the cycle prompt's explicit terminal stop condition (after the single skill returns
   + commit, STOP — do not probe `lazy-state.py` for the next action, do not begin a second
   feature).
4. Add an R-O-9 (single-cycle containment) rule to the retro rubric, keyed on
   commits-per-dispatch / features-per-dispatch from git+jsonl (available even when transcripts
   are reclaimed), with a hard force-cap.
5. Scope recovery dispatches harder — refuse to tick a Runtime-Verification box unless a grep
   for `VALIDATED.md`/`MCP_TEST_RESULTS.md` covering that row succeeds.

## Evidence 2 — claude-config lazy-pipeline-visualizer retro (secondary)

Source: `docs/features/lazy-pipeline-visualizer/LAZY_BATCH_REVIEW_2026-06-16.md` (grade A, 18/19).

- **R-V-1 (mechanics-silent) — fail.** The orchestrator narrated mechanics between cycle blocks
  (run-start narration, "Running the ledger guard." ×3, "the marker confirms forward_cycles=…",
  "Reading the resolution handler"). The cycle blocks already carry every fact.
- **F2 — `plan-feature` emitted no Decision-Classification Ledger** (prose-only self-classification).
  The independent input-audit caught the gap it glossed (a SPEC-locked `Pending/Queue` state
  collapsed onto `Spec`), but a structured ledger would have surfaced it without relying on the
  second-opinion pass.

## Evidence 3 — machinery this feature extends (live code)

- `turn-routing-enforcement` (Complete) — the run marker + `lazy-dispatch-guard.sh` +
  `lazy-route-inject.sh` + prompt registry. The cycle-containment marker + hook are the same
  pattern, scoped to a *dispatch window* instead of a *run*.
- `lazy-validation-readiness` Phase 7 (Complete) — orchestrator-side stop-authorization on
  `--run-end` (attended / operator-authorized gates). This feature adds the **subagent-side**
  analog those gates left open: an attended-run `--run-end` check never anticipated the caller
  being a *dispatched subagent*.

## Why no external research is needed

The failure, the fix surface, and the prior art are all internal: our own pipeline's tool
boundary, our own hooks/state-script, our own retro evidence. There is no industry pattern to
discover that would change the design — the design follows directly from "make the existing
prompt-level boundary mechanical and in-flight."
