---
kind: skip-mcp-test
feature_id: lazy-pipeline-visualizer
reason: claude-config has no MCP server / Tauri runtime / AlgoBooth audio tools — the standalone stdlib http.server visualizer has zero MCP-reachable surface
alternative_validation: full repo gates green at this commit — pytest 575/575 (visualizer slice 63/63), project-skills clean, lint-skills --check-projected --check-capabilities clean, plus a live-boot reachability smoke (200 + correct content-types on /api/state, /api/queue, /, /static/*)
date: 2026-06-15
skipped_by: mcp-test
granted_by: mcp-test
spec_class: standalone tool — no app/MCP integration (no MCP server, no Tauri runtime, no AlgoBooth audio tools exist in claude-config; capabilities.txt declares zero capabilities)
---

# MCP Test Skip — Lazy Pipeline Visualizer

## Assessment (mcp-test cycle, CONCUR)

This feature is a self-contained operator tool living entirely in
`user/scripts/pipeline_visualizer/`: a Python **stdlib `http.server`**
(`ThreadingHTTPServer`) backend plus a vanilla browser frontend (vendored
Cytoscape.js + dagre, no build step). It is a **read renderer** over the
existing `lazy-state.py` / `bug-state.py` JSON, with a single guarded
`queue.json` write path.

I verified the structural-untestability claim before granting this skip:

- **No MCP-reachable surface exists.** claude-config has **no MCP server** and
  **no Tauri runtime**. `.claude/skill-config/capabilities.txt` declares **zero
  capabilities** (explicitly NOT `mcp`); `.claude/skill-config/quality-gates.md`
  documents the "MCP exemption (Step 9)". The AlgoBooth MCP HTTP tools the
  `/mcp-test` skill drives (`load_test_tone`, `get_audio_buffer`, etc.) target
  AlgoBooth's audio/Tauri runtime — there is no audio, no Rust callback, no cpal
  device, and no MCP HTTP endpoint anywhere in this repo for those tools to
  reach. The "Audio IS MCP-testable" caution does not apply: this feature has no
  audio path of any kind.
- This is the **standalone-tool / no-app-integration** untestable class — the
  analog of the mcp-testing SPEC's "standalone crate — no app integration" row.
  Booting a dev runtime would surface nothing for an MCP tool to observe.

Per the `/mcp-test` orchestrator override: this is the **CONCUR** path (no
MCP-reachable surface), so this `SKIP_MCP_TEST.md` is written with
`granted_by: mcp-test` + `spec_class`, no runtime was booted, and no MCP HTTP
call was attempted.

## Alternative validation (the non-MCP evidence, run THIS cycle)

All certified against HEAD `21a9fb0c288db7547775d8f091993e930973832c`:

- **`python -m pytest user/scripts/ -q` → 575 passed** (full script suite),
  including the visualizer slice **`test_pipeline_visualizer.py` → 63 passed**:
  curated_stage rollup (every documented literal incl. all side-states, feature
  + bug), cache debounce (injected fake clock + probe-call counter), leases
  freshness boundary, probe JSON-parse + malformed handling, `receipt_present`
  detection, static-asset serving (+ API-wins-over-static + path-traversal
  guard), queue permutation validation, atomic round-trip, AV-lock retry, and
  run-marker refusal (409 + byte-identical), all over a live
  `ThreadingHTTPServer` on an ephemeral port driving the REAL `lazy-state.py`.
- **`python user/scripts/project-skills.py`** — clean (78 skills, 89 components,
  no circular-include / missing-component errors).
- **`python user/scripts/lint-skills.py --check-projected --check-capabilities`**
  — clean (no broken/embedded `!cat`, no unexpanded patterns, no capability
  pollution).
- **Live-boot reachability smoke** (workstation-eligible, ran this cycle): booted
  `make_server(repo_root=<this repo>, port=0)` on an ephemeral port and issued
  real HTTP requests:
  - `GET /api/state` → **200**, JSON keys `{bugs, features, leases, queue_locked,
    roadmap, server_time}` (the locked top-level shape); `features`/`bugs` are
    arrays; `queue_locked: true` correctly reflects the live `/lazy-batch`
    run-marker present during this orchestration run (proves run-marker detection
    end-to-end).
  - `GET /api/queue` → **200**, keys `{bugs, features}`.
  - `GET /` → **200** `text/html`; `GET /static/app.js` → **200**
    `text/javascript`; `GET /static/styles.css` → **200** `text/css`;
    `GET /static/cytoscape.umd.js` → **200** `text/javascript`.

The remaining unchecked PHASES Runtime Verification rows are **manual browser-UI**
behaviors (token animation, side-state ejection, drill-down, fade-and-drop, drag
UX, locked-handle visuals). claude-config has **no headless-browser harness**
(adding one is explicitly out of scope per the SPEC / Phase 2 testing strategy);
those are documented in `MANUAL_TESTING.md` for human execution and re-scoped to
non-checkbox follow-up notes in PHASES.md under a `⚖` disclosure — they are not
MCP-testable and do not block this skip.
