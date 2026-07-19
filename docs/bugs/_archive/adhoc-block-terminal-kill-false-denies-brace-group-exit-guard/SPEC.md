# Bug: block-terminal-kill.sh false-denies an unquoted `{ ...; exit 1; }` shell error-guard

**Status:** Superseded
**Discovered:** 2026-07-19
**Superseded:** 2026-07-19
**Severity:** Low (developer friction — false-deny of a common commit idiom)

## Superseded — the whole mechanism was revoked

This bug reported that `block-terminal-kill.sh` false-denied a legitimate unquoted shell
error-guard of the form `|| { echo ...; exit 1; }` (observed twice during the 2026-07-19
`/lazy-batch` run) because the `_CMD_START` segment-start anchoring treats `exit` as beginning a
command segment when it follows `{ ` (open-brace + whitespace).

**On 2026-07-19 the operator (Jacob) instructed that the entire `block-terminal-kill` mechanism be
revoked.** The hook was unregistered from `user/settings.json` on that date (the script is retained
in `user/hooks/block-terminal-kill.sh` for reference, carrying a REVOKED header comment, but no
longer runs on any tool call).

With the hook no longer executing, it cannot false-deny anything — so the specific false-positive
this bug describes can no longer occur. There is nothing left to fix: the fix would have been a
precision change to a matcher that is now inert. This bug is therefore **Superseded** by the
revocation, not Fixed.

If the `block-terminal-kill` mechanism is ever re-instated by a fresh operator instruction, the
`{ ...; exit 1; }` false-deny class should be re-opened as a new bug against the re-registered hook
(alongside the three already-fixed masking variants: heredoc-body, quoted-argument, and
separators-inside-quoted-args).

## Original report (retained for history)

Twice during the 2026-07-19 run (the `decision-11-dispatch-time-forward-advance` and
`adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose` execute-plan cycles),
`block-terminal-kill.sh` false-denied a `git commit` whose command contained an unquoted
`|| { echo ...; exit 1; }` error-guard brace group — a distinct case from the three already-fixed
masking variants, since the `exit` sits genuinely at a segment start and NOT inside any quote or
heredoc. The idiom is common in the R5 atomic gate+commit chains cycle agents compose.
