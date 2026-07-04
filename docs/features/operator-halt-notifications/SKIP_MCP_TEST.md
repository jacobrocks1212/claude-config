---
kind: skip-mcp-test
feature_id: operator-halt-notifications
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature adds a fail-OPEN lazy_core notifier + two one-line state-script call sites (terminal-emission chokepoint); none of it reaches an MCP tool surface. The only network path (the ntfy urllib POST) is an operator-configured push channel, exercised hermetically via the injected-sender seam and deferred for live phone verification (workstation-only, recorded in PHASES.md Phase 3).
alternative_validation: pytest gate suite 1300 passed / 2 sanctioned skips across the 10 suites (test_lazy_core 921 incl. the 11 new notify cases; test_lazy_parity 32 incl. the new seven-surface fires-when-notify-halt-missing case) + test_toolify_miner.py all pass + lazy-state.py/bug-state.py --test smokes green with the new [notify-halt-call-site] fixtures (baselines re-pinned via _normalize_smoke_output only) + lazy_coord.py --test green + lazy_parity_audit.py --repo-root <worktree> exit 0 (surface #7 present in both scripts) + lint-skills.py clean + doc-drift-lint.py 0 findings.
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration (no Tauri/MCP surface; harness mechanics validated by pytest, the in-file smoke harnesses, and the parity audit; live phone/cloud delivery deferred as workstation-only evidence)
validated_commit: 9824db2f98535ee2d8244b4be9f5acddf68d99da
---

# MCP Test Skip — Operator Paging on Pipeline Halts

## Why this feature has no MCP-reachable surface

`operator-halt-notifications` lives entirely in **claude-config**, the Claude Code configuration
harness — NOT an application. There is no Tauri app (`src-tauri/` absent), no frontend /
`package.json`, and no MCP HTTP server to connect to. The feature is pure harness mechanics:

- `lazy_core.py` — `notify_halt()` + config loader (`~/.claude/notify.json` /
  `LAZY_NOTIFY_URL` / `LAZY_NOTIFY_DISABLE`), the `_NOTIFY_ATTENTION_TERMINALS` /
  `_NOTIFY_CLEAN_STOP_TERMINALS` frozensets, sentinel-identity dedup over `notify-ledger.json`,
  the rich payload composer, the `_ntfy_send` channel behind the injected `sender` seam, and the
  `notify-error.json` fail-OPEN breadcrumb.
- `lazy-state.py` / `bug-state.py` — one-line `lazy_core.notify_halt(state, args.repo_root,
  pipeline=…)` call sites at the terminal-emission chokepoint in each `main()`.
- `lazy_parity_audit.py` — coupled-pair surface #7 (`lazy_core.notify_halt(`).

None of this reaches an MCP tool surface — there is no live runtime to probe. This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING, at `validated_commit`)

| Suite | Command | Result |
|-------|---------|--------|
| Full pytest gate suite (10 files) | `python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py -q` | **1300 passed, 2 skipped** (the two sanctioned environment skips) |
| Notify unit suite (config precedence, identity refresh, ledger prune/atomicity, payload + remote normalization, inert byte-identity, gating, dedup, fail-OPEN breadcrumb+retry, RFC-2047 ntfy headers) | within `test_lazy_core.py` (11 new cases, `_TESTS`-registered) | **all pass** |
| State-script parity (seven surfaces incl. notify_halt; negative fixture proves the check fires) | `python3 -m pytest test_lazy_parity.py -q` + `python3 lazy_parity_audit.py --repo-root .` | **32 passed**, audit **exit 0** |
| Smoke baselines (with the new `[notify-halt-call-site]` fixture in EACH script) | `lazy-state.py --test` / `bug-state.py --test` | green (baselines re-pinned only via `_normalize_smoke_output`) |
| Toolify miner / concurrency plane | `python3 test_toolify_miner.py` / `python3 lazy_coord.py --test` | all pass |
| Skill projection + lint / doc drift | `lint-skills.py` / `doc-drift-lint.py --repo-root .` | clean / 0 drift findings |

Every SPEC Validation-Criteria row except the two live-device rows names `pytest` / `--test
fixture` / `ledger inspection` as its "Where to Check"; **zero** rows name an MCP surface.

## Deferred live evidence (workstation-only — recorded in PHASES.md Phase 3, not silently skipped)

The two SPEC Validation-Criteria rows that need the real world — "Real phone delivery" (manual
`/lazy` halt → page on device with decisions + working deep link) and "Cloud reachability"
(env-provisioned URL through the container proxy, or an honest `notify-error.json` breadcrumb) —
are **DEFERRED workstation/phone legs**, not waived: the hermetic twins (injected fake sender,
raising sender → breadcrumb + no-ledger retry, `main()`-driven call-site fixtures) are all green,
and the production sender path (RFC-2047 headers for the em-dash-bearing `notify_message` titles,
`timeout=5`, Click link) is unit-verified against a monkeypatched `urlopen`.
