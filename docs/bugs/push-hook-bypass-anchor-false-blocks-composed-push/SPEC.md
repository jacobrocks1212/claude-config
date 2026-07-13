# Push-hook bypass token `^`-anchored — false-blocks any composed approved push — Investigation Spec

> The work-repo push hook only honors the `CLAUDE_PUSH_APPROVED=1` bypass when it *leads the whole command string*, so an approved push prefixed with `cd …&&` (or any other command/env) is falsely blocked.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-13
**Placement:** docs/bugs/push-hook-bypass-anchor-false-blocks-composed-push
**Related:** `docs/bugs/legacy-tool-input-env-hooks-dead/` (this hook's prior stdin-JSON rewrite), `docs/bugs/powershell-tool-bypasses-bash-matched-guards/` and `docs/bugs/_archive/long-build-and-build-queue-matcher-bypasses/` (sibling hook-matcher robustness), `user/skills/push/SKILL.md` (the sanctioned caller)

---

## Verified Symptoms

1. **[VERIFIED]** A push carrying the approval token but not leading with it — `cd "C:/Users/JacobMadsen/source/repos/Cognito Forms" && CLAUDE_PUSH_APPROVED=1 git push -u origin HEAD` — is **denied** by the hook with `BLOCKED: git push is not allowed in work repos (detected work email: jacob@cognitoforms.com)`. Observed live twice this session (the merge-push for `p/57077-cog-pay-account-deletion`), then succeeded only after re-issuing the command token-first.
2. **[VERIFIED]** The bare token-led form `CLAUDE_PUSH_APPROVED=1 git push -u origin HEAD` (exactly what `push/SKILL.md:83` prescribes) is allowed and pushes normally — confirmed live in the same session immediately after the blocked attempts.

## Reproduction Steps

1. In a repo whose `git config user.email` is `jacob@cognitoforms.com`, stage a pushable commit on a branch.
2. Issue the push via the Bash tool as a **composed** command (the natural shape when a working dir must be set first):
   ```bash
   cd "/path/to/work-repo" && CLAUDE_PUSH_APPROVED=1 git push -u origin HEAD
   ```
3. Observe the PreToolUse deny: `BLOCKED: git push is not allowed in work repos …`.
4. Re-issue the **same** push token-first (Bash tool cwd already persists), and it succeeds:
   ```bash
   CLAUDE_PUSH_APPROVED=1 git push -u origin HEAD
   ```

**Expected:** Both forms are approved pushes — the `&&`-chained form sets `CLAUDE_PUSH_APPROVED` for the `git push` process exactly as the bare form does (shell env-assignment-prefix semantics) — so both should be allowed.
**Actual:** The composed form is denied; only the bare leading-token form is allowed.
**Consistency:** Always — deterministic on the anchored regex, independent of timing.

## Evidence Collected

### Source Code

`user/hooks/block-work-repo-git-push.sh` — PreToolUse(Bash|PowerShell) hook, inline Python body (`-c`) reading the stdin-JSON payload:

```
command = (payload.get("tool_input") or {}).get("command") or ""     :58
if not re.search(r"\bgit\s+push\b", command, re.IGNORECASE): _allow() :61   # push detector — re.search (unanchored)
if re.match(r"^CLAUDE_PUSH_APPROVED=1\b", command): _allow()          :65   # bypass detector — re.match (^-anchored)  ← FIX SITE
… git config user.email (from payload cwd) …                          :70-76
if email == "jacob@cognitoforms.com": _deny(…)                        :80-85
```

The bug is the **asymmetry** between `:61` and `:65`: the push detector uses unanchored `re.search`, but the bypass detector uses `re.match`, which anchors at string start (`^` is also explicit). Any command that does not *begin* with the literal token — `cd …&&`, another `VAR=… ` prefix, or an `&&`/`;` list — fails the anchor even though the token is a legitimate env-assignment on the `git push` itself.

The hook's own CONTRACT comment states the intent as bypass on a command **prefixed** `CLAUDE_PUSH_APPROVED=1` (`:18`); the `^`-anchor is stricter than that intent and stricter than shell semantics warrant.

### Serving-Path Trace (`traced`)

```
Bash tool call:  cd "…" && CLAUDE_PUSH_APPROVED=1 git push -u origin HEAD
  → PreToolUse(Bash) hook runs                          user/hooks/block-work-repo-git-push.sh:99
  → command = payload.tool_input.command                                            :58
  → re.search(r"\bgit\s+push\b", command) matches → NOT fast-allowed                :61
  → re.match(r"^CLAUDE_PUSH_APPROVED=1\b", command) → FAILS (command starts "cd")    :65   ← fix node, on path
  → git config user.email == jacob@cognitoforms.com                                 :70-80
  → _deny("BLOCKED: git push is not allowed …")                                     :80-85
```

Label: **`traced`** — chain read from the serving code and confirmed by live reproduction (deny observed, then allow after token-led re-issue). Fix site (`:65`) is *on* the path: it is the exact node that reads the command and decides the bypass. Not runtime-coupled (deterministic regex on the payload string).

### Runtime Evidence

Live session (2026-07-13, `Cognito Forms` repo, branch `p/57077-cog-pay-account-deletion`):
- `cd "…" && export CLAUDE_PUSH_APPROVED=1 && git push …` → `BLOCKED …` (token present but not leading).
- `cd "…" && CLAUDE_PUSH_APPROVED=1 git push …` → `BLOCKED …`.
- `CLAUDE_PUSH_APPROVED=1 git push -u origin HEAD` → success: `4e8f82a3f2b..6af64865706  HEAD -> p/57077-cog-pay-account-deletion`.

### Test Harness

`user/scripts/test_hooks.py` has a dedicated block for this hook (`:6974-7115`):
- `test_push_denies_in_work_repo` (`:6976`), `test_push_allows_with_bypass_token` (`:6996`), `test_push_allows_in_non_work_repo` (`:7013`), `test_push_allows_non_push_command` (`:7029`), `test_push_malformed_fails_open` (`:7045`), `test_push_powershell_payload_denies` (`:7059`), `test_push_registered_widened_matcher` (`:7106`).
- The existing allow-case (`:6996`) only exercises the **bare** token-led form (`CLAUDE_PUSH_APPROVED=1 git push origin main`). **No test exercises a composed/prefixed approved push** — which is exactly why the anchor regression went unnoticed. The harness pattern to reuse: `_hook_payload(command, cwd=str(repo))` + `_run_bash(_PUSH_HOOK_SH, …)` + `_hook_decision(result)`.

## Theories

### Theory 1: `re.match` anchor is stricter than the bypass intent
- **Hypothesis:** `re.match(r"^CLAUDE_PUSH_APPROVED=1\b", …)` at `:65` only matches a bare leading token, so any composed approved push (cd-prefixed, env-chained, `&&`-listed) is denied.
- **Supporting evidence:** Live repro (composed → deny, bare → allow); `re.match` semantics anchor at start; the sibling detector at `:61` uses unanchored `re.search`; CONTRACT comment `:18` intends "prefixed", not "leads the entire string".
- **Contradicting evidence:** None found.
- **Status:** **Confirmed.**

## Proven Findings

- **Root cause (`traced`):** `user/hooks/block-work-repo-git-push.sh:65` uses `^`-anchored `re.match` for bypass detection, so an approved push is only honored when the token is the very first token of the command. Composed commands (the normal Bash-tool shape) are false-blocked.
- **Confirmed fix (approved with Jacob):** Relax `:65` to an **unanchored `re.search`** for the token — `re.search(r"CLAUDE_PUSH_APPROVED=1\b", command)` — matching the same idiom the push detector already uses one line up (`:61`). This is intra-file convergence, not new machinery. (The looser token-anywhere match was chosen deliberately over an env-prefix-before-`git push` regex; the token is Claude-controlled, so a stray-token bypass is an accepted, low risk in exchange for simplicity.)
- **Confirmed scope (approved with Jacob):**
  1. **Hook regex (load-bearing):** the `:65` fix above.
  2. **Regression coverage:** add a `test_hooks.py` case for a composed approved push (e.g. `test_push_allows_with_bypass_token_after_cd_prefix`) asserting `cd "…" && CLAUDE_PUSH_APPROVED=1 git push origin main` → allow. It fails against the current anchor and passes after the fix.
  - **Out of scope (decided):** no change to `push/SKILL.md` step 8 — the bare token-led form stays the prescribed shape; the hook fix makes composed callers safe without relying on caller discipline.

## Reuse Ledger

| Capability | Existing system | Verdict | Evidence | Confidence |
|---|---|---|---|---|
| Detect `git push` in a hook command string | unanchored `re.search(r"\bgit\s+push\b", …)` | reuse-as-is (already correct) | `block-work-repo-git-push.sh:61` | high |
| Detect the `CLAUDE_PUSH_APPROVED=1` bypass token | `^`-anchored `re.match` | **refactor** → reuse the sibling `re.search` idiom (unanchored) | `block-work-repo-git-push.sh:65` vs `:61` | high |
| Test an approved-push allow-case | `_hook_payload(cmd, cwd)` + `_run_bash(_PUSH_HOOK_SH, …)` + `_hook_decision()` | extend (add composed-command case) | `user/scripts/test_hooks.py:6996` (pattern), `:6810` (`_PUSH_HOOK_SH`) | high |

The `refactor` verdict is confirmed with Jacob (Step R5). It converges the buggy detector onto the existing, correct `re.search` pattern already in the same file — the preferred "refactor to match existing pattern" outcome over new code.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Work-repo push guard | `user/hooks/block-work-repo-git-push.sh` (`:65`) | False-blocks every approved push that is not a bare leading-token command |
| Hook test suite | `user/scripts/test_hooks.py` (`:6974-7115`) | Missing coverage for composed approved pushes let the anchor regression ship |
| Sanctioned caller (unchanged) | `user/skills/push/SKILL.md` (`:83`) | Prescribes the bare form; unaffected by the fix, but composed callers currently trip the guard |

## Open Questions

- None blocking. (Considered and dismissed: reading the actual `CLAUDE_PUSH_APPROVED` env var in the hook — not viable, the PreToolUse interface delivers only the command string, per the `legacy-tool-input-env-hooks-dead` finding that the old env-var read was dead.)
