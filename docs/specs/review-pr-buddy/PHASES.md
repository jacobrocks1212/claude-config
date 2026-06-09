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
- [x] **(2c) Wire the parallel stage into `commands/review-pr.md`** — insert after Step 4 (planner-validates-triage, lines 40-43), dispatched in parallel with Step 5 (investigation+sweep, lines 46-49); fan out one reuse agent per net-new cluster (cap ~6 clusters, estimated — verify during Phase 2); keep `review-pr.md` the single source of pipeline truth
- [x] **(2d) Extend `scripts/aggregate-findings.ts`** — recognize `reuse-*.json` at the file-discovery line (~line 123, alongside `f.startsWith("investigation-")` and hardcoded `sweep.json` at line 182); add `reuse` to the recognized source set. Intermediate runtime checkpoint: confirm `reuse-*.json` outputs appear in aggregated `findings.json`
- [x] **(2e) Extend `scripts/post-process.ts`** — route reuse findings through the investigation lane (fixed `effective_weight: 1.0`, never weight-filtered; parallel to the existing investigation path at line 291); add a verdict→severity map: `refactor`/`reuse` → important, `extend`/`wrap` → minor/nit, `acceptable-new` → dropped (informational); `CATEGORY_MAP` already bridges `code-consistency` → `consistency` multiplier (line 129) — no change needed there (Validated Assumption 2)
- [x] **(2f) Add reuse rules to `knowledge/rules/code-consistency.yaml` and weights to `knowledge/weights.yaml`** — append rules using real per-rule schema (`id`/`severity`/`description`/`trigger_patterns`/`anti_pattern`/`correct_pattern`); add `rule_weights` entries to `weights.yaml`; rules must instruct the cache-only sweep agent to FLAG heuristic signals ("new `*Service` mirrors an existing one") and ESCALATE to the reuse stage rather than asserting a local-codebase fact (Validated Assumption 3). Run `/rebuild-agents` to re-embed rules into agent prompts
- [x] **(2g) Add "Reuse & Duplication" subsection to `agents/synthesizer-v2.md`** — insert after Rule-Based Findings (~line 104); subsection is omittable when empty (consistent with section-omission rules at lines 140-145); renders reuse findings with verdict, candidate `file:line`/symbol, and escalation path. Intermediate runtime checkpoint: review doc contains the section after a run with reuse findings
- [x] Tests/verification: `review-pr` run on a PR adding duplicative code yields a `source:"reuse"` finding in `processed-findings.json` with `file:line` candidate + verdict; agent-output timestamps confirm reuse agents ran in parallel with investigation/sweep; `acceptable-new` findings carry a negative-search trail; sweep emits an escalation (not a fabricated local-codebase fact) when a reuse heuristic fires

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

**Implementation Notes (2026-06-08, Phase 2 Batch 2 — WU-3 + /rebuild-agents):**
- **/rebuild-agents:** embedded the 4 new reuse rules into `agents/sweep.md` between its `RULES_START/END` markers (under `### Code Consistency Rules`, with weights), each retaining FLAG+ESCALATE wording ("Sweep cannot verify local-codebase facts"). `cognito-consistency-checker.md` deliberately left unchanged — it IS the reuse stage, so embedding "escalate to the reuse stage" into it would be circular. Only `sweep.md` was modified by the rebuild (mtime-confirmed).
- **WU-3 (review-pr.md):** added `### Step 5b: Reuse-Candidacy Stage (parallel with Step 5)` — clusters net-new/substantive files from `manifest.baselines[]` (cap 6, skip-if-empty), fans out one `cognito-consistency-checker` per cluster concurrently with investigation/sweep, with explicit investigation-level access (not sweep cache-only), writing `{cacheDir}/agent-output/reuse-{cluster-slug}.json`. Updated the line-15 pipeline one-liner + the Architecture ASCII diagram + Component Descriptions. All critical steps preserved (1.5/4/5/6/7/8/12.6). Step 7 aggregate + Step 8 post-process already route reuse-*.json (WU-4/WU-5).
- **Full wired chain verified structurally + mechanically:** prep `baselines[]` → Step 5b per-cluster dispatch → `reuse-{cluster}.json` → aggregate (`source:"reuse"`) → post-process (investigation lane + verdict→severity) → synthesizer "Reuse & Duplication". The script half (aggregate→post-process) is proven by the integrated fixture; the agent-dispatch half is wired in markdown.
- **Runtime verification DEFERRED (manual/live):** a live `review-pr` run on a real PR adding duplicative code (to observe a real `source:"reuse"` finding end-to-end, parallel agent-output timestamps, a real `negative_search_trail`, and a real sweep escalation) requires GitHub + the full Opus pipeline and is the runtime verification not performed by the implementing agent (see the Runtime Verification checklist below — left unchecked pending a live run). All mechanical equivalents are green.

---

### Phase 3: `review-pr-buddy` Command

**Scope:** Author the full `commands/review-pr-buddy.md` orchestration: Phase 0 non-interactive prep delegation, Phase 1 interactive journey walk, Phase 2 human-curated synthesis. Session state, compaction recovery, and cache-boundary handling.

**Deliverables:**
- [x] Create `commands/review-pr-buddy.md` — argument parsing mirrors `review-pr` (PR id / `local` / aspects)
- [x] **Phase 0 (non-interactive prep):** delegate to `review-pr.md` pipeline steps (reference the step bodies, do not copy — resolves SPEC Open Question #1; keep `review-pr.md` the single source of truth); delegation includes the reuse-candidacy stage wired in Phase 2; when Phase 0 finishes, inform the reviewer that prep is done and the walk is starting
- [x] **Phase 1 (interactive walk):** iterate the journey's Manual Review Guide steps in order (template from `agents/journey-planner.md:110-114`: `### Step N: {Group Name}` / `Files:` / `What to look for:` / `Key questions:`); for each chunk: (1) Teach — explain what changed, why, how in senior-architect framing; (2) Surface findings — scoped to chunk's files: investigation findings, sweep rule hits, reuse-candidacy flags; (3) Socratic prompt — pose the journey's Key questions; (4) Capture verdict — via `AskUserQuestion`: keep / dismiss (with optional note) / will-comment / add-own; (5) Checkpoint to `{cacheDir}/buddy-session.json`; (6) Advance to next chunk. Reviewer may interrupt to dig deeper, open a file, or revisit a prior chunk
- [x] **Cache boundary:** Phase 1 reads cached diffs/files for teaching (cache-bound, like the journey); if the reviewer asks to open an unchanged local file, handle as an investigation-style carve-out (not sweep's cache-only rule), consistent with `agents/investigation.md:49-65`
- [x] **Session state:** `{cacheDir}/buddy-session.json` records per-chunk progress and per-finding dispositions; Task tools track high-level phases (Phase 0 / Phase 1 / Phase 2); compaction mid-walk resumes at the correct chunk
- [x] **Phase 2 (culminating review doc):** synthesize a human-curated `PR-{id}.md` in synthesizer-v2 format/location (shape from `agents/synthesizer-v2.md:69-127`); content = kept findings + reviewer's own observations + will-comment notes only; autonomous synthesizer is NOT run — the session IS the synthesis. Journey file and `REVIEWED.md` sentinel behavior unchanged from `review-pr` (emitted at `review-pr.md:399-430`)
- [x] Tests/verification: journey file + `processed-findings.json` exist before Phase 1's first prompt; each interactive chunk maps to a journey Manual Review Guide step; `buddy-session.json` records dispositions and a simulated resume returns to the right chunk; `PR-{id}.md` contains only kept findings + reviewer observations in synthesizer-v2 format

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

**Implementation Notes (2026-06-08, Phase 3 — WU-1):**
- Authored `commands/review-pr-buddy.md` (290 lines, net-new). Frontmatter mirrors `review-pr` (`description`/`argument-hint`/`allowed-tools` incl. `Agent`+`AskUserQuestion`); discoverable alongside sibling `commands/*.md`.
- **Phase 0 = delegation (resolves SPEC Open Question #1):** references `review-pr.md` Steps 1–8 explicitly as "the single source of truth for those step bodies" — no duplication. Reuse findings from Step 5b land in `processed-findings.json`.
- **Phase 1 = interactive walk:** iterates the journey's `## Manual Review Guide` `### Step N` chunks; per-chunk 6-step loop (Teach / Surface chunk-scoped investigation+sweep+`source:"reuse"` findings / Socratic / Capture via 4-option `AskUserQuestion` keep·dismiss·will-comment·add-own / Checkpoint / Advance); interrupt handling (dig-in, open-file, revisit). Unchanged-file opens use the investigation carve-out (local codebase on `main`), NOT sweep's cache-only rule.
- **`buddy-session.json` schema (stable):** `{ pr_id, cache_dir, phase, current_chunk_index, total_chunks, chunks:[{index,group,status,dispositions:[{finding_ref,verdict,note}]}], added_observations:[{file,line,note}] }`. **Compaction recovery:** on start, read the file, find the first chunk whose status ≠ `done`, resume there (Task tools track Phase 0/1/2).
- **Phase 2 = curated synthesis (NOT the autonomous synthesizer):** writes `PR-{id}.md` in synthesizer-v2 format (incl. the "Reuse & Duplication" section name from Part 2) at review-pr.md Step 10's location; content = kept findings + add-own observations + will-comment notes only; dismissed excluded. Mirrors `REVIEWED.md` Step 12.6 sentinel. **Final artifact path:** `.claude.local/reviews/PR-{id}.md` (+ cog-docs location when applicable).
- **Live verification DEFERRED:** the Phase 3 Runtime Verification checklist (journey+processed-findings on disk before first prompt; chunk↔guide mapping; resume-to-right-chunk; curated doc contents) requires a live `review-pr-buddy` run and is the Completion smoke test (runtime, not performed by the implementing agent). Structure verified by reading.

---

### Phase 4: Integration + Docs

**Scope:** Update plugin metadata and documentation to surface the buddy command and reuse stage; end-to-end smoke test; plugin-reload verification.

**Deliverables:**
- [x] Update `.claude-plugin/plugin.json` — bump version (currently v2.5.0); update description to mention the buddy command and reuse-candidacy stage
- [x] Update `README.md` — document `/cognito-pr-review:review-pr-buddy` usage (arguments, Phase 0/1/2 behavior); update pipeline diagram to show the reuse-candidacy stage alongside investigation+sweep
- [x] Update `CLAUDE.md` — add buddy command to the v2 pipeline description; add editing notes for the reuse agent and shared protocol path; update pipeline step list
- [x] Verify `manifest.psd1` plugin symlink is present and correct (already added in a prior session — confirm, do not recreate)
- [ ] End-to-end smoke test: run `review-pr` on a real PR that adds duplicative code → confirm a reuse finding surfaces in the review doc; run `review-pr-buddy` on the same PR → confirm Phase 0 pre-computes reuse findings, Phase 1 presents them per chunk, Phase 2 produces a curated doc
- [ ] Plugin-reload smoke test: restart the Claude Code session, reload the plugin, confirm `/cognito-pr-review:review-pr-buddy` and `/cognito-pr-review:review-pr` are both available and argument-complete
- [x] Tests/verification: `lint-skills.py` still exits 0 after all edits; `project-skills.py` green; plugin commands appear in the command palette after reload

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

**Implementation Notes (2026-06-08, Phase 4 — WU-2/3/4):**
- `plugin.json`: version 2.5.0 → **2.6.0** (minor); description now mentions the reuse-candidacy stage + interactive `review-pr-buddy`. Valid JSON.
- `README.md`: added a "Buddy Review" usage section (args + Phase 0/1/2), updated the top-line pipeline description and the Architecture diagram to show `reuse-candidacy` parallel with investigation+sweep, and listed `review-pr-buddy.md` in the file structure.
- `CLAUDE.md` (plugin): added the `review-pr-buddy` Key Commands row + an Architecture paragraph (interactive front-end over the same pipeline; Phase 0 delegates to review-pr.md; buddy-session.json; curated PR-{id}.md) + a "When editing commands" note (buddy delegates, don't duplicate). The reuse-stage docs from the Phase 2 post-step are intact. (Most of the original WU-4 reuse-doc scope was already satisfied in Phase 2's post-phase CLAUDE.md update — Phase 4 added the buddy-command docs.)
- **Manifest:** `setup.ps1 check` reports `OK User | cognito-pr-review` — the plugin symlink is present and correct (verified, not recreated).
- **Gates:** `lint-skills.py` source exit 0; `project-skills.py` green; `lint-skills.py --check-projected --check-capabilities` exit 0; `plugin.json` valid JSON.
- **Runtime smoke tests DEFERRED (manual):** the end-to-end live `review-pr` + `review-pr-buddy` run on a real duplicative-code PR, and the plugin-reload-after-restart command-palette check, require a live Claude Code session restart + a real PR + the full Opus pipeline. These are the SPEC/PHASES Runtime Verification items (not performed by the implementing agent) and remain unchecked pending a manual run. All mechanical/structural equivalents are green.

---

### Phase 5: Intra-File Reuse & Consistency Stage (Wired, Parallel)

**Scope:** Add the *intra-file* complement to Phase 2's cross-file reuse stage. Phase 2 seeds reuse clusters from `manifest.baselines[]`, which compares each changed file against *other* similar files and explicitly excludes the file itself (`scripts/prep-pr.ts:1273` `if (candidate === file.path) continue`). That leaves a gap: when a substantial change lands in a file, nothing asks whether the new code should have **reused existing code already in that same file**, or whether it is **consistent with the surrounding conventions** in the file (naming, structure, error handling, established patterns). This phase wires a dedicated intra-file agent into the same parallel Step 5b stage so both `review-pr` and `review-pr-buddy` consume it for free. The host file's `main` version is the implicit baseline; the agent reads the cached PR-branch version + the local `main` version + the cached diff (investigation-level access, NOT sweep's cache-only rule). Eligibility: **all substantively-modified substantive files (services / types / components / helpers), across all triage tiers** — no size gate, no cross-file baseline required.

**Deliverables:**
- [x] **(5a) Extract shared agent scaffold into a `_components` file** — create `user/skills/_components/pr-review-reuse-agent-scaffold.md` holding the content currently duplicated (or about to be duplicated) across reuse-class agents: the investigation-equivalent access model (cache + local-`main` + tree-sitter; explicitly NOT sweep's cache-only boundary), the tree-sitter tool-usage guidance, the shared finding output schema, and the verdict→severity + negative-search-trail reminders. Codebase-neutral where possible; PR-review-specific where required. Refactor `agents/cognito-consistency-checker.md` to `Read` this scaffold at runtime (behavior-preserving — its emitted JSON schema and `similarityScore>=50` baseline consumption must be unchanged; Phase 2's aggregate→post-process fixture + a re-read are the proof). The new intra-file agent (5b) `Read`s the same scaffold. This realizes "dedicated agent, reuse content via components" — same shared-`_components`-read pattern as Phase 1's `reuse-discovery-protocol.md`.
- [ ] **(5b) Author the dedicated intra-file agent `agents/cognito-intra-file-consistency.md`** — Opus, investigation-equivalent access. At runtime it `Read`s both `~/.claude/skills/_components/reuse-discovery-protocol.md` (R1–R4 mechanics) and `~/.claude/skills/_components/pr-review-reuse-agent-scaffold.md` (5a). Per assigned file it answers two questions: **(i) intra-file duplication** — does the changed/added code reimplement a function, query, branch, or pattern that already exists *elsewhere in this same file* on `main` (verdict `reuse`/`refactor` against an in-file `file:line`/symbol candidate; use `get_file_structure`/`find_symbol_usages` to locate the existing in-file member; `get_callers` for `refactor` blast radius); and **(ii) surrounding-code consistency** — is the change consistent with the file's established conventions (naming, structure, error handling, logging, the shape of sibling functions). Emits findings in the shared schema with `source:"intrafile"`, writing `{cacheDir}/agent-output/intrafile-{slug}.json`. `acceptable`/`consistent` outcomes are dropped-with-trail (no finding surfaced) — same negative-trail discipline as `acceptable-new`.
- [ ] **(5c) Wire intra-file clustering + dispatch into `commands/review-pr.md` Step 5b** (`review-pr.md:283`) — add a second clustering pass alongside the existing baseline-seeded reuse clustering: select all substantively-modified substantive files from the manifest (exclude pure test files, config, generated types; all tiers), group into ≤6 clusters, and fan out one `cognito-intra-file-consistency` agent per cluster, dispatched **in parallel with Step 5** (no serial latency), with the same investigation-level access note. Prep (`prep-pr.ts`) is intentionally **not** modified — Step 5b derives eligibility from manifest file status + path heuristics, and the agent reads `main` directly via its local-codebase access.
- [x] **(5d) Extend `scripts/aggregate-findings.ts`** — recognize `intrafile-*.json` at the agent-output discovery line (`aggregate-findings.ts:189`, alongside the `reuse-*` filter), into the same Opus-lane group set.
- [x] **(5e) Extend `scripts/post-process.ts`** — add `"intrafile"` to the `source` union (`post-process.ts:125`); route intra-file findings through the **investigation lane** (fixed `effective_weight: 1.0`, never weight-filtered — identical to the reuse lane), and treat them as Opus-lane in dedup/rank. Severity map: intra-file duplication (`reuse`/`refactor`) → **important**; surrounding-code `inconsistent` → **minor/nit**; `consistent`/`acceptable` → **dropped**. (The duplication-vs-consistency severity boundary is a tunable for future `/learn-from-pr` calibration, same as Phase 2's verdict→severity boundary.)
- [ ] **(5f) Render intra-file findings in `agents/synthesizer-v2.md`** — add an omittable `## Intra-File Consistency` section (distinct from `## Reuse & Duplication`, which stays cross-file), placed adjacent to it; lists intra-file duplication + consistency findings with the in-file `file:line`/symbol candidate and suggested action. Omit when empty, consistent with the section-omission rules.
- [ ] **(5g) Surface intra-file findings in `commands/review-pr-buddy.md` Phase 1** — add an "Intra-file reuse & consistency" bullet to the per-chunk **Surface Findings** enumeration (`review-pr-buddy.md:82-88`, alongside the `source:"investigation"` / `"sweep"` / `"reuse"` bullets), keyed on `source:"intrafile"` and scoped to the chunk's files. Add the `## Intra-File Consistency` section name to the Phase 2 curated-doc rendering note (`review-pr-buddy.md:194`) so kept intra-file findings appear in `PR-{id}.md`.
- [ ] **(5h) Add intra-file sweep rules to `knowledge/rules/code-consistency.yaml` + weights to `knowledge/weights.yaml`** — sweep is cache-only but *has the full cached file*, so it can honestly FLAG in-file heuristic signals (e.g. "this added block closely mirrors another block already in this file") and ESCALATE to the intra-file stage — it must not assert a confirmed duplication. Append 1–2 rules using the real per-rule schema; add matching `rule_weights`. Run `/cognito-pr-review:rebuild-agents` to re-embed into `agents/sweep.md`.
- [ ] Tests/verification: `npx tsc --noEmit` clean across `scripts/`; an aggregate→post-process fixture seeded with an `intrafile-*.json` (one `refactor` duplication finding, one `inconsistent` finding, one dropped `consistent`) yields a `source:"intrafile"` entry routed through the investigation lane (effective_weight 1.0), duplication→important, inconsistent→minor, consistent absent; refactored `cognito-consistency-checker.md` re-read confirms unchanged emitted schema; YAML parses; `/rebuild-agents` updates only `sweep.md`.

**Minimum Verifiable Behavior:** Running an aggregate→post-process fixture with an `{cacheDir}/agent-output/intrafile-{slug}.json` containing an intra-file `refactor` finding (in-file `file:line` candidate) produces a `source:"intrafile"` entry in `processed-findings.json` with `effective_weight: 1.0` and `severity: "important"`, and a `consistent` outcome in the same fixture produces no surfaced finding.

**Runtime Verification** *(checked by manual testing or a real run — NOT by the implementing agent):*
- [ ] `review-pr` on a PR that adds a block to a large file duplicating an existing in-file helper → `{cacheDir}/agent-output/intrafile-*.json` contains a `refactor`/`reuse` finding citing the existing in-file `file:line`, and the review doc's `## Intra-File Consistency` section lists it
- [ ] Intra-file agents are dispatched in parallel with investigation/sweep/reuse (confirm via Step 5b ordering + agent-output directory timestamps)
- [ ] A `consistent`/`acceptable` intra-file outcome carries a negative-search trail in the agent JSON and surfaces no finding
- [ ] `review-pr-buddy` on the same PR surfaces the intra-file finding in the relevant chunk's Surface-Findings step, and a kept intra-file finding appears in the curated `PR-{id}.md` under `## Intra-File Consistency`
- [ ] Sweep output for an intra-file heuristic rule hit contains an escalation flag/note rather than an asserted confirmed-duplication claim
- [ ] `python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities` exits 0 after the new `_components` file is added

**Prerequisites:**
- Phase 1: Shared Reuse-Discovery Protocol (the new agent reads `reuse-discovery-protocol.md`; the new scaffold sits beside it in `_components/`)
- Phase 2: Reuse-Candidacy Stage (this phase extends the *same* Step 5b stage, the `reuse-*` aggregate discovery, the investigation-lane routing in post-process, and the `cognito-consistency-checker` agent that 5a refactors)

**Files likely modified:**
- `user/skills/_components/pr-review-reuse-agent-scaffold.md` — new file (net-new shared scaffold)
- `agents/cognito-intra-file-consistency.md` — new file (net-new dedicated intra-file agent)
- `agents/cognito-consistency-checker.md` — refactor to `Read` the shared scaffold (behavior-preserving; emitted schema unchanged)
- `commands/review-pr.md` — extend Step 5b (line 283) with the intra-file clustering pass + parallel dispatch
- `scripts/aggregate-findings.ts` — recognize `intrafile-*.json` (line 189 area)
- `scripts/post-process.ts` — add `"intrafile"` source (line 125), investigation-lane routing + duplication/consistency→severity map
- `agents/synthesizer-v2.md` — add omittable `## Intra-File Consistency` section
- `commands/review-pr-buddy.md` — add intra-file bullet to Surface Findings (lines 82-88) + section name to curated-doc note (line 194)
- `knowledge/rules/code-consistency.yaml` — append intra-file FLAG+ESCALATE rule(s)
- `knowledge/weights.yaml` — add `rule_weights` for the new rule ids
- `agents/sweep.md` — re-embedded by `/rebuild-agents` (do not hand-edit between markers)

**Reuse:**
- `agents/cognito-consistency-checker.md` access model + output schema (`cognito-consistency-checker.md:41-90`) — extracted into the shared scaffold (5a) and consumed by both agents. Ledger row: "Reuse-class agent scaffold", verdict: **refactor** (extract-to-component).
- `user/skills/_components/reuse-discovery-protocol.md` (Phase 1) — read at runtime by the new agent unchanged. Ledger row: "Reuse-discovery protocol", verdict: **reuse-as-is**.
- `agents/investigation.md` access model (`investigation.md:49-65`, local-`main` carve-out; `68-87` tree-sitter) — inherited by the new agent via the scaffold. Ledger row: "Cache-boundary enforcement", verdict: **reuse-as-is**.
- `scripts/aggregate-findings.ts` reuse discovery (`aggregate-findings.ts:189`) — extended to cover `intrafile-*`. Ledger row: "Findings aggregation", verdict: **extend**.
- `scripts/post-process.ts` investigation lane + verdict→severity (Phase 2, `post-process.ts:125`, fixed weight 1.0) — reused as the routing path for intra-file findings. Ledger row: "Findings post-processing", verdict: **extend**.
- `commands/review-pr.md` Step 5b parallel-dispatch + clustering (`review-pr.md:283-325`) — reused as the fan-out shape for the intra-file clustering pass. Ledger row: "Parallel discovery fan-out", verdict: **reuse-as-is** (pattern).
- `agents/synthesizer-v2.md` `## Reuse & Duplication` omittable-section pattern — mirrored for `## Intra-File Consistency`. Ledger row: "Review doc synthesis", verdict: **extend**.
- `knowledge/rules/code-consistency.yaml` + `weights.yaml` reuse-rule FLAG+ESCALATE pattern (Phase 2 `reuse-*` rules) — mirrored for intra-file rules. Ledger row: "Rule corpus + weights", verdict: **extend**.

**Testing Strategy:** No test harness exists in `scripts/` (per Phase 2 Implementation Notes), so the script wiring (5d/5e) is verified by `npx tsc --noEmit` + a runnable aggregate→post-process fixture seeded with a representative `intrafile-*.json` — the same approach Phase 2 used and proved. The 5a refactor is verified behavior-preserving by re-reading `cognito-consistency-checker.md`'s emitted-schema section and confirming it is unchanged, plus the Phase 2 fixture still passing. Agent prompts (5a/5b) and markdown wiring (5c/5f/5g) are verified structurally by reading. YAML parses; `/rebuild-agents` touches only `sweep.md` (mtime-confirmed). Live end-to-end behavior (a real PR exercising the Opus intra-file agent) is the deferred Runtime Verification, consistent with Phases 2–4.

**Runtime Assumption Validation:** Gate **skipped** — every load-bearing assumption is code-provable. The wiring mirrors the already-proven Phase 2 reuse lane (aggregate discovery glob, investigation-lane routing, source-enum extension, omittable synthesizer section), all readable from source and covered by the fixture. The only runtime-coupled assumption — that the Opus intra-file agent produces good findings on a real PR — is not load-bearing for the wiring and is deferred as a Runtime Verification item (same convention as Phases 2–4).

**Integration Notes for Next Phase:** This is a terminal extension phase; no further phase depends on it. If a docs pass follows, `README.md` / plugin `CLAUDE.md` should gain the `## Intra-File Consistency` finding class and the `cognito-intra-file-consistency` agent in the agent list + pipeline diagram (the Phase 4 docs cover only the cross-file reuse stage).

**Context from prior phases:**
- **Investigation lane is the proven routing path** (PHASES Validated Assumption 2; Phase 2 WU-5): Opus-agent findings get fixed `effective_weight: 1.0` and are never weight-filtered. Intra-file findings are Opus-produced → same lane. Do NOT route them through the EMA/`MIN_EFFECTIVE_WEIGHT` sweep path.
- **No `scripts/` test harness** (Phase 2 Batch 1 note): use direct implementation + a runnable fixture, NOT fabricated unit-test infra.
- **`source` enum extension is the established seam** (Phase 2 added `"reuse"` at `post-process.ts:125`); `"intrafile"` follows the identical pattern through aggregate → post-process → synthesizer → buddy.
- **Grow/extend-in-place precedent** (Phase 2 Validated Assumption 4): the `cognito-consistency-checker` has live refs at `rebuild-agents.md:47` and `learn-from-pr.md:26` — the 5a refactor is behavior-preserving and keeps those refs valid; do not delete or rename the checker.
- **Verdict→severity is a documented tunable** for `/learn-from-pr` (Phase 2 WU-5); the new duplication-vs-consistency severity boundary should be added to that same tunable surface, not hardcoded as immutable.
- **CRLF + tabs** per `.editorconfig` for the `.ts`/`.md` files (YAML uses spaces); subagents have written LF and git normalizes — not blocking, but author CRLF.

**Implementation Notes (2026-06-09, Phase 5 Batch 1 — WU-1/4/5):**
- **WU-1 (5a):** Extracted the shared scaffold to `user/skills/_components/pr-review-reuse-agent-scaffold.md` (126 lines, net-new). Moved verbatim out of `cognito-consistency-checker.md`: Cache-Based File Access (incl. the `similarityScore>=50` baseline strategy), Codebase Exploration, Structural Codebase Queries (tree-sitter), Verdict Taxonomy, and the Output Schema JSON block + schema rules (byte-for-byte). The checker (291→179 lines) now `Read`s BOTH `reuse-discovery-protocol.md` (line 28) and `pr-review-reuse-agent-scaffold.md` (line 45) at runtime; its `## Output` pointer still names the concrete `reuse-{cluster}.json` so behavior is preserved. The scaffold's only deviation from the inlined original is generalizing the output-filename line to `{output-prefix}-{cluster}.json` (the reuse checker uses `reuse`; the WU-2 intra-file agent will use `intrafile`). Header comment names both consumers. Behavior-preserving: schema field names + baseline-consumption unchanged.
- **WU-4 (5d):** `aggregate-findings.ts` discovers `intrafile-*.json` exactly like `reuse-*.json` — `intrafile: InvestigationGroup[]` on `CombinedFindings`, an intrafile discovery/read loop, the nothing-to-aggregate guard now includes `intrafileGroups.length === 0`, and `intrafile: intrafileGroups` in the combined output. (Cosmetic: the guard's stderr message was updated to mention intrafile.)
- **WU-5 (5e):** `post-process.ts` — `"intrafile"` added to the `source` union (line 130) + optional `intrafile?` on its `CombinedFindings` interface; a new intrafile ingest loop in `step1_computeWeights` (mirrors the reuse loop) drops `acceptable-new`/`acceptable`/`consistent`, maps `refactor`/`reuse`→important, `inconsistent`→nit, `extend`/`wrap`→nit, and pushes `source:"intrafile"`, `effective_weight:1.0`. Intrafile added to ALL four Opus-lane sites: `matchesPreviousFinding` (298), `step3_deduplicate` incomingIsOpus/existingIsOpus (428-429), `step4_rank` tierA/tierB (451-452). The reuse lane is unchanged.
- **`intrafile` contract as built:** `source:"intrafile"` rides the investigation lane (fixed `effective_weight:1.0`, never weight-filtered, top tier in dedup/rank). Output files `{cacheDir}/agent-output/intrafile-{slug}.json`, same finding schema as reuse. Verdict→severity: duplication (`refactor`/`reuse`)→important; `inconsistent`→nit; `consistent`/`acceptable`/`acceptable-new`→dropped (via `continue`, NOT counted in `dropped_count`).
- **Integrated fixture (aggregate→post-process, ephemeral temp dir):** seeded `intrafile-test.json` with `refactor`(line10)/`inconsistent`(line20)/`consistent`(line30). Result (independently re-verified by orchestrator): refactor→`important` w=1.0, inconsistent→`nit` w=1.0, consistent ABSENT (dropped), `dropped_count:0` (no sweep findings; verdict-drops are uncounted — matches Phase 2's `acceptable-new` precedent). The plan's "dropped_count reflects only the consistent drop" was reconciled: drops via `continue` are not counted, so absence-from-output is the proof.
- **Gates (all green, orchestrator-reverified):** `npx tsc --noEmit` over `scripts/` clean; integrated fixture PASS; `lint-skills.py` exit 0; `lint-skills.py --check-projected --check-capabilities` exit 0 (only the pre-existing non-fatal cog-docs missing-capabilities warning); `project-skills.py` green (7 repos).
- **Review verdict:** PASS-WITH-FIXES (one cosmetic stderr-message fix applied inline by the orchestrator; ground-truth verified `yes` for WU-1/4/5).
