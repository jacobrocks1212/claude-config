#!/bin/bash
# SessionStart(compact) hook: re-orient an in-flight /execute-plan run after context compaction.
#
# /execute-plan Step 1d writes a per-repo run marker at
#   ~/.claude/state/execute-plan/<md5(repo_root)[:12]>.json  ({"plan": "...", "repo_root": "..."})
# and removes it at completion / on BLOCKED-NEEDS_INPUT halts. When a compaction fires while the
# marker is present, this hook injects a short reorientation block (plan path + the mandatory
# re-read sequence) so the orchestrator re-anchors on the plan and its on-disk execution
# contracts instead of acting from a lossy summary. Pointer-based plans (cognito-lanes-v2 /
# write-plan v2) carry no inlined policy, so the re-read sequence is the recovery path.
#
# Fail-OPEN: every error path exits 0 silently. This hook only ever ADDS context — it never
# denies anything. Self-heals a stale marker whose plan file is already status: Complete.

input=$(cat 2>/dev/null)

if command -v jq &>/dev/null; then
  cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
else
  cwd=$(printf '%s' "$input" | grep -oP '"cwd"\s*:\s*"\K[^"]+' 2>/dev/null)
fi
[[ -z "$cwd" ]] && exit 0

root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)
[[ -z "$root" ]] && root="$cwd"

key=$(printf '%s' "$root" | md5sum 2>/dev/null | cut -c1-12)
[[ -z "$key" ]] && exit 0
marker="$HOME/.claude/state/execute-plan/$key.json"
[[ -f "$marker" ]] || exit 0

if command -v jq &>/dev/null; then
  plan=$(jq -r '.plan // empty' "$marker" 2>/dev/null)
else
  plan=$(grep -oP '"plan"\s*:\s*"\K[^"]+' "$marker" 2>/dev/null)
fi
[[ -z "$plan" || ! -f "$plan" ]] && exit 0

# Stale self-heal: plan already flipped to Complete -> remove marker, stay silent.
if head -12 "$plan" 2>/dev/null | grep -qiE '^status:[[:space:]]*Complete[[:space:]]*$'; then
  rm -f "$marker" 2>/dev/null
  exit 0
fi

block="[execute-plan-compact-reorient] An /execute-plan run is IN FLIGHT for this repo.
Active plan: ${plan}
MANDATORY — before doing ANYTHING else:
1. TaskList — the first non-completed task is your position; never re-execute a completed one.
2. Re-read the plan file above IN FULL from disk.
3. Read the execution contract(s) its pointer block names — ~/.claude/skills/_components/execution-contract.md plus any repo contract (e.g. .claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md) — they are your operating policy; the plan does not inline it.
4. You are the ORCHESTRATOR: never Edit/Write source or test files — dispatch Sonnet agents per the contract.
5. Re-verify PHASES.md / plan WU checkboxes for the last completed task before resuming."

if command -v jq &>/dev/null; then
  jq -n --arg ctx "$block" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}' -c
else
  escaped=$(printf '%s' "$block" \
    | sed 's/\\/\\\\/g' \
    | sed 's/"/\\"/g' \
    | sed ':a;N;$!ba;s/\n/\\n/g' \
    | sed 's/\t/\\t/g' \
    | sed 's/\r/\\r/g')
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$escaped"
fi

exit 0
