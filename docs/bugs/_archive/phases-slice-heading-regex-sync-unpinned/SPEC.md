# phases-slice.py phase-heading regex sync is comment-only — no mechanical pin to the lazy_core canonical — Investigation Spec

> `user/scripts/phases-slice.py` carries a deliberately private copy of the canonical
> phase-heading regex (`_PHASE_HEADING_RE`) whose only sync contract is a comment
> ("keep byte-identical to lazy_core._PHASE_HEADING_RE", phases-slice.py:39). No test in
> `test_phases_slice.py` or `test_lazy_core.py` pins the two pattern strings equal — so a
> future edit to the canonical silently desynchronizes the scoped reader's phase boundaries.
> The canonical just MOVED (`lazy-core-package-decomposition` Phase 2 WU-2:
> `lazy_core/_monolith.py` → `lazy_core/docmodel.py`), and phases 3–6 of the decomposition
> keep its home a moving target — comment-discipline alone is now measurably weaker.

**Status:** Fixed
**Fixed:** 2026-07-18
**Fix commit:** a78845f7
**Priority:** P2
**Last updated:** 2026-07-13
**Related:** `docs/features/lazy-core-package-decomposition/` (the module move that exposed the gap; Phase 2 WU-2 relocated the canonical to `lazy_core/docmodel.py:1419` with the facade entry `_PHASE_HEADING_RE → docmodel` in `lazy_core/__init__.py:100`); `docs/features/phases-slice-scoped-reads/` (the feature that shipped the private copy with the comment-only contract); `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Round 38 (the hardening round that fixes this).

## Verified Symptom

Observed during `lazy-core-package-decomposition` Phase 2 execution (2026-07-13):

- `user/scripts/phases-slice.py:39-42` compiles a private `_PHASE_HEADING_RE` under the
  comment "Canonical phase-heading marker — keep byte-identical to
  lazy_core._PHASE_HEADING_RE." The two patterns are byte-identical TODAY
  (`r"^#{2,3}\s+Phase\s+(?:[A-Za-z.+]*\d[A-Za-z0-9.+]*|[A-Za-z0-9.+]+\s*[:—-])"`,
  docmodel.py:1419-1421) — no live drift, this is a latent-defect capture.
- `grep -n "_PHASE_HEADING_RE" user/scripts/test_phases_slice.py` → zero hits;
  `test_lazy_core.py` likewise has no cross-file pattern-equality assertion. The sync
  contract is enforced by nothing.
- The Phase-2 plan referenced a monolith-side reciprocal "keep in sync with phases-slice.py"
  comment that NEVER EXISTED — the definition site (`docmodel.py:1419`) carries no pointer
  back at its copier, so an editor of the canonical has zero signal that a private copy
  depends on it.
- Consequence of undetected drift: `phases-slice.py`'s phase boundaries diverge from the
  boundaries `lazy_core` (deliverable counting, completion gates, `--count-phases`) computes —
  the scoped reader silently shows `/execute-plan` orchestrators a different phase slicing
  than the state machine enforces.

## Root Cause

**Classification: `missing-contract`.**

The `phases-slice-scoped-reads` feature deliberately duplicated the regex (the script is a
standalone pure-read tool that should not import `lazy_core`) but shipped the sync contract
as comment prose only. The repo already has the canonical pattern for exactly this shape —
a lockstep test asserting a copier's literal equals the SSOT symbol
(`test_ruvonly_marker_lockstep_producers_match_ssot` pins producer prose ==
`lazy_core._VERIFICATION_ONLY_MARKER`) — and `test_phases_slice.py` already imports
`phases-slice.py` via `importlib.util.spec_from_file_location` (line 12), so the mechanical
pin was cheap and simply never authored. The decomposition (canonical relocating across
phases 3–6) converts this from theoretical to probable drift.

Near-neighbor sweep (single-instance confirmation): `phases-slice.py:39` is the ONLY
byte-identity comment contract on a private copy in `user/scripts/` —
`lazy-queue-doc.py:130`'s `_PHASE_HEADING_RE` is a deliberately different display-only
heuristic (`^###\s+Phase\b`) claiming no sync.

## Fix Scope

1. **Lockstep test (the mechanical pin):** add `test_phase_heading_re_lockstep_with_lazy_core`
   to `user/scripts/test_phases_slice.py` asserting
   `ps._PHASE_HEADING_RE.pattern == lazy_core._PHASE_HEADING_RE.pattern` (and flags equal).
   Import `lazy_core` via the package (facade re-export) — the test then survives the
   remaining decomposition phases regardless of which submodule hosts the definition.
2. **Reciprocal comment at the definition site:** annotate `lazy_core/docmodel.py:1419` with
   a keep-in-sync pointer naming `phases-slice.py`'s private copy and the lockstep test, so
   an editor of the canonical sees the dependency (the comment the Phase-2 plan wrongly
   assumed existed).

No behavior change; docs + test only.
