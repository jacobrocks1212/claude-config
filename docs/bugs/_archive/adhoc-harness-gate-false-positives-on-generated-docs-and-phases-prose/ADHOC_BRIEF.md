---
kind: adhoc-brief
bug_id: adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: harness-gate.py gate_weakening/overfit false-positives on generated docs + PHASES.md prose

harness-gate.py's structural detectors fire on NON-CODE content, producing gate_weakening=hit false positives that force operator sign-off on plane-strengthening changes. Two live cases in one /lazy-batch run (2026-07-18): (1) containment-hook fix — gate_weakening matched a PHASES.md PROSE row mentioning BUILD_QUEUE_BYPASS (its *_BYPASS env-var detector); (2) subagent-wedge-backstop-hook — gate_weakening matched LAZY_QUEUE.md's auto-generated queue-count renumbering ('## Bugs (17) -> (16)', index shifts) via its 'numeric-literal change on a gate line' detector. LAZY_QUEUE.md is a generated doc regenerated every cycle commit; PHASES.md prose rows are documentation. Neither is a gate/code surface. The overfit detector similarly flags fail-open breadcrumb shell lines (_HOOK_*_TS timestamps) as 'alternation literal appended', and sweeps unrelated bug-SPEC incident literals into a feature's range. Fix: scope the gate_weakening + overfit detectors to actual code/gate files — exclude generated docs (LAZY_QUEUE.md, SCORECARD.md), PHASES.md prose rows, and unrelated docs/{features,bugs}/*/SPEC.md swept into a range; the control-surface manifest already lists the real gate files, so restrict scanning to changed paths that are code (or on the manifest), not every path in the diff range. Add regression fixtures for both observed false-positive shapes. Origin: /lazy-batch run 2026-07-18 (containment-hook + subagent-wedge-backstop-hook completions each forced a redundant operator sign-off).
