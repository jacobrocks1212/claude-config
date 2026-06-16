# Research gate fires on already-implemented features — Investigation Spec

> `lazy-state.py`'s Step 5 research gate decides solely on RESEARCH*.md presence and never inspects PHASES.md, so a feature whose phases are already implemented gets routed to `needs-research` — wasting a full Gemini research prompt + ingest round-trip on work that is already done.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-16
**Placement:** docs/bugs/research-gate-ignores-existing-phases
**Related:** `user/scripts/CLAUDE.md` (lifecycle precedence), `docs/specs/lazy-decision-gates/`, `docs/specs/lazy-pipeline-ergonomics/`, sibling bug `docs/bugs/hardening-blind-to-process-friction/`

---

## Verified Symptoms

1. **[VERIFIED]** Feature `mcp-testing` (AlgoBooth) had a Gemini research prompt generated and research **ingested** on 2026-06-15 even though all of its phases were already implemented on disk (Implementation Notes dated 2026-05-08 — **38 days earlier**). The research round-trip was wasted work. — operator report; confirmed via AlgoBooth git history + PHASES.md below.
2. **[VERIFIED]** The phases were implemented (not all marked `Complete` — phases 8–10 were `In-progress` with substantial Execution Notes on disk; phases 1–7 `Complete`), i.e. the feature was past planning/implementation, not awaiting pre-implementation research. — `C:\Users\Jacob\repos\AlgoBooth\docs\features\mcp-testing\PHASES.md`.

## Reproduction Steps

1. Enqueue a feature that already has `SPEC.md` **and** a `PHASES.md` with implemented phases, but **no `RESEARCH.md`/`RESEARCH_SUMMARY.md`** (e.g. a feature built before the research-gated flow existed, or enqueued post-hoc).
2. Run `/lazy-batch` (or `/lazy`).
3. `compute_state()` reaches Step 5 (research gate) *before* Step 6 (PHASES.md), sees no RESEARCH.md, and routes to `needs-research` / "generate research prompt".

**Expected:** because `PHASES.md` already exists with implemented phases, the research gate is moot — the pipeline should skip research and fall through to the normal phase/implement/complete routing (Step 6+).
**Actual:** the pipeline requests research, halts on `needs-research`, and the operator runs Gemini + ingests results that are never needed.
**Consistency:** deterministic whenever `SPEC.md` + implemented `PHASES.md` exist without `RESEARCH.md`. Rare in practice (most features flow research→phases in order), but fully reproducible.

## Evidence Collected

### Source Code

The Step 5 research gate (`user/scripts/lazy-state.py:1461–1513`) branches **only** on `RESEARCH.md` / `RESEARCH_SUMMARY.md` / `RESEARCH_PROMPT.md` / `NEEDS_RESEARCH.md` presence:

```python
# Step 5: Research validation gate            (lazy-state.py:1461)
research = spec_path / "RESEARCH.md"
research_summary = spec_path / "RESEARCH_SUMMARY.md"
research_prompt = spec_path / "RESEARCH_PROMPT.md"
needs_research_file = spec_path / "NEEDS_RESEARCH.md"

if not research.exists() and not research_summary.exists():
    if needs_research_file.exists(): ... terminal_reason="needs-research"   # :1476
    if research_prompt.exists():     ... terminal_reason="needs-research"   # :1487
    return ... current_step="Step 5: generate research prompt", sub_skill="spec"  # :1496
```

**Zero inspection of PHASES.md.** The `PHASES.md` existence/completion check is Step 6 (`lazy-state.py:1515`) — strictly *after* the research gate. Precedence (from `user/scripts/CLAUDE.md`): Step 4 SPEC → Step 4.5 stub → **Step 4.6 upstream realign → Step 5 research gate → Step 6 PHASES** → Step 7 plan/execute …. So research is decided before PHASES is ever consulted.

The harness can already detect implementation status: `lazy_core.parse_phases()` (`lazy_core.py:1365–1459`) extracts each phase's `**Status:**`, and `count_deliverables()` (`lazy_core.py:1209`) counts checked/unchecked deliverables — both used at Step 6/7, neither consulted at Step 5.

A related flag exists but does not cover this case: `--skip-needs-research` (`lazy-state.py:15`, queue-selection skip at `:1232`) only **skips** research-pending items during *queue selection* in batch mode; it does not make the gate aware of existing phases, and `/lazy-batch` halted on the gate rather than skipping.

### Runtime / Git Evidence

AlgoBooth `docs/features/mcp-testing/`:
- PHASES.md: phases 1–7 `**Status:** Complete` with Implementation Notes **Completed: 2026-05-08**; phases 8–10 `In-progress` with Execution Notes started 2026-05-09. SPEC.md `**Status:** Ready` (2026-05-08).
- Research files: `fd97966a docs(mcp-testing): generate Gemini research prompt` (2026-06-15 18:58) → `8b447b83 docs(mcp-testing): ingest Gemini research` (2026-06-15 22:00).
- **Ordering: implementation (2026-05-08) precedes the research prompt/ingest (2026-06-15) by 38 days** — the research gate fired on a feature whose phases were long since implemented.
- Session `45e82e63` (2026-06-16 03:54) ingested upload `bcb6c457-Integration_Test_Maintenance_Strategies.txt` for this feature.

## Theories

### Theory 1: Research gate is logically a pre-PHASES.md gate but is not guarded as one (PRIMARY)
- **Hypothesis:** In the intended lifecycle, research runs *before* `spec-phases` authors `PHASES.md`. Therefore the only way to reach Step 5 with no `RESEARCH.md` *and* an existing implemented `PHASES.md` is a feature planned/implemented outside the research-gated flow. The gate should not fire once `PHASES.md` exists with implementation evidence.
- **Supporting evidence:** Step 5 precedes Step 6; gate ignores PHASES; the mcp-testing timeline (phases 38 days before research).
- **Contradicting evidence:** none — there is no legitimate flow that authors `PHASES.md` before research.
- **Status:** Confirmed.

## Proven Findings

1. **Root-cause class: `missing-contract`** — the research gate has no precondition tying it to the pre-planning stage; it fires purely on RESEARCH*.md absence, with no awareness that `PHASES.md` already exists with implemented phases.
2. **Fix locus is narrow and deterministic:** a guard before Step 5 (or a precondition inside it) that consults `PHASES.md` via the existing `parse_phases()` / `count_deliverables()`.

## Locked Decisions (proposed — operator to confirm during /plan-bug)

- **D1 — Research is a pre-PHASES.md gate.** Skip Step 5 when `PHASES.md` exists with implementation evidence; fall through to Step 6+ (which already routes `/execute-plan` for unchecked deliverables or mark-complete when done). This handles the "implemented but not all `Complete`" case the operator described (phases 8–10 were `In-progress`).
- **D2 — "Implementation evidence" predicate (deterministic, reuse existing parsers).** Treat `PHASES.md` as past-research when it parses to ≥1 phase AND shows implementation: any phase `**Status:**` of `Complete`/`In-progress`, OR `count_deliverables()` reports ≥1 checked box, OR an `## Implementation Notes` block is present. Prefer the broadest cheap signal so a partially-built feature is never sent back for research. (Exact predicate finalized in planning.)
- **D3 — No silent skip.** When the gate is bypassed because phases already exist, emit a diagnostic (`_DIAGNOSTICS`) so the decision is visible in the probe/retro rather than an invisible behavior change.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Research gate | `user/scripts/lazy-state.py:1461–1513` (Step 5) | Add a pre-Step-5 guard: if `PHASES.md` exists with implementation evidence, skip the research gate and continue to Step 6. |
| Implementation-evidence predicate | `user/scripts/lazy_core.py` (`parse_phases` `:1365`, `count_deliverables` `:1209`) | Add/compose a small predicate (e.g. `phases_show_implementation(phases_text)`) reusing existing parsers; no new parsing surface. |
| Wrappers (lockstep) | `user/skills/lazy/SKILL.md`, `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` | State-machine change → keep the paired wrappers' Step-5 prose in sync per the Coupling Rule. |
| Tests | `user/scripts/test_lazy_core.py`, `lazy-state.py --test` baseline (`tests/baselines/lazy-state-test-baseline.txt`) | New fixture: SPEC + implemented PHASES + no RESEARCH.md → routes to Step 6 (NOT `needs-research`); guard the default-unchanged path. |

## Open Questions

- Should the skip also apply when `PHASES.md` exists but is an empty stub (no phases parsed)? Proposed: **no** — require parsed phases + evidence, else a stub PHASES.md would wrongly suppress legitimate research.
- Does any existing `--test` fixture assert `needs-research` with a PHASES.md present (would this change a pinned baseline)? Verify before locking D2.
- Bug-pipeline parity: `bug-state.py` drops the research steps entirely, so no mirror is needed — confirm during planning.
