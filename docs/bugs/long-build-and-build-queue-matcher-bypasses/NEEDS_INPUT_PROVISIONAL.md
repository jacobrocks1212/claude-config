---
kind: needs-input
bug_id: long-build-and-build-queue-matcher-bypasses
written_by: fix
decisions:
  - "D2: bash -c / sh -c string-wrap scope — subscan vs documented-limitation (plane-wide)"
date: 2026-07-12
class: product
divergence: isolated
audit_divergence: isolated
next_skill: fix
---

# NEEDS_INPUT — Provisionally Accepted (park-provisional protocol)

This bug's SPEC (`## Decisions` → D2) left the `bash -c` / `sh -c` string-wrap scope
**explicitly unresolved at investigation close**: "requires the planner to pick subscan vs
documented-limitation plane-wide" — no recommended option was named, unlike D1 (which the SPEC
does resolve with a clear recommendation, implemented as-is). This session implemented Fix Scope
items 1, 2, and 4 (the `_LONG_BUILD_RE` runner/path-prefix extension and the `_WRAPPER_RE`
anchoring, both TDD-covered in `test_hooks.py`) but treated D2 as a genuine fork requiring a
choice with no SPEC-stated recommendation. Per the park-provisional protocol, this session made
and implemented a call (documented-limitation) rather than halting, and records that choice here
for ratify-or-redirect review — **this bug's Status is NOT flipped to Fixed** pending that
review, even though the rest of the SPEC's Fix Scope is implemented and tested.

## Decision Context

### 1. D2: bash -c / sh -c string-wrap scope

**Problem:** every `_CMD_START`-anchored matcher in this plane (`lazy-cycle-containment.sh`'s
recursion/routing/lifecycle denies, `long-build-ownership-guard.sh`'s `_LONG_BUILD_RE`,
`build-queue-enforce.sh`'s deny surface + the newly-anchored `_WRAPPER_DIRECT_RE`/
`_WRAPPER_POWERSHELL_RE`) requires the denied/allowed token to sit at a top-level command-segment
start. A `bash -c "cargo build --release"` / `sh -c "dotnet build ..."` places that token inside a
**quoted STRING ARGUMENT** — one level of indirection none of these matchers unwraps (distinct
from the EXISTING `powershell/pwsh -Command "..."` nesting normalization, which DOES unwrap one
level for that specific PowerShell form). The SPEC's own fix-scope item 3 requires this to be
**decided, not left to silently drift**: "Either add a quoted-string subscan (rescan the argument
of `(?:ba)?sh\s+-l?c\s+` as a nested command text) or write the explicit out-of-scope note in the
hook headers + `user/hooks/CLAUDE.md`. Do not fix it for one hook only."

**Options (from the SPEC's fix-scope item 3, no SPEC recommendation given):**
- **A — bash -c / sh -c nested-command subscan (mirror the existing PowerShell `-Command`
  unwrap).** Re-run every anchored matcher against the quoted argument as a synthetic segment,
  the same additive-normalization shape `_normalize_ps_syntax` already uses for
  `powershell/pwsh -Command "..."`. Closes the gap completely across the whole anchor-pair
  family in one shared normalization step.
- **B — documented-limitation (accepted residual), plane-wide.** Add an explicit, prominent
  out-of-scope note to all three hooks' headers + `user/hooks/CLAUDE.md`, and pin the CURRENT
  (unfixed) behavior with an explicit regression test per hook so a future change is a conscious
  decision, not a silent regression.

**This session's choice: B (documented-limitation).**

**Rationale (why B, absent a SPEC recommendation):**
- **Scope containment.** A real subscan is plane-wide by the SPEC's own item 5 coordination rule
  (the `_ENV_PREFIX`/`_CMD_START` anchor pair exists in three copies — `lazy-cycle-containment.sh`,
  `long-build-ownership-guard.sh`, `build-queue-enforce.sh` — and item 5 requires any anchor-
  semantics change to land in all three, or route through `docs/features/shared-hook-lib`). This
  bug's assigned lane (HOOKS) does not include a mandate to touch `lazy-cycle-containment.sh`'s
  anchor semantics, and doing so unreviewed risks the SAME hook whose false-deny class item 3 of
  this run (`lazy-cycle-containment-false-denies-reference-only-routing-mentions`) had JUST
  hardened in the opposite direction (tightening reference-vs-invocation discrimination). A
  subscan is a genuine new capability (parsing a shell string argument as a nested command line)
  with its own false-positive/quoting-edge-case surface (nested quotes, escaped characters,
  `$(...)`  substitution inside the wrapped string) — meaningfully riskier than the flat
  string operations every existing normalization here uses.
- **Precedent for the documented-residual pattern already exists in this exact codebase.** The
  sibling bug `lazy-cycle-containment-false-denies-reference-only-routing-mentions` (Concluded
  this same round, fully pre-landed at HEAD) explicitly accepted an analogous residual: "a
  pathological commit message that literally embeds a shell separator immediately followed by a
  state-script invocation ... can still create a fake segment boundary and false-deny. This is
  the identical narrow residual the build-queue hook accepts; not worth shell-quote parsing." B is
  the same call, applied consistently to the ALLOW direction (bypass) rather than the DENY
  direction (false-positive).
- **The gap is pinned, not silent.** `test_longbuild_guard_bash_dash_c_wrap_accepted_residual` and
  `test_bqe_bash_dash_c_wrapper_reference_accepted_residual` (both green) assert the CURRENT
  (unfixed) ALLOW behavior explicitly, so a future accidental "fix" or regression is caught either
  way — the residual is documented in three places: the `_LONG_BUILD_RE` docstring in
  `long-build-ownership-guard.sh`, the `_WRAPPER_RE` replacement-rationale comment in
  `build-queue-enforce.sh`, and a new "Known limitation" block in `user/hooks/CLAUDE.md`.

**Recommendation (this session, for ratification):** B — lower blast radius, consistent with
existing precedent in this codebase for the identical anchor-pair shape, and the gap is fully
documented + regression-pinned rather than silently present. A (the subscan) remains available as
a deliberate future fix — implementing it would mean turning the pinned residual tests from
GREEN (documents ALLOW) to RED, then fixing them to DENY, exactly as the CLAUDE.md note
instructs.

## Resolution

Not yet ratified. This file documents the provisional choice; the bug's `SPEC.md` **Status**
stays `Concluded` (not `Fixed`) until an operator reviews and either ratifies B or redirects to A.
Fix Scope items 1, 2, and 4 (the matcher-gap closures + regression tests) are implemented,
tested, and landed independent of this decision — they do not depend on the D2 outcome.
