# Implementation Phases — Plan-Structure Authoring Gate

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress

**MCP runtime:** not-required — pure claude-config harness mechanics (a stdlib Python
validator CLI mode, pytest fixtures, and orchestrator-prose skill wiring). No Tauri app, no
MCP-reachable surface in this repo; validation is `pytest` + the real-corpus scan +
`lint-skills.py`/`project-skills.py`/`generate-coupled-skills.py --check`/
`lazy_parity_audit.py`. This is the `standalone — no app integration` untestable class.

## Cross-feature Integration Notes

No hard `**Depends on:**` block in the SPEC. Substantive reuse (not sibling-feature
dependencies): `lazy_core.py`'s existing consumer-side parsers
(`_plan_wu_checkbox_counts`, `remaining_unchecked_are_verification_only`,
`_VERIFICATION_ONLY_MARKER`, `_VERIFICATION_SECTION_RE`, `_DELIVERABLES_SECTION_RE`,
`_PLAN_PART_RE`) — imported, never edited; `user/skills/_components/
phases-runtime-verification.md` — the placement rule + gate-owned-row ban this gate
mechanizes; `user/scripts/validate-plan.py` — the pre-existing Cognito-rules validator this
gate's `--structural` mode is added beside (byte-untouched).

## Lane scope note (READ BEFORE ASSUMING Phase 4 is missing by accident)

This feature was implemented under an explicit two-lane split: a SKILLS lane (this work —
`user/skills/**`, `user/scripts/validate-plan.py` + its test) and a separate, concurrently-active
STATE lane (`user/scripts/lazy_core.py` + the state scripts + their tests). **Phase 4 (the
pickup backstop) requires editing `lazy_core.py`/`lazy-state.py`/`bug-state.py` and is therefore
explicitly out of this lane's scope** — not an oversight, not deferred by uncertainty. See
`NEEDS_INPUT_PROVISIONAL.md` D4 for the wanted cross-lane diff. **The feature is NOT marked
Complete** as a direct consequence (per the operator's park-provisional protocol: a recorded
`NEEDS_INPUT_PROVISIONAL.md` means COMPLETED.md and a Status flip to Complete are withheld).

---

### Phase 1: Structural checks (rules 1, 2, 3, 4, 6) + `--structural` CLI mode

**Scope:** The `validate-plan.py --structural <file>` entry point; rules 1 (WU checklist), 2
(verification-row placement), 3 (template-row rejection), 4 (gate-owned-row ban), and 6
(frontmatter sanity, WARN); pytest fixtures per rule; a real-corpus check against every
committed plan part / PHASES.md in this repo.

**Deliverables:**
- [x] `user/scripts/validate-plan.py` — new `--structural` mode dispatched from `main()` before
  the legacy two-positional-arg parsing (byte-identical legacy behavior preserved and verified).
  `StructuralFinding`, `_load_lazy_core` (importlib load, not a bare `import` — resilient to
  invocation via the `~/.claude/scripts` symlink), `_read_frontmatter_safe` (exception-safe
  frontmatter reader — see `RESEARCH_SUMMARY.md` finding 2 for why the `lazy_core` original
  isn't called directly), `_local_plan_series_index`/`_local_plan_phase_set` (exception-safe
  siblings of the `lazy_core` originals, reusing the imported `_PLAN_PART_RE` constant),
  `_iter_checkbox_rows` (fence-aware section-tracking shared by rules 2/3), rules 1/2/3/4/6 as
  pure functions, `_classify_structural_target` (path-convention scope gate: `PHASES.md` /
  `plans/*.md` / `plans/cloud-*.md` excluded / everything else out-of-scope), `run_structural_
  checks(path) -> (lines, exit_code)`, `main_structural`.
- [x] `user/scripts/test_validate_plan.py` (new) — 29 tests: per-rule red/green fixtures
  (`TestRuleWuChecklist`, `TestRuleVerificationPlacement`, `TestRuleTemplateRows`,
  `TestRuleGateOwnedRows`, `TestRuleFrontmatterSanity`), scope/IO edge cases
  (`TestScopeAndIo` — out-of-scope files, `plans/cloud-*.md` exclusion, missing file, CLI exit
  code), the recognizer-parity cross-check (`TestRecognizerParityCrossCheck` — a file this gate
  passes/fails and `lazy_core.remaining_unchecked_are_verification_only` agree on the same
  fixture text), and `TestRealCorpusCheck` (walks every real `docs/features/**` +
  `docs/bugs/**` plan/PHASES file; asserts the violation set matches an explicit, one-line-reason
  allowlist — a NEW violation anywhere in the tree fails the test).
- [x] Real-corpus check run and DOCUMENTED (not silently accepted): 252 real files scanned; two
  rules (2 and 3) needed narrowing beyond the SPEC's literal recommendation wording to eliminate
  false positives the corpus surfaced (see `SPEC.md` D2's locked note and
  `RESEARCH_SUMMARY.md` finding 3 for the exact before/after). Final result: 4 genuine
  pre-existing violations, 0 false positives — enumerated in the test's allowlist.

**Minimum Verifiable Behavior:** `python3 user/scripts/validate-plan.py --structural
<plan-or-PHASES-file>` exits 1 with a named finding (rule id, line, fix) on a file missing its WU
checklist, and exits 0 on every one of the 248 non-violating real corpus files.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] <!-- verification-only --> `python3 -m pytest user/scripts/test_validate_plan.py -q` — 29
  passed, including the live 252-file real-corpus scan. *(Evidence: `SKIP_MCP_TEST.md` — pytest
  run this session, see PHASES.md completion notes below.)*

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config has no
Tauri/MCP app in scope for this feature). Verification is `pytest`.

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/validate-plan.py` (extended), `user/scripts/
test_validate_plan.py` (new).

**Testing Strategy:** Hermetic `tempfile.TemporaryDirectory()` fixtures per rule (red + green);
a live scan over the real committed corpus (not a copy) asserted against an explicit
allowlist so drift is caught going forward, not just measured once.

**Integration Notes for Next Phase:** Phase 2's series-order rule reuses this phase's
`_local_plan_series_index`/`_local_plan_phase_set`/`_ENTRY_CRITERIA_RE` scaffolding; Phase 3's
skill wiring shells this phase's `run_structural_checks` CLI entry point.

---

### Phase 2: Series-vs-dependency ordering (rule 5)

**Scope:** Declared-prerequisite extraction from a plan part's Entry-criteria/Prerequisites
text; cross-reference against sibling `-part-K` files' `phases:` sets; series-index-vs-
dependency-order violation detection; fixtures reproducing the e076ed30 phase-number-inversion
shape (and the corrected, non-inverted shape).

**Deliverables:**
- [x] `rule_series_dependency_order` + `_sibling_glob_pattern` + `_extract_prereq_phases` (with
  `_PREREQ_PHASE_COMPLETE_RE` / `_PREREQ_PHASE_VERB_RE`) in `user/scripts/validate-plan.py`.
  N/A (no findings, not "passed") for a plan with no `-part-K` series — single-part and legacy
  plans are unaffected.
- [x] Fixtures in `test_validate_plan.py::TestRuleSeriesDependencyOrder`: the e076ed30 inversion
  shape (part-1=Phase 5 declaring "Phase 6 complete" as its entry criterion while Phase 6 is
  scheduled in part-2 — refused), the corrected shape (part-1=Phase 6 as prerequisite, part-2=
  Phase 5 depends on it — series index 1 < 2 matches dependency order, passes despite the
  inverted phase numbers), the real corpus false-positive shape (a forward-looking "Phase N
  propagates" mention that is NOT a dependency declaration — must not trip), and the
  single-part-plan N/A case.

**Minimum Verifiable Behavior:** A fixture pair with part-1 declaring "Phase 6 complete" as its
Entry criterion while Phase 6 lives in part-2 exits 1 naming the inversion; the corrected pair
(part-1=Phase 6, part-2=Phase 5 depending on it) exits 0.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] <!-- verification-only --> `python3 -m pytest user/scripts/test_validate_plan.py -k
  SeriesDependencyOrder -q` — all 4 fixtures pass (inversion refused, valid high-phase
  prerequisite passes, forward-mention not flagged, single-part N/A). *(Evidence:
  `SKIP_MCP_TEST.md`.)*

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (the `--structural` CLI mode and shared scaffolding).

**Files likely modified:** `user/scripts/validate-plan.py`, `user/scripts/test_validate_plan.py`.

**Testing Strategy:** Same hermetic tempdir-fixture approach as Phase 1, plus the real-corpus
scan (Phase 1's `TestRealCorpusCheck`) already exercises rule 5 across every real multi-part
plan series in the repo (0 violations found on the real corpus, after the forward-mention fix).

**Integration Notes for Next Phase:** Phase 3 wires the finalization step that shells the CLI
mode both prior phases completed — no further validator changes needed.

---

### Phase 3: Skill wiring

**Scope:** The shared `_components/plan-structural-gate.md` finalization-step component;
injection into `/write-plan`, `/spec-phases`, and `/spec-phases-batch`; confirmation that
`/plan-feature` and `/plan-bug` inherit it for free (pure dispatch wrappers, no separate
injection point); the `/write-plan-cloud` exclusion (documented, not an oversight); re-projection
+ skill-lint clean.

**Deliverables:**
- [x] `user/skills/_components/plan-structural-gate.md` (new) — why/when-it-runs/what-it-checks/
  residency-note/coupling-note, modeled on `mcp-coverage-audit.md`'s shape.
- [x] `user/skills/write-plan/SKILL.md` — new "Step 4.5: Structural Gate" between the frontmatter
  rules and "Multi-part Output Reporting" (files are written by this point in the flow; the gate
  runs before the final report).
- [x] `user/skills/spec-phases/SKILL.md` — new "Step 6.5: Structural Gate" between Step 6 (the
  subagent PHASES.md write + mandatory review gate) and Step 7 (cross-link back to SPEC).
- [x] `user/skills/spec-phases-batch/SKILL.md` — new "Step E.3.5: Structural Gate" between the
  holistic cross-feature review (Step E.3) and the commit step (Step E.4) — this skill authors
  PHASES.md content directly via its own subagent dispatch prompts (unlike `/plan-feature`/
  `/plan-bug`), so it needed its own injection point.
- [x] `/plan-feature` and `/plan-bug` — read both `SKILL.md` files in full; confirmed neither
  authors plan/PHASES content directly (both exclusively dispatch `/spec-phases`/`/write-plan`
  as sub-skills) — no injection needed; documented in `SPEC.md` D3's locked note.
- [x] `python3 user/scripts/project-skills.py` — clean re-projection (88 skills, 100 components,
  0 errors, all 3 repo projections). Spot-checked the projected `write-plan`, `spec-phases`, and
  `spec-phases-batch` `SKILL.md` files: the component expands verbatim at the new step headings.
- [x] `python3 user/scripts/lint-skills.py --check-projected --check-capabilities` — clean (no
  broken/embedded `!cat` patterns, no unexpanded patterns in projected output, no capability
  namespace pollution).

**Minimum Verifiable Behavior:** The projected `write-plan/SKILL.md`, `spec-phases/SKILL.md`, and
`spec-phases-batch/SKILL.md` each contain the fully-expanded `## Plan-Structure Authoring Gate`
component body at their respective new step headings (confirmed by grep against the projected
output this session).

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] <!-- verification-only --> `python3 user/scripts/project-skills.py` clean +
  `python3 user/scripts/lint-skills.py --check-projected --check-capabilities` clean this
  session. *(Evidence: `SKIP_MCP_TEST.md`.)*
- **DEFERRED (cross-lane, not a completion blocker for Phases 1-3):** a live `/write-plan` or
  `/spec-phases` cycle actually invoking this gate end-to-end (the prose trigger itself is
  orchestrator-invoked at the next real planning cycle in this or another repo — mirrors the
  existing `mcp-coverage-audit.md`/`spec-friction-kpi-gate.md` precedent's own deferred-live-run
  notes). The deterministic half (the CLI the prose shells) is fully covered by Phase 1/2's
  pytest suite + the real corpus scan.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–2 (the validator + full rule set must exist before wiring the
trigger that shells it).

**Files likely modified:** `user/skills/_components/plan-structural-gate.md` (new),
`user/skills/write-plan/SKILL.md`, `user/skills/spec-phases/SKILL.md`,
`user/skills/spec-phases-batch/SKILL.md`.

**Testing Strategy:** `project-skills.py` (re-projection) + `lint-skills.py`
(`--check-projected --check-capabilities`) are the mechanical gates for skill/component
correctness; no new pytest surface (the component is prose, the CLI it shells is already
tested in Phases 1–2).

**Integration Notes for Next Phase:** Phase 4 (cross-lane, not started) is the mechanical
backstop — it does NOT need any further change to this phase's skill wiring; it consumes the
same `run_structural_checks`/rule functions (or shells the same CLI) at a different call site
(`lazy-state.py`/`bug-state.py`'s plan-pickup probe).

---

### Phase 4: Pickup backstop (in-process validation at first `/execute-plan` routing) — APPLIED, STATE lane (state-batch-5)

**Phase kind:** cross-lane / applied this session (STATE lane)

**Scope (as designed, per SPEC D4 — unchanged from the SPEC's recommendation):** the probe that
first routes `execute-plan` onto a plan part (`lazy-state.py` / `bug-state.py`) runs the same
structural checks in-process; a structural ERROR refuses the route and surfaces the findings +
the fix command, before any execution begins; legacy pre-gate plans already mid-execution (some
`- [x]` WU ticked) are exempted from refusal (WARN only).

**Reuse shape chosen (D1-RESIDENCY, resolves to option (c)/(b)):** neither a hoist into
`lazy_core.py` nor a subprocess shell-out — `lazy_core.plan_structural_backstop` imports
`validate-plan.py` IN-PROCESS via `importlib` (the same reverse-direction pattern
`validate-plan.py` itself already uses to load `lazy_core.py`), calling
`run_structural_checks(plan_path)` directly. Zero subprocess spawn cost (satisfying D1's literal
"in-process" intent) AND zero rule-function hoist (`validate-plan.py` stays byte-untouched, so
the SKILLS lane's ownership of that file is respected retroactively).

**Delta from the literal recorded design (documented, not silent):** the mid-execution
discriminator is BROADER than "`checked` count only". A plan with ZERO parseable WU checkboxes at
ALL (`unchecked == checked == 0`) is ALSO exempted from refusal — this repo's OWN pre-existing
legacy plans (verified via this repo's own `lazy-state.py --test` / `bug-state.py --test` smoke
fixtures, e.g. `mid-implementation`, `legacy-plan-diagnostics`) have no WU checklist at all, a
shape `_plan_wu_checkbox_counts`'s own docstring calls "a legacy pre-ISSUE-6 plan" that the rest of
this codebase has always tolerated (falls back to PHASES-level tracking, never an error).
Rule 1 (`wu-checklist`) flags EVERY such plan as ERROR regardless of age, so applying the literal
"checked count only" discriminator would have refused routing on every pre-existing legacy plan —
verified as a real regression against 8 named smoke fixtures before this exemption was added.
See `lazy_core.plan_structural_backstop`'s docstring for the full rationale.

**Deliverables:**
- [x] Reuse shape decided: in-process `importlib` load of `validate-plan.py` (see above).
- [x] Wired into the plan-pickup probe in BOTH `lazy-state.py` (Step 7a, right before the
  `execute-plan` dispatch) and `bug-state.py` (the mirrored Step 7a site) — a scoped, fresh,
  structurally-invalid plan writes `BLOCKED.md` (`blocker_kind: plan-structural-invalid`) and
  refuses the route; a mid-execution/legacy plan WARNs (findings surfaced, findings never block).
- [x] The mid-execution exemption: `lazy_core.plan_structural_backstop(plan_path)` reads
  `_plan_wu_checkbox_counts` directly (`checked > 0` OR the legacy-no-checkboxes case above).
- [x] `lazy-state.py --test` / `bug-state.py --test` fixtures:
  `plan-structural-backstop-refuses-fresh-invalid` (BLOCKED.md + `terminal_reason: blocked`) and
  `plan-structural-backstop-mid-execution-warns` (falls through to `execute-plan`) — added to both
  scripts' in-file smoke harness + the byte-pinned baselines regenerated (2 new lines each, via
  `_normalize_smoke_output`, no other diff). `lazy_parity_audit.py --repo-root .` exit 0.
  `test_lazy_core.py`: 5 unit fixtures on `plan_structural_backstop`/`format_plan_structural_blocker`
  (clean plan / fresh-invalid refuses / mid-execution warns / missing-file fails open / blocker body
  names findings).

**Minimum Verifiable Behavior:** a fresh plan part with an unfilled WU-checklist template-row
placeholder reaching the pickup probe refuses the route with the structural findings (verified via
both the unit fixture and the state-script smoke fixture); the same defect on a plan with 1+
ticked WUs proceeds with a WARN (findings still surfaced).

**Runtime Verification** *(checked by integration test)*:
- [x] `python -m pytest user/scripts/test_lazy_core.py -k "plan_structural_backstop or
  format_plan_structural_blocker"` — 5 passed. `python user/scripts/lazy-state.py --test` /
  `python user/scripts/bug-state.py --test` — both `All smoke tests passed.`, baselines
  byte-stable modulo the 2 new named fixture lines each. <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–3 (the validator + rule set + skill wiring this session delivered).

**Files modified:** `user/scripts/lazy_core.py` (`_load_validate_plan_module`,
`plan_structural_backstop`, `format_plan_structural_blocker`), `user/scripts/lazy-state.py` (Step
7a pickup wiring + 2 smoke fixtures), `user/scripts/bug-state.py` (mirrored wiring + 2 smoke
fixtures), `user/scripts/test_lazy_core.py` (5 unit fixtures),
`user/scripts/tests/baselines/{lazy-state,bug-state}-test-baseline.txt` (regenerated).

**Testing Strategy:** Hermetic `--test` fixtures on both state scripts (mirroring the existing
plan-pickup fixture shapes), plus hermetic pytest unit fixtures on the shared helper and the
parity audit.
