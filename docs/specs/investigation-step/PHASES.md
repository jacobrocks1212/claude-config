# Implementation Phases — On-Demand Investigation Step (`/investigate`)

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config skill/component prose plus one additive, filename-keyed schema entry in AlgoBooth's docs checker; no app-runtime-observable behavior (build-tooling / docs-only class per `docs/features/mcp-testing/SPEC.md`).

**Status:** Complete
**Original phase count:** 2

## Validated Assumptions

All load-bearing assumptions are grep/test-confirmed; none carries a runtime-coupled smell (no sidecar/IPC/audio-observable behavior is in play — the deliverables are prose plus one filename-keyed schema entry whose harness is vitest). Per-assumption determinations are stated in the ledger rows.

| assumption | how-confirmed (`grep` / `runtime` / `spike`) | evidence |
|---|---|---|
| `validation_escalation: true` is emitted by both blocked terminals at `blocker_kind: mcp-validation` + `retry_count >= 2` | grep + test harness | lazy-hardening P11 WU-1a (2026-06-11): `lazy_core.validation_escalation`, lazy-state Step 3 ~L1299, bug-state Step 3 ~L758; tests `test_lazy_state_blocked_escalation_payload` et al., suite 241/241 |
| the escalation seam-audit contract + `## Seam Enumeration` BLOCKED.md section already exist for `/investigate` to consume | grep | `blocked-resolution.md` step 1a; mcp-test SKILL "Seam Enumeration" subsection; `cycle-base-prompt.md` R14 SEAM ENUMERATION bullet (all P11 WU-1b/c) |
| AlgoBooth sentinel validation is filename-keyed and additive: adding `INVESTIGATION.md` to `SENTINEL_SCHEMAS` is the complete integration; unrecognized files are ignored today (zero migration risk) | grep | `check-docs-consistency.ts:782` `SENTINEL_FILENAMES = Object.keys(SENTINEL_SCHEMAS)`; unknown-keys rule at `:2290`; `MCP_TEST_RESULTS.md` permanent-audit precedent. Code-provable — pure config-map lookup, no runtime smell (determination per gate Step A) |
| the per-repo `!cat`-with-fallback hook pattern is established for repo-specific guidance injection | grep | `phases-review-guardrails`, `reuse-first-discovery`, `team-architect-stance` hooks in spec/spec-phases/add-phase; `.claude/skill-config/` precedents (quality-gates, commit-policy, cycle-prompt-addenda) |
| ad-hoc component-template-owned dispatches (not `lazy-state` cycle emissions) are an established class — no state-script change is needed for v1 | grep | `blocked-resolution.md` step 6 apply-subagent dispatch; `decision-resume.md`; Step 1e.4a recovery dispatch. Code-provable — dispatch-shape precedent, no runtime smell |

## Touchpoint Summary

| File | Audit verdict | Disposition |
|------|---------------|-------------|
| `scripts/check-docs-consistency.ts` (AlgoBooth, 2,821 LOC) | **block** (`LOC 2821 > fail threshold 1500`, no baseline entry; recommendation `split-first`) | **Deliberate exception — see §Plan Notes.** This plan's change is a ~20-line additive `SENTINEL_SCHEMAS` entry + tests, identical in class to the last three rule additions (`2e315e4e`, `321441aa`, `8b63c017`) |
| All other targets | n/a | New files (`user/skills/investigate/SKILL.md`, `_components/investigation-dispatch.md`, algobooth `investigation-runtime.md`) or claude-config markdown components (not audit subjects — no LOC-growth tooling applies to skill prose) |

---

### Phase 1: The artifact, the skill, and the schema (both repos)

**Status:** Complete

**Scope:** Everything that defines what an investigation IS: the `/investigate` skill contract, the orchestrator-side dispatch template, the `INVESTIGATION.md` artifact schema in both lockstep locations, and AlgoBooth's repo runtime hook. After this phase a human can invoke `/investigate` standalone and produce a schema-valid artifact; no pipeline trigger fires yet (Phase 2).

**Deliverables:**
- [x] `user/skills/investigate/SKILL.md` — NEW. Frontmatter (`name: investigate`, description with USE WHEN wording covering the three trigger classes + standalone use). Body sections:
  - **Arguments:** `<spec-or-bug-dir> [symptom...]` (+ `--batch` no-op note: the skill is already non-interactive by design — it asks nothing; honest terminal states replace questions).
  - **Inputs read:** BLOCKED.md (incl. `## Seam Enumeration` when present — the starting checklist), MCP_TEST_RESULTS.md, the feature's PHASES.md Validated Assumptions ledgers, prior `INVESTIGATION.md` rounds, orchestrator-passed hypotheses (which MUST arrive labeled `unproven`).
  - **Method:** reference `systematic-debugging` (root-cause-before-fix discipline) + the four-attempt-trap rule (no code-read confirmation of runtime-coupled claims) + control runs when attributing causality to a change.
  - **The five contract rules** from SPEC §"The cycle contract", verbatim in force: (1) no production fixes — allowed commits are the artifact, `diag(<feature_id>):`-prefixed off-hot-path instrumentation (reverted or disclosed-retained), and tests driving REAL components; (2) no fire-and-forget (mcp-test wording: blocking foreground waits, owed artifact on disk before turn end); (3) runtime ownership incl. binary-freshness verification before trusting observations; (4) hypothesis-ledger discipline (no confirmed/refuted without a cited evidence artifact); (5) honest terminal states (`inconclusive` legal, with the seam table showing exactly what remains `unprobed` and why); plus WORK-BRANCH-ONLY commits.
  - **Artifact authoring section:** the full `INVESTIGATION.md` schema (frontmatter + the five body sections from SPEC §"artifact contract"), the append-rounds rule (one file, `## Investigation N` rounds), and the freshness semantics (`investigated_commit` vs HEAD; own `diag(...)` commits don't stale it).
  - **Repo runtime hook:** `!cat .claude/skill-config/investigation-runtime.md 2>/dev/null || true` with generic fallback guidance (find the repo's dev lifecycle docs; no repo-specific instructions inline).
- [x] `user/skills/_components/investigation-dispatch.md` — NEW. The ad-hoc dispatch template (same class as blocked-resolution's apply-subagent prompt — NOT a `lazy-state` cycle emission; states this explicitly). Contains: the full subagent prompt with runtime placeholders fillable from state-script JSON + orchestrator context (`{feature_id}`, `{feature_name}`, `{spec_path}`, `{cwd}`, `{work_branch}`, `{trigger}`, `{symptom}`, `{inherited_hypotheses}`); the inherited-hypotheses-are-unproven rule; model: opus; Skill-tool permission for `/investigate`; the no-Agent-tool rule; a coupling note naming the consumers (the three batch SKILLs + blocked-resolution + halt-resolution, wired in Phase 2).
- [x] `user/skills/_components/sentinel-frontmatter.md` — `INVESTIGATION.md` schema section (`kind: investigation`; required: `feature_id`, `date`, `trigger`, `status`, `investigated_commit`; enums per SPEC; lifetime: permanent audit artifact, MCP_TEST_RESULTS-class, explicitly NOT a halt sentinel — the state scripts do not key on it; lockstep note to AlgoBooth `SENTINEL_SCHEMAS`).
- [x] AlgoBooth `scripts/check-docs-consistency.ts` — `SENTINEL_SCHEMAS['INVESTIGATION.md']` entry (kind/required/enumFields for `trigger` + `status`, `dateFields: ['date']`, `stringFields: ['investigated_commit']`), comment citing the lockstep source and the permanent-audit class.
- [x] Tests: AlgoBooth `scripts/__tests__/check-docs-consistency.test.ts` — well-formed artifact ⇒ zero violations AND zero `sentinel-unknown-keys` warnings; missing required field ⇒ `sentinel-required-fields`; bad `status` enum ⇒ flagged; `kind` mismatch ⇒ `sentinel-kind-matches-filename`. Mirror the RETRO_DONE `phase_count_at_retro` test structure (newest precedent).
- [x] claude-config `repos/algobooth/.claude/skill-config/investigation-runtime.md` — NEW (symlink-served into AlgoBooth): dev-app lifecycle pointer (`docs/development/CLAUDE.md`, fresh `logs/session-*/` resolution, NEVER cache), MCP tool guidance pointer (`MCP_USAGE_GUIDE.md` + registrations dir; POST-method warning), `load_test_tone`/`get_audio_buffer` observability note, the NEVER-instrument-the-audio-callback-hot-path prohibition, audio INVARIANTS.md gate pointer.

**Minimum Verifiable Behavior:** `python user/scripts/lint-skills.py` exits 0 with the new skill + component present; AlgoBooth checker vitest green including the new INVESTIGATION.md cases; a synthetic well-formed `INVESTIGATION.md` dropped in a scratch feature dir validates clean through `npx tsx scripts/check-docs-consistency.ts` (then removed).

**Runtime Verification** *(checked at execution time — NOT by the doc author)*:
- [x] AlgoBooth checker vitest suite green with the new schema cases; `qg:docs-consistency` rc=0 repo-wide after the schema lands
- [x] All three claude-config regression gates green, baselines byte-identical (v1 touches no state scripts — this is the no-regression tripwire)

**MCP Integration Test Assertions:**
N/A — no app-runtime-observable behavior (docs/build-tooling class; see header line).

**Prerequisites:** None (lazy-hardening P11 surfaces this consumes are already on main).

**Files likely modified:**
- claude-config: `user/skills/investigate/SKILL.md` (NEW), `user/skills/_components/investigation-dispatch.md` (NEW), `user/skills/_components/sentinel-frontmatter.md`, `repos/algobooth/.claude/skill-config/investigation-runtime.md` (NEW)
- AlgoBooth: `scripts/check-docs-consistency.ts`, `scripts/__tests__/check-docs-consistency.test.ts` (one atomic explicit-path commit; live-session co-tenancy rules apply)

**Testing Strategy:**
- Entry point: the AlgoBooth checker's exported `validate()` driven by the real vitest harness — the same entry production (`qg:docs-consistency`) uses; the synthetic-artifact smoke drives the real CLI.
- Ground-truth assertion: concrete rule-id literals (`sentinel-required-fields`, `sentinel-kind-matches-filename`) and zero-warning counts — not re-computations.
- Boundary coverage: the only boundary is claude-config schema doc ↔ AlgoBooth schema map (lockstep-by-convention); covered by the vitest cases asserting the exact field set documented in `sentinel-frontmatter.md`.
- Runtime gate: none (N/A class) — the checker vitest + lint ARE the gates.
- claude-config side: `lint-skills.py` + all three regression gates (unchanged baselines prove no script coupling leaked in).

**Integration Notes for Next Phase:**
- Phase 2 wires triggers by REFERENCE to the dispatch component — never inline copies of the prompt (Phase 8 lesson: hand-synced inline copies drift).
- The freshness rule (`investigated_commit` + own-`diag` tolerance) is defined here in the skill/schema; Phase 2's consumption hooks cite it rather than restating it.

#### Implementation Notes (Phase 1)
**Completed:** 2026-06-11
**Review verdict:** PASS (orchestrator-authored prose reviewed inline against the SPEC contract; AlgoBooth half implemented + verified by a dedicated subagent)
**Work completed:**
- `user/skills/investigate/SKILL.md` — full cycle contract per the deliverable spec (all five rules + WORK-BRANCH-ONLY, artifact authoring section with full schema/append-rounds/freshness, repo runtime hook via `!cat`-with-fallback, structured return format). The skill appeared in the live session skill list immediately via the symlink.
- `user/skills/_components/investigation-dispatch.md` — triggers, no-narrative-as-fact rule, full dispatch prompt (single source — `grep -c` of the prompt's distinctive line across all skills = 1), consumption guidance, coupling note.
- `sentinel-frontmatter.md` — `INVESTIGATION.md` section inserted after MCP_TEST_RESULTS (same permanent-audit class), with freshness semantics + lockstep note.
- AlgoBooth (subagent): `SENTINEL_SCHEMAS['INVESTIGATION.md']` at check-docs-consistency.ts:638-654; docs/features/CLAUDE.md "Eleven recognized filenames" + table row; 4 new vitest cases — **37/37 green**, repo-wide checker **rc 0**, synthetic-artifact smoke clean (placed/validated/removed).
- `repos/algobooth/.claude/skill-config/investigation-runtime.md` — seeded with dev-lifecycle, binary-freshness, MCP-tool, hot-path-prohibition, and scheduler-liveness guidance (each item traced to a live-run incident).
**Pitfalls & guidance:**
- ⚖ Co-tenancy collision: the live d8 session's commit `853fe009` swept the agent's three AlgoBooth files into its own commit before the agent could commit (the live session stages broadly per AlgoBooth's commit-scope rule). Content verified byte-identical via `git show` and already pushed — no separate `feat(docs-gate)` commit exists for the AlgoBooth half; this note is the provenance record.
- The skill description's USE WHEN wording is the discovery surface — keep the three trigger names in it if ever edited.
**Files modified:** claude-config: 3 new + 1 edited (above); AlgoBooth: via co-tenant commit `853fe009`.

---

### Phase 2: Triggers and consumption (the wiring)

**Status:** Complete

**Scope:** Make the pipeline actually use the step: the three dispatch triggers, the no-narrative-as-fact rule, and downstream consumption in blocked-resolution → add-phase → write-plan. After this phase, an escalated BLOCKED routes through an investigation before a corrective phase is drafted, a failed fix's next dispatch is an investigation, and orchestrator dispatch prompts cite the artifact instead of authoring causal narratives.

**Deliverables:**
- [x] `user/skills/_components/blocked-resolution.md` — extend step 1a (the P11 escalation check): when `validation_escalation` is flagged AND no `INVESTIGATION.md` is current for the symptom (freshness per the Phase-1 rule), the resolution flow dispatches `/investigate` (via the investigation-dispatch component) BEFORE enacting any corrective-phase path; the subsequent `{ADD_PHASE}` description cites the artifact. The existing seam-audit requirement text is updated to name the investigation as its executor (the corrective phase consumes the artifact's seam table instead of re-deriving it).
- [x] `user/skills/_components/halt-resolution.md` — mirror in the blocked row (single-dispatch wrappers): same investigate-first rule at escalation.
- [x] The three batch orchestrator SKILLs (`user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`):
  - **Failed-fix trigger:** when a fix cycle lands and the post-fix live/validation check shows the symptom unchanged, the next dispatch for that issue is `/investigate`, not another fix cycle (cite the cycle-20 ~266k-token incident in one line).
  - **Inline-diagnosis budget** (probe-hygiene sections): more than ~8 inline diagnostic tool calls on one issue → STOP and dispatch `/investigate`; quick checks stay inline.
  - **No-narrative-as-fact rule:** dispatch prompts reference `INVESTIGATION.md` (or state "cause unknown — investigation pending"); inherited hypotheses are passed labeled `unproven`, never as evidence headers.
  - Cloud variant: note that `/investigate` is workstation-class work (needs the live runtime) — cloud orchestrators record the trigger and defer dispatch to a workstation run rather than running it cloud-side.
- [x] `user/skills/add-phase/SKILL.md` — consumption hook in Step 3.5 + the Step-4 seam-audit paragraph: when a current `INVESTIGATION.md` exists, its confirmed hypothesis-ledger rows are citable as `runtime` evidence in the corrective phase's Validated Assumptions ledger (evidence column cites the artifact + its evidence artifact), and its `## Recommended Fix Scope` seeds the phase's Files-likely-modified; a stale artifact is cited only with `(stale — re-verify)`.
- [x] `user/skills/write-plan/SKILL.md` — citation hook: plans for corrective phases reference the artifact's repro recipe + fix scope; spike WUs that duplicate already-confirmed ledger rows are skipped (cite the row instead).
- [x] Tests: grep-assertion checklist executed and recorded in Implementation Notes — investigate-first wording present in both resolution components; all three batch SKILLs carry the three trigger rules; add-phase + write-plan consumption wording present; dispatch-template reference (never inline copy) verified by `grep -c` of the prompt's distinctive lines across consumers (must be 1 — the component only).

**Minimum Verifiable Behavior:** the grep-assertion checklist above passes; `lint-skills.py` exits 0; a dry-read of `investigation-dispatch.md` with all placeholders bound from a real state-script JSON sample leaves zero `{unknown_token}` residue.

**Runtime Verification** *(checked at execution time — NOT by the doc author)*:
- [x] All three claude-config regression gates green, baselines byte-identical (still no script changes)

**MCP Integration Test Assertions:**
N/A — no app-runtime-observable behavior (same class as Phase 1).

**Prerequisites:**
- Phase 1: the skill, dispatch component, and artifact schema exist (every hook added here references them).

**Files likely modified:**
- claude-config: `user/skills/_components/{blocked-resolution,halt-resolution}.md`, `user/skills/{lazy-batch,lazy-bug-batch,add-phase,write-plan}/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`

**Testing Strategy:**
- Entry point: the consuming documents themselves (prose wiring) — verification is mechanical grep assertions + lint, the same harness that gates every prior prose phase in lazy-hardening.
- Ground-truth assertion: literal wording presence/absence + reference-not-copy counts (`grep -c` = 1 for dispatch-prompt distinctive lines).
- Boundary coverage: none crossed (single-repo prose, plus the cloud mirror which is part of the consumer set checked).
- Runtime gate: none (N/A class). The three claude-config regression gates re-run as the no-coupling tripwire.

**Integration Notes for Next Phase:**
- (No further phases planned.) Follow-up candidates recorded in SPEC §Open Questions: mechanical state-script gate (refuse corrective-phase routing at escalation without a fresh artifact), retro grading anchors for investigation cycles, `plan-bug`/`fix` out-of-band consumption.

#### Implementation Notes (Phase 2)
**Completed:** 2026-06-11
**Review verdict:** PASS (grep-assertion checklist below; all gates re-run fresh)
**Work completed:**
- `blocked-resolution.md` — "Investigate FIRST" block added to step 1a (current-artifact check, dispatch-and-wait, artifact-cited `{ADD_PHASE}` description, cloud defer note) + step 6 ESCALATION clause now consumes `INVESTIGATION.md`.
- `halt-resolution.md` — blocked-row escalation now routes investigate-first and consumes the artifact.
- `lazy-batch/SKILL.md` — full trigger paragraph in Step 1a (three triggers + ~8-call inline-diagnosis budget + no-narrative-as-fact, with measured-cost citations); `lazy-bug-batch/SKILL.md` — by-reference applicability note (bug id rides in `feature_id`); `lazy-batch-cloud/SKILL.md` — record-and-DEFER variant (workstation-class work; no cloud dispatch) with the no-narrative rule still binding.
- `add-phase/SKILL.md` — "Consume INVESTIGATION.md" paragraph (confirmed rows citable as `runtime` evidence, refuted rows un-plannable, fix scope seeds file lists, stale = `(stale — re-verify)`, flag-the-gap rule).
- `write-plan/SKILL.md` — citation bullet in 1c.5 (cite repro/fix-scope; skip spikes duplicating confirmed rows; never plan against refuted rows).
**Grep-assertion checklist (executed):** investigation-dispatch.md referenced by both resolution components (2/2) and all three batch SKILLs (3/3); INVESTIGATION.md consumption present in add-phase + write-plan (2/2); dispatch prompt's distinctive line found in exactly 1 file (the component). `lint-skills.py` rc 0; all three regression gates green with `git status user/scripts` empty (zero script coupling — v1 is prose-only as designed).
**Pitfalls & guidance:**
- The trigger paragraph cites measured costs (~266k tokens, ~60% orchestrator activity) from the 2026-06-11 live run — keep those literals if rewording; they are the argument.
**Files modified:** `user/skills/_components/{blocked-resolution,halt-resolution}.md`, `user/skills/{lazy-batch,lazy-bug-batch,add-phase,write-plan}/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.

---

## Plan Notes

**Touchpoint-audit exception (deliberate, documented):** `scripts/check-docs-consistency.ts` (AlgoBooth) returned `block` (2,821 LOC > 1,500 fail threshold, no baseline entry, recommendation `split-first`). Decomposing AlgoBooth's checker is out of scope for this claude-config pipeline feature: the planned change is a ~20-line additive, filename-keyed `SENTINEL_SCHEMAS` entry + tests — the identical change-class as the three most recent rule additions (`2e315e4e`, `321441aa`, `8b63c017`), none of which destabilized the file. The block verdict is real tech debt owned by AlgoBooth: **follow-up candidate** — decompose `check-docs-consistency.ts` (rules/, schemas/, parsers/ modules) under AlgoBooth's own tech-debt track, where the file's tests (49+ vitest cases) make a behavior-preserving split practical. Recorded here per the audit gate's exception protocol; non-interactive run, so the exception is disclosed in the session summary rather than via `AskUserQuestion`.
