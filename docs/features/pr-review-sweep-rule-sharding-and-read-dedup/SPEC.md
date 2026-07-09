# PR-Review Sweep Rule-Sharding & Read Dedup — Feature Specification

> Shard sweep's 66KB embedded rule block by category so each review sends only the rules matching its file types, and eliminate the pipeline's duplicated reads (whole-diff-set ×3, manifest ×9–15, reuse components ×12, weights.yaml outside the cache).

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-09
**Friction-reduction feature:** yes

**Depends on:**

- pr-review-size-aware-pipeline-downshift — hard — both rewrite `commands/review-pr.md` and `agents/sweep.md`; the downshift feature owns the Step 5/8 output-contract edits and lands first, so the shard rewrite is authored once against the settled files.
- pr-review-plugin-repo-scoping-and-orphan-purge — hard — both rewrite `commands/rebuild-agents.md`; the orphan purge shrinks it to live agents first, so the shard-emission rewrite is authored once against the purged file.

---

## Executive Summary

The sweep agent's prompt file (`agents/sweep.md`, 71,026 bytes / 2,176 lines) embeds the full rendered rule corpus between `<!-- RULES_START -->` (line 66) and `<!-- RULES_END -->` (line 2088) — ~93% of the file, ≈16.5k tokens **resent as system prompt on every sweep invocation regardless of PR content**. The corpus is already partitioned into 8 category YAMLs whose sizes are known (csharp-architecture 25,046 B, code-consistency 16,019 B, testing 15,039 B, frontend-vue 11,399 B, api-design 5,899 B, performance 5,090 B, security 1,897 B, template-binding 1,611 B — 115 rules total), and each file's type is known deterministically from the prep manifest. A backend-only PR never needs frontend-vue + template-binding (~13KB source); a frontend-only PR never needs csharp-architecture (~25KB). Sharding the rendered rules per category and loading only matching shards cuts the single largest fixed cost of the pipeline by an estimated 30–60%.

Beyond sweep, the pipeline re-reads the same inputs many times per run (internals audit, 2026-07-09): the **full diff set is read whole at least 3×** (journey-planner "Read all diffs" `agents/journey-planner.md:32`, triage "Read all diffs" `agents/triage.md:24`, sweep per-file diff+full-file `agents/sweep.md:2162-2163`) plus per-group/per-cluster subsets downstream; **manifest.json is read by every agent** (9–15 reads/run); and the two reuse-stage components (`reuse-discovery-protocol.md` 4,262 B + `pr-review-reuse-agent-scaffold.md` 7,655 B) are runtime-`Read` by **every** reuse/intrafile cluster agent — up to 12 agents × 11,917 B ≈ 36k duplicated tokens per run. Finally, sweep's own access contract is self-contradictory: it mandates cache-only reads (`agents/sweep.md:25-30`) yet requires a live read of `knowledge/weights.yaml` at the plugin root (`agents/sweep.md:47`), outside the cache.

This feature: (a) `/rebuild-agents` emits per-category rule shards to `knowledge/rendered/<category>.md` and sweep reads only the shards matching its tier assignment's file types; (b) `prep-pr.ts` emits a condensed `pr-brief.md` (objectives + per-file diff summary) that journey-planner and triage consume instead of the raw diff set; (c) `/rebuild-agents` inlines the two reuse components into the two checker agent files (build-time embed replaces runtime Read); (d) `prep-pr.ts` snapshots weights into the cache (`weights-snapshot.json`), resolving sweep's cache-only contradiction.

## User Experience

Operator-visible effects only — review outputs are unchanged in shape:

- Reviews get cheaper (fewer fresh + cache-read tokens per run) and sweep starts faster (smaller system prompt, fewer tool round-trips).
- `/cognito-pr-review:rebuild-agents` now also (re)generates `knowledge/rendered/<category>.md` shards and re-embeds the reuse components; editing a rule or a shared component has the same workflow as today (edit → rebuild).
- Weight edits keep working with recalibration alone: the snapshot is taken at prep time per review, so `weights.yaml` remains the single authoring surface.

## Technical Design

### A. Rule sharding (granularity locked 2026-07-09: category-level)

1. `/rebuild-agents` renders each `knowledge/rules/<category>.yaml` to `knowledge/rendered/<category>.md` (same per-rule rendering as today's embed), and replaces sweep.md's embedded corpus with: the rule-evaluation protocol (unchanged) + a **shard manifest table** (category → shard path → file-type applicability) + the instruction to Read only applicable shards.
2. **Applicability mapping** (deterministic, from manifest file extensions/paths of the sweep tier assignment): `.cs` → csharp-architecture, api-design, security, performance, testing (test files), code-consistency; `.vue/.ts/.tsx` → frontend-vue, template-binding, code-consistency, performance, testing; config/other → code-consistency, security. Categories applying to both stacks (code-consistency, security, performance, testing) load once. The mapping table lives in sweep.md next to the shard manifest so `/learn-from-pr` can tune it.
3. Orchestrator change in `commands/review-pr.md` Step 5: the sweep dispatch prompt lists the applicable shard paths (computed from the manifest's file-type set) so sweep needs zero discovery.
4. Weight-aware thresholds are unaffected — weights are not embedded (they come from the snapshot, D below).

### B. pr-brief for journey/triage

1. `prep-pr.ts` additionally emits `{cacheDir}/pr-brief.md`: PR objectives (from pr-context), per-file entries (path, status, adds/dels, a ≤5-line diff summary, flags like "test file"/"generated"), and iteration deltas on re-review.
2. `agents/journey-planner.md` and `agents/triage.md` reading strategies change from "Read all diffs from `{cacheDir}/diffs/`" to "Read `pr-brief.md`; open an individual diff only when the brief is insufficient for a specific file". Investigation/sweep/checker agents keep reading real diffs — the brief serves the two whole-PR planning agents only.

### C. Component inlining

1. `/rebuild-agents` gains an embed step: inject the current text of `~/.claude/skills/_components/reuse-discovery-protocol.md` and `pr-review-reuse-agent-scaffold.md` into `agents/cognito-consistency-checker.md` and `agents/cognito-intra-file-consistency.md` between `COMPONENT_START/END` markers (the sweep RULES embed pattern).
2. The components remain the single source of truth; the agent files carry a "generated — edit the component, then /rebuild-agents" banner in the embed block. Runtime `Read` instructions are removed from both agents.

### D. Weights snapshot

1. `prep-pr.ts` copies the resolved weights into `{cacheDir}/weights-snapshot.json` (parsed YAML → JSON) at prep time.
2. `agents/sweep.md` reads the snapshot from the cache (contradiction resolved: all sweep reads are now cache-reads); `scripts/post-process.ts` keeps reading `weights.yaml` directly (same values — snapshot taken the same run).
3. The snapshot also pins one weights view per review run (a mid-run recalibration can no longer make sweep and post-process disagree).

## Implementation Phases

1. **Phase 1 — Weights snapshot (D).** Smallest, unblocks the cache-guard contradiction. Deliverable: sweep cache-only for real; snapshot in every new cache.
2. **Phase 2 — Rule sharding (A).** rebuild-agents shard emission + sweep.md rewrite + review-pr.md Step 5 shard listing. Deliverable: sweep.md < 15KB; shards on disk; backend-only local review loads no frontend shards.
3. **Phase 3 — pr-brief (B).** prep-pr.ts emission + journey/triage reading-strategy edits. **Entry gate:** brief-faithfulness validation on 2–3 historical PRs (journey diff before/after — see Open Questions) before the journey/triage reading-strategy edits are locked in. Deliverable: brief in cache; journey/triage prompts reference it; faithfulness comparison recorded.
4. **Phase 4 — Component inlining (C).** rebuild-agents embed step + agent-file markers. Deliverable: zero runtime component Reads in cluster-agent transcripts.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Shards generated | Run `/cognito-pr-review:rebuild-agents` | `knowledge/rendered/*.md` exist, one per category; sweep.md rule block replaced by shard manifest | File listing + sweep.md size (< ~15KB) |
| Sweep loads only applicable shards | Local-mode review of a backend-only change | Sweep transcript Reads csharp/api/etc. shards, no frontend-vue/template-binding Read | Sweep subagent transcript tool calls |
| Rule coverage preserved | Same rule corpus before/after | Every rule id present in exactly one shard; shard union == 115 ids | `grep -c 'id:'` over rendered shards |
| Journey/triage stop whole-diff reads | Any PR review post-change | journey-planner + triage transcripts read pr-brief.md, not every `diffs/*.diff` | Subagent transcripts |
| Cache-only sweep | Any review | No sweep Read outside `{cacheDir}` | Sweep transcript + pr-review-cache-guard hook log |
| Sweep fixed-context drop (KPI) | mine-sessions over sweep subagent transcripts pre/post | `sweep-agent-first-turn-ctx-tokens` decreases materially | First assistant-turn ctx in `subagents/agent-*.jsonl` for sweep dispatches |

## KPI Declaration

```json
{
  "id": "pr-review-sweep-first-turn-ctx",
  "system": "cognito-pr-review",
  "title": "Sweep agent first-turn context footprint",
  "friction": "Sweep's 66KB embedded rule corpus (~16.5k tokens) is resent on every invocation regardless of PR file types, and the pipeline re-reads the same diffs/manifest/components across agents — pure duplicated token spend on every review.",
  "signal": {
    "source": "session-log-mining",
    "selector": "sweep-agent-first-turn-ctx-tokens"
  },
  "unit": "tokens",
  "direction": "down-is-good",
  "baseline": {
    "value": null,
    "captured_at": null,
    "window": "90d",
    "provenance": "pending"
  },
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "cognito-forms",
  "notes": "Measured on demand via mine-sessions: first assistant-turn ctx (input + cache_read + cache_creation) of sweep-dispatch subagent transcripts under Cognito Forms project dirs. No automated collector — compute renders honest NO-DATA until mined."
}
```

## Locked Decisions

| # | id | Decision | Decided |
|---|----|----------|---------|
| 1 | shard-granularity | Category-level shards in v1 (8 shards matching the existing rule YAMLs); per-stack splits of mixed categories (e.g. code-consistency) deferred unless shard-size evidence demands it | 2026-07-09 — Jacob |
| 2 | plugin-cache-bump | Each phase's completion includes a plugin version bump. Docs-confirmed 2026-07-09: marketplace plugins are ALWAYS served from the versioned cache — no serve-from-source mode exists (see bug `pr-review-plugin-cache-split-brain-freezes-weights`) | 2026-07-09 — mechanical, docs-confirmed |

## Open Questions

- **pr-brief faithfulness (validation task, not a decision):** journey quality depends on the brief capturing behavioral intent; validate on 2–3 historical PRs (journey diff before/after) before locking Phase 3's reading-strategy edits. Carried as Phase 3's entry gate above.

_(Coordination with the sibling pr-review features is machine-enforced via the header hard-dep block; the sharding SPEC owns the sweep.md/rebuild-agents rule-block sections once its deps complete.)_

## Research References

No external research phase (skipped per operator direction 2026-07-09). Evidence base, gathered in-session and re-verified against source 2026-07-09:

- `agents/sweep.md`: 71,026 B / 2,176 lines; RULES_START line 66, RULES_END line 2088; cache-only mandate lines 25–30 vs live weights read line 47; per-file diff+full-file reads lines 2162–2163.
- Category YAML sizes + 115-rule count (grep-verified). Components: `reuse-discovery-protocol.md` 4,262 B, `pr-review-reuse-agent-scaffold.md` 7,655 B; ≤12 cluster agents/run re-Read both.
- Duplicated whole-diff reads: `agents/journey-planner.md:32`, `agents/triage.md:24`, plus sweep per-file reads.
- Session mining (~40 review runs): sweep subagent transcripts run 27–77 turns; one small-review sweep reached 155k ctx.
