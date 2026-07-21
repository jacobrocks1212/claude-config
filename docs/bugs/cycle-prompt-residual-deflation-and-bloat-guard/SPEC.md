# Cycle-Prompt Residual War-Story Prose + Standing Anti-Bloat Guard — Investigation Spec

> The assembled per-cycle dispatch prompt still carries removable historical/incident/rationale
> prose after the parent 19.8% trim, and nothing prevents future harden rounds from re-accreting
> it — the byte ratchet gates whole-prompt size, not per-section growth or the war-story pattern.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-20
**Placement:** docs/bugs/cycle-prompt-residual-deflation-and-bloat-guard
**Related:**
- `docs/features/cycle-prompt-deflation` (Complete 2026-07-19) — the parent feature this follows up; its SPEC / IMPLEMENTATION_NOTES / SEMANTIC_DIFF_PHASE2+3 are the reference playbook.
- `docs/features/lazy-batch-skill-deflation` — the prose→verdict-rule playbook + `skill-size-ratchet.py` gate both features extend.
- `docs/features/phases-slice-scoped-reads` — the precedent that made the parent reject "reference-by-path" externalization (a prose read-mandate failed in this exact prompt).
- `docs/features/anti-overfit-design-gate` — the new lint's detectors must be structural (shape-keyed), not incident-literal, to pass `harness-gate.py`'s own overfit check.
- `docs/features/coupled-pair-generation` — `cycle-base-prompt.md` mirrors into bug/cloud variants via `generate-coupled-skills.py`; every section edit flows through it.

---

## Verified Symptoms

<!-- Reporter = the harness operator, who pasted a live AlgoBooth cycle-subagent prompt and
     directed this follow-up. These are confirmed by direct inspection of the on-disk template
     that the emitter dispatches verbatim, plus the operator's three scope answers. -->

1. **[VERIFIED]** The dispatched cycle-subagent prompt carries **incident-narrative / historical-justification prose** that adds no enforceable instruction — e.g. `(Live incident: dispatched on Sonnet for the mechanical part-2, the subagent silently executed the complex part-1 instead, then died resultless.)`, `(HARD — ISSUE 2, d8-effect-chains run)`, `(hydra-overlay false-block, 2026-07-19)`. Confirmed present in `cycle-base-prompt.md` at lines 286/295/299 and their `-cloud` twins 320/329/333. — operator pasted the live prompt; grep confirms the literals on disk.

2. **[VERIFIED]** The parent feature deflated **only the 8 `skills=all` boilerplate sections**; the **9 `skills=<specific>` section families were never a deflation target** and remain at full pre-deflation density (`skill-execute-plan[-cloud]`, `skill-mcp-test-common` + `mcp-test-runtime` ×2, `skill-retro[-feature]`, `provenance-lookup`, `resume-safety`, `park-spec-sentinel-mediation`). Measured un-deflated skill-specific prose ≈ **19.6 KB** total; largest single section is `skill-mcp-test-common` at **5,658 B**. — per-`@section` byte census (Evidence below).

3. **[VERIFIED]** **Residual rationale clauses survive inside the already-deflated `skills=all` sections** — the parent trimmed for policy-preservation but left explanatory tails: line 139 `(an absent file raises on empty stdin)`, line 142 `a mature PHASES.md exceeds the Read cap; the slicer returns the index + only the phase(s) named`, line 150 `No /mnt/c/... (WSL dialect)`, line 233 `2026-07-09 — the former inline-only ban is lifted on workstation; cloud keeps it`. — grep confirms.

4. **[VERIFIED]** The **AlgoBooth addendum** (`repos/algobooth/.claude/skill-config/cycle-prompt-addenda.md`, 53 lines / 3,724 B) carries the verbose `over-cap-gate-decomposition` + `audio-invariants` blocks the operator saw in the pasted prompt — a second, repo-scoped surface of the same class. — confirmed; operator scoped it IN.

5. **[VERIFIED — GAP, not a code fault]** **No mechanism prevents re-accretion of this prose.** The parent's `skill-size-ratchet.py` `profiles` block gates the **whole assembled prompt** against a per-profile byte ceiling; it does **not** gate per-section growth (one section can bloat while another shrinks and net-pass) and does **not** detect the war-story **pattern** (a dated incident / "Live incident:" narrative passes as long as total bytes fit). There is also **no `CLAUDE.md`** in `user/skills/_components/lazy-batch-prompts/` stating the authoring contract at the edit site. — operator directive to add the prevention mechanism; grep confirms neither guard exists.

## Reproduction Steps

<!-- The "symptom" is a static, on-disk quality/efficiency defect in a dispatched artifact —
     it reproduces by inspecting the emitter's output, no runtime needed. -->

1. Emit any dispatchable cycle prompt through the real emitter, e.g. from repo root:
   `python3 user/scripts/skill-size-ratchet.py --check` (exercises `emit_cycle_prompt` for all 20 profiles), or inspect the template directly:
   `grep -nE "Live incident|ISSUE 2|hydra-overlay|2026-[0-9-]+|raises on empty stdin|exceeds the Read cap|WSL dialect|the former inline-only ban" user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`
2. Observe war-story / rationale clauses in the dispatched text (lines 139, 142, 150, 233, 286–333).
3. Add a new dated incident clause to any section and re-run the ratchet: as long as the net assembled bytes stay under the profile ceiling, **`--check` still passes** — the anti-pattern is not caught.

**Expected:** The dispatched prompt carries imperative rules and load-bearing marker literals ONLY; incident/provenance narrative lives in the SPEC/IMPLEMENTATION_NOTES. A per-section + pattern guard refuses re-accretion at authoring time.
**Actual:** ~19.6 KB of never-deflated skill-specific prose + residual rationale in the boilerplate ride every matching dispatch, and only a whole-prompt byte ceiling (blind to per-section growth and to the war-story pattern) guards against regrowth.
**Consistency:** Always (static artifact).

## Evidence Collected

### Source Code

**Serving path (fully traced — this is a `traced` cause, not `asserted`):**
```
dispatched cycle-subagent prompt (what the operator pasted)
  → orchestrator dispatches probe.cycle_prompt VERBATIM   user/skills/lazy-batch/SKILL.md:813
  → probe.cycle_prompt = emit_cycle_prompt(...).prompt     user/scripts/lazy_core/dispatch.py:886
  → reads template + selects @sections + binds {tokens}    dispatch.py:952 (read), 205 (parse), 1052 (bind)
  → the war-story prose IS the template literal            user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md:139,142,150,233,286-333  ← fix site (ON the path)
  → (AlgoBooth) merged addendum                            repos/algobooth/.claude/skill-config/cycle-prompt-addenda.md:21-53  ← fix site (ON the path)
```
The fix site (template prose) is literally the value read on the symptom's serving path — fix-site-on-path satisfied.

**Per-`@section` byte census** (`cycle-base-prompt.md`, via the emitter's own section grammar):

| Section | Bytes | skills= | Deflated by parent? |
|---|---|---|---|
| skill-mcp-test-common | 5,658 | mcp-test | **No** |
| turn-end (×2 mode variants) | 3,639 / 3,724 | all | Yes |
| skill-execute-plan | 2,634 | execute-plan,retro-feature | **No** |
| hard-contract (×2) | 2,436 / 2,954 | all | Yes |
| workstation-dispatch | 2,561 | all | Yes (residual at L233) |
| skill-execute-plan-cloud | 2,448 | execute-plan,retro-feature | **No** |
| mcp-test-runtime (×2) | 2,028 / 1,416 | mcp-test | **No** |
| park-spec-sentinel-mediation | 1,794 | spec,spec-bug | **No** |
| resume-safety (×2) | 556 / 928 | execute-plan,retro,retro-feature | **No** |
| provenance-lookup / skill-retro / skill-retro-feature | 835 / 648 / 693 | (specific) | **No** |
| env-dialect-core / -windows | 1,067 / 853 | all | Yes (residual at L139/142/150) |

Total never-deflated skill-specific prose ≈ **19,638 B** (only the sections matching a given cycle's skill emit, so no single dispatch pays all of it — but each dispatch of that skill pays its share every cycle + every compaction re-pay).

**The "in general" surface (operator's generalization):** the dispatched-prompt template family is 15 files under `user/skills/_components/lazy-batch-prompts/` (`cycle-base-prompt.md` 51.8 KB, `dispatch-*.md` ×11, `input-audit-prompt.md` 16.5 KB, `loop-block.md`, `research-halt-announcement.md`) **plus** per-repo `cycle-prompt-addenda.md`. All are dispatched verbatim to a subagent; all are subject to the same war-story-accretion pressure from harden rounds. The prevention guard must cover the family, not just `cycle-base-prompt.md`.

### Runtime Evidence
The live AlgoBooth `/lazy-batch` cycle-subagent prompt the operator pasted (an `execute-plan` cycle for `inspector-track-dashboard-part-4`) — the direct field artifact showing the war-story clauses + the verbose AlgoBooth over-cap block in a real dispatch.

### Git History
Parent `cycle-prompt-deflation` landed 2026-07-19 (`COMPLETED.md` `completed_commit: 65e3ed0e`, IMPLEMENTED commits `b7985f9…5e73936`). `skill-size-baseline.json` notes show a steady cadence of harden-round hand-raises (spike-pipeline-role, orchestrator-tool-search, rounds 68/70/129/130) — direct evidence of the ongoing accretion pressure this guard is meant to arrest.

### Related Documentation
- Parent SPEC line 27: trim-in-place, **never externalize/reference-by-path** (the `phases-slice-scoped-reads` failure precedent). Binding on this follow-up.
- Parent IMPLEMENTATION_NOTES Phase 3: `⚖ policy: scope-tightening selector narrowing → trim-only (no narrowing)` — the declined lever. **Operator confirmed: stay prose-density only; do NOT re-open selector-narrowing.**
- Parent SEMANTIC_DIFF_PHASE2/3: the preserved-literal list (test-asserted) this follow-up must not break.
- `user/scripts/CLAUDE.md` "Verification-only canonical marker" — precedent for replacing a growing free-text regex with a structural marker; informs the anti-pattern detector design.

## Theories

### Theory 1: Scope gap in the parent feature (Symptoms 1–4) — CONFIRMED
- **Hypothesis:** The residual prose exists because the parent's scope was explicitly the 8 `skills=all` boilerplate sections + trim-only; skill-specific sections and rationale tails were out of scope by construction, not overlooked.
- **Supporting evidence:** Parent SPEC §"eight `skills=all` boilerplate sections (deflation targets)" enumerates exactly those 8; IMPLEMENTATION_NOTES Phases 2–3 touch only them; the byte census shows every `skills=<specific>` section at full density.
- **Contradicting evidence:** None.
- **Status:** **Confirmed.** Root cause = a deliberately-bounded parent scope, leaving a clean, well-defined remainder.

### Theory 2: The size ratchet is pattern-blind and section-blind (Symptom 5) — CONFIRMED
- **Hypothesis:** The parent's durability mechanism (assembled-profile byte ratchet) cannot arrest war-story re-accretion because it measures whole-prompt bytes, not per-section growth or the narrative pattern.
- **Supporting evidence:** `skill-size-ratchet.py` has no per-section or anti-pattern check (grep returns nothing); `profiles` block is a single ceiling per `(pipeline,mode,skill,variant)`; the baseline-notes hand-raise cadence proves accretion routinely lands.
- **Contradicting evidence:** The whole-prompt ceiling DOES cap gross size — so this is a granularity/qualitative gap, not a total absence of protection. The new guard COMPOSES with (does not replace) the existing ratchet.
- **Status:** **Confirmed.**

## Proven Findings

- **Root cause is `traced`, not `asserted`:** the war-story prose is the literal template read on the symptom's verbatim-dispatch serving path (SKILL.md:813 → dispatch.py:886/952 → template lines); the AlgoBooth over-cap prose is the merged addendum on the same path. The fix sites are ON the path.
- **Two co-equal deliverables** (below) — a one-time lean + a standing guard — because a cleanup without a guard re-accretes (Symptom 5 / Git evidence), and a guard without the cleanup locks in the current bloat.

## Proposed Fix Shape (for /plan-bug)

**Deliverable 1 — One-time residual deflation (prose-density only; operator-confirmed).**
- Class A: deflate the never-touched `skills=<specific>` sections in `cycle-base-prompt.md` (start with the highest-return: `skill-mcp-test-common` 5.7 KB, `skill-execute-plan[-cloud]` ~5 KB combined).
- Class B: strip residual rationale tails from the already-deflated `skills=all` sections (L139/142/150/233).
- AlgoBooth addendum: condense `over-cap-gate-decomposition` + `audio-invariants` to imperative rules.
- **Discipline (inherited from the parent, binding):** trim-in-place, never reference-by-path; preserve every load-bearing marker literal (`@section` selectors, `WORKSTATION DISPATCH — LOAD-BEARING`, tokens `{cwd}`/`{work_branch}`/`{receipt_name}`, the R5 chained command, `git_safe_push`, `classify_conflict`/`conflict_kind: semantic`, `--verify-ledger` `ok:true`, `cycle-subagent-bg-gate-guard.sh`, `series_index` prerequisite-ordering **algorithm** — this is load-bearing logic, NOT a war-story: compress framing, keep the rule); produce a `SEMANTIC_DIFF` mapping every removed clause → surviving rule (parent's regression guard); regenerate coupled variants (`generate-coupled-skills.py --check` green); **re-lock** the assembled-profile ratchet via `skill-size-ratchet.py --lock-in-profile` (never hand-raise).
- **Out of scope (operator-confirmed):** `@section` selector-narrowing (parent's declined lever); the path-shorthand/context-header restructure (Gemini's variable idea — rejected: verbatim dispatch + `{cwd}` already a bound token, shorthand risks mid-command mis-resolution).

**Deliverable 2 — Standing anti-bloat guard (two layers, the repo's mechanical+prose pattern).**
- **2a. Mechanical lint** over the dispatched-prompt template family (`user/skills/_components/lazy-batch-prompts/*.md` + per-repo `cycle-prompt-addenda.md`), wired into the lint battery (`lint-skills.py` / `gate-battery.json`) so it refuses at authoring time. Two checks:
  - **War-story pattern detector** — **structural, shape-keyed (not incident-literal — must pass `harness-gate.py`'s own overfit check):** ISO incident-date tokens (`\b20\d\d-\d\d-\d\d\b`), issue/round refs (`ISSUE \d`, `Round \d+`, `d8-effect-chains`), `Live incident:` / removed-history narrative (`the former … ban`, `used to`, `previously … now`), and bare `docs/{bugs,features}/<slug>` incident literals — **within the dispatched-prompt scope only** (NOT SKILL.md orchestrator prose or docs, where provenance is legitimate). An allowlist rescues genuine load-bearing literals (hook/script filenames, `@section` names).
  - **Per-section byte ceiling** — extend the ratchet from whole-assembled to per-`@section` granularity so a single section can't grow silently under a net-passing total.
- **2b. Authoring-contract `CLAUDE.md`** at `user/skills/_components/lazy-batch-prompts/CLAUDE.md` (none exists) — states the contract at the edit site per the repo's nested-CLAUDE.md convention: *these files are dispatched VERBATIM to a subagent → imperative rules + load-bearing marker literals ONLY; incident/provenance/dated-history narrative belongs in the SPEC/IMPLEMENTATION_NOTES, never the prompt; the lint enforces it; here is the deflation playbook + the preserved-literal list.*

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Cycle prompt template | `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` | Deflate Class A skill-specific sections + Class B rationale tails (D1) |
| AlgoBooth addendum | `repos/algobooth/.claude/skill-config/cycle-prompt-addenda.md` | Condense over-cap + audio-invariants blocks (D1) |
| Dispatched-prompt family | `user/skills/_components/lazy-batch-prompts/*.md` (15 files) + per-repo addenda | Scope of the new anti-bloat lint (D2a) |
| Size ratchet | `user/scripts/skill-size-ratchet.py` + `skill-size-baseline.json` | Add per-section ceiling; re-lock profiles after D1 (D2a) |
| Lint battery | `user/scripts/lint-skills.py`, `.claude/skill-config/gate-battery.json` | Wire the new war-story/per-section check (D2a) |
| Authoring contract | `user/skills/_components/lazy-batch-prompts/CLAUDE.md` (**new**) | Document the verbatim-dispatch / no-provenance discipline (D2b) |
| Coupled-pair gate | `generate-coupled-skills.py` (`--check`) | Must stay green after template edits |
| Control-surface manifest | `docs/gate/control-surfaces.json` | The new gate is a control surface — register it so `harness-gate.py` covers its own diff |

## Resolved Decisions (operator disposition 2026-07-20)

<!-- The four plan-time forks below were surfaced to the operator and resolved before /plan-bug.
     They are LOCKED inputs to PHASES authoring, not open. -->

1. **Lint severity → HARD GATE from day one.** The war-story pattern detector AND the per-section
   byte ceiling block the battery on any match (like `skill-size-ratchet.py`), not advisory-first.
   Bright-line, low false-positive within the narrow dispatched-prompt scope; a harden round adding
   an incident date is refused immediately rather than during a soak.
2. **Detector breadth → CONFIRMED SHAPES ONLY.** The pattern set is exactly: ISO-date tokens
   (`\b20\d\d-\d\d-\d\d\b`), `ISSUE \d` / `Round \d+` / `d8-effect-chains`, `Live incident:`, and
   bare `docs/{bugs,features}/<slug>` incident literals. **Excluded** (deliberately, to avoid
   false-positives on legitimate imperative rules): loose narrative phrasings like `the former … ban`
   / `used to` / `previously … now`. Accepted miss: a novel undated narrative phrasing — caught by
   the per-section byte ceiling + the D2b CLAUDE.md contract instead.
3. **Detector home → FOLD INTO `skill-size-ratchet.py`.** Per-section byte ceiling extends the
   existing per-profile ratchet in-file; the pattern check rides the same script, reachable via
   `lint-skills.py --check-skill-size` — one battery entry, no new script.
4. **Allowlist → REASON-REQUIRED INLINE ENTRIES.** Each load-bearing-literal exemption carries a
   reason at its point of use, mirroring `cli-surface-lint.py`'s `<!-- marker -->` and
   `lint-skill-config.py`'s `SUPPRESSIONS` — keeps the escape hatch auditable and resists silent
   overfit growth.

**Anti-overfit self-check (plan-time action, not a fork):** the detector edits a matcher set, so
`harness-gate.py` may flag it. Defense = the structural (shape-keyed, not incident-literal) design
above; `/plan-bug` must register the new gate in `docs/gate/control-surfaces.json` and author
`GATE_VERDICT.md` if flagged.
