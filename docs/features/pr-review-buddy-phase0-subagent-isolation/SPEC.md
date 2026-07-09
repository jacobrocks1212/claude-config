# PR-Review Buddy Phase-0 Subagent Isolation — Feature Specification

> Delegate `review-pr-buddy`'s Phase 0 (pipeline Steps 1–8) out of the interactive orchestrator's context and lazy-load per-chunk data during the walk, so the reviewer starts the interactive session with a near-fresh window instead of ~115–191k tokens already spent.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-09
**Friction-reduction feature:** yes

**Depends on:**

- pr-review-size-aware-pipeline-downshift — hard — the Phase-0 delegate executes review-pr Steps 1–8, which that feature rewrites (routing step, tri-step collapse, change (d) self-written agent outputs — (d) is also what keeps the delegate's own window small); machine-enforced ordering replaces the prose coordination note.

---

## Executive Summary

`/cognito-pr-review:review-pr-buddy` runs its non-interactive prep (Phase 0 — `review-pr.md` Steps 1–8: prep script → journey → triage → planner-validate → investigation/sweep/reuse/intrafile fan-out → aggregate → post-process) **inside the interactive orchestrator's own context window**. Session mining across 34 buddy sessions (2026-07-09) shows the orchestrator's context at the *first* interactive question is median **115k tokens, max 191k** — on a model without a 1M window, the walk that is the entire point of buddy mode runs degraded from its first chunk. Attribution of the pre-walk window: ~64k session-startup baseline + the 34KB buddy command expansion + the orchestrator re-reading `commands/review-pr.md` (33KB) to execute Phase 0 + `processed-findings.json` (36KB observed) + the journey file (often read twice) + raw diffs, plus triage JSON and transcribed agent outputs transiting the window.

This feature makes two structural changes. **(1) Phase-0 isolation:** Phase 0 executes outside the orchestrator's window and returns only a small result envelope — `{cacheDir, cogDocsItemDir, journey path, per-tier finding counts, chunk count}`. The orchestrator never reads `review-pr.md`, never sees triage JSON or agent outputs, and never touches raw prep tool output. **(2) Lazy per-chunk loading:** Phase 1's walk stops front-loading `processed-findings.json` + the full journey; a new machine-readable **chunk index sidecar** (emitted at the end of Phase 0) lets the orchestrator load exactly one chunk's files, diffs, and findings when the walk arrives at that chunk.

The compaction-recovery contract is preserved: `buddy-session.json` remains the recovery anchor, and the chunk index makes recovery *cheaper* (resume reads one chunk's slice, not the whole findings file). Expected effect: walk-start context drops from ~115k median to near the ~64k session baseline + one chunk's working set, eliminating most mid-walk compactions (sessions today reach 200–258k with up to 2 compactions during the walk).

## User Experience

- The reviewer invokes `/cognito-pr-review:review-pr-buddy <PR>` exactly as today. Announcements change only in that Phase 0 reports progress as a single delegated stage ("Prep running in background agent… done: N findings across M chunks") instead of streaming pipeline noise.
- The interactive walk itself is unchanged in shape (orient → independent read → reconcile → disposition → checkpoint → advance) — but starts on a fresh window, so chunk teaching, diagrams, and dispositions stay high-quality deep into large PRs.
- On compaction or interruption, resume behavior is unchanged from the reviewer's perspective (`buddy-session.json` resume at first non-done chunk), and faster.
- Failure surface: if the Phase-0 delegate fails, the orchestrator reports the delegate's error verbatim and stops — same contract as a Step-1 prep failure today.

## Technical Design

### Phase-0 execution vehicle (DECIDED 2026-07-09 — Option A)

**Option A locked by Jacob 2026-07-09.** The blocking constraint — nested Agent dispatch — was probed live the same day: a `general-purpose` subagent successfully dispatched its own nested Explore agent in this harness (and the harness's containment-hook docs record that recursive Agent/Task dispatch is deliberately allowed). Option B remains below only as the fallback if runtime nesting ever regresses.

- **Option A — single Phase-0 subagent (CHOSEN).** Buddy dispatches ONE `general-purpose` agent whose prompt is: "execute `commands/review-pr.md` Steps 1–8 for PR {id}; write all artifacts to disk; return the result envelope JSON only." The subagent reads `review-pr.md` (33KB) and dispatches the pipeline's specialist agents itself. Implementation still re-runs the two-line nested-dispatch probe as its first task — a cheap regression check, no longer a decision gate.
- **Option B — orchestrator dispatches, zero-echo discipline (fallback only).** The orchestrator still dispatches the pipeline agents (no nesting needed) but every byte-heavy artifact is file-piped: agents write their own `agent-output/*.json` (per the sibling `pr-review-size-aware-pipeline-downshift` change (d)), post-process stdout goes to a shell redirect, triage JSON is written to `{cacheDir}/triage.json` and passed by path, and the orchestrator's Phase-0 instructions live in a slim extracted `commands/phase0-checklist.md` (< 4KB) instead of the full 33KB `review-pr.md`. Lower risk, smaller win (the ~64k baseline + dispatch envelopes remain, but the ~50–100k of artifact transit disappears).

Either way, `review-pr.md` remains the single source of pipeline truth — Option A reads it in the delegate; Option B's checklist is a pointer file that references `review-pr.md` step numbers without duplicating bodies (same "delegation, not duplication" rule buddy already declares).

### Result envelope (both options)

Phase 0 ends by writing `{cacheDir}/phase0-result.json`:

```json
{
  "pr_id": "...",
  "cacheDir": "...",
  "cogDocsItemDir": "...",
  "journey_path": "...",
  "chunk_count": 0,
  "finding_counts": { "investigation": 0, "sweep": 0, "reuse": 0, "intrafile": 0 },
  "chunk_index_path": "..."
}
```

The orchestrator reads ONLY this envelope to initialize the walk and `buddy-session.json`.

### Chunk index sidecar (lazy loading)

Phase 0 emits `{cacheDir}/chunk-index.json`, derived deterministically from the journey's `## Manual Review Guide` (`### Step N` chunks) joined against `processed-findings.json` (a finding belongs to a chunk if its `file` appears in the chunk's `**Files:**` list — the same rule buddy applies today):

```json
{
  "chunks": [
    {
      "index": 0,
      "group": "…",
      "complexity": "trivial|non-trivial",
      "files": ["path", "…"],
      "journey_lines": [120, 168],
      "diff_paths": ["{cacheDir}/diffs/….diff"],
      "finding_refs": [
        { "finding_ref": "file.cs:42", "source": "investigation", "offset_in_processed": 3 }
      ]
    }
  ]
}
```

During the walk, arriving at chunk *k* the orchestrator reads: the journey slice (`journey_lines` ranged read), the chunk's `diff_paths`, and the chunk's findings (either via `offset_in_processed` ranged extraction or — simpler and preferred — Phase 0 additionally shards findings to `{cacheDir}/findings-by-chunk/chunk-{k}.json`). Nothing outside chunk *k* enters the window. The Finding ID Convention, disposition taxonomy, pre-filters (already-commented, stale-Copilot), and calibration join are unchanged — they operate on the same finding objects, now loaded per-chunk.

### Compaction recovery

Unchanged anchor: `buddy-session.json` (schema untouched). Recovery reads the envelope + chunk index + the first non-done chunk's shard — strictly less data than today's full re-read. The chunk index path is recorded in `buddy-session.json`'s top level (additive field `chunk_index_path`) so recovery doesn't depend on re-deriving it.

### Files touched

- `commands/review-pr-buddy.md` — Phase 0 section rewritten to the delegate + envelope contract; Phase 1 setup reads envelope + chunk index instead of journey + processed-findings whole; per-chunk loop loads shard files; interruption carve-outs unchanged.
- `commands/review-pr.md` — additive Step 8.5: emit `chunk-index.json` + `findings-by-chunk/` shards + `phase0-result.json` (deterministic post-processing extension — candidate for a small TypeScript helper `scripts/emit-chunk-index.ts` rather than LLM assembly).
- (Option B only) new `commands/phase0-checklist.md`.

## Implementation Phases

1. **Phase 1 — Chunk index + shards (no behavior change).** Add `scripts/emit-chunk-index.ts` (deterministic; reads journey + processed-findings; writes chunk-index.json + findings-by-chunk/ + phase0-result.json); wire as review-pr Step 8.5. Buddy still works unchanged (files are additive).
2. **Phase 2 — Nested-dispatch regression probe.** Re-run the two-line subagent→subagent dispatch probe (capability confirmed 2026-07-09) and record the result; proceed with Option A, falling back to Option B only on a failed probe.
3. **Phase 3 — Buddy Phase 0 delegation.** Rewrite buddy Phase 0 to the Option-A delegate + envelope read; delete the orchestrator's mandated reads of review-pr.md/journey/processed-findings from Phase 0.
4. **Phase 4 — Lazy walk.** Rewrite Phase 1 setup + per-chunk loop to shard loads; add `chunk_index_path` to buddy-session.json; verify compaction resume path.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Chunk index emitted and complete | Run review-pr through Step 8.5 on a cached PR | `chunk-index.json` chunk count == journey `### Step N` count; every processed finding appears in exactly one shard | `{cacheDir}/chunk-index.json`, `findings-by-chunk/` |
| Envelope-only Phase 0 | Run buddy Phase 0 on a test PR | Orchestrator transcript contains no triage JSON, no agent-output bodies, no review-pr.md read | session transcript (mine-sessions render) |
| Walk-start context reduced | Complete a buddy review; mine the session | ctx at first AskUserQuestion < 90k (vs 115k median baseline) | `digest_sessions.py` + first-AskUser extraction |
| Lazy chunk loads | Walk a multi-chunk PR | Reads during chunk k reference only chunk k's shard/diff/journey-slice paths | session transcript |
| Compaction resume intact | Interrupt mid-walk; resume | Resume announces correct chunk; dispositions preserved; walk completes | `buddy-session.json`, final `PR-{id}.md` |

## KPI Declaration

```json
{
  "id": "buddy-first-ask-ctx-tokens",
  "system": "cognito-pr-review",
  "title": "Buddy orchestrator context at first interactive question",
  "friction": "Phase 0 running inside the interactive orchestrator burns ~115k median tokens before the reviewer's first disposition, degrading walk quality and forcing mid-walk compactions.",
  "signal": { "source": "session-log-mining", "selector": "buddy-first-ask-ctx-tokens" },
  "unit": "tokens",
  "direction": "down-is-good",
  "baseline": { "value": 115000, "captured_at": "2026-07-09", "window": "90d", "provenance": "measured" },
  "band": { "warn": 130000, "breach": 160000 },
  "review_by": "2026-10-01",
  "repo_scope": "cognito-forms",
  "notes": "Baseline measured 2026-07-09 via mine-sessions: digest of 34 buddy sessions in the Cognito Forms project dirs; per-session ctx (input + cache-read + cache-creation) at the first AskUserQuestion tool_use; median 115k, min 91k, max 191k. No automated collector yet — compute returns NO-DATA until one is wired; re-measure with the same method."
}
```

## Locked Decisions

| # | id | Decision | Decided |
|---|----|----------|---------|
| 1 | buddy-phase0-vehicle | Option A — single Phase-0 delegate subagent. Nested Agent dispatch probe-confirmed working 2026-07-09 (general-purpose subagent dispatched a nested Explore agent successfully); Option B retained as fallback only | 2026-07-09 — Jacob |
| 2 | buddy-chunk-shard-format | Separate `findings-by-chunk/chunk-{k}.json` shard files (not offsets into `processed-findings.json`) — simplest ranged loading, cheapest compaction resume | 2026-07-09 — mechanical, recommended option |

## Open Questions

(none — sequencing with `pr-review-size-aware-pipeline-downshift` is now a machine-enforced hard dep in the header block)

## Research References

No Gemini research phase — operator-directed skip; grounded in in-session evidence (2026-07-09): session mining of ~40 review runs (34 buddy) via `mine-sessions` (`digest_sessions.py`, `attribute_predispatch.py --until-tool AskUserQuestion`, per-subagent token accounting), the plugin internals audit (per-agent mandated reads, `review-pr.md`/`review-pr-buddy.md` line evidence), and the cog-docs artifact corpus (31 reviewed PRs). Key figures: first-AskUser ctx median 115k / max 191k (n=34); pre-walk attribution — review-pr.md read ~102KB total across 3 attributed sessions, processed-findings.json 36KB, journey 16–22KB (sometimes twice); buddy sessions reach 200–258k with up to 2 mid-walk compactions.
