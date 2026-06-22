# Implementation Phases — MCP Tooling Not Predetermined at Planning

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress — all 4 phases implemented (P1–P4 done); validation tail (`/mcp-test` → `__mark_fixed__`) is orchestrator-owned and pending. Do NOT set Fixed / write FIXED.md here.

**MCP runtime:** not-required — this is a harness-defect fix entirely in skill/component markdown + per-repo skill-config docs (`docs-only` class per `docs/features/mcp-testing/SPEC.md`); no AlgoBooth app surface, store, or audio path is modified, so nothing here is MCP-reachable. The behavior is verified by re-running the (shared, deterministic) capability-audit prose against a seeded missing-tool case and by the existing `lint-skills.py` / `project-skills.py` checks, not by a Tauri+MCP runtime.

## Resolved Open Questions (from SPEC, resolvable in /plan-bug)

Both SPEC `## Open Questions` were marked "Resolvable in `/plan-bug`" and differ only in implementation completeness/fidelity (scope-class, not product-class). Resolved here:

- ⚖ policy: catalog enumeration fidelity → grep live registrations (no generated manifest). A grep over `scripts/mcp-test/tool-methods.ts` plus the Rust `inventory::submit!` registration sites is sufficient — it is the exact enumerate→grep pattern `phases-runtime-validation.md` already uses for SPEC-example capability audits, applied to a new catalog. A generated manifest is deferred (not needed; would add a build-order dependency for no fidelity gain since the registrations ARE the live surface). The per-repo catalog file names BOTH source paths so the audit greps the live registry, never a stale copy.
- ⚖ policy: auto-authored build-phase fidelity → name + decision + stub deliverable (shape deferred to /execute-plan). On a missing-tool miss the audit auto-authors a phase that names the required tool, cites the SPEC Locked Decision driving the requirement, and emits a stub `- [ ]` deliverable ("register MCP tool `X` exposing `<surface>`"). Full tool implementation shape (signature, handler, field paths) is left for `/execute-plan` — the harness predetermines existence and schedules the build up front; it does not pre-design the tool.

## Cross-feature Integration Notes

- This bug extends the planning-time capability-audit seam shipped by `docs/features/unified-pipeline-orchestrator/` (the `lazy-state.py --gate-coverage` completion gate) — but moves the MCP-surface check to the FRONT of the pipeline (`/spec` capture + `/spec-phases` verify) so it gates before implementation, not at `__mark_complete__`. The completion gate is left as the assertion target (Phase 4): newly-captured tooling Locked Decisions become coverable by the existing `--gate-coverage` audit.

---

### Phase 1: Per-repo MCP tool catalog declaration

**Scope:** Introduce a per-repo skill-config file that declares WHERE a repo's live MCP tool surface is enumerated, so the shared (repo-agnostic) capability audit in `/spec-phases` can grep the right paths. The mechanism is shared-harness; only the catalog paths are repo-specific (Proven Finding 4). Precedent: `phases-runtime-validation.md` and `spec-testing-guidance.md` are already per-repo overridable via `.claude/skill-config/`.

**Deliverables:**
- [x] New `repos/algobooth/.claude/skill-config/mcp-tool-catalog.md` naming the live-registry source paths: `scripts/mcp-test/tool-methods.ts` (TS tool-method registrations) and the Rust `inventory::submit!` registration sites. Documents the grep contract (how the audit derives the registered-tool-name set from each path) and the one-row-per-tool ledger format the audit consumes.
- [x] A "catalog absent → audit is a no-op" note in the file's header (repos without this file get no MCP-existence audit — the audit degrades to skip, never errors), mirroring how `phases-runtime-validation.md`'s gate skips when no source is configured.
- [x] Tests: none (declarative per-repo config doc). Verified by Phase 2's audit consuming it.

**Status:** Done — `repos/algobooth/.claude/skill-config/mcp-tool-catalog.md` authored.

#### Implementation Notes (Phase 1 — 2026-06-22)
- Authored `repos/algobooth/.claude/skill-config/mcp-tool-catalog.md`. Names two live-registry source paths: (1) `scripts/mcp-test/tool-methods.ts` (TS tool-name→method map), (2) `src-tauri/src/ipc/mcp/registrations/` (Rust `inventory::submit!` sites, entrypoint `mod.rs`). Documents the grep contract + one-row-per-tool ledger (`tool-name | registered? | source file:line`) and the catalog-absent → no-op header note.
- **Path provenance:** the AlgoBooth working tree is NOT checked out on this authoring machine, so the `[VERIFY]` greps could not run against the live tree. The two paths are the proven sites from SPEC Proven Finding 4, corroborated in-repo by `repos/algobooth/.claude/skills/mcp-test/SKILL.md` (`tool-methods.ts` map + `inventory::submit!` compile-time registration) and `repos/algobooth/.claude/skill-config/{investigation-runtime,phases-runtime-validation}.md` (`src-tauri/src/ipc/mcp/registrations/`). The catalog carries an explicit path-resolution note instructing the audit to confirm/record the ACTUAL resolved path in the live tree and never invent one — so this is NOT the "registry path cannot be located" blocker (the path is proven, just not greppable on this machine).
- **Review verdict:** PASS — traces to SPEC `## Affected Area` "Repo tool catalog" row + Proven Finding 4 + Resolved Open Question 1; no gate-owned rows. Lint + projection green.

**Minimum Verifiable Behavior:** The file exists at the declared path and the two registry source paths it names resolve to real files in the AlgoBooth repo (`scripts/mcp-test/tool-methods.ts` + the Rust registration site) — confirmable by reading the catalog and checking each named path is a real, greppable source of tool-name registrations.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `repos/algobooth/.claude/skill-config/mcp-tool-catalog.md` — new per-repo catalog (the only repo with an MCP surface today).

**Testing Strategy:** Structural — the file is a config doc consumed by Phase 2. Confirm the named registry paths exist in the AlgoBooth repo so the Phase 2 grep has a real target.

**Integration Notes for Next Phase:**
- Phase 2's audit reads this catalog via the standard `cat .claude/skill-config/mcp-tool-catalog.md 2>/dev/null || <skip>` injection pattern (so it is a no-op outside repos that configure it).
- The catalog enumerates EXISTING tool names; Phase 2 compares the SPEC's REQUIRED tool names against this set and auto-authors a build phase for any miss.

---

### Phase 2: Extend the /spec-phases capability audit to enumerate + verify MCP tools, auto-authoring a build phase on a miss

**Scope:** Extend `user/skills/_components/phases-runtime-validation.md` (the SPEC-example capability audit injected at `/spec-phases` Step 2.7) to additionally enumerate the MCP tools the SPEC's validation will call, grep the Phase-1 per-repo catalog to verify each exists, and — on a miss — AUTO-AUTHOR a "build MCP tool X" phase/deliverable up front in PHASES.md (Locked Decision 2: auto-author is the default; NEEDS_INPUT only when the requirement is genuinely ambiguous). This is the same enumerate→grep→act pattern the component already runs for API surfaces, applied to the MCP-tool catalog. This is the primary fix (root cause: Theory 1 — planning has no MCP tool-existence guard).

**Deliverables:**
- [x] Add an "MCP tool-existence audit" subsection to `phases-runtime-validation.md`: enumerate the MCP tool names the SPEC's `## Validation Criteria` / `## Locked Decisions` (and AlgoBooth's `## Audio Quality Contracts` table where present) name; for each, grep the Phase-1 catalog's registry paths for the tool-name registration; record one ledger row per tool (`how-confirmed: grep`, citing file:line of the registration or the absence of hits).
- [x] On a miss (required tool not registered): AUTO-AUTHOR a build phase/deliverable up front in PHASES.md naming the tool, citing the driving SPEC decision, and emitting a stub `- [ ]` deliverable per the Q2 resolution above — NOT a late validation discovery, NOT a NEEDS_INPUT halt (auto-author is the default per Locked Decision 2).
- [x] NEEDS_INPUT fallback: reserve `NEEDS_INPUT.md` for the genuinely-ambiguous case (the required tool's surface/shape cannot be inferred from the SPEC) — the explicit fallback Locked Decision 2 carves out.
- [x] Catalog-absent degradation: when no `mcp-tool-catalog.md` is configured for the repo, the MCP-tool audit is a no-op (record the skip reason), exactly as the existing capability-audit gate skips when its source is unconfigured.
- [x] Tests: a seeded missing-tool walkthrough recorded inline in the component (a SPEC naming a tool absent from the catalog → audit produces an auto-authored build-phase row) as the worked example, mirroring the d8-live-looping motivating-incident example already in the component.

**Status:** Done — MCP tool-existence audit added to both the generic component and the AlgoBooth override; `/spec-phases` Step 2.7 prose updated.

#### Implementation Notes (Phase 2 — 2026-06-22)
- Added an "MCP tool-existence audit" block (enumerate → resolve catalog → grep → ledger → auto-author-on-miss → NEEDS_INPUT-only-if-ambiguous → catalog-absent no-op → seeded worked example) to BOTH `user/skills/_components/phases-runtime-validation.md` (generic) AND `repos/algobooth/.claude/skill-config/phases-runtime-validation.md` (AlgoBooth override). ⚖ policy: where to add MCP audit prose → BOTH files — the Step-2.7 injection is `cat .claude/skill-config/... || cat ~/.claude/skills/_components/...`, so the AlgoBooth override SHADOWS the generic component; adding only to the generic file would leave AlgoBooth (the one repo with an MCP surface + catalog) never running the audit. Scope-class completeness, disclosed.
- WU-3: `user/skills/spec-phases/SKILL.md` Step 2.7 intro prose gained a one-line mention that the gate now also runs the MCP tool-existence audit (component already injected at line ~186 — no re-wiring needed, light prose touch as the plan anticipated).
- Auto-authored row is explicitly a PLAIN build deliverable (no status flip / receipt) per the spec-phases "No gate-owned rows" discipline.
- **Review verdict:** PASS — traces to SPEC `## Affected Area` "Phase decomposition" row + Locked Decision 2 + Resolved Open Question 2; projection re-expands cleanly into the spec-phases consumer; lint green.

**Minimum Verifiable Behavior:** Running the extended audit prose against a seeded SPEC that names an MCP tool NOT in the catalog produces (a) a ledger row marking the tool absent and (b) an auto-authored "build MCP tool X" phase row in the drafted PHASES.md — verifiable by tracing the seeded example in the component against the Phase-1 catalog. A SPEC whose named tools all resolve produces a clean ledger with no auto-authored phase.

**Prerequisites:**
- Phase 1: the per-repo `mcp-tool-catalog.md` must exist for the audit to have registry paths to grep (absent → audit no-ops, so Phase 2 is still correct standalone, but the AlgoBooth end-to-end behavior needs Phase 1).

**Files likely modified:**
- `user/skills/_components/phases-runtime-validation.md` — add the MCP tool-existence audit subsection + auto-author rule + worked example.
- `user/skills/spec-phases/SKILL.md` — Step 2.7 prose pointer to the new audit behavior if the existing injection text needs to name the MCP-tool catalog (likely a one-line mention; the component is already injected at Step 2.7).

**Testing Strategy:** Structural + projection. Re-run `python ~/.claude/scripts/project-skills.py` and confirm the extended component expands cleanly into the `/spec-phases` projection (no broken `!cat` injections, no circular includes). Trace the seeded missing-tool example by hand against the Phase-1 catalog to confirm the auto-author path fires.

**Integration Notes for Next Phase:**
- The auto-authored build phase produced here is what eliminates the corrective loop (the 4 `adhoc-mcp-*` spin-offs + 1 in-feature corrective phase in the Evidence table). Phase 3 captures the requirement at `/spec` time so this Phase-2 verify has a named tool to check (defense-in-depth, Locked Decision 3 "Seam = both").
- The audit must NOT author gate-owned rows (status flips / receipt writes) — the auto-authored row is an ordinary build deliverable, per the spec-phases "No gate-owned rows" discipline.

---

### Phase 3: Capture required MCP tooling as a Locked Decision during /spec

**Scope:** Extend `/spec` (and AlgoBooth's `spec-testing-guidance.md` override) to capture the MCP tools a feature's validation will require AS a Locked Decision, so (a) the Phase-2 `/spec-phases` audit has a named requirement to verify, and (b) the existing completion-time `mcp-coverage-audit` / `--gate-coverage` gate can assert on it (Locked Decision 3: defense-in-depth across both skills). Today `/spec` names tools only as a fixed menu of EXISTING tools to assert against (Evidence: spec skill source); this adds an explicit "required tooling" capture that flags tools that must EXIST/be BUILT.

**Deliverables:**
- [x] Add a "required MCP tooling" capture step to `user/skills/spec/SKILL.md` (in/near `## Validation Criteria`): when a feature's validation will call MCP tools, enumerate them as a Locked Decision (so they land in the `## Locked Decisions` surface the coverage gate already parses).
- [x] Extend `repos/algobooth/.claude/skill-config/spec-testing-guidance.md` (the AlgoBooth `## Audio Quality Contracts` override) to record required-but-possibly-missing tools, not only the existing-tool menu.
- [x] Tests: none (skill-prose change). Verified by the captured Locked Decision being parseable by `--gate-coverage` (Phase 4) and consumable by the Phase-2 audit.

**Status:** Done — required-MCP-tooling capture added to `/spec` (`## Validation Criteria` → Locked Decision) and the AlgoBooth `spec-testing-guidance.md` override.

#### Implementation Notes (Phase 3 — 2026-06-22)
- `user/skills/spec/SKILL.md`: added a "Required MCP tooling (capture as a Locked Decision)" subsection right after the Validation Criteria table. It instructs capturing required-to-exist (possibly-missing) MCP tools as a `## Locked Decisions` table row in the EXACT gate-parseable shape (`| ID | Decision |`, first column = `L4`/title), with a worked example, and to omit it when validation calls no MCP tools.
- `repos/algobooth/.claude/skill-config/spec-testing-guidance.md`: extended the `## Audio Quality Contracts` block with a "Required-but-possibly-missing tooling" note distinguishing the existing-tool menu (the `Tool` column) from required-to-build tools captured as a Locked Decision.
- **Shape alignment:** the captured surface is the same `## Locked Decisions` H2 table that `mcp-coverage-audit.md` Step 1 (and `lazy-state.py --gate-coverage`) enumerates — no new section invented, so Phase 4's assertion works without parser changes.
- **Review verdict:** PASS — traces to Locked Decision 3 ("Seam = both") + SPEC `## Affected Area` "Spec authoring" row; projection + lint green.

**Minimum Verifiable Behavior:** A spec authored through the extended `/spec` prose lands a `## Locked Decisions` entry naming the required MCP tool(s) — verifiable by checking that entry is in the canonical Locked-Decision surface `lazy-state.py --gate-coverage` and the Phase-2 audit both parse (the same H2 the `mcp-coverage-audit` algorithm enumerates).

**Prerequisites:**
- Phase 2: defines what the captured decision feeds (the verify seam). Authoring the capture before the verify exists would capture data nothing consumes.

**Files likely modified:**
- `user/skills/spec/SKILL.md` — required-MCP-tooling capture near `## Validation Criteria`.
- `repos/algobooth/.claude/skill-config/spec-testing-guidance.md` — AlgoBooth override extension.

**Testing Strategy:** Structural + projection. Re-run `project-skills.py`; confirm the `/spec` projection (and the AlgoBooth-scoped projection) expand cleanly. Confirm the captured Locked-Decision shape matches the surface `mcp-coverage-audit.md` Step 1 enumerates (so Phase 4's assertion works).

**Integration Notes for Next Phase:**
- The Locked Decision captured here is the assertion TARGET Phase 4 verifies. Keep its shape aligned with the `## Locked Decisions` table/numbered-block format `mcp-coverage-audit.md` Step 1 already parses — do NOT invent a new section the gate can't see.

---

### Phase 4: Wire newly-captured tooling decisions as assertable completion coverage + docs

**Scope:** Close the defense-in-depth loop (Locked Decision 3): ensure the required-MCP-tooling Locked Decisions captured in Phase 3 are picked up by the existing completion-time coverage gate (`user/skills/_components/mcp-coverage-audit.md` + `lazy-state.py --gate-coverage`) as assertable coverage, and update the harness docs (`CLAUDE.md` component descriptions + the bug's reverse-reference). No new gate logic is needed if Phase 3 lands the decision in the canonical surface the gate already parses — this phase CONFIRMS that and documents the now-two-seam contract.

**Deliverables:**
- [x] Confirm (and, if the surface shape needs a note, document in `mcp-coverage-audit.md`) that a required-MCP-tooling Locked Decision captured per Phase 3 is enumerated by the `--gate-coverage` algorithm — so the completion gate asserts the tool's scenario coverage. Add a one-line note to `mcp-coverage-audit.md` cross-referencing the new planning-time predetermination seam (this bug) as the upstream that makes such decisions exist.
- [x] Update `CLAUDE.md` (repo root) component descriptions where they describe `phases-runtime-validation.md` / the MCP seams, so the layout doc reflects the new planning-time MCP tool-existence audit.
- [x] Reverse-reference: add an Implementation Notes line to this PHASES.md (or SPEC `## Related`) confirming no spin-off legs were created (all work is in-scope harness edits) — see Implementation Notes below.
- [x] Tests: `lint-skills.py --check-projected --check-capabilities` passes; `project-skills.py` re-projects cleanly across `_default/` and the AlgoBooth projection.

**Status:** Done — no algorithm change needed (the Phase-3 capture is an ordinary `## Locked Decisions` row the gate already parses); cross-reference note added to `mcp-coverage-audit.md`; root `CLAUDE.md` component descriptions updated.

#### Implementation Notes (Phase 4 — 2026-06-22)
- Confirmed `mcp-coverage-audit.md` Step 1 already enumerates a `## Locked Decisions` H2 table (first column = ID / one-line title) — the EXACT shape Phase 3 captures the required-MCP-tooling decision in. NO `--gate-coverage` / `lazy_core.gate_coverage` algorithm change is needed; the new decision is recognized as an ordinary Locked Decision.
- Added a "Planning-time predetermination seam" cross-reference blockquote to `user/skills/_components/mcp-coverage-audit.md` naming this bug as the upstream and describing the two-seam (planning-time auto-author / completion-time assert) defense-in-depth contract.
- Updated root `CLAUDE.md` `**Key components:**` list: added a `phases-runtime-validation.md` entry (the new planning-time MCP tool-existence audit + the per-repo `mcp-tool-catalog.md` registry) and extended the `mcp-coverage-audit.md` entry with the completion-time-half cross-reference.
- **No spin-off legs** — all work is in-scope harness markdown edits (already noted in the global Implementation Notes block above); both reverse-reference directions are N/A.
- **Review verdict:** PASS — traces to Locked Decision 3 + SPEC `## Affected Area` "Completion gate" row; final lint + projection green.

**Minimum Verifiable Behavior:** `python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities` exits clean after all edits, and a required-MCP-tooling Locked Decision (Phase 3 shape) traced through the `mcp-coverage-audit.md` Step 1 enumeration is recognized as a decision (so the completion gate will assert on it) — confirming both the planning-time (Phase 2) and completion-time (this phase) seams cover the same requirement.

**Prerequisites:**
- Phase 2 (verify seam) and Phase 3 (capture seam) both landed — this phase confirms they compose with the existing completion gate and documents the contract.

**Files likely modified:**
- `user/skills/_components/mcp-coverage-audit.md` — cross-reference note (no algorithm change expected).
- `CLAUDE.md` (repo root) — component-description updates for the new MCP planning seam.

**Testing Strategy:** Run the harness lint + projection scripts as the gate. Trace one required-MCP-tooling decision end-to-end (captured at `/spec` → verified at `/spec-phases` → asserted at `__mark_complete__`) to confirm the two seams cover the same requirement without divergence.

**Integration Notes for Next Phase:**
- Final phase. When this phase's work lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) and let the state machine route to the validation tail. The terminal Fixed flip + FIXED.md receipt are orchestrator-owned (`__mark_fixed__` gate) — never written here.

---

## Implementation Notes

- **No spin-off legs.** All work is in-scope harness edits (skill/component markdown + AlgoBooth skill-config). No bug doc or `--enqueue-adhoc` feature was spun off; both reverse-reference directions are therefore N/A for this plan.
- **Coupled-pair check (for /execute-plan):** Phase 2 edits `phases-runtime-validation.md`, a shared component injected into `/spec-phases` Step 2.7 — re-run `project-skills.py` after editing so both `_default/` and the AlgoBooth projection pick up the change. No `/lazy` ↔ `/lazy-cloud` or `/lazy-batch` ↔ `/lazy-batch-cloud` coupled-pair files are touched.
- **Seam = both (Locked Decision 3):** the capture (Phase 3, `/spec`) and the verify+auto-author (Phase 2, `/spec-phases`) are intentionally redundant — defense-in-depth. Do NOT collapse them into one seam during execution.
