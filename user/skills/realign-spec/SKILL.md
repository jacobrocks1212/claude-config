---
name: realign-spec
description: Read-only reality check on completed upstream features. Diffs the current SPEC+PHASES against upstream PHASES.md (and optionally upstream plans) and writes a plans/realign-<date>.md with drift assessment and a recommended next step. Does NOT mutate SPEC, PHASES, or any upstream artifact.
argument-hint: <path/to/SPEC.md>
plan-mode: never
allowed-tools: ["Read", "Glob", "Grep", "Bash", "Write"]
---

# Realign Spec — Upstream Reality Check

Compares a feature's current SPEC.md + PHASES.md against the **actual** decisions captured in each completed upstream's PHASES.md (and, when needed, its `plans/*.md`). Surfaces drift, classifies severity, and recommends a single next step. The caller — usually `/lazy` Step 4.6, or a human running this directly — acts on the recommendation.

**HARD CONSTRAINT — READ-ONLY ON UPSTREAM:** This skill MUST NOT call `Edit` or `Write` against any file under any upstream's directory. The ONLY file this skill writes is `<feature-dir>/plans/realign-<date>.md` belonging to the downstream feature passed in.

**HARD CONSTRAINT — NO MUTATION OF CURRENT SPEC OR PHASES:** This skill MUST NOT edit the current SPEC.md or PHASES.md either. Recommendations only — the caller acts.

---

## Step 0: Parse Arguments and Resolve Paths

`$ARGUMENTS` is the path to the downstream feature's `SPEC.md`.

1. Confirm the SPEC.md exists. If not, print a one-line error and STOP.
2. Resolve:
   - `<feature-dir>` = parent directory of SPEC.md
   - `<phases-md>` = `<feature-dir>/PHASES.md` (may not exist yet — that's OK; treat missing as "no phases authored")
   - `<plans-dir>` = `<feature-dir>/plans/`
3. Announce: `"/realign-spec — checking <feature-id> against its completed upstream dependencies"`

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

Template (write verbatim, filling in bracketed values):

```markdown
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

## Step 5: Report

Print to chat:

```
## /realign-spec — Done

**Feature:** <feature-id>
**Upstreams checked:** <list>
**Findings:** <N minor / M moderate / K severe>
**Recommendation:** <one of inline-edit | add-phase | respec>
**Plan file:** <absolute path to plans/realign-<date>.md>
```

STOP. Do not invoke any other skill. The caller (likely `/lazy` Step 4.6) reads the plan file and decides what to do next.

---

## Notes

- This skill is reusable: humans can invoke it directly via `/realign-spec <path/to/SPEC.md>` between phases when they suspect drift, and it works the same way.
- If a hard upstream has no PHASES.md (older feature, never decomposed), check `<upstream-dir>/SPEC.md`'s `Status:` line and any Implementation Notes there. Treat the absence of PHASES.md as a quality issue worth surfacing in the report's Inputs section, but do not abort.
- The skill does not invoke quality gates, run tests, or build the project. It is pure documentation analysis.
- This skill does NOT call `interview_work_log_append` — it produces a planning artifact, not engineering work. The caller that acts on the recommendation logs the resulting work instead.
