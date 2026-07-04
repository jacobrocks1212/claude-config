---
kind: research-summary
feature_id: cross-repo-fleet-view
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — cross-repo-fleet-view

Codebase survey verifying every surface the SPEC names, against the lane base (which includes
the freshly-landed `harness-telemetry-ledger`).

## Verified surfaces

| SPEC claim | Verified location | Status |
|------------|-------------------|--------|
| `pipeline_visualizer` package: `make_server`, `/api/state` + `/api/queue`, `TtlCache` | `user/scripts/pipeline_visualizer/server.py` (`make_server(repo_root, host, port)`), `cache.py` (`DEFAULT_TTL_SECONDS = 2.0`) | ✅ as specced, PLUS a third route `/api/trends` (see drift note 1) |
| `probe.probe_state(repo_root)` shells one state-script subprocess per queue item | `probe.py:77` `_run_state_script` (`_PROBE_TIMEOUT = 60`), called per feature/bug entry in `probe_state` | ✅ |
| `probe.receipt_present` plain-stat precedent | `probe.py:108` — "presence check only … never re-infers state" | ✅ |
| `probe.read_queue` (missing file → `[]`) | `probe.py:125` | ✅ |
| `probe._item_dir` fallback `<pipeline_dir>/<spec_dir or id>` | `probe.py:92` | ✅ |
| `lazy_core.repo_key` — one-way sha1 of normalized realpath | `lazy_core.py:6604` (SPEC/RESEARCH cited ~6597 — drifted a few lines; contract identical) | ✅ |
| `lazy_core.claude_state_dir(create=True)` default; `LAZY_STATE_DIR` override returns the exact dir un-keyed | `lazy_core.py:9216` | ✅ (fleet reads must not call it with `create=True`; the raw path helper composes the keyed path itself) |
| `lazy_core.read_run_marker` DELETE-ON-READ at the 24h age gate (path A) + corrupt-file delete | `lazy_core.py:9409` (`_MARKER_STALE_SECONDS = 24*3600` at `lazy_core.py:6466`) | ✅ — confirms raw read is mandatory for the fleet layer |
| `write_run_marker` stamps `repo_root` in the marker | `lazy_core.py:9296` ff. (`repo_root` is a required positional; field written) | ✅ — the marker-union discovery leg is viable |
| `server._run_marker_present` flips `set_active_repo_root` per check | `server.py:24-57` | ✅ — confirmed unsafe to reuse per-request across repos under `ThreadingHTTPServer`; fleet mode uses the raw keyed-path read instead |
| Per-repo reorder write: `POST /api/queue`, marker-refused (409), atomic `os.replace` | `server.py:134-171` + `queue_writer.py` | ✅ |
| `LAZY_QUEUE.md` root-level doc (`mobile-queue-control`) | `user/scripts/lazy-queue-doc.py`; this repo's root carries a committed `LAZY_QUEUE.md` | ✅ |
| `~/.claude/lazy-repos.json` | Does NOT exist anywhere in the tree (grep clean) — mobile-queue-control specified it but shipped without needing it | ✅ as SPEC states: this feature is its first consumer and must document the schema |

## Integration points found by survey (not in the SPEC)

1. **`harness-telemetry-ledger` landed on the base.** `pipeline_visualizer` now has `trends.py`,
   an `/api/trends` route served through its OWN `TtlCache`, and a Trends tab in `static/`
   (`app.js` `fetchTrends`). The fleet drill-in must therefore expose
   `/repo/<slug>/api/trends` too, or the nested per-repo page's Trends tab breaks. Its tests
   (`test_pipeline_visualizer.py`, 86 passing at survey time) must stay green unmodified.
2. **The frontend uses ABSOLUTE URL paths.** `static/index.html` references `/static/*.js|css`
   and `static/app.js` fetches `/api/state`, `/api/queue`, `/api/trends` (absolute). Serving the
   same page nested under `/repo/<slug>/` requires either path rewriting or relative URLs.
   Resolution: switch the per-repo frontend to RELATIVE paths (`static/app.js`, `api/state`) —
   resolved identically at `/` in single-repo mode (all existing static/API tests stay green,
   requesting the same absolute routes), and resolved to `/repo/<slug>/...` when nested. A
   `/repo/<slug>` (no trailing slash) request must 301-redirect to `/repo/<slug>/` so relative
   resolution is correct.
3. **Marker raw-read precedent confirmed:** `write_run_checkpoint` (`lazy_core.py:13631`) reads
   the marker file raw for exactly the delete-on-read reason; the fleet layer mirrors it.
4. **Existing test conventions:** `test_pipeline_visualizer.py` starts real ephemeral-port
   servers in daemon threads, uses `_isolated_state_dir` (a flat `LAZY_STATE_DIR` fixture) and
   `_keyed_home` (temp `HOME`, production keyed layout). Fleet tests pass an explicit
   `state_base` (keyed layout under a temp dir via `lazy_core.repo_key`) instead of mutating
   `HOME`, keeping fixtures hermetic and race-free.

## Spec assumptions checked, none proved wrong

- No fleet-level write is needed anywhere (D6): confirmed — the only write path in the package
  is `queue_writer.reorder_queue` behind `POST /api/queue`.
- The `manifest.psd1` Repos scope is still Cognito-only (wrong discovery proxy — D1 rejection
  stands).
- `probe_state` cost shape unchanged (one subprocess per queue item, 60s timeout each) — the
  shallow-row rationale (D5) stands.

## GitHub `LAZY_QUEUE.md` link derivation (D4-B detail)

No shallow-safe git *subprocess* is allowed on the fleet poll; the link is derived from plain
file reads: `.git/config` (`[remote "origin"] url`, https or ssh form normalized to
`https://github.com/<owner>/<repo>`) + `.git/HEAD` (`ref: refs/heads/<branch>`). Worktree `.git`
*files* (`gitdir: …`) are followed one level for `HEAD`; any parse failure yields no link
(honest degradation, never an error row).
