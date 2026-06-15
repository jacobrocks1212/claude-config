---
name: lazy-bug
description: Stateless dispatcher — infers bug state from filesystem via bug-state.py, invokes exactly ONE sub-skill per invocation to progress the current bug. Drives docs/bugs/ (NOT docs/features/). The `__mark_fixed__` special action performs the archive-on-fix flow: writes/verifies FIXED.md receipt (kind: fixed, gated by the completion-integrity gate), sets SPEC **Status:** Fixed + **Fixed:** and **Fix commit:** header lines, git mv to docs/bugs/_archive/, repoints inbound root-relative references, and commits. Receipt is FIXED.md (kind: fixed); Won't-fix bugs are receipt-EXEMPT. No research/Gemini steps, no stub-spec step, no realign step — N/A to bugs. Status vocab: Open | Investigating | In-progress | Fixed | Won't-fix.
argument-hint: [optional: "status" to report, "skip" to skip current bug, or an ad-hoc task / `--adhoc "<task>"` to enqueue work at the top of the queue]
plan-mode: never
---

# Lazy Bug — Autonomous Bug Dispatcher

Thin LLM wrapper around `~/.claude/scripts/bug-state.py`. Each invocation:

1. Loads tools and parses arguments
2. Runs the state script to determine the next action
3. Either reports a terminal state and stops, or dispatches **exactly one** sub-skill
4. Logs work and stops

Designed for fresh sessions. Run `/lazy-bug` repeatedly to progress through the entire bug queue.
The state-machine logic lives in `bug-state.py` (source of truth). This skill is dispatch glue.

**HARD REQUIREMENT — ONE SKILL PER INVOCATION:** Execute at most one sub-skill (via Skill tool).
After it completes, report what happened and STOP. Do not chain multiple skills.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. This skill
dispatches directly.

**HARD REQUIREMENT — STATUS BOOKENDS:** Every /lazy-bug invocation must produce two status messages:

1. **Before acting** (after running bug-state.py, before invoking any skill):
   ```
   ## /lazy-bug — {bug_name} (Severity {severity})
   **State:** {current_step from state script}
   **Action:** {what skill will be invoked and why}
   ```
   No user confirmation needed — just announce and proceed.

2. **After acting** (after the dispatched skill returns or after a STOP decision):
   ```
   ## /lazy-bug — Done
   **Completed:** {what was accomplished this invocation}
   **Issues:** {any problems encountered, or "None"}
   **Next `/lazy-bug` will:** {best guess based on the state script's output, or "Run bug-state.py to find out"}
   ```
   If there were issues (partial failures, warnings, unexpected state), surface them here.

---

## Sentinel File Format

All sentinel files this skill reads or writes follow the canonical YAML-frontmatter schema.

**Sentinel frontmatter schema:** when you write or validate any sentinel file (NEEDS_INPUT.md / BLOCKED.md / VALIDATED.md / FIXED.md / etc.), **Read `~/.claude/skills/_components/sentinel-frontmatter.md`** for the required `kind:`/`provenance:`/field schema. (Read on demand — do not assume it is already in context.)

When this skill writes a sentinel (Step 4 special actions), emit the YAML frontmatter first, then a
blank line, then a human-readable markdown body. When this skill reads a sentinel, parse the
frontmatter per the protocol above; the markdown body is for humans only.

---

## Step 0.0: Environment Preflight (FIRST — before the start banner and before remote sync)

**Read and follow `~/.claude/skills/_components/lazy-preflight.md` as the very first action of this
invocation — before the start banner, before Step 0.4 remote sync, before the first state probe.**
Run its read-only check block (skills symlink resolves, `~/.claude/scripts/bug-state.py` exists,
`python3` runs, node resolvable — prepending `/c/nvm4w/nodejs` if needed). If any check fails, print the
component's setup recipe and **STOP — zero cycles consumed** (do not print the banner, do not call the
state script, do not enter the loop). On success, node is on PATH for the whole session (no per-call
`export PATH`), and you continue to the banner / Step 0.4 as normal.

---

## Step 0: Load Tools and Parse Arguments

1. Load PushNotification: `ToolSearch({ query: "select:PushNotification" })`
2. Parse `$ARGUMENTS`:
   - If `"status"` → run the same logic as `/lazy-bug-status` (read-only report) and STOP
   - If `"skip"` → mark current bug as skipped (see Step 5) and STOP
   - If it starts with `--adhoc` (optionally followed by task text), OR is any other non-empty
     free-text that is not one of the keywords above → treat it as an **ad-hoc task**: run
     **Step 0.3 (Ad-hoc Enqueue)**, then proceed to Step 1. (`--adhoc` with no text infers the
     task from the conversation.)
   - If empty → proceed to Step 1 (normal queue order)

---

## Step 0.3: Ad-hoc Enqueue (only when an ad-hoc task was supplied)

!`cat ~/.claude/skills/_components/adhoc-enqueue.md`

---

## Step 1: Run bug-state.py

Invoke the state inference script with the project root as the working directory:

```bash
python3 ~/.claude/scripts/bug-state.py
```

Capture stdout (a single JSON object). If the script exits non-zero, surface the error to the user
and STOP — do not try to parse malformed state.

**Real-device capability (audio MCP deferral).** The script's `--real-device` defaults to `auto`,
which reads `$ALGOBOOTH_REAL_AUDIO_DEVICE` (absent → no device). On a no-real-device host (WSL2/CI,
where the audio backend runs the HeadlessPumpDriver) the state machine DEFERS real-device-only MCP
assertions rather than skipping them; on a real-device host (set `ALGOBOOTH_REAL_AUDIO_DEVICE=1`,
or native hardware) it RE-OPENS any deferred assertions for certification. You do not normally pass
`--real-device` by hand — the env var is the host's standing declaration, and `/mcp-test` observes
the live backend via `get_audio_mode` (`mode: cpal` & not `forced` → real device) when it runs.
See `DEFERRED_REQUIRES_DEVICE.md` in the sentinel schema.

Parse the JSON. You now have:
- `feature_id`, `feature_name`, `spec_path` — current bug context (null if no current bug)
- `current_step` — human-readable description of where we are in the state machine
- `sub_skill` — the skill to dispatch (null when terminal or when a special action is needed)
- `sub_skill_args` — exact args string for the sub-skill
- `terminal_reason` — set when the state machine halts (e.g. `"blocked"`, `"all-bugs-fixed"`)
- `notify_message` — string for PushNotification when terminal

---

## Step 2: Handle Terminal States

If `terminal_reason` is set, branch on whether it is **operator-resolvable** (ask the operator how to proceed, then enact it as this invocation's one action) or a **clean stop** (report + STOP). The guiding rule: `/lazy-bug` does not dead-end on a recoverable obstacle — it asks for a resolution path instead.

### 2a. Operator-resolvable terminals → ask for a resolution path (do NOT bare-STOP)

For `blocked`, `needs-input`, `completion-unverified`, and `stale_upstream`, follow the shared operator-directed halt-resolution component — re-print the obstacle context, `AskUserQuestion` the resolution path, dispatch the Opus apply-resolution subagent to enact it (neutralizing any sentinel by RENAME, never a `kind:` flip — `bug-state.py` keys halts on the filename), then STOP per the **single-dispatch** post-enact rule (the enactment is this invocation's ONE meaningful action; the next `/lazy-bug` continues from the enacted state). Read and apply exactly:

`~/.claude/skills/_components/halt-resolution.md`

Use the matrix's `blocked` and `needs-input` rows (single-dispatch wrappers route those here — `/lazy-bug` has no bespoke Step 1g/1h); for `completion-unverified` use that row (reopen & re-validate / grandfather via `bug-state.py --backfill-receipts` / defer / halt). Only the operator-chosen "Halt for manual fix" reverts to a report + STOP.

### 2b. Clean-stop terminals → report + STOP

For these there is nothing to resolve in-session: PushNotification with `notify_message`, print the **before** bookend (State `current_step`, Action `"halt — {terminal_reason}"`) and the **after** bookend (Completed "halted on {terminal_reason}"; Next `/lazy-bug` will: per the row below), then STOP.

| `terminal_reason` | After-bookend / operator action |
|------|---|
| `all-bugs-fixed` | All bugs fixed or retired; nothing else to do |
| `all-remaining-deferred` | Every open bug is operator-parked via `DEFERRED.md` (a deliberate park, not an obstacle). Re-include a bug by deleting its `DEFERRED.md`, then re-run. |
| `cloud-queue-exhausted` | Workstation-only path — does not occur for plain `/lazy-bug` |
| `device-queue-exhausted` | Only on a NO-real-device host: the remaining bug(s) carry real-device-only assertions deferred via `DEFERRED_REQUIRES_DEVICE.md`. Tell the user to re-run `/lazy-bug` on a real-device host (set `ALGOBOOTH_REAL_AUDIO_DEVICE=1` or run on native hardware) to certify them. |
| `queue-missing` | `docs/bugs/queue.json` missing — surface the expected path; the queue is optional (on-disk bugs are auto-discovered), so this is informational |

---

## Step 3: Handle Special Actions (sentinel writes / completion)

If `sub_skill` begins with `__` (double-underscore), it is a **special action** the wrapper
performs directly, not a Skill dispatch. The wrapper itself does the small file edits and commit.

### `__write_validated_from_skip__`

`sub_skill_args` is `{spec_path}`. SKIP_MCP_TEST.md exists; write VALIDATED.md so the state
machine progresses to retro on the next invocation.

1. Parse `{spec_path}/SKIP_MCP_TEST.md`'s frontmatter.
2. Write `{spec_path}/VALIDATED.md` with kind `validated`, `mcp_scenarios: []`,
   `result: all-passing`, and a body note: "MCP tests skipped per prior SKIP_MCP_TEST.md".
3. Print the after-status bookend, STOP.

### `__write_validated_from_results__`

`sub_skill_args` is `{spec_path}`. MCP_TEST_RESULTS.md exists with all-passing; write VALIDATED.md.

1. Parse `{spec_path}/MCP_TEST_RESULTS.md`'s frontmatter — extract `scenarios`.
2. Write `{spec_path}/VALIDATED.md` with kind `validated`, the parsed scenarios,
   `result: all-passing`.
3. Print the after-status bookend, STOP.

### `__mark_fixed__`

`sub_skill_args` is `{spec_path}`. VALIDATED.md exists (retro is unwired — RETRO_DONE.md is no
longer required); finalize the bug via the archive-on-fix procedure.

**Gate 1 — MCP-coverage audit** per
`~/.claude/skills/_components/mcp-coverage-audit.md`.
Run the audit with `{spec_path}` and `{bug_id}`. If the audit returns:

- `uncovered:N` — per the audit component's D7 outcome (`~/.claude/skills/_components/completeness-policy.md`
  §4 — Gate 1 never asks, no NEEDS_INPUT.md): perform the docs-only routing as THIS invocation's
  remaining action — author the `mcp-tests/` scenario(s) for the uncovered decisions (or write
  the SPEC test-exempt note for any decision in a documented MCP-untestable class per
  `docs/features/mcp-testing/SPEC.md`), emit one `⚖ policy:` line per decision, commit + push.
  Do NOT run Gate 2 or the archive steps. Print the after-status bookend (Completed:
  "MCP-coverage gate halted mark-fixed — authored corrective coverage / test-exempt note(s) for
  {N} locked decision(s)", Next `/lazy-bug` will: "Run /mcp-test against the corrective
  scenario(s), then re-attempt __mark_fixed__ (the re-run audit returns clean)"), STOP.
- `clean` — proceed to Gate 2.

**Gate 2 — Completion-integrity gate and FIXED.md receipt.**

The gate and archive procedure are documented in the shared component below:

!`cat ~/.claude/skills/_components/mark-fixed-archive.md`

Run the gate and archive procedure per the component above with `{spec_path}`, `{bug_id}`, and
`{cloud}=false` (workstation). If the gate returns:

- `gated` — receipt written, all preconditions met. Proceed with the archive steps documented in
  the component.
- `refused:<reason>` — the gate just wrote `{spec_path}/NEEDS_INPUT.md`. Do NOT run the archive
  steps. Print the after-status bookend (Completed: "completion-integrity gate halted mark-fixed
  — {reason}", Next `/lazy-bug` will: "Surface NEEDS_INPUT.md and reconcile the completion gap"),
  STOP.

After the component's archive procedure completes successfully:
1. PushNotification: `"{bug_name} FIXED and archived. Run /lazy-bug to continue."`
2. Print the after-status bookend, STOP.

### `__flip_plan_complete_cloud_saturated__`

`sub_skill_args` is the absolute path of a plan file with `status: In-progress`. Emitted only by
`bug-state.py --cloud` when the plan's only unchecked WUs are documented in
`{spec_path}/DEFERRED_NON_CLOUD.md` as workstation-only.

1. Read the plan file. Locate the `status:` line inside the YAML frontmatter fence.
2. Replace ONLY the value: `In-progress` → `Complete`. Leave every other frontmatter field and
   the markdown body untouched. If the line is already `Complete`, no-op (idempotent).
3. Stage the plan file and invoke `Skill({ skill: "commit", args: "chore({bug_id}): mark plan
   Complete (cloud-saturated)" })`.
4. Print the after-status bookend, STOP.

### Any other `__*__` action

Print the after-status bookend with an explanatory message ("unrecognized special action:
<name>") and STOP. Do not improvise.

---

## Step 4: Dispatch the Sub-Skill

If `sub_skill` is a regular skill name (not `__*__`), invoke it exactly:

```
Skill({ skill: "<sub_skill>", args: "<sub_skill_args>" })
```

Sub-skill routing table (from `bug-state.py`'s `SKILL_*` constants):

| `sub_skill` from script | Dispatches to |
|------------------------|--------------|
| `spec-bug` | `/spec-bug` — root-cause investigation |
| `plan-bug` | `/plan-bug` — consolidated planning round-trip (emitted when SPEC.md is `**Status:** Concluded` and no PHASES.md exists; authors PHASES.md from the concluded investigation, then runs `/write-plan`) |
| `spec-phases` | `/spec-phases` — decompose bug SPEC into PHASES |
| `write-plan` | `/write-plan` — write implementation plan |
| `execute-plan` | `/execute-plan` — run the next ready plan |
| `retro-feature` | `/retro-feature` — retrospective pass |
| `mcp-test` | `/mcp-test` — MCP / runtime validation |

After the skill returns:
1. **Post-`/execute-plan` (and `/mcp-test`) ledger-consistency guard.** If `sub_skill` was
   `/execute-plan` or `/mcp-test`, run a single-turn consistency check before reporting (one
   git/grep check, not polling): (a) `git status --short` is empty; (b) `HEAD == origin/<branch>`
   (after `git fetch origin <branch>`); (c) **(`/execute-plan` only)** the plan part's frontmatter
   is `status: Complete` AND `grep -c "- \[ \]" {spec_path}/PHASES.md` returns `0`. The dispatched
   skill's atomic gate+commit should leave this clean, but it empirically loses its turn between
   gates and commit; this guard catches the residue. If any check fails, reconcile inline (stage +
   commit + push residue, tick the remaining PHASES.md verification boxes, re-flip the plan status
   if needed) and re-check before reporting — do NOT report a clean run while the tree is dirty or
   the dual ledger is half-flipped.
2. Print the after-status bookend (Completed: "ran /<sub_skill>", Next `/lazy-bug` will:
   "Re-run bug-state.py to determine.").
3. STOP.

The sub-skill is responsible for its own internal status bookends.

---

## Step 5: Skip Current Bug

Only triggered when `$ARGUMENTS` contains `"skip"`.

1. Run `python3 ~/.claude/scripts/bug-state.py` to find the current bug.
2. Ask why (via AskUserQuestion): "Why should {bug_name} be skipped?"
3. Mark the bug as Won't-fix in its SPEC.md (update `**Status:** Won't-fix`) and note the
   reason in a `> Skipped: {reason}` line below the status block.
4. The next `/lazy-bug` invocation will automatically pick up the following bug.
5. STOP.

---

## Sentinel Files Reference

| File | Created by | Purpose | Lifecycle |
|------|-----------|---------|-----------|
| `plans/*.md` | /write-plan, /retro-feature, etc. | Colocated plan files | Persists (audit trail) |
| `BLOCKED.md` | /execute-plan or /lazy-bug | Blocker details | Persists until resolved |
| `MCP_TEST_RESULTS.md` | /lazy-bug (after mcp-test) | Test results with pass/fail | Persists permanently (audit trail) |
| `VALIDATED.md` | /lazy-bug (after 100% pass) | Validation gate | Deleted on bug archival |
| `SKIP_MCP_TEST.md` | /lazy-bug (assessment) | Documents why MCP testing was skipped | Persists permanently |
| `DEFERRED_REQUIRES_DEVICE.md` | /mcp-test (no-device host) | Defers real-device-only assertions | Deleted by a real-device run after certification |
| `RETRO_DONE.md` | /lazy-bug (after retro execution) | Retro completion gate | Deleted on bug archival |
| `NEEDS_INPUT.md` | any `--batch` skill | Halt: ambiguous decision encountered | Deleted when the human resolves the decision |
| `FIXED.md` | /lazy-bug `__mark_fixed__` gate | Completion receipt (kind: fixed) | Persists permanently in `_archive/` |
| `mcp-tests/*.md` | /lazy-bug (symlinks) | Links to test scenarios | Persists permanently |

---

## State Machine Summary

The state machine lives in `~/.claude/scripts/bug-state.py`. This skill is a thin LLM wrapper
that runs the script, dispatches the named sub-skill, and stops. The high-level shape is:

```
[ad-hoc task supplied?]  → Step 0.3 enqueue at top of queue (Bash, once) → fall through
bug-state.py → JSON {sub_skill, sub_skill_args, terminal_reason}

terminal_reason set?     → notify + STOP
sub_skill = "__*__"?     → wrapper performs special action (sentinel write / mark fixed) + STOP
sub_skill = real skill?  → Skill({skill, args}) → STOP
```

The script mirrors the lifecycle:

```
SPEC (Open/Investigating) → spec-bug (investigation) → PHASES → write-plan → execute-plan
→ mcp-test (VALIDATED.md / skip / device-defer)
→ __mark_fixed__ (FIXED.md receipt → Status: Fixed → git mv _archive/ → commit)
```

> Retro unwired (operator decision, 2026-06): the `/retro-feature` step that previously sat
> between execute-plan and mcp-test is removed — `bug-state.py` routes directly to the MCP gate
> once phases are complete. The `/retro-feature` skill remains in the catalog (restore path).

**No research/Gemini steps (N/A to bugs).** The feature pipeline's Step 4.5 stub-spec, Step 4.6
realign, and Step 5 research gate have no bug analog — bugs have a root cause to investigate
(dispatched as `spec-bug`), not a feature to design via Gemini research.

**Won't-fix vs Fixed:** `Won't-fix` is receipt-exempt (never produces a FIXED.md; retired without
fix). `Fixed` without a receipt halts on `completion-unverified`. The only valid terminal is
`Fixed` + `FIXED.md` (written by the `__mark_fixed__` gate) + in `_archive/`.

When the state machine needs to change, update `bug-state.py`. This skill is dispatch glue; the
logic lives in the script.
