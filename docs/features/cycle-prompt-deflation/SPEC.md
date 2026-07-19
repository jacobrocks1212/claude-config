# Cycle-Prompt Deflation — Feature Specification

> Shrink the assembled per-cycle dispatch prompt (`cycle-base-prompt.md`) to an inline-safe size by trimming boilerplate in place and scoping `@section` selection to what each cycle actually uses, enforced by a mechanical assembled-size ratchet.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-19
**Friction-reduction feature:** yes

**Depends on:**

- coupled-pair-generation — hard — `cycle-base-prompt.md` is mirrored into the bug/cloud SKILL variants through the overlay generator; every section edit must flow through that machinery or break coupled-pair parity.
- lazy-batch-skill-deflation — composes — extends its deflation playbook (prose→verdict-rules) and its `skill-size-ratchet.py` gate from whole-file skills to the assembled cycle prompt.
- mechanize-prose-only-orchestrator-contracts — soft — the `emit_cycle_prompt` / `@section` emitter this feature deflates is established by that contract; deflation edits its output, never forks the emitter.
- cycle-prompt-environment-dialect — soft — co-editor of `cycle-base-prompt.md` (owns `@section env-dialect-*`); deflation must preserve its section boundaries and selection attributes.

---

## Executive Summary

The autonomous `/lazy-batch` pipeline dispatches one Opus cycle subagent per cycle. Its prompt is assembled at probe time by the Python emitter `lazy_core.emit_cycle_prompt` from a single sectioned template, `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (57,737 bytes on disk, 25 `@section` blocks), selecting only the sections matching the current `pipeline × mode × skills × variant × park × host`. The orchestrator dispatches the assembled bytes verbatim (it is forbidden from hand-composing).

Field measurement across ~1,340 ref-resolved dispatches (1.19 GB AlgoBooth + 126 MB claude-config session corpus) shows the assembled cycle prompt peaks at **~16.8 KB** and that **~13–14 KB of every workstation cycle is fixed boilerplate** carried regardless of the dispatched skill — the eight `skills=all` sections (`turn-end` ~4.9 KB, `workstation-dispatch` ~4.8 KB, `hard-contract` ~3 KB, `d7`, `env-dialect-*`, `status-honesty`, `terminal-stop`, `task`). Only one or two skill-specific sections vary per cycle.

This feature deflates the assembled prompt by (1) **trimming the boilerplate prose in place** to terse verdict-routing rules — the exact playbook `lazy-batch-skill-deflation` applied to the 252 KB orchestrator SKILL.md — and (2) **tightening `@section` selection** so a cycle emits only the sections it actually consumes (e.g. a `spec` cycle should not necessarily carry the full 4.8 KB sub-subagent `workstation-dispatch` policy). Success is enforced by a **mechanical assembled-cycle-prompt size ratchet**, extending `skill-size-ratchet.py` from whole-file measurement to per-cycle assembled measurement, so the size cannot silently re-bloat (the observed pre-gate growth curve was +57%/4 weeks on the sibling SKILL.md).

The chosen method deliberately **avoids externalizing boilerplate into files the subagent reads by path**. That was the original framing, but `phases-slice-scoped-reads` proved a prose "go read this file/slice" mandate *in this exact prompt* already failed in the field and had to be replaced with mechanical enforcement — so a reference-by-path approach repeats a known failure mode unless every read is mechanically guaranteed. Trim-in-place keeps the dispatched prompt fully self-contained: no new read-reliability failure surface.

**Relationship to the `@@lazy-ref` reliability work (already owned — do NOT re-spec).** The `@@lazy-ref` nonce token exists *because* the prompt is large enough that the orchestrator prefers a token to pasting ~16 KB per dispatch. Two facts, both already established in the repo, make deflation the primary dispatch-cost lever:

- `hookSpecificOutput.updatedInput` is **platform-broken for the Agent tool as a class** (upstream `anthropics/claude-code#39814`, closed not-planned) — so `@@lazy-ref` cannot deliver a prompt on *any* Agent dispatch. Confirmed in `docs/bugs/byref-updatedinput-unapplied-on-background-agent-dispatch/PLATFORM_CONFIRMATION.md`.
- That bug is **Concluded with a locked fix** (`--resolve-ref <nonce>` consumed-nonce read + a "resolve your nonce first" dispatch-template contract; PHASES.md ready). The open policy question — flip the dispatch preference to **verbatim `cycle_prompt` for all Agent dispatches** — is operator park `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` decision #1, which the platform confirmation supports flipping.

If (as the evidence points) the harness flips to verbatim dispatch, the *full* assembled prompt is inlined verbatim every cycle — making its byte size the direct, unavoidable per-dispatch cost. This feature only shrinks that payload; it neither owns nor duplicates the ref-delivery fix.

## User Experience

The "user" is the harness operator; the observable surfaces are cycle telemetry and lint output.

- **Smaller dispatch prompts.** Each `/lazy-batch` cycle subagent boots on a leaner prompt (target ceiling ~9–10 KB assembled, ratcheting down), cutting tokens paid per dispatch and per compaction re-pay, with no change to the instructions' semantic content.
- **A hard size gate.** `skill-size-ratchet.py --check` (already run in the lint battery) additionally fails loudly when any assembled cycle-prompt profile exceeds its baseline ceiling, naming the profile, the metric, and current-vs-ceiling — the same "refuse early" shape as the whole-file gate.
- **No behavior regression.** Every rule currently expressed in a boilerplate section survives deflation as an equivalent terse rule; the deflation is prose-density, not policy removal. The regression guard is an assembled-prompt semantic diff review, not just a byte count.
- **Coupled-pair integrity preserved.** The bug/cloud mirrors of `cycle-base-prompt.md` regenerate cleanly from the deflated canonical via the overlay generator; the parity/freshness gate stays green.

## Technical Design

### Current architecture (as-built, verified)

- **Template:** `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — 25 `@section` blocks, each with an HTML-comment selector line `<!-- @section <name> pipelines=… modes=… skills=… [variant=…] [park=…] [hosts=…] -->`.
- **Emitter:** `lazy_core.emit_cycle_prompt` (`user/scripts/lazy_core/dispatch.py:886`), assembly loop `dispatch.py:952-1069`; section filter `dispatch.py:965-997`; token bind `dispatch.py:1052-1067`; residue guard (refuses on unbound `{token}`) `dispatch.py:1170+`. Sections joined by a single blank line.
- **Optional addenda:** `<repo>/.claude/skill-config/cycle-prompt-addenda.md` (AlgoBooth-only; absent in claude-config) and `loop-block.md` (2,884 B, appended when `repeat_count >= 2`).
- **Size ratchet:** `user/scripts/skill-size-ratchet.py` + `user/scripts/skill-size-baseline.json` — per-*file* byte + long-line (>500 char) ceilings; `--check` in the lint battery; `--lock-in` only ever lowers a ceiling.

### The eight `skills=all` boilerplate sections (deflation targets)

`task`, `env-dialect-core`, `env-dialect-windows` (hosts=windows), `d7`, `workstation-dispatch`, `status-honesty`, `hard-contract`, `terminal-stop`, `turn-end`. These are carried on every workstation cycle. Two independent levers:

1. **Trim-in-place** — rewrite each to terse rules (measure per-section before/after; target the ~4.9 KB `turn-end`, ~4.8 KB `workstation-dispatch`, ~3 KB `hard-contract` first — highest absolute return). Semantic content preserved.
2. **Scope-tighten** — re-examine each `skills=all` selector: is the section actually consumed by *every* skill, or can its `skills=` list be narrowed? Candidate: `workstation-dispatch` (sub-subagent fan-out policy) may not be needed by cycles that never fan out. Any narrowing must be evidence-backed (the section's rules must genuinely not apply to the excluded cycles) — a scope error silently under-briefs a cycle, which is worse than a few extra KB. This lever is applied conservatively and only where the exclusion is provably safe.

### New capability — assembled-cycle-prompt ratchet

`skill-size-ratchet.py` today measures files on disk. This feature adds an **assembled-profile** measurement mode:

- A profile = a concrete `(pipeline, mode, skill[, variant, park, host])` tuple representing a real dispatchable cycle (e.g. `feature/workstation/execute-plan`, `feature/workstation/mcp-test/runtime-up`).
- The ratchet assembles each profile via the *same* `emit_cycle_prompt` selection logic (imported, never re-implemented — the CLAUDE.md "projection can never drift from the parser it introspects" convention), measures assembled bytes, and checks against a per-profile ceiling in the baseline JSON.
- `--lock-in` semantics identical: only ever lowers a ceiling; new profiles seeded at current size.
- Wired into `lint-skills.py --check-skill-size` and the `gate-battery.json` invariant battery so it runs every lint pass.

### Coupled-pair constraint

`cycle-base-prompt.md` is the canonical from which the bug/cloud variants derive via `generate-coupled-skills.py` + the overlay store. Every section edit must (a) preserve `@section` selector boundaries so the emitter's filter still resolves, (b) preserve the marker literals other co-editing features depend on (`cycle-prompt-environment-dialect`, `lazy-cycle-containment` terminal-stop C4, `stub-origin-provisional-exclusion`, `code-doc-provenance-linkage`), and (c) leave the overlay generator's `--check` freshness gate green. The regression suite runs the generator `--check` after every deflation phase.

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown (4 phases: measurement harness + baseline seed + KPI/gate wiring → trim top-3 sections → trim remaining + scope-tightening → measured KPI baseline).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Assembled prompt shrank | Emit each cycle profile post-deflation | Every profile's assembled bytes ≤ its new ratchet ceiling; top-3 sections measurably smaller | `skill-size-ratchet.py --check` output; per-profile census |
| No policy lost | Semantic diff of each deflated section vs. original | Every original rule maps to a surviving terse rule; reviewer sign-off | Phase 2/3 semantic-equivalence review artifact |
| Coupled-pair parity intact | Run overlay generator `--check` after each phase | Exit 0 (mirrors regenerate cleanly from deflated canonical) | `generate-coupled-skills.py --check` |
| Ratchet blocks re-bloat | Add bytes to a deflated section past ceiling | `--check` exits 1 naming the profile + current-vs-ceiling | `skill-size-ratchet.py --check`; lint battery |
| Emitter still assembles | Emit every profile | No unbound-`{token}` residue error; residue guard passes | `emit_cycle_prompt` residue guard; `test_*` |

## KPI Declaration

**Friction:** tokens paid per cycle dispatch (and re-paid per compaction) inflate every `/lazy-batch` run; the boilerplate is the dominant, non-cycle-specific contributor.

> **New selector — registration is a Phase deliverable.** The `docs/kpi/registry.json` framework only measures a `(source, selector)` pair whose computation is registered in `kpi-scorecard.py`. `cycle-prompt-assembled-bytes` is a **new** `repo-static-scan` selector with no existing computation, so `kpi-scorecard.py --lint --spec` will flag it until **Phase 1** registers the selector + its assembled-profile census computation. This is the correct behavior — a friction feature cannot claim an unmeasurable KPI — not a spec defect. Row below is the target schema.

```json
{
  "id": "cycle-prompt-assembled-bytes",
  "system": "cycle-prompt-deflation",
  "title": "Max assembled cycle-prompt bytes across dispatchable profiles",
  "friction": "Tokens paid per cycle dispatch and re-paid per compaction; dominated by ~13-14KB fixed boilerplate carried every cycle.",
  "signal": {
    "source": "repo-static-scan",
    "selector": "skill-size-ratchet.py assembled-profile census: max(assembled_bytes) over all dispatchable (pipeline,mode,skill,variant) profiles"
  },
  "unit": "bytes",
  "direction": "down-is-good",
  "baseline": { "value": null, "captured_at": null, "window": "30d", "provenance": "pending" },
  "band": null,
  "review_by": "2026-10-19",
  "repo_scope": "claude-config",
  "notes": "Field pre-deflation max ~16.8KB (session-corpus measured). Phase-4 --capture-baseline stamps measured provenance from the post-Phase-3 census."
}
```

## Open Questions

- **Target ceiling.** ~9–10 KB assembled is the working target; the achievable floor depends on how much `turn-end`/`workstation-dispatch` compress without policy loss. The ratchet locks whatever Phase 3 achieves rather than committing to a number up front (estimated — verify during Phase 3).
- **Scope-tightening scope.** Which `skills=all` sections (if any) are provably safe to narrow is decided per-section in Phase 3 with evidence; the conservative default is trim-only (no selector change) for any section whose exclusion safety is uncertain.

## Research References

Grounded entirely in the claude-config codebase and the session-corpus mining (2026-07-19 evidence pass): the `emit_cycle_prompt`/`@section` architecture, the ~16.8 KB field ceiling and ~13–14 KB boilerplate split, the `phases-slice-scoped-reads` cautionary precedent (prose read-mandate failed in this exact prompt), and the `lazy-batch-skill-deflation` playbook + `skill-size-ratchet.py` gate this extends. No external deep-research pass (internal harness plumbing; skip-research path).
