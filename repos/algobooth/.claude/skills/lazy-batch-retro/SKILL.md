---
name: lazy-batch-retro
description: Audit and grade a completed /lazy-batch or /lazy-batch-cloud run for skill-compliance. Read-only. Writes per-feature review artifacts under docs/features/<feat>/LAZY_BATCH_REVIEW_<date>.md. After writing, Step 6c runs the shared audit-table-validator component over every artifact, annotating Compliance Matrix / Findings rows with ⚠ NOT-FOUND-IN-SPEC or ⚠ CROSS-FEATURE-DUP markers so the next audit walker spots misattributions and copy-paste errors before walking them as gaps. Triggers on 'audit batch', 'grade batch', 'review batch run', '/lazy-batch-retro'.
argument-hint: [session-id | --branch <ref> | --features <feat,feat,...>]
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
---

# Lazy Batch Retro — Skill-Compliance Auditor

A read-only auditor that grades a completed `/lazy-batch` or `/lazy-batch-cloud` run for **skill compliance** (NOT spec compliance — that's `/retro`'s job). Reads the parent session JSONL, every surviving subagent transcript under `/tmp/claude-0/...`, the on-disk git evidence, every feature artifact, and re-loads every skill that was invoked. Produces one review artifact per feature touched plus a cross-cutting overview when multiple features are involved.

**HARD REQUIREMENT — READ-ONLY ON SOURCE.** This skill MUST NOT touch source code, tests, plan files, PHASES.md, SPEC.md, or any artifact other than:
  - The review markdown files it produces under `docs/features/<area>/<feat>/LAZY_BATCH_REVIEW_<YYYY-MM-DD>.md`.
  - The optional cross-cutting overview under `docs/features/_index/LAZY_BATCH_REVIEW_<YYYY-MM-DD>_overview.md`.
  - One commit message documenting the review.

**HARD REQUIREMENT — ORCHESTRATOR-ONLY (NO SUBAGENT DISPATCH).** This skill does NOT call `Agent` or `Skill`. The audit is bounded — a few thousand lines of jsonl + a handful of skill files. Keep it in the orchestrator session so the audit's own behavior is auditable.

**HARD REQUIREMENT — NO PLAN MODE.** Do NOT call `EnterPlanMode` or `ExitPlanMode`. Write artifacts directly.

**HARD REQUIREMENT — CITATIONS NOT TRUST.** Do NOT trust agent summaries alone. Past runs showed cycles that ran quality gates but elided them from the summary. Every grading assertion MUST cite a specific source — a jsonl line, a transcript tool_use, a commit SHA, a sentinel path, or a line in the skill being graded.

---

## Step 0: Parse Arguments

`$ARGUMENTS` is tokenized on whitespace. Recognized forms:

| Form | Meaning |
|------|---------|
| (empty) | Auto-detect: current git branch + most recent jsonl whose mtime overlaps the branch's first commit timestamp |
| `<session-id>` | A bare jsonl basename (with or without `.jsonl` suffix) — `glob ~/.claude/projects/<encoded-cwd>/<id>*.jsonl` |
| `--branch <ref>` | Grade all batch cycles on the given branch ref. Selector logic: find every jsonl whose first `/lazy-batch[-cloud]` invocation occurred while HEAD pointed at this ref. |
| `--features <feat,feat,...>` | Filter to specific feature IDs. May be combined with the above selectors. |

Reject unknown tokens with:

> `/lazy-batch-retro`: unrecognized argument `{token}`. Usage: `/lazy-batch-retro [session-id | --branch <ref> | --features <feat,feat,...>]`.

Print the start bookend:

```
## /lazy-batch-retro — Starting
**Repo root:** {cwd}
**Selector:** {auto-detect | session-id=<id> | --branch <ref>}
**Feature filter:** {none | <list>}
```

---

## Step 1: Resolve the batch run (Phase 0 — locate jsonl)

Walk the selector in priority order and resolve a list of one or more jsonl paths.

### 1a. Encode the cwd path the way Claude Code does

Claude Code stores parent-session jsonls under `~/.claude/projects/<encoded-cwd>/`. The encoding rule: replace `/` with `-`, prepend a leading `-`. Example: `/home/user/AlgoBooth` → `-home-user-AlgoBooth`.

```bash
encoded_cwd=$(pwd | sed 's|/|-|g')   # leading slash → leading dash naturally
projects_dir="$HOME/.claude/projects/$encoded_cwd"
```

If `$projects_dir` does not exist, halt with:

> `/lazy-batch-retro`: no Claude Code session directory found at `{projects_dir}`. The audit requires the parent session JSONLs — re-run from the repo root that hosted the batch invocation.

### 1b. Resolve candidate jsonls

- **Explicit session-id:** `glob $projects_dir/<id>*.jsonl`. Strip `.jsonl` suffix from the arg if present. If zero matches, halt with `no matching jsonl for session id '<id>'`.
- **--branch:** list every jsonl in `$projects_dir` whose first `/lazy-batch` or `/lazy-batch-cloud` invocation falls inside the branch's commit-time window (first commit of branch from `merge-base origin/main..HEAD` → tip of branch). Use mtime as a pre-filter, then confirm by parsing the user messages.
- **Auto-detect:** current `git branch --show-current` → use --branch logic above with the current branch.

For each candidate, verify it actually contains a `/lazy-batch` or `/lazy-batch-cloud` slash-command in a user message. If a candidate has none, drop it silently. If the final list is empty, halt with:

> `/lazy-batch-retro`: no /lazy-batch or /lazy-batch-cloud invocation found in the resolved session(s). Provide an explicit <session-id> or correct --branch.

Print:

```
**Candidate sessions:** {N}
{for each:}  - {basename}.jsonl ({first-batch-invocation-line-number}, {feature_count} features touched)
```

---

## Step 2: Context gathering (Phase 1 — exhaustive evidence walk)

Walk every evidence source. Cache contents in memory (the orchestrator session). Each citation in the final artifact must name the source file and (where applicable) line/SHA.

### 2a. Parent session JSONL

For each resolved jsonl, parse line-by-line. Use Python via `Bash` heredoc (the format is stable enough for `json.loads` + a handful of regexes):

```bash
python3 << 'PYEOF'
import json, re
from pathlib import Path

jsonl = Path("{jsonl_path}")
events = {
    "user_typed": [],      # user-typed slash commands & responses
    "agent_dispatches": [], # Agent tool_use calls from main session
    "task_notifications": [], # task-notification user messages
    "stop_hook_feedback": [], # stop-hook signals
    "command_names": [],   # <command-name> tags
}

for lineno, line in enumerate(jsonl.read_text().splitlines(), start=1):
    if not line.strip():
        continue
    try:
        ev = json.loads(line)
    except Exception:
        continue
    t = ev.get("type")
    if t == "user":
        content = ev.get("message", {}).get("content")
        if isinstance(content, str):
            # Extract <command-name> tags
            for m in re.finditer(r"<command-name>([^<]+)</command-name>", content):
                events["command_names"].append({"line": lineno, "name": m.group(1)})
            # Slash invocations
            if "/lazy-batch" in content or content.lstrip().startswith("/"):
                events["user_typed"].append({"line": lineno, "text": content})
            # Task notifications
            if "<task-id>" in content:
                tid = re.search(r"<task-id>([^<]+)</task-id>", content)
                summ = re.search(r"<summary>(.*?)</summary>", content, re.DOTALL)
                tok = re.search(r"<total_tokens>(\d+)</total_tokens>", content)
                tools = re.search(r"<tool_uses>(\d+)</tool_uses>", content)
                dur = re.search(r"<duration_ms>(\d+)</duration_ms>", content)
                events["task_notifications"].append({
                    "line": lineno,
                    "task_id": tid.group(1) if tid else None,
                    "summary": summ.group(1).strip() if summ else "",
                    "total_tokens": int(tok.group(1)) if tok else None,
                    "tool_uses": int(tools.group(1)) if tools else None,
                    "duration_ms": int(dur.group(1)) if dur else None,
                })
            if "stop-hook" in content.lower() or "uncommitted" in content.lower():
                events["stop_hook_feedback"].append({"line": lineno, "text": content[:500]})
    elif t == "assistant":
        content = ev.get("message", {}).get("content", [])
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_use" and block.get("name") == "Agent":
                    inp = block.get("input", {})
                    events["agent_dispatches"].append({
                        "line": lineno,
                        "tool_use_id": block.get("id"),
                        "model": inp.get("model"),
                        "subagent_type": inp.get("subagent_type"),
                        "description": inp.get("description"),
                        "prompt": inp.get("prompt"),  # FULL prompt — do NOT truncate
                    })

import json as _j
print(_j.dumps(events, indent=2))
PYEOF
```

Save the parsed events into an in-memory dict keyed by jsonl basename.

### 2b. Subagent transcripts (ephemeral — /tmp/claude-0/...)

For each `agent_dispatch` event recorded in 2a, look up its transcript:

```bash
tmp_dir="/tmp/claude-0/$encoded_cwd/$session_id/tasks"
transcript="$tmp_dir/{task_id}.output"   # task_id == tool_use_id
```

If the file exists, parse the same shape (one JSONL of the subagent's own session). Extract:

- Every Bash tool_use call. Classify the command into:
  - `qg` — matches `npm run qg`
  - `cargo-test` — matches `cargo test`
  - `cargo-clippy` — matches `cargo clippy`
  - `cargo-check` — matches `cargo check`
  - `vitest` — matches `vitest`, `npx vitest`, or `npm run test`
  - `git-commit` — matches `git commit`
  - `git-push` — matches `git push`
  - `git-other` — any other `git` command
  - `fs` — `ls`, `cat`, `find`, `grep`, `rg`, etc.
  - `other`
- Every Edit and Write tool_use call. Record `file_path` and a sha1 of the diff/content (do NOT keep the full content — too noisy). Flag any path under `src/`, `src-tauri/`, `tests/`, or matching `*.rs`/`*.ts`/`*.tsx`/`*.vue` as a source-file mutation.
- Every nested Agent tool_use call — these are **sub-subagent** dispatches. Record `.input.model`, `.input.subagent_type`, `.input.description`. **This is the load-bearing check for "did /execute-plan correctly dispatch Sonnet sub-subagents?"**
- Tool result content for each tool_use, truncated to 500 chars per result.

**IMPORTANT — transcript availability is degraded.** `/tmp` is reclaimed on container restart. For each agent dispatch, record `transcript_available: bool`. If false, every R-EP-*, R-O-3, R-O-4 grade on that cycle MUST be `unverifiable` (not "pass") and the artifact's confidence section MUST flag the gap.

### 2c. Git evidence

```bash
# Determine the baseline. Default: merge-base with origin/main, or the
# first commit timestamp older than the earliest jsonl mtime.
baseline=$(git merge-base origin/main HEAD 2>/dev/null || git rev-list --max-parents=0 HEAD | head -1)
git log --format='%H %ci %s' "$baseline"..HEAD
for sha in $(git log --format='%H' "$baseline"..HEAD); do
  git show --stat "$sha"
done
```

Parse commit messages for batch markers: `Phase \d+`, `batch \d+`, conventional-commit prefixes (`feat`, `chore`, `docs`, `fix`, `refactor`), and feature-id slugs. Map commits to features and (where possible) to cycles.

### 2d. Feature artifacts on disk

For every feature_id touched in the run (determined from 2a's `current_step` references and 2c's commit messages), read:

- `docs/features/<area>/<feat>/SPEC.md` — capture the `**Status:**` line.
- `docs/features/<area>/<feat>/PHASES.md` — capture every phase's `Status:` field AND every `Implementation Notes (YYYY-MM-DD)` block. These notes are the durable record of QG runs, test counts, design deviations.
- `docs/features/<area>/<feat>/plans/*.md` — capture each plan's YAML frontmatter (`status`, `kind`, `phases`) and the count of unchecked deliverables (`- [ ]`) vs checked (`- [x]`).
- All sentinel files: `BLOCKED.md`, `NEEDS_INPUT.md`, `NEEDS_RESEARCH.md`, `DEFERRED_NON_CLOUD.md`, `RETRO_DONE.md`, `VALIDATED.md`, `MCP_TEST_RESULTS.md`, `SKIP_MCP_TEST.md`. Record presence, parsed YAML frontmatter, and last-modified time.

Also diff the feature directory against the pre-batch baseline commit to identify which files actually landed during the run vs which were pre-existing.

### 2e. Skill definitions (re-loaded from disk, NOT from memory)

Read each skill in full and cache the contents:

- The invoked top-level orchestrator: `~/.claude/skills/lazy-batch/SKILL.md` OR `~/source/repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (path may vary based on `cwd` — try both `.claude/skills/lazy-batch-cloud/SKILL.md` relative to cwd and `~/.claude/skills/lazy-batch-cloud/SKILL.md` for symlink resolution).
- Every downstream skill referenced by an `agent_dispatch.prompt` from 2a:
  - `~/.claude/skills/spec/SKILL.md`
  - `~/.claude/skills/spec-phases/SKILL.md`
  - `~/.claude/skills/write-plan/SKILL.md`
  - `~/.claude/skills/execute-plan/SKILL.md`
  - `~/.claude/skills/retro/SKILL.md`
  - `~/.claude/skills/retro-feature/SKILL.md` (when present)
  - `~/.claude/skills/ingest-research/SKILL.md`
  - `~/.claude/skills/add-phase/SKILL.md`
  - `.claude/skills/mcp-test/SKILL.md` (repo-scoped)
- Every `_components/*.md` referenced inline by those skills (via `!cat ~/.claude/skills/_components/<name>.md`): `task-tracking.md`, `tdd-protocol.md`, `subagent-launch.md`, `subagent-review.md`, `quality-gates.md`, `commit-and-push.md`, `sentinel-frontmatter.md`, `implementation-agent.md`, `tdd-test-agent.md`, `phases-update.md`, `plan-file-output.md`.
- The state script: `~/.claude/scripts/lazy-state.py` (cache the source for citing state-machine rules).

For each cached skill, also record the file's git SHA at HEAD (`git log -1 --format=%H -- <path>` if tracked) so the artifact's "skill versions" footer reflects exactly which revision was graded.

---

## Step 3: Build the cycle ledger (Phase 2)

Reconstruct the run as an ordered ledger. Each row is one cycle (one subagent dispatch OR one pseudo-skill inline action). Columns:

| Column | Source |
|--------|--------|
| `cycle_n` | running 1-indexed count |
| `timestamp` | parent jsonl event timestamp |
| `model` | from `agent_dispatch.model` (e.g., `opus`, `sonnet`) |
| `subagent_type` | from `agent_dispatch.subagent_type` |
| `description` | from `agent_dispatch.description` |
| `task_id` | from `agent_dispatch.tool_use_id` |
| `total_tokens` | from matching task-notification |
| `tool_uses` | from matching task-notification |
| `duration_ms` | from matching task-notification |
| `result_disposition` | inferred (see below) |
| `feature_id` | inferred from the agent prompt's `Feature: ...` line + commit attribution |
| `transcript_available` | true iff `/tmp/claude-0/.../tasks/<task_id>.output` exists |

**`result_disposition` ∈** {`success`, `halted-blocked`, `halted-needs-input`, `halted-needs-research`, `halted-cloud-limitation`, `max-cycles`, `user-halt`, `unknown`}. Infer from:
- Sentinel writes attributed to this cycle (by commit attribution or by timestamp window).
- The final summary block in the subagent transcript (look for "BLOCKED", "DEFERRED", "needs input", "max cycles" in the last assistant message).

Also reconstruct pseudo-skill cycles (`__write_validated_from_skip__`, `__write_validated_from_results__`, `__mark_complete__`, `__write_deferred_non_cloud__`) by scanning the parent session for sentinel-file Edit/Write tool_uses by the orchestrator itself (not a subagent). These are inline orchestrator actions — record them with `subagent_type: "(inline)"`, `model: "(orchestrator)"`, `task_id: null`, `transcript_available: false`.

Print a compact summary to chat:

```
**Cycle ledger:** {N} cycles across {M} feature(s).
  Real-skill (subagent dispatch): {count}
  Pseudo-skill (inline orchestrator): {count}
  Transcripts available: {avail_count}/{count}  ⚠ {note if any missing}
```

---

## Step 4: Grade against the skill rules (Phase 3)

For each cycle, walk the relevant skill's instructions verbatim and grade compliance. Verdicts: `pass`, `fail`, `partial`, `unverifiable`, `n/a`. Each verdict needs a 1–2 sentence citation pointing at the cached source.

### 4a. ORCHESTRATOR-LEVEL RULES (against lazy-batch[-cloud]/SKILL.md)

| Rule | What to check |
|------|---------------|
| **R-O-1** Cycle cadence | The orchestrator called `lazy-state.py` before each cycle. Check the parent jsonl for Bash tool_uses matching `python3.*lazy-state.py` immediately preceding each cycle's Agent dispatch. |
| **R-O-2** Cycle count | `cycle_count ≤ --max-cycles` (default 10 unless `$ARGUMENTS` overrode). Read the orchestrator's start-bookend from the first assistant message in the parent jsonl to recover `max_cycles`. |
| **R-O-3** Subagent model | Every real-skill cycle dispatched with `model: "opus"` per the skill's HARD CONSTRAINTS. Exceptions explicitly permitted: `/ingest-research` (Sonnet), Step 1g apply-resolution (Sonnet), Step 0.5 pre-loop ingest (Sonnet). |
| **R-O-4** Prompt template compliance | Compare each cycle's dispatched `prompt` against the lazy-batch skill's base template (capture verbatim). Produce a unified diff. Flag missing load-bearing clauses: "Operating mode: batch", "follow the skill's internal subagent-vs-orchestrator rules", absence of contradictory "you may NOT spawn further subagents" inside an `/execute-plan` cycle prompt. |
| **R-O-5** Halt-on-sentinel honored | Look for cycles whose state script returned `terminal_reason: blocked` / `needs-input` / `needs-research`. Verify the orchestrator either (a) halted cleanly OR (b) ran the Step 1g `AskUserQuestion` + apply-resolution path. |
| **R-O-6** Push cadence | Every cycle ended with a `git push -u origin <branch>` visible in either the subagent transcript Bash calls or the parent session Bash calls (within the cycle's timestamp window). |
| **R-O-7** Stop-hook signals addressed | No "uncommitted changes" warning carried across cycle boundaries. Cross-reference the `stop_hook_feedback` events from 2a against the next cycle's first user message. |

### 4b. DOWNSTREAM-SKILL RULES

For each cycle whose `description` or prompt resolves to a downstream skill, grade against that skill's own SKILL.md text:

#### `/spec` cycles
- **R-SP-1** Phase routing + Phase 1 contract: grade the cycle against the feature dir snapshot at cycle time.
  - **Phase 1** (no SPEC.md at cycle start, e.g. an `--adhoc` brief): the cycle MUST run the mechanical work autonomously and EITHER write a baseline `SPEC.md` draft + (optionally) a `NEEDS_INPUT.md` capping ≤4 baseline-GATING product-behavior decisions, OR write `BLOCKED.md` with `blocker_kind: pre-research-input-required` only for a genuine "can't draft even a placeholder" blocker. `fail` if the cycle wrote `BLOCKED.md` for what were really pick-A-or-B decisions (those belong in `NEEDS_INPUT.md`), or lifted research-answerable questions into `NEEDS_INPUT.md` instead of the research prompt, or invented answers to gating product-behavior decisions instead of surfacing them.
  - **Phase 2** (SPEC.md present, no RESEARCH.md): the cycle MUST write `RESEARCH_PROMPT.md` and return normally (no `NEEDS_INPUT.md`, no refusal); the `needs-research` gate is what pauses the loop.
  - **Phase 3** fired only when `SPEC.md + RESEARCH.md` both existed.
- **R-SP-2** Exit state: SPEC.md status not `Draft (research stub)` after a finalize cycle.

#### `/spec-phases` cycles
- **R-SPH-1** Cross-feature integration matrix populated in PHASES.md (look for a `## Integration` section or matrix table).
- **R-SPH-2** PHASES.md touchpoint audit table present.

#### `/write-plan` cycles
- **R-WP-1** Partition cap honored — check write-plan's TRUE invariant, NOT a fixed part-count ceiling. Per `~/.claude/skills/write-plan/SKILL.md` Step 2.5, the hard cap is **≤ 8 work units per plan part**, and the skill splits into as many parts as the phase queue requires (a legitimately 7-phase feature can yield 7 parts when each phase is its own part — that is NOT a violation). Grade `pass` when (a) every `plans/*part-*.md` (or single `plans/*.md`) carries ≤ 8 work units AND (b) the parts' `phases:` frontmatter, taken together, cover every pending phase in execution order with no phase split across two parts. Grade `fail` ONLY when a part exceeds 8 WUs or a phase is split/dropped. Do NOT cap on part count alone — over-fragmentation (one-phase-per-part when packing was legal) is a `partial` efficiency note, not a hard `fail`, since write-plan Step 2.5 treats it as a contract smell rather than a cap breach. Cross-check the exact WU cap against the producer skill (`write-plan` Step 2.5) so this rule never drifts from it.
- **R-WP-2** Each plan part has valid YAML frontmatter (`status`, `kind`, `phases`) per `_components/plan-frontmatter.md`.
- **R-WP-3** Reference-based component card present in each plan.

#### `/execute-plan` cycles (THE LOAD-BEARING GRADE)

| Rule | What to check |
|------|---------------|
| **R-EP-1** HARD CONSTRAINT — no orchestrator Edit/Write on source files | Inspect the subagent transcript's Edit/Write tool_uses. Any `file_path` matching source patterns (`src/**`, `src-tauri/**`, `tests/**`, `*.rs`, `*.ts`, `*.tsx`, `*.vue`) called by the **subagent itself** (not its sub-subagents) is a violation. If transcript unavailable → `unverifiable` (NOT pass). |
| **R-EP-2** Sonnet sub-subagent dispatch | Count nested Agent tool_uses in the subagent transcript. Expected: ≥ 1 per batch in the plan (one test-agent + one impl-agent per batch is the minimum per the plan template). **ZERO sub-subagents = fail, full stop.** |
| **R-EP-3** Per-batch TDD | A test-agent Agent call (description containing "test", "TDD") precedes an impl-agent Agent call (description containing "impl", "implementation") in transcript order. |
| **R-EP-4** Subagent review step (Step B.2) | The orchestrator (the /execute-plan subagent) read each sub-subagent's output before dispatching the next batch — visible as a Read tool_use of the sub-subagent's report path or a continuation in the parent transcript. |
| **R-EP-5** PHASES.md update (Step B.3) | Implementation Notes block added per phase, dated, citing actual test counts + commands. Verify in the feature artifact snapshot from 2d. |
| **R-EP-6** Quality Gates (Step B.4) | QG commands present in transcript, right-sized per quality-gates.md's **Batch frequency** rule: a **full-workspace** `npm run qg [-- <lang>]` run is REQUIRED at plan-part completion AND on any escalation-triggering batch (import indirection, struct/interface field add, vitest/jest alias change, module rename/re-export); **intermediate batches MAY use targeted `cargo test -p` / `vitest <path>`** runs. Differentiate: `qg` (full workspace), `targeted-cargo/vitest`, `skipped`. **Pass** = a full-workspace run is present at part-end (and on each escalation batch) and passed; targeted-only on an intermediate batch is NOT a violation. **Fail** = the part closed (status → Complete) with no part-end full-workspace run, OR an escalation-triggering batch ran only a targeted gate, OR any gate failed and was not fixed. |
| **R-EP-7** Commit policy (Step B.5) | One commit per batch with the project's required message format (`feat(<feat>): <phase> <batch> — ...`). |
| **R-EP-8** Post-phase integration verification + CLAUDE.md review | Integration verification step ran at end of phase; CLAUDE.md updates landed when the phase introduced reusable patterns. |

**CLOUD BRANCH — `/execute-plan` under the `/lazy-batch-cloud` cloud-override.** The rows above describe the WORKSTATION contract, where `/execute-plan` MUST dispatch Sonnet test-agent + impl-agent sub-subagents and the orchestrator subagent must NOT touch source files itself. `/lazy-batch-cloud` documents a load-bearing override: the cloud cycle subagent has **no `Agent` tool**, so it performs ALL source/test edits INLINE with zero sub-subagents (see `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` HARD CONSTRAINTS "Cloud-specific" paragraph + the Step 1d cycle-prompt "Sub-subagent dispatch policy (CLOUD OVERRIDE — LOAD-BEARING)" block). When this override is in effect, the workstation R-EP-1/2/3/4 grades INVERT or become n/a — grading them as `fail` would force-cap every cloud feature for correctly following its own contract.

**Detecting cloud-mode for a given cycle.** A cycle is graded under the cloud branch iff EITHER:
  - the parent jsonl's `/lazy-batch[-cloud]` invocation (from 2a `user_typed` / `command_names`) was `/lazy-batch-cloud`, OR
  - the dispatched cycle prompt text (`agent_dispatch.prompt` from 2a) contains the cloud-override block — match on the marker phrases `"does NOT have the `Agent` tool"`, `"CLOUD OVERRIDE — LOAD-BEARING"`, or `"perform ... INLINE"` / `"Zero sub-subagent dispatches in a cloud /execute-plan cycle is the EXPECTED state"`.
Prefer the per-cycle prompt text when present (it is authoritative for that specific dispatch); fall back to the parent invocation otherwise. Record the detected mode in the cycle ledger so the compliance matrix citation can state which branch was applied.

When the cloud branch is in effect, grade the load-bearing rows as:

| Rule | Cloud-branch verdict |
|------|----------------------|
| **R-EP-1** (no subagent Edit/Write on source) | **INVERTS.** Inline source/test edits by the dispatched cycle subagent are EXPECTED, not forbidden → grade `pass` when the cycle subagent edited source inline (this is the cloud contract). The workstation reading ("any inline source edit is a violation") does NOT apply. If the transcript is unavailable, `unverifiable` (NOT pass) per the usual rule. |
| **R-EP-2** (Sonnet sub-subagent dispatch) | `n/a (cloud-override)` — zero sub-subagents is the EXPECTED state in cloud, NOT a `fail`. |
| **R-EP-3** (per-batch TDD agent ordering) | `n/a (cloud-override)` — no test-agent→impl-agent dispatch exists to order; TDD agent-separation is traded away in cloud (the cycle subagent should still write tests-before-impl inline, but that is not structurally verifiable from sub-subagent dispatch evidence). |
| **R-EP-4** (subagent review step B.2) | `n/a (cloud-override)` — there is no sub-subagent output to review between batches. |

R-EP-5 through R-EP-8 (PHASES.md update, quality gates, commit policy, integration verification) are UNCHANGED in cloud — they are still required and graded exactly as on workstation. Gates + the workstation `/retro` + the deferred MCP-validation pass are the compensating controls that the cloud override leans on; verify R-EP-6 (quality gates) especially, since it is the load-bearing check that survives the override.

#### `/retro` cycles
- **R-RE-1** `RETRO_DONE.md` written when no significant divergences (per retro's Step 6c).
- **R-RE-2** Plan file generated with `kind: retro-plan` and `status: Ready` (or Complete after a follow-up round).
- **R-RE-3** Round count tracked in `RETRO_DONE.md` frontmatter (`rounds:` field matches actual `retro-N-*.md` count).

#### `/mcp-test` cycles
- **R-MT-1** Scenario file referenced exists (`docs/testing/mcp-tests/<name>.md`).
- **R-MT-2** MCP server reachable precondition checked (`curl /health` in transcript).
- **R-MT-3** On cloud: correctly deferred via DEFERRED_NON_CLOUD.md (workstation should never see this; cloud should never run the actual test).

#### `/ingest-research` cycles
- **R-IR-1** Both `RESEARCH.md` AND `RESEARCH_SUMMARY.md` written per feature. **Critical** — bare staged `.txt` does not survive cloud container reclaim.
- **R-IR-2** SPEC.md's `> Draft (pre-Gemini)` trailer cleared.
- **R-IR-3** `queue.json` `"stub": true` flag cleared on ingested features.

### 4c. CLOUD-SPECIFIC RULES (only when grading /lazy-batch-cloud)

| Rule | What to check |
|------|---------------|
| **R-C-1** Step 2 cloud-saturation skip | Features with `RETRO_DONE.md + DEFERRED_NON_CLOUD.md + no VALIDATED.md` were skipped, not re-dispatched. Cross-reference the state-script output (parent jsonl Bash result) against the cycle dispatch list. |
| **R-C-2** Step 8 MCP deferral | Every MCP-test step in cloud wrote a `DEFERRED_NON_CLOUD.md` with proper frontmatter (`kind: deferred-non-cloud`, `deferred_step: 8` or `9` depending on revision, `deferred_by: lazy-cloud`). |
| **R-C-3** In-session research ingest | If research was uploaded mid-run, `/ingest-research` was dispatched and the loop resumed (not halted with terminal `needs-research`). |
| **R-C-4** No premature Complete (low severity) | A cloud cycle MUST NOT promote a feature's SPEC.md / PHASES.md top `**Status:**` to `Complete` while `DEFERRED_NON_CLOUD.md` exists and `VALIDATED.md` does not — that asserts completion before the workstation MCP-validation pass has run. From the 2d artifact snapshot: if `SPEC.md` `**Status:** Complete` AND `DEFERRED_NON_CLOUD.md` present AND `VALIDATED.md` absent → grade `fail` (severity **low**). The honest terminal cloud state is `In-progress` (or an explicit cloud-saturated marker) pending the workstation pass that writes `VALIDATED.md` and only then flips to `Complete`. Cite the offending status line + the sentinel presence/absence. |
| **R-C-5** Completion receipt present (medium severity) | Every feature whose `SPEC.md` top `**Status:**` is `Complete` MUST carry a `COMPLETED.md` receipt (`kind: completed`) — the durable proof it passed `__mark_complete__`'s integrity gate (phase-coherence + validation sentinel + MCP-coverage audit). From the 2d artifact snapshot: if `SPEC.md` `**Status:** Complete` AND `COMPLETED.md` absent → grade `fail` (severity **medium**) — the feature was flipped OUTSIDE the gate (the failure mode that let an unvalidated deliverable ship as Complete). `Superseded` features are exempt. A receipt with `provenance: backfilled-unverified` passes this rule but should be NOTED as never gate-verified. Cite the status line + receipt presence/provenance. |

---

## Step 5: Compute scores (Phase 4)

### 5a. Per-cycle compliance

```
cycle.compliance = pass_count / (pass_count + fail_count + partial_count)
```

`unverifiable` and `n/a` are excluded from the denominator. Round to nearest percent.

### 5b. Per-feature rollup

Average each feature's cycles' compliance (weighted equally). Also compute per-skill rollups for the executive summary (e.g. "execute-plan compliance: 7/12 = 58%").

### 5c. Headline grade

| Grade | Compliance |
|-------|------------|
| A | ≥ 95% |
| B | ≥ 85% |
| C | ≥ 70% |
| D | ≥ 50% |
| F | < 50% |

**Force-cap rule:** if any cycle's `R-EP-1` OR `R-EP-2` graded a **genuine workstation `fail`**, force-cap the feature's headline grade at **C** regardless of arithmetic. These are load-bearing workstation hard constraints; their violation breaks the skill contract. **The cap fires ONLY on a true workstation `fail`** — it MUST NOT fire on the Step 4b cloud-branch verdicts: a cloud `R-EP-1` `pass` (inverted — inline edits expected) and a cloud `R-EP-2`/`R-EP-3`/`R-EP-4` `n/a (cloud-override)` are correct contract-following, not violations. `n/a` and `pass` never cap; only a workstation `fail` does. (As always, `unverifiable` from a reclaimed transcript also never caps — it downgrades confidence, not grade.)

**Canary check (2026-05-22 audit context) — scoped to PRE-cloud-override sessions only.** This canary predates the documented `/lazy-batch-cloud` cloud-override. It applies ONLY to a cloud session whose cycle prompts do **NOT** contain the cloud-override block (detect per Step 4b "Detecting cloud-mode" — no `"CLOUD OVERRIDE — LOAD-BEARING"` / `"does NOT have the `Agent` tool"` markers in `agent_dispatch.prompt`). For such a pre-override session — e.g. reproducing session `0a6dafab` against branch `claude/lazy-batch-cloud-3rJaT` — expected output is **F on R-EP-1 and R-EP-2** for both `hard-state-reload` and `audio-thread-panic-catching` (Edit/Write used directly by /execute-plan subagent, zero Sonnet sub-subagents across 9 surviving transcripts), and the force-cap fires. **For any POST-cloud-override cloud run (cycle prompt CONTAINS the override block), this expectation is INVERTED:** the Step 4b cloud branch applies, so the expected verdict is `R-EP-1` **pass** (inline edits expected) and `R-EP-2`/`R-EP-3`/`R-EP-4` **`n/a (cloud-override)`**, and the force-cap does NOT fire. Do not assert F against a post-override cloud session — that would force-cap it for correctly following its own contract. If your audit gives a verdict that disagrees with whichever branch the session falls into, the skill is mis-implemented — re-check cloud-mode detection, transcript-availability handling, and the Edit/Write attribution.

---

## Step 6: Write review artifacts (Phase 5)

Write one markdown file per feature touched in the batch run.

**Path:** `docs/features/<area>/<feat>/LAZY_BATCH_REVIEW_<YYYY-MM-DD>.md`. If a file already exists for today, append the suffix `_2`, `_3`, etc. (probe by listing matching files first).

**Frontmatter (required):**

```yaml
---
kind: lazy-batch-review
feature_id: <id>
batch_invocation: <"lazy-batch" | "lazy-batch-cloud">
branch: <ref>
session_id: <basename of parent jsonl, without .jsonl>
cycles_count: <int>
headline_grade: <A|B|C|D|F>
force_capped: <true|false>
generated_at: <ISO 8601 UTC>
---
```

**Required body sections (in order):**

### 1. Executive Summary

≤ 5 bullets. State the headline grade, the worst rule, the best rule, the most surprising finding, and the headline recommendation.

### 2. Cycle Ledger

The Step 3 ledger filtered to this feature, rendered as a markdown table.

### 3. Compliance Matrix

Every applicable rule (orchestrator-level + downstream-skill rules that fired) with verdict + citation. Render as:

| Rule | Verdict | Citation |
|------|---------|----------|
| R-O-1 | pass | parent jsonl line 142: `Bash python3 ~/.claude/scripts/lazy-state.py` preceding Agent dispatch at line 158 |
| R-EP-1 | fail | `/tmp/claude-0/.../tasks/<id>.output` Edit tool_use at offset 12: `file_path: src-tauri/src/voice.rs` — orchestrator-level edit forbidden |
| ... | ... | ... |

### 4. Subagent Prompt Diff

For each real-skill cycle, two-column comparison: dispatched prompt (verbatim) vs expected template (from the skill's prompt-template section). Render the unified diff using `+`/`-` markers. Flag missing load-bearing clauses inline.

### 5. Tool-Call Census

Per cycle, a row:

| Cycle | Feature | Bash:qg | Bash:cargo | Bash:vitest | Bash:git | Bash:fs | Edit | Write | Agent (nested) |
|-------|---------|---------|-----------|-------------|----------|---------|------|-------|----------------|
| 1 | ... | 0 | 12 | 0 | 3 | 8 | 0 | 0 | 0 |

### 6. Artifact Delta

What files/sentinels changed during the batch (from git diff + sentinel mtime comparison against pre-batch baseline). Group by:
- Source files modified
- PHASES.md / SPEC.md / plan files modified
- Sentinels written (with `written_by` field)
- Sentinels deleted (with attribution if traceable)

### 7. Findings

Concrete deviations, ordered by severity (`critical` → `high` → `medium` → `low`). Each finding has:
- **Title** (one line)
- **Severity**
- **Rules failed** (comma-separated rule IDs)
- **Evidence** (citation)
- **Impact** (what the deviation cost the run — wasted cycles, lost work, hidden regressions, etc.)

### 8. Recommendations

Two subsections:

#### For the operator
How to invoke better next time — e.g., "pass `--max-cycles 6` until /execute-plan's sub-subagent issue is fixed", "stage research as RESEARCH.md not .txt before cloud sessions".

#### For the skill authors
Rule changes that would have caught this — e.g., "add a precondition check in /execute-plan that refuses to run if the orchestrator prompt contains 'you may NOT spawn further subagents'".

### 9. Skill versions footer

A small table recording the git SHA + path of every skill graded — so re-running the audit later on the same session against an updated skill set is unambiguous about which revision was checked.

```
| Skill | Path | SHA at HEAD |
|-------|------|-------------|
| lazy-batch | ~/.claude/skills/lazy-batch/SKILL.md | abc1234 |
| execute-plan | ~/.claude/skills/execute-plan/SKILL.md | def5678 |
| ... | ... | ... |
```

---

## Step 6b: Cross-cutting overview (when multiple features touched)

When the batch run touched ≥ 2 features, ALSO write `docs/features/_index/LAZY_BATCH_REVIEW_<YYYY-MM-DD>_overview.md` with:

```yaml
---
kind: lazy-batch-review-overview
batch_invocation: <"lazy-batch" | "lazy-batch-cloud">
branch: <ref>
session_id: <basename>
features: [<id1>, <id2>, ...]
generated_at: <ISO 8601 UTC>
---
```

Body sections:
1. **Per-feature headline grades** (table).
2. **Cross-cutting findings** — issues observed across multiple features (e.g., "every /execute-plan cycle in this run violated R-EP-1 — systemic, not feature-specific").
3. **Aggregate tool-call census** (sum across all features).
4. **Links** to each per-feature artifact.

Create `docs/features/_index/` if it does not exist (`mkdir -p`).

---

## Step 6c: Audit-Table Validator Pass (NEW — runs BEFORE commit)

**Rationale.** The audit walk surfaced two failure modes in per-feature decision tables that this skill writes: (a) `audit-misattribution` — a row flags a decision as a gap when it's actually resolved in the current SPEC (4 of 199 walked decisions had this shape); (b) `cross-feature copy-paste error` — a row appears literally identical in two different feature artifacts (17.L5 was a literal duplicate of 15.L4 in the source ledger). Both root-cause to "table written against an early snapshot, never re-validated". This step runs the shared validator over every artifact written in Steps 6 and 6b, before the Step 7 commit, so the annotations land in the same commit as the artifacts themselves.

The validator is non-destructive — it appends `⚠ NOT-FOUND-IN-SPEC` and/or `⚠ CROSS-FEATURE-DUP(<other-feature-id>)` markers to flagged table rows, never removes content. The audit walker (next operator or `/code-review`) sees the markers and can re-classify the rows before walking them as gaps.

!`cat ~/.claude/skills/_components/audit-table-validator.md`

### Invocation

For each per-feature artifact written in Step 6, build a record:

```
{
  artifact_path: "docs/features/<area>/<feature_id>/LAZY_BATCH_REVIEW_<date>.md",
  feature_id: <from frontmatter>,
  spec_md_path: <resolved via `find docs/features -name SPEC.md -path "*/<feature_id>/*"` — exactly one match expected>,
  tables: [
    {table_section_title: "## Compliance Matrix", row_anchor_column: 0},  # Rule column
    {table_section_title: "## Findings",          row_anchor_column: 0},  # Title column
  ]
}
```

For the cross-cutting overview from Step 6b (if written), include it in `artifact_paths` for cross-feature dup detection only (no SPEC validation — it has no `feature_id` in frontmatter, only a `features:` list).

Run the validator algorithm per the component above. The validator writes its annotations + summary block in place; capture its return status (`clean` or `annotated:N_not_found+M_dup`) for the Step 8 final bookend.

### Status-bookend integration

The Step 8 final bookend gains a `**Audit-table validator:**` line:

- `clean` — `**Audit-table validator:** clean — no SPEC drift / cross-feature dup detected.`
- `annotated:N+M` — `**Audit-table validator:** flagged {N} NOT-FOUND-IN-SPEC and {M} CROSS-FEATURE-DUP rows — review annotations in artifact files before walking.`

If the validator runs in `annotated` mode, the Step 7 commit message should be:

```
docs(lazy-batch-retro): grade <branch> batch run (audit-table validator flagged N+M rows)
```

So the commit history surfaces the validation outcome without requiring the audit walker to re-run the validator manually.

---

## Step 7: Commit (Phase 6)

Stage the review artifacts and create a commit:

```bash
git add docs/features/**/LAZY_BATCH_REVIEW_*.md docs/features/_index/LAZY_BATCH_REVIEW_*_overview.md 2>/dev/null
git commit -m "docs(lazy-batch-retro): grade <branch> batch run"
```

**Do NOT push.** Review docs are local-first; the user decides whether to push them.

If the project has a `.claude/skill-config/commit-policy.md`, follow it instead of the default message. Trailer line: omit per project default (review artifacts have no Claude-Code session URL convention).

---

## Step 8: Final status bookend

```
## /lazy-batch-retro — Done
**Sessions audited:** {N}
**Features graded:** {M}
**Headline grades:** {feat-A: B, feat-B: F, ...}
**Force-caps applied:** {feat-B (R-EP-1, R-EP-2 fail)}
**Artifacts written:**
  - docs/features/<area>/<feat-A>/LAZY_BATCH_REVIEW_<date>.md
  - docs/features/<area>/<feat-B>/LAZY_BATCH_REVIEW_<date>.md
  - docs/features/_index/LAZY_BATCH_REVIEW_<date>_overview.md  (if multi-feature)
**Commit:** {sha} — not pushed
**Confidence caveats:** {e.g., "2 cycles unverifiable due to transcript reclaim"}
```

STOP. Do not call work-log (review skills are themselves the work log).

---

## Notes

- This skill is **read-only** against source. The ONLY writes are the review markdown files + their commit.
- **No subagent dispatch.** The audit is bounded; keep it auditable in the orchestrator session.
- **Transcript availability is degraded** — `/tmp/claude-0/...` is reclaimed on container restart. Run the audit promptly after the batch run, OR accept downgraded confidence (every `R-EP-*` and `R-O-3/4` grade against a missing transcript is `unverifiable`, NEVER silently `pass`).
- The new sentinel kind `lazy-batch-review` is documented in `.claude/skill-config/sentinel-frontmatter.md` so the existing sentinel-frontmatter lint catches malformed artifacts.
- Coupling: this skill is NOT paired with another skill — there is no `/lazy-batch-retro-cloud`. Cloud-vs-workstation differences are handled by inspecting the parent jsonl's invocation (look for `/lazy-batch-cloud` vs `/lazy-batch` in `command_names`).
