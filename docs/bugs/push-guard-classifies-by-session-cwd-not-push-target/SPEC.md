# Bug: work-repo push guard classifies by session cwd, not the push target repo

**Status:** Concluded
**Discovered:** 2026-07-22
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage); `user/hooks/CLAUDE.md` (hook-plane contract)

## Symptom (verified — live incident 2026-07-22)

A dispatched harden subagent running inside a Cognito Forms work-repo session finished a fix
in the personal `claude-config` repo and tried to `git push` it. `claude-config` mandates
auto-push on completion and its own `CLAUDE.md` documents that this push hook "does NOT apply
here." The push was nonetheless DENIED, forcing the operator to publish the commits manually
via a throwaway worktree.

## Root cause — hook-defect (`block-work-repo-git-push.sh`)

The hook resolves the work-repo signal from the **PreToolUse payload `cwd`** — the
*session/invocation* directory — not the repository the push actually targets:

```python
cwd = payload.get("cwd") or None
proc = subprocess.run(["git", "config", "user.email"], cwd=cwd, ...)
if email == "jacob@cognitoforms.com": _deny(...)
```

When a push targets a repo other than the session cwd — a cross-repo subagent, or a
`cd <other-repo> && git push` / `git -C <other-repo> push` compound — `cwd` is NOT the push
target, so a **personal-repo push invoked from a work-repo session is falsely DENIED**
(session cwd resolves the work email).

### Secondary defect — trigger regex misses `git -C <dir> push`

The trigger `\bgit\s+push\b` requires `git` and `push` to be adjacent, so `git -C <dir> push`
(git/push separated by the global `-C <dir>` option) is not matched at all — that form
**silently bypasses the hook entirely**. The `-C <dir>` argument is also precisely the signal
needed to resolve the true target repo.

## Fix scope

Resolve the work-repo signal from the repository the push actually targets:

1. Broaden the trigger to also match `git -C <dir> push` / `git -c <kv> push` (git global
   options between `git` and `push`), closing the bypass gap — without matching unrelated
   commands (`git log --grep push` must not trigger).
2. Compute the effective target dir: a leading `cd <dir> &&` / `pushd <dir>` prefix (bash `&&`
   or PowerShell `;`), overridden by an explicit `git -C <dir>` (resolved relative to the base
   dir), falling back to payload `cwd`. Read `git config user.email` there.

## Hard contract preserved (`user/hooks/CLAUDE.md`)

- Deny via JSON `permissionDecision` (never `exit 2`).
- FAIL-OPEN on any parse/resolution error (unresolvable dir → ALLOW).
- Bypass token `CLAUDE_PUSH_APPROVED=1` (bash) / `$env:CLAUDE_PUSH_APPROVED='1'` (PowerShell)
  honored anywhere in the command.
- Tool-name-agnostic body (`Bash|PowerShell`).

## Regression coverage (`test_hooks.py`)

- (a) personal-target push from a work-session cwd (via `cd`/`-C`) → ALLOW.
- (b) work-target push from a work-session cwd → DENY (unchanged).
- (c) `cd <personal> && git push` from a work cwd → ALLOW; reverse `cd <work> && git push`
  from a personal cwd → DENY.
- (d) `git -C <work> push` correctly classified as work (DENY) — proving it is no longer
  silently bypassed by the regex gap — and `git -C <personal> push` from a work cwd → ALLOW.
- (e) unresolvable target dir → fail-open ALLOW.
