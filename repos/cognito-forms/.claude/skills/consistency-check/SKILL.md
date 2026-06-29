---
name: consistency-check
description: Review changed code for consistency by spawning the two Cognito PR-review consistency agents in parallel — intra-file (in-file duplication + surrounding-code conventions) and cross-file (missed reuse of existing Cognito systems). NOT a correctness-bug review.
argument-hint: [scope — e.g. "the staged changes", a file/glob, PR-NNNNN, or omit to infer from chat/branch]
---

# Consistency Check

Spawn the two `cognito-pr-review` consistency agents **in parallel** to review a set of changes for consistency only:

- **`cognito-pr-review:cognito-intra-file-consistency`** — does the net-new code reimplement logic already present *in the same file*, and is it consistent with that file's established conventions (naming, formatting, async/error-handling style)?
- **`cognito-pr-review:cognito-consistency-checker`** — does the net-new code duplicate or fail to reuse an *existing Cognito system in other files*? Names the existing helper/pattern that should be called instead.

This is a **consistency** review, not correctness. It does not hunt for bugs (use `/code-review` / `/cognito-pr-review:review-pr` for that) and it does not do the broader reuse/simplify sweep (use `/simplify`).

---

## Step 1: Resolve the review scope

Pick the scope in this order:

1. **Explicit argument.** If the invocation names a scope, use it verbatim:
   - `"the staged changes"` / `"staged"` → `git diff --cached`
   - `"working tree"` / `"unstaged"` → `git diff HEAD`
   - a file path or glob → those files
   - `PR-NNNNN` / `NNNNN` / a branch name → that PR/branch diff vs `main`
2. **Infer from chat.** If no argument, scan the recent conversation for the changes under discussion (e.g. "review these changes", a just-finished `/execute-plan`, `/simplify`, or `/stage` partition). Prefer the most specific set just produced or staged.
3. **Infer from branch state.** If chat is ambiguous, derive scope from git:
   - If the index has staged changes → `git diff --cached`
   - Else if the working tree is dirty → `git diff HEAD`
   - Else → the branch diff: `git diff main...HEAD`

Run the relevant `git` commands to enumerate the concrete changed files. If the resolved scope is empty (clean tree, no diff), say so and stop — there is nothing to review.

Announce the resolved scope and file list in one line before dispatching.

## Step 1.5: Load prior decisions from PHASES.md

A consistency finding is only worth raising if it's *new*. A branch's `PHASES.md` often records a prior consistency/quality pass that already **adjudicated** these exact findings — deliberately leaving a cross-file dedup out of scope, keeping a "dead" constant as a forward contract for a later phase, preserving a human-authored comment. Re-surfacing those wastes effort and risks reversing intentional decisions. **Before dispatching, resolve and read the PHASES.md governing this change:**

1. **Explicit.** If the invocation names a PHASES.md (path or directory), use it.
2. **Inferred from branch.** Otherwise resolve the current branch to its docs dir: grep the sibling `cog-docs` repo for a `**Branch:** <current-branch>` line under `cog-docs/docs/{bugs,features}/**/{SPEC,PHASES}.md` (the same mechanism the SessionStart `load-branch-docs-context.sh` hook uses), and read the matched `PHASES.md`. The SessionStart pointer, if present, already names this directory.
3. **None found.** If no PHASES.md resolves (not every change has one), say so in one line and proceed — this step is best-effort, not a gate.

From a resolved PHASES.md, extract the **prior-decisions list**: any "consistency review" / "quality pass" / "simplification" notes and their `rejected` / `deferred` / `out of scope` / `kept` verdicts, plus forward-contract rationale (constants/fields intentionally unused now but consumed in a later phase). Carry this list into Steps 2 and 3.

**Caveat — PHASES.md is not infallible.** Its notes can be stale or wrong (e.g. an EOL/convention claim contradicted by the actual committed bytes). If ground truth in the code contradicts a PHASES.md claim, trust the code and surface the discrepancy rather than deferring to the doc.

## Step 2: Dispatch both agents in parallel

Send **both** Agent calls in a **single message** so they run concurrently. Give each agent:

- The exact git command to obtain the diff (so it reads the same scope), e.g. `git -C "<repo-root>" diff --cached`.
- The explicit list of changed files, flagging any **build-generated** files (e.g. `Cognito.Web.Client/libs/types/server-types/**`) as out of scope for style/duplication findings.
- Repo conventions to judge against: tabs for indentation, CRLF, no code comments except `///` doc comments on public interfaces, `async`/`await` never `.Result`/`.Wait()`.
- A clear division of labor so they don't overlap:
  - **intra-file agent:** only in-file duplication + surrounding-code consistency; read each changed file's full contents (not just the diff). Do NOT report cross-file duplication or correctness bugs.
  - **cross-file agent:** only missed reuse of existing systems in *other* files; grep the codebase and name the existing helper/pattern. Treat deliberate mirroring of an established sibling pattern as intended, not duplication. Do NOT report intra-file duplication or correctness bugs.
- The **prior-decisions list** from Step 1.5, if any: tell each agent these findings were already adjudicated in PHASES.md and **not to re-report them** unless it has concrete new evidence the decision was wrong. Quote the relevant verdicts so the agent can recognize them.

Each agent returns grounded findings with `file`, `line`, a one-line `summary`, and the concrete cost; or confirms the code is clean.

## Step 3: Synthesize

When both agents complete:

- Dedup findings that point at the same line/mechanism.
- **Reconcile against the Step 1.5 prior-decisions list.** Cross-check every finding against what PHASES.md already adjudicated. Drop or clearly mark (with the PHASES.md rationale) any finding that was already decided — never present an already-rejected decision as a fresh issue. A finding survives reconciliation only if it is genuinely new, or you have concrete evidence the prior decision was wrong (in which case say so explicitly).
- Group by file; within each file, list intra-file findings then cross-file findings.
- For each finding, give the concrete fix (the in-file helper to call, or the existing Cognito system to reuse).
- Separate genuine issues from notes the agents raised but judged acceptable (e.g. intended sibling-pattern mirroring) and from items already adjudicated in PHASES.md.
- Do **not** apply fixes — this skill reports only. If the user wants the safe ones applied, suggest `/simplify`.

End with a one-line verdict: clean, N consistency findings worth addressing, or "all findings already adjudicated in PHASES.md" when reconciliation clears them.
