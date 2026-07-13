---
kind: research-summary
feature_id: state-cli-contract-registry
date: 2026-07-13
source: inline recon (autonomous single-lane implementation session; no Gemini research —
  the SPEC's own re-measurement session already enumerated the surface; this pass re-verified
  against HEAD before implementation)
---

# Research Summary — state-cli-contract-registry

Inline recon against the working tree immediately before implementation, re-verifying the
SPEC's flag-count claims (which were themselves dated 2026-07-11) and confirming the roster's
real argparse shape before hoisting any parser construction.

## Verified surfaces

### The seven roster scripts' argparse blocks

- `user/scripts/lazy-state.py` — `main()` builds its `ArgumentParser` inline (lines
  ~11309–11949 pre-hoist); a single `args = parser.parse_args()` call site. Re-measured
  `add_argument` census at HEAD (2026-07-13, before this session's edits): **91** flags (SPEC's
  2026-07-11 figure was 86 — the surface grew across the intervening seams: `--ack-deny`,
  `--marker-status`, `--reassert-owner`, `--next-merged`, `--count-phases`, and others landed in
  the five days between the SPEC's measurement and this session). Confirms the SPEC's own
  framing: "fast-moving" is not hyperbole — a registry generated once and never regenerated
  would already be stale by the time this feature landed.
- `user/scripts/bug-state.py` — same shape, `main()` at a single inline block; **81** flags
  re-measured (SPEC's figure: 75).
- `user/scripts/surface_resolver.py` — `main()` built its parser with a LOCAL `import argparse`
  (not top-level) — required promoting it to a top-level import before `build_parser()` could be
  hoisted to module level (a pure mechanical fix, zero behavior change; verified no other
  top-level `import argparse` collision). `--repo-root` is `required=True`. 4 flags pre-registry
  (`--repo-root`, `--lint`, `--allow`, positional `scenarios`) plus `-h`/`--help` and the new
  `--dump-cli-surface` = 6 in the generated registry.
- `user/scripts/lazy_parity_audit.py` — CLI lives directly in `if __name__ == "__main__":`, not
  a `main()` function; hoisting required introducing `build_parser()` as a genuinely new
  top-level function (not a rename of an existing one, unlike the other six). `--repo-root`
  `required=True`.
- `user/scripts/kpi-scorecard.py` — `main(argv=None)` already had a `_SCRIPTS_DIR`-on-`sys.path`
  bootstrap block (the `lazy-queue-doc.py` sibling-import pattern) — `import cli_surface` slots
  in there directly, no new bootstrap needed.
- `user/scripts/lint-skills.py` — `main() -> None` (bare, no return code) with all execution
  logic inline in the same function as the `argparse.ArgumentParser()` construction and the
  final `sys.exit(exit_code)` — required a real split into `build_parser()` (parser only) +
  `main()` (parse + dispatch + exit), not just a rename. Already had the sibling-import
  `sys.path.insert` bootstrap for `skill_repos`.
- `user/scripts/doc-drift-lint.py` — `main(argv=None)` returns an int (not `sys.exit` inline);
  no existing sibling-import bootstrap — added one (mirrors the `bug-state.py` guard pattern
  verbatim, since another feature in this repo will eventually want to `import doc-drift-lint`
  helpers the same way `lazy-state.py` already does — see the `live_settings_probe` seam at
  `lazy-state.py:~11276` that already `importlib`-loads this exact file).

### Coupled-pair smoke-baseline mechanics (D1's "behavior-neutral" bar)

- `user/scripts/tests/baselines/{lazy,bug}-state-test-baseline.txt` are byte-pinned via
  `test_lazy_core.py::test_{lazy,bug}_state_test_output_matches_baseline` (cross-platform
  normalized through `_normalize_smoke_output`). The `build_parser()` hoist itself was
  byte-identical (confirmed BEFORE adding any new smoke fixture); the ONE expected baseline
  diff was the new `did-you-mean-cli-suggestion` fixture line added for Phase 3 — regenerated
  via the documented procedure (live `--test` output piped through `_normalize_smoke_output`,
  isolated `LAZY_STATE_DIR`), diff-reviewed to confirm it added exactly one line each.
- The in-file `--test` harness in both twins is one large `run_smoke_tests()` function with
  inline named fixture blocks (`fix_name`/`ok` pattern) — NOT a `def test_*()`-per-fixture
  reflection scheme the top-of-file docstring in `user/scripts/CLAUDE.md` implies ("write `def
  test_<name>():` and register it"). Followed the REAL pattern (matching the most recent
  `record-intervention-*` fixtures) rather than the aspirational doc text.

### `docs/cli/` — new directory, no prior art in this repo

- No existing `docs/cli/` directory; modeled the registry's committed-artifact discipline
  (schema_version, key-sorted, byte-stable, no wall-clock) directly on `docs/kpi/registry.json`
  (friction-kpi-registry) and the freshness-gate shape on `cli_surface_gen.py --check` vs.
  `doc-drift-lint.py`'s own pure-read drift check (same family, different consumer: doc-drift
  checks CLAUDE.md prose against on-disk reality generically; this feature's lint checks
  `--flag` prose specifically against the introspected CLI contract).

## Assumptions that proved wrong / drifted

- **D2's attribution rule ("same line/sentence") needed a real sentence split, not just a
  logical-line join.** A naive whole-physical-line attribution unit produced ~34 false
  positives against `user/scripts/CLAUDE.md` alone — that file's script-table rows are ONE
  physical markdown line per script (table cells cannot contain literal newlines), often 1000+
  characters discussing several OTHER scripts by name. Splitting further on `.`/`;` boundaries
  cut real-repo findings from 54 to 20 without losing the SPEC's own worked regression case
  (a `lazy_parity_audit.py --report`-shaped same-clause mention). Documented as a v1 known
  imprecision in the script's own CLAUDE.md row rather than chasing a perfect clause grammar.
- **`difflib.get_close_matches` needed `cutoff=0.3`, not the more typical `0.6`, to reproduce
  the SPEC's own worked example** (`--route-mcp-test-tier` → nearest `--repo-root`, similarity
  ratio ≈0.31). The Phase-3 did-you-mean suggestion (typo-correction, high-confidence) correctly
  stays at `cutoff=0.6` — the two consumers have different precision bars by design (Phase 2's
  "nearest" is a best-effort authoring hint over a small per-script flag set; Phase 3's
  suggestion is presented as a direct correction to a runtime user).

## Scope decision (not drift, but load-bearing for this session)

- Deliverable (b) (`state_cli.py` extraction, SPEC Phase 4 / D5) is **deferred**, per the
  dispatching session's explicit instruction to stay conservative given the sibling
  `lazy-core-package-decomposition` feature's later `compute_state` phases touching the same
  twins' `main()` plumbing. This is sanctioned by the SPEC's own D6 sequencing text ("no hard
  dep in either direction") — see `SPEC.md` § Locked Decisions, item 5.
