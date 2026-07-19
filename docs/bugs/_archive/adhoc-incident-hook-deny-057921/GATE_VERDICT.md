---
kind: gate-verdict
feature_id: adhoc-incident-hook-deny-057921
gate_version: 1
date: 2026-07-19
scope_hit: [user/hooks/CLAUDE.md, user/hooks/lazy-cycle-containment.sh]
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: the whole-shared-index staged-path evaluation in the second-feature-commit tripwire (the false-DENY behavior under concurrent lanes); net-new parser helpers (`_commit_pathspecs` / `_commit_effective_paths`) that pay for themselves by removing the false-deny while preserving the genuine catch (bare / `-a` / foreign-pathspec commits still deny whole-index).
override: absent
---

## Adversarial answers

### overfit

The checker flagged five diff-shape hits, all literal elements appended to membership
constructs in `user/hooks/lazy-cycle-containment.sh`:

- the git-commit value-consuming-option recognition set: `-m`/`--message`, `-F`/`--file`,
  `-C`/`--reuse-message`, `-c`/`--reedit-message`, `--author`, `--date`, `-t`/`--template`,
  `--fixup`, `--squash`, `--cleanup`, `-S`/`--gpg-sign`
- `_COMMIT_SEG_SEPARATOR_CHARS = frozenset("\n;&|({")`
- a quote-character literal used by the tokenizer's quote-span detection

**Nearest recurrence this rule does NOT catch:** a genuinely new `git commit` CLI option that
git itself adds in a future release and that this parser has not yet been taught to
skip-as-value-consuming (e.g. a hypothetical `--trailer <value>`-shaped flag). That miss is real
— but it is not an *incident-shaped* literal (a `docs/{features,bugs}/<slug>` id, a date, a
session id) fitted to the one observed deny. The parser keys on the STRUCTURE of git commit
argument syntax — "is this token an option that consumes a following value, or is it a bare
pathspec token" — and the enumerated list is a CLOSED, git-CLI-defined set (git's own `git-commit`
manual page), not a set this feature invented from the incident. The structural property the rule
keys on: **value-consuming vs. pathspec-shaped tokens in `git commit` argv**, evaluated the same
way regardless of which specific option names populate the value-consuming set. A future git
option is a maintenance addition to a structurally-scoped list (mirroring how `_mask_heredoc` /
`_normalize_ps_syntax` already enumerate closed shell-syntax classes elsewhere in this same file)
— not evidence the rule is fitted to this one incident. `checks.overfit = flag-justified`.

### tautology

**If this change were BROKEN** (e.g. it over-scoped and stopped catching genuine second-feature
commits), the metric would look like: the second-feature-commit deny-recurrence count would DROP
*and* cross-feature commits would slip through uncaught — i.e. a bare or `-a` commit that should
have denied would silently allow. That is NOT "identical to working" — a broken over-scope is
visibly distinguishable from a correct re-scope by watching whether the bare/`-a`/foreign-pathspec
paths (five of the six new regression cases) keep denying. The declared independent signal is the
`INCIDENT.md` incident_key deny-recurrence count in the deny ledger
(`claude-config|hook-deny|lazy-cycle-containment|second-feature-commit`) — a ledger this change
does not itself emit or suppress (it is produced by `incident-scan.py` clustering the hook's own
deny-ledger lines, independent of the fix code). Expected direction: the FALSE-deny signature
(pathspec-scoped commit denied over a foreign concurrent-lane staged path) drops to zero
recurrence across subsequent concurrent-completion bursts, while the genuine bare/`-a` catch
continues to fire on any real cross-contamination (asserted directly by the five non-weakening
regression tests in `user/scripts/test_hooks.py`). `signal_independence: independent` (recorded in
SPEC.md `## Intervention Hypothesis`). `checks.tautology = flag-justified`.

### gate_weakening

`harness-gate.py`'s gate_weakening detector reported `hit: false` — no `def test_*` deletion, no
numeric-literal-only change on a gate line, no exemption/sanction-set membership add, no
`*_BYPASS` env-var, no `permissionDecision: deny`/`refuse_*`/`exit 3` removal. Confirmed by
inspection: the `_deny(... "second-feature-commit")` call site is byte-unchanged; the fix ADDS a
pathspec-scoping filter (`_commit_effective_paths`) ahead of the existing `offending` computation,
narrowing the evaluated set only when the commit is confidently pathspec-scoped (parse ambiguity,
`-a`/`--all`, or no explicit pathspec all fall back to the whole index — the deny-safe direction).
The change is a precision RE-SCOPE, not a weakening: five of the six new regression tests assert
the deny is PRESERVED for bare/`-a`/foreign-pathspec commits; only the genuinely-compliant
pathspec-scoped case (the incident repro) is newly allowed. `checks.gate_weakening = pass`;
`override: absent` (no sign-off needed — nothing was weakened).

### complexity

**Retires:** the whole-shared-index staged-path evaluation in the second-feature-commit tripwire
— specifically, the false-DENY behavior that arose from `staged = _staged_paths()` being read
unfiltered at the tripwire (`lazy-cycle-containment.sh:716`, pre-fix). That evaluation mode is
retired at this call site: post-fix, `staged` is always the commit's EFFECTIVE set
(`_commit_effective_paths(command, _staged_paths())`), collapsing to the old whole-index behavior
only on the fallback paths (bare/`-a`/ambiguous) rather than unconditionally.

**Net-new surface:** `_commit_pathspecs(command)` and `_commit_effective_paths(command, staged)`
— two module-scope helper functions. Justification: they pay for themselves by removing the
false-deny (the incident this bug fixes) while PRESERVING the genuine cross-contamination catch
(bare/`-a`/foreign-pathspec commits still deny whole-index, asserted by 5 of the 6 new regression
tests) — a net reduction in operator friction with no reduction in the guard's actual catch
surface. `checks.complexity = declared`.
