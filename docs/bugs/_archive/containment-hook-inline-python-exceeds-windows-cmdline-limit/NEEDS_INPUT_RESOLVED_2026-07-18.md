---
kind: needs-input
feature_id: containment-hook-inline-python-exceeds-windows-cmdline-limit
written_by: harness-change-gate
class: product
decisions:
  - Operator sign-off on the harness-change gate_weakening flag (enforcement-plane change) before marking the bug Fixed
date: 2026-07-18
next_skill: __mark_fixed__
---

# Harness-Change Design Gate — operator sign-off required (gate_weakening)

## Decision Context

### Operator sign-off on the gate_weakening flag

**Problem.** The containment-hook fix (commits `53eb47e8`/`74b8d26f`/`82183884`) modified two
enforcement-plane hooks in `docs/gate/control-surfaces.json` scope
(`user/hooks/lazy-cycle-containment.sh`, `user/hooks/build-queue-enforce.sh`), so the anti-overfit
design gate ran. `harness-gate.py` raised `gate_weakening: hit`, which is NEVER judgment-passable
and always requires operator sign-off (harness-change-gate.md D4), blocking `__mark_fixed__` until
signed.

**The flag is a verified false positive.** Its SOLE evidence is a **PHASES.md prose row** (not
code): `- [x] <!-- verification-only --> Post-conversion, \`build-queue-enforce.sh\` under [the
limit]` — whose text mentions `build-queue-enforce.sh` (which contains a `BUILD_QUEUE_BYPASS`
token), matching the detector's `*_BYPASS` pattern. `git diff` over the two hook bodies shows ZERO
removed `def test_*`, ZERO removed `permissionDecision: deny`/`refuse_*`/`exit 3` branches, ZERO
added `*_BYPASS=` env-vars, and the embedded deny body is BYTE-UNCHANGED. The fix STRENGTHENS the
plane: it re-arms the `lazy-cycle-containment.sh` guard that the E2BIG bug had silently disarmed on
Windows (the guard was fail-opening on every invocation, 22 `test_containment_*` red → now green).

**Options.**
- **Sign off (approve) — recommended.** Transcribe `override: operator-approved` into
  `GATE_VERDICT.md`, mark the bug Fixed. The change weakens no gate; the flag is a detector
  precision artifact (it scans PHASES.md prose). Per-change approval, non-standing.
- **Decline / reshape.** Reject the change and reshape it (e.g. reword the PHASES.md row so the
  detector does not fire, or split the diff). Higher friction; does not change the fix's behavior.

**Recommendation:** Sign off — the change strengthens the enforcement plane, no deny logic was
weakened, and the flag is a confirmed harness-gate.py false positive on documentation prose. (A
separate harden of harness-gate.py to not scan PHASES.md prose rows for gate-weakening patterns is
a reasonable follow-up.)
