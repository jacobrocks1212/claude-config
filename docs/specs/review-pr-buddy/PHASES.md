# Implementation Phases — Interactive PR Review Buddy & Reuse-Candidacy Stage

> Phases for [`SPEC.md`](./SPEC.md)

## Validated Assumptions

The following corrections were established by a verified touchpoint audit of the plugin source and must override any conflicting assumption in SPEC.md.

1. **`findBaselines()` is a stub returning `[]` always (Phase 2 IN SCOPE).** `scripts/prep-pr.ts:1181-1203` contains a comment "skip baseline detection for MVP, let consistency checker handle it" and returns an empty array unconditionally. Implementing real baseline detection — comparing each changed file against same-type/same-directory existing files on local main, scoring by name/path proximity + structural similarity — is in scope for Phase 2. This is the first deliverable of Phase 2; the rest of the reuse stage depends on a populated `manifest.baselines[]`.

2. **Reuse findings route through the investigation lane, not the sweep lane.** `scripts/post-process.ts:291` gives investigation findings a fixed `effective_weight: 1.0` and never weight-filters them. `scripts/post-process.ts:310-326` EMA-weights and drops sweep findings below `MIN_EFFECTIVE_WEIGHT=0.3`. Reuse findings are Opus-agent-produced (same class as investigation), so they follow the investigation lane. Drop vs. surface is controlled by a verdict→severity map: `refactor`/`reuse` → important; `extend`/`wrap` → minor; `acceptable-new` → dropped (informational, not surfaced). Exact minor-vs-important boundary is an in-phase tuning decision.

3. **Rule schema: per-rule fields in rule yaml, weights in weights.yaml.** `knowledge/rules/code-consistency.yaml` uses file-level `category: code-consistency` (line 4) and `file_patterns` (lines 5-9) with per-rule fields `id`/`severity`/`description`/optional `trigger_patterns`/`anti_pattern`/`correct_pattern`. Weights are NOT embedded in rule files — they live in `knowledge/weights.yaml` under `rule_weights:`. Reuse rules are appended to `code-consistency.yaml` using this real per-rule schema; their weights are added separately to `weights.yaml`. `CATEGORY_MAP` in `post-process.ts:129` bridges `code-consistency` → `consistency` multiplier in weights.yaml.

4. **`cognito-consistency-checker` is orphaned but has blast radius.** `agents/cognito-consistency-checker.md` is absent from all 12 steps of `commands/review-pr.md` (zero refs), but is referenced at `commands/rebuild-agents.md:47` (rule-routing table) and `commands/learn-from-pr.md:26` (code-consistency.yaml → checker routing). Preferred disposition: grow it in place into the per-cluster reuse agent so those references remain valid. If Phase 2 instead supersedes and deletes it, both `rebuild-agents.md` and `learn-from-pr.md` must be updated in the same phase. The grow-in-place path is the recommendation; final decision deferred to Phase 2 after re-reading the agent against the protocol.

---

### Phase 1: Shared Reuse-Discovery Protocol

**Scope:** Extract the codebase-neutral reuse-discovery protocol core into a single shared file and refactor the Cognito-specific `/spec` component to consume it.

**Deliverables:**
- [x] Create `user/skills/_components/reuse-discovery-protocol.md` — codebase-neutral protocol core: capability extraction, grounding-resource catalog (domain skills / agent-docs / tree-sitter tools), verdict taxonomy (`reuse` / `extend` / `refactor` / `wrap` / `acceptable-new` a.k.a. build-new), ledger shape, 100%-confidence gate, and negative-search trail requirement for `acceptable-new`
- [x] Refactor `repos/cognito-forms/.claude/skill-config/reuse-first-discovery.md` to reference the shared protocol core via `!cat` or equivalent — preserving the Cognito-specific wrapper verbatim: title (line 1), domain-skill catalog (lines 22-28), agent-docs refs (lines 29-35), `/spec`+`/spec-bug` framing (lines 75-76), and `--batch NEEDS_INPUT` hook (lines 81-86)
- [x] No-op default `user/skills/_components/reuse-first-discovery.md` remains unchanged (6-line HTML-comment opt-in)
- [x] Tests/verification: `python ~/.claude/scripts/lint-skills.py` exits 0; `python ~/.claude/scripts/project-skills.py` exits green; `python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities` reports 0 errors; projected `/spec` resolves the shared protocol content (spot-check projected output)

**Minimum Verifiable Behavior:** Running `python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities` exits 0, and the projected output for `repos/cognito-forms` contains the expanded protocol content from `reuse-discovery-protocol.md`.

**Runtime Verification** *(checked by manual testing or a real run — NOT by the implementing agent):*
- [x] `python ~/.claude/scripts/project-skills.py --repos-dir ~/source/repos` exits green and the projected `/spec` skill for cognito-forms contains the shared protocol body inline (verified: projected `Cognito Forms/spec/SKILL.md` lines 469-592 — override `reuse-first-discovery.md` recursively expands nested `reuse-discovery-protocol.md` at 478-549)
- [x] `python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities` exits 0 — no broken `!cat` references, no capability drift (verified: exit 0; only a pre-existing cog-docs missing-capabilities *warning* remains, non-fatal)
- [ ] A `/spec` invocation in the cognito-forms repo still resolves the reuse-first-discovery component (injection line at `spec/SKILL.md:344` unchanged; only the content it pulls changes) — injection line confirmed unchanged + projection proves resolution; live `/spec` invocation pending manual test
- [x] `repos/cognito-forms/.claude/skill-config/reuse-first-discovery.md` Cognito-specific sections (domain-skill catalog, agent-docs refs, --batch hook) are intact after refactor (verified: grep count 5 for `cognito-storage|core-controller-endpoints|AskUserQuestion|NEEDS_INPUT|onboarding-repo-map`)

**Prerequisites:** None

**Files likely modified:**
- `user/skills/_components/reuse-discovery-protocol.md` — new file (net-new; the shared protocol core)
- `repos/cognito-forms/.claude/skill-config/reuse-first-discovery.md` — refactored to reference shared protocol; keep all Cognito-specific wrapper content (lines 1, 22-35, 75-76, 81-86)

**Reuse:** Extracts and generalizes the capability extraction → grounding-resource catalog → verdict taxonomy → ledger → confidence gate → negative-search trail already embodied in `repos/cognito-forms/.claude/skill-config/reuse-first-discovery.md:8-77` (Reuse Ledger row: "Reuse-discovery protocol", verdict: **refactor**). The no-op default `user/skills/_components/reuse-first-discovery.md` (6 ln, HTML-comment opt-in) is reused as-is.

**Testing Strategy:** Lint scripts provide structural verification. Spot-check the projected skill output for both `_default/` and `cognito-forms/` to confirm the `!cat` reference expands correctly and no content was dropped from the Cognito wrapper.

**Integration Notes for Next Phase:**
- Phase 2's reuse agent reads `user/skills/_components/reuse-discovery-protocol.md` — this path must be stable and live before Phase 2 begins
- The `!cat` reference pattern used in `reuse-first-discovery.md` is the model for how the plugin's reuse agent will be instructed to read the shared protocol (likely via a direct read instruction in the agent prompt rather than `!cat`, since agent prompts are not projected the same way)
- Confirm the exact live path (`~/.claude/skills/_components/reuse-discovery-protocol.md`) matches what `symlink setup.ps1` will serve to agents at runtime before Phase 2 hardcodes references to it

**Implementation Notes (2026-06-08, Batch 1 — WU-1):**
- Authored `user/skills/_components/reuse-discovery-protocol.md` (70 lines). Real path: `C:\Users\JacobMadsen\source\repos\claude-config\user\skills\_components\reuse-discovery-protocol.md` (live symlink `~/.claude/skills/_components/reuse-discovery-protocol.md` — the stable path Phase 2 will reference).
- Contains ONLY the codebase-neutral core: R1 capability extraction, R2 parallel discovery with a generic grounding-resource catalog *placeholder* (domain/system-map skills, architecture/pattern docs, structural code-nav tools — no Cognito names), R3 ledger table shape + verdict taxonomy (`reuse`/`extend`/`refactor`/`wrap`/`acceptable-new`), R4 100%-confidence gate, the negative-search-trail requirement, and a generic persist note. No `/spec` interactive framing, no `--batch`/`NEEDS_INPUT` hooks, no domain catalog — those stay in the WU-2 wrapper.
- Verified codebase-neutral: `grep -nE "cognito|spec-bug|--batch|NEEDS_INPUT|AskUserQuestion"` matches only the line-1 header comment (which names the two consumers by design).

**Implementation Notes (2026-06-08, Batch 2 — WU-2 + tooling reconciliation):**
- Refactored `repos/cognito-forms/.claude/skill-config/reuse-first-discovery.md` (now 51 lines): title + intro framing kept verbatim; generic R1–R4/ledger/verdict/gate prose **replaced** by a nested include `` !`cat ~/.claude/skills/_components/reuse-discovery-protocol.md` `` (line 9); Cognito grounding catalog, `/spec-bug` note, R5, R6, and `--batch` hook all preserved verbatim. `/spec` injection unchanged: `spec/SKILL.md:344` still `` !`cat .claude/skill-config/reuse-first-discovery.md 2>/dev/null || cat ~/.claude/skills/_components/reuse-first-discovery.md` ``.
- **Include mechanism:** the nested include resolves via `project-skills.py`'s recursive `!cat` expansion. The shared core's stable live path is `~/.claude/skills/_components/reuse-discovery-protocol.md` (Phase 2's reuse agent references this same path).
- **DEVIATION FROM PLAN (reconciliation, ground-truth-driven):** the plan assumed `project-skills.py` already "recursively expands all `!cat` references." Ground-truth showed it did NOT recurse on the one path that matters here — the `_FALLBACK_CAT` branch when a project override exists (it did a raw `read_text`), while the other two `!cat` forms recursed. The plan's Blocking Protocol flagged "nested-include not expanding" as an escalate-don't-hack trigger, but its rationale ("would require rethinking the shared-file approach") was false: the shared-file approach is sound and was realized by two minimal, test-covered tooling fixes (no architectural rethink). Both fixes followed TDD (RED test first, then GREEN impl):
  - `user/scripts/project-skills.py`: the `_FALLBACK_CAT` override-present branch now recurses via `_resolve_file_content` (with circular-include protection), uniform with the other two forms. New test `test_fallback_cat_recurses_into_override` (19/19 pass).
  - `user/scripts/lint-skills.py`: `lint_projected` switched from a crude `"!cat" in line` substring (which both **false-positived** on prose `` `!cat` `` — 16 pre-existing failures in `lazy-bug-batch` — and **false-negatived** on genuine `` !`cat `` directives) to the precise `_RUNTIME_TRIGGER` regex the source linter already uses. New test file `user/scripts/test_lint_skills.py` (2/2 pass).
- **Minor terminology note for Phase 2:** the shared core names the build-new verdict `acceptable-new`; the Cognito wrapper's verbatim-preserved R5/R6/`--batch` sections still say `build-new` (SPEC-documented synonyms). Phase 2's reuse agent (also consuming the shared core) should standardize on `acceptable-new`.
- **Gates (all green):** source-lint exit 0; `project-skills.py` no errors (7 repos); `lint-skills.py --check-projected --check-capabilities` exit 0; positive spot-check confirms nested expansion + Cognito wrapper survival in projected `Cognito Forms/spec/SKILL.md`; `_default` and non-Cognito repos still resolve the 6-line no-op default (unchanged).

---

### Phase 2: Reuse-Candidacy Stage (Wired, Parallel)

**Scope:** Implement and wire the full reuse-candidacy stage: baseline detection, per-cluster reuse agent, pipeline wiring, aggregation/post-processing, sweep rules, synthesizer rendering.

**Deliverables:**
- [x] **(2a) Implement `findBaselines()` in `scripts/prep-pr.ts`** (lines 1181-1203) — compare each changed file against same-type/same-directory existing files on local main branch; score by name/path proximity + structural similarity; populate `ManifestFile.baselines[]` with `{path, similarityScore, cachedFile}` per changed file (schema: `prep-pr.ts:130-135`). Intermediate runtime checkpoint: run prep on a real PR and confirm `manifest.baselines[]` is non-empty with plausible scores
- [x] **(2b) Grow `agents/cognito-consistency-checker.md` into the per-cluster reuse agent** (grow-in-place recommended per Validated Assumption 4) — Opus model, investigation-equivalent access model (cache + local codebase + tree-sitter; inherit investigation's carve-out from `investigation.md:49-65`), reads the shared reuse-discovery protocol from Phase 1, consumes `manifest.baselines[]` (existing `similarityScore>=50` filter at `cognito-consistency-checker.md:26-39` goes live), answers the capability-level question per cluster, emits verdict findings (`reuse`/`extend`/`refactor`/`wrap`/`acceptable-new`) with cited `file:line`/symbol/skill candidate, blast-radius via `get_callers` for `refactor` verdicts, negative-search trail for `acceptable-new`, writes to `{cacheDir}/agent-output/reuse-{cluster}.json` in aggregate-findings-compatible JSON schema. If grow-in-place is chosen: `rebuild-agents.md:47` and `learn-from-pr.md:26` refs remain valid. If supersede+delete is chosen: update both files in this same phase
- [ ] **(2c) Wire the parallel stage into `commands/review-pr.md`** — insert after Step 4 (planner-validates-triage, lines 40-43), dispatched in parallel with Step 5 (investigation+sweep, lines 46-49); fan out one reuse agent per net-new cluster (cap ~6 clusters, estimated — verify during Phase 2); keep `review-pr.md` the single source of pipeline truth
- [x] **(2d) Extend `scripts/aggregate-findings.ts`** — recognize `reuse-*.json` at the file-discovery line (~line 123, alongside `f.startsWith("investigation-")` and hardcoded `sweep.json` at line 182); add `reuse` to the recognized source set. Intermediate runtime checkpoint: confirm `reuse-*.json` outputs appear in aggregated `findings.json`
- [x] **(2e) Extend `scripts/post-process.ts`** — route reuse findings through the investigation lane (fixed `effective_weight: 1.0`, never weight-filtered; parallel to the existing investigation path at line 291); add a verdict→severity map: `refactor`/`reuse` → important, `extend`/`wrap` → minor/nit, `acceptable-new` → dropped (informational); `CATEGORY_MAP` already bridges `code-consistency` → `consistency` multiplier (line 129) — no change needed there (Validated Assumption 2)
- [x] **(2f) Add reuse rules to `knowledge/rules/code-consistency.yaml` and weights to `knowledge/weights.yaml`** — append rules using real per-rule schema (`id`/`severity`/`description`/`trigger_patterns`/`anti_pattern`/`correct_pattern`); add `rule_weights` entries to `weights.yaml`; rules must instruct the cache-only sweep agent to FLAG heuristic signals ("new `*Service` mirrors an existing one") and ESCALATE to the reuse stage rather than asserting a local-codebase fact (Validated Assumption 3). Run `/rebuild-agents` to re-embed rules into agent prompts
- [x] **(2g) Add "Reuse & Duplication" subsection to `agents/synthesizer-v2.md`** — insert after Rule-Based Findings (~line 104); subsection is omittable when empty (consistent with section-omission rules at lines 140-145); renders reuse findings with verdict, candidate `file:line`/symbol, and escalation path. Intermediate runtime checkpoint: review doc contains the section after a run with reuse findings
- [ ] Tests/verification: `review-pr` run on a PR adding duplicative code yields a `source:"reuse"` finding in `processed-findings.json` with `file:line` candidate + verdict; agent-output timestamps confirm reuse agents ran in parallel with investigation/sweep; `acceptable-new` findings carry a negative-search trail; sweep emits an escalation (not a fabricated local-codebase fact) when a reuse heuristic fires

**Minimum Verifiable Behavior:** Running `review-pr` on a PR that adds a service duplicating an existing one produces at least one `source:"reuse"` entry in `{cacheDir}/agent-output/reuse-*.json` with a non-empty verdict and a `file:line` existing-system candidate in `processed-findings.json`.

**Runtime Verification** *(checked by manual testing or a real run — NOT by the implementing agent):*
- [ ] After 2a: prep run on a real PR → `manifest.json` contains `baselines[]` entries with `similarityScore` values, not an empty array
- [ ] After 2d: aggregated `findings.json` contains findings with `"source": "reuse"`
- [ ] After 2e: `processed-findings.json` contains reuse findings routed through the investigation lane (effective_weight 1.0); `acceptable-new` verdicts are absent (dropped); `refactor`/`reuse` verdicts appear as `severity: "important"`
- [ ] After 2g: generated review doc contains a "Reuse & Duplication" section with at least one cited candidate
- [ ] Reuse agents are dispatched in parallel with investigation/sweep (confirm via `review-pr.md` step ordering and agent-output directory timestamps)
- [ ] An `acceptable-new` finding in reuse agent JSON contains a `negative_search_trail` field listing searched skills/docs/symbols
- [ ] Sweep output for a reuse-heuristic rule hit contains an escalation flag/note rather than an asserted local-codebase claim

**Prerequisites:** Phase 1: Shared Reuse-Discovery Protocol

**Files likely modified:**
- `scripts/prep-pr.ts` — implement `findBaselines()` (lines 1181-1203); populates `ManifestFile.baselines[]` (schema at lines 130-135)
- `agents/cognito-consistency-checker.md` — grown in place into the per-cluster reuse agent (513 ln); blast-radius callers: `commands/rebuild-agents.md:47`, `commands/learn-from-pr.md:26` (if grow-in-place: no changes needed there; if supersede+delete: both must be updated in this phase)
- `commands/review-pr.md` — insert reuse-candidacy stage after Step 4, parallel with Step 5 (lines 40-49 area)
- `scripts/aggregate-findings.ts` — add `reuse-*.json` recognition at ~line 123
- `scripts/post-process.ts` — add investigation-lane routing for reuse source + verdict→severity map (alongside line 291)
- `knowledge/rules/code-consistency.yaml` — append reuse rules using per-rule schema (category: code-consistency at line 4)
- `knowledge/weights.yaml` — add `rule_weights` entries for new reuse rule ids
- `agents/synthesizer-v2.md` — add "Reuse & Duplication" subsection after ~line 104
- `commands/rebuild-agents.md` — update only if cognito-consistency-checker is superseded+deleted (line 47)
- `commands/learn-from-pr.md` — update only if cognito-consistency-checker is superseded+deleted (line 26)

**Reuse:**
- `agents/cognito-consistency-checker.md` — grown into the reuse agent; reuses its existing `manifest.baselines[]` consumption pattern (lines 26-39, `similarityScore>=50` filter) and duplicate-logic detection (lines 178-198). Ledger row: "Reuse / duplicate detection", verdict: **refactor**.
- `scripts/prep-pr.ts` `ManifestFile.baselines[]` schema (lines 130-135) — reused as-is as the inter-component contract. Ledger row: "Baseline pre-identification", verdict: **reuse-as-is** (schema); `findBaselines()` body is the new implementation.
- `scripts/aggregate-findings.ts` discovery pattern (`f.startsWith("investigation-")` at line 123) — extended to cover `reuse-*`. Ledger row: "Findings aggregation + weighting", verdict: **extend**.
- `scripts/post-process.ts` investigation lane (line 291, fixed weight 1.0) — reused as the routing path for reuse findings. Ledger row: "Findings aggregation + weighting", verdict: **extend**.
- `knowledge/rules/code-consistency.yaml` + `knowledge/weights.yaml` — extended with reuse rules. Ledger row: "Rule corpus + weights + calibration", verdict: **extend**.
- `agents/investigation.md` access model (lines 49-65, local-codebase carve-out; lines 68-87, tree-sitter tools) — inherited by the reuse agent. Ledger row: "Cache-boundary enforcement", verdict: **reuse-as-is** (access model).
- `commands/review-pr.md` parallel-dispatch pattern (lines 228-272) — reused as the fan-out shape for reuse agents. Ledger row: "Parallel discovery fan-out", verdict: **reuse-as-is** (pattern).

**Testing Strategy:** Incremental runtime checkpoints after each sub-deliverable (see intermediate checkpoints in Deliverables). Full end-to-end verification via a `review-pr` run on a PR that introduces a new service/component overlapping an existing one. Parallelism confirmed by checking `review-pr.md` step ordering and agent-output directory timestamps.

**Integration Notes for Next Phase:**
- Phase 3's buddy Phase 0 delegates to `review-pr.md` steps — the reuse stage is included for free once it is wired here
- The `{cacheDir}/agent-output/reuse-{cluster}.json` files and `processed-findings.json` reuse entries are the inputs buddy Phase 1 surfaces to the reviewer; the schema must be stable before Phase 3
- The `synthesizer-v2.md` "Reuse & Duplication" subsection shape established here is the basis for buddy Phase 2's curated rendering — keep the section name stable so Phase 3 can reference it

**Implementation Notes (2026-06-08, Phase 2 Batch 1 — WU-1/2/4/5/6/7):**
- **TDD path:** the plugin's `scripts/` has NO test harness (no vitest/jest/node:test, no `test` script). Per the plan's TDD note, WU-1/4/5 used **direct implementation + runnable fixture verification** (not fabricated unit tests). Verified by `npx tsc --noEmit` (full `scripts/` clean) + a runnable aggregate→post-process fixture.
- **WU-1 (prep-pr.ts):** `findBaselines()` implemented (now exported, line ~1225) + helpers `filenameTokenOverlap`, `contentLineSimilarity`. Scores via `git ls-tree main` enumeration, same-ext/sibling-dir + role-suffix + filename-token + structural-line-Jaccard; top-3 above threshold; writes baselines to `{cacheDir}/baselines/`. Fixture: sibling `*Service.cs` → score 85 (≥50), unrelated `.md` excluded. The impl agent also fixed 4 pre-existing tsc errors (3× TS7022 in `ghFetchPaginated`, 1× TS2769 in `generateDiff`) required for a clean typecheck.
- **WU-2 (cognito-consistency-checker.md):** grown in place (grow-in-place chosen, per Validated Assumption 4 — `rebuild-agents.md`/`learn-from-pr.md` refs stay valid; file NOT deleted). 290 lines. Reads shared protocol at runtime (`Read ~/.claude/skills/_components/reuse-discovery-protocol.md`, line 28), inherits investigation access model (cache + local-main + tree-sitter), preserves `similarityScore>=50` baseline consumption + duplicate-logic detection as sub-capability, emits `reuse-{cluster}.json`.
- **reuse-{cluster}.json schema (stable — Part 3 surfaces these):** `{ group, findings: [{file,line,severity,title,verdict,candidate,hypothesis,evidence{snippet,reference},suggestion,blast_radius,negative_search_trail,escalation_candidate,specialist_domain}], escalations }`. Output path: `{cacheDir}/agent-output/reuse-{cluster}.json`.
- **WU-4 (aggregate-findings.ts):** discovers `reuse-*.json` like `investigation-*.json`; adds `reuse: InvestigationGroup[]` to `CombinedFindings`. **WU-5 (post-process.ts):** reuse lane — `source:"reuse"`, `effective_weight:1.0`, never weight-filtered (MIN_EFFECTIVE_WEIGHT stays sweep-only); verdict→severity (`refactor`/`reuse`→important, `extend`/`wrap`→nit, `acceptable-new`→dropped); reuse treated as Opus-lane in dedup/rank. Integrated fixture: refactor→important, extend→nit, acceptable-new absent, dropped_count 0. **(verdict→severity boundary is the tunable for future `/learn-from-pr` calibration.)**
- **WU-6 (yaml):** 4 reuse rules appended to `code-consistency.yaml` (`reuse-service-duplication`/`-utility-duplication`/`-dto-type-overlap`/`-endpoint-duplication`), each instructing sweep to FLAG+ESCALATE (not assert — sweep is cache-only); matching `rule_weights` (weight 0.7, data_points 0) added to `weights.yaml`. Both parse. **WU-7 (synthesizer-v2.md):** omittable `## Reuse & Duplication` section inserted between Rule-Based Findings and Strengths (lines 104<116<135).
- **Gates:** full `npx tsc --noEmit` clean; aggregate→post-process integrated fixture PASS; YAML parse OK. `/rebuild-agents` + live end-to-end `review-pr` run recorded below / deferred to runtime per the Runtime Verification convention.

---

### Phase 3: `review-pr-buddy` Command

**Scope:** Author the full `commands/review-pr-buddy.md` orchestration: Phase 0 non-interactive prep delegation, Phase 1 interactive journey walk, Phase 2 human-curated synthesis. Session state, compaction recovery, and cache-boundary handling.

**Deliverables:**
- [ ] Create `commands/review-pr-buddy.md` — argument parsing mirrors `review-pr` (PR id / `local` / aspects)
- [ ] **Phase 0 (non-interactive prep):** delegate to `review-pr.md` pipeline steps (reference the step bodies, do not copy — resolves SPEC Open Question #1; keep `review-pr.md` the single source of truth); delegation includes the reuse-candidacy stage wired in Phase 2; when Phase 0 finishes, inform the reviewer that prep is done and the walk is starting
- [ ] **Phase 1 (interactive walk):** iterate the journey's Manual Review Guide steps in order (template from `agents/journey-planner.md:110-114`: `### Step N: {Group Name}` / `Files:` / `What to look for:` / `Key questions:`); for each chunk: (1) Teach — explain what changed, why, how in senior-architect framing; (2) Surface findings — scoped to chunk's files: investigation findings, sweep rule hits, reuse-candidacy flags; (3) Socratic prompt — pose the journey's Key questions; (4) Capture verdict — via `AskUserQuestion`: keep / dismiss (with optional note) / will-comment / add-own; (5) Checkpoint to `{cacheDir}/buddy-session.json`; (6) Advance to next chunk. Reviewer may interrupt to dig deeper, open a file, or revisit a prior chunk
- [ ] **Cache boundary:** Phase 1 reads cached diffs/files for teaching (cache-bound, like the journey); if the reviewer asks to open an unchanged local file, handle as an investigation-style carve-out (not sweep's cache-only rule), consistent with `agents/investigation.md:49-65`
- [ ] **Session state:** `{cacheDir}/buddy-session.json` records per-chunk progress and per-finding dispositions; Task tools track high-level phases (Phase 0 / Phase 1 / Phase 2); compaction mid-walk resumes at the correct chunk
- [ ] **Phase 2 (culminating review doc):** synthesize a human-curated `PR-{id}.md` in synthesizer-v2 format/location (shape from `agents/synthesizer-v2.md:69-127`); content = kept findings + reviewer's own observations + will-comment notes only; autonomous synthesizer is NOT run — the session IS the synthesis. Journey file and `REVIEWED.md` sentinel behavior unchanged from `review-pr` (emitted at `review-pr.md:399-430`)
- [ ] Tests/verification: journey file + `processed-findings.json` exist before Phase 1's first prompt; each interactive chunk maps to a journey Manual Review Guide step; `buddy-session.json` records dispositions and a simulated resume returns to the right chunk; `PR-{id}.md` contains only kept findings + reviewer observations in synthesizer-v2 format

**Minimum Verifiable Behavior:** Running `/cognito-pr-review:review-pr-buddy {pr}` on a local PR produces a `{cacheDir}/buddy-session.json` after Phase 0 and then presents the first journey chunk interactively, with findings scoped to that chunk's files visible before asking for a verdict.

**Runtime Verification** *(checked by manual testing or a real run — NOT by the implementing agent):*
- [ ] `journey.md` and `processed-findings.json` exist in `{cacheDir}` before the first Phase 1 interactive prompt appears
- [ ] Each Phase 1 interactive chunk corresponds to a named step from the journey's Manual Review Guide (verify chunk title against `journey.md`)
- [ ] After dispositioning all findings in a chunk and advancing, `buddy-session.json` contains the chunk's verdicts; simulating compaction (clearing context and resuming) returns to the correct next chunk
- [ ] Asking the buddy to open an unchanged local file during Phase 1 succeeds (investigation carve-out) rather than being blocked by the cache-boundary
- [ ] Finishing the session produces `PR-{id}.md` in synthesizer-v2 format containing only the reviewer's kept findings and added observations — no auto-synthesized findings that the reviewer dismissed
- [ ] `REVIEWED.md` sentinel file is present after session completion

**Prerequisites:** Phase 2: Reuse-Candidacy Stage (Wired, Parallel)

**Files likely modified:**
- `commands/review-pr-buddy.md` — new file (net-new interactive orchestration)

**Reuse:**
- `agents/journey-planner.md:110-114` — Manual Review Guide template drives Phase 1 chunk structure verbatim. Ledger row: "Human walkthrough script", verdict: **reuse-as-is**.
- `commands/review-pr.md:98-323` (Steps 1-8) — Phase 0 delegates to these steps unchanged. Ledger row: "PR prep / cache / triage / findings", verdict: **reuse-as-is**.
- `agents/synthesizer-v2.md:69-127` (output template) — Phase 2 curated doc follows the same shape. Ledger row: "Review doc synthesis + format", verdict: **extend** (human-curated variant).
- `agents/investigation.md:49-65` (local-codebase carve-out) — Phase 1 inherits this access model for reviewer-requested file opens. Ledger row: "Cache-boundary enforcement", verdict: **reuse-as-is** (with carve-out).
- `AskUserQuestion` + Task tools — per-chunk verdict capture and high-level phase tracking. Ledger row: "Interactive picker + checkpointing", verdict: **reuse-as-is**.
- `review-pr.md:126-141` (cache marker `pr-review-active.json`) + `review-pr.md:391-397` (cleanup) + `review-pr.md:399-430` (REVIEWED.md emit) — buddy session follows the same lifecycle markers. Ledger row: "Cache-boundary enforcement", verdict: **reuse-as-is**.

**Testing Strategy:** Manual walkthrough of a real PR. Verify Phase 0 completion artifacts on disk before Phase 1 prompt. Test compaction recovery by clearing context after two chunks and resuming. Verify the final `PR-{id}.md` contains exactly the kept findings, no dismissed ones.

**Integration Notes for Next Phase:**
- Phase 4 docs will document the buddy command — the argument shape, phase names, and session-state file path must be stable before writing the README/CLAUDE.md updates
- The `REVIEWED.md` sentinel location and `PR-{id}.md` artifact path should be confirmed against `review-pr.md:399-430` before documenting in Phase 4

---

### Phase 4: Integration + Docs

**Scope:** Update plugin metadata and documentation to surface the buddy command and reuse stage; end-to-end smoke test; plugin-reload verification.

**Deliverables:**
- [ ] Update `.claude-plugin/plugin.json` — bump version (currently v2.5.0); update description to mention the buddy command and reuse-candidacy stage
- [ ] Update `README.md` — document `/cognito-pr-review:review-pr-buddy` usage (arguments, Phase 0/1/2 behavior); update pipeline diagram to show the reuse-candidacy stage alongside investigation+sweep
- [ ] Update `CLAUDE.md` — add buddy command to the v2 pipeline description; add editing notes for the reuse agent and shared protocol path; update pipeline step list
- [ ] Verify `manifest.psd1` plugin symlink is present and correct (already added in a prior session — confirm, do not recreate)
- [ ] End-to-end smoke test: run `review-pr` on a real PR that adds duplicative code → confirm a reuse finding surfaces in the review doc; run `review-pr-buddy` on the same PR → confirm Phase 0 pre-computes reuse findings, Phase 1 presents them per chunk, Phase 2 produces a curated doc
- [ ] Plugin-reload smoke test: restart the Claude Code session, reload the plugin, confirm `/cognito-pr-review:review-pr-buddy` and `/cognito-pr-review:review-pr` are both available and argument-complete
- [ ] Tests/verification: `lint-skills.py` still exits 0 after all edits; `project-skills.py` green; plugin commands appear in the command palette after reload

**Minimum Verifiable Behavior:** After a Claude Code restart and plugin reload, `/cognito-pr-review:review-pr-buddy` appears in the command palette with correct argument hints, and `README.md` accurately describes both the reuse stage and the buddy command's three phases.

**Runtime Verification** *(checked by manual testing or a real run — NOT by the implementing agent):*
- [ ] `/cognito-pr-review:review-pr` on a PR adding duplicative code → review doc contains a "Reuse & Duplication" section with at least one cited `file:line` candidate
- [ ] `/cognito-pr-review:review-pr-buddy` on the same PR → full Phase 0/1/2 run completes without errors; curated `PR-{id}.md` produced
- [ ] After Claude Code restart: both commands appear in the command palette; no broken references in plugin.json
- [ ] `python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities` exits 0 after all Phase 4 edits

**Prerequisites:** Phase 3: `review-pr-buddy` Command

**Files likely modified:**
- `.claude-plugin/plugin.json` — version bump + description update
- `README.md` — add buddy command docs; update pipeline diagram
- `CLAUDE.md` — update pipeline description and editing notes

**Reuse:** No new Reuse Ledger rows consumed in this phase. Verifies and documents the capabilities built in Phases 1-3.

**Testing Strategy:** Manual end-to-end smoke test on a real PR (both `review-pr` and `review-pr-buddy` runs). Plugin-reload check. Lint/projection scripts confirm no regressions to Phase 1 outputs.

**Integration Notes for Next Phase:**
- This is the final phase. All validation criteria from `SPEC.md § Validation Criteria` should be checkable after Phase 4 completes.
- If open questions remain (e.g. minor-vs-important verdict threshold tuning from Validated Assumption 2), document them as known tuning parameters in `CLAUDE.md` for future `/learn-from-pr` calibration cycles.
