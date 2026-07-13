---
kind: skip-mcp-test
feature_id: build-queue-hygiene-dot-source-discarded-in-child-scope
reason: repo has no MCP-reachable surface (no src-tauri/, no package.json at repo root) — nothing to boot, nothing to probe; the MCP gate is structurally vacuous. This is Windows PowerShell build-queue tooling.
alternative_validation: Pester suite (build-queue-hygiene.Tests.ps1) — 100 passed / 3 pre-existing baseline failures. Symptom reproduction (per symptom-reproduction-gate, bound to SPEC ## Reproduction Steps): (1) serving-path structural regression guard — the scope-in-caller AST guard asserts the hygiene dot-source is a top-level statement in all three callers; RED (97/6) on the unpatched tree, GREEN (100/3) after the fix. (2) runtime observable of the reported symptom — the SPEC's own "Minimal cause isolation" repro, executed red→green: `Get-SafeValue { . hygiene.ps1 }` → `New-BuildJobObject` defined=False (the bug), fixed `try { . hygiene.ps1 } catch {}` → defined=True. The full production end-to-end symptom (a real /nxbuild printing the RESULT banner + a rich results/<seq>.json) is a documented OPTIONAL workstation-manual check on a live Cognito worktree (PHASES Runtime Verification), a superset not required to reach VERIFIED at the mechanism serving path.
date: 2026-07-06
skipped_by: pipeline
granted_by: pipeline-structural
spec_class: standalone — no app integration (no Tauri/MCP surface in repo)
validated_commit: 2d9f8ae306237935901f4460bff699cecd06821d
---

# MCP Test Skip — structural (no app surface)

Granted inline: this repo contains no `src-tauri/` and no root `package.json`, so there is no MCP HTTP server / dev runtime to drive any MCP tool against. The `**MCP runtime:** not-required` PHASES declaration is re-verified structurally here (`repo_has_no_app_surface` + `phases_mcp_runtime_not_required` both True), so no /mcp-test subagent is dispatched. `skip_waiver_refusal()` re-checks the same structural predicate before this waiver can validate.

**Symptom-reproduction is satisfied separately (not by this skip).** Per `symptom-reproduction-gate.md`, a bug may not flip Fixed on a SKIP_MCP_TEST.md alone. The serving-path evidence lives in ordinary Pester unit-test land and is recorded in PHASES.md (Batch 2 Implementation Notes) and bound to the SPEC's `## Reproduction Steps`: the AST scope-in-caller guard (RED→GREEN across all three callers) plus a runtime red→green of the SPEC's "Minimal cause isolation" recipe (child-scope discard `defined=False` → top-level `defined=True`).
