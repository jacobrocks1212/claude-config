# Research — Cross-Repo Fleet Home Page

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **`user/scripts/pipeline_visualizer/`** — the entire per-repo layer already exists and is the
  substrate: `probe.probe_state(repo_root)` (pure read, shells `lazy-state.py --feature-id` /
  `bug-state.py --bug-id` per queue item, attaches display-only `curated_stage`),
  `server.make_server` (ThreadingHTTPServer, routes `/api/state` + `/api/queue` GET/POST,
  static assets rooted at `static/`), `cache.TtlCache` (`DEFAULT_TTL_SECONDS = 2.0`,
  double-checked lock). Its SPEC (Decision 8) locked "single project via `--repo-root`;
  multi-repo is v2" — this feature is that deferred v2, so extending in place (not a parallel
  tool) is the consistent move.
- **Probe cost shape** — `probe._run_state_script` spawns one Python subprocess per queue item
  with a 60s timeout. This is what makes a naive N-repo full probe unacceptable on a landing
  page and drove the shallow-row design (SPEC D5). The package already contains the cheap-read
  precedent: `probe.receipt_present` is documented as "a presence check only … a plain stat …
  never re-infers state" — the fleet halt-sentinel stat is the same class of read.
- **Per-repo keyed state dirs** (`multi-repo-concurrent-runs`) — `lazy_core.repo_key(repo_root)`
  (sha1 of normalized realpath, one-way; `lazy_core.py:6597`), `claude_state_dir()` (note the
  `create=True` default — a read view must avoid it), and `write_run_marker` recording
  `"repo_root": str(repo_root)` in the marker (`lazy_core.py:9353`). The recorded `repo_root` is
  the ONLY way back from a keyed dir to a root, which shaped D1's marker-union discovery leg.
- **Marker read semantics** — `lazy_core.read_run_marker` (docstring at `lazy_core.py:9402`)
  is DELETE-ON-READ at the 24h age gate (staleness path A). The in-repo precedent for avoiding
  it on a non-lifecycle read already exists: `write_run_checkpoint` reads the marker raw
  precisely because "read_run_marker … would delete a stale marker" (user/scripts/CLAUDE.md).
  The fleet layer adopts the same raw read, which also avoids flipping the module-level
  `set_active_repo_root` binding per request — `server._run_marker_present` binds the active
  repo on every check, which is fine for one closed-over repo but a data race if flipped
  per-request across threads in a multi-repo server.
- **`mobile-queue-control` (Complete)** — Decision 2 established the repo-discovery convention
  (auto-discover `~/source/repos/*/docs/{features,bugs}/queue.json`, optional
  `~/.claude/lazy-repos.json` pins/excludes) and explicitly deferred "a cross-repo aggregate
  index" as "a possible later add, not v1". The fleet page is the browser-channel realization of
  that deferred aggregate; reusing its discovery convention is consistency, not invention.
  `LAZY_QUEUE.md` (root-level, per repo) is the peer GitHub-mobile channel the fleet page links
  out to.
- **`manifest.psd1` Repos scope** — evaluated as a discovery registry and rejected with direct
  evidence: the current manifest's `Repos` map contains `cognito-forms` (+ B/C/D worktree
  aliases) and `cognito-docs` — repos registered for `.claude/`-config symlinks, none
  lazy-enabled — while lazy-enabled repos need no manifest entry. Wrong proxy in both
  directions.
- **Halt surfacing precedents** — the per-repo visualizer's triage strip ("Action Required" bar)
  and `LAZY_QUEUE.md`'s "Needs attention" section both mirror Blocked/Needs-input items; the
  fleet triage strip (D4-B) is the cross-repo lift of the same pattern, and
  `operator-halt-notifications` (being fleshed in parallel) is the push-side complement — the
  fleet page is the pull-side surface for the same time-to-notice problem.

## External prior art & concepts

Training-knowledge, not live research:

- **Multi-project CI dashboards** (GitLab operations/environments dashboards, Jenkins Blue Ocean
  multi-pipeline views, Buildkite pipeline listings): the settled pattern is exactly a
  rows-of-projects landing page — status badge, counts, last-activity age — with drill-in to the
  single-project view; nobody renders N full pipeline graphs on the landing page. Supports
  D4-B/D5-A.
- **Staleness display in fleet tooling** (Kubernetes node `NotReady` + age, Nomad client
  heartbeat status, Prometheus `up`/staleness marking): honest aging badges with the raw age
  shown, and a hard rule that monitoring reads never mutate the state they observe. Supports
  D3-A's graded badge + never-delete.
- **Registry + live-discovery union** (Prometheus static_configs + service discovery; Terraform
  workspaces listing): combining a declared registry with runtime-discovered members, deduped by
  canonical identity, is the standard answer to "declared set vs actually-running set" — the
  D1-A shape.

## Alternatives analysis

- **Discovery (D1):** manifest.psd1 loses on proxy accuracy (verified Cognito-only); state-dir
  scan alone loses idle repos (the marker exists only during/after a run, and a cleanly-ended
  run deletes it at `--run-end`); a hardcoded repo list in a new config loses to the
  already-ratified `lazy-repos.json` convention. Registry-convention ∪ marker-scan covers idle +
  out-of-tree-live with one dedup pass over realpaths.
- **Serving model (D2):** N per-repo instances fail the problem statement (the stub exists
  because N instances is the pain); a separate fleet binary duplicates the server plumbing the
  package already has. In-place `--fleet` mode costs a handler parameterization (closure → slug
  map) and buys one process/port/bookmark. Single-repo mode stays byte-identical, so the blast
  radius is additive.
- **Staleness (D3):** the key insight is that the harness already has a canonical staleness
  boundary (24h in `read_run_marker`) — the display should align with it, not invent a second
  definition; the graded warn threshold below it is display-only and clearly labeled. Deleting
  from the read view was never on the table (reclamation is script-owned; the 2026-06-12
  silent-disarm-by-delete incident is the cautionary tale for reads that mutate markers).
- **Aggregation cost (D5):** measured shape, not speculation: full probe = one subprocess per
  item (60s timeout each), so a 6-repo × 10-item fleet is ~120 potential subprocess spawns per
  refresh vs zero for shallow rows. Shallow rows answer the fleet questions; stage-level
  fidelity is already one click away behind the existing per-repo TTL cache.

## Pitfalls & risks

- **Silent repo omission.** A discovery bug that drops a repo makes the fleet page lie by
  omission — worse than no fleet page. Mitigated by per-repo error rows (a failed probe renders
  as an error, never a skip) and discovery fixtures for each source and the union/dedup.
- **Read view mutating state.** Any code path that reaches `read_run_marker` or
  `claude_state_dir(create=True)` from the fleet layer can delete a marker or create keyed dirs
  as a side effect of *looking*. The raw-read helper is the single sanctioned marker access;
  Phase 1's test asserts a ≥24h marker survives the read.
- **Thread race on the active-repo binding.** Flipping `set_active_repo_root` per request under
  `ThreadingHTTPServer` would let repo A's request read repo B's marker. Avoided structurally
  (raw keyed-path reads compose the path from `repo_key` without the binding).
- **Fleet page as a second state machine.** Scope creep toward parsing sentinel frontmatter or
  reproducing `curated_stage` logic in the shallow row would fork state inference. The bar:
  shallow rows may stat and count, never interpret; anything needing interpretation defers to
  the drill-in's `probe_state`.
- **Dead weight risk.** If the operator in practice runs one repo at a time, the fleet page
  idles. Falsifiability: the page is cheap (no new process, no new deps), and its usage signal
  is trivial (does the operator launch `--fleet` or `--repo-root`?); a retro can retire the flag
  if it goes unused — nothing else couples to it.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 discovery | Registry convention (`~/source/repos` glob + `lazy-repos.json`) ∪ live-marker `repo_root` scan | High |
| D2 serving model | Single instance, `--fleet` mode, nested `/repo/<slug>/` views | High |
| D3 staleness display | Graded badge (active / run-silent ~2h / stale 24h) + age, never delete | High |
| D4 page shape | Compact table + cross-repo triage strip + `LAZY_QUEUE.md` links | Medium-high |
| D5 probe strategy | Shallow presence-based rows; full probe on drill-in only | High (auto-accepted) |
| D6 read-only fleet | No new write routes; per-repo reorder unchanged | High (auto-accepted, stub-set) |
| D7 URL identity | Basename slug, server-owned map; `repo_key` never in URLs | High (auto-accepted) |
