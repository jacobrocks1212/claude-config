---
name: lazy-bug-status
description: Read-only bug pipeline dashboard — runs bug-state.py and formats its output. Shows current bug, queue progress from docs/bugs/queue.json, next /lazy-bug action, blockers, and MCP/validation status. NO mutations. Drives docs/bugs/ (NOT docs/features/).
argument-hint: [optional: "--cloud" to use the cloud state machine]
model: haiku
plan-mode: never
allowed-tools: ["Bash", "Read"]
---

# Lazy Bug Status

Read-only dashboard for the autonomous bug pipeline. Runs `~/.claude/scripts/bug-state.py`,
parses its JSON output, and formats a compact status report. **This skill is pure presentation
— all state inference lives in the script.**

State-machine logic lives exclusively in `bug-state.py`. If the dashboard is wrong, fix the
script — do not duplicate the state machine here.

---

## Step 0: Parse Arguments

If `$ARGUMENTS` contains `--cloud`, pass `--cloud` to the state script. Otherwise run without it.

The cloud variant changes nothing about this skill's behavior beyond which sub-skill the script
picks for Step 9 (workstation: `mcp-test`; cloud: `__write_deferred_non_cloud__`) and how it
handles cloud-saturated bugs at completion.

---

## Step 1: Run bug-state.py

```bash
python3 ~/.claude/scripts/bug-state.py [--cloud]
```

Capture stdout (one JSON object). If the script exits non-zero, print its error verbatim and
STOP — do not try to format malformed state.

Parse the JSON:
- `feature_id`, `feature_name`, `spec_path` — current-bug context (null when there is no
  current bug)
- `current_step` — the state script's human-readable position
- `sub_skill`, `sub_skill_args` — what /lazy-bug would dispatch next
- `terminal_reason`, `notify_message` — set when the pipeline halts
- `device_deferred_features` — bugs the device axis skipped this probe (each has
  `DEFERRED_REQUIRES_DEVICE.md` + no `VALIDATED.md` on a no-real-device host). Always present;
  non-empty means lingering In-progress deferrals awaiting a real-device host.

---

## Step 2: Gather Light Additional Context

These are presentation-only enrichments — they do NOT influence state. Run in parallel:

1. `git log --oneline -1` → last commit (hash + message).
2. If `feature_name` is set: count `### Phase` headings in `{spec_path}/PHASES.md` (if it exists)
   and count how many phases have ALL deliverables checked (`- [x]`) → produces
   "Phase {current}/{total}".
3. If `feature_name` is set: list `{spec_path}/mcp-tests/` entries if the directory exists.
4. If `feature_name` is set AND `{spec_path}/BLOCKED.md` exists: parse its YAML frontmatter per
   `~/.claude/skills/_components/sentinel-frontmatter.md` and grab the `phase` and
   `recovery_suggestion` fields.
5. From `docs/bugs/queue.json` (if it exists): total queue length and how many bugs have been
   archived (have `FIXED.md` in `docs/bugs/_archive/`).

If any of these reads fail (file missing, parse error), continue with the field set to `"—"`.
Do not error out — this skill is a dashboard.

---

## Step 3: Map sub_skill to a Human-Readable Next Action

The state script emits both real sub-skill names and pseudo-skills (prefixed `__`). Translate:

| `sub_skill` from script | "Next /lazy-bug action" |
|-------------------------|------------------------|
| `null` + `terminal_reason` set | halt — see Terminal column below |
| `spec-bug` | /spec-bug — root-cause investigation |
| `spec-phases` | /spec-phases — decompose bug into phases |
| `write-plan` | /write-plan — write the implementation plan |
| `execute-plan` | /execute-plan — run the next plan |
| `mcp-test` | /mcp-test — validate via MCP |
| `retro-feature` | /retro-feature — run retrospective |
| `__write_deferred_non_cloud__` | DEFER MCP test (cloud) → fall through to retro on next cycle |
| `__write_validated_from_skip__` | promote SKIP_MCP_TEST.md → VALIDATED.md |
| `__write_validated_from_results__` | promote MCP_TEST_RESULTS.md → VALIDATED.md |
| `__mark_fixed__` | mark bug fixed, write FIXED.md receipt, archive to _archive/ |
| `__flip_plan_complete_cloud_saturated__` | mark plan part Complete (cloud-saturated) |

Terminal-reason mapping:

| `terminal_reason` | Status line |
|---|---|
| `blocked` | "BLOCKED — see {spec_path}/BLOCKED.md" |
| `needs-input` | "Awaiting human decision — see {spec_path}/NEEDS_INPUT.md" |
| `completion-unverified` | "⚠ {bug} marks Fixed with no FIXED.md receipt — flipped outside the gate. Reconcile: reopen to In-progress, or `bug-state.py --backfill-receipts` to grandfather." |
| `all-bugs-fixed` | "ALL BUGS FIXED — nothing left in queue" |
| `cloud-queue-exhausted` | "Cloud queue exhausted — run /lazy-bug on workstation for MCP testing" |
| `device-queue-exhausted` | "Device queue exhausted — remaining bug(s) have real-device-only assertions deferred via DEFERRED_REQUIRES_DEVICE.md. Re-run /lazy-bug on a real-device host (ALGOBOOTH_REAL_AUDIO_DEVICE=1 or native hardware) to certify them." |
| `queue-missing` | "docs/bugs/queue.json not found (optional — on-disk bugs auto-discovered; create it for explicit ordering)" |

---

## Step 4: Format and Output

Output this exact format (fill in values, replacing missing fields with `—`):

```
## Bug Pipeline Status{ (cloud)}

**Current:** {bug_name | "—"} (Phase {current}/{total} — {state})
**State step:** {current_step | "—"}
**Queue:** {archived}/{total queue length} bugs fixed ({remaining} remaining open)
**Last commit:** {short hash} "{commit message}"
**Blockers:** {None | "<BLOCKED phase>: <recovery_suggestion>"}
**MCP Tests:** {count} scenarios linked | Not yet created | Skipped (see SKIP_MCP_TEST.md) | Deferred (cloud) | Deferred (real-device — see DEFERRED_REQUIRES_DEVICE.md)
**Device-deferred:** {None | comma-separated `device_deferred_features`} — bugs awaiting a real-device host
**Next /lazy-bug action:** {mapped action from Step 3}
```

Notes:

- If `feature_name` is null (terminal queue state), drop the **Current**, **Blockers**, and
  **MCP Tests** lines and surface just **State step**, **Queue**, **Last commit**, and **Next
  /lazy-bug action** — the latter will be the terminal status line.
- When `terminal_reason` is `blocked`, the **Blockers** line takes the BLOCKED.md `phase` +
  `recovery_suggestion` from Step 2.4.
- The "Phase {current}/{total}" annotation is best-effort; if PHASES.md doesn't exist yet,
  write `"—/— ({state})"`.
- The "Deferred (cloud)" / "Skipped" labels for MCP Tests apply when `$ARGUMENTS` contains
  `--cloud` AND the spec dir has `DEFERRED_NON_CLOUD.md` / `SKIP_MCP_TEST.md` respectively.
- The "Deferred (real-device)" label applies when the spec dir has
  `DEFERRED_REQUIRES_DEVICE.md` — real-device-only assertions deferred on the device axis.
- The **Device-deferred** line lists `device_deferred_features` from the state JSON (bugs the
  QUEUE skipped past this probe). Drop the line when the list is empty.
- The **Queue** counts bugs fixed/archived. If `queue.json` is absent, derive the total from
  on-disk open bug directories (the script auto-discovers them).

**Do NOT execute any skills or modify any files. Report only.**

---

## Notes

- This skill replaces ad-hoc sentinel-parsing with a single `bug-state.py` invocation. Do not
  re-introduce sentinel-parsing logic here; that lives in the script.
- For human-only "what's next?" checks, prefer this over `/lazy-bug` itself — `/lazy-bug` will
  dispatch a sub-skill, `/lazy-bug-status` just reports.
- The script is project-agnostic for the `docs/bugs/` layout; this skill works in any repo with
  a `docs/bugs/` directory containing `SPEC.md` files (queue.json is optional).
- For the equivalent feature pipeline dashboard, use `/lazy-status`.
