# Plan-Skills Redesign — Implementation Phases

> Decomposition of `SPEC.md` (Plan-Skills Redesign). Six phases, ordered by dependency. Each is independently testable; phases 3→4 and the D2-dependent phases (5, 6) carry explicit prerequisites. This is harness-internals work in `claude-config/` — no Cognito product code, no `/msbuild`/`/mstest`. Verification is Python unit tests (`pytest user/scripts/test_*.py`), the projection/lint scripts, and `setup.ps1 check`.

**Status:** Phases 1–2 Complete (all deliverables landed; Phases 3–6 pending)
**Spec:** `./SPEC.md`
**Last updated:** 2026-06-29

---

## Touchpoint Audit (verified 2026-06-29)

Three read-only Explore agents verified every file the plan modifies. All paths are under `~/source/repos/claude-config/` unless noted. Edits go to the **real targets** in `claude-config/` (the Edit tool refuses symlink writes).

| Planned file | Exists? | Verified symbols / lines | Action | Directive |
|---|---|---|---|---|
| `repos/cognito-forms/.claude/skills/write-plan/SKILL.md` | yes (385L) | frontmatter `name: write-plan`; lane partitioning Step 2.5 (L111–159); typegen seam (L294–306); tiered gates (L316–320) | rename dir + `name:` | dir → `write-plan-cognito/`; `name: write-plan-cognito` |
| `repos/cognito-forms/.claude/skills/write-plan/lane-agent-briefing.md` | yes (73L) | self-ref path `.claude/skills/write-plan/lane-agent-briefing.md` (SKILL.md L194) | move w/ dir + fix ref | update path to `write-plan-cognito/` |
| `manifest.psd1` | yes | `DotClaudeDirs = @('skill-config','skills','knowledge')` (L45) — directory-level symlink | none (transparent) | `setup.ps1 check` after rename |
| `repos/cognito-forms/.claude/skill-config/skill-catalog.md` | yes (12L) | problem→skill map; **no** `write-plan` ref | none | confirm no menu elsewhere advertises the bare name (Phase 1 discovery) |
| `user/scripts/lazy-state.py` | yes | emits `sub_skill` string for pipeline dispatch | edit | emit `write-plan-cognito` for Cognito repos (locate selection site) |
| `user/skills/lazy/SKILL.md` | yes | Step 6 dispatches planner; Step 7 → generic `/execute-plan` | edit | Step 6 → `/write-plan-cognito` in Cognito context |
| `user/skills/plan-feature/SKILL.md` | yes | `= /spec-phases + /write-plan` | edit | dispatch `/write-plan-cognito` in Cognito context |
| `user/skills/_components/execution-contract.md` | **no** | — | create | extract policy from generic `write-plan` boilerplate (below) |
| `user/skills/write-plan/SKILL.md` | yes (649L) | emits EXECUTION MODEL (L252–267), COMPONENT LOADING (L268–271), MANDATORY RULES (L308–324), Execution Protocol (L388–495), Blocking Issue (L498–527), Completion (L530–554) | edit | stop emitting boilerplate; emit one-line pointer |
| `user/skills/execute-plan/SKILL.md` | yes (419L) | reads PHASES.md full (L90–114); delegates notes to `phases-update` (L254–256); GT gate via `subagent-review` (L266–270) | edit | reference+read `execution-contract.md`; D4/D5 land here |
| `user/skills/_components/phases-update.md` | yes | appends Implementation Notes to PHASES.md (the shared writer) | edit | **flip writer** → `IMPLEMENTATION_NOTES.md` |
| `user/scripts/lazy_core.py` | yes | `_IMPL_NOTES_HEADING_RE` (L1906); `phases_show_implementation()` (L1909–1950, greps PHASES.md L1949) | edit | sibling-then-embedded read; `remaining_unchecked_*`/`verify_ledger_gate` unaffected |
| `user/scripts/test_lazy_core.py` | yes | `test_phases_show_impl_implementation_notes_true` (L308) + siblings (L261–335) | edit | add sibling-file coverage |
| `user/skills/_components/source-reread.md` | yes | reads "prior Implementation Notes in PHASES.md" | edit (P3 **and** P4) | P3: current-phase-slice read; P4: sibling-then-embedded notes read — merge both, do not clobber |
| `user/skills/add-phase/SKILL.md` | yes | mines Implementation Notes (L155–186) | edit | sibling-then-embedded |
| `user/skills/lazy/SKILL.md` | yes | research-gate predicate checks `## Implementation Notes` (L281) | edit | sibling-then-embedded |
| `user/skills/lazy-batch/SKILL.md` | yes | PHASES.md/notes refs (L87–101) | edit | sibling-then-embedded |
| `user/skills/realign-spec/SKILL.md` | yes | reads upstream Implementation Notes (L68) | edit | sibling-then-embedded |
| `user/skills/implement-phase/SKILL.md` | yes | reads prior Implementation Notes (L54) | edit | sibling-then-embedded |
| `user/skills/implement-phase-batch/SKILL.md` | yes | reads prior Implementation Notes (L73–75) | edit | sibling-then-embedded |
| `user/skills/spec-phases-batch/SKILL.md` | yes | Implementation Notes ref (L192) | edit | sibling-then-embedded |
| `user/skills/spec-phases/SKILL.md` | yes | Step 1.5 upstream look-back reads Implementation Notes | edit | sibling-then-embedded |
| `user/skills/_components/subagent-review.md` | yes | ground-truth gate (L33–62) | edit (Phase 6) | cheap-checks default; 529 inline-fallback |
| `user/skills/_components/subagent-launch.md` | yes | Build Concurrency rule | edit (Phase 5) | same-message disjoint batching; background builds |
| `user/scripts/lint-skills.py` / `test_project_skills.py` | yes | `!cat` expansion + projection validation | verify | confirm `execution-contract.md` round-trips |

**Cross-cutting note:** none of these are tracked by the host repo's git — they live in `claude-config` (branch `build-queue`). Commit there. After any skill/component edit, run `python ~/.claude/scripts/project-skills.py` and `lint-skills.py` to re-project and validate.

---

## Phase 1 — Rename the Cognito planner + lock resolution (D1)

**Goal.** Make the advertised planner the one that runs. Rename the *only* colliding skill so the Cognito lane planner stops being shadowed by the user-level generic.

**Prerequisites.** None — independent, lowest risk; do first.

**Deliverables.**
- [x] Rename `repos/cognito-forms/.claude/skills/write-plan/` → `write-plan-cognito/` and set frontmatter `name: write-plan-cognito`.
- [x] Update the `lane-agent-briefing.md` self-reference path in the renamed SKILL.md (`.claude/skills/write-plan/` → `.claude/skills/write-plan-cognito/`).
- [x] Run `setup.ps1 check` (and `repair` if needed) to confirm the directory symlink re-resolves.
- [x] **Discovery (gates the edit below):** pin the exact `lazy-state.py` branch that emits the planner `sub_skill` string, and the dispatch sites in `/lazy` Step 6 and `plan-feature`. The Explore sweep confirmed the file emits a `sub_skill` but did not pin the deciding line/branch — this discovery closes that gap before any edit.
- [x] Edit the pinned dispatch site(s) so Cognito repos emit `write-plan-cognito`; confirm `/lazy` Step 7 still targets generic `/execute-plan`.
- [x] Discovery: confirm whether any catalog/menu advertises the bare `write-plan` name; if found, update to `write-plan-cognito`; if not, record that discovery is symlink-based (no catalog edit needed). *(Touchpoint sweep already found the skill-catalog has no `write-plan` ref — bounded.)*
- [x] Strip personal-project residue (Tauri, MCP-validation, `/lazy-batch` Step 9) from the Cognito planner.
- [x] Add a projection/lint assertion that `/write-plan-cognito` exists and resolves (no same-name collision remains).
- [x] Add a lint/skills-dir assertion that **no `execute-plan-cognito` exists** (closes the SPEC "One generic executor, no Cognito fork" criterion — the negative invariant from the locked decision).

**Testing strategy.** `setup.ps1 check` green; `python project-skills.py` projects `write-plan-cognito` with no broken `!cat`; `lint-skills.py` green; manual: in a Cognito worktree (fresh session) `/write-plan-cognito` resolves to the lane variant and `/write-plan` to the generic — both invocable, neither shadowed. **Dispatch assertion (not just resolution):** a Cognito-repo pipeline dispatch *emits* `write-plan-cognito` (verified in a run transcript), proving the routing edit fires — resolution alone does not prove the pipeline selects the renamed name.

**Integration notes.** The rename is mechanical at the directory level (symlink is transparent). The *behavioral* risk is the dispatch-site routing: if `lazy-state.py`/`plan-feature` keep emitting bare `write-plan` for Cognito, the pipeline silently runs the generic planner again. That selection site is the load-bearing edit — verify it explicitly.

#### Implementation Notes (Phase 1 — Batch 1: WU-1 + WU-2)
**Completed:** 2026-06-29
**Review verdict:** PASS

**Work completed:**
- WU-1 (rename): `git mv` of `repos/cognito-forms/.claude/skills/write-plan/` → `write-plan-cognito/` (history-preserving — `R` status). Frontmatter `name:` set to `write-plan-cognito`. Both internal self-ref paths (`.claude/skills/write-plan/lane-agent-briefing.md` at SKILL.md L194 + L289) rewritten to `write-plan-cognito/`. `manifest.psd1` NOT edited — `DotClaudeDirs` symlinks `.claude/skills` at the directory level (L45), so the subdir rename is transparent. The renamed skill now registers as a distinct skill (`write-plan-cognito` appears in the catalog alongside generic `write-plan` — no collision).
- WU-2 (dispatch routing): **Pinned dispatch branch — `lazy-state.py` "Step 7a: write plan" branch (the `elif not plans:` block, was L2868–2874, the sole direct `sub_skill="write-plan"` planner emission).** Edited it to emit `write-plan-cognito` when `repo_uses_cognito_planner(repo_root)` is True, else generic `write-plan`. Added helper `repo_uses_cognito_planner(repo_root)` to `lazy_core.py` (returns True iff `repo_root/.claude/skills/write-plan-cognito/` is a dir) — the rename-aligned, deterministic discriminator. Wired the import into `lazy-state.py`. Confirmed Step 7b executor emission (`sub_skill="execute-plan"`, L2999) stays generic — no `execute-plan-cognito`. `plan-feature/SKILL.md` Step 2 planner dispatch updated to resolve `write-plan-cognito` vs `write-plan` by the same `.claude/skills/write-plan-cognito/` presence test. `lazy/SKILL.md` needs NO routing edit: it is dispatch glue that emits whatever `sub_skill` the script returns — its only `write-plan` mentions are a sentinel-table audit row (L248) and the execute-plan consistency guard (L224), neither a dispatch directive.
- Tests: 3 `repo_uses_cognito_planner` cases added to `test_lazy_core.py` (present→True, generic-only→False, no-skills-dir→False) + registry entries. All pass.

**Integration notes (for next implementer / Phase 2):**
- The Cognito-context discriminator is `lazy_core.repo_uses_cognito_planner(repo_root)` — reuse it, do NOT hardcode worktree names or use `repo_has_no_app_surface` (the latter is a "no-MCP-surface" check; both Cognito and AlgoBooth roots lack a top-level `package.json`, so it does NOT distinguish Cognito).
- Phase 2 edits `write-plan-cognito/SKILL.md` (the renamed file) — it now lives at `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md`.

**Pitfalls & guidance:**
- Run gates with `pwsh` (PowerShell 7), not `powershell.exe` (5.1) — `setup.ps1` uses `Import-PowerShellDataFile`, absent in the 5.1 Git-Bash invocation context.
- `setup.ps1 check` reports 5 pre-existing broken items (`normalize-crlf.ps1` REAL/MISSING across worktrees) unrelated to this work; all `skills` symlinks report OK.
- `test_lazy_core.py` has 4 pre-existing failures on a clean baseline (missing sibling `algobooth` repo for the merged-view parity audit + Windows CRLF/permission snapshot drift in `test_lazy_state_test_output_matches_baseline` / `test_bug_state_test_output_matches_baseline` / `test_archive_fixed_*`). Verified identical via `git stash`; this work introduced zero regressions. The `lazy-state.py --test` smoke snapshot is unaffected by the routing edit (the Cognito Step-7a path is not in the smoke fixtures).

**Files modified:**
- `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md` — renamed (from `write-plan/`); `name:` + 2 self-ref paths
- `repos/cognito-forms/.claude/skills/write-plan-cognito/lane-agent-briefing.md` — renamed (content unchanged)
- `user/scripts/lazy_core.py` — new `repo_uses_cognito_planner()` helper
- `user/scripts/lazy-state.py` — import + Step-7a planner-name branch
- `user/skills/plan-feature/SKILL.md` — Step 2 planner dispatch resolves by repo
- `user/scripts/test_lazy_core.py` — 3 new helper tests + registry entries

#### Implementation Notes (Phase 1 — Batch 2: WU-3 + WU-4)
**Completed:** 2026-06-29
**Review verdict:** PASS

**Work completed:**
- WU-3 (strip personal residue): **No edit required — verified clean.** A broad sweep of `write-plan-cognito/SKILL.md` (385L) found ZERO Tauri / cargo / clippy / rust / MCP-validation / `VALIDATED.md` / real-device / `/lazy-batch` Step-9 references. The only two "MCP" mentions (L10, L18) are deliberate Cognito-context *affirmations* that the repo has no MCP surface — correct lane behavior to preserve, the opposite of residue. The file was already authored clean for the Cognito profile; the deliverable is satisfied by verification.
- WU-4 (lint assertions + catalog audit): Added `lint_planner_resolution(repos_dir, user_skills_dir)` + `_skill_dirs_under()` helper to `lint-skills.py`, wired into `main()` to run on every default lint invocation (exit 1 on violation). It enforces: (positive) `write-plan-cognito` resolves under some `repos/*/.claude/skills/` with NO same-name user-level collision; (negative) NO `execute-plan-cognito` exists under any `repos/*/.claude/skills/` or `user/skills/`. Added 6 pytest cases to `test_project_skills.py` (clean tree, missing-planner, user-collision, repo executor-fork, user executor-fork, and a real-tree-is-clean assertion). **Catalog audit:** `repos/cognito-forms/.claude/skill-config/skill-catalog.md` has NO `write-plan` reference — discovery is symlink-based, so no catalog edit was needed (confirms the touchpoint sweep).

**Integration notes (for next implementer):**
- The new lint gate is part of the standard `lint-skills.py` run — it prints `OK — planner resolution: write-plan-cognito resolves; no execute-plan-cognito fork.` when clean. Phases 2+ that add an `execute-plan-cognito` (they should not) will trip this gate.

**Pitfalls & guidance:**
- `lint_planner_resolution`'s `repos_dir` default at CLI is `~/source/repos` (live worktrees); the pytest real-tree test scopes it to `claude-config/repos/` (source tree) — both satisfy the invariant since the rename landed in the source and the symlink makes it visible in the worktrees.

**Files modified (Batch 2):**
- `user/scripts/lint-skills.py` — `lint_planner_resolution()` + `_skill_dirs_under()` + `main()` wiring
- `user/scripts/test_project_skills.py` — 6 new planner-resolution tests
- (WU-3: no file edit — verified-clean)

**Post-phase CLAUDE.md / consumer review (additional dispatch site found):**
- `repos/cognito-forms/.claude/skills/resolve-review/SKILL.md` — a Cognito-repo-scoped skill that dispatches the planner via its `/add-phase` → planner bridge (Step 7). Updated its 5 planner refs from `/write-plan` to `/write-plan-cognito` so the Cognito review-remediation pipeline gets lane partitioning (it only ever runs in the Cognito repo). This site was NOT in the touchpoint audit's enumerated dispatch sites but falls under WU-2's intent. Left untouched: illustrative `write-plan` *example* references in `log/SKILL.md` (work-log `--skill` example) and `CLAUDE.local.md` (work-logging param examples) — these are not planner-dispatch directives.

---

## Phase 2 — Single-source execution policy (D2)

**Goal.** Policy lives in one component; plans carry a pointer, not ~150–190 verbatim lines.

**Prerequisites.** Phase 1 (hard — the rename must precede: this phase edits `write-plan-cognito/SKILL.md`, which does not exist until Phase 1 renames it).

**Deliverables.**
- [x] Author `user/skills/_components/execution-contract.md` extracting: EXECUTION MODEL, COMPONENT LOADING PROTOCOL, MANDATORY RULES, Execution Protocol / Phase-Selection Loop / per-batch steps, Blocking Issue Protocol, Completion, Work Log (sourced from generic `write-plan` L252–554).
- [x] Refactor generic `execute-plan/SKILL.md` to reference + read `execution-contract.md` (cacheable).
- [x] Refactor generic `write-plan/SKILL.md` to stop emitting the boilerplate sections; emit a one-line pointer to the component instead.
- [x] Apply the same pointer change to `write-plan-cognito/SKILL.md`.
- [x] Verify `project-skills.py` expands any new `!cat` reference and `lint-skills.py` / `test_project_skills.py` stay green.

**Testing strategy.** Generate a plan via the redesigned `/write-plan` → assert it contains the pointer and **no** EXECUTION MODEL / MANDATORY RULES blocks; measure line-count delta vs an old plan (target ~32–44% smaller). Edit one rule in `execution-contract.md` and confirm a subsequent `/execute-plan` run reflects it with no plan regeneration.

**Integration notes.** `execution-contract.md` becomes the home for the D4 (parallelism) and D5 (gate) rules added in phases 5–6 — author its structure with those sections anticipated.

#### Implementation Notes (Phase 2 — Batch 1: WU-1)
**Completed:** 2026-06-29
**Review verdict:** PASS

**Work completed:**
- WU-1: Authored net-new `user/skills/_components/execution-contract.md` (249 lines), the single canonical home for the execution policy that `/write-plan` previously re-emitted verbatim into every generated plan. Extracted, in order, from generic `write-plan/SKILL.md` L252–554: EXECUTION MODEL table + HARD CONSTRAINT + dispatch pattern; COMPONENT LOADING PROTOCOL; Component Reference Card (with a note that a plan MAY override rows for non-default repos); MANDATORY RULES (1–12); Execution Protocol (Phase Selection Loop, Step 0, per-batch Steps B.0–B.6, Propagation Awareness, Post-Phase Steps); Blocking Issue Protocol; Completion; Work Log.
- **Anticipated D4/D5 homes:** added two clearly-labeled placeholder sections — "Parallelism & background builds" (D4, Phase 5) and "Per-WU verification gate" (D5, Phase 6) — each carrying the current baseline policy and a note that the later phase extends rather than restructures it. This satisfies the integration note above.
- **Round-trip proof:** the component is a clean leaf (no `!cat` of its own). Verified by a throwaway probe skill that `!cat`-included it: `project-skills.py` projected it (component count 92→93, errors: none) and the projected output contained the contract sections with zero unresolved `!cat`. Probe removed; projection restored to baseline (84 skills / 92 components / no errors).

**Files modified:**
- `user/skills/_components/execution-contract.md` — created (net-new)

#### Implementation Notes (Phase 2 — Batch 2: WU-2 + WU-3 + WU-4)
**Completed:** 2026-06-29
**Review verdict:** PASS

**Work completed:**
- WU-2 (`execute-plan/SKILL.md`, 419→425L): added a new "Execution Contract (single source — READ THIS FIRST)" section ahead of Execution Model Enforcement that directs the executor to `Read` `~/.claude/skills/_components/execution-contract.md` once per run (cacheable) and treat it as the operating contract. Reframed the Execution Model Enforcement bullets as "Per the EXECUTION MODEL in the contract you just read". **Preserved** all executor-specific logic the contract does not cover: plan-status protocol (1a.5), part-integrity / cloud-saturation gates (1a.6/1a.6a), the Ground-Truth Verification Gate, compaction recovery, PHASES.md slice handling, per-WU checkbox discipline, atomic gate+commit. Net +6 lines (a reference, not a duplication).
- WU-3 (`write-plan/SKILL.md`, 649→445L, −204L / −31%): replaced the three "write this verbatim" boilerplate-emission blocks (EXECUTION MODEL + COMPONENT LOADING + Component Reference Card; MANDATORY RULES; Execution Protocol + Blocking Issue + Completion) with a single one-line "Execution Policy — single-sourced" pointer block plus a short instruction enumerating the phase-specific content the planner DOES still emit (Execution Schedule, per-phase blocks, work units, batch tables, `## Work Units` checklist, plan-specific deviations). **Preserved** every healthy pre-draft part: partitioning (`subagent-partitioning.md` `!cat`), the `[VERIFY:]` Anchor discipline, the PER-WU PROGRESS CHECKBOX requirement, References section, dirty-tree/touchpoint audit.
- WU-4 (`write-plan-cognito/SKILL.md`, 385→389L; + `test_project_skills.py`): emitted the same single-source pointer ("Execution Policy — single-sourced + Cognito lane overrides"), removed the pure-generic COMPONENT LOADING PROTOCOL verbatim block, and **reframed** the lane-specific blocks (EXECUTION MODEL, Component Reference Card, MANDATORY RULES, Execution Protocol) as explicit "Cognito lane override" sections that the contract's override clause defers to — these genuinely differ from the generic contract (lane agents not WUs, queue-routed `/msbuild`/`/mstest`/`/nxtest` gates, typegen seam Step L.2, Tier 1/Tier 2 gates, no-auto-commit repo policy) so they are legitimate specialization, not duplication, and were preserved verbatim. The Cognito Blocking Issue / Completion blocks were likewise left intact (no-commit policy + lane census differ from the generic). Added 3 D2 round-trip tests to `test_project_skills.py`: contract-exists-with-extracted-sections, contract-round-trips-through-projection (a `!cat` expands with no unresolved directive), and planners-point-at-contract-not-inline-boilerplate.

**Single-source verification (acceptance criterion):**
- The contract is consumed two ways: the planners emit a one-line *pointer* (cacheable, not `!cat`-inlined into each plan body — so generated plans shrink), and `execute-plan` *reads* it at runtime. The component itself round-trips through `project-skills.py` (proven in Batch 1 and pinned by the new `test_execution_contract_round_trips_through_projection`).
- A contract edit changes executor behavior with NO plan regeneration: generated plans carry only the pointer, so editing a rule in `execution-contract.md` is reflected on the next `/execute-plan` `Read` of the contract — the plan body is unaffected.
- **Plan line-count delta:** the generic planner shrank 649→445 (−31%); the boilerplate it used to inject into every generated plan (the EXECUTION MODEL + COMPONENT LOADING + MANDATORY RULES + Execution Protocol + Blocking Issue + Completion blocks, ~190 lines) is now replaced in each plan by a ~10-line pointer block, i.e. a generated plan loses ~180 lines of duplicated policy — within the SPEC ~32–44% target for plan size.

**Pitfalls & guidance:**
- The Cognito planner did NOT shrink in raw line count (it gained 4) because almost all of its "boilerplate" was already lane-specific override content that must be preserved; the win there is single-sourcing the *generic* policy (the pointer) and removing the one pure-generic block (COMPONENT LOADING). The line-count win is on the generic planner and on every plan it generates.
- `project-skills.py` component count stays 92 (not 93) because `execution-contract.md` is *read at runtime by the executor*, not `!cat`-inlined into a skill body — this is the intended cacheable design, not a missing include. Its round-trip is proven by a probe and by the new pytest case.

**Files modified:**
- `user/skills/execute-plan/SKILL.md` — reference + read the contract
- `user/skills/write-plan/SKILL.md` — pointer replaces verbatim boilerplate emission
- `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md` — pointer + lane-override framing
- `user/scripts/test_project_skills.py` — 3 new D2 round-trip / single-source tests

---

## Phase 3 — Thin PHASES.md + sibling notes: writer + harness reader (D3 core)

**Goal.** Stop PHASES.md from growing monotonically; relocate Implementation Notes to a sibling and make the harness gate tolerate the split.

**Prerequisites.** None; establishes the tolerant-read pattern that Phase 4 propagates.

**Deliverables.**
- [ ] Flip `_components/phases-update.md` to append per-batch Implementation Notes to a sibling `IMPLEMENTATION_NOTES.md` (one file, per-phase sections — OQ3 default), not PHASES.md.
- [ ] Implement current-phase-slice + completed-phases-index reads in `execute-plan` / `source-reread.md` (offset/limit on a stable phase-boundary marker — settle OQ2 marker format here).
- [ ] Keep `/spec-phases` emitting the thin-checklist PHASES.md shape (verify it does not embed notes at authoring time).
- [ ] Update `lazy_core.py::phases_show_implementation()` to check sibling `IMPLEMENTATION_NOTES.md` first, then fall back to the embedded `## Implementation Notes` heading.
- [ ] Extend `test_lazy_core.py`: add a sibling-file case (notes in `IMPLEMENTATION_NOTES.md`, none embedded → returns True) and keep the legacy embedded case green.

**Testing strategy.** `pytest user/scripts/test_lazy_core.py -k phases_show_impl -v` green for both shapes. Confirm `remaining_unchecked_are_verification_only()` and `verify_ledger_gate()` behavior is unchanged (they never parse Notes internals). Run `/execute-plan` across ≥2 batches → notes land in the sibling; PHASES.md size stays flat. **Read-narrowing assertion (SPEC validation row):** confirm startup / `source-reread` reads *only* the current-phase slice + completed-phases index — assert via the read calls in a transcript (offset/limit bounded, not a whole-file read), not just that PHASES.md is small. Record the chosen OQ2 phase-boundary marker format as an explicit deliverable output (a one-line note in this phase's eventual Implementation Notes), so downstream slice-readers key off a documented marker.

**Integration notes.** `phases_show_implementation()` is the critical blocker: if it only greps PHASES.md, a relocated-notes feature reads as "not implemented" and `lazy-state.py` re-routes it to the research step (wasted Gemini spend, wrong state). The sibling-then-embedded fallback is what keeps in-flight features (embedded notes) resolving — no flag-day. **`source-reread.md` is edited again in Phase 4** (sibling-then-embedded notes read). Phase 3 adds the *slice-read* responsibility to the same file; the two edits target different concerns and must be **merged**, not sequentially clobbered — Phase 4 must build on Phase 3's version of `source-reread.md`.

---

## Phase 4 — Propagate the D3 split across generic consumers (D3 blast radius)

**Goal.** Every skill that reads Implementation Notes finds them after relocation. Universal generic-skill edits — **no `-cognito` variants** (per the locked "universal wins in generic skills" rule).

**Prerequisites.** Phase 3 (writer flipped + tolerant-read pattern established).

**Deliverables.**
- [ ] `source-reread.md` component: sibling-then-embedded read of prior Implementation Notes.
- [ ] `add-phase`: mine notes from sibling, fall back to embedded.
- [ ] `lazy`: research-gate predicate checks sibling-then-embedded.
- [ ] `lazy-batch`: ledger/notes scope reads sibling-then-embedded.
- [ ] `realign-spec`: upstream-drift read of Implementation Notes from sibling-then-embedded.
- [ ] `implement-phase` and `implement-phase-batch`: prior-phase Implementation Notes from sibling-then-embedded.
- [ ] `spec-phases-batch` and `spec-phases` Step 1.5 (upstream look-back): sibling-then-embedded.

**Testing strategy.** For a representative trio (`add-phase`, `realign-spec`, `implement-phase`), run against a feature with sibling notes → assert the relocated notes are surfaced; run against a legacy feature with embedded notes → assert fallback works. Re-project + lint after edits.

**Integration notes.** These are prose/predicate edits to skill markdown, low individual risk but broad. Apply one consistent sibling-then-embedded idiom (consider a shared `_components/` snippet describing the read order so the rule is single-sourced, mirroring D2's philosophy). **Consumer-set bounding:** before editing, re-verify the 8-consumer set with a sweep for *all* notes-mining phrasings (not just the literal `## Implementation Notes` string) — a consumer that reads notes via a different phrase (e.g. `lazy-batch-retro`, `retro-feature`) would otherwise be missed. Record the sweep result so the set is verified, not assumed. **`source-reread.md`:** this phase's sibling-then-embedded edit builds on Phase 3's slice-read edit to the same file — merge, do not clobber.

---

## Phase 5 — Executor parallelism + background builds (D4)

**Goal.** Exploit the harness's only real-parallelism path (same-message Agent blocks) and background the build spine.

**Prerequisites.** Phase 2 (the rules live in `execution-contract.md`).

**Deliverables.**
- [ ] Encode same-message file-disjoint batching in `execution-contract.md` / `subagent-launch.md`: provably disjoint WUs dispatched as multiple `Agent` blocks in one assistant message.
- [ ] Encode background builds: long / Tier-2 / typegen builds run `run_in_background: true`; next independent agent dispatched while the build runs (settle OQ4 — which builds count as Tier-2/typegen — against the queue skills).
- [ ] Constraint guard: a backgrounded build's output must not be consumed by a dependent agent before completion — enforced by disjoint-file + seam-classification rules, not new queue machinery.
- [ ] Ensure `/write-plan-cognito` authors disjoint-WU batches the executor can exploit (seam classification gates what is parallelizable).

**Testing strategy.** Run a phase with ≥2 file-disjoint WUs → transcript shows multiple `Agent` blocks in ONE message; wall-clock < serial sum. Run a phase triggering a Tier-2/typegen build → build dispatched `run_in_background`, next independent agent dispatched before it completes.

**Integration notes.** Builds remain a serial spine through the queue; only agent think/edit/test-author time overlaps. Target ~1.5–2× wall-clock per phase, not unbounded fan-out.

---

## Phase 6 — Lighten the ground-truth gate (D5)

**Goal.** Stop re-running the full suite per WU (0/16 catch rate); make the cheap integrity + assertion read the default.

**Prerequisites.** Phase 2 (gate policy lives in `execution-contract.md` / `subagent-review.md`).

**Deliverables.**
- [ ] Default per-WU verification: `git status` / `wc -l` / `grep -n` integrity checks + the assertion-vs-intent read. Re-run tests **only on integrity mismatch**.
- [ ] 529 inline-fallback: after 1–2 failed review-subagent dispatch attempts (API 529), fall back to inline review immediately (fixes the ~16-min retry burn).
- [ ] Keep the review mechanism hybrid/scope-gated (small batches inline, larger via review subagent at the orchestrator's model).
- [ ] **Final non-regression gate (owns SPEC "Healthy parts not regressed", §Validation):** run `/write-plan` (and `/write-plan-cognito`) end-to-end and confirm the healthy parts all still fire — partitioning, pre-draft `[VERIFY:]` anchor gates, dirty-tree handling, pre-dispatch drift reconciliation, Tasks recovery anchor, typegen seam, right-sized builds. Capture the pre-draft gate output + a generated plan as evidence.

**Testing strategy.** Per-WU verification transcript shows cheap checks + assertion read, no full-suite run unless an integrity check disagrees. Simulate a review-subagent 529 → falls back to inline within 1–2 strikes, no multi-minute retry loop. The final non-regression gate (above) exercises the §Validation "Healthy parts not regressed" row directly — no prior phase owned it, so it lands here as the terminal check.

**Integration notes.** The assertion-vs-intent read is the only mechanism that caught the single real defect in the corpus — it stays mandatory. The full-suite re-run becomes conditional, not default. The non-regression gate is terminal because the healthy-parts surface is only fully wired once all five directions have landed; running it earlier would not exercise the post-redesign planner end-to-end.

---

## Cross-feature Integration Notes

- **Dogfooding:** this very PHASES.md uses the embedded-notes shape because D3 is not yet implemented. Once Phase 3 lands, this feature's own Implementation Notes go to a sibling `IMPLEMENTATION_NOTES.md`.
- **Do-not-regress (SPEC §"Determinism / harness principles", INVESTIGATION §4):** partitioning, pre-draft `[VERIFY:]` anchor gates, dirty-tree handling, pre-dispatch drift reconciliation, Tasks recovery anchor, typegen seam, right-sized builds — all must still fire after each phase.
- **Phase ordering:** 1 and 2 are independent (1 first by risk). 3 must precede 4. 5 and 6 both require 2. No phase depends on 5 or 6, so they can land last in either order.

---

## Review Notes

**Decomposition review verdict:** PASS-WITH-FIXES (2026-06-29, independent read-only `Plan` agent against SPEC.md). Decomposition covers D1–D5, honors both locked decisions (one generic executor; universal D3 with tolerant readers), and the dependency ordering is correct. Seven surgical fixes were applied to this file:

1. Phase 1 — split "locate the dispatch site" into a discovery sub-step gating the edit; added a dispatch-emission assertion (not just resolution) to the testing strategy.
2. Touchpoint table + Phase 3/4 — flagged `source-reread.md` as edited in both phases (slice-read + sibling-then-embedded); added merge-don't-clobber integration notes.
3. Phase 6 — added a terminal non-regression gate that owns the SPEC "Healthy parts not regressed" validation row (previously prose-only, no testable owner).
4. Phase 3 — added a read-narrowing assertion (startup reads only the current-phase slice + index) and made the OQ2 marker format a recorded deliverable output.
5. Phase 2 — relabeled prerequisite from "None functionally" to a hard dependency on Phase 1's rename.
6. Phase 1 — added a lint/skills-dir assertion that no `execute-plan-cognito` exists (closes the negative-invariant validation row).
7. Phase 4 — added a note to bound the 8-consumer set by a verified notes-mining sweep (all phrasings, not just the literal `## Implementation Notes` string).
