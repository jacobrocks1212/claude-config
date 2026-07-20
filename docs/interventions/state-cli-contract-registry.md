---
kind: intervention
intervention_id: state-cli-contract-registry
pipeline: feature
provenance: gated
shipped_date: '2026-07-13'
shipped_commit: 7105ba88ee485c3c03e8313a2728783987a24441
commit_set: 7105ba88ee485c3c03e8313a2728783987a24441
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-13T16:07:03Z'
review_after_runs: 20
min_sample: 5
band_pct: 20
review_count: 1
status: inconclusive
escalated: false
reconsideration_enqueued: null
canary:
  opened: '2026-07-13'
  window_runs: 10
  surfaces:
  - user/hooks/CLAUDE.md
  - user/hooks/block-terminal-kill.sh
  - user/scripts/lazy_core.py
  commit_set:
  - 3411b45
  - 84f4a03
  - b77b5b2
  - 535a03a
  pair_scope: []
  degraded_revert_note: null
  status: closed-clean
---

# Intervention: state-cli-contract-registry

Hypothesis: shipping `state-cli-contract-registry` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.

## Canary 2026-07-17

- window: closed after 10/10 observed post-ship run(s) (matured: True)
- signal movement: band-not-evaluable (target undeclared)
- incidents attributed: none
- unattributed in-window incidents: 32 (listed, never counted)
- handoff: the efficacy review proceeds on its own longer cadence — a clean canary does NOT pre-judge the efficacy verdict, and the watcher stops waking this record.

## Review 2026-07-19

- review_number: 1
- verdict: INCONCLUSIVE
- reason: undeclared target_signal (declare an ## Intervention Hypothesis block)
- baseline: None ev/run (None events / None runs; status not-computable)
- post_window: None ev/run (None events / 20 runs)
- delta_pct: None
- confounders: adhoc-audit-obligation-fires-on-zero-commit-failed-cycle (undeclared), adhoc-containment-denies-mandated-explore-fanout (undeclared), adhoc-cycle-begin-real-requires-sub-skill (undeclared), adhoc-cycle-return-omits-decision-classification-ledger (undeclared), adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose (undeclared), adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move (undeclared), adhoc-incident-hook-deny-057921 (undeclared), adhoc-incident-hook-deny-4b767b (undeclared), adhoc-lane-plan-single-lane-seam-classification (undeclared), adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke (undeclared), adhoc-parity-audit-blind-to-compute-state-routing-branches (undeclared), adhoc-process-friction-detector-counts-concurrent-session-commits (undeclared), adhoc-unify-merged-head-coordinator-exemptions (undeclared), adhoc-write-plan-cognito-planner-contract-read (undeclared), anti-overfit-design-gate (kpi:anti-overfit-gate.gate-weakening-unreviewed-reaching-main), bug-queue-aging-backpressure (undeclared), build-queue-copy-lock-stale-dll-false-success (undeclared), build-queue-enforce-cd-prefix-bypass (undeclared), build-queue-eta-marker-mojibake-on-redirected-stdout (undeclared), build-queue-false-green-on-silent-build-failure (undeclared), build-queue-foreground-wait-blocks-past-terminal-outcome (undeclared), build-queue-hygiene-dot-source-discarded-in-child-scope (undeclared), build-queue-runner-tests-dual-beforeall-fails-pester6 (undeclared), completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo (undeclared), concurrent-worktree-agent-coordination (undeclared), containment-hook-inline-python-exceeds-windows-cmdline-limit (undeclared), coupled-pair-generation (undeclared), cycle-prompt-environment-dialect (undeclared), decision-11-dispatch-time-forward-advance (undeclared), decision-2-6-uncovered-row-reroute-to-mcp-test (undeclared), descoped-row-recognition-needs-canonical-marker (undeclared), dispatched-harden-record-intervention-refused-by-containment (undeclared), efficacy-signal-integrity (undeclared), execute-plan-skill-diet (undeclared), external-owner-contracts-locked-without-consultation (undeclared), generalized-build-test-runner-skills (undeclared), harden-2026-07-r1 (undeclared), harden-2026-07-r100 (event:halt), harden-2026-07-r101 (event:halt), harden-2026-07-r102 (event:halt), harden-2026-07-r103 (undeclared), harden-2026-07-r104 (undeclared), harden-2026-07-r109 (event:containment-refusal), harden-2026-07-r110 (event:halt), harden-2026-07-r113 (event:gate-refusal), harden-2026-07-r114 (event:dispatch), harden-2026-07-r14 (event:gate-refusal), harden-2026-07-r15 (event:gate-refusal), harden-2026-07-r16 (event:gate-refusal), harden-2026-07-r17 (undeclared), harden-2026-07-r18 (event:gate-refusal), harden-2026-07-r19 (undeclared), harden-2026-07-r2 (undeclared), harden-2026-07-r20 (event:gate-refusal), harden-2026-07-r21 (event:gate-refusal), harden-2026-07-r22 (undeclared), harden-2026-07-r23 (undeclared), harden-2026-07-r24 (undeclared), harden-2026-07-r25 (undeclared), harden-2026-07-r26 (undeclared), harden-2026-07-r27 (undeclared), harden-2026-07-r28 (event:containment-refusal), harden-2026-07-r29 (undeclared), harden-2026-07-r3 (undeclared), harden-2026-07-r30 (undeclared), harden-2026-07-r31 (event:halt), harden-2026-07-r32 (event:halt), harden-2026-07-r33 (event:deny), harden-2026-07-r35 (event:gate-refusal), harden-2026-07-r36 (event:gate-refusal), harden-2026-07-r37 (undeclared), harden-2026-07-r38 (undeclared), harden-2026-07-r39 (undeclared), harden-2026-07-r40 (undeclared), harden-2026-07-r41 (undeclared), harden-2026-07-r42 (undeclared), harden-2026-07-r43 (undeclared), harden-2026-07-r44 (event:gate-refusal), harden-2026-07-r45 (undeclared), harden-2026-07-r48 (event:containment-refusal), harden-2026-07-r49 (undeclared), harden-2026-07-r5 (undeclared), harden-2026-07-r50 (event:halt), harden-2026-07-r51 (undeclared), harden-2026-07-r52 (event:gate-refusal), harden-2026-07-r53 (event:containment-refusal), harden-2026-07-r54 (event:gate-refusal), harden-2026-07-r55 (event:halt), harden-2026-07-r56 (event:halt), harden-2026-07-r57 (event:halt), harden-2026-07-r6 (undeclared), harden-2026-07-r61 (event:gate-refusal), harden-2026-07-r62 (event:halt), harden-2026-07-r63 (undeclared), harden-2026-07-r64 (event:halt), harden-2026-07-r65 (event:halt), harden-2026-07-r66 (undeclared), harden-2026-07-r67 (event:cycle-end), harden-2026-07-r7 (undeclared), harden-2026-07-r71 (undeclared), harden-2026-07-r72 (event:containment-refusal), harden-2026-07-r73 (undeclared), harden-2026-07-r74 (undeclared), harden-2026-07-r75 (event:containment-refusal), harden-2026-07-r76 (undeclared), harden-2026-07-r77 (undeclared), harden-2026-07-r78 (undeclared), harden-2026-07-r79 (undeclared), harden-2026-07-r80 (undeclared), harden-2026-07-r81 (undeclared), harden-2026-07-r82 (undeclared), harden-2026-07-r85 (undeclared), harden-2026-07-r86 (event:gate-refusal), harden-2026-07-r87 (undeclared), harden-2026-07-r89 (event:containment-refusal), harden-2026-07-r90 (event:halt), harden-2026-07-r91 (event:halt), harden-2026-07-r92 (event:halt), harden-2026-07-r93 (event:halt), harden-2026-07-r94 (event:dispatch), harden-2026-07-r96 (undeclared), harden-2026-07-r97 (event:halt), harden-2026-07-r98 (undeclared), harden-2026-07-r99 (undeclared), hardening-intervention-records-unmeasurable-or-missing (undeclared), harness-gate-gate-weakening-false-positives-rename-and-docstring (undeclared), intervention-efficacy-tracking (undeclared), interventions-telemetry-repo-scope-split-brain (undeclared), lazy-batch-skill-deflation (undeclared), lazy-core-package-decomposition (undeclared), lean-plan-files (undeclared), live-settings-split-brain-disarms-enforcement-plane (undeclared), long-build-and-build-queue-matcher-bypasses (undeclared), mechanize-prose-only-orchestrator-contracts (undeclared), merged-head-actionability-oracle (undeclared), merged-head-includes-parked-items-deadlocks-park-run (undeclared), merged-head-oracle-per-signal-supplement-churn (undeclared), meta-dispatch-not-by-reference-and-ack-overpriced (undeclared), no-sanctioned-cli-for-queue-state-mutations (undeclared), operator-halt-notifications (undeclared), park-provisional-acceptance (undeclared), phases-slice-scoped-reads (undeclared), plan-skills-lack-targeted-phase-scoped-read (undeclared), plan-skills-redesign (undeclared), plan-structure-authoring-gate (undeclared), pr-review-rereview-low-fidelity-metadata (undeclared), push-hook-bypass-anchor-false-blocks-composed-push (undeclared), run-end-gate-refusals-no-telemetry-event (undeclared), shared-hook-lib (undeclared), skill-config-schema-and-reference-lint (undeclared), skip-mcp-test-frontmatter-unquoted-colon (undeclared), spec-excerpt-scoped-plans (undeclared), spike-pipeline-role (undeclared), stub-origin-provisional-exclusion (undeclared), subagent-wedge-backstop-hook (undeclared), test-only-production-seams (undeclared), workstation-recursive-subagent-dispatch (undeclared)
- independence: undeclared
- consequence: none
