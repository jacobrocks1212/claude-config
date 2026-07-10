# Park-Provisional Acceptance — Feature Specification

> A third decision tier between the D2 two-key mechanical auto-accept and the plain product-class park: in `--park --park-provisional` mode, a low-divergence product-class `NEEDS_INPUT.md` whose every decision carries a recommendation is PROVISIONALLY accepted (recommended option taken, pipeline continues implementing), durably marked `NEEDS_INPUT_PROVISIONAL.md`, and re-surfaced to the operator for ratify-or-redirect before the feature can ever complete.

**Status:** In-progress
**Priority:** P1
**Last updated:** 2026-07-09
**Friction-reduction feature:** yes

**Depends on:**

- feature-budget-guard-and-skip-ahead — composes — Reuses the `--park-*` skip-branch shape in `compute_state` queue selection and the run-scoped surfaced-list pattern (`_PARKED` / probe keys).
- parallel-worktree-batch-execution — composes — Lane probes carry the same park flags; the `__provisional_accept__` route runs inside a lane exactly like any other pipeline-advancing cycle (P1 disjoint spec-dir ownership covers its writes).

---

## Executive Summary

Overnight `--park` runs advance the queue past `NEEDS_INPUT.md` / `BLOCKED.md` halts, but a parked feature itself makes **zero further progress** until the operator answers at the flush. The existing D2 two-key auto-accept (parked-flush Step 2.5) relaxes this only for `class: mechanical` + `audit_concurs: true` sentinels; every product-class decision — even one with a strong recommendation and trivially-reversible consequences — stalls its feature for the whole run.

This feature adds a **provisional acceptance** tier, opt-in via `--park-provisional` (a modifier of `--park-needs-input`):

1. **Accept at park time, not flush time.** When the probe walk reaches a feature whose `NEEDS_INPUT.md` is provisional-eligible, it routes the pseudo-skill `__provisional_accept__` instead of parking. The orchestrator runs the script-owned `--provisionalize-sentinel` action (append `## Resolution` with `resolved_by: auto-provisional` + the HEAD `decision_commit`, rename to `NEEDS_INPUT_PROVISIONAL.md`), dispatches the standard apply-resolution subagent to propagate the recommended choices into SPEC/PHASES, and the feature keeps moving — through phases, plan, implementation, even MCP validation.
2. **Divergence two-key is the rework-prevention rail.** Eligibility requires TWO independent low-divergence grades: the producer's `divergence:` and the input-audit's `audit_divergence:`, both ∈ {`isolated`, `contained`}. A `structural` grade from either — the options fork architecture, data model, or user-visible workflow — always parks for the operator. The recorded `decision_commit` bounds any later redirect to the exact downstream diff.
3. **Ratification is structurally guaranteed.** `NEEDS_INPUT_PROVISIONAL.md` is workable to park-mode probes but (a) a **non-park** probe halts on the new `needs-ratification` terminal, routed to a ratify-or-redirect resolution mode; (b) park-mode Step 10 **parks** the feature (`sentinel_kind: provisional`) instead of emitting `__mark_complete__`, so the run-end flush surfaces ratification; and (c) `apply_pseudo __mark_complete__` / `__mark_fixed__` **mechanically refuses** while an unratified provisional sentinel exists — a provisionally-decided feature can never silently complete.
4. **Redirect routes to bounded correction.** If the operator overrides the recommendation at ratification, the apply-resolution subagent propagates the changed choice into SPEC/PHASES and authors a `**Phase kind:** corrective` phase scoped by `git diff <decision_commit>..HEAD`, and the feature re-enters the queue naturally.

Default behavior — no flags, or plain `--park` without the new token — is byte-identical except where a `NEEDS_INPUT_PROVISIONAL.md` file already exists on disk, which only a provisional run can create.

## User Experience

The "user" is the operator running `/lazy-batch <N> --park --park-provisional` (typically unattended/overnight) and reviewing the run afterward.

- **During the run:** each provisional acceptance emits a PushNotification — `provisional-accept {feature_name} — {N} decision(s) auto-accepted on recommendation (divergence: {grade}); ratification pending` — and a T5 chat line. Structural or ungraded decisions park exactly as today (with the standard park notification).
- **Run report:** a new digest table, `### Provisionally accepted decisions (--park-provisional)`, mirrors the two-key table: feature, decision, chosen option, divergence grades, `decision_commit`, sentinel path.
- **Run-end flush:** features that finished all other work but hold an unratified provisional sentinel appear in the flush with the ratification affordance (see `provisional-ratification.md`): per decision — **Ratify** (keep the auto-accepted recommendation; neutralize the sentinel), **Redirect** (choose a different option; corrective propagation), or **Defer** (leave provisional; completion stays blocked).
- **Next non-park run:** any surviving `NEEDS_INPUT_PROVISIONAL.md` halts that feature on `needs-ratification`, and the orchestrator runs the same ratification affordance inline (Step 1g-ratify) — the operator is always re-asked before completion; nothing is silently finalized.

## Technical Design

### State machine (`lazy-state.py` / `bug-state.py`, helpers in `lazy_core.py`)

- **CLI:** `--park-provisional` (both scripts). Supplying it without `--park-needs-input` is a hard CLI error (exit 2). `compute_state(..., park_provisional=False)` param threaded like the other park flags.
- **Eligibility predicate** (`lazy_core.provisional_eligibility(sentinel_path)` — deterministic, frontmatter + cheap body checks, FAIL-CLOSED; returns `(eligible, reason)`):
  - frontmatter parses; `kind: needs-input`; `decisions:` a non-empty list (≤4);
  - NOT two-key mechanical (`class: mechanical` AND `audit_concurs: true` → the existing, stronger flush path wins);
  - `written_by` is NOT `completion-integrity-gate` (integrity gaps are never recommendations);
  - `divergence` ∈ {`isolated`, `contained`} AND `audit_divergence` ∈ {`isolated`, `contained`} (two-key; any absence, `structural`, or unknown value → ineligible);
  - body contains `## Decision Context` and at least `len(decisions)` `**Recommendation:**` blocks.
- **Routing (park mode, walk loop):** in the `park_needs_input` NEEDS_INPUT.md branch, when `park_provisional` is also set and the predicate passes, return a routed state `sub_skill: "__provisional_accept__"`, `sub_skill_args: <spec_path>`, `current_step: "Step 3.5: needs-input (provisional accept)"` instead of appending to `_PARKED`. Predicate fails → park exactly as today (the `reason` is `_diag`'d). BLOCKED.md precedence over the needs-input branch is unchanged.
- **`--provisionalize-sentinel <path>` CLI action** (shared implementation `lazy_core.provisionalize_sentinel(path, repo_root)`): re-validates the full predicate (plus rigorous per-H3 recommendation extraction — the first bold option label of each `**Recommendation:**` line); appends a `## Resolution` block (`resolved_by: auto-provisional`, `decision_commit: <git rev-parse HEAD>`, per-decision `**Choice:**` = recommended label); renames `NEEDS_INPUT.md → NEEDS_INPUT_PROVISIONAL.md` (git-mv-aware, collision-refusing). Refuses with zero writes on ANY validation failure. Returns JSON `{ok, refused, choices, divergence, audit_divergence, decision_commit, renamed_to}`.
- **`NEEDS_INPUT_PROVISIONAL.md` semantics:**
  - Park-mode probes: the file is NOT a halt and NOT parked mid-walk — the feature advances normally. All `_PROVISIONAL`-bearing features observed during the walk are surfaced in a park-mode-only `provisional[]` probe key (entries via `build_parked_entry`, whose `sentinel_kind` gains `"provisional"`).
  - Non-park probes: new Step 3.6 — halt with `terminal_reason: "needs-ratification"`, `current_step: "Step 3.6: needs-ratification"`. `NEEDS_INPUT.md` takes precedence when both exist (a NEW decision outranks a pending ratification).
  - Park-mode Step 10 (and the bug pipeline's mark-fixed emission point): if the file exists, do NOT emit `__mark_complete__`/`__mark_fixed__`; park the feature (`_PARKED` entry, `sentinel_kind: "provisional"`) and continue the walk — ratification is deferred to the flush.
- **Completion backstop:** `lazy_core.apply_pseudo` `__mark_complete__` / `__mark_fixed__` refuses (`refused: "unratified provisional decision(s) — NEEDS_INPUT_PROVISIONAL.md present"`, zero writes) while the file exists. The prose layer (`completion-integrity-gate.md`) gains matching precondition 2c.
- **Ratification neutralization** reuses `--neutralize-sentinel` verbatim (`NEEDS_INPUT_PROVISIONAL.md → NEEDS_INPUT_PROVISIONAL_RESOLVED_<date>.md`); the `kind:` field never flips (filename is the state carrier, per the established rename convention).

### Sentinel schema (`sentinel-frontmatter.md`)

- New optional file-level `NEEDS_INPUT.md` keys: `divergence` and `audit_divergence`, closed enum `isolated | contained | structural` — file-level = the MOST SEVERE grade across the file's decisions (mirrors the file-level `class:` convention). `divergence` is authored by the producer (cycle subagent); `audit_divergence` ONLY by the Step 1d.5 input-audit. Absent ⇒ treated as `structural` (conservative default — never provisional-eligible).
- Grade meanings: `isolated` — the options differ inside one module/doc surface; redirecting later is a small local edit. `contained` — a few files, no architectural fork; redirect is a bounded corrective phase. `structural` — the options fork architecture, persistent data, or user-visible workflow; redirect would be significant rework → NEVER provisional.
- `NEEDS_INPUT_PROVISIONAL.md` documented as a lifecycle state of `kind: needs-input` (rename, not a new kind), with the resolution-marker vocabulary gaining `resolved_by: auto-provisional` and the `## Ratification` block (`outcome: ratified | redirected`, `ratified_by: operator`).

### Orchestration (skills + components)

- `/lazy-batch` Step 0 parses `--park-provisional` (error without `--park`); Step 1a appends it to every probe (and to `--emit-prompt` calls); Step 1c.5 gains the `__provisional_accept__` pseudo-skill (script action → commit → apply-resolution dispatch with `resolution_kind: provisional` — propagate ONLY, never neutralize → notification → digest → meta-cycle accounting); a Step 1g-ratify routes `needs-ratification` (non-park) through the new shared `provisional-ratification.md`; the parked-flush gains a Step 2.7 branch for `sentinel_kind: provisional` entries using the same component; the batch report gains the provisional digest table.
- `dispatch-apply-resolution.md` gains a `resolution_kind: provisional` section (propagate the auto-accepted choices; DO NOT neutralize — the `_PROVISIONAL` sentinel is the ratification claim-check) and a `resolution_kind: ratify-redirect` section (propagate the operator's changed choice, author the corrective phase scoped by `decision_commit`, then neutralize).
- Parity: `lazy-bug-batch` and `lazy-batch-cloud` mirror by reference through the shared components; `/lazy-batch-parallel` passes the flag through to lane probes (D10).

## Locked Decisions

Resolved 2026-07-09 under the operator's completeness-first standing policy (autonomous implementation session; each records its rationale — flagged for operator review in the session summary).

1. **Flag semantics → `--park-provisional` is a strict modifier of `--park-needs-input`.** Supplying it alone is a hard CLI error on both state scripts, and `/lazy-batch --park-provisional` without `--park` is an argument error. Rationale: provisional acceptance only makes sense where parking is the alternative; a standalone flag would create an untested third mode matrix.
2. **Acceptance timing → park time (probe-routed pseudo-skill), not flush time.** The probe routes `__provisional_accept__` the moment the walk reaches the eligible sentinel, so the feature keeps implementing in the same run — the whole point of the tier. The flush-time path (where the two-key lives) would strand the feature until queue exhaustion. The acceptance is idempotent and crash-safe: until the rename lands, every re-probe returns the same route.
3. **Two-key divergence grading, file-level, fail-closed.** Eligibility = `divergence` (producer) AND `audit_divergence` (independent input-audit) both ∈ {isolated, contained}. File-level MOST-SEVERE grading mirrors the established file-level `class:` convention; absent grades are `structural`. This is the operator's requested "more robust prevention mechanism": two independent Opus opinions must BOTH assess the rework blast radius as low before any product-class recommendation is provisionally taken.
4. **Two-key mechanical precedence.** A sentinel qualifying for the D2 two-key (`class: mechanical` + `audit_concurs: true`) parks and resolves via the existing flush auto-accept — FULL resolution, no ratification debt — rather than being provisionally accepted. The structural guarantee that two-key auto-accept lives exclusively in `parked-flush.md` is preserved untouched.
5. **`NEEDS_INPUT_PROVISIONAL.md` is a filename state, not a new `kind`.** Rename via the acceptance action; ratification neutralizes via the existing `--neutralize-sentinel` rename machinery. Keys the same "filename is the state carrier" convention as `_RESOLVED_` (kind-flips are the documented real-bug anti-pattern).
6. **Triple-layer completion backstop.** (a) park-mode Step 10 parks instead of emitting the completion pseudo-skill; (b) non-park Step 3.6 halts `needs-ratification` before Step 10 is reachable; (c) `apply_pseudo` mechanically refuses with zero writes. Layer (c) is the load-bearing one — layers (a)/(b) exist to keep the loop honest and churn-free.
7. **Redirect correction is corrective-phase-shaped and commit-scoped.** The recorded `decision_commit` (HEAD at acceptance) bounds `git diff <decision_commit>..HEAD` — the only code that could embody the provisional choice. The redirect path authors a `**Phase kind:** corrective` phase (does not re-stale retro machinery) rather than reverting commits: forward-fix over rollback, matching the pipeline's existing corrective-phase convention.
8. **Never provisional:** Gemini research gates (`needs-research` routing untouched), `BLOCKED.md` of any kind, structural/ungraded divergence, malformed sentinels (missing rich body / recommendations), `written_by: completion-integrity-gate` sentinels, and two-key-mechanical sentinels (better path exists, D4).
9. **Bug-pipeline parity: full mirror.** `bug-state.py` gains the same flag, predicate, route, terminal, Step-10-park and `__mark_fixed__` refusal; the shared components already bind both pipelines. (`lazy_parity_audit.py` must stay exit 0.)
10. **Parallel composition: lane-local acceptance, coordinator-serial ratification.** `/lazy-batch-parallel` passes `--park-provisional` through to lane probes; `__provisional_accept__` is a pipeline-advancing route executed INSIDE the lane (docs-only writes in the lane's own `docs/features/<slug>/`, committed on the lane branch — P1 disjoint ownership holds). P6 park-on-sentinel is unchanged for everything else; a lane that ends the run with an unratified provisional sentinel is ported/flushed at the main root exactly like other parked sentinels, and ratification runs in the coordinator's serial resolution modes.
11. **Probe surface: `provisional[]` key, park mode only.** Mirrors the `parked[]` gating exactly (present iff park mode), so default output stays byte-identical. Non-park probes surface provisional state only through the `needs-ratification` terminal.
12. **`__provisional_accept__` is a meta cycle.** It resolves process state rather than advancing SPEC/plan/implementation content; matches the accounting of every other resolution-mode dispatch.
13. **Park-mode stub-spec dispatches are sentinel-mediated (no interactive brainstorm).** The Step 4.5 stub-spec `/spec` cycle subagent is normally "allowed and expected" to call `AskUserQuestion` during Phase-1 brainstorming (HARD CONSTRAINT 5 carve-out) — in an unattended park/provisional run (and inside a `/lazy-batch-parallel` lane) that is a silent hang no park flag can catch, because no `NEEDS_INPUT.md` ever lands for the probe to park on. Mechanism (locked): `emit_cycle_prompt` gains a `park_mode` parameter (threaded from the probe's park flags by both state scripts' `--emit-prompt` handlers), the `@section` grammar gains an optional `park=park|both` filter (default `both` — absent attribute keeps every existing section selected, byte-identical), and `cycle-base-prompt.md` gains a `park=park`, `skills=spec` section: the dispatched `/spec` MUST NOT call `AskUserQuestion`; it drafts the baseline first (the "Phase 1 under `--batch`" contract), applies D7 in-cycle for scope-class, and surfaces the ≤4 genuinely baseline-gating product forks via `NEEDS_INPUT.md` — rich body, recommendation-first options, and a self-graded `divergence:` — so the standard park/provisional machinery picks them up on the next probe (the input-audit then supplies `audit_divergence` as Key 2). Non-park dispatch prompts are byte-identical; `/lazy-batch`'s stub-spec disambiguation table gains the park-mode row.

## Ratification affordance (shared component `provisional-ratification.md`)

Consumed by (a) Step 1g-ratify (`needs-ratification`, non-park) and (b) the parked-flush provisional branch (park mode, run end). Zero-context briefing re-prints the `## Decision Context` AND the `## Resolution` (what was provisionally chosen, when, at which commit), then one `AskUserQuestion` per sentinel (≤4 questions):

- **Ratify (Recommended)** — keep the auto-accepted choice; append `## Ratification` (`outcome: ratified`), neutralize the sentinel. No further dispatch (SPEC/PHASES already reflect the choice).
- **Redirect to <option>** — one option per remaining alternative; append `## Ratification` (`outcome: redirected`, the new Choice), dispatch the apply-resolution subagent (`resolution_kind: ratify-redirect`): propagate the changed choice into SPEC/PHASES, author the corrective phase scoped by `decision_commit`, neutralize the sentinel.
- **Defer** — leave `NEEDS_INPUT_PROVISIONAL.md` in place; the feature stays completion-blocked and re-surfaces next run.

## KPI Declaration

**Friction-reduction feature:** yes — the tier exists to cut the operator-blocking dwell of parked product decisions during unattended runs, and to keep per-feature cycle spend flowing instead of stalling behind decision halts. Declared against existing registry rows:

- kpi: halt-dwell-p50
- kpi: cycles-per-completion

## MCP validation

This repo has no MCP-reachable surface (no `src-tauri/`, no `package.json`); validation is the two state scripts' in-file `--test` harnesses (new fixtures for every state/flag added), `pytest test_lazy_core.py`, and `lazy_parity_audit.py` exit 0 — the same structural-skip class every completed claude-config feature carries.

## Open Questions

- **vN — per-decision divergence grading.** v1 grades file-level (most severe wins), which can park a 3-decision file for one structural decision. A per-decision `divergences: []` parallel list (index-matched like the H3 pairing) could split a mixed file into provisional + parked halves; deferred until field data shows mixed files are common.
- **vN — redirect-cost telemetry.** Record redirected-vs-ratified counts per divergence grade in the telemetry ledger to validate (or tighten) the two-grade eligibility bar empirically.
