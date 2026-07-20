# Orchestrator Tool-Search — Feature Specification

> A thin `--tool-search` CLI the `/lazy-batch` orchestrator invokes when it hits an abnormal situation needing a specific action/tool — ranked matches over the existing tool inventories; a miss auto-dispatches a backgrounded `/harden-harness` to build the tool and, when the operation is correctness-load-bearing, holds the run until it ships.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-19
**Friction-reduction feature:** yes

**Depends on:**

- unified-pipeline-orchestrator — hard — provides the toolify miner + promotion ledger; the miss-path must dedup a runtime tool-gap against that ledger so it never double-proposes a tool the offline miner already surfaced.
- harness-hardening-retro-fixes — hard — the `/harden-harness` skill the miss-path auto-dispatches; its anti-overfit reflex and toolify-candidate routing constrain what a backgrounded build may do.
- mechanize-prose-only-orchestrator-contracts — hard — supplies the `--emit-dispatch` / `pending_hardening` route-withhold surface this feature reuses verbatim as the "run waits" mechanism; the miss-path emits through it, never forks it.
- toolify-auto-promotion — composes — this feature is the inline, mid-run analog of that offline tool-proposer and shares its promotion ledger for dedup.
- incident-auto-capture — soft — the shipped "auto-dispatch a hardening cycle + dedup against double-report" precedent the miss-path mirrors.
- host-capability-declaration-for-gated-features — soft — the "needed CLI binary absent → deterministic defer" model reused when the missing tool is an absent host binary/toolchain.
- long-build-and-runtime-ownership — soft — backgrounded-run survival so a backgrounded `/harden-harness` outlives the cycle turn boundary.
- cycle-prompt-deflation — soft — co-edits `cycle-base-prompt.md`; this feature's terse `--tool-search` prose addition must fit under that feature's assembled-size ratchet.

---

## Executive Summary

During a `/lazy-batch` run the orchestrator regularly hits an **abnormal situation** — an operation it must perform for which it needs a specific action or CLI tool, and it is uncertain whether a suitable one already exists. Today there is **no dispatch-time tool-availability lookup**: the orchestrator either proceeds on improvisation or dispatches `/harden-harness` *blindly*, without first checking whether the capability already ships. Both are wasteful — improvisation risks incorrect work, and a blind harden dispatch can rebuild or re-propose a tool that already exists or that the offline toolify miner already surfaced.

This feature adds a **search-before-acting** step, directly modeled on Claude Code's own ToolSearch (query → matched tool schemas fetched on demand). A thin, read-only `--tool-search "<need>"` CLI aggregates the tool inventories that already exist in the repo — `docs/cli/cli-surface.json` (CLI flags), the `CLAUDE.md` Scripts table, the skill catalogs, `host-capability` declarations, and per-repo `mcp-tool-catalog.md` — and returns ranked matches with each match's invocation contract, or a clear MISS signal.

On a **hit**, the orchestrator uses the found tool. On a **miss**, the deterministic miss signal drives the *existing* remediation primitives (no new machinery): it emits a backgrounded **observed-friction `/harden-harness` dispatch** (harden trigger #5, `blocking` policy) to build the durable tool, deduped against the toolify promotion ledger so it never double-proposes. Whether the run **waits** is **correctness-gated**: if the needed operation is load-bearing for a gate/validation/correctness, the run holds at the gap via the shipped `pending_hardening` route-withhold until the tool ships or the operator resolves; if it is a mere convenience, the orchestrator takes a reasonable workaround now and lets the backgrounded harden build the durable tool for next time.

Crucially, a model-invoked search only helps if the model knows to call it: the orchestrator's pre-run/cycle prose (`/lazy-batch` SKILL.md + `cycle-base-prompt.md`, mirrored across the coupled dispatch skills) is wired to reference `--tool-search` — what it is, *when* to invoke it (before performing an abnormal operation that needs a specific tool), and the miss→harden protocol.

## User Experience

The "user" is the harness operator; the observable surfaces are orchestrator behavior and run telemetry.

- **Search instead of guess.** When a cycle needs an operation requiring a specific tool/CLI, the orchestrator runs `--tool-search "<need>"` and either invokes the ranked match or acts on an explicit MISS — replacing "improvise or blind-dispatch harden."
- **No double-proposals.** A runtime tool-gap is deduped against the toolify promotion ledger and the open queues, so the same tool is never proposed twice (once by the offline miner, once inline).
- **Correctness-gated blocking.** A miss on a correctness/gate-load-bearing operation holds the run at the gap (deterministic route-withhold) rather than shipping unverified work; a miss on a convenience never blocks — the run continues on a workaround while the tool builds in the background.
- **Durable capability growth.** Every miss that survives dedup produces a backgrounded `/harden-harness` that builds the missing tool once, so the next run's search hits.
- **Discoverable by construction.** The orchestrator prose names `--tool-search`, its trigger conditions, and the miss protocol, so the capability is actually reached (not a CLI nobody invokes).

## Technical Design

### The `--tool-search` CLI (new, read-only roster script)

- **Invocation:** `--tool-search "<natural-language need>" [--json] [--top N]`. Read-only; stdlib-only; a CLI-surface roster member (gains `--dump-cli-surface` + `DidYouMeanArgumentParser` per `state-cli-contract-registry`).
- **Corpus (aggregated from existing sources — never a new curated index):**
  - `docs/cli/cli-surface.json` — roster scripts + their argparse flags (the authoritative CLI capability surface).
  - `user/scripts/CLAUDE.md` + root `CLAUDE.md` Scripts tables — script purpose prose.
  - Skill catalogs (`.claude/skill-config/skill-catalog.md`, user + repo skills) — skill capabilities.
  - `host-capability` declarations — host binaries/toolchains a capability requires.
  - per-repo `mcp-tool-catalog.md` — MCP tool registration sources (no-op where absent, e.g. claude-config).
- **Ranking:** deterministic keyword/token match with a `difflib`-class near-miss score (reuse the `cli-surface-lint.py` / `DidYouMeanArgumentParser` matching style — never a new fuzzy engine). Output = ranked matches, each with source + invocation contract, or an explicit `MISS` verdict as the LAST stdout line (the authoritative-last-line banner convention).
- **Freshness:** because the corpus IS the existing registries, `--tool-search` cannot drift from reality any more than those registries do; `doc-drift-lint` / `cli_surface_gen --check` already gate their freshness.

### Trigger model (model-invoked search, mechanical miss-handling)

"I need a tool I may not have" cannot be mechanically detected — it is a judgment, exactly as Claude Code's own ToolSearch is model-invoked. So the **search invocation** is prose-triggered (the orchestrator recognizes the need and runs `--tool-search`). But the **miss→remediation** is mechanical: a `--tool-search` MISS is a deterministic signal that emits an observed-friction harden dispatch through the existing `--emit-dispatch` surface — no reliance on the orchestrator to "remember" to dispatch.

Prose-drift caveat (acknowledged): a prose "invoke `--tool-search` first" mandate in the cycle prompt shares the risk `phases-slice-scoped-reads` documented. Mitigations: (1) place the reference where it is most durable (a terse rule in the always-present cycle boilerplate, not a deep skill sub-step); (2) the mechanical miss-handling means that *when* a search does run, remediation is guaranteed; (3) a later hardening pass may add a mechanical nudge if telemetry shows the search is under-invoked. v1 does not attempt to mechanize the trigger.

### Miss handling (correctness-gated)

1. **Dedup first.** Check the toolify promotion ledger (`docs/features/unified-pipeline-orchestrator/toolify-ledger.json`) + open feature/bug queues for an already-proposed tool matching the need. A dedup hit → point at the existing item, do NOT dispatch.
2. **Classify the operation.** `correctness-load-bearing` (a gate, validation, or step whose wrong/absent result would ship incorrect work) vs `convenience`.
3. **Dispatch (backgrounded).** Emit an observed-friction `/harden-harness` (`trigger_kind: observed-friction`, `blocking` per class) via `--emit-dispatch hardening` (marker-active) — the durable-tool build. Backgrounded so it outlives the cycle turn boundary (`long-build-and-runtime-ownership`). Depth-capped: a hardening dispatch never recurses (existing `SKILL.md:915-922`).
4. **Wait vs workaround.**
   - `correctness-load-bearing` → the run **holds** at the gap: reuse the `pending_hardening` route-withhold (`route_overridden_by: pending-hardening-debt`) so `cycle_prompt` is withheld / `--run-end` refuses until the tool ships or the operator resolves the sentinel. No unverified progress past the gap.
   - `convenience` → the orchestrator takes a reasonable workaround now and proceeds; the backgrounded harden builds the durable tool for next run.
5. **Missing host binary special case.** When the "tool" is an absent host binary/toolchain (not a harness script to author), route through `host-capability-declaration-for-gated-features`' deterministic defer instead of a build dispatch.

### Prose wiring (operator's explicit requirement)

- `user/skills/lazy-batch/SKILL.md` — a terse rule: "before performing an abnormal operation that needs a specific tool/CLI, run `--tool-search "<need>"`; on a hit invoke the match; on a MISS follow the miss protocol." Coupled-pair mirror into `user/skills/lazy-bug-batch/SKILL.md` + `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (parity-audited).
- `cycle-base-prompt.md` — the equivalent terse rule in the appropriate `@section`, so a cycle subagent that hits the need also reaches the search. Coordinated with `cycle-prompt-deflation` (this is a small terse addition; it replaces blind gap-dispatch, and must respect that feature's assembled-size ratchet).

### What this feature explicitly does NOT build

The remediation spine — observed-friction harden, `pending_hardening` route-withhold, depth-cap, toolify ledger, host-capability defer — all already ships. This feature adds only (a) the `--tool-search` CLI and (b) the prose wiring + the mechanical miss→dispatch glue. It is a **thin inline consumer**, not a parallel proposer.

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Search returns real matches | `--tool-search "<need with a known tool>"` | Ranked match naming the correct script/skill + invocation contract | CLI output; `test_tool_search` |
| Miss is explicit | `--tool-search "<need with no tool>"` | `MISS` as the authoritative last line | CLI banner; test |
| No double-proposal | Miss on a need the toolify ledger already proposed | Dedup hit → points at existing item, no harden dispatch emitted | Phase-2 dedup test; dispatch ledger |
| Correctness-miss holds the run | Miss classified correctness-load-bearing | `pending_hardening` route-withhold engaged; run does not proceed past the gap | probe `route_overridden_by`; `--run-end` refusal |
| Convenience-miss proceeds | Miss classified convenience | Workaround taken; backgrounded harden dispatched; run continues | dispatch ledger; cycle log |
| Orchestrator invokes it | A cycle hitting an abnormal tool-needing operation | Prose references `--tool-search`; search invoked before blind dispatch | SKILL.md/cycle-prompt prose; run transcript |
| CLI-surface freshness | `cli_surface_gen.py --check` | `--tool-search` registered; exit 0 | CI/lint battery |

## KPI Declaration

**Friction:** blind `/harden-harness` dispatches and duplicate tool proposals waste cycles; proceeding on improvisation past a missing correctness tool ships wrong work.

> **New selector — registration is a Phase deliverable.** `blind-tool-gap-dispatch-rate` is a **new** `session-log-mining` selector with no existing computation in `kpi-scorecard.py`, so `--lint --spec` will flag it until **Phase 1** registers the selector + its computation (correlate the tool-search invocation breadcrumb against the hardening-dispatch ledger). A friction feature cannot claim an unmeasurable KPI — the flag is correct, not a spec defect. Row below is the target schema.

```json
{
  "id": "blind-tool-gap-dispatch-rate",
  "system": "orchestrator-tool-search",
  "title": "Share of tool-gap harden dispatches NOT preceded by a --tool-search in the same cycle",
  "friction": "Blind gap-dispatch and duplicate tool proposals waste cycles; improvisation past a missing tool risks incorrect work.",
  "signal": {
    "source": "session-log-mining",
    "selector": "tool-search invocation breadcrumb vs hardening-dispatch ledger: count(observed-friction/tool-gap harden dispatches with no preceding --tool-search this cycle) / count(all such dispatches)"
  },
  "unit": "ratio",
  "direction": "down-is-good",
  "baseline": { "value": null, "captured_at": null, "window": "30d", "provenance": "pending" },
  "band": null,
  "review_by": "2026-10-19",
  "repo_scope": "claude-config",
  "notes": "Requires a tool-search invocation breadcrumb (Phase 1) to correlate against the dispatch ledger. Pre-feature baseline is ~1.0 (no search exists today) — Phase-4 --capture-baseline stamps the measured post-wiring value."
}
```

## Open Questions

- **Trigger mechanization (deferred to a later pass).** v1 relies on prose to invoke the search (model-invoked, like Claude Code ToolSearch). If telemetry shows under-invocation, a mechanical nudge (e.g. detecting a harden dispatch with no preceding search and back-pressuring it) is a follow-up — not v1 scope.
- **Ranking precision.** The deterministic keyword/near-miss ranker's precision over the prose-y Scripts table is bounded; if match quality is poor in practice, enriching the corpus with per-tool keyword tags is a Phase-1 follow-up (estimated — verify during Phase 1).
- **Convenience vs correctness classification authority.** v1 leaves the classification to the orchestrator's judgment at the miss site; if this proves inconsistent, a declared per-operation classification is a follow-up.
- **Discovered at `/spec-phases` (2026-07-19):** `user/scripts/cli_surface.py` already ships a per-script `--search-ops`/`ops_index` token-overlap search (deterministic, over one script's own argparse flags). `--tool-search` reuses that exact scoring shape (documented as a reuse directive in `PHASES.md`'s touchpoint audit) but stays a separate script because its scope is cross-source aggregation, not one parser's own flags — flagged here in case a future pass decides to fold the two into one shared ranking module instead of two independent call sites of the same algorithm shape.
- **Discovered at `/spec-phases` (2026-07-19):** the SPEC's `/spec-phases` Step 1.6 dep-sync (`lazy-state.py --sync-deps`) is refused for any cycle subagent by design (`refuse_if_cycle_active`), so it could not run during this feature's own phase-authoring cycle — the SPEC's `**Depends on:**` block is already locked and the realign stub records the upstream hashes, so this has no effect on THIS feature's correctness, but it is a standing harness-doc gap (spec-phases's Step 1.6 interpretation table doesn't name the exit-3 cycle-subagent case) worth a future `harden-harness` pass, not something this feature's phases need to fix.

## Research References

Grounded in the claude-config codebase + the 2026-07-19 evidence pass: confirmed no dispatch-time tool-search exists; the observed-friction harden trigger #5 with its `blocking` policy (`lazy-batch/SKILL.md:883-908`); the `pending_hardening` route-withhold (`mechanize-prose-only-orchestrator-contracts`); the toolify miner/promotion ledger (`unified-pipeline-orchestrator`, `toolify-auto-promotion`); host-capability defer; depth-cap. Modeled on Claude Code's ToolSearch (deferred-tool query→fetch). No external deep-research pass (internal harness plumbing; skip-research path).
