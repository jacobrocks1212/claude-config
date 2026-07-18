# Implementation Phases — spec-buddy

> Phases for [`SPEC.md`](./SPEC.md)

## Validated Assumptions

1. **No manifest.psd1 edit needed.** `user/skills/` is mapped as a whole-directory symlink in `manifest.psd1`; any new subdirectory placed there is auto-discovered and projected to `~/.claude/skills/` without a manifest entry.
2. **`/spec` is left untouched.** The SPEC mandates "/spec stays lean and untouched." Two small inline blocks from `/spec` — the ~30-line final `SPEC.md` structure template and the user-invoked Gemini research prompt — are therefore minimally replicated inside `spec-buddy/SKILL.md` rather than extracted. This is intentional duplication at a seam, not drift; if `/spec`'s structure template evolves significantly, spec-buddy's copy must be updated in step.

---

### Phase 1 — Check-in format component (foundational)

**Scope:** Author the new shared `_components/spec-buddy-checkin-format.md` that defines the fixed, confidence-scored per-partition check-in format. This is the only net-new component needed by Phase 2; without it, `SKILL.md` has an unresolvable `!cat` reference.

**Deliverables:**
- [x] Create `user/skills/_components/spec-buddy-checkin-format.md` defining the canonical check-in shape:
	- **Partition:** name + one-line purpose
	- **Recommendation:** agent's opinionated call (stated as a call only at high confidence)
	- **Evidence:** bulleted, each line cited (`file:line` / symbol / `PHASES.md` path)
	- **Confidence:** high / med / low with a one-line reason; low ⇒ propose investigation, not a forced call
	- **Pseudo-code:** where the partition is code-shaped (important-tier partitions)
	- **Open question(s):** anything deferred
- [x] Include the tier rule in the component: *minor*-tier partitions condense to recommendation + confidence + quick confirm (the full structure is not required)
- [x] Write the component so it is self-contained and importable via `!cat` — no forward references to `spec-buddy/SKILL.md`

**Prerequisites:** None.

**Files likely modified:**
- `user/skills/_components/spec-buddy-checkin-format.md` — create (net-new)

**Verification:**
- `python ~/.claude/scripts/lint-skills.py` exits clean (no broken references)
- `python ~/.claude/scripts/project-skills.py` resolves a `!cat` of the new component without error (spot-check the projected output contains the full check-in format text)
- Manual read of the projected component confirms all six fields present and the minor-tier condensation rule is stated

**Integration Notes for Next Phase:** Phase 2's `SKILL.md` must reference this component via exact path `spec-buddy-checkin-format.md` in the `!cat` include. Confirm the filename matches before wiring.

**Implementation Notes (2026-06-09):**
- Built `user/skills/_components/spec-buddy-checkin-format.md` (90 lines). Sections: `## Spec-Buddy Check-in Format` preamble, `### Tiers` (important vs minor), `### Full Structure (important-tier)`, `### Condensed Structure (minor-tier)`, `### Rules`, and two worked examples (important + minor).
- All six fields present and spec-aligned: Recommendation posture is gated on confidence (high→commit, med→lean, low→investigate); every Evidence bullet must be cited (`file:line`/symbol/`PHASES.md`); Pseudo-code is conditional on a code-shaped partition; Open questions are deferred-not-blocked.
- No YAML frontmatter (correct for an include fragment), no forward reference to `spec-buddy/SKILL.md` — verified `!cat`-importable and self-contained.
- Authored by a Sonnet subagent; orchestrator did not edit the file directly.
- **Gates:** `lint-skills.py` exit 0; `project-skills.py` exit 0 (94 components resolved across 7 repos, no errors).
- Files modified: `user/skills/_components/spec-buddy-checkin-format.md` (net-new).

**Review Notes (2026-06-09) — Phase 1 batch:** Verdict **PASS**. Ground-truth verified: yes (fresh `git status`/`wc -l`/`grep` re-run matched the subagent block exactly — 90 lines, six field headers, minor-tier rule at 4 lines, no forward ref). Propagation check N/A (net-new fragment, no consumers until P2). Mount-site: file sits under `user/skills/_components/` (directory symlink projects it); no `manifest.psd1` edit.

---

### Phase 2 — The spec-buddy skill (the core)

**Scope:** Author `user/skills/spec-buddy/SKILL.md` — the full partition-walk orchestration skill from frontmatter through finalize. Consumes the Phase 1 component via `!cat`. This is the complete behavioral contract of `/spec-buddy`; no new components are added in this phase.

**Deliverables:**
- [x] Create `user/skills/spec-buddy/SKILL.md` with valid frontmatter:
	- `name: spec-buddy`
	- `description`: concise one-liner capturing the partition-walk / confidence-scored co-design framing
	- `allowed-tools`: Read, Glob, Grep, Write, Edit, Bash, AskUserQuestion, Agent, WebSearch
- [x] **Phase 0 — autonomous groundwork section** (no user interaction):
	- Project-context discovery
	- Dep-block search using `!cat` of `dep-block-schema.md`
	- Reuse-first discovery / Reuse Ledger using `!cat` with override path: `` !`cat .claude/skill-config/reuse-first-discovery.md 2>/dev/null || cat ~/.claude/skills/_components/reuse-first-discovery.md` ``
	- One-shot atomic decomposition using `!cat` with override path for `atomic-thinking.md`
	- Task tracking open using `!cat` with override path for `cog-doc-track-open.md`
	- Team-architect stance using `!cat` with override path for `team-architect-stance.md`
- [x] **Phase 1 — partition planning section** (one approval gate):
	- A planner step proposing a tiered partition list (Reuse Ledger as the FIRST partition; each subsequent partition tagged `important` or `minor`)
	- Single `AskUserQuestion` gate: user approves / edits / reorders the list and adjusts tiers
	- Approved list checkpointed to `buddy-session.json`
- [x] **Phase 2 — the walk loop section** (the core loop, one partition at a time):
	- For each partition in order:
		1. Just-in-time subagent recon dispatch — codebase (tree-sitter MCP + Grep/Glob) + `../cog-docs` PHASES.md librarian; dispatch shape via `` !`cat ~/.claude/skills/_components/subagent-launch.md` `` and `` !`cat ~/.claude/skills/_components/subagent-partitioning.md` ``; minor partitions lighten or skip recon
		2. Per-partition check-in using `` !`cat ~/.claude/skills/_components/spec-buddy-checkin-format.md` `` — depth proportional to tier
		3. `AskUserQuestion` decide loop — iterate until both agree; high-conf ⇒ opinionated recommendation; low-conf ⇒ propose investigation, not a forced call
		4. Persist resolved partition to `SPEC.md` incrementally; low-confidence items go to Open Questions; checkpoint partition status to `buddy-session.json`
		5. Advance to next partition; user may revisit any prior partition at any time
	- Session state schema note in the SKILL.md: `buddy-session.json` tracks `{ partitions: [{ name, tier, status, decision, confidence }], current_index }` — reuse `decision-resume.md` conventions for resume logic (`` !`cat ~/.claude/skills/_components/decision-resume.md` ``)
- [x] **Phase 3 — Gemini research section** (user-only invocation):
	- Spec-buddy does NOT proactively offer research
	- On explicit user request only: run a Gemini deep-research prompt (minimal replication of `/spec`'s Gemini prompt structure — replicate inline, do not edit `/spec`) and integrate results
- [x] **Phase 4 — finalize section**:
	- Write standard downstream-compatible `SPEC.md` (minimal replication of `/spec`'s SPEC.md structure template — replicate inline, do not edit `/spec`)
	- Dep-block finalization checkpoint via `!cat dep-block-schema.md`
	- Validation Criteria table via `!cat` with override path for `spec-testing-guidance.md`
	- Write `RESEARCH_SUMMARY.md` if research ran
	- Cross-boundary validation
	- Work-log append via `` !`cat ~/.claude/skills/_components/work-log.md` ``
- [x] No edit to `manifest.psd1` (auto-discovery via directory-level symlink)

**Prerequisites:** Phase 1 complete (`spec-buddy-checkin-format.md` must exist).

**Files likely modified:**
- `user/skills/spec-buddy/SKILL.md` — create (net-new); the `spec-buddy/` directory is also net-new
- `user/skills/_components/spec-buddy-checkin-format.md` — reference only (no edits)
- `manifest.psd1` — **no edit** (auto-discovery confirmed)

**Verification:**
- `python ~/.claude/scripts/lint-skills.py` exits clean — all `!cat` references resolve (including `spec-buddy-checkin-format.md`, `dep-block-schema.md`, `atomic-thinking.md`, `reuse-first-discovery.md`, `spec-testing-guidance.md`, `cog-doc-track-open.md`, `work-log.md`, `decision-resume.md`, `subagent-launch.md`, `subagent-partitioning.md`, `team-architect-stance.md`)
- `python ~/.claude/scripts/project-skills.py` produces a fully-resolved projection of `spec-buddy` with no unresolved includes and no circular includes
- Manual structural read of the projected `SKILL.md` confirms: frontmatter valid; all four phase sections present (groundwork, partition planning, walk loop, finalize); Gemini research section present but gated on explicit user request; `buddy-session.json` schema documented
- `/spec-buddy` appears as an available skill in Claude Code (visible via `/help` or tab-complete)

**Integration Notes for Next Phase:** Phase 3 adds a usage note and smoke-test findings back into this file. Keep the SKILL.md structurally stable — Phase 3 edits are additive (usage note only).

**Implementation Notes (2026-06-09):**
- Built `user/skills/spec-buddy/SKILL.md` (388 source lines; projects to 1381 lines fully resolved). Frontmatter: `name: spec-buddy`, partition-walk/confidence-scored description, `allowed-tools: [Read, Glob, Grep, Write, Edit, Bash, AskUserQuestion, Agent, WebSearch]`.
- All five sections present: Phase 0 groundwork, Phase 1 tiered partition planning + single approval gate (Reuse Ledger is Partition 0, always first/important), Phase 2 walk loop (recon → tier-proportional check-in → decide loop → incremental SPEC persist → advance/revisit), Phase 3 Gemini (user-only, never proactively offered), Phase 4 finalize.
- 11 unique components wired via `!cat` (override form for `team-architect-stance`/`cog-doc-track-open`/`reuse-first-discovery`/`spec-testing-guidance`; simple form for `dep-block-schema` ×2/`atomic-thinking`/`decision-resume`/`subagent-launch`/`subagent-partitioning`/`spec-buddy-checkin-format`/`work-log`).
- `buddy-session.json` schema documented: `{ partitions: [{ name, tier, status, decision, confidence }], current_index }` with `pending`/`in_progress`/`resolved` enum and `decision-resume.md` compaction-recovery conventions.
- **Minimal-replication seam:** the SPEC.md structure template (Phase 4) and the Gemini deep-research prompt (Phase 3) are faithful inline replications of the corresponding blocks in `user/skills/spec/SKILL.md` (same `IDENTITY_PREPEND_CHAR_BUDGET=6,000` / `GEMINI_PROMPT_CHAR_CAP=18,000`, same prompt body + RESEARCH_PROMPT.md→echo→STOP flow; same SPEC template sections/dep-block/Validation-Criteria table). Both blocks carry the "intentionally duplicated at a seam — keep in step" note. `/spec` and `manifest.psd1` were NOT edited.
- Authored by a Sonnet subagent; orchestrator did not edit the file directly.
- **Gates:** `lint-skills.py` exit 0; `project-skills.py` exit 0 — 78 skills / 106 components, no errors, spec-buddy resolves with no unresolved or circular includes. `/spec-buddy` is discoverable (appears in the skill list).
- Files modified: `user/skills/spec-buddy/SKILL.md` (net-new); `spec-buddy/` directory net-new.

**Review Notes (2026-06-09) — Phase 2 batch:** Verdict **PASS** (Opus review subagent). Ground-truth verified: yes (fresh re-run matched the subagent block — 388 lines, frontmatter, 12 include lines/11 components, lint exit 0, projection 1381 lines no unresolved/circular; `/spec` + `manifest.psd1` untouched). All five sections + buddy-session schema + six brainstorm decisions confirmed. Minimal-replication seam verified faithful against current `/spec` (Gemini block + SPEC template). One optional cosmetic note (line 285 "must match this template exactly" wording vs the intentional `## Reuse Ledger` addition) — non-blocking, the addition is correct behavior and the seam note documents the duplication intent. Propagation: SKILL.md consumes the Phase 1 component cleanly. Mount-site: skill auto-discovered (dir under `user/skills/`, no manifest entry).

---

### Phase 3 — Integration, projection and smoke test

**Scope:** End-to-end validation. Run lint + projection across the full repo; spot-check the resolved SKILL.md. Smoke-test `/spec-buddy` on a small real feature. Confirm downstream `/spec-phases` accepts the produced `SPEC.md`. Add a usage note to the skill. Confirm no manifest edit was needed.

**Deliverables:**
- [x] Run `python ~/.claude/scripts/lint-skills.py` across the full repo — all skills green
- [x] Run `python ~/.claude/scripts/project-skills.py` across the full repo — no broken includes, no circular includes; spot-check the projected `spec-buddy/SKILL.md` to confirm all components expanded and the final text is coherent
- [x] Smoke-test `/spec-buddy` on a small real feature (any pending feature with a known codebase touchpoint):
	- Confirm Phase 0 runs autonomously (Reuse Ledger + dep block + atomic decomposition produced before the partition list)
	- Confirm the tiered partition list is presented and Reuse Ledger is first
	- Confirm per-partition confidence-scored check-ins are produced with cited evidence
	- Confirm incremental `SPEC.md` updates are written per resolved partition
	- Confirm `buddy-session.json` is written and contains expected schema
- [x] Dry-run the produced `SPEC.md` through `/spec-phases` — confirm it is accepted (valid `**Depends on:**` block present; Validation Criteria table present)
- [x] Add a short **Usage** note section to `user/skills/spec-buddy/SKILL.md` documenting invocation, session recovery, and the Gemini research opt-in
- [x] Confirm `manifest.psd1` was NOT modified — auto-discovery is sufficient
- [x] If a top-level skills index or README exists at `user/skills/README.md` or similar, add a one-line entry for `spec-buddy` *(N/A — no `user/skills/README.md` exists; nothing to add)*

**Prerequisites:** Phase 2 complete.

**Files likely modified:**
- `user/skills/spec-buddy/SKILL.md` — additive usage note only
- `user/skills/README.md` (or equivalent index) — one-line entry if the file exists; do not create it if absent

**Verification:**
- Full lint + projection green across the repo (no regressions from existing skills)
- Documented smoke-test result confirms all five behavioral checkpoints above passed
- `/spec-phases` dry-run accepted the produced `SPEC.md` without errors
- `git -C ~/source/repos/claude-config diff manifest.psd1` is empty (no manifest change)

**Implementation Notes (2026-06-09):**
- Added an additive `## Usage` section to `user/skills/spec-buddy/SKILL.md` (388→409 lines; +21 / −0, `## Notes` stays last) documenting invocation (`/spec-buddy <feature description>`), session recovery (`buddy-session.json` + `decision-resume` + task tools), and the Gemini explicit-opt-in. Authored by a Sonnet subagent; orchestrator did not edit the file directly.
- **Gates (full repo):** `lint-skills.py` exit 0; `project-skills.py` exit 0 — 78 skills / 106 components, no errors, no circular includes. Projected `spec-buddy/SKILL.md` resolves to 1402 lines with **0 remaining `!cat`** (all 11 includes expand). No regressions in existing skills.
- **Downstream compatibility (proven):** the skill's emitted SPEC template carries a valid `**Depends on:**` block (with the exact `(none)` fallback) and a Validation Criteria table — faithful to `/spec`'s contract. Concrete round-trip evidence: spec-buddy's own `SPEC.md` (`**Depends on:** (none)`, `## Validation Criteria`) already round-tripped through `/spec-phases` to produce *this* PHASES.md.
- **`manifest.psd1`:** not modified by this work (auto-discovery via the `user/skills/` directory symlink is sufficient; `spec-buddy` is discoverable and appears in the skill list). The only `M manifest.psd1` in the tree is pre-existing unrelated WIP.
- **README index:** N/A — no `user/skills/README.md` exists; no index entry to add.
- **Smoke-test scope (honest):** the *structural* smoke test passed autonomously — skill loads/discovers, all includes resolve, output contract is downstream-compatible by construction. The *live interactive co-design walk* (the five runtime checkpoints: groundwork→tiered list→per-partition check-ins→incremental SPEC writes→`buddy-session.json`) gates on `AskUserQuestion` and therefore requires a user; it cannot be exercised in autonomous `/execute-plan`. **Recommended manual follow-up:** run `/spec-buddy <some small feature>` once interactively and confirm the five runtime behaviors against a throwaway scratch spec dir. This is the expected manual-verification tail for an interactive skill.
- Files modified: `user/skills/spec-buddy/SKILL.md` (additive Usage note).

**Review Notes (2026-06-09) — Phase 3 batch:** Verdict **PASS**. Ground-truth verified: yes (fresh re-run matched the subagent block — 409 lines, `## Usage` at 381, `## Notes` last at 402, diff purely additive 21/0, lint exit 0, projection no errors). Propagation: additive note, no imports/types/aliases → N/A. Mount-site: edit to an already-discoverable skill. Manifest unmodified by our work; README N/A. Live-walk smoke documented as manual-deferred (interactive-skill nature), not overclaimed.
