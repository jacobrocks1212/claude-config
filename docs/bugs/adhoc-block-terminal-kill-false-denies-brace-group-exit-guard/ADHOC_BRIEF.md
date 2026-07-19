---
kind: adhoc-brief
bug_id: adhoc-block-terminal-kill-false-denies-brace-group-exit-guard
enqueued_by: lazy-adhoc
date: 2026-07-19
---

# Ad-hoc bug: block-terminal-kill.sh false-denies an unquoted { ...; exit 1; } shell error-guard

Twice this run (the decision-11 and harness-gate-false-positives execute-plan cycles), block-terminal-kill.sh false-denied a legitimate git commit whose command contained an unquoted shell error-guard brace group of the form '|| { echo ...; exit 1; }'. The segment-start anchoring (_CMD_START) treats 'exit' as beginning a command segment because it follows '{ ' (open-brace + whitespace, which counts as a separator), so a real script-exit-with-status guard clause is mis-classified as a terminal exit/logout op and denied. This is a DISTINCT case from the three already-fixed variants (heredoc-body-tokens, quoted-argument-tokens, separators-inside-quoted-args): here the 'exit' is genuinely at a segment start and NOT inside any quote or heredoc, so the existing masking passes do not cover it. The '|| { ...; exit 1; }' idiom is common in the R5 atomic gate+commit chains the cycle agents compose. Fix site: harness-gate/block-terminal-kill segment classification must not deny a bare 'exit <n>' that is an in-script status exit within a brace group (vs an interactive shell exit/logout). /spec-bug to trace + decide the precise discriminator.
