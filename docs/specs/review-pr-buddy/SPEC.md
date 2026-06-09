# Interactive PR Review Buddy & Reuse-Candidacy Stage — Feature Specification

> Add a senior-architect *pair-review* command (`/cognito-pr-review:review-pr-buddy`) that walks a human through a PR chunk-by-chunk over the existing review pipeline, and mirror the `/spec` reuse-first discovery system into the review pipeline as a wired, parallel reuse-candidacy stage that both `review-pr` and `review-pr-buddy` consume.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-06-08

**Depends on:** (none)

<!-- This feature *composes* two existing substrates, neither of which is a spec'd feature-id under
     docs/specs/, so there is no parseable feature-id to depend on (per dep-block schema, recorded as
     (none); coupling documented in Technical Design § Composed substrate):
     1. The cognito-pr-review plugin's review-pr pipeline (now tracked at
        user/plugins/local-tools/plugins/cognito-pr-review/).
     2. The /spec reuse-first-discovery component
        (repos/cognito-forms/.claude/skill-config/reuse-first-discovery.md + its no-op user default). -->

---

## Executive Summary

The `cognito-pr-review` plugin runs a fully autonomous review pipeline: deterministic prep → journey-planner (Opus) → triage → investigation+sweep → post-process → synthesizer, producing two artifacts — a persistent **journey file** and a synthesized **review doc**. It is excellent at *producing a verdict* but does nothing to *bring a human to understanding*. This feature adds that second mode.

`/cognito-pr-review:review-pr-buddy` is an interactive, senior-architect pair-review. It reuses the autonomous pipeline verbatim to pre-compute everything non-interactively (journey + all findings), then sits down with the reviewer and walks the PR **chunk by chunk along the journey's Manual Review Guide** — teaching what changed, why, and how; surfacing the pre-computed bugs, coverage gaps, and reuse flags scoped to each chunk; posing the journey's "key questions"; and capturing the reviewer's verdict per finding. The session culminates in a **human-curated review doc** in the existing synthesizer format — containing only what the reviewer kept, plus their own observations.

The second half of the feature mirrors the reuse-first discipline we built for `/spec` into the review pipeline. Today the pipeline's reuse/duplication awareness is split between an *orphaned* `cognito-consistency-checker` agent (not wired into the 12-step orchestration) and a shallow per-group "Consistency Pass" inside the investigation agent. Neither asks the capability-level question `/spec` now asks at design time: *"does an existing Cognito system already do this, such that the PR should have reused/extended/refactored it instead of adding new code?"* This feature wires a **reuse-candidacy stage** into the pipeline that fans out **parallel discovery agents** over the PR's net-new code, grounded in the same domain skills / agent-docs / tree-sitter substrate `/spec` uses, emitting verdicts (`reuse` / `extend` / `refactor` / `wrap` / `acceptable-new`) with cited evidence. Both `review-pr` and `review-pr-buddy` get it for free, because it lives in the shared pre-compute path.

## Reuse Ledger

Per the reuse-first discipline, the existing systems were inventoried before any new design. Discovery surface: the plugin source at `user/plugins/local-tools/plugins/cognito-pr-review/` (read in full across the prior brainstorm), the `/spec` reuse-first component, and the Cognito agent-docs. The dominant verdict is **reuse/extend/refactor** — almost nothing here is greenfield.

| Capability | Existing candidate (file / symbol) | What it does today | Verdict | Evidence | Confidence |
|---|---|---|---|---|---|
| Human walkthrough script | `agents/journey-planner.md` → **Manual Review Guide** | Emits "ordered steps for a human reviewer," each with *Files / What to look for / Key questions* | **reuse-as-is** | `journey-planner.md:106-122` (template); produced non-interactively as Step 2 of `review-pr.md` | high |
| PR prep / cache / triage / findings | `commands/review-pr.md` Steps 1–8 | Deterministic prep → journey → triage → investigation+sweep → aggregate → post-process | **reuse-as-is** | `review-pr.md:98-323`; buddy Phase 0 invokes this unchanged | high |
| Review doc synthesis + format | `agents/synthesizer-v2.md` | Narrative review from processed findings + journey, fixed section template | **extend** | `synthesizer-v2.md:70-127` (output template); buddy produces a human-curated variant of the same shape | high |
| Reuse / duplicate detection | `agents/cognito-consistency-checker.md` (**orphaned**) + investigation "Consistency Pass" | Baseline comparison, "doesn't reinvent existing functionality," duplicate-logic detection — but checker is *not* in the pipeline; investigation pass is file-vs-baseline only | **refactor** | checker exists in `agents/` but absent from `review-pr.md`'s 12 steps; investigation pass at `investigation.md:157-171` | high |
| Baseline pre-identification | `scripts/prep-pr.ts` → `manifest.baselines[]` | Schema exists (`{path, similarityScore, cachedFile}`), but `findBaselines()` is a **stub returning `[]`** ("skip detection for MVP") | **extend (implement the stub)** | schema at `prep-pr.ts:130-135`; empty body at `prep-pr.ts:1181-1203`; consumer `cognito-consistency-checker.md:26-39` (`similarityScore>=50`) goes live once populated — implementing it is in scope (Phase 2, deliverable 2a) | high |
| Findings aggregation + weighting | `scripts/aggregate-findings.ts`, `scripts/post-process.ts` | Combine agent JSON → EMA-weight, dedup, rank, filter, lifespan | **extend** | `review-pr.md:303-323`; add a `reuse` source to the schema/source enum | med |
| Rule corpus + weights + calibration | `knowledge/rules/*.yaml`, `knowledge/weights.yaml`, `/rebuild-agents`, `/learn-from-pr` | 95 calibrated rules across 8 categories incl. `code-consistency`; EMA weights; rule re-embedding | **extend** | `CLAUDE.md:45-66`; add reuse rules under `code-consistency` so sweep can cheaply flag + escalate | high |
| Reuse-discovery protocol | `repos/cognito-forms/.claude/skill-config/reuse-first-discovery.md` | Capability → domain-skill/agent-doc/tree-sitter grounding → verdict taxonomy → ledger → confidence gate | **refactor** | the `/spec` component built last session; extract the codebase-neutral protocol core into one shared file both `/spec` and the plugin consume | high |
| Parallel discovery fan-out | `/spec` reuse-first Step R2; investigation parallel dispatch in `review-pr.md:228-272` | One agent per capability cluster / critical group, dispatched in parallel | **reuse-as-is** (pattern) | `review-pr.md:228-272`; the reuse stage reuses this dispatch shape | high |
| Interactive picker + checkpointing | `AskUserQuestion`; Task tools; `track-work.py` WIP liveness | Structured choice capture; compaction-safe task list; item liveness marker | **reuse-as-is** | used throughout `/spec`; buddy uses them for per-chunk verdict capture + recovery | high |
| Cache-boundary enforcement | `review-pr.md` Step 1.5 marker + PreToolUse hook | Blocks reads outside the cache during review | **reuse-as-is** (with carve-out) | `review-pr.md:126-141`; reuse stage needs *local-codebase* reads (like investigation) — inherit investigation's carve-out, NOT sweep's cache-only boundary | high |

**Net-new (build) surface — minimal, and each composes the above:**
- `commands/review-pr-buddy.md` — the interactive orchestration shell (Phases 0/1/2). Composes the pipeline + journey + synthesizer; the only genuinely new control flow.
- A reuse-candidacy **agent prompt** + its **wired stage** in `review-pr.md`. Grows the orphaned `cognito-consistency-checker` rather than starting fresh.
- A handful of `code-consistency` reuse rules in the corpus.

**build-new negative-search trail:** no existing command performs an interactive, chunked, human-in-the-loop walkthrough (searched `commands/*.md` — all are autonomous or utility: `review-pr`, `learn-from-pr`, `calibrate`, `weights`, `rebuild-agents`). No existing pipeline stage emits capability-level reuse verdicts (searched the 12 steps + all `agents/*.md`). Hence the two build-new items above are justified.

## User Experience

### `/cognito-pr-review:review-pr-buddy [PR# | local] [aspects]`

**Phase 0 — non-interactive prep (no user interaction).** The command runs the full `review-pr` pipeline to completion: prep → journey doc → triage → planner validation → **reuse-candidacy stage** + investigation + sweep → aggregate → post-process. When Phase 0 finishes, the journey file and `processed-findings.json` (including reuse findings) are on disk. The reviewer is told prep is done and the walk is starting.

**Phase 1 — interactive walk (senior-architect pair).** The buddy iterates the journey's **Manual Review Guide** steps in order. For each chunk (a journey step / file group):

1. **Teach** — explain *what* changed in this chunk, *why* (tie to the journey Objective it serves), and *how* (the approach the author took). Senior-architect framing, grounded in the cached diff — not a diff dump.
2. **Surface findings** — present the pre-computed findings scoped to this chunk's files: investigation findings (bugs, edge cases, correctness), sweep rule hits (coverage/consistency), and **reuse-candidacy flags** ("this duplicates `X`; consider extending it"). Highlighted, not buried.
3. **Socratic prompt** — pose the journey's "Key questions" for the chunk plus the buddy's own, inviting the reviewer to reason about the change before being told the verdict.
4. **Capture verdict** — via `AskUserQuestion`, the reviewer dispositions each surfaced finding: **keep** (goes in the review), **dismiss** (with optional note), **will-comment** (the reviewer will leave a PR comment), or **add-own** (the reviewer's own observation, not from the pipeline). Checkpoint the chunk to a session-state file for compaction recovery.
5. **Advance** to the next chunk.

The reviewer may interrupt at any chunk to dig deeper, ask the buddy to open a file, or revisit a prior chunk.

**Phase 2 — culminating review doc.** The buddy synthesizes a **human-curated** `PR-{id}.md` in the existing synthesizer-v2 format/location, containing only kept findings + the reviewer's own observations + the comments they intend to leave. The autonomous synthesizer is *not* run as a competitor — the session *is* the synthesis. (The journey file and `REVIEWED.md` sentinel behavior are unchanged from `review-pr`.)

### Reuse-candidacy in autonomous `review-pr`

For a plain `review-pr` run, the reuse-candidacy stage adds a new finding class to the standard review doc: reuse/refactor opportunities with cited existing-system evidence, weighted and surfaced like any other finding. No new UX; it flows through the existing synthesizer sections.

## Technical Design

### Composed substrate

- **Plugin home:** `user/plugins/local-tools/plugins/cognito-pr-review/` in claude-config (moved + symlinked into the `local-tools` marketplace; tracked via `manifest.psd1`).
- **Shared with `/spec`:** the reuse-discovery protocol. Per the locked decision (single shared file), the codebase-neutral protocol core is extracted to one file consumed by both `/spec`'s `reuse-first-discovery.md` and the plugin's reuse agents.

### `review-pr-buddy` command

A new `commands/review-pr-buddy.md`. Argument parsing mirrors `review-pr` (PR id / `local` / aspects). Phase 0 delegates to the `review-pr` pipeline steps (ideally by referencing the same step bodies rather than copying them — keep `review-pr.md` the single source of pipeline truth). Phase 1 is the new interactive loop driven by the journey Manual Review Guide. Phase 2 invokes a synthesizer variant fed the session's kept-findings set.

- **Session state:** a `{cacheDir}/buddy-session.json` records per-chunk progress and per-finding dispositions, so a compaction mid-walk resumes at the right chunk. Task tools track the high-level phases.
- **Cache boundary:** Phase 1 reads cached diffs/files for teaching (cache-bound, like the journey). If the reviewer asks to open an unchanged file, that is a local-codebase read — handle like investigation's carve-out, not sweep's cache-only rule.

### Reuse-candidacy stage (wired, parallel)

A new stage in `review-pr.md`, positioned **after triage validation (Step 4) and dispatched in parallel with investigation+sweep (Step 5)** so it adds no serial latency:

1. **Cluster net-new code** from the manifest — added/substantially-modified substantive files (services, types, components, helpers), using the prep script's `baselines[]` as seed signal.
2. **Fan out one discovery agent per cluster** (cap ~6, same dispatch shape as investigation). Each agent is Opus with investigation-equivalent access (cache + local codebase + tree-sitter), and **reads the shared reuse-discovery protocol**. It answers the capability-level question and emits findings with a verdict ∈ {`reuse`, `extend`, `refactor`, `wrap`, `acceptable-new`}, the existing-system candidate (`file:line`/symbol/skill), blast radius for `refactor` (via `get_callers`), and a negative-search trail for `acceptable-new`.
3. **Write outputs** to `{cacheDir}/agent-output/reuse-{cluster}.json`, schema-compatible with `aggregate-findings.ts`.

This grows the orphaned `cognito-consistency-checker` agent into the stage's per-cluster agent (or supersedes it) rather than authoring a new agent from nothing.

### Pipeline + script wiring

- `aggregate-findings.ts` — accept `reuse-*.json` agent outputs; add `reuse` to the recognized source set.
- `post-process.ts` — treat `reuse` findings through the existing EMA/dedup/rank/filter path; map reuse verdicts to severity (e.g. `refactor`/`reuse` → important, `acceptable-new` → informational/dropped).
- `synthesizer-v2.md` — add handling so reuse findings render (e.g. a "Reuse & Duplication" subsection or folded into Rule-Based/Critical as appropriate).
- `knowledge/rules/*.yaml` + `weights.yaml` — add a few `code-consistency` reuse rules so the cache-only **sweep** agent can cheaply flag heuristic signals ("new `*Service` mirrors an existing one") and **escalate** to the reuse stage rather than attempt the (impossible-for-it) local-codebase check. Run `/rebuild-agents` to re-embed.

### Shared reuse-discovery protocol

Extract the codebase-neutral core (capability extraction → grounding-resource catalog → verdict taxonomy → ledger shape → confidence gate) into a single file at a stable live path (e.g. `~/.claude/skills/_components/reuse-discovery-protocol.md`). `/spec`'s `reuse-first-discovery.md` references it (wrapping it with spec-design framing); the plugin's reuse agents are instructed to read it (wrapping it with PR-review framing). One source of truth, no drift.

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown (authored by `/spec-phases`). Intended ordering:

1. **Shared reuse-discovery protocol** — extract the protocol core; refactor `/spec`'s component to consume it. Lint + projection green. (Foundational; both downstreams depend on it.)
2. **Reuse-candidacy stage** — author the per-cluster reuse agent (grow `cognito-consistency-checker`); wire the parallel stage into `review-pr.md`; extend `aggregate-findings.ts` + `post-process.ts` for the `reuse` source; add `code-consistency` reuse rules + `/rebuild-agents`; update `synthesizer-v2.md` rendering. Verifiable via a `review-pr` run that surfaces a reuse finding.
3. **`review-pr-buddy` command** — author `commands/review-pr-buddy.md` (Phase 0 delegation, Phase 1 interactive walk, Phase 2 curated synthesis); session-state + recovery; human-curated synthesizer variant.
4. **Integration + docs** — update plugin `README.md` / `CLAUDE.md` / `marketplace.json`; end-to-end smoke test on a real PR.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|---|---|---|---|
| Shared protocol consumed by both consumers | Project skills + read reuse agent prompt | `/spec` reuse-first-discovery resolves the shared protocol; reuse agent instructed to read same file | `lint-skills.py` exit 0; projected `/spec`; reuse agent prompt |
| Reuse stage emits a verdict finding | `review-pr` on a PR that adds code duplicating an existing system | `processed-findings.json` contains a `source:"reuse"` finding with a `file:line` existing-system candidate + verdict | `{cacheDir}/agent-output/reuse-*.json`, `processed-findings.json`, review doc |
| Reuse stage runs in parallel, no serial latency | `review-pr` run | reuse agents dispatched alongside investigation/sweep, not after | `review-pr.md` step ordering; agent-output timestamps |
| `acceptable-new` carries a negative-search trail | reuse finding with `acceptable-new` verdict | finding includes the searched skills/docs/symbols that came back empty | reuse agent JSON output |
| Buddy pre-computes everything before the walk | `review-pr-buddy {pr}` | journey file + `processed-findings.json` exist before Phase 1's first prompt | `{cacheDir}`, chat transcript ordering |
| Buddy walks the journey's Manual Review Guide | during Phase 1 | each interactive chunk maps to a journey Manual Review Guide step | journey file vs. session transcript |
| Per-chunk verdicts are captured + recoverable | disposition findings, simulate compaction | `buddy-session.json` records dispositions; resume returns to the right chunk | `{cacheDir}/buddy-session.json` |
| Culminating doc is human-curated | finish a buddy session | `PR-{id}.md` contains only kept findings + reviewer observations, in synthesizer-v2 format | review artifact path |
| Sweep escalates reuse heuristics rather than asserting | `review-pr`, cache-only sweep hits a reuse heuristic | sweep emits an escalation (not a fabricated local-codebase claim) | sweep output, `knowledge/rules` reuse rule |

## Open Questions

- **Phase 0 reuse for the buddy** — does `review-pr-buddy` literally invoke the `review-pr` steps (single source of truth, preferred) or duplicate the orchestration? Resolve during Phase 3 authoring; preference is delegation.
- **consistency-checker disposition** — grow the orphaned `cognito-consistency-checker` in place into the reuse-stage agent, or supersede it with a new agent and delete it? Decide in Phase 2 after re-reading it against the reuse-discovery protocol.
- **Reuse verdict → severity mapping** in `post-process.ts` — the *lane* is resolved by the touchpoint audit (reuse findings follow the **investigation lane**: fixed `effective_weight: 1.0`, not EMA-weighted, not dropped by `MIN_EFFECTIVE_WEIGHT`, since they are Opus-agent-produced like investigation). What remains to tune is the verdict→severity boundary: `refactor`/`reuse` → important, `extend`/`wrap` → minor, `acceptable-new` → dropped. See PHASES.md Validated Assumption 2.

## Research References

None — research was explicitly skipped for this feature (`/spec (no research)`). The design is grounded in direct reading of the plugin source and the `/spec` reuse-first component across the originating brainstorm session.
