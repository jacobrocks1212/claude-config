---
kind: investigation-spec
bug_id: lazy-cycle-containment-false-denies-reference-only-routing-mentions
---

# lazy-cycle-containment.sh false-denies legitimate cycle commits that merely MENTION routing tokens (reference-only-mention false-deny) — Investigation Spec

> Harness-hardening round (observed-friction, 2026-07-12). While a cycle marker is live, `lazy-cycle-containment.sh` DENIED a legitimate `git commit`/`git add` from a cycle subagent whenever a `lazy-state.py`/`bug-state.py` token or a routing flag appeared as INCIDENTAL text — a commit-message body or a staged filename argument — even though the git command invoked no routing op. The token-matching was unanchored (`_STATE_PY_RE.search(command)` + `flag in command`), so it could not distinguish an INVOCATION from a MENTION. The sibling `build-queue-enforce.sh` already solved this exact class via `_CMD_START` segment anchoring.

**Status:** Concluded
**Severity:** Medium
**Discovered:** 2026-07-12
**Placement:** docs/bugs/lazy-cycle-containment-false-denies-reference-only-routing-mentions
**Related:** `docs/bugs/adhoc-incident-hook-deny-4b767b` (the SAME reference-only-mention class, fixed earlier for the `_LAZY_BATCH_DIRECT_RE` regex in this same hook — the prior occurrence establishing the ≥2 class recurrence); `user/hooks/build-queue-enforce.sh` (the proven `_CMD_START` segment-anchor pattern this fix mirrors); hardening-log 2026-07 round (the fix round)

---

## Reconstructed Route (divergence point)

- **Item in flight:** `interventions-telemetry-repo-scope-split-brain` (claude-config, live cycle marker present).
- **Attempted op:** a cycle subagent's ordinary self-edit commit — e.g. `git commit -m "...fix lazy-state.py --probe edge; routes to Part 2 via --emit-dispatch..."` and `git add user/scripts/lazy-state.py`.
- **Divergence point:** `lazy-cycle-containment.sh` inline-Python loop-formation trip (`main()` subagent branch). `_STATE_PY_RE = re.compile(r"\b(?:lazy-state|bug-state)\.py\b")` matched the token in the commit-message body / staged filename, then `any(flag in command for flag in LOOP_FORMATION_FLAGS)` matched a routing flag mentioned in the same message → `_deny(CORRECTIVE, "loop-formation-flag")`.
- **Recurrence:** seen 2× in one run (harden round 32 doc-heredoc commit + cycle-8 execute-plan commit). Cycle subagents worked around it (message-file + `git add -u`), but it recurred on every commit-heavy self-edit cycle.

## Root Cause (classification: hook-defect)

`lazy-cycle-containment.sh` matched the state-script token and the routing flags **unanchored** — anywhere in the command string, including argument and message text. It therefore could not tell a real routing INVOCATION (`python3 lazy-state.py --run-start`) from a reference-only MENTION (`git commit -m "...lazy-state.py --run-start..."`, `git add user/scripts/lazy-state.py`). This is the identical failure class that `build-queue-enforce.sh` closed via segment-start anchoring (`_CMD_START` — a build token must BEGIN a command segment to deny; a reference-only mention like `cat .../build-filtered.ps1` is allowed) and that this same hook already closed once for the `_LAZY_BATCH_DIRECT_RE` regex (`docs/bugs/adhoc-incident-hook-deny-4b767b`).

## Verified Symptom

- Pre-fix: `git add user/scripts/lazy-state.py` (subagent + marker) → DENY (`loop-formation-flag`); `git commit -m "...lazy-state.py ... --emit-dispatch..."` → DENY.
- Reproduced deterministically in the regression test `test_containment_allows_state_script_reference_only_mention` (RED against the unanchored matcher).
- Post-fix live proof: this round's own `harden(hook):` commit — whose message contains `lazy-state.py`, `bug-state.py`, `routing`, `--run-start` — was ALLOWED (commit `8494a4f0`).

## Fix Scope

`user/hooks/lazy-cycle-containment.sh` only (no target-repo, no state-script, no gate change):

- Replace unanchored `_STATE_PY_RE` with a segment-anchored invocation matcher `_STATE_PY_INVOKE_RE` (`_CMD_START` + optional `python`/`python3` interpreter + optional path prefix + `(?:lazy-state|bug-state)\.py\b`), mirroring `build-queue-enforce.sh`.
- Scope the routing-flag check to the INVOKING segment (`_SEGMENT_SPLIT_RE` + `_STATE_PY_INVOKE_SEG_RE`), so a routing flag mentioned in an unrelated later segment (e.g. a commit-message body) cannot trip the deny. This also correctly denies a real invocation chained behind another command.
- All real-runaway denies preserved (`test_containment_still_denies_real_state_script_invocation`; the existing loop-formation/lifecycle/lazy-batch tests unchanged).

**Accepted residual (mirrors build-queue-enforce.sh):** a pathological commit message that literally embeds a shell separator immediately followed by a state-script invocation (`git commit -m "...; python3 lazy-state.py --run-start"`) can still create a fake segment boundary and false-deny. This is the identical narrow residual the build-queue hook accepts; not worth shell-quote parsing.

## Reproduction Steps

1. Arm a cycle marker (`lazy-state.py --cycle-begin ...`) for feature `feat-A`.
2. As a subagent (agent_id present), run `git add user/scripts/lazy-state.py` or `git commit -m "...lazy-state.py --emit-dispatch..."`.
3. Pre-fix: DENY (`loop-formation-flag`). Post-fix: ALLOW.
