---
kind: needs-input
feature_id: state-cli-contract-registry
written_by: spec
decisions:
  - D2 — skill/prose lint scope + attribution rule
  - D4 — runtime "did you mean" on the two state-script twins
date: 2026-07-13
next_skill: spec-phases
class: product
divergence: contained
audit_divergence: contained
---

# /spec (STATE lane) — Needs Input

Autonomous single-lane implementation session (STATE lane only — `user/scripts/**` python +
tests + baselines + `user/scripts/CLAUDE.md`), operating under the operator's overnight
park-provisional blanket directive: never halt for these decisions, take the recommended option,
keep implementing, and record a durable ratification claim-check. Two **product-behavior**
decisions gate this SPEC — D2 changes which skill/component prose surfaces become gate-red on a
stale flag mention, and D4 changes agent-visible argparse error text on the two state-script
twins. The four **mechanical-internal** decisions (D1, D3, D6, and the D5 sequencing text) are
auto-accepted per their own SPEC resolutions. D5 itself (the `state_cli.py` extraction, SPEC
Phase 4) is a fifth PRODUCT decision but is **DEFERRED, not provisionally accepted** — see
`SPEC.md` § Locked Decisions item 5 and `RESEARCH_SUMMARY.md`'s "Scope decision" section; it
carries no NEEDS_INPUT entry here because nothing was implemented against it to ratify.

## Decision Context

### 1. D2 — skill/prose lint scope + attribution rule

**Problem:** The new `cli-surface-lint.py` checks every `--flag` mention in skill/component
prose against the committed registry. Which files are scanned, and how is a `--flag` token
attributed to a specific roster script (so a bare flag from some unrelated tool doesn't false-positive)?
This is a product call because it decides which of the operator's existing skill prose goes
gate-red today, and the attribution heuristic's precision directly trades false positives
against false negatives across ~90 skills.

**Options:**
- **A — new `cli-surface-lint.py`, scoped to skills + components + per-repo skill dirs +
  `user/scripts/CLAUDE.md` (Recommended):** same-line/sentence co-occurrence attribution; an
  HTML-comment exemption marker (`<!-- cli-surface: historical -->`) for deliberately-documented
  removed flags.
- **B — extend `lint-skills.py`:** fewer entry points, but muddies that tool's projection-safety
  charter.
- **C — fenced-code-only:** cheaper, misses the roughly-half of mined misfires that live in prose.

**Recommendation:** A (with B's runner integration — `lint-skills.py` gains an opt-in
`--check-cli-surface` flag alongside its existing `--check-skill-config`/`--check-skill-size`
family, rather than an unconditional default-run gate this repo has no CI to force anyway).

### 2. D4 — runtime "did you mean" on argparse error

**Problem:** Should `lazy-state.py`/`bug-state.py`'s argparse errors suggest near-miss flags on
an "unrecognized arguments" failure? This changes agent-visible error text on the harness's two
most-invoked scripts — a product call, not an internal refactor.

**Options:**
- **A — yes, the two state scripts only (Recommended):** override `ArgumentParser.error` to
  append a `difflib`-suggested near-miss + a registry pointer; the leading `error:` line and exit
  code stay byte-identical (additive epilogue only).
- **B — all roster scripts:** more coverage, but the mined misfires concentrate on the twins.
- **C — no runtime change:** the invented-flag class (never-documented flags an agent
  confabulates) is invisible to any static lint — only a runtime epilogue reaches it.

**Recommendation:** A — the invented-flag class is only reachable at runtime.

## Resolution

resolved_by: auto-provisional
decision_commit: 8d0eb08aaec8f3923b8b87b7d951cb21b2fea7ce

**Provisionally accepted** under the operator's overnight park-provisional blanket directive
(2026-07-13). For each decision the stated `**Recommendation:**` (option A in both cases) is
adopted and propagated into `SPEC.md` § Locked Decisions; the feature is implemented against
these choices, but `SPEC.md` **Status stays Draft** and NO `COMPLETED.md`/`IMPLEMENTED.md` is
written — completion is mechanically blocked while this unratified
`NEEDS_INPUT_PROVISIONAL.md` exists, per the park-provisional contract. The operator ratifies or
redirects each choice before the feature can ever complete.

> **Divergence graded `contained`, not `structural`.** Both decisions' recommended shape was
> implemented and verified this session (real-repo lint run: 20 findings, all attribution-class
> or genuine stale-prose findings outside this lane's scope; did-you-mean verified end-to-end on
> both twins with a byte-identical leading error line + exit code). A redirect on D2 (e.g.
> narrowing the scanned-file set, or swapping the attribution grain) is a bounded edit to one
> new, isolated script (`cli-surface-lint.py`) with no downstream consumers yet wired to its
> exit code as a hard gate. A redirect on D4 (e.g. extending to more scripts, or reverting) is a
> bounded edit to `cli_surface.py`'s one class + two call sites in the twins' `build_parser()`.
> Neither forks a data model, a persistent artifact schema, or a user-visible workflow the way
> the anti-overfit-design-gate precedent's four `structural` decisions did — hence the softer
> grade here, though ratification is still required before completion (this session did not
> self-certify the two-key `provisional_eligibility` predicate via the script-owned
> `--provisionalize-sentinel` action — this file was hand-authored under the same operator
> blanket directive `anti-overfit-design-gate`'s was, and the grades above are the SPEC author's
> own honest assessment for the ratification step, not a machine-verified eligibility pass).

Per-decision choices (recommended option A, verbatim label from each Decision Context block):

- **D2 — skill/prose lint scope + attribution rule:** **Choice:** A — new `cli-surface-lint.py`
  scoped to `user/skills/**/SKILL.md`, `user/skills/_components/*.md`,
  `repos/*/.claude/skills/**`, `repos/*/.claude/skill-config/**`, `user/scripts/CLAUDE.md`;
  same-line/sentence attribution + `<!-- cli-surface: historical -->` exemption marker; runner
  integration as `lint-skills.py --check-cli-surface` (opt-in, matching the existing flag
  family rather than an unconditional gate).
- **D4 — runtime "did you mean" on argparse error:** **Choice:** A — the two state scripts only,
  via `cli_surface.DidYouMeanArgumentParser`; leading `error:` line + exit code 2 byte-identical,
  epilogue additive.

## Deferred (not provisionally accepted — see SPEC § Locked Decisions item 5)

- **D5 — `state_cli.py` extraction (SPEC Phase 4).** The dispatching session's brief overrode
  the SPEC's own Option-A recommendation, directing deferral given the overlapping
  `lazy-core-package-decomposition` sibling's later `compute_state` phases. This is a scope cut
  sanctioned by the SPEC's own D6 sequencing text, not a fork this NEEDS_INPUT round adjudicates.

## Ratification

*Recorded on 2026-07-13.*
ratified_by: operator
outcome: ratified

Both provisionally-accepted decisions were ratified by the operator on their recommended
option A (implemented + verified this session). No redirect; SPEC/PHASES already reflect these
choices. The feature is unblocked for completion.

### 1. D2 — skill/prose lint scope + attribution rule
**Choice:** A — new `cli-surface-lint.py` scoped to `user/skills/**/SKILL.md`,
`user/skills/_components/*.md`, `repos/*/.claude/skills/**`, `repos/*/.claude/skill-config/**`,
`user/scripts/CLAUDE.md`; same-line/sentence attribution + `<!-- cli-surface: historical -->`
exemption marker; runner integration as `lint-skills.py --check-cli-surface` (opt-in). (ratified)

### 2. D4 — runtime "did you mean" on argparse error
**Choice:** A — the two state scripts only, via `cli_surface.DidYouMeanArgumentParser`; leading
`error:` line + exit code 2 byte-identical, epilogue additive. (ratified)
