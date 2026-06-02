---
kind: implementation-plan
feature_id: lazy-bug-family
status: Complete
created: 2026-06-01
phases: [1, 2, 3, 4, 5, 6]
---

> **Cross-repo plan** — authored 2026-06-01, brought to `Ready` from the `/crud-skill` Draft.
> To execute: `/execute-plan user/scripts/plans/lazy-bug-family.md`
> This plan is fully self-contained. The executing session needs no additional context.
> Tracking surface (checkbox persistence + Implementation Notes): `docs/specs/lazy-bug-family/PHASES.md`
> (in **claude-config**, relative to that repo root).

# Implementation Plan — Lazy-Bug Family

Clone the `/lazy` autonomous-pipeline infrastructure to operate against `docs/bugs/`,
standardizing the bug directory's frontmatter / plan structure / state-update protocol to match
`docs/features/`. Research/Gemini/stub steps are dropped (N/A to bugs); the terminal action is
**archive-on-fix** instead of mark-complete-in-place.

**PHASES.md (tracking surface):**
- `docs/specs/lazy-bug-family/PHASES.md` (claude-config, 6 phases) — the executor checks off
  deliverables here and writes Implementation Notes. **This plan body is read-only during
  execution** (frontmatter `status:` transitions only).

**Repos in scope:**
- `claude-config` — `/home/jacob/repos/claude-config` (Phases 1, 2, 4; Phase 6 partial)
- `AlgoBooth` — `/home/jacob/repos/AlgoBooth` (Phases 3, 5; Phase 6 partial)

**Total phases:** 6 (single feature, cross-repo)
**Plan version:** v1 (reference-based — components loaded from disk per step)

---

## EXECUTION MODEL — READ THIS FIRST

This plan uses an **orchestrator + Sonnet subagent** architecture:

| Role | What it does | Allowed tools |
|------|-------------|---------------|
| **Orchestrator (you)** | Read plan, compose Agent prompts, dispatch subagents, review output, run quality gates, update tracking docs (PHASES.md, CLAUDE.md), manage git per-repo | `Agent`, `Read`, `Bash` (gates/git only), `TaskCreate`/`TaskUpdate`, `Edit`/`Write` on PHASES.md + CLAUDE.md only |
| **Sonnet subagent** | Write ALL source and test code (`.py`, `.ts`, `.json`, `SKILL.md`, component `.md`, bug `SPEC.md`) | `Edit`, `Write`, `Read`, `Bash`, `Grep`, `Glob` |

**HARD CONSTRAINT:** You MUST NOT call `Edit` or `Write` on source or test files. If you are about
to modify a `.py`, `.ts`, `.tsx`, `.js`, `.json`, a `SKILL.md`, a `_components/*.md`, or a bug
`docs/bugs/**/SPEC.md` — STOP and compose an `Agent` tool call instead. The ONLY files you may
modify directly: the tracking **`PHASES.md`** (`docs/specs/lazy-bug-family/PHASES.md`), any
**`CLAUDE.md`** (Phase 6 doc rewrites land here — orchestrator-editable), `work-log.jsonl`, this
plan file's **frontmatter `status:` field only**, and task tracking.

**Dispatch pattern:** `Agent({ description: "...", model: "sonnet", prompt: "<FULL self-contained
context — subagent has zero prior context>" })`. Each subagent prompt MUST name the **absolute repo
root** it works in (`/home/jacob/repos/claude-config` or `/home/jacob/repos/AlgoBooth`) and include
the verbatim clause:

> **You do not run `git commit` or `git push`.** Staging (`git add`) is also reserved for the
> orchestrator. Your job ends after producing the `GROUND-TRUTH OUTPUT` block defined in your briefing.

---

## CROSS-REPO ROUTING (LOAD-BEARING)

This plan spans two git repos. Get the routing wrong and commits land in the wrong tree.

| Phase | Repo | Working root | Notes |
|-------|------|-------------|-------|
| 1 | claude-config | `/home/jacob/repos/claude-config` | `user/scripts/` — symlinked to `~/.claude/scripts`, so `--test` runs edited code live |
| 2 | claude-config | `/home/jacob/repos/claude-config` | `user/scripts/bug-state.py` (new) |
| 3 | AlgoBooth | `/home/jacob/repos/AlgoBooth` | `docs/bugs/**` migration + `queue.json` |
| 4 | claude-config | `/home/jacob/repos/claude-config` | `user/skills/lazy-bug{,-batch,-status}/` + `_components/mark-fixed-archive.md` (symlinked to `~/.claude/skills/_components/`) |
| 5 | AlgoBooth | `/home/jacob/repos/AlgoBooth` | `scripts/check-*-consistency.ts` + `package.json` qg wiring |
| 6 | both | both roots | `docs/bugs/CLAUDE.md` (AlgoBooth) + `user/scripts/CLAUDE.md` (claude-config) + dry run |

**Symlink fact (verified):** `~/.claude/scripts → claude-config/user/scripts`, and
`~/.claude/skills/_components/` resolves into claude-config. Editing files under
`claude-config/user/scripts/` is immediately visible at `~/.claude/scripts/`, so the workstation
runtime-verification commands (`python3 ~/.claude/scripts/...`) exercise the edited code with no
copy step. Use `git -C <root>` for all git operations so the orchestrator never relies on a
persisted `cd`.

**Branch policy (per repo):**
- **claude-config is currently on `main`** — the global rule is "if on the default branch, branch
  first." Before the first claude-config commit (Phase 1), create a working branch, e.g.
  `git -C /home/jacob/repos/claude-config switch -c feature/lazy-bug-family`. Commit per-phase on
  that branch. Do NOT commit to `main`. Do NOT push without explicit user permission.
- **AlgoBooth is on `chore/qg-wave1-green`**, which is unrelated to bug-pipeline work. Before the
  first AlgoBooth commit (Phase 3), create a dedicated branch, e.g.
  `git -C /home/jacob/repos/AlgoBooth switch -c feature/lazy-bug-pipeline`. Commit per-phase there.
  Do NOT push without explicit user permission.
- Phase 6 produces one commit in **each** repo (CLAUDE.md docs land per-repo).

---

## COMPONENT LOADING PROTOCOL

This plan references reusable component files by path instead of inlining their content. **Before
executing each step**, `Read` the component files listed for that step from disk. Do NOT proceed
from memory. After context compaction, re-read this plan file first, then load components for your
current step.

## Component Reference Card

| Step | Component | Path |
|------|-----------|------|
| Step 0 | Task Tracking | `~/.claude/skills/_components/task-tracking.md` |
| Step B.0 | Source Re-read | `~/.claude/skills/_components/source-reread.md` |
| Step B.1 | TDD Protocol | `~/.claude/skills/_components/tdd-protocol.md` |
| Step B.1 | Subagent Launch | `~/.claude/skills/_components/subagent-launch.md` |
| Step B.1 | Test Agent Briefing | `~/.claude/skills/_components/tdd-test-agent.md` |
| Step B.1 | Impl Agent Briefing | `~/.claude/skills/_components/implementation-agent.md` |
| Step B.2 | Subagent Review | `~/.claude/skills/_components/subagent-review.md` |
| Step B.2 | Mount-Site Verification | `~/.claude/skills/_components/mount-site-verification.md` |
| Step B.3 | PHASES.md Update | `~/.claude/skills/_components/phases-update.md` |
| Step B.4 | Quality Gates | `~/.claude/skills/_components/quality-gates.md` |
| Step B.5 | Commit Policy | `~/.claude/skills/_components/commit-and-push.md` |
| Phase 4 | Sentinel Frontmatter | `~/.claude/skills/_components/sentinel-frontmatter.md` |
| Phase 4 | Plan Frontmatter | `~/.claude/skills/_components/plan-frontmatter.md` |
| Phase 4 | MCP Coverage Audit | `~/.claude/skills/_components/mcp-coverage-audit.md` |
| Phase 4 | Completion Integrity Gate | `~/.claude/skills/_components/completion-integrity-gate.md` |
| Post-phase | Integration Verification | `~/.claude/skills/_components/integration-verification.md` |
| Post-phase | CLAUDE.md Review | `~/.claude/skills/_components/claude-md-review.md` |
| Final | Work Log | `~/.claude/skills/_components/work-log.md` |

---

## MANDATORY RULES — DO NOT SKIP ANY STEP

1. **ALL implementation and test-writing work MUST be delegated to Sonnet subagents** — the
   orchestrating session MUST NOT call `Edit`/`Write` on `.py`/`.ts`/`.json`/`SKILL.md`/
   `_components/*.md`/bug `SPEC.md`. The ONLY direct-edit exceptions: the tracking PHASES.md,
   `CLAUDE.md` files (Phase 6), `work-log.jsonl`, this plan's frontmatter `status:`, and task tracking.
2. All subagent edits happen in the current worktree of the correct repo — NEVER create worktrees.
   Always pass the absolute repo root in the subagent prompt.
3. **Code phases (1, 2, 5) follow strict TDD**: a dedicated test-agent writes failing tests first,
   then a dedicated impl-agent makes them pass. **Doc/migration/skill phases (3, 4) dispatch an
   authoring/impl-agent PLUS a verification-agent** that runs the phase's mechanical gate
   (`bug-state.py --test`, link-integrity check, `lint-skills.py`, `project-skills.py`) — the
   orchestrator does not author those files inline. This keeps `agents_dispatched_per_batch ≥ 2`.
4. **Phase 6 is the documented exception** to the ≥2-subagents rule: it produces only `CLAUDE.md`
   edits (orchestrator-editable) plus a dry run. It legitimately dispatches **zero** source
   subagents — this is NOT a contract violation. Record it explicitly in the dispatch census so
   `/lazy-batch-retro` does not flag a false positive.
5. PHASES.md (`docs/specs/lazy-bug-family/PHASES.md`) is updated AFTER EACH batch (not deferred).
6. Every subagent's output is reviewed for correctness and TDD discipline before continuing.
7. Mistakes are fixed immediately before launching the next batch.
8. After all batches in a phase finish, integration verification confirms the changes cohere.
9. Each completed phase is committed (per-repo, on the working branch) before the next phase begins.
   Do NOT push without explicit user permission.
10. This plan is self-contained — follow it exactly without relying on external context.
11. **Before each step, `Read` the component files listed for that step from disk** — do NOT rely on memory.
12. **Phase 1 is a zero-behavior-change refactor of the production `/lazy` pipeline.** The
    acceptance bar is `lazy-state.py --test` green AND a byte-identical JSON baseline diff. Any
    delta is a regression — treat it as a blocking issue, not an acceptable change.

---

## Embedded Spec Context (carried from the `/crud-skill` intake)

### Locked decisions

| Fork | Decision |
|------|----------|
| State engine | **Refactor shared core first** → `lazy_core.py` imported by both `lazy-state.py` and `bug-state.py`. |
| Pipeline fidelity | **Full apparatus, minus research** — PHASES + plans + sentinels + retro + MCP-validation + device-axis + receipt-gating + archive. |
| Variants | **Core trio** — `lazy-bug`, `lazy-bug-batch`, `lazy-bug-status`. |
| Ordering | **Hybrid** — `docs/bugs/queue.json` overrides, falling back to severity (P0→P1→P2→Low) then Discovered date for any open bug not listed. |
| Skill scope | **User-level** (`user/skills/`), mirroring `lazy`/`-batch`/`-status`. |
| Status vocab | **Bug-semantic**: `Open \| Investigating \| In-progress \| Fixed \| Won't-fix`. |

### Status → lifecycle mapping

| Bug Status | Pipeline meaning | Features analog |
|------------|------------------|-----------------|
| `Open` | SPEC exists, no investigation/plan yet | (Draft, pre-research) |
| `Investigating` | Root-cause analysis underway (INVESTIGATION.md) | Draft |
| `In-progress` | PHASES + plan authored; executing the fix | In-progress |
| `Fixed` | Receipt-gated terminal: `FIXED.md` present, archived | Complete |
| `Won't-fix` | Retired without fix; **receipt-exempt** | Superseded |

The first `**Status:**` line MUST be a **bare canonical token** (no trailing prose — the current
`cue-channel-audio-bleed/SPEC.md` violates this and will break `spec_status()`).

### Target per-bug lifecycle

```
SPEC (Open) → investigate → PHASES → plan → execute-plan (In-progress)
            → retro (RETRO_DONE.md) → MCP/test validation (VALIDATED.md / skip / device-defer)
            → __mark_fixed__  (FIXED.md receipt → Status: Fixed + Fixed:/Fix commit: →
                               git mv dir → _archive/ → repoint inbound refs → commit)
```

Differences from the feature pipeline: **No** Step 4.5 stub-spec, Step 4.6 realign, or Step 5
research gate. `__mark_complete__` → `__mark_fixed__` additionally performs the `git mv` to
`_archive/` and repoints inbound references per `docs/bugs/CLAUDE.md`. Receipt file is `FIXED.md`
(`kind: fixed`). Ordering is severity-driven (hybrid), not topo-ordered by deps.

---

## Execution Schedule

Phases are sequential per the dependency graph (Phase 1 blocks all; 2→{3,4}; 3→5; 6 last). Phases 3
and 4 are parallel-eligible after Phase 2 (different repos, no file overlap); the default schedule
runs them sequentially and the orchestrator MAY dispatch them concurrently if it has bandwidth.

| Step | Phase | Repo | Title | Blocked by | Parallel? |
|------|-------|------|-------|------------|-----------|
| 1 | P1 | claude-config | Shared core `lazy_core.py` (zero-behavior refactor) | — | Solo |
| 2 | P2 | claude-config | Bug state machine `bug-state.py` | P1 | Solo |
| 3 | P3 | AlgoBooth | Bug frontmatter standard + migration | P2 | May run with P4 |
| 4 | P4 | claude-config | The three skills (`lazy-bug{,-batch,-status}`) | P2 | May run with P3 |
| 5 | P5 | AlgoBooth | docs-consistency gate for bugs | P3 | Solo |
| 6 | P6 | both | Docs + end-to-end dry run | P1–P5 | Solo |

---

## Per-Phase Plans

### Phase: lazy-bug-family P1 — Shared core `lazy_core.py`

**Goal:** Extract domain-agnostic helpers from `lazy-state.py` into an importable `lazy_core.py`;
rewire `lazy-state.py` to import them; keep `--test` green with zero behavior change.

**Entry criteria:** None — first phase.

**Repo/root:** claude-config — `/home/jacob/repos/claude-config`.

**Batch overview:**

| Batch | Work Units | Parallel? | Notes |
|-------|-----------|-----------|-------|
| 1 | WU-1.1, WU-1.2 | Solo | Characterization baseline must land before the extraction |

#### WU-1.1: Capture characterization baseline (TDD: yes — test-agent)

- **Scope:** Lock current `/lazy` behavior before refactoring.
- **Files:** a baseline fixture/snapshot under `user/scripts/` (e.g. capture `python3 lazy-state.py`
  JSON for AlgoBooth + the full `--test` output) plus, if the suite lacks one, a characterization
  assertion that the post-refactor JSON is byte-identical to the captured baseline.
- **Test expectations:**
  1. `python3 lazy-state.py --test` currently exits 0 — capture the exact pass output.
  2. `python3 lazy-state.py --repo-root /home/jacob/repos/AlgoBooth` JSON is captured to a baseline
     artifact the impl-agent can diff against.
- **Dispatch:** test-agent. **Batch:** 1.

#### WU-1.2: Extract `lazy_core.py` + rewire `lazy-state.py` (TDD: yes — impl-agent)

- **Scope:** All Phase 1 PHASES.md deliverables.
- **Extract (domain-agnostic):** `_atomic_write`, `_die`, `_DIAGNOSTICS` + `_diag` +
  `clear_diagnostics()`, the parameterized `_state()` field-set builder; sentinel/plan parsing
  (`parse_sentinel`, `_parse_plan_frontmatter`, `_plan_status`, `_plan_lowest_phase`,
  `_plan_phase_set`, `_unchecked_wus_in_plan_scope`, `find_implementation_plans`,
  `find_retro_plans`, `latest_retro_plan`, `_has_any_complete_plan`,
  `retro_plan_has_significant_divergences`); PHASES analysis (`count_deliverables`,
  `remaining_unchecked_are_verification_only`, `_VERIFICATION_SECTION_RE`); receipts
  (`write_completed_receipt` generalized on `kind:`/filename, `has_completion_receipt`
  parameterized on receipt filename, `spec_status` generic `**Status:**` reader).
- **Keep in `lazy-state.py`:** research gates, `is_stub_spec`, dep-block/realign, cloud/device
  branches, `docs/features` queue loading, `ROADMAP.md` semantics, `enqueue_adhoc`,
  `backfill_receipts`, the smoke fixtures.
- **Files:** `user/scripts/lazy_core.py` (new, with module docstring); `user/scripts/lazy-state.py`
  (rewire to `import lazy_core`; core owns `_DIAGNOSTICS`; each `compute_state()` calls
  `clear_diagnostics()` at entry).
- **Verification:** `python3 lazy-state.py --test` exits 0 with zero fixture changes; baseline JSON
  diff from WU-1.1 is **empty**.
- **Risk:** module name must be underscore (`lazy_core`) and sit in the same dir so `import
  lazy_core` resolves under the `~/.claude/scripts` symlink.
- **Dispatch:** impl-agent. **Batch:** 1.

**Phase 1 quality gates:** `python3 user/scripts/lazy-state.py --test` (exit 0) + empty baseline
JSON diff. This IS the full gate for Phase 1 (Python pipeline, no `npm run qg`).

---

### Phase: lazy-bug-family P2 — Bug state machine `bug-state.py`

**Goal:** A `compute_state()` for the bug lifecycle emitting the same JSON contract, reusing
`lazy_core`, with in-file `--test` smoke fixtures.

**Entry criteria:** Phase 1 complete (`lazy_core.py` importable; `lazy-state.py --test` green).

**Repo/root:** claude-config.

**Batch overview:**

| Batch | Work Units | Parallel? | Notes |
|-------|-----------|-----------|-------|
| 1 | WU-2.1, WU-2.2 | Solo | Fixtures (failing) before the state machine |

#### WU-2.1: In-file smoke fixtures (TDD: yes — test-agent)

- **Scope:** The `--test` fixture suite for `bug-state.py`, written to fail until WU-2.2 lands.
- **Test expectations:** fixtures covering fresh-open-bug, blocked, mid-fix,
  phases-complete-no-retro, retro-done-needs-mcp, ready-to-mark-fixed, device-deferred,
  hybrid-ordering (queue + unlisted severity fallback), won't-fix-exempt, fixed-no-receipt-halt.
- **Dispatch:** test-agent. **Batch:** 1.

#### WU-2.2: Implement `bug-state.py` (TDD: yes — impl-agent)

- **Scope:** All Phase 2 PHASES.md deliverables — `load_bug_queue`, `bug_severity`,
  `bug_discovered`, the state machine steps, completion semantics (`Fixed`/`Won't-fix` + receipt),
  terminals, `--backfill-receipts`, CLI parity (`--cloud`/`--real-device`/`--repo-root`/`--test`).
- **Files:** `user/scripts/bug-state.py` (new), importing `lazy_core`.
- **Verification:** `python3 bug-state.py --test` exits 0 (all WU-2.1 fixtures green).
- **Dispatch:** impl-agent. **Batch:** 1.

**Phase 2 quality gates:** `python3 user/scripts/bug-state.py --test` (exit 0) AND
`python3 user/scripts/lazy-state.py --test` still green (regression guard — shared `lazy_core`).

---

### Phase: lazy-bug-family P3 — Bug frontmatter standard + migration

**Goal:** Bring `docs/bugs/` SPECs and queue up to the machine-parseable standard.

**Entry criteria:** Phase 2 complete (`bug-state.py --backfill-receipts` available).

**Repo/root:** AlgoBooth — `/home/jacob/repos/AlgoBooth`.

**Batch overview:**

| Batch | Work Units | Parallel? | Notes |
|-------|-----------|-----------|-------|
| 1 | WU-3.1, WU-3.2 | Solo | Migrate + verify; receipts backfill is mechanical |

#### WU-3.1: Migrate headers + create `queue.json` + backfill receipts (impl-agent)

- **Scope:** Phase 3 deliverables 1–4.
- **Files:** `docs/bugs/queue.json` (new, hybrid seed from the 10 open bugs — explicit ordering
  only where it matters); the **10 open** bug `SPEC.md` headers normalized (bare `**Status:**`
  token; prose moved to a `>` description/note line — fixes `cue-channel-audio-bleed` et al.);
  canonical header documented inline in `docs/bugs/CLAUDE.md` (Phase 6 finalizes prose). Run
  `python3 ~/.claude/scripts/bug-state.py --repo-root /home/jacob/repos/AlgoBooth
  --backfill-receipts` to write `FIXED.md` for the 27 archived bugs.
- **Dispatch:** impl-agent. **Batch:** 1.

#### WU-3.2: Migration verification (verification-agent)

- **Scope:** Phase 3 deliverable 5 + runtime verification.
- **Test expectations:** `bug-state.py --repo-root <AlgoBooth>` parses every migrated SPEC header
  with zero diagnostics warnings; no bug-internal relative link is broken (root-relative path rule);
  all 27 archived bugs now carry a `FIXED.md`.
- **Dispatch:** verification-agent (writes/runs the parse + link-integrity check). **Batch:** 1.

**Phase 3 quality gates:** `bug-state.py --repo-root <AlgoBooth>` clean parse + link-integrity check
green. (The mechanical `npm run qg:bugs-consistency` gate arrives in Phase 5.)

---

### Phase: lazy-bug-family P4 — The three skills

**Goal:** Thin wrappers mirroring `lazy`/`-batch`/`-status`, dispatching against `bug-state.py`.

**Entry criteria:** Phase 2 complete.

**Repo/root:** claude-config.

**Batch overview:**

| Batch | Work Units | Parallel? | Notes |
|-------|-----------|-----------|-------|
| 1 | WU-4.1, WU-4.2 | Solo | Author skills + component, then lint/project |

#### WU-4.1: Author the three skills + `mark-fixed-archive.md` component (impl-agent)

- **Scope:** Phase 4 deliverables 1–5.
- **Files:** `user/skills/lazy-bug/SKILL.md` (mirror of `lazy` — one sub-skill per invocation,
  `__mark_fixed__` special action, status bookends, work-log); `user/skills/lazy-bug-batch/SKILL.md`
  (mirror of `lazy-batch`); `user/skills/lazy-bug-status/SKILL.md` (mirror of `lazy-status`,
  read-only); a new `_components/mark-fixed-archive.md` (the `git mv` to `_archive/` + inbound-ref
  repoint). Reuse `sentinel-frontmatter.md`, `mcp-coverage-audit.md`,
  `completion-integrity-gate.md` by reference where they generalize; decompose any shared block per
  /crud-skill Step 6. All three carry frontmatter `plan-mode: never`.
- **Reference reading (subagent prompt must include):** the existing `user/skills/lazy/SKILL.md`,
  `lazy-batch/SKILL.md`, `lazy-status/SKILL.md` as the templates to mirror.
- **Dispatch:** impl-agent. **Batch:** 1.

#### WU-4.2: Skill lint + projection (verification-agent)

- **Scope:** Phase 4 deliverable 6 + runtime verification.
- **Test expectations:** `python3 ~/.claude/scripts/lint-skills.py` exits 0; `project-skills.py`
  resolves the three skills with no circular includes; capability lint clean.
- **Dispatch:** verification-agent. **Batch:** 1.

**Phase 4 quality gates:** `lint-skills.py` exit 0 + `project-skills.py` clean projection.

---

### Phase: lazy-bug-family P5 — docs-consistency gate for bugs

**Goal:** Mechanically enforce the bug contracts the way features are enforced.

**Entry criteria:** Phase 3 complete (gate validates the migrated standard).

**Repo/root:** AlgoBooth.

**Batch overview:**

| Batch | Work Units | Parallel? | Notes |
|-------|-----------|-----------|-------|
| 1 | WU-5.1, WU-5.2 | Solo | Failing checker tests, then the checker + qg wiring |

#### WU-5.1: Checker tests (TDD: yes — test-agent)

- **Scope:** Failing tests for the bug-consistency checks.
- **Test expectations:** assertions for bug SPEC frontmatter (canonical Status/Severity),
  `docs/bugs/queue.json` schema, bug sentinel/plan frontmatter, `fixed-requires-receipt`, and
  archive-coherence (`Fixed` ⇒ under `_archive/`). Use fixtures or a temp tree so the test does not
  depend on the live `docs/bugs/` passing yet.
- **Dispatch:** test-agent. **Batch:** 1.

#### WU-5.2: Implement the checker + wire `npm run qg` (TDD: yes — impl-agent)

- **Scope:** Phase 5 deliverables 1–3.
- **Files:** extend `scripts/check-docs-consistency.ts` OR add sibling
  `scripts/check-bugs-consistency.ts`; wire a `qg:bugs-consistency` script (or fold into
  `qg:docs-consistency`) in `package.json`.
- **Verification:** WU-5.1 tests green; `npm run qg:bugs-consistency` (or folded) exits 0 against
  the migrated tree from Phase 3.
- **Dispatch:** impl-agent. **Batch:** 1.

**Phase 5 quality gates:** `npm run qg -- ts` (checker is TypeScript) + `npm run qg:bugs-consistency`
(or folded gate) exit 0. If the checker introduces a new vitest alias or shared import, run full
`npm run qg`.

---

### Phase: lazy-bug-family P6 — Docs + end-to-end dry run

**Goal:** Finalize documentation and prove the loop end-to-end. **Orchestrator-driven** (CLAUDE.md
edits + dry run). Per MANDATORY RULE 4, this phase may dispatch **zero** source subagents — record
that in the census; it is not a violation.

**Entry criteria:** Phases 1–5 complete.

**Repo/root:** both — one commit per repo.

**Deliverables (orchestrator edits CLAUDE.md directly):**
- Rewrite `docs/bugs/CLAUDE.md` (AlgoBooth) to mirror `docs/features/CLAUDE.md` (lifecycle, sentinel
  table, receipt-gating, plan schema, archive protocol).
- Update `user/scripts/CLAUDE.md` (claude-config) to drop the "(planned)" markers on
  `lazy_core.py` / `bug-state.py` and document the lazy-bug family as shipped.
- Dry-run `/lazy-bug-status`, then a single `/lazy-bug` cycle against a real open bug; confirm the
  dispatch + sentinel writes are correct. (If the dry run would mutate a real bug irreversibly,
  capture the intended dispatch/sentinel output and stop short of the archive `git mv`.)
- `interview_work_log_append` for the build (also covered by the plan's Work Log step).

**Phase 6 quality gates:** re-run `lazy-state.py --test` + `bug-state.py --test` (both green) and
`npm run qg:bugs-consistency` (green) as the final cross-cutting check.

---

## Execution Protocol

This protocol governs autonomous execution of every phase. Follow it exactly.

### Phase Selection Loop

Repeat until all 6 phases are complete or a blocking issue triggers early exit:

1. **Select ready phase(s):** entry criteria satisfied (prerequisite phases' deliverables checked
   off in PHASES.md). P3 and P4 are parallel-eligible after P2. If no phase is ready, jump to the
   Blocking Issue Protocol.
2. **Announce:** Print "Implementing lazy-bug-family Phase N: [title] (repo: <repo>)".
3. **Review prior context:** Re-read previously completed phases' Implementation Notes in
   `docs/specs/lazy-bug-family/PHASES.md`. They take priority over this plan where they diverge.
4. **Execute all batches** per the Per-Batch Steps below.
5. **Run Post-Phase Steps** below.
6. **Report:** Print "lazy-bug-family Phase N: [title] — committed as [hash] in <repo>".
7. **Loop:** Re-evaluate readiness. Return to step 1.

### Step 0: Initialize Task Tracking (MANDATORY PREREQUISITE)

Read `~/.claude/skills/_components/task-tracking.md` and follow it. Create one task per Work Unit
defined above. If `TaskCreate`/`TaskUpdate`/`TaskList` are unavailable, proceed without tracking and
note the omission in the Work Log.

### Per-Batch Steps

#### Step B.0: Re-read Source Documents (MANDATORY)

Read `~/.claude/skills/_components/source-reread.md`. Re-read from disk: this plan file,
`docs/specs/lazy-bug-family/PHASES.md` (current phase + prior Implementation Notes), and the live
files the batch touches. Do NOT rely on remembered content.

#### Step B.1: Launch Subagents (COMPOSE Agent TOOL CALLS — ZERO INLINE IMPLEMENTATION)

**PRE-FLIGHT:** confirm (1) you will use `Agent` with `model: "sonnet"` for ALL source/test changes,
(2) you will NOT `Edit`/`Write` source/test files. Read `tdd-protocol.md`, `subagent-launch.md`,
`tdd-test-agent.md`, `implementation-agent.md`. Per MANDATORY RULE 3, dispatch test-agent → impl-agent
for code phases (1, 2, 5) and impl/authoring-agent + verification-agent for doc/skill/migration
phases (3, 4). Phase 6 dispatches no source subagents (RULE 4). Every subagent prompt names the
absolute repo root and includes the no-commit/no-stage clause.

**POST-DISPATCH GATE:** verify you composed `Agent` calls and did not edit source/test files
directly. If violated, revert inline edits and re-dispatch.

#### Step B.2: Review Batch Output (MANDATORY GATE)

Read `~/.claude/skills/_components/subagent-review.md` and `mount-site-verification.md`. Re-run each
subagent's pasted commands and diff against the paste; verify mount sites for new files; produce a
PASS / PASS-WITH-FIXES / NEEDS-REWORK verdict before proceeding.

#### Step B.3: Update PHASES.md (MANDATORY)

Read `~/.claude/skills/_components/phases-update.md`. In `docs/specs/lazy-bug-family/PHASES.md`,
check off completed deliverables and append an Implementation Notes block (date, work completed,
integration notes, pitfalls, files modified). Re-read PHASES.md to verify the write landed. This is
a blocking gate — do not proceed until verified.

#### Step B.4: Run Quality Gates (MANDATORY)

Read `~/.claude/skills/_components/quality-gates.md`. Run the phase's gate from its "Phase N quality
gates" line:
- Phase 1/2/6 Python: `python3 user/scripts/lazy-state.py --test` and/or
  `python3 user/scripts/bug-state.py --test` (run from claude-config root).
- Phase 3: `bug-state.py --repo-root <AlgoBooth>` clean parse + link check.
- Phase 4: `lint-skills.py` + `project-skills.py`.
- Phase 5: `npm run qg -- ts` + `npm run qg:bugs-consistency` (full `npm run qg` if a vitest alias
  or shared import was introduced).
100% pass required before Step B.5.

#### Step B.5: Commit Batch (per-repo)

Read `~/.claude/skills/_components/commit-and-push.md`. Commit with `git -C <repo-root>` on the
repo's working branch (create the branch first per the Branch policy if this is the repo's first
commit). **Do NOT push without explicit user permission.** Commit message scope: `feat(lazy-bug):`
or `chore(lazy-bug):` as appropriate.

#### Step B.6: Proceed to Next Batch

**Checklist (all must be true):** review verdict produced · PHASES.md updated + verified · quality
gates pass · batch committed. If any is unchecked, complete it before the next batch.

### Post-Phase Steps (after all batches in a phase)

#### Integration Verification (MANDATORY)

Read `~/.claude/skills/_components/integration-verification.md`. Confirm cross-agent integration and
that the phase's runtime-verification line in PHASES.md holds.

#### Update CLAUDE.md Files (MANDATORY consideration)

Read `~/.claude/skills/_components/claude-md-review.md`. Phase 6 owns the major CLAUDE.md rewrites;
earlier phases update CLAUDE.md only if a new invariant warrants it.

#### Commit and Push Post-Phase Changes

Commit per-repo on the working branch. Push only with explicit user permission.

---

## Blocking Issue Protocol

If a blocking issue is encountered at any point:

1. **Stop all in-progress work.** Do not launch new subagents.
2. **Flip this plan's frontmatter `status: Ready` → `status: In-progress`** (one-line edit), so the
   next `/execute-plan` run resumes from the first unchecked WU.
3. **Commit any completed phases** (per-repo) including the status flip.
4. **Print a blocking-issue report** (completed phases + hashes, blocked phase, reason, recovery
   suggestion, remaining phases).
5. **Write `BLOCKED.md`** to `docs/specs/lazy-bug-family/` with the same content.
6. **Do not work around the blocker.** The user provides a resolution and re-triggers execution.

Blocking issues include: a Phase 1 JSON baseline delta that can't be reconciled (zero-behavior-change
contract broken); a subagent failure unfixable after 2 retries; a quality-gate failure unfixable
after 2 retries; a git conflict unresolvable by rebase; or any decision requiring scope beyond this
plan.

---

## Completion

When all 6 phases are complete:

1. **Run the final cross-cutting gate:** `lazy-state.py --test` + `bug-state.py --test` (both green)
   + `npm run qg:bugs-consistency` (green).
2. **Print a completion report:** features implemented (lazy-bug-family), phases completed (6),
   per-repo commit log table (commit · repo · phase · title), and an Implementation Notes summary.
3. **Flip this plan's frontmatter to `status: Complete`** (one-line edit) and stage it in the final
   commit. The plan file STAYS in `plans/` — Complete is the audit trail, not a deletion signal.

---

## Append to Work Log (MANDATORY — DO NOT SKIP)

Read `~/.claude/skills/_components/work-log.md`. Call `interview_work_log_append` with:

- `skill`: `"execute-plan"`
- `project`: `"claude-config"` (cross-repo build; note AlgoBooth in `technical_context`)
- `title`: "Lazy-Bug autonomous pipeline — clone of /lazy family for docs/bugs"
- `summary`: 2–4 sentences on the shared-core extraction, the bug state machine, the migration, and
  the three skills.
- `files_modified`: all files touched across both repos.
- `branch`: the claude-config working branch (note the AlgoBooth branch in `technical_context`).
- `commit`: HEAD short sha (claude-config).
- `phases_md`: `docs/specs/lazy-bug-family/PHASES.md`
- `technologies`: `["Python", "TypeScript", "Markdown", "Claude Code skills"]`
- `patterns`: `["shared-core-extraction", "state-machine", "receipt-gating", "hybrid-ordering",
  "archive-on-fix", "characterization-test"]`
- `technical_context`: 3–5 sentences on the cross-repo split (claude-config tooling + AlgoBooth
  docs/bugs migration), the zero-behavior-change refactor risk on the production `/lazy` pipeline,
  and the receipt-gated archive-on-fix terminal that differs from the feature pipeline's
  mark-complete-in-place.

If `interview_work_log_append` is unavailable, skip with a note in the completion report.

---

## §Plan Notes

- **Phase 1 is the highest-risk step:** it mutates the live `/lazy` features pipeline. The WU-1.1
  characterization baseline + byte-identical JSON diff is the safety net — do not skip it, and treat
  any diff as a blocker.
- **Symlink awareness:** `~/.claude/scripts → claude-config/user/scripts`, so workstation
  runtime-verification commands exercise edited code directly. Edit only in the claude-config tree.
- **Cross-repo commits:** always `git -C <root>`; never rely on a persisted `cd`. claude-config must
  be branched off `main` before its first commit; AlgoBooth must be branched off
  `chore/qg-wave1-green` before its first commit. No pushes without explicit user permission.
- **`docs/bugs/` counts at authoring time:** 10 open bug dirs, 27 archived — these are the migration
  targets for Phase 3. If the counts drift before execution, re-derive from
  `find docs/bugs -maxdepth 1 -mindepth 1 -type d ! -name _archive`.
