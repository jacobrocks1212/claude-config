---
kind: needs-input
feature_id: lazy-core-package-decomposition
written_by: harden-harness
decisions:
  - "Patch-visibility mechanism fork: bless the _resolve_ntfy_send facade-patch resolution shim as THE pattern for external-harness facade-level patches, or plan its retirement (redirect the two smoke fixtures to owning-module patching in a later phase and delete the shim)?"
date: 2026-07-13
---

## Decision Context

Phase 1 of the decomposition shipped TWO coexisting patch-visibility mechanisms, and later
phases need to know which one is canonical before they extract more seams:

1. **The operator-ratified L1 mechanism-3** — "redirect the patches to the resolving module":
   a test that monkeypatches an internal collaborator patches it on the module that RESOLVES
   the name (post-split: `lazy_core._monolith`, or the owning submodule once extracted), not on
   the `lazy_core` facade. This is the ratified rule for tests INSIDE this repo's own suite.

2. **The `_resolve_ntfy_send` shim** (`user/scripts/lazy_core/_monolith.py:20099-20125`) —
   added during Phase 1 because the state scripts' `[notify-halt-call-site]` in-file smoke
   fixtures (e.g. `lazy-state.py:11102`: `lazy_core._ntfy_send = fake`) patch at FACADE level
   and were out of Phase-1 scope to rewrite. At each `notify_halt` send, the shim checks the
   live `lazy_core` package's own `__dict__` for a patched `_ntfy_send` FIRST (a plain dict
   read that never triggers the PEP 562 `__getattr__`), falling back to `_monolith`'s own
   binding. Production behavior is identical either way; the shim exists purely so
   facade-level patches stay honored.

### The fork

- **Option A — bless the shim as THE pattern for external-harness facade-level patches.**
  Rationale: the facade is the package's public surface; external consumers (the two state
  scripts' in-file fixtures today, potentially other harness scripts tomorrow) should not have
  to know which submodule currently owns a name mid-decomposition — the submodule map churns
  through Phases 2-6 by design. Cost: every future extracted seam whose internals are patched
  externally needs its own `_resolve_*` shim (a per-name resolution indirection), and the
  codebase permanently carries two documented patch conventions (internal tests → owning
  module; external harness → facade). Requires documenting the pattern in
  `user/scripts/CLAUDE.md`'s patch-target guidance.

- **Option B — plan the shim's retirement.** A later decomposition phase (whichever extracts
  the notify seam, or a dedicated WU) redirects the two `[notify-halt-call-site]` smoke
  fixtures to patch the owning module directly (`lazy_core._monolith._ntfy_send = fake` today;
  the notify submodule after extraction), then deletes `_resolve_ntfy_send` — leaving the
  ratified mechanism-3 as the SINGLE patch-visibility rule for all callers, internal and
  external. Cost: external fixtures become coupled to the internal submodule layout (each
  later extraction that moves `_ntfy_send` must also touch the two state-script fixtures);
  the decomposition's "facade consumers are untouched" property is weakened for
  patch-writers (though not for readers — PEP 562 forwarding covers reads).

- **Option C — Option B with an interim guard:** keep the shim through the remaining
  decomposition phases (it is correct and tested today), but add an explicit retirement WU to
  the phase that extracts the notify seam so the shim cannot silently become permanent
  convention by default.

### Why this is operator-owned (not decided unilaterally)

Mechanism-3 ("redirect the patches to the resolving module") was an OPERATOR-RATIFIED L1
decision of this feature; the shim is a de-facto second mechanism that partially supersedes it
for one name. Blessing or retiring it changes the feature's ratified patch-target contract and
sets the convention every later extraction phase follows — an authority change per the
harden-harness contract/policy/design-fork rule, not a mechanical fix.

**Recommendation (non-binding):** Option C — it preserves the single-mechanism end state the
operator already ratified while costing nothing now and preventing convention-by-inertia.
