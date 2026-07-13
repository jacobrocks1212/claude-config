---
kind: fixed
feature_id: state-script-test-runner-crashes-on-systemexit-from-live-cycle-marker
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: lazy-state.py --test (hermetic RED-then-GREEN repro under a synthetic live cycle marker)
auto_ticked_rows: 0
---

# Completion Receipt

state-script-test-runner-crashes-on-systemexit-from-live-cycle-marker marked Fixed on 2026-07-12 by
operator-directed interactive close-out.

## Root Cause (premise-false, small real finding fixed)

The bug's originally-claimed mechanism ("SystemExit escapes `except Exception` and crashes the
suite") was FALSE at HEAD — the runner already caught `SystemExit` explicitly. The real, smaller
finding: the `apply-pseudo-provisional-refusal` fixture lacked its own `LAZY_STATE_DIR` isolation
(unlike sibling fixture groups), so it spuriously FAILed (not crashed) under a genuinely-live cycle
marker, masking its actual assertion behind an unrelated environment-coupled refusal.

## Symptom Reproduction (red -> green)

```
mkdir -p /tmp/repro-state-dir
printf '{"feature_id": "repro-feat", "started_at": "2026-07-12T00:00:00Z"}' \
  > /tmp/repro-state-dir/lazy-cycle-active.json
LAZY_STATE_DIR=/tmp/repro-state-dir python3 user/scripts/lazy-state.py --test
```

- **Before this pass's fix (both fixtures unisolated):** exit 1, `FAILURES:` naming
  `resume-partial-apply-walk-convergence` (a second, previously-undiscovered instance of the same
  defect class — see Notes) after the SPEC's originally-named fixture was isolated first.
- **After isolating BOTH fixtures:** exit 0, `All smoke tests passed.`

## Notes

Fixed the SPEC's named fixture (`apply-pseudo-provisional-refusal`, `lazy-state.py` ~9818-9855) by
wrapping its one `lazy_core.apply_pseudo(...)` call in a private `LAZY_STATE_DIR`
save/point-at-temp-dir/restore bracket, mirroring the sibling isolation pattern already used
elsewhere in the file.

**Extension beyond the SPEC (found during this pass's verification):** re-running the SPEC's exact
hermetic repro against HEAD surfaced a SECOND unisolated in-process `apply_pseudo` call —
`resume-partial-apply-walk-convergence` (`lazy-state.py` ~9917-9923), part of the
`mark-complete-partial-apply-noop-unrecoverable` fix that landed after this bug's SPEC was authored
(so the SPEC's original scan could not have found it). Fixed identically (same isolation shape).
Not a design fork — a second instance of the exact defect class the SPEC's own Fix Scope
recommendation already prescribes fixing.

No change to `bug-state.py` (confirmed: no in-process `apply_pseudo` call in its `--test` harness,
per the SPEC).

## Verification

```
LAZY_STATE_DIR=<empty dir> python user/scripts/lazy-state.py --test   -> exit 0, All smoke tests passed.
LAZY_STATE_DIR=<empty dir> python user/scripts/bug-state.py --test    -> exit 0, All smoke tests passed.
LAZY_STATE_DIR=<dir w/ live cycle marker> python user/scripts/lazy-state.py --test -> exit 0, All smoke tests passed.
```
