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
- [ ] Create `user/skills/spec-buddy/SKILL.md` with valid frontmatter:
	- `name: spec-buddy`
	- `description`: concise one-liner capturing the partition-walk / confidence-scored co-design framing
	- `allowed-tools`: Read, Glob, Grep, Write, Edit, Bash, AskUserQuestion, Agent, WebSearch
- [ ] **Phase 0 — autonomous groundwork section** (no user interaction):
	- Project-context discovery
	- Dep-block search using `!cat` of `dep-block-schema.md`
	- Reuse-first discovery / Reuse Ledger using `!cat` with override path: `` !`cat .claude/skill-config/reuse-first-discovery.md 2>/dev/null || cat ~/.claude/skills/_components/reuse-first-discovery.md` ``
	- One-shot atomic decomposition using `!cat` with override path for `atomic-thinking.md`
	- Task tracking open using `!cat` with override path for `cog-doc-track-open.md`
	- Team-architect stance using `!cat` with override path for `team-architect-stance.md`
- [ ] **Phase 1 — partition planning section** (one approval gate):
	- A planner step proposing a tiered partition list (Reuse Ledger as the FIRST partition; each subsequent partition tagged `important` or `minor`)
	- Single `AskUserQuestion` gate: user approves / edits / reorders the list and adjusts tiers
	- Approved list checkpointed to `buddy-session.json`
- [ ] **Phase 2 — the walk loop section** (the core loop, one partition at a time):
	- For each partition in order:
		1. Just-in-time subagent recon dispatch — codebase (tree-sitter MCP + Grep/Glob) + `../cog-docs` PHASES.md librarian; dispatch shape via `` !`cat ~/.claude/skills/_components/subagent-launch.md` `` and `` !`cat ~/.claude/skills/_components/subagent-partitioning.md` ``; minor partitions lighten or skip recon
		2. Per-partition check-in using `` !`cat ~/.claude/skills/_components/spec-buddy-checkin-format.md` `` — depth proportional to tier
		3. `AskUserQuestion` decide loop — iterate until both agree; high-conf ⇒ opinionated recommendation; low-conf ⇒ propose investigation, not a forced call
		4. Persist resolved partition to `SPEC.md` incrementally; low-confidence items go to Open Questions; checkpoint partition status to `buddy-session.json`
		5. Advance to next partition; user may revisit any prior partition at any time
	- Session state schema note in the SKILL.md: `buddy-session.json` tracks `{ partitions: [{ name, tier, status, decision, confidence }], current_index }` — reuse `decision-resume.md` conventions for resume logic (`` !`cat ~/.claude/skills/_components/decision-resume.md` ``)
- [ ] **Phase 3 — Gemini research section** (user-only invocation):
	- Spec-buddy does NOT proactively offer research
	- On explicit user request only: run a Gemini deep-research prompt (minimal replication of `/spec`'s Gemini prompt structure — replicate inline, do not edit `/spec`) and integrate results
- [ ] **Phase 4 — finalize section**:
	- Write standard downstream-compatible `SPEC.md` (minimal replication of `/spec`'s SPEC.md structure template — replicate inline, do not edit `/spec`)
	- Dep-block finalization checkpoint via `!cat dep-block-schema.md`
	- Validation Criteria table via `!cat` with override path for `spec-testing-guidance.md`
	- Write `RESEARCH_SUMMARY.md` if research ran
	- Cross-boundary validation
	- Work-log append via `` !`cat ~/.claude/skills/_components/work-log.md` ``
- [ ] No edit to `manifest.psd1` (auto-discovery via directory-level symlink)

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

---

### Phase 3 — Integration, projection and smoke test

**Scope:** End-to-end validation. Run lint + projection across the full repo; spot-check the resolved SKILL.md. Smoke-test `/spec-buddy` on a small real feature. Confirm downstream `/spec-phases` accepts the produced `SPEC.md`. Add a usage note to the skill. Confirm no manifest edit was needed.

**Deliverables:**
- [ ] Run `python ~/.claude/scripts/lint-skills.py` across the full repo — all skills green
- [ ] Run `python ~/.claude/scripts/project-skills.py` across the full repo — no broken includes, no circular includes; spot-check the projected `spec-buddy/SKILL.md` to confirm all components expanded and the final text is coherent
- [ ] Smoke-test `/spec-buddy` on a small real feature (any pending feature with a known codebase touchpoint):
	- Confirm Phase 0 runs autonomously (Reuse Ledger + dep block + atomic decomposition produced before the partition list)
	- Confirm the tiered partition list is presented and Reuse Ledger is first
	- Confirm per-partition confidence-scored check-ins are produced with cited evidence
	- Confirm incremental `SPEC.md` updates are written per resolved partition
	- Confirm `buddy-session.json` is written and contains expected schema
- [ ] Dry-run the produced `SPEC.md` through `/spec-phases` — confirm it is accepted (valid `**Depends on:**` block present; Validation Criteria table present)
- [ ] Add a short **Usage** note section to `user/skills/spec-buddy/SKILL.md` documenting invocation, session recovery, and the Gemini research opt-in
- [ ] Confirm `manifest.psd1` was NOT modified — auto-discovery is sufficient
- [ ] If a top-level skills index or README exists at `user/skills/README.md` or similar, add a one-line entry for `spec-buddy`

**Prerequisites:** Phase 2 complete.

**Files likely modified:**
- `user/skills/spec-buddy/SKILL.md` — additive usage note only
- `user/skills/README.md` (or equivalent index) — one-line entry if the file exists; do not create it if absent

**Verification:**
- Full lint + projection green across the repo (no regressions from existing skills)
- Documented smoke-test result confirms all five behavioral checkpoints above passed
- `/spec-phases` dry-run accepted the produced `SPEC.md` without errors
- `git -C ~/source/repos/claude-config diff manifest.psd1` is empty (no manifest change)
