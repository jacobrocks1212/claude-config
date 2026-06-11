---
name: realign-spec
description: Read-only reality check on completed upstream features. Diffs the current SPEC+PHASES against upstream PHASES.md (and optionally upstream plans) and writes a plans/realign-<date>.md with drift assessment and a recommended next step. With --apply, also acts on the recommendation (inline-edit / add-phase / write BLOCKED.md).
argument-hint: <path/to/SPEC.md> [--apply]
plan-mode: never
allowed-tools: ["Read", "Glob", "Grep", "Bash", "Write", "Edit", "Skill"]
---

# Realign Spec — Upstream Reality Check

Compares a feature's current SPEC.md + PHASES.md against the **actual** decisions captured in each completed upstream's PHASES.md (and, when needed, its `plans/*.md`). Surfaces drift, classifies severity, and recommends a single next step. Without `--apply`, writes the realign plan and stops — the caller acts on the recommendation. With `--apply`, additionally executes the recommendation in the same invocation.

**HARD CONSTRAINT — READ-ONLY ON UPSTREAM:** This skill MUST NOT call `Edit` or `Write` against any file under any upstream's directory. The ONLY file this skill writes outside the downstream feature dir is — there is none. All writes happen under the downstream `<feature-dir>`.

**HARD CONSTRAINT — DOWNSTREAM WRITES ARE NARROWLY SCOPED:**
- Without `--apply`: only `<feature-dir>/plans/realign-<date>.md` is written.
- With `--apply`: the realign plan is written first, then exactly one follow-on action runs (apply Minor patches, invoke /add-phase, or write BLOCKED.md) per the Recommended verdict. Nothing else is touched.

**Halting discipline (`NEEDS_INPUT.md` vs. `BLOCKED.md`):**

`/realign-spec` runs at state-machine Step 4.6 — *before* research integration. Per the post-research halting rule in `~/.claude/skills/_components/sentinel-frontmatter.md`, this skill is NOT eligible to write `NEEDS_INPUT.md`. The two escalation paths it owns are:

- **Severe drift** → write `BLOCKED.md` with `blocker_kind: upstream-realign` (Step 5c below). The downstream design no longer holds; this is a "pre-research-input-required"-shaped fundamental change, not a "pick option A or B" decision.
- **Moderate drift** → dispatch `/add-phase --batch` (Step 5b). `/add-phase` itself MAY write `NEEDS_INPUT.md` if the corrective phase shape genuinely admits multiple defensible designs; that halt is `add-phase`'s, not `realign-spec`'s, and `add-phase` is post-research-eligible because the corrective phase scope is derived from completed upstream PHASES.md content (which is the analogue of "research is on disk").

---

## Step 0: Parse Arguments and Resolve Paths

`$ARGUMENTS` is the path to the downstream feature's `SPEC.md`, optionally followed by `--apply`.

1. Detect the `--apply` flag: if it appears anywhere in `$ARGUMENTS`, set `apply_mode = true` and strip it from arguments before resolving the path. Otherwise `apply_mode = false`.
2. Confirm the SPEC.md exists. If not, print a one-line error and STOP.
3. Resolve:
   - `<feature-dir>` = parent directory of SPEC.md
   - `<feature-id>` = basename of `<feature-dir>`
   - `<phases-md>` = `<feature-dir>/PHASES.md` (may not exist yet — that's OK; treat missing as "no phases authored")
   - `<plans-dir>` = `<feature-dir>/plans/`
4. Announce: `"/realign-spec — checking <feature-id> against its completed upstream dependencies"` (note `apply_mode` if true).

---

## Step 1: Load Dep-Block Schema

!`cat ~/.claude/skills/_components/dep-block-schema.md`

Apply the parsing protocol above to `<feature-dir>/SPEC.md`. Yields a list of `{feature_id, kind, reason}` records.

Filter to `kind == hard`. Soft and composes deps are out of scope for reality-check (no design hinge → no drift to detect).

For each remaining hard dep:

1. Resolve its upstream directory using the resolution protocol in the schema component.
2. Check the completion gate (ROADMAP.md strikethrough+COMPLETE or upstream SPEC `Status: Complete`).
3. Drop deps whose upstream is not yet Complete — there's nothing settled to look back at.

If the filtered list is empty after this, write a minimal "Aligned — no completed hard upstreams" plan file (per Step 4 template, with empty Drift sections and `inline-edit` as a no-op recommendation), print the path, and STOP.

---

## Step 2: Load Inputs

Read in this order:

1. `<feature-dir>/SPEC.md` — full content.
2. `<phases-md>` — full content if it exists; otherwise note "PHASES.md not yet authored — only SPEC-level drift will be assessed."
3. For each upstream in the filtered hard-dep list:
   - `<upstream-dir>/PHASES.md` — full content. This is the authoritative record of decisions made during implementation. Read every Implementation Notes block; that's where the drift signal lives.
   - `<upstream-dir>/SPEC.md` — for cross-referencing original intent vs. realized state.
   - `<upstream-dir>/plans/*.md` — read selectively. Glob the directory and read any plan file whose title or first heading mentions a topic that the downstream SPEC's `Technical Design`, `User Experience`, or hard-dep reason touches. Skip retro plans unless their filename suggests they captured a relevant architectural fix.

Do NOT read more than the above. This skill must not balloon into a general codebase audit.

---

## Step 3: Diff and Classify

For each upstream, compare what the downstream's SPEC+PHASES *assumes* against what the upstream's PHASES.md (and selected plans) *actually decided*. Areas to check:

- **API / IPC contract shape** — function signatures, message types, channel names, event payloads.
- **Schema / data model** — field names, types, nullability, defaults.
- **File locations / module boundaries** — paths the downstream expects to import from, mount points, registry entries.
- **Naming** — renames or refactors that happened during upstream implementation.
- **Behavior / invariants** — preconditions, postconditions, threading model, error semantics.
- **Capabilities scoped in or out** — was something descoped in the upstream that the downstream is relying on, or vice versa?

Classify each finding into one of three buckets:

- **minor** — small wording/path/name adjustments. The downstream SPEC sentence (or PHASES bullet) is wrong about a name or path; correcting it is a local, mechanical edit that does not change design intent.
- **moderate** — the downstream is missing an integration touchpoint or assumes a capability that the upstream didn't ship (or shipped differently). A new corrective phase is needed, but the existing phase structure is salvageable.
- **severe** — a foundational decision shifted. The downstream's current design rests on an upstream contract that no longer exists. Phases would need to be rewritten; SPEC sections need redesign.

Also record an **Aligned** section: places where the downstream correctly anticipates the upstream's actual state. This proves the diff was performed and gives the user confidence in the verdict.

---

## Step 4: Write the Realign Plan File

Compute today's date as `YYYY-MM-DD`. Write to `<feature-dir>/plans/realign-<YYYY-MM-DD>.md`. If a file with that name already exists (a same-day re-run), append `-2`, `-3`, etc. until unique.

Create `<plans-dir>` if it doesn't exist: `mkdir -p <feature-dir>/plans`.

Template (write verbatim, filling in bracketed values). The YAML frontmatter at the top is REQUIRED — see `~/.claude/skills/_components/plan-frontmatter.md` for the full schema. Realign plans use `kind: realign-plan`, default to `status: Ready`, and list the phase numbers (or `["all"]`) that the drift assessment touches.

**`upstream_phases_hashes` is REQUIRED** (WU-8): for each filtered hard-complete upstream in the dep list, compute `sha256(<upstream-dir>/PHASES.md bytes)` and record it as `upstream_phases_hashes: { <upstream-dir-name>: <hex> }`. `lazy-state.py`'s `realign_is_fresh` gate reads these recorded hashes to decide whether a re-realign is needed — comparing them against each upstream's current `PHASES.md` content rather than relying on file mtimes (which reset on git checkout/clone and are therefore unreliable). A realign plan without `upstream_phases_hashes` falls back to the old mtime comparison; always write it for new plans.

```markdown
---
kind: realign-plan
feature_id: <feature-id>
status: Ready
created: <YYYY-MM-DD>
phases: [<phase-numbers-touched-by-drift>, or "all"]
upstream_phases_hashes:
  <upstream-dir-name-1>: <sha256-hex-of-upstream-dir-1/PHASES.md>
  <upstream-dir-name-2>: <sha256-hex-of-upstream-dir-2/PHASES.md>
---

# Realign — <feature-id> (<YYYY-MM-DD>)

> Read-only reality check against completed upstream dependencies. Generated by `/realign-spec`.
> No SPEC or PHASES files were modified by this analysis.

## Inputs

- **Downstream SPEC:** `<feature-dir>/SPEC.md`
- **Downstream PHASES:** `<feature-dir>/PHASES.md` (or "not authored yet")
- **Upstream dependencies checked (kind=hard, Status=Complete):**
  - `<upstream-id-1>` — PHASES.md (+ N plans: list filenames)
  - `<upstream-id-2>` — PHASES.md (+ M plans: list filenames)

## Aligned

Places the downstream correctly anticipates the upstream's actual state. Listed for diff completeness and reviewer confidence.

- **<short heading>** — <one sentence: what the downstream assumed and where the upstream confirms it>
- ...

(If no upstreams were Complete, write: "No completed hard upstreams — nothing to align against yet.")

## Drift

### Minor

Small wording/path/name corrections. Safe to apply inline to the downstream SPEC/PHASES.

| # | Location (file:section) | Current text | Upstream reality | Suggested patch |
|---|-------------------------|--------------|------------------|-----------------|
| 1 | SPEC.md § Technical Design | "..." | "..." | "..." |
| ... | | | | |

### Moderate

Missing integration touchpoints or capability gaps. Adding a corrective phase is the cleanest fix.

| # | Issue | Affected SPEC section | Proposed corrective phase |
|---|-------|------------------------|---------------------------|
| 1 | <one-line summary> | <section name> | <phase title + 1-2 sentence scope> |
| ... | | | |

### Severe

Foundational decisions shifted. The current design rests on an upstream contract that no longer holds.

| # | Issue | Affected SPEC section(s) | Why redesign is needed |
|---|-------|---------------------------|------------------------|
| 1 | <one-line summary> | <section names> | <one sentence> |
| ... | | | |

(Omit any subsection that has zero findings — write "(none)" instead of a table.)

## Recommended next step

Exactly one of:

- `inline-edit` — apply Minor patches to SPEC.md / PHASES.md as listed above; nothing else required.
- `add-phase` — invoke `/add-phase <feature-dir>/PHASES.md` with the Moderate corrective phase(s) from the table above. Minor patches may be applied in the same change.
- `respec` — the downstream's design no longer holds. Halt downstream work, surface the Severe findings, and run `/spec` (or targeted SPEC edits) to redesign before proceeding.

**Recommended:** `<one of the three>`

**Why:** <one-sentence justification tied to the most severe finding above>
```

Determine the recommendation by the highest-severity bucket that has findings:

- Any **severe** finding → `respec`
- Else any **moderate** finding → `add-phase`
- Else (only minor, or nothing) → `inline-edit`

---

## Step 5: Act on the Recommendation (only if `--apply`)

If `apply_mode == false`: skip this step entirely. Go to Step 6.

If `apply_mode == true`: execute exactly one follow-on action below, matching the verdict written in Step 4. After acting, fall through to Step 6 (Report) so the caller sees both what was decided and what was done.

### 5a. `inline-edit` — apply Minor patches

For each row in the Minor table:
1. Resolve the target file: rows in the table name a location like `SPEC.md § Technical Design` or `PHASES.md § Phase 2`. Map to `<feature-dir>/SPEC.md` or `<feature-dir>/PHASES.md` accordingly. Never touch upstream files.
2. Apply the row's `Suggested patch` via the `Edit` tool. If the suggested patch is a section rewrite, use `Edit` with enough surrounding context to be unique. If the patch is a one-line replacement, the `old_string` may be just the affected line.
3. If a row cannot be applied mechanically (target text not found, ambiguous match), skip it and note the row in the action report. Do NOT improvise — leave it for a human.

After all rows are processed, commit via the project's commit policy:
- First try `.claude/skill-config/commit-policy.md`; if absent, follow the standard pattern.
- Commit message: `docs(<feature-id>): realign with upstream — minor corrections per plans/realign-<date>.md`

Track for the action report: number of rows applied vs. skipped, the commit hash.

### 5b. `add-phase` — invoke /add-phase with corrective scope

Read the Moderate table from the realign plan to construct the corrective phase title and one-line scope. Then invoke:

```
Skill({ skill: "add-phase", args: "<phases-md> Corrective — Realign with upstream <upstream-id>: <one-line scope from realign plan> --batch" })
```

(`--batch` keeps the orchestrator-driven path free of interactive prompts; humans running `/realign-spec --apply` directly will get the same behavior, which is fine — the realign plan already authoritatively describes the desired phase.)

If `<phases-md>` does not exist, that's a precondition error: `add-phase` requires an existing PHASES.md. In that case, skip the dispatch and instead record in the action report that the corrective phase needs to be added manually after `/spec-phases` produces PHASES.md.

Track for the action report: whether /add-phase was dispatched, whether it wrote `<feature-dir>/NEEDS_INPUT.md` (orchestrator-relevant halt), the proposed phase title.

Any Minor patches alongside the Moderate findings are deferred to the next realign cycle — the freshness gate in `/lazy` Step 4.6a will pick them up.

### 5c. `respec` — write BLOCKED.md

The downstream's design no longer holds. Do NOT silently rewrite it.

Write `<feature-dir>/BLOCKED.md` per `~/.claude/skills/_components/sentinel-frontmatter.md`:

```markdown
---
kind: blocked
feature_id: <feature-id>
phase: Upstream Realignment
blocked_at: <ISO 8601 now>
retry_count: 0
blocker_kind: upstream-realign
recovery_suggestion: Review plans/realign-<date>.md and run /spec or revise SPEC sections.
---

# BLOCKED

**Feature:** <feature-id>
**Phase:** Upstream Realignment
**Blocked at:** <ISO 8601 now>
**Retry count:** 0

## Details
Severe drift detected against completed upstream(s): <comma-separated upstream-ids with severe findings>.
Foundational design assumptions no longer hold; phase rework is not sufficient.

## What was tried
/realign-spec --apply produced plans/realign-<date>.md classifying drift as severe.

## Recovery Suggestion
Review plans/realign-<date>.md, then either:
- Run /spec on this feature to redesign against the actual upstream contract, or
- Manually revise SPEC.md sections called out in the Severe table and re-run /lazy.
```

Do NOT delete or modify the existing SPEC.md or PHASES.md. The blocker forces a human decision before any rewrite.

Track for the action report: that BLOCKED.md was written, the severe upstream-ids that motivated it.

### Safety net

Step 5 is the only place this skill writes outside `<feature-dir>/plans/`. Even with `--apply`, the writes are narrowly scoped to one of three small actions above. If you find yourself wanting to do something else (e.g. edit upstream files, rewrite a PHASES.md section that's not on the Minor list, dispatch a different skill), STOP — that means the recommendation was wrong, and the right answer is to surface it to the caller without action.

---

## Step 6: Report

Print to chat:

```
## /realign-spec — Done

**Feature:** <feature-id>
**Upstreams checked:** <list>
**Findings:** <N minor / M moderate / K severe>
**Recommendation:** <one of inline-edit | add-phase | respec>
**Plan file:** <absolute path to plans/realign-<date>.md>
**Applied:** <"no — caller acts on recommendation" if apply_mode == false; otherwise a one-line summary of Step 5's action>
```

If `apply_mode == true`, also append a structured action report below the bookend:

```
### Action taken
- **Verdict:** <inline-edit | add-phase | respec>
- **Outcome:** <one of:
    "Applied N of M minor patches; commit <hash>",
    "Dispatched /add-phase with scope '<phase title>' (subagent path: <subagent reported summary>)",
    "Wrote <feature-dir>/BLOCKED.md (kind=blocked, blocker_kind=upstream-realign)"
  >
- **Skipped rows / unresolved items:** <list, or "none">
- **Next /lazy invocation will:** <see freshness gate; usually skip past Step 4.6 because the realign plan is now newer than upstream PHASES>
```

STOP. With `--apply`, the follow-on has already been performed and no other skill needs to act. Without `--apply`, the caller (e.g. `/lazy` Step 4.6) reads the plan file and acts.

---

## Notes

- This skill is reusable: humans can invoke it directly via `/realign-spec <path/to/SPEC.md>` (read-only) or `/realign-spec <path/to/SPEC.md> --apply` (read + act) between phases when they suspect drift, and it works the same way.
- If a hard upstream has no PHASES.md (older feature, never decomposed), check `<upstream-dir>/SPEC.md`'s `Status:` line and any Implementation Notes there. Treat the absence of PHASES.md as a quality issue worth surfacing in the report's Inputs section, but do not abort.
- The skill does not invoke quality gates, run tests, or build the project. It is pure documentation analysis (plus, in `--apply` mode, narrow doc edits or sentinel writes).
- This skill does NOT call `interview_work_log_append` — it produces a planning artifact, not engineering work. The caller that acts on the recommendation (or, in `--apply` mode, the dispatched `/add-phase` subagent) logs the resulting work instead.
