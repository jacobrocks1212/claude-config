---
kind: implemented
feature_id: scheduled-autonomous-runs
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [0e6b802, 76e73fe, 54d909c, ac65269, 89a753c, f57ad34, abe8390, c2175a4, c83db10]
decisions: []
---

# Implementation Ledger

**What shipped:** Wire `/lazy-batch-cloud` to the platform's scheduled triggers so opted-in repos drain their lazy queues nightly in fresh cloud sessions, with a bounded budget per fire. All of the safety machinery already exists — `refuse_run_start_clobber` arbitration, the `--unattended` run marker, `--park` halt-parking, per-cycle `LAZY_QUEUE.md` commits — so this feature is scheduling glue plus an honest morning-report contract: the operator wakes to a routine completion notification, a `LAZY_QUEUE.md` diff on GitHub mobile, halt pages for anything needing a decision (sibling `operator-halt-notifications`), and a workstation flush of the cloud run's `DEFERRED_NON_CLOUD.md` items. Verify, don't rebuild: no new arbitration, budget, or containment code.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**
