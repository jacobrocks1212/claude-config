# Plan-Structure Authoring Gate — Feature Specification

> Add emit-time structural validation to plan-part and PHASES.md authoring: when `/write-plan`
> or `/spec-phases` write these files, a deterministic validator refuses structural defects the
> harness itself currently permits — missing per-WU `- [ ] WU-N` checklists, verification rows
> outside a recognized Runtime Verification subsection, unfilled template/boilerplate rows
> counted as work, and plan-part series that contradict declared dependency order. Every one of
> these defect classes today survives authoring and is caught only downstream, as a recovery or
> coherence-recovery meta-dispatch mid-run — the gate moves the refusal to the moment of
> authorship.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-11
**Source:** repo-exploration proposal session 2026-07-11 (transcript mining of sessions
e076ed30, 5c33b6ba; operator complaints in e076ed30 and f92a0a42)
**Friction-reduction feature:** yes

> Substantive (non-block) dependencies are **implemented mechanisms this gate reuses or
> complements**, not sibling specs:
> - `lazy_core`'s consumer-side parsers become the validator's single source of truth:
>   `_plan_wu_checkbox_counts` (~3536) + `_plan_unchecked_wus_are_verification_only` (the
>   verify-ledger plan-WU source-of-truth, commit `9a78a0c`),
>   `remaining_unchecked_are_verification_only()` (PHASES verification-row recognition,
>   ~2129–2320), `_plan_sort_key` / `_plan_series_index` / `_plan_phase_set` (~1769–1810).
> - `user/skills/_components/phases-runtime-verification.md` — the placement rule + gate-owned
>   row ban this gate mechanizes.
> - `lean-plan-files` (Complete) — plan *size/pointer* policy; fully orthogonal to structure
>   (see Scope & Dedupe).
> - `user/scripts/validate-plan.py` — today a Cognito coding-rules ExitPlanMode checker; D1
>   decides whether the structural mode extends it or lands beside it.

---

## Executive Summary

Transcript mining of two `/lazy-batch` runs (sessions e076ed30, 5c33b6ba) attributes **12 + 4
recovery/coherence dispatches — ~7% of all dispatches — to plan-format defects the harness
itself permitted at authoring time**:

- plans authored with **no per-WU checkboxes** (e076ed30 ~4639) — despite write-plan ISSUE-6
  making the `## Work Units` `- [ ] WU-N` checklist a HARD prose requirement
  (`user/skills/write-plan/SKILL.md:317–322`) and `verify-ledger` making those rows the machine
  source of truth for `deliverables_done` (commit `9a78a0c`);
- **verification rows not under a recognized "Runtime Verification" subsection**, so the
  completion machinery counts them as incomplete deliverables (~2100) — the placement rule
  exists as prose (`SKILL.md:119`, `phases-runtime-verification.md`) and the *consumer*
  heuristic exists (`remaining_unchecked_are_verification_only()`), but nothing validates
  placement when the file is written;
- **boilerplate template checkboxes counted as work** (~2146) — skeleton rows from the
  spec-phases template surviving into committed PHASES.md;
- worst case, a **phase-number-inversion routing impasse**: a corrective Phase 6 was
  prerequisite to Phase-5 plan parts, and phase-number-ordered routing structurally blocked the
  router, requiring a run-end plus bespoke hardening (e076ed30 ~4646–4658). The *router* side
  is since root-cause-fixed — `_plan_sort_key` now sorts by `-part-K` series index ahead of
  phase number (`lazy_core.py:1769–1798`, d8-effect-chains 2026-06-14) — but the fix explicitly
  **relies on an unvalidated producer invariant**: it "route[s] correctly as long as the
  producer wrote the parts in dependency order — which is the series invariant." Nothing checks
  that invariant at authoring time.

The repeated operator complaint names the pattern directly: "Seems like we frequently have
recovery agents to fix issues with PHASES.md formatting?" (e076ed30); "structural problem in
the mechanism that creates/updates PHASES.md docs?" (f92a0a42).

Each recovery dispatch is a meta-cycle (~1 Opus round-trip + commits) spent fixing a file the
harness wrote minutes earlier. The fix is the standard house move — a deterministic,
authoring-time refusal (the `phases-runtime-validation.md` / dep-block-checkpoint pattern:
audit at planning time what used to fail at pipeline end), never a mid-run recovery.

## Scope & Dedupe (what this spec deliberately does NOT cover)

- **`lean-plan-files` / the context-diet family** — plan *bytes* (pointer-based plans, contract
  single-sourcing). This gate validates *structure*; a lean pointer-based plan and a bloated
  legacy plan are equally in scope.
- **`user/scripts/validate-plan.py` as it exists** — it validates plan *content* against
  Cognito Forms coding rules (`cognito-pr-review` knowledge base, PreToolUse-on-ExitPlanMode
  design; 355 lines, YAML rule files, severity buckets). It performs **zero structural
  validation** of lazy-pipeline plan parts or PHASES.md, and is not wired into
  `/write-plan`/`/spec-phases`. D1 governs residency.
- **Consumer-side enforcement that already landed** — `verify-ledger`'s plan-WU
  source-of-truth read (`9a78a0c`), the router's series-index ordering fix, the
  completion-integrity gate, and `--gate-coverage`. Those catch or tolerate defects at
  *consumption*; this gate refuses them at *emission*. No consumer behavior changes.
- **Prose mandates that already exist** — write-plan ISSUE-6, the placement rule, the
  gate-owned-row ban (`SKILL.md:121`, `spec-phases/SKILL.md:321`), the reachability-smoke and
  no-terminal-MCP-stacking rules. The gate mechanizes the *checkable* subset; the judgment
  rules (e.g. smoke placement quality) stay prose.

## Design Decisions

### D1. Validator residency: extend `validate-plan.py` vs new lazy-core-backed CLI

- **Classification:** `product-behavior (open — recommendation below)`
- **Question:** Where does the structural validator live? The proposal directive says "wire
  into validate-plan.py (extend, don't fork)" — but the file as found is a Cognito
  coding-rules checker with no lazy_core dependency.
- **Options:**
  - **A — extend `validate-plan.py` with a `--structural` mode (recommended, per directive):**
    the existing rules-based mode is untouched (its Cognito consumers keep their CLI); a new
    `--structural <plan-or-phases-file>` mode imports the `lazy_core` parsers and runs the D2
    check set. One "validate a plan file" entry point, two modes. Cost: the script gains a
    `lazy_core` import on one path (guarded, so the rules mode still runs standalone).
  - **B — new `lazy-state.py --validate-plan-structure <path>` subcommand:** keeps structural
    logic beside its parsers and inside the parity-audited script family; but plan authoring
    happens inside `/write-plan` subagents where a self-contained file-arg CLI is the simpler
    contract, and `lazy-state.py` is already 12.7K lines.
  - **C — standalone `user/scripts/validate-plan-structure.py`:** cleanest import story, but
    forks the "validate a plan" surface the directive says not to fork.
- **Recommendation:** A, with the structural mode a thin CLI shell over functions that live in
  `lazy_core` (so `bug-state.py`/`lazy-state.py` can call the same checks in-process for the D4
  backstop without shelling out). Honors "extend, don't fork" while keeping one source of
  truth for parsing.
- **Locked (provisional — see `NEEDS_INPUT_PROVISIONAL.md`):** adopted A's surface exactly —
  `validate-plan.py --structural <file>` is the one new entry point, the legacy Cognito
  rules-mode is byte-untouched. The rule FUNCTIONS themselves live in `validate-plan.py` this
  round (importing, never editing, `lazy_core`'s existing exception-free parsers/constants),
  not hoisted into `lazy_core.py` — that hoist is a `lazy_core.py` edit and this implementation
  lane's scope is explicitly SKILLS-only (`user/scripts/lazy_core.py` + the state scripts are a
  separate active lane tonight). D4's in-process reuse therefore isn't available yet; see
  `NEEDS_INPUT_PROVISIONAL.md` D1 for the two follow-up options (hoist vs. subprocess shell-out).

### D2. Check set (v1)

- **Classification:** `mechanical-internal (recommendation below)`
- **Question:** Which structural rules does the gate enforce, and at what severity?
- **Options / Recommendation (single coherent set):** all checks are **deterministic reads of
  the authored file** — no LLM judgment:
  1. **Per-WU checklist (plan parts, ERROR):** a `## Work Units` flat checklist with ≥1
     `- [ ] WU-N` row exists, and every `WU-N` heading in the body has a matching checklist
     row (count via `_plan_wu_checkbox_counts`). Direct mechanization of ISSUE-6; kills the
     e076ed30 ~4639 class.
  2. **Verification-row placement (plans + PHASES, ERROR):** every checkbox whose text matches
     the verification vocabulary (MCP assertion / runtime verification / reachability-smoke
     tags) sits under a recognized `Runtime Verification` / `**MCP Integration Test
     Assertions:**` subsection — the *same* recognizer `remaining_unchecked_are_
     verification_only()` uses, imported not re-implemented, so gate and consumer can never
     disagree. Kills the ~2100 class.
  3. **Template-row rejection (plans + PHASES, ERROR):** unfilled placeholders (`{…}` /
     `<angle-bracket>` skeleton text lifted from the spec-phases/write-plan templates) in any
     checkbox row; template boilerplate rows (byte-match against the known skeleton row set).
     Kills the ~2146 class.
  4. **Gate-owned-row ban (plans + PHASES, ERROR):** `- [ ]` rows for Status flips / receipt
     writes / ROADMAP marks / archive moves (the `phases-runtime-verification.md` ban, today
     prose-only at authoring).
  5. **Dependency-ordered plan series (plan parts, ERROR):** every part carries a `-part-K`
     suffix + `phases:` frontmatter; and when a part's body declares a prerequisite on a
     sibling part (the "Execute parts strictly in order" contract), its series index must not
     precede that prerequisite's. Validates the series invariant `_plan_sort_key` relies on —
     the authoring-side closure of the phase-number-inversion impasse. Raw phase-number order
     is explicitly NOT required (the router no longer uses it); what must hold is
     series-index = dependency order.
  6. **Frontmatter sanity (WARN):** parseable frontmatter, `phases:` values numeric-ish (the
     `_plan_phase_set` leniency), duplicate WU numbers.
- ERRORs refuse (exit 1, named findings with line numbers); WARNs print and pass.
- **Locked:** the six-rule set as recommended, implemented and tuned against a full
  corpus run (252 real committed plan-part/PHASES.md files) rather than only synthetic
  fixtures. Two rules needed narrowing beyond the recommendation's literal wording to avoid
  false positives the corpus surfaced (both mechanical-internal refinements, not scope
  changes): rule 2's vocabulary excludes bare "runtime verification"/"VALIDATED.md" mentions
  (13/13 corpus hits were rows merely cross-referencing the section by name or naming the
  sentinel filename in unrelated prose, zero true positives) — retained vocabulary is the
  self-describing tag language the templates actually emit on a verification row ("mcp
  integration test" / "mcp test assertion" / "mcp assertion" / "reachability smoke"); rule 5's
  prerequisite extraction requires a completion word ("Phase N complete") or a dependency verb
  ("requires/depends on/blocked by Phase N") rather than a bare "Phase N" mention, after a real
  corpus row ("Entry criteria: None; establishes the pattern Phase 4 propagates") showed a
  bare-mention scan flags a FORWARD reference (this phase feeds a later one) as if it were a
  dependency in the opposite direction. Also locked: rule 1/rule 5 are N/A (not "failed") for
  `kind: retro-plan` / `kind: realign-plan` — those carry a deliberately different,
  checklist-free shape (`plan-frontmatter.md`'s kind taxonomy). Final corpus result: 4 genuine
  pre-existing violations across 252 files (3 pre-ISSUE-6 legacy plans, 1 historical gate-owned
  Status-flip row), all enumerated in `test_validate_plan.py`'s allowlist, none newly introduced.

### D3. Wiring: skill-contract gate at authoring

- **Classification:** `mechanical-internal (recommendation below)`
- **Question:** How do `/write-plan` and `/spec-phases` become unable to hand off an invalid
  file?
- **Recommendation:** both SKILLs gain a mandatory finalization step — run the validator on
  every authored/updated plan part and PHASES.md and fix findings **before** reporting done
  (the dep-block-checkpoint "fail ⇒ surface and STOP; do not write" pattern). Injected as a
  shared `_components/` block so `/write-plan`, `/write-plan-cloud`, `/plan-feature`,
  `/plan-bug`, and `/spec-phases(-batch)` all inherit it (re-project + `lint-skills.py`
  after). This is a prose trigger shelling a deterministic check — the proven
  `mcp-coverage-audit.md` → `--gate-coverage` two-layer shape.
- **Locked (with one scope refinement):** the new `_components/plan-structural-gate.md`
  component is injected into `/write-plan` (Step 4.5), `/spec-phases` (Step 6.5), and
  `/spec-phases-batch` (Step E.3.5). `/plan-feature` and `/plan-bug` inherit it for free — both
  are pure dispatch wrappers around `/spec-phases`/`/write-plan` and author no plan/PHASES
  content of their own (confirmed by reading both SKILL.md files; no separate injection needed
  or possible there). **`/write-plan-cloud` is deliberately NOT wired** — on inspection its
  output contract (`plans/cloud-*.md`, a self-contained GitHub-Copilot-cloud briefing for a
  different repo/consumer) explicitly BANS the checkbox format rules 1/2/3 assume
  (`write-plan-cloud/SKILL.md` Step 4 item 7: "No progress checkboxes"). Wiring the gate there
  would force an incompatible format onto a document engineered not to have it — this is the
  SPEC's own "Failure states" carve-out ("files outside the lazy plan/PHASES shapes... pass
  untouched") applied to a fifth named skill, not a scope reduction of the gate's actual intent.
  The validator's own path-convention scope gate excludes `plans/cloud-*.md` for the same reason.
  `repos/cognito-forms/.claude/skills/write-plan-cognito/` (a sixth, repo-scoped planner not
  named in D3) is NOT wired this round either — its live behavior is validated only on the work
  laptop per this lane's operating brief; wiring it is a clean, mechanical follow-up (same
  component injection) for that session.

### D4. Mechanical backstop for the prose trigger

- **Classification:** `product-behavior (open — recommendation below)`
- **Question:** D3's trigger is itself prose (the exact failure mode the
  mechanize-prose-only-orchestrator-contracts sibling documents). Does a state-script backstop
  enforce it, and where?
- **Options:**
  - **A — validate at plan pickup (recommended):** the probe that first routes `execute-plan`
    onto a plan part runs the same checks in-process (D1's lazy_core functions); a structural
    ERROR refuses the route and surfaces the findings + the fix command, before any execution
    begins. Still authoring-time in pipeline terms — the plan has not been executed — and
    catches plans authored outside the skills (hand-written, cloud-generated).
  - **B — skill-contract only:** no backstop; a skipped trigger reproduces today's behavior.
  - **C — PreToolUse Write/Edit hook on `plans/*.md`:** true write-time enforcement, but
    plan files are written incrementally (a part is invalid mid-write by construction) —
    write-time hooks fight the authoring process.
- **Recommendation:** A. Route-refusal precedent already exists (pending-hardening withhold);
  legacy pre-gate plans that are already mid-execution (some `- [x]` WU ticked) are exempted
  from refusal (WARN only) to avoid bricking in-flight features.
- **Locked (recommendation stands; NOT implemented this round — cross-lane):** D4 requires
  editing `lazy_core.py` / `lazy-state.py` / `bug-state.py` (the probe that routes
  `/execute-plan`), which is outside this implementation lane's scope tonight (a separate STATE
  lane is active on those files). Recommendation A stands as the intended design. See
  `NEEDS_INPUT_PROVISIONAL.md` D4 and the feature's `PHASES.md` Phase 4 for the wanted diff.
  This feature is therefore **NOT marked Complete** — Phases 1–3 (the SKILLS-lane scope: the
  validator, its rule set, and skill wiring) are done and gate-green; Phase 4 (the backstop)
  remains open.

## User Experience

- **Planner subagent:** after writing a plan part / PHASES.md, runs
  `python3 user/scripts/validate-plan.py --structural <file>`; findings name the rule, the
  line, and the fix (e.g. `WU-3 has no '- [ ] WU-3' row in ## Work Units`); fixes and re-runs
  until exit 0 before reporting the cycle done.
- **Orchestrator:** a structurally invalid plan can no longer reach `/execute-plan` — the probe
  refuses with the findings instead of dispatching a doomed cycle that ends in a recovery.
- **Operator:** the "recovery agents fixing PHASES.md formatting" pattern disappears from run
  reports; when a refusal fires it names the defect at authoring, inside the same cycle that
  created it.
- **Failure states:** unreadable/unparseable file → ERROR naming the parse failure (never a
  silent pass); files outside the lazy plan/PHASES shapes (e.g. Cognito lane plans, which have
  their own contract) are out of scope by path convention and pass untouched.

## Technical Design

```
/write-plan | /spec-phases | /plan-feature | /plan-bug   (authoring moment)
        └─ injected finalization block ──▶ validate-plan.py --structural <file>
                                                │ imports
                                    lazy_core structural checks (NEW, thin):
                                      • wu-checklist   (reuses _plan_wu_checkbox_counts)
                                      • verif-placement (reuses remaining_unchecked_…)
                                      • template-rows / gate-owned rows
                                      • series-vs-dependency order (reuses _plan_sort_key
                                        inputs: _plan_series_index, _plan_phase_set)
                                                │ same functions, in-process
lazy-state.py / bug-state.py probe ── plan pickup backstop (D4-A): ERROR ⇒ refuse route,
                                      surface findings (WARN-only for mid-execution plans)
```

- Checks are pure functions over file text (fixture-testable, no I/O beyond the read);
  ERROR/WARN vocabularies and exit codes mirror `kpi-scorecard.py --lint`.
- Rule 5's prerequisite detection reads only *declared* structure (part frontmatter + the
  explicit "depends on part-N" / prerequisite lines the write-plan template emits) — it never
  infers dependencies from prose.
- Parity: backstop lands in both `lazy-state.py` and `bug-state.py` via shared `lazy_core`
  functions (`lazy_parity_audit.py` green).

## KPI Declaration

- kpi: cycles-per-completion

Recovery and coherence-recovery dispatches are meta-cycles, so the registry's
`cycles-per-completion` row is the coarse channel this gate must move. The defect-specific
rate is drafted below; its dedicated selector (e.g. `plan-format-recovery-dispatch-count`)
is registered in `kpi-scorecard.py` `_SOURCES` at implementation and the row re-pointed (the
`canary-trip-precision` registration precedent) — until then it points at the live
`deny-ledger` process-friction channel where these recoveries are ledgered/clustered.

```json
{
  "id": "plan-format-recovery-dispatch-rate",
  "system": "plan-authoring",
  "title": "Recovery/coherence dispatches attributable to plan/PHASES structural defects",
  "friction": "Structurally defective plan parts and PHASES.md files pass authoring unvalidated and surface downstream as recovery/coherence meta-dispatches (~7% of all dispatches in the mined runs) or, worst case, a routing impasse requiring run-end + bespoke hardening.",
  "signal": { "source": "deny-ledger", "selector": "process-friction-count" },
  "unit": "dispatches/30d",
  "direction": "down-is-good",
  "baseline": { "value": 16, "captured_at": "2026-07-11", "window": "30d", "provenance": "retro-derived" },
  "band": null,
  "review_by": "2026-10-15",
  "notes": "Baseline = 12+4 plan-format-triggered recovery/coherence dispatches mined from sessions e076ed30 + 5c33b6ba (~7% of all dispatches; window approximates the mined-run period). Post-gate expectation: near-zero — the defect classes are refused at authoring. Retro-graded until the dedicated selector lands."
}
```

## Implementation Phases

- **Phase 1 — structural checks in `lazy_core` + `--structural` CLI mode (~1–2 sessions).**
  Rules 1–4 + 6 as pure functions (reusing the named parsers); `validate-plan.py --structural`
  shell; pytest fixtures red/green per rule (including a real-world corpus check against the
  repo's existing committed plans — pre-existing violations enumerated, not silently accepted).
- **Phase 2 — series-vs-dependency ordering (rule 5) (~1 session).** Declared-prerequisite
  extraction + series-index consistency check; fixtures reproducing the e076ed30 inversion
  (part-1=Phase 6 prerequisite to part-2=Phase 5 passes; the inverted authoring refuses).
- **Phase 3 — skill wiring (~1 session).** Shared finalization component injected into the five
  authoring skills; re-project + `lint-skills.py`; template skeleton row set exported for
  rule 3.
- **Phase 4 — pickup backstop (~1 session).** In-process validation at first `execute-plan`
  routing in both state scripts; mid-execution exemption; parity audit green.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Missing WU checklist refused | plan part without `- [ ] WU-N` rows | exit 1 naming missing WUs | pytest fixtures |
| Misplaced verification row refused | verification checkbox under `### Deliverables` | exit 1 with line number | pytest fixtures |
| Recognizer parity | file passing the gate | `remaining_unchecked_are_verification_only()` agrees (same function) | pytest cross-check |
| Template rows refused | skeleton `{placeholder}` checkbox | exit 1 naming the row | pytest fixtures |
| Gate-owned row refused | `- [ ] flip SPEC Status` row | exit 1 citing the ban | pytest fixtures |
| Inversion caught at authoring | part series contradicting declared prerequisite | exit 1; the d8/e076 shape reproduced | pytest fixtures |
| Valid high-phase prerequisite passes | part-1=Phase 6 before part-2=Phase 5, declared order | exit 0 | pytest fixtures |
| Backstop refuses route | structurally invalid fresh plan at pickup | probe refusal + findings, no dispatch | state-script self-tests |
| Mid-execution exemption | invalid plan with ticked WUs | WARN, route proceeds | state-script self-tests |
| Cognito rules mode untouched | legacy CLI invocation | byte-identical behavior | existing tests |

## Open Questions

- D1 residency and D4 backstop are the operator-facing calls (recommendations: extend
  `validate-plan.py`; pickup-time backstop) — surface at `/spec` finalization.
- Whether rule 3's skeleton set is maintained as literal strings exported from the templates or
  as a marker convention in the templates themselves (implementation detail, Phase 3).

## Research References

- Sessions e076ed30 (~2100, ~2146, ~4639, ~4646–4658), 5c33b6ba — mined dispatch attribution;
  operator complaints e076ed30, f92a0a42.
- `user/scripts/lazy_core.py:1769–1798` — `_plan_sort_key` series-index root-cause fix
  (d8-effect-chains 2026-06-14) and its explicitly unvalidated producer invariant; `:3536`
  `_plan_wu_checkbox_counts`; ~2129–2320 verification-row recognizer.
- Commit `9a78a0c` — verify-ledger plan-WU source-of-truth (`deliverables_done` reads plan-WU
  checkboxes; "mandatory since write-plan ISSUE-6").
- `user/skills/write-plan/SKILL.md:117–121, 317–348` — ISSUE-6, placement rule, gate-owned-row
  ban; `user/skills/spec-phases/SKILL.md:315–323`;
  `user/skills/_components/phases-runtime-verification.md`.
- `user/scripts/validate-plan.py` — current Cognito-rules scope (dedupe basis);
  `docs/features/lean-plan-files/SPEC.md` — size/pointer scope (dedupe basis).
