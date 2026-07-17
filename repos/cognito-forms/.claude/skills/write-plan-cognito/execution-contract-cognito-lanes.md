# Execution Contract — Cognito lane overrides (single source)

**Contract version:** cognito-lanes-v3
(v3: SPEC content rides in the plan as per-phase `#### SPEC excerpts` blocks — the executor
does not read SPEC.md; PHASES.md reads are script-owned via `phases-slice.py`. v2 plans — no
excerpt blocks — remain executable: their L.0 falls back to reading the SPEC sections named in
the per-phase "SPEC.md references" field.)

This file is the **one canonical home** for the Cognito lane-execution policy that
`/write-plan-cognito` plans used to re-emit verbatim into every plan body (~16KB/plan). A
generated lane plan carries a short pointer block naming this file; `/execute-plan` reads it
(together with the generic `~/.claude/skills/_components/execution-contract.md`) as its operating
contract. Edit the lane policy HERE — never re-inline it into a plan.

> **How this file is consumed**
> - **Generated lane plans** carry a pointer block: read the generic contract first, then this
>   file; where the two disagree, THIS file wins (it is the Cognito-lane specialization). Plans do
>   NOT inline the sections below — they carry only per-plan content (touchpoint audit, schedule,
>   lanes, batch structure, plan-specific execution notes).
> - **`/execute-plan`** reads the generic contract per its own Step 3, then reads this file when
>   the plan's pointer block names it. The plan's own "Plan-specific execution notes" section
>   overrides both contracts where it speaks.
> - **Precedence (most-specific wins):** plan-specific notes → this lane contract → generic
>   `execution-contract.md`.
> - Repo-relative path (resolvable from any Cognito Forms worktree):
>   `.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md`.

---

## EXECUTION MODEL — READ THIS FIRST (Cognito lane override)

This plan uses an **orchestrator + Sonnet lane-agent** architecture:

| Role | What it does | Allowed tools |
|------|-------------|---------------|
| **Orchestrator (you)** | Read plan, compose Agent prompts, dispatch lane agents, run the typegen seam step, review output, run quality gates, update tracking docs | `Agent`, `Read`, `Bash` (gates/typegen only), `Skill` (build/test gates — `/msbuild` `/mstest` `/nxbuild` `/nxtest`), `TaskCreate`/`TaskUpdate` |
| **Sonnet lane agent** | Write ALL source and test code for ONE lane — tests first (RED), then implementation (GREEN) | `Edit`, `Write`, `Read`, `Bash`, `Grep`, `Glob`, `Skill` (for `/msbuild`, `/mstest`, `/nxtest` — the only sanctioned build/test path) |

**HARD CONSTRAINT:** You MUST NOT call `Edit` or `Write` on source or test files. If you are
about to modify a `.cs`, `.ts`, `.vue`, `.js`, `.tsx`, or test file — STOP and compose an `Agent`
tool call instead. The ONLY files you may modify directly: `PHASES.md`, `CLAUDE.md`, `CLAUDE.local.md`, the plan
file's frontmatter, `work-log.jsonl`. The ONLY source-adjacent artifact you regenerate directly
is `Cognito.Web.Client/libs/types/server-types/**` — via the typegen script, never by hand.

**Dispatch pattern:** `Agent({ description: "...", model: "sonnet", prompt: "<FULL self-contained context — lane definition + lane-agent briefing — the agent has zero prior context>" })`

**Dispatch-census note (overrides generic executor expectations):** Lane plans use inline-TDD
lane agents. ONE lane agent serves as BOTH the test agent and the implementation agent for its
lane — its briefing mandates failing-tests-first with pasted RED and GREEN output. For any
dispatch census, count each lane agent as one test-agent AND one impl-agent. A batch with ≥ 1
lane-agent dispatch satisfies the per-batch dispatch contract; do NOT dispatch separate test/impl
agents.

(The COMPONENT LOADING PROTOCOL is part of the generic `execution-contract.md` — it is not
repeated here. The Component Reference Card below OVERRIDES the generic contract's default card,
because lane plans use lane-specific steps L.0–L.7, repo-relative components, and queue-routed
gates.)

## Component Reference Card (Cognito lane override)

| Step | Component | Path |
|------|-----------|------|
| Step 0 | Task Tracking | `~/.claude/skills/_components/task-tracking.md` |
| Step L.0 | Source Re-read | `~/.claude/skills/_components/source-reread.md` |
| Step L.1 | Lane Agent Briefing | `.claude/skills/write-plan-cognito/lane-agent-briefing.md` (repo-relative) |
| Step L.3 | Lane Review | `~/.claude/skills/_components/subagent-review.md` |
| Step L.3 | Mount-Site Verification | `~/.claude/skills/_components/mount-site-verification.md` |
| Step L.4 | PHASES.md Update | `~/.claude/skills/_components/phases-update.md` |
| Step L.5 / Part-end | Quality Gates (tiered) | `.claude/skill-config/quality-gates.md` (repo-relative) |
| Step L.6 | Commit Policy | `.claude/skill-config/commit-policy.md` (repo-relative — this repo: no auto-commits) |
| Part-end | Integration Verification | `~/.claude/skills/_components/integration-verification.md` |
| Part-end | CLAUDE.md Review | `~/.claude/skills/_components/claude-md-review.md` |
| Final | Work Log | `~/.claude/skills/_components/work-log.md` |

## MANDATORY RULES — DO NOT SKIP ANY STEP (Cognito lane override)

These replace the generic contract's MANDATORY RULES for lane plans:

1. ALL source and test code is written by Sonnet lane agents via the `Agent` tool. The orchestrator never edits source/test files. The ONLY exception: trivial PASS-WITH-FIXES items (a few lines).
2. All lane-agent edits happen in the current worktree — NEVER create worktrees for agents.
3. Every lane with testable behavior follows inline TDD — the lane agent writes failing tests first and pastes RED then GREEN ground-truth output.
4. Lane agents use Tier 1 verification commands only, routed through the queue skills: `/msbuild -Project "<csproj>"` for an incremental project build and `/mstest -Filter "ClassName~…"` / `/nxtest -Project … -Pattern … -NoCoverage` for filtered tests. Never raw `dotnet`/`npx nx`. Nobody runs a full-solution `/msbuild` (no `-Project`) except the orchestrator at part-end Tier 2 (or on an escalation trigger).
5. Sequenced phases: the frontend lane is NOT dispatched until the typegen seam step completes and the server-types diff is reviewed.
6. Every lane's output is reviewed (diff review is the gate — assertion-vs-intent + propagation + scope; the `/mstest` re-run is conditional per Step L.3) before PHASES.md is updated or the next batch launches.
7. PHASES.md is updated after EACH batch completes (not deferred).
8. NO git commits or pushes at any point — repo policy. All git operations are manual (see commit-policy component).
9. The part-end Tier 2 gate (full-solution `/msbuild` (no `-Project`) + filtered `/mstest`/`/nxtest` for all touched areas) is MANDATORY and 100%-pass before this plan part is reported complete.
10. The plan + this contract are the complete instruction set — follow them exactly without relying on other external context.
11. Before each step, `Read` the component files listed for that step from disk.

---

## Execution Protocol (Cognito lane override)

The lane steps L.0–L.7, typegen seam, and tiered gates below replace the generic contract's
per-batch Steps B.0–B.6.

### Phase Selection Loop

Repeat until all phases in the plan's Execution Schedule are complete or a blocking issue
triggers early exit:

1. **Select ready phase(s):** entry criteria satisfied (prerequisite phases' deliverables all checked off). Phases from different features may run concurrently when the schedule allows and no lanes conflict on files.
2. **Announce:** "Implementing [feature] Phase N: [title]"
3. **Review prior context:** re-read previously completed phases' Implementation Notes (sibling `IMPLEMENTATION_NOTES.md` first, embedded in PHASES.md as fallback) — they take priority over the plan where they diverge.
4. **Execute all batches** per the Per-Batch Steps below.
5. **Report:** "[feature] Phase N: [title] — complete (uncommitted, per repo policy)"
6. **Loop.**

### Step 0: Initialize Task Tracking (MANDATORY — BEFORE ANYTHING ELSE)

Read `~/.claude/skills/_components/task-tracking.md` and follow it. Create one task per lane (not
per deliverable).

### Per-Batch Steps

#### Step L.0: Re-read Source Documents (MANDATORY)

Read `~/.claude/skills/_components/source-reread.md` and follow it. Re-read from disk: the
current phase's PHASES.md slice via `python ~/.claude/scripts/phases-slice.py <PHASES.md>
--phase <id> --no-preamble` (never the whole file; the script also indexes the sibling
`IMPLEMENTATION_NOTES.md` — slice prior-phase notes with `--notes <id>` so earlier lanes'
hiccups are not repeated), the plan file, and the SPEC content — which for v3 plans is the
phase's `#### SPEC excerpts` block in the plan itself (do NOT read SPEC.md; escalate per the
block's escalation rule only when an excerpt is insufficient, and record the escalation in the
phase's Implementation Notes).

#### Step L.1: Dispatch Lane Agent(s)

**PRE-FLIGHT:** confirm you will use `Agent` with `model: "sonnet"` for ALL code changes and will
NOT edit source/test files yourself.

Read `.claude/skills/write-plan-cognito/lane-agent-briefing.md`. For each lane in this batch,
compose an Agent prompt containing: (1) the lane definition from the plan (scope, files, test
expectations, implementation goal, spec requirements, Tier 1 commands), (2) the phase's `####
SPEC excerpts` block from the plan (verbatim — v2 plans without one: the SPEC sections its
"SPEC.md references" field names), (3) prior Implementation Notes that affect this lane (slice
via `phases-slice.py --notes <id>` — forwarding earlier lanes' pitfalls is what stops a later
lane from repeating them), (4) any Verified Touchpoint Audit rows the plan carries for this
lane's files, (5) the lane-agent briefing verbatim.

Parallel-seam phases: dispatch the batch's file-disjoint lane agents in a SINGLE message (the
plan's batch table is the disjointness proof — do not infer disjointness it doesn't assert).
Sequenced phases: dispatch only the backend lane now.

**Failed-agent recovery:** if a lane agent fails or returns garbage, re-dispatch once with the
failure context appended. Two failures on the same lane = blocking issue.

#### Step L.2: Typegen Seam (Sequenced phases only — between backend and frontend lanes)

After the backend lane passes review (Step L.3 runs for the backend lane FIRST in sequenced
phases):

1. Incremental build of the Services chain (NOT the full solution), queue-serialized + filtered:
   `/msbuild -Project "Cognito.Services/Cognito.Services.csproj"`
2. Regenerate types in place:
   `powershell.exe -Command "cd '<repo-root>\Cognito.Web.Client\libs\types\typegen'; ./generate-server-types.ps1 -UpdateInPlace"`
3. Review the diff: `git status --short -- "Cognito.Web.Client/libs/types/server-types/"` then `git diff -- "Cognito.Web.Client/libs/types/server-types/"`. Confirm the type changes match the backend lane's contract changes — nothing missing, nothing unexpected. Unexpected diffs = treat as a backend-lane review finding (NEEDS-REWORK the backend lane).
4. Dispatch the frontend lane (return to Step L.1) — its briefing must note that regenerated types are already on disk.

If a Sequenced phase's backend lane turns out to produce NO server-types diff, note that in
PHASES.md and continue — the classification was conservative, no harm done.

A phase the plan classifies **Single-lane (no seam)** skips this step entirely: it has exactly
one lane, so there is no frontend lane to dispatch and no mid-phase typegen — do not go looking
for a seam step or a second lane. A `server-types/**` diff surfacing at the part-end Tier 2 full
build is reconciled there (Part Completion). Older v3 plans may express the same shape as
`Sequenced` plus a plan-specific note that the seam is not run — treat identically.

#### Step L.3: Review Lane Output (MANDATORY BLOCKING GATE)

Read `~/.claude/skills/_components/subagent-review.md` and follow its complete protocol
(including the Ground-Truth Verification Gate), plus
`~/.claude/skills/_components/mount-site-verification.md` for new files/test classes.

**Cognito gate-cost rules (D5 — trust the banner; the diff read is the gate).** Field mining of 47
execute-plan runs (164 orchestrator ground-truth re-runs) found the per-lane `/mstest` re-run
caught **zero** clean PASS/FAIL divergences from a lane's pasted banner — every real defect in the
corpus came from *reading the diff* (assertion-vs-intent, propagation, scope/plan-conformance),
which a re-run cannot see (the tests were genuinely green). So the ground-truth re-run is now
**conditional**, and the mechanical integrity ceremony is default-off:

- **Default: trust the lane's `RESULT=<PASS|FAIL>` banner line.** The queue banner is
  fidelity-tagged (`result_fidelity=verified`; `build_fidelity` forces `RESULT=FAIL` on a
  no-output build), so its outcome is authoritative — do NOT re-run `/mstest`/`/nxtest` to
  re-confirm a `result_fidelity=verified` result. For inline-TDD lanes, read the lane agent's OWN
  pasted RED/GREEN output as the TDD evidence — verify the RED failed for the right reason
  (behavioral, not compile/setup) and the GREEN passes the same filter.
- **Conditional re-run — only when trust breaks.** Re-run the equivalent queue-routed command
  (`/mstest -Filter "ClassName~<same>"` / `/nxtest -Project <same> -Pattern <same> -NoCoverage` —
  compare PASS/FAIL outcome, NEVER trigger a build) ONLY if: the banner is missing / not
  `result_fidelity=verified`, the lane reported a backgrounded `enqueued as seq=N` instead of a
  completed banner, or the `git status --short` scope check (below) disagrees with the paste.
  `/mstest` is `--no-build` and filtered, so the conditional re-run stays cheap when it fires.
- **Skip the mechanical integrity ceremony by default** (overrides `subagent-review.md` Step 1.5's
  "always" integrity commands): the `wc -l`/`grep -n` byte-diff of the `GROUND-TRUTH OUTPUT` block
  and the "already-complete" `git log` sanity check caught nothing in the corpus — run them only if
  something already looks off. Keep the `git status --short` scope check of the lane's touched files
  as the one default integrity check — it is what caught out-of-scope edits (a real catch class).

The load-bearing gate is Step 2's diff review (assertion-vs-intent + propagation check + scope /
plan-conformance) — that is MANDATORY and never skipped; it is where every real defect was caught.

#### Step L.4: Update PHASES.md (MANDATORY)

Read `~/.claude/skills/_components/phases-update.md` and follow it. Check off completed
deliverables; add Implementation Notes (date, work completed, integration notes, pitfalls, files
modified).

#### Step L.5: Quality Gates (Tier 1 — already satisfied; verify, don't re-run)

Read `.claude/skill-config/quality-gates.md`. In-loop (Tier 1), the lane agent's verified
ground-truth output IS the gate — do not run additional builds or test passes beyond the Step L.3
re-run. **Escalation check:** if this batch changed server-side types consumed by the frontend
beyond what the typegen seam handled, added a field to a widely-constructed entity, or
renamed/re-exported a module — run the Tier 2 gate NOW (see Part Completion) before proceeding.

#### Step L.6: Commit Step

Read `.claude/skill-config/commit-policy.md`. **This repo: no auto-commits, no pushes — this step
is a no-op.** Proceed.

#### Step L.7: Proceed to Next Batch

Checklist (all must be true): review report with verdict produced; ground-truth verified;
PHASES.md updated; escalation check done. If any item is unchecked, go back.

### Part Completion (after ALL phases in this plan part)

1. **Tier 2 authoritative gate (MANDATORY, 100% pass):**
   - C# changes: `/msbuild` (full-solution, no `-Project` — also regenerates server types authoritatively) → `/mstest` filtered to ALL test classes touched by this part (never unfiltered).
   - Frontend changes: `/nxbuild` (touched projects) → `/nxtest` (touched projects).
   - Mixed: C# pair then frontend pair.
   - After the full build, check `git status --short -- "Cognito.Web.Client/libs/types/server-types/"` — any NEW diff means the typegen seam missed something; reconcile before proceeding.
   - Failures: dispatch Sonnet fix agents, re-run the failing gate. Two failed fix attempts = blocking issue.
2. **Integration verification:** read `~/.claude/skills/_components/integration-verification.md` and follow it (cross-lane integration, spec alignment, full-stack coverage for user-facing changes).
2b. **Symptom reproduction (SEAM B — MANDATORY for bug fixes; this repo has no MCP step).** Because this repo declares "No MCP integration test step," the bug-completion evidence bar is enforced HERE. Read `~/.claude/skills/_components/symptom-reproduction-gate.md`. A bug-fix part may not be reported complete without the REQUIRED rung: a **serving-path regression test** — a `/mstest`-run test on the symptom's *actual serving path* (a service/controller test exercising the real path the symptom is served through), verified RED→GREEN — **NOT** a unit test asserting on the fix's *internal target* (a stored value / facet / private helper). A `local-ui-tests` Selenium run or a `/write-manual-testing-doc` artifact observing the original symptom gone at the user surface is accepted as a STRONGER alternative. Bind the evidence to the SPEC's `## Reproduction Steps`. If only an internal-target unit test exists, the part is NOT complete — route a serving-path regression-test lane.
2c. **Pending runtime gates (feature parts — MANDATORY; this repo declares `MCP runtime: not-required`).** Read `~/.claude/skills/_components/pending-runtime-gates.md` and follow it. The flip to complete stays — but the completion OUTPUT contract changes: enumerate every unchecked `<!-- verification-only -->` / `**Runtime Verification**` row across the part's phases (count = N; N = 0 → no-op); write/update the `RUNTIME_GATES.md` ledger in the feature dir (columns: gate row text, how to run it, owning phase, date deferred — idempotent per plan, re-running replaces the plan's section); the completion report MUST LEAD with `N MANUAL RUNTIME GATES PENDING — feature not verified end-to-end` BEFORE any completion language (anti-pattern — 57077: "complete across all 5 phases" first, the unrun `:7775` manual rows a footnote, HTTP 500 found by the operator two days later); each affected phase status line gains `— RUNTIME GATES PENDING (N)`. Because this repo has no `/mcp-test` downstream owner, the report MUST state that the ledger is the ONLY owner of these rows.
3. **CLAUDE.md review:** read `~/.claude/skills/_components/claude-md-review.md` and follow it.
4. Leave everything uncommitted — the developer commits manually (repo policy).

---

## Blocking Issue Protocol

If a blocking issue is encountered:

1. **Stop all in-progress work.** Do not dispatch new agents.
2. Do NOT commit anything (repo policy) — leave the working tree as-is and describe its state precisely in the report.
3. **Print a blocking-issue report:** completed phases, blocked phase + reason, exact working-tree state (`git status --short` output), recovery suggestion, remaining phases not attempted.
4. **Do not work around the blocker.**

Blocking issues include: circular phase dependencies; a lane agent failing twice; a Tier 2
failure unfixable in two attempts; a typegen run that fails or produces irreconcilable diffs;
entry criteria referencing a feature/phase not in the input set; anything requiring architectural
decisions beyond the specs — plus any plan-specific triggers the plan's "Plan-specific execution
notes" section adds.

---

## Completion

When all phases in the plan part are complete and the Part Completion steps have passed:

Print a completion report: features/phases implemented, lane dispatch census (lane agents
dispatched, batches executed), Tier 2 gate result, files modified (grouped by lane),
Implementation Notes summary, and the reminder that the working tree is intentionally uncommitted
for manual review (`git status --short` snapshot).

---

## Append to Work Log (MANDATORY)

Read `~/.claude/skills/_components/work-log.md` and follow it. Call `work_log_append` with
`skill` (`execute-plan`), `project` (`cognito-forms`), `title`, `summary`, `files_modified`,
`branch`, and `technical_context`.
