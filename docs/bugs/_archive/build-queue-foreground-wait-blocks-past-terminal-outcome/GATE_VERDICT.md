---
kind: gate-verdict
feature_id: build-queue-foreground-wait-blocks-past-terminal-outcome
gate_version: 1
date: 2026-07-13
scope_hit:
  - user/scripts/build-queue.ps1
  - user/scripts/build-queue-runner.ps1
  - user/scripts/build-queue-hygiene.ps1
  - user/scripts/build-queue-foreground-outcome.Tests.ps1
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: hit-signed
  complexity: declared
retires: net-new — two pure helpers extracted into build-queue-hygiene.ps1 (`Wait-ForRecordedOutcome`, `Test-ShouldSweepPoisonedArtifacts`). Nothing retired; the added surface pays for itself by making the foreground wait model + the poison-sweep predicate serving-path-testable in Pester (previously untestable inline script), which is what let the SEAM-B regression prove the symptom gone.
override: operator-approved 2026-07-13 — false positive: BUILD_QUEUE_BYPASS is a pre-existing doc mention on a rewritten one-line CLAUDE.md row; no bypass env-var introduced, no gate/deny/refuse/exit-3/test weakened or removed.
---

## Adversarial answers

### overfit
The checker flagged "alternation literal appended" on Pester assertions (`$outcome.Outcome | Should -BeExactly 'result-recorded'`, `$banner | Should -Match 'RESULT=PASS'`) and a type-union docstring (`Outcome = 'result-recorded' | 'process-exited' | 'timeout'`), plus an "incident-shaped literal" on a test fixture timestamp (`2026-07-13T00:00:00.0000000Z`, the injected `-Now` seam value). None of these is a matcher/allow-list/exemption-set literal — they are test-expectation strings and a doc `|` type union. **Nearest recurrence this rule does NOT catch:** irrelevant — there is no rule keyed on an incident literal here; the code paths (`Wait-ForRecordedOutcome` returning `result-recorded` vs `process-exited`; the sweep predicate over `$IsBuildOp`/`$ExitCode`) key on STRUCTURE (result-file presence + readable exit_code; build-op-ness), not on any enumerated literal. The flagged strings are the fixed vocabulary of the outcome contract (the banner grammar / the function's return enum), not fitting to an observed incident. The fixture timestamp is a deterministic injected clock value, not a hard-coded incident id.

### tautology
This is a **behavior-restoring bugfix**, not a friction-reduction intervention, so it carries no `## Intervention Hypothesis` KPI (the checker's `no ## Intervention Hypothesis block` note). **If this change were broken, how would its success metric look?** NOT identical to working — the metric is an independent, non-self-emitted observable: the serving-path Pester assertion that `Wait-ForRecordedOutcome` returns `result-recorded` WITHOUT consulting process-liveness or sleeping (alive-probe calls = 0, sleep calls = 0). A broken fix (still waiting on `$proc.HasExited`) makes those probe/sleep counts non-zero and the test RED. The signal is the test suite's pass/fail, which the change does not itself emit or suppress. `signal_independence: independent`.

### gate_weakening
**The exact "weakening":** the checker's `*_BYPASS` detector matched `BUILD_QUEUE_BYPASS=1` on a changed CLAUDE.md line. **This is a false positive** — `BUILD_QUEUE_BYPASS` is the pre-existing build-queue one-off override token, already present in that `build-queue.ps1` doc row before this change; the row is a single long line, so rewriting part of it (to document the foreground early-return) surfaces the entire row — including the unchanged bypass mention — as an added line in the diff. No `*_BYPASS` env-var was introduced in any code file; no `permissionDecision: deny` / `refuse_*` / `exit 3` branch was removed; no `def test_*` was deleted; no numeric gate literal changed; no sanction/exemption set grew. **Underlying-defect alternative considered:** none applicable — there is no gate to fix instead, because no gate was weakened. **Operator rationale (D4 sign-off, per-change):** approved 2026-07-13 as a verified doc-prose false positive; the actual code change (build-op-only poison-sweep gate) makes hygiene stricter/more correct, not weaker.

### complexity
`retires: net-new`. Two small pure functions added to `build-queue-hygiene.ps1`: `Wait-ForRecordedOutcome` (the extracted terminal-aware foreground wait) and `Test-ShouldSweepPoisonedArtifacts` (the extracted build-op poison-sweep predicate). Neither retires an existing rule — the retire claim is honestly `net-new`. The added surface pays for itself: both were previously inline, untestable script; extracting them is what made the SEAM-B serving-path regression (and the 8 gate cases) expressible in Pester, converging the foreground path onto the same result-file model the proven `build-queue-await.ps1` already uses.
