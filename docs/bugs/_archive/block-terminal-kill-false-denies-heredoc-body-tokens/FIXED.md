---
kind: fixed
feature_id: block-terminal-kill-false-denies-heredoc-body-tokens
date: 2026-07-15
provenance: manual
completed_commit: 31ee7de47400e2d50012bf36faee0ecb02c9a8c9
validated_via: pytest
auto_ticked_rows: 0
---

# Completion Receipt

Fixed out-of-pipeline (manual harness fix, not via `/lazy-bug-batch`
`__mark_fixed__`). Root cause: `block-terminal-kill.sh` (and the three
sibling `_CMD_START`-anchored guards — `lazy-cycle-containment.sh`,
`long-build-ownership-guard.sh`, `build-queue-enforce.sh`) matched deny
tokens at command-segment starts over a command string masked for quoted
spans (`_mask_quoted`) but not heredoc bodies — a heredoc body's own
interior newlines satisfied `_CMD_START`'s `\n` separator class like a real
command boundary, fabricating a false segment start.

Fix: `_mask_heredoc` (flat single-pass, offset-preserving, same discipline
as `_mask_quoted`) added to all four `_CMD_START`-anchored guards, applied
before their existing matchers. `block-work-repo-git-push.sh` audited and
confirmed NOT vulnerable (no `_CMD_START` anchoring at all) — pinned
unchanged, not fixed.

**Serving-path regression test evidence (the symptom-reproduction
evidence for this fix):** `user/scripts/test_hooks.py`
`test_termkill_allows_heredoc_commit_message_kill_repro` and
`test_termkill_allows_heredoc_log_append_exit_repro` reproduce the SPEC's
two exact repros (a `git commit -F - <<'EOF'` message body line-leading
`kill`; a `cat >> f << 'EOF'` body line-leading `exit 0`) driving the real
`block-terminal-kill.sh` hook as a subprocess via its actual PreToolUse
stdin-JSON serving path — RED-confirmed against the pre-fix hook (denied),
GREEN after the fix (allowed). Sibling coverage:
`test_containment_allows_heredoc_body_mentioning_lazy_batch`,
`test_longbuild_guard_allows_heredoc_body_mentioning_cargo_build`,
`test_bqe_allows_heredoc_body_mentioning_dotnet_build` (+ one
after-terminator-still-denies regression test per hook) and
`test_push_unaffected_by_heredoc_body_no_cmd_start_anchoring` +
`test_termkill_ps_herestring_apostrophe_body_kill_accepted_residual`
(accepted-residual pins). All pass individually; the full relevant subset
(171 tests) passed together on a clean run — some individual reruns hit
this machine's documented CPython-3.14/Windows `OSError: [WinError 6]`
subprocess-spawn flake (confirmed non-logic by direct function-call
invocation, per `docs/bugs/CLAUDE.md`'s environmental-flake precedent).
