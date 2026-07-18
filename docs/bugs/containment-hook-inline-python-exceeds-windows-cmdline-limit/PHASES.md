# Implementation Phases — lazy-cycle-containment.sh inline python exceeds the Windows command-line limit → silent fail-open

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config harness/hook tooling with no app runtime surface (no Tauri, no MCP HTTP server, no MCP tool catalog); every deliverable is a bash-hook / pytest change, structurally outside MCP reach. Verified via the `user/scripts/test_hooks.py` pytest gate + direct hook driving.

## Root cause (from concluded SPEC)

`user/hooks/lazy-cycle-containment.sh:809` runs the hook's embedded python body via `-c`:
`LCC_SCRIPTS_DIR="$LCC_SCRIPTS_DIR" "$PYTHON" -c "$_LCC_PY"`. The `$_LCC_PY` heredoc body (lines
117–797) is **~33.7 KB**, exceeding the Windows `CreateProcess` command-line limit of **32,767
chars**. On Windows (Git Bash → native `python`) the process is never spawned — bash reports
`Argument list too long` (E2BIG) — and the hook falls through to its unconditional `exit 0`
(line 813). The containment guard is **silently disarmed on Windows**; 22 `test_containment_*`
tests are red. The fail-open is **untraced** (E2BIG is neither the "no-python" bash fallback nor
reachable by the python-side `except`, since the process never starts).

## Validated Assumptions (runtime-coupled — observed on the repro host DESKTOP-GHTC5K6)

- **Temp-file invocation works cross-dialect on this host.** Driving native `python` from Git Bash
  against a `mktemp --suffix=.py` script file, with the PreToolUse payload simultaneously on stdin,
  succeeds (exit 0, payload read) for **both** the raw MSYS path (`/tmp/tmp.XXXX.py`) **and** the
  `cygpath -w`-converted Windows path (`C:\Users\...\Temp\tmp.XXXX.py`). Evidence: spike run
  2026-07-18 — `echo '{"x":1}' | python /tmp/tmp.*.py` and `... python "$(cygpath -w …)"` both
  printed `OK payload: {"x":1}`. → The temp-file fix keeps the payload on stdin (the SPEC's
  recommended, and only viable, option) and is confirmed to run on the exact box the bug repros on.
  Phase 1 still converts the path via `cygpath -w` where available (defensive — not every native
  python build resolves `/tmp`), with the raw path as fallback.
- **`build-queue-enforce.sh` embedded body is 31,966 bytes** (measured 2026-07-18) — only ~800 B
  under the hard limit, and the *effective* command line adds the `BQE_SCRIPTS_DIR=… ` env prefix +
  `python -c ` + shell quoting on top. It is one harden round from tripping the identical E2BIG
  fail-open. This is the near-miss sibling remediated in Phase 2.

## Touchpoint Audit (verified inline against the live codebase — dispatch available; small mechanical batch)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/hooks/lazy-cycle-containment.sh` | yes | `_LCC_PY` heredoc body (117–797); python resolution (84–107) with no-python breadcrumb + `hook-events.jsonl` append; payload read at py body line 630 `raw = sys.stdin.read()`; `-c` invoke at 809; `exit 0` at 813; bash base dir `$LCC_BASE_DIR` | refactor | Replace the line-809 `-c "$_LCC_PY"` with a temp-`.py`-file invocation (`"$PYTHON" "$tmpfile"`), payload STAYS on stdin (py line 630 untouched); reuse the existing no-python breadcrumb block (99–107) shape for a NEW **traced** fail-open when temp write/mktemp fails; keep `LCC_SCRIPTS_DIR`/`LAZY_STATE_DIR` env passthrough; `trap`-cleanup the temp file |
| `user/hooks/build-queue-enforce.sh` | yes | `_BQE_PY` heredoc body = 31,966 B; `-c "$_BQE_PY"` at 841; `BQE_SCRIPTS_DIR` env prefix | refactor | Same temp-file conversion, reusing the Phase-1 pattern; near-limit, remediated proactively |
| `user/scripts/test_hooks.py` | yes | `_run_bash(script, stdin_text, env)` (265); `_bash_preToolUse_json(...)` (3089); Phase-4 containment tests (3067+); `_CONTAINMENT_SH` (3082); no existing size-guard test | modify | Confirm the 22 `test_containment_*` go green post-fix; add an explicit Windows deny regression + a NEW plane-wide embedded-`-c`-body size-guard test |

**Contradiction resolved (anchor-grade, corrected in-plan — not a premise halt):** the SPEC's Fix
Scope offers `"$PYTHON" - <<<"$_LCC_PY"` as one option. That option is **falsified** by the code —
the payload occupies stdin (py body line 630 `sys.stdin.read()`; the 111–116 comment explains `-c`
was chosen precisely so a heredoc would not swallow the payload). Feeding the script on stdin would
clobber the payload. The SPEC *also* offers, and **recommends**, the temp-file option ("keeping the
payload on stdin ... the cleaner shape") — that recommended path is unfalsified and is what these
phases build on. No premise is demoted; the wrong sibling option is simply not selected.

**Audit no-ops (recorded):** SPEC-example capability audit — the SPEC has no code examples
consuming a target API (it is a shell-hook defect); nothing to audit. MCP tool-existence audit —
no `.claude/skill-config/mcp-tool-catalog.md` in this repo → no-op. Reachability axiom — the hook
has no user-facing surface; N/A. Data-reach / module-move audits — no entity retention, no module
move/rename/delete; N/A.

---

### Phase 1: Convert the containment hook to a temp-file python invocation (restore the guard on Windows)

**Status:** Complete

**Scope:** Stop passing the ~33.7 KB `$_LCC_PY` body as a `-c` argument. Write it to a temporary
`.py` file and invoke `"$PYTHON" "$tmpfile"` with the PreToolUse payload still on real stdin —
neither is bounded by the command-line limit — so the containment guard spawns and DENIES on
Windows again. Add a **traced** fail-open for the new failure mode (mktemp/temp-write failure),
closing the observability gap the SPEC flagged.

**Deliverables:**
- [x] `user/hooks/lazy-cycle-containment.sh`: replace the line-809 `-c "$_LCC_PY"` invocation with a temp-file invocation — `mktemp` a `.py` file, write `$_LCC_PY` into it, run `LCC_SCRIPTS_DIR="$LCC_SCRIPTS_DIR" "$PYTHON" "$tmpfile"` with the payload on stdin, and `trap`-remove the temp file on EXIT.
- [x] Windows path handling: convert the temp path with `cygpath -w "$tmpfile"` when `cygpath` is available (Git Bash on Windows), falling back to the raw path otherwise — per the Validated Assumption. `LAZY_STATE_DIR`/`LCC_SCRIPTS_DIR` env passthrough preserved unchanged.
- [x] **Traced fail-open** on mktemp/temp-write failure: on any failure to create or write the temp file, write the existing `hook-error.json` breadcrumb + `hook-events.jsonl` append (reuse the no-python block shape at lines 99–107, with a distinct `detail`) then `exit 0` — so this residual fail-open path is observable, unlike the E2BIG one it replaces.
- [x] Preserve the fail-OPEN-via-empty-output contract and the unconditional `exit 0` (line 813); the embedded python body (117–797), including the stdin payload read at line 630, is otherwise untouched.
- [x] Tests: the 22 previously-red `test_containment_*` in `user/scripts/test_hooks.py` pass; a direct drive (marker present + subagent routing-op payload) emits a `permissionDecision: deny` block.

**Minimum Verifiable Behavior:** `python user/scripts/test_hooks.py` shows the `test_containment_*`
group green (was 22 failing); driving `bash user/hooks/lazy-cycle-containment.sh` with a cycle
marker + a subagent lifecycle-op payload prints a deny JSON on stdout (no `Argument list too long`
on stderr).

**Runtime Verification** *(checked by the pytest gate / direct hook drive — NOT by the implementation agent):*
- [x] <!-- verification-only --> Under a cycle marker on Windows, the containment hook DENIES a subagent routing/lifecycle op (emits `permissionDecision: deny`) instead of fast-path-allowing — the exact reproduction inverted.
- [x] <!-- verification-only --> A forced temp-file-write failure fails OPEN **and** leaves a `hook-error.json` + `hook-events.jsonl` breadcrumb (traced), not a silent exit 0.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface; verification is the `test_hooks.py` pytest gate.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/hooks/lazy-cycle-containment.sh` — temp-file invocation + traced fail-open (the fix).

**Testing Strategy:** Drive the hook via `test_hooks.py::_run_bash` with a tmp `LAZY_STATE_DIR` +
crafted PreToolUse payloads (marker absent → allow; marker present + lifecycle/routing op → deny).
Run the existing Phase-4 containment suite; it must go from 22-red to green on this Windows host.

**Integration Notes for Next Phase:**
- The temp-file invocation shape established here (mktemp `.py` + `cygpath -w` where available + `trap` cleanup + traced fail-open on write failure) is the **reusable pattern** Phase 2 applies to `build-queue-enforce.sh`. Keep it factored simply enough to copy faithfully across hooks.
- Do NOT feed the body on stdin (`- <<<"$_LCC_PY"`) — stdin carries the PreToolUse payload (py body line 630); that option is falsified. Temp-file only.

**Implementation Notes (2026-07-18):**
- `user/hooks/lazy-cycle-containment.sh` converted from `-c "$_LCC_PY"` to a temp-file invocation. Actual landed shape: `tmpfile="$(mktemp --suffix=.py 2>/dev/null)"` (plain `mktemp`, honors `TMPDIR` — the standard POSIX seam the test exploits), `trap 'rm -f "$tmpfile"' EXIT` set right after a successful mktemp, `printf '%s' "$_LCC_PY" > "$tmpfile"`, `cygpath -w` conversion guarded by `command -v cygpath`, then `LCC_SCRIPTS_DIR="$LCC_SCRIPTS_DIR" "$PYTHON" "$tmppath"` with the PreToolUse payload untouched on real stdin. Invocation site now ~line 866; unconditional `exit 0` at ~870.
- **Traced fail-open** on mktemp/write failure reuses the no-python breadcrumb block shape byte-for-byte with a DISTINCT `detail: "temp-file write failed"` (both `hook-error.json` and one `hook-events.jsonl` `kind:"error"` line), then `exit 0`. Line/offset references in the deliverables above (809/813/630/99–107) are pre-fix; the embedded python body (incl. `raw = sys.stdin.read()`, now ~line 641) is byte-unchanged — only the comment block above it and the invocation footer moved.
- **Seam agreement:** test (`test_containment_temp_write_failure_fails_open_traced`, `test_hooks.py:4307`) forces failure via `TMPDIR=<non-existent-parent>`; confirmed on this host that `mktemp` honors TMPDIR and fails there (`rc=1`, "No such file or directory").
- **Gates:** `python -m pytest user/scripts/test_hooks.py -k containment -q` → 54 passed (was 23 red / 31 passed); full `test_hooks.py` → 271 passed; `lint-skills.py` clean.

---

### Phase 2: Remediate the near-limit sibling (`build-queue-enforce.sh`) with the same temp-file shape

**Scope:** The plane-wide audit (SPEC Sibling Check) found `build-queue-enforce.sh`'s embedded
`_BQE_PY` body at **31,966 bytes** — ~800 B under the hard limit before its env-prefix + `-c ` +
quoting overhead is even counted. It is one accretion from the identical silent E2BIG fail-open.
Convert it proactively to the Phase-1 temp-file pattern. The remaining `-c`-invoking hooks
(`long-build-ownership-guard.sh` 19,805 B, `block-terminal-kill.sh` 11,323 B,
`subagent-wedge-backstop.sh` 8,424 B, `block-sentinel-write-on-stray-branch.sh` 7,673 B,
`block-noncanonical-blocker-write.sh` 6,115 B, `block-work-repo-git-push.sh` 2,597 B) are safely
under the limit and are left on `-c` — the Phase-3 size guard keeps them honest.

**Deliverables:**
- [ ] `user/hooks/build-queue-enforce.sh`: replace the line-841 `-c "$_BQE_PY"` with the Phase-1 temp-file invocation (mktemp `.py`, `cygpath -w` where available, payload on stdin, `trap` cleanup, traced fail-open on write failure), preserving the `BQE_SCRIPTS_DIR` env passthrough and the fail-OPEN-via-JSON contract.
- [ ] Audit ledger recorded in this phase's Integration Notes: one row per `-c`-invoking hook with its measured body size and disposition (convert vs. leave-on-`-c`).
- [ ] Tests: `build-queue-enforce.sh`'s existing `test_hooks.py` coverage (deny/allow/bypass/fail-open) stays green after conversion; add/confirm a Windows drive proving it still DENIES a manifested build token under the ops manifest.

**Minimum Verifiable Behavior:** `python user/scripts/test_hooks.py` — the `build-queue-enforce`
test group stays green post-conversion; a direct Windows drive of a raw manifested build token
(under a repo with `build-queue-ops.json`) emits `permissionDecision: deny` (the redirect naming
the op's skill), not a fail-open.

**Runtime Verification** *(checked by the pytest gate / direct hook drive):*
- [ ] <!-- verification-only --> Post-conversion, `build-queue-enforce.sh` under a manifested repo still DENIES a raw build token beginning a command segment, and still ALLOWS the safe variants + the `BUILD_QUEUE_BYPASS=1` override + the `build-queue.ps1` wrapper.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:**
- Phase 1: the temp-file invocation pattern (mktemp + `cygpath -w` + trap cleanup + traced fail-open) is established and green.

**Files likely modified:**
- `user/hooks/build-queue-enforce.sh` — temp-file invocation (same shape as Phase 1).

**Testing Strategy:** Re-run the `build-queue-enforce` portion of `test_hooks.py` (deny set, safe
variants, bypass token, fail-open on malformed) against the converted hook; assert byte-for-byte
identical deny/allow behavior, only the invocation mechanism changed.

**Integration Notes for Next Phase:**
- Record the final embedded-`-c`-body census here so Phase 3's size-guard ceiling can be set below every *remaining* `-c` body. After Phases 1–2, the two large bodies no longer ship via `-c`; the max remaining `-c` body is `long-build-ownership-guard.sh` at 19,805 B → a ceiling of ~25,000 B leaves comfortable headroom while still catching any future body that creeps toward 32,767.

---

### Phase 3: Plane-wide recurrence guard — embedded-`-c`-body size ceiling test

**Scope:** Make the E2BIG class mechanically impossible to reintroduce silently. Add a test (in
`test_hooks.py`) that scans every hook still invoking `"$PYTHON" -c "$_<VAR>"`, measures the
corresponding embedded heredoc body, and FAILS if any body exceeds a conservative ceiling well
under the 32,767 `CreateProcess` limit. Hooks converted to the temp-file shape (Phases 1–2) carry
no `-c` body and are exempt by construction. This is the guard that would have caught
`build-queue-enforce.sh` before it tripped.

**Deliverables:**
- [ ] `user/scripts/test_hooks.py`: a new test that, for each hook file invoking `"$PYTHON" -c "$_..._PY"`, extracts the named heredoc body and asserts `len(body) <= CEILING` (a module constant, e.g. `25000`, with an explanatory comment citing the 32,767 Windows limit and this bug). The test discovers hooks generically (glob `user/hooks/*.sh`), so a new `-c`-invoking hook is covered automatically.
- [ ] The ceiling and its rationale are documented inline (why 25,000, the 32,767 limit, the env-prefix/quoting overhead margin, and the `docs/bugs/containment-hook-inline-python-exceeds-windows-cmdline-limit` reference).
- [ ] Tests: the new size-guard test passes (green) because Phases 1–2 removed both over-/near-limit `-c` bodies; the full `test_hooks.py` run is green.

**Minimum Verifiable Behavior:** `python user/scripts/test_hooks.py` — the new size-guard test is
present and passes; temporarily bloating any `-c`-invoking hook's body past the ceiling makes it
FAIL (demonstrated once during authoring, then reverted).

**Runtime Verification** *(checked by the pytest gate):*
- [ ] <!-- verification-only --> The size-guard test FAILS when an embedded `-c` body is inflated past the ceiling and PASSES for the shipped hooks — i.e. it actually gates, not tautologically green.

**MCP Integration Test Assertions:** N/A — pure static/pytest guard, no runtime surface.

**Prerequisites:**
- Phase 1 and Phase 2: both large `-c` bodies converted to temp-file, so the ceiling can sit below every remaining `-c` body without a false failure.

**Files likely modified:**
- `user/scripts/test_hooks.py` — new plane-wide embedded-`-c`-body size-guard test + ceiling constant.

**Testing Strategy:** Run the new test against the shipped hooks (green). Prove it gates by
inflating a body past the ceiling in a scratch copy and confirming a FAIL, then revert. Confirm the
full `test_hooks.py` suite is green end-to-end.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed and
writes FIXED.md once this phase's verification passes and the validation tail clears — this plan
never flips status or writes a receipt itself.

---

## Cross-feature Integration Notes

No hard dependencies on completed upstream features — this bug's SPEC carries no `**Depends on:**`
block (harness hook defect, self-contained). Related prior art (cross-linked in SPEC
`**Related:**`): `docs/bugs/guard-fail-open-leaves-no-trace` (this bug is a NEW untraced fail-open
class that slips between that fix's no-python and python-`except` breadcrumb sites — Phase 1's
traced-temp-write-failure deliverable closes the residual) and `user/hooks/CLAUDE.md` →
"Fail-OPEN is mandatory" / "Fail-open observability".
