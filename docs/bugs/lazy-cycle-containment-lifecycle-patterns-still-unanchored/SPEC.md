---
kind: investigation-spec
bug_id: lazy-cycle-containment-lifecycle-patterns-still-unanchored
---

# lazy-cycle-containment.sh LIFECYCLE_PATTERNS is the last unanchored `token in command` deny check (same reference-only-mention class) — Investigation Spec

> Over-fit spin-off from the harden-harness round that segment-anchored the state-script invocation deny (`lazy-cycle-containment-false-denies-reference-only-routing-mentions`, hardening-log 2026-07 Round 33). The reference-only-mention false-deny CLASS has now been closed twice in THIS hook (the `_LAZY_BATCH_DIRECT_RE` anchoring in `adhoc-incident-hook-deny-4b767b`, then the `_STATE_PY` anchoring in Round 33) — signal-2 recurrence. `LIFECYCLE_PATTERNS` is the remaining unanchored substring check.

**Status:** Concluded
**Severity:** Low
**Discovered:** 2026-07-12
**Concluded:** 2026-07-12
**Last updated:** 2026-07-12
**Placement:** docs/bugs/lazy-cycle-containment-lifecycle-patterns-still-unanchored
**Related:** `docs/bugs/lazy-cycle-containment-false-denies-reference-only-routing-mentions` (Round 33 PRIMARY, the immediate origin); `docs/bugs/adhoc-incident-hook-deny-4b767b` (the first anchoring in this hook); `user/hooks/build-queue-enforce.sh` (the proven `_CMD_START` pattern); `docs/bugs/powershell-tool-bypasses-bash-matched-guards` (concurrent HOOKS-lane round, in-flight in the same file at conclusion time — see Concurrent-Edit Reconciliation below; disjoint from this bug's fix surface)

---

## Class Boundary (deliberately tight)

- **IN:** the remaining unanchored `for pat in LIFECYCLE_PATTERNS: if pat in command` deny check in `lazy-cycle-containment.sh` (`dev:kill`, `dev:restart`, `kill-port 3333`, `kill-port 1420`) — a subagent commit whose MESSAGE BODY mentions e.g. `dev:kill` would false-deny (`lifecycle-command`), the identical reference-only-mention class Round 33 fixed for the state-script check.
- **OUT:** the already-anchored `_LAZY_BATCH_*_RE` and `_STATE_PY_INVOKE_RE` (done); cross-hook generalization (`build-queue-enforce.sh` already anchored); any new lifecycle behavior. No behavior beyond subsuming the observed instance's near neighbor.

## Why not fixed in Round 33

Anchoring `LIFECYCLE_PATTERNS` is NOT a byte-for-byte mirror of the state-script fix: these tokens are legitimately NON-segment-leading in real invocations (`npm run dev:kill` runs `dev:kill` as an argument to `npm run`, and the existing test `test_containment_denies_lifecycle_commands` REQUIRES `npm run dev:kill` to deny). So a naive `_CMD_START` anchor would BREAK a real-runaway deny. The correct fix must recognize the `npm run <script>` / task-runner forms while still rejecting a bare commit-message mention — a distinct, scoped design worth its own investigation, not a rushed inline mirror.

## Candidate Approach (to be decided by /spec-bug)

Match the lifecycle tokens only when they appear as an invoked task/command (segment-leading, OR immediately after a recognized task-runner verb like `npm run` / `pnpm run` / `yarn`), never as free text in a quoted `-m` message body. Preserve every existing lifecycle deny (the `npm run dev:kill` form included). Add a reference-only-mention allow test mirroring `test_containment_allows_state_script_reference_only_mention`.

## Reconstructed Route (surface → source, HEAD-cited)

All citations against the **stable committed HEAD** version of the hook
(`git show HEAD:user/hooks/lazy-cycle-containment.sh`, saved to
`scratchpad/lazy-cycle-containment_HEAD.sh` for this investigation — the
working copy is mid-edit by a concurrent HOOKS-lane round; see
Concurrent-Edit Reconciliation below for what that edit does and does not touch).

```
surface: PreToolUse deny — permissionDecision="deny",
  permissionDecisionReason=CORRECTIVE, signature="lifecycle-command" — fired
  on a subagent Bash command whose text merely MENTIONS a lifecycle token
  (e.g. inside a `git commit -m "..."` message body), never invokes one.
  ↓
  lazy-cycle-containment.sh (HEAD) :507-509 — the deny site:
    for pat in LIFECYCLE_PATTERNS:
        if pat in command:
            _deny(CORRECTIVE, "lifecycle-command")
  ↓
  lazy-cycle-containment.sh (HEAD) :198-200 — LIFECYCLE_PATTERNS, a plain
    string tuple with NO anchoring:
    LIFECYCLE_PATTERNS = ("dev:kill", "dev:restart", "kill-port 3333", "kill-port 1420")
  ↓
  lazy-cycle-containment.sh (HEAD) :478 — `command` is the FULL, unmodified
    Bash `tool_input.command` string, including any quoted `-m` message body
    (`command = (payload.get("tool_input") or {}).get("command", "")`).
```

Contrast with the two SIBLING deny checks in the SAME file that already got
the segment-anchoring treatment: `_LAZY_BATCH_DIRECT_RE`/`_LAZY_BATCH_NESTED_RE`
(HEAD:223-228) and `_STATE_PY_INVOKE_RE`/`_STATE_PY_INVOKE_SEG_RE`
(HEAD:243-253), both built on the shared `_CMD_START` segment-start anchor
(HEAD:210-211). `LIFECYCLE_PATTERNS` at HEAD:507-509 is the one remaining
`token in command` substring check with no such anchor — the bug's premise is
**TRUE at HEAD**.

**Fix-site-on-path:** the deny site (HEAD:507-509) and/or the LIFECYCLE_PATTERNS
matching logic are exactly where a fix must land — on the traced path.

## Mechanical Reproduction (hermetic, zero real-state writes)

Ran the STABLE HEAD-pinned copy of the hook (not the concurrently-edited
working copy) via a fabricated PreToolUse Bash payload, `agent_id` present
(subagent), under a fake live cycle marker in an isolated temp
`LAZY_STATE_DIR` — reusing the hook's own `_run_containment`/
`_bash_preToolUse_json` test-harness shape from `user/scripts/test_hooks.py`:

| Command | Expected | Actual (HEAD) |
|---|---|---|
| `git commit -m "docs: explain the npm run dev:kill teardown behavior in README"` | ALLOW (reference-only mention) | **DENY** ← false positive |
| `git commit -m "note: our docs mention kill-port 3333 as an example"` | ALLOW (reference-only mention) | **DENY** ← false positive |
| `npm run dev:kill` | DENY (real invocation; pinned by `test_containment_denies_lifecycle_commands`) | DENY (correct) |
| `dev:kill` (bare) | DENY (real invocation) | DENY (correct) |

This confirms both halves of the bug's own framing: (a) the false-positive is
real and reproducible, and (b) `test_containment_denies_lifecycle_commands`
(`user/scripts/test_hooks.py:3193-3213`) and
`test_containment_agentid_present_denies_lifecycle_no_marker`
(`test_hooks.py:3710-3723`) both REQUIRE `npm run dev:kill` to deny — confirming
the SPEC's own "Why not fixed in Round 33" reasoning: a naive segment-start-only
anchor (mirroring `_CMD_START` verbatim) would BREAK these two pinned tests,
since `dev:kill` is not segment-leading in `npm run dev:kill` (the segment
starts with `npm`). No existing test currently pins the reference-only-mention
allow case — this is an untested gap, the same class Round 33 fixed for the
state-script check.

## Root Cause

**Cause label: `traced`.** `LIFECYCLE_PATTERNS`'s deny check
(`lazy-cycle-containment.sh` HEAD:198-200, 507-509) performs an unanchored
substring test (`pat in command`) against the ENTIRE Bash command string,
unlike its two already-anchored siblings in the same file. A subagent commit
whose message BODY merely mentions `dev:kill` / `dev:restart` / `kill-port 3333`
/ `kill-port 1420` as prose is wrongly denied with the `lifecycle-command`
signature — mechanically confirmed above.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Lifecycle deny check | `user/hooks/lazy-cycle-containment.sh` (HEAD:198-200 `LIFECYCLE_PATTERNS` definition; HEAD:507-509 the unanchored `for pat in LIFECYCLE_PATTERNS: if pat in command:` deny loop) | False-deny on any subagent Bash command (commit message, doc-writing, grep) that merely mentions one of 4 tokens as text |
| Test coverage | `user/scripts/test_hooks.py` (existing `test_containment_denies_lifecycle_commands` L3193, `test_containment_agentid_present_denies_lifecycle_no_marker` L3710 — both REQUIRE `npm run dev:kill` to deny; no existing reference-only-mention allow test for lifecycle tokens) | Any fix must not regress these two pinned tests |

## Fix Scope

Per the SPEC's own Candidate Approach (confirmed sound by this investigation):
recognize the lifecycle tokens only when they appear as an INVOKED
task/command — segment-leading (mirroring `_CMD_START`), OR immediately
following a recognized task-runner verb (`npm run`, `pnpm run`, `yarn`) — never
as free text elsewhere in the command string (e.g. inside a quoted `-m` message
body). Concretely: build a `_LIFECYCLE_INVOKE_RE` analogous to
`_STATE_PY_INVOKE_RE`/`_STATE_PY_INVOKE_SEG_RE` (HEAD:243-253) — either
`_CMD_START` + one of the bare tokens, or `_CMD_START` + a task-runner verb
(`npm|pnpm|yarn`) `\s+run\s+` + the token — and scope the match to the
INVOKING segment the same way the state-script check already does (split on
`_SEGMENT_SPLIT_RE`, match each segment from its start). Add a
reference-only-mention allow test mirroring
`test_containment_allows_state_script_reference_only_mention`, alongside the
two existing pinned lifecycle-deny tests (must stay green, unmodified
behavior for real invocations).

**Recommendation:** ship the segment/task-runner-verb-anchored regex above.
Low severity (rare trigger — only a commit message literally containing one of
4 tokens), fail-open hook (a hook error already allows), so this is a
correctness/friction fix, not a containment-safety regression risk.

Runtime residue: none — this is a pure hook-logic fix; the mechanical
reproduction above (hermetic subprocess run of the HEAD-pinned script) is the
full confirming evidence, no runtime/device access needed.

## Concurrent-Edit Reconciliation

At investigation-conclusion time (2026-07-12), `git diff HEAD --
user/hooks/lazy-cycle-containment.sh` shows an **in-flight, uncommitted**
working-copy edit from the concurrent HOOKS-lane round
(`docs/bugs/powershell-tool-bypasses-bash-matched-guards`). That edit:

- Adds `COMMAND_TOOL_NAMES = frozenset({"Bash", "PowerShell"})` and widens the
  `tool_name != "Bash"` gate to `tool_name not in COMMAND_TOOL_NAMES`.
- Adds PowerShell-syntax normalization: `$env:NAME='value';` recognized in
  `_ENV_PREFIX`, backtick line-continuation collapsing
  (`_PS_LINE_CONTINUATION_RE`), and nested `powershell/pwsh -Command "..."`
  unwrapping (`_PS_NESTED_COMMAND_RE` / `_normalize_ps_syntax`).

**This edit does NOT touch `LIFECYCLE_PATTERNS` or its deny loop** (HEAD:198-200,
507-509 — confirmed unchanged in the diff hunks). The two changes are
orthogonal: the concurrent round widens WHICH TOOLS/SYNTAX feed into the
matchers; this bug is about ONE MATCHER (`LIFECYCLE_PATTERNS`) still being
unanchored regardless of tool/syntax. **This bug's finding and fix scope are
unaffected by the concurrent edit** — the fix here should land as a normal
follow-up commit after the PowerShell-bypass round merges (both touch the same
file; expect a straightforward textual rebase, not a semantic conflict, since
the two changes touch disjoint functions/patterns).
