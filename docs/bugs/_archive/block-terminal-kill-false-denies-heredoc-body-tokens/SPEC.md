# block-terminal-kill.sh false-denies termination keywords inside heredoc bodies — Investigation Spec

> `block-terminal-kill.sh` treats the entire `tool_input.command` as a flat shell string and denies
> a `kill`/`exit`/`taskkill` token at any `\n`-delimited segment start. A heredoc body (`<<EOF … EOF`)
> is DATA, not command segments, but `_mask_quoted` only masks `'…'`/`"…"` spans — so a termination
> keyword appearing as prose inside a heredoc body (e.g. a git commit message) fabricates a false
> segment start and false-denies a completely benign command.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-13
**Fixed:** 2026-07-15
**Fix commit:** 31ee7de
**Placement:** docs/bugs/block-terminal-kill-false-denies-heredoc-body-tokens
**Related:** `docs/bugs/_archive/powershell-tool-bypasses-bash-matched-guards` (variant 1 — segment-start anchoring), `docs/bugs/block-terminal-kill-false-denies-quoted-argument-tokens` (variant 2 — `_mask_quoted`), `user/hooks/CLAUDE.md` → "Every command-execution tool" / "Known limitation — `bash -c` / `sh -c` string-wraps", root `CLAUDE.md` Hooks table (`block-terminal-kill.sh` row)

<!-- Status lifecycle: Investigating → Concluded (root cause traced; ready for /plan-bug). -->

---

## Verified Symptoms

1. **[VERIFIED]** A benign `git commit -q -F - <<'EOF' … EOF` whose message body contained a line
   beginning with `kill` (the prose `kill/taskkill still deny …`) was denied with
   `BLOCKED: \`kill\` is not allowed during the mobile/remote workflow` — observed **first-hand this
   session** (2026-07-15) while committing the rebase-reconciliation work. The command was denied
   before running; nothing executed. Workaround: the commit message was written to a file and passed
   via `-F <file>`, which does not route the body through the hook as a command.
2. **[VERIFIED]** The `/harden-harness` Round 39 subagent (2026-07-13) hit the same false-deny live
   while appending prose containing `; exit 124` to a log file via `cat >> log.md << 'EOF' … EOF` —
   recorded in `ADHOC_BRIEF.md` and `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`.
   Independent reproduction of the same class on the `exit` matcher (vs. the `kill` matcher above).

## Reproduction Steps

Deterministic, from any repo where the hook is registered (fires regardless of tool, per the
`Bash|PowerShell` matcher). The heredoc body is pure data, yet the hook denies:

```bash
git commit -q -F - <<'EOF'
some subject line

a body line that ends with post-quote
kill/taskkill still deny — this line begins with `kill`
EOF
```

Equivalent minimal repro (no git needed):

```bash
cat >> /tmp/note.md << 'EOF'
prose mentioning
exit 0 at a line start
EOF
```

**Expected:** Both commands run — the heredoc body is file/message CONTENT, never executed; no
terminal is terminated.
**Actual:** PreToolUse deny — `_KILL_RE` (repro 1) / `_TERMINATE_RE` (repro 2) matches the keyword
at the heredoc-body line start (`\n` in `_CMD_START`'s separator class), emitting
`permissionDecision: deny`.
**Consistency:** Always — deterministic on any heredoc body whose line begins with a matched
termination token (`kill`, `exit`, `taskkill`, `logout`, `shutdown`, `Stop-Process`).

## Evidence Collected

### Source Code — serving-path trace (cause: `traced`)

Symptom (repro 1) traced surface→source, each hop `file:line` in `user/hooks/block-terminal-kill.sh`:

```
deny "BLOCKED: `kill` is not allowed…"                  block-terminal-kill.sh:186–189  (_deny)
  → _KILL_RE.search(command) returned a match           block-terminal-kill.sh:185
  → _KILL_RE = _CMD_START + r"kill\b"                    block-terminal-kill.sh:143
  → _CMD_START matches the "\n" before "kill"            block-terminal-kill.sh:66
       (_CMD_START = r"(?:^|[\n;&|(]|\{(?=\s))\s*" + _ENV_PREFIX — "\n" is a segment separator)
  → command was masked for QUOTED spans only, not heredocs   block-terminal-kill.sh:176 (_mask_quoted, def :74)
  → command = raw tool_input.command (heredoc body intact)   block-terminal-kill.sh:171
```

`_mask_quoted` (`:74`) blanks the interior of `'…'` and `"…"` spans only; it has no notion of a
heredoc introducer (`<<WORD` / `<< 'WORD'` / `<<-WORD`) or its terminator line, so the body survives
masking verbatim and reaches the matchers at `:179`/`:185`/`:192`/`:200`. The `exit`/shutdown variant
(repro 2) is the identical path through `_TERMINATE_RE` (`:145` def, `:192` call).

**Fix site is ON the traced path:** the masking step at `:176` (or a new `_mask_heredoc` inserted
immediately before it) feeds the matcher input at `:185`. Blanking heredoc-body interiors there —
the same offset-preserving, flat single-pass discipline as `_mask_quoted` — removes the false segment
start without weakening any genuine deny (a real `kill` at a top-level segment start lives OUTSIDE any
heredoc body and is untouched).

### Git History
- 2026-07-15 (this session): the live deny occurred committing `baef994`'s predecessor; message was
  re-authored to a file to land. Rebase-reconciliation context in the same session's commits
  (`281445c`, `baef994`).
- Class variants already shipped on the `block-terminal-kill.sh` row of root `CLAUDE.md`:
  segment-start anchoring (2026-07-12) and `_mask_quoted` quote-awareness (2026-07-13).

### Related Documentation
- `ADHOC_BRIEF.md` (this dir) — Round 39 stub, enqueued 2026-07-13 by `lazy-adhoc`; carries the
  class history and the suggested fix direction (mask heredoc bodies).
- `user/hooks/CLAUDE.md` — documents the plane-wide `_CMD_START` segment-start idiom and the existing
  `bash -c`/`sh -c` accepted-residual (a DIFFERENT bypass surface — that one *widens to allow*
  executable shell; this one *false-denies* pure data, the opposite failure direction).
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` — Round 39 log.

## Theories

### Theory 1: heredoc bodies are unmasked data misread as command segments
- **Hypothesis:** `_mask_quoted` masks quoted spans but not heredoc bodies, so a `\n`-led termination
  keyword inside a heredoc body satisfies `_CMD_START` and false-denies.
- **Supporting evidence:** the serving-path trace above (`:66`/`:143`/`:176`); two independent live
  repros (kill + exit variants); `_mask_quoted` source has no heredoc handling.
- **Contradicting evidence:** none found.
- **Status:** **Confirmed** (see Proven Findings).

## Proven Findings

**Root cause (`traced`, not runtime-coupled).** `block-terminal-kill.sh` matches termination tokens
at `_CMD_START` (`\n`-delimited) segment starts over a command string that has been masked for
`'…'`/`"…"` quoted spans (`_mask_quoted`, `:176`) but **not** for heredoc bodies. A heredoc body is
inert data, but its interior `\n`-led lines look like command segment starts to the matchers, so a
`kill`/`exit`/`taskkill`/etc. token as prose inside the body false-denies the whole command. This is
the **third variant** of the same false-deny class (1: bare word-boundary → segment-start anchoring;
2: quoted-argument tokens → `_mask_quoted`; 3: **this** — heredoc bodies). It is a pure static
string-matching defect confirmed by code inspection + two deterministic repros — no runtime evidence
needed.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| block-terminal-kill hook | `user/hooks/block-terminal-kill.sh` (`_CMD_START` :66, `_mask_quoted` :74/:176, matchers :143/:145/:179/:185/:192/:200) | False-denies any command whose heredoc body has a line beginning with a termination token. Primary fix site. |
| Sibling segment-start guards (audit) | `user/hooks/lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, `build-queue-enforce.sh`, `block-work-repo-git-push.sh` | Share the `_CMD_START` segment-start idiom; likely have the same heredoc-blindness for their own deny tokens. Audit + fix in the same shape (per operator scope decision). |
| Hook docs | `user/hooks/CLAUDE.md`, root `CLAUDE.md` Hooks table | Add the heredoc-masking behavior to the `block-terminal-kill.sh` row + the shared-pattern section once fixed. |

## Fix Scope (operator-confirmed 2026-07-15)

**Hook + audit siblings.** (1) Mask heredoc bodies in `block-terminal-kill.sh` — from the `<<WORD` /
`<< 'WORD'` / `<<-WORD` introducer through the terminator line — offsets preserved, BEFORE the
segment-start matchers run (mirroring `_mask_quoted`'s flat single-pass discipline; not a full shell
parser). (2) Audit the four sibling segment-start guards for the same heredoc-blindness and apply the
same masking where they share the `_CMD_START` idiom. Preserve every genuine deny: a real termination
invocation at a top-level segment start lives outside any heredoc body and must still deny. Fail-OPEN
contract unchanged.

## Open Questions

- Whether a **shared** heredoc-masking helper should be factored across the segment-start guards, or
  copied per-hook in lockstep like the existing `_normalize_ps_syntax` / `COMMAND_TOOL_NAMES` triples
  (`user/hooks/CLAUDE.md` notes "no shared-hook-lib feature exists in this repo yet"). Resolve at
  `/plan-bug`.
- PowerShell here-strings (`@" … "@` / `@' … '@`) are a distinct construct from POSIX heredocs — confirm
  at `/plan-bug` whether they need equivalent masking or are already covered by quote/other handling.
