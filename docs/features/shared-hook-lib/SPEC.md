# Shared Hook Library — Feature Specification

> Extract the ~470 duplicated scaffolding lines (~20% of the 2,411-line `user/hooks/` plane)
> into a shared, fail-open-guarded pair — `hook-prelude.sh` (sourced bash: python resolution,
> SCRIPT_DIR derivation, no-python fallback breadcrumb) and `hook_lib.py` (allow/deny emitters,
> `_append_hook_event`, `_breadcrumb`, the shared `_ENV_PREFIX`/`_CMD_START` anchor regexes) —
> then migrate the seven python-bearing hooks one at a time, re-running the full 157-test
> `test_hooks.py` suite after each. Copy-drift in this scaffolding has already produced real
> bugs; a matcher-semantics change today must be hand-landed in three places.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-11
**Source:** repo-exploration proposal session 2026-07-11

**Friction-reduction feature:** yes

## Executive Summary

The 13 hooks in `user/hooks/` (2,411 lines total) share no code: every hook inlines its own
copy of the same scaffolding. Verified inventory (2026-07-11, grep-confirmed per file):

| Duplicated block | Copies | Where | Approx. lines |
|---|---|---|---|
| `_append_hook_event` (keyed lazy_core append + inline fallback) | ×5 | block-noncanonical, block-sentinel, build-queue-enforce, lazy-cycle-containment, long-build-ownership | ~40 each ≈ 200 |
| python3→python resolution (`command -v` chain) | ×7 | all python-bearing hooks | ~8 each ≈ 56 |
| `SELF`/SCRIPT_DIR derivation (backslash-normalize, builtins-only) | ×7 | same seven (evidence note: earlier count of 6 was low — grep finds 7) | ~7 each ≈ 49 |
| `_allow` / `_deny` JSON emitters | ×5 | the five inline-Python enforcement hooks | ~18 each ≈ 90 |
| `_breadcrumb` (hook-error.json writer) | ×3 | build-queue-enforce, lazy-cycle-containment, long-build-ownership | ~20 each ≈ 60 |
| `_ENV_PREFIX` / `_CMD_START` anchor regexes | ×3 | lazy-cycle-containment ~195-196, long-build-ownership ~113-116, build-queue-enforce ~140-141 | ~4 each ≈ 12 |

Total ≈ 467 duplicated lines — roughly a fifth of the plane. The cost is not aesthetic; the
drift class has a bug trail:

- `docs/bugs/guard-fail-open-leaves-no-trace/` — the `$STATE_DIR`-vs-`LCC_BASE_DIR`
  namespace drift inside lazy-cycle-containment's hand-rolled no-python breadcrumb (never
  worked), and the sentinel pair (`block-noncanonical-blocker-write.sh`,
  `block-sentinel-write-on-stray-branch.sh`) whose hand-copied scaffolding never gained the
  `_breadcrumb` tail their siblings have.
- `docs/bugs/legacy-tool-input-env-hooks-dead/` (authored in parallel, 2026-07-11) — the
  three `$TOOL_INPUT_command` env-reading hooks (`block-terminal-kill.sh`,
  `block-work-repo-git-push.sh`, `block-work-repo-git-writes.sh`) were never migrated to the
  stdin-payload pattern, precisely because there is no shared substrate to migrate *onto*.
- `docs/bugs/long-build-and-build-queue-matcher-bypasses/` — its fix wants an anchor-semantics
  change (`_CMD_START` family), which today must be hand-landed in **three** files that each
  believe they own the regex.

A shared library turns each of these from an N-site coordinated edit (with per-site drift
risk) into a one-site change with N pipe-tested consumers, and gives contracts like
"every error path leaves a trace" exactly one place to live.

## Design Decisions

### D1. Library shape: sourced bash prelude + importable python module

- **Classification:** `mechanical-internal (proposed)`
- `user/hooks/hook-prelude.sh` — **sourced** (never executed) by each hook, fail-open-guarded
  at the source site (`. "$…/hook-prelude.sh" 2>/dev/null || exit 0` — a missing/broken
  prelude allows, never wedges). Provides: python3→python resolution (`HOOK_PYTHON`),
  SCRIPT_DIR/scripts-dir derivation (`HOOK_SCRIPTS_DIR`), and the **pure-bash no-python
  fallback breadcrumb/event append** (the guard-fail-open bug's fix-scope §1 — printf/date
  only, best-effort).
- `user/scripts/hook_lib.py` — imported by the hooks' inline Python bodies (`sys.path` seeded
  from the threaded scripts dir, exactly as the five `_append_hook_event` copies already do
  for `lazy_core`). Provides: `allow()` / `deny(reason)` emitters, `append_hook_event(...)`
  (delegating to `lazy_core.append_hook_event` when importable, inline fallback otherwise —
  the current per-hook function, once), `breadcrumb(hook, err)`, and the shared anchor
  constants `ENV_PREFIX` / `CMD_START` (+ helpers like the path-prefix idiom).
- Residency note: `hook_lib.py` sits in `user/scripts/` beside `lazy_core.py` so the existing
  scripts-dir threading (`*_SCRIPTS_DIR` env vars) resolves it with zero new plumbing.

### D2. One inline fallback retained — the library must not become a single point of failure

- **Classification:** `product-behavior (proposed)`
- Each migrated hook keeps a **minimal** inline fallback: if `import hook_lib` fails for any
  reason, the hook still fails open correctly (bare `sys.exit(0)` allow) and — per the
  guard-fail-open bug's contract — leaves a trace via the bash-side prelude writer. The rich
  per-hook copies of `_append_hook_event`'s *inline fallback branch* collapse into
  `hook_lib`; only the import-failed guard survives per hook (a few lines, not forty).
- Constraint carried over from every current hook header: the Python body is passed via `-c`
  (never a heredoc — stdin carries the PreToolUse payload), and `hook_lib` import must not
  read stdin.

### D3. Migration: hook-by-hook, full suite per step, no behavior change

- **Classification:** `mechanical-internal (proposed)`
- Order: lowest-risk first (`block-noncanonical-blocker-write.sh`) → the sentinel sibling →
  `long-build-ownership-guard.sh` → `build-queue-enforce.sh` → `lazy-cycle-containment.sh` →
  the two thin wrappers (`lazy-dispatch-guard.sh`, `lazy-route-inject.sh`, prelude-only).
  After each hook: full `python user/scripts/test_hooks.py` run (157 tests, count verified
  2026-07-11) — the suite pipe-tests deny/allow output byte-identically, which is the
  no-behavior-change proof.
- The legacy `TOOL_INPUT` trio migrates onto the prelude as part of (or immediately after)
  `legacy-tool-input-env-hooks-dead`'s fix — that bug supplies the behavioral fix, this
  feature supplies the substrate.

### D4. Related but distinct: per-invocation latency

- **Classification:** `out-of-scope (documented)`
- A measured concern rides the same plane: `lazy_guard.py` imports all of `lazy_core` per
  invocation — re-measured 2026-07-11 on this machine: ~95 ms warm in-process import, ~180-670
  ms full interpreter+import per invocation (proposal session measured ~106 ms warm / ~705 ms
  cold; consistent). `hook_lib.py` therefore must stay **import-light** (stdlib only at module
  top; `lazy_core` imported lazily inside `append_hook_event`). Actually shrinking
  `lazy_guard`'s hot path is a separate optimization item, not this feature.

## Technical Design

```
user/hooks/<hook>.sh
  └─ . hook-prelude.sh            (fail-open-guarded source; missing ⇒ exit 0 allow)
       ├─ HOOK_PYTHON             (python3→python; absent ⇒ bash fallback breadcrumb + exit 0)
       ├─ HOOK_SCRIPTS_DIR        (SELF-normalized, builtins-only)
       └─ hook_emit_error_event() (pure-bash JSONL append + hook-error.json — no python needed)
  └─ "$HOOK_PYTHON" -c "$BODY"    (stdin = PreToolUse payload, unchanged)
       └─ import hook_lib          (sys.path ← HOOK_SCRIPTS_DIR; ImportError ⇒ minimal inline allow)
            ├─ allow() / deny(reason)
            ├─ append_hook_event(kind, hook, signature, detail, repo_root)
            ├─ breadcrumb(hook, err)      # chains into append_hook_event("error", …)
            └─ ENV_PREFIX / CMD_START     # single source for the anchor pair
```

House invariants honored: fail-OPEN on every new path (missing prelude, missing lib, broken
python); deny is JSON, never an exit code; bash never re-derives repo identity (repo keying
stays inside `lazy_core` behind `append_hook_event`); `LAZY_STATE_DIR` override semantics
byte-identical for every existing pipe-test.

## KPI Declaration

The headline signals for this feature are (1) **hook-plane duplicated-line count** (the table
above; down-is-good; measurable today by a deterministic static scan of `user/hooks/`) and
(2) **hook-drift-bug recurrence** (new `docs/bugs/*` entries whose root cause is hook-plane
copy drift; down-is-good). Neither has a registered signal in the closed v1 source/selector
enum (`kpi-scorecard.py` `_SOURCES` — no static-scan source exists), and this authoring
session does not edit the validator, so — following the `canary-trip-precision` /
`session-log-mining` precedent of registering selectors alongside the feature — **Phase 4
below registers the selector + registry row**, at which point the fenced draft here converts
to a live `docs/kpi/registry.json` row. Until then the drafted row is shown in a non-claiming
fence (deliberately not ```json — the deterministic validator must not treat an unregistered
selector as claimable):

```jsonc
{
  "id": "hook-plane-duplicated-lines",
  "system": "hook-plane",
  "title": "Hook-plane duplicated scaffolding lines",
  "friction": "Copy-pasted hook scaffolding drifts per copy; each drifted copy is a latent guard bug (breadcrumb-path defect, never-migrated payload pattern) and every cross-cutting matcher change costs one coordinated edit per copy.",
  "signal": { "source": "repo-static-scan", "selector": "hook-duplicated-line-count" },
  "unit": "lines",
  "direction": "down-is-good",
  "baseline": { "value": 467, "captured_at": "2026-07-11", "window": "n/a-static", "provenance": "retro-derived" },
  "band": null,
  "review_by": "2026-12-01",
  "notes": "Baseline hand-counted 2026-07-11 (grep inventory in the SPEC's Executive Summary). Source 'repo-static-scan' + selector registration land in Phase 4 (new _SOURCES entry + a deterministic counter script); until then this is a drafted, non-claiming row per the canary-trip-precision precedent."
}
```

Additionally, one existing registry row is a declared downstream beneficiary:

- kpi: build-queue-raw-invocation-deny-recurrence

That row's notes defer its signal on "a best-effort, fail-OPEN-preserving hook-side append of
build-queue denies into the deny ledger"; the shared `hook_lib.append_hook_event` /
ledger-append surface this feature builds is the sanctioned one-site vehicle for that append,
un-blocking the row's collection without another per-hook copy. (Honest scope note: that row
measures build-queue skill-routing recurrence, not this feature's dedup itself — it is listed
as the enabled consumer, with the headline metrics above carried by the Phase-4 row.)

## Implementation Phases

- **Phase 1 — `hook-prelude.sh` + no-python fallback (~1 session).** Prelude with python
  resolution, SCRIPT_DIR, pure-bash event/breadcrumb writer; wire into the two thin wrapper
  hooks (`lazy-dispatch-guard.sh`, `lazy-route-inject.sh`) as first consumers. Lands
  `guard-fail-open-leaves-no-trace` fix-scope §1 as a side effect. Pipe-tests: no-python
  branch leaves the event line; sourcing a missing prelude still allows.
- **Phase 2 — `hook_lib.py` (~1 session).** Emitters, appender, breadcrumb, anchor constants;
  unit tests + import-light guard (a test asserting `import hook_lib` does not pull
  `lazy_core`).
- **Phase 3 — migrate the five inline-Python hooks (~1-2 sessions).** One hook per step, D3
  order, full `test_hooks.py` (157) after each; byte-identical deny/allow output asserted by
  the existing suite. The `_ENV_PREFIX`/`_CMD_START` triplication collapses here —
  coordinate with `long-build-and-build-queue-matcher-bypasses` so the anchor fix lands once.
- **Phase 4 — KPI wiring (~0.5 session).** Register `repo-static-scan` /
  `hook-duplicated-line-count` in `kpi-scorecard.py` `_SOURCES` + the deterministic counter;
  move the drafted row into `docs/kpi/registry.json`; re-run
  `kpi-scorecard.py --lint` + `--lint --spec` on this SPEC.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| No behavior change per migration | Full pipe-test suite after each hook | 157/157 pass, deny/allow output byte-identical | `test_hooks.py` |
| Missing prelude fails open | Hook run with prelude renamed away | exit 0, no output (allow) | new pipe-test |
| No-python path leaves a trace | Hook run with stripped PATH | `hook-events.jsonl` gains one bash-written error line | new pipe-test |
| `hook_lib` import failure fails open | `HOOK_SCRIPTS_DIR` pointed at empty dir | allow + prelude-side trace | new pipe-test |
| Duplication actually removed | Post-migration grep inventory | `_append_hook_event`/`_breadcrumb`/anchor defs each exist once | grep + Phase-4 counter |
| Import-light lib | Unit test | `import hook_lib` does not import `lazy_core` | `test_hook_lib.py` |

## Open Questions

- Does the pure-bash event writer's second-granularity integer `ts` need widening for
  `incident-scan.py` consumers (guard-fail-open D1)? Verify before Phase 1 lands.
- Should the legacy `TOOL_INPUT` trio be migrated inside Phase 3 or left to
  `legacy-tool-input-env-hooks-dead`'s own fix (which this feature merely unblocks)? Default:
  the bug owns the behavior change, this feature owns the substrate.
- Windows git-bash sourcing cost: the prelude adds one `source` per hook invocation — confirm
  it is negligible against the existing 5s hook timeout budget (expected: microseconds).
