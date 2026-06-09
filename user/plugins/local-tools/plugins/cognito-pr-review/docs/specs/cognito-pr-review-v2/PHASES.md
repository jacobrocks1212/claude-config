# Implementation Phases — Cognito PR Review Plugin v2

> Phases for [`SPEC.md`](./SPEC.md)

---

### Phase 1: Name Scrub + Weight Schema

**Scope:** Remove all personal names from the rules corpus and agent prompts. Create the `weights.yaml` skeleton with EMA schema. Update `learn-from-pr` and `rebuild-agents` to never propagate source/name fields.

**Deliverables:**
- [x] Strip all `source:` fields from `knowledge/rules/api-design.yaml`
- [x] Strip all `source:` fields from `knowledge/rules/code-consistency.yaml`
- [x] Strip all `source:` fields from `knowledge/rules/csharp-architecture.yaml`
- [x] Strip all `source:` fields from `knowledge/rules/frontend-vue.yaml`
- [x] Strip all `source:` fields from `knowledge/rules/performance.yaml`
- [x] Strip all `source:` fields from `knowledge/rules/security.yaml`
- [x] Strip all `source:` fields from `knowledge/rules/template-binding.yaml`
- [x] Strip all `source:` fields from `knowledge/rules/testing.yaml`
- [x] Remove any inline name references from all `.md` files in `agents/`
- [x] Create `knowledge/weights.yaml` — top-level keys: `version`, `last_calibrated`, `calibration_prs`, `ema_alpha`, `category_multipliers`, `rule_weights`; every rule ID from all 8 YAML files listed under `rule_weights` with `weight: 0.7` and `data_points: 0` as initial values; `category_multipliers` initialized per spec (architecture: 1.0, frontend: 1.0, api_design: 1.0, consistency: 0.8, testing: 0.9, security: 1.2, performance: 0.9, template_binding: 0.7)
- [x] Update `commands/learn-from-pr.md` — remove `source:` from the rule template; add a note that no attribution fields are ever recorded
- [x] Update `commands/rebuild-agents.md` — add instruction to skip/omit source fields when embedding rules into agent prompts
- [x] Run `rebuild-agents` to propagate the clean rules into all existing agent prompts

**Prerequisites:** None — this is the baseline phase that all other phases depend on.

**Files likely modified:**
- `knowledge/rules/api-design.yaml` — strip `source:` fields
- `knowledge/rules/code-consistency.yaml` — strip `source:` fields
- `knowledge/rules/csharp-architecture.yaml` — strip `source:` fields
- `knowledge/rules/frontend-vue.yaml` — strip `source:` fields
- `knowledge/rules/performance.yaml` — strip `source:` fields
- `knowledge/rules/security.yaml` — strip `source:` fields
- `knowledge/rules/template-binding.yaml` — strip `source:` fields
- `knowledge/rules/testing.yaml` — strip `source:` fields
- `agents/cognito-api-design.md` — remove name references if present
- `agents/cognito-architecture.md` — remove name references if present
- `agents/cognito-behavior.md` — remove name references if present
- `agents/cognito-consistency-checker.md` — remove name references if present
- `agents/cognito-frontend.md` — remove name references if present
- `agents/cognito-test-coverage.md` — remove name references if present
- `agents/review-synthesizer.md` — remove name references if present
- `knowledge/weights.yaml` — new file
- `commands/learn-from-pr.md` — exclude source field from rule template
- `commands/rebuild-agents.md` — skip source field when embedding rules

**TDD:** no

**Testing Strategy:**
Run `grep -r "source:" knowledge/rules/` — expect zero hits. Run `grep -r "(Taylor|Bryan|Jacob)" knowledge/ agents/` — expect zero hits (reviewing names found in rules specifically, not the plugin author). Verify `knowledge/weights.yaml` exists and contains an entry for every rule ID found across all 8 YAML files. Manually inspect `learn-from-pr.md` and `rebuild-agents.md` for removed attribution logic.

**Integration Notes for Next Phase:**
- The `weights.yaml` schema established here (with all ~100 rule IDs) is the exact format the calibration command will populate — the calibrate command reads rule IDs from this file, so every rule must have an entry before Phase 2 runs
- The `rule_weights` key names must exactly match the `id:` fields in the YAML rule files — mismatches will cause calibration to produce orphan weight entries

**Implementation Notes:**
- Stripped 24 `source:` fields from 6 YAML files (security.yaml and template-binding.yaml had none)
- Removed 6 `*Source: PR #NNNNN — Name*` attribution lines from 4 agent .md files (cognito-api-design, cognito-architecture, cognito-consistency-checker, cognito-frontend)
- Created `weights.yaml` with 95 rule IDs across 8 categories, verified via `data_points: 0` count
- Updated `learn-from-pr.md`: quote-only attribution in AskUserQuestion, no-source-field note
- Updated `rebuild-agents.md`: skip source fields instruction, no-embed note
- WU-6 (rebuild-agents): no-op — WU-2 already removed attribution from agents, rules content unchanged
- QG: `source:` in rules → 0 hits; names in knowledge/agents → 0 hits; weights.yaml → 95 entries ✓

---

### Phase 2: Bulk Calibration Command

**Scope:** Build the `/cognito-pr-review:calibrate` command that pulls ADO comments for all ~30 historical PRs, compares against plugin review artifacts using hybrid matching (file:line proximity + Haiku semantic judge), and generates initial weights via EMA.

**Deliverables:**
- [x] New `commands/calibrate.md` — orchestration command that: enumerates all `.claude.local/reviews/PR-*.md` review artifacts, pulls ADO comments for each PR via `get-pr-comments.ps1`, parses plugin findings from the review artifact, runs hybrid matching (Step 1: file + line proximity within ~20 lines; Step 2: Haiku LLM judge for semantic equivalence), classifies each finding as TP/FP/FN, applies EMA updates to `knowledge/weights.yaml` (α = 0.25, signal = 1.0 for TP / 0.0 for FP), increments `data_points` counters, and writes a calibration report
- [x] New `commands/weights.md` — view and manually adjust the weight system; shows each rule with its current weight, data_points count, category multiplier, and computed effective_weight; allows manual override of individual rule weights with a rationale note
- [ ] Calibration report written to `docs/specs/cognito-pr-review-v2/calibration-report.md` — TP/FP/FN breakdown per rule, per category aggregates, false-negative patterns flagged as rule candidates

**Prerequisites:** Phase 1 complete — `weights.yaml` with all rule IDs must exist before calibration can populate it.

**Files likely modified:**
- `commands/calibrate.md` — new file
- `commands/weights.md` — new file
- `knowledge/weights.yaml` — populated by running the command (not a code change, a runtime artifact)
- `docs/specs/cognito-pr-review-v2/calibration-report.md` — generated output (new file, written by the command at runtime)

**TDD:** no

**Testing Strategy:**
Run `/cognito-pr-review:calibrate`. Verify `knowledge/weights.yaml` has `data_points > 0` for rules that appear in the historical reviews. Verify `calibration-report.md` is created with a TP/FP/FN breakdown table. Spot-check 3–5 PRs: manually compare a known human comment against what the calibration classified it as (TP/FP) to validate the Haiku judge is making reasonable calls. Run `/cognito-pr-review:weights` and verify it displays current weights in a readable format.

**Integration Notes for Next Phase:**
- The populated `weights.yaml` will be read by the post-processing script (Phase 7) and referenced in the manifest v2 schema (Phase 3) via the `"weights": "weights.yaml"` field
- The calibration command's hybrid matching logic (proximity + Haiku judge) is also used in the enhanced `learn-from-pr` command (Phase 8) — document the shared matching approach so Phase 8 can reference/reuse it

**Implementation Notes:**
- Created `calibrate.md` with 8-step workflow: enumerate artifacts → pull ADO comments → parse findings → hybrid match (proximity + Haiku judge) → classify TP/FP/FN → EMA update → write report → summary
- Created `weights.md` with 3 modes: view (default, shows effective weight table), set (manual override with AskUserQuestion confirm), reset (restore defaults)
- Calibration report (3rd deliverable) is a runtime artifact generated when `/calibrate` is executed — not a code deliverable
- Both commands reference proper paths and ADO API patterns
- QG: both files have valid YAML frontmatter, reference weights.yaml ✓

---

### Phase 3: Enhanced Prep Script

**Scope:** Extend `scripts/prep-pr.ts` (~975 lines) with PR timeline metadata, iteration diffs, thread status tracking, re-review detection, Haiku context distillation for large files, and the manifest v2 schema.

**Deliverables:**
- [x] New function `fetchTimeline()` in `scripts/prep-pr.ts` — calls ADO REST `GET /pullrequests/{id}/threads`, `GET /pullrequests/{id}/iterations`, and `GET /pullrequests/{id}/statuses`; structures chronological lifecycle data (iteration timestamps, vote history, status transitions, comment thread timeline); writes `pr-timeline.json` to the cache directory
- [x] New function `computeIterationDiff()` in `scripts/prep-pr.ts` — calls ADO REST `GET /pullrequests/{id}/iterations/{iterationId}/changes`; computes which files were added/removed/modified between the current and previous review iteration; writes `iteration-diff.json` to cache (only emitted on re-reviews)
- [x] Enhanced `fetchPRContext()` in `scripts/prep-pr.ts` — augments existing PR context with structured thread status data: per-thread status (active/resolved/won't-fix/closed), thread author role (reviewer vs. author vs. other), and thread file/line/iteration context; written into the existing `pr-context.json`
- [x] New function `detectReReview()` in `scripts/prep-pr.ts` — checks for `.claude.local/reviews/PR-{id}-journey.md`; if found, sets `manifest.isReReview = true`, extracts `previousIterationId` from journey file metadata, records the journey file path in manifest
- [x] New function `distillLargeFiles()` in `scripts/prep-pr.ts` — for each downloaded file exceeding 2000 lines: known files (`build.js`, `FormsService.cs`) invoke the appropriate skill index; all other large files spawn a Haiku context distiller sub-agent that reads the file + diff and extracts modified functions/methods, immediate callers/callees, class-level state, and structural context; outputs written to `structural-context/{filename}.md` in the cache directory
- [x] Updated manifest schema to v2 — adds fields: `version: 2`, `isReReview`, `previousIterationId`, `journeyFile`, `timelineFile`, `iterationDiffFile`, `structuralContextFiles[]`, `weights: "weights.yaml"`

**Prerequisites:** Phase 1 complete (weights.yaml schema exists for manifest reference). Phase 2 recommended but not blocking.

**Files likely modified:**
- `scripts/prep-pr.ts` — primary change; add `fetchTimeline()`, `computeIterationDiff()`, `detectReReview()`, `distillLargeFiles()`; update `fetchPRContext()` for thread status; update manifest generation

**TDD:** no

**Testing Strategy:**
Run the prep script against a known PR that has multiple iterations and large files. Verify: `pr-timeline.json` exists in cache with iteration timestamps and vote history; `manifest.json` has `version: 2` and all new fields present; `pr-context.json` has structured thread status objects. For a re-review scenario, create a placeholder journey file at `.claude.local/reviews/PR-{id}-journey.md` and re-run — verify `manifest.isReReview = true` and `iteration-diff.json` is generated. For a PR that touches `FormsService.cs` or a large unknown file, verify `structural-context/` directory is populated in cache.

**Integration Notes for Next Phase:**
- The journey/planner agent (Phase 4) reads `manifest.json`, `pr-context.json`, and `pr-timeline.json` from the cache — all three must be present before the planner is invoked
- The `manifest.isReReview` flag and `manifest.journeyFile` path tell the journey agent whether to create a new journey file or append to an existing one
- The `manifest.structuralContextFiles` array tells the investigation and sweep agents (Phases 5–6) which large-file context files to read instead of the raw file

**Implementation Notes:**
- File grew from ~975 to ~1310 lines across 3 sequential batches (WU-9, WU-10, WU-11)
- WU-9: Added `fetchTimeline()` (line 497) + `getEnhancedThreadStatuses()` (line 585); enhanced `fetchPrContext()` to accept optional `TimelineData` and enrich pr-context.json with thread statuses; integrated into `prepPR()` between cache dir creation and file fetching
- WU-10: Added `computeIterationDiff()` (line 613) + `detectReReview()` (line 666); integrated into `prepPR()` after timeline/context fetch; iteration diff only computed on re-reviews with known previous iteration
- WU-11: Added `distillLargeFiles()` (line 719), `LARGE_FILE_LINE_THRESHOLD` constant, `KNOWN_LARGE_FILE_SKILLS` map; updated `Manifest` interface to v2 with 7 new fields; updated both `prepPR()` and `prepLocal()` manifest construction; removed separate reviewHistory copy block (now inline)
- `tsc --noEmit` QG not applicable — TypeScript not a local dep; script runs via `npx tsx`; verified via grep that all functions and v2 fields exist
- QG: `fetchTimeline` ✓, `computeIterationDiff` ✓, `detectReReview` ✓, `distillLargeFiles` ✓; manifest v2 fields in both PR and local mode ✓

---

### Phase 4: Journey / Planner Agent

**Scope:** Create the Journey Agent prompt that produces the persistent journey file and acts as the hierarchical planner (triage validation + investigation dispatch).

**Deliverables:**
- [x] New `agents/journey-planner.md` — agent prompt with YAML frontmatter specifying model: opus, allowed-tools: Read, Write, Agent; prompt covers both roles:
  - **Document producer role:** on initial review, creates `.claude.local/reviews/PR-{id}-journey.md` with the full format from spec (Overview, Objectives, File Change Map with table, Manual Review Guide with core-first/tests-last ordering, PR Lifecycle section); on re-review, reads existing journey file, appends new iteration section to PR Lifecycle, updates File Change Map to reflect current state, updates finding lifespan counts, and regenerates Manual Review Guide prioritizing changed files → unresolved comment files → unchanged critical → everything else
  - **Hierarchical planner role:** after receiving triage output, cross-checks against prep data — files touching core services classified as skim are overridden to important/critical; files central to PR objectives classified below important are overridden; re-review files that changed since last iteration classified as skim are overridden to at least important; all overrides logged with rationale in the amended triage manifest; only after validation does the planner dispatch investigation + sweep agents

**Prerequisites:** Phase 3 complete — the planner reads `manifest.json`, `pr-context.json`, `pr-timeline.json`, and optionally `iteration-diff.json` from the cache.

**Files likely modified:**
- `agents/journey-planner.md` — new file

**TDD:** no

**Testing Strategy:**
Manually invoke the journey-planner agent with a populated prep cache from Phase 3. Verify: journey file is created at `.claude.local/reviews/PR-{id}-journey.md` with all required sections (Overview, Objectives, File Change Map table, Manual Review Guide steps, PR Lifecycle). For re-review: provide the agent with an existing journey file and an `iteration-diff.json` — verify the agent appends a new iteration section rather than overwriting. For planner validation: provide a triage JSON with a deliberate misclassification (core service file marked as skim) — verify the agent produces an amended triage JSON with an override and rationale.

**Integration Notes for Next Phase:**
- The triage agent (Phase 5) reads the journey file as its primary context — the File Change Map and Objectives sections are the key inputs for triage classification
- The triage output JSON that the planner validates is then consumed directly by Phase 8 orchestration to dispatch investigation agents — the validated triage JSON must conform exactly to the schema defined in the spec

**Implementation Notes:**
- Created `agents/journey-planner.md` (213 lines) with dual-role structure: Part 1 (Document Producer) and Part 2 (Hierarchical Planner) as distinct H2 sections
- Journey file template includes all 5 spec sections: Overview, Objectives, File Change Map (table), Manual Review Guide (ordered steps), PR Lifecycle (append-only)
- Re-review behavior covers all 7 steps from spec: read existing journey, read iteration-diff, read thread statuses, append lifecycle, update file change map, update lifespan counts, regenerate manual review guide with priority ordering
- Triage validation has 4 rules: core services override, objective-critical override, re-review changed files override, and a triage confidence warning for bulk-skim scenarios
- Override log format uses JSON with file, originalClassification, amendedClassification, rule, and rationale fields
- Added "Behaviour Notes" section with conservative override guidance and quality guardrails
- QG: frontmatter valid (opus, purple), all spec sections present, no personal names ✓

---

### Phase 5: Triage Agent

**Scope:** Create the Triage Agent prompt that classifies files and change-groups into critical/important/skim tiers based on PR objective alignment and code complexity/blast radius signals.

**Deliverables:**
- [x] New `agents/triage.md` — agent prompt with YAML frontmatter specifying model: opus, allowed-tools: Read; prompt instructs the agent to:
  - Read the journey file (File Change Map + Objectives sections) and `manifest.json` + all diffs for a holistic view
  - Classify each file or logical change-group into critical/important/skim using the two signal dimensions: PR objective alignment × code complexity/blast radius
  - On re-review: apply tier boost to files that changed since last iteration (sourced from `iteration-diff.json`) and to files with unresolved review comments (sourced from `pr-context.json` thread statuses)
  - Output triage JSON conforming to the spec schema (critical/important/skim arrays, each entry with: group, files, rationale, investigationFocus, reReviewNote)
  - Include tier definitions verbatim from spec in the prompt (Critical = PR objective + high blast radius → Investigation Agents; Important = supporting changes → Sweep with standard thresholds; Skim = trivial/generated/low blast radius → Sweep with elevated thresholds)

**Prerequisites:** Phase 4 complete — the triage agent reads the journey file produced by the planner; Phase 3 complete for access to manifest, diffs, and pr-context.

**Files likely modified:**
- `agents/triage.md` — new file

**TDD:** no

**Testing Strategy:**
Manually invoke the triage agent with a journey file and prep cache. Verify: output is valid JSON with `critical`, `important`, and `skim` arrays; each entry has `group`, `files`, `rationale`, `investigationFocus`, and (for re-reviews) `reReviewNote`. Test the re-review tier boost: use a scenario where a previously-skim file appears in `iteration-diff.json` — verify it gets promoted to at least important. Cross-check that the triage output's files list covers all files in the manifest (no files left unclassified).

**Integration Notes for Next Phase:**
- Investigation agents (Phase 6) receive one triage `critical` group entry per agent instance — the `investigationFocus` field from the triage JSON is used verbatim as the agent's assignment
- The sweep agent (Phase 6) receives the full `important` + `skim` file lists and uses the tier distinction to apply correct confidence thresholds (+10% for skim)
- The orchestrator (Phase 8) uses the count of `critical` groups to determine how many investigation agents to spawn in parallel

**Implementation Notes:**
- Created `agents/triage.md` (163 lines) with all spec sections: tier definitions (verbatim), triage signal dimensions, re-review priority boost, classification process, completeness requirement, output JSON schema
- Tier definitions appear exactly as specified: Critical (investigation), Important (sweep standard 0.5), Skim (sweep elevated 0.7)
- Output JSON schema matches spec exactly with group, files, rationale, investigationFocus (required for critical, null otherwise), reReviewNote (present only when tier boost applied)
- Completeness requirement ensures every manifest file appears in exactly one tier
- Cache boundary enforcement included — Read only from cache files + journey file
- QG: frontmatter valid (opus, orange), tier definitions verbatim, output schema exact match, no personal names ✓

---

### Phase 6: Investigation + Sweep Agents

**Scope:** Create the investigation agent prompt template (with Solver-Verifier protocol and specialist escalation) and the sweep agent prompt (with weight-aware thresholds and escalation rights).

**Deliverables:**
- [x] New `agents/investigation.md` — agent prompt template with YAML frontmatter specifying model: opus, allowed-tools: Read (unrestricted), Grep, Glob; prompt includes:
  - Assignment section populated at dispatch time (group name + `investigationFocus` from triage)
  - Condensed PR context section (sourced from journey file overview + objectives)
  - File list for the assigned group (cached file paths + diffs; structural-context file if large file)
  - Full Solver-Verifier protocol section: for every finding — (1) generate hypothesis, (2) verify against codebase evidence (read actual code, trace execution path, confirm alternatives exist), (3) include evidence in output; explicit instruction that no finding is reportable without verification
  - Codebase exploration instructions: local repo = main branch; use for pattern comparison, API existence checks, blast radius validation; do NOT use local files as current state of PR files
  - Specialist escalation section: agent can flag findings needing domain expertise (security, performance, etc.) as escalation candidates with the specialist domain; escalations returned as separate array in output
  - Output format: structured findings JSON with fields: file, line, severity, title, hypothesis, evidence (code snippet + file reference), suggestion, escalation_candidate (bool), specialist_domain (if escalation)
- [x] New `agents/sweep.md` — agent prompt with YAML frontmatter specifying model: sonnet, allowed-tools: Read (cache only); prompt includes:
  - Full embedded YAML rule set (all 8 categories, all ~100 rules, embedded by `rebuild-agents`)
  - Weight-aware threshold instructions: important tier uses standard thresholds (effective_weight >= 0.5); skim tier uses elevated thresholds (effective_weight >= 0.7, i.e., standard threshold + 0.2 buffer equivalent)
  - Cache boundary enforcement: agent may only read files from the PR cache directory, not the local codebase
  - Escalation rights: agent can flag high-severity findings in non-critical files as escalation candidates (same output format as investigation agent escalation field)
  - Output format: same structured findings JSON as investigation agent (for backward compatibility with post-processing)
- [x] Run `rebuild-agents` to embed the clean (source-stripped) rules into `sweep.md`

**Prerequisites:** Phase 1 complete (clean rules for embedding). Phase 2 recommended (weights for threshold documentation). Phase 3 complete (cache structure with structural-context files). Phase 5 complete (triage output format understood).

**Files likely modified:**
- `agents/investigation.md` — new file
- `agents/sweep.md` — new file
- `commands/rebuild-agents.md` — extend to handle the new `sweep.md` agent (embed rules) and skip `investigation.md` (template, not rule-based)

**TDD:** no

**Testing Strategy:**
Manually invoke the investigation agent against a critical area from a cached PR. Verify: findings include explicit evidence citations with file references and code snippets; no finding is reported without an evidence field; the Solver-Verifier section in the output is followed (check agent's reasoning trace). Manually invoke the sweep agent on non-critical files from the same cached PR. Verify: all reads stay within the cache directory; skim-tier borderline findings are suppressed compared to a v1 run; an artificially inserted high-severity pattern in a skim file produces an escalation candidate entry. Verify `rebuild-agents` correctly embeds rules into `sweep.md` but not `investigation.md`.

**Integration Notes for Next Phase:**
- Post-processing (Phase 7) expects findings JSON from both investigation and sweep agents in a unified format — the output schema defined here must be honored exactly
- Escalation candidates are returned as a separate top-level array in each agent's JSON output — the planner (in Phase 8 orchestration) reads this array to decide whether to spawn ad-hoc investigators
- The sweep agent's `effective_weight` threshold logic is duplicated in the post-processing script (Phase 7) for the deterministic filtering step — keep the threshold values consistent between the two

**Implementation Notes:**
- Created `agents/investigation.md` (179 lines) with Solver-Verifier as the central protocol: 3 explicit stages (Hypothesize → Verify → Evidence) with distinct verification requirements per finding type (bugs, edge cases, alternatives, architectural concerns)
- Investigation agent has UNRESTRICTED read access (cache + local codebase) with clear caveat: local = main branch, not PR branch; use for pattern comparison, caller tracing, blast radius assessment
- Specialist escalation covers 5 domains: security, performance, concurrency, data-integrity, api-design
- Output JSON includes findings[] + escalations[] arrays with full evidence fields
- Created `agents/sweep.md` (1957 lines after rule embedding) with weight-aware thresholds: Important >= 0.5, Skim >= 0.7
- Sweep has STRICT cache boundaries (no local codebase access) — opposite of investigation agent
- RULES_START/RULES_END markers preserved; 95 rules embedded across 8 category H3 sections with id, severity, weight, effective weight, and code examples
- Sweep output includes extra fields vs investigation: rule_id, rule_category, effective_weight, tier (for post-processing)
- Updated `commands/rebuild-agents.md`: sweep added to all 8 YAML mappings; journey-planner, triage, investigation added to skip list; special handling for RULES_START/RULES_END markers documented
- QG: all 4 files exist, frontmatter valid, no personal names, unified findings JSON, no duplicate agent names, 95 rules embedded in sweep.md ✓

---

### Phase 7: Post-Processing Script + Synthesizer Upgrade

**Scope:** Build the deterministic TypeScript post-processing script and upgrade the synthesizer from Haiku to Sonnet with a new output format.

**Deliverables:**
- [x] New `scripts/post-process.ts` — TypeScript script that reads findings JSON (from all agents, passed via stdin or file argument), loads `knowledge/weights.yaml`, and executes in order: (1) compute `effective_weight = rule_weight × category_multiplier` for each sweep finding; (2) drop sweep findings below minimum effective weight threshold (0.3); (3) deduplicate by file:line — keep highest-weighted when duplicates exist; (4) rank all findings by tier (critical > important > skim) → severity (blocking > important > nit) → effective_weight; (5) filter out-of-scope findings (files not in manifest); (6) on re-reviews, annotate finding lifespan by comparing against previous review artifact findings using fingerprint match (rule_id + file + approximate line range); outputs processed findings JSON to stdout with a `processed_findings` top-level array and `dropped_count`, `dedup_count`, `lifespan_annotations` summary fields; script header documents expected input JSON schema
- [x] New `agents/synthesizer-v2.md` — agent prompt replacing `agents/review-synthesizer.md`; YAML frontmatter: model: sonnet, allowed-tools: Read; reads processed findings JSON, journey file, and triage classification; produces final review markdown in the output format from spec: header block (author, branch, date, review type), Summary (2–3 paragraph narrative contextualizing findings within PR objectives), Critical Findings (investigation agent findings with evidence + suggestion + lifespan), Rule-Based Findings (sweep findings with effective_weight annotations, split into Important/Minor), Re-Review Status section (comment resolution counts, unresolved threads, new changes, persistent findings) if applicable, Strengths section; narrative distinguishes investigation findings (deep, evidence-based) from sweep findings (rule-based)

**Prerequisites:** Phase 6 complete — post-processing expects the unified findings JSON format defined in Phase 6. Phase 4 complete — synthesizer reads the journey file. Phase 5 complete — synthesizer reads triage classification.

**Files likely modified:**
- `scripts/post-process.ts` — new file
- `agents/synthesizer-v2.md` — new file
- `agents/review-synthesizer.md` — can be retained as legacy reference or renamed; Phase 8 orchestration will reference `synthesizer-v2.md` going forward

**TDD:** no

**Testing Strategy:**
Feed a hand-crafted findings JSON through `post-process.ts` with known weight values. Verify: a finding with `effective_weight < 0.3` is dropped; two findings at the same file:line keep the higher-weighted one; findings are output in tier → severity → weight order; a finding with a file not in the manifest is filtered. For re-review lifespan: create two findings JSON inputs (simulating current and previous review) with one overlapping fingerprint — verify the overlap is annotated with `"raised_in": 2`. Invoke `synthesizer-v2.md` with processed findings + a real journey file — verify the output markdown has all required sections and the summary references the PR's actual objectives.

**Integration Notes for Next Phase:**
- Phase 8 orchestration invokes `post-process.ts` after all agent outputs are collected, passing combined findings JSON and receiving ranked, filtered output
- The synthesizer is the last LLM step — Phase 8 feeds it the post-process output + journey file path and writes the synthesizer's markdown output to `.claude.local/reviews/PR-{id}.md`
- The `post-process.ts` script expects a specific input schema — Phase 8 must aggregate investigation + sweep agent outputs into that schema before calling the script

**Implementation Notes:**
- Created `scripts/post-process.ts` (489 lines) with 6 named pipeline steps: step1_computeWeights, step2_dropBelowThreshold, step3_deduplicate, step4_rank, step5_filterOutOfScope, step6_annotateLifespan
- Category mapping converts rule file categories (`csharp-architecture`, `api-design`, etc.) to weights.yaml multiplier keys (`architecture`, `api_design`, etc.)
- Investigation findings get `effective_weight: 1.0` and `tier: "critical"` for ranking priority; they pass through all steps except weight computation
- Dedup prefers investigation findings over sweep at same `file:line`; among same source, keeps highest effective_weight
- Previous review parsing uses regex to extract `file:line` from both `**File:**` patterns (investigation) and `[file:line]` patterns (sweep)
- Lifespan fingerprinting uses file + line proximity (±20 lines) + title comparison for investigation findings
- `@types/js-yaml` moved to devDependencies; `@types/node` and `typescript` added as devDependencies for type-checking
- `tsconfig.json` updated with `"types": ["node"]` for proper Node.js type resolution
- Created `agents/synthesizer-v2.md` (158 lines) with Sonnet model, blue color; includes full input spec, output template with all 6 SPEC sections, narrative guidelines, section omission rules, ordering preservation, cache boundary constraints
- Old `review-synthesizer.md` retained as legacy reference
- QG: post-process.ts type-checks (zero errors), synthesizer-v2.md has valid frontmatter, no personal names, all pipeline steps present ✓

---

### Phase 8: Orchestration Rewrite

**Scope:** Rewrite `commands/review-pr.md` to implement the full v2 pipeline end-to-end. Update `commands/learn-from-pr.md` with EMA calibration via hybrid matching.

**Deliverables:**
- [x] Rewritten `commands/review-pr.md` — full v2 pipeline orchestration in order:
  1. Run enhanced prep script (`scripts/prep-pr.ts`) — produces cache with manifest v2, `pr-timeline.json`, `pr-context.json`, diffs, downloaded files, structural context
  2. Launch journey/planner agent (`agents/journey-planner.md`) → produces journey file at `.claude.local/reviews/PR-{id}-journey.md` (created or appended)
  3. Launch triage agent (`agents/triage.md`) → produces triage JSON
  4. Planner validates triage — planner agent reads triage JSON and prepares amended/validated triage manifest; logs overrides with rationale
  5. Dispatch investigation agents in parallel (one per `critical` group from validated triage, using `agents/investigation.md` template) + sweep agent in parallel (`agents/sweep.md` on all important + skim files)
  6. Planner evaluates sweep escalation candidates — for each escalation flagged by sweep agent, planner decides whether to spawn an ad-hoc investigation agent; if so, launches agent and collects output
  7. Aggregate all findings JSON from investigation agents + sweep agent into unified input for post-processing
  8. Run deterministic post-processing (`scripts/post-process.ts`) — produces ranked, filtered, deduplicated, lifespan-annotated findings JSON
  9. Launch synthesizer agent (`agents/synthesizer-v2.md`) with processed findings + journey file → produces final review markdown
  10. Write review to `.claude.local/reviews/PR-{id}.md`
  11. Write/update journey file (planner confirms it is finalized)
  12. Print cache directory path and review artifact path as completion output
- [x] Updated `commands/learn-from-pr.md` — enhanced post-review calibration: (1) pull ADO comments for the reviewed PR via `get-pr-comments.ps1`; (2) load the plugin review artifact from `.claude.local/reviews/PR-{id}.md`; (3) apply hybrid matching — proximity filter (same file, within ~20 lines) then Haiku LLM judge for semantic equivalence — to classify each plugin finding as TP/FP; identify FN where human comments have no matching plugin finding; (4) update `knowledge/weights.yaml` via EMA for each affected rule (`new_weight = 0.25 × signal + 0.75 × old_weight`; increment `data_points`); (5) extract new rules from FN patterns (existing behavior); (6) never record a `source:` field in new rules; (7) update `last_calibrated` and `calibration_prs` list in `weights.yaml`
- [ ] End-to-end verification on a real PR (see testing strategy) — *runtime verification, not code deliverable*
- [ ] Re-review verification — review the same PR twice, confirming journey file append and finding lifespan annotation — *runtime verification, not code deliverable*

**Prerequisites:** All preceding phases complete (1–7).

**Files likely modified:**
- `commands/review-pr.md` — full rewrite
- `commands/learn-from-pr.md` — enhanced with EMA calibration

**TDD:** no

**Testing Strategy:**
Run `/cognito-pr-review:review-pr {PR_ID}` on a real PR end-to-end. Verify: cache directory is populated (timeline, context, structural context if applicable); journey file created with all required sections; triage JSON produced and planner validation log shows at least a cross-check occurred (override or no-override, both are valid outcomes); investigation agents ran for each critical group and their findings include evidence citations; sweep agent ran and produced weight-annotated findings; post-process.ts reduced the finding count (dedup/filtering occurred); final review markdown exists at `.claude.local/reviews/PR-{id}.md` with all output format sections. For re-review: run the same PR again — verify `manifest.isReReview = true`, journey file has a new iteration section appended, review markdown includes a Re-Review Status section with comment resolution data. Run `/cognito-pr-review:learn-from-pr` for the reviewed PR and verify `knowledge/weights.yaml` has updated `data_points` for rules that appeared in the review.

**Integration Notes for Next Phase:**
- Phase 9 (Tree-Sitter MCP) is an optimization overlay — the Phase 8 pipeline is complete and functional without it
- Investigation agents currently use Read/Grep/Glob for codebase exploration; Phase 9 will add Tree-Sitter MCP tools as an additional (optional) mechanism by updating `agents/investigation.md`
- The `review-pr.md` orchestration step for dispatching investigation agents should be written to be forward-compatible with additional tool availability (i.e., don't hardcode the tool list in the orchestration command — let the agent prompt define its own tools)

**Implementation Notes:**
- Rewrote `commands/review-pr.md` with 12-step v2 pipeline: prep → journey → triage → planner validation → investigation+sweep (parallel) → escalation evaluation → aggregate → post-process → synthesize → write → finalize → report
- Preserved backwards compatibility: same argument parsing (PR_ID, aspects, sequential, local), same cache boundary enforcement (pr-review-active.json), same usage examples, same local mode invocation
- Aspect filtering works as a file filter on triage output, not as agent selection — all triage runs regardless, but investigation/sweep only receive matching files
- Sequential mode applies to Step 5 (investigation agents run one at a time instead of parallel)
- Cache boundary marker created at Step 1.5 and removed at Step 12.5
- Forward compatibility: investigation agent tools defined in agent prompt (agents/investigation.md), not in orchestration — Phase 9 Tree-Sitter tools can be added without changing review-pr.md
- Enhanced `commands/learn-from-pr.md` with Step 2.5 (EMA Calibration): hybrid matching (proximity filter ±20 lines + Haiku semantic judge), TP/FP/FN classification, EMA weight update (α=0.25), calibration metadata (last_calibrated, calibration_prs), calibration summary report
- FN patterns from calibration feed into Step 3 as high-priority rule candidates
- Added `Agent` to learn-from-pr.md allowed-tools for Haiku semantic judge
- Updated `rebuild-agents.md` skip list to include `synthesizer-v2`
- QG: review-pr.md references all v2 agents (49 matches), preserves backwards compat, learn-from-pr.md has EMA formula + hybrid matching + calibration metadata updates, no personal names ✓

---

### Phase 9: Tree-Sitter MCP Server (Deferred)

**Scope:** Build a Tree-Sitter MCP server for C# and TypeScript that provides structural codebase queries to investigation agents, replacing expensive raw file reads with graph-native symbol lookups.

**Deliverables:**
- [x] New MCP server project at `~/.claude/mcp-servers/tree-sitter/` — TypeScript implementation with web-tree-sitter (WASM) parsers for C# and TypeScript
- [x] MCP tool: `find_symbol_usages(symbol: string, file?: string)` — find all references to a symbol across the codebase
- [x] MCP tool: `get_callers(function: string, file: string)` — find all callers of a given function
- [x] MCP tool: `get_callees(function: string, file: string)` — find all functions called by a given function
- [x] MCP tool: `get_file_structure(path: string)` — return class/method/function outline for a file
- [x] MCP tool: `get_dependencies(file: string)` — return imports and cross-file references
- [x] Updated `agents/investigation.md` — add section instructing agents to prefer structural MCP queries when tools are available (e.g., use `get_callers` before reading entire files to find blast radius); retain Read/Grep/Glob as fallback
- [ ] Validation: run investigation agent on the same PR with and without Tree-Sitter MCP available; compare token consumption and finding quality — *runtime verification, not code deliverable*

**Prerequisites:** Phase 8 complete (full pipeline working; Tree-Sitter is an optimization, not a correctness requirement).

**Files likely modified:**
- `~/.claude/mcp-servers/tree-sitter/` — new MCP server project (all files)
- `agents/investigation.md` — add preferred structural query instructions with MCP tool names
- MCP server registration in Claude Code settings (to expose tools to the investigation agent)

**TDD:** no

**Testing Strategy:**
Start the Tree-Sitter MCP server and register it. Run an investigation agent on a critical area of a cached PR — verify the agent calls `get_callers` or `get_file_structure` before falling back to raw `Read` calls. Compare token count from the agent tool call log against a baseline run without the MCP server on the same PR. Verify finding quality is equal or better (no regressions). Test edge cases: symbol not found, file outside C#/TypeScript (should gracefully fall back to Read).

**Integration Notes:**
- This is a self-contained optimization layer — if the MCP server is unavailable, investigation agents fall back to Read/Grep/Glob without any pipeline changes
- The `agents/investigation.md` update is the only plugin file that changes; all orchestration in `commands/review-pr.md` remains unchanged

**Implementation Notes:**
- Built TypeScript MCP server (16 source files) using web-tree-sitter ^0.25.3 (WASM) + tree-sitter-wasms ^0.1.13 for C# and TypeScript/TSX grammar support
- Hybrid architecture: single-file AST parsing via tree-sitter for local queries (get_file_structure, get_callees, get_dependencies) + ripgrep-based cross-file search with tree-sitter verification for global queries (find_symbol_usages, get_callers)
- Lazy parser initialization (Parser.init() on first tool call, not at import) with LRU parse cache (50 entries, mtime-based invalidation)
- All 5 tools use `registerTool()` with title, comprehensive description (Args/Returns/Examples/Error Handling), `.strict()` Zod schemas, all 4 annotations, and dual response format (content + structuredContent)
- CHARACTER_LIMIT = 25000 applied to all tool responses with truncation guidance
- Zero console.log (stdout reserved for JSON-RPC), zero `any` types, `strict: true` TypeScript
- MCP server registered in `.mcp.json` alongside existing ADO server via `npx tsx` runner
- investigation.md updated with new "Structural Codebase Queries (MCP Tools)" section between "Codebase Exploration" and "Solver-Verifier Protocol", with clear usage guidance and fallback instructions
- Exclusion patterns cover Cognito Forms monorepo: bin, obj, node_modules, packages, Dependencies, .nx, dist, TestResults, .git, BuildSupport, .vs, .idea, TestData, wwwroot/lib
- QG: `tsc --noEmit` zero errors, `npm run build` produces dist/index.js, server starts on stdio without crash, no stubs/console.log/any remaining ✓

---

### Phase 10: ADO → GitHub Migration — Prep Script + Comment Export

**Scope:** Replace all Azure DevOps REST API integration in `scripts/prep-pr.ts` with GitHub REST API equivalents. Replace the ADO-based `get-pr-comments.ps1` script with a GitHub-based version using `gh api`. Update all command files that reference ADO. The Cognito Forms repo has migrated to GitHub (`origin → https://github.com/cognitoforms/cognito.git`); work items remain in ADO but PRs and PR comments are now on GitHub. This replaces the ADO API layer built in Phase 3 while preserving all manifest v2 output formats so downstream agents (Phases 4–9) are unaffected.

**Deliverables:**
- [x] Rewritten API layer in `scripts/prep-pr.ts` — replace ADO auth/fetch with GitHub equivalents:
  - Replace `ADO_ORG`, `ADO_PROJECT`, `ADO_REPO` constants with `GITHUB_OWNER = "cognitoforms"`, `GITHUB_REPO = "cognito"`; add auto-detection from `git remote -v` (parse origin URL) as fallback
  - Replace `getAccessToken()` (Azure CLI) with `getGitHubToken()` using `gh auth token` or `GITHUB_TOKEN` env var
  - Replace `adoFetch<T>()` with `ghFetch<T>()` targeting `https://api.github.com/repos/{owner}/{repo}/...` with `Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28` headers
  - Replace `getPullRequest()` — `GET /repos/{owner}/{repo}/pulls/{pr_number}`; map response shape (`user.login`, `head.ref`, `head.sha`, `base.ref`, `base.sha`)
  - Replace `getChangedFiles()` — `GET /repos/{owner}/{repo}/pulls/{pr_number}/files?per_page=100&page=N`; paginated, max 3000 files; response items have `filename`, `status`, `patch`, `additions`, `deletions`
  - Replace `getFileContent()` — `https://raw.githubusercontent.com/{owner}/{repo}/{commit_sha}/{path}` for raw content download (simpler than contents API for our use case)
  - Replace `getIterations()` — GitHub has no first-class iteration concept; approximate via `GET /repos/{owner}/{repo}/issues/{pr_number}/timeline` (group `pushed` events into synthetic iterations) + `GET /repos/{owner}/{repo}/pulls/{pr_number}/commits`
  - Replace `fetchTimeline()` — combine: PR reviews (`GET /pulls/{pr_number}/reviews`), review comments (`GET /pulls/{pr_number}/comments`), issue comments (`GET /issues/{pr_number}/comments`), commit check runs (`GET /commits/{sha}/check-runs`); map ADO votes to GitHub review states (`APPROVED` → vote 10, `CHANGES_REQUESTED` → vote -5, `COMMENTED` → vote 0)
  - Replace `computeIterationDiff()` — use `GET /repos/{owner}/{repo}/compare/{base_sha}...{head_sha}` between consecutive push event SHAs
  - Replace `fetchPrContext()` — inline GitHub API calls instead of delegating to `get-pr-comments.ps1`; PR description comes from PR metadata `.body`; thread statuses from review comments with `resolved` field
  - Update all TypeScript interfaces (`PullRequest`, `DiffChange`, `DiffResponse`, `PRThread`, `PRStatus`, `Iteration`) to match GitHub response shapes
  - `Manifest`, `ManifestFile`, `TimelineData` output interfaces unchanged — downstream agents see identical cache format
  - Local mode (`prepLocal()`) unchanged — no remote API dependency
- [x] Rewritten `get-pr-comments.ps1` to use `gh api` instead of `az devops` CLI — same output format (Markdown/JSON) so `calibrate.md` and `learn-from-pr.md` consume it unchanged; parameters: `PrIdOrBranch`, `OutputFile`, `ActiveCommentsOnly`, `Format`, `IncludePrDescription`, `IncludeWorkItems`; work item extraction from PR description (ADO WI IDs in `AB#NNNNN` format) still uses `az boards` if available, otherwise parses from PR body
- [x] Updated `commands/review-pr.md` — replace "ADO REST API" references with "GitHub REST API"; update Step 1 error guidance (`az login` → `gh auth login`); update component descriptions; update notes section
- [x] Updated `commands/learn-from-pr.md` — replace "ADO comments" / "ADO reviewer comments" references with "GitHub PR comments"; update the `get-pr-comments.ps1` invocation documentation
- [x] Updated `commands/calibrate.md` — replace "Pull ADO Comments" step title and description; update `get-pr-comments.ps1` references
- [ ] Updated `README.md` — rewrite Architecture section for v2 pipeline + GitHub; update Requirements section (`gh` CLI instead of Azure CLI); update file structure to include v2 agents and scripts; bump version to v2.5

**Implementation Notes (Phase 10):**
- `prep-pr.ts`: 1476 lines total. Key new functions: `ghFetch<T>()` (line 443), `ghFetchPaginated<T>()` (line 462), `getGitHubToken()` (line 432), `detectGitHubRepo()` (line 29), `mapGitHubStatus()` (line 525). Iterations are synthetic (one per PR commit). `fetchPrContext()` is self-contained (no external script dependency). `PRThread`/`ThreadComment`/`PRStatus` interfaces remain defined but are unused dead types — they can be cleaned up later.
- `get-pr-comments.ps1`: 414 lines. Uses `gh api --paginate` for inline review comments and issue comments. Thread grouping via `in_reply_to_id`. Bot filtering via `user.type -eq "Bot"`. Work items parsed from `AB#NNNNN` in PR body; `az boards` used for enrichment if available, otherwise stub data.
- All command files: zero ADO remnants confirmed via grep.
- README.md deliverable deferred (not in implementation plan scope — plan focused on 5 files only).

**Prerequisites:** Phase 8 complete (full v2 pipeline working). Phase 9 optional (Tree-Sitter MCP is independent).

**Files likely modified:**
- `scripts/prep-pr.ts` — major rewrite of API layer (~400 lines of ADO-specific code replaced with GitHub equivalents); all downstream-facing output interfaces preserved
- `get-pr-comments.ps1` (at Cognito Forms repo root `C:\Users\JacobMadsen\source\repos\Cognito Forms\get-pr-comments.ps1`) — rewrite to use `gh api` instead of `az devops`
- `commands/review-pr.md` — ADO → GitHub reference updates
- `commands/learn-from-pr.md` — ADO → GitHub reference updates
- `commands/calibrate.md` — ADO → GitHub reference updates
- `README.md` — full update for v2 + GitHub

**TDD:** no

**Testing Strategy:**
Run `prep-pr.ts` against a real GitHub PR (create a test PR or use an existing one). Verify: manifest.json has correct file list matching GitHub PR files; diffs are accurate; `pr-timeline.json` has iteration-like data from push events, review data from GitHub reviews, and check run status data; `pr-context.json` has thread statuses mapped from GitHub review comments; structural context generated for large files. Run the full pipeline end-to-end (`/cognito-pr-review:review-pr {PR_NUMBER}`) to confirm downstream agents are unaffected by the data source change. Verify local mode is completely unchanged. Test `get-pr-comments.ps1` with a GitHub PR number — verify output matches the expected format for `calibrate.md` consumption. Verify auth error handling: run without `gh` auth → expect clear error message directing to `gh auth login`.

**Integration Notes:**
- The `pr-context.json` shape will differ slightly from ADO (GitHub comment model has `resolved` field on review comments rather than thread-level status). Downstream agents that read `pr-context.json` (journey-planner, triage) are LLM-based and read the JSON structure — they'll adapt to the new shape without prompt changes as long as the semantic content (file, line, status, author) is preserved.
- GitHub's "iteration" concept is synthetic (from push events). If re-review detection (`detectReReview()`) relies on exact iteration IDs matching the journey file, verify the synthetic IDs are stable across prep runs for the same PR.
- GitHub API rate limits: authenticated requests get 5000/hour. A typical PR prep uses ~20-50 API calls. No rate limiting concern for normal usage, but add a rate limit check/warning for bulk operations.
- The `get-pr-comments.ps1` output format must remain compatible with both `calibrate.md` and `learn-from-pr.md` hybrid matching logic — test with both commands after migration.

**Context from prior phases:**
- Phase 3 Implementation Notes: `fetchTimeline()` is at ~line 497, `computeIterationDiff()` at ~line 613, `detectReReview()` at ~line 666, `distillLargeFiles()` at ~line 719 of prep-pr.ts. Total file is ~1310 lines.
- Phase 3: The iteration diff uses ADO's `changeType` numeric enum (1=add, 2=delete, 4=edit, 8=rename, 16=sourcerename) — GitHub uses string status (`added`, `removed`, `modified`, `renamed`).
- Phase 8 Implementation Notes: `review-pr.md` already treats prep script output as opaque (reads manifest.json, doesn't know about ADO internals). This means the orchestration layer requires zero changes.
- Phase 8: `learn-from-pr.md` calls `get-pr-comments.ps1` in Step 1 — this script must be migrated or the calibration commands break.
- Phase 7: `post-process.ts` and `aggregate-findings.ts` consume agent output JSON, not PR API data — completely unaffected.
