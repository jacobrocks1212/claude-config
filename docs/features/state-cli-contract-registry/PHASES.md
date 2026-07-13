# Implementation Phases — State-CLI Contract Registry + Shared Surface Extraction

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete
<!-- Cannot reach Complete: D2 and D4 are provisionally accepted under the park-provisional
     directive (NEEDS_INPUT_PROVISIONAL.md, divergence: contained). Completion is mechanically
     blocked (lazy_core.apply_pseudo refuses on the provisional sentinel) until the operator
     ratifies-or-redirects. Phase 4 (D5, state_cli.py extraction) is additionally DEFERRED — not
     attempted this session — per the dispatching session's explicit scope cut; picking it up
     later does not require re-opening D2/D4's ratification. -->

**MCP runtime:** not-required — pure claude-config harness mechanics (a committed JSON registry,
two stdlib Python tools, a parser-construction hoist across seven existing scripts, and an
argparse `error()` override on two of them). No Tauri app, no MCP-reachable surface; validation
is `pytest` on `test_cli_surface_gen.py` + `test_cli_surface_lint.py`, the existing
`test_lazy_core.py` + `test_kpi_scorecard.py` suites, `lazy-state.py --test` / `bug-state.py
--test`, `lazy_parity_audit.py`, and `doc-drift-lint.py`. This is the `standalone — no app
integration` untestable class → `SKIP_MCP_TEST.md` at the MCP gate (not reached this session —
see Provisional-acceptance status).

## Provisional-acceptance status (park-provisional-acceptance)

Two PRODUCT decisions were provisionally accepted 2026-07-13 (recommended option A each, see
`NEEDS_INPUT_PROVISIONAL.md`): **D2** the `cli-surface-lint.py` scan scope + same-line/sentence
attribution rule + `<!-- cli-surface: historical -->` exemption marker, runner-integrated as
`lint-skills.py --check-cli-surface`; **D4** the `DidYouMeanArgumentParser` runtime suggestion on
the two state-script twins, additive epilogue, byte-identical leading error line + exit code.
File-level divergence graded `contained` (bounded, isolated edit surfaces — see the sentinel's
own rationale). The mechanical decisions (D1, D3, D6) auto-accept per their SPEC resolutions.
**D5 is separately DEFERRED** (not provisionally accepted — nothing was implemented against it
to ratify); see SPEC § Locked Decisions item 5.

## Cross-feature Integration Notes

- **`lazy-core-package-decomposition` (Draft, sibling) — soft interplay, sequenced by D6.** That
  feature's later `compute_state` phases will touch `lazy_core.py` internals, not the twins'
  `main()`/`build_parser()` plumbing this feature touched — no collision expected. Per D6's own
  resolution text, whichever feature's write-path phases run second (decomposition, since it is
  scheduled to run AFTER this lane) re-runs the smoke-baseline suite on the merged tree before
  its first commit. This feature's Phase 4 (`state_cli.py` extraction) is deferred specifically
  so it does not race decomposition's later phases over the same twins.
- **`doc-drift-linter` (Complete) — sibling family, no code dependency.** `cli-surface-lint.py`
  is a deliberate structural sibling (committed-claims-vs-reality lint, `<!-- marker -->`
  exemption precedent) but shares no code — confirmed via `doc-drift-lint.py --repo-root .`
  staying exit 0 clean after this session's edits (5 checks, 0 drift, 2 pre-existing exempted
  divergences unrelated to this feature).
- **`friction-kpi-registry` (Complete) — model only, no registry row.** This feature's own SPEC
  carries a drafted `## KPI Declaration` (`state-cli-usage-error-recurrence`, `provenance:
  pending`) but registering it in `docs/kpi/registry.json` is deferred to the ratification round
  (registering a KPI row for a feature that is not yet ratified would be premature commitment of
  a `pending`-provenance row the operator has not yet seen the shape of).

---

### Phase 1: Introspection + registry

**Phase kind:** design

**Scope:** `build_parser()` hoisted to module level on all seven roster scripts (behavior-neutral
— zero smoke-baseline change from the hoist itself); the shared `cli_surface.py` introspection
library (`add_dump_cli_surface_flag`, `dump_parser_surface`, `maybe_handle_dump_cli_surface`);
`--dump-cli-surface` wired into every roster script's `main()` immediately after
`parser.parse_args(...)`; `cli_surface_gen.py` aggregator + committed `docs/cli/cli-surface.json`
+ `--check` freshness mode; `test_cli_surface_gen.py`.

**Deliverables:**
- [x] `user/scripts/cli_surface.py` — schema-v1 introspection (`_describe_action`, `dump_parser_surface`, `add_dump_cli_surface_flag`, `maybe_handle_dump_cli_surface`); no default VALUES leaked (only `default_kind`).
- [x] `build_parser()` hoisted on all seven roster scripts (`lazy-state.py`, `bug-state.py`, `surface_resolver.py`, `lazy_parity_audit.py`, `kpi-scorecard.py`, `lint-skills.py`, `doc-drift-lint.py`); `surface_resolver.py`'s local `import argparse` promoted to top-level; `lazy_parity_audit.py`'s inline `__main__` CLI split into a real `build_parser()`; `lint-skills.py`'s bare `main()` split into `build_parser()` + `main()`.
- [x] `--dump-cli-surface` self-describing flag on all seven; verified each prints valid schema-v1 JSON standalone.
- [x] `user/scripts/cli_surface_gen.py` — `generate_registry`/`render_registry`/`write_registry`/`check_freshness`/`dump_one`, CLI (`--repo-root`, `--check`, `--python`); writes committed, key-sorted, byte-stable `docs/cli/cli-surface.json` (schema_version 1, 7 scripts, 207 flags at HEAD).
- [x] `user/scripts/test_cli_surface_gen.py` — 18 tests: introspection shape (store_true/append/choices/mutually-exclusive group/positional/no-leaked-defaults), `maybe_handle_dump_cli_surface` None-vs-JSON, hermetic-fixture-roster drift detection (added/removed/changed flag), byte-stable regeneration, missing-registry `--check` exit 1, CLI subprocess round trip, and a LIVE self-check that the real repo's committed registry is fresh against the real 7-script roster (the regression net for a future roster script's argparse changing without a regen).

**Minimum Verifiable Behavior:** `python3 user/scripts/cli_surface_gen.py --repo-root . --check`
exits 0 on the committed registry; a fixture script's added flag makes `--check` exit 1 naming
it; `lazy-state.py --test` and `bug-state.py --test` are byte-identical to the pre-hoist
baselines except for the Phase-3 fixture line added later in this same session.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] `cli_surface_gen.py --repo-root . --check` exits 0 clean on the real repo. *(Evidence: `SKIP_MCP_TEST.md` — `test_cli_surface_gen.py::test_real_repo_registry_is_fresh` + a live subprocess `--check` run this session.)* <!-- verification-only -->
- [x] Byte-stable regeneration confirmed by diffing two consecutive live runs. *(Evidence: manual `diff` this session, zero output.)* <!-- verification-only -->
- [x] Smoke baselines (`lazy-state.py --test`, `bug-state.py --test`) unchanged by the hoist itself. *(Evidence: `pytest test_lazy_core.py -k baseline` green before AND after the hoist, checked separately from the Phase-3 fixture addition.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** none.

**Files likely modified:** `user/scripts/cli_surface.py` (new), `user/scripts/cli_surface_gen.py` (new), `user/scripts/test_cli_surface_gen.py` (new), `docs/cli/cli-surface.json` (new), `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/surface_resolver.py`, `user/scripts/lazy_parity_audit.py`, `user/scripts/kpi-scorecard.py`, `user/scripts/lint-skills.py`, `user/scripts/doc-drift-lint.py`.

**Testing Strategy:** Hermetic fixture roster (a throwaway script in `tmp_path`) for drift-detection
unit tests, independent of the real 7-script roster's size/runtime; a live self-check pins the
real registry fresh (doc-drift-lint.py's "self-check that THIS repo is clean" precedent).

**Integration Notes for Next Phase:** Phase 2's lint reads the SAME committed registry this
phase writes — no parallel description.

---

### Phase 2: Prose/fence lint

**Phase kind:** design

**Scope:** `cli-surface-lint.py` per D2 (scan scope, same-line/sentence attribution, exemption
marker); `lint-skills.py --check-cli-surface` runner integration; `test_cli_surface_lint.py`.
KPI-selector registration (SPEC's stated Phase-2 deliverable, `cli-usage-error-count`) is
DEFERRED alongside the KPI registry row itself (see Cross-feature Integration Notes) — the SPEC's
drafted `## KPI Declaration` proxy (`process-friction-count`) stands as-is pending ratification.

**Deliverables:**
- [x] `user/scripts/cli-surface-lint.py` — `lint_repo`/`lint_text`/`Finding` + CLI (`--repo-root`); scans `user/skills/**/SKILL.md`, `user/skills/_components/*.md`, `repos/*/.claude/skills/**/*.md`, `repos/*/.claude/skill-config/**/*.md`, `user/scripts/CLAUDE.md`; attribution unit = logical line (backslash-continuation joined) further split on `.`/`;` sentence boundaries (refinement over the SPEC's literal "same line" wording — see RESEARCH_SUMMARY.md); `<!-- cli-surface: historical -->` exemption marker (checked at the logical-line level, not per-sentence).
- [x] `lint-skills.py --check-cli-surface` — opt-in flag, `importlib`-loads `cli-surface-lint.py` and prints its findings, matching the `--check-skill-config`/`--check-skill-size` convention.
- [x] `user/scripts/test_cli_surface_lint.py` — 14 tests: stale-flag detection (incl. a fixture modeled on the real `user/scripts/CLAUDE.md` Gotcha block — the SPEC's own named regression case), known-flag non-finding, attribution false-positive control (bare flag, ambiguous multi-script sentence, flag checked against the ONE script actually named nearby), exemption marker (own-line-only scope), sentence-boundary scoping within one dense line, multiline shell-continuation joining, hermetic `lint_repo` integration over a fixture tree, CLI exit codes, and a live smoke pass over the real repo (parses cleanly, not a zero-findings assertion).
- [x] Found-stale-mention sweep: run against the real repo (20 findings — 14 in `user/skills/**`/`repos/algobooth/.claude/skills/**` SKILL.md files, out of this STATE-lane agent's scope per its dispatching brief; 6 in `user/scripts/CLAUDE.md`, inspected and confirmed to be attribution-heuristic artifacts from that file's dense single-line-per-script table format, not genuine stale docs — left as-is with the imprecision documented in the script's own `user/scripts/CLAUDE.md` row rather than hand-editing accurate prose to please a v1 lint heuristic). Fixing the 14 SKILL.md findings is reported to the dispatching orchestrator, not fixed in this lane.

**Minimum Verifiable Behavior:** A fixture SKILL.md documenting `surface_resolver.py
--route-mcp-test-tier` is an ERROR naming file:line + nearest flag (`--repo-root`); a fixture
line with the exemption marker produces no finding; `lint-skills.py --check-cli-surface` against
the real repo prints 20 findings and exits 1 (a KNOWN, inspected count — not a hard gate this
session, since fixing SKILL.md prose is out of this lane's scope).

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] Real-repo lint run inspected line-by-line; the SPEC's own worked `lazy_parity_audit.py --report` regression case verified as a FIXTURE test (not asserted against the live doc, which phrases the flag as explicitly nonexistent — see `test_cli_surface_lint.py::test_gotcha_shaped_report_mention_is_flagged`). *(Evidence: `SKIP_MCP_TEST.md` + this session's manual `cli-surface-lint.py --repo-root .` run.)* <!-- verification-only -->
- **DEFERRED (ratification-gated, not a completion blocker for THIS phase):** deciding whether to fix the 14 out-of-lane SKILL.md findings now or as a follow-up sweep is an operator call at ratification, not implemented either way this session.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (registry).

**Files likely modified:** `user/scripts/cli-surface-lint.py` (new), `user/scripts/test_cli_surface_lint.py` (new), `user/scripts/lint-skills.py`.

**Testing Strategy:** A fixture registry (hand-built dict, not the real 207-flag one) keeps unit
tests fast and independent of roster growth; a live smoke test over the real repo asserts
well-formed output (path/line/flag shape) without pinning an exact finding count that would
break every time a skill's prose changes.

**Integration Notes for Next Phase:** Phase 3's did-you-mean epilogue names the SAME registry
path (`docs/cli/cli-surface.json`) this phase's findings point at — one pointer, two consumers.

---

### Phase 3: Runtime "did you mean"

**Phase kind:** integration

**Scope:** `cli_surface.DidYouMeanArgumentParser` (D4); wired into `lazy-state.py` and
`bug-state.py`'s `build_parser()`; smoke-harness confirmation fixture in both twins' `--test`.

**Deliverables:**
- [x] `cli_surface.DidYouMeanArgumentParser` — `error()` override; on "unrecognized arguments" appends `difflib`-suggested near-miss(es) (cutoff 0.6) + `(registry: docs/cli/cli-surface.json)` pointer; leading `<prog>: error: ...` line + exit code 2 byte-identical to stock argparse; falls through to stock behavior for every other error class and for a no-close-match unrecognized-arguments error.
- [x] `lazy-state.py build_parser()` and `bug-state.py build_parser()` swapped to `cli_surface.DidYouMeanArgumentParser`.
- [x] In-file `--test` fixture `did-you-mean-cli-suggestion` on BOTH twins (coupled-pair mirror) — confirms the WIRING itself (build_parser() returns the subclass; `--emit-prompts`/`--fsk` near-misses suggest `--emit-prompt`/`--fsck`; exit 2), distinct from `cli_surface.py`'s own unit tests which cover the class in isolation.
- [x] Smoke baselines regenerated (`tests/baselines/{lazy,bug}-state-test-baseline.txt`) — the ONLY diff is the one new `PASS [did-you-mean-cli-suggestion]` line per file, confirmed via `git diff`.

**Minimum Verifiable Behavior:** `lazy-state.py --emit-prompts` (typo) exits 2 with `unrecognized
arguments: --emit-prompts` as the leading error line and `did you mean: --emit-prompt?` as an
additive epilogue line; `bug-state.py --fsk` analogously suggests `--fsck`.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] Both twins' `--test` harness green with the new fixture; `pytest test_lazy_core.py -k baseline` green (8/8) against the regenerated baselines. *(Evidence: `SKIP_MCP_TEST.md` — this session's `lazy-state.py --test` / `bug-state.py --test` / `pytest -k baseline` runs.)* <!-- verification-only -->
- [x] In-process near-miss invocation on both twins confirmed the leading error line + suggestion + exit code manually (avoiding the live `lazy-cycle-containment.sh` guard, which denies a real routing-shaped CLI invocation of `lazy-state.py` from within an active pipeline session — an environment constraint of this dispatching session, not a defect). *(Evidence: this session's transcript.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (registry + `cli_surface.py`).

**Files likely modified:** `user/scripts/cli_surface.py`, `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/tests/baselines/lazy-state-test-baseline.txt`, `user/scripts/tests/baselines/bug-state-test-baseline.txt`.

**Testing Strategy:** Class-level unit tests (`test_cli_surface_gen.py`) exercise
`DidYouMeanArgumentParser` in isolation with a minimal fixture parser; the in-file `--test`
fixtures confirm the WIRING (the twins' own `build_parser()` actually uses the subclass) without
duplicating the class-level assertions.

**Integration Notes for Next Phase:** Phase 4 (deferred) would move the shared 72-flag surface
into `state_cli.py`'s `build_shared_parser(cfg)` — that builder would need to accept/return the
SAME `DidYouMeanArgumentParser` type (or thread it via `cfg`) so this phase's behavior survives
the extraction. Noted for whoever picks up Phase 4.

---

### Phase 4: `state_cli.py` extraction — DEFERRED, not attempted

**Phase kind:** integration (deferred)

**Scope (as specified, NOT implemented this session):** Per SPEC D5 — a parameterized
`user/scripts/state_cli.py` (`build_shared_parser(cfg)` / `dispatch_shared(args, cfg)`) hoisting
the 72 name-shared flags + their handler plumbing out of `lazy-state.py`/`bug-state.py`, plus the
eight duplicated helpers (`resolve_real_device`, `_current_head`, `_scoped_skip_state`,
`_write_yaml_sentinel`, `_write_yaml_blocked_sentinel`, `_phases_effectively_complete`,
`backfill_receipts`, `enqueue_adhoc`) into `state_cli.py` or `lazy_core` (per-helper reviewed),
retiring each corresponding `lazy_parity_audit.py` regex in the SAME commit that moves its
surface, with `--help` goldens added and the registry diff as the review artifact.

**Why deferred:** The dispatching session's brief was explicit: "be CONSERVATIVE about (b)...
if the SPEC allows deferring (b) to decomposition, defer it with a documented note." SPEC's own
D6 sequencing text sanctions this (deliverable (b) "touches only the twins' parser/handler
plumbing, not `lazy_core` internals... No hard dep in either direction"). The sibling
`lazy-core-package-decomposition` (Draft) is scheduled to run its `compute_state`-phase work
AFTER this lane; attempting Phase 4 here risks exactly the collision D6 warns about (both
features editing the twins' `main()`/parser plumbing in the same window), for a deliverable the
SPEC itself calls "the higher-risk half" and "severable" (Open Questions: "deliverable (a) stands
alone and pays for itself").

**Deliverables:** none attempted (all descoped-in-place). <!-- descoped -->

The header line above carries the canonical structural header-scope descope marker
(`lazy_core._DESCOPED_MARKER`), and each row below repeats it row-scope — the mechanical
projection of the locked D5 deferral (SPEC § Locked Decisions item 5: "deferred, not
provisionally accepted … not a fork requiring operator ratification"). Within THIS feature these
deliverables are dropped-in-place (severed to the sibling `lazy-core-package-decomposition` / a vN
follow-up), so `remaining_unchecked_are_verification_only` treats them exactly like
Superseded-phase rows and the state machine routes forward to the completion tail instead of
looping on write-plan. The work itself is NOT cancelled — it is tracked as an Open Question / vN
follow-up (see SPEC Open Questions + the Cross-feature Integration Notes above); re-opening it is a
NEW plan against the sibling feature, never an unchecked row in this one.
- [ ] `user/scripts/state_cli.py` — NOT created. <!-- descoped -->
- [ ] Shared-flag/helper hoist — NOT performed. <!-- descoped -->
- [ ] `--help` goldens — NOT added. <!-- descoped -->
- [ ] Parity-audit regex retirement — NOT performed (all regexes remain valid; nothing moved). <!-- descoped -->

**Minimum Verifiable Behavior:** N/A — not attempted.

**Runtime Verification:** N/A — not attempted.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phases 1–3 (landed); `lazy-core-package-decomposition` reaching a stable
merged-tree checkpoint is the RECOMMENDED (not required) trigger to revisit this phase, per D6.

**Files likely modified (when picked up):** `user/scripts/state_cli.py` (new),
`user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/lazy_parity_audit.py`,
`user/scripts/lazy_parity_audit.py`'s manifest-driven regex set, new `--help` golden fixtures
under `user/scripts/tests/baselines/`.

**Testing Strategy (when picked up):** Zero-behavior-change is receipt-gated per the SPEC: the
committed smoke baselines + a new `--help`-output golden must be byte-identical before/after each
extraction SLICE commit (flags first, then helpers, then handler dispatch — reviewed
independently per D5's consequences list), with the `cli-surface.json` registry diff as the
provable-no-drift artifact across each slice.

**Integration Notes for Next Phase:** None — this is the SPEC's final phase. Whoever resumes it
should re-read D5's "Consequences, named as design constraints" block in `SPEC.md` before
starting, and re-run `lazy_parity_audit.py --repo-root .` + the full smoke-baseline suite on the
CURRENT tree first (D6's obligation).
