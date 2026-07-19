# Implementation Phases — Shared Hook Library

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri+MCP dev runtime; the entire deliverable is hook/script harness infrastructure (sourced bash + an imported python module + KPI tooling) with no app integration and no MCP-reachable surface (the "build tooling / no app integration" untestable class per docs/features/mcp-testing/SPEC.md). Verification is the in-repo pipe-test / unit-test suite (`python user/scripts/test_hooks.py`, a new `test_hook_lib.py`, `kpi-scorecard.py --lint`), runnable in-session by the implementation agent — NOT a deferred runtime gate.

## Touchpoint Audit

Verified against the live tree 2026-07-18 (two parallel `Explore` agents + inline grep). Every planned path is `exists: yes` or `net-new`.

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/hooks/hook-prelude.sh` | **NO (net-new)** | — | create | Sourced (never executed) bash prelude; fail-open at the source site. |
| `user/scripts/hook_lib.py` | **NO (net-new)** | — | create | Imported python module; sits beside `lazy_core/` so `*_SCRIPTS_DIR` threading resolves it with zero new plumbing. |
| `user/hooks/lazy-dispatch-guard.sh` | yes | python3→python resolution + SELF/SCRIPT_DIR derivation only (NO inline emitter/anchor scaffolding) | refactor | Phase-1 first consumer of the prelude (thin wrapper). |
| `user/hooks/lazy-route-inject.sh` | yes | python3→python resolution + SELF/SCRIPT_DIR derivation only | refactor | Phase-1 second consumer of the prelude (thin wrapper). |
| `user/hooks/block-noncanonical-blocker-write.sh` | yes | `_allow`/`_deny`/`_append_hook_event` + `_breadcrumb` present; NO `_ENV_PREFIX`/`_CMD_START` | refactor | Phase-3 migration #1 (lowest blast radius, D3 order). |
| `user/hooks/block-sentinel-write-on-stray-branch.sh` | yes | `_allow`/`_deny`/`_append_hook_event` + `_breadcrumb` present; NO anchors | refactor | Phase-3 migration #2. |
| `user/hooks/long-build-ownership-guard.sh` | yes | full scaffolding: emitters, `_append_hook_event`, `_breadcrumb`, `_ENV_PREFIX`/`_CMD_START` @ **lines 153/161** | refactor | Phase-3 migration #3; collapse anchor pair into `hook_lib.ENV_PREFIX`/`CMD_START`. |
| `user/hooks/build-queue-enforce.sh` | yes | full scaffolding; `_ENV_PREFIX`/`_CMD_START` @ **lines 211/217** | refactor | Phase-3 migration #4. |
| `user/hooks/lazy-cycle-containment.sh` | yes | full scaffolding; `_ENV_PREFIX`/`_CMD_START` @ **lines 263/269** | refactor | Phase-3 migration #5 (highest blast radius, last). |
| `user/scripts/lazy_core/statedir.py` | yes | `append_hook_event(kind, hook, signature, detail, repo_root=None, now=None) -> bool` @ line 228; `repo_key` @ 88; `claude_state_dir` @ 159 | reuse (read-only) | `hook_lib.append_hook_event` LAZILY delegates to `lazy_core.append_hook_event` (re-exported by the package's PEP-562 facade) when importable; mirrors this signature. Do NOT edit. |
| `user/scripts/test_hooks.py` | yes | pipe-test harness `_run_bash(script, stdin_text, env)` @ line 273; ~273 test defs | extend | Add new pipe-tests (missing-prelude-allows, no-python-leaves-event-line, hook_lib-import-failure-allows); re-run full suite after each Phase-3 migration. |
| `user/scripts/test_hook_lib.py` | **NO (net-new)** | — | create | Phase-2 unit tests incl. the import-light guard. |
| `user/scripts/kpi-scorecard.py` | yes | `_SOURCES` frozenset-map @ line 75 (no `repo-static-scan` source); selector dispatch `_sel_*` (e.g. `_sel_telemetry` @ 843) | extend | Phase-4: add `repo-static-scan` source + `hook-duplicated-line-count` selector + a deterministic counter. |
| `docs/kpi/registry.json` | yes | `{schema_version, kpis:[...]}`; no `hook-plane-duplicated-lines` row | extend | Phase-4: append the drafted row (currently a non-claiming fence in the SPEC's KPI Declaration). |
| `user/scripts/test_kpi_scorecard.py` | yes | existing suite | extend | Phase-4: cover the new source/selector + counter. |

**Anchor-grade drift corrected in-plan (mechanical, non-halting):** (1) the SPEC Executive-Summary anchor lines for `_ENV_PREFIX`/`_CMD_START` (~113-116 / ~140-141 / ~195-196) are stale — actual lines are 153/161, 211/217, 263/269 (files grew). (2) `lazy_core` is a **package** (`lazy_core/statedir.py`), not a flat `lazy_core.py`; the package facade re-exports `append_hook_event`, so the SPEC's D1 "delegating to `lazy_core.append_hook_event`" holds unchanged. (3) `test_hooks.py` now carries ~273 test defs, not the SPEC's 2026-07-11 snapshot of 157 — the byte-identical-output proof mechanism is unchanged; use the live count. No premise-grade contradiction surfaced; the SPEC's design (D1–D4) stands verbatim.

## Validated Assumptions

Per the Step 2.7 runtime-assumption gate. This feature has **no user-facing product surface** (hooks are PreToolUse infrastructure, not a user-reachable feature), so the reachability axiom does not apply. The one load-bearing runtime-coupled assumption — **"migration preserves each hook's deny/allow output byte-for-byte"** — is validated per phase by the `test_hooks.py` pipe-test suite, which drives each hook as a real subprocess (stdin PreToolUse payload → asserted stdout deny/allow JSON). This is genuine runtime observation of the real component, distributed per phase (not a terminal-only gate), so the assumption never rides unverified into a later phase.

- **Open Question 1 (event-writer `ts` width) — RESOLVED:** `lazy_core.append_hook_event` records `ts` as an **epoch float**; `incident-scan.py` reads it as a float. A pure-bash `date +%s` integer-seconds `ts` parses as an int and compares correctly against float windows, so **integer-second granularity is sufficient** — no widening needed. Phase 1 emits `date +%s` and its pipe-test asserts the written line parses as JSON with a numeric `ts`.
- **Open Question 2 (legacy `TOOL_INPUT` trio migration ownership) — HONORING SPEC DEFAULT:** the SPEC locks "the bug owns the behavior change, this feature owns the substrate." Scope is therefore the SPEC's enumerated **seven** python-bearing hooks (2 thin wrappers in Phase 1 + 5 enforcement hooks in Phase 3); the now-stdin-migrated `block-terminal-kill.sh` / `block-work-repo-git-push.sh` are OUT of this feature's migration scope and adopt the prelude/`hook_lib` later under their own item. Not a descope — a SPEC-locked boundary.
- **Open Question 3 (git-bash source cost) — implementation-time confirm:** the prelude adds one `source` per hook invocation; expected microseconds against the 5s hook timeout. Phase 1 confirms the full pipe-test suite wall-time does not regress meaningfully.

---

### Phase 1: `hook-prelude.sh` + pure-bash no-python fallback (wire the two thin wrappers)

**Scope:** Author `user/hooks/hook-prelude.sh` — a sourced (never executed), fail-open-guarded bash prelude providing `HOOK_PYTHON` (python3→python resolution), `HOOK_SCRIPTS_DIR` (SELF-normalized, builtins-only SCRIPT_DIR derivation), and `hook_emit_error_event()` (a pure-bash `hook-events.jsonl` + `hook-error.json` writer — printf/date only, best-effort, no python needed). Wire it into the two thin prelude-only wrappers (`lazy-dispatch-guard.sh`, `lazy-route-inject.sh`) as first consumers via `. "$…/hook-prelude.sh" 2>/dev/null || exit 0`. Lands the `guard-fail-open-leaves-no-trace` fix-scope §1 (a no-python error path that leaves a trace) as a side effect.

**Status:** ✅ Complete (2026-07-18)

**Deliverables:**
- [x] `user/hooks/hook-prelude.sh` — `HOOK_PYTHON` resolution (`command -v python3` → `command -v python` → fallback breadcrumb + `exit 0`), `HOOK_SCRIPTS_DIR` derivation (backslash-normalize, builtins-only), `hook_emit_error_event(hook, signature, detail)` pure-bash JSONL append (integer `date +%s` `ts`, `kind:"error"`) + single-line `hook-error.json` overwrite, all best-effort/fail-open.
- [x] `user/hooks/lazy-dispatch-guard.sh` — source the prelude fail-open-guarded; replace its inline python-resolution + SCRIPT_DIR derivation with `HOOK_PYTHON` / `HOOK_SCRIPTS_DIR`. Deny/allow behavior byte-identical.
- [x] `user/hooks/lazy-route-inject.sh` — same prelude wiring; behavior byte-identical.
- [x] Tests: new pipe-tests in `test_hooks.py` — (a) sourcing a renamed-away prelude still `exit 0` allows; (b) a stripped-`PATH` no-python run leaves one bash-written `kind:"error"` line in `hook-events.jsonl`; (c) both wrappers' existing deny/allow pipe-tests still pass unchanged.

**Minimum Verifiable Behavior:** `python user/scripts/test_hooks.py` passes (all existing + the 3 new prelude pipe-tests); the no-python test asserts a JSON-parseable event line with a numeric `ts` is written; the missing-prelude test asserts exit 0 with no output.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/hooks/hook-prelude.sh` — net-new sourced prelude.
- `user/hooks/lazy-dispatch-guard.sh` — first consumer (refactor: python-resolution + SCRIPT_DIR → prelude).
- `user/hooks/lazy-route-inject.sh` — second consumer.
- `user/scripts/test_hooks.py` — new prelude pipe-tests.

**Testing Strategy:** Pipe-test the two wrappers before/after wiring — deny/allow stdout must be byte-identical. Add dedicated prelude pipe-tests (missing prelude → allow; no-python → traced allow). The full suite is the regression net; a passing suite IS the no-behavior-change proof.

**Integration Notes for Next Phase:**
- The prelude owns the BASH-side fail-open contract (missing prelude, no python). Phase 2's `hook_lib.py` owns the PYTHON-side contract (import-failed → minimal inline allow + a prelude-written trace).
- `HOOK_SCRIPTS_DIR` is the `sys.path` seed the Phase-3 hooks pass to `import hook_lib` — establish its exact derivation here so Phase 3 reuses it verbatim.
- `hook_emit_error_event` emits integer-second `ts` (Open Question 1 resolved); keep it float-compatible for `incident-scan.py`.

**Implementation Notes (2026-07-18):**
- Authored `user/hooks/hook-prelude.sh` (sourced, never executed). Provides `HOOK_NAME` (basename of `$0` sans `.sh` — `$0` is preserved across `source`, so the prelude derives the CONSUMING hook's identity for the breadcrumb without the consumer setting anything), `hook_emit_error_event(hook, signature, detail)` (pure-bash `hook-error.json` overwrite + one `hook-events.jsonl` `{"ts":<int>,"kind":"error",...}` line, honoring `LAZY_STATE_DIR`; every write `2>/dev/null || true`), `HOOK_PYTHON` (`python3`→`python`→ breadcrumb + `exit 0` — the `exit 0` in a sourced file exits the consuming hook), and `HOOK_SCRIPTS_DIR` (`$_HOOK_PRELUDE_DIR/../scripts`).
- **Irreducible bootstrap stays in each consumer:** to LOCATE the prelude, each hook derives its own dir (`SELF="${0//\\//}"` + `cd`/`pwd`) then `. "$_HOOK_DIR/hook-prelude.sh" 2>/dev/null || exit 0` (SPEC D2). This ~7-line bootstrap is not dedup-able (you can't source a file without knowing where it is); the win is the ~24-line inline no-python block + python-resolution moving into the prelude. `HOOK_SCRIPTS_DIR` is `.../hooks/../scripts` (a `..`-bearing but fully-usable path, valid both as an interpreter-path prefix and, in Phase 3, as a `sys.path` seed).
- Both wrappers (`lazy-dispatch-guard.sh`, `lazy-route-inject.sh`) now consume `$HOOK_PYTHON` / `$HOOK_SCRIPTS_DIR`; `$PYTHON`/`$SCRIPT_DIR` deleted. Behavior byte-identical — proven by the full 261 pre-existing `test_hooks.py` pipe-tests staying green, incl. the no-python sweep (the prelude's breadcrumb uses `HOOK_NAME` = the consumer's stem, so `hook == hook_sh.stem` still holds).
- **Gate:** `python user/scripts/test_hooks.py` → **265/265 passed** (261 existing + 4 new: `test_prelude_file_exists`, `test_wrappers_source_prelude_and_drop_inline_python_resolution`, `test_missing_prelude_source_fails_open_allows`, `test_prelude_no_python_leaves_numeric_ts_event`).

---

### Phase 2: `hook_lib.py` (emitters, appender, breadcrumb, anchor constants)

**Scope:** Author `user/scripts/hook_lib.py` — the imported python substrate. Provides `allow()` / `deny(reason)` JSON emitters, `append_hook_event(kind, hook, signature, detail, repo_root=None)` (lazily delegating to `lazy_core.append_hook_event` when importable, with the current per-hook inline fallback branch collapsed to live here ONCE), `breadcrumb(hook, err)` (chaining into `append_hook_event("error", …)`), and the shared anchor constants `ENV_PREFIX` / `CMD_START` (single source for the pair triplicated across three hooks). **Import-light discipline (D4):** stdlib only at module top; `import lazy_core` deferred lazily inside `append_hook_event`. `hook_lib` import must never read stdin.

**Status:** ✅ Complete (2026-07-18)

**Deliverables:**
- [x] `user/scripts/hook_lib.py` — `allow()`, `deny(reason)`, `append_hook_event(...)` (lazy `lazy_core` delegation + inline JSONL fallback), `breadcrumb(hook, err)`, `ENV_PREFIX` / `CMD_START` module constants, plus the shared path-prefix helper idiom.
- [x] Tests: `user/scripts/test_hook_lib.py` — unit tests for each emitter/appender/breadcrumb (assert JSON shape + fail-open on write error) AND the **import-light guard**: a subprocess `import hook_lib` MUST NOT have imported `lazy_core` (assert `"lazy_core" not in sys.modules` after `import hook_lib`).

**Minimum Verifiable Behavior:** `python user/scripts/test_hook_lib.py` passes, including the import-light guard proving `import hook_lib` does not pull `lazy_core` into `sys.modules`.

**Prerequisites:**
- Phase 1: `HOOK_SCRIPTS_DIR` derivation established (the `sys.path` seed the hooks will use to reach `hook_lib`).

**Files likely modified:**
- `user/scripts/hook_lib.py` — net-new module.
- `user/scripts/test_hook_lib.py` — net-new unit suite.

**Testing Strategy:** Pure unit tests (no hook subprocess yet — that's Phase 3). Assert emitter JSON byte-shape matches what the hooks currently produce (so Phase 3 migrations stay byte-identical). The import-light guard is load-bearing per D4's per-invocation latency constraint.

**Integration Notes for Next Phase:**
- `append_hook_event`'s inline fallback branch now lives ONCE here; Phase 3 hooks retain only a MINIMAL `except ImportError: sys.exit(0)` guard (a few lines), not the ~40-line per-hook copy.
- `ENV_PREFIX` / `CMD_START` here are the single source; Phase 3 deletes the three inline copies and imports these. Coordinate the anchor SEMANTICS with the archived `long-build-and-build-queue-matcher-bypasses` bug so the matcher-semantics live in one place.
- Mirror `lazy_core.append_hook_event`'s signature exactly (`kind, hook, signature, detail, repo_root=None`) so the delegation is a pass-through.

**Implementation Notes (2026-07-18):**
- Authored `user/scripts/hook_lib.py` (import-light: only `datetime`/`json`/`os`/`sys`/`time` at module top; `lazy_core` imported LAZILY inside `append_hook_event`, seeding its own dir onto `sys.path` first). `allow()`/`deny(reason)` are byte-identical to the enforcement hooks' `_allow`/`_deny` (deny shape asserted byte-exact via `json.dumps` insertion order). `append_hook_event(kind, hook, signature, detail, repo_root=None)` delegates to `lazy_core.append_hook_event` (binding the active repo when `repo_root` given), inline base-dir fallback otherwise; returns bool, never raises. `breadcrumb(hook, err)` writes `hook-error.json` + chains one `append_hook_event("error", ...)` line. `ENV_PREFIX`/`CMD_START`/`PATH_PREFIX` copied BYTE-IDENTICALLY from `long-build-ownership-guard.sh` so Phase 3's anchor collapse is a pure de-dup.
- **Import-light guard (D4) proven:** `test_import_hook_lib_does_not_import_lazy_core` runs a fresh subprocess `import hook_lib` and asserts `"lazy_core" not in sys.modules` — the per-invocation `lazy_core` import cost (~95 ms warm) never lands at hook-import time.
- **Gate:** `python user/scripts/test_hook_lib.py` → **7/7 passed** (constants incl. PATH_PREFIX; allow/deny exact shape via subprocess; append writes-line + returns-False-on-write-error; breadcrumb writes + chains; import-light guard). Also pytest-collectable (`pytest user/scripts/test_hook_lib.py` → 7 passed).
- **Phase 3 is NOT touched** (out of this plan part — parts 2/3). The five enforcement hooks still carry their inline copies; they migrate onto `hook_lib` + the prelude in Phase 3.

> **Repo invariant-battery note (PRE-EXISTING, unrelated to this feature):** `gate-battery.py`
> reports `RESULT=FAIL` on the `pytest` gate, but the SOLE failure is
> `test_kpi_scorecard.py:142` (`assert len(registry["kpis"]) == 21` — the committed
> `docs/kpi/registry.json` has 22 rows; the 22nd, `subagent-wedge-strand-recurrence`, was
> seeded by commit `d6e9465e` BEFORE this session). shared-hook-lib touches no KPI file; the
> battery was already red at the tree this part started from. Its own two gates
> (`test_hooks.py` 265/265, `test_hook_lib.py` 7/7) are fully green. Reported to the
> orchestrator for a harden-harness spin-off (stale hardcoded count → 22 + add the new id).

---

### Phase 3: Migrate the five inline-Python enforcement hooks (one per step)

**Status:** ✅ Complete (2026-07-18)

**Scope:** Migrate each of the five inline-Python enforcement hooks onto the prelude (`source` + `HOOK_PYTHON`/`HOOK_SCRIPTS_DIR`) and `hook_lib` (`import hook_lib` seeded from `HOOK_SCRIPTS_DIR`), in D3 lowest-blast-radius-first order. Each hook drops its inline `_allow`/`_deny`/`_append_hook_event`/`_breadcrumb` copies and (for the three anchor-bearing hooks) its `_ENV_PREFIX`/`_CMD_START` definitions, retaining only a minimal `except ImportError: sys.exit(0)` fallback. **Full `python user/scripts/test_hooks.py` after EACH single-hook migration** — the pipe-tests assert deny/allow output byte-identically, which is the no-behavior-change proof; a regression is attributable to exactly one hook.

**Deliverables:**
- [x] Migrate `user/hooks/block-noncanonical-blocker-write.sh` (#1) → prelude + `hook_lib`; full suite green.
- [x] Migrate `user/hooks/block-sentinel-write-on-stray-branch.sh` (#2) → prelude + `hook_lib`; full suite green.
- [x] Migrate `user/hooks/long-build-ownership-guard.sh` (#3) → prelude + `hook_lib`; collapse `_ENV_PREFIX`/`_CMD_START` (lines 153/161) into `hook_lib.ENV_PREFIX`/`CMD_START`; full suite green.
- [x] Migrate `user/hooks/build-queue-enforce.sh` (#4) → prelude + `hook_lib`; collapse anchors (lines 211/217); full suite green.
- [x] Migrate `user/hooks/lazy-cycle-containment.sh` (#5, highest blast radius) → prelude + `hook_lib`; collapse anchors (lines 263/269); full suite green.
- [x] Tests: extend `test_hooks.py` with the D2 import-failure pipe-test (`HOOK_SCRIPTS_DIR` pointed at an empty dir → `import hook_lib` fails → hook still allows + leaves a prelude-side trace) for at least one migrated enforcement hook.

**Minimum Verifiable Behavior:** After each migration, `python user/scripts/test_hooks.py` reports the full suite passing (~273 tests) with deny/allow output byte-identical to the pre-migration baseline; the new import-failure pipe-test asserts fail-open + a traced allow.

**Prerequisites:**
- Phase 1: `hook-prelude.sh` exists and is proven fail-open.
- Phase 2: `hook_lib.py` exists with emitters, appender, breadcrumb, and `ENV_PREFIX`/`CMD_START`; import-light.

**Files likely modified:**
- `user/hooks/block-noncanonical-blocker-write.sh`, `user/hooks/block-sentinel-write-on-stray-branch.sh`, `user/hooks/long-build-ownership-guard.sh`, `user/hooks/build-queue-enforce.sh`, `user/hooks/lazy-cycle-containment.sh` — one migration per WU (do NOT batch two into one step; the per-hook full-suite gate is the isolation mechanism).
- `user/scripts/test_hooks.py` — the import-failure pipe-test.

**Testing Strategy:** Single-hook-at-a-time migration with a full-suite gate between each — the pipe-tests' byte-identical deny/allow assertion is the behavior-preservation proof. The `_ENV_PREFIX`/`_CMD_START` collapse is the highest-risk change (matcher semantics); its regression surface is exactly the segment-anchoring pipe-tests already in the suite.

**Integration Notes for Next Phase:**
- After Phase 3, `grep` inventory should show `_append_hook_event` / `_breadcrumb` / the anchor pair each defined ONCE (in `hook_lib.py`) — this is the input to Phase 4's duplicated-line counter.
- The anchor-semantics collapse coordinates with the archived `long-build-and-build-queue-matcher-bypasses` bug: the matcher fix now lands in one place (`hook_lib.CMD_START`).
- The `block-terminal-kill` / `block-work-repo-git-push` stdin hooks are deliberately NOT migrated (Open Question 2 — owned by `legacy-tool-input-env-hooks-dead`).

**Implementation Notes (2026-07-18, plan part 2):**
- All 5 enforcement hooks migrated in D3 order (WU-1..5), full `test_hooks.py` suite green after EACH single-hook migration (byte-identical deny/allow = the no-behavior-change proof). Final suite: **266/266** (was 265 + the new import-failure pipe-test).
- Each hook now: sources `hook-prelude.sh` (fail-open-guarded) for `HOOK_PYTHON`/`HOOK_SCRIPTS_DIR`/`HOOK_NAME`/`hook_emit_error_event`; imports `hook_lib` (seeded from `HOOK_SCRIPTS_DIR`) for `allow`/`deny`/`append_hook_event`/`breadcrumb`; retains only a minimal `except ImportError: sys.exit(0)`. The inline `_allow`/`_deny`/`_append_hook_event`/`_breadcrumb` copies and the anchor triplication are GONE — verified by grep (defined ONCE in `hook_lib.py`).
- Anchor collapse: WU-3/4/5 consume `hook_lib.ENV_PREFIX`/`CMD_START` (and, for full de-duplication, `hook_lib.PATH_PREFIX`); WU-4 also collapsed its second `_ENV_PREFIX_ANY` copy, retiring the "keep the two env-prefix literals in lockstep" burden. `_normalize_ps_syntax` / `_mask_heredoc` / `COMMAND_TOOL_NAMES` stay hook-local (not provided by `hook_lib`).
- **D2 trace on shared-module-unavailable (uniform across all 5):** a bash `[ -f "$HOOK_SCRIPTS_DIR/hook_lib.py" ]` guard after the prelude source calls `hook_emit_error_event` and fails open when `hook_lib.py` is absent — restoring the "leave a trace even when the shared module is unavailable" property the pre-migration inline `lazy_core` fallback carried. The Python `except ImportError: sys.exit(0)` stays the silent last-resort for a present-but-unimportable `hook_lib`. New pipe-test `test_containment_hook_lib_unavailable_fails_open_with_trace` asserts this (allow + traced), and a red-check confirmed the guard is load-bearing (no trace without it).
- `lazy-cycle-containment.sh` keeps ONE direct `import lazy_core` in `_resolve_marker_path` (for `claude_state_dir` — `hook_lib` deliberately does not re-export it); the `build-queue-enforce.sh` / `lazy-cycle-containment.sh` temp-file invocation (windows-32k E2BIG fix) is preserved, with its temp-write-failed breadcrumb folded onto the prelude's `hook_emit_error_event`.
- `block-terminal-kill.sh` retains its own `_CMD_START` copy (out of scope — not one of the 5; see the note above).

---

### Phase 4: KPI wiring (register the static-scan source + counter; promote the drafted row)

**Scope:** Register the `repo-static-scan` signal source and `hook-duplicated-line-count` selector in `kpi-scorecard.py`'s `_SOURCES` map plus a deterministic counter (a static scan of `user/hooks/` that counts the remaining duplicated scaffolding lines), and move the SPEC's drafted `hook-plane-duplicated-lines` row from its non-claiming fence into `docs/kpi/registry.json`. Follows the `canary-trip-precision` / `session-log-mining` precedent (register the selector alongside the feature so the drafted row becomes claimable). Re-run `kpi-scorecard.py --lint` + `--lint --spec`.

**Deliverables:**
- [x] `user/scripts/kpi-scorecard.py` — add `"repo-static-scan": frozenset({"hook-duplicated-line-count"})` to `_SOURCES` (line ~75) + a `_sel_*` selector function computing the deterministic count (static scan of `user/hooks/`, honesty ladder: absent/unrecordable → NO-DATA, never a fabricated zero).
- [ ] `docs/kpi/registry.json` — append the `hook-plane-duplicated-lines` row verbatim from the SPEC's KPI Declaration (idempotent — do not duplicate an existing id).
- [x] Tests: extend `user/scripts/test_kpi_scorecard.py` — cover the new source/selector registration + the counter (deterministic count on a fixture tree; NO-DATA on an unrecordable input).
- **Completion (gate-owned):** the `__mark_complete__` gate flips SPEC.md `**Status:**` to Complete and writes `COMPLETED.md` once this phase lands — do NOT author a status-flip checkbox.

**Minimum Verifiable Behavior:** `python user/scripts/kpi-scorecard.py --lint` exits 0 (registry schema/enum valid with the new row + source); `python user/scripts/kpi-scorecard.py --lint --spec docs/features/shared-hook-lib/SPEC.md` exits 0 (the SPEC's `## KPI Declaration` now lints against a registered selector); `python user/scripts/test_kpi_scorecard.py` passes.

**Prerequisites:**
- Phase 3: duplication actually collapsed, so the counter measures a real post-migration number (the baseline was 467; the counter reports the remaining count).

**Files likely modified:**
- `user/scripts/kpi-scorecard.py` — `_SOURCES` entry + selector/counter.
- `docs/kpi/registry.json` — the promoted row.
- `user/scripts/test_kpi_scorecard.py` — coverage for the new source/selector.

**Testing Strategy:** Deterministic counter unit-tested against a fixture hook tree (known duplicated-line count). Registry `--lint` and the `--lint --spec` gate are the end-to-end proof that the drafted row is now live and claimable. No wall-clock in the scorecard render (byte-stable, per the script's existing contract).

**Integration Notes for Next Phase:** Terminal phase. Once landed, the drafted row in the SPEC's KPI Declaration is a live `docs/kpi/registry.json` row reachable by a future `--capture-baseline`. The existing `build-queue-raw-invocation-deny-recurrence` row's deferred hook-side-append signal is now un-blockable via `hook_lib.append_hook_event` (documented downstream beneficiary; not this feature's headline metric).
