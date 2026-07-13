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
