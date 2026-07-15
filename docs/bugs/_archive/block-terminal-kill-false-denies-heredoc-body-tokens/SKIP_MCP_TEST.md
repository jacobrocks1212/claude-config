---
kind: skip-mcp-test
feature_id: block-terminal-kill-false-denies-heredoc-body-tokens
reason: claude-config is a no-MCP harness repo — this is a PreToolUse hook-logic fix (Python inline in a bash hook script); there is no dev server / MCP HTTP surface to boot or probe.
alternative_validation: serving-path regression tests in user/scripts/test_hooks.py drive the real block-terminal-kill.sh (+ the 3 fixed sibling guard hooks) as subprocesses via their actual PreToolUse stdin-JSON interface — the same interface the live harness invokes them through — RED-confirmed against the pre-fix hooks, GREEN after the fix.
date: 2026-07-15
skipped_by: manual
granted_by: operator-directed-manual-fix
spec_class: harness hook fix (no app/Tauri/MCP surface in claude-config)
validated_commit: 31ee7de47400e2d50012bf36faee0ecb02c9a8c9
---

# MCP Test Skip — structural (no app surface)

claude-config has no `src-tauri/` and no `package.json` app surface — there
is no MCP HTTP server or dev runtime for `/mcp-test` to drive. This bug's
fix is entirely `user/hooks/*.sh` PreToolUse hook logic + its
`user/scripts/test_hooks.py` pytest serving-path regression coverage
(subprocess-driven against the real hook scripts through their actual
stdin-JSON interface), which is the load-bearing evidence for this fix —
see the sibling archived build-queue bugs
(`docs/bugs/_archive/build-queue-copy-lock-stale-dll-false-success/SKIP_MCP_TEST.md`)
for the same structural-skip precedent in this repo.
