# lazy-cycle-containment.sh E2BIG fail-open on Windows-native Git Bash — Investigation Spec

> The containment hook's ~32KB inline Python body, when handed to the interpreter via `python3 -c "$_LCC_PY"`, exceeds Windows CreateProcess's 32,767-char command-line limit (E2BIG), so the process fails to spawn and the hook falls through to its unconditional `exit 0` — silently disarming the lazy cycle-containment plane on Windows-native hosts. **This defect was already fixed and shipped** under the duplicate bug `containment-hook-inline-python-exceeds-windows-cmdline-limit` (Fixed + archived 2026-07-18).

**Status:** Investigating
**Severity:** P2
**Discovered:** 2026-07-18
**Placement:** docs/bugs/adhoc-containment-hook-e2big-fails-open-windows-native
**Related:** `docs/bugs/_archive/containment-hook-inline-python-exceeds-windows-cmdline-limit` (the already-Fixed duplicate that resolved this exact defect)

<!-- Status stays Investigating (NOT Concluded): the technical investigation IS complete, but
     the only remaining action is a DISPOSITION (close this dir as a duplicate) that requires the
     orchestrator's Won't-fix authority. Marking Concluded would route bug-state.py to /plan-bug,
     which would fabricate PHASES for a fix that already shipped. Disposition parked via
     NEEDS_INPUT.md instead. -->

---

## Verified Symptoms

1. **[VERIFIED]** On Windows-native Git Bash, the containment hook's inline-Python invocation form determines whether the guard plane arms at all — reproduced deterministically by the regression tests `test_containment_temp_write_failure_fails_open_traced` and the plane-wide `test_no_embedded_c_python_body_exceeds_cmdline_ceiling` (both PASS on this host, 2026-07-19), which encode the E2BIG-disarm class and the ≤25,000-byte `-c` body ceiling.
2. **[VERIFIED — already remediated]** The live hook no longer invokes Python via `-c`; it writes the body to a `mktemp`'d temp file and invokes `python <tmppath>` (`user/hooks/lazy-cycle-containment.sh:934-984`), keeping the spawned command line short regardless of body size. The containment plane arms on a Windows-size command line.

## Reproduction Steps

1. `cd C:/Users/Jacob/source/repos/claude-config/user/scripts`
2. `python -m pytest test_hooks.py -k "test_no_embedded_c_python_body_exceeds_cmdline_ceiling or test_containment_temp_write_failure_fails_open_traced or test_bqe_temp_write_failure_fails_open_traced" -v`
3. Observed result (2026-07-19): **3 passed**.

**Expected (post-fix):** No hook still invokes Python via `"$PYTHON" -c "$_<VAR>_PY"` with a body over the 25,000-byte ceiling; the containment hook arms on a Windows-size command line.
**Actual (pre-fix, the defect):** `python3 -c "$_LCC_PY"` with a ~32KB body exceeded CreateProcess's 32,767-char limit → E2BIG → no spawn → shell `exit 0` → guard silently disarmed, no trace.
**Consistency:** Deterministic on Windows-native hosts (a pure function of command-line length); N/A on POSIX hosts (much higher `ARG_MAX`).

## Evidence Collected

### Source Code
- `user/hooks/lazy-cycle-containment.sh:102-116` — the fix-rationale comment block naming `windows-32k-cmdline-e2big-silently-disarms-containment`; the body "is handed to the interpreter via a `mktemp`'d TEMP FILE, NOT `-c "$_LCC_PY"`."
- `user/hooks/lazy-cycle-containment.sh:934-984` — the landed fix: `mktemp --suffix=.py`, guarded write via `printf`, `cygpath -w` for native `python.exe`, then `"$HOOK_PYTHON" "$tmppath"` (short command line). Traced fail-open (`hook_emit_error_event` + breadcrumb) on any temp-write failure; the PreToolUse payload stays on stdin untouched.
- `user/scripts/test_hooks.py:43-49` — `_EMBEDDED_PY_CEILING = 25000`, the plane-wide ceiling constant, citing `containment-hook-inline-python-exceeds-windows-cmdline-limit`.
- `user/scripts/test_hooks.py:10404` — `test_no_embedded_c_python_body_exceeds_cmdline_ceiling`, the generic recurrence guard that globs every `*.sh` in the hooks dir for a `-c "$_..._PY"` invocation over the ceiling.

### Runtime Evidence
- Full E2BIG/temp-file/containment test sweep run 2026-07-19: 63 passed (`-k "body_size or temp or windows or containment or arms or lcc"`); the three targeted regression tests: 3 passed.

### Git History
- `53eb47e8` fix(containment-hook): P1 temp-file python invocation restores Windows guard
- `74b8d26f` fix(containment-hook): P2 convert near-limit sibling build-queue-enforce.sh
- `82183884` fix(containment-hook): P3 plane-wide -c-body size-guard test (recurrence prevention)
- `e1c5ed57` fix(containment-hook): mark Fixed — gated FIXED.md receipt (E2BIG guard re-armed on Windows)  — all dated 2026-07-18, ~15h AFTER this ad-hoc stub was enqueued (00:27 the same day).

### Related Documentation
- `docs/bugs/_archive/containment-hook-inline-python-exceeds-windows-cmdline-limit/{SPEC,PHASES,FIXED,IMPLEMENTED}.md` — the concluded, fixed, archived duplicate (`**Status:** Fixed`).
- `user/hooks/CLAUDE.md` — the fail-OPEN + no-python-breadcrumb plane doc (the containment hook is one of the 8 python-bearing hooks).

## Theories

### Theory 1: Duplicate of an already-fixed bug
- **Hypothesis:** This ad-hoc stub (Round 90 finding) describes exactly the defect that `containment-hook-inline-python-exceeds-windows-cmdline-limit` fixed later the same day; the stub was enqueued before that fix landed, so it is now stale duplicate bookkeeping.
- **Supporting evidence:** Identical fix shape demanded by the brief (deliver body via temp file/stdin instead of `-c`; add a regression test asserting the hook arms on a Windows-size command line) vs. what P1–P3 actually shipped; the live hook already carries the temp-file fix; the archived duplicate's SPEC is `**Status:** Fixed`; all regression tests pass.
- **Contradicting evidence:** None found. The plane-wide ceiling test proves NO hook remains on an over-limit `-c` body (no residual sibling).
- **Status:** Confirmed.

## Proven Findings

- **[traced]** The E2BIG symptom (containment plane silently disarmed on Windows-native Git Bash) is produced by the pre-fix `python3 -c "$_LCC_PY"` invocation whose command line (interpreter + `-c` + ~32KB body) exceeds CreateProcess's 32,767-char limit. Serving path: hook `exit 0` fall-through (`lazy-cycle-containment.sh`, unconditional shell tail) ← failed `python -c` spawn ← over-length command line ← the `-c "$_LCC_PY"` form. The fix site is **on** this path: the `-c` form was replaced by a temp-file invocation (`lazy-cycle-containment.sh:944-984`), so the command line is now interpreter + one short path. This is a static command-line-length property (not runtime-coupled), corroborated by the passing regression tests.
- **[Confirmed]** The defect is already fixed and shipped. There is **no remaining code cause to fix** in this dir; the only open item is disposition (close as a duplicate of the archived bug).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Containment hook | `user/hooks/lazy-cycle-containment.sh` | Already fixed (temp-file invocation) |
| Sibling near-limit hook | `user/hooks/build-queue-enforce.sh` | Already fixed (P2 conversion) |
| Recurrence guard | `user/scripts/test_hooks.py` | Already added (P3 plane-wide ceiling test) |

## Open Questions

- Disposition only: should this duplicate dir be closed as Won't-fix (duplicate), or is there a residual not covered by the shipped fix? (Investigation found none — the plane-wide ceiling test passes.) Parked to the operator via `NEEDS_INPUT.md` — the Won't-fix flip + receipt are orchestrator-owned and cannot be written from a cycle subagent.
