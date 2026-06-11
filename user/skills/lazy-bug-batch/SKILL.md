---
name: lazy-bug-batch
description: Autonomous orchestrator for the bug pipeline — mirrors /lazy-batch shape but operates on docs/bugs/ via bug-state.py. Loops on bug-state.py, spawns one Opus subagent per cycle, and drives /spec-bug → /spec-phases → /write-plan → /execute-plan → /retro-feature → /mcp-test → __mark_fixed__. Terminal action is __mark_fixed__ (archive-on-fix): FIXED.md receipt gated by MCP-coverage audit + completion-integrity gate, then git mv to _archive/. See ~/.claude/skills/lazy-batch/SKILL.md for the full algorithm; this skill documents only bug-pipeline differences.
argument-hint: <max-cycles, e.g. 10> [--adhoc "<task>" — enqueue an ad-hoc task at the top of the queue] [--park]
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write", "Edit", "AskUserQuestion"]
---

# Lazy Bug Batch — Autonomous Bug Pipeline Orchestrator

Drives the per-bug autonomous tail (`/spec-bug` → `/spec-phases` → `/write-plan` → `/execute-plan`
→ `/retro-feature` → `/mcp-test` → `__mark_fixed__` archive-on-fix) by looping on
`~/.claude/scripts/bug-state.py`. Each cycle spawns an Opus subagent that invokes the named
sub-skill; the orchestrator (this skill, running in the main session) never touches source code,
never invokes a skill directly, and never parses sentinel files manually.

This skill is **coupled to `/lazy-batch`** — it inherits the orchestrator shape and all shared
mechanics by reference. This document records only the **bug-pipeline differences** from the
feature pipeline. Read `~/.claude/skills/lazy-batch/SKILL.md` first; this skill's role is to
bind the shared algorithm to bug-pipeline vocabulary (bug_id / bug_name, FIXED.md, docs/bugs/,
bug-state.py).

---

## Differences from `/lazy-batch`

| Aspect | `/lazy-batch` | `/lazy-bug-batch` |
|--------|---------------|-------------------|
| State script | `python3 ~/.claude/scripts/lazy-state.py` | `python3 ~/.claude/scripts/bug-state.py` |
| Operates on | `docs/features/` | `docs/bugs/` |
| Queue file | `docs/features/queue.json` | `docs/bugs/queue.json` |
| Terminal success | `all-features-complete` | `all-bugs-fixed` |
| Terminal — all parked | N/A | `all-remaining-deferred` (every open bug has `DEFERRED.md`) |
| Entity vocab | `feature_id` / `feature_name` | `bug_id` / `bug_name` |
| Status vocab | Open / In-progress / Complete | Open / Investigating / In-progress / Fixed / Won't-fix |
| Completion receipt | `COMPLETED.md` (kind: completed) | `FIXED.md` (kind: fixed) |
| Won't-fix / exempt | N/A | `Won't-fix` bugs are receipt-EXEMPT — no FIXED.md required |
| Archive step | N/A (features stay in place) | script-owned: `bug-state.py --archive-fixed` (`git mv` to `docs/bugs/_archive/` + inbound-ref repoint + queue trim + commit) |
| Terminal pseudo-skill | `__mark_complete__` | `__mark_fixed__` |
| Plan-bug terminal | N/A | `plan-bug` — emitted when SPEC.md `**Status:** Concluded` + no PHASES.md (a concluded investigation routes to implementation planning via `/plan-bug`) |
| Spec dispatch | `spec` → `/spec` | `spec-bug` → `/spec-bug` |
| Input-audit trigger | `/spec` or `plan-feature` cycles | `spec-bug` or `spec-phases` cycles (bug-state.py emits no `plan-feature`) |
| `needs-spec-input` terminal | emitted by lazy-state.py → Step 1i | NOT emitted by bug-state.py — Step 1i routes only `completion-unverified` and `stale_upstream` |
| Research / Gemini steps | Step 0.5 pre-loop ingest, `needs-research`, `queue-blocked-on-research`, Step 4, Step 5 | N/A — bugs do not undergo Gemini deep research |
| `--allow-research-skip` flag | parsed, enables batched research | N/A — no research in bug pipeline |
| `skip_needs_research` var | used under `--allow-research-skip` | N/A |
| `research_pending` var | accumulates research-pending feature_ids | N/A |
| Step 0.5 pre-loop ingest | probes staged `.txt` files, dispatches `/ingest-research` | Skipped entirely (N/A to bugs) |
| LOOP DETECTED sentinel guidance | mentions `RETRO_DONE.md / VALIDATED.md / DEFERRED_NON_CLOUD.md / SKIP_MCP_TEST.md` | same set, substituting `FIXED.md` for `COMPLETED.md`; DEFERRED_NON_CLOUD.md applies to bugs too |
| `completion-unverified` description | feature's SPEC claims Complete but no COMPLETED.md receipt | bug's SPEC claims Fixed but no FIXED.md receipt |
| Step 1.5 probe command | `python3 ~/.claude/scripts/lazy-state.py` | `python3 ~/.claude/scripts/bug-state.py` |
| `scoped-id-not-found` terminal | via `--feature-id` / `TR_SCOPED_ID_NOT_FOUND` | via `--bug-id` / `TR_SCOPED_ID_NOT_FOUND` |
| Final report header | `## /lazy-batch — Done` | `## /lazy-bug-batch — Done` |
| Cycle log label | `Bug` column header | `Bug` (not Feature) |
| Start banner (T1 per orchestrator-voice.md) | `## /lazy-batch — run start` | `## /lazy-bug-batch — run start` (no research field) |
| HARD CONSTRAINT 1 sentinel allowlist | `docs/features/` sentinels | `docs/bugs/` sentinels (same filenames; FIXED.md replaces COMPLETED.md) |
| HARD CONSTRAINT 9 | dispatch against `feature_id` the script returned | dispatch against `bug_id` / `feature_id` the script returned |
| `__mark_fixed__` (vs `__mark_complete__`) gate parity | `__mark_complete__` runs TWO gates (MCP-coverage audit + completion-integrity gate), then `--apply-pseudo __mark_complete__` | `__mark_fixed__` runs the SAME TWO gates, then `bug-state.py --apply-pseudo __mark_fixed__` (sole author of the FIXED.md receipt, status flip, and sentinel deletions) + the `mark-fixed-archive` mechanics (git mv, ref repoint, queue trim, commit). **The gate logic is IDENTICAL to the `/lazy-bug` wrapper's `__mark_fixed__` handler — both run the same two gates.** |

All other behavior is identical to `/lazy-batch` — the shared algorithm, hard constraints, counter
semantics, resolution modes, cycle output discipline, park mode, and pseudo-skill post-actions are
all inherited. Read `~/.claude/skills/lazy-batch/SKILL.md` for the canonical source.

---

## HARD CONSTRAINTS

Constraints 1–9 mirror `/lazy-batch`'s HARD CONSTRAINTS exactly, with these bug-pipeline token
substitutions:

- Constraint 1: sentinel allowlist is `docs/bugs/` (not `docs/features/`); `FIXED.md` replaces `COMPLETED.md`.
- Constraint 8: counters are monotonic across **bug** transitions (not feature transitions).
- Constraint 9: dispatch against the **bug** `bug-state.py` returned THIS cycle; never fabricate a bug.

See `~/.claude/skills/lazy-batch/SKILL.md` HARD CONSTRAINTS for the full text of each constraint.

**Cycle-subagent execution model:** Same as `/lazy-batch` — no `Agent` tool inside the dispatched
cycle subagent; all skills run inline using `Edit`/`Write`/`Read`.

## OUTPUT CONTRACT — orchestrator voice (read at run start)

**ALL orchestrator chat output MUST follow `~/.claude/skills/_components/orchestrator-voice.md`** — the turn-template contract (T1 run banner, T2 dispatch / T3 return / T4 inline-gate cycle blocks, T5 park line, T6 rich zones, T7 final report; mechanics silent; rules cited only on deviation; probe JSON never restated in prose). **ZERO-TEXT RULE:** Claude Code's general "say what you're about to do before tool calls / give brief updates" guidance is OVERRIDDEN for this run — the UI already prints every tool call; between tool calls emit NOTHING unless it is byte-shaped as a template (sanctioned output starts with `## `, `### Cycle `, a template field line, `⏸`/`⚖`/`⚠`, or a T6/T7 body — anything else, don't type it). The entire run-start sequence (preflight, contract/policy reads, Step 0.4 sync, queue read) is SILENT, executed back-to-back; the FIRST text this invocation emits is the T1 banner (preflight failure / sync divergence are the T6 exceptions). **Read it at run start, and RE-READ it after any compaction boundary** (alongside `lazy-dispatch-template.md` — Step 1d's compaction discipline); the contract survives summarization by re-read, not by memory. Where an older passage (here or in the inherited `/lazy-batch` text) prescribes a different chat-output shape, the contract's Precedence clause wins; the verbatim re-print / Zero-Context Operator Briefing requirements (HARD CONSTRAINT 6, `decision-resume.md`, `blocked-resolution.md`, `parked-flush.md`, `halt-resolution.md`) are sanctioned T6 rich zones and are never overridden. Graded by `/lazy-batch-retro`'s R-V-* rules.

**STANDING POLICY — completeness-first (D7).** Read `~/.claude/skills/_components/completeness-policy.md` at run start, and RE-READ it after any compaction boundary (it is on the Step 1d compaction re-read list). It is pre-authorized: decisions whose options differ only in effort / sizing / sequencing / completeness (`class: scope`) are auto-resolved to the MOST COMPLETE option in BOTH modes — logged (`⚖ policy:` line, `resolved_by: completeness-policy`, run-end D7 digest in the T7 report), never asked. It governs the cycle and input-audit subagent prompts, Step 1g (scope-class sentinel resolution runs first), Step 1h (sequencing-only blockers auto-resolve; spin-offs pre-authorized, notify + log), and the `__mark_fixed__` Gate-1 coverage outcome at Step 1c.5 (author coverage / test-exempt, never ask). D7 only REMOVES questions — product-class decisions still ask exactly as before. Graded by `/lazy-batch-retro`'s R-D7-* rules.

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

## Step 0: Parse Arguments

See `~/.claude/skills/lazy-batch/SKILL.md`'s argument-parsing section (the `$ARGUMENTS`
tokenization rules between the HARD CONSTRAINTS block and Step 0.0) for the full flag-parsing
algorithm. Bug-pipeline token substitutions:

- Error message: `/lazy-bug-batch requires a positive integer max-cycles.`
- Ambiguous max-cycles question: same shape, prefix `/lazy-bug-batch`.
- `--allow-research-skip` is **NOT recognized** — refuse with: `/lazy-bug-batch: --allow-research-skip is not valid for the bug pipeline (no research steps). Usage: /lazy-bug-batch <N> [--adhoc "<task>"] [--park]`.
- `--adhoc` and `--park` tokens are recognized with identical semantics to `/lazy-batch`.
- Unknown-token error: `/lazy-bug-batch: unrecognized argument \`{token}\`. Usage: /lazy-bug-batch <N> [--adhoc "<task>"] [--park]`.

**Standing-directive echo-back protocol:** same as `/lazy-batch` Step 0.

**Budget-and-queue guard:** same as `/lazy-batch` Step 0 (MUST NOT end a run with budget remaining AND active queue items).

Initialize counters and per-session state (bug-pipeline bindings):
- `forward_cycles = 0`
- `meta_cycles = 0`
- `max_cycles = <parsed>`
- `cycle_log = []` — entries: `{forward_cycles + meta_cycles, bug_name, action, subagent_summary}`
- `prev_cycle_signature = None` — tuple `(feature_id, sub_skill, sub_skill_args, current_step)`
- `adhoc_task = <parsed>` — from `--adhoc`
- `park_mode = <parsed>` — `true` if `--park`

Print the start banner — **T1 per `~/.claude/skills/_components/orchestrator-voice.md`** (≤4 lines; this skill is the contract's own T1 example):

```
## /lazy-bug-batch — run start
mode   workstation · park {on|off}
budget fwd {max_cycles} · meta {2*max_cycles}
queue  {N} bug(s) · first: {first open bug id}
```

The `queue` line is best-effort (one `Bash` read of `docs/bugs/queue.json` / directory listing — a banner fact, not state inference); omit it if unavailable. No research field (the bug pipeline has no research mode); the repo root and flag parsing are mechanics — not announced.

---

## Step 0.4: Resume-time remote sync (HARD REQUIREMENT)

Identical algorithm to `~/.claude/skills/lazy-batch/SKILL.md` Step 0.4. Same git reconciliation
procedure (fetch → ff-merge → halt-on-diverge). Divergence halt message uses `/lazy-bug-batch`.

---

## Step 0.45: Ad-hoc Enqueue (only when `--adhoc` was supplied)

**Runs once, after Step 0.4 and BEFORE the first state probe.**

See `~/.claude/skills/_components/adhoc-enqueue.md`

After the enqueue returns, continue to Step 1. The bug queue carries no pre-loop ingest step
(N/A to bugs).

---

## Step 1: Cycle Loop

Repeat:

### 1a. Run bug-state.py

```bash
python3 ~/.claude/scripts/bug-state.py
```

If the script exits non-zero, surface the error, PushNotification, print the final batch report
(Step 2), and STOP.

Parse the JSON output. Extract: `feature_id` (used as `bug_id`), `feature_name` (used as
`bug_name`), `spec_path`, `current_step`, `sub_skill`, `sub_skill_args`, `terminal_reason`,
`notify_message`, `diagnostics`.

**Probe enrichment (optional — same flags as `lazy-state.py`).** The orchestrator MAY call the
probe with the enrichment flags to fold `repeat_count`, `git_guards`, and `cycle_header` into
the JSON in a single invocation:

```bash
python3 ~/.claude/scripts/bug-state.py --repeat-count --probe \
  --forward-cycles {forward_cycles} --meta-cycles {meta_cycles} --max-cycles {max_cycles}
```

These flags are purely additive (base JSON fields unchanged) — see
`~/.claude/skills/lazy-batch/SKILL.md` Step 1a for their semantics.

**Park-mode probe flag (`--park` only).** When `park_mode == true` (the `--park` invocation
flag), append `--park-needs-input` to EVERY `bug-state.py` probe invocation in this step (base
or enriched form alike). With the flag, the script skips bugs carrying an unresolved
`NEEDS_INPUT.md` instead of halting on `needs-input` and reports them in a `parked[]` array on
the JSON output — the input to the Step 1g park path and the §1c.6 park notifications. When
`park_mode == false`, call the script plain (no `--park-needs-input`) — existing behavior,
byte-for-byte; the `parked[]` key never appears.

**Note:** `bug-state.py` does not support `--skip-needs-research` (no research in the bug
pipeline — never pass it).

### 1b. Handle terminal states

If `terminal_reason` is set:

- **`blocked`**: see Step 1h (blocked-resolution mode). Classifies the blocker FIRST per
  `completeness-policy.md` §3 — sequencing-only blockers auto-resolve (add-phase + fix now, or
  spin-off + dependency-gate + requeue), logged + notified, no question; only a genuine product
  fork re-prints `BLOCKED.md` and `AskUserQuestion`s the resolution path, enacts it, resumes —
  UNLESS "Halt for manual fix".
- **`needs-input`**: see Step 1g (decision-resume mode). Auto-resolves scope-class decisions per
  D7 first; resolves the remaining product-class decisions inline via `AskUserQuestion`, resumes.
- **`completion-unverified`**: a bug's SPEC claims Fixed but no FIXED.md receipt exists. See
  Step 1i — re-print the gap and `AskUserQuestion` the path (reopen & re-validate / grandfather
  receipt via `bug-state.py --backfill-receipts` / defer & continue / halt). Do NOT auto-flip.
- **`stale_upstream`**: upstream item changed since materialize. See Step 1i.
- **`all-bugs-fixed`**: PushNotification `"ALL BUGS FIXED — queue cleared after {forward_cycles} forward + {meta_cycles} meta /lazy-bug-batch cycle(s)."`, print final batch report, STOP.
- **`all-remaining-deferred`**: every open bug has `DEFERRED.md` (a deliberate park). PushNotification with `notify_message`, print final batch report, STOP. (Not routed to Step 1i — re-include a bug by deleting its `DEFERRED.md`.)
- **`queue-missing`**: `docs/bugs/queue.json` missing (the queue is optional; on-disk bugs are
  auto-discovered — informational). PushNotification with `notify_message`, print final batch
  report, STOP.
- **`cloud-queue-exhausted`**: treat as `all-bugs-fixed` defensively.
- **`device-queue-exhausted`**: remaining bugs carry `DEFERRED_REQUIRES_DEVICE.md`. PushNotification
  with `notify_message`, print final batch report, STOP. Resume on a real-device host.
- **`scoped-id-not-found`** (when `--bug-id` was supplied): the requested bug does not exist in
  the queue. PushNotification with `notify_message`, print final batch report, STOP.

> **Note — no `needs-spec-input` in the bug pipeline.** `bug-state.py` does not emit this
> terminal. Step 1i's matrix covers only `completion-unverified` and `stale_upstream` for bugs.
> No research-related terminals (`needs-research`, `queue-blocked-on-research`) exist either.

### 1c. Check the max-cycles cap

See `~/.claude/skills/lazy-batch/SKILL.md` Step 1c. Bug-pipeline binding: message uses
`lazy-bug-batch`.

```
PushNotification({ message: "lazy-bug-batch hit max-cycles ({max_cycles}). Restart from a fresh session to continue." })
```

Print final batch report, STOP.

### 1c.6. PushNotification policy (park / halt / flush / run-end)

Identical to `~/.claude/skills/lazy-batch/SKILL.md` Step 1c.6 with bug-pipeline token bindings:

1. **park** — message: `"parked {bug_name} — {N} decision(s) parked so far this run"`. **Chat line (T5):** each newly-notified park also emits the single-line T5 park block to chat — `⏸ parked {bug_name} — {N} decision(s) · notified ({parked_count} parked this run)` — governed by the SAME dedup set as the notification (per `/lazy-batch` §1c.6 item 1).
2. **halt** — on every terminal/halt: `all-bugs-fixed`, `all-remaining-deferred`,
   `queue-missing`, `BLOCKED` halt-for-manual, `NEEDS_INPUT` halt, `max-cycles`, `meta-cap`,
   `device-queue-exhausted`, script-error, and any future obstacle terminal.
3. **flush** — message: `"lazy-bug-batch flush — {N} parked decision(s) ready for your input"`.
4. **run-end** — every run termination.

### 1c.5. Inline pseudo-skill handling (NO subagent dispatch)

If `sub_skill` starts with `__`, perform the action inline. Bug-pipeline pseudo-skills:

- **`__write_validated_from_skip__`** — same as `/lazy-batch` Step 1c.5: run
  `python3 ~/.claude/scripts/bug-state.py --apply-pseudo __write_validated_from_skip__ <spec_path>`
  (the script writes VALIDATED.md from SKIP_MCP_TEST.md), then commit + push per policy.

- **`__write_validated_from_results__`** — same as `/lazy-batch` Step 1c.5: run
  `python3 ~/.claude/scripts/bug-state.py --apply-pseudo __write_validated_from_results__ <spec_path>`
  (the script writes VALIDATED.md from MCP_TEST_RESULTS.md), then commit + push per policy.

- **`__mark_fixed__`** — **gated by TWO inline docs-only gates, in order, BEFORE the archive
  runs.** Gate logic is IDENTICAL to the `/lazy-bug` wrapper's `__mark_fixed__` handler — both
  run the same two gates (parity intentional and verified — the wrapper runs Gate 1 MCP-coverage audit + Gate 2 completion-integrity).

  **Gate 1 — MCP-coverage audit** per
  `~/.claude/skills/_components/mcp-coverage-audit.md`.
  Run the audit with `{spec_path}` and `{bug_id}`. If the audit returns `uncovered:N`, follow
  its D7 outcome (`completeness-policy.md` §4 — Gate 1 never asks, no NEEDS_INPUT.md):
  documented-MCP-untestable decisions get an inline SPEC test-exempt note; the rest route to a
  corrective coverage cycle (dispatch a cycle subagent to author the `mcp-tests/` scenario(s)
  + run them — meta cycle), with `⚖ policy:` line(s) + D7-digest entries. Do NOT run the
  archive steps. Append to `cycle_log`
  `{forward_cycles + meta_cycles + 1, bug_name, "__mark_fixed__ (gate 1 halted)", "{N} uncovered → corrective coverage cycle"}`,
  increment `forward_cycles` (gate-halted mark-fixed is still a forward-advancing attempt),
  return to Step 1a — the next mark-fixed attempt re-audits `clean`.

  **Gate 2 — completion-integrity gate** per
  `~/.claude/skills/_components/completion-integrity-gate.md`
  (runs ONLY after gate 1 returns `clean`). Adapted for bugs: `kind: fixed`, `filename: FIXED.md`.
  If a precondition fails, write `{spec_path}/NEEDS_INPUT.md` (`written_by: completion-integrity-gate`),
  commit it, and return `refused:<reason>` — same halt-cycle-and-surface-via-Step-1g pattern as gate 1.

  Only when BOTH gates pass: run
  `python3 ~/.claude/scripts/bug-state.py --apply-pseudo __mark_fixed__ {spec_path}`
  per `~/.claude/skills/_components/completion-integrity-gate.md` — the script is the **single
  author** of the `FIXED.md` receipt write (`kind: fixed`, `provenance: gated`, folding validation
  evidence from VALIDATED.md / MCP_TEST_RESULTS.md into the receipt body), the SPEC.md/PHASES.md
  `**Status:** Fixed` flip, and the deletion of the consumed VALIDATED.md / RETRO_DONE.md /
  DEFERRED_NON_CLOUD.md sentinels (FIXED.md / SKIP_MCP_TEST.md / MCP_TEST_RESULTS.md are kept).
  The orchestrator NEVER hand-writes the receipt, the status flip, or the sentinel deletions.
  After the script returns, the orchestrator runs ONE more script call — the **archive
  mechanics** are also script-owned per `~/.claude/skills/_components/mark-fixed-archive.md`:
  `python3 ~/.claude/scripts/bug-state.py --repo-root {repo_root} --archive-fixed {spec_path}`
  (SPEC evidence header lines, staged-deletion-coherent `git mv` with Windows-lock retry,
  tracked-only inbound-reference repoint, queue.json trim, atomic commit — then push the
  commit it created). The orchestrator performs ZERO hand edits for the archive; on
  `ok: false` it writes BLOCKED.md (`blocker_kind: archive-failure`) quoting the script's
  `refused` diagnostic verbatim (sentinel-scope — within HARD CONSTRAINT 1). The call is
  idempotent and resume-safe — a PARTIAL STATE diagnostic means re-run, never hand-unwind.

- **`__flip_plan_complete_cloud_saturated__`** — emitted only by `bug-state.py --cloud` when an
  `In-progress` plan's only unchecked WUs are in `{spec_path}/DEFERRED_NON_CLOUD.md` as
  workstation-only. `sub_skill_args` is the absolute plan-file path. Run
  `python3 ~/.claude/scripts/bug-state.py --apply-pseudo __flip_plan_complete_cloud_saturated__ <spec_path> --plan <plan_file_path>`
  (the script edits only the `status:` line → `Complete`, idempotent). Commit with message
  `chore(<bug_id>): mark plan part N Complete (cloud-saturated)`, then push. **Forward cycle** —
  increment `forward_cycles`.

- **`__flip_plan_complete_stale__`** — emitted by `bug-state.py` at Step 7a (cloud and workstation)
  when every WU a Ready/In-progress plan references is already `[x]`. `sub_skill_args` is the
  absolute plan-file path. Read the plan's YAML frontmatter, edit ONLY the `status:` line
  (`Ready` or `In-progress` → `Complete`). Derive the plan part number from `phases:`; fall back
  to the plan filename. Commit with message
  `chore(<bug_id>): mark plan part N Complete (stale — already applied)`. Do NOT touch SPEC.md
  or any sentinel. **Meta cycle** — increment `meta_cycles`.

After each inline action, follow the uniform post-cycle procedure from
`~/.claude/skills/lazy-batch/SKILL.md` Step 1c.5 (cycle_log append, push backstop, emit Step 3
block, update `prev_cycle_signature`, increment the correct counter). Return to Step 1a — DO NOT
fall through to Step 1d.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

**Compaction discipline — re-read the dispatch template AND the output contract first.** Before composing this dispatch — and ALWAYS as the first action after any compaction boundary — re-read `~/.claude/skills/_components/lazy-dispatch-template.md`, `~/.claude/skills/_components/orchestrator-voice.md` (the chat-output contract — its turn templates survive summarization by re-read, not by memory; the re-reads themselves are silent mechanics), AND `~/.claude/skills/_components/completeness-policy.md` (the D7 standing policy — its auto-resolve rules likewise survive compaction by re-read, not memory). The dispatch template is the on-disk canonical dispatch skeleton (`subagent_type`, the REQUIRED `model:` field, prompt envelope) and carries the **Read-before-Edit rule**: compaction resets read-state, so re-`Read` any file (PHASES.md, plans, SKILLs, components) before you `Edit`/`Write` it. 41% of post-compaction spawns in the 2026-06-10 audit dropped the `model:` field — re-reading this template before each dispatch is what prevents that.

**Long-build ownership (harness-tracked).** Any build or test that may exceed a single subagent turn is **orchestrator-owned**: start it with `Bash` `run_in_background: true` from this (the orchestrator) session and track it via the harness — NEVER background it from inside a dispatched cycle subagent, whose process tree is torn down when its turn ends (a `tauri build` backgrounded that way once silently vanished). Before committing to a 20–40 min packaged `tauri build`, run `cargo check --release` first to catch compile errors in minutes. Full rule: `.claude/skill-config/long-build-ownership.md`. This is `Bash`-only process ownership — it does not expand the orchestrator's sentinel-only `Write`/`Edit` scope (HARD CONSTRAINT 1 holds).

If Step 1c.5 did not handle this cycle, build a minimal subagent prompt. See
`~/.claude/skills/lazy-batch/SKILL.md` Step 1d for the full base prompt template, loop-guard
check, LOOP DETECTED block, and dispatch mechanics.

Bug-pipeline token substitutions in the prompt:
- `"autonomous feature pipeline"` → `"autonomous bug pipeline"`
- `Feature: {feature_name} ({feature_id})` → `Bug: {bug_name} ({bug_id})`
- `COMPLETED.md` / `FIXED.md` in sentinel lists
- LOOP DETECTED block guidance: mentions `RETRO_DONE.md / VALIDATED.md / SKIP_MCP_TEST.md /
  DEFERRED_NON_CLOUD.md` — the same set, but `FIXED.md` replaces `COMPLETED.md`

Per-skill inline override substitutions (in addition to `/lazy-batch`'s overrides):
- `/spec-bug` replaces `/spec` — already orchestrator-only docs pass; no sub-subagents.
- `plan-bug` replaces `plan-feature` — dispatched after a concluded investigation (SPEC.md
  `**Status:** Concluded`); it calls `/spec-phases` then `/write-plan` in-context, no Agent
  dispatch needed.

**"No premature Fixed" guard** (replaces `/lazy-batch`'s "No premature Complete"):
```
No premature Fixed (PIPELINE-GATE HONESTY — HARD REQUIREMENT):
  - You MUST NOT set the `**Status:**` of SPEC.md to `Fixed` or `Won't-fix`.
    That flip is reserved EXCLUSIVELY for the orchestrator's `__mark_fixed__`
    pseudo-skill, which runs ONLY after the full downstream tail: /retro-feature
    (writes RETRO_DONE.md) → /mcp-test (writes VALIDATED.md or a justified
    SKIP_MCP_TEST.md) → the __mark_fixed__ gates. If a cycle subagent flips
    SPEC **Status:** Fixed itself, the bug has NO FIXED.md receipt, so
    bug-state.py hard-halts on `completion-unverified` instead of advancing.
    Do NOT write a FIXED.md yourself either — only the orchestrator's
    __mark_fixed__ integrity gate may, after the validation tail passes.
  - What you MAY flip: the PLAN-PART frontmatter `status:` (Ready → In-progress
    → Complete) and per-PHASE checkboxes/Status line for the phase you just
    implemented. When the last phase's work lands, set the top-level PHASES
    **Status:** to `In-progress` (NOT `Complete` and NOT `Fixed`).
```

#### 1d.0. Pre-boot the dev runtime for `/mcp-test` cycles (WORKSTATION ONLY)

**Applies ONLY when `sub_skill == "mcp-test"`.** Skip for every other `sub_skill`.

See `~/.claude/skills/lazy-batch/SKILL.md` Step 1d.0 for the full pre-boot procedure, health
probe, background `npm run dev:restart`, MCP-readiness poll, and BLOCKED.md guidance. The
procedure is **identical** for the bug pipeline — bug `mcp-test` cycles need the same
orchestrator-owned runtime. This INCLUDES step 0 (plan-declared structural untestability):
when the bug's PHASES.md carries `**MCP runtime:** not-required`, skip the boot entirely and
dispatch with the "RUNTIME NOT PRE-BOOTED" variant block; honor the `NEEDS_RUNTIME`
single-line return with a boot + `(opus, recovery)` re-dispatch. RUNTIME IS ALREADY UP
guidance and NO FIRE-AND-FORGET clause (a resultless return is a violation) carry over
verbatim — substitute `{bug_name}/{bug_id}` for `{feature_name}/{feature_id}` in any messages.

**HARD CONSTRAINT 1 is NOT relaxed.** Step 1d.0 is `Bash`-only.

#### Loop-guard check and LOOP DETECTED block

See `~/.claude/skills/lazy-batch/SKILL.md` Step 1d for the full loop-guard logic. Same
`prev_cycle_signature == (feature_id, sub_skill, sub_skill_args, current_step)` check; same
LOOP DETECTED block appended to the prompt; same Sonnet model selection on LOOP DETECTED cycles.

Dispatch:

```
Agent({
  description: "lazy-bug-batch cycle {forward_cycles + meta_cycles + 1}: {sub_skill} for {bug_name}",
  subagent_type: "general-purpose",
  model: <"sonnet" if LOOP DETECTED else "opus">,
  prompt: <the prompt above>
})
```

### 1d.5. Post-cycle input audit (Opus — runs only on `spec-bug` and `spec-phases` cycles)

**Skip conditions (bug-pipeline bindings):**
- `sub_skill` is NOT in {`spec-bug`, `spec-phases`}. (`bug-state.py` emits no `plan-feature`;
  `plan-bug` is a planning step, not a SPEC/PHASES-authoring cycle — skip audit for `plan-bug`.)
- The cycle was a pseudo-skill (Step 1c.5 already ran inline).
- The cycle subagent already wrote `NEEDS_INPUT.md` for this bug this cycle (double-fire guard).
- The cycle subagent returned a hard failure with no SPEC/PHASES delta.

For the full audit dispatch, prompt shape, `audit_concurs` recording, and post-return handling
see `~/.claude/skills/lazy-batch/SKILL.md` Step 1d.5. Bug-pipeline token substitutions:
- `written_by: lazy-batch-input-audit` → `written_by: lazy-bug-batch-input-audit`
- `feature_id`/`feature_name` → `bug_id`/`bug_name`
- `next_skill: spec` → `next_skill: spec-bug`
- Audit prompt bias examples tailored for bugs:
  - Root-cause determination scope (what is in scope vs out of scope for this fix).
  - Fix approach when multiple technically-valid approaches exist.
  - Regression-test surface (what behavior the regression tests cover).
  - User-visible behavior changes (however subtle) introduced by the fix.

### 1e. Record cycle outcome and loop

See `~/.claude/skills/lazy-batch/SKILL.md` Step 1e for the full post-cycle procedure. Bug-pipeline
bindings:

- `cycle_log` entry uses `bug_name` instead of `feature_name`.
- Per-cycle chat output: T2 at dispatch + T3 at return per orchestrator-voice.md / `/lazy-batch` Step 3 — heading `### {Step name} — {work summary} [{n}/{max}]` (forward: `[{forward_cycles+1}/{max_cycles}]`; meta: `[meta {meta_cycles}/{2*max_cycles}]`); the `disp` line carries `{sub_skill} → {bug_id}`.
- **Post-`/execute-plan` and `/mcp-test` ledger-consistency guard (guardrail D):** see
  `~/.claude/skills/lazy-batch/SKILL.md` Step 1e item 4a for the full guard algorithm. Runs
  identically for the bug pipeline:
  ```bash
  git fetch origin $(git rev-parse --abbrev-ref HEAD)
  python3 ~/.claude/scripts/bug-state.py --repo-root <repo_root> --verify-ledger {spec_path}
  ```
  Recovery guidance per `failing_check` is identical to lazy-batch's Step 1e 4a.
- Increment `forward_cycles`. Return to Step 1a.

### 1f. Research-wait mode

NOT APPLICABLE to the bug pipeline. `bug-state.py` never emits `needs-research` or
`queue-blocked-on-research`. This step is entirely absent.

### 1g. Decision-resume mode (`terminal_reason == "needs-input"`)

**Meta-cap check (FIRST):** `if meta_cycles >= 2 * max_cycles:` → halt with message
`"lazy-bug-batch meta-cycle cap (2× max_cycles = {2*max_cycles}) reached — too many resolution/recovery cycles. Restart from a fresh session."`, PushNotification, print final batch report, STOP.

**Pipeline binding for the shared handler** — `{SKILL}` = `/lazy-bug-batch`,
`{STATE_SCRIPT}` = `bug-state.py`, `{ITEM}` = bug, `{PUSH_RULE}` = workstation (standard push).
The shared handler's "increment `cycle`" step translates to **increment `meta_cycles`**. The
per-cycle update block heading uses the two-counter format (Step 3 template).

See `~/.claude/skills/_components/decision-resume.md`

**Park mode — processing `parked[]` output (`--park` only):** When `park_mode == true` and the
probe returns a non-empty `parked[]` array, park each item: increment `parked_count` and fire
`PushNotification({ message: "parked {bug_name} — {parked_count} decision(s) parked so far this run" })`.
Continue queue walk. Flush later via Step 1g-flush.

---

### 1g-flush. Parked-decision flush (`--park` only)

**Guard:** runs only when `park_mode == true`.

**Pipeline binding** — `{SKILL}` = `/lazy-bug-batch`, `{STATE_SCRIPT}` = `bug-state.py`,
`{ITEM}` = bug, `{PUSH_RULE}` = workstation (standard end-of-work push). Meta-cycle accounting:
**increment `meta_cycles`** per applied decision.

**Three flush triggers** (same as `/lazy-batch` Step 1g-flush):
- **(a) Operator message mid-run** while unresolved parked items exist.
- **(b) No unparked work remains** — `bug-state.py` returns `all-bugs-fixed` (or any
  queue-exhausted terminal) and unresolved parked items still exist.
- **(c) Run end** — flush before the final batch report whenever `parked_count > 0`.

See `~/.claude/skills/_components/parked-flush.md`

---

### 1h. Blocked-resolution mode (`terminal_reason == "blocked"`)

**Meta-cap check (FIRST):** same as Step 1g meta-cap check, using `lazy-bug-batch` in message.

**Pipeline binding** — `{SKILL}` = `/lazy-bug-batch`, `{STATE_SCRIPT}` = `bug-state.py`,
`{ITEM}` = bug, `{SPEC_ROOT}` = `docs/bugs`, `{ADD_PHASE}` = `/add-phase` (or `/plan-bug` if
PHASES.md is absent), `{PUSH_RULE}` = workstation (standard push). Increment `meta_cycles`.

See `~/.claude/skills/_components/blocked-resolution.md`

---

### 1i. Operator-directed halt-resolution (other non-max-cycles problem-terminals)

**Meta-cap check (FIRST):** same as Step 1g meta-cap check.

Bug-pipeline terminals routed here: `completion-unverified` and `stale_upstream`. (`bug-state.py`
does NOT emit `needs-spec-input`.) Increment `meta_cycles`.

`max-cycles` (cost bound), `all-bugs-fixed` (success), `all-remaining-deferred` (deliberate park),
`device-queue-exhausted` / `cloud-queue-exhausted` (environment), and `queue-missing` keep their
existing clean stops per the halt-resolution component's exclusion list.

See `~/.claude/skills/_components/halt-resolution.md`

---

## Step 1.5: Forward-Progress Verification

After the cycle loop exits with any terminal reason **other than** `blocked`, `needs-input`, or
`queue-missing`, run a final read-only state probe:

```bash
python3 ~/.claude/scripts/bug-state.py
```

See `~/.claude/skills/lazy-batch/SKILL.md` Step 1.5 for the full algorithm. Bug-pipeline
substitutions: compare probe tuple against `prev_cycle_signature` and prepend ✅ or ⚠ block to
the Step 2 report. The ⚠ WARNING block's "Likely causes" bullet replaces feature-pipeline
sentinels with bug-pipeline equivalents (`RETRO_DONE.md`, `VALIDATED.md`, `FIXED.md`,
`DEFERRED_NON_CLOUD.md`, `SKIP_MCP_TEST.md`). Use `lazy-bug-batch` in the push-notification
message.

---

## Step 2: Final Batch Report

When the loop exits, print:

```
## /lazy-bug-batch — Done

**Forward cycles used:** {forward_cycles}/{max_cycles}
**Meta cycles used:** {meta_cycles}/{2*max_cycles}
**Terminal reason:** {terminal_reason or "forward-cycles-cap"}
**Last notification:** {notify_message or "—"}
**Park mode:** {on | off}

### Cycle log
| # | Bug | Action | Summary |
|---|-----|--------|---------|
{cycle_log rows}

**Next step:**
  - If terminal_reason is "blocked": reached ONLY when the operator chose "Halt for manual fix" in Step 1h. Resolve {spec_path}/BLOCKED.md by hand, then re-run `/lazy-bug-batch {max_cycles}`.
  - If terminal_reason is "all-bugs-fixed": all bugs fixed or retired.
  - If terminal_reason is "completion-unverified": reconcile the receipt gap.
  - If terminal_reason is "all-remaining-deferred": re-include a bug by deleting its DEFERRED.md.
  - If forward-cycles-cap: re-run `/lazy-bug-batch {max_cycles}` from a fresh session.
  - If meta-cycles-cap (2× max_cycles): too many resolution/recovery cycles — investigate before re-running.
  - (needs-input is no longer a terminal state — Step 1g resolves inline.)
```

*(Print the following table ONLY when `park_mode == true` AND `auto_accepted[]` is non-empty.
Omit entirely otherwise.)*

```
### Auto-accepted decisions (`--park` two-key)

| Bug | Decision | Chosen option | Resolved sentinel |
|-----|----------|---------------|-------------------|
| {bug_name} ({bug_id}) | {decision title} | {chosen option label} | `{resolved_sentinel_path}` |
```

*(Print the following table whenever the run applied the completeness-first standing policy at
least once — BOTH modes. Omit entirely when no D7 applications occurred.)*

```
### Completeness-policy applications (D7)

| Bug | Decision / blocker | Chosen path | Spin-off | Link |
|-----|--------------------|-------------|----------|------|
| {bug_name} ({bug_id}) | {≤8-word summary} | {most-complete path taken} | {spun-off id or —} | `{resolved sentinel / SPEC note / scenario path}` |
```

*(One row per `⚖ policy:` application — Step 1g scope resolutions, Step 1h sequencing-only
blocker resolutions, parked-flush backstop resolutions, Gate-1 coverage routings, and in-cycle
applications disclosed in cycle summaries. Required by `completeness-policy.md` Logging; graded
by R-D7-2.)*

Framing prose around the final report is capped at **≤2 sentences total (T7 per orchestrator-voice.md)** — the cycle table, counters, digests, terminal reason, and Next-step lines carry all required content.

STOP.

---

## Step 3: Cycle Output Discipline (orchestrator-voice.md is the binding contract)

Identical to `~/.claude/skills/lazy-batch/SKILL.md` Step 3 with bug-pipeline token substitutions:
per-cycle chat output is the T2 dispatch block + T3 return block (or T4 for inline pseudo-skills)
from `~/.claude/skills/_components/orchestrator-voice.md`, under the canonical step heading:

```
### {Step name} — {work summary, ≤12 words} [{n}/{max}]
disp   {sub_skill} → {bug_id} ({model}[, loop-resolution|recovery])
done   {duration} · {load-bearing outcome} · {short-sha | —}
audit  {…}        ← only where required (see below)
ledger {clean · pushed | …}
next   {fresh probe routing | terminal: <reason>}
```

The heading leads with the pipeline step being advanced to (bug-pipeline names: Investigate /
Plan / Implement / Retro / Validate / Mark Fixed), then a ≤12-word summary of this cycle's
work, then the counter — `[{forward_cycles}/{max_cycles}]` for forward cycles (post-increment),
`[meta {meta_cycles}/{2*max_cycles}]` for meta cycles. The retired `### Cycle fwd N/M · meta
K/L` heading must not reappear. All contract rules are inherited verbatim from
`/lazy-batch` Step 3 (mechanics silent; deviations are T6; halt/resolution briefings are T6 rich
zones; final report is T7; the retired `**Result:**`/`**Commit:**` bullets, `· {bug_name} ·
{sub_skill}` heading suffix, and any multi-line cycle summary must NOT reappear). Bug-pipeline
`audit`-line bindings: the `/execute-plan` inline/test-first audit signal (REQUIRED — `/lazy-batch`
Step 1e item 2), and `audit  {N} product-behavior decision(s) surfaced → NEEDS_INPUT.md` on a
`spec-bug`/`spec-phases` cycle where Step 1d.5 fired.

---

## Notes

- This skill never invokes the work-log MCP tool. Each sub-skill invoked by the cycle subagents logs its own work.
- No persistence layer — restart is free. State lives in the filesystem sentinels.
- Commit policy is delegated to the cycle subagent (which follows `.claude/skill-config/commit-policy.md` or the standard pattern).
- **No research/ingest steps.** Unlike `/lazy-batch`, this skill has no Step 0.5 pre-loop ingest check, no `needs-research` halt path, no `--allow-research-skip` flag, and no in-session resume protocol for research uploads. Bugs do not undergo Gemini deep research.
- **Coupling rule:** changes to `/lazy-batch`'s shared algorithm (hard constraints, cycle loop shape, resolution modes, pseudo-skill post-actions, cycle output discipline) must be mirrored here unless bug-pipeline-scoped per the differences table above.
