# Git Identity — Full Mechanism Reference

Reference detail relocated from `workspace/CLAUDE.md` (subagent-baseline-claude-md-diet). The
workspace doc keeps the operative summary; this file holds the mechanism, seeding recipes, and
design history.

## Credential helper mechanism

Both accounts live on the same host (`github.com`), so account selection is by **repo path**, not
host. Both contexts use **Git Credential Manager (GCM)** with an explicitly *pinned* account, so
git credentials are fully deterministic and never depend on gh's (mutable, global) active account:

- **Personal repos (default)** — global `~/.gitconfig` pins `username = jacobrocks1212`.
- **Work repos** — `~/.gitconfig-cognitoforms` (loaded via `includeIf` *after* the global block,
  so it wins for matched paths) overrides to `username = jacob-cognitoforms`.

```ini
# global ~/.gitconfig — default/personal
[credential "https://github.com"]
    helper =                       # reset the inherited helper chain
    helper = manager
    username = jacobrocks1212

# ~/.gitconfig-cognitoforms — work override (includeIf-matched paths only)
[credential "https://github.com"]
    helper =
    helper = manager
    username = jacob-cognitoforms
```

GCM (the same helper Visual Studio uses) looks up the stored credential for the pinned username in
Windows Credential Manager and returns it silently — no account picker. GCM holds **both**
accounts' tokens, keyed by username.

**Guarantee:** in a personal repo, both the commit identity (`jacobmadsen12321@gmail.com`) *and*
the push credential (`jacobrocks1212`) are personal regardless of what gh's active account happens
to be. A push from a personal repo can never authenticate as the work account.

## Seeding / re-auth

If GCM ever prompts or a push 401s (stored token rotated/expired), reseed the affected account
from a repo of that type — or just let the GCM browser flow re-auth, which stores a fresh token:

```bash
# work (run from a work repo)
printf "protocol=https\nhost=github.com\nusername=jacob-cognitoforms\npassword=%s\n\n" \
  "$(gh auth token --user jacob-cognitoforms)" | git credential approve
# personal (run from a personal repo)
printf "protocol=https\nhost=github.com\nusername=jacobrocks1212\npassword=%s\n\n" \
  "$(gh auth token --user jacobrocks1212)" | git credential approve
```

## Why this design (history)

The previous helper was a bash script (`~/.git-credential-cognitoforms.sh`) that ran
`gh auth switch` to flip the active account, fetch the credential, then switch back. That caused
two failures: (1) Visual Studio couldn't run a `!bash …/.sh` helper on Windows, so it fell back to
GCM's two-account picker and prompted every time; (2) the constant active-account flipping (plus
personal repos depending on gh's active account) meant Claude Code's `gh` commands and personal
pushes could run as the **wrong** account → **403s** / wrong attribution. The script is now
orphaned and can be deleted.
