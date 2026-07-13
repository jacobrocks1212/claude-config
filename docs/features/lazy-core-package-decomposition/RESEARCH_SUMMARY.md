# RESEARCH_SUMMARY — lazy-core-package-decomposition

Module-boundary inventory measured against the working tree at HEAD `337e41de` (2026-07-13).
All figures here **supersede the SPEC's 2026-07-11 anchors**, which tonight's ~20 lazy_core commits
made stale. Read the "Spec-refresh deltas" and "Three landmines" sections before executing — they
change the risk profile materially.

## Baseline metrics (re-measured; benchmark harness `benchmark_lazy_core_import.py`)

| Proxy | SPEC (2026-07-11) | Re-measured (HEAD, 2026-07-13) | Note |
|-------|-------------------|-------------------------------|------|
| `lazy_core.py` LoC | 17,686 | **20,172** | +2,486; still the hottest file |
| `import lazy_core` cold wall | 107 ms warm | **88.7 ms best / 93.7 median** (cold subprocess) | lower than cited; still the per-fire hook tax |
| `test_lazy_core.py` LoC | 32,675 | **37,842** | one flat file |
| pytest collection | 973 tests / 8.60 s | **1125 tests / 0.30 s in-proc (0.77 s subprocess)** | **collection is NOT 8.6 s** — the "collection tax" premise is largely stale |
| duplicate `_current_head` (F811) | 2 defs @3875/@5661 | **1 def @6510** — already de-duped | a `test_duplicate_def_guard_detects_planted_violation` guard already exists |

The load-bearing consequence: the **test-drag** rationale (D5) and the **F811 baseline-fix** rationale
(D6) are weaker than the SPEC assumes. The **hook-import-cost** rationale (D4) and the **blast-radius /
review-scope** rationale (D1) remain fully valid — an 88 ms full-module parse on every PreToolUse fire,
and every one-plane change canarying against a 20K-line module, are real and unchanged.

## Section map (verified section headers + key-function anchors, HEAD line numbers)

| Plane (target submodule) | Approx range | Key anchors | Risk |
|--------------------------|--------------|-------------|------|
| Diagnostics + `_ctx` globals | 85–335 | `clear_diagnostics`@102, `_atomic_write`@111, `_DIAGNOSTICS`@~88 | identity-critical |
| Queue dependency DAG (`depdag`) | 336–807 | dep-block regex@352, `parse_dep_block` | clean |
| Sentinel parsing (`docmodel`) | 808–1080 | `parse_sentinel`@878 | clean |
| SKIP/app-surface predicates | 1081–1400 | skip-waiver, app-surface | clean |
| SPEC parsing helpers (`docmodel`) | 1154–1657 | park-provisional vocab, materialized-list | clean |
| Plan file parsing (`docmodel`) | 1658–2113 | complexity-tier set, `-part-K` regex | clean |
| PHASES.md analysis (`docmodel`) | 2115–2889 | `_PHASE_HEADING_RE`@2667 (copied in phases-slice.py) | clean |
| Gates / evidence (`gates`) | 3052–3623 | `evaluate_completion_evidence`@3257 | **write-path-adjacent** |
| Ledger verify (`gates`) | 3624–3953 | `verify_ledger`@4090 | medium |
| `apply_pseudo` (`pseudo`) | 4738–~6099 (~1,362 ln) | `apply_pseudo`@4738 | **riskiest; write-path** |
| Misc detectors | 6100–6505 | `detect_noncanonical_blocker`@6100, `write_completed_receipt`@1341 | medium |
| `_current_head` | 6510 (single) | — | — |
| Dispatch / prompt plane (`dispatch`) | 6687–7522 approx | cycle prompts, template dir@7659 (`__file__`) | medium |
| Runtime plane (`runtimeplane`) | 8231–10064 | `set_active_repo_root`@8686, `ensure_runtime`@9522 | medium; write-path |
| Marker / ownership / refusals (`markers`) | 10600–~12330 | run-marker, refuse-by-construction | **riskiest; write-path** |
| Prompt registry (`dispatch`) | 12171–13002 | skill-path@12244/12339 (`__file__`) | medium |
| Host capabilities (`hostcaps`) | 13387–13707 | — | clean |
| State-dir / registry (**hook surface**) | ~11618, ~13729 | `claude_state_dir`@11618, `_load_registry`@13729, `append_hook_event`@15963 | **D4 target — must land in a small submodule** |
| Provenance / deny ledger (`ledgers`) | 14183–15585 | — | medium; write-path |
| Telemetry / efficacy (`ledgers`) | 15585–15985 | — | medium; write-path |
| Notify plane (`notifyplane`) | ~19900–end | `notify_halt`@20011, `notify_event`@20076 | clean (but uses subprocess + `_atomic_write`) |

Top-level `def`/`class` count: **328**.

## Import fan-in (20 external importers — the facade's compatibility contract)

State scripts: `lazy-state.py`, `bug-state.py` (both `sys.path.insert` the scripts dir, then
`import lazy_core` + broad `from lazy_core import (...)`; both mutate `lazy_core._DIAGNOSTICS` in
place — the canonical-list-object contract).
Hooks (per-fire import cost): `lazy_guard.py` (`claude_state_dir`, `append_hook_event`,
`_load_registry`), `lazy_inject.py` (`import lazy_core`).
Sibling tools: `efficacy-eval.py`, `incident-scan.py`, `kpi-scorecard.py` (`lazy_core._atomic_write`,
deny-ledger compute), `lazy-queue-doc.py`, `toolify-promote.py`, `track-work.py`, `work-status.py`,
`skill-size-ratchet.py` (`lazy_core._atomic_write`).
pipeline_visualizer: `fleet.py`, `server.py`, `trends.py`.
Tests: `test_lazy_core.py`, `test_hooks.py`, `test_pipeline_visualizer.py`, `test_efficacy_eval.py`,
`test_project_skills.py`.

**Regex-over-source auditors that pin call-site spelling** (facade must keep these literals matching):
- `lazy_parity_audit.py`: `r"lazy_core\.notify_halt\("` (line 363), `r"(?:lazy_core\.)?set_active_repo_root\("` (306).
- `doc-drift-lint.py`: greps the `user/scripts/CLAUDE.md` "scripts" table for documented paths existing on disk → the `lazy_core.py` row must become a `lazy_core/` row **in the same commit** the file becomes a package.
- `phases-slice.py`: carries a **byte-identical private copy** of `_PHASE_HEADING_RE` (NOT an import) — a docmodel split does not touch it, but the "keep in sync" comment obligation persists.

**Independence contract preserved:** `lazy_coord.py` does **not** import `lazy_core` (the grep hits are
comments stating the prohibition + a documented `kernel_start_time`/`_atomic_write` duplication). Its
`--test` harness must keep passing without importing the package.

## Three landmines (why "move-only mechanical split" is NOT mechanical here)

These are the decisive execution risks, discovered by measurement, not present in the SPEC's framing.
Each turns a supposedly-mechanical move into a design decision.

### L1 — Monkeypatch-by-attribute-assignment identity (the dominant constraint)
`test_lazy_core.py` patches collaborators by **direct assignment on the module object**, not
`monkeypatch.setattr` and not qualified `lazy_core.X` access inside the code:
`lazy_core.time =` (14 sites), `lazy_core.os =` (6), `lazy_core.subprocess =` (1),
`lazy_core._atomic_write =` (2), and patched **functions** `write_runtime_lock`, `consume_nonce`,
`bind_marker_session`, `ack_oldest_deny` (2 each), plus ~15 constants.
Python resolves a free name inside a function from **that function's defining module globals**. If a
function moves to `runtimeplane.py`, its `subprocess`/`time`/`_atomic_write`/`write_runtime_lock`
references resolve from `runtimeplane`'s namespace — so a test patching `lazy_core.subprocess`
(the facade namespace) **no longer affects it**. This silently breaks tests with green-looking imports.
Consequence: a genuine cross-module move of any function that (a) is itself patched, or (b) references
a patched name, is **not** behavior-preserving unless either the reference is rewritten to qualified
`lazy_core.X` access (violates the SPEC's "zero logic edits" invariant) **or** the facade is a
`sys.modules` forwarding-module-class whose `__setattr__`/`__getattr__` proxy to the single body
module — but that only works while the body stays in ONE module (it does not survive functions
actually leaving that module). **This is a real D1 design fork, not a mechanical detail.**

### L2 — `__file__`-relative sibling/skill/template resolution
`lazy_core.py` derives paths from its own location six times:
`Path(__file__).resolve().parent / "harness-gate.py"` (@3141), `.../ "validate-plan.py"` (@3975),
`.parent.parent.joinpath(*_CYCLE_TEMPLATE_DIRNAME)` (@7659), `Path(__file__).parent` (@7871),
and `.parent.parent / "skills" / ... / "SKILL.md"` (@12244, @12339).
Moving the body into `lazy_core/__init__.py` (or any submodule) shifts `__file__` down one directory,
so `.parent` → `user/scripts/lazy_core/` and `.parent.parent` → `user/scripts/` — **all six break**.
The package's `__init__.py` (or `_ctx`) must expose a `_SCRIPTS_DIR` anchor computed once
(`Path(__file__).resolve().parent.parent`) and every mover reference it — a **required edit**, so even
the "pure file move" is not literally zero-edit.

### L3 — `_ctx` global identity + rebinding
`_DIAGNOSTICS` (canonical list object, mutated in place by both state scripts) must remain the **same
object** through the facade — a plain `from ._ctx import _DIAGNOSTICS` in the body preserves identity
for a mutated list, but `_legacy_state_migrated` / `_active_repo_root` are **rebindable** module globals
(and `_legacy_state_migrated` is patched by tests as `lazy_core._legacy_state_migrated =`). A submodule
that `import`s a rebindable name by value and then rebinds it forks its own copy — the classic
split-the-monolith identity bug. These require getter/setter wrapping (SPEC D2 anticipates this) — again
a **logic edit**, not a move.

## Extraction-order recommendation (unchanged from SPEC D3, risk-reconfirmed)

facade+`_ctx` → docmodel/depdag/hostcaps/notify (clean) → gates/ledgers/dispatch/runtime (medium,
gated on the now-satisfied bug receipts) → markers/pseudo (riskiest, last). But **every step past the
package skeleton is blocked on resolving L1** — see the SPEC's refreshed D1/D4 and PHASES Phase 1.

## Precondition status (SPEC Phase 0)

Both hard-dep bugs carry **Fixed + archived** receipts:
`docs/bugs/_archive/mark-complete-partial-apply-noop-unrecoverable/FIXED.md`
(`provenance: operator-directed-interactive`) and
`docs/bugs/_archive/production-sentinel-writes-bypass-atomic-write/FIXED.md`. Write-path moves
(Phase 4+) are **unblocked** by the dep gate; the residual blocker is L1 (facade mechanism), not the bugs.
