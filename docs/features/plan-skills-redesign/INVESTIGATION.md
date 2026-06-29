# Investigation — `/write-plan` + `/execute-plan` Redesign (Cognito Forms)

**Status:** Investigation complete — ready for `/spec`
**Date:** 2026-06-29
**Author:** session-mining investigation (5 parallel mining agents over Claude Code session history)
**Scope:** Redesign the plan-generation/execution skill pair (`/write-plan`, `/execute-plan`) for Cognito Forms. Cross-repo improvements noted where general. Skills are authored in `claude-config` (`user/skills/{write-plan,execute-plan}/` and `repos/cognito-forms/.claude/skills/write-plan/`).

> This doc is the evidence base for `/spec`. It records *what is*, with citations, plus recommended scope directions. `/spec` should formalize requirements; treat the recommendations here as inputs, not decisions.

---

## 1. Motivation (user-stated problems)

1. **Plan-load context bloat.** Invoking `/execute-plan` in a fresh session fills the window to ~120K (~85%) before any work begins.
2. **Compaction during execution.** Plans are huge, so compaction is near-guaranteed mid-execution. The Tasks tool is intended to mitigate post-compaction drift; it *feels* like it works — verify.
3. **Build/test serialization not exploited.** Both skills were designed *before* the machine-global build/test queue (`/msbuild`, `/mstest`, `/nxbuild`, `/nxtest` → `~/.claude/scripts/build-queue.ps1`; raw `dotnet`/`npx nx` blocked by a PreToolUse hook since 2026-06-24). Since builds serialize anyway, can more work parallelize?
4. (User refinements during investigation) Boilerplate (e.g. subagent execution policy) should live in the *skills*, not be baked into plan files. PHASES.md grows with implementation and is itself a load problem.

---

## 2. Method & corpus

- **Source:** Claude Code transcripts at `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`. Cognito Forms spans multiple project dirs (main `…-Cognito-Forms` + worktree siblings `…-B`, `…-C`, `…-D`, plus feature worktrees and `…-Cognito-Web-Client`).
- **Subagent transcripts** live in `…/<parent-session-uuid>/subagents/agent-<id>.jsonl` (NOT inline `isSidechain` in this setup). The first-pass digest missed these; the build-serialization analysis used them (163 subagent transcripts — where the actual builds/edits happen).
- **Corpus:** 77 plan-bearing sessions (130 MB). 26 `/write-plan`, 56 `/execute-plan` invocations (via `<command-name>` markers); 3 `/write-plan-cloud`.
- **Tooling (persisted):** the `mine-sessions` skill (`claude-config/user/skills/mine-sessions/`) with `digest_sessions.py` (quantitative per-session signals; `--include-subagents`, `active_min` gap-filtering) and `render_session.py` (readable per-turn linearization with `ctx=` token footprint + `<<COMPACTION/HUMAN/TOOL_ERROR>>` markers). Built during this investigation; reusable for follow-ups.
- **Five parallel mining agents:** plan-load composition; compaction/Tasks resilience; build serialization/parallelization; rework/review-gate loops; write-plan authoring friction.

**Caveat on metrics:** `duration_min` is raw first→last wall-clock and includes overnight idle (e.g. a "1528 min" write-plan session = ~124 min real work). Use `active_min` (gaps >30 min filtered). The raw `needs_rework` count (literal string "NEEDS-REWORK") is ~95% template noise — the review component lists it as a verdict option ~5×/batch. Count only confirmed `**Verdict:** NEEDS-REWORK` lines.

---

## 3. Findings

### 3.1 🔴 Skill-name collision — wrong `/write-plan` runs (highest impact)

The **generic** user-level `/write-plan` (`claude-config/user/skills/write-plan/SKILL.md`) is what actually executed in the mined Cognito sessions — **not** the Cognito lane-based variant (`claude-config/repos/cognito-forms/.claude/skills/write-plan/SKILL.md`) that the skill catalog advertises.

- Evidence: every target write-plan session loads generic-only markers — `8-WU cap`, `complexity: mechanical|complex` frontmatter, `[VERIFY:]` Step 3.5, separate **test-agent + impl-agent** TDD pipeline — plus personal-project residue (`/lazy-batch Step 9`, Tauri, MCP-validation). The lane variant's signatures (`Lane partitioning`, `cognito-lanes-v1`, `lane-agent-briefing`, `orchestrator + Sonnet lane-agent`, typegen seam, tiered gates) appear in **zero** target sessions. Generated plans say "orchestrator + Sonnet **subagent**" (generic), never "lane-agent".
- The catalog/menu *describes* the Cognito variant (`918ae3e6` #1: "lane-based … backend/frontend lanes, tiered gates, typegen seam"), so the model is told it has the lane planner and handed the generic one.
- The lane variant **does** run in some other worktrees (`9fc3870e`, `dcdaf9f4`, `fe381719`, `f2f25019` reference `lane-agent-briefing`) → **resolution is nondeterministic / cwd-/worktree-dependent**. Leading hypothesis: repo-scoped `.claude/skills/` is symlinked into the main worktree but not all sibling worktrees, so user-level generic wins there. **Verify this first in `/spec`.**
- **Consequence:** plans authored as per-deliverable TDD micro-units with **no typegen seam and no tiered gates** — forfeiting exactly the slow-build savings the Cognito lane variant exists to capture. The micro-unit decomposition (test-agent + impl-agent + review *triple per WU*, e.g. `wp_31d2` #162–183) multiplies build/test cycles — the dominant cost in this repo.

### 3.2 Plan-load context composition (~116K plateau, before work begins)

Measured climb (session `0090b4d3`, representative; `usage` = input+cache_read+cache_creation):

| Turn | Action | ctx | Δ |
|---|---|---|---|
| #5 | baseline after skill load | 67,939 | — |
| #9 | after Read plan file | 87,755 | +19.8K |
| #13 | after Read PHASES.md | 103,188 | +15.4K |
| #17 | after Read SPEC.md | 111,711 | +8.5K |
| #23 | after ToolSearch + git | 115,802 | +4.1K |

First-assistant-turn footprint across all 56 execute sessions: **median 65.6K, range 53–84K** — i.e. ~1/3 of the window is gone *before the plan is read*. Composition of the ~116K plateau:

| Bucket | ~Tokens | Notes |
|---|---|---|
| Fixed harness + MCP/tool schemas | **~43K** | github, Slack, Notion, work-logging, tree-sitter, context7 + agent-type catalog. Largest fixed cost; hardest to cut (needs MCP scoping per session). |
| `/execute-plan` skill body | **~13K** | Source SKILL.md ~9.3K tok + eagerly `!cat`-inlined `subagent-review.md` (~2.8K). ~2.3K is dead cloud/`--batch`/lazy-batch/Tauri/MCP-validation logic irrelevant to a human-invoked local Cognito run. |
| Nested CLAUDE.md / AGENTS.md injections | ~9.3K | workspace CLAUDE.md 2.5K + AGENTS.md 1.8K + CLAUDE.local.md 4.0K + Web.Client CLAUDE.local.md 0.8K + .claude/CLAUDE.md 0.16K. |
| **Plan + PHASES.md + SPEC.md read in full** | **~46K** | Biggest single lever. PHASES.md alone ≈29K on disk; SPEC.md ≈6.6K; plan content ≈10.8K. |

Runtime component loads add ~7.5K more (6–8 `_components/*.md` Read during execution; some re-Read up to 4× across batches — no caching).

### 3.3 Plan-file anatomy — ~32–44% boilerplate that duplicates the skill

- 60 on-disk plans: **avg 340 lines, median 334, max 873** (`person-entry-details-refactoring.md`).
- Mandated-verbatim boilerplate = **~32% (plan-load agent) to ~44% median, 45–62% common** (write-plan agent's per-file measure): EXECUTION MODEL table, COMPONENT LOADING PROTOCOL, Component Reference Card, MANDATORY RULES 1–11, Execution Protocol (Phase Selection Loop + Per-Batch Steps B.0–B.6), Blocking Issue Protocol, Completion, Work Log. ~150–190 verbatim lines per plan.
- This **restates rules the `/execute-plan` skill already holds in the same context** — the plan's "EXECUTION MODEL", "COMPONENT LOADING PROTOCOL", "Blocking Issue Protocol", "Completion" are near-verbatim of skill-body sections (SKILL.md L42–48, Step 3, Step 4). Net redundant overlap ≈3–3.5K tok/plan, on top of an already-resident skill.
- Self-defeating: the v2 rule says components are *referenced by path and read from disk*, yet the skill still mandates inlining ~150 lines of prose that mostly tell the executor to go read those components.
- **Policy is dual-sourced:** fixing an execution-policy bug means editing the skill *and* regenerating every plan.

### 3.4 PHASES.md growth — compounding, re-paid many times

- Largest startup document (~29K / 540 lines for the cognito-pay feature) and **grows monotonically**: `/execute-plan` appends an Implementation Notes block (date, work done, integration notes, pitfalls, files) after every batch. A late-feature plan-part reads a PHASES.md fat with all earlier phases' prose.
- The skill mandates re-reading PHASES.md **in full** at startup, on every `source-reread` (per batch), and on every compaction recovery → with ~2 compactions/session + per-batch re-reads, a 29K file is paid **5–10× per session**.

### 3.5 Compaction & Tasks resilience (hypothesis: half-confirmed)

- **Compaction is near-guaranteed:** 56/56 execute sessions compacted. Peaks 250–416K (highest `918a` 416K). Resets per session 1–5. Bimodal trigger: many at ~180–240K from manual `/compact`; some run to 350–416K before auto-compaction.
- **Post-compaction floor ~55–74K** — the injected summary + full skill re-injection + components. This large floor shortens each sawtooth tooth and *forces more frequent compaction*.
- **Drift the skill fears did not materialize:** across 7 deep-read sessions, **0 cases** of re-executing completed work, re-dispatching a finished WU, or mis-identifying resume position. Recovery clean ~7/7 for real mid-execution resumes.
- **Tasks works but is not load-bearing.** Created one-per-WU at Step 0, kept current (often per-batch-step granularity; TaskCreate/TaskUpdate counts confirm upkeep — e.g. `d74e` 23/33, `3880` 15/29). It's one of **four redundant anchors**: Tasks, compaction-summary prose, PHASES.md, `git status`.
  - **Strongest pro-evidence:** `3880` #300–311 — a true terminal-close with no compaction summary; `TaskList` + `git status` were the only anchors and pinpointed `#8 in_progress` for a flawless resume.
  - **Caveat:** two sessions (`9a64`, `918a`) never called `TaskList` at all yet recovered cleanly off summary + PHASES.md. The protocol's "TaskList-first" step is not reliably honored — got lucky on good summaries. A no-summary recovery that *also* skips TaskList would fly blind.
  - **No stale/misleading Tasks** found.
- PHASES.md is a co-equal, load-bearing anchor; no case where a lost PHASES.md update broke recovery (redundancy saved it).
- What grows the orchestrator's context: primarily **subagent result payloads** (GROUND-TRUTH reports 1–4K each) and **re-reads of plan/PHASES.md/components** at every batch boundary — not gate output (auto-backgrounded) and not raw file reads (delegated to subagents).

### 3.6 Build/test serialization & parallelization (biggest actionable win)

- **Real agent parallelism ≈ zero.** Across all 8 heavy sessions, every `Agent` dispatch is **batch-size 1** (one tool_use per assistant message). The orchestrator *narrates* parallelism ("Launching Wave 1 — WU-2 + WU-1 in parallel", `9a64`) but emits them in **separate turns** (#72/#73 with #74 = WU-2's result) → the harness runs them **sequentially**. The harness only parallelizes `Agent` blocks in the *same* message. Timestamps confirm 15–20 min serial gaps.
- **Block-hook friction is a red herring.** 537 raw `dotnet`/`nx` build/test calls live in subagents (102 in orchestrators); only **~19 were ever denied** — the rest predate the 2026-06-24 enforce hook and ran off-queue historically. Post-cutover, dispatch prompts teach the queue skills and compliance is essentially total (0 raw in clean post-hook sessions). Recovery from a deny ≈1 turn (the deny text carries the corrected command).
- **Queue contention is cheap.** Of 272 measured queue invocations, only 31 (11%) saw position >1; contention adds ~28s mean to those. Median build 74s either way. The dominant cost is build *frequency × synchronicity* (~270 builds × 74s ≈ 5–6 h serialized), not waiting in line.
- **Right-sizing largely solved post-cutover.** Full:incremental = 42:69; newest sessions honor "full once per plan-part" (`9a64` 0 full/21 proj/22 mstest). Outliers: `5b7c215e` 15 full + 0 incremental (06-23, pre-right-sizing); `9c72334a` 8 full/0 proj. Typegen seam (orchestrator-owned incremental `Cognito.Services` build + `-UpdateInPlace`) used in 13 sessions, working as designed.
- **Background builds: 2.6% of invocations** (`run_in_background` gated on a >10-min heuristic that incremental builds never trip). The synchronous wrapper freezes the orchestrator's whole turn (~74s median, max 540s).
- **The fix is two orchestrator-contract changes, not queue changes:** (a) emit multi-agent batches in **one** message (disjoint-file WUs are already guaranteed safe by the file-overlap rule); (b) background long/Tier-2/typegen builds and dispatch the next independent agent while they run. Builds stay a serial spine, but agent think/edit/test-author time (the 15–20 min gaps) is fully parallelizable. Realistic ~1.5–2× wall-clock per phase; ~2× on a true Parallel BE+FE phase.

### 3.7 Rework & review-gate cost (mostly healthy; one cost to trim)

- **Real rework rate ≈ 1 NEEDS-REWORK per ~16 batches.** Across 8 sessions: ~16 PASS, ~2 PASS-WITH-FIXES (both cosmetic), **1 NEEDS-REWORK** (`052d` Phase 3 — pre-existing tests encoded old buggy behavior with invalid token IDs; caught by assertion-vs-intent read, fixed in one re-dispatch). Genuine fix re-dispatches: 2 total. No 2+-rework loop; the "two failures = blocking" rule never fired; no `BLOCKED.md` written.
- **Ground-truth gate: partly justified.** Cost: orchestrator re-runs `git status`/`wc -l`/`grep -n` + **the full test suite** per WU (Bash GT re-runs per session: `4c01` 72, `3880` 39, `052d` 28…). A dispatched review consumes ~50–70K subagent tokens (`09c2` review = 69,758). **It caught 0 falsified reports in ~16 batches** — Sonnet was honest about test counts. Its real value was forcing the *assertion-vs-intent read* (the only mechanism that caught the one defect). **Recommendation:** keep the substantive read; replace the mandatory full-suite re-run with cheap integrity checks (`git status`/`wc -l`/`grep -n`), re-running tests only on mismatch.
- **Review mechanism is healthy:** hybrid scope-gated (small batches inline, larger via review subagent at orchestrator's model — `3306` used Opus), thorough not rubber-stamped.
- **Infra friction:** `3880` burned ~16 min retrying a review-subagent dispatch 4× on API 529 before falling back to inline. Add a 1–2-strike inline-fallback fast-path.

### 3.8 Write-plan authoring — healthy parts (keep)

- **Partitioning: no churn.** WU count + part split decided in one pass every time; parts well-balanced; cap-driven splits only when warranted (`ddca4953` 12 WUs → 2 balanced parts with `Plan series`).
- **Pre-draft gates earn their cost.** Dirty-tree check made the right call each time (honored work-repo manual-git policy). Touchpoint audit + `[VERIFY:]` anchor-existence (Step 3.5) caught **genuine phantom anchors** (`ce62dce3`: `StampCustomerEntryIdAsync` did NOT exist on-branch — an Explore agent had read an unmerged stacked branch; also corrected wrong entity grounding `Order`→`CognitoOrder`; `47ff3aff`: two anchors corrected before shipping `Ready`). These prevented execute-time rework.
- **No unwarranted halts.** No write-plan portion wrote `NEEDS_INPUT.md`; AskUserQuestion calls belonged to preceding `/spec-*` phases or were user-requested. Auto-accept of mechanical choices held.
- **Pre-dispatch drift reconciliation** (execute-side) front-loaded anchor verification (`4c01` #301/#373/#445/#460) — why anchor-drift rework was zero. Cheap insurance; keep.

---

## 4. What is healthy — do NOT regress in the redesign

Partitioning logic; pre-draft anchor/touchpoint `[VERIFY:]` gates; dirty-tree handling; pre-dispatch drift reconciliation; Tasks-based recovery (keep as one anchor); the typegen seam (when the lane variant runs); right-sized builds ("full once per plan-part").

---

## 5. Recommended scope directions for `/spec` (inputs, not decisions)

Ranked by impact:

1. **Resolve the skill collision (3.1).** Make `/write-plan` deterministically resolve to the Cognito lane variant in this repo and all worktrees (verify worktree-symlink coverage; consider renaming generic to `/write-plan-generic` or repo-shadowing by name). Strip Tauri/MCP/lazy-batch residue from whatever runs in Cognito.
2. **Boilerplate lives in the skill, not the plan (3.3, user request).** Plans carry only unique content (work units, file/symbol anchors, batch schedule, seam classification) + a one-line pointer to a shared execution-contract component. Expect ~32–44% smaller plans and single-source policy.
3. **Stop full-loading PHASES.md/SPEC.md (3.2, 3.4, user request).** Load only the current-phase slice (offset/limit) + a compact completed-phases index; consider relocating accumulated Implementation Notes to a sibling `IMPLEMENTATION_NOTES.md` (or per-phase files) so PHASES.md stays a thin checklist. Scope compaction-recovery + `source-reread` to the relevant section.
4. **Encode true parallelism + background builds in the executor contract (3.6).** Multi-agent batches as a single message; background Tier-2/typegen builds and overlap with the next independent dispatch. ~1.5–2× wall-clock.
5. **Lighten the ground-truth gate (3.7).** Cheap integrity checks + assertion-vs-intent read by default; re-run tests only on mismatch. Add a 529 inline-fallback.
6. **Shrink the post-compaction floor (3.2, 3.5).** A condensed "recovery card" (TaskList → plan path → current-phase PHASES slice → resume) instead of full skill re-injection; make `TaskList`-first literal on any context-reload turn.
7. **Trim the resident MCP/tool surface (3.2).** Scope MCP servers loaded for execute-plan sessions (largest fixed cost, ~43K). Hardest to action; biggest ceiling (could push the floor under 60K).

---

## 6. Reproducing / extending this investigation

Use the `mine-sessions` skill:

```bash
# rank Cognito execute-plan sessions by signal
python ~/.claude/skills/mine-sessions/scripts/digest_sessions.py \
    --match Cognito-Forms --command execute-plan --out digest.json --include-subagents

# deep-read one session around compaction boundaries
python ~/.claude/skills/mine-sessions/scripts/render_session.py \
    ~/.claude/projects/C--Users-JacobMadsen-source-repos-Cognito-Forms/<uuid>.jsonl \
    --grep "COMPACTION" > out.txt
```

Skill sources under audit:
- `claude-config/user/skills/execute-plan/SKILL.md` (generic executor — the one that runs)
- `claude-config/user/skills/write-plan/SKILL.md` (generic planner — the one that runs)
- `claude-config/repos/cognito-forms/.claude/skills/write-plan/SKILL.md` (Cognito lane variant — advertised, intermittently runs)
- `claude-config/repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest,build-queue-status}/SKILL.md`
- `~/.claude/scripts/build-queue.ps1`, `build-queue-enforce.sh` (hook, installed 2026-06-24)
- Shared components: `~/.claude/skills/_components/{subagent-review,subagent-launch,tdd-*,phases-update,task-tracking,source-reread,quality-gates}.md`
- Representative plans: `cog-docs/docs/{features,bugs}/*/plans/*.md`
