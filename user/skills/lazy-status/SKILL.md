---
name: lazy-status
description: Read-only progress dashboard — runs lazy-state.py and formats its output. Shows current feature, queue progress, next /lazy action, blockers, and MCP test status.
argument-hint: [optional: "--cloud" to use the /lazy-cloud state machine]
model: haiku
plan-mode: never
allowed-tools: ["Bash", "Read"]
---

# Lazy Status

Read-only dashboard for the autonomous feature pipeline. Runs `~/.claude/scripts/lazy-state.py`, parses its JSON output, and formats a compact status report. **This skill is pure presentation — all state inference lives in the script.**

State-machine logic lives exclusively in `lazy-state.py`. If the dashboard is wrong, fix the script — do not duplicate the state machine here.

---

## Step 0: Parse Arguments

If `$ARGUMENTS` contains `--cloud`, pass `--cloud` to the state script. Otherwise run without it.

The cloud variant changes nothing about this skill's behavior beyond which sub-skill the script picks for Step 9 (workstation: `mcp-test`; cloud: `__write_deferred_non_cloud__`) and how it handles cloud-saturated features at Step 2.

---

## Step 1: Run lazy-state.py

```bash
python3 ~/.claude/scripts/lazy-state.py [--cloud]
```

Capture stdout (one JSON object). If the script exits non-zero, print its error verbatim and STOP — do not try to format malformed state.

Parse the JSON:
- `feature_id`, `feature_name`, `spec_path` — current-feature context (null when there is no current feature)
- `current_step` — the state script's human-readable position
- `sub_skill`, `sub_skill_args` — what /lazy would dispatch next
- `terminal_reason`, `notify_message` — set when the pipeline halts
- `device_deferred_features` — features the device axis skipped this probe (each has `DEFERRED_REQUIRES_DEVICE.md` + no `VALIDATED.md` on a no-real-device host). Always present; non-empty means lingering In-progress deferrals awaiting a real-device host.

---

## Step 2: Gather Light Additional Context

These are presentation-only enrichments — they do NOT influence state. Run in parallel:

1. `git log --oneline -1` → last commit (hash + message).
2. If `feature_name` is set: count `### Phase` headings in `{spec_path}/PHASES.md` (if it exists) and count how many phases have ALL deliverables checked (`- [x]`) → produces "Phase {current}/{total}".
3. If `feature_name` is set: list `{spec_path}/mcp-tests/` entries if the directory exists.
4. If `feature_name` is set AND `{spec_path}/BLOCKED.md` exists: parse its YAML frontmatter per `~/.claude/skills/_components/sentinel-frontmatter.md` and grab the `phase` and `recovery_suggestion` fields.
5. From `docs/features/queue.json`: total queue length and how many features have a strikethrough+COMPLETE row in `docs/features/ROADMAP.md`.
6. **Lane rows (parallel-worktree-batch-execution):** if the repo's keyed state dir holds a `lanes.json` lane ledger (`$(python3 -c "import sys,os;sys.path.insert(0,os.path.expanduser('~/.claude/scripts'));import lazy_core;lazy_core.set_active_repo_root(os.getcwd());print(lazy_core.claude_state_dir(create=False))")/lanes.json`), read it (one `Bash` JSON read — presentation only). Group entries via the ledger's `status` field (`claimed`/`lane-complete`/`merged`/`demoted`/`parked`). For each still-interesting lane (anything not `merged`), optionally enrich with a read-only per-worktree probe `python3 ~/.claude/scripts/lazy-state.py --repo-root <pool>/<slot> --feature-id <id>` when the worktree still exists. Absent file ⇒ skip entirely (output byte-identical to today).

If any of these reads fail (file missing, parse error), continue with the field set to `"—"`. Do not error out — this skill is a dashboard.

---

## Step 3: Map sub_skill to a Human-Readable Next Action

The state script emits both real sub-skill names and pseudo-skills (prefixed `__`). Translate:

| `sub_skill` from script | "Next /lazy action" |
|-------------------------|---------------------|
| `null` + `terminal_reason` set | halt — see Terminal column below |
| `spec` | /spec — generate/finalize spec or research prompt |
| `spec-phases` | /spec-phases — decompose into phases |
| `write-plan` | /write-plan — write the implementation plan |
| `execute-plan` | /execute-plan — run the next plan |
| `mcp-test` | /mcp-test — validate via MCP |
| `realign-spec` | /realign-spec --apply — reality-check upstream + act on verdict |
| `__write_deferred_non_cloud__` | DEFER MCP test (cloud) → phases complete routes directly to the Step 9 MCP gate on the next cycle (retro is unwired) |
| `__write_validated_from_skip__` | promote SKIP_MCP_TEST.md → VALIDATED.md |
| `__write_validated_from_results__` | promote MCP_TEST_RESULTS.md → VALIDATED.md |
| `__mark_complete__` | mark feature complete on ROADMAP + cleanup sentinels |
| `__flip_plan_complete_cloud_saturated__` | flip In-progress plan → Complete (cloud-saturated: only unchecked WUs are workstation-only deferred per DEFERRED_NON_CLOUD.md) |
| `__flip_plan_complete_stale__` | flip In-progress/Ready plan → Complete (stale: all referenced WUs already checked, frontmatter not yet flipped) |

Terminal-reason mapping:

| `terminal_reason` | Status line |
|---|---|
| `blocked` | "BLOCKED — see {spec_path}/BLOCKED.md" |
| `needs-research` | "Awaiting Gemini research (RESEARCH_PROMPT.md exists, RESEARCH.md absent)" |
| `needs-input` | "Awaiting human decision — see {spec_path}/NEEDS_INPUT.md" |
| `needs-spec-input` | "No SPEC/research yet — run /spec interactively" |
| `completion-unverified` | "⚠ {feature} marks Complete with no COMPLETED.md receipt — flipped outside the gate. Reconcile: reopen to In-progress, or `lazy-state.py --backfill-receipts` to grandfather." |
| `stale_upstream` | "STALE UPSTREAM — an upstream item changed since materialize (see {spec_path}/STALE_UPSTREAM.md). Re-materialize / realign, or reject." |
| `queue-blocked-on-research` | "Queue blocked on research — every remaining feature is research-pending (only reachable under --skip-needs-research)" |
| `all-features-complete` | "ALL FEATURES COMPLETE — nothing left in queue" |
| `cloud-queue-exhausted` | "Cloud queue exhausted — run /lazy on workstation for MCP testing" |
| `device-queue-exhausted` | "Device queue exhausted — remaining feature(s) have real-device-only assertions deferred via DEFERRED_REQUIRES_DEVICE.md. Re-run /lazy on a real-device host (ALGOBOOTH_REAL_AUDIO_DEVICE=1 or native hardware) to certify them." |
| `queue-missing` | "queue.json not found" |

---

## Step 4: Format and Output

Output this exact format (fill in values, replacing missing fields with `—`):

```
## Pipeline Status{ (cloud)}

**Current:** {feature_name | "—"} (Phase {current}/{total} — {state})
**State step:** {current_step | "—"}
**Queue:** {completed}/{total queue length} features complete ({remaining} remaining)
**Last commit:** {short hash} "{commit message}"
**Blockers:** {None | "<BLOCKED phase>: <recovery_suggestion>"}
**MCP Tests:** {count} scenarios linked | Not yet created | Skipped (see SKIP_MCP_TEST.md) | Deferred (cloud) | Deferred (real-device — see DEFERRED_REQUIRES_DEVICE.md)
**Device-deferred:** {None | comma-separated `device_deferred_features`} — features awaiting a real-device host
**Lanes:** {one row per lane from lanes.json: `{item} · {slot} · {branch} · {status}` — a parked lane renders `⬡ needs-input (lane parked)` / `⬡ blocked (lane parked)`; a demoted lane renders `↩ demoted: serial (branch preserved)`}
**Next /lazy action:** {mapped action from Step 3}
```

Notes:

- If `feature_name` is null (terminal queue state), drop the **Current**, **Blockers**, and **MCP Tests** lines and surface just **State step**, **Queue**, **Last commit**, and **Next /lazy action** — the latter will be the terminal status line.
- When `terminal_reason` is `blocked`, the **Blockers** line takes the BLOCKED.md `phase` + `recovery_suggestion` from Step 2.4.
- The "Phase {current}/{total}" annotation is best-effort; if PHASES.md doesn't exist yet, write `"—/— ({state})"`.
- The "Skipped (cloud)" / "Deferred (cloud)" labels for MCP Tests apply when `$ARGUMENTS` contains `--cloud` AND the spec dir has SKIP_MCP_TEST.md / DEFERRED_NON_CLOUD.md respectively.
- The "Deferred (real-device)" label applies when the spec dir has `DEFERRED_REQUIRES_DEVICE.md` — real-device-only assertions deferred on the device axis (independent of `--cloud`).
- The **Device-deferred** line lists `device_deferred_features` from the state JSON (features the QUEUE skipped past this probe, distinct from the current feature). Drop the line when the list is empty. This is the deterministic surface for lingering In-progress deferrals that would otherwise be invisible until queue exhaustion.
- The **Lanes** rows appear ONLY when a `lanes.json` lane ledger exists in the repo's keyed state dir (a `/lazy-batch-parallel` run, live or recently flushed). Drop the line entirely otherwise — output stays byte-identical for serial-only repos. Rows are read from the ledger (+ optional per-worktree probes); this skill never mutates the ledger, leases, or any lane worktree.

**Do NOT execute any skills or modify any files. Report only.**

---

## Notes

- This skill replaces the old prose-based state inference with a single `lazy-state.py` invocation. Do not re-introduce sentinel-parsing logic here; that lives in the script.
- For human-only "what's next?" checks, prefer this over `/lazy` itself — /lazy will dispatch a sub-skill, /lazy-status just reports.
- The script is project-agnostic; this skill works in any repo with `docs/features/queue.json`.
