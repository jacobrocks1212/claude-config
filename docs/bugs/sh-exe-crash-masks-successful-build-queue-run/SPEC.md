# Git-Bash `sh.exe` crash surfaces as a false build-queue FAIL — Investigation Spec

> Git Bash's `sh.exe` intermittently segfaults while hosting a `build-queue.ps1` invocation from the Bash tool. The tool reports `Segmentation fault` / exit 139 and a `sh.exe.stackdump` file appears in the repo root, but `build-queue.ps1` had already run to completion and the wrapped build had genuinely succeeded — the crash is in the shell process, not in the queued operation. Nothing in the harness tells an agent to disbelieve the shell-level signal and check the seq's own log/banner first.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-08
**Placement:** docs/bugs/sh-exe-crash-masks-successful-build-queue-run
**Related:** `docs/bugs/build-queue-false-green-on-silent-build-failure/` (sibling "can the signal be trusted?" theme, opposite direction — that spec is a false PASS on a broken build; this one is a false FAIL/crash on a working build), `docs/bugs/build-queue-outcome-opacity-and-inspect-deny/` (agents already resort to inspecting queue state when the outcome is unclear), `docs/features/skill-usage-miner/PHASES.md:176` (prior awareness of `sh.exe.stackdump` as a stray file, not as a signal-integrity issue)

---

## Verified Symptoms

1. **[VERIFIED]** Running `powershell.exe -ExecutionPolicy Bypass -File build-queue.ps1 -Op msbuild -Exec build-filtered.ps1 -Project "Cognito/Cognito.csproj"` through the Bash tool returned `Exit code 139` with the literal error text `/usr/bin/bash: line 1: 3170 Segmentation fault      powershell.exe -ExecutionPolicy Bypass -File ...` — directly observed in this session (Cognito Forms-C repo, seq=855).
2. **[VERIFIED]** A `sh.exe.stackdump` file was written to the repo root at the time of the crash (`Cognito Forms-C/sh.exe.stackdump`), and an earlier, unrelated occurrence of the same artifact was already present in that repo's git status at the very start of this session — this is a recurring event, not a one-off.
3. **[VERIFIED]** Despite the reported segfault, `build-queue.ps1` had already completed its full run: the seq's own log shows `build-queue: seq=855 op=msbuild RESULT=FAIL (result_fidelity=n/a) -> read logs/855.build.err.log` (a banner produced by `Format-BuildQueueBanner`, `user/scripts/build-queue-hygiene.ps1:1419`), and the underlying build log (`855.build.log`) reads `Building solution...` / `Build SUCCEEDED (0 Errors)` — i.e. the actual `dotnet build` succeeded, but the crash left the queue's own outcome banner reporting FAIL.
4. **[VERIFIED]** The crash is reproducible with an identical stack trace across unrelated repos: `Cognito Forms-C/sh.exe.stackdump` and `claude-config/sh.exe.stackdump` (captured independently, different working directories) contain byte-for-byte identical frame addresses (`00210062B0E`, `0021004846A`, `002100484A2`, `002100D307E`, `002100D31A5`, `002100D4765`). Identical addresses across independent invocations point to a deterministic crash inside a fixed-base DLL (consistent with the well-known MSYS2/Cygwin `fork()`/DLL-rebase failure class), not a use-after-free or a race condition triggered by anything this repo's scripts do.

## Reproduction Steps

1. From a Cognito worktree (or any repo), run a `build-queue.ps1`-wrapped operation via the Bash tool, e.g.:
   `REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op msbuild -Exec "$REPO_ROOT/.claude/scripts/build-filtered.ps1" -Project "<any>.csproj"`
2. Intermittently (not on every run — not reproducible on demand in this session), the Bash tool reports `Segmentation fault` and a nonzero exit code, and a `sh.exe.stackdump` file appears in the current directory.
3. Inspect `~/.claude/state/build-queue/logs/<seq>.log` and `<seq>.build.log` for the same `seq` — they show the wrapped build/test operation ran to completion, independent of whatever exit signal the shell surfaced.

**Expected:** A `Segmentation fault` / exit 139 from the Bash tool should not be trusted as the outcome of the queued operation; the seq's own log/banner (or `/build-queue-status`) is the source of truth.
**Actual:** The raw shell-level signal looks identical to (and is easy to mistake for) a real build-queue failure, and nothing in the harness tells an agent to cross-check the log before acting on it.
**Consistency:** Intermittent — could not be reproduced on demand; observed twice in this session across two different repos with byte-identical crash signatures.

## Evidence Collected

### Source Code
- `user/scripts/build-queue.ps1:343-350` — the *outer* script (the one the Bash tool invokes directly and whose process is hosted by `sh.exe`) starts a *second*, detached `powershell.exe` running `build-queue-runner.ps1` via `Start-Process`, then tails its log and, at `:420`, sets `$exitCode = $proc.ExitCode` (the runner's exit code) and at `:496-500` formats and prints the final banner before `exit $exitCode`. All of this ran to completion in the observed case (the banner text was captured), so the outer script itself did not fail — the crash manifested as `sh.exe` (the host process the Bash tool spawned) terminating abnormally, not as a genuine PowerShell exception.
- `user/scripts/build-queue-hygiene.ps1:1419-1440` (`Format-BuildQueueBanner`) — `RESULT=FAIL` fires whenever `$ExitCode -ne 0`, independent of `$BuildFidelity`; in this instance `result_fidelity=n/a`, meaning the hygiene payload the banner read was itself incomplete, consistent with the runner process being disrupted mid-run by the same environmental event rather than a real build defect (the build log it wrote before that point already shows `Build SUCCEEDED (0 Errors)`).
- No code path in `build-queue.ps1`, `build-queue-runner.ps1`, or `build-queue-hygiene.ps1` is implicated as the source of the crash — the stack trace addresses point outside any script this repo owns (see Verified Symptom 4).

### Runtime Evidence
- `~/.claude/state/build-queue/logs/855.log` = `True` (single stray boolean line — truncated capture).
- `~/.claude/state/build-queue/logs/855.build.log` = `Building solution...` / `Build SUCCEEDED (0 Errors)`.
- `~/.claude/state/build-queue/logs/855.err.log` and `855.build.err.log` = both empty.
- `Cognito Forms-C/sh.exe.stackdump` and `claude-config/sh.exe.stackdump` — identical 6-frame stack traces (see Verified Symptom 4).

### Related Documentation
- `docs/features/skill-usage-miner/PHASES.md:176-182` already treats `sh.exe.stackdump` purely as a stray file to sweep during workspace hygiene passes — it was not previously connected to a build-queue signal-integrity risk.
- `docs/bugs/build-queue-false-green-on-silent-build-failure/` and siblings establish the precedent that "trust but verify" already applies to build-queue signals for *build-side* misclassification; this spec extends the same discipline to *shell-host* crashes that occur around (not inside) the queue's own logic.

## Theories

### Theory 1: `sh.exe` (Git Bash/MSYS2) crashes independently of the wrapped PowerShell operation
- **Hypothesis:** The segfault originates in the MSYS2 runtime hosting `sh.exe` — a known class of intermittent `fork()`/DLL-rebase-conflict crash in Cygwin-derived shells on Windows — and is unrelated to anything `build-queue.ps1` or the wrapped build does.
- **Supporting evidence:** Identical stack-trace addresses across two independent invocations in two different repos (Verified Symptom 4); the wrapped operation's own artifacts (banner text, `.build.log`) show it completed and succeeded before/independent of the crash; no code in this repo's scripts appears in the crash frames.
- **Contradicting evidence:** None found — no evidence ties the crash to a specific line in this repo's PowerShell scripts.
- **Status:** Confirmed (traced via direct log/artifact inspection, not inferred).

### Theory 2 (out of scope): Root cause of *why* `sh.exe` itself segfaults
- **Hypothesis:** Some interaction between Git-for-Windows' MSYS2 build, Windows Defender/AV, or a DLL rebase collision causes the intermittent crash.
- **Supporting evidence:** This is a widely-documented external phenomenon in Git-for-Windows/MSYS2 issue trackers; not something fixable from within this repo's scripts.
- **Contradicting evidence:** N/A.
- **Status:** Unverified — explicitly not pursued; no file in this repository can fix a crash inside the MSYS2 runtime itself. Tracked as an accepted environmental risk, not a harness defect to patch.

## Proven Findings

- The observed "build-queue FAIL" signal in this instance was **not** a real build-queue defect: `build-queue.ps1`'s own banner and the underlying `.build.log` for the same `seq` show the wrapped build succeeded. The false-FAIL appearance was produced by `sh.exe` crashing around the same time, which both (a) surfaced a misleading `Segmentation fault`/exit 139 to the Bash tool and (b) apparently disrupted the runner process's hygiene payload write, leaving `result_fidelity=n/a` in an otherwise-successful build's banner.
- **Fix-site-on-path:** there is no in-repo fix site for the crash itself (Theory 2 is out of scope). The actionable harness gap is procedural: nothing currently tells an agent, when the Bash tool reports a shell-level crash/segfault around a build-queue invocation, to treat the seq's own `<seq>.log`/`<seq>.build.log` (or `/build-queue-status`) as the source of truth rather than the shell's exit signal.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Agent build/test workflow guidance | `repos/cognito-forms/CLAUDE.local.md` (Build & Test Workflow section), `user/skills/build-queue-status/` (if applicable) | Agents may misinterpret a shell-level crash as a real build/test failure and waste a cycle re-investigating or re-running instead of reading the seq log |
| `build-queue.ps1` / `build-queue-hygiene.ps1` | No code defect found; `result_fidelity=n/a` on a crash-disrupted run is a reasonable degrade, not a bug | None — behaves correctly given a crashed host process |

## Open Questions

- None blocking. The unresolved item (why `sh.exe` itself segfaults) is explicitly out of scope per Theory 2 — it is an external MSYS2/Git-for-Windows runtime issue with no code path in this repository to fix.
