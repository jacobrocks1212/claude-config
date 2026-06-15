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
→ `/mcp-test` → `__mark_fixed__` archive-on-fix) by looping on
`~/.claude/scripts/bug-state.py`. (The `/retro-feature` step has been unwired — operator decision
2026-06 — so once phases are complete the pipeline routes directly to the MCP gate.) Each cycle spawns an Opus subagent that invokes the named
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

**10. HARD CONSTRAINT — stop-authorization (mirrors `/lazy-batch` HARD CONSTRAINT 10).** The orchestrator MUST NOT end a bug-pipeline run except on `max-cycles` or a genuine script-emitted terminal. The ONLY legitimate no-`AskUserQuestion` stops are: (a) `forward_cycles >= max_cycles`, and (b) a `terminal_reason` in {`all-bugs-fixed`, `max-cycles`, `queue-missing`, `blocked-halt-for-manual`, `needs-research`, `queue-blocked-on-research`} returned by `bug-state.py` in the CURRENT cycle's probe. Any DESIRE to stop for any other reason routes through the budget-and-queue-guard `AskUserQuestion` first; a checkpoint stop MAY proceed only after operator confirmation via `bug-state.py --run-end --reason checkpoint --operator-authorized`. An attended `--run-end --reason checkpoint` without `--operator-authorized` is REFUSED (exit 1, marker kept). When ending on a genuine terminal, pass `--run-end --reason terminal --terminal-reason <reason>` (sanctioned set above, or `--operator-authorized` required). See `/lazy-batch` HARD CONSTRAINT 10 for the full incident description (2026-06-14 / lazy-validation-readiness Phase 7).

**Cycle-subagent execution model:** Same as `/lazy-batch` — no `Agent` tool inside the dispatched
cycle subagent; all skills run inline using `Edit`/`Write`/`Read`.

**Meta-dispatch by-reference — PREFER `dispatch_prompt_ref` at ALL `--emit-dispatch` sites (mirrors `/lazy-batch` Phase 7 / lazy-validation-readiness).** Every `bug-state.py --emit-dispatch <class>` call emits BOTH `dispatch_prompt` AND `dispatch_prompt_ref` (`@@lazy-ref nonce=<hex>`). When dispatching any meta-dispatch prompt (hardening, recovery, apply-resolution, coherence-recovery, input-audit, investigation, etc.), PREFER `dispatch_prompt_ref` over the verbatim `dispatch_prompt`. Fall back to `dispatch_prompt` verbatim ONLY when `dispatch_prompt_ref` is absent or null. See `/lazy-batch`'s "Meta-dispatch by-reference" paragraph (§1d) for the full rationale.

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

**Budget-and-queue guard:** same as `/lazy-batch` Step 0 (MUST NOT end a run with budget remaining AND active queue items) — INCLUDING the unattended-checkpoint arm: in an unattended run, an early stop is sanctioned ONLY as a CHECKPOINT, permitted when a reliability trigger holds (≥2 guard denials this run, OR an operator pause message), and requires ALL of (1) `python3 ~/.claude/scripts/bug-state.py --run-end --reason checkpoint --next-route "<probed next route>"`, (2) a PushNotification carrying the next route + reason, (3) the T7 trigger naming. An early stop without the checkpoint `--run-end` is a contract violation. Resume side: `--run-start` echoes `resumed_from_checkpoint` (and deletes the checkpoint file) — surface it on T1 as one line (see Step 0.55).

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

After the enqueue returns, continue to Step 0.55. The bug queue carries no pre-loop ingest step
(N/A to bugs).

---

## Step 0.55: Write the run marker (IMMEDIATELY before the T1 banner / loop entry)

After Step 0.45 (or Step 0.4 if `--adhoc` was absent) completes — and before printing the T1 banner or entering the Step 1 loop — write the run marker:

```bash
python3 ~/.claude/scripts/bug-state.py \
  --run-start --max-cycles {max_cycles} \
  --repo-root {cwd}
```

**Attendedness:** interactive `/lazy-bug-batch` invocations call `--run-start` WITHOUT `--unattended` — the marker records `attended: true` (the default). Only a scheduled/cron driver passes `--unattended`, recording `attended: false`. The `attended` field governs whether `--run-end --reason checkpoint` requires `--operator-authorized` (see HARD CONSTRAINT 10 and the budget-and-queue guard above). Legacy markers lacking the field are treated as attended — the stricter gate is the safe default.

**What this does.** The marker (`~/.claude/state/lazy-run-marker.json`) is the single on/off switch for the inject + validate-deny hooks. While the marker is present:
- The inject hook (`lazy-route-inject.sh`) fires on every UserPromptSubmit turn, runs the full probe form, and injects the route (`LAZY-ROUTE (hook-injected, turn N): …`) into the model's context via `additionalContext`.
- The validate-deny guard (`lazy-dispatch-guard.sh`) checks every `Agent` dispatch against the prompt registry; an unregistered prompt is denied with a corrective recipe.

Interactive sessions (no marker) are **completely untouched** — both hooks exit instantly on the `test -f` fast path. The marker is script-owned: `--run-start` writes it; `--run-end` deletes it. The orchestrator never hand-writes the marker file.

**Session state pinned in the marker:** `pipeline=bug`, `cloud=false`, `repo_root`, `max_cycles`, `session_id` (bound on first hook firing), `nonce_seed`. Counters (`forward_cycles`, `meta_cycles`) are persisted in the marker from this point forward — the inject hook reads them without needing CLI flags.

**Resume from a checkpoint.** If a prior run ended via the unattended-checkpoint arm (Step 0 budget-and-queue guard), `--run-start` consumes `lazy-run-checkpoint.json` and echoes its content as `resumed_from_checkpoint` in the run-start output (then deletes the file — single-use). When present, surface it on the T1 banner as one extra line — `resume <next_route> (checkpoint <date>)` (orchestrator-voice.md T1).

**`--run-end` is MANDATORY on every terminal/halt path** — see §1c.6 for the enumeration. A missed deletion is self-healing (24h staleness + session-id mismatch cleanup) but is a protocol violation the retro grades.

If `--run-start` fails (script error), surface a T6 `⚠` and STOP before printing the banner — a run with no marker degrades to pre-Phase-5 behavior (no hook enforcement) but should not silently proceed without the operator knowing enforcement is off.

---

## Step 1: Cycle Loop

Repeat:

### 1a. Run bug-state.py

**LAZY-ROUTE banner check (FIRST — before deciding to run the probe).** The inject hook fires on every UserPromptSubmit turn while the run marker is present. When the hook fires, it runs the full probe form itself and injects the result into the turn context as a single `additionalContext` string:

```
LAZY-ROUTE (hook-injected, turn N): {"feature_id": "...", "sub_skill": "...", "cycle_prompt": "...", "cycle_model": "opus", ...} nonce=<hex-value>
```

On post-compaction re-entry, a `POST-COMPACTION RE-ENTRY:` paragraph follows the nonce. If the inject hook errored, a `HOOK_ERROR: <error text>` suffix appears at the end. **If the current turn carries this banner**, consume it directly — extract `feature_id`/`bug_id`, `sub_skill`, `cycle_prompt`, `cycle_model`, and all other probe fields from the injected JSON. **Do NOT run another `bug-state.py` probe on this turn.** Re-probing advances the persisted counters TWICE for one logical cycle — a protocol violation. If no LAZY-ROUTE banner is present, run the probe as below.

```bash
python3 ~/.claude/scripts/bug-state.py
```

If the script exits non-zero, run `python3 ~/.claude/scripts/bug-state.py --run-end` (idempotent), surface the error, PushNotification, print the final batch report (Step 2), and STOP.

Parse the JSON output. Extract: `feature_id` (used as `bug_id`), `feature_name` (used as
`bug_name`), `spec_path`, `current_step`, `sub_skill`, `sub_skill_args`, `terminal_reason`,
`notify_message`, `diagnostics`.

**Probe enrichment (optional — same flags as `lazy-state.py`).** The orchestrator MAY call the
probe with the enrichment flags to fold `repeat_count`, `git_guards`, and `cycle_header` into
the JSON in a single invocation:

```bash
python3 ~/.claude/scripts/bug-state.py --repeat-count --emit-prompt --probe \
  --max-cycles {max_cycles}
```

The `--forward-cycles` and `--meta-cycles` flags are NO LONGER passed on probe invocations. The marker persists the counters from `--run-start`; the inject hook and probe read them from the marker without needing CLI flags. Passing them would override the marker's persisted state with stale in-memory values.

These flags are purely additive (base JSON fields unchanged) — see
`~/.claude/skills/lazy-batch/SKILL.md` Step 1a for their semantics, INCLUDING probe hygiene:
`--repeat-count` advances the persisted (HEAD-aware) streak and is reserved for the SINGLE
dispatch-bound probe per cycle; diagnostic / inspection probes use `--repeat-count-peek` (reads
the would-be streak without advancing it); never redirect probe or diagnostic output into the
repo tree (use the OS temp dir). `--repeat-count` also emits `step_repeat_count` (consecutive
cycles at the same `(bug_id, current_step)` step — `sub_skill`/args-blind, NO head-advance reset):
when it is `>= 3`, STOP — surface `⚠ step '<current_step>' reached <N> times without advancing —
inspect routing before dispatching` and do NOT keep dispatching the emitted action mechanically.
This catches "productive-looking" oscillation (each cycle commits → HEAD advances → the dispatch
streak resets while routing never leaves the step). Full semantics: `/lazy-batch` Step 1a.
The **investigation triggers, inline-diagnosis budget (~8 own diagnostic tool calls per issue),
and no-narrative-as-fact rule apply identically** to the bug pipeline — see `/lazy-batch` Step 1a
and `~/.claude/skills/_components/investigation-dispatch.md` (the bug id rides in `feature_id`; the artifact lives in the bug's `docs/bugs/<id>/` dir; the orchestrator emits the dispatch via `python3 ~/.claude/scripts/bug-state.py --emit-dispatch investigation --context item_name=… --context spec_path=… --context symptom=… --context trigger=… --context inherited_hypotheses=… --context item_id=… --context cwd=…` and dispatches `dispatch_prompt` VERBATIM). `--emit-prompt` folds the
script-assembled `cycle_prompt` / `cycle_model` (`cycle_prompt_refused` on assembly failure) into
the JSON, with the `pipelines=bug` sections selected and the bug tokens bound; SHOULD be passed on
every probe (null on pseudo-skill/terminal probes, always safe). Step 1d consumes it verbatim.

**Step 1a — probe ONCE per cycle (F2 double-probe debounce).** Run exactly ONE advancing, dispatch-bound `--repeat-count --emit-prompt` probe per cycle — the one whose `cycle_prompt` you actually dispatch — and use `--repeat-count-peek` for EVERY inspection / sanity / out-of-band probe so that only the single dispatch-bound probe advances the streaks. Probing a route twice with no dispatch between (an inspection probe, then the dispatch-bound probe) is a re-read, not a re-attempt, and historically inflated `step_repeat_count` into false `LOOP DETECTED` blocks. `update_repeat_counts` now defends this in depth: when a run marker is present it debounces a re-read via the registry consume-count delta (an unchanged consumed-emission count between two identical step probes ⇒ no dispatch landed ⇒ `step_repeat_count` is HELD, not incremented), so a genuine same-step oscillation (a real dispatch — hence a consume — between repeats) still trips while a benign double-probe no longer does. This note is the behavioral complement: even with the script debounce, keep to one advancing probe + peek for inspection.

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
- **`all-bugs-fixed`**: Run `python3 ~/.claude/scripts/bug-state.py --run-end`, then PushNotification `"ALL BUGS FIXED — queue cleared after {forward_cycles} forward + {meta_cycles} meta /lazy-bug-batch cycle(s)."`, print final batch report, STOP.
- **`all-remaining-deferred`**: every open bug has `DEFERRED.md` (a deliberate park). Run `--run-end`, then PushNotification with `notify_message`, print final batch report, STOP. (Not routed to Step 1i — re-include a bug by deleting its `DEFERRED.md`.)
- **`queue-missing`**: `docs/bugs/queue.json` missing (the queue is optional; on-disk bugs are
  auto-discovered — informational). Run `--run-end`, then PushNotification with `notify_message`,
  print final batch report, STOP.
- **`cloud-queue-exhausted`**: treat as `all-bugs-fixed` defensively (run `--run-end` first).
- **`device-queue-exhausted`**: remaining bugs carry `DEFERRED_REQUIRES_DEVICE.md`. Run `--run-end`,
  then PushNotification with `notify_message`, print final batch report, STOP. Resume on a real-device host.
- **`scoped-id-not-found`** (when `--bug-id` was supplied): the requested bug does not exist in
  the queue. Run `--run-end`, then PushNotification with `notify_message`, print final batch report, STOP.

> **Note — no `needs-spec-input` in the bug pipeline.** `bug-state.py` does not emit this
> terminal. Step 1i's matrix covers only `completion-unverified` and `stale_upstream` for bugs.
> No research-related terminals (`needs-research`, `queue-blocked-on-research`) exist either.

### 1c. Check the max-cycles cap

See `~/.claude/skills/lazy-batch/SKILL.md` Step 1c. Bug-pipeline binding: message uses
`lazy-bug-batch`.

```bash
python3 ~/.claude/scripts/bug-state.py --run-end
```

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

   **`--run-end` is MANDATORY before EVERY terminal/halt PushNotification.** On every path listed above, call `python3 ~/.claude/scripts/bug-state.py --run-end` BEFORE the PushNotification fires. `--run-end` deletes the run marker AND the prompt registry (all run-scoped enforcement state). A missed deletion is self-healing (24h staleness + session-id mismatch cleanup) but is a protocol violation the retro grades. The call is idempotent — if the marker is already absent, `--run-end` exits cleanly.

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
  **The script is the SINGLE author of VALIDATED.md — hand-writing it is banned.** The apply
  refuses (zero writes) on missing/wrong-kind results, `result` ≠ `all-passing`,
  `pass_count != total_count`, or a stale `validated_commit` vs HEAD. On refusal do NOT retry
  blindly or hand-write the sentinel — route a fresh `/mcp-test` cycle (see `/lazy-batch`
  Step 1c.5 for the full gate list and rationale).

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
  **Mechanical third gate inside `--apply-pseudo __mark_fixed__`:** the script auto-flips
  all-ticked phases to Complete and REFUSES (`refused:<reason>`, zero writes) if any phase
  retains an unchecked box (verification rows included) or a non-Complete/Superseded Status. On
  `ok: false` + this refusal, do NOT retry blindly — route a corrective coherence cycle. Emit the dispatch via the script:
  ```bash
  python3 ~/.claude/scripts/bug-state.py \
    --emit-dispatch coherence-recovery \
    --context item_name="{bug_name}" \
    --context spec_path="{spec_path}" \
    --context gate_output="<the --apply-pseudo refusal reason string>" \
    --context item_id="{bug_id}" \
    --context cwd="{cwd}"
  ```
  Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`. The subagent reconciles PHASES.md honestly (tick-with-evidence or re-scope, never blind-tick) then returns to Step 1a. Exactly as a Gate-1 halt routes.
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

**Post-compaction re-entry protocol (HARD — the first post-compaction action is NEVER a dispatch; mirrored from `/lazy-batch` Step 1d).** Compaction is the measured protocol cliff (2026-06-11 run: counters never recovered, probes stopped, prompts went hand-authored post-boundary). On the first turn after any compaction boundary, BEFORE any `Agent` call: (1) re-read Step 1a of this SKILL plus the three components named above; (2) the session counters (`forward_cycles`, `meta_cycles`) are persisted in the run marker — the post-compaction probe reads them from the marker directly, so no manual reconstruction is needed. As a cross-check, verify the surviving T1/T2/T4 context broadly agrees with the marker's counters; if there is a discrepancy, trust the marker and record any divergence in a single T6 `⚠` line; (3) run the FULL Step 1a probe form (`bug-state.py --repeat-count --emit-prompt --probe --max-cycles …`) — note: `--forward-cycles`/`--meta-cycles` are NOT passed (the marker owns the counters); proceed only from its output. Dispatching from a pre-compaction probe held in memory, or from a hand-reconstructed prompt, is a contract violation.

**Long-build ownership (harness-tracked).** Any build or test that may exceed a single subagent turn is **orchestrator-owned**: start it with `Bash` `run_in_background: true` from this (the orchestrator) session and track it via the harness — NEVER background it from inside a dispatched cycle subagent, whose process tree is torn down when its turn ends (a `tauri build` backgrounded that way once silently vanished). Before committing to a 20–40 min packaged `tauri build`, run `cargo check --release` first to catch compile errors in minutes. Full rule: `.claude/skill-config/long-build-ownership.md`. This is `Bash`-only process ownership — it does not expand the orchestrator's sentinel-only `Write`/`Edit` scope (HARD CONSTRAINT 1 holds).

If Step 1c.5 did not handle this cycle, build the dispatch by CONSUMING the script-assembled
prompt. Composition is now `python3 ~/.claude/scripts/bug-state.py … --repeat-count --emit-prompt`
(the bug-pipeline mirror of lazy-batch's Step 1a probe) → use the probe's `cycle_prompt` verbatim
as the Agent `prompt:` and `cycle_model` as the Agent `model:`. See
`~/.claude/skills/lazy-batch/SKILL.md` Step 1d for the shared consume-and-dispatch rules,
in-session loop-guard cross-check, and the `cycle_prompt`-null/refused fallback — they apply
identically to the bug pipeline.

**Continuation cycles re-emit + probe-presence guard (mirrored from `/lazy-batch` Step 1d —
both apply verbatim here).** A real-skill dispatch is valid ONLY when its `prompt:` is the
`cycle_prompt` produced by an `--emit-prompt` probe run in the SAME turn as the `Agent` call —
when a cycle returns partial or needs a retry, return to Step 1a and RE-PROBE; never hand-compose
a "continuation prompt" (both measured protocol failures in the 2026-06-11 run were hand-composed
continuations). **Freshness — never dispatch an emission from an earlier turn** (applies to
`cycle_prompt` AND every `--emit-dispatch <class>` output): the emitted text is dispatchable only
while verbatim in context within the SAME turn it was emitted. If any turn boundary, summarization,
or edit intervened since the emit, RE-EMIT fresh and dispatch within that same turn. Hand-editing
emitted text (appending notes, "cleaning up", re-typing) is the failure class; the template's
`--context` slots are the ONLY customization point. And the T2/T4 heading line MUST carry the
dispatch-bound probe's `cycle_header` field VERBATIM — a probe-shaped heading with no same-turn
probe behind it is graded as a probe-cadence violation.

**Bug wording, the work branch, and the premature-status guard are now SCRIPT-BOUND via the
sectioned template's tokens** (`{item_label}`/`{pipeline_phrase}`/`{receipt_name}` = FIXED.md /
`{mark_pseudo}` = __mark_fixed__ / `{forbidden_status}` = "Fixed or Won't-fix" / `{work_branch}`,
plus per-pipeline sentinel-set sections). The orchestrator does NO hand-substitution — `bug-state.py
--emit-prompt` selects the `pipelines=bug` sections and binds every token, so the former
"autonomous bug pipeline" / `Bug:`-header / FIXED.md substitution list and the whole "No premature
Fixed" guard block are dead (the template's generic status-honesty section emits them already).

Bug cycles dispatch `spec-bug` / `plan-bug` / `execute-plan` / `retro-feature` / `mcp-test`; the
sectioned template covers all of them via its `skills=` section selection (`/spec-bug` replaces
`/spec`, `plan-bug` replaces `plan-feature` — both orchestrator-only docs passes, no sub-subagents).

#### 1d.0. Pre-boot the dev runtime for `/mcp-test` cycles (WORKSTATION ONLY)

**Applies ONLY when `sub_skill == "mcp-test"`.** Skip for every other `sub_skill`.

See `~/.claude/skills/lazy-batch/SKILL.md` Step 1d.0 for the full pre-boot procedure, health
probe, background `npm run dev:restart`, MCP-readiness poll, and BLOCKED.md guidance. The
procedure is **identical** for the bug pipeline — bug `mcp-test` cycles need the same
orchestrator-owned runtime. This INCLUDES step 0 (plan-declared structural untestability):
when the bug's PHASES.md carries `**MCP runtime:** not-required`, skip the boot entirely. **The
mcp-test prompt VARIANT (runtime-up vs no-runtime) is script-owned** — `bug-state.py --emit-prompt`
reads the same PHASES.md `**MCP runtime:**` line and selects the matching section, so `cycle_prompt`
already carries the correct variant; the orchestrator does NOT swap a runtime block by hand (mirror of
lazy-batch Step 1d.0 step 4). Honor the `NEEDS_RUNTIME` single-line return with a boot + registry-validated re-dispatch (emit via the script):
```bash
python3 ~/.claude/scripts/bug-state.py \
  --emit-dispatch needs-runtime-redispatch \
  --context item_name="{bug_name}" \
  --context spec_path="{spec_path}" \
  --context original_cycle_prompt_note="mcp-test cycle found MCP-testable surface; plan declared not-required" \
  --context item_id="{bug_id}" \
  --context cwd="{cwd}"
```
Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`. Tag the re-dispatch `disp` line `(opus, recovery)`. The NO FIRE-AND-FORGET clause (a resultless return is a violation)
carries over — the bug-pipeline token bindings (`{item_label}`/`{item_name}`/`{item_id}` =
Bug/`{bug_name}`/`{bug_id}`) are bound by the script, not substituted in any orchestrator message.

**HARD CONSTRAINT 1 is NOT relaxed.** Step 1d.0 is `Bash`-only.

#### Loop-guard check and LOOP DETECTED block

See `~/.claude/skills/lazy-batch/SKILL.md` Step 1d for the full loop-guard logic. **Loop-block
inclusion and the opus/sonnet selection are SCRIPT-OWNED** (driven by the persisted per-pipeline
`repeat_count` `bug-state.py` reads itself): `cycle_prompt` arrives with the loop block already
appended and `cycle_model` already flipped to `"sonnet"` when `repeat_count >= 2`. The in-session
`prev_cycle_signature == (feature_id, sub_skill, sub_skill_args, current_step)` check is RETAINED as
the orchestrator's cross-check (it still drives the T2 `(sonnet, loop-resolution)` `disp` tag); if it
fires but `cycle_model` came back `"opus"`, re-run the probe WITH `--repeat-count --emit-prompt --max-cycles {max_cycles}` (no `--forward-cycles`/`--meta-cycles` — counters live in the marker)
rather than hand-appending the block.

Dispatch:

```
Agent({
  description: "lazy-bug-batch cycle {forward_cycles + meta_cycles + 1}: {sub_skill} for {bug_name}",
  subagent_type: "general-purpose",
  model: <the probe's cycle_model>,
  prompt: <the probe's cycle_prompt, verbatim>
})
```

#### 1d.1. Denial recovery (validate-deny guard + hardening dispatch)

Mirrors `/lazy-batch` Step 1d.1 exactly, with `bug-state.py` in place of `lazy-state.py` and `bug_id`/`bug_name` in place of `feature_id`/`feature_name`:

**Pending hardening debt (script-routed — the probe WITHHOLDS the forward route).** Every guard deny is appended to the deny ledger (`lazy-deny-ledger.jsonl`); a marker-gated probe surfaces `pending_hardening: <int>` (with `pending_denials: [<reason summaries>]` when `> 0`). While debt is pending, the probe emits NO `cycle_prompt` — it returns `route_overridden_by: "pending-hardening-debt"` plus `hardening_emit_command`, a pre-composed `bug-state.py --emit-dispatch hardening` command bound from the oldest unacked denial. Run it verbatim and dispatch its `dispatch_prompt`; the entry is acked when the GUARD ALLOWS the hardening dispatch (not at emission — emitting without dispatching clears nothing). Repeat probe → hardening until a normal forward route returns. **Consume the FULL probe JSON** — piping probe output through field-extractors is BANNED (it blinds the orchestrator to `route_overridden_by`); the probe also warns on stderr while debt is live. `--run-end` REFUSES (exit 1) while any unacked denial remains; the `--ack-unhardened` override is operator-authorization-ONLY (it prints into the run-end message for retro grading) — never passed autonomously.

**Trigger 1 — validate-deny (denied dispatch):**
1. Re-run `python3 ~/.claude/scripts/bug-state.py --repeat-count --probe --emit-prompt --max-cycles {max_cycles}`. The fresh `cycle_prompt` carries a newly registered nonce.
2. Dispatch the fresh `cycle_prompt` **VERBATIM**.
3. **IN ADDITION**, on EVERY guard denial emit a hardening dispatch (locked decision 4: a denial means a hand-composed prompt reached the guard, which is a harness gap by definition — inline, unbounded, no dedup):

```bash
python3 ~/.claude/scripts/bug-state.py \
  --emit-dispatch hardening \
  --context trigger_kind=validate-deny \
  --context item_id={bug_id} \
  --context denied_prompt_summary="<one-line summary of the denied prompt>" \
  --context denial_reason="<the permissionDecisionReason from the guard>" \
  --context probe_json="<probe JSON from this turn>" \
  --context registry_state="<relevant registry entries or 'empty'>" \
  --context cwd="{cwd}"
```

Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`. The hardening dispatch is emitted REGARDLESS of whether the re-probe dispatch (step 2) succeeds or fails — the denial itself is the trigger. **Depth-cap exception:** a denial OF a hardening dispatch never dispatches another hardening stage (see Depth cap below). If the step-2 re-dispatch is also denied, proceed to trigger 2.

**Trigger 2 — no-route (cycle_prompt_refused / unknown state / marker-state divergence):**
Emit a hardening dispatch:

```bash
python3 ~/.claude/scripts/bug-state.py \
  --emit-dispatch hardening \
  --context trigger_kind=no-route \
  --context item_id={bug_id} \
  --context denied_prompt_summary="<one-line summary>" \
  --context denial_reason="<cycle_prompt_refused reason or no-route description>" \
  --context probe_json="<probe JSON from this turn>" \
  --context registry_state="<relevant registry entries or 'empty'>" \
  --context cwd="{cwd}"
```

**Trigger 3 — HOOK_ERROR breadcrumb in an injected banner:** emit hardening dispatch with `trigger_kind=inject-hook-error` and `denial_reason` set to the breadcrumb text.

Dispatch `dispatch_prompt` VERBATIM using `dispatch_model` (`"opus"`). Reference: `~/.claude/skills/_components/hardening-dispatch.md`.

**Depth cap (two deny shapes — the guard's reason text discriminates):** **(a)** an ordinary corrective recipe on the hardening dispatch (hash mismatch — a transcription slip on YOUR copy of the emitted `dispatch_prompt`, NOT recursion) → re-run `python3 ~/.claude/scripts/bug-state.py --emit-dispatch hardening …` (fresh nonce, same `--context` keys) and make exactly ONE verbatim re-dispatch attempt, copying `dispatch_prompt` mechanically. **(b)** the guard's HALT REASON (text contains "halt" and "PushNotification" — the denied prompt matched a registered hardening-class entry, i.e. genuine depth-1 recursion) OR a SECOND recipe denial → run `python3 ~/.claude/scripts/bug-state.py --run-end`; surface `⚠ hardening dispatch denied — depth cap reached; halting run` (T6); PushNotification `"lazy-bug-batch halted — hardening dispatch denied at depth cap; operator review required."`; print final batch report, STOP. Never a hardening dispatch beyond the single (a) re-attempt.

### 1d.5. Post-cycle input audit (Opus — runs only on `spec-bug` and `spec-phases` cycles)

**Skip conditions (bug-pipeline bindings):**
- `sub_skill` is NOT in {`spec-bug`, `spec-phases`}. (`bug-state.py` emits no `plan-feature`;
  `plan-bug` is a planning step, not a SPEC/PHASES-authoring cycle — skip audit for `plan-bug`.)
- The cycle was a pseudo-skill (Step 1c.5 already ran inline).
- The cycle subagent already wrote `NEEDS_INPUT.md` for this bug this cycle (double-fire guard).
- The cycle subagent returned a hard failure with no SPEC/PHASES delta.

Emit the input-audit dispatch via the script (registry-registered, guard allows it):

```bash
python3 ~/.claude/scripts/bug-state.py \
  --emit-dispatch input-audit \
  --context item_name="{bug_name}" \
  --context spec_path="{spec_path}" \
  --context cycle_kind="{sub_skill}" \
  --context cycle_summary="{cycle_summary}" \
  --context cycle_commit_sha="{cycle_commit_sha or HEAD~1}" \
  --context item_id="{bug_id}" \
  --context cwd="{cwd}"
```

Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`. The `@requires` keys for `--emit-dispatch input-audit` are: `item_name`, `spec_path`, `cycle_kind`, `cycle_summary`, `cycle_commit_sha`, `item_id`, `cwd`.

For post-return handling and `audit_concurs` recording see `~/.claude/skills/lazy-batch/SKILL.md` Step 1d.5. Bug-pipeline token substitutions:
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
- **Spin-off notification (Step 1e step 3a):** if a cycle return reports spinning off a bug doc or an `--enqueue-adhoc` item (the cycle owns the reverse-reference in the origin doc per `cycle-base-prompt.md`), fire `PushNotification("spun off {id} — {reason}")` and add the D7 digest entry (`completeness-policy.md` §Logging / §5 — pre-authorized, notify + log, never a question).
- Per-cycle chat output: T2 at dispatch + T3 at return per orchestrator-voice.md / `/lazy-batch` Step 3 — heading `### {Step name} — {work summary} [{n}/{max}]` (forward: `[{forward_cycles+1}/{max_cycles}]`; meta: `[meta {meta_cycles}/{2*max_cycles}]`); the `disp` line carries `{sub_skill} → {bug_id}`.
- **Post-`/execute-plan` and `/mcp-test` ledger-consistency guard (guardrail D):** see
  `~/.claude/skills/lazy-batch/SKILL.md` Step 1e item 4a for the full guard algorithm. Runs
  identically for the bug pipeline — including the plan-scoping rule: pass `--plan {plan_file}`
  (the probe's `sub_skill_args`) on `/execute-plan` cycles so a pending later plan part does not
  false-fail the guard; use the feature-level call on `/mcp-test` cycles (no plan part):
  ```bash
  git fetch origin $(git rev-parse --abbrev-ref HEAD)
  # /execute-plan cycle (plan-scoped):
  python3 ~/.claude/scripts/bug-state.py --repo-root <repo_root> --verify-ledger {spec_path} --plan {plan_file}
  # /mcp-test cycle (feature-level):
  python3 ~/.claude/scripts/bug-state.py --repo-root <repo_root> --verify-ledger {spec_path}
  ```
  Recovery dispatch (emit-dispatch — registry-registered, guard allows it):
  ```bash
  python3 ~/.claude/scripts/bug-state.py \
    --emit-dispatch recovery \
    --context item_name="{bug_name}" \
    --context spec_path="{spec_path}" \
    --context failure_summary="<failing_check name: <description>>" \
    --context item_id="{bug_id}" \
    --context cwd="{cwd}"
  ```
  Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`. The `@requires` keys for `--emit-dispatch recovery` are: `item_name`, `spec_path`, `failure_summary`, `cwd`, `item_id`.
- Increment `forward_cycles`. Return to Step 1a.

### 1f. Research-wait mode

NOT APPLICABLE to the bug pipeline. `bug-state.py` never emits `needs-research` or
`queue-blocked-on-research`. This step is entirely absent.

### 1g. Decision-resume mode (`terminal_reason == "needs-input"`)

**Meta-cap check (FIRST):** `if meta_cycles >= 2 * max_cycles:` → run `python3 ~/.claude/scripts/bug-state.py --run-end`, then halt with message
`"lazy-bug-batch meta-cycle cap (2× max_cycles = {2*max_cycles}) reached — too many resolution/recovery cycles. Restart from a fresh session."`, PushNotification, print final batch report, STOP.

**Pipeline binding for the shared handler** — `{SKILL}` = `/lazy-bug-batch`,
`{STATE_SCRIPT}` = `bug-state.py`, `{ITEM}` = bug, `{PUSH_RULE}` = workstation (standard push).
The shared handler's "increment `cycle`" step translates to **increment `meta_cycles`**. The
per-cycle update block heading uses the two-counter format (Step 3 template).

**Apply-resolution dispatch (emit-dispatch — registry-validated).** When the shared handler instructs you to dispatch the apply-resolution subagent, emit it via the script:

```bash
python3 ~/.claude/scripts/bug-state.py \
  --emit-dispatch apply-resolution \
  --context item_name="{bug_name}" \
  --context spec_path="{spec_path}" \
  --context sentinel_path="{spec_path}/NEEDS_INPUT.md" \
  --context resolution_summary="<one-line summary of the chosen resolution>" \
  --context resolution_kind="needs-input" \
  --context chosen_path="<the option label the operator chose>" \
  --context item_id="{bug_id}" \
  --context cwd="{cwd}"
```

Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`.

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

**Meta-cap check (FIRST):** same as Step 1g meta-cap check (run `--run-end` before PushNotification + final report).

**Pipeline binding** — `{SKILL}` = `/lazy-bug-batch`, `{STATE_SCRIPT}` = `bug-state.py`,
`{ITEM}` = bug, `{SPEC_ROOT}` = `docs/bugs`, `{ADD_PHASE}` = `/add-phase` (or `/plan-bug` if
PHASES.md is absent), `{PUSH_RULE}` = workstation (standard push). Increment `meta_cycles`.

**Apply-resolution dispatch (emit-dispatch — registry-validated).** When the shared handler instructs you to dispatch the apply-resolution subagent, emit it via the script:

```bash
python3 ~/.claude/scripts/bug-state.py \
  --emit-dispatch apply-resolution \
  --context item_name="{bug_name}" \
  --context spec_path="{spec_path}" \
  --context sentinel_path="{spec_path}/BLOCKED.md" \
  --context resolution_summary="<one-line summary of the chosen resolution>" \
  --context resolution_kind="blocked" \
  --context chosen_path="<the option label the operator chose>" \
  --context item_id="{bug_id}" \
  --context cwd="{cwd}"
```

Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`.

See `~/.claude/skills/_components/blocked-resolution.md`

---

### 1i. Operator-directed halt-resolution (other non-max-cycles problem-terminals)

**Meta-cap check (FIRST):** same as Step 1g meta-cap check (run `--run-end` before PushNotification + final report).

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
done   {duration} · {load-bearing outcome}
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
- **Hook machinery (Phase 5 — turn-routing-enforcement).** `--run-start` (Step 0.55, uses `bug-state.py`) activates the inject + validate-deny hooks scoped to the run. `--run-end` (every terminal path, §1c.6) deletes the marker + registry. The hardening dispatch (`--emit-dispatch hardening`) is the self-repair signal — depth hard-capped at 1. All non-cycle dispatch classes are emitted via `--emit-dispatch <class>` and dispatched VERBATIM.

<!-- COUPLED-PAIR DIFF (lazy-bug-batch vs lazy-batch / lazy-batch-cloud) — Phase 5 turn-routing-enforcement
     lazy-bug-batch differences from lazy-batch:
       - State script: bug-state.py (not lazy-state.py)
       - Spec root: docs/bugs/ (not docs/features/)
       - Entity vocab: bug_id/bug_name (not feature_id/feature_name)
       - Terminal success: all-bugs-fixed (not all-features-complete)
       - Completion receipt: FIXED.md / __mark_fixed__ (not COMPLETED.md / __mark_complete__)
       - Step 0.55 marker: pipeline=bug (not pipeline=feature)
       - No Step 0.5 pre-loop ingest (bugs have no research)
       - No --allow-research-skip, no needs-research, no queue-blocked-on-research
       - all-remaining-deferred terminal (bugs only)
       - scoped-id-not-found terminal via --bug-id
     Structurally identical to lazy-batch for Changes A–G (hook activation, run-end on terminals,
       LAZY-ROUTE banner consumption, denial recovery, emit-dispatch dispatch sites,
       post-compaction counter from marker, coupled-pair diff comment). -->

<!-- COUPLED-PAIR DIFF (lazy-bug-batch ↔ lazy-batch ↔ lazy-batch-cloud) — Phase 7 turn-routing-enforcement
     Mirrored identically with lazy-batch (bug-state.py / bug_id|bug_name bindings):
       - WU-7.1: §1d.1 "Pending hardening debt" — pending_hardening>0 ⇒ FIFO emit+dispatch before any
         forward route; --run-end refuses on unacked denials; --ack-unhardened operator-only.
       - WU-7.2: §1d.1 Depth-cap split into shape-(a) recipe denial (one verbatim re-dispatch, fresh
         nonce) vs shape-(b) halt-reason / second-recipe denial (existing halt). Never a 3rd.
       - WU-7.3c: §1d "Continuation cycles re-emit" gained the Freshness rule (no cross-turn dispatch;
         re-emit fresh same-turn; --context slots the only customization point).
       - WU-7.4: Budget-and-queue guard gained the unattended-checkpoint arm (--run-end --reason
         checkpoint --next-route + PushNotification + T7 trigger); Step 0.55 surfaces resumed_from_checkpoint.
       - WU-7.5c: Step 1e binding — PushNotification("spun off {id} — {reason}") + D7 digest on any cycle
         return reporting a spin-off. -->
<!-- Phase 8 (turn-routing-enforcement, 2026-06-12) — coupled-pair mirror note:
       - WU-8.2/8.3: §1d.1 "Pending hardening debt" rewritten — probe WITHHOLDS the forward route
         (route_overridden_by + hardening_emit_command); ack moved to guard-allow time (emission
         no longer acks); full-probe-JSON consumption rule (field-extractor piping BANNED).
       Mirrored verbatim across lazy-batch / lazy-bug-batch / lazy-batch-cloud (cloud keeps
       lazy-state.py --cloud paths). Script contract: lazy_core.py read_run_marker path B is now
       non-destructive (concurrent interactive sessions never delete a live run's marker). -->

