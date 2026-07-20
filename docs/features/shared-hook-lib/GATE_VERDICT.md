---
kind: gate-verdict
feature_id: shared-hook-lib
gate_version: 1
date: 2026-07-18
scope_hit: [user/hooks/block-noncanonical-blocker-write.sh, user/hooks/block-sentinel-write-on-stray-branch.sh, user/hooks/build-queue-enforce.sh, user/hooks/hook-prelude.sh, user/hooks/lazy-cycle-containment.sh, user/hooks/lazy-dispatch-guard.sh, user/hooks/lazy-route-inject.sh, user/hooks/long-build-ownership-guard.sh]
checks:
  overfit: flag-justified
  tautology: pass
  gate_weakening: hit-signed
  complexity: declared
retires: duplicated hook boilerplate — the copy-pasted `HOOK_PYTHON`/`HOOK_SCRIPTS_DIR` resolution, the fail-open no-python breadcrumb writer, and the `hook-error.json`/`hook-events.jsonl` observability emitters that lived as near-identical inline copies across 8 enforcement-plane hooks. Consolidated into a single sourced library (`hook-prelude.sh` + `hook_lib.py`). Net LoC reduction across `user/hooks/*.sh`; each migrated hook now SOURCES the prelude instead of carrying its own copy. This RETIRES duplication — it is a consolidation, not net-new enforcement surface.
override: operator-approved 2026-07-18 — false-positive gate_weakening flag on a behavior-PRESERVING refactor (extracts shared hook boilerplate into hook-prelude.sh/hook_lib.py; migrates 8 hooks onto it). The per-file detector reads "gate-refusal construct removed without replacement" on 5 hooks because the SHARED SETUP moved cross-file into the prelude — but every hook's deny logic (`_deny` + call sites) is intact in-file, and the remaining evidence is LAZY_QUEUE.md generated-doc count renumbering (not a gate). Behavior preserved: test_hooks.py 266/266 + test_hook_lib.py green. Signed via /lazy-batch Step 1g after a zero-context operator briefing. Per-change, non-standing. Operator also directed the recurring-false-positive class be enqueued as a fix (adhoc bug, this run).
---

## Adversarial answers

### overfit
The checker flagged incident-shaped literals swept from the broad 45-commit bracket range (concurrent
docs churn), NOT this feature's hook work. shared-hook-lib appends nothing to any matcher
alternation/allow-list/exemption-set — it EXTRACTS shared boilerplate into a sourced library. Nearest
recurrence the change must still catch: every migrated hook's deny path is unchanged (the `_deny`
emitters and their call sites remain in-file, e.g. `lazy-cycle-containment.sh:496,623–723`); the
prelude carries only env/breadcrumb setup, no matcher literals. There is no incident-fit surface here
to over-narrow.

### tautology
N/A — no self-emitted-signal metric. The feature's KPI (`hook-plane-duplicated-lines`, registry row)
is measured by a deterministic cross-file duplicated-line counter over `user/hooks/*.sh` — an
independent signal the change does not itself emit.

### gate_weakening
The SOLE gate_weakening evidence is (a) "gate-refusal construct removed without replacement (net 1)"
on 5 hooks and (b) LAZY_QUEUE.md numeric-literal renumbering. Both are FALSE POSITIVES of the
per-file diff heuristic:
- (a) The refactor moves the shared setup (HOOK_PYTHON resolution, fail-open breadcrumb, observability
  writes) into `hook-prelude.sh`; each migrated hook now `source`s the prelude (`. "$_HOOK_DIR/hook-prelude.sh"`,
  e.g. `lazy-cycle-containment.sh:83`). The per-file detector sees a "removed" refusal-shaped line in
  the hook and cannot see the cross-file replacement in the prelude. The actual gate — the
  `permissionDecision: deny` emission via `_deny` — is UNCHANGED and present in every hook.
- (b) `LAZY_QUEUE.md` is a GENERATED queue-status doc regenerated on every cycle commit; its
  `## Features (5) → (4)` counts are not a "gate line."
No `def test_*` deleted (test_hooks.py grew 266/266; test_hook_lib.py is net-new), no
`permissionDecision: deny`/`refuse_*`/`exit 3` genuinely removed, no `*_BYPASS` added. Underlying-defect
alternative: the detector is per-file-blind to cross-file consolidation — enqueued as a fix this run per
operator direction. Routed to operator sign-off per the never-judgment-passable rule; `override` above
records the approval. Per-change, non-standing.

### complexity
This change REDUCES complexity (see `retires:`) — it deletes duplicated boilerplate across 8 hooks in
favor of one sourced library. It generalizes: every enforcement hook that sources `hook-prelude.sh`
inherits the single-source env/breadcrumb/observability contract, so a future fail-open-observability
fix lands once in the prelude instead of being re-copied into N hooks (the exact recurrence class that
motivated the feature).
