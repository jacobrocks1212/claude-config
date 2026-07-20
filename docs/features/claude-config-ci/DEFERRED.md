---
kind: deferred
feature_id: claude-config-ci
written_by: lazy-batch-parallel-orchestrator
date: 2026-07-18
reason: operator-excluded
---

# Operator-Deferred — excluded from the 2026-07-18 drain run

The operator's run directive for the 2026-07-18 overnight `/lazy-batch-parallel` drain
explicitly excluded this item: "draining all non-complete features and bugs in this repo
that can be worked on in this machine (i.e. skip CI and mobile app)". This is the CI item
(also a `stub: true` entry that would route to an interactive `/spec` baseline round — not
runnable unattended). Deferred mechanically (operator-defer facet — excluded from dispatch
and merged ordering) so the autonomous walk cannot route it.

Un-defer by deleting this file when you want the pipeline to pick it up again.
