---
kind: investigation-spec
bug_id: lazy-cycle-containment-lifecycle-patterns-still-unanchored
---

# lazy-cycle-containment.sh LIFECYCLE_PATTERNS is the last unanchored `token in command` deny check (same reference-only-mention class) — Investigation Spec

> Over-fit spin-off from the harden-harness round that segment-anchored the state-script invocation deny (`lazy-cycle-containment-false-denies-reference-only-routing-mentions`, hardening-log 2026-07 Round 33). The reference-only-mention false-deny CLASS has now been closed twice in THIS hook (the `_LAZY_BATCH_DIRECT_RE` anchoring in `adhoc-incident-hook-deny-4b767b`, then the `_STATE_PY` anchoring in Round 33) — signal-2 recurrence. `LIFECYCLE_PATTERNS` is the remaining unanchored substring check.

**Status:** Investigating
**Severity:** Low
**Discovered:** 2026-07-12
**Placement:** docs/bugs/lazy-cycle-containment-lifecycle-patterns-still-unanchored
**Related:** `docs/bugs/lazy-cycle-containment-false-denies-reference-only-routing-mentions` (Round 33 PRIMARY, the immediate origin); `docs/bugs/adhoc-incident-hook-deny-4b767b` (the first anchoring in this hook); `user/hooks/build-queue-enforce.sh` (the proven `_CMD_START` pattern)

---

## Class Boundary (deliberately tight)

- **IN:** the remaining unanchored `for pat in LIFECYCLE_PATTERNS: if pat in command` deny check in `lazy-cycle-containment.sh` (`dev:kill`, `dev:restart`, `kill-port 3333`, `kill-port 1420`) — a subagent commit whose MESSAGE BODY mentions e.g. `dev:kill` would false-deny (`lifecycle-command`), the identical reference-only-mention class Round 33 fixed for the state-script check.
- **OUT:** the already-anchored `_LAZY_BATCH_*_RE` and `_STATE_PY_INVOKE_RE` (done); cross-hook generalization (`build-queue-enforce.sh` already anchored); any new lifecycle behavior. No behavior beyond subsuming the observed instance's near neighbor.

## Why not fixed in Round 33

Anchoring `LIFECYCLE_PATTERNS` is NOT a byte-for-byte mirror of the state-script fix: these tokens are legitimately NON-segment-leading in real invocations (`npm run dev:kill` runs `dev:kill` as an argument to `npm run`, and the existing test `test_containment_denies_lifecycle_commands` REQUIRES `npm run dev:kill` to deny). So a naive `_CMD_START` anchor would BREAK a real-runaway deny. The correct fix must recognize the `npm run <script>` / task-runner forms while still rejecting a bare commit-message mention — a distinct, scoped design worth its own investigation, not a rushed inline mirror.

## Candidate Approach (to be decided by /spec-bug)

Match the lifecycle tokens only when they appear as an invoked task/command (segment-leading, OR immediately after a recognized task-runner verb like `npm run` / `pnpm run` / `yarn`), never as free text in a quoted `-m` message body. Preserve every existing lifecycle deny (the `npm run dev:kill` form included). Add a reference-only-mention allow test mirroring `test_containment_allows_state_script_reference_only_mention`.
