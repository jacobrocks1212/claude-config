# Bug: Process friction: unexpected-commits (×2) — DUPLICATE

**Status:** Won't-fix

**Severity:** Low

**Resolution:** Won't-fix — **duplicate** of already-tracked work (operator-directed disposition, 2026-07-20).

This incident was auto-captured by `incident-scan.py` (`incident_key: claude-config|friction|unexpected-commits`, 2 occurrences). Investigation is unnecessary — the root cause is already understood, fixed, and/or tracked:

- **Occurrence 1** (30 commits) — operator-confirmed **FALSE POSITIVE** in its own INCIDENT.md capsule: a concurrent same-branch session's mark-fixed/archive commits inflated the `--cycle-end` process-friction commit count. Its real fix is **already shipped + archived**: `docs/bugs/_archive/adhoc-process-friction-detector-counts-concurrent-session-commits/`.
- **Occurrence 2** (11 commits during `execute-plan`) — the same over-count class (concurrent-dispatch commits on HEAD). The residual is **already tracked open**: `docs/bugs/process-friction-counts-same-run-concurrent-dispatch-commits/`.

No new root cause and no independent fix exist here; closing as a duplicate avoids re-deriving tracked work. The evidence capsule is preserved in `INCIDENT.md`. If the detector over-count recurs after `process-friction-counts-same-run-concurrent-dispatch-commits` ships, that is the bug to reopen — not this capture.
