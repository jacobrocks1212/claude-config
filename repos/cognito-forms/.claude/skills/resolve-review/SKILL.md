---
name: resolve-review
description: Resolve a Cognito PR review — read the review + journey, validate critical/important findings with Sonnet subagents, gather resolution choices, then add a remediation phase and write an implementation plan
argument-hint: [review-path | PR-NNNNN | NNNNN]
---

# Resolve Review

Turn a completed Cognito PR review into actionable remediation work. This skill reads a review (and its always-present `-journey.md` companion), independently validates the high-severity findings with Sonnet subagents, asks you how to resolve each actionable item, then bridges your choices into the planning pipeline: `/add-phase` appends a remediation phase to the feature's `PHASES.md`, and `/write-plan-cognito` emits the implementation plan.

**Scope:** Cognito Forms repo. Reviews live in `.claude.local/reviews/`; feature docs live in the sibling `../cog-docs/docs/features/` repo.

**Flow:** Resolve review → classify findings → validate flagged findings (Sonnet) → present actionable items + gather resolution choices → validate decline rationales (Sonnet) → infer+confirm feature dir → `/add-phase --batch` → `/write-plan-cognito` → report.

This skill is interactive and read-only with respect to source code — it never edits `.cs`/`.ts`/`.vue` files. Its only writes are delegated to `/add-phase` (PHASES.md) and `/write-plan-cognito` (plan file).

---

## Step 1: Resolve the Review

1. **Parse `$ARGUMENTS`** for a review reference. Accept any of: an absolute/relative path to a review `.md`, a bare filename (`PR-16537.md`), a PR slug (`PR-16537`), or a bare number (`16537`). Normalize to the file under `.claude.local/reviews/` (e.g. `16537` → `.claude.local/reviews/PR-16537.md`).
2. **If no argument is supplied, infer from context:**
   - Read the current git branch (`git rev-parse --abbrev-ref HEAD`). Look for a review whose body references that branch.
   - Otherwise fall back to the most-recently-modified `PR-*.md` (excluding `-journey.md`) in `.claude.local/reviews/`.
   - Present the inferred review to the user and confirm before proceeding (`AskUserQuestion`). If nothing plausible is found, ask the user for the review path.
3. **Load the journey companion.** For review `PR-NNNNN.md`, the file `PR-NNNNN-journey.md` is **always available** in the same directory — read it too. The journey carries the PR objective, file-change map, and the **Open Review Concerns** (Copilot threads with IDs) that map onto the review's findings.
4. **Read BOTH files in full.** Do not skim. The review carries severities and suggested fixes; the journey carries thread IDs, objective framing, and the manual-review guide.

---

## Step 2: Extract & Classify Findings

Parse the review into a structured finding list. Sources to pull from:

- **Requirements Coverage** table — any row marked `Partial` / `Not covered` is a gap finding.
- **Critical Findings** sections — each is a finding (severity from its `**Severity:**` line).
- **Rule-Based Findings** — `Important` and `Minor` subsections (weights/nit tags included).
- **Pre-merge checklist** — each unticked item is a finding (often a build/CI gate or a one-line fix).

For each finding, record: a short title, the cited `file:line`, severity (`critical`/`important`/`minor`/`nit`), the review's suggested fix, and any **journey thread IDs** it corroborates (cross-reference the journey's *Open Review Concerns* — findings often map to one or more Copilot threads; carry the thread IDs forward so resolutions can be posted back to the right threads).

**Tag each finding `validate: yes` if any of:**
- severity is `critical` or `important`, **or**
- the review explicitly flags it as latent / unverified / "did not surface in testing" / "absent by inspection" / "worth confirming".

`minor` and `nit` findings are tagged `validate: no` — they are carried forward as-is without independent validation.

---

## Step 3: Validate Flagged Findings (Sonnet Subagents)

For every finding tagged `validate: yes`, spawn a **Sonnet** subagent to independently confirm or refute it against the live codebase. Dispatch them **in parallel** — emit multiple `Agent` calls in a single message (cap concurrency at ~6; batch if there are more).

Each subagent prompt must be fully self-contained (the subagent has zero prior context) and include:
- The finding title, severity, cited `file:line`, and the review's evidence + suggested fix.
- The PR branch and a one-line objective summary from the journey.
- This task: *Read the cited file(s) and surrounding code. Determine whether the finding is real under normal operating conditions. Return a structured verdict.*

Require each subagent to return: **Verdict** (`Confirmed` / `Refuted` / `Partial` / `Needs-human`), **Evidence** (the specific code that supports the verdict, with `file:line`), **Fix approach** (concrete, minimal — or "n/a" if refuted), and **Risk/Effort** (one line).

Dispatch shape:

```
Agent({ description: "validate: <short title>", model: "sonnet",
        prompt: "<self-contained finding + cited code refs + return-format contract>" })
```

After all subagents return:
- **Refuted** findings are dropped from the actionable list (record them so they can be reported as "investigated, not a real issue").
- **Confirmed / Partial / Needs-human** findings proceed, annotated with the validated fix approach (this becomes the basis for the remediation phase's deliverables).

---

## Step 4: Present Actionable Items & Gather Resolution Choices

1. **Print a consolidated actionable table to chat** so the user sees the full picture before choosing. Columns: `#`, title, severity, validated verdict, `file:line`, suggested fix, journey thread IDs. Include `minor`/`nit` items (unvalidated) and note any refuted findings separately below the table.
2. **Group items into clusters.** The review/journey usually already cluster related findings (e.g. *Cluster A — server-honoring gap*, *Cluster B — UI guard regression*). Reuse those clusters; otherwise group by file/subsystem.
3. **Ask resolution per cluster via `AskUserQuestion`** (≤ 4 questions per call — run multiple calls if there are more clusters). For each cluster, offer:
   - **Fix now (Recommended)** — include in the remediation phase.
   - **Defer to follow-up** — out of scope for this remediation; note it.
   - **Won't fix** — record the rationale (capture the user's note; factual code claims in it are validated in step 4 below before being recorded).
   - **Needs discussion** — flag for the user to resolve before planning; do not bake into the phase.

   Capture any free-text notes the user attaches — they refine the deliverable wording.

4. **Validate decline rationales (Sonnet) — BEFORE recording them.** Any resolution other than **Fix now** (Won't fix, Defer, or leave-as-is with a documented rationale) whose rationale makes a **factual code claim** — "no async overload exists", "X is unreachable", "already handled by Y" — gets the same Sonnet subagent validation as Step 3 findings. Spawn the subagent (same self-contained prompt shape and verdict contract as Step 3) with this task: *verify the claim against the live code, including attribute-level facts — `[Obsolete]` messages, `sealed`/`internal` modifiers, existing overloads. A claim can be literally true yet refuted by an adjacent fact the decline ignores.* This runs BEFORE the rationale is recorded for the report and BEFORE any PR reply is drafted from it. A **refuted** rationale re-opens the resolution question: present the refuting evidence to the user via `AskUserQuestion` and gather a fresh choice — never carry a refuted rationale forward.

   *Anti-pattern (57077 Phase 9):* Taylor's "Can this be async?" was declined with "no async non-generic `Query(Type)` overload exists" — true but irrelevant: `IStorageContext.Query<T>()` is `[Obsolete("Consider using GetAll or GetRange.")]` and the obsoletion message names the async fix. The unvalidated decline shipped to the PR thread and had to be reversed by corrective Phase 12.

Only items resolved **Fix now** flow into the remediation phase. Hold the rest for the final report.

---

## Step 5: Map to the Feature Directory (Infer, Then Confirm)

The remediation phase attaches to a feature doc directory under `../cog-docs/docs/features/<dir>/`.

1. **Infer the best match.** Gather signal tokens from the review/journey: the work item (`AB#NNNNN`), the PR title, and the branch name. Search the feature dirs for those tokens:

   ```
   # from the Cognito Forms repo root
   grep -ril "AB#<NNNNN>" ../cog-docs/docs/features/*/   # work-item match (strongest signal)
   ```

   Also scan each candidate's `overview.md` / `requirements.md` / `progress.md` / `PHASES.md` for distinctive title tokens and the branch name. Rank by match strength (work item > branch > title tokens).
2. **Confirm with the user** (`AskUserQuestion`): present the best match and ask to confirm or pick another. If no confident match exists, fall back to a picker listing the feature dirs.
3. **Verify the dir has a `PHASES.md`** — the `/add-phase` → `/write-plan-cognito` bridge requires one. If it's missing, ask the user which `PHASES.md` to target (or whether the feature predates phased planning, in which case point `/write-plan-cognito` at the correct existing one).

---

## Step 6: Add the Remediation Phase (`/add-phase --batch`)

Synthesize the **Fix now** items (with their validated fix approaches) into a single remediation phase, then invoke `/add-phase` in batch mode so it proceeds without a redundant approval gate (the user already chose resolutions in Step 4).

- **Title:** something like `Review Remediation — PR-NNNNN`.
- **Deliverables:** one checkbox per Fix-now item, each naming the real `file:line` and the validated fix approach. Add a `Tests:` deliverable describing the coverage each fix needs (the review usually names the missing test).
- **Description passed to `/add-phase`** must be rich and unambiguous (batch mode refuses to invent scope and will write `NEEDS_INPUT.md` if the description is thin — so be specific).

Invoke via the `Skill` tool:

```
/add-phase --batch <abs-path-to-feature-PHASES.md> "<synthesized remediation phase: title, deliverables with file:line + fix approach, tests>"
```

**Coding-convention guard:** `cog-docs` is the planning repo, so naming `PR-NNNNN` inside `PHASES.md` is fine. But the *implementation* lands in the Cognito Forms repo, where checked-in code, test names, comments, and commit messages must **never** reference review/PR/planning docs. Word the deliverables so the eventual implementer describes behavior, not "fix the finding from PR-NNNNN."

---

## Step 7: Write the Plan (`/write-plan-cognito`)

Invoke `/write-plan-cognito` (the Cognito Forms lane planner) on the same feature `PHASES.md` to generate the implementation plan covering the new remediation phase (and any other open phases):

```
/write-plan-cognito <abs-path-to-feature-PHASES.md>
```

`/write-plan-cognito` partitions into backend/frontend lanes, drafts, and writes the plan file(s) into the feature's `plans/` directory and reports the path(s) and the `/execute-plan` command(s). Surface those to the user verbatim.

---

## Step 8: Report

Print a concise summary:
- **Review resolved:** PR-NNNNN (+ journey).
- **Validation results:** N findings validated → confirmed / partial / refuted (list refuted ones — investigated, not real).
- **Resolution choices:** Fix-now / deferred / won't-fix / needs-discussion (with the user's notes).
- **Phase added:** the new phase number + title in `PHASES.md`.
- **Plan written:** the plan path(s) and the `/execute-plan` command(s) from Step 7.
- **Follow-ups:** any deferred / needs-discussion items and unresolved journey threads the user still needs to respond to on GitHub.
