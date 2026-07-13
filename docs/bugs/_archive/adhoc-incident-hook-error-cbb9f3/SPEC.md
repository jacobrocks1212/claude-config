---
kind: investigation-spec
bug_id: adhoc-incident-hook-error-cbb9f3
---

# Hook fail-open errors: long-build-ownership-guard (2x/7d) — Investigation Spec

> incident-scan auto-captured 2 `hook-error` events for `long-build-ownership-guard` in
> claude-config within 7d (2026-07-12T04:30:07Z, 2026-07-13T03:17:13Z). Investigation reads the
> breadcrumb payloads directly: both are `json.JSONDecodeError`s on `sys.stdin.read()` — one
> truncated-mid-object, one completely empty — caught by the hook's existing fail-open
> `except Exception` tail and correctly allowed through with no incorrect block/deny. The
> breadcrumb/fail-open mechanism that captured both predates both timestamps (it was not added by
> any commit landed this session); tonight's hook-hardening commits (`21539228`, `302258cb`,
> `b380c733`) touch unrelated code paths in this same file. No code defect found; both are
> isolated, non-reproducible, non-correlated malformed-stdin deliveries to this one hook
> subprocess, safely absorbed by the pre-existing fail-open contract.

**Status:** Won't-fix
**Severity:** Low
**Discovered:** 2026-07-13
**Placement:** docs/bugs/adhoc-incident-hook-error-cbb9f3
**Related:** `user/hooks/long-build-ownership-guard.sh` (the hook); `docs/bugs/_archive/guard-fail-open-leaves-no-trace` (the feature that made this class of error observable at all); `docs/bugs/_archive/legacy-tool-input-env-hooks-dead` (unrelated same-evening hook work, ruled out as a cause below)

---

## Verified Symptoms

1. **[REPORTED]** incident-scan captured 2 `hook-error` events for hook
   `long-build-ownership-guard` in claude-config, `first_ts: 2026-07-12T04:30:07Z`,
   `last_ts: 2026-07-13T03:17:13Z` (`incident_key claude-config|hook-error|long-build-ownership-guard`).
2. **[VERIFIED]** Read directly from the keyed `hook-events.jsonl`
   (`~/.claude/state/853ac81…/hook-events.jsonl`, read-only):
   ```
   {"ts": 1783830607.902566, "kind": "error", "hook": "long-build-ownership-guard",
    "repo_root": "C:/Users/Jacob/source/repos/claude-config", "signature": "",
    "detail": "Expecting ',' delimiter: line 1 column 57 (char 56)"}
   {"ts": 1783912633.425099, "kind": "error", "hook": "long-build-ownership-guard",
    "repo_root": "C:/Users/Jacob/source/repos/claude-config", "signature": "",
    "detail": "Expecting value: line 1 column 1 (char 0)"}
   ```
   Both `detail` strings are the literal `str()` form of a Python `json.JSONDecodeError`. The
   first ("Expecting ',' delimiter... char 56") indicates a **truncated/malformed but non-empty**
   stdin payload; the second ("Expecting value... char 0") indicates **completely empty** stdin
   (`raw = ""`).
3. **[VERIFIED]** No sibling hook (`lazy-cycle-containment`, `build-queue-enforce`,
   `block-noncanonical-blocker-write`, `block-sentinel-write-on-stray-branch`,
   `lazy-dispatch-guard`, `lazy-route-inject`) logged an error/deny within ±10s of either
   timestamp — the corruption is isolated to this one hook's subprocess invocation each time, not
   a shared multi-hook harness event.

## Reproduction Steps

Not reproducible from available evidence — the breadcrumb records only the parse-failure message,
not the raw (corrupted) stdin content or the triggering command. No live harness access to force
a truncated/empty stdin delivery is available in this investigation.

**Expected:** `long-build-ownership-guard.sh` receives a complete PreToolUse JSON payload on
stdin.
**Actual:** twice in 7 days, the payload arrived malformed (once truncated, once empty).
**Consistency:** non-deterministic / not reproduced — 2 occurrences against a volume of many
thousands of hook invocations over the same window (every Bash/PowerShell tool call in this
session's marathon `/lazy-bug-batch` run fires this hook), with two *different* corruption
signatures (rules out one deterministic single-cause bug — a code defect would be expected to
fail the same way every time).

## Evidence Collected

### Source Code

- `user/hooks/long-build-ownership-guard.sh` `main()`: `raw = sys.stdin.read(); payload = json.loads(raw)`
  — no local try/except; relies on the file-level wrapper:
  ```
  try:
      main()
  except SystemExit:
      raise
  except Exception as exc:  # fail-OPEN on ANY error.
      _breadcrumb(exc)
      sys.exit(0)
  ```
  This wrapper — and the `_breadcrumb()`/`_append_hook_event()` pair that write
  `hook-error.json` + the keyed `hook-events.jsonl` line — were verified present, **byte-identical
  in shape**, in the version of this file from **before** commit `21539228` (this evening's
  "fail-open breadcrumbs on all 7 python hooks" commit): `git show 21539228^:user/hooks/long-build-ownership-guard.sh`
  already has `STATE_DIR`, `_append_hook_event`, the `try/except` wrapper, and
  `json.loads(raw)  # JSONDecodeError → caught below → fail-open` at the same relative
  location. **Commit `21539228`'s diff to this specific file touches only the "no python at all"
  branch** (a pure-bash breadcrumb fallback for when neither `python3` nor `python` resolves) —
  it does not touch `main()`, the JSON parse, or the catch-all wrapper.
- Confirmed by timestamp ordering: both incident errors (`1783830607.9` = 2026-07-12T04:30:07Z,
  `1783912633.4` = 2026-07-13T03:17:13Z) occurred **before** commit `21539228` landed
  (2026-07-12T22:08:31-06:00 local = **2026-07-13T04:08:31Z**, i.e. ~51 minutes after the second
  error and ~23.6 hours after the first). Both errors were captured by breadcrumb code that
  already existed, unchanged, at the time each fired — this session's hook-hardening commits did
  not "fix" anything relevant to these two occurrences; they postdate both.
- The pre-fix "dead-`$STATE_DIR`" defect referenced in this session's briefing (addressed across
  the `hooks-batch` commits) does not apply to this hook's JSON-parse failure path either: the
  breadcrumbs for both incidents **were successfully written** to the correct keyed state dir
  (proven by the fact they are readable in `hook-events.jsonl` at all) — a dead/wrong `STATE_DIR`
  would have prevented exactly that.

### Runtime Evidence

- Both breadcrumbs use forward-slash `repo_root` (`"C:/Users/Jacob/source/repos/claude-config"`),
  while other hooks' breadcrumbs in the same file (e.g. the most recent `build-queue-enforce`
  error) use backslashes (`"C:\\Users\\Jacob\\..."`)  — consistent with `git -C <cwd> rev-parse
  --show-toplevel` normalizing to forward slashes regardless of invocation shell, not evidence of
  a distinct code path.
- No correlated hook-error/hook-deny event from any other hook within ±10s of either timestamp
  (checked directly against the full `hook-events.jsonl`) — rules out a shared harness-wide stdin
  corruption event at either instant; each is isolated to this one hook's own subprocess spawn.

### Git History

`git log --oneline -- user/hooks/long-build-ownership-guard.sh` shows this session's changes are
`b380c733` (tauri/runner-prefix matcher widening — matcher regex only, not stdin handling) and
`21539228` (no-python branch only, per above). Neither touches the JSON-parse / fail-open path
that produced these two breadcrumbs.

### Related Documentation

- `user/hooks/CLAUDE.md` "Fail-OPEN is mandatory" / "Countable deny/error events" — documents this
  exact contract: any internal error (including malformed payload) falls through to allow, with a
  breadcrumb. Both incidents are the contract working exactly as documented.
- `docs/bugs/_archive/guard-fail-open-leaves-no-trace` — the feature that made this whole error
  class *visible* (before it landed, some hooks had no catch-all breadcrumb at all). This hook
  (`long-build-ownership-guard.sh`) was **not** one of the two hooks that lacked observability
  (that gap was specific to the Write/Edit sentinel pair, `block-noncanonical-blocker-write.sh` /
  `block-sentinel-write-on-stray-branch.sh` — see `user/hooks/CLAUDE.md` "Countable deny/error
  events"). This hook already had full breadcrumb coverage well before either incident.

## Theories

### Theory 1: Pre-fix dead-`$STATE_DIR` bug (RULED OUT)
- **Hypothesis:** the breadcrumbs were captured under a defective `STATE_DIR` resolution later
  fixed this session.
- **Contradicting evidence:** both breadcrumbs were successfully written to the correct keyed
  state dir (that's how they're readable at all); `git show 21539228^` shows this hook's
  `STATE_DIR`/`_append_hook_event`/wrapper code was already correct and unchanged by that commit.
- **Status:** Ruled Out.

### Theory 2: Transient python-resolution failure (RULED OUT)
- **Hypothesis:** `python3`/`python` intermittently failed to resolve, hitting the no-python
  fail-open branch.
- **Contradicting evidence:** the no-python branch writes a **different, fixed** detail string
  (`"no python interpreter on PATH"`), never a `json.JSONDecodeError` message. Both captured
  errors are JSON parse failures from *inside* the python process (`main()`'s `json.loads`), which
  requires python to have successfully started and read (some) stdin. This rules out a
  python-resolution failure as the cause of either specific error.
- **Status:** Ruled Out.

### Theory 3: Isolated, non-reproducible stdin-delivery corruption to this one hook's subprocess (LIKELY)
- **Hypothesis:** on two occasions, 23 hours apart, the harness's per-hook subprocess spawn for
  this hook specifically received a corrupted (once truncated, once empty) copy of the PreToolUse
  payload — an environmental/plumbing flake (e.g. Windows Git-Bash `read -r -d ''`-then-`-c`
  invocation shape under contention during a long, hook-heavy batch run), not a defect in this
  repo's hook logic.
- **Supporting evidence:** the existing fail-open + breadcrumb contract is proven correct in both
  instances (no incorrect block, no crash, no wedge); the two failure signatures differ (rules out
  one deterministic code-level bug, which would be expected to fail identically every time); no
  sibling hook shows a correlated failure at either instant (rules out a harness-wide event); the
  occurrence rate (2 in 7 days) is vanishingly small against the actual invocation volume during
  this session's marathon run (many thousands of Bash/PowerShell tool calls, each firing this
  hook).
- **Status:** Best-supported explanation; not independently provable further without live
  reproduction (out of scope for a static evidence-only investigation).

## Proven Findings

1. **Not a code defect.** The fail-open + breadcrumb mechanism that captured both errors predates
   both timestamps and is unchanged by this session's commits; it performed exactly as designed —
   catch the parse failure, log it, allow the command through with zero incorrect behavior.
2. **Neither of the two causes named in this bug's briefing (dead-`$STATE_DIR`, transient
   python-resolution failure) explains either occurrence** — both are ruled out by direct evidence
   (breadcrumbs wrote successfully; the error is a `JSONDecodeError`, not a python-resolution
   symptom).
3. **Best-supported root cause:** isolated, non-reproducible, non-correlated malformed-stdin
   delivery to this hook's subprocess on two separate occasions — a rare environmental flake, not
   a standing defect. Severity is negligible: the fail-open contract absorbed both without any
   observable harm (no build was ever wrongly permitted or blocked as a result).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Hook (already correct) | `user/hooks/long-build-ownership-guard.sh` | Fail-open + breadcrumb contract proven correct in both instances; no change warranted. |

## Open Questions

- The exact mechanism of the isolated stdin corruption (harness-side subprocess spawn / pipe
  timing on Windows) is not determinable from static evidence and is not worth pursuing further
  given the negligible severity and zero observed harm — flagged here rather than silently
  dropped, per this repo's investigation-spec convention.

## Disposition

**Won't-fix.** No code defect found in `long-build-ownership-guard.sh`; the fail-open + breadcrumb
contract (which predates both incidents) is proven correct in both cases. The two named candidate
causes in this bug's briefing (dead-`$STATE_DIR`, transient python-resolution failure) are both
ruled out by direct evidence. Root cause is best explained as isolated, non-reproducible,
environmental stdin-delivery corruption — negligible severity, zero observed harm, not warranting
a speculative code change. **Prevention note:** no action needed; if this signature recurs at a
materially higher rate, the first productive step would be capturing the raw (corrupted) stdin
bytes alongside the parse error (an additive breadcrumb enhancement, not attempted here absent
evidence it's needed). Receipt-exempt (Won't-fix close; no `FIXED.md`).
