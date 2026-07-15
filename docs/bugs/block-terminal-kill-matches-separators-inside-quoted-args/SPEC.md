# block-terminal-kill.sh false-denies innocent commands whose quoted argument contains a shell-separator + a termination/kill token — Investigation Spec

> `_CMD_START`'s separator class (`\n ; & | (`) matches separators that occur **inside a quoted string argument**, so a `python -c "…"` body or a `grep '…|kill…'` pattern is mis-read as a shell command position and denied.

**Status:** Superseded
**Severity:** P1
**Discovered:** 2026-07-13
**Superseded by:** the shipped `_mask_quoted` fix — `docs/bugs/block-terminal-kill-false-denies-quoted-argument-tokens` (already on `main`)

> **Duplicate — superseded 2026-07-15 (rebase reconciliation).** origin/main independently shipped
> `_mask_quoted` for the sibling bug `block-terminal-kill-false-denies-quoted-argument-tokens`, which
> blanks *every* interior char of a quoted span (a separator `; & | (` inside quotes becomes a space,
> so `_CMD_START` cannot fire on it). Every repro case below was verified allowed under the shipped
> `_mask_quoted` (`grep 'foo|kill'`, `python -c "…;exit(0)"`, literal-newline-in-quotes) while genuine
> post-quote `kill`/`taskkill` still deny (18/18 termkill tests green). The in-flight `_mask_quoted_spans`
> that this SPEC was filed to justify was dropped during the rebase in favor of the tested `_mask_quoted`;
> no fix remains outstanding. Superseded is receipt-exempt per `docs/bugs/CLAUDE.md`.
**Placement:** docs/bugs/block-terminal-kill-matches-separators-inside-quoted-args
**Related:** `docs/bugs/_archive/powershell-tool-bypasses-bash-matched-guards` (the segment-start anchoring this bug extends), `user/hooks/CLAUDE.md` → "PowerShell-syntax regex audit" / "Known limitation — `bash -c` / `sh -c` string-wraps evade every `_CMD_START`-anchored matcher"

---

## Verified Symptoms

1. **[VERIFIED]** A `python -c "import json,os…"` command that reads `~/.claude/state/build-queue/results/1097.json` (the `/build-queue-await` result read) is denied with `BLOCKED: session/system termination (exit/logout/shutdown) is not allowed during the mobile/remote workflow` — the reported screenshot. The Python `-c` body is entirely innocent (a JSON read); the guard matched a termination token inside the quoted `-c` string.
2. **[VERIFIED]** Live in this session: `grep -iE 'terminal|kill|terminate|guard|false'` was denied with `BLOCKED: `kill` is not allowed during the mobile/remote workflow` — the `|kill` inside the single-quoted regex was read as a shell pipe introducing a `kill` command.

## Reproduction Steps

1. Run a Bash command whose quoted argument contains a shell-separator character (`\n`, `;`, `&`, `|`, or `(`) immediately before a termination/kill token, e.g.:
   - `grep -iE 'foo|kill' file.txt`  (separator `|` inside single quotes, before `kill`)
   - `python -c $'import os\nexit(0)'` / any `python -c "…"` whose body has a line beginning `exit(`  (separator `\n` inside double quotes, before `exit`)
2. Observe: the PreToolUse hook `block-terminal-kill.sh` emits a `permissionDecision: deny`.

**Expected:** Allow — the token is inside a quoted string argument to another program; it is not a shell command position and cannot terminate the terminal.
**Actual:** Denied as `kill` / session-termination.
**Consistency:** Always, whenever a `_CMD_START` separator char precedes a trigger token inside a quoted span.

## Evidence Collected

### Source Code (`user/hooks/block-terminal-kill.sh`)

The four deny matchers are all anchored on `_CMD_START`:

```
_CMD_START = r"(?:^|[\n;&|(]|\{(?=\s))\s*" + _ENV_PREFIX          # line 66
_TERMINATE_RE = _CMD_START + r"(?:exit|logout|…|shutdown)\b"      # lines 76-79
_KILL_RE      = _CMD_START + r"kill\b"                            # line 74
```

`_CMD_START` was tightened (in `powershell-tool-bypasses-bash-matched-guards` item 5) to fix
`\b`-word-boundary false positives — but the tightening only addressed *space-adjacent* and
`{`-adjacent tokens. It operates on the **raw command string** and has no notion of shell
quoting, so a genuine separator **character** (`\n ; & | (`) appearing inside a `'…'` / `"…"`
span still satisfies the anchor.

The three existing false-positive tests pass only because their trigger token is preceded by a
*space* (`-k "test and kill"`, a commit message) or by `{`-no-space (`awk '{exit}'`) — none of
them place a real separator char inside the quotes. The reported cases do.

### Serving-path trace (`traced` — fix-site-on-path shown)

```
deny "session/system termination (exit/logout/shutdown)"   [surface: terminal output / tool error]
  → block-terminal-kill.sh:147   "$PYTHON" -c "$_BTK_PY"        (runs the inline matcher)
  → main() reads tool_input.command                             block-terminal-kill.sh:100-103
  → _TERMINATE_RE.search(command)  (or _KILL_RE for the grep)   block-terminal-kill.sh:119 / 112
  → _TERMINATE_RE = _CMD_START + (exit|…|shutdown)              block-terminal-kill.sh:76-79
  → _CMD_START separator class  [\n;&|(]                        block-terminal-kill.sh:66   ← matches a separator INSIDE the quoted body
  → _deny(reason)                                               block-terminal-kill.sh:119-124  ← the observed message
```

**Fix site (on path):** the string the four matchers scan (`command`, consumed at line 103 →
119/112/106/127). Neutralizing the interior of quoted spans **before** the matchers run makes
`_CMD_START`'s "beginning of a shell command segment" premise actually correct — a separator
inside quotes is, as a matter of shell grammar, *not* a command-segment boundary. The changed
node (the scan input) is read on the symptom's serving path.

### Git History

`block-terminal-kill.sh` last changed in `302258c` (the `powershell-tool-bypasses-bash-matched-guards`
fix that introduced `_CMD_START` segment anchoring). This bug is the residual that fix did not cover.

## Theories

### Theory 1: `_CMD_START` separators are matched inside quoted string arguments
- **Hypothesis:** the matcher scans the raw command and treats `\n ; & | (` inside a `'…'`/`"…"` span as shell separators, so any quoted argument that contains a separator followed by a trigger token false-denies.
- **Supporting evidence:** both VERIFIED symptoms; the source (`_CMD_START` is quote-blind); the existing tests only cover space/`{`-adjacent cases.
- **Contradicting evidence:** none.
- **Status:** Confirmed.

## Proven Findings

- **[traced]** The false deny is produced by `_CMD_START`'s separator class matching a separator character inside a quoted argument span (serving-path chain above, each hop `file:line`, fix-site-on-path shown). This is a **static, non-runtime** cause — the matcher is a pure function of the command string; no runtime evidence is required.
- The correct, generalizing fix is to **mask the interior of quoted spans** (both `'…'` and `"…"`, honoring `\`-escapes inside double quotes) to a neutral filler before the four deny matchers run. This preserves every genuine deny (real `kill`/`exit`/`taskkill`/`wt.exe` invocations live *outside* quotes at a segment start; masking touches only quote interiors) and subsumes the interpreter-body and grep-pattern cases in one change. The `bash -c "…"`/`sh -c "…"` residual (a *bypass*, already accepted/documented in `user/hooks/CLAUDE.md`) is unaffected in spirit — masking a `bash -c "exit"` body only widens an already-accepted allow, never narrows a contract-required deny.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Terminal-kill guard | `user/hooks/block-terminal-kill.sh` | False denies of innocent quoted-argument commands (grep patterns, `python -c` bodies) during the mobile/remote workflow — blocks legitimate work |
| Hook tests | `user/scripts/test_hooks.py` | New false-positive regression fixtures (quoted separator + trigger token) + preserved true-positive fixtures |

## Open Questions

- None. Fix scope is a single normalization pass in one hook; true-positive denies are preserved by construction (masking only touches quote interiors).
