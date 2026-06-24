---
name: write-plan-cloud
description: Generate a FULLY self-contained implementation plan for a GitHub Copilot cloud coding agent — all spec/context/commands inlined, zero references to SPEC/PHASES or on-disk components, single-agent execution, PR as the deliverable
argument-hint: <path/to/PHASES.md> [path/to/PHASES2.md ...]
plan-mode: never
---

# Write Plan (Cloud)

Author a self-contained implementation plan that a **GitHub Copilot cloud coding agent** can execute standalone. You (locally) read the planning docs and source tree, then emit a single Markdown plan file whose body is the *entire* prompt the cloud agent will ever see.

This is the **cloud sibling of `/write-plan`**. The engineering fidelity is identical — same work-unit decomposition, same TDD rigor, same anchor discipline, same quality-gate strictness. **Only the audience changes**, and that change drives a different output contract:

| | `/write-plan` (local) | `/write-plan-cloud` (this skill) |
|---|---|---|
| Executor | Orchestrator + Sonnet subagents, in your worktree | One GitHub Copilot cloud agent, fresh checkout |
| Available context | Repo + `../cog-docs/` SPEC/PHASES + `~/.claude/skills/_components/*` | **Only the repo + this plan file** |
| Component loading | Plan references components by disk path; executor `Read`s them | **Forbidden** — every needed instruction is inlined |
| SPEC/PHASES references | Plan cites them by path; executor re-reads them | **Forbidden** — relevant spec is *quoted* inline |
| Subagent dispatch | Orchestrator composes `Agent` tool calls | **None** — the cloud agent does all the work itself |
| Deliverable of execution | Code changes; commits per project policy | **A pull request** with the implemented change |

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. Do NOT present the plan for interactive approval. The deliverable of this skill is a written plan file, not a plan-mode interaction.

**HARD REQUIREMENT — SIZE LIMIT (< 30,000 characters per file):** The GitHub Copilot cloud agent accepts a prompt of **at most 30,000 characters**, and the prompt *is* this plan file's full contents (frontmatter + body) — that is what the human pastes in. A file that exceeds this is unusable: Copilot rejects or silently truncates it, and a truncated self-contained plan is worse than useless. **Treat 30,000 characters as a hard ceiling and target ≤ 28,000** to leave paste/encoding margin. If the self-contained content for the in-scope work cannot fit under the ceiling, you MUST split into sequential parts (Step 2 / Step 5), each independently self-contained **and** each under the ceiling — never ship an oversized file or trim away required context to squeak under. Measure the real character count during the audit (Step 4) and again after writing each file (Step 5).

**THE GOLDEN RULE — TOTAL SELF-CONTAINMENT:** The cloud agent receives the plan body and *nothing else from your world*. It cannot read `../cog-docs/`, cannot read `~/.claude/skills/_components/`, cannot read your SPEC.md or PHASES.md, and has no memory of this session. **Every fact, requirement, command, convention, and acceptance criterion the agent needs MUST be written into the plan body itself.** Before you finalize, reread the plan as if you were a stranger who has only the Cognito repo and this file — if any instruction depends on a document the agent can't open, inline that document's relevant content.

> **What the cloud agent CAN see beyond the plan:** the checked-out repository, including in-repo files like `AGENTS.md`. You MAY rely on the agent reading in-repo files *that you cite by repo-relative path and that you have confirmed exist*. You may NOT rely on anything outside the repo. When in doubt, inline.

**Flow:** Load + distill all context → verify every anchor against the real tree → draft ONE self-contained plan (all context inlined) → verify no external references leaked **and the file is under 30,000 characters** → write plan file → report path + char count + handoff instructions.

---

## Step 1: Gather and Distill All Context (via parallel subagents)

The plan must inline a *lot* of distilled source — full SPEC intent, verbatim requirement passages, verified anchors, concrete commands, upstream contracts. Reading all of that into the orchestrator's own context would blow its window and slow authoring. **So you (the orchestrator) delegate the heavy reads to parallel subagents and keep only their distilled returns.**

> **Orchestrator vs. cloud agent — do not conflate.** The subagents here run *locally, at plan-authoring time*, to build YOUR context efficiently. They are unrelated to the cloud agent, which still works solo (Step 2). Using subagents to *write* the plan is fine and encouraged; the *plan you emit* must never tell the cloud agent to spawn any.

### 1a. Resolve PHASES.md Paths

- `$ARGUMENTS` must contain 1+ `.md` paths (a feature/bug PHASES.md, typically under `../cog-docs/docs/{features,bugs}/<slug>/`). If none are provided, use **AskUserQuestion** to ask which feature/bug to plan.
- Confirm each file exists. If one doesn't, report and exclude it.

### 1b. Read ONLY the PHASES.md spine yourself

The orchestrator reads **only the PHASES.md file(s)** directly — they are small, and you need them in your own context to scope the work and partition it (Step 2). For **each** PHASES.md: read it in full, identify which phases/deliverables this plan covers (the unchecked `- [ ]` items unless the user scoped a subset), and note the feature/bug slug. Everything heavier (SPEC, source tree, conventions, upstream plans) is delegated below — do NOT read those into your own context.

### 1c. Dispatch Parallel Context Subagents (preserve your window)

From the in-scope PHASES.md deliverables, derive (a) the list of existing symbols/files/types/routes the plan will touch or integrate with, and (b) which subsystems are involved. Then dispatch the following **read-only** subagents **concurrently** (one message, multiple `Agent` tool calls — use the `Explore` agent type, or `general-purpose` for the heavier distillation tasks). Each subagent returns **compact, directly-inlinable Markdown** — verbatim quotes, exact paths, real signatures — NOT a vague summary, because its output is pasted into the plan.

1. **SPEC distiller.** Input: SPEC.md path (+ any `INVESTIGATION.md`/repro/design notes in the same dir) and the in-scope deliverable list. Returns: the **ADO work-item ID** (from a `**Work Item:**`/`**WI:**` field or the dir slug — needed for frontmatter), a tight Background narrative (the *why* and intended user-facing behavior), the key design decisions already made, the non-goals, and — keyed to each deliverable — the **verbatim** requirement passage(s) that govern it (quote exactly; these get inlined as the agent's source of truth). Instruct it: precision over brevity on requirement text; never paraphrase a normative requirement.
2. **Anchor verifier (this is the mandatory anchor-existence check — do not skip it).** Input: the list of existing symbols/files/types/routes from (a). For each, it greps/opens the tree and returns the real `repo-relative/path.ext:line` plus the exact signature, OR flags it **PHANTOM** (zero hits). It also returns the surrounding pattern to copy for each integration point. This subagent's verdict is authoritative for anchor existence.
3. **Conventions & commands gatherer.** Input: the involved subsystems/paths. Reads the repo root + nearest local `AGENTS.md`, the relevant subdir `CLAUDE.local.md`/`CLAUDE.md`, and the quality-gate definition (`.claude/skill-config/quality-gates.md`, fallback `~/.claude/skills/_components/quality-gates.md`). Returns: the **concrete** in-loop and authoritative build/test command lines (resolved, not described), the area-specific coding conventions, and the "do not do" guardrails relevant to these files.
4. **Upstream contract extractor (only if deps exist).** Input: the SPEC's `**Depends on:**` hard deps / PHASES entry criteria that name completed upstream work. Reads the upstream plan/PHASES and returns the **concrete contract** to honor — exact type/method/route names, signatures, file paths, invariants — so the plan can inline it instead of referencing the upstream doc.

Wait for all of them, then keep their distilled returns as your working material. If a subagent returns thin or self-contradictory output, re-dispatch it with a sharper brief rather than reading the source yourself (protect your window).

### 1d. Reconcile & Build the Work Queue

From the subagent returns:
- **Resolve every PHANTOM** the anchor verifier flagged: either correct the name (re-dispatch a targeted check) or convert that dependency into a "must be BUILT by this plan" deliverable with explicit files-to-create. **Do not draft a single "extends/uses/calls existing X" instruction whose X the anchor verifier did not confirm.**
- Build the work queue: for each in-scope deliverable record what it builds, exact files it creates/modifies, whether it has testable behavior (TDD candidate), the governing SPEC passage (from the SPEC distiller), and any ordering dependency (especially same-file edits). This is the raw material for Step 2.

---

## Step 2: Partition into Work Units (MANDATORY — BEFORE DRAFTING)

The cloud agent executes work units **sequentially, by itself** (there is no subagent fleet). "Batches" from the local pipeline collapse to **execution order** here: a same-file dependency means one work unit must finish before the next begins. Apply the standard sizing and overlap discipline below, reading "subagent receives a work unit" as "the agent does one work unit before starting the next":

!`cat ~/.claude/skills/_components/subagent-partitioning.md`

**Cloud adaptations to the above (the component is written for a subagent fleet — translate it):**
- **One agent, no subagents.** The above talks about "subagents" each receiving a work unit. The cloud agent CANNOT spawn subagents and CANNOT run work units in parallel — it does every work unit itself, one after another. Use the component only for its WU *sizing and file-overlap* logic; ignore its dispatch/parallelism framing. **The output plan must never tell the agent to spawn an agent, dispatch a subagent, run work units in parallel, or use any orchestration tool.**
- **Sequential ordering.** Order work units so any WU depending on another's output (or editing the same file) comes after it. Optimize for a clean linear order with a natural verify point after each WU.
- **Two independent split triggers — 8 work units AND 30,000 characters per file.** Partition into N sequential plan files (Step 5) when *either* limit is hit: more than 8 in-scope WUs, **or** a single file that would exceed 30,000 characters. Each part must be ≤ 8 WUs, under the char ceiling, and **independently self-contained** (full context repeated — the cloud agent running part 2 has never seen part 1's prompt). Target ~3–5 WUs per part.
- **Budget the character ceiling up front.** Because every part repeats the full preamble + background + orientation + conventions + gates verbatim, that fixed overhead (~6–10k characters) is spent before a single WU is written, and each WU's inlined spec/anchors/tests typically adds a few thousand more. A part with only 2–4 heavy WUs can already approach 30,000 characters. When the distilled context is large, plan for *fewer* WUs per part so each file clears the ceiling — let the char budget, not just the 8-WU cap, decide where you split.
- **Each part = one Copilot spawn.** Later parts assume earlier parts have already merged to the base branch. State that assumption explicitly in the later part's context section, and inline the contract earlier parts established (same discipline as Step 1c upstream deps).
- **A red flag, not a split point:** if a single phase has >8 WUs on its own, surface it in the final report (the phase is too large) and generate one oversized plan as best-effort rather than splitting a phase mid-deliverable.

---

## Step 3: Draft the Self-Contained Cloud Plan

Write the plan addressing the cloud agent directly in the second person ("You will implement…"). The body must read as a complete, standalone briefing. Use the structure below. **Every `>`-quoted block is plan content — write it into the file**, filling bracketed values and inlining distilled content.

### 3a. Frontmatter + Preamble

```
---
work_item: <ADO work-item ID — e.g. 16742>   # FIRST field, always present; the human spawning the cloud agent keys off this
kind: cloud-implementation-plan
feature_id: <feature/bug directory slug>
status: Ready
created: <YYYY-MM-DD today>
phases: [<phase numbers this plan covers>]
target_repo: cognitoforms/cognito
agent: github-copilot-cloud
---
```

**Resolve `work_item` before writing.** Pull the ADO work-item ID from the SPEC.md/PHASES.md (commonly a `**Work Item:**`/`**WI:**` field or in the directory slug `<id>-<slug>`); the Step 1 SPEC distiller should return it. It is the FIRST frontmatter key so it's immediately visible to the human who spawns the cloud agent. If no WI ID can be resolved, use **AskUserQuestion** to get it rather than omitting it or guessing — do not write `work_item: unknown`. (This is orchestrator/human metadata only — per the Pull Request section the cloud agent must NOT put the WI number in the PR.)

> # Implementation Plan — [feature/bug title]
>
> **You are a GitHub Copilot coding agent working in the `cognitoforms/cognito` repository.** This document is your complete brief. It is fully self-contained: everything you need is written here. Do not assume access to any external design document, ticket, or wiki — if something seems to be "described elsewhere", it has been inlined below.
>
> **Your deliverable is a pull request** that implements everything in the Work Units section, with all tests passing and all quality gates green.

If this is part K of N (Step 5), immediately add:

> **Plan part K of N.** This part assumes parts 1…K-1 have already been merged to the base branch. The contracts those parts established that you depend on are inlined in the Context section below — you do not need their plan files.

### 3b. Background & Intent (inline the SPEC's "why")

> ## Background
>
> [2–5 paragraphs distilled from SPEC.md: what this feature/fix is, the problem it solves, the user-facing behavior, and the key design decisions already made. The agent must understand *intent* well enough to make correct micro-decisions the work units don't spell out. Quote SPEC passages where precision matters. Do NOT cite SPEC.md by path — the agent cannot open it.]

### 3c. Repository Orientation (only what's relevant)

> ## Where Things Live
>
> [A tight map of the subsystems this change touches — confirmed paths from the Step 1 anchor verifier. For each: its role, the key existing types/methods you'll integrate with (with `path:line` and signatures), and the pattern to copy. Keep it scoped to this change; do not paste the whole repo map.]

### 3d. Scope & Non-Goals

> ## Scope
> [Bulleted list of exactly what to build.]
>
> ## Non-Goals — Do NOT
> [Explicit guardrails: files/areas to leave alone, generated artifacts not to hand-edit, behaviors out of scope. Inline the relevant repo guardrails, e.g.: do not hand-edit generated frontend types under `Cognito.Web.Client/libs/types/server-types/` — change the server-side source of truth and let the build regenerate them; prefer constructor-injected dependencies over new `ModuleFactory` lookups; follow `IEntity`/`ICollection<T>` patterns rather than defensively initializing list properties.]

### 3e. Coding Conventions (inline — the agent has no global config)

> ## Conventions You MUST Follow
>
> [Inline only the conventions relevant to the files this plan touches. Pull from the repo's AGENTS.md / CLAUDE conventions and the per-language rules. Typical set for Cognito:]
> - Indentation is **tabs**; line endings are **CRLF** (follow `.editorconfig`).
> - **Do not write code comments.** The only exception is a doc comment on a public/service interface where genuinely warranted. Never delete an existing human comment.
> - **C#:** Microsoft conventions — `PascalCase` public members, `_camelCase` private fields. Always `async`/`await`, never `.Result`/`.Wait()`. Nullable reference types enabled. Check the target project's `<LangVersion>` before using newer syntax — most projects are C# 8; `Cognito.Core` and `Cognito.Services` are C# 10. Avoid file-scoped namespaces, required members, raw string literals, generic attributes.
> - **TypeScript/Vue:** strict mode, `const`/`let` (never `var`), interfaces for object shapes, arrow functions for callbacks, `async`/`await` over `.then()`. Vue 2.7 **Composition API** (not Vue 3); prefer `ref()` over `reactive()` for primitives; use composables for shared logic.
> - [Add any area-specific patterns distilled from the local CLAUDE.local.md/AGENTS.md.]

### 3f. Work Units

Add a plain overview list near the top (NOT a checkbox list — the cloud agent does not track progress by ticking boxes; it works the units in order and verifies via the gates):

> ## Work Units (execute in this order)
> 1. WU-1 — [short title]
> 2. WU-2 — [short title]
> …

Then, for **each** work unit, in execution order:

> ### WU-N — [title]
>
> **Goal:** [one sentence — what this WU achieves.]
>
> **Depends on:** [WU-M, or "nothing — start here". Note any same-file ordering constraint.]
>
> **Files to create/modify:** [exact repo-relative paths. For modified files, the confirmed `path:line` anchor and what changes there.]
>
> **What to implement:** [Precise, self-contained implementation requirements. Quote the governing SPEC requirement inline. Spell out the algorithm/behavior, edge cases, and integration points using the verified anchors from Step 1. The agent should not need to infer anything material.]
>
> **Tests (TDD — write these first, watch them fail, then implement):**
> [TDD work units only. Exact test file path(s), the test class/describe block, and each test's behavior + assertion. Inline how tests are run for this area (concrete command). For non-testable WUs — pure config/scaffolding — state "No automated tests; verified by the build gate" and why.]
>
> **Acceptance criteria:** [Observable, checkable conditions that mean this WU is done — the behavior works, the tests pass, the build is clean.]

**Anchor discipline (inline as fact):** every "extends/uses/calls/refactors existing X" phrase in a WU must name the verified `path:line` from Step 1. No unverified existing-symbol references.

### 3g. Execution Protocol (write verbatim, adapted)

> ## How to Execute This Plan
>
> 1. Create a working branch off the base branch.
> 2. Work the Work Units **in listed order**. For each WU: if it has tests, write the failing tests first, then implement until they pass; otherwise implement and rely on the build gate.
> 3. After each WU, run the **in-loop gate** (below) scoped to what you changed, and confirm it passes before starting the next WU.
> 4. After the final WU, run the **full authoritative gate** (below). It must be 100% green.
> 5. Open a pull request (see Pull Request section). Do not consider the task done until the PR is open and gates pass.
> 6. If you hit a genuine blocker (a requirement that contradicts the code, a missing dependency you cannot build, an ambiguity with materially different correct answers), STOP, open the PR as a **draft** with what you completed, and clearly describe the blocker and what you need in the PR body. Do not guess past an architectural fork.

### 3h. Quality Gates (inline the CONCRETE commands)

Inline the actual commands the Step 1c conventions-&-commands subagent resolved — never "run the quality gates" or a path reference.

> ## Quality Gates
>
> **In-loop (after each work unit — scope to what you changed):**
> [Concrete targeted commands. For Cognito C#: incremental build of the affected test project then a filtered test run, e.g.
> `dotnet build .\Cognito.UnitTests\Cognito.UnitTests.csproj -c Debug -v minimal --nologo` then
> `dotnet test .\Cognito.UnitTests\Cognito.UnitTests.csproj -c Debug -v minimal --nologo --filter "FullyQualifiedName~<ClassUnderTest>"`.
> For frontend: `npx nx test <project> -- --testPathPattern="<pattern>" --no-coverage`.]
>
> **Authoritative (before opening the PR — MANDATORY, 100% pass):**
> [Concrete full commands. C#: `dotnet build .\Cognito.sln -c Debug -v minimal --nologo` then the filtered test run across every touched test class. Frontend: build + test the touched Nx projects. Mixed: run both. After a full build, check `git status --short -- "Cognito.Web.Client/libs/types/server-types/"` — a new diff means generated types changed; commit them as part of the change.]
>
> Use the `Debug` / `net472` configuration. Do NOT use `NETCORE Debug`. Do not run the entire unfiltered test project — always `--filter` to the relevant classes.

### 3i. Pull Request

The PR **is** the deliverable — unlike the local pipeline, the cloud agent must commit and open it.

> ## Pull Request
>
> When all gates are green, open a pull request against the base branch:
> - **Title:** a concise summary of the change.
> - **Body:** what changed and why (distilled intent), the work units completed, how you verified (commands run + results), and anything a reviewer should scrutinize. Do not reference internal planning docs, work-item numbers, or this plan by name — describe the change on its own terms.
> - Ensure CI / required checks pass on the PR.

### 3j. Definition of Done

> ## Definition of Done
> The task is complete when ALL of the following hold:
> - Every work unit is implemented.
> - All tests written for TDD work units pass.
> - The authoritative quality gate is 100% green.
> - No generated artifacts were hand-edited; any regenerated artifacts are committed.
> - A pull request is open with a complete description and passing checks.

---

## Step 4: Self-Containment Audit (MANDATORY — BEFORE WRITING TO DISK)

Reread the drafted plan as the cloud agent — a stranger with only the Cognito repo and this file. Fix every violation:

1. **No external-doc references.** Search the draft for `SPEC.md`, `PHASES.md`, `INVESTIGATION.md`, `../cog-docs`, `cog-docs/`, `~/.claude`, `skills/_components`, "the spec", "the plan above" (across parts), or any "see X" pointing outside the repo. Each must be replaced by inlined content. (In-repo paths like `AGENTS.md` or `Cognito.Core/...` that you confirmed exist are allowed.)
2. **No phantom anchors.** Every existing-symbol citation traces to a Step 1 anchor-verifier confirmation. Re-check any you're unsure of; a zero-hit citation blocks finalization (correct it or convert to a build deliverable).
3. **Commands are concrete.** No "run the quality gates", "the usual build", or component-path references — actual command lines only.
4. **Intent is inlined.** A reviewer reading only this plan understands *why*, not just *what*.
5. **Parts are independent.** For multi-part output, each part repeats full context/conventions and never says "see part K".
6. **No subagent / orchestration language.** Search the draft for "subagent", "dispatch", "Agent tool", "in parallel", "orchestrator", "batch". The cloud agent works alone and sequentially — rephrase any such instruction as a direct, single-agent action.
7. **No progress checkboxes.** The Work Units overview and Definition of Done are plain lists, not `- [ ]` checkboxes. The cloud agent doesn't tick boxes; it verifies via the gates. (Any `- [ ]` in the draft that the agent is told to "check off" is a leak — remove the check-off semantics.)
8. **Under the 30,000-character ceiling.** Measure the drafted plan's full character count (frontmatter + body — exactly what gets pasted). It MUST be < 30,000; if it is over, or hugging the ceiling with no margin against your ~28,000 target, fix it in this order: (a) tighten verbose prose and remove orientation that isn't load-bearing; (b) if it's still over, split into another sequential part per Step 2 (each part re-audited for size). **Do NOT** drop required spec text, anchors, conventions, or gates to fit — self-containment outranks brevity, so split rather than starve. Re-audit after any split. While drafting you can estimate length with the Bash tool (`wc -m`); the authoritative measurement happens against the written file in Step 5.

A plan that fails any check — including the size ceiling — is not `status: Ready`. If a genuine design fork makes the plan unwriteable without a decision, use **AskUserQuestion** to resolve it, then continue — do not bake an arbitrary choice into a standalone plan the agent can't question.

---

## Step 5: Write Plan File(s) to Disk

**HARD REQUIREMENT — NO PLAN MODE.** The plan file is the deliverable.

### Output path

Colocate with the feature/bug docs, in a `plans/` subdirectory, marked as a cloud plan:
- Single part: `{phases-dir}/plans/cloud-{slug}.md`
- N parts: `{phases-dir}/plans/cloud-{slug}-part-K.md`

Create `plans/` if needed (`mkdir -p`). Write with the `Write` tool. The frontmatter from Step 3a goes first, then the preamble, then the body.

### Verify size against the ceiling (MANDATORY, per file)

After writing **each** plan file, measure its real character count and confirm it is under the 30,000-character ceiling. On this Windows machine, count characters with PowerShell:

```
powershell.exe -Command "(Get-Content -Raw -LiteralPath '<absolute-path>').Length"
```

(`wc -m '<path>'` via the Bash tool also works.) If any file is **≥ 30,000**, it is not shippable: go back to Step 4 item 8 — tighten prose or split into an additional sequential part — then rewrite and re-measure. Do not stop until every written file is confirmed under the ceiling.

### Final report

1. Print the absolute path(s) written, with WU counts **and the measured character count** (so the user can see the margin against the 30,000 limit):
   ```
   Cloud plan written: <absolute-path>  (<N> work units, <C> chars / 30,000)
   ```
   For multi-part output, list every part with its own char count and the execution order.
2. If a phase exceeded the 8-WU cap, print the red-flag note above the paths.
3. **Handoff instructions** — the plan body is the cloud agent's prompt. Tell the user how to use it:
   ```
   To run: open a GitHub Copilot cloud coding-agent task on cognitoforms/cognito
   and paste the contents of this file as the task description (or attach it).
   The plan is fully self-contained — the agent needs nothing else.
   For multi-part plans, run each part as a separate task, in order, after the
   previous part's PR has merged.
   ```

This is the final output. Do not enter plan mode and do not add commentary after the handoff block.
