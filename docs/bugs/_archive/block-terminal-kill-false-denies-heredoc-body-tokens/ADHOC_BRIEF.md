---
kind: adhoc-brief
bug_id: block-terminal-kill-false-denies-heredoc-body-tokens
enqueued_by: lazy-adhoc
date: 2026-07-13
---

# Ad-hoc bug: block-terminal-kill false-denies termination keywords inside heredoc bodies

Reported by the /harden-harness Round 39 subagent (2026-07-13), which hit the false deny live
while appending prose to a log file.

## Symptom

`user/hooks/block-terminal-kill.sh` denied a command whose only "termination" content was
inside a **heredoc body** — file CONTENT, never executed. Observed repro shape:

```bash
cat >> some/log.md << 'EOF'
... prose mentioning `; exit 124` ...
EOF
```

The `; exit 124` text inside the quoted-heredoc body was matched as a segment-leading `exit`
token and denied.

## Class history (third variant of the same false-deny class)

1. **2026-07-12** — segment-start anchoring (`powershell-tool-bypasses-bash-matched-guards`):
   bare word-boundary matches false-denied awk `'{exit}'` bodies / pytest `-k` expressions.
2. **2026-07-13** — quote-awareness (`block-terminal-kill-false-denies-quoted-argument-tokens`):
   `_mask_quoted` blanks single-/double-quoted spans before matching.
3. **THIS BUG** — heredoc bodies are neither quoted spans nor separate segments, so
   `_mask_quoted` + segment-start anchoring both miss them: a separator character inside the
   body fabricates a false segment start for a following keyword token.

## Suggested fix direction (from the reporting round — verify, don't assume)

Mask heredoc bodies (from the `<<WORD` / `<< 'WORD'` introducer to the terminator line) the
same way `_mask_quoted` masks quoted spans — offsets preserved — BEFORE segment splitting and
keyword matching. Then audit the sibling segment-start guards for the same shape:
`lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, `build-queue-enforce.sh`,
`block-work-repo-git-push.sh` (all share the segment-start command-anchoring idiom).

## Evidence pointers

- Round 39 hardening log: `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`
- Prior variants: the 07-12/07-13 tightenings documented on the `block-terminal-kill.sh` row
  of the root `CLAUDE.md` Hooks table.
