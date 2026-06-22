# Lazy Queue Status Doc (GitHub-Mobile Readable) — Feature Specification

> An auto-generated, always-current, **read-only** markdown document — one per lazy-enabled repo — that renders the repo's lazy feature + bug queue (with per-item drill-in) on **GitHub mobile**. Generated purely from on-disk lazy state and kept up to date as the pipeline progresses. **Reads happen on GitHub mobile; writes (reorder / remove / enqueue) stay in chat** via the existing `--reorder-queue` / `--enqueue-adhoc` CLI — nothing new is built for writes.

**Status:** Complete
**Priority:** P2
**Last updated:** 2026-06-22

**Depends on:** (none)

> Formally no dep-block entries (this repo's specs carry no `queue.json` dependency graph, per the sibling `lazy-pipeline-visualizer` SPEC). Substantive (non-block) dependencies are **implemented data contracts**, not sibling specs:
> - `lazy-state.py` / `bug-state.py` CLI read ops (`--probe`, `--feature-id`/`--bug-id`, `--next-merged`), all `--repo-root`-addressable. The generator is a **pure read renderer** over this contract; it must not re-implement state inference.
> - `docs/features/queue.json` + `docs/bugs/queue.json` per repo (schema: `id`, `name`, `spec_dir`, `tier`/`severity`, `adhoc`, `stub`, `independent`).
> - Per-item docs at `docs/{features,bugs}/<spec_dir>/SPEC.md` — linked from the generated doc (GitHub renders them natively).
> - **Peer, not dependency:** `lazy-pipeline-visualizer` is the desktop/browser channel onto the same state. This feature is the GitHub-mobile read channel; the two coexist.
> - **Writes are out of scope (already solved):** reorder/remove/enqueue run through the existing run-marker-safe state-script CLI, driven from chat. This feature builds no write path.

---

## Executive Summary

Jacob runs autonomous lazy pipelines (features + bugs) across many repos and steers them from his phone. He already does *writes* from his phone — he asks a workstation Claude session to reorder/enqueue, which calls the existing run-marker-safe state-script CLI. What he's missing is a good **read** surface: a way to see each repo's queue, and drill into what each queued item actually *is*, from his phone.

His phone already renders any committed markdown beautifully via **GitHub mobile**. So the solution is to **generate a read-only status document per repo** — committed into the repo — that GitHub mobile displays. The document is produced **purely from on-disk lazy state** (queue.json + the state scripts' JSON + the SPEC docs), so the generator is a pure function of doc state and can run anytime. It is kept current by being **regenerated as the lazy pipeline progresses** (trigger + publish mechanism — Decision 6), so what he reads on GitHub mobile tracks reality without manual refresh.

Drill-in leverages GitHub's native rendering: each queue item shows a **curated summary inline** plus a **link to its full `SPEC.md`**, which GitHub mobile renders on tap (Decision 7). The generator never re-infers state and never writes `queue.json`; it only reads state and writes its own document.

## Locked Decisions

**Round 1 — channel & scope foundations**
1. **Read channel — an auto-generated read-only document per repo, read on GitHub mobile.** (Refined from "chat-native view": the *view* is a committed doc on GitHub mobile, not a chat render.) **Write channel — chat, via the existing CLI; nothing new built.**
2. **Per-repo doc generation, auto-discovered.** Each lazy-enabled repo gets its own doc. Repo set = auto-discover `~/source/repos/*/docs/{features,bugs}/queue.json` with an optional `~/.claude/lazy-repos.json` override (pins/excludes). (The doc lives *in* each repo; "all my repos" = navigate to each repo on GitHub mobile. A cross-repo aggregate index is a possible later add, not v1.)
3. **Drill-in — curated summary inline + link to full SPEC.md.** (Refined for the GitHub-mobile channel: "expand" = a markdown link GitHub renders natively, rather than a chat command.)
4. **Write scope is reorder + remove + enqueue ad-hoc** — but all three already exist as CLI ops driven from chat, so this feature implements **no write path**. The capability stands; the implementation is already done.
5. ~~Chat-view layout~~ → **superseded by the generated-doc layout** (Decision 1 pivot). The per-repo grouped, compact shape (features then bugs, one line per item, reorder index, triage signal in the header) carries over as the *document's* layout.

**Round 2 — refresh & drill-in mechanics (post-pivot)**
6. **Refresh + publish — pipeline-integrated.** The generator runs at each lazy cycle boundary and the doc is committed within the pipeline's existing commit. **Scope: claude-config + AlgoBooth**, both of which work on, commit to, and push to `main` — so the doc lands on the default branch and GitHub mobile shows it without branch-switching, and the existing push cadence publishes it. (The work-branch / push-blocked concern that argued against pipeline-integration does not apply to these two repos.) The generator stays a pure function of doc state, so it remains runnable standalone for any other repo.
7. **Drill-in — inline curated summary + link to full SPEC.md.** Each row shows the curated summary (status, phase N/M, next action, one-line exec summary) and links the item name to its `SPEC.md`, which GitHub mobile renders on tap.

> **Doc path:** root-level `LAZY_QUEUE.md` per repo (one-tap discoverability + easy bookmark on GitHub mobile).

## User Experience

### The document (per repo)
A single root-level `LAZY_QUEUE.md` committed in each lazy-enabled repo, laid out as the Round-1 per-repo grouped view:

```
# Lazy Queue — <repo>            (run active 🔒 | idle)

## Features (N)
| # | item | state | tier | |
|---|------|-------|------|--|
| 1 | [d8-effect-chains](docs/features/d8-effect-chains/SPEC.md) | ▶ implement | T1 | |
| 2 | [mixer-automation](docs/features/mixer-automation/SPEC.md) | ◷ spec | T1 | |
| 3 | [waveform-zoom](docs/features/waveform-zoom/SPEC.md) | ⬡ needs-input | T2 | |

## Bugs (M)
| # | item | state | sev | |
|---|------|-------|-----|--|
| 1 | [marker-race-disarm](docs/bugs/marker-race-disarm/SPEC.md) | ▶ execute | P1 | |

## Needs attention
- ⬡ waveform-zoom — needs-input
```

- **Per-item drill-in:** each row links to the item's `SPEC.md` (GitHub mobile renders it). A curated summary may also be inlined (Decision 7).
- **Triage signal:** a "Needs attention" section mirrors Blocked / Needs-Input items (the `/lazy-status` triage signal), so a stalled item isn't buried.
- **Freshness signal:** the doc carries a run-active/idle marker (`🔒`/idle) so a live run is self-evident. It embeds **no** wall-clock timestamp — "last updated" is read from GitHub's native last-commit time for `LAZY_QUEUE.md` (operator decision 2026-06-22, NEEDS_INPUT.md Decision 1 → option (a)). Dropping the embedded wall-clock keeps regeneration byte-stable (an unchanged-state regen is byte-identical → no spurious commit, satisfying the Phase 3 no-op-commit gate with zero special-casing).

### Reading flow
Open the repo on GitHub mobile → the doc renders → tap an item to read its SPEC.md. To change order, switch to the Claude app and ask the session to reorder (existing behavior).

## Technical Design

```
on-disk lazy state                generator (pure read)              committed doc            GitHub remote
 queue.json (F + B)   ──read──▶   reads state, emits markdown  ──▶  ./LAZY_QUEUE.md (root)  ──push──▶  GitHub mobile
 lazy-state.py JSON   ──read──▶   (never re-infers, never                                   (publish:
 bug-state.py JSON                 writes queue.json)                                        Decision 6)
 SPEC.md docs        ──link──▶   row links → SPEC.md
```

- **Pure-read generator.** A stdlib Python script (sibling to `lazy-state.py`) that, given `--repo-root`, shells the existing state scripts for JSON, reads `queue.json`, resolves `spec_dir` → SPEC paths, and emits the markdown doc. It is a pure function of doc state — runnable standalone at any time. It never re-implements inference and never mutates `queue.json`.
- **Trigger + publish — pipeline-integrated (Decision 6).** The generator is invoked at each lazy cycle boundary (orchestrator/state-script post-transition), regenerates `LAZY_QUEUE.md`, and stages it so it rides the cycle's **existing commit**. Because the target repos (claude-config, AlgoBooth) work on and push to `main`, the doc lands on the default branch and the existing push publishes it to the GitHub remote — no extra commits, no separate process. Byte-stable generation means an unchanged doc produces no diff and adds nothing to the commit.
- **Scope.** v1 wires this into claude-config + AlgoBooth (both main-based + pushed). The generator remains a pure, `--repo-root`-addressable function of doc state, so any other repo can produce the doc on demand (e.g. via the desktop visualizer or a manual run) even without the pipeline hook.
- **No new infrastructure** beyond the generator script and its pipeline hook: no server, port, tunnel, or auth. The write path is untouched (existing CLI + chat).

## Implementation Phases

- **Phase 1 — Pure-read generator.** Script reads state (F + B), resolves SPEC paths, emits the per-repo grouped `LAZY_QUEUE.md` (with triage section + run-active/idle marker; no embedded wall-clock — freshness is git commit time). Idempotent; byte-stable when state is unchanged.
- **Phase 2 — Drill-in rendering.** Per-item rows: inline curated summary (status, phase N/M, next action, one-line exec summary) + SPEC.md link, per Decision 7.
- **Phase 3 — Pipeline-integrated trigger.** Invoke the generator at each lazy cycle boundary in claude-config + AlgoBooth; stage `LAZY_QUEUE.md` so it rides the cycle's existing commit on `main`; verify byte-stable no-op when unchanged and an honest freshness/run-active marker.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Doc reflects queue state | Generate against a repo with known states | Each item's row state matches `lazy-state.py`/`bug-state.py` JSON | Compare doc to state JSON |
| Byte-stable when unchanged | Re-run generator with no state change | Doc unchanged (no spurious diff/commit) | Diff successive generations |
| SPEC links resolve | Tap a row on GitHub mobile | The item's SPEC.md renders | GitHub mobile navigation |
| Triage section accurate | A repo has a blocked/needs-input item | Item appears under "Needs attention" | Compare to sentinels |
| Stays current as pipeline runs | Advance an item a stage | Doc (and remote, where pushable) updates within the trigger window | State diff + git commit time |
| Freshness marker honest | Read during/after a run | Run-active/idle marker matches reality (no embedded wall-clock; freshness is git commit time) | Marker vs run-marker presence |

## Open Questions
- **GitHub mobile relative-link behavior** — confirm that relative links to `docs/.../SPEC.md` render and navigate correctly in the GitHub mobile app's markdown viewer (a quick empirical check, not deep research). If relative links misbehave, fall back to absolute `github.com/<owner>/<repo>/blob/main/...` links.
- Exact cycle-boundary hook point for the generator (orchestrator post-cycle vs state-script side-effect) — a `/spec-phases` integration detail.
- Whether a cross-repo aggregate index doc is wanted later (v1 is per-repo only).
- Whether the desktop `lazy-pipeline-visualizer` should link to / surface the generated doc (assume coexist for v1).

## Research References
- **Gemini deep research intentionally skipped** (operator decision, 2026-06-22) — internal harness tooling with negligible external prior art; design is fully grounded in the existing `lazy-state.py`/`bug-state.py` + visualizer system. See `RESEARCH.md` for the skip record and the one empirical check deferred to implementation (GitHub-mobile relative-link behavior).
- Sibling: `docs/features/lazy-pipeline-visualizer/SPEC.md` (desktop channel onto the same state).
