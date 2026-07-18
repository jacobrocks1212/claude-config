---
kind: adhoc-brief
bug_id: adhoc-audit-obligation-fires-on-zero-commit-failed-cycle
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: Input-audit obligation fires (mis-targeted) after a zero-commit failed spec cycle

During the 2026-07-18 run, a spec-cycle Agent dispatch failed abnormally (0 tool uses, returned boilerplate; no commit landed). The closed spec-kind cycle bracket still armed the audit-obligation, and the pre-composed input_audit_emit_command bound cycle_commit_sha=HEAD~1 - which pointed at an UNRELATED bug item's commit - plus the wrong cycle_summary. The dispatched audit correctly no-opped but cost ~77k tokens. Fix shape: the audit obligation should key on the closed bracket having a non-empty commit delta (begin_sha != end_sha, or at least one commit touching the item's spec dir); a zero-commit bracket close (failed/no-op dispatch) should clear or skip the obligation; the pre-composed emit command should bind the bracket's actual end commit, never a positional HEAD~1.
