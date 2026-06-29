# Implementation Phases — Spot-Check Review

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this feature is a Claude Code plugin command (markdown orchestration) plus plugin docs/metadata; it has no Tauri app or MCP-reachable runtime surface. Verification is a real `/cognito-pr-review:spot-check` run against a PR, observed directly.

> **Note on testing model:** there is no automated unit-test harness for slash-command markdown. "Tests" here are real end-to-end runs of the command against a small PR, with the observable artifact and dispatch behavior asserted by inspection. Phases are therefore non-TDD.

---

### Phase 1: Author the `spot-check` command

**Scope:** Author the complete `commands/spot-check.md` — the entire command in one file: frontmatter, argument + scope parsing, prep delegation, scope resolution, inline-first review, conditional single-`investigation` escalation, inline synthesis, and timestamped standalone artifact output. Scope resolution and the inline review loop are deliverables *within* this phase, not separate phases — they all live in the one markdown file and cannot be exercised independently of the command shell (splitting them would put multiple writers on one file).

**Deliverables:**
- [x] `commands/spot-check.md` with frontmatter: `description`, `argument-hint: "[PR_ID | local] [scope: last-commit|since-review|<sha>..<sha>|<glob>|<free-text>]"`, `allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Agent"]`.
- [x] Argument parsing: PR mode (first numeric token) vs local mode (`local` / no ID, with `--base`, `--include-untracked`); remaining tokens parsed as scope (structured tokens + free-text).
- [x] Step 1 — Prep delegation: invoke `prep-pr.ts {id}` (PR) or `--local …` exactly as `review-pr.md` Step 1, referencing it as the source of truth (do not duplicate the body). Read `cacheDir` / `cogDocsItemDir` from prep output. Explicitly skip the cache-boundary marker.
- [x] Step 2 — Scope resolution: whole-PR default; `last-commit`/`latest`; `since-review` via `pr-timeline.json` review timestamps with `last-commit` fallback; `<sha>..<sha>`; path/glob filter; free-text interpreted against the manifest. Record the resolved human-readable scope.
- [x] Step 3 — Inline review: orchestrator reads the scoped cached diffs and reviews directly with senior-Cognito-reviewer judgment (no sweep/triage/journey/reuse/intra-file agents).
- [x] Step 4 — Conditional escalation: dispatch at most one `cognito-pr-review:investigation` agent, only for a genuinely risky change; fold its findings in.
- [x] Step 5 — Inline synthesis in `synthesizer-v2` output format (no synthesizer agent dispatch); header marks it a spot-check and states the reviewed scope.
- [x] Step 6 — Write artifact: PR mode → `<cogDocsItemDir>/PR-{id}-spot-{YYYY-MM-DD-HHMM}.md`; local → `.claude.local/reviews/LOCAL-{branch}-spot-{YYYY-MM-DD-HHMM}.md`. Print completion summary. No `REVIEWED.md`, no `pending-calibration.json`, no calibration.
- [x] Explicit non-goal stated in-command: never invoke ADO MCP or `az`.

**Reuse:** reuses `scripts/prep-pr.ts` as-is (SPEC Reuse Ledger row "PR data / diffs / timeline / cog-docs dir"); conditionally dispatches `agents/investigation.md` (`subagent_type: cognito-pr-review:investigation` — Ledger row "Deep-dive a risky change"); follows `agents/synthesizer-v2.md`'s output format inline without dispatching it (Ledger row "Review document format"). Governed by the plugin `CLAUDE.md` orchestration patterns; mirrors `commands/review-pr.md` structure.

**Minimum Verifiable Behavior:** running `/cognito-pr-review:spot-check <small PR id>` produces `PR-{id}-spot-{YYYY-MM-DD-HHMM}.md` in the resolved cog-docs item dir, and a clean small PR completes with **zero** subagent dispatches.

**Runtime Verification** *(checked by a real command run — NOT by an implementation agent):*
- [x] <!-- verification-only --> `/cognito-pr-review:spot-check <small PR>` writes a `PR-{id}-spot-{datetime}.md` artifact in the cog-docs item dir, in synthesizer-v2 format, with a header stating the reviewed scope.
- [ ] <!-- verification-only --> A clean small PR completes with zero `investigation` dispatches; a PR with a subtle correctness change escalates exactly one `investigation` agent and folds its finding into the artifact.
- [ ] <!-- verification-only --> `/cognito-pr-review:spot-check <id> last-commit` reviews only the latest commit's files; `since-review` resolves changes since the reviewer's last review (or falls back to `last-commit`, stated in the header).
- [ ] <!-- verification-only --> Local mode (`/cognito-pr-review:spot-check` with uncommitted changes) writes to `.claude.local/reviews/`.
- [x] <!-- verification-only --> No `az`/ADO-MCP call occurs; no `REVIEWED.md` or `pending-calibration.json` is written; `knowledge/weights.yaml` is unchanged after a run.

**MCP Integration Test Assertions:** N/A — no MCP-reachable runtime surface (plugin command authoring).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `commands/spot-check.md` — **net-new (create)**: the full command orchestration.

**Testing Strategy:** Manual end-to-end runs. (1) A small, clean PR → expect a clean artifact, zero dispatches. (2) A PR with a planted risky change → expect one `investigation` escalation and the finding in the artifact. (3) Scope runs: `last-commit`, `since-review`, a path glob, and a free-text phrase → expect the header to reflect the narrowed scope. (4) A local-mode run on uncommitted changes. Confirm absence of ADO calls / sentinels / weight writes in each.

**Integration Notes for Next Phase:**
- The command name (`spot-check`) and the timestamped artifact naming (`PR-{id}-spot-{YYYY-MM-DD-HHMM}.md`) established here are what Phase 2's docs must describe.
- The argument-hint string authored here is the canonical scope-syntax reference; Phase 2 README examples should match it verbatim.

#### Implementation Notes

**Date:** 2026-06-29
**Status:** Implementation complete (runtime-verification rows remain unchecked — a real `/cognito-pr-review:spot-check` run owns those).

**Work completed:** Authored the net-new `commands/spot-check.md` — the full lightweight spot-check command in one file. All eight implementation deliverables landed: frontmatter (canonical `argument-hint`), argument/scope parsing, Step 1 prep reuse (references `review-pr.md` Step 1, reads `cacheDir` from stdout manifest + `cogDocsItemDir` from stderr, explicitly skips the Step 1.5 cache-boundary marker with stated reason), Step 2 scope grammar (whole-PR / `last-commit` / `since-review` w/ `last-commit` fallback / `<sha>..<sha>` / glob / free-text), Step 3 inline review, Step 4 single conditional `cognito-pr-review:investigation` escalation, Step 5 inline synthesizer-v2 format synthesis, Step 6 timestamped standalone artifact, and the explicit no-ADO/`az` non-goal.

**Canonical strings (Phase 2 docs MUST mirror verbatim):**
- `argument-hint`: `"[PR_ID | local] [scope: last-commit|since-review|<sha>..<sha>|<glob>|<free-text>]"`
- Artifact naming: PR mode `PR-{id}-spot-{YYYY-MM-DD-HHMM}.md`; local mode `LOCAL-{branch}-spot-{YYYY-MM-DD-HHMM}.md`.

**Integration notes:** No CLAUDE.md change made in Phase 1 (the spot-check Key Commands row is owned by Phase 2 — one writer per file). Reuse anchors verified present on branch before authoring (`review-pr.md`, `agents/investigation.md`, `agents/synthesizer-v2.md`, `scripts/prep-pr.ts`).

**Files modified:** `commands/spot-check.md` (net-new), this PHASES.md, plan part-1 frontmatter/WU checkbox.

**Deviation:** Recursive `Agent` dispatch was DENIED in the execution environment (single-cycle subagent constraint). Per the plan's invocation note ("if you cannot fan out further, author the file directly yourself"), the orchestrator authored `commands/spot-check.md` directly. The Step B.2 review gate was then run inline against SPEC + deliverables.

**Quality gates:** Frontmatter parses as valid YAML; `argument-hint` verbatim canonical; `allowed-tools` correct. Leakage grep clean — the only hits for `weights.yaml`/`pending-calibration`/`REVIEWED.md` are inside the explicit Standalone Guarantees / Step 6 non-goal statements (no operational leakage); no `az ` operational match.

#### Review Notes

**Review verdict:** PASS (2026-06-29). Inline review (recursive reviewer dispatch denied). All six steps present and aligned with SPEC Technical Design + Reuse Ledger; frontmatter exact; investigation capped at one; synthesis inline in synthesizer-v2 format with correct omission rules; artifact paths timestamped; standalone guarantees present. Propagation check N/A (standalone markdown). Mount-site correct (command auto-discovered from `commands/`).

---

### Phase 2: Integrate & document

**Scope:** Surface the new command in the plugin's docs and metadata so it is discoverable and loads correctly. Separate phase from Phase 1 purely to keep one writer per file (different files than `spot-check.md`).

**Deliverables:**
- [x] `README.md`: add a `spot-check` usage block (mirroring the SPEC examples) and a short architecture note distinguishing it from `review-pr` / `review-pr-buddy` (lighter, inline-first, scope-targetable, standalone).
- [x] `CLAUDE.md`: add a Key Commands table row for `/cognito-pr-review:spot-check [PR#] [scope]` with a one-line purpose.
- [x] `.claude-plugin/plugin.json`: bump `version` `2.7.0` → `2.8.0` and extend the `description` to mention the lightweight spot-check command.

**Reuse:** none beyond editing existing docs/metadata (no ledger capability touched).

**Minimum Verifiable Behavior:** after reload, `/cognito-pr-review:spot-check` is listed as an available command and the README/CLAUDE.md examples match the command's actual argument-hint.

**Runtime Verification** *(checked by inspection / plugin reload):*
- [x] <!-- verification-only --> The plugin loads and `/cognito-pr-review:spot-check` appears in the command list.
- [x] <!-- verification-only --> README usage examples and the `CLAUDE.md` row match the Phase 1 `argument-hint` (no drift).

**MCP Integration Test Assertions:** N/A — docs/metadata only.

**Prerequisites:**
- Phase 1: `commands/spot-check.md` must exist (its frontmatter `argument-hint` is the source the docs mirror).

**Files likely modified:**
- `README.md` — add usage + architecture note.
- `CLAUDE.md` — add Key Commands row.
- `.claude-plugin/plugin.json` — version bump + description extension.

**Testing Strategy:** Reload the plugin; confirm the command is listed and invocable. Diff the README/CLAUDE examples against the Phase 1 argument-hint to confirm no drift.

**Integration Notes for Next Phase:** N/A — final phase.

**Completion (gate-owned):** flipping the SPEC `**Status:**` to Complete is not a checkbox here; it is recorded when both phases' runtime verification passes.

#### Implementation Notes

**Date:** 2026-06-29
**Status:** Implementation complete (runtime-verification rows remain unchecked — a real plugin reload + command list observation owns those).

**Work completed:** All three Phase 2 deliverables landed. `README.md` received a new `### Spot-Check (Lightweight / Scope-Targeted)` section inserted between `### Buddy Review` and `### Learn from PRs / Calibrate`, containing all 7 verbatim example invocations from SPEC and a 4-trait distinguishing description (lighter / inline-first / scope-targetable / standalone). `CLAUDE.md` Key Commands table received a new row for `/cognito-pr-review:spot-check [PR#] [scope]` immediately after the `review-pr-buddy` row. `.claude-plugin/plugin.json` was bumped from `2.7.0` → `2.8.0` and the description was extended with a spot-check clause; JSON validity confirmed via `python -m json.tool`.

**Final state:** `version: 2.8.0`; README examples and CLAUDE.md row match the Phase 1 `argument-hint` verbatim (`[PR_ID | local] [scope: last-commit|since-review|<sha>..<sha>|<glob>|<free-text>]`); no drift detected across all three surfaces.

**Deviation:** Recursive Agent dispatch was DENIED in the execution environment (single-cycle subagent constraint). Per the plan's invocation note and user prompt ("fall back to authoring the files directly yourself"), the orchestrator authored all three files directly. The Step B.2 review gate was run inline.

**Quality gates:** JSON valid (python -m json.tool passes); version 2.8.0 confirmed (grep hit at line 3); no-drift confirmed (7 README spot-check lines + 1 CLAUDE.md row, all matching canonical argument-hint).

#### Review Notes

**Review verdict:** PASS (2026-06-29). Inline review (recursive dispatcher denied). README block: 7 verbatim example lines, correct heading placement, distinguishing prose covers all 4 required traits. CLAUDE.md row: correct format, correct placement, command notation matches canonical argument-hint. plugin.json: valid JSON, version 2.8.0, description extended, no other field altered. No-drift confirmed across all three surfaces against Phase 1 canonical strings.

---

## Notes

- **One writer per file** is the only reason there are two phases rather than one — Phase 1 owns `commands/spot-check.md`; Phase 2 owns `README.md` / `CLAUDE.md` / `plugin.json`. Both phases are small and could run in a single session.
- **No Cross-feature Integration Notes section:** the sole dependency (`cognito-pr-review-v2`) is `composes`, not `hard`, so no upstream PHASES look-back is required.
- **No Review Guardrails block:** the modified files are markdown/JSON, not `*.cs`/`*.vue`/`*.ts`, so the Cognito review-rule corpus selects nothing applicable.
