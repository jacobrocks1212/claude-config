# Lazy-Core Package Decomposition — Feature Specification

> `lazy_core.py` is a 17,686-line single-module monolith with 169 commits since 2026-05-01 — the
> hottest file in the repo — so every intervention, however local, canaries against one file, and
> the PreToolUse hooks (`lazy_guard.py`/`lazy_inject.py`) pay a full-module import (~107 ms warm,
> ~705 ms cold) on every fire. Its test twin `test_lazy_core.py` is 32,675 lines / 973 tests in
> one flat file (8.6 s collection, 726 hand-rolled `TemporaryDirectory` sites, zero
> parametrize/fixtures). Decompose it into a `lazy_core/` package behind a byte-compatible facade
> — cleanest seams first (docmodel, dep DAG, host capabilities, notify), the marker/ownership
> plane last — with three locked constraints: mutable module globals hoist into a shared `_ctx`
> first; the facade keeps all 20 importers and the regex-over-source auditors working unmodified;
> and no write-path module moves while the two open write-path bugs are unfixed (hard deps).
> In scope alongside: the test-file split with conftest fixtures, a fast-import path for hooks,
> and a ruff/pyflakes gate on `user/scripts/` (F811 would already catch `lazy_core.py`'s
> duplicate `_current_head` at lines 3875/5661).

**Status:** Complete
auto-accepted; **product forks D1/D4/D6 RATIFIED by operator 2026-07-13** (interactive session):
L1 facade mechanism = **3 (redirect-the-patches)**; D4 = **PEP 562 lazy facade**; D6 = **ruff
F-rules advisory-first**. Phase 0 landed green (preconditions verified + benchmark harness).
Phases 1–6 unblocked.
**Priority:** P1
**Last updated:** 2026-07-13
**Friction-reduction feature:** yes
**Source:** repo-exploration proposal session 2026-07-11 (architectural review of the state-script
plane; all line anchors and metrics re-measured against the working tree 2026-07-11)

**Depends on:**

- mark-complete-partial-apply-noop-unrecoverable — hard — **bug pipeline**
  (`docs/bugs/mark-complete-partial-apply-noop-unrecoverable/`, investigation Concluded
  2026-07-11): `apply_pseudo`'s multi-file `__mark_complete__` write sequence has a known
  partial-apply crash window. Splitting a file with a known-buggy write path guarantees the fix
  and the move land entangled; the fix lands first, on the monolith, where its diff is reviewable.
- production-sentinel-writes-bypass-atomic-write — hard — **bug pipeline**
  (`docs/bugs/production-sentinel-writes-bypass-atomic-write/`, investigation Concluded
  2026-07-11): production sentinel writes bypass `_atomic_write`; same rationale — the write-path
  contract must be honest before the write-path code moves.

> **Cross-pipeline note:** both hard deps are bug-pipeline items. `queue.json` `deps` cannot
> encode `bug:` ids in v1 (reserved/refused by `--sync-deps` validation), so the dep-gate cannot
> machine-enforce these. Enforcement is explicit instead: Phase 0 of PHASES.md is a precondition
> check that both bug dirs carry a fixed/archived terminal receipt, and the phase plan refuses to
> start Phase 4+ (the first write-path move) without it.
>
> Soft interplay with `state-cli-contract-registry` (sibling Draft, same session): no hard dep in
> either direction — its facade-preserving contract is this spec's locked constraint 2; whichever
> feature's write-path phases run second re-runs the smoke baselines on the merged tree (see that
> spec's D6).

---

## Decision Ledger (2026-07-13 finalization)

Re-audited against HEAD `337e41de` after tonight's ~20 lazy_core commits. See
`RESEARCH_SUMMARY.md` for the measured inventory and the three landmines.

**Refreshed metrics (SPEC anchors were stale):** `lazy_core.py` 20,172 LoC (was 17,686);
`import lazy_core` 88.7 ms cold best (was 107 ms warm); `test_lazy_core.py` 37,842 LoC / 1125 tests;
**collection 0.30 s in-proc** (was cited 8.60 s — the test-drag premise is largely stale); the
duplicate `_current_head` F811 is **already resolved** (single def @6510; a duplicate-def guard test
already exists). Net: D1 (blast radius) and D4 (hook import cost) rationales stand; D5 (test drag)
and D6 (F811 baseline fix) are materially weaker than the SPEC assumed.

**Preconditions (Phase 0) — SATISFIED:** both hard-dep bugs carry Fixed+archived receipts under
`docs/bugs/_archive/` — write-path moves are dep-gate-unblocked.

| Decision | Class | Disposition 2026-07-13 |
|----------|-------|------------------------|
| D1 package shape + facade | product-behavior | **RATIFIED 2026-07-13 (operator, interactive)** — recommendation A (package + permanent facade) accepted; L1 facade mechanism = **3 (redirect-the-patches)**: tests are split along seams (D5) and each patch points at the owning submodule. 1125-test count + names preserved; byte baselines untouched. |
| D2 locked constraints | mechanical | **AUTO-ACCEPT** + amended: add L2 (`__file__`-relative path anchor) and L3 (rebindable-global getter/setter) as first-commit obligations. |
| D3 extraction order | mechanical | **AUTO-ACCEPT** — order unchanged; every step past the skeleton is L1-blocked. |
| D5 test decomposition | mechanical | **AUTO-ACCEPT** but de-prioritized — collection is already 0.30 s, so the split's value is editor-ergonomics + per-seam selection, not collection time. `tests/` dir already exists. |
| D6 lint gate | product-behavior | **RATIFIED 2026-07-13 (operator, interactive)** — ruff F-rules on `user/scripts/`, **advisory-first** (flip to enforcing in a later session once clean). Lands as a *forward* guard — the headline F811 (`_current_head`) is already fixed. |
| D7 compute_state follow-up | mechanical | **AUTO-ACCEPT** — measurement-only hook; out of scope here. |
| D4 hook fast-import | product-behavior | **RATIFIED 2026-07-13 (operator, interactive)** — **PEP 562 lazy facade** accepted. Safe under L1 mechanism 3: patches target owning submodules directly, so the facade's lazy `__getattr__` never sits on the patched-collaborator-resolution path. Fallback B (thin `lazy_state_dir.py`/`lazy_registry.py`) remains the documented alternative if Phase-1/2 measurement disqualifies A. |

**The unresolved fork blocking Phases 1–6 (landmine L1 — needs operator ratification):**
Tests patch `lazy_core.time/os/subprocess/_atomic_write/write_runtime_lock/consume_nonce/...` by
direct attribute assignment. A function that leaves the `lazy_core` namespace stops resolving those
patched names from it, silently breaking tests. The three candidate mechanisms — each with a cost —
are an operator decision, not a mechanical one:

1. **Qualified-access rewrite** — every mover references collaborators as `lazy_core.X`. Preserves
   patchability but violates the SPEC's "zero logic edits / move-only" invariant across hundreds of
   sites; large, reviewable-but-noisy diff.
2. **Forwarding-module-class facade** — `sys.modules["lazy_core"]` becomes a class instance proxying
   `__getattr__`/`__setattr__` to a single body module. Keeps patchability *only while the body stays
   in one module* — i.e. it enables the package skeleton but NOT genuine seam extraction. Good for the
   D1 skeleton; does not by itself deliver the size/hook wins.
3. **Redirect the patches** — split tests along seams (D5) and point each patch at the owning submodule
   (`lazy_core.runtimeplane.subprocess`). Delivers real extraction but edits test bodies (must preserve
   the 1125 count + names; "baselines untouched" still holds — these are pytest tests, not the byte
   baselines).

Until an operator picks among 1/2/3, no seam extraction lands. This is a genuine PRODUCT fork
(it changes the invariant the whole feature is built on), correctly parked rather than force-resolved.

> **RESOLVED 2026-07-13:** the operator ratified **mechanism 3 (redirect-the-patches)** in an
> interactive session. Consequence for the invariants: "move-only" holds for production code
> (modulo the L2/L3 required anchors + intra-package import rewiring); test patch-target lines
> are the sanctioned edit surface, with the 1125-test count + names preserved per move commit
> and the byte baselines untouched.
>
> **Shim follow-up (RESOLVED 2026-07-13, Option C):** Phase 1 shipped a transitional
> `_resolve_ntfy_send` shim so the two state scripts' facade-level `[notify-halt-call-site]`
> smoke fixtures kept working without out-of-scope edits. The operator ratified **Option C** of
> the Phase-1 NEEDS_INPUT fork: the shim stays (correct + tested) until the notifyplane
> extraction (Phase 2 WU-4), which carries an explicit retirement WU — redirect the two fixtures
> to `lazy_core.notifyplane._ntfy_send`, delete the shim — leaving mechanism-3 as the SINGLE
> patch-visibility rule for all callers, internal and external.

## Executive Summary

Every recent harness intervention converges on one file. `lazy_core.py` is 17,686 lines
(re-measured 2026-07-11) with 169 commits since 2026-05-01 — its entire history, i.e. the file
has averaged >2 commits/day since it was born and is the most-churned file in the repo. The costs
are concrete: (1) **blast radius** — a one-function change shares a module with the marker
plane, the completion gates, and the provenance ledgers, so review and canary scope is always
"the whole state machine"; (2) **hook latency** — `lazy_guard.py` and `lazy_inject.py` `import
lazy_core` on every PreToolUse fire to reach three small surfaces (`claude_state_dir`,
`append_hook_event`, `_load_registry` — `lazy_guard.py:63,91,107,307`), paying the full-module
parse/exec (~107 ms warm re-measured; ~705 ms cold per the proposal session's measurement);
(3) **test drag** — `test_lazy_core.py` is 32,675 lines, 973 collected tests in 8.6 s
(re-measured), one flat file with 726 `TemporaryDirectory` call sites and zero
`parametrize`/fixture usage, so every test edit fights a 32K-line buffer and every run pays flat
collection; (4) **latent defects a gate would catch** — the module already contains two
`def _current_head` definitions (lines 3875 and 5661; the later silently shadows the earlier —
pyflakes F811), and no Python lint gate exists on `user/scripts/` at all (no
ruff/pyflakes/flake8 config or CI step — verified).

The decomposition is tractable because the module is already internally sectioned (verified
section headers): **cleanest** — the docmodel plane (sentinel parsing 802–1074 with
`parse_sentinel` at 872; plan parsing 1629–2084; PHASES.md analysis 2085–2889), the queue
dependency DAG (330–801), host capabilities (13387–13707), and the halt notifier (17242–end,
`notify` at 17624) are pure functions over parsed documents with almost no marker coupling;
**medium** — gates/evidence (`evaluate_completion_evidence` 2963, `verify_ledger` 3590),
provenance/deny ledgers (14183–15585) + telemetry/efficacy (15585–15985), the dispatch/prompt
plane (6687–7522) and prompt registry (12330–13002), and the runtime plane (`ensure_runtime`
8319, transient build 9393–10064); **riskiest** — the marker/ownership/refusals plane
(10454–12330, including refuse-by-construction at 11974) and `apply_pseudo` (3974–5245, a
~1,277-line function owning every sentinel/receipt write).

Naive splitting is dangerous for three named reasons, locked as design constraints (D2): the
module owns **mutable globals with identity contracts** — `lazy_core._DIAGNOSTICS` (line 88) is
documented at `lazy-state.py:68-72` as "the canonical list object" that callers must mutate
in place, plus `_active_repo_root` (7707) and `_legacy_state_migrated` (10370) — which must hoist
into a single `lazy_core/_ctx.py` before anything else moves; **regex-over-source auditors**
(`lazy_parity_audit.py:360-456` greps the state scripts for `lazy_core.<fn>(` call literals such
as `lazy_core.notify_halt(`; `doc-drift-lint.py`'s scripts table checks documented script paths
exist on disk) plus 20 importing files pin the import name and call-site spelling — so a facade
`lazy_core/__init__.py` re-exporting everything byte-compatibly is non-negotiable; and **two open
write-path bugs** mean the write plane is currently misdocumented — moving it now would smear the
fixes across a rename diff (hard deps above).

It serves the mission's **effective** criterion (interventions whose canary scope matches their
actual blast radius) and reduces measured friction: hook import cost on every PreToolUse fire, 8.6 s
of collection tax on every test run, and the review tax of 17.7K-line context for every
one-plane change.

## KPI Declaration

Drafted row (full schema; v1 signal rides the registered `process-friction-count` selector; the
primary metrics are deterministic on-disk/on-clock proxies named in notes, re-measurable in one
command each):

```json
{
  "id": "lazy-core-monolith-intervention-drag",
  "system": "lazy-core",
  "title": "Monolith-induced drag on lazy_core interventions",
  "friction": "Every harness intervention lands in one 17,686-line module imported wholesale by PreToolUse hooks (~107ms warm import per fire) and tested from one 32,675-line file (8.6s collection, 973 tests), so review scope, canary scope, hook latency, and test drag are all paid at whole-state-machine size for one-plane changes.",
  "signal": { "source": "deny-ledger", "selector": "process-friction-count" },
  "unit": "count",
  "direction": "down-is-good",
  "baseline": { "value": null, "captured_at": null, "window": "30d", "provenance": "pending" },
  "band": null,
  "review_by": "2026-11-01",
  "repo_scope": "claude-config",
  "notes": "v1 rides the registered process-friction-count selector (lazy-core-attributable process-friction incidents in the deny ledger); a dedicated selector is registered at implementation if incident attribution proves too coarse. The load-bearing success measures are deterministic proxies captured in this spec and re-measured at each phase gate: (1) hook import: python3 -c 'import lazy_core' wall ms, 107ms warm at baseline -> target <15ms for the hook-touched surface via the lazy facade; (2) test collection: pytest test_lazy_core.py --collect-only 8.60s at baseline; (3) largest-module size: lazy_core.py 17,686 LoC at baseline -> no post-split module >4K LoC; (4) F811/pyflakes findings on user/scripts/: >=1 known at baseline (_current_head x2) -> 0 with the gate on. Provenance stays pending until the Phase-1 benchmark harness stamps a measured baseline."
}
```

## Design Decisions

### D1. Package shape + facade contract

- **Classification:** `product-behavior (PENDING operator)` — restructures the single most
  load-bearing module in the harness.
- **Question:** What does `lazy_core` become on disk, and what keeps 20 importers, two hooks,
  and the regex auditors working unmodified?
- **Options:**
  - **A — `user/scripts/lazy_core/` package with a re-exporting `__init__.py` facade
    (recommended):** submodules per seam (`_ctx.py`, `docmodel.py`, `depdag.py`, `hostcaps.py`,
    `notifyplane.py`, `gates.py`, `ledgers.py`, `dispatch.py`, `runtimeplane.py`, `markers.py`,
    `pseudo.py` — final roster fixed at Phase-1 review); `__init__.py` re-exports every public
    AND currently-used-private name (`_atomic_write`, `_DIAGNOSTICS`, `_load_registry`, …)
    byte-compatibly, so `import lazy_core` / `from lazy_core import _atomic_write` /
    `lazy_core.notify_halt(...)` all keep working and the parity-audit regexes keep matching
    the state scripts' unchanged call sites. `lazy_core.py` the *file* disappears; the one
    `user/scripts/CLAUDE.md` "Files in this directory" table row updates in the same commit
    (`doc-drift-lint.py` checks doc→disk existence, so the row update is gate-enforced, not
    optional).
  - **B — keep `lazy_core.py` as a thin shim over a differently-named package
    (`_lazy_core_pkg/`):** zero doc churn, but permanently ugly and the shim itself becomes an
    eighth wonder the auditors must know about.
  - **C — many top-level sibling modules (`lazy_docmodel.py`, `lazy_markers.py`, …):** no
    facade needed for new call sites, but every existing importer and auditor regex breaks —
    exactly what constraint 2 forbids.
- **Recommendation:** A. The facade is a compatibility contract, not a transition aid — it is
  permanent, and new internal call sites may still use it (the split is about module size and
  import cost, not about churning 20 consumers).

### D2. Locked constraints (the three reasons naive splitting fails)

- **Classification:** `mechanical-internal (auto-accept candidate)` — these are constraints the
  seams impose, not choices.
- **Constraint 1 — `_ctx.py` hoists the mutable globals FIRST.** `_DIAGNOSTICS`
  (`lazy_core.py:88`) has a documented object-identity contract: `lazy-state.py:68-72` imports
  the module "so `lazy_core._DIAGNOSTICS` is the canonical list object" and mutates *that list*.
  `_active_repo_root` (7707) and `_legacy_state_migrated` (10370) are rebindable module globals
  read across planes. All three move into `lazy_core/_ctx.py` in the first extraction commit,
  with the facade exposing the same objects (`from ._ctx import _DIAGNOSTICS, ...`); rebinding
  globals (`_active_repo_root`) are wrapped in getter/setter functions inside `_ctx` so
  submodules never rebind a name they imported by value (the classic split-the-monolith
  identity bug). A dedicated test asserts `lazy_core._DIAGNOSTICS is lazy_core._ctx._DIAGNOSTICS`
  and that a mutation through the facade is visible to a reader inside a submodule.
- **Constraint 2 — the facade keeps auditors and importers unmoved.** 20 files import
  `lazy_core` (re-measured: both state scripts, both hooks, `lazy_coord.py`,
  `kpi-scorecard.py`, `efficacy-eval.py`, `incident-scan.py`, `toolify-promote.py`,
  `track-work.py`, `work-status.py`, the three `pipeline_visualizer/` modules, and five test
  files). `lazy_parity_audit.py` greps state-script *source text* for `lazy_core.<fn>(` call
  literals (e.g. `_NOTIFY_HALT_RE = re.compile(r"lazy_core\.notify_halt\(")` at line 357).
  None of these files change in any extraction commit; a CI-side check greps the diff of each
  extraction commit and fails if it touches any importer other than the package itself (+ the
  doc-table row commit-1 exception).
- **Constraint 3 — write-path bugs fixed before write-path moves.** The two hard-dep bugs live
  exactly in the riskiest plane (`apply_pseudo` sequencing; sentinel `write_text` vs
  `_atomic_write`). Phases 1–3 (facade/_ctx, docmodel/depDAG/hostcaps/notify, tests) touch no
  write path and may proceed while the bug fixes land on the monolith; Phase 4+ (gates,
  dispatch, runtime, markers, pseudo) is gated on both bugs carrying fixed/archived receipts
  (Phase 0 precondition check, re-run at the Phase-4 gate).

### D3. Extraction order (cleanliness-ranked seams)

- **Classification:** `mechanical-internal (auto-accept candidate)`
- **Resolution candidate:** facade + `_ctx` → **cleanest** (docmodel: sentinel parsing 802–1074,
  plan parsing 1629–2084, PHASES analysis 2085–2889; dep DAG 330–801; host capabilities
  13387–13707; notify 17242–end) → **test split** (D5; early, so every later move lands with
  per-seam tests already separated) → **medium** (gates/evidence 2890–3870;
  provenance/ledgers 14183–15585 + telemetry 15585–15985; dispatch/prompt 6687–7522 + prompt
  registry 12330–13002; runtime plane 8194–10064) → **riskiest last** (marker/ownership/refusals
  10454–12330; `apply_pseudo` 3974–5245 — moved intact as `pseudo.py`, NOT internally refactored
  in this feature; decomposing the ~1,277-line function is its own future feature once it has a
  module boundary and a receipt-gated test wall around it). Each extraction is a
  move-plus-facade-re-export commit with zero logic edits — `git log --follow` and review diffs
  stay readable, and the full `test_lazy_core` suite + smoke baselines must be green per commit.

### D4. Hook fast-import path

- **Classification:** `product-behavior (PENDING operator)` — changes what the PreToolUse hooks
  execute on every tool call.
- **Question:** The hooks need 3 small surfaces but pay the full module. What cuts it?
- **Options:**
  - **A — PEP 562 lazy facade (recommended):** `lazy_core/__init__.py` defines the re-export
    surface via module-level `__getattr__` backed by a name→submodule map (plus eager import of
    only `_ctx`). Attribute access loads only the owning submodule: hooks touching
    `claude_state_dir`/`append_hook_event`/`_load_registry` pull only the small
    state-dir/registry submodules (proposal estimate ~10x import-cost cut — re-measured at
    Phase 1 by the benchmark harness; the 107 ms warm / ~705 ms cold baseline is per-fire hook
    tax today). State scripts doing broad `from lazy_core import (...)` simply trigger most
    submodules — no worse than today. Risk: lazy import moves ImportError timing from process
    start to first touch; mitigated by an eager `lazy_core.load_all()` called by the state
    scripts' main() and by the test suite importing everything.
  - **B — separate thin modules (`lazy_state_dir.py` + `lazy_registry.py`) that hooks import
    directly:** simplest possible hook path and no lazy-import machinery, but it forks the
    state-dir/registry logic's import name — two spellings for one surface, and the auditors/
    docs must learn the second one.
  - **C — eager facade, accept the cost:** simplest, but preserves the exact hook tax this
    feature cites, and the tax scales with every future line added to any plane.
- **Recommendation:** A, with B as the documented fallback if PEP 562 interacts badly with
  anything in the hook environment (measured, not assumed, at Phase 1).

### D5. Test decomposition

- **Classification:** `mechanical-internal (auto-accept candidate)`
- **Resolution candidate:** split `test_lazy_core.py` (32,675 lines / 973 tests / 726
  `TemporaryDirectory` sites / zero fixtures — all re-measured) along the same seams into
  `user/scripts/tests/test_lazy_core/` (`test_docmodel.py`, `test_markers.py`, …) with a shared
  `conftest.py` owning a `tmp_repo` fixture (tmp dir + minimal `docs/features` skeleton — the
  pattern currently hand-rolled 726 times). Mechanical move first (tests keep their bodies;
  imports unchanged via the facade), fixture adoption incrementally per file afterwards — never
  a rewrite-the-suite commit. Test count is receipt-checked per move commit: collected-test
  count before == after (973 at baseline), names preserved, so no test is silently dropped.
  Collection cost falls with per-file selection (`pytest tests/test_lazy_core/test_markers.py`
  collects one seam, not 973 tests).

### D6. Python lint gate on `user/scripts/`

- **Classification:** `product-behavior (PENDING operator)` — a new gate that can go red on
  existing code.
- **Question:** No ruff/pyflakes/flake8 gate exists on `user/scripts/` (verified: no config
  file, no CI step). The split multiplies module boundaries — shadowed imports and duplicate
  defs become likelier, and F811 would already catch the existing duplicate `_current_head`
  (`lazy_core.py:3875` vs `5661` — the second def silently shadows the first; which body wins
  today must be diffed before either is deleted).
- **Options:**
  - **A — ruff with a narrow, correctness-only rule set (recommended):** `F` (pyflakes) + a
    small explicit list; no style rules (the repo has no formatting contract and a style gate
    would generate a worthless mega-diff). Advisory on first land (report, exit 0), promoted to
    enforcing once the baseline findings are fixed — the repo's standard advisory→ratchet
    pattern. Config committed at repo root scoped to `user/scripts/`.
  - **B — pyflakes only:** lighter, but ruff subsumes it and is the tool already pinned in
    sibling ecosystems.
  - **C — no gate:** keeps the status quo where a duplicate 40-line helper ships silently.
- **Recommendation:** A. The `_current_head` duplication is resolved as part of this gate's
  baseline-fix commit (diff both bodies; keep the semantically-current one; the twins'
  third+fourth copies at `lazy-state.py:393` / `bug-state.py:374` are the sibling spec's D5
  hoist and are NOT touched here).

### D7. compute_state monoliths — later-phase candidates only

- **Classification:** `mechanical-internal (auto-accept candidate)`
- **Resolution candidate:** `lazy-state.py::compute_state` is 2,047 lines (1617–3663) and
  `bug-state.py::compute_state` is 1,099 (621–1719) — the same monolith disease one level up.
  They are explicitly OUT of this feature's mandatory scope (they live in the twins, not
  `lazy_core`, and the sibling `state-cli-contract-registry` D5 touches the twins' plumbing) and
  are recorded here as the natural follow-up feature once (a) this decomposition proves the
  move-behind-a-facade playbook and (b) the sibling's builder extraction settles the twins'
  file layout. A final phase in this feature adds only the measurement hook: the composite
  worklist gains per-function-size visibility for the two functions so the follow-up has a
  baseline.

## User Experience

- **Interventions:** a hardening feature touching (say) the notify plane edits
  `lazy_core/notifyplane.py` (~500 lines) and its `tests/test_lazy_core/test_notify.py` — review
  and canary scope match the change. `import lazy_core` and every documented call spelling keep
  working; skills/docs need no updates beyond the one CLAUDE.md table row.
- **Hooks:** no behavior change; PreToolUse fires import only the state-dir/registry submodules.
  The Phase-1 benchmark prints before/after import ms into the phase receipt.
- **Tests:** `pytest user/scripts/tests/test_lazy_core/` runs everything (973 tests preserved);
  per-seam files run alone in seconds. New tests for a seam go in that seam's file; the flat
  32K-line file is gone.
- **On failure:** any extraction commit that breaks an importer fails the same commit's suite
  (all 20 importers are exercised by existing tests: `test_lazy_core.py`, `test_hooks.py`,
  `test_pipeline_visualizer.py`, `test_efficacy_eval.py`, smoke baselines for the twins). The
  facade means a consumer can never observe a half-moved state.

## Technical Design

```
user/scripts/lazy_core/            (package; replaces lazy_core.py — one doc-table row updates)
├── __init__.py                    PEP 562 lazy facade: eager `from ._ctx import *identity objects*`;
│                                  __getattr__ → name→submodule map re-exporting EVERY name the
│                                  monolith exported (public + used-private, byte-compatible);
│                                  load_all() for eager consumers (state-script main(), tests)
├── _ctx.py                        _DIAGNOSTICS (same list object), _active_repo_root get/set,
│                                  _legacy_state_migrated get/set  ← FIRST extraction commit
├── docmodel.py                    sentinel parsing (802–1074, parse_sentinel@872), plan parsing
│                                  (1629–2084), PHASES analysis (2085–2889)
├── depdag.py                      queue dependency DAG (330–801)
├── hostcaps.py                    host capabilities (13387–13707)
├── notifyplane.py                 halt notifier (17242–end, notify@17624)
├── gates.py                       evaluate_completion_evidence (2963), autotick (3330–3476),
│                                  verify_ledger (3590)                    ← after bug fixes
├── ledgers.py                     deny ledger + provenance (14183–15585), telemetry/efficacy
│                                  (15585–15985), canary (16183–…)
├── dispatch.py                    cycle/dispatch prompts (6687–7522), prompt registry (12330–13002)
├── runtimeplane.py                ensure_runtime (8319), transient build (9393–10064)
├── markers.py                     run-marker/ownership/refusals (10454–12330)  ← riskiest, last
└── pseudo.py                      apply_pseudo (3974–5245) moved INTACT (no internal refactor)

user/scripts/tests/test_lazy_core/ conftest.py (tmp_repo fixture) + one test file per seam;
                                   973-test count receipt-checked per move commit
ruff (F-rules) on user/scripts/    advisory → enforcing after baseline fix (incl. F811
                                   _current_head @3875/@5661 resolution)
```

- **Invariants per extraction commit:** move-only (zero logic edits); full suite + twins' smoke
  baselines (`user/scripts/tests/baselines/*`) green; no file outside the package + its tests
  (+ the commit-1 doc row) touched; `lazy_parity_audit.py` default invocation exit 0;
  `doc-drift-lint.py` exit 0.
- **Identity contracts:** `_ctx` owns every mutable global; facade re-exports the same objects;
  rebinding access only through `_ctx` functions; regression tests pin object identity across
  the facade.
- **Sequencing with open bugs:** Phase 0 verifies both hard-dep bug receipts; the check re-runs
  at the Phase-4 gate (first write-path move). Bug fixes land on whichever shape the tree has
  when they're ready — if they land pre-split they move with the plane; the split never lands
  first on an unfixed write path.
- **House invariants honored:** stdlib-only runtime code (ruff is a dev/CI-only tool, not a
  runtime import); facade permanence (never a deprecation treadmill for 20 consumers);
  receipt-gated phases (benchmark numbers + test-count receipts in phase evidence); gates that
  refuse early (the importer-diff check per commit) over review-time archaeology.

## Implementation Phases

- **Phase 0 — Preconditions + benchmark harness (~0.5 session).** Verify both hard-dep bug
  receipts (halt with BLOCKED.md naming the missing receipt otherwise); commit a tiny
  `benchmark_lazy_core_import.py` (wall-ms for `import lazy_core`, hook-surface-only import, and
  pytest collection) and stamp the measured baseline into the KPI row
  (`--capture-baseline` path once the selector narrows; the spec's 107 ms / 8.60 s / 17,686 LoC
  figures are the seed). Proven done: receipts verified; baseline numbers in the phase receipt.
- **Phase 1 — Facade + `_ctx` (~1 session).** Package skeleton; monolith body moves wholesale
  into a single private submodule behind the facade (`lazy_core/_monolith.py`) so the facade
  contract is proven BEFORE any seam moves; `_ctx` extraction with identity tests; PEP 562
  mechanism + `load_all()`; doc-table row update; importer-diff guard. Proven done: all 20
  importers + hooks + auditors green with zero edits; identity tests pass; hook-surface import
  ms recorded (facade alone may not cut it yet — honest number, not a claim).
- **Phase 2 — Cleanest seams (~1–2 sessions).** `docmodel.py`, `depdag.py`, `hostcaps.py`,
  `notifyplane.py` move out of `_monolith.py`; hook-touched state-dir/registry surfaces land in
  their own small submodule here so the D4 latency cut is realized and re-measured. Proven done:
  per-commit invariants; import-ms delta in receipt.
- **Phase 3 — Test split (~1–2 sessions).** `tests/test_lazy_core/` per D5; conftest `tmp_repo`;
  973-test count receipts; collection-time delta recorded. Proven done: count preserved;
  per-seam selection works.
- **Phase 4 — Medium seams (~2 sessions; gated on Phase-0 re-check).** `gates.py`,
  `ledgers.py`, `dispatch.py`, `runtimeplane.py`. Proven done: per-commit invariants; smoke
  baselines byte-identical.
- **Phase 5 — Marker plane + pseudo (~1–2 sessions).** `markers.py`, `pseudo.py` (intact);
  `_monolith.py` deleted (facade map now total). Proven done: `_monolith.py` gone; every seam
  ≤4K LoC; full invariants.
- **Phase 6 — Lint gate + follow-up hooks (~1 session).** Ruff F-rules advisory → baseline fix
  (incl. `_current_head` F811 resolution) → enforcing; per-function-size measurement hook for
  the D7 compute_state follow-up. Proven done: gate red on a fixture F811, green on the tree;
  KPI proxies re-measured and recorded.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Facade byte-compatibility | Every extraction commit | 20 importers + hooks pass their existing tests with zero edits; `lazy_parity_audit.py` exit 0 | full suite per commit |
| Mutable-global identity | Mutate `lazy_core._DIAGNOSTICS` through the facade | Reader inside a submodule sees the mutation; `is`-identity test passes | `test_ctx.py` |
| Zero behavior change | Twins' smoke run per extraction commit | `tests/baselines/{lazy,bug}-state-*` byte-identical | smoke suite |
| No test silently dropped | Each test-move commit | Collected count == 973 and names preserved | count receipt |
| Hook import cut | Phase-2 benchmark | Hook-surface import ms ≪ 107 ms baseline (target <15 ms; honest number recorded either way) | benchmark receipt |
| Write-path gating | Attempt Phase 4 with a missing bug receipt | Phase-0 re-check halts with BLOCKED.md naming the receipt | phase gate |
| Move-only discipline | Any extraction commit touching an importer | Importer-diff guard fails the commit | CI/gate check |
| Lint gate catches duplicates | Fixture module with a duplicate def | Ruff F811 error; tree green post-baseline-fix | gate fixture |
| No new monolith | Post-Phase-5 census | Every `lazy_core/` submodule ≤4K LoC; `_monolith.py` deleted | LoC census in receipt |

## Open Questions

- ~~**D1 (operator):** approve the package-with-permanent-facade shape (vs the B shim).~~
  **RESOLVED 2026-07-13:** approved; L1 mechanism = 3 (redirect-the-patches).
- ~~**D4 (operator):** approve the PEP 562 lazy facade for the hook path.~~
  **RESOLVED 2026-07-13:** approved (fallback B stays the documented alternative if Phase-1/2
  measurement disqualifies A).
- ~~**D6 (operator):** approve the ruff F-rules gate on `user/scripts/`.~~
  **RESOLVED 2026-07-13:** approved, advisory-first.
- **Empirical (Phase 1):** actual hook-surface import ms under the lazy facade (the ~10x
  proposal estimate is unverified until the benchmark exists); cold-start ms re-measurement
  (the ~705 ms figure is from the proposal session and was not re-measured 2026-07-11).
- **Empirical (Phase 6):** which `_current_head` body (3875 vs 5661) is semantically current —
  they must be diffed, not assumed identical, before the F811 fix deletes one.
- **Cross-pipeline dep mechanics:** whether the queue dep-gate grows `bug:` id support before
  this feature schedules — if it does, the two hard deps move from Phase-0 prose enforcement
  into `queue.json` `deps` via `--sync-deps`.

## Research References

- Re-measurement session 2026-07-11 (this spec): line counts (`wc -l`), commit census
  (`git log --oneline --since=2026-05-01`), section-header map of `lazy_core.py` (all seam
  anchors cited above), `_DIAGNOSTICS`/`_active_repo_root`/`_legacy_state_migrated` locations,
  importer census (20 files), hook import sites (`lazy_guard.py:63,91,107,307`), warm-import
  timing (107 ms), pytest collection (973 tests / 8.60 s), `TemporaryDirectory` census (726),
  fixture census (0), duplicate `_current_head` (3875/5661), absence of any Python lint config.
- `docs/bugs/mark-complete-partial-apply-noop-unrecoverable/SPEC.md` +
  `docs/bugs/production-sentinel-writes-bypass-atomic-write/SPEC.md` — the two hard deps; both
  investigations Concluded 2026-07-11.
- `user/scripts/lazy_parity_audit.py:360-456` + `user/scripts/doc-drift-lint.py` — the
  regex-over-source / doc-vs-disk auditors that lock constraint 2 (facade permanence).
- `docs/features/state-cli-contract-registry/SPEC.md` (sibling Draft) — D6 sequencing contract
  and the twins-side helper hoists deliberately excluded from this feature's scope.
- MEMORY: "Lazy-system audit 2026-06-10" — prior prioritized hardening findings for the
  lazy-family scripts; consulted for seam-risk ranking (marker plane last).
