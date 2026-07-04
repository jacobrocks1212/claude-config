# Implementation Phases — Doc-Drift Linter (CLAUDE.md vs. Reality)

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In Progress

**MCP runtime:** not-required — pure claude-config harness mechanics (a stdlib-Python pure-read
lint script + doc fixes). No Tauri app, no MCP-reachable surface; validation is pytest
(`test_doc_drift_lint.py` hermetic fixtures + a self-check against this repo root) plus the
existing lane gate suite. This is the `standalone — no app integration` untestable class →
`SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** (none)`. The linter reads already-shipped artifacts; nothing upstream is in
flight:

- **`lazy-parity-manifest.json` / `lazy_parity_audit.py`:** the coupled-pairs check consumes the
  manifest READ-ONLY. The audit script stays the owner of pair *content* sync; this linter only
  asserts the root `CLAUDE.md` table *lists* the same pairs. No parity-audit change; the linter
  is not itself a coupled pair.
- **`claude-config-ci` (stub, separate queue item):** CI wiring is explicitly deferred to it
  (SPEC D4). The pytest self-check (`test_doc_drift_lint.py::test_this_repo_is_clean`) keeps the
  linter enforced by the gate suite until then.
- **`worktree-claude-doc-drift` (fixed bug):** the motivating incident; no code coupling.
- **Cross-lane note:** Phase 2 edits root `CLAUDE.md` (hooks + coupled-pairs tables) and
  `manifest.psd1` in tightly-scoped rows/comments only, minimizing merge surface against sibling
  lanes that add their own doc rows.

---

### Phase 1: Linter core + hermetic test suite

**Phase kind:** design

**Scope:** Build `user/scripts/doc-drift-lint.py` (stdlib-only, pure-read) with the generic
markdown-table extractor, the D5 minimal `.psd1` parser, the four checks (hooks, scripts,
coupled-pairs, manifest), the D2 marker exemption, the D6 finding model, and the CLI
(`--repo-root`, exit 0/1/2). TDD against hermetic tmp-tree fixtures in a new
`user/scripts/test_doc_drift_lint.py`.

**Deliverables:**
- [x] `doc-drift-lint.py`: `DIVERGENCE_MARKER` module constant (SSOT), `parse_markdown_tables`,
  section-anchored table lookup, `parse_psd1_manifest` (shape-bound, fail-closed → malformed),
  `check_hooks`, `check_scripts`, `check_coupled_pairs`, `check_manifest`, finding model
  (`check`/`kind`/`doc file`/`subject`/`message` + exempted flag), `main()` with `--repo-root`,
  summary line, exit contract 0/1/2.
- [x] `test_doc_drift_lint.py` (pytest): per-check fixtures — drift-present AND clean cases for
  each of the four checks; matcher-mismatch; NOT-registered-row assertion (both directions);
  registered-but-undocumented; missing-script (file + trailing-slash dir rows); coupled-pair
  symmetric difference (both directions); manifest forward/reverse + Alias resolution;
  divergence-marker exemption (markdown row + psd1 comment); malformed inputs → exit 2
  (bad JSON, out-of-shape psd1, missing table/heading, missing settings.json).

**Minimum Verifiable Behavior:** Against a fixture tree containing one drifted claim per check
class, the linter prints four drift findings and exits 1; against the corrected fixture it exits
0; with the marker on a drifted row the finding moves to "exempted" and the exit returns to 0.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] All four check classes detect their planted drift and pass their clean fixtures; exit codes
  0/1/2 observed as specified.
<!-- verification-only -->
- [ ] Marker exemption changes reporting but never masks a *different* finding on the same
  surface.
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config has no
Tauri/MCP app). Verification is `pytest`.

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/doc-drift-lint.py` (new),
`user/scripts/test_doc_drift_lint.py` (new).

**Testing Strategy:** Pure pytest, hermetic `tmp_path` trees (no `LAZY_STATE_DIR`, no `HOME`
dependence — the linter reads only the tree under `--repo-root`). Each check class gets its own
minimal fixture builder so failures localize. No existing suite is touched.

**Integration Notes for Next Phase:** Phase 2 runs this linter against the real repo; the
RESEARCH_SUMMARY drift inventory (5 items) is the expected finding list — any delta means either
a linter bug or new drift, both of which Phase 2 must resolve honestly.

---

### Phase 2: Fix the live drift (the feature proving itself)

**Phase kind:** integration

**Scope:** Run `doc-drift-lint.py --repo-root .` against this repo; fix every genuine finding in
the docs; annotate the one deliberate divergence with the D2 marker. No linter code changes
expected (a needed change means Phase 1 missed a case — fix with a test).

**Deliverables:**
- [x] Root `CLAUDE.md` hooks table: `pr-review-cache-guard.sh` trigger corrected to
  `PreToolUse (Read)`; `block-work-repo-git-writes.sh` row rewritten as a NOT-registered row
  (script exists, never registered in tracked `user/settings.json`); new row for
  `load-branch-docs-context.sh` (`SessionStart (startup|resume|clear|compact)`).
- [x] Root `CLAUDE.md` Coupled Skill Pairs table: 3 new rows for the bug-axis pairs
  (`/lazy ↔ /lazy-bug`, `/lazy-batch ↔ /lazy-bug-batch`, `/lazy-status ↔ /lazy-bug-status`)
  matching `lazy-parity-manifest.json`.
- [x] `manifest.psd1`: D2 marker `#` comment exempting `repos/algobooth/` (reason: live repo
  deleted in `47b4fa4`; `.claude/skills` kept as coupled-pair cloud halves).
- [x] `test_doc_drift_lint.py::test_this_repo_is_clean` self-check green (linter exit 0 against
  the repo root).

**Minimum Verifiable Behavior:** `python3 user/scripts/doc-drift-lint.py --repo-root .` exits 0,
reporting 0 drift findings and exactly 1 exempted divergence (algobooth).

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] The five RESEARCH_SUMMARY inventory items were each detected by the linter BEFORE the doc
  fixes (exit 1) and resolved AFTER (exit 0) — detection demonstrated on real drift, not only
  fixtures.
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A — docs + one repo-root self-check; verification is the
linter run + pytest.

**Prerequisites:** Phase 1.

**Files likely modified:** `CLAUDE.md` (hooks + coupled-pairs tables), `manifest.psd1`,
`user/scripts/test_doc_drift_lint.py` (self-check test).

**Testing Strategy:** The linter itself is the test harness here; the self-check pytest case
pins the clean state so future doc edits re-run it via the gate suite.

**Integration Notes for Next Phase:** Phase 3 adds the linter's own script-table rows — which the
scripts check then covers, so the docs for this feature are themselves under its gate.

---

### Phase 3: Docs rows + finalize

**Phase kind:** chore

**Scope:** Document the new script in both script tables; run the full lane gate suite; final
linter self-run.

**Deliverables:**
- [ ] Root `CLAUDE.md` `## Scripts` table: `doc-drift-lint.py` row (purpose, four checks, exit
  contract, marker convention).
- [ ] `user/scripts/CLAUDE.md` `## Files in this directory` table: `doc-drift-lint.py` row
  (+ tests pointer to `test_doc_drift_lint.py`).
- [ ] Full gate suite green (all existing suites + `test_doc_drift_lint.py`); final
  `doc-drift-lint.py --repo-root .` exit 0 at the finalize commit.

**Minimum Verifiable Behavior:** Gate suite green; the linter's scripts check passes over the
two rows that document the linter itself.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Docs/lint consistency green at final HEAD.
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phases 1–2.

**Files likely modified:** `CLAUDE.md`, `user/scripts/CLAUDE.md`.

**Testing Strategy:** Docs + full-suite acceptance only; no new behavior.
