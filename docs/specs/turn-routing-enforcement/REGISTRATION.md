# Per-Machine Hook Registration — turn-routing-enforcement

> See SPEC.md §Settings placement for the design context.

## JSON Fragment

Paste this fragment as the `hooks` key in each machine's live `~/.claude/settings.json`.
The paths use `~/.claude/hooks/...` — a portable form that resolves correctly on every
machine as long as the `~/.claude/hooks` symlink is present (created by `setup.ps1`).

```json
"hooks": {
  "UserPromptSubmit": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "bash ~/.claude/hooks/lazy-route-inject.sh",
          "timeout": 90
        }
      ]
    }
  ],
  "SessionStart": [
    {
      "matcher": "compact",
      "hooks": [
        {
          "type": "command",
          "command": "bash ~/.claude/hooks/lazy-route-inject.sh",
          "timeout": 90
        }
      ]
    }
  ],
  "PostCompact": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "bash ~/.claude/hooks/lazy-route-inject.sh",
          "timeout": 90
        }
      ]
    }
  ],
  "PreToolUse": [
    {
      "matcher": "Agent|Task",
      "hooks": [
        {
          "type": "command",
          "command": "bash ~/.claude/hooks/lazy-dispatch-guard.sh",
          "timeout": 30
        }
      ]
    }
  ]
}
```

## Timeout Rationale

| Hook | Timeout | Reason |
|------|---------|--------|
| `lazy-route-inject.sh` | 90s | The inject hook runs the full probe form (`--repeat-count --probe --emit-prompt`), which is a Python subprocess invocation. Observed probe runtime is ~1–2s, but the inject script's Python subprocess is allowed up to 60s internally (Phase 2 Implementation Notes). The hook timeout must **exceed** the subprocess ceiling — 90s satisfies SPEC §Failure modes (UserPromptSubmit timeout ≥ 30s) and the 60s subprocess ceiling. |
| `lazy-dispatch-guard.sh` | 30s | The guard delegates to `lazy_guard.py` for a registry lookup + hash comparison — sub-second in practice. 30s provides a comfortable safety margin without impacting interactive latency. No subprocess with a multi-second ceiling is involved. |

## Marker-absent fast path

Both hook scripts perform a single `test -f $STATE_DIR/lazy-run-marker.json` on entry.
When no marker is present (interactive sessions, non-orchestrator runs), both scripts
exit 0 instantly — one filesystem stat per hook event, zero Python startup overhead.
Interactive sessions are completely unaffected.

## Registration events

| Event | Matcher | Script | Purpose |
|-------|---------|--------|---------|
| `UserPromptSubmit` | (none — all prompts) | `lazy-route-inject.sh` | Primary injection event: runs the probe and injects LAZY-ROUTE banner + probe JSON + nonce into `additionalContext` on every turn. |
| `SessionStart` | `compact` | `lazy-route-inject.sh` | Post-compaction re-injection: fires when Claude Code resumes after context compaction. Injects the re-entry protocol + marker-sourced `forward_cycles`/`meta_cycles` counters — the compaction counter-loss class dies by construction. |
| `PostCompact` | (none) | `lazy-route-inject.sh` | Supplementary: `additionalContext` is not documented for `PostCompact` per A2 (PHASES.md Validated Assumptions). Registered as a harmless belt-and-suspenders guard; if it fires with injection support it covers the compaction event window. Harmless if it never fires (exits fast-path 0 when no marker, no output otherwise). |
| `PreToolUse` | `Agent\|Task` | `lazy-dispatch-guard.sh` | Validates every `Agent` or `Task` dispatch against the prompt registry. Unregistered dispatch → deny with corrective recipe. Registered + unconsumed nonce → allow, nonce consumed. Marker absent → silent allow. |

## Per-machine notes

The `~/.claude/hooks/...` form in the command strings is portable across all three
environments because each machine's `~/.claude/hooks` is a symlink into the
claude-config checkout:

| Machine | `~/.claude/hooks` target |
|---------|--------------------------|
| Laptop (`C:\Users\Jacob`, `DESKTOP-GHTC5K6`) | `C:\Users\Jacob\source\repos\claude-config\user\hooks` |
| Desktop (`C:\Users\JacobMadsen`) | `C:\Users\JacobMadsen\source\repos\claude-config\user\hooks` |
| WSL (`~`) | `~/repos/claude-config/user/hooks` |

The symlink is created by `setup.ps1 repair -Target User` (or `bootstrap`). Run
`setup.ps1 check` to verify — it will WARN if the hooks are not registered in the
live settings.json.

**Existing hooks in tracked `user/settings.json` are NOT affected.** The tracked file
carries the desktop machine's hook registrations. This registration adds the
turn-routing-enforcement hooks to each machine's untracked live `~/.claude/settings.json`
(a separate per-machine file). Settings unification across machines is out of scope here
— see SPEC.md §Out of scope.

## Merging with existing hooks

When the live settings.json already has a `hooks` key (other hook registrations),
merge the events rather than replacing. For example, if `PreToolUse` already has
a `Read` matcher entry, append the `Agent|Task` entry to the `PreToolUse` array:

```json
"PreToolUse": [
  {
    "matcher": "Read",
    "hooks": [ { "type": "command", "command": "bash ~/.claude/hooks/pr-review-cache-guard.sh", "timeout": 5 } ]
  },
  {
    "matcher": "Agent|Task",
    "hooks": [ { "type": "command", "command": "bash ~/.claude/hooks/lazy-dispatch-guard.sh", "timeout": 30 } ]
  }
]
```

## Pipe-test run records (Phase 6)

**Date:** 2026-06-11

WSL legs executed — `test_pipe_tests_wsl` PASSED (not skipped). The test confirmed
that WSL bash can execute `lazy-dispatch-guard.sh` and `lazy_guard.py` using Windows
working-tree paths (via `wslpath -u`), and that both the fast-path (no marker → silent
exit 0) and the deny path (unregistered prompt → deny JSON with corrective recipe) work
correctly from within WSL.

```
Results: 21/21 passed, 0 skipped, 0 failed
```

All 21 tests passed with 0 skipped — no WSL legs were skipped, confirming WSL is
functional on this machine and both platforms (Windows git-bash + WSL) verified.
