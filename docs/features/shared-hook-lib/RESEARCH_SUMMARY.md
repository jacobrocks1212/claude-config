---
kind: research-summary
feature_id: shared-hook-lib
provenance: operator-waived
date: 2026-07-18
---

# Research Summary — Shared Hook Library

**Deep (Gemini) research was operator-waived** on 2026-07-18 during the overnight
`/lazy-batch-parallel` wind-down (see `RESEARCH.md`). No external findings exist. This summary
therefore analyzes the baseline against **in-repo prior art** and the `RESEARCH_PROMPT.md`
question inventory (retained as a design checklist for the implementation phases), which is what
the finalized baseline is grounded in.

## Key findings relevant to the baseline

- **The design tension is real and already resolved in the baseline.** The research prompt's
  central question — "does extracting shared scaffolding convert N independent, locally-degrading
  fail-open guards into ONE correlated failure point?" — is answered by the baseline's D2 (retain
  a minimal per-hook inline fallback) + the fail-open-guarded `source` at the call site
  (`. hook-prelude.sh 2>/dev/null || exit 0`) and `import hook_lib` ImportError degradation. No
  external source is needed to validate this; it is a direct application of the repo's fail-OPEN
  constitution.
- **Rich in-repo prior art exists to copy from, not invent.** The five `_append_hook_event`
  copies already thread `*_SCRIPTS_DIR` and seed `sys.path` to import `lazy_core`; `hook_lib.py`
  residing beside `lazy_core.py` reuses that exact plumbing with zero new machinery. The behavior
  the library centralizes is already written seven times — the feature is a dedup, not a design.
- **The "no behavior change" claim is operationalized, not narrative.** The 157-test `test_hooks.py`
  suite pipe-tests each hook's stdin→stdout deny/allow JSON byte-for-byte; re-running it after each
  single-hook migration is the proof. This is the strongest possible confirmation an internal
  refactor can carry and needs no external corroboration.

## Ideas to adopt from prior art

- **Import-light discipline** (baseline D4): keep `hook_lib.py` stdlib-only at module top and defer
  the `lazy_core` import lazily inside `append_hook_event`, because the per-invocation import cost
  (~95 ms warm / up to ~670 ms cold, re-measured 2026-07-11) runs against the 5 s hook timeout on
  every matching tool call. This is a measured local constraint, not a research recommendation.
- **Migration order = lowest-blast-radius first** (baseline D3): start at
  `block-noncanonical-blocker-write.sh`, end at the thin prelude-only wrappers; full suite between
  every step so a regression is attributed to exactly one hook.

## Pitfalls / concerns to address (already tracked in the baseline)

- **Single point of failure** — addressed by D2 + the source-site fail-open guard. The library must
  never be able to wedge a hook: a missing prelude `exit 0`s, a failed `import hook_lib` bare-allows
  and still leaves a bash-side trace.
- **Losing the "leave a trace" contract on the fail-open path** — the exact defect
  `guard-fail-open-leaves-no-trace` fixed; the prelude's pure-bash event/breadcrumb writer (Phase 1)
  gives every error path one owner.
- **The `_ENV_PREFIX`/`_CMD_START` triplication** — collapses in Phase 3; must coordinate with
  `long-build-and-build-queue-matcher-bypasses` so the anchor-semantics fix lands once.

## Baseline decisions to revisit

None. Research surfaced no new choice and no external convention that reverses a baseline decision.
D2 (the one decision drafted as `product-behavior`) has no viable alternative under the fail-OPEN
constitution and produces byte-identical observable behavior, so it is not a live product choice —
it is finalized as `mechanical-internal (constitution-forced)`. The three `## Open Questions` are
implementation-time verifications with stated defaults (event-writer `ts` width, TOOL_INPUT-trio
migration ownership, git-bash sourcing cost), not baseline-gating product decisions.
