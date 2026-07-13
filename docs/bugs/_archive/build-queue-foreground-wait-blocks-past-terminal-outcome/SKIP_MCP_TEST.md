---
kind: skip-mcp-test
feature_id: build-queue-foreground-wait-blocks-past-terminal-outcome
reason: repo has no MCP-reachable surface (no src-tauri/, no package.json) — nothing to boot, nothing to probe; the MCP gate is structurally vacuous.
alternative_validation: serving-path Pester regression suite (build-queue-foreground-outcome.Tests.ps1, 15/0) — red→green on the ORIGINAL symptom (Wait-ForRecordedOutcome returns result-recorded WITHOUT consulting process-liveness or sleeping), plus banner-parity re-emission for exit 3/5/PASS and the build-op-only poison-sweep gate. build-queue-await.Tests.ps1 (8/0) and build-queue-hygiene.Tests.ps1 (178/0) confirm no regression on the sibling paths.
date: 2026-07-13
skipped_by: pipeline
granted_by: pipeline-structural
spec_class: standalone — no app integration (no Tauri/MCP surface in repo)
validated_commit: a0b97bfebaf49ddac2780d3f637ad6c1225b5181
---

# MCP Test Skip — structural (no app surface)

Granted inline: this repo contains no `src-tauri/` and no `package.json`, so there is no MCP HTTP server / dev runtime to drive any MCP tool against. The `**MCP runtime:** not-required` PHASES declaration is re-verified structurally here (`skip_waiver_refusal()` re-checks `repo_has_no_app_surface(repo_root)` before this waiver can validate — an app repo would be refused).

**SEAM B (symptom-reproduction) evidence — rung 1, serving-path regression test.** The symptom's serving path is the foreground wrapper's wait model; the fix extracted it into `Wait-ForRecordedOutcome`, and `build-queue-foreground-outcome.Tests.ps1` asserts (red→green) that it returns `result-recorded` the instant the terminal `results/<seq>.json` is present, WITHOUT waiting for full runner-process exit or sleeping — i.e. the original "warned but didn't return promptly" symptom is gone at its serving surface. This is unit-test-land evidence on the ACTUAL serving path, not a proxy on an internal value.
