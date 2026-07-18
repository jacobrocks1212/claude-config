# Bug: `--run-end` efficacy-flush gate refuses under a concurrent cross-repo run — the interventions-scope breadcrumb is attributed to the OTHER run's `run_started_at`

**Status:** Open
**Priority:** P1
**Reported via:** AlgoBooth `/lazy-batch` session, 2026-07-18 (operator-directed logging of run friction). Run-blocking for a clean `--run-end`: the terminal path could only complete via the operator-authorization escape (`--efficacy-skip-authorized`), which is a workaround, not a fix.
**Root-cause class:** `script-defect` (breadcrumb run-attribution keys on the flushed-scope's marker, not the invoking run).
**Related:**
- `docs/bugs/_archive/interventions-telemetry-repo-scope-split-brain/` — the ALREADY-FIXED split-brain (Phase-1 merged READ). This bug is the residual WRITE-side / attribution manifestation the archived fix did not cover.
- `docs/bugs/lazy-batch-parallel-run-harness-gaps/` Gap 5 — the sibling efficacy-gate refusal, but for PARALLEL lanes (`parent_run` non-null). Distinct: this bug is a NON-parallel top-level run.
- `docs/specs/turn-routing-enforcement/` — owns the `--run-end` efficacy-coverage gate + the two-scope flush prose (`§1c.6`).
- `docs/bugs/_archive/gate-scope-folds-concurrent-harden-commits/` — adjacent concurrent-writer class (commit-scoping, not breadcrumb-attribution).

## Context

The two-scope efficacy flush (SKILL §1c.6) requires the end-of-run efficacy/canary/incident trio to
run against BOTH the target repo (`--repo-root .`) AND the interventions-bearing scope
(claude-config, where intervention records live). `--run-end` mechanically enforces this: it REFUSES
(exit 1, marker kept) unless a breadcrumb "COVERING THE INTERVENTIONS-BEARING SCOPE for this run" is
present (`efficacy-future-check-unenforced-orchestrator-prose`). Each trio invocation drops a
run-scoped `lazy-efficacy-flush.json` breadcrumb keyed on `run_started_at` + `covered_scopes`.

## Verified Symptom

Live AlgoBooth `/lazy-batch 15` run (`run_started_at: 2026-07-18T18:21:25Z`), which deadlocked on a
separate structural bug and was stopping via an operator-authorized checkpoint. The end-of-run flush
was executed correctly in BOTH scopes:

- `efficacy-eval.py --repo-root .` + `--canary` + `incident-scan.py --repo-root .` (target: AlgoBooth)
- `efficacy-eval.py --repo-root <claude-config>` + `--canary` + `incident-scan.py --repo-root <claude-config>` (interventions scope)

Yet `--run-end --reason checkpoint --operator-authorized` REFUSED **twice**, each time:

```
No efficacy-flush breadcrumb COVERING THE INTERVENTIONS-BEARING SCOPE for this run.
... Run the trio against the interventions-bearing scope and re-invoke --run-end,
or pass --efficacy-skip-authorized ...
[efficacy-future-check-unenforced-orchestrator-prose] [interventions-telemetry-repo-scope-split-brain]
```

### Root cause (reproduced from on-disk breadcrumb state)

A SECOND, unrelated `/lazy-batch` (or `/lazy`/harden) run was **concurrently live in claude-config**
(`run_started_at: 2026-07-18T16:50:52Z`, active cycle `subagent-wedge-backstop-hook`). The two
runs' state lives in per-`repo_key` dirs:

- AlgoBooth run key `37850b6e…`: `lazy-efficacy-flush.json` → `{"run_started_at": "2026-07-18T18:21:25Z", "covered_scopes": ["37850b6e…"], "interventions_covered": false}`
- claude-config run key `853ac81e…`: `lazy-efficacy-flush.json` → `{"run_started_at": "2026-07-18T16:50:52Z", "covered_scopes": ["853ac81e…"], "interventions_covered": true}`

When the AlgoBooth run's cc-scoped `efficacy-eval.py --repo-root <claude-config>` ran, it wrote/updated
the claude-config-key breadcrumb stamped with the **concurrent run's** `run_started_at`
(`16:50:52Z`) — because the breadcrumb-writer reads the run marker present in the flushed scope's
`repo_key` dir (the concurrent run's marker), NOT the invoking run. The AlgoBooth `--run-end` gate
then looks for a breadcrumb with ITS OWN `run_started_at` (`18:21:25Z`) that has
`interventions_covered: true`, finds only its target-scope breadcrumb (`interventions_covered:
false`), and refuses. The interventions-scope breadcrumb it needs exists but is attributed to the
wrong run. **No number of retries fixes it** — the concurrent run keeps owning claude-config's
marker, so the invoking run can never stamp a matching interventions-scope breadcrumb.

## Impact

- A legitimate, fully-executed two-scope flush cannot discharge the `--run-end` gate whenever ANY
  other lazy run is concurrently live in the interventions-bearing (claude-config) repo.
- The only completion path is the operator-authorization escape `--efficacy-skip-authorized`, which
  is recorded as a deliberate SKIP for retro grading — misrepresenting a run that genuinely DID
  flush as one that skipped the flush.
- Concurrent workstation + cloud (or two workstation) lazy runs are an expected configuration, so
  this is not a rare edge.

## Suspected fix direction (for investigation — not locked)

The interventions-scope breadcrumb must be attributed to the **invoking** run, not to whatever run
happens to own the flushed scope's `repo_key` marker. Options to weigh during `/spec-bug`:

1. Have the cc-scoped `efficacy-eval.py` / `incident-scan.py` accept the invoking run's identity
   (e.g. an explicit `--for-run-started-at` / `--attributing-run-key` passed by the orchestrator, or
   read from `LAZY_ORCHESTRATOR` + the invoking run's marker path) and stamp the breadcrumb with THAT
   `run_started_at`, so a cross-repo flush credits the correct run.
2. Have the `--run-end` gate match the interventions-scope breadcrumb by `covered_scopes` +
   freshness relative to the invoking run's `started_at` window, rather than by exact
   `run_started_at` equality (tolerating a concurrent run's marker in the flushed scope).
3. Record the interventions-scope coverage on the INVOKING run's own breadcrumb
   (`interventions_covered: true` written into the AlgoBooth-key breadcrumb) when the cc-scoped trio
   runs, instead of relying on the cc-key breadcrumb.

Any fix must preserve the gate's purpose (a genuinely-skipped flush still refuses) and stay correct
when NO concurrent run exists (the common case the archived split-brain fix already handles).

## Reproduction

1. Start a `/lazy-batch` run in claude-config; let it reach an active cycle (owns claude-config's
   `repo_key` marker).
2. In another repo (e.g. AlgoBooth), run `/lazy-batch`; run the full end-of-run flush in both scopes.
3. `--run-end` → refused with the interventions-scope breadcrumb message, despite the cc-scoped trio
   having run. Inspect the two `lazy-efficacy-flush.json` breadcrumbs — the cc-key one carries the
   concurrent run's `run_started_at`.
