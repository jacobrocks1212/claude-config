# lazy-core-package-decomposition — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 1 — Facade + `_ctx` skeleton

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-13
**Work completed:**
- Package skeleton (WU-1): `git mv user/scripts/lazy_core.py user/scripts/lazy_core/_monolith.py` (R100, zero content edits in the move itself); hand-authored `lazy_core/__init__.py` — permanent PEP 562 lazy facade (`_SUBMODULE_BY_NAME` overrides, `_FALLBACK_SUBMODULE="_monolith"`, `_ALL_SUBMODULES=("_ctx","_monolith")`, non-memoizing `__getattr__` with a submodule-name branch, `__dir__`, `load_all()`).
- Scripted patch-target redirect (WU-1, ratified L1 mechanism 3): every `lazy_core.<name>` → `lazy_core._monolith.<name>` in `test_lazy_core.py` for the 25 census names. **Receipt:** 165 occurrences rewritten, 0 residual; per-name assignment-site counts matched the census exactly and sum to **50 assignment sites** (the plan's "43" headline was arithmetic slippage — its own per-name table sums to 50). Zero `monkeypatch.setattr(lazy_core`/`patch.object(lazy_core` anywhere.
- `_ctx.py` extraction (WU-2, TDD — 4 contract tests written RED-first by an independent test agent): owns `_DIAGNOSTICS` (same list object — identity-pinned across facade/_ctx/_monolith), `_diag`, `clear_diagnostics` (in-place `.clear()`, identity-pinned), `_atomic_write` (shared kernel, byte-identical move), and accessor-based storage for the rebindables (`get_active_repo_root`/`set_active_repo_root_value`, `legacy_state_migrated`/`set_legacy_state_migrated`). `_monolith` rebind/read sites rewired through the accessors (set_active_repo_root body, active_repo_root read, migration guard); mechanism-3 test redirects for `_legacy_state_migrated`/`_active_repo_root` → `_ctx` (the resolving module); the 2 `_monolith._atomic_write` patch sites deliberately stay at `_monolith`.
- L2 `_SCRIPTS_DIR` anchor (WU-3): `_ctx._SCRIPTS_DIR = Path(__file__).resolve().parent.parent`; all six `__file__`-relative lookups repointed (harness-gate.py, validate-plan.py, cycle-template dir, `_here` sys.path fallback, 2× skill-path candidates). Zero `__file__` refs remain in `_monolith.py`.
- Doc row + manifest + canary (WU-4): `user/scripts/CLAUDE.md` row → `lazy_core/` (dir form); `docs/gate/control-surfaces.json` + `_CANARY_CONTROL_SURFACES_FALLBACK` → `user/scripts/lazy_core/**` (glob semantics verified against `_canary_glob_to_re`); 3 canary test fixtures retargeted intent-preservingly; `GATE_VERDICT.md` recorded (overfit flag-justified, tautology flag-justified, gate_weakening pass, complexity declared; checker: in_scope, no gate-weakening hit).
- `load_all()` wiring (WU-5, commit 1b): eager `lazy_core.load_all()` as first statement of `main()` in BOTH state scripts (coupled-pair lockstep; SPEC D4-A ImportError-timing mitigation; hooks deliberately not wired).

**Receipts (per-commit invariants):**
- Full battery green before commit 1a: pytest `user/scripts/` **2216 passed, 0 failed**; `lazy-state.py --test` + `bug-state.py --test` byte-pinned baselines pass (ZERO baseline regeneration); `lazy_parity_audit.py` exit 0; `cli_surface_gen.py --check` OK; `doc-drift-lint.py` 0 findings; `lint-skills.py` OK.
- Count+names receipt: pre-split collect = **1135 names**; post-Phase-1 = **1139** = the same 1135 preserved byte-identically + exactly the 4 sanctioned `_ctx` contract tests (`test_ctx_diagnostics_identity`, `test_ctx_mutation_visible_through_facade`, `test_ctx_rebindable_globals_via_accessors`, `test_monolith_patch_target_effective`); diff shows zero removals/renames.
- Benchmark re-run (`benchmark_lazy_core_import.py`, 2026-07-13, post-move): cold `import lazy_core` **best 36.34 ms / median 38.89 ms** vs the 88.7/93.7 ms Phase-0 baseline — the lazy facade defers the 20k-line `_monolith` import on bare import, a ~59% cut (better than the "may be a wash" expectation; the honest caveat: an eager consumer that touches any monolith attribute still pays the full load, so hook-path savings apply only to probes that never touch `_monolith` attributes). Collection 1139 in 0.85 s. LoC census: `_monolith.py` 20,289 (over the 4K ceiling — expected at Phase 1; later phases shrink it).
- Hooks-live check: `lazy-state.py --marker-present --repo-root .` exits cleanly, no traceback.

**Integration notes:**
- The facade NEVER memoizes forwarded attributes (patchability contract); only the eager `_DIAGNOSTICS` identity re-export is bound into facade globals (sanctioned — mutated in place, never rebound).
- Patch-redirect rule for later phases: a test patching by module-attribute assignment targets the module whose function-under-test RESOLVES the name. When a name moves out of `_monolith` into a new submodule, its patch sites move with it (the WU-2 `_ctx` redirects are the template), and `_SUBMODULE_BY_NAME` gets the new entries.
- `_ctx.py` is a leaf: it must never import `_monolith` or the facade.
- `test_monolith_patch_target_effective` pins `_notify_identity`'s clock read — revisit that pin when `_notify_identity` moves out of `_monolith`.

**Pitfalls & guidance (for later phases + retro):**
- **Plan enumeration gap (inbound seams):** the plan fixed all six OUTBOUND `__file__` lookups but enumerated no WU for INBOUND flat-file loaders of `lazy_core.py`. Two existed: `validate-plan.py::_load_lazy_core` (production — its failure was converted to a silent `{'ok': True}` by the structural backstop's broad fail-open, a false-green caught only by the batch-3 reviewer) and `test_validate_plan.py:34-38` (collection error). Both fixed to package imports; included in commit 1a as a documented importer-diff-guard deviation.
- **In-flight-state racing incident (initially logged as a falsified report — corrected):** the WU-3 impl agent's session outlived its first completion notification and kept working through the later batches; the red `plan_structural_backstop` state the batch-3 reviewer and the orchestrator observed was its IN-FLIGHT tree, and its final tree was genuinely 1139-green. The reviewer's independent re-run still added real value (it surfaced the validate-plan inbound seam early and precisely). Orchestration lesson for the retro: a subagent's completion notification is not proof its writes have settled — re-verify on a quiesced tree, and never stage (`git add -A`) while any dispatched agent may still be writing.
- **`_resolve_ntfy_send` shim (landed in commit 1a via the long-lived WU-3 session; reviewed post-hoc, PASS-WITH-NOTES):** `notify_halt`'s two `sender` closures now resolve the ntfy sender via `_monolith._resolve_ntfy_send()`, which honors a facade-level `lazy_core._ntfy_send = fake` patch (a plain `sys.modules["lazy_core"].__dict__` read — never triggers the facade `__getattr__`; unpatched behavior byte-identical). Rationale: the state scripts' in-file `[notify-halt-call-site]` smoke fixtures patch at facade level and were outside Phase-1's writable scope. This is a SECOND patch-visibility mechanism alongside ratified mechanism-3 — flagged to harden-harness to either bless it as the pattern for external-harness facade patches or redirect those fixtures in a later phase and retire the shim.
- **Canary fixture staleness:** swapping the manifest literal to a glob broke 3 canary tests whose fixtures used the exact old path; fixtures retargeted (`_monolith.py` for touch-fixtures, the glob literal for tuple-membership asserts).
- Harden-harness follow-ups spun off (see run report): (a) `run_structural_checks`'s fail-open converts loader crashes into silent structural-gate passes — should degrade to an ERROR finding; (b) stale path-arithmetic prose at `_monolith.py:7726` and ~12300/~12392 and the `migrate_legacy_state_dir` docstring.

**Review verdicts (batch audit trail):**
- Batch 1 (WU-1): PASS. Batch 2 (WU-2): PASS. Batch 3 (WU-3): NEEDS-REWORK (inbound validate-plan seam) → fixed → re-verified green. Batch 4 (WU-4 + canary fixtures): PASS (inline, deviation noted — all edits deterministically gate-verified).

**Files modified:**
- `user/scripts/lazy_core/{__init__.py,_ctx.py,_monolith.py}` — package skeleton (facade / kernel / moved body with sanctioned L2/L3 edits)
- `user/scripts/test_lazy_core.py` — mechanism-3 redirects (165 occurrences), 4 new `_ctx` contract tests (+ `_TESTS` registration), path/collector/canary accommodations
- `user/scripts/validate-plan.py`, `user/scripts/test_validate_plan.py` — inbound loaders → package imports (plan-gap fixes)
- `user/scripts/CLAUDE.md` — `lazy_core/` package row
- `docs/gate/control-surfaces.json` — `user/scripts/lazy_core/**` glob (+ in-body canary mirror)
- `docs/features/lazy-core-package-decomposition/GATE_VERDICT.md` — recorded gate verdict
- `user/scripts/lazy-state.py`, `user/scripts/bug-state.py` — eager `load_all()` in `main()` (commit 1b)

## Phase 2 — Cleanest seams (depdag, docmodel, hostcaps, notifyplane, statedir)

#### Implementation Notes (Phase 2)
**Completed:** 2026-07-13 (plan part 2 of 6, `/execute-plan`, 5 batches / 5 move-only commits)
**Work completed:**
- WU-1 `depdag.py` (commit e1d31e28): queue-dependency-DAG plane, 10 top-level names, 472 monolith
  deletions -> 491-line module. Zero test redirects (no patch sites target moved consumers). depdag
  imports `_die` + `has_completion_receipt` from `_monolith` top-level (no cycle: monolith never
  imports depdag) and — post-WU-2 — `spec_status` from `.docmodel`.
- WU-2 `docmodel.py` (commit d35306c9): read-path document-model plane, 61 names across 5 disjoint
  ranges (1,901 lines) — sentinel parsing + SKIP/app-surface predicates (moved WITH the sentinel
  plane; contiguous, marker-plane-free), `spec_status`, PROVISIONAL/parked-entry builders, plan-file
  parsing, PHASES analysis (`_PHASE_HEADING_RE`, `_VERIFICATION_ONLY_MARKER`). **Sliced AROUND the
  receipt writers** `has_completion_receipt`/`write_completed_receipt` (write-path stays in
  `_monolith` per SPEC D2 ordering). Import-back: `from . import docmodel` + 28-name value import +
  4 `docmodel._VERIFICATION_ONLY_MARKER` attribute rewrites (patched-name rule). 3 test patch-site
  redirects (`_VERIFICATION_ONLY_MARKER`). One deferred local import (`_die` in `parse_sentinel`).
- WU-3 `hostcaps.py` (commit c730a6bb): host-capability plane, 12 names, 375 pure deletions, ZERO
  monolith insertions (no import-back needed — every consumer resolves via facade). `utc_now_iso`
  moved with the contiguous slice (zero bare-name monolith consumers; no patch sites — rationale in
  the module docstring). `write_deferred_requires_host` (writer) sliced around. Deferred local
  imports: probe primitives in `_default_host_probes`; `read_run_marker` (+ `claude_state_dir`,
  re-pointed at WU-5) in `host_present_capabilities`. `_FakeOsName` trio untouched (consumers =
  `emit_cycle_prompt`, monolith-resident).
- WU-4 `notifyplane.py` + shim retirement (commit 5b1a57db): notify plane (22 names, 575 pure
  deletions, monolith tail). **Ratified Option C executed:** `_resolve_ntfy_send` DELETED (29
  lines); the two production sender closures rewrote the resolver call to plain `_ntfy_send(...)`
  (module-global, ordinary mechanism-3). Receipt: `grep -rn "_resolve_ntfy_send" user/scripts/`
  -> ZERO hits. State-script `[notify-halt-call-site]` fixtures redirected `lazy_core._ntfy_send`
  -> `lazy_core.notifyplane._ntfy_send` (3 lines each, symmetric; production
  `lazy_core.notify_halt(` call sites untouched — parity audit exit 0). 19 test-line redirects:
  11 `_NOTIFY_*` constant reads, 4 ledger-spy `_atomic_write` (scoped to
  `test_notify_ledger_roundtrip_prune_and_atomic`; the 3 kernel-direct `_atomic_write` tests + 2
  sentinel-lint prose mentions stay on `_monolith`), 3+1 pin-test `time` lines
  (`test_monolith_patch_target_effective` — its own docstring mandated the re-point when
  `_notify_identity` moved).
- WU-5 `statedir.py` + benchmark + receipt (this commit): hook-touched state-dir surface — 12 names
  (`claude_state_dir`, `_load_registry`, `append_hook_event` + closure: `repo_key`,
  `migrate_legacy_state_dir`, `active_repo_root`/`set_active_repo_root`, `_MARKER_FILENAME`,
  `_REGISTRY_FILENAME`, `_HOOK_EVENTS_FILENAME`, `_LEGACY_STATE_FILENAMES`, `_LEDGER_HEAD_CHARS`),
  ~249 lines across 8 disjoint ranges. TDD: `test_hook_surface_imports_without_monolith` written
  and verified RED first (subprocess exit 1 — `_monolith` in `sys.modules`), GREEN post-extraction.
  Monolith import-back: 8-name value import. ONE deferred local import: `_git` in
  `active_repo_root`'s cwd-git fallback (the hook path always binds `--repo-root`, so the fallback
  — and its `_monolith` load — is never paid by hooks). WU-3/WU-4 deferred `claude_state_dir`
  imports re-pointed to `.statedir` (hostcaps 1 site split; notifyplane 3 sites).
  `benchmark_lazy_core_import.py` gained additive `--hook-surface` (fresh-subprocess import +
  3-name facade touch, records `monolith_loaded_samples`).

**Receipts (per-commit invariant battery, all 5 commits):** pytest `user/scripts/` green (2219
passed per commit; 2220 on the final — the +1 TDD pin), `lazy-state.py --test` + `bug-state.py
--test` byte-pinned baselines pass with ZERO baseline regeneration, `lazy_parity_audit.py` exit 0,
`cli_surface_gen.py --check` OK, `doc-drift-lint.py` 0 findings, `lint-skills.py` OK. Collected
count 1141 with identical name set through WU-1..4; 1142 after WU-5's sanctioned pin (name-set
diff = exactly the one addition).

**Benchmark (2026-07-13, post-WU-5):** cold `import lazy_core` best 32.45 / median 35.85 ms; hook
surface (import + `claude_state_dir` + `_load_registry` + `append_hook_event`) best **42.64** /
median **43.98 ms** with **`monolith_loaded_samples=0`** — the D4 cut is mechanically realized
(statedir resolves all three; `_monolith` never imports on that path; pinned by the WU-5 test).
HONEST caveats: (a) the <15 ms KPI aspiration is NOT met — the Python-interpreter + facade
baseline alone is ~32 ms, so the statedir increment is ~8-11 ms; (b) the guard's marker-reading
paths (`read_run_marker` etc.) still load `_monolith` until Phase 5 — this number covers ONLY the
statedir-resolved hook surface. Monolith LoC: 20,289 (post-P1) -> 16,784 (post-P2).

**Review verdicts (batch audit trail):**
- Batch 1 (WU-1): PASS (dedicated review subagent; byte-verbatim move confirmed via difflib).
- Batch 2 (WU-2): PASS (dedicated review subagent; 0 unexplained diff lines across 1,905 deletions
  / 41 sanctioned insertions; 5 semantically-null blank-line collapses at range joints noted).
- Batch 3 (WU-3): PASS (inline: 375-deletion/0-insertion numstat, facade 12/12 AST-verified,
  residue grep zero, full battery green pre-commit; agent report corroborated).
- Batch 4 (WU-4): PASS (inline: full move-only accounting — all 37 body-diff lines are the
  sanctioned shim deletion + 2 closure rewrites + 4 deferred imports; name set identical).
- Batch 5 (WU-5): PASS (inline: TDD RED->GREEN pin, AST unresolved-name scan clean after the
  `_LEDGER_HEAD_CHARS` closure fix, full battery green pre-commit).

**Deviations & findings (for the retro):**
1. Task tools (TaskCreate/TaskUpdate) unavailable in the executing environment — plan-part WU
   checkboxes + PHASES.md served as the persistent ledger.
2. Importer-diff guard deviation (documented per commit message): each seam commit also carries
   the plan-part WU checkbox tick (+ status flips) — required by `/execute-plan`'s verify-ledger
   contract; the plan's allowed-set enumeration omitted the plan file itself.
3. Plan drift: the "keep in sync with phases-slice.py" comment the plan required to travel with
   `_PHASE_HEADING_RE` never existed in `_monolith.py` — the sync obligation lives on
   `phases-slice.py`'s side (its own "keep byte-identical" comment + the facade map) and is
   intact. HARDENING GAP (batched to harden-harness): no mechanical test pins the two regex
   copies equal.
4. Plan said suite count 1135; live baseline was 1141 (+4 sanctioned Phase-1 `_ctx` tests, +2
   hardening-round tests post-authoring). Name-set diffs were verified per commit against the
   live captured baseline.
5. WU-2/WU-3 subagents each initially ended their turn with verification incomplete (backgrounded
   test runs); resumed and completed honestly. WU-4/WU-5 executed inline by the orchestrator on
   coordinator directive (contract deviation recorded: batches 4-5 had zero sub-subagent
   dispatches; scripted transforms + full battery + the inline review protocol applied instead).
6. `append_hook_event`'s fail-open masked a missing closure constant during WU-5 (returned False
   instead of raising on the unresolved `_LEDGER_HEAD_CHARS`) — caught by the existing shape
   test, fixed by moving the constant. Note for Phase 4/5 movers: fail-open functions hide
   NameErrors; AST-scan for unresolved names after every slice.

**Files modified (net, Phase 2):**
- `user/scripts/lazy_core/{depdag,docmodel,hostcaps,notifyplane,statedir}.py` (new seam modules)
- `user/scripts/lazy_core/{__init__,_monolith}.py` (facade map growth; pure seam deletions + import-backs)
- `user/scripts/test_lazy_core.py` (mechanism-3 redirects; +1 TDD pin)
- `user/scripts/lazy-state.py`, `user/scripts/bug-state.py` (WU-4 fixture lines only)
- `user/scripts/benchmark_lazy_core_import.py` (WU-5 `--hook-surface`)
- plan part 2 (WU ticks + status), `PHASES.md` (P2 rows + receipt), this file

## Phase 3 — Test split (tests/test_lazy_core/ package)

#### Implementation Notes (Phase 3)
**Completed:** 2026-07-13 (plan part 3 of 6, `/execute-plan`, 3 WUs, ONE atomic commit)
**Work completed:**
- `user/scripts/test_lazy_core.py` (38,476 lines / 1142 pytest-collected tests) split into the
  package `user/scripts/tests/test_lazy_core/`: 12 per-seam files + shared `_util.py` +
  `conftest.py` (sys.path bootstrap + the new `tmp_repo` fixture) + empty `__init__.py`. Old flat
  file deleted in the same commit (atomic — both present would double-collect / package-shadow).
- Line counts: docmodel 3586 / depdag 600 / hostcaps 527 / notifyplane 922 / statedir 803 /
  gates 2793 / dispatch 5575 / runtimeplane 4290 / markers 7640 / pseudo 4237 / ledgers 4045 /
  misc ~4838 / _util ~1830. Tests per file: docmodel 155, markers 198, dispatch 129, pseudo 128,
  misc 130, ledgers 124, runtimeplane 123, gates 92, hostcaps 17, statedir 16, depdag 15,
  notifyplane 15 (= 1142).
- **Scripted transform honored (plan note 2):** WU-1 built a 1408-block gapless total partition
  (`split-map.json`, AST top-level blocks incl. preceding comments; coverage assertion 1..38476)
  + scratchpad analyzer; WU-2's scratchpad splitter (`build_split.py`) distributed VERBATIM line
  ranges — no test body retyped. Sanctioned non-verbatim edits: per-file headers
  (`_SCRIPTS_DIR = Path(__file__).resolve().parents[2]` + own-dir sys.path insert for `import
  _util`), per-file regenerated `_TESTS` registries + verbatim `main()` runner copies
  (runner state `_IMPORT_ERROR`/`_PASSES`/`_FAILURES`/`_guard`/`_run_test` duplicated per file
  by design — mutable runner state is per-file, plan risk note b), ~14 mapped `__file__`
  hop-count rewrites (constants → `parents[3]`, repo-root → `parents[4]`, scripts-dir →
  `parents[2]`), and the 3 self-auditing meta-guards generalized to iterate every
  `test_*.py` in the split dir (orphan guard now statically AST-extracts each sibling's
  `_TESTS` names; pure collectors unchanged).
- **Receipts (the phase gate, plan note 3):** pre-split capture 1142 collected; post-split
  `pytest user/scripts/tests/test_lazy_core/ --collect-only -q` = **1142 collected, 0 errors**;
  bare-name (`::`-suffix) multiset diff = **EMPTY** (scripted Counter diff, both sides 1142).
  NOTE: plan said "1135" and PHASES said "1125" — both stale literals; the live baseline (1142,
  = Phase 2's 1141 + its sanctioned TDD pin) was captured pre-change and used as the receipt.
- **Both runners verified:** full package `pytest` run **1142 passed** (212s); manual per-file
  runners green (`python tests/test_lazy_core/test_docmodel.py` 155/155 exit 0;
  `test_statedir.py` all pass exit 0); per-seam selection works
  (`pytest tests/test_lazy_core/test_markers.py -q` green). Full battery green pre-commit
  (pytest user/scripts/ + both state-script byte-pinned `--test` baselines with ZERO baseline
  regeneration + parity audit + cli-surface `--check` + doc-drift + lint-skills).
- **Collection-time delta (honest):** pre-split 0.29–0.36 s (single flat file); post-split
  0.79 s via `benchmark_lazy_core_import.py` fallback target `tests/` (package walk + conftest
  import). A small wall-time regression — the phase's value was editor ergonomics + per-seam
  selection (PHASES de-prioritization rationale), both realized.
- **tmp_repo fixture: defined, 0 adopters** — adoption is incremental per SPEC D5; no existing
  test was rewritten onto it (the 726 hand-rolled `TemporaryDirectory` sites are unchanged).

**Review verdicts (batch audit trail):**
- Batch 1 (WU-1, split map + conftest): PASS after one orchestrator-found map defect was fixed
  mid-flight (runner-state blocks `_IMPORT_ERROR`/`_FAILURES`/`_PASSES` initially mapped to
  test_misc.py only while their per-file consumers were ALL-duplicated — AnnAssign nodes missed
  by the ALL-classifier; fixed + coverage re-asserted). Ground-truth verified fresh.
- Batch 2 (WU-2, the split): agent's intermediate full-suite run showed 40 failures with 3
  self-diagnosed root causes; orchestrator (coordinator-directed takeover) applied the three
  designed fixes inline and re-verified: (1) `_util.py`'s `_REAL_TEMPLATE_DIR` never got its
  hop rewrite AND its `if not …exists()` fallback block was split away into test_misc.py —
  primary re-anchored `parents[2]`, fallback co-located back (`parents[3]`), stray block
  removed from test_misc.py (~37 failures); (2) `test_misc.py` missing
  `_collect_registered_test_names` in its `from _util import` (1 failure — orphan guard);
  (3) `test_statedir.py::test_clear_state_dir_restores_process_launch_override` patched its own
  module's `globals()` while the reader `_clear_state_dir` now lives in `_util` — repointed to
  `import _util` + `_util._ORIGINAL_LAZY_STATE_DIR` (1 failure). Post-fix: 1142/1142 green.
- Batch 3 (WU-3, docs + receipt + commit): inline (doc sweep rows in `user/scripts/CLAUDE.md`;
  root CLAUDE.md clean — doc-drift-lint 0 findings).

**Deviations & findings (for the retro):**
1. Task tools (TaskCreate/TaskUpdate) unavailable in the executing environment — plan-part WU
   checkboxes + PHASES.md served as the persistent ledger (same as Phase 2).
2. WU-2 fix-up + WU-3 executed inline by the orchestrator on coordinator directive (contract
   deviation recorded: the turn-end gate forbade idling on inner agents; WU-1 and the bulk of
   WU-2 were Sonnet-subagent-executed with ground-truth review; the WU-2 agent was killed by a
   transient API 529-class error mid-verification and its 3 designed fixes were applied inline).
3. Transitional collection error (KNOWN, unavoidable): between WU-1 and WU-2's delete, the old
   flat module shadowed the new package name (`'test_lazy_core' is not a package`) — the plan's
   WU-1 "collection unchanged" check is unsatisfiable while both exist; resolved by the atomic
   delete (0 collection errors after).
4. Plan drift: count literals stale (1135/1125 vs live 1142); `_TESTS` extension blocks were 18
   `_TESTS =` assignment sites (map found 71 registry blocks incl. list-literal continuation
   segments), not the plan's "7".
5. `pytest user/scripts/` total is now 2221 (concurrent hardening round added 1 test mid-phase);
   foreign-agent churn (docs/bugs/*, docs/interventions/*, user/skills/*) was excluded from this
   phase's commit via explicit pathspecs — `git add -A` would have swept another writer's
   uncommitted work.

**Files modified (net, Phase 3):**
- `user/scripts/tests/test_lazy_core/` (NEW: `__init__.py`, `conftest.py`, `_util.py`,
  12 `test_*.py`)
- `user/scripts/test_lazy_core.py` (DELETED)
- `user/scripts/CLAUDE.md` (7 live-path rows → `tests/test_lazy_core/`)
- plan part 3 (WU ticks + status Complete), `PHASES.md` (P3 rows + heading + Status line), this file

## Phase 4 — Medium seams (gates, ledgers, dispatch, runtimeplane)

#### Implementation Notes (Phase 4)
**Completed:** 2026-07-13 (plan part 4 of 6, `/execute-plan`, 4 WUs / 4 move-only commits)
**Work completed:**
- WU-1 `gates.py` (commit 4d0988b5): completion-gate plane — 29 names, ONE contiguous 1,478-line
  slice (gate_verdict_ok ship-seam plumbing, foreign-harden helpers, evaluate_completion_evidence
  + observation-gap/commit-drift verdicts, autotick (+`_UNCHECKED_ROW_RE`/`_AUTOTICK_COMMENT_PREFIX`),
  plan checkbox detail helpers, structural backstop, verify_ledger, summarize_failing_detail).
  Import-back 6 names. Redirects: 2 `import lazy_core._monolith as _mono` lines in test_gates.py
  (the 6 `_mono._load_validate_plan_module` patch sites resolve through them). WRITE-PATH GATE
  executed first: both archived receipts present.
- WU-2 `ledgers.py` (commit 26ce9313): 98 names, 2 slices (5-line `_DENY_LEDGER_FILENAME` block
  sliced out of the marker-constants region + the contiguous 3,376-line ledger tail: deny/friction
  ledger + acks + hardening emit-command, hook-events reader, guard-plane heartbeat, commit
  brackets, provenance plane, auto-readmit/transcription-slip, efficacy breadcrumbs, telemetry,
  interventions, canary). Import-back 10. Redirects: 37 test lines (ack_oldest_deny x11,
  `_TELEMETRY_*` x21, INTERVENTION_* x4, `_INTERVENTIONS_DIRNAME` x1). gates.py's 3 WU-1 deferred
  imports re-pointed `._monolith` -> `.ledgers`.
- WU-3 `dispatch.py` (commit 27a592ed): 43 names, 4 slices (cycle-template/emit_cycle_prompt/
  emit_dispatch_prompt 884 ln; skill-frontmatter readers 174 ln; `_CYCLE_COMMIT_*`/`_MULTI_COMMIT_*`
  constants 109 ln; prompt registry 672 ln) sliced AROUND the marker/ownership plane. Boundary
  verified: `consume_nonce` is registry read/write (moves); `resolve_cycle_worker_nonce`/
  `write_cycle_marker`/`refuse_*`/`REGISTRY_ENTRY_TTL_SECONDS`/`_REGISTRY_RING_CAP` stay for
  Phase 5. Import-back 8. Redirects: 32 test lines (consume_nonce x20 incl. `_util.py`,
  `_monolith.os` x10 — the `_FakeOsName` sites, consumer emit_cycle_prompt, -> `dispatch.os`;
  test_dispatch's 2 `_CYCLE_COMMIT_*` value asserts). test_markers' 2 `_CYCLE_COMMIT_MULTI` reads
  DELIBERATELY kept at `_monolith` (consumer detect_cycle_bracket_friction is monolith-resident and
  reads its own import-backed global — patching/reading `_monolith` is the correct resolution
  module there). ledgers.py's 2 `normalize_prompt_for_hash` deferred imports re-pointed to
  `.dispatch`; dispatch imports `_DENY_LEDGER_FILENAME` from `.ledgers` top-level (no cycle:
  ledgers reaches dispatch only via deferred function-local imports).
- WU-4 `runtimeplane.py` (this commit): 54 names, 2 slices (1,330 + 926 ln): ensure_runtime + M4
  evaluation/recovery + patient-waits, runtime/sidecar/frontend/stale probes, spawn_detached +
  Transient Build (run_transient_build/promote_artifact_atomically), reconcile_cycle_begin_git_
  consistency, kernel_start_time, runtime lock + boot stamp, verify_runtime_ownership, and the
  host-capability ACTIVE probe primitives (probe_binary/env/platform_capability — hostcaps'
  deferred import re-pointed `._monolith` -> `.runtimeplane`, closing Phase 2's partial-plane
  note). Import-back ZERO (remaining monolith references no runtime name — unresolved-globals
  scan green). Redirects: 63 test_runtimeplane lines (`subprocess` x32, `time` x23,
  write_runtime_lock x8 — code, docstrings, AND the meta-guard negative-fixture strings rewritten
  in lockstep). Meta-guards needed NO collector code change: `_is_lazy_core_chain` structurally
  accepts `lazy_core.<any-submodule>.subprocess`; post-redirect population verified NON-EMPTY
  (5 production-binding tests, 10 swap sites); one collector comment updated for accuracy
  (the sanctioned RETARGET edit — no assertion weakened).

**Receipts (per-commit invariant battery, all 4 commits):** pytest `user/scripts/` **2230 passed**
per commit; `lazy-state.py --test` + `bug-state.py --test` byte-pinned baselines pass with **ZERO
baseline regeneration** (`tests/baselines/` untouched all phase); `lazy_parity_audit.py` exit 0;
`cli_surface_gen.py --check` OK; `doc-drift-lint.py` 0 findings; `lint-skills.py` OK. Collect-only
count **2230 pre == 2230 post** per commit (full `user/scripts/` scope; the test_lazy_core subset
is 1142 — plan literals 1125/1135 stale as documented in Phase 3); bare-name multiset diff EMPTY
per commit (scripted sort+diff against the live pre-capture).

**Benchmark census (2026-07-13, post-WU-4):** `_monolith.py` **16,784 -> 7,858 LoC** (gates 1,533 +
ledgers 3,451 + dispatch 1,895 + runtimeplane 2,312; facade `__init__.py` 436). Cold `import
lazy_core` best 33.52 / median 38.08 ms (unchanged band vs Phase 2 — expected: bare import defers
everything). `_monolith.py` is the only module over the 4K ceiling (Phase 5 shrinks it further).

**Deferred `# Phase-5 re-point` inventory (function-local imports of monolith-resident names):**
- gates.py: `_current_head` (evaluate_completion_evidence).
- ledgers.py: `read_run_marker` (guard_plane_heartbeat, find_auto_readmit_entry,
  find_transcription_slip_entry), `head_sha_snapshot` + `read_cycle_marker`
  (record_cycle_commit_bracket), `head_sha_snapshot` (record_intervention),
  `_parse_locked_decisions` (write_provenance), `REGISTRY_ENTRY_TTL_SECONDS` (both find_* helpers),
  `_MARKER_STALE_SECONDS` (_run_marker_state_dir, _telemetry_run_marker,
  _originating_telemetry_paths).
- dispatch.py: `read_run_marker` (emit_dispatch_prompt, lookup_emission, resolve_emission_by_nonce,
  register_emission_if_marked), `_REGISTRY_RING_CAP` (register_emission),
  `REGISTRY_ENTRY_TTL_SECONDS` (lookup_emission, resolve_emission_by_nonce).
- runtimeplane.py: `_git` (_default_git_clean_staging).
- Pre-existing (Phase 2, unchanged): docmodel `_die`; statedir `_git`; notifyplane
  `detect_noncanonical_blocker`; hostcaps `read_run_marker`.

**Deviations & findings (for the retro):**
1. Plan's "Verified ground truth" line anchors were pre-Phase-1 and fully stale (expected; plan
   itself says "re-locate by pattern") — all four seams re-located by AST block map.
2. Plan said "collected count 1135" (note 5) — stale literal; the live capture (2230 full /
   1142 test_lazy_core) was the receipt baseline, per the Phase-3 precedent.
3. ONE analyzer misclassification caught before any battery: the seam analyzer's naive Name-load
   scan flagged `build_hardening_emit_command`'s `registry_summary` PARAMETER as a monolith-global
   reference; the injected deferred import shadowed the parameter (caught by 2 red tests in the
   WU-2 seam smoke). Fixed by symtable-auditing ALL 20 Phase-4 deferred injections (19 genuine
   globals, 1 removed). Lesson for Phase 5: symtable-audit deferred-import targets BEFORE apply.
4. `harness-gate.py --staged` flagged the WU-1 diff in-scope (overfit flag + tautology flag +
   complexity declaration-required; gate_weakening PASS) — GATE_VERDICT.md extended with a
   Phase-4 entry covering all four identically-shaped seam commits (risk note d).
5. Executed inline by the phase-execution agent with scripted transforms (scratchpad
   seam_move.py: AST block map -> verbatim run slices -> header + deferred-import injection ->
   recomputed import-backs -> facade-map append -> per-module unresolved-globals scan via
   symtable) + per-commit difflib verbatim receipts (every seam byte-identical to its slice
   modulo ONLY the enumerated sanctioned insertions) — no hand-retyped bodies (plan note 3).
6. WU-4's plan-anticipated "update the collectors' matched token patterns" turned out to be a
   no-op for collector CODE (the chain matcher is submodule-agnostic by design since Phase 1);
   only comments/docstrings/negative-fixture strings carried the old tokens and were rewritten
   in lockstep with the real patch sites.

**Files modified (net, Phase 4):**
- `user/scripts/lazy_core/{gates,ledgers,dispatch,runtimeplane}.py` (new seam modules)
- `user/scripts/lazy_core/{__init__,_monolith}.py` (facade map +224 entries; pure seam deletions
  + import-backs 6/10/8/0)
- `user/scripts/lazy_core/hostcaps.py` (probe-primitive deferred import re-pointed)
- `user/scripts/tests/test_lazy_core/{test_gates,test_ledgers,test_misc,test_dispatch,
  test_markers,_util,test_runtimeplane}.py` (mechanism-3 redirects: 2 + 37 + 32 + 63 lines)
- `docs/features/lazy-core-package-decomposition/GATE_VERDICT.md` (Phase-4 entry)
- plan part 4 (WU ticks + status Complete), `PHASES.md` (P4 row + heading), this file

## Phase 5 — Marker plane + pseudo; `_monolith` deleted

#### Implementation Notes (Phase 5)
**Completed:** 2026-07-13 (plan part 5 of 6, `/execute-plan`, 4 WUs / 4 commits)
**Work completed:**
- WU-1 `markers.py` (commit a9e0581a): the run-marker / ownership / refusals / cycle-bracket
  plane — 56 names, 5 verbatim runs (3,305 monolith deletions -> 3,394-line module): run-marker
  lifecycle + born-owner-bound ownership plane, cycle markers + nonce resolution, C3 refusals
  (refuse_if_cycle_active / refuse_cycle_marker_mutation_if_subagent / refuse_run_start_clobber
  + CYCLE_REFUSED_OPS / SANCTIONED_STOP_TERMINAL), RUN_CONTINUITY/FRESH partition + checkpoints,
  budget counters (advance_* / fold / per-feature guard + budget_trip_signals /
  feature_is_near_complete), cycle-bracket friction detector, repeat counters, resolution signal,
  audit obligations. Import-back 1 (refuse_if_cycle_active, apply_pseudo's gate — retired at
  WU-2). Monolith sibling import-backs recomputed: 34 now-unused names pruned (_DIAGNOSTICS
  deliberately kept — test identity pins scheduled to WU-4). Deferred re-points: ledgers x7 +
  dispatch x4 + hostcaps x1 marker-plane imports -> `.markers` (the two combined
  `REGISTRY_ENTRY_TTL_SECONDS, read_run_marker` lines split — the constant stayed
  monolith-resident until WU-3). Redirects: bind_marker_session x7, _CYCLE_COMMIT_MULTI x2
  (the Phase-4 deliberate keep — consumer detect_cycle_bracket_friction moved here, so the
  reads re-pointed per the L1 mechanism-3 rule). **D4 hook cut completed at this WU:** a
  `read_run_marker` facade touch no longer loads `_monolith` (markers' top-level imports are
  _ctx/statedir/docmodel/gates/ledgers/dispatch — none reach the monolith).
- WU-2 `pseudo.py` (commit 4bd51536): ONE contiguous 1,576-line verbatim slice
  (_resolve_under_repo + ROADMAP strike helpers + _completion_postconditions_missing +
  apply_pseudo — the roadmap helpers' only consumers are pseudo-internal, so the contiguous
  867-2444 run moved whole). **apply_pseudo INTACT receipt:** all 6 moved defs BYTE-IDENTICAL
  to their HEAD monolith blocks (string-equality receipt; apply_pseudo = 1,354 lines,
  zero internal edits — only the module import header added). Import-back ZERO; the WU-1
  refuse_if_cycle_active import-back + gates/ledgers blocks + 5 stdlib imports + stale_binary
  pruned from the monolith (recomputed).
- WU-3 residue sweep (commit 147fd912): every remaining name (71 names / 90 blocks) distributed
  in ONE scripted multi-slice pass. **Per-symbol placement decisions (recorded per plan):**
  `_die` -> `_ctx` (kernel; depdag/docmodel/markers re-point); queue-mutation ops
  (reorder_queue/clear_queue_stub) + merged ordering plane (merged_priority/merged_worklist/
  next_merged + severity/age/pin helpers) + skip_ahead_ready -> `depdag` (queue plane, sync_deps
  proximity); receipt writers + validation_escalation + archive_fixed + the gate-coverage plane
  (_parse_locked_decisions/gate_coverage) -> `gates` (completion write-path); stale-upstream +
  materialized + WIP/stage tracking (derive_stage/track_*) + decision records +
  build_input_audit_emit_command (sibling of build_hardening_emit_command) -> `ledgers`;
  sentinel lifecycle (detect_noncanonical_blocker/neutralize_sentinel/provisional_*) +
  independent-marker parse -> `docmodel`; git helpers (_git/_current_head/git_head_short_sha/
  git_guard_status) + self-edit detection (GOVERNING_FILE_SET/self_edit_mode/
  governing_files_touched) -> `runtimeplane` (plan rule: git helpers); cycle-header formatter
  (SUB_SKILL_STEP_NAMES/format_cycle_header) + registry constants (REGISTRY_ENTRY_TTL_SECONDS/
  _REGISTRY_RING_CAP) -> `dispatch`; write_deferred_requires_host -> `hostcaps` (completes the
  host plane). The orphan `_COMPILE_WENT_DEAD` trailing-docstring Expr (stranded when Phase 4
  moved its constant) re-homed under the constant in runtimeplane. **`# Phase-5 re-point`
  closure: ZERO remain** — all 24 deferred sites re-pointed to final homes; 2 genuine-cycle
  function-local imports RECORDED: docmodel.provisionalize_sentinel -> runtimeplane._current_head
  (runtimeplane imports docmodel top-level) and gates' provenance-derivation trio -> .ledgers
  (ledgers imports gates top-level, new edge). New top-level edges gates->runtimeplane,
  ledgers->gates, depdag->gates — final import DAG verified acyclic; package-wide symtable
  unresolved-globals audit CLEAN. `_monolith.py` reduced to a 13-line shell kept ONLY for the
  WU-4 test identity pins.
- WU-4 (this commit): TDD pin `test_facade_map_total_and_collision_free` written + verified RED
  first (failed on `_FALLBACK_SUBMODULE` present), GREEN post-deletion — asserts fallback retired,
  `lazy_core._monolith` unimportable, every mapped module imports + every mapped name resolves,
  definition-site uniqueness across submodules (AST), bogus getattr raises clean AttributeError.
  Facade made EXPLICIT-TOTAL by scripted AST generation: 480 existing entries verified
  definition-true, ZERO cross-module definition collisions, 6 missing `_ctx` accessor names added
  (486 total); `_FALLBACK_SUBMODULE` + fallback branch deleted; `_ALL_SUBMODULES` = the 12 seams;
  `__dir__` rewritten off the fallback module. `git rm _monolith.py`. Test-surface cleanup:
  kernel `_atomic_write` x3 + `_DIAGNOSTICS` x7 identity pins -> `lazy_core._ctx` (the owner);
  the `test_hook_surface_imports_without_monolith` pin STRENGTHENED (was `_monolith not in
  sys.modules` — vacuous post-deletion; now asserts loaded lazy_core modules within {facade, _ctx,
  statedir}); canary/control-surface fixture paths retargeted `_monolith.py` -> `markers.py`
  (same glob semantics); stale present-tense "monolith-resident" docstrings across all 12
  modules + 7 test files updated in lockstep (prose only, no assertion weakened).

**Receipts (per-commit invariant battery, all 4 commits):** pytest `user/scripts/` green
(2230 passed WU-1..3; 2231 on WU-4 — the +1 sanctioned TDD pin); `lazy-state.py --test` +
`bug-state.py --test` byte-pinned baselines pass with ZERO baseline regeneration
(`tests/baselines/` untouched all phase); `lazy_parity_audit.py` exit 0; `cli_surface_gen.py
--check` OK; `doc-drift-lint.py` 0 findings; `lint-skills.py` OK. Collect-only bare-name
multiset diff EMPTY per WU-1..3 commit (2230 == 2230); WU-4 diff = exactly the one addition.

**Benchmark census (2026-07-13, post-deletion):** `_monolith.py` GONE (7,858 -> 0). Final
roster (13 files incl. facade): __init__ 584 / _ctx 113 / depdag 1,049 / dispatch 2,005 /
docmodel 2,445 / gates 2,352 / hostcaps 503 / ledgers 3,921 / markers 3,393 / notifyplane 585 /
pseudo 1,654 / runtimeplane 2,595 / statedir 295 — **`over_4k_ceiling: []`** (largest = ledgers
3,921; the WU-3 placement deliberately routed audit obligations to markers to keep ledgers under
the ceiling). Cold `import lazy_core` best 36.73 / median 37.26 ms (Phase-2 band preserved).
Hook surface best **43.28 / median 44.59 ms** vs Phase-2's 42.64/43.98 — same band, but the
claim is now STRUCTURAL: `monolith_loaded_samples=0` is guaranteed by deletion, and the
strengthened statedir pin proves the hook probe loads ONLY facade+_ctx+statedir. HONEST caveat
unchanged: the <15 ms KPI aspiration is NOT met (interpreter+facade baseline ~32 ms dominates);
the guard marker paths' residual monolith load noted at Phase 2 is eliminated by construction.

**Deviations & findings (for the retro):**
1. Executed inline by the phase-execution agent with scripted transforms (Phase-4 precedent,
   recorded deviation from the orchestrator+Sonnet-subagent contract): block_map/analyze ->
   name-driven seam_move.py (Phase-4 tool reused) -> residue_move.py (append-capable variant) ->
   per-edit exact-count replacements -> package-wide symtable audit -> byte-equality receipts.
   Task tools unavailable; plan WU checkboxes + PHASES.md were the persistent ledger.
2. `harness-gate.py --staged` flagged every Phase-5 commit in-scope; WU-1/WU-2 additionally
   tripped **gate_weakening: hit** (refuse_* construct "removals" from _monolith + sanction-set
   "adds" in markers.py — the two sides of a byte-verbatim move diff). Recorded in GATE_VERDICT.md
   Phase-5 entry with the move receipts; the D4 operator sign-off obligation is surfaced via
   NEEDS_INPUT_PROVISIONAL.md (park-provisional — run never halted). WU-3/WU-4 gate_weakening: pass.
3. The plan's WU-1 redirect prediction ("consume_nonce(2), bind_marker_session(2)") was stale:
   consume_nonce moved to dispatch in Phase 4; live redirect surface was bind_marker_session x7 +
   _CYCLE_COMMIT_MULTI x2. Plan literals re-derived from disk per the standing instruction.
4. The Phase-4 symtable-audit lesson applied: every deferred injection audited; zero
   parameter-shadow collisions this phase (the WU-2 pseudo header needed one iteration — the
   facade-attribute `docmodel.<name>` rewrites inside apply_pseudo required `from . import
   docmodel`, caught by the tool's unresolved-globals FATAL before any battery).
5. Monolith import-back recomputation after each WU pruned 30+ dead imports per commit rather
   than letting them ride to WU-4 — kept every intermediate tree honest (no unused-import debt).
6. `benchmark_lazy_core_import.py` was NOT edited (outside the plan's file-set): its
   `monolith_loaded_samples` probe now trivially reports 0 (the module no longer exists) and its
   module docstring's "guard marker paths still load _monolith" caveat is stale — a 2-line
   prose cleanup for Phase 6 / a hardening round.

**Files modified (net, Phase 5):**
- `user/scripts/lazy_core/markers.py`, `user/scripts/lazy_core/pseudo.py` (new seam modules)
- `user/scripts/lazy_core/_monolith.py` (DELETED)
- `user/scripts/lazy_core/{__init__,_ctx,depdag,dispatch,docmodel,gates,hostcaps,ledgers,notifyplane,runtimeplane,statedir}.py` (residue appends, import re-points, facade explicit-total)
- `user/scripts/tests/test_lazy_core/{test_markers,test_misc,test_ledgers,test_gates,test_notifyplane,test_statedir,test_runtimeplane}.py` (mechanism-3 redirects + WU-4 pin + prose lockstep)
- `user/scripts/CLAUDE.md` (lazy_core row -> 12-seam roster), `docs/features/lazy-core-package-decomposition/{PHASES.md,GATE_VERDICT.md,NEEDS_INPUT_PROVISIONAL.md}`, plan part 5 (WU ticks + status Complete), this file
