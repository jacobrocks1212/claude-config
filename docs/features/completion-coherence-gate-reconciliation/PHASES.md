# Implementation Phases — Completion / Coherence Gate Reconciliation

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP server; per `.claude/skill-config/quality-gates.md` the Step-9 MCP gate is N/A and validation is the repo's Python pytest + lint suite (the "untestable-via-mcp" class). A `SKIP_MCP_TEST.md` (granted_by: operator) promotes to VALIDATED.md.

## Cross-feature Integration Notes

Phase-level dependencies on completed upstream features, extracted from each upstream's PHASES.md during /spec-phases Step 1.5. Phase plans below MUST honor these; deviations require /realign-spec before implementation.

- **harness-hardening-retro-fixes (kind=composes, NOT hard):** The SPEC's `Depends on:` block declares this as `composes`, not `hard` — so Step 1.5's hard-dep PHASES read is skipped, but the composition contract is load-bearing and recorded here. That feature's Phase 2 introduced the canonical per-row marker `lazy_core._VERIFICATION_ONLY_MARKER = "<!-- verification-only -->"` (SSOT constant, verified live at `lazy_core.py:1396`) and the `remaining_unchecked_are_verification_only(phases_text)` detector (`lazy_core.py:1419`) for the MID-feature gate. This feature **extends that exact marker + detector** to the COMPLETION-time gate (`_phase_completion_plan`, `lazy_core.py:1824`) which it deliberately left untouched. All phases below reuse the existing `_VERIFICATION_ONLY_MARKER` constant and the `_atomic_write` helper (`lazy_core.py:97`) by name — never re-hardcoding a divergent marker string or a parallel write path.

### Phase 1: Evidence reader + authoritative-evidence decision table

**Scope:** Add a pure, side-effect-free evidence-evaluation helper to `lazy_core.py` that reads the on-disk `/mcp-test` receipts (`VALIDATED.md`, `MCP_TEST_RESULTS.md`, plus the fail-closed `SKIP_MCP_TEST.md` / `DEFERRED_*` sentinels) for a feature dir and returns a verdict — `exempt-and-tick`, `refuse`, or `warn-exempt` (docs-only HEAD drift) — implementing the SPEC's authoritative-evidence decision table. This phase builds the *decision* layer only; it does NOT mutate PHASES.md (that is Phase 2) and does NOT wire into the completion gate (that is Phase 3). The helper is the seam the whole feature rests on, so it is closed end-to-end here with a real fixture-driven smoke test.

**Deliverables:**
- [ ] `lazy_core.py`: new `evaluate_completion_evidence(feature_dir, repo_root, *, pass_count_out=None) -> dict` (or equivalently-named) returning `{verdict: "exempt-and-tick"|"warn-exempt"|"refuse", reason: str, pass_count: int|None, validated_commit: str|None}`. Reuses the existing sentinel parser (`parse_sentinel`) and `_current_head` — never a parallel reader.
- [ ] Decision-table logic implementing every row of the SPEC's authoritative-evidence table: require the union of `VALIDATED.md` (`kind: validated`) AND `MCP_TEST_RESULTS.md` (`all-passing`, `pass==total`, `pass>0`); `validated_commit == HEAD` exact; `VALIDATED.md` present + results missing/malformed → refuse (forged-attestation); results present + `VALIDATED.md` missing → refuse; `SKIP_MCP_TEST.md` / `DEFERRED_*` present (without passing results) → refuse, no tick (fail-closed); neither → refuse.
- [ ] HEAD-drift carve-out: when `validated_commit != HEAD`, inspect `git diff --name-only <validated_commit> HEAD` (via the existing subprocess pattern); all paths matching `*.md` → `warn-exempt`; any non-`.md` (source/script/config) path → `refuse` (refuse-and-revalidate / TOCTOU).
- [ ] `pass>0` zero-test guard: `pass==total==0` → refuse (CI false-positive anti-pattern), distinct reason string.
- [ ] Tests: register `lazy_core.py` `_TESTS` smoke fixtures covering EACH decision-table row — exempt-and-tick happy path, forged-attestation refuse, results-without-validated refuse, SKIP fail-closed, DEFERRED fail-closed, zero-test refuse, HEAD-drift docs-only warn-exempt, HEAD-drift source-file refuse-and-revalidate, neither-present refuse. Each builds a temp feature dir (and a git fixture for the HEAD-drift rows).

**Minimum Verifiable Behavior:** `python user/scripts/lazy-state.py --test` and `python user/scripts/test_lazy_core.py` both green, with the new `evaluate_completion_evidence` fixtures asserting: a temp feature dir carrying `VALIDATED.md` + a passing `MCP_TEST_RESULTS.md` (validated_commit == fixture HEAD) returns `verdict == "exempt-and-tick"`; the same dir with `MCP_TEST_RESULTS.md` removed returns `verdict == "refuse"`. This is a runnable command (`pytest user/scripts/test_lazy_core.py -q`), not "unit tests pass" in the abstract.

**Runtime Verification** *(checked by the Python test suite — this repo has no MCP runtime):*
- [ ] `python -m pytest user/scripts/test_lazy_core.py -q` green with the new evidence-table fixtures <!-- verification-only -->
- [ ] `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` green (shared `lazy_core` import surface unbroken) <!-- verification-only -->

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — new `evaluate_completion_evidence` helper near the existing `verify_ledger` / `__write_validated_from_results__` evidence-reading code (which already parses `MCP_TEST_RESULTS.md` pass/total/validated_commit — reuse those exact parse paths; do NOT duplicate them).
- `user/scripts/test_lazy_core.py` — register new fixtures in `_TESTS` (the dead-coverage guard `test_no_orphaned_test_functions` FAILS any unregistered `def test_*`).

**Testing Strategy:** Pure-function unit/fixture tests. The helper has exactly one I/O surface (reading sentinel files + one `git diff` for the drift row); fixtures build a temp dir with the sentinels written and, for drift rows, an init'd git repo with two commits. No mocking of the completion gate is needed — this phase is isolated from `_phase_completion_plan`.

**Integration Notes for Next Phase:**
- The verdict dict's `pass_count` field is the cardinality-lock numerator Phase 2 asserts against (`auto_tick_count <= pass_count`). Phase 1 MUST surface `pass_count` in the return so Phase 2 does not re-parse `MCP_TEST_RESULTS.md`.
- The `validated_commit` (sha) field is what Phase 2 stamps into each row's `<!-- auto-ticked: validated_commit=<sha> -->` audit comment — surface it in the return.
- Decide the exact verdict vocabulary here (`exempt-and-tick` / `warn-exempt` / `refuse`); Phase 3 branches on these literal strings, so they are a locked contract once this phase lands.

---

### Phase 2: Atomic, line-anchored, audited auto-tick rewrite of verification rows

**Scope:** Add the PHASES.md normalization pass: given a feature whose Phase-1 verdict is `exempt-and-tick` (or `warn-exempt`), rewrite every remaining unchecked verification-marked row (`- [ ]` carrying `<!-- verification-only -->`) to `- [x]`, atomically and auditably, with the cardinality over-relaxation guard. This phase owns the *mutation* contract; it is still NOT wired into `__mark_complete__` (that is Phase 3) — it is exercised directly by fixtures so the rewrite safety properties are proven in isolation.

**Deliverables:**
- [ ] `lazy_core.py`: new `autotick_verification_rows(phases_path, validated_commit, pass_count) -> dict` returning `{ticked_count: int, ok: bool, reason: str|None}`. Uses the existing `_atomic_write` helper (`lazy_core.py:97`, temp-in-same-dir → `os.replace`) — never `open('r+')` / naive truncate.
- [ ] Line-anchored + code-fence-safe matcher: rewrite only lines matching `^\s*-\s+\[\s+\]` that ALSO carry `_VERIFICATION_ONLY_MARKER` on the SAME line (tolerate variable whitespace `- [  ]`); skip any line inside a ``` fence. NO global `.replace('- [ ]','- [x]')`. Reuse the fence-tracking pattern already in `_phases_text_scoped_to` / `remaining_unchecked_are_verification_only`.
- [ ] Audit-trail comment: append a byte-stable `<!-- auto-ticked: validated_commit=<sha> -->` to each rewritten row, so a later auditor distinguishes gate mutations from human/agent edits.
- [ ] Cardinality lock: assert `ticked_count <= pass_count`; if more rows would be ticked than tests passed, abort the rewrite (return `ok: false`, write nothing) — catches marker-drift hallucination / forged evidence.
- [ ] Superseded-aware: do NOT count or require unchecked boxes under phases whose Status is `Superseded` (mirror `_phase_completion_plan`'s existing `is_superseded` skip) so the downstream `check-docs-consistency.ts` is satisfied without ticking superseded rows.
- [ ] Tests: `_TESTS` fixtures — happy rewrite (N marker rows → all ticked, audit comments present, atomic), code-fence row NOT touched, non-verification `- [ ]` row NOT touched, variable-whitespace `- [  ]` row IS matched, cardinality-lock abort when `ticked_count > pass_count`, Superseded-phase unchecked box left alone, idempotent re-run (already-ticked rows unchanged, no duplicate audit comment).

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py -q` green with a fixture that writes a temp PHASES.md containing one fenced `- [ ]` block, one plain implementation `- [ ]`, and two `- [ ]` rows carrying `<!-- verification-only -->`; after `autotick_verification_rows(path, sha, pass_count=2)` the file has exactly the two marker rows flipped to `- [x]` each with the audit comment, the fenced and implementation rows byte-unchanged, and `ticked_count == 2`. A second cardinality fixture with `pass_count=1` against the same 2-row file returns `ok: false` and leaves the file unmodified.

**Runtime Verification** *(checked by the Python test suite):*
- [ ] `python -m pytest user/scripts/test_lazy_core.py -q` green with the auto-tick rewrite fixtures (atomicity, fence-safety, cardinality lock, idempotency) <!-- verification-only -->

**Prerequisites:**
- Phase 1: the verdict dict supplies `validated_commit` (sha for the audit comment) and `pass_count` (cardinality-lock numerator). This phase consumes those; it does not re-read `MCP_TEST_RESULTS.md`.

**Files likely modified:**
- `user/scripts/lazy_core.py` — new `autotick_verification_rows` near `_phase_completion_plan` / the verification-marker helpers; reuses `_atomic_write` and `_VERIFICATION_ONLY_MARKER`.
- `user/scripts/test_lazy_core.py` — register the rewrite fixtures in `_TESTS`.

**Testing Strategy:** Fixture-driven over temp PHASES.md files. Atomicity is asserted by checking the file content is fully-rewritten-or-untouched (the cardinality-abort fixture proves the no-partial-write property). Fence-safety and marker-anchoring are asserted by byte-comparing non-target lines pre/post.

**Integration Notes for Next Phase:**
- `autotick_verification_rows` returns `ticked_count`; Phase 3 records this count in `COMPLETED.md` (the receipt audit field) and surfaces it in the `--apply-pseudo` JSON result alongside the existing `flipped_phases`.
- The rewrite MUST run BEFORE `_phase_completion_plan`'s residual-incoherence check re-evaluates in Phase 3 (tick first, then the gate sees zero unchecked verification rows). Phase 3 owns the ordering.

---

### Phase 3: Wire the evidence-gated exemption into `_phase_completion_plan` / `__mark_complete__`, with kill-switch

**Scope:** Connect Phases 1+2 into the live completion path. `_phase_completion_plan` (and its `__mark_complete__` / `__mark_fixed__` `--apply-pseudo` call site) now: consult the Phase-1 evidence verdict; when it is `exempt-and-tick`/`warn-exempt` AND every remaining unchecked row is verification-marked, run the Phase-2 auto-tick rewrite, record the count in `COMPLETED.md`, then proceed to mint the receipt. A genuine unchecked *implementation* row still refuses, naming the phase. The entire relaxation sits behind an env kill-switch that restores the legacy strict behavior. This is the phase that crosses the full live boundary (gate → evidence → mutation → receipt), so it carries the end-to-end completion smoke test.

**Deliverables:**
- [ ] `_phase_completion_plan` (`lazy_core.py:1824`): thread the evidence verdict so that when remaining unchecked rows are ALL verification-marked AND the verdict is exempt/warn-exempt, those rows are NOT counted as refusals (they will be auto-ticked); a non-verification unchecked row still appends a refusal naming the phase. Preserve the existing auto-flip-to-Complete and Superseded behavior exactly. (Signature change: pass the evidence verdict + a callable/flag in; update all in-repo callers — `verify_ledger` and the `--apply-pseudo` handler — and the `--test` fixtures.)
- [ ] `--apply-pseudo __mark_complete__` / `__mark_fixed__` handler: BEFORE the residual-incoherence refusal, when the verdict authorizes, call `autotick_verification_rows`; then re-run the coherence check (now zero unchecked verification rows); then mint the receipt. Order: tick → re-check → write receipt.
- [ ] `COMPLETED.md` receipt: record the auto-ticked row count (e.g. `auto_ticked_rows: <n>`) so a later auditor sees how many rows the gate mutated. Mirror in `FIXED.md` for `__mark_fixed__`.
- [ ] Kill-switch env var (`LAZY_STRICT_EVIDENCE_GATE` / `LAZY_DISABLE_AUTOTICK`): when set/truthy, `_phase_completion_plan` falls back to the legacy strict path (verification rows INCLUDED in refusals) and the auto-tick rewrite is skipped entirely — frictionless rollback with no code revert. Read once via `os.environ.get`.
- [ ] `--apply-pseudo` JSON result surfaces `auto_ticked_rows` alongside `flipped_phases` (orchestrator-visible), matching the existing warning/flip surfacing pattern.
- [ ] Tests: end-to-end `_TESTS` fixtures — (a) validated feature with only verification rows unchecked → `__mark_complete__` mints `COMPLETED.md`, rows ticked, `auto_ticked_rows` recorded, NO refusal; (b) feature with a real implementation `- [ ]` row → refuses, names the phase, zero writes (PHASES.md byte-unchanged, no receipt); (c) `verify_ledger` and `_phase_completion_plan` agree on the same input (both pass, or both name the same phase); (d) kill-switch set → legacy refusal, zero PHASES.md mutation; (e) the Phase-1 refuse rows (missing results, SKIP/DEFERRED, zero-test, cardinality over-tick, source HEAD-drift) all refuse at the live gate with NO tick.

**Minimum Verifiable Behavior:** `python user/scripts/lazy-state.py --test`, `python user/scripts/bug-state.py --test`, and `python user/scripts/test_lazy_core.py -q` all green. The decisive end-to-end fixture: a temp feature dir with passing evidence (validated_commit == HEAD) and a PHASES.md whose only unchecked rows are `<!-- verification-only -->`-marked, run through `--apply-pseudo __mark_complete__`, yields a `COMPLETED.md` on disk, every verification row flipped to `- [x]` with an audit comment, `auto_ticked_rows` recorded in both the receipt and the JSON result, and exit 0 — with NO recovery cycle. Re-running with `LAZY_STRICT_EVIDENCE_GATE=1` against the un-ticked file refuses (exit 1) and leaves PHASES.md byte-unchanged.

**Runtime Verification** *(checked by the Python test suite + the repo's full gate set):*
- [ ] `python user/scripts/lazy-state.py --test` + `python user/scripts/bug-state.py --test` green; baselines regenerated only via `_normalize_smoke_output` if intentionally changed <!-- verification-only -->
- [ ] `python -m pytest user/scripts/ -q` full suite green <!-- verification-only -->
- [ ] `python user/scripts/lazy_parity_audit.py --report` clean — the completion-gate change is mirrored to / shared across both state machines via `lazy_core`, no unexplained drift <!-- verification-only -->

**Prerequisites:**
- Phase 1: `evaluate_completion_evidence` verdict.
- Phase 2: `autotick_verification_rows` rewrite.

**Files likely modified:**
- `user/scripts/lazy_core.py` — `_phase_completion_plan` signature + body, the `--apply-pseudo __mark_complete__`/`__mark_fixed__` handler, the `COMPLETED.md`/`FIXED.md` receipt writer (add `auto_ticked_rows`), kill-switch env read.
- `user/scripts/lazy-state.py` — `--test` fixtures for the completion path (already imports `lazy_core`); regenerate the pinned `--test` baseline if output legitimately changes.
- `user/scripts/bug-state.py` — mirror `--test` fixtures for `__mark_fixed__`; pinned baseline.
- `user/scripts/test_lazy_core.py` — register the end-to-end + kill-switch fixtures.
- `user/scripts/CLAUDE.md` — document the new evidence-gated completion exemption + kill-switch under the "Verification-only canonical marker" / completion-gate section (keep the schema/behavior prose in lockstep with the code, per the Coupling Rule).

**Testing Strategy:** End-to-end through the real `--apply-pseudo` entry point against temp feature/bug dirs (the same harness the existing completion fixtures use). The kill-switch fixture sets the env var inside the fixture and asserts byte-identical legacy behavior. `verify_ledger`-agreement is asserted by running BOTH gates on one fixture and comparing verdicts. Full repo gate set (`project-skills.py` is a no-op here since no skill prose changes except CLAUDE.md docs; `lint-skills.py`, `pytest`, `lazy_parity_audit.py`) runs before the phase is marked done.

**Integration Notes for Next Phase:** (terminal phase) — none. On completion, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending); the state machine routes to the Step-9 validation tail (here: operator `SKIP_MCP_TEST.md` → VALIDATED.md per the repo's MCP exemption), then `__mark_complete__` mints the receipt. Do NOT self-flip to Complete.

---

## Implementation Notes

- **Single-repo, reversible change.** Per Technical Design (LOCKED, Direction A): all edits are in `lazy_core.py` (+ its two state-machine importers' `--test` fixtures + `CLAUDE.md` docs). No sibling-repo (`check-docs-consistency.ts`) edit — the exhaustive auto-tick normalization satisfies the naive count-everything checker (SPEC Open Question 4 / RESEARCH_SUMMARY finding 6).
- **Lint side is out of scope here (Swiss-Cheese, owned upstream).** SPEC Open Question 5: this feature owns the completion-gate EVIDENCE side; the authoring-time marker-correctness lint (marker only on test-shaped rows) is partly upstream in `harness-hardening-retro-fixes`. The gate-side mitigation for a hallucinated marker on an implementation row is the Phase-2 cardinality lock (`ticked_count <= pass_count`). Not re-litigated here.
- **`lazy_core.py` line anchors** (`:97`, `:1396`, `:1419`, `:1824`, `:2780`+) verified live 2026-06-19; minor drift resolved by symbol name during implementation, per the SPEC's note.
