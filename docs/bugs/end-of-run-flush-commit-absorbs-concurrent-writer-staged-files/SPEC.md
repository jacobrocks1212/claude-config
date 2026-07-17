# End-of-run efficacy flush commit absorbs a concurrent writer's staged files (one-writer coordination gap)

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-17 (observed live: commit `115a991a` "docs(interventions): efficacy verdicts" swallowed a concurrently-running harden agent's Fix-1/2 `docs/bugs/.../SPEC.md` files; Rounds 65-67 each had to isolate their own commit range to clear the resulting whole-range `harness-gate` noise)
**Related:** `intervention-efficacy-tracking` (the efficacy/canary flush); `efficacy-signal-integrity` (KPI scorecard regen); `hardening-intervention-records-unmeasurable-or-missing` (intervention-coverage lint); the `orchestration` one-writer-per-file constitution rule; the coupled trio `/lazy-batch`, `/lazy-bug-batch`, `/lazy-batch-cloud` §1c.6.

## Trigger

The end-of-run efficacy flush (§1c.6.6 — incident-scan / efficacy-eval / canary / KPI scorecard + the orchestrator's `docs(interventions)` commit) stages and commits in **claude-config** (the interventions-bearing scope) even when the run itself targets a DIFFERENT repo (AlgoBooth). When a `/harden-harness` agent is concurrently writing claude-config (a backgrounded observed-friction harden, or a standalone harden the operator launched), the flush's broad directory add absorbs the harden agent's staged, unrelated spec files into the flush commit — attribution and atomicity break, and it inflates the harden agent's whole-range `harness-gate` (the flush's `review_count:` / `SCORECARD.md` edits appear as `gate_weakening` HITs the harden agent did not author).

No work was lost in the observed incident, but the commit boundary is wrong and the coupling is a live one-writer-per-file violation across two concurrent claude-config writers.

## Reconstructed route (divergence point)

- §1c.6 (canonical `/lazy-batch` SKILL, mirrored in `/lazy-bug-batch` + `/lazy-batch-cloud`) instructs the orchestrator to "stage `docs/interventions/` (and any `docs/bugs/reconsider-*` seed) and commit them" and to "stage + commit the regenerated `docs/kpi/SCORECARD.md`". This is prose, not an explicit-pathspec command.
- The orchestrator improvised a broad `git add -A docs/interventions docs/kpi docs/bugs` — far wider than the artifacts the flush actually generated — which staged the concurrent harden agent's `docs/bugs/<slug>/SPEC.md` files and committed them under `docs(interventions): efficacy verdicts`.

**Divergence point:** the flush commit's staging step is a broad directory add, not a scoped add of the specific artifacts the evaluators wrote this run.

## Root cause

**`root_cause_class: missing-contract`** — the flush-commit prose never bounded WHICH paths to stage, so a broad `git add -A docs/*` was a permissible reading. There is no mechanical guarantee that a foreign staged file cannot be absorbed. The orchestrator's flush and a concurrent harden agent are two writers of the same claude-config tree with no coordination on the commit boundary.

## Fix scope

The flush's claude-config commit must stage ONLY the specific artifacts it generated, BY EXPLICIT PATH, and must be structurally incapable of absorbing a concurrent writer's staged files.

- **Prose contract (coupled trio §1c.6).** Replace "stage `docs/interventions/` …" with: stage + commit ONLY the exact `docs/interventions/<id>.md` records the evaluators wrote THIS run (the `verdicts[].id` / canary ids from the efficacy/canary JSON), the regenerated `docs/kpi/SCORECARD.md`, and the specific `docs/bugs/reconsider-<id>/` / `docs/bugs/canary-revert-<id>/` seeds enqueued this run — via a PATHSPEC-SCOPED commit (`git commit -m "…" -- <explicit paths>`), NEVER a broad `git add -A docs/*` / directory add. A pathspec on the commit commits only the named paths from the working tree, so any concurrently-staged foreign file is left untouched (never absorbed). If a foreign staged/dirty claude-config state is present, the flush still commits only its own explicit paths (narrow, never blanket-add).
- **Mechanical enforcement + regression.** `lazy_core.flush_commit_artifacts(repo_root, artifact_paths, message)` encapsulates the sanctioned `git commit -- <pathspec>` mechanism (stage the explicit paths, commit them by pathspec). A temp-git-repo regression asserts that when a FOREIGN file is staged alongside a flush artifact, `flush_commit_artifacts` commits ONLY the artifact and the foreign staged file is NOT absorbed (remains uncommitted).

## Verified symptom → target signal

- **Before:** a broad `git add -A docs/…` + `git commit` absorbs any concurrently-staged `docs/bugs/**` into the flush commit.
- **After (target — the measurable regression):** `flush_commit_artifacts` given `["docs/interventions/x.md"]` with a foreign `docs/bugs/other/SPEC.md` ALSO staged commits ONLY `docs/interventions/x.md`; the foreign path is absent from the commit and remains staged/uncommitted for its owner. No closed ledger-event tracks flush-absorption → the intervention's measurement target is honestly `undeclared`; the durable guarantee is this regression.
