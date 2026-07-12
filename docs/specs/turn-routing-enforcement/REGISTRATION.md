# Per-Machine Hook Registration — turn-routing-enforcement

> **RETIRED 2026-07-12.** The per-machine paste-fragment registration design documented
> below is retired. Hook registration for these two hooks (`lazy-route-inject.sh`,
> `lazy-dispatch-guard.sh`) now ships **tracked** in `user/settings.json` — the single
> SSOT for hook registration, merged in by
> `docs/bugs/live-settings-split-brain-disarms-enforcement-plane` Phase 1. The live
> `~/.claude/settings.json` on every machine is restored to the manifest-declared
> **symlink** into that tracked file via `setup.ps1 repair` (Windows) or
> `setup.py repair` (cross-platform) — there is no longer a separate untracked
> per-machine file to hand-edit. See that bug's directory for the reconciliation
> details. The rest of this document is retained below as a historical record only;
> do not act on it as a live instruction.

> See SPEC.md §Settings placement for the design context (also amended to reflect the
> retirement above).

## JSON Fragment

Historical fragment (SUPERSEDED — retained for reference only). This fragment WAS
applied as the `hooks` key in each machine's live `~/.claude/settings.json` before
registration moved into the tracked SSOT described in the retirement banner above.
Do not apply it today — if a machine's live settings.json is missing these
registrations, run `setup.ps1 repair` (or `setup.py repair`) to restore the symlink
into the tracked `user/settings.json` instead of pasting JSON by hand.
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

## Per-machine notes (historical — superseded)

This section describes the now-retired per-machine model; it no longer reflects how
registration works. Retained for historical context only.

The `~/.claude/hooks/...` form in the command strings was portable across all three
environments because each machine's `~/.claude/hooks` is a symlink into the
claude-config checkout:

| Machine | `~/.claude/hooks` target |
|---------|--------------------------|
| Laptop (`C:\Users\Jacob`, `DESKTOP-GHTC5K6`) | `C:\Users\Jacob\source\repos\claude-config\user\hooks` |
| Desktop (`C:\Users\JacobMadsen`) | `C:\Users\JacobMadsen\source\repos\claude-config\user\hooks` |
| WSL (`~`) | `~/repos/claude-config/user/hooks` |

The symlink is created by `setup.ps1 repair -Target User` (or `bootstrap`). Run
`setup.ps1 check` to verify the symlink and the tracked hook set's presence in the
live settings.json.

**Superseded:** the paragraph below described the pre-retirement state, where the
tracked `user/settings.json` carried only the desktop machine's hook registrations
and each other machine needed its own separately-maintained live file. That split is
what `docs/bugs/live-settings-split-brain-disarms-enforcement-plane` Phase 1
reconciled: `user/settings.json` is now the single tracked SSOT for all hook
registrations (including these two), and every machine's live `~/.claude/settings.json`
is a symlink back into it. There is no more per-machine registration to unify or
maintain by hand.

~~Existing hooks in tracked `user/settings.json` are NOT affected. The tracked file
carries the desktop machine's hook registrations. This registration adds the
turn-routing-enforcement hooks to each machine's untracked live `~/.claude/settings.json`
(a separate per-machine file). Settings unification across machines is out of scope here
— see SPEC.md §Out of scope.~~

## Merging with existing hooks (historical — superseded)

This section is retained for historical context only; it no longer applies now that
registration ships in the tracked SSOT (see the retirement banner at the top of this
document). Previously: when the live settings.json already had a `hooks` key (other
hook registrations), the merge was done by hand — for example, if `PreToolUse` already
had a `Read` matcher entry, the `Agent|Task` entry was appended to the `PreToolUse`
array:

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
