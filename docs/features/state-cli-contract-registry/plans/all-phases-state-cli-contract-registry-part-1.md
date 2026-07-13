---
kind: implementation-plan
feature_id: state-cli-contract-registry
status: In-progress
created: 2026-07-13
complexity: complex
phases: [1, 2, 3]
---

> **Plan** — single self-contained part. Phases 1, 2, 3 worked INLINE this session (STATE-lane
> single-agent implementation batch, 2026-07-13). Phase 4 (`state_cli.py` extraction, D5) is
> DEFERRED — not attempted, not seam-stubbed — per the dispatching session's explicit
> conservative-scope instruction; see `PHASES.md` → Phase 4 for the full rationale. The feature is
> provisional-blocked (`NEEDS_INPUT_PROVISIONAL.md`, D2 + D4) and cannot complete until the
> operator ratifies — deferring Phase 4 costs no additional completion debt beyond that gate.

# Implementation Plan — state-cli-contract-registry (Phases 1–3; Phase 4 deferred)

**PHASES.md:** `docs/features/state-cli-contract-registry/PHASES.md`
**SPEC.md:** `docs/features/state-cli-contract-registry/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** executed INLINE with `Read`/`Edit`/`Write`/`Bash` (no `Agent`
> delegation). Never invoked `/lazy` or `/lazy-batch` recursively — direct CLI invocations of
> `lazy-state.py` with routing-shaped args were avoided (a live `lazy-cycle-containment.sh`
> guard denies them from within an active dispatching session); did-you-mean was instead verified
> in-process via `importlib`-loaded `build_parser()` + `parser.parse_args([...])`.

**Gate suite (run before marking done):**
```bash
python3 -m pytest user/scripts/test_lazy_core.py user/scripts/test_kpi_scorecard.py \
    user/scripts/test_cli_surface_gen.py user/scripts/test_cli_surface_lint.py -q
python3 user/scripts/lazy-state.py --test
python3 user/scripts/bug-state.py --test
python3 user/scripts/lazy_parity_audit.py --repo-root .
python3 user/scripts/doc-drift-lint.py --repo-root .
python3 user/scripts/cli_surface_gen.py --repo-root . --check
python3 user/scripts/cli-surface-lint.py --repo-root .   # informational — 20 known findings, not a gate
```

## Key design contract (read before implementing)

- **The registry is a projection, never a parallel description (D1).** `cli_surface_gen.py`
  NEVER hand-encodes a script's flags — it shells each roster script's own
  `--dump-cli-surface`, which introspects the LIVE `parser._actions`. If a future change ever
  makes the registry hand-editable or re-derives flags from source text (regex/AST) instead of
  a live parser walk, that is a regression against this feature's entire premise.
- **`build_parser()` hoists are behavior-neutral — prove it BEFORE adding anything else.** Each
  hoist was verified against the pre-existing smoke baselines (`--test` diff, plus
  `pytest -k baseline`) BEFORE the Phase-3 did-you-mean swap, so any baseline drift could be
  attributed to the right change.
- **No defaults' VALUES ever leak into the registry** — only `default_kind: none|const|value`.
  `test_dump_parser_surface_no_default_values_leaked` is a named regression fixture for this.
- **Attribution is per-sentence, not per-line, in `cli-surface-lint.py`** — see
  `RESEARCH_SUMMARY.md`'s "Assumptions that proved wrong/drifted" for why the naive whole-line
  rule the SPEC describes had to be refined for this repo's dense table-cell doc format. The
  refinement is DOCUMENTED, not silent — `cli-surface-lint.py`'s own docstring + the
  `user/scripts/CLAUDE.md` row both explain it.
- **`DidYouMeanArgumentParser`'s epilogue is strictly additive.** The leading `<prog>: error:
  ...` line and exit code 2 are byte-identical to stock argparse; this was the hard constraint
  from SPEC D4 ("usage-line format preserved — smoke baselines must not move") and is
  unit-tested directly (`test_did_you_mean_other_errors_unchanged`).
- **Never git-commit from this lane.** Per the dispatching brief's HARD RULES, no
  state-mutating git commands were run — every change described here is uncommitted in the
  working tree, left for the dispatching orchestrator to review/commit.

## Phase 1 — Introspection + registry (worked inline)

Order of operations, in case this needs to be re-derived or partially reverted:

1. Wrote `user/scripts/cli_surface.py` (the shared library) FIRST, standalone-compileable
   before touching any roster script.
2. For the five smaller roster scripts (`lazy_parity_audit.py`, `kpi-scorecard.py`,
   `lint-skills.py`, `doc-drift-lint.py`, `surface_resolver.py`): hand-edited each with `Edit`,
   since their argparse blocks were small (4–14 flags) and each needed a DIFFERENT structural
   fix (inline-`__main__` → real function; bare `main()` → split `build_parser()`+`main()`;
   local `import argparse` → top-level; etc. — see `RESEARCH_SUMMARY.md`).
3. For the two twins (`lazy-state.py`, `bug-state.py`, ~86–91 and ~75–82 flags respectively): a
   ONE-SHOT mechanical Python transform script (`_hoist_build_parser.py`, written, run, then
   DELETED — not part of the shipped diff) located the `parser = argparse.ArgumentParser(...)`
   → `args = parser.parse_args()` span inside `main()` and mechanically relocated it into a new
   top-level `build_parser()`, verified via `py_compile` + `--test` immediately after.
4. Ran `cli_surface_gen.py --repo-root .` to generate `docs/cli/cli-surface.json`, then
   `--check` twice in a row (byte-stability proof) before writing any tests.
5. Wrote `test_cli_surface_gen.py` LAST, once the shape was proven manually.

**Gate for this phase:** `python3 user/scripts/lazy-state.py --test` / `bug-state.py --test`
green, `pytest test_lazy_core.py -k baseline` green (8/8), `cli_surface_gen.py --check` exit 0.

## Phase 2 — Prose/fence lint (worked inline)

1. Wrote `cli-surface-lint.py` with a naive whole-logical-line attribution rule first (matching
   the SPEC's literal wording), ran it against the real repo — 54 findings, several of them
   OBVIOUSLY cross-attributed (a flag from a non-roster tool mentioned near a roster script's
   name later in the same giant table-cell line).
2. Diagnosed the `user/scripts/CLAUDE.md` table-cell shape as the root cause (one physical line
   per script, 1000+ characters, mentioning several OTHER scripts by name) and added the
   sentence-boundary split (`.`/`;`) as the attribution grain refinement — re-ran: 20 findings.
3. Manually inspected all 20: 14 in `user/skills/**` / `repos/algobooth/.claude/skills/**`
   (genuine, out-of-lane per this session's scope — reported, not fixed); 6 in
   `user/scripts/CLAUDE.md` (in-lane, inspected individually, confirmed to be attribution
   artifacts of the same dense-table-cell shape, NOT genuine stale docs — left as-is,
   documented as a known v1 imprecision rather than editing accurate prose to please the lint).
4. Wired `lint-skills.py --check-cli-surface` LAST, once the standalone tool was stable.
5. Wrote `test_cli_surface_lint.py`, including the SPEC's own named regression fixture (the
   `lazy_parity_audit.py --report` Gotcha-shaped mention) as a FIXTURE test, not a live-repo
   assertion (the real doc phrases the flag as explicitly nonexistent, in a different sentence
   from the script name after the sentence split — see `RESEARCH_SUMMARY.md`).

**Gate for this phase:** `pytest test_cli_surface_lint.py -q` green (14/14); manual real-repo
run inspected and understood (not asserted to zero — see PHASES.md Phase 2 deliverables).

## Phase 3 — Runtime "did you mean" (worked inline)

1. Added `DidYouMeanArgumentParser` to `cli_surface.py` (not a new file — SPEC keeps it in the
   shared library since it is consumed by exactly the two roster scripts already importing
   `cli_surface`).
2. Swapped `argparse.ArgumentParser(...)` → `cli_surface.DidYouMeanArgumentParser(...)` in both
   twins' `build_parser()` — a one-line change each.
3. Verified the epilogue end-to-end via `importlib`-loaded `build_parser()` +
   `parser.parse_args(["--emit-prompts"])` / `["--fsk"]` in-process (a real CLI subprocess
   invocation of `lazy-state.py` with routing-shaped args is denied by the live
   `lazy-cycle-containment.sh` guard from within this dispatching session — an environment
   constraint, worked around by testing the parser object directly rather than shelling out).
4. Added the `did-you-mean-cli-suggestion` fixture to BOTH twins' in-file `--test` harness
   (coupled-pair mirror), confirming the WIRING (not re-testing the class, which
   `test_cli_surface_gen.py` already covers in isolation).
5. Regenerated `tests/baselines/{lazy,bug}-state-test-baseline.txt` via the documented procedure
   (isolated `LAZY_STATE_DIR`, `_normalize_smoke_output`) and `git diff`-reviewed each — exactly
   one new line per file.

**Gate for this phase:** both twins' `--test` green (incl. the new fixture);
`pytest test_lazy_core.py -k baseline` green (8/8) against the REGENERATED baselines.

## Phase 4 — DEFERRED (not started)

See `PHASES.md` → Phase 4 and `SPEC.md` § Locked Decisions item 5 for the full rationale. No
files touched for this phase; nothing to roll back.

## Final gate run (this session, all green)

```
python3 -m pytest user/scripts/test_lazy_core.py user/scripts/test_kpi_scorecard.py \
    user/scripts/test_cli_surface_gen.py user/scripts/test_cli_surface_lint.py -q
  -> 1239 passed (1207 pre-existing lazy_core+kpi baseline + 32 new: 18 gen + 14 lint)
python3 user/scripts/lazy-state.py --test   -> All smoke tests passed.
python3 user/scripts/bug-state.py --test    -> All smoke tests passed.
python3 user/scripts/lazy_parity_audit.py --repo-root .   -> exit 0, no findings
python3 user/scripts/doc-drift-lint.py --repo-root .      -> 5 checks, 0 drift, 2 pre-existing exempted divergences
python3 user/scripts/cli_surface_gen.py --repo-root . --check   -> exit 0, up to date
```

## Completion status

**Not completing this session.** Two PRODUCT decisions (D2, D4) were provisionally accepted
under the park-provisional directive and recorded in `NEEDS_INPUT_PROVISIONAL.md` — completion
is mechanically out of scope until the operator ratifies. `SPEC.md` and `PHASES.md` both stay
`Status: Draft` / `In-progress`. No `COMPLETED.md`, `IMPLEMENTED.md`, or `SKIP_MCP_TEST.md` was
written this session (the SKIP_MCP_TEST rationale is drafted inline in `PHASES.md`'s header for
whoever ratifies and finalizes).
