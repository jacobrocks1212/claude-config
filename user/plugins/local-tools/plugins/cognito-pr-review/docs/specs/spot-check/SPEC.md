# Spot-Check Review — Feature Specification

> A fast, lightweight `/cognito-pr-review:spot-check` command for quickly reviewing small (or narrowly-scoped) PRs without the full investigation-driven pipeline, ADO, buddy back-and-forth, or calibration machinery.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-06-29

**Depends on:**

- cognito-pr-review-v2 — composes — reuses `prep-pr.ts` (cache + cog-docs resolution + PR timeline) and the `investigation` agent, and mirrors `synthesizer-v2`'s output format.

---

## Executive Summary

`/cognito-pr-review:review-pr` is a 12-step, hierarchical, investigation-driven pipeline that can dispatch a dozen-plus subagents (journey-planner → triage → planner-validate → per-group investigation + sweep + ≤6 reuse + ≤6 intra-file + escalation → aggregate/post-process → synthesizer-v2). `review-pr-buddy` layers an interactive chunk-by-chunk walk on top. Both are the right tool for a substantial PR, but they are heavyweight for the common case: a small PR (<5 files) that the reviewer just wants to spot-check, where the review almost always comes back clean.

`spot-check` is a deliberately lighter sibling command. It **reuses the deterministic prep** (so PR data, diffs, timeline, and the cog-docs item dir are resolved exactly as in the full pipeline) but replaces the multi-agent fan-out with an **inline-first review**: the orchestrator reads the (optionally scoped) diff and reviews it directly, escalating to a **single** `investigation` agent only when it spots something genuinely risky. It still produces a committable review artifact, but casts a narrower net — it investigates the changes that matter without running the 95-rule sweep, reuse/intra-file clustering, or EMA calibration.

It is also **scope-targetable**: the reviewer can aim it at part of a PR — the latest commit, the author's latest attempt at addressing prior feedback, a commit range, specific files, or a natural-language description — which makes it useful even against a large PR when only a slice needs a fresh look.

## Goals

- **Fast, few dispatches.** Zero subagent dispatches on a clean small PR; one (`investigation`) when a change warrants a deeper look.
- **Self-contained.** Never invoke Azure DevOps MCP or the `az` CLI at any point.
- **Still produces a review artifact**, in the same format as a full review, written to the cog-docs item dir.
- **Scope-targetable** to a subset of a PR's changes via structured tokens or free-text.
- **Standalone** — no EMA calibration, no stage sentinels, no journey file.

## Non-Goals

- **Not a replacement for `/review-pr`** on substantial PRs. It intentionally trades thoroughness for speed.
- **No ADO interaction** — no work-item board reads/writes, no MCP, no `az`. (`prep-pr.ts` already only parses `AB#NNNNN` from the PR title/branch as plain strings — this is preserved.)
- **No calibration loop** — does not read or write `weights.yaml`, does not write `pending-calibration.json`, does not run `disposition-calibration.ts`.
- **No stage sentinels** — does not write `REVIEWED.md` (so it does not flip `derive_stage` to `reviewed`).
- **No journey file, triage, sweep, reuse-candidacy, or intra-file passes.**
- **No hard size guard** — it warns about nothing and never refuses; the reviewer chooses scope.

## User Experience

### Invocation

```
/cognito-pr-review:spot-check [PR_ID | local] [scope...]
```

- **PR mode:** first numeric token is the PR ID (e.g. `17890`).
- **Local mode:** no PR ID, or the `local` keyword — reviews uncommitted changes via `prep-pr.ts --local` (supports `--base <branch>` and `--include-untracked`, same as `review-pr`).
- **scope:** zero or more scope tokens and/or a free-text phrase (see below). Default = the whole PR/local diff.

### Scope syntax (tokens + free-text)

The reviewer aims spot-check at part of a PR. Recognized **structured tokens**:

| Token | Meaning |
|-------|---------|
| `last-commit` (or `latest`) | Only the files/hunks in the most recent commit. |
| `since-review` | Changes since the reviewer's most recent review on this PR — "the author's latest attempt to address my feedback." |
| `<sha>..<sha>` | A commit range. |
| `<path>` / glob (e.g. `*.cs`, `Cognito.Core/**`) | Restrict to matching files. |

Any remaining argument text is treated as **free-text scope** — a natural-language description ("just the validation changes", "the new queue message class") that the orchestrator interprets against the manifest/diff to select the relevant files and hunks. Free-text and tokens may combine (e.g. `17890 last-commit "the retry logic"`).

If no scope is given, the whole diff is reviewed.

### Examples

```
/cognito-pr-review:spot-check 17890                     # whole small PR, fresh-eyes spot check
/cognito-pr-review:spot-check 17890 since-review        # only the author's latest attempt at my feedback
/cognito-pr-review:spot-check 17890 last-commit         # only the most recent commit
/cognito-pr-review:spot-check 17890 "the validation changes"   # natural-language slice of a larger PR
/cognito-pr-review:spot-check 17890 Cognito.Core/**     # only files under Cognito.Core
/cognito-pr-review:spot-check                           # local uncommitted changes
/cognito-pr-review:spot-check local last-commit         # local, just the last commit
```

### Output

- **PR mode:** a review artifact at `<cogDocsItemDir>/PR-{id}-spot-{YYYY-MM-DD-HHMM}.md` (date **and time** in the name so repeated spot-checks never clobber each other or the authoritative full-review `PR-{id}.md`).
- **Local mode:** `.claude.local/reviews/LOCAL-{branch}-spot-{YYYY-MM-DD-HHMM}.md`.
- The artifact follows the `synthesizer-v2` output format (structured sections, severity tiers) so spot-check reviews read consistently with full reviews. A short header notes it is a **spot-check** and records the **scope** that was reviewed.
- A completion summary is printed to chat: artifact path, scope reviewed, file/finding counts, and whether an investigation agent was escalated.

## Technical Design

### Pipeline

```
spot-check [PR|local] [scope]
   │
   ├─ Step 1  prep-pr.ts            (REUSED as-is: cache, diffs, timeline, cog-docs item dir resolve/create)
   │
   ├─ Step 2  Resolve scope         (inline: token/free-text → target file+hunk set)
   │
   ├─ Step 3  Inline review         (orchestrator reads scoped cached diffs; senior-reviewer judgment;
   │                                 NO sweep / triage / journey / reuse / intra-file agents)
   │
   ├─ Step 4  Conditional escalate  (dispatch ONE investigation agent ONLY for a genuinely risky change;
   │                                 reuses agents/investigation.md, cache + codebase access)
   │
   ├─ Step 5  Inline synthesis      (orchestrator writes the artifact in synthesizer-v2 FORMAT; no synth agent)
   │
   └─ Step 6  Write + report        (PR-{id}-spot-{datetime}.md; print summary. No sentinels, no calibration.)
```

Contrast with `review-pr.md`: spot-check keeps **Step 1 (prep)** and a **conditional** version of **Step 5 (investigation)**, and drops Steps 2–4 (journey/triage/planner-validate), 5b (reuse + intra-file), 6 (escalation eval), 7–8 (aggregate/post-process), the synthesizer-v2 *agent* (format is reused inline), and Steps 12.6/12.7 (sentinels + calibration marker).

### Step detail

**Step 1 — Prep (reused).** Run `prep-pr.ts {id}` (PR) or `prep-pr.ts --local --base <branch> [--include-untracked]` (local), identical to `review-pr.md` Step 1. This resolves/creates the cog-docs item dir (`resolveOrCreateCogDocsItemDir`, prep-pr.ts:1026) and populates the cache (manifest, per-file diffs, `pr-timeline.json`, `pr-context.json`). Read `cacheDir` and `cogDocsItemDir` from the manifest/pr-context the script prints. **Skip the cache-boundary marker** (`review-pr.md` Step 1.5): the inline review and the optional investigation agent both need normal codebase read access, and there is no cache-only `sweep` agent in this pipeline.

**Step 2 — Scope resolution (inline).** Starting from the manifest's full file list, narrow to the target set:
- *whole PR* (default) — all manifest files.
- `last-commit`/`latest` — files+hunks in the most recent commit. PR mode: `gh api repos/cognitoforms/cognito/pulls/{id}/commits` (last entry) or `gh pr diff`; local mode: `git show`/`git diff HEAD~1`.
- `since-review` — read `pr-timeline.json`; find the reviewer's most recent review timestamp; select commits/files pushed after it. **Fall back to `last-commit` if no prior review by the reviewer is found** (ambiguous).
- `<sha>..<sha>` — the diff for that range.
- path/glob — filter the manifest by path.
- free-text — the orchestrator interprets the phrase against the manifest + diffs and selects the relevant files/hunks, stating which it chose.

Record the resolved scope (human-readable) for the artifact header and completion summary.

**Step 3 — Inline review.** The orchestrator reads the scoped cached diffs and reviews them directly with senior-Cognito-reviewer judgment (correctness, obvious pattern/DI/storage/async issues, test gaps on changed behavior). It applies focused judgment rather than the 95-rule sweep — the goal is "investigate the important changes," not "cast a wide net." Most small PRs produce no findings here.

**Step 4 — Conditional escalation.** If the orchestrator encounters a change it cannot confidently resolve inline (subtle correctness risk, non-obvious blast radius, a pattern that needs codebase verification), it dispatches **exactly one** `investigation` agent (`agents/investigation.md`, Opus) scoped to that area, passing the relevant cached files/diffs + `cacheDir`. The agent's evidence-based findings are folded into synthesis. If nothing warrants it, no agent is dispatched.

**Step 5 — Inline synthesis.** The orchestrator composes the review itself, following the `synthesizer-v2` section/severity format (no synthesizer agent dispatch). Findings are tiered consistently with full reviews. The header marks it a spot-check and states the reviewed scope.

**Step 6 — Write + report.** Write the artifact (PR mode → `<cogDocsItemDir>/PR-{id}-spot-{YYYY-MM-DD-HHMM}.md`; local → `.claude.local/reviews/LOCAL-{branch}-spot-{YYYY-MM-DD-HHMM}.md`). Print summary. Do **not** write `REVIEWED.md` or `pending-calibration.json`; do **not** run calibration.

### Reuse Ledger

| Capability | Existing implementation | Verdict | Evidence |
|------------|-------------------------|---------|----------|
| PR data / diffs / timeline / cog-docs dir | `scripts/prep-pr.ts` | **reuse-as-is** | `review-pr.md` Step 1; `prep-pr.ts:1490-1496`, `resolveOrCreateCogDocsItemDir` `:1026` |
| Deep-dive a risky change | `agents/investigation.md` (Opus, Solver-Verifier) | **reuse** (dispatched conditionally, ≤1) | `review-pr.md` Step 5; `agents/investigation.md` frontmatter |
| Review document format | `agents/synthesizer-v2.md` output format | **wrap** (follow format inline; do not dispatch the agent) | `agents/synthesizer-v2.md` |
| `since-review` resolution | `pr-timeline.json` (reviews + iterations) | **reuse** (read for scope) | `prep-pr.ts` timeline output; `review-pr.md` Step 1 |
| Findings weighting / dedup / rank | `post-process.ts`, `aggregate-findings.ts` | **not used** — calibration machinery; inline ranking suffices for a quick check | `review-pr.md` Steps 7–8 |
| Wide rule scan | `agents/sweep.md` + 95 YAML rules | **not used** — casts too wide a net for a spot check | `agents/sweep.md` |
| Triage / journey / planner / reuse / intra-file | corresponding agents | **not used** — heavyweight for small/scoped PRs | `review-pr.md` Steps 2–6, 5b |
| Stage signal + calibration loop | `REVIEWED.md`, `pending-calibration.json`, `disposition-calibration.ts` | **not used** — standalone by design (Q4) | `review-pr.md` Steps 12.6–12.7 |

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown. In brief: **Phase 1** authors the complete `commands/spot-check.md` (arg/scope parsing, prep reuse, scope resolution, inline-first review, conditional `investigation` escalation, inline synthesis, timestamped standalone artifact); **Phase 2** integrates docs + metadata (`README.md`, `CLAUDE.md`, `plugin.json` version bump). Two phases only to keep one writer per file — both are small.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Produces a review artifact | `spot-check <small PR id>` | `PR-{id}-spot-{YYYY-MM-DD-HHMM}.md` exists in the cog-docs item dir | `ls <cogDocsItemDir>` |
| Does not clobber a full review | Run `review-pr`, then `spot-check`, same PR | `PR-{id}.md` unchanged; spot artifact has a distinct timestamped name | file mtimes / diff |
| Zero dispatches on a clean PR | spot-check a trivial PR | No `investigation` agent dispatched; review reports clean | run transcript / agent count |
| Escalates on a risky change | spot-check a PR with a subtle correctness change | Exactly one `investigation` agent dispatched, finding folded into the artifact | run transcript; artifact findings |
| Scope targeting works | `spot-check <id> last-commit` | Only the latest commit's files appear in the reviewed-scope header; others ignored | artifact header + body |
| `since-review` resolves via timeline | `spot-check <id> since-review` after a prior review | Reviewed scope = changes after the reviewer's last review (or `last-commit` fallback, stated) | artifact header |
| Local mode works | `spot-check` with uncommitted changes | Artifact under `.claude.local/reviews/` | `ls .claude.local/reviews` |
| No ADO / no calibration / no sentinels | any spot-check run | No `az`/ADO-MCP calls; no `REVIEWED.md`; no `pending-calibration.json`; `weights.yaml` unchanged | run transcript; `ls <cogDocsItemDir>`; git status of `weights.yaml` |

## Open Questions

- **Inline-review depth knob.** Should the inline review optionally consult a *small* curated subset of the rule catalog (e.g. high-weight C# correctness rules) rather than pure judgment? Deferred — start with judgment-only and revisit if spot-checks miss things full reviews catch.
- **Free-text scope precision.** Natural-language scope relies on orchestrator interpretation; if it proves imprecise, consider echoing the resolved file set and confirming before review. Start without confirmation (speed-first); add a `--confirm-scope` opt-in if needed.

## Research References

No external research conducted — prior art is the plugin's own pipeline. Key source files: `commands/review-pr.md`, `commands/review-pr-buddy.md`, `scripts/prep-pr.ts`, `agents/investigation.md`, `agents/synthesizer-v2.md`, plugin `CLAUDE.md`, `README.md`.
