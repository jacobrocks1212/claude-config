# Build-Queue Outcome Opacity + Enforce-Hook Over-Blocks Read-Only Inspection — Investigation Spec

> Agents routinely can't tell what a `/msbuild` `/mstest` `/nxbuild` `/nxtest` invocation actually did — pass, fail, zero-match, or broken log capture all surface as the same `exit_code=0` with suppressed output — so they try to inspect the runner script / results JSON / logs to disambiguate. The `build-queue-enforce.sh` hook then DENIES that read-only inspection because its (now unanchored) deny regexes match a `*-filtered.ps1` / `dotnet build` token *anywhere* in the command, including inside a `cat`/`grep`/`tail`/`find`. The two defects compound into a wasted-cycle loop: opaque outcome → inspect to understand → inspection blocked → work around.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-03
**Placement:** docs/bugs/build-queue-outcome-opacity-and-inspect-deny
**Related:** `docs/bugs/_archive/build-queue-enforce-cd-prefix-bypass/` (the unanchored-regex change that introduced the false-positive; its SPEC line 90 *predicted* this), `docs/bugs/build-queue-orphaned-result-on-wrapper-kill/`, `docs/bugs/build-queue-recycle-kills-concurrent-worktree-build/`, `user/hooks/build-queue-enforce.sh`, `user/scripts/build-queue-runner.ps1`, `user/scripts/build-queue.ps1`, `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md`

---

## Verified Symptoms

<!-- Confirmed with the user (scope + severity) and grounded in /mine-sessions evidence across 1563 transcripts. -->

1. **[VERIFIED]** The `build-queue-enforce.sh` hook denies **read-only inspection** commands that merely *reference* a build token — a `cat`/`grep`/`tail`/`find`/`ls` of a `*-filtered.ps1` script, a `results/<seq>.json`, or a `logs/<seq>.build.err.log` — as if they were an *invocation* of a heavy build, redirecting to `/mstest`/`/msbuild`. *(Confirmed: user screenshot #1 — `cat "…/results/614.json"` denied with the `/mstest` message; plus 30+ mined deny events, below.)*
2. **[VERIFIED]** Agents frequently cannot distinguish, from a build/test invocation, **"tests genuinely passed"** vs **"the filter matched zero tests"** vs **"log capture broke / output was suppressed"** — all present as `exit_code=0` with the filtered script hiding passing output. *(Confirmed: user; mined verbatim — `"exit 0 with no failures = green — but I want to confirm tests actually ran (a zero-match filter can also exit 0)"`.)*
3. **[VERIFIED]** The opacity **causes** the hook false-positives: the agent's response to an ambiguous outcome is to `cat`/`grep` the runner, the results JSON, or the log — the exact commands the hook then denies. The two defects are one loop, not two independent bugs. *(Confirmed: mined denies include `cat …/results/614.json`, `cat build-filtered.ps1 | head`, `grep -n "stale|exit 4|WARN" test-filtered.ps1`, `cat …/logs/500.build.err.log`.)*
4. **[VERIFIED]** This is a **predicted regression** — `build-queue-enforce-cd-prefix-bypass`'s fix intentionally made the deny regexes unanchored and its SPEC recorded the false-positive as an "acceptable" risk. Observed real-world friction now reclassifies that risk as a defect worth fixing. *(Confirmed: that SPEC line 90.)*
5. **[REPORTED/SUSPECTED]** The `results/` dir is **machine-global** and shared across worktrees, so an agent that resolves "its" result by newest-file globbing can read a *concurrent worktree's* `seq`, misattributing a `build_fidelity: log-failure-override` from another build. *(Source: mined — `"most recent file from results/*.json … shared across all worktrees … That concurrent build in another worktree (seq=444/446) likely wrote a build_fidelity: log-failure-override"`.)*

## Reproduction Steps

**Thread A — read-only inspection denied:**
1. In a Cognito Forms worktree, after a `/mstest` run, inspect the result: `cat "$HOME/.claude/state/build-queue/results/<seq>.json"` in a command that also references `test-filtered.ps1` (or `cat`/`grep`/`head` the runner script itself).
2. Observe: `permissionDecision: deny` — "BUILD QUEUE ENFORCED — use `/mstest` or `/nxtest` instead of invoking *-filtered.ps1 directly."

**Expected:** A read-only `cat`/`grep`/`tail`/`find` that does not *invoke* a build runs normally.
**Actual:** Denied because a build token appears anywhere in the command string.
**Consistency:** Always — deterministic, driven by the unanchored substring regex.

**Thread B — opaque outcome:**
1. Run `/mstest -Filter "ClassName~DoesNotExist"` (a filter that matches zero tests), or a `/mstest` where the per-test stream buffers to console instead of the log.
2. Observe: `exit_code=0`, filtered output empty — indistinguishable from an all-green run.

**Expected:** The invocation states, immediately and unambiguously, tests-run count, pass/fail counts, whether the filter matched anything, and the next action.
**Actual:** `exit_code=0` + empty output; the agent must open the runner/log/results to guess what happened.
**Consistency:** Whenever the filter matches nothing, output is suppressed, or log capture drops the stream.

## Evidence Collected

### /mine-sessions (hard evidence — 1563 transcripts across 10 Cognito worktree dirs)

Scanner added to the toolkit: `user/skills/mine-sessions/scripts/scan_build_queue_friction.py` (streams every transcript + subagent file, joins each `BUILD QUEUE ENFORCED` deny to its triggering Bash command, and greps a curated outcome-confusion phrase set).

**Hook denies — 51 total.** Excluding 9 hook-*test-harness* invocations (sessions developing the hook itself), **42 real-world denies**, classified by triggering command:

| Class | Count | Verdict |
|-------|------:|---------|
| `readonly-inspect` (cat/grep/tail/find/ls of a script/log/results) | 14 | **False positive** |
| `mixed-inspect-ref` (inspection command that also contains a build token) | 20 | **Mostly false positive** |
| `other` / `unknown` (e.g. `git diff user/settings.json`) | 5 | Mostly false positive (regex hit hook/diff text) |
| `real-build` (an actual off-queue `*-filtered.ps1` invocation) | 3 | Legitimate deny |

Representative false-positive triggers (verbatim): `cat "…/results/614.json"` (the screenshot), `cat build-filtered.ps1 … head -100`, `grep -n "stale\|exit 4\|WARN" test-filtered.ps1`, `cat …/logs/500.build.err.log; … build-filtered.ps1 output path`, `find . -name "build-filtered.ps1"`, `git diff user/settings.json`. Only ~3 of 42 real-world denies were genuine off-queue builds — the deny surface is overwhelmingly hitting inspection, not invocation.

**Outcome-confusion — 343 phrase hits** (some noise in the raw `ambiguous`/`empty` buckets; the build/test-specific signal is unambiguous):

| Signal | Count |
|--------|------:|
| `tautolog*` (worry a passing test proves nothing / is tautological) | 54 |
| `no output` / `zero output` | 39 |
| `red flag` | 29 |
| `zero test` / `matched nothing` | 16 |
| `log capture` (dropped/broken) | 8 |
| distinct one-off `exit 0 … suspicious/surprising/unexpected/off/fail/red` phrasings | ~35 |
| `inspect the runner` / `inspect the result` / `build_fidelity` | ~6 |

Verbatim, high-signal:
- *"The filtered script suppresses passing names, so exit 0 with no failures = green — but I want to confirm tests actually **ran** (a zero-match filter can also exit 0). Let me find the test results file."*
- *"Exit code 0 is surprising given the SPEC predicted 27 failures. Let me read the test output log."* → *"The scripts use `Write-Host` and the log capture seems to be dropping it. Let me check the runner to understand output capture…"*
- *"the per-test stream buffered to console rather than the log file, but the queue's `exit_code=0` is the authoritative…"* (agent unsure which signal to trust)
- *"Let's inspect the runner script to see exactly how it invokes the exec…"* (the inspection that then gets denied)

### Source Code

- `user/hooks/build-queue-enforce.sh` — `_FILTERED_SCRIPT_RE` (lines 110–113) matches `(build|test|client-build|client-test)-filtered\.ps1` **anywhere** in the command; `_DOTNET_BUILD_RE`/`_DOTNET_TEST_RE`/`_NX_BUILD_TEST_RE` likewise scan the whole (safe-variant-suppressed) command. The only pre-deny exemptions are `BUILD_QUEUE_BYPASS=1` (`_BYPASS_RE`) and the `build-queue.ps1` wrapper (`_WRAPPER_RE`). There is **no exemption for a read-only leading verb** and **no distinction between invoking a script and naming it** as a `cat`/redirect/`grep` target. A `cat "…/results/614.json"` whose command also contains `test-filtered.ps1` matches `_FILTERED_SCRIPT_RE` → `_deny(filtered-test)`.
- `user/scripts/build-queue-runner.ps1` — the results JSON schema (lines 177–189) already records `result_fidelity` (`verified`/`no-output`/`n/a`) and `build_fidelity` (`verified`/`log-failure-override`/`n/a`), and `test-filtered.ps1` exits `3` on zero output / `4` on staleness. **The data largely exists** — but it is buried in a JSON file the agent must fetch by `seq`, not surfaced in the invocation's own stdout, so `exit_code=0` remains the only thing the agent sees inline. The `no-output` fidelity is derived only from `exitCode==3`; a **zero-match filter that still exits 0** is NOT flagged `no-output`, so Symptom 2's most common case is invisible even in the JSON.
- `repos/cognito-forms/.claude/skills/mstest/SKILL.md` — instruction 3 says "Do not interpret or reformat the output"; the filtered script suppresses passing test names, so a green run and a zero-match run look identical inline. Instruction 4's background path tells the agent to read `results/<seq>.json` by the `seq` from the enqueue line — but under output truncation / concurrency agents fall back to globbing `results/*.json`, hitting the machine-global-dir wrong-seq trap (Symptom 5).

### Git History

Recent build-queue hardening (last ~10 commits) fixed honesty/hygiene at the *result-file* layer (`build_fidelity`, `result_fidelity`, DLL quarantine, occupancy-gated recycle) and closed the `cd`-prefix enforcement bypass — but none surfaced the outcome inline to the caller, and the bypass fix is what introduced the inspection false-positive. This bug is the "last mile": make the outcome legible at the point of invocation and stop blocking the agent from reading it.

### Related Documentation

- `docs/bugs/_archive/build-queue-enforce-cd-prefix-bypass/SPEC.md` line 90 — explicitly predicted the unanchored-match false-positive and deferred it as acceptable.
- `user/hooks/CLAUDE.md` — fail-OPEN + deny-via-JSON contract (any fix must preserve both).
- `repos/cognito-forms/CLAUDE.local.md` (Build & Test Workflow) — the sanctioned-skills contract the enforcement protects.

## Theories

### Theory 1: Unanchored deny regex can't distinguish invoke-vs-reference (PRIMARY — hook thread)
- **Hypothesis:** `_FILTERED_SCRIPT_RE` (and the dotnet/nx matchers) fire on a build token *anywhere* in the command, so a read-only `cat`/`grep`/`tail`/`find` that names a runner script, result, or log is denied identically to an actual invocation.
- **Supporting evidence:** Source reading above; 30+ mined false-positive denies vs ~3 legitimate; the screenshot; the cd-prefix SPEC's own prediction.
- **Contradicting evidence:** None.
- **Status:** **Confirmed.**

### Theory 2: Outcome is not surfaced inline; `exit_code=0` is overloaded (PRIMARY — fidelity thread)
- **Hypothesis:** pass / zero-match-filter / suppressed-or-dropped-output all collapse to `exit_code=0` with empty filtered output, forcing the agent to reverse-engineer the runner/log/results to learn what happened.
- **Supporting evidence:** 54 tautological-worry + 39 no-output + 29 red-flag + ~35 exit-0-suspicion mined hits; verbatim quotes; the runner records fidelity in JSON but not inline, and does not flag a zero-match-but-exit-0 filter at all.
- **Contradicting evidence:** Much of the needed data already exists in `results/<seq>.json` (`result_fidelity`, `build_fidelity`, exit 3/4) — this is a *surfacing/completeness* gap, not a data-collection gap. Lowers effort, not validity.
- **Status:** **Confirmed.**

### Theory 3: Machine-global `results/` dir → wrong-seq attribution (CONTRIBUTING)
- **Hypothesis:** because `results/` is shared across worktrees and the skill's fallback is newest-file globbing, a concurrent worktree's `seq` gets read, misattributing its fidelity/exit code.
- **Supporting evidence:** one clear mined instance naming seq=444/446 cross-worktree; the global-dir design is confirmed in `build-queue-runner.ps1`.
- **Status:** Likely; lower frequency than 1 & 2. Fold into the fidelity fix (make the invocation echo *its own* seq + outcome inline so no globbing is needed).

## Proven Findings

- **Root cause (hook):** the deny surface matches invocation tokens as bare substrings with no invoke-vs-reference discrimination and no read-only-verb exemption; ~85% of real-world denies are false positives on inspection commands. Deterministic, confirmed from source.
- **Root cause (fidelity):** the invocation surfaces only `exit_code`, which is overloaded across pass / zero-match / suppressed-output; the disambiguating data mostly exists in `results/<seq>.json` but is neither inline nor complete (zero-match-exit-0 unflagged).
- **The two are one loop:** opacity drives the very inspection the hook then blocks. Fixing only one leaves the loop intact — fix both.

## Fix Direction (recommended; final approach deferred to /plan-bug per user)

**Defense in depth — both threads, mirrored across the enforcement family.**

1. **Hook — distinguish invocation from reference (recommended over a read-verb whitelist).** Deny only when a heavy build is the *invoked* command: the build token begins a command segment (start, or after `&&`/`;`/`|`/`(`), OR appears as a `powershell(.exe) … -File <script>` argument. A build token that appears only as an argument to a read-only verb (`cat`/`less`/`head`/`tail`/`grep`/`rg`/`find`/`ls`/`Get-Content`/`Select-String`/`type`), inside a quoted results/log path, or in `git diff`/`echo` text, does NOT deny. This *preserves* the cd-prefix fix (a real `cd … && dotnet build` still denies — `dotnet build` is a segment-leading invocation) while removing the inspection false-positive.
   - Apply the same invoke-vs-reference discrimination to `long-build-ownership-guard.sh` (shares the unanchored-substring shape).
   - Keep `BUILD_QUEUE_BYPASS=1` and the `build-queue.ps1` wrapper exemptions; keep fail-OPEN + deny-via-JSON.
   - A read-verb whitelist is the simpler fallback if segment-parsing proves fragile — capture both options for /plan-bug; recommend invoke-vs-reference.
2. **Runner/skills — make the outcome legible inline.** Have the queue wrapper/runner print a one-line, unambiguous outcome banner to the *invocation's own stdout* (the thing the agent already sees), e.g. `build-queue: seq=614 op=mstest RESULT=PASS tests=312 failed=0 (result_fidelity=verified)` — and critically distinguish **zero-match / zero-output** (`RESULT=NO-TESTS-MATCHED`, non-green) from a true green. Include the explicit **next action** on any non-clean outcome (rebuild on staleness exit 4, widen filter on zero-match, read `logs/<seq>.build.err.log` on log-failure-override). This removes the incentive to `cat` the runner/results at all.
   - Close the data gap: flag a **zero-match filter that still exits 0** as a distinct non-`verified` fidelity (today only `exitCode==3` yields `no-output`).
   - Echo the invocation's **own seq** in the banner so agents never glob the machine-global `results/` dir (Symptom 5).
3. **Regression coverage.** Add hook cases: `cat results/<seq>.json`, `grep test-filtered.ps1`, `tail logs/<seq>.build.err.log`, `find -name build-filtered.ps1`, `git diff settings.json` → ALLOW; `dotnet build`, `cd … && dotnet test`, bare `*-filtered.ps1` invocation, `restore && build` → DENY. (Open Q from the sibling bug: where hook unit tests live.)

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Build-queue enforcement hook | `user/hooks/build-queue-enforce.sh` | Invoke-vs-reference discrimination (or read-verb whitelist) in the deny surface |
| Long-build ownership hook | `user/hooks/long-build-ownership-guard.sh` | Same discrimination for consistency |
| Queue runner | `user/scripts/build-queue-runner.ps1` | Flag zero-match-exit-0; make outcome + fidelity + next-action inline-legible |
| Queue wrapper | `user/scripts/build-queue.ps1` | Emit a one-line outcome banner (seq + RESULT + counts + next action) to stdout |
| Build/test skills | `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md` | Tell agents to trust the banner; drop the "glob results/" fallback |
| Mine-sessions toolkit | `user/skills/mine-sessions/scripts/scan_build_queue_friction.py` | New reusable scanner (added during this investigation) |
| Hook tests | (location TBD — see Open Questions) | Add invoke-vs-reference regression cases |

## Open Questions

- Where do hook unit tests live so the invoke-vs-reference cases are regression-guarded? (Carried over unresolved from `build-queue-enforce-cd-prefix-bypass`.)
- Invoke-vs-reference **segment parsing** vs the simpler **read-only-verb whitelist** — which is robust enough without re-opening a bypass? (Recommend the former; decide in `/plan-bug`.)
- Banner surface: emit from `build-queue.ps1` (wrapper, always in the foreground path) vs `build-queue-runner.ps1` (detached, survives wrapper kill) — or both? Background-poll path needs the banner in the result too.
- Should the zero-match-filter detection live in `test-filtered.ps1` (it knows the discovered-test count) or be inferred in the runner? (Likely the former.)
