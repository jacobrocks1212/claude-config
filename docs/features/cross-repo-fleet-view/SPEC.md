# Cross-Repo Fleet Home Page — Feature Specification

> A multi-repo landing view for the existing `pipeline_visualizer`: one page answering "which
> repos have live runs, which are halted, what's queued where" across every lazy-enabled repo.
> The fleet layer is a **pure read** — it discovers repo roots (registry + live run markers),
> renders a per-repo status row from cheap on-disk reads (queue depth, run-marker freshness,
> halt sentinels), and links into the shipped per-repo visualizer views for drill-in. It never
> re-infers pipeline state, never deletes a marker, and adds no new write path.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:** (none)

> Formally no dep-block entries. Substantive dependencies are **implemented data contracts, not
> sibling specs**:
> - `user/scripts/pipeline_visualizer/` — the shipped stdlib server (`make_server`, routes
>   `/api/state` + `/api/queue`, `TtlCache`) and `probe.probe_state(repo_root)`, the pure-read
>   aggregate this feature extends. The fleet layer must not re-implement state inference.
> - Per-repo keyed state dirs `~/.claude/state/<repo_key>/` (`multi-repo-concurrent-runs`):
>   `lazy_core.repo_key()` is a one-way sha1 of the normalized realpath, so discovering repo
>   roots FROM keyed dirs relies on each run marker's recorded `repo_root` field
>   (`lazy_core.write_run_marker` stamps it).
> - `manifest.psd1` Repos scope — a candidate repo registry (evaluated and rejected as the
>   primary discovery source; see D1).
> - `LAZY_QUEUE.md` / `user/scripts/lazy-queue-doc.py` (`mobile-queue-control`, Complete) — the
>   GitHub-mobile peer channel onto the same state; the fleet page links to it, never replaces it.

---

## Executive Summary

`multi-repo-concurrent-runs` made concurrent `/lazy-batch` runs across repos a supported
configuration: run-scoped state is keyed per repo under `~/.claude/state/<repo_key>/`, and the
enforcement hooks scope by repo. But the observability surface did not follow — the shipped
`lazy-pipeline-visualizer` takes exactly one `--repo-root` (its SPEC explicitly deferred
"multi-repo switcher" to v2), so steering N concurrent runs today means N visualizer instances or
N terminal probes. There is no single surface for the fleet-level questions: which repos have live
runs, which are halted on `NEEDS_INPUT.md`/`BLOCKED.md`, what is queued where, and which run
markers are stale leftovers of a crashed run.

This feature adds that surface as a **fleet home page inside the existing visualizer server**: a
`--fleet` serving mode whose landing page shows one row per lazy-enabled repo (run
active/idle/stale, queue depths, halt counts) and links into the current per-repo three-pane view.
The fleet row is deliberately **shallow** — queue.json reads, a raw (non-deleting) run-marker
read, and sentinel *presence* checks, the same class of plain-stat read `probe.receipt_present`
already uses — so the landing page never pays N-repos × M-items × state-script-subprocess cost.
The full `probe_state` probe runs only for the repo whose drill-in view is open, exactly as today.

Mission criteria served: **efficient** (one control plane instead of N instances; the fleet poll
costs file stats, not subprocess fan-out) and **effective** (stale markers and halted items are
surfaced honestly instead of discovered hours later — the same time-to-notice gap
`operator-halt-notifications` attacks from the push side; this feature is the pull side).

## Design Decisions

### D1. Repo-root discovery mechanism

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** Which repos appear on the fleet page? The keyed state dirs cannot be enumerated
  back to roots (`repo_key` is a one-way sha1), a live marker exists only while a run is live, and
  the operator needs idle repos listed too.
- **Options:**
  - **A — Registry convention + live-marker union:** reuse the `mobile-queue-control` Decision 2
    convention verbatim — auto-discover `~/source/repos/*/docs/{features,bugs}/queue.json`, with
    an optional `~/.claude/lazy-repos.json` pins/excludes override — then UNION the roots recorded
    in live run markers (scan `~/.claude/state/*/lazy-run-marker.json`, read each marker's
    `repo_root` field raw). Pros: consistent with the established convention; idle repos found;
    a live run outside `~/source/repos` still appears. Cons: two sources to merge; the
    `lazy-repos.json` file does not exist yet (mobile-queue-control specified it but shipped
    without needing it — this feature would be its first real consumer).
  - **B — `manifest.psd1` Repos scope as the registry:** parse the symlink manifest's `Repos`
    map. Pros: an existing, versioned registry. Cons: it registers repos by `.claude/`-config
    presence, not lazy-enablement — today it lists the Cognito work repos (plus worktree aliases
    B/C/D), none of which carry `docs/features/queue.json`, while lazy-enabled repos need no
    manifest entry at all. Wrong proxy in both directions, plus a PSD1 parse from Python.
  - **C — State-dir markers only:** enumerate `~/.claude/state/*/` and read marker `repo_root`s.
    Pros: zero configuration. Cons: catches live-run (or recently-crashed) repos only; an idle
    lazy-enabled repo is invisible, which defeats "what's queued where".
- **Recommendation:** A — it is the convention the operator already ratified for the sibling
  channel (mobile-queue-control Decision 2), it covers idle repos, and the marker union closes
  A's only structural gap (a run in a nonstandard root). The manifest is demonstrably the wrong
  proxy (verified against the current `manifest.psd1`: its Repos scope is Cognito-only).
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D2. Serving model — one `--fleet` instance vs per-repo instances

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** The CLI today takes one `--repo-root`. How does the operator launch and navigate
  the multi-repo view?
- **Options:**
  - **A — One instance, `--fleet` mode:** `python -m pipeline_visualizer --fleet` serves the
    fleet home at `/` and nests the existing per-repo views under `/repo/<slug>/…` (same handler
    code, parameterized by the row's repo root). `--repo-root` mode stays byte-identical for
    single-repo use. Pros: one process, one port, one bookmark; drill-in is a link, not a second
    launch. Cons: the per-repo handlers must become repo-parameterized (today `repo_root` is
    closed over in `make_server`), and the marker read must drop the module-level
    `set_active_repo_root` binding to stay race-free across threads (see Technical Design).
  - **B — Fleet aggregator + N per-repo instances:** a fleet page that links to separately
    launched `--repo-root` servers. Pros: zero change to the shipped per-repo server. Cons:
    reintroduces the exact N-instances problem the stub names; link targets depend on N ports
    being up; dead links when an instance isn't running.
- **Recommendation:** A — the stub's stated direction is "a home page in the existing
  `pipeline_visualizer` server, linking into the current per-repo views", and B fails the
  feature's own problem statement. The handler parameterization is mechanical (the closure
  becomes a lookup keyed by URL slug).
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation (the launch/URL
  shape is operator-visible).

### D3. Staleness display for dead/stale run markers

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** A run marker whose owning run crashed is on disk until something reclaims it
  (`lazy_core.read_run_marker` deletes at the 24h age gate — but only when *that* code path runs
  in that repo). What does the fleet page show for such a repo, and does the read view ever
  reclaim?
- **Options:**
  - **A — Graded age, honest three-state badge, never delete:** every fleet row shows one of
    `run-active` (marker present, age below a warn threshold), `run-silent` (marker present, age
    past the warn threshold but below 24h — "live run or wedged, look closer"), `stale-marker`
    (age ≥ 24h, the same boundary the state scripts treat as presumed-dead), or `idle` (no
    marker). Marker age is always displayed. The fleet read NEVER deletes a marker — reclamation
    stays exclusively script-owned. Pros: honest; aligns the stale boundary with
    `read_run_marker`'s documented 24h rule instead of inventing a second staleness definition.
    Cons: the warn threshold is a new displayed number the operator must interpret.
  - **B — Binary fresh/stale at 24h only:** marker present+fresh = active, present+old = stale.
    Pros: simplest, exactly mirrors script semantics. Cons: a run wedged for 6 hours renders
    indistinguishable from a healthy one — the fleet page's whole point is noticing that.
  - **C — Hide stale markers:** render `idle` once past 24h. Pros: clean page. Cons: dishonest —
    a read view silently masking an anomalous on-disk state contradicts the harness's
    honest-halts posture.
- **Recommendation:** A, with the warn threshold defaulting to 2h and read from config (the
  marker's `started_at` plus per-cycle activity is not directly readable without deeper probes,
  so age-since-`started_at` is the v1 signal; a finer "last cycle activity" signal is a
  documented vN upgrade). Never-delete is non-negotiable for a read view.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation (the badge taxonomy
  and threshold are operator-visible).

### D4. Fleet page shape

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** What does the landing page actually show per repo, and where do the links go?
- **Options:**
  - **A — Compact table only:** one row per repo — repo name, run badge (D3), features queued,
    bugs queued, halt count — linking to the per-repo view.
  - **B — Table + cross-repo triage strip:** the A table, plus a persistent "Needs attention"
    strip listing every halted item across all repos (repo-prefixed), mirroring the per-repo
    visualizer's triage strip and `LAZY_QUEUE.md`'s "Needs attention" section. Each row links to
    the per-repo view; halt entries deep-link to the item. A secondary link per row opens the
    repo's `LAZY_QUEUE.md` on GitHub when the repo has one.
  - **C — Per-repo mini-graphs:** thumbnail two-track graphs per repo. Pros: visual. Cons: pays
    the full probe per repo on the landing page — exactly the aggregation cost D5 avoids — for
    signal the drill-in already provides.
- **Recommendation:** B — the triage strip is the highest-value fleet signal (a halted item in
  repo 3 of 6 must not require six drill-ins to find), it is computable from the shallow probe
  (sentinel presence + item id), and it reuses a layout pattern the operator already reads in two
  sibling surfaces.
- **Resolution:** OPEN — recommendation is B; awaiting operator confirmation.

### D5. Fleet-row probe strategy and aggregation cost

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** `probe_state` shells one state-script subprocess **per queue item**
  (`probe._run_state_script`, timeout 60s each). A naive fleet poll of N repos × M items × 2
  pipelines is seconds-to-minutes of subprocess fan-out per refresh — the stub's "performance
  with many repos" question.
- **Options:**
  - **A — Shallow fleet rows + on-demand full probe:** the fleet row reads only `queue.json`
    (both pipelines), the raw run marker, and per-item halt-sentinel *presence*
    (`NEEDS_INPUT.md` / `BLOCKED.md` stat in each queued item's dir — the `receipt_present`
    plain-stat precedent, presence not parsing). No state script is shelled on the fleet poll.
    The full `probe_state` runs only for the repo whose `/repo/<slug>/` view is open, behind its
    existing per-repo `TtlCache`. Shallow fan-out across repos runs in a
    `concurrent.futures.ThreadPoolExecutor` (stdlib) with a distinct fleet TTL (~5s).
  - **B — Full probe per repo, cached hard:** run `probe_state` for every repo on a long TTL.
    Pros: richer rows (curated stage per item). Cons: cost scales with fleet size and queue
    depth; a 60s hung item wedges the poll; the extra fidelity is one click away anyway.
- **Recommendation:** A — the fleet page's questions (active? halted? how deep?) are answerable
  from presence checks; per-item stage fidelity belongs to the drill-in, which already has it.
  Reuses `probe.read_queue` and the `receipt_present` read pattern; adds zero subprocess load to
  the landing page.
- **Resolution:** Auto-accepted A; probe internals and caching are invisible so long as the
  rendered data is honest (the row shows depth + halts, and labels itself as shallow).

### D6. Read-only guarantee of the fleet layer

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Does the fleet home expose any write?
- **Options:**
  - **A — Fleet layer is pure read:** no new POST routes; the fleet page renders and links. The
    per-repo drag-reorder write (`POST /api/queue`, run-marker-refused, shipped in
    `lazy-pipeline-visualizer` Decision 11) remains available only inside the per-repo drill-in
    view, unchanged.
  - **B — Fleet-level writes (cross-repo reorder, marker cleanup):** rejected — marker deletion
    from a read view is exactly what D3 forbids, and cross-repo mutation has no consumer.
- **Recommendation:** A — the stub's direction line is operator-set ("pure read over
  `probe_state`, never re-inferring state") and nothing in the fleet use case needs a write.
- **Resolution:** Auto-accepted A; this restates a stub constraint rather than opening one.

### D7. Repo identity in URLs and payloads

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What token identifies a repo in `/repo/<slug>/…` routes and `/api/fleet` rows?
- **Options:**
  - **A — Basename slug, server-owned mapping:** slug = repo dir basename (kebab-cased), with a
    short `repo_key` prefix appended only on basename collision; the slug→root map lives in the
    server process and `/api/fleet` carries both `slug` and `repo_root`.
  - **B — Raw `repo_key`:** 40-hex URLs. Unreadable, and invites re-deriving the key outside
    Python (the key derivation is documented as Python-only).
- **Recommendation:** A — human-legible, collision-safe, and keeps `repo_key` derivation inside
  `lazy_core` where it belongs.
- **Resolution:** Auto-accepted A; internal naming with no behavioral implication beyond URL
  cosmetics.

## User Experience

```bash
# One instance for the whole fleet (D2-A):
python -m pipeline_visualizer --fleet            # serves http://127.0.0.1:8765/
# Existing single-repo mode, byte-identical:
python -m pipeline_visualizer --repo-root <repo>
```

The landing page (D4-B recommendation):

```
Lazy Fleet                                                    refreshed 3s ago

| repo           | run                      | features | bugs | needs attention |
|----------------|--------------------------|----------|------|-----------------|
| claude-config  | 🔒 active (12m)          | 7        | 2    | 1 ⬡             |
| algobooth      | idle                     | 4        | 0    | —               |
| strudel        | ⚠ stale marker (26h)     | 2        | 1    | 1 ⛔            |

Needs attention (all repos)
- ⬡ claude-config / waveform-zoom — NEEDS_INPUT.md present
- ⛔ strudel / marker-race-disarm — BLOCKED.md present
```

- Clicking a repo row opens the shipped three-pane per-repo view at `/repo/<slug>/` (graph,
  queues with guarded drag-reorder, fleet pane) — the full `probe_state` fidelity.
- A `stale marker` badge (D3) names the marker age and the state dir path; it is information,
  not an action — the page offers no delete button (reclamation is script-owned).
- Repos with a committed `LAZY_QUEUE.md` get a phone icon linking to it on GitHub, tying the
  desktop and GitHub-mobile channels together.
- Failure honesty: a repo whose shallow probe errors (unreadable queue.json, permission error)
  renders an explicit error row, never a silently-omitted repo — same posture as the per-repo
  view's "Connection Lost" banner.

## Technical Design

```
discovery (D1)                      fleet shallow probe (D5)             fleet home
 ~/source/repos/*/docs/**/queue.json ─┐   queue.json (F+B) ──read──┐
 ~/.claude/lazy-repos.json (pins/excl)├─▶ per repo: raw marker read ├─▶ GET /api/fleet ─▶ table +
 ~/.claude/state/*/lazy-run-marker.json┘  halt-sentinel stat        │      (TTL ~5s)      triage
        (marker.repo_root, raw read)                                │
                                          drill-in: probe_state ────┘  GET /repo/<slug>/api/state
                                          (existing, per-repo TtlCache)     (existing contract)
```

- **New module `user/scripts/pipeline_visualizer/fleet.py`** (stdlib-only, like the rest of the
  package): `discover_repos()` implementing D1 (glob + `lazy-repos.json` pins/excludes + marker
  union, normalized/deduped via realpath), `read_marker_raw(repo_root)` (below), and
  `fleet_row(repo_root)` returning `{slug, repo_root, marker: {present, age_seconds, badge,
  pipeline, work_branch}, features: {depth, halts:[{id, kind}]}, bugs: {…}, lazy_queue_doc:
  bool, error}`.
- **Raw marker read — never `read_run_marker`.** `lazy_core.read_run_marker` is DELETE-ON-READ at
  its 24h age gate (staleness path A) — correct for the state machine, forbidden for a read view
  (D3). The fleet reads the marker file raw: path composed as
  `~/.claude/state/<lazy_core.repo_key(repo_root)>/lazy-run-marker.json`, JSON-parsed, never
  written, never deleted. This follows the existing raw-read precedent
  (`write_run_checkpoint` reads the marker raw for exactly this reason) and also sidesteps the
  module-level `set_active_repo_root` binding, which is not safe to flip per-request under
  `ThreadingHTTPServer` when multiple repos are served from one process. The existing
  single-repo `server._run_marker_present` path is untouched in `--repo-root` mode; in `--fleet`
  mode the per-repo `queue_locked` / reorder-refusal check switches to the same raw keyed-path
  read (presence + freshness only, still no delete) so two repos' requests cannot race the
  binding. `claude_state_dir` is not called with its default `create=True` from any fleet read —
  a read view must not create state dirs.
- **Server routing (D2-A):** `make_server` gains a fleet mode: `/` → fleet home page (new static
  asset), `/api/fleet` → aggregated `fleet_row` list (own `TtlCache`, fleet TTL ≥ the per-repo
  2.0s `DEFAULT_TTL_SECONDS`), `/repo/<slug>/api/state|queue` and `/repo/<slug>/…` static →
  the existing handlers with `repo_root` resolved from the slug map instead of the closure. One
  `TtlCache` per repo for the heavy probe (allocated lazily on first drill-in). Single-repo mode
  (`--repo-root`) constructs exactly today's handler — byte-identical behavior, guarded by the
  existing `test_pipeline_visualizer.py` suite.
- **Shallow halt detection:** presence-stat of `NEEDS_INPUT.md` / `BLOCKED.md` in each queued
  item's `spec_dir` (resolved the same way `probe._item_dir` falls back:
  `<pipeline_dir>/<spec_dir or id>`). Presence, not parsing — no schema logic is duplicated, no
  state is re-inferred; the authoritative interpretation stays in the state scripts and is one
  drill-in click away.
- **House invariants honored:** pure-read renderer over script-owned state (no inference, no
  queue writes from the fleet layer); no marker deletion from a read path; stdlib-only Python;
  per-repo keyed state dirs respected via `lazy_core.repo_key` (never re-derived outside
  Python); the one existing guarded write (per-repo reorder) keeps its run-marker refusal and
  atomic `os.replace` path unchanged; fail-open display (a broken repo degrades to an error row,
  never crashes the fleet poll — mirroring `parse_state_output`'s per-item error flagging).

## Implementation Phases

- **Phase 1 — Discovery + shallow probe library.** `fleet.py`: `discover_repos()` (D1),
  `read_marker_raw()`, `fleet_row()` (D5). Proven by pytest fixtures in
  `test_pipeline_visualizer.py` (temp repos with queue.json/sentinels/markers; a ≥24h-old marker
  fixture asserting the file still exists after the read).
- **Phase 2 — `--fleet` serving mode.** `__main__.py` flag; `make_server` fleet routing +
  slug-parameterized per-repo handlers; `/api/fleet` behind its TTL cache; raw keyed-path marker
  read for per-repo `queue_locked` in fleet mode. Proven by server tests: `/api/fleet` JSON
  shape; `/repo/<slug>/api/state` equals the single-repo `/api/state` for the same root;
  `--repo-root` mode byte-identical (existing suite green, no fixture edits).
- **Phase 3 — Fleet home frontend.** Static fleet page (table + triage strip + badges + links,
  D3/D4), no build step, same asset conventions as `static/`. Proven by rendering against a
  multi-repo fixture and the validation table below.
- **Phase 4 — Aggregation hardening.** Parallel shallow fan-out (`concurrent.futures`), per-repo
  error rows, fleet-TTL tuning, `LAZY_QUEUE.md` link detection. Proven by a many-repo fixture
  (≥10 temp repos) keeping the fleet poll under a bounded wall-time with zero state-script
  subprocesses spawned (assert via a monkeypatched `probe._run_state_script` call counter).

Estimate: ~2-3 sessions (Phases 1-2 one session; 3-4 one to two).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Discovery matches D1 | Fixture home with registry repos + a live marker for an out-of-tree root | Union of both sources, deduped; excludes honored | `test_pipeline_visualizer.py` fleet fixtures |
| Stale marker honest + preserved | Fleet poll over a repo with a ≥24h-old marker | Row shows `stale-marker` + age; marker file still on disk after N polls | Test asserts file mtime/existence unchanged |
| Queue depths accurate | Fleet row vs known queue.json contents | Depths equal `len(queue)` per pipeline | Fixture comparison |
| Halt triage accurate | Item dir carries `NEEDS_INPUT.md` or `BLOCKED.md` | Item listed in the cross-repo triage strip with repo prefix | Fixture comparison |
| No subprocess on fleet poll | Poll `/api/fleet` repeatedly | Zero `_run_state_script` invocations | Monkeypatched call counter |
| Single-repo mode unchanged | Run existing suite with no `--fleet` | All existing `test_pipeline_visualizer.py` tests green, unmodified | pytest |
| Fleet layer read-only | Attempt POST to any fleet route | 404/405; only `/repo/<slug>/api/queue` accepts POST, still marker-refused | Server test |
| Drill-in fidelity | Open `/repo/<slug>/` | Full `probe_state` payload identical to single-repo mode | Server test |

## Open Questions

- **D1 — repo discovery:** registry convention (`~/source/repos/*/docs/{features,bugs}/queue.json`
  auto-discover + `~/.claude/lazy-repos.json` pins/excludes) unioned with live-marker `repo_root`
  scan? Standing recommendation: yes (option A) — consistency with mobile-queue-control
  Decision 2; manifest.psd1 rejected as a wrong-proxy registry.
- **D2 — serving model:** single instance with `--fleet` mode and nested `/repo/<slug>/` views
  (option A), vs per-repo instances behind an aggregator? Standing recommendation: A.
- **D3 — staleness display:** graded three-state badge (active / run-silent past a ~2h warn
  threshold / stale-marker at the script-aligned 24h boundary) with age always shown and
  never-delete (option A)? Standing recommendation: A.
- **D4 — page shape:** compact table plus a cross-repo "Needs attention" triage strip and
  GitHub `LAZY_QUEUE.md` links (option B)? Standing recommendation: B.
- Deferred empirical checks (implementation-time, not decisions): actual shallow-poll wall time
  at realistic fleet size (the ≥10-repo fixture, Phase 4); whether `~/.claude/lazy-repos.json`
  needs a `pins` list at all in practice or only `excludes` (schema finalized when first
  written); slug-collision frequency across the operator's real repo set (D7 fallback).

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: the shipped `pipeline_visualizer` contracts and the
  mobile-queue-control discovery convention; delete-on-read marker semantics drove the raw-read
  design.
- `docs/features/lazy-pipeline-visualizer/SPEC.md` — the shipped per-repo design this extends
  (its Decision 8 explicitly deferred multi-repo to v2; this is that v2).
- `docs/features/mobile-queue-control/SPEC.md` — Decision 2 (repo auto-discovery convention);
  the peer-channel framing ("cross-repo aggregate index is a possible later add").
- `user/scripts/CLAUDE.md` — per-repo keyed state dir, `repo_key`, run-marker staleness rules.
