---
kind: research-summary
feature_id: harness-telemetry-ledger
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — harness-telemetry-ledger

Gemini deep research was intentionally skipped (operator directive, 2026-07-04 — see
`RESEARCH.md`). This file records the pre-implementation **codebase survey**: every surface /
line-anchor the SPEC names was re-verified against the live tree, drift noted, and the
integration points enumerated.

## SPEC surface verification (all anchors checked 2026-07-04)

| SPEC claim | Verified? | Notes |
|---|---|---|
| `lazy-state.py` `_state()` dispatch return "line ~111" | ✓ | `def _state(` at `lazy-state.py:111`. Not an emission site (D3-A hooks CLI handlers, not `compute_state`). |
| `append_deny_ledger_entry` (~12592) / `append_friction_ledger_entry` (~12645) / `read_deny_ledger` (~12977) | ✓ | Exact contract as described: plain `open("a")` append, swallow-all fail-open returning `False`, corrupt-line-skipping reader over `claude_state_dir(create=False)`. `_DENY_LEDGER_FILENAME` at `lazy_core.py:6447`. |
| `claude_state_dir()` per-repo keying (~9209) | ✓ | `LAZY_STATE_DIR` env override returns the exact dir (hermetic tests); production path keys `~/.claude/state/<repo_key>/`. `create=False` read-path purity documented in the docstring — the D3 constraint this feature must preserve. |
| `write_run_marker` (~9289) / `read_run_marker` (~9402) | ✓ | Marker carries `pipeline`, `cloud`, `repo_root`, `started_at` (the canonical run identity → `run_id`), counters. **Gotcha found:** `read_run_marker` is *destructive* on a stale/corrupt marker (deletes it) — the telemetry emitter must NOT use it from refusal paths that promise "zero side effects". Implementation uses a raw non-destructive marker read (age-fresh check only, no unlink), mirroring `refuse_run_start_clobber`'s own raw read. |
| `--run-start`/`--run-end`/`--cycle-begin`/`--cycle-end` handlers | ✓ | `lazy-state.py:9402–9703`, `bug-state.py:5431–5672`. `--run-end` deletes the marker at the END of the success path → run-end emission (and the D5-B cloud flush) must fire BEFORE `delete_run_marker`. |
| Exit-3 refusal sites | ✓ | `refuse_if_cycle_active` (lazy_core:10581), `refuse_cycle_marker_mutation_if_subagent` (10633), `refuse_run_start_clobber` (10694). All three live in `lazy_core` and `sys.exit(3)` after a stderr message — ONE emission call inside each helper covers both state scripts (parity by construction). |
| Exit-1 verdict gates | ✓ | `--verify-ledger` (lazy-state:9934 / bug-state:5828), `--gate-coverage` (lazy-state:9353 — **feature-pipeline only**; `bug-state.py` has no `--gate-coverage` handler, a pre-existing justified divergence), `--apply-pseudo` not-ok path (lazy-state:9820 / bug-state:5747). |
| `--emit-prompt` dispatch surface | ✓ | `lazy-state.py:10004` / `bug-state.py:5895`. Both branches (withheld-by-hardening-debt and normal emission) mutate `state` and fall through to the single `sys.stdout.write(json.dumps(state))` — the dispatch/halt emission sits at the end of the `if args.emit_prompt:` block, adding NO output keys. Confirmed `--emit-prompt` is the sole per-cycle real-dispatch probe surface (the meta surface is `--emit-dispatch`, deliberately NOT a v1 event — meta cycles are visible via `cycle-begin --kind meta` brackets instead). |
| `--neutralize-sentinel` | ✓ | `lazy-state.py:9815` / `bug-state.py:5742`; shared `lazy_core.neutralize_sentinel` (4446) returns `{ok, ...}`. |
| `pipeline_visualizer` server/cache | ✓ | `server.py` `make_server` closes over one `TtlCache`; `probe_state` referenced as a module attribute so tests monkeypatch it — the trends producer mirrors this pattern. Static assets under `pipeline_visualizer/static/` served rooted at `static/`. |
| `migrate_legacy_state_dir` untouched | ✓ | The telemetry file never existed un-keyed; the legacy-migration file list does not need (and does not get) a new entry. |

## Assumptions that proved wrong / needed adjustment

1. **`read_run_marker` is not side-effect-free.** It deletes age-stale/corrupt markers on read.
   Using it inside `append_telemetry_event` would give the exit-3 refusal paths (contractually
   "ZERO side effects") a destructive read. Fixed by a dedicated raw, non-destructive,
   age-fresh-checking marker read inside the emitter.
2. **`<run_id>.jsonl` is not a legal Windows filename** (colons). The committed cloud segment
   would break checkout on the operator's Windows workstation. Resolved: strip colons from the
   filename only (see SPEC D5 implementation notes); line content unchanged.
3. **`--gate-coverage` exists only on `lazy-state.py`.** The SPEC's "both scripts" chokepoint
   table is otherwise symmetric; the bug script simply has no Gate-1 coverage CLI (pre-existing
   divergence, confirmed against `lazy_parity_audit.py` which does not audit it).
4. **The retro skill is user-level** (`user/skills/lazy-batch-retro/SKILL.md`), not repo-scoped
   as the root CLAUDE.md's skill-family table implies. The D8 "Ledger deltas" step lands there.
   It is the *derived* member of no parity pair, so only `lint-skills.py` + re-projection gate it.

## Integration points

- `lazy_core.py`: new `_TELEMETRY_LEDGER_FILENAME` / `_TELEMETRY_SCHEMA_VERSION` /
  `_TELEMETRY_ROTATE_BYTES` / `_TELEMETRY_ROTATED_SEGMENTS` constants beside
  `_DENY_LEDGER_FILENAME`; `append_telemetry_event`, `read_telemetry_events`,
  `TELEMETRY_HALT_TERMINAL_REASONS`, `flush_cloud_telemetry_segment`; one
  `append_telemetry_event("containment-refusal", ...)` call inside each of the three refusal
  helpers (before `sys.exit(3)`, after the refusal decision — observability, not state).
- `lazy-state.py` + `bug-state.py`: mirrored emission calls in the run/cycle bracket handlers,
  `--emit-prompt`, `--apply-pseudo`, `--verify-ledger`, `--neutralize-sentinel` (+
  `--gate-coverage` on the feature script only); D5-B flush call in both `--run-end` handlers.
- `pipeline_visualizer/trends.py` (new): pure aggregation functions + repo loaders + `main()`
  CLI (`python3 -m pipeline_visualizer.trends --repo-root <r> [--run-id <id>]`).
- `pipeline_visualizer/server.py`: `/api/trends` route through a second `TtlCache`;
  `static/index.html` + `static/app.js` (+ `styles.css`) gain the Trends tab.
- `user/skills/lazy-batch-retro/SKILL.md`: additive "Ledger deltas" step shelling the trends CLI.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`: run-end prose + a "Differences
  from /lazy-batch" row for the cloud telemetry-segment commit (the D5-B tabulated divergence).
- Tests: `test_lazy_core.py` (+ `_TESTS` registration), in-file `--test` fixtures in both state
  scripts (baselines regenerated via `_normalize_smoke_output` — new PASS lines are expected),
  `test_pipeline_visualizer.py` trends fixtures.

## Baseline (pre-implementation, this worktree @ b5c1021)

`pytest` 1202 passed / 2 sanctioned skips; `lazy-state.py --test`, `bug-state.py --test`,
`lazy_coord.py --test` all green; `lazy_parity_audit.py --repo-root .` exit 0.
