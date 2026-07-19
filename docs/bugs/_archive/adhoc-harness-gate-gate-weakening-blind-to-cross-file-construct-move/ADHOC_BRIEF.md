---
kind: adhoc-brief
bug_id: adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: harness-gate gate_weakening false-positive: per-file detector blind to gate-refusal construct moved to a sibling file

harness-gate.py's gate_weakening detector fires 'gate-refusal construct removed without replacement (net 1; 1 removed, 0 added)' on a behavior-PRESERVING refactor that MOVES a deny/refusal construct from one file into a shared sibling file within the SAME change. Live case: /lazy-batch 2026-07-18 shared-hook-lib completion — 5 enforcement hooks (block-noncanonical-blocker-write.sh, block-sentinel-write-on-stray-branch.sh, build-queue-enforce.sh, lazy-cycle-containment.sh, long-build-ownership-guard.sh) each showed a 'removed' refusal-shaped line because shared setup migrated into the new sourced library hook-prelude.sh; every hook's actual deny logic (_deny + call sites) stayed intact in-file, and test_hooks.py 266/266 + test_hook_lib.py green proved behavior preserved. The per-file diff view cannot see the cross-file replacement, so it forces a redundant operator sign-off on a plane-strengthening consolidation. DISTINCT from adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose (that bug's fix = restrict scanning to code/manifest paths; these hooks ARE code/manifest files, so path-scoping does NOT fix this). Fix vector: reconcile removed-vs-added gate-refusal constructs ACROSS the whole change's file set (a construct removed from file A but present/added in file B within the same commit range is a MOVE, not a removal — net-zero across the diff), and/or add a behavior-preserving-refactor exemption keyed on a net-count reconciliation. Add a regression fixture for the cross-file-move shape. Origin: shared-hook-lib completion forced a third redundant operator sign-off in one run.
