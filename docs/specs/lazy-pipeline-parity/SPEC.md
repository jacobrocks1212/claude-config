# Lazy Skill-Family Parity — orchestrator drift control — Feature Specification

> Close the behavioral units where derived lazy skills silently fell behind their canonical twin, and build the durable mechanism that keeps the **whole lazy skill family** in sync from now on — a machine-readable, per-pair divergence registry plus a hard-gating parity audit, so every future change to a canonical lazy skill must either propagate to each derived twin or be recorded as an intentional, per-pair divergence at authoring time, never discovered at runtime.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-06-15

**Depends on:** (none)

> Formally no dep-block entries (this repo's specs have no queue.json). Substantive relationships:
> - **lazy-validation-readiness** (`docs/specs/lazy-validation-readiness/SPEC.md`, Complete) is the **source of the drift this spec audits**: its F2a (dispatch-by-reference), F5 (validation-readiness pre-screen / Step 0.52), and F7 (stale-binary detection) are the recent `/lazy-batch` enhancements whose propagation into the derived skills this spec verifies. F5 is recorded here as a feature-only divergence; the F2a cycle-dispatch sub-unit is one of the leaked gaps this spec closes.
> - **lazy-hardening** (`docs/specs/lazy-hardening/PHASES.md`, Complete) Phase 6 WU-1 performed the "lazy-bug-batch by-reference rebuild (D4)" that established the thin "differences-only" skill structure this spec formalizes and protects.
> - **turn-routing-enforcement** (`docs/specs/turn-routing-enforcement/SPEC.md`, Complete) built the prompt registry / nonce dispatch contract (`register_emission`/`lookup_emission`, the validate-deny guard) that the F2a `cycle_prompt_ref` mechanic — one of the audited Tier-2 mechanics — rides on.
> - **lazy-bug-family** (`docs/specs/lazy-bug-family/`) is the original bug-pipeline charter; this spec governs how the bug-axis derivatives track their canonical twins.

---

## Executive Summary

The lazy skill family is organized as **canonical roots with derived variants**. Three canonical skills carry the full algorithm — `lazy-batch` (batch orchestrator), `lazy` (single-item dispatcher), and `lazy-status` (dashboard) — and five derived skills re-express each canonical along one of two axes: the **bug axis** (`docs/bugs/` + `bug-state.py` + `FIXED.md` + archive-on-fix, no Gemini research) and the **cloud axis** (`lazy-state.py --cloud`, defer Tauri/MCP, `DEFERRED_NON_CLOUD`). Two derivation *flavors* exist: **inherit-by-reference** (a thin "Differences from X" skill with "see Step N" pointers) and **full parallel restatement** (the canonical's prose duplicated wholesale with a vocab swap).

Either flavor has the same structural weakness: **nothing detects when a new behavioral unit in a canonical skill gains no coverage in its derived twins.** Propagation depends on whoever edits the canonical remembering to mirror-or-justify across every derivative — and that discipline failed. A live `/lazy-bug-batch` run surfaced enhancements that never reached it. A read-only audit then found the same class elsewhere in the family.

This spec does two things. **(1) Close the known leaks** — mirror the F2a cycle-dispatch template and the mandatory `dev:kill` run-end teardown into `/lazy-bug-batch`, and record the per-pair divergences the audit surfaced (e.g. F5 is feature-only; `dev:kill` is legitimately absent in the cloud batch variant because cloud never boots the runtime). **(2) Build the durable, family-wide sync mechanism** — a machine-readable, **per-pair divergence registry** (the structured successor to each derived skill's prose "Differences" table) plus a **parity-audit engine** that reconciles every canonical skill's behavioral units against each derived twin's coverage, wired as a **hard gate** in the repo's pytest harness. After this spec, drift anywhere in the family is caught at authoring time: a new canonical unit with no parity decision for one of its twins fails the suite, and the only way green is to mirror the unit or add a registry entry — scoped to that specific pair — with a stated reason.

## The drift, atomically

```
Terms in play:
- behavioral unit   → a step, rule, or template in a CANONICAL lazy skill that determines its behavior.
                      Granularity tiers: (T1) section headings (## Step / ### sub-step); (T2) load-bearing
                      sub-heading mechanics (dispatch templates, run-end teardown, gate sequences, sentinel contracts).
- canonical / derived → canonical = the skill carrying the full algorithm (lazy-batch, lazy, lazy-status);
                      derived = a variant re-expressing it along ONE axis (bug or cloud).
- "in sync"         → for every canonical unit, each derived twin provides coverage that is exactly one of:
                        • restated   — derived re-states the unit with axis token substitution
                        • inherited  — derived carries an explicit "see <canonical> Step X" pointer that resolves
                        • divergence — the unit is listed in the registry FOR THAT PAIR with a reason
                      Any (canonical unit × derived twin) with none of these = DRIFT.
- "remain in sync"  → a DETECTOR that fails at authoring time (in the test suite) the moment a (unit × twin)
                      pair has no coverage, rather than a human noticing missing behavior in a live run.
- "intentional divergence" → a PER-PAIR registry entry recording WHAT differs, FOR WHICH TWIN, and WHY; the
                      auditable escape hatch that keeps the hard gate honest.

Reconstructed question: How do we close the leaked units and build a detector that forces every future change to
a canonical lazy skill to propagate to EACH derived twin or be recorded as a per-pair intentional divergence —
caught in the test suite, not in a live run?
```

**Per-pair, not global.** The headline insight from the audit: the *same* mechanic can be a gap for one twin and a legitimate divergence for another. The `dev:kill` run-end teardown is a **genuine leak in `/lazy-bug-batch`** (the bug pipeline boots the orchestrator-owned runtime for mcp-test cycles and leaks it) but a **legitimate divergence in `/lazy-batch-cloud`** (cloud defers Tauri/MCP and never boots the runtime, so there is nothing to tear down). A global rule would mis-handle one of them. Coverage is therefore recorded **per (canonical, derived) pair**.

**Directionality.** Each canonical is the authoritative source; derived twins must cover every canonical unit or register a divergence. Derived-only behavior (axis-specific steps that have no canonical counterpart — e.g. cloud's `__write_deferred_non_cloud__`) is itself a divergence entry, so the registry is the full bidirectional record for each pair.

## The lazy skill family — parity DAG

Three canonical roots, five derived twins, two standalone skills (excluded, with reason). All nine live in the `claude-config` repo (the AlgoBooth `.claude/skills` symlink points back to `repos/algobooth/.claude/skills/`), so the audit reads them all from one repo across two subtrees.

| Canonical (root) | Derived twin | Axis | Flavor | Derived location |
|---|---|---|---|---|
| `lazy-batch` (1296 ln) | `lazy-bug-batch` (866) | bug | inherit-by-reference | `user/skills/` |
| `lazy-batch` | `lazy-batch-cloud` (903) | cloud | inherit-by-reference | `repos/algobooth/.claude/skills/` |
| `lazy` (281) | `lazy-bug` (335) | bug | **full restatement** | `user/skills/` |
| `lazy` | `lazy-cloud` (274) | cloud | inherit-by-reference (thin wrapper, ~44 pointers) | `repos/algobooth/.claude/skills/` |
| `lazy-status` (130) | `lazy-bug-status` (159) | bug | **full restatement** | `user/skills/` |

- **No diamond / transitive parity.** Each derived twin diverges from its canonical along exactly one axis. There is no `lazy-bug-cloud`, no cloud dashboard, no bug-and-cloud combination — so the five pairs are independent edges, never a chain. This keeps each pair's coverage self-contained.
- **Flavor drives audit emphasis.** `inherit-by-reference` pairs are checked mostly via pointer resolution (C2) plus Tier-2 predicates. **`full restatement` pairs (`lazy`↔`lazy-bug`, `lazy-status`↔`lazy-bug-status`) are the highest drift risk** — the prose is duplicated with no pointers to anchor it — so for them the audit leans on Tier-1 heading-parity + Tier-2 mechanic predicates.

**Excluded (with reason — flag if you disagree):**
- `lazy-worker` (213 ln) — a standalone worker-pool session model (leased queue item + worktree slot → PR), with no canonical twin. Not a variant of any other lazy skill; nothing to keep in parity with.
- `lazy-batch-retro` (670 ln) — a standalone read-only audit/grading tool, not a pipeline variant. It is a **consumer**, not a pair: it grades both `/lazy-batch` and `/lazy-batch-cloud` runs, so Phase 4 adds a note pointing it at the registry (so grading rubrics can reference recorded divergences), but it is not itself a parity edge.

## Divergence audit — findings (evidence base)

Read-only passes over the canonical/derived SKILL.md files, cross-checked against the git history of the recent `/lazy-batch` enhancements. Two passes fully audited the `lazy-batch`↔`lazy-bug-batch` pair; targeted spot-checks established the family-wide picture for the other four pairs (each pair gets its own full audit when its registry section is authored — see Phase 3).

### `lazy-batch` → `lazy-bug-batch` (fully audited)

| Recent `/lazy-batch` enhancement | Channel into bug pipeline | Verdict |
|---|---|---|
| **F2a dispatch-by-reference** (3e2900a) | Meta-dispatch synced (line 84); **cycle-dispatch template (line ~495) still hard-codes `prompt: <cycle_prompt, verbatim>`** | **GAP — close (Phase 1)** |
| **mcp-test `dev:kill` run-end teardown** (78cec8e ISSUE 4) | `/lazy-batch` §1c.6 has mandatory `dev:kill`; **bug §1c.6 (lines ~301-313) lacks it** → bug mcp-test cycles boot the orchestrator-owned runtime (Step 1d.0) and leak it at run-end | **GAP — close (Phase 1)** |
| **F5 validation-readiness pre-screen / Step 0.52** (60856f2) | Absent; front-loading a `DEFERRED_NON_CLOUD` cohort is feature-curation that does not map to bug queueing | **Divergence — record (Phase 3)** |
| F7 stale-binary (ffd1745), runtime-up rewrite (62077a0) | Inherited — bug Step 1d.0 is a total-delegation pointer to `/lazy-batch` Step 1d.0 | Non-gap (inherited) |
| `deliverables_done` plan-WU checkboxes (9a78a0c) | Inherited — shared `lazy_core.verify_ledger`; bug §1e passes `--verify-ledger --plan` | Non-gap (shared script) |
| NEEDS_INPUT skip self-announcing (fdbbf5e), 78cec8e sub-skill parts | Inherited via shared `_components/` + dispatched sub-skills | Non-gap (shared component) |
| Research-halt path (0ba0598, 6903f19), Step 0.5 ingest, `needs-research`, Step 4/5 | **Bugs do not undergo Gemini deep research** (operator-confirmed 2026-06-15) | Divergence (pre-existing; migrate to registry) |

### Family-wide spot-checks (each gets a full audit in Phase 3)

| Pair | Spot-check finding | Implication |
|---|---|---|
| `lazy-batch` → **`lazy-batch-cloud`** | `cycle_prompt_ref` **synced** (8/8 occurrences vs canonical); **`dev:kill` absent (0)** | Not a leak — cloud defers Tauri/MCP and never boots the runtime → `dev:kill` is a **legitimate divergence** to RECORD (the per-pair gap-vs-divergence example). The cloud pair is otherwise well-maintained (meta-dispatch by-ref, Step 1d.5 mirror, Step 4/5 pointers all present). |
| `lazy` → **`lazy-bug`** | Near-identical heading structure (Sentinel Format, Step 0.0/0/0.3/1/2a/2b/3/4/5, Refs, State-Machine Summary); two-gate `__mark_fixed__` logic present | **Full restatement, highest drift risk.** No "Differences from /lazy" section, no pointers — every canonical unit is duplicated prose that can silently drift. Needs full Tier-1 + Tier-2 audit. |
| `lazy` → **`lazy-cloud`** | Thin wrapper (~44 `/lazy` pointers); cloud-axis steps (`__write_deferred_non_cloud__`, deferral bookends) | Mostly inherited; cloud-axis steps are derived-only divergences to record. |
| `lazy-status` → **`lazy-bug-status`** | Parallel restatement (7/7 headings each) | Full restatement; low-stakes (read-only dashboards) but in scope for completeness. |

**Net:** 2 runtime-affecting prose gaps to close now (both in `/lazy-bug-batch`), plus a family of per-pair divergences and restatement-drift surfaces to capture in the registry. The audit's deeper lesson holds across the family: the gaps are **sub-heading-level** (a derived skill *has* the §/step but the mechanic inside differs), so the mechanism must reach Tier-2, and coverage must be **per-pair** so `dev:kill`-style "gap here / divergence there" splits are expressible.

## User Experience (skill author)

The audience is the skill author (Jacob, or a `/lazy-*` maintenance cycle) — not an end user.

- **Authoring a canonical change.** You edit `lazy-batch` (or `lazy`, or `lazy-status`). If your edit adds a step or alters a tracked Tier-2 mechanic, running `pytest user/scripts/` now **fails per affected twin**: e.g. `lazy-parity [lazy-batch→lazy-bug-batch]: unit "Step 0.7: …" has no coverage — mirror it or add a divergence entry`. You resolve each twin (restate / inherit / diverge) and the suite goes green. Drift cannot land silently anywhere in the family.
- **Diverging on purpose, per twin.** When a canonical unit shouldn't exist in one twin but should in another (the `dev:kill` case: leak in bug-batch, divergence in batch-cloud), you mirror it into one and add a one-line registry divergence (with `reason`) for the other. The split is now explicit and permanent.
- **Reading the contract.** The structured registry is the single source of truth for "what differs, for which twin, and why," across all five pairs. Each derived skill's prose "Differences" table remains the human-facing view; the audit warns (soft) if a table and the registry disagree, so docs never silently rot.
- **No runtime behavior change** to any skill beyond the two closed `/lazy-bug-batch` gaps. The mechanism is an authoring-time gate, invisible during live runs.

## Technical Design

### 1. The per-pair divergence registry (canonical source of truth)

A machine-readable manifest at `user/scripts/lazy-parity-manifest.json` (JSON → stdlib only, no new dependency). Schema (illustrative):

```jsonc
{
  // Tier-2 mechanic catalogs are keyed by canonical root and reused across that root's pairs,
  // so a batch-orchestrator mechanic is defined once and asserted against both bug-batch and batch-cloud.
  "mechanic_sets": {
    "lazy-batch": [
      {"id": "cycle-dispatch-by-ref", "assert": {"type": "regex_present", "pattern": "cycle_prompt_ref"}},
      {"id": "meta-dispatch-by-ref",  "assert": {"type": "regex_present", "pattern": "dispatch_prompt_ref"}},
      {"id": "run-end-dev-kill",       "assert": {"type": "regex_present", "pattern": "dev:kill"}},
      {"id": "two-gate-terminal",      "assert": {"type": "regex_present", "pattern": "MCP-coverage audit.*completion-integrity"}},
      {"id": "output-contract-voice",  "assert": {"type": "regex_present", "pattern": "orchestrator-voice\\.md"}},
      {"id": "completeness-policy",    "assert": {"type": "regex_present", "pattern": "completeness-policy\\.md"}},
      {"id": "stop-authorization-hc10","assert": {"type": "regex_present", "pattern": "operator-authorized"}}
    ],
    "lazy": [
      {"id": "mark-terminal-two-gate", "assert": {"type": "regex_present", "pattern": "completion-integrity"}},
      {"id": "one-skill-per-invocation","assert": {"type": "regex_present", "pattern": "exactly ONE sub-skill"}},
      {"id": "preflight-first",        "assert": {"type": "regex_present", "pattern": "lazy-preflight\\.md"}},
      {"id": "completeness-policy",    "assert": {"type": "regex_present", "pattern": "completeness-policy\\.md"}}
    ],
    "lazy-status": [
      {"id": "read-only-no-mutation",  "assert": {"type": "regex_present", "pattern": "NO mutations|read-only"}},
      {"id": "runs-state-script",      "assert": {"type": "regex_present", "pattern": "state\\.py"}}
    ]
  },

  "pairs": [
    {
      "canonical": "user/skills/lazy-batch/SKILL.md",
      "derived":   "user/skills/lazy-bug-batch/SKILL.md",
      "axis": "bug", "flavor": "inherit-by-reference",
      "mechanic_set": "lazy-batch",
      "token_substitutions": [
        {"canonical": "lazy-state.py", "derived": "bug-state.py"},
        {"canonical": "COMPLETED.md",  "derived": "FIXED.md"},
        {"canonical": "__mark_complete__", "derived": "__mark_fixed__"}
      ],
      "headings": [
        {"heading": "## Step 0.52: Validation-readiness pre-screen", "coverage": "divergence",
         "reason": "Front-loading a DEFERRED_NON_CLOUD cohort is feature-curation; does not map to bug queueing.",
         "doc_anchor": "Differences table: Step 0.52 / validation-readiness"},
        {"heading": "## Step 4: Research Halt", "coverage": "divergence",
         "reason": "Bugs do not undergo Gemini deep research (operator-confirmed 2026-06-15).",
         "doc_anchor": "Differences table: Research / Gemini steps"}
        // ... one entry per canonical heading ...
      ],
      // Per-pair mechanic overrides (when a root mechanic diverges for THIS twin):
      "mechanic_overrides": []
    },
    {
      "canonical": "user/skills/lazy-batch/SKILL.md",
      "derived":   "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md",
      "axis": "cloud", "flavor": "inherit-by-reference",
      "mechanic_set": "lazy-batch",
      "mechanic_overrides": [
        {"id": "run-end-dev-kill", "coverage": "divergence",
         "reason": "Cloud defers Tauri/MCP and never boots the orchestrator-owned runtime, so there is nothing to tear down at run-end."}
      ],
      "headings": [ /* cloud-axis divergences: DEFERRED_NON_CLOUD, cloud terminals, ... */ ]
    },
    { "canonical": "user/skills/lazy/SKILL.md", "derived": "user/skills/lazy-bug/SKILL.md",
      "axis": "bug", "flavor": "restatement", "mechanic_set": "lazy", "headings": [ /* ... */ ] },
    { "canonical": "user/skills/lazy/SKILL.md",
      "derived": "repos/algobooth/.claude/skills/lazy-cloud/SKILL.md",
      "axis": "cloud", "flavor": "inherit-by-reference", "mechanic_set": "lazy", "headings": [ /* ... */ ] },
    { "canonical": "user/skills/lazy-status/SKILL.md", "derived": "user/skills/lazy-bug-status/SKILL.md",
      "axis": "bug", "flavor": "restatement", "mechanic_set": "lazy-status", "headings": [ /* ... */ ] }
  ]
}
```

- **`pairs` enumerates all five edges.** Adding a future pair (or populating `lazy-worker` if it ever gains a twin) is a data edit, not a code change.
- **`mechanic_sets` keyed by canonical root** — a root's Tier-2 mechanics are defined once and asserted against every derived twin of that root; `mechanic_overrides` on a pair express the per-pair gap-vs-divergence split (the `dev:kill`-in-cloud case).
- **`coverage` enum** = `restated | inherited | divergence`; `reason` required for `divergence`, forbidden otherwise; `doc_anchor` (optional) links to the derived skill's prose "Differences" table for the soft consistency check.
- **`flavor`** tunes which checks dominate (pointer resolution for inherit-by-reference; heading-parity + mechanics for restatement).

### 2. The parity-audit engine

`user/scripts/lazy_parity_audit.py` — importable module + CLI (`--repo-root`, optional `--pair <derived-name>` to scope, exit 0 clean / 1 drift), mirroring the established `stale_binary.py` / `surface_resolver.py` pattern. Per pair it runs:

| # | Check | Failure condition | Catches |
|---|-------|-------------------|---------|
| C1 | **Tier-1 completeness** | A `## Step`/`### sub-step` heading exists in the canonical but has no `headings[]` entry for this pair | A new canonical step with no parity decision for this twin (the new-unit detector) |
| C2 | **Coverage resolves** | A `restated`/`inherited` entry's evidence regex (after token substitution) does not match in the derived skill | A pointer/restatement removed or never written |
| C3 | **Tier-2 predicates** | A `mechanic_set` predicate (less any `mechanic_overrides`) fails against the derived skill | A sub-heading mechanic that leaked (the F2a cycle-dispatch + `dev:kill`-in-bug-batch class) |
| C4 | **No stale divergence** | A `headings`/override entry references a canonical heading/mechanic that no longer exists | Registry rot when a canonical deletes a unit |
| C5 | **Reason hygiene** | A `divergence` lacks `reason`, or a non-divergence carries one | A divergence smuggled in without justification |
| C6 (soft/warn) | **Doc-table consistency** | A `divergence` with a `doc_anchor` not found in the derived skill's prose "Differences" table | The human doc silently going stale |

C1–C5 are hard (exit 1); C6 warns. Token substitutions are applied before matching so axis vocab (`feature`↔`bug`, workstation↔`--cloud`) doesn't false-fail.

### 3. Enforcement — hard gate via the pytest harness

No CI workflow exists in this repo; the enforcement surface is the **pytest suite** (the ~407 harness tests run as part of the dev workflow). Wiring mirrors the `script + test_*.py` convention:

- `user/scripts/test_lazy_parity.py` — imports `lazy_parity_audit`, runs it against the live repo for **all five pairs**, and **asserts zero drift**. This test joins the suite; a leaked unit in any pair makes the suite red. This *is* the hard gate.
- Fixture-based engine tests in the same file (a synthetic canonical/derived pair) prove each check: missing heading → C1; broken pointer → C2; missing mechanic → C3; stale divergence → C4; reasonless divergence → C5; and a `mechanic_override` correctly suppressing C3 for the overridden twin.
- Optional `lint-skills.py --check-parity` flag for a standalone human run (parity with its `--check-projected` / `--check-capabilities` flags). Decided at implementation.

### 4. Out of scope / non-goals

- **No behavioral change to any skill** beyond the two closed `/lazy-bug-batch` gaps.
- **No deeper structural refactor** (extracting canonical bodies into shared `_components/`). The registry+audit was chosen over that rewrite for risk reasons; if the registry later shows restatement pairs (`lazy-bug`, `lazy-bug-status`) still drift heavily, incremental component-extraction is a follow-up spec.
- **`lazy-worker` and `lazy-batch-retro` are excluded** (standalone; no twin) — `lazy-batch-retro` gets only a Phase-4 registry-awareness note.
- **Bugs still do not undergo Gemini deep research**, and cloud still defers Tauri/MCP — these axis divergences are preserved and recorded, never "aligned away."
- **No change to the validate-deny guard, the stall threshold, or the prompt registry** — the audit is read-only over skill prose + a manifest.

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown. Summary: P1 closes the two known `lazy-bug-batch` leaks → P2 builds the registry + audit engine + tests proven on the fully-audited pair → P3 extends the registry to the remaining four pairs → P4 reconciles docs and hardens the gate family-wide.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| F2a cycle-dispatch mirrored | Read bug-batch §1d cycle template | Template references `cycle_prompt_ref` | `lazy-bug-batch/SKILL.md` ~line 495 |
| `dev:kill` teardown mirrored | Read bug-batch §1c.6 | `npm run dev:kill` present on run-end path | `lazy-bug-batch/SKILL.md` §1c.6 |
| New canonical step detected per twin | Add a dummy `## Step X` to `lazy-batch` with no manifest entry; run suite | C1 fails naming the step AND the affected twin | `pytest user/scripts/test_lazy_parity.py` |
| Leaked Tier-2 mechanic detected | Remove `cycle_prompt_ref` from a derived skill; run suite | C3 fails naming `cycle-dispatch-by-ref` + pair | `pytest user/scripts/test_lazy_parity.py` |
| Per-pair override works | `dev:kill` absent in `lazy-batch-cloud` | C3 suppressed for that pair (override); still required for `lazy-bug-batch` | `pytest user/scripts/test_lazy_parity.py` |
| Broken pointer detected | Corrupt an `inherited` evidence target; run suite | C2 fails | `pytest user/scripts/test_lazy_parity.py` |
| Reasonless divergence rejected | Add a `divergence` with no `reason`; run suite | C5 fails | `pytest user/scripts/test_lazy_parity.py` |
| Whole family in sync | Run suite on finished repo | Zero drift across all five pairs; suite green | `pytest user/scripts/` |
| Divergences documented | Read the registry | F5, research, `dev:kill`-in-cloud, cloud/bug axis steps carry `reason` | `lazy-parity-manifest.json` |

## Open Questions

- **Tier-2 mechanic catalog completeness (per root).** Phase 2/3 must curate each root's `mechanic_sets`. The audit only protects mechanics it knows about; the catalogs are seeded from the audited gaps and should be reviewed for other load-bearing sub-heading mechanics worth pinning per root. (Resolved-enough to start; flagged for review.)
- **Restatement-pair heading-match noise.** For `lazy`↔`lazy-bug` and `lazy-status`↔`lazy-bug-status`, a canonical heading reword surfaces as C4 (remove) + C1 (add), forcing a re-decision. Intended forcing function; Phase 3 should confirm it isn't excessively noisy given these are full restatements.
- **Excluded-skill confirmation.** `lazy-worker` and `lazy-batch-retro` are excluded as standalone. Flag if either should instead be tracked (e.g. if `lazy-worker` is considered a derivative of some canonical).

## Research References

**Gemini deep research skipped** — internal harness mechanism with root causes already diagnosed by the read-only audit passes (no external prior art to investigate), matching the precedent set by `lazy-validation-readiness`. Evidence base: the divergence-audit findings tables above (full audit of the `lazy-batch`↔`lazy-bug-batch` pair + family-wide spot-checks of the other four pairs + the git history of the recent `/lazy-batch` enhancement commits).

## Decisions resolved at authoring (operator, 2026-06-15)

- **Sync mechanism = parity-audit lint + machine-readable, per-pair divergence registry** on the existing thin-skill structure (not a deeper component refactor, not process-only).
- **Enforcement = hard gate** (pytest suite fails on drift), with the registry entry as the auditable escape hatch.
- **Scope = the whole lazy family** — five canonical↔derived pairs across the bug and cloud axes; `lazy-worker` and `lazy-batch-retro` excluded as standalone (the latter gets a registry-awareness note).
- **Coverage is per-pair** — the same mechanic can be a gap for one twin and a recorded divergence for another (the `dev:kill` case).
- **F5 = feature-only divergence; bugs skip Gemini research; cloud defers Tauri/MCP** — all recorded, never aligned away.
- **Gemini research phase for this spec = skipped** (internal harness change).
