# Build-Queue Enforcement Bypassed by `cd`-Prefixed Build Commands — Investigation Spec

> The `build-queue-enforce.sh` PreToolUse hook fails open whenever a heavy build is chained behind a leading command (`cd "…" && dotnet build …`), because its deny regexes are anchored to the start of the command. Agents — trained by the repo's own `AGENTS.md`/`/msbuild` examples to write exactly that form — bypass the queue and run raw `dotnet build`/`dotnet test`. A reinforcing skill-capability gap (no single-project build path) gives them a reason to.

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-06-24
**Fixed:** 2026-07-06
**Fix commit:** 3e04a72
**Placement:** docs/bugs/build-queue-enforce-cd-prefix-bypass
**Related:** `docs/bugs/build-queue-orphaned-result-on-wrapper-kill/`, `user/hooks/build-queue-enforce.sh`, `user/hooks/long-build-ownership-guard.sh`, `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md`

---

## Verified Symptoms

1. **[VERIFIED]** A Sonnet subagent executing `phase-1-lifecycle-detection-engine.md` ran `cd "C:\Users\JacobMadsen\source\repos\Cognito Forms" && dotnet build ".\Cognito.Core\Cognito.Core.csproj" -c Debug -v minimal --nologo 2>&1 | tail -20` directly via the Bash tool — it was **not** denied/redirected by the build-queue hook. *(Confirmed: user screenshot #1.)*
2. **[VERIFIED]** On retry the same agent ran the build foreground (`cd "…\Cognito Forms" && dotnet build "./Cognito.Core/Cognito.Core.csproj" … 2>&1 | tail -10`) — again not blocked, completing entirely outside the FIFO queue. *(Confirmed: user screenshot #2.)*
3. **[VERIFIED]** The agent first tried the background path, hit an empty-output / missing-task-output-file condition, got confused, and *fell back* to the raw foreground `dotnet build`. The sanctioned background-poll path was error-prone enough to abandon. *(Confirmed: user screenshot #2.)*
4. **[VERIFIED]** The bypass occurred from inside a Task-tool subagent, but the hook is not subagent-scoped — it is wired with a bare `Bash` matcher and PreToolUse fires for subagent Bash calls too. The failure is matcher coverage, not subagent exemption. *(Confirmed: `user/settings.json` PreToolUse wiring.)*

## Reproduction Steps

1. In a Cognito Forms worktree (remote matches `cognitoforms/cognito`), run via Bash:
   `cd "<repo>" && dotnet build "./Cognito.Core/Cognito.Core.csproj" -c Debug`
2. Observe: the command runs. No `permissionDecision: deny`, no `/msbuild` redirect.

**Expected:** Hook denies and redirects to `/msbuild` (as it does for a bare `dotnet build …`).
**Actual:** Hook fails open; the build runs outside the queue.
**Consistency:** Always — deterministic, driven by the regex anchor.

## Evidence Collected

### Source Code

`user/hooks/build-queue-enforce.sh` deny matchers (lines 76–98) are all anchored:

```python
_ENV_PREFIX = r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"
_DOTNET_BUILD_RE = re.compile(r"^\s*" + _ENV_PREFIX + r"dotnet\s+build(?:\s|$)")
_DOTNET_TEST_RE  = re.compile(r"^\s*" + _ENV_PREFIX + r"dotnet\s+test(?:\s|$)")
```

`^\s*` + (only `NAME=value` env assignments) means the build verb must be the **first real token**. For `cd "…" && dotnet build …` the first token is `cd`, so `.match()` returns `None` → `main()` falls through to `_allow()` (line 293). The scope gate (`_is_cognito_worktree`, lines 146–159) actually *passed* here (cwd was the Cognito worktree) — the miss is purely the deny anchor, a strict superset of the header's documented "KNOWN BLIND SPOT" (lines 33–36), which only anticipated `cd <other-repo>` defeating the *scope* gate.

`long-build-ownership-guard.sh` shares the identical `^\s*` + `_ENV_PREFIX` anchoring (lines 85–92) → the **same** `cd`-prefix blind spot exists for the `tauri build` / `cargo build --release` / `npm run build` deny set. Fix should be applied consistently across both hooks.

### Skill Capability Gap

`repos/cognito-forms/.claude/skills/msbuild/SKILL.md` always builds the whole `Cognito.sln` (`-File "…/build-filtered.ps1"`); its only params are `-Restore`, `-Test`, `-TestProject`. There is **no** single-project / `-Project` option. The agent's actual need — "did my one new `Cognito.Core` file compile?" — has no sanctioned fast path, so a raw targeted `dotnet build <csproj>` is the rational move. `/mstest` runs `--no-build` and tells the agent to "build first with `/msbuild`", compounding the friction for a quick targeted check.

### Hook Wiring

`user/settings.json` → `PreToolUse`: `build-queue-enforce.sh` and `long-build-ownership-guard.sh` are both registered under a bare `Bash` matcher (fire for all Bash, subagents included). Not a scoping problem.

### Related Documentation

- `user/hooks/CLAUDE.md` — fail-open guard family contract (deny via JSON, never non-zero exit).
- `AGENTS.md` "Command Defaults" models `cd ... && dotnet build` / `dotnet test --filter` — i.e. the repo trains agents into the exact bypassing form.
- `docs/bugs/build-queue-orphaned-result-on-wrapper-kill/` — sibling build-queue defect (just fixed on this branch); the background-poll ergonomics in symptom #3 intersect with that work.

## Theories

### Theory 1: Anchored deny regex + `cd`-prefix (PRIMARY)
- **Hypothesis:** The `^\s*`-anchored deny matchers only fire when the build verb is the first token, so any leading command (`cd && …`, a pipeline, `;`) makes the hook fail open.
- **Supporting evidence:** Regex reading above; both screenshots show `cd … && dotnet build …` passing; scope gate confirmed passing.
- **Contradicting evidence:** None.
- **Status:** **Confirmed.**

### Theory 2: Skill-capability gap creates the bypass incentive (CONTRIBUTING)
- **Hypothesis:** No single-project build path in `/msbuild` (and `--no-build`-only `/mstest`) pushes agents to raw `dotnet` for fast targeted feedback.
- **Supporting evidence:** Skill source has no `-Project`; agent explicitly targeted one `.csproj`.
- **Status:** **Confirmed** (user-corroborated).

### Theory 3: Background-poll ergonomics are agent-hostile (SECONDARY)
- **Hypothesis:** The skill's "run_in_background then poll results/<seq>.json" instructions are error-prone, so agents abandon the sanctioned path under any friction.
- **Supporting evidence:** Screenshot #2 — empty output, a failed `type …output` read, then fallback to raw foreground build.
- **Status:** Likely; lower priority than 1 & 2.

## Proven Findings

- **Root cause:** anchored deny matchers in `build-queue-enforce.sh` (and `long-build-ownership-guard.sh`) miss any build verb not at the start of the command. Confirmed from source; deterministic.
- The hook correctly fires for subagents; subagent exemption is **not** the cause.
- A real capability gap (no single-project build) gives agents a legitimate reason to bypass — enforcement alone won't remove the incentive.

## Fix Direction (confirmed with user)

**Scope: defense in depth — both prongs.**

1. **Hook hardening (chosen approach: unanchored substring match).** Deny when `dotnet build` / `dotnet test` / an nx build|test|run-many target / a `*-filtered.ps1` invocation appears **anywhere** in the command, not only at the start. Apply the same change to `long-build-ownership-guard.sh`'s long-build set.
   - **Subtlety to handle in `/plan-bug`:** unanchored deny changes allow-list semantics. The existing anchored allow-lists (`dotnet restore|--version|ef|msbuild`, `nx lint|typecheck|format`, the `build-queue.ps1` wrapper, `BUILD_QUEUE_BYPASS=1`) currently short-circuit on a leading match. With unanchored deny, a compound like `dotnet restore && dotnet build` must still **deny** (a real build is present) — so allow-list precedence must be re-derived per-build-verb, not "allow the whole command if any safe token leads." Recommended: detect each heavy-build occurrence, then suppress only the specific occurrences that are genuinely the safe variant; deny if any real heavy build remains.
   - **False-positive mitigation (record explicitly):** unanchored matching can hit `dotnet build` inside quoted strings / commit messages / `echo` / `--help` text. Keep deny scope-gated to Cognito worktrees (already so), keep `BUILD_QUEUE_BYPASS=1` as the escape hatch, and consider a cheap guard against matches inside obvious string literals. Net risk is a spurious *redirect* (non-destructive), acceptable given the bypass it closes.
2. **Skill capability (remove the incentive).** Add a sanctioned single-project build path — e.g. `/msbuild -Project "Cognito.Core/Cognito.Core.csproj"` routed through the queue wrapper — so agents have a fast targeted compile check without leaving the queue. Re-examine `/mstest` `--no-build` friction and the background-poll ergonomics (symptom #3) while here.

> Note: the user is separately updating `/write-plan` so generated plans instruct executors to use `/msbuild`+`/mstest` rather than raw `dotnet`. That is a third, complementary layer (prompt-level) and is out of scope for this bug; this spec covers the enforcement (hook) and capability (skill) layers.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Build-queue enforcement hook | `user/hooks/build-queue-enforce.sh` | Anchored deny regexes → unanchored, with re-derived allow-list precedence |
| Long-build ownership hook | `user/hooks/long-build-ownership-guard.sh` | Same `cd`-prefix blind spot; apply consistent fix |
| Build skill | `repos/cognito-forms/.claude/skills/msbuild/SKILL.md` (+ `build-filtered.ps1` / `build-queue.ps1` wrapper) | Add single-project build path |
| Test skill | `repos/cognito-forms/.claude/skills/mstest/SKILL.md` | Re-examine `--no-build` friction + background-poll ergonomics |
| Hook tests | (wherever hook unit tests live, if any) | Add cases for `cd && build`, pipelines, compound `restore && build` |

## Open Questions

- Where do (or should) the hook unit tests live so the new `cd`-prefix / compound-command cases are regression-guarded?
- For the single-project skill path: surface as a new `-Project` parameter on `/msbuild`, or a separate lightweight skill? (Defer to `/plan-bug`.)
- Should `build-filtered.ps1` / the queue wrapper gain native single-project support, or does `/msbuild -Project` just forward to `dotnet build <csproj>` under the queue lock?
