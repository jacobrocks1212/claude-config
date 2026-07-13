# Implementation Phases — lazy-cycle-containment.sh false-denies reference-only routing mentions

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; this is a shell hook
verified via subprocess **pipe tests** in `user/scripts/test_hooks.py` (the repo's established
hook-verification harness), the "build-tooling / repo-config, no app integration" untestable
class.

## Close-out note (2026-07-12)

This bug's fix was found **fully implemented and tested at HEAD** when this close-out pass
started — the `_STATE_PY_INVOKE_RE`/`_STATE_PY_INVOKE_SEG_RE` segment-anchored invocation matcher
and the `_LIFECYCLE_INVOKE_RE` anchored lifecycle-command matcher described in the SPEC's Fix
Scope are both present in `user/hooks/lazy-cycle-containment.sh`, and every regression test the
SPEC's Reproduction Steps + Fix Scope call for already exists in `test_hooks.py` and passes. No
code changes were made in this pass — this PHASES.md documents the pre-existing landed state with
evidence, per the standard bug close-out contract (a PHASES.md is required before `Status: Fixed`
even when the fix itself predates this session).

---

### Phase 1: Segment-anchored invocation matchers for state-script routing flags + lifecycle commands

**Scope:** Replace the unanchored `_STATE_PY_RE.search(command)` / `flag in command` /
unanchored `LIFECYCLE_PATTERNS` substring checks in `lazy-cycle-containment.sh`'s subagent
loop-formation trip with segment-anchored invocation matchers, so a `lazy-state.py`/`bug-state.py`
token or a routing flag or a lifecycle command token that appears only as **incidental text** (a
commit-message body, a staged filename argument) no longer trips the deny — only a genuine
command-segment-start INVOCATION does.

**Status:** Complete (pre-landed at HEAD; confirmed by this close-out pass, no code changed)

**Deliverables:**
- [x] `_STATE_PY_INVOKE_RE` — a segment-anchored matcher (`_CMD_START` + optional
  `python`/`python3` interpreter + optional path prefix + `(?:lazy-state|bug-state)\.py\b`),
  mirroring `build-queue-enforce.sh`'s invoke-vs-reference discrimination. Present in
  `user/hooks/lazy-cycle-containment.sh` (`_STATE_PY_TAIL` / `_STATE_PY_INVOKE_RE` block, the
  "reference-only-mention false-deny" comment naming this exact bug).
- [x] The routing-flag check is scoped to the INVOKING segment only —
  `_STATE_PY_INVOKE_SEG_RE` (`^\s*` + `_ENV_PREFIX` + `_STATE_PY_TAIL`) matched per-segment
  (`_SEGMENT_SPLIT_RE.split(command)`), so a `LOOP_FORMATION_FLAGS` token mentioned in an
  unrelated LATER segment (e.g. a commit-message body) cannot trip the deny — only a flag
  present in the segment that itself invokes `lazy-state.py`/`bug-state.py` does. Present in
  `main()`'s subagent branch (the `if _STATE_PY_INVOKE_RE.search(command): for _seg in
  _SEGMENT_SPLIT_RE.split(command): ...` block).
- [x] `_LIFECYCLE_INVOKE_RE` — the same anchoring discipline applied to `LIFECYCLE_PATTERNS`
  (`dev:kill`, `dev:restart`, `kill-port 3333`, `kill-port 1420`): matches only a bare
  segment-leading token OR the token immediately after a recognized task-runner verb (`npm run` /
  `pnpm run` / `yarn run`) — never a mention elsewhere in the command (a quoted commit-message
  body). This closed the SIBLING recurrence of the same false-deny class for the lifecycle
  patterns (`lazy-cycle-containment-lifecycle-patterns-still-unanchored`, same hardening round).
- [x] All real-runaway denies preserved: a genuine `python3 lazy-state.py --run-start` invocation
  (or any `LOOP_FORMATION_FLAGS` member) still denies; `dev:kill` / `npm run dev:kill` /
  `kill-port 3333` still deny when genuinely invoked.
- [x] Regression tests in `user/scripts/test_hooks.py` (all present, all GREEN):
  - `test_containment_allows_state_script_reference_only_mention` — `git add
    user/scripts/lazy-state.py` and a commit message mentioning `lazy-state.py --emit-dispatch`
    → ALLOW (the RED-before-fix repro this bug's Verified Symptom section documents).
  - `test_containment_still_denies_real_state_script_invocation` — a genuine invocation still
    DENIES.
  - `test_containment_denies_lifecycle_commands` — `dev:kill` / `npm run dev:kill` / bare
    `kill-port 3333` still DENY when genuinely invoked.
  - `test_containment_allows_lifecycle_reference_only_mention` — a commit message merely
    mentioning `dev:kill` as prose → ALLOW.
  - `test_containment_agentid_present_denies_lifecycle_no_marker` /
    `test_containment_agentid_absent_allows_lifecycle_no_marker` — the agent_id-gated,
    marker-independent activation model is unaffected by the anchoring change.

**Implementation Notes:** Pre-existing at HEAD when this close-out pass started (git history:
the anchoring landed in an earlier hardening round alongside the sibling
`lazy-cycle-containment-lifecycle-patterns-still-unanchored` fix — both share the exact
`_CMD_START`/`_ENV_PREFIX`/`_SEGMENT_SPLIT_RE` idiom `build-queue-enforce.sh` established). This
close-out pass re-ran the full regression suite to confirm the fix holds: `python -m pytest
user/scripts/test_hooks.py -q -k "test_containment_allows_state_script_reference_only_mention or
test_containment_still_denies_real_state_script_invocation or
test_containment_denies_lifecycle_commands or
test_containment_allows_lifecycle_reference_only_mention or
test_containment_agentid_present_denies_lifecycle_no_marker or
test_containment_agentid_absent_allows_lifecycle_no_marker"` → **6 passed**. Full suite:
`python -m pytest user/scripts/test_hooks.py -q` → **217 passed** (206 baseline + 11 new tests
from the sibling `long-build-and-build-queue-matcher-bypasses` bug fixed in the same pass; none
of the 217 relate to a regression in this bug's own fix). No files modified for this bug in this
pass — `user/hooks/lazy-cycle-containment.sh` and `user/scripts/test_hooks.py` were already
correct.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_hooks.py -q` exits 0, with
every test named above passing.

**Runtime Verification** *(checked by the pipe tests — the hook's runtime IS the subprocess
pipe):*
- [x] <!-- verification-only --> `git add user/scripts/lazy-state.py` / a commit message
  mentioning `lazy-state.py --emit-dispatch` (subagent + marker) → ALLOW. **Verified 2026-07-12**
  via `test_containment_allows_state_script_reference_only_mention` (GREEN).
- [x] <!-- verification-only --> A genuine `python3 lazy-state.py --run-start` invocation
  (subagent + marker) → DENY. **Verified 2026-07-12** via
  `test_containment_still_denies_real_state_script_invocation` (GREEN).
- [x] <!-- verification-only --> `dev:kill` / `npm run dev:kill` / bare `kill-port 3333`
  (subagent + marker) → DENY when genuinely invoked; a commit message merely mentioning
  `dev:kill` as prose → ALLOW. **Verified 2026-07-12** via `test_containment_denies_lifecycle_commands`
  + `test_containment_allows_lifecycle_reference_only_mention` (both GREEN).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in this repo (harness
tooling).

**Prerequisites:** None.

**Files likely modified:** None in this pass — `user/hooks/lazy-cycle-containment.sh` and
`user/scripts/test_hooks.py` already carried the fix.

**Testing Strategy:** Pure pipe testing via `test_hooks.py`'s existing `_run_bash` /
`_containment_decision` harness — no new harness needed.

**Integration Notes for Next Phase:** None — final phase.

**Completion (gate-owned):** Status flip to `Fixed` + `FIXED.md` receipt authored in this
close-out pass (`provenance: operator-directed-interactive` — not the pipeline's `__mark_fixed__`
gate; see `FIXED.md`).

TDD: n/a for this pass (the tests already existed and already passed; no red→green cycle was
needed this session). The ORIGINAL implementation of this fix was TDD per the SPEC's own
Verified Symptom section ("Reproduced deterministically in the regression test
`test_containment_allows_state_script_reference_only_mention` (RED against the unanchored
matcher)").

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_
