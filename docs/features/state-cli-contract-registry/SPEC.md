# State-CLI Contract Registry + Shared Surface Extraction — Feature Specification

> The state-script CLI surface (86 flags on `lazy-state.py`, 75 on `bug-state.py`, plus the
> smaller pipeline tools) has no machine-readable contract: nothing lints skill/component prose
> against the real argparse surface, so agents invoke flags that don't exist (~46 transcript-mined
> argparse usage errors across ~25 sessions, including 10 invocations of a
> `surface_resolver.py --route-mcp-test-tier` flag that exists nowhere in the tree), and the only
> defenses are prose Gotcha blocks in `user/scripts/CLAUDE.md`. Two coupled deliverables: (a) a
> committed, introspection-generated `cli-surface.json` registry + a deterministic lint of every
> `--flag` mention in SKILL.md/component prose against it (+ an optional runtime "did you mean"
> on argparse error); (b) extraction of the twins' shared flag/handler surface into a
> parameterized `state_cli.py` builder — 72 of `bug-state.py`'s 75 flags are name-identical to
> `lazy-state.py`'s and ~half its production lines are verbatim copies — so coupled-pair parity
> for that surface becomes structural instead of a hand-maintained regex ratchet.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-11
**Friction-reduction feature:** yes
**Source:** repo-exploration proposal session 2026-07-11 (architectural review of the state-script
plane; all numeric claims re-measured against the working tree 2026-07-11)

**Depends on:**

> No hard dependencies. Soft interplay with `lazy-core-package-decomposition` (sibling Draft,
> same proposal session): the registry/lint deliverable (a) is independent and can land first in
> either order; the `state_cli.py` extraction deliverable (b) touches the same
> `lazy-state.py`/`bug-state.py` main() plumbing that decomposition's later compute_state phases
> would touch — whichever feature lands second rebases its smoke-baseline run on the other's
> merged state. Neither blocks the other (see D6).

---

## Executive Summary

The two state scripts are the harness's authoritative CLI, and their surface is large and
fast-moving: `lazy-state.py` defines 86 `add_argument` flags across 12,728 lines; `bug-state.py`
defines 75 across 7,954 lines (both re-measured 2026-07-11). That surface is documented only in
prose — skill bodies, `_components/`, and `user/scripts/CLAUDE.md` — and nothing checks the prose
against the parsers. The field cost is measurable: transcript mining found ~46 argparse usage
errors ("unrecognized arguments", missing required flags) across ~25 sessions. The starkest case:
`surface_resolver.py --route-mcp-test-tier` was invoked 10 times across 7 sessions, yet the flag
exists nowhere in the current tree — not in `surface_resolver.py`'s argparse (its full surface is
`--repo-root`, `--lint`, `--allow`, positional `scenarios`; `user/scripts/surface_resolver.py:486-518`)
and not in any SKILL.md, component, or projected skill (repo-wide grep, 0 hits). Agents
confabulate plausible flags, and today the harness's only countermeasure is reactive prose — the
"Gotcha (40+ misfires in session logs)" block warning that `lazy_parity_audit.py` has no
`--report` flag (`user/scripts/CLAUDE.md:83-84`) documents exactly this failure class as a
warning instead of a gate.

The same review found the deeper cause: the twins are maintained as parallel copies.
Re-measured 2026-07-11: 72 of `bug-state.py`'s 75 long flags are name-identical to
`lazy-state.py` flags — and **zero** of those 72 have byte-identical `add_argument` definitions
(every one differs only in pipeline-flavored help text/formatting, e.g. `--cloud`: "Use
/lazy-cloud state machine variants" vs "Use cloud state-machine variants (no Tauri/MCP/device).").
46.5% of `bug-state.py`'s 6,146 stripped non-comment production lines are verbatim-identical to
`lazy-state.py` lines (multiset match; 52.6% under set-matching — the proposal session's 57% was
measured with a looser method; the re-measured range is the honest figure). At least eight
helpers are maintained as per-script copies (`resolve_real_device`, `_current_head`,
`_scoped_skip_state`, `_write_yaml_sentinel`, `_write_yaml_blocked_sentinel`,
`_phases_effectively_complete`, `backfill_receipts`, `enqueue_adhoc` — verified at
`lazy-state.py:361/393/201/3664/3670/1579/1109/626` vs
`bug-state.py:357/374/328/1844/1864/593/1720/1765`). Parity between the copies is defended by
`lazy_parity_audit.py::audit_state_script_parity` (`user/scripts/lazy_parity_audit.py:360-456`) —
a hand-maintained regex ratchet: 8 finding blocks driven by 9 hand-written source-text regexes,
one added per past hardening feature, catching only the specific divergences that already burned
us once.

This feature makes the contract machine-readable and the parity structural: generate and commit
`cli-surface.json` by introspecting each script's `ArgumentParser`; lint every `--flag` mention
in skills/components against it (drift becomes a red gate, not a Gotcha paragraph); optionally
teach the parsers a "did you mean" error epilogue pointing at the registry; and hoist the shared
flag definitions + handler plumbing into a parameterized `state_cli.py` builder (item noun,
pipeline name, queue/docs-root loaders, help-text flavor as parameters) so the shared surface
cannot diverge by construction. The existing smoke-baseline golden files
(`user/scripts/tests/baselines/{lazy,bug}-state-*.{json,txt}`) pin zero behavior change across
the extraction. It serves the mission's **effective** criterion (a gate with a deterministic
verdict instead of prose warnings) and shrinks the per-hardening-feature tax of writing one more
bespoke parity regex.

## KPI Declaration

Drafted row (full schema; the v1 signal rides the registered `process-friction-count` selector —
CLI-misfire incidents reach the deny ledger via incident-scan's process-friction capture; a
dedicated transcript-mined selector is registered during implementation, see notes):

```json
{
  "id": "state-cli-usage-error-recurrence",
  "system": "state-cli",
  "title": "Agent CLI usage errors against the state-script surface",
  "friction": "Agents invoke flags that do not exist or mis-shape required arguments (~46 transcript-mined argparse usage errors across ~25 sessions), burning a failed tool call plus a diagnose-retry round-trip each time.",
  "signal": { "source": "deny-ledger", "selector": "process-friction-count" },
  "unit": "count",
  "direction": "down-is-good",
  "baseline": { "value": null, "captured_at": null, "window": "30d", "provenance": "pending" },
  "band": null,
  "review_by": "2026-10-15",
  "repo_scope": "claude-config",
  "notes": "Primary corpus is transcript-mined (mine-sessions over session logs: ~46 argparse usage errors / ~25 sessions, incl. 10 invocations of the never-existed surface_resolver.py --route-mcp-test-tier across 7 sessions). v1 rides the registered process-friction-count selector (incident-scan ledgers recurring CLI friction as kind: process-friction); implementation registers a dedicated session-log-mining selector (cli-usage-error-count) at Phase 1 so the row's signal narrows to exactly this error class — same registered-at-spec-vs-wired-later pattern as canary-trip-precision. Deterministic proxy meanwhile: count of `unrecognized arguments` / `the following arguments are required` lines in mined transcripts. Secondary proxy: bespoke regex count in audit_state_script_parity (9 today) stops growing once the shared surface is structural."
}
```

## Design Decisions

### D1. Registry artifact: what is committed, and how it is generated

- **Classification:** `mechanical-internal (auto-accept candidate)`
- **Question:** What machine-readable form does the CLI contract take, and who produces it?
- **Options:**
  - **A — per-script `--dump-cli-surface` subcommand + committed `docs/cli/cli-surface.json`
    (recommended):** each in-scope script grows one introspection subcommand that walks its own
    live `ArgumentParser._actions` and emits `{script, flags: [{name, aliases, nargs, required,
    choices, default_kind, action, help_head, mutually_exclusive_group}]}`; a thin aggregator
    (`user/scripts/cli_surface_gen.py`) invokes each script's dump and writes the merged,
    key-sorted, committed `docs/cli/cli-surface.json` (`schema_version: 1`, one entry per
    script). Introspecting the live parser can never drift from the parser — the registry is a
    projection, not a parallel description. Byte-stable output (sorted keys, no wall-clock) so
    an unchanged surface regenerates identically, per the `lazy-queue-doc.py`/`SCORECARD.md`
    discipline.
  - **B — offline AST/regex generator over script source:** no runtime import of heavyweight
    scripts, but re-implements argparse semantics (aliases, subparsers, `action=` classes) and
    WILL diverge — the exact failure mode this feature exists to kill.
  - **C — registry only, no committed artifact (lint regenerates on the fly):** no drift risk,
    but the contract stops being diffable/reviewable, and every lint run pays full script import
    (`lazy-state.py` transitively imports the 17.7K-line `lazy_core.py`).
- **Recommendation:** A. Committed projection + regenerate-and-diff freshness check (D3).
  `--dump-cli-surface` is itself a flag in the registry — self-describing. Scripts whose parser
  is built inside `main()` hoist parser construction into a module-level `build_parser()` (a
  mechanical, behavior-neutral refactor that D5 needs anyway).
- **Scope roster (closed, v1):** `lazy-state.py`, `bug-state.py`, `surface_resolver.py`,
  `lazy_parity_audit.py`, `kpi-scorecard.py`, `lint-skills.py`, `doc-drift-lint.py`. Additions
  are one roster line in the aggregator. (The roster starts with the scripts skills actually
  tell agents to invoke; the two misfire exemplars — `surface_resolver.py`,
  `lazy_parity_audit.py` — are both in.)

### D2. Skill/prose lint: where flag mentions are checked, and against what

- **Classification:** `product-behavior (PENDING operator)` — this decides which prose surfaces
  become gate-red on a stale flag mention.
- **Question:** Which files are linted, how are `--flag` mentions attributed to a script, and is
  the linter an extension of `lint-skills.py` or a new tool?
- **Options:**
  - **A — new `cli-surface-lint.py`, scoped to skills + components + scripts-CLAUDE.md
    (recommended):** lint every `user/skills/**/SKILL.md`, `user/skills/_components/*.md`,
    per-repo `.claude/skills/**` and `.claude/skill-config/**`, plus `user/scripts/CLAUDE.md`.
    Attribution rule: a `--flag` token is checked only when a roster script name appears in the
    same code fence or the same prose line/sentence (`python3 user/scripts/lazy-state.py
    --emit-prompt` ⇒ check `--emit-prompt` against `lazy-state.py`'s registry entry); bare
    `--flag` tokens with no attributable script are ignored (false-positive control — plenty of
    non-roster CLIs appear in skills). Unknown flag ⇒ ERROR naming file:line, flag, script, and
    the nearest registered flag. Exemption: an HTML comment marker on the mention line
    (`<!-- cli-surface: historical -->`) for deliberately-documented removed flags, mirroring
    `doc-drift-lint.py`'s DIVERGENCE_MARKER pattern.
  - **B — extend `lint-skills.py`:** one fewer entry point, but that tool's charter is `!cat`
    projection safety (`--check-projected`, `--check-capabilities`, `--check-parity`); grafting
    CLI semantics onto it muddies both. Its runner can *invoke* the new linter.
  - **C — lint only fenced code blocks, not prose:** cheaper, but the mined misfires quote flags
    in prose as often as in fences; prose is where drift hides.
- **Recommendation:** A (with B's runner integration — whatever CI/pre-commit step runs
  `lint-skills.py` also runs `cli-surface-lint.py`). The Gotcha block at
  `user/scripts/CLAUDE.md:83-84` becomes a regression test: the linter must be able to flag a
  hypothetical `lazy_parity_audit.py --report` mention.

### D3. Registry freshness: regenerate-and-diff gate

- **Classification:** `mechanical-internal (auto-accept candidate)`
- **Question:** How does the committed registry stay current with the parsers?
- **Options:**
  - **A — regenerate-and-diff check (recommended):** `cli_surface_gen.py --check` regenerates to
    a temp path and diffs against the committed file; any drift ⇒ exit 1 naming the script and
    the changed flags. Runs beside the skill lint (same gate step) and is listed in the parity
    audit's default invocation notes. A flag change therefore forces the registry (and, via D2,
    any stale prose) to update in the same commit.
  - **B — pre-commit hook only:** misses edits made outside hook-bearing environments.
- **Recommendation:** A (B additionally where the repo's existing hook infrastructure already
  runs lints — additive, not load-bearing).

### D4. Runtime "did you mean" on argparse error

- **Classification:** `product-behavior (PENDING operator)` — changes error text agents see.
- **Question:** Should the state scripts' argparse errors suggest near-miss flags?
- **Options:**
  - **A — yes, on the two state scripts only (recommended):** override `ArgumentParser.error`
    to append, on "unrecognized arguments", the closest registered flags
    (`difflib.get_close_matches` over the live parser's option strings) plus one pointer line
    ("full surface: docs/cli/cli-surface.json"). Exit code and the leading error line stay
    byte-identical (usage-line format preserved — smoke baselines must not move); the epilogue
    is additive. This converts each misfire from a dead-end into a one-round-trip self-repair.
  - **B — all roster scripts:** more coverage, but the small tools' surfaces are tiny and the
    mined misfires concentrate on the twins (and on flags for scripts that print usage fine
    already).
  - **C — no runtime change:** registry+lint fixes documented-drift, but the
    `--route-mcp-test-tier` class (agent-invented flags never documented anywhere) is only
    reachable at runtime — lint can't catch what was never written down.
- **Recommendation:** A. The invented-flag class (10 of the mined hits) is invisible to any
  static lint; the runtime epilogue is the only defense that reaches it.

### D5. Shared CLI surface extraction: parameterized `state_cli.py` builder

- **Classification:** `product-behavior (PENDING operator)` — restructures the harness's two
  most load-bearing scripts; zero-behavior-change is the bar.
- **Question:** How do the twins stop being parallel copies of the same surface?
- **Options:**
  - **A — `user/scripts/state_cli.py` parameterized builder (recommended):** a
    `build_shared_parser(cfg)` + `dispatch_shared(args, cfg)` pair where `cfg` carries the
    pipeline parameters: item noun ("feature"/"bug"), pipeline name, docs root
    (`docs/features`/`docs/bugs`), queue loader, terminal-action names
    (`__mark_complete__`/`__mark_fixed__`), and a help-flavor formatter (the re-measurement
    showing 72/72 shared flags differ *only* in help wording is direct evidence help text must
    be a parameter, not a copy). The 72 name-shared flags and their handler plumbing move into
    the builder; each twin keeps its genuinely divergent surface (14 lazy-only flags, 3
    bug-only) and its own `compute_state` walk untouched. The eight duplicated helpers hoist
    into `state_cli.py` (or `lazy_core` where they already have a sibling — `_current_head`
    already exists in `lazy_core.py` at lines 3875 and 5661, itself a duplicate that
    `lazy-core-package-decomposition`'s lint gate would flag).
  - **B — bug-state.py imports lazy-state.py:** no third module, but makes the feature script a
    library with import side effects and couples the twins asymmetrically.
  - **C — codegen (one template renders both scripts):** structural parity too, but generated
    files as the editing surface fights every existing tool (parity audit, doc-drift, direct
    reads).
- **Recommendation:** A. Consequences, named as design constraints:
  - **Parity audit shrinkage, not removal:** `audit_state_script_parity`'s regexes that assert
    "both scripts carry flag X / call `lazy_core.<fn>` at main()" remain valid — the builder
    call site in each twin still matches or the regexes are updated to assert the single
    builder call instead (each retired regex is retired in the same commit that moves its
    surface, never before). The audit's remaining charter is the genuinely divergent walk
    logic and the SKILL.md pair manifest — the part regexes are actually good at.
  - **Zero behavior change is receipt-gated:** the committed smoke baselines
    (`user/scripts/tests/baselines/lazy-state-{algobooth.json,test-baseline.txt}` and
    `bug-state-*`) must be byte-identical before/after each extraction commit; `--help` output
    for both twins is additionally snapshotted as a new golden (help text is allowed to change
    ONLY in the commit that parameterizes it, with the diff reviewed).
  - **`--dump-cli-surface` (D1) lands before extraction:** the registry diff across the
    extraction commits is the review artifact proving the surface didn't move.

### D6. Sequencing against `lazy-core-package-decomposition`

- **Classification:** `mechanical-internal (auto-accept candidate)`
- **Question:** The sibling Draft moves `lazy_core.py` internals; D5 moves state-script
  plumbing. How do they avoid colliding?
- **Resolution candidate:** Deliverable (a) (registry + lint + did-you-mean) is read-only with
  respect to both siblings' seams — land it first, independently. Deliverable (b) touches only
  the twins' parser/handler plumbing, not `lazy_core` internals; the decomposition's facade
  contract (its locked constraint 2) guarantees `lazy_core.<fn>` call sites in the twins keep
  working unmodified. The only real ordering rule: whichever feature's write-path phases run
  second re-runs the smoke-baseline suite on the merged tree before its first extraction
  commit. No hard dep in either direction.

## Locked Decisions

Resolved 2026-07-13 under the operator's overnight park-provisional blanket directive
(autonomous single-lane implementation session, STATE lane only — see the dispatching prompt).
Mechanical-internal decisions are auto-accepted per their own SPEC resolution text; the two
PRODUCT-classified decisions (D2, D4) are **provisionally accepted** on their stated
recommendation and recorded in `NEEDS_INPUT_PROVISIONAL.md` — `SPEC.md` **Status stays Draft**,
and no `COMPLETED.md` is written, per the park-provisional contract. D5 (the higher-risk
`state_cli.py` extraction, Phase 4) is **deferred, not provisionally accepted** — see below.

1. **D1 — Registry artifact (mechanical, auto-accepted): Option A.** `--dump-cli-surface`
   introspection subcommand per roster script (shared implementation in the new
   `user/scripts/cli_surface.py`) + the `user/scripts/cli_surface_gen.py` aggregator writing
   the committed, key-sorted, byte-stable `docs/cli/cli-surface.json`. Landed exactly as
   specified; the closed v1 roster (`lazy-state.py`, `bug-state.py`, `surface_resolver.py`,
   `lazy_parity_audit.py`, `kpi-scorecard.py`, `lint-skills.py`, `doc-drift-lint.py`) all hoist
   a module-level `build_parser()` (behavior-neutral — smoke baselines byte-identical) and wire
   `--dump-cli-surface` immediately after `parser.parse_args(...)`, before any other side effect.
2. **D2 — Skill/prose lint scope + attribution (PRODUCT, provisionally accepted): Option A.**
   New `user/scripts/cli-surface-lint.py`, scoped to `user/skills/**/SKILL.md`,
   `user/skills/_components/*.md`, `repos/*/.claude/skills/**`, `repos/*/.claude/skill-config/**`,
   and `user/scripts/CLAUDE.md`. Attribution rule implemented as SPEC-recommended (same
   fence/line/sentence co-occurrence — refined to sentence-level splitting on `.`/`;` boundaries
   within a logical line to control false positives against this repo's dense single-line
   markdown-table-cell script docs; see the script's own docstring). Exemption marker
   `<!-- cli-surface: historical -->` implemented verbatim. Runner integration (D2's "B's runner
   integration" clause) is wired as `lint-skills.py --check-cli-surface` — an opt-in flag
   alongside the existing `--check-skill-config`/`--check-skill-size` family, matching this
   repo's existing convention of optional additive lint-skills flags rather than an unconditional
   default-run gate (this repo has no CI pipeline that force-runs `lint-skills.py`; the flag is
   reachable on demand exactly like its siblings).
3. **D3 — Registry freshness (mechanical, auto-accepted): Option A.** `cli_surface_gen.py
   --check` regenerate-and-diff; exit 1 naming the drifted script + flags. Verified byte-stable
   across repeated regenerations and a live self-check (`test_cli_surface_gen.py`) that the real
   committed registry is fresh against the real roster — the regression net for a future roster
   script's argparse changing without a regen.
4. **D4 — Runtime "did you mean" (PRODUCT, provisionally accepted): Option A.** The two state
   scripts only. `cli_surface.DidYouMeanArgumentParser` overrides `error()` to append a
   `difflib`-suggested near-miss + registry pointer on an "unrecognized arguments" error, with
   the leading `error:` line and exit code (2) byte-identical to stock argparse (verified via a
   dedicated smoke-harness fixture in both twins' `--test`, plus unit tests in
   `test_cli_surface_gen.py`). Wired into both twins' `build_parser()`.
5. **D5 — `state_cli.py` extraction / Phase 4 (PRODUCT, DEFERRED — not provisionally
   accepted).** The dispatching session's brief explicitly overrode the SPEC's own Option-A
   recommendation here: deliverable (a) (D1–D4) lands fully this session; deliverable (b) is
   deferred to avoid rebase/rework tax against `lazy-core-package-decomposition`'s later
   `compute_state` phases, which touch the same twins' `main()` plumbing (per D6's own
   sequencing text — "no hard dep in either direction," "whichever feature's write-path phases
   run second re-runs the smoke-baseline suite"). This is a scope decision sanctioned by the
   SPEC's own D6 resolution, not a fork requiring operator ratification — recorded here as an
   Open Question / vN follow-up (Phase 4 in `PHASES.md` is authored but marked deferred, not
   attempted), distinct from the D2/D4 provisional-accept shape above.
6. **D6 — Sequencing (mechanical, auto-accepted): resolution candidate as written.** Honored by
   construction — this session touches nothing under `lazy_core.py`'s package boundary; the
   deferred D5/Phase-4 work explicitly inherits the "rerun smoke baselines on the merged tree
   before the first extraction commit" obligation whenever it is picked up (by this feature or
   by `lazy-core-package-decomposition`, whichever lands second).

## User Experience

- **Agent hits a wrong flag (post-D4):**

  ```
  $ python3 user/scripts/lazy-state.py --repo-root . --emit-prompts
  usage: lazy-state.py [-h] ...
  lazy-state.py: error: unrecognized arguments: --emit-prompts
  did you mean: --emit-prompt? (registry: docs/cli/cli-surface.json)
  ```

- **Skill author documents a flag that doesn't exist:** `cli-surface-lint.py` (run with the
  existing skill-lint step) fails:

  ```
  ERROR user/skills/mcp-test/SKILL.md:41: surface_resolver.py has no flag
        --route-mcp-test-tier (nearest: --repo-root; registry entry: surface_resolver.py,
        4 flags). Fix the prose or regenerate docs/cli/cli-surface.json if the script changed.
  ```

- **Flag added/changed on a script:** `cli_surface_gen.py --check` goes red until
  `docs/cli/cli-surface.json` is regenerated in the same commit; stale skill prose goes red with
  it. The Gotcha-block class of documentation (`user/scripts/CLAUDE.md:83-84`) stops being the
  only defense.
- **CLI:**

  ```bash
  python3 user/scripts/lazy-state.py --dump-cli-surface            # one script's projection
  python3 user/scripts/cli_surface_gen.py --repo-root .            # regenerate committed registry
  python3 user/scripts/cli_surface_gen.py --repo-root . --check    # freshness gate (exit 1 on drift)
  python3 user/scripts/cli-surface-lint.py --repo-root .           # prose/fence lint (exit 1 on stale mention)
  ```

## Technical Design

```
ArgumentParser (live, per script; build_parser() hoisted to module level)
      │ --dump-cli-surface (introspection; never a parallel description)
      ▼
cli_surface_gen.py ──writes──▶ docs/cli/cli-surface.json  (committed; schema_version;
      │ --check (regen+diff ⇒ exit 1)                      key-sorted; byte-stable)
      ▼                                                        │ read
freshness gate (runs beside lint-skills.py step)               ▼
                                              cli-surface-lint.py — every --flag mention in
                                              skills/components/scripts-CLAUDE.md, attributed
                                              to a roster script by same-fence/same-line rule
      state_cli.py (D5)                       ⇒ ERROR on unknown flag, exemption marker honored
      build_shared_parser(cfg) / dispatch_shared(args, cfg)
      ▲ cfg: item noun, pipeline name, docs root, queue loader,
      │      terminal names, help-flavor formatter
      ├── lazy-state.py  (86-flag surface: 72 shared via builder + lazy-only residue)
      └── bug-state.py   (75-flag surface: 72 shared via builder + bug-only residue)
      parity: STRUCTURAL for the shared surface; lazy_parity_audit.py keeps the
      divergent-walk + SKILL-pair charter (regexes retired only in the commit that
      moves their surface); smoke baselines tests/baselines/* pin zero behavior change
```

- **Registry schema (v1):** `{"schema_version": 1, "generated_by": "cli_surface_gen.py",
  "scripts": {"lazy-state.py": {"flags": [...]}, ...}}`; per-flag: `name`, `aliases`, `action`,
  `nargs`, `required`, `choices`, `metavar`, `help_head` (first sentence only — full help lives
  in the script), `group` (mutually-exclusive group id when present). No defaults' *values*
  (only `default_kind: none|const|value`) — values can be env-dependent and would break
  byte-stability.
- **House invariants honored:** stdlib-only Python; committed artifact regenerated
  deterministically (no wall-clock); the registry is script-owned — hand-edits are out of
  contract exactly like `queue.json` (`reorder_queue` precedent); gates that refuse early
  (lint at author time) over Gotcha prose that warns late; fail-loud freshness (exit 1 diff)
  rather than silent regeneration.
- **What this feature deliberately does NOT do:** no subparser migration, no flag renames, no
  behavior changes to any handler (all pinned by smoke baselines); no lint of transcripts or
  runtime telemetry (the KPI row's mining stays in `mine-sessions`/incident-scan); no attempt to
  registry-ize non-roster scripts in v1.

## Implementation Phases

- **Phase 1 — Introspection + registry (~1 session).** `build_parser()` hoists on the roster
  scripts (behavior-neutral; smoke baselines byte-identical); `--dump-cli-surface` on each;
  `cli_surface_gen.py` + committed `docs/cli/cli-surface.json`; `--check` freshness mode;
  pytest `test_cli_surface_gen.py`. Proven done: registry commits clean; `--check` red on a
  fixture flag add; baselines unchanged.
- **Phase 2 — Prose/fence lint + KPI selector (~1 session).** `cli-surface-lint.py` per D2
  (attribution rule, exemption marker); wire into the skill-lint step; register the
  `session-log-mining` selector `cli-usage-error-count` in `kpi-scorecard.py`'s closed enum +
  registry row promotion from the drafted proxy. Proven done: linter red on a fixture stale
  mention (incl. a synthetic `lazy_parity_audit.py --report`), green on the real tree after
  fixing whatever it finds; a found-stale-mention sweep of existing skills lands in the same
  phase.
- **Phase 3 — Runtime "did you mean" (~0.5 session; PENDING D4 approval).** `error()` override
  on the twins; leading error line + exit code byte-compatible; epilogue additive. Proven done:
  unit test asserts suggestion on a near-miss and unchanged usage-line prefix; smoke baselines
  byte-identical.
- **Phase 4 — `state_cli.py` extraction (~2–3 sessions; PENDING D5 approval; sequenced per
  D6).** Builder + cfg; move the 72 shared flags and their handler plumbing in reviewed slices
  (flags first, then the eight duplicated helpers, then handler dispatch); parameterize help
  text (single reviewed help-diff commit); retire each parity-audit regex in the commit that
  moves its surface; `--help` goldens added. Proven done: smoke baselines + registry diff
  byte-identical across every slice commit except the one reviewed help-text commit;
  `lazy_parity_audit.py` default invocation exits 0 throughout.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Registry is a projection, not prose | Flag added to a roster script without regenerating | `cli_surface_gen.py --check` exit 1 naming script+flag | `test_cli_surface_gen.py` |
| Byte-stable regen | Regenerate with unchanged parsers | Byte-identical `cli-surface.json` | diff successive runs |
| Stale skill prose goes red | Fixture SKILL.md documenting a nonexistent flag (incl. the `--report` Gotcha case) | Lint ERROR with file:line + nearest flag | `test_cli_surface_lint.py` |
| Attribution rule controls false positives | Fixture prose with a bare `--flag` and no roster script nearby | No finding | `test_cli_surface_lint.py` |
| Invented-flag runtime repair | `lazy-state.py` invoked with a near-miss flag | "did you mean" epilogue; unchanged usage prefix + exit code | unit test |
| Zero behavior change through extraction | Each Phase-4 slice commit | `tests/baselines/{lazy,bug}-state-*` byte-identical; parity audit exit 0 | smoke suite per commit |
| Structural parity replaces ratchet | A shared-surface flag edited in the builder | Both twins' `--dump-cli-surface` change identically; no new bespoke regex needed | registry diff |
| KPI honesty | Scorecard before Phase-2 selector lands | Row renders via proxy/NO-DATA, never fabricated zero | `kpi-scorecard.py --stdout` |

## Open Questions

- **D2 (operator):** confirm the linted-surface roster (skills + components + per-repo skill
  dirs + `user/scripts/CLAUDE.md`) and the exemption-marker mechanism.
- **D4 (operator):** approve the runtime error-epilogue on the twins (it changes agent-visible
  error text; the leading line stays byte-compatible).
- **D5 (operator):** approve the extraction itself — it is the higher-risk half and is severable;
  deliverable (a) stands alone and pays for itself.
- **Empirical (Phase 2):** how many stale flag mentions the first real lint run finds across the
  ~90 skills — sizes the sweep commit.
- **Empirical (Phase 4):** whether `_scoped_skip_state`'s two copies (`lazy-state.py:201`,
  `bug-state.py:328`) are still semantically identical after recent hardening features, or one
  drifted — the hoist commit must diff them line-by-line first (the same check per helper).

## Research References

- Re-measurement session 2026-07-11 (this spec): flag counts via `add_argument` census; shared-line
  measurement (multiset + set matching over stripped non-comment lines); flag-name/definition
  identity via paren-balanced `add_argument` block extraction; repo-wide `--route-mcp-test-tier`
  grep (0 hits); `surface_resolver.py:486-518` argparse read; `lazy_parity_audit.py:360-456` read.
- `user/scripts/CLAUDE.md:83-84` — the "Gotcha (40+ misfires)" block: the prose-warning
  antipattern this feature mechanizes away.
- `docs/features/doc-drift-linter/SPEC.md` + `user/scripts/doc-drift-lint.py` — the committed
  claims-vs-reality lint family this joins (DIVERGENCE_MARKER exemption precedent).
- `docs/features/friction-kpi-registry/SPEC.md` — committed-registry + deterministic-lint +
  byte-stable-regen discipline mirrored here.
- `docs/features/lazy-core-package-decomposition/SPEC.md` (sibling Draft) — D6 sequencing; its
  ruff/F811 gate would independently catch the `_current_head` duplication noted in D5.
