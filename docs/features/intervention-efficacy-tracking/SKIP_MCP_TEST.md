---
kind: skip-mcp-test
feature_id: intervention-efficacy-tracking
reason: claude-config is pure harness mechanics — no Tauri app, no src-tauri, no package.json, no MCP-reachable surface exists to drive any MCP HTTP tool against. The feature adds a script-owned capture chokepoint inside lazy_core.apply_pseudo + a coupled-pair --record-intervention CLI, a standalone stdlib evaluator (efficacy-eval.py) over the telemetry ledger, and orchestrator/retro/hardening skill prose; none of it reaches an MCP tool surface.
alternative_validation: pytest (test_lazy_core 867 + test_efficacy_eval 16 + test_lazy_parity 30 + test_hooks + test_pipeline_visualizer + test_lazy_queue_doc + test_lint_skills + test_surface_resolver + test_stale_binary + test_retro_ro9 + test_project_skills = 1260 passed, 2 sanctioned skips) + test_toolify_miner.py (all passed) + lazy-state.py --test / bug-state.py --test smoke (baselines green, unchanged) + lazy_coord.py --test (all passed) + lazy_parity_audit.py --repo-root . (exit 0, incl. the NEW --record-intervention coupled-pair check) + lint-skills.py (clean) + lane-local project-skills.py projection (0 errors) + doc-drift-lint.py (0 findings) + live CLI smoke (--record-intervention on BOTH scripts against a fixture repo; end-to-end REFUTED → reconsider-<id> enqueued exactly once across repeated evaluations in test_efficacy_eval.py).
date: 2026-07-04
skipped_by: pipeline
granted_by: mcp-test
spec_class: standalone — no app integration
validated_commit: 42d662b2e454201ef43d95f43e21554f6ef1dc20
---

# MCP Test Skip — Intervention Efficacy Tracking (Hypothesis Ledger)

## Why this feature has no MCP-reachable surface

`intervention-efficacy-tracking` lives entirely in **claude-config**, the Claude Code
configuration harness — NOT an application. There is no Tauri app (`src-tauri/` absent), no
frontend / `package.json`, and no MCP HTTP server to connect to. The feature is pure harness
mechanics:

- `lazy_core.py` — the D5 constants block, `parse_intervention_hypothesis`,
  `read_intervention_telemetry`, `_render_intervention_record`, `record_intervention`, the
  `_interventions_queue_flag` opt-in reader, and the fail-open capture call inside the
  `apply_pseudo` `__mark_complete__`/`__mark_fixed__` completion branch.
- `lazy-state.py` / `bug-state.py` — the coupled-pair orchestrator-only `--record-intervention`
  CLI (+ hypothesis-override and D9 backfill flags), parity-audited by the NEW
  `_RECORD_INTERVENTION_RE` check in `lazy_parity_audit.py`.
- `efficacy-eval.py` — the standalone stdlib evaluator (windows, verdict bands, confounder cap,
  escalation, two-layer-guarded REFUTED enqueue via the shipped `--enqueue-adhoc --type bug`
  subprocess).
- Skill prose — the §1c.6 end-of-run flush paragraphs (`/lazy-batch` + `/lazy-batch-cloud`,
  coupled-pair mirrored + divergence-table row), `/lazy-batch-retro` Step 6e (report-only
  citation), `/harden-harness` Step 4 (hardening-round capture).

None of this reaches an MCP tool surface — there is no live runtime to probe. This is the
`standalone — no app integration` untestable class.

## Alternative validation performed (all PASSING at `validated_commit`)

| Suite | Command | Result |
|-------|---------|--------|
| Full pytest gate (core capture fixtures: flag-on capture, flag-off byte-identity, block-without-flag, no-ledger degradation, backfill/hardening provenance, nested `baseline:` parse_sentinel round-trip; evaluator: CONFIRMED/REFUTED/INCONCLUSIVE bands, min-sample, not-due accrual, frozen-baseline-after-ledger-delete, undeclared/kpi degradation, same-signal confounder cap, self-emitted annotation, escalation N=2, dry-run byte-inertness, --id filter, REFUTED-enqueues-exactly-once + both guard layers) | `python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py test_efficacy_eval.py -q` | **1260 passed, 2 skipped** (the two sanctioned: Windows cold-boot spawn; WSL pipe) |
| Toolify miner suite | `python3 test_toolify_miner.py` | all passed |
| Smoke baselines (byte-pinned, unchanged) | `lazy-state.py --test` / `bug-state.py --test` | green |
| Concurrency plane | `python3 lazy_coord.py --test` | all passed |
| Coupled-pair parity (incl. the new `--record-intervention` check on both scripts) | `python3 lazy_parity_audit.py --repo-root .` | exit 0 |
| Skill lint + lane-local projection | `lint-skills.py` / `project-skills.py --output-dir /tmp/proj-…` | clean / 0 errors |
| Doc-drift lint (root + scripts CLAUDE.md rows vs disk) | `python3 doc-drift-lint.py --repo-root .` | 0 findings |
| Live CLI smoke | `--record-intervention` on BOTH scripts against a fixture repo (SPEC-block route + hardening-override route) | records written; idempotent |

Every SPEC Validation-Criteria row names `apply_pseudo` output / `test_efficacy_eval.py` /
`test_lazy_core.py` / the parity audit as its "Where to Check"; **zero** rows name an MCP
surface (every phase's MCP Integration Test Assertions block is `N/A — no MCP surface`).
