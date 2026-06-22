# MCP Tooling Not Predetermined at Planning — Investigation Spec

> The lazy feature pipeline never enumerates the MCP tool surface a feature's own `/mcp-test` scenario will call, so a missing tool is only discovered at Step 9 (pipeline end) — after full planning and implementation — forcing a corrective add-phase or `adhoc-mcp-*` spin-off and 3–6 wasted Step-9 cycles.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-22
**Fixed:** 2026-06-22
**Fix commit:** 273dd95
**Placement:** docs/bugs/mcp-tooling-not-predetermined-at-planning
**Related:** `user/skills/_components/mcp-coverage-audit.md` (the post-implementation completion gate — the symptom, not the fix); `docs/features/unified-pipeline-orchestrator/` (shipped `lazy-state.py --gate-coverage`); `user/skills/spec-phases/SKILL.md` Step 2.7 + `user/skills/_components/phases-runtime-validation.md` (the existing capability-audit seam this fix extends)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
  Root cause is proven below and the design forks are locked (see Locked Decisions), so this
  spec is Concluded and ready for /plan-bug.
-->

---

## Verified Symptoms

1. **[VERIFIED]** A feature plans and implements cleanly, then `/mcp-test` (Step 9) cannot certify because the MCP tool surface its scenario needs does not exist — confirmed by the user's lived experience across AlgoBooth `/lazy-batch` runs and corroborated by 5 distinct on-disk cases (see Evidence).
2. **[VERIFIED]** The failure triggers corrective rework — either an in-feature corrective phase (`**Phase kind:** corrective`) or a spun-off `adhoc-mcp-*` feature that dependency-gates the original — not a clean completion. Confirmed by the user and the on-disk resolution artifacts.
3. **[VERIFIED]** Planning today does not predetermine the required MCP tooling — the user's stated goal is to have planning predetermine it and avoid the corrective phase entirely.
4. **[VERIFIED]** The loop is costly: f5-slip-mode and foot-switch-injectors each looped 3–6 Step-9 cycles (hitting the `step_repeat_count` / `retry_count` oscillation tripwires) before the missing-surface gap was even named.

## Reproduction Steps

1. Enqueue an AlgoBooth feature whose validation scenario must call an MCP tool that is not yet registered in the AlgoBooth tool surface (e.g. a new substrate/store with no control-tier tools).
2. Run `/lazy-batch`. The feature passes `/spec` → `/plan-feature` → `/execute-plan` with no MCP-tooling check.
3. At Step 9 `/mcp-test`, the deterministic engine's pre-flight field-path dry-run cannot resolve the assertion against the absent tool → `harness` miss / Gate-2 `genuine` → `BLOCKED.md` with `blocker_kind: missing-mcp-surface` (or `mcp-validation`).

**Expected:** Planning enumerates the MCP tools the feature's validation will require, verifies each exists, and — when one is missing — auto-authors a "build MCP tool X" phase up front so the tool lands before `/mcp-test`.
**Actual:** Tool absence is discovered only at Step 9, after full implementation, and is bolted on via a corrective add-phase or `adhoc-mcp-*` spin-off.
**Consistency:** Consistent — 5 distinct features in a single ~10-day window; the harness has institutionalized the reaction as completeness-policy D7 ("Add a phase to resolve the blocker").

## Evidence Collected

### Runtime / Session Evidence (5 distinct features, June 2026 AlgoBooth `/lazy-batch` runs)

| Feature | Missing MCP surface | Corrective response | Source artifact |
|---------|--------------------|--------------------|-----------------|
| `d8-effect-chains` (06-15) | `load_ir_library` (no IR-load tool in the 216-tool surface) | spun off `adhoc-mcp-load-ir-library` | `…/d8-effect-chains/NEEDS_INPUT_RESOLVED_2026-06-15.md:23` |
| `mcp-audio-quality-observability` (06-16) | runner cross-step `capture_id` interpolation | spun off `adhoc-mcp-runner-payload-interpolation`; held PARTIAL | `…/mcp-audio-quality-observability/BLOCKED_RESOLVED_2026-06-16.md:20` |
| `f5-slip-mode` (06-20) | `add_midi_mapping_pad` + MCP-registered `set_slip_pad_template` (`blocker_kind: missing-mcp-surface`) | spun off `adhoc-mcp-slip-pad-binding-tools`, hard `Depends on:` | `…/f5-slip-mode/MCP_TEST_RESULTS.md:26-35`, `BLOCKED_RESOLVED_2026-06-20.md:7` |
| `change-queue` (06-21) | `scene_create/_add_item/_arm/_fire`, `get_scene_state` (no MCP surface for `scenesStore`) | **in-feature corrective Phase 6** (`plans/phase-6-scene-mcp-tools.md`) — the textbook case | `…/change-queue/BLOCKED_RESOLVED_2026-06-20.md:12,92-115` |
| `foot-switch-injectors` (06-13→17) | engine `TransactionIdCounter` reset + staged-swap MCP wiring | spun off bug + requeue (partly a real tx-id race) | `…/foot-switch-injectors/BLOCKED.md:118-120,204` |

Totals: **4 `adhoc-mcp-*` spin-offs + 1 in-feature corrective phase + 1 spun-off bug.** Provenance in session JSONL `3b08f4e8-797c-433a-bbdc-7182f9db1eff.jsonl` and `180f2a40-c64b-4d69-9951-2dcf991c388e.jsonl` under `C:\Users\Jacob\.claude\projects\C--Users-Jacob-repos-AlgoBooth\`.

Representative failure quote (`change-queue`): *"MCP validation is blocked because no MCP surface exists for the `scenesStore` substrate… none of these entry points are reachable from the MCP control tier."* Resolution: *"Chosen path: Add a phase to resolve the blocker. resolved_by: completeness-policy… a new Phase 6, Phase kind: corrective… Build Seam A — scene-management MCP tools… then re-run `/mcp-test change-queue`."*

### Source Code (current pipeline — where MCP tooling is determined)

- **`user/skills/_components/mcp-coverage-audit.md`** — gates `__mark_complete__`/`__mark_fixed__` at **completion time**. Enumerates SPEC `## Locked Decisions` and greps `mcp-tests/*.md` to confirm each decision is covered by a *scenario*. Audits **scenario↔decision coverage, NOT tool existence** — a scenario can "cover" a decision in text while the tool it calls is unregistered. Deterministic verdict via `lazy-state.py --gate-coverage <spec>`. Runs *after* implementation; cannot prevent the late discovery.
- **`user/skills/spec-phases/SKILL.md`** — has an `**MCP runtime:** required | not-required` header (a **routing flag**, "not a waiver"), per-phase assertion authoring, and sentinel triage. **Closest existing analog**: Step 2.7 injects `phases-runtime-validation.md`'s SPEC-example capability audit, which already enumerates "every API surface, source type, method… the SPEC's code examples consume," runs a negative-evidence grep for explicit rejection, and **halts at planning time** on an unsupported capability. The reachability-smoke rule acknowledges a phase may *introduce* a new MCP tool — but it schedules a runtime smoke at implementation time; it never predetermines that an *existing required* tool is present or that a *missing* one must be built up front.
- **`user/skills/plan-feature/SKILL.md`** — pure dispatch glue (`/spec-phases` + `/write-plan`); no MCP-tool enumeration.
- **`user/skills/spec/SKILL.md`** — captures MCP behavior in `## Validation Criteria`; the AlgoBooth `spec-testing-guidance.md` override adds an `## Audio Quality Contracts` table naming specific audio tools. **This is the only place tools are enumerated by name during planning — but as a fixed menu of *existing* tools to assert against, not a check that required tooling exists / needs building.**
- **`repos/algobooth/.claude/skills/mcp-test/SKILL.md`** — where absence is *actually* discovered: pre-flight field-path dry-run → unresolvable path = `harness` miss; self-heal is mechanics-only (casing/field drift), so a genuinely absent tool is not self-healable → `NEEDS_INPUT.md`/BLOCKED. Step 6 even says to "note [a missing MCP tool] as a candidate for `/spec` or `/add-phase`" — explicit acknowledgement that absence is found *here* and kicked back to planning *after the fact*.
- **`user/skills/add-phase/SKILL.md`** — the corrective mechanism; tags the phase `**Phase kind:** corrective` for `blocker_kind: mcp-validation`. Its phase-count circuit-breaker (Step 2.5, fires at >+50% expansion) exists *because* repeated MCP-corrective add-phases blow up phase counts — direct evidence the loop is a known, costly pattern.

### Related Documentation

- No existing bug covers this. The two archived MCP bugs (`mcp-test-haiku-tier-unwired`, `mcp-test-legacy-md-routes-to-haiku`) are about *which model runs* mcp-test, not MCP-surface determination.
- `docs/features/unified-pipeline-orchestrator/` (COMPLETED) shipped the completion-time coverage gate — the near-miss machinery, but it fires at the wrong end of the pipeline.

## Theories

### Theory 1: Planning has no MCP tool-existence guard (root cause)
- **Hypothesis:** `/spec`, `/spec-phases`, and `/plan-feature` decide *whether* MCP validation is needed and *what to assert*, but never enumerate *which tools the assertions call* nor verify those tools exist. Tool existence is first checked at `/mcp-test` (Step 9), guaranteeing late discovery and corrective rework.
- **Supporting evidence:** Code analysis confirms no tool-existence check in any planning skill; all 5 evidence features failed at Step 9 with missing-surface blockers; the completion gate (`mcp-coverage-audit`) audits coverage, not existence.
- **Contradicting evidence:** None material. (`foot-switch-injectors` is partly a real production tx-id race, but its *validation gap* is still "the MCP surface to certify doesn't exist.")
- **Status:** Confirmed

## Proven Findings

1. **MCP tool existence is determined only at `/mcp-test` (pipeline end), not during planning.** Confirmed across all planning skills and the mcp-test skill.
2. **The completion-time coverage gate is the wrong seam** — it runs at `__mark_complete__` and audits scenario↔decision coverage, so it cannot prevent the late discovery.
3. **A correct planning-time seam already exists**: `/spec-phases` Step 2.7 / `phases-runtime-validation.md` runs an enumerate→grep→halt capability audit over SPEC code-example API surfaces. Extending it to MCP tools is the same pattern applied to a new catalog.
4. **The mechanism is shared-harness; the tool catalog is repo-specific.** AlgoBooth's registry lives in `scripts/mcp-test/tool-methods.ts` + Rust `inventory::submit!` registrations; the audit must grep a repo-supplied catalog path (precedent: `phases-runtime-validation.md` and `spec-testing-guidance.md` are already per-repo overridable).

## Locked Decisions

<!-- Confirmed with the user via AskUserQuestion, 2026-06-22. These constrain /plan-bug. -->

1. **Placement = bug.** Filed as a harness defect (late-discovery rework from a missing planning guard), per the mission's "friction observed in a run is a bug report against this repo." Routes to `/plan-bug`.
2. **On-detect behavior = auto-author the build phase.** When planning detects a required-but-missing MCP tool, the harness auto-inserts a "build MCP tool X" phase/deliverable up front in PHASES.md so the tool lands before `/mcp-test`, eliminating the corrective loop without operator intervention (fits the unattended `/lazy-batch` model). NEEDS_INPUT halt is the fallback only when the requirement is genuinely ambiguous, not the default.
3. **Seam = both.** Capture required MCP tooling as a Locked Decision during `/spec` (so the existing `mcp-coverage-audit` / `--gate-coverage` gate can assert on it), AND verify tool existence during `/spec-phases` (extend the Step 2.7 capability audit to grep the repo tool catalog and auto-author the build phase on a miss). Defense-in-depth across the two skills.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Spec authoring | `user/skills/spec/SKILL.md` (+ AlgoBooth `spec-testing-guidance.md`) | Capture required MCP tooling as a Locked Decision |
| Phase decomposition | `user/skills/spec-phases/SKILL.md` Step 2.7, `user/skills/_components/phases-runtime-validation.md` | Extend capability audit to enumerate + verify MCP tools; auto-author build phase on a miss |
| Repo tool catalog | `repos/algobooth/.claude/skill-config/` (new `mcp-tool-catalog.md` naming `scripts/mcp-test/tool-methods.ts` + Rust registry) | Per-repo registry paths the shared audit greps against |
| Completion gate (assertion target) | `user/skills/_components/mcp-coverage-audit.md`, `lazy-state.py --gate-coverage` | Newly-captured tooling decisions become assertable coverage |

## Open Questions

- Catalog enumeration fidelity: is a grep over `tool-methods.ts` + `inventory::submit!` sufficient to enumerate the live tool surface, or is a generated manifest needed? (Resolvable in `/plan-bug`.)
- Auto-authored build-phase content: how much can the harness specify the new tool's shape vs. leaving a stub deliverable for `/execute-plan`? (Resolvable in `/plan-bug`.)
