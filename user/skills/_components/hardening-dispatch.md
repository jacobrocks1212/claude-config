# Hardening Dispatch Component

> Orchestrator-side reference for emitting a hardening dispatch via `--emit-dispatch hardening`.

## Overview

A hardening dispatch is emitted whenever the orchestrator hits a misroute (denied dispatch),
a no-route condition (`cycle_prompt_refused`, unknown/contradictory state, or marker/state
divergence), or when the inject hook itself errors against a live marker. It routes the
situation to the harness-hardening stage (`/harden-harness`) — an Opus subagent that
root-causes the gap and either fixes the harness mechanically (under full gates) or surfaces
a NEEDS_INPUT.md for genuine design forks.

Like all dispatch classes (including cycle dispatches), the hardening dispatch is
**registry-validated**: emitting via `--emit-dispatch hardening` registers the prompt hash +
nonce in the lazy-prompt-registry, so the validate-deny guard (`lazy-dispatch-guard.sh`) will
ALLOW it. This is the designed escape hatch: the guard never blocks its own repair signal.

## Emitting a hardening dispatch

```
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch hardening \
  --context trigger_kind=validate-deny \
  --context item_id=feat-my-feature \
  --context denied_prompt_summary="<one-line summary of the denied prompt>" \
  --context denial_reason="<the permissionDecisionReason from the guard>" \
  --context probe_json="<probe JSON from the last --probe call>" \
  --context registry_state="<relevant registry entries as JSON string>" \
  --context cwd="$(pwd)"
```

Output JSON shape:
```json
{
  "dispatch_prompt": "<fully-bound Opus prompt — dispatch this verbatim>",
  "dispatch_model":  "opus",
  "dispatch_class":  "hardening"
}
```

Dispatch the `dispatch_prompt` verbatim as an `Agent` call — do not paraphrase or
re-compose it. Because it was registered at emit time, the validate-deny guard will allow
the exact prompt; a re-composed prompt would be denied.

## Required context keys (`@requires`)

All seven keys below must be supplied via `--context key=value`:

| Key | What to supply |
|-----|---------------|
| `denied_prompt_summary` | One-line summary of the prompt that was denied or refused. For `process-friction` entries, `build_hardening_emit_command` binds `friction_reason` here automatically. |
| `denial_reason` | The `permissionDecisionReason` from the guard, or the no-route reason string. For `process-friction` entries, `build_hardening_emit_command` binds `friction_detail` here automatically. |
| `probe_json` | The probe JSON (`--probe` output) from the turn where the failure occurred |
| `registry_state` | Relevant registry entries (or `"empty"` if no marker was present) |
| `trigger_kind` | One of: `validate-deny`, `no-route`, `inject-hook-error`, `process-friction`, `manual` |
| `item_id` | The feature/bug ID currently in flight (e.g. `feat-d9-example`) |
| `cwd` | Working directory — `$(pwd)` or the repo root |

### `process-friction` trigger — context binding notes

When `trigger_kind=process-friction`, the `--emit-dispatch hardening` command is typically
consumed verbatim from the probe's `hardening_emit_command` field (the probe pre-composes it).
`build_hardening_emit_command` in `lazy_core.py` binds the keys as follows for this entry kind:

| Standard key | What it carries for process-friction |
|---|---|
| `denied_prompt_summary` | `friction_reason` from the ledger entry (e.g. `cycle-bracket-break` or `unexpected-commits`) |
| `denial_reason` | `friction_detail` from the ledger entry (human-readable description of the signal) |
| `probe_json` | The probe JSON at the time the debt was surfaced |
| `registry_state` | `"process-friction-entry"` (no prompt registry involved) |

The `/harden-harness` skill receives these keys through the same `{denied_prompt_summary}` /
`{denial_reason}` template slots — no template change is required. The `trigger_kind` value
`process-friction` is the discriminator that tells the hardening agent to interpret those slots
as the friction signal rather than a guard denial.

## Depth cap

A hardening dispatch's own registry entry carries `class: hardening`. The validate-deny
guard (`lazy_guard.py`) recognizes this tag: if a hardening-class entry is denied (consumed
nonce or stale), the guard emits a halt reason (containing "halt" and "PushNotification")
rather than recommending another hardening dispatch. Depth is hard-capped at 1 — the
orchestrator must NEVER attempt to dispatch a second hardening stage in response to a
hardening denial; it must halt and notify the operator instead.

## Example invocation (feature pipeline, workstation mode)

```python
# From orchestrator Step 1a, after receiving a validate-deny on a hand-composed dispatch:
result = subprocess.run([
    "python3", lazy_state_script,
    "--emit-dispatch", "hardening",
    "--context", f"trigger_kind=validate-deny",
    "--context", f"item_id={item_id}",
    "--context", f"denied_prompt_summary={denied_summary}",
    "--context", f"denial_reason={denial_reason}",
    "--context", f"probe_json={probe_json_str}",
    "--context", f"registry_state={registry_str}",
    "--context", f"cwd={cwd}",
], capture_output=True, text=True, env=env_with_marker)

out = json.loads(result.stdout)
# Dispatch out["dispatch_prompt"] verbatim as an Agent call.
```
