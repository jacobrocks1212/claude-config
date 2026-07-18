---
kind: gate-verdict
feature_id: containment-hook-inline-python-exceeds-windows-cmdline-limit
gate_version: 1
date: 2026-07-18
scope_hit: [user/hooks/lazy-cycle-containment.sh, user/hooks/build-queue-enforce.sh]
checks:
  overfit: flag-justified
  tautology: pass
  gate_weakening: hit-signed
  complexity: declared
retires: net-new — the mktemp temp-file invocation shim + the plane-wide 25000-char `-c`-body ceiling test are net-new defensive surface. They pay for themselves by eliminating the entire Windows E2BIG silent-fail-open class for ANY `-c`-invoking hook (not just the two converted here): the ceiling test fails the moment any hook's embedded python body approaches the 32,767-char CreateProcess limit, so the class cannot recur silently.
override: operator-approved 2026-07-18 — false-positive gate_weakening flag on a plane-STRENGTHENING fix (re-arms a guard the E2BIG bug had silently disarmed); no deny logic weakened. Signed via /lazy-batch Step 1g.
---

## Adversarial answers

### overfit
The checker flagged "alternation literal appended" on lines in `lazy-cycle-containment.sh` /
`build-queue-enforce.sh` (`if [ -z "$tmpfile" ] ...`, `_HOOK_TMPWRITE_TS=...`, the fail-open
breadcrumb writes) and "literal element appended to a membership construct" in `test_hooks.py`.
These are NOT matcher-overfitting: the fix keys on **no literal matcher at all**. It replaces the
`python -c "$BODY"` *invocation mechanism* with an `mktemp`'d temp-file + stdin invocation — a
structure-level change to how the interpreter is launched, independent of any command/token the
hook matches. The added `test_hooks.py` lines assert a **size CEILING** (`_EMBEDDED_PY_CEILING =
25000`) over ALL `-c`-invoking hooks and a fail-open-on-tmpwrite-failure invariant — structural
properties, not incident literals. Nearest recurrence the change must (and does) catch: a *third*
hook whose embedded python body grows past the limit — the ceiling test catches it with zero new
literals, because it keys on body-length structure, not on the two hook names fixed here.

### tautology
N/A — no `## Intervention Hypothesis` self-emitted-signal concern here. The fix's success signal is
independent and observable: the 22 `test_containment_*` tests (which drive the REAL hook under a
marker and assert `permissionDecision: deny`) invert from red→green at the reported surface — an
independent regression suite, not a metric the change itself emits or suppresses. If the fix were
broken (guard still disarmed), those 22 tests would stay red.

### gate_weakening
The checker's SOLE gate_weakening evidence is a **PHASES.md prose row** —
`- [x] <!-- verification-only --> Post-conversion, \`build-queue-enforce.sh\` under [the limit]` —
whose text mentions `build-queue-enforce.sh` (which itself contains a `BUILD_QUEUE_BYPASS` token),
matching the detector's `*_BYPASS` pattern. This is a **documentation row, not a code change**:
`git diff` over the two hook bodies shows ZERO removed `def test_*`, ZERO removed
`permissionDecision: deny` / `refuse_*` / `exit 3` branches, ZERO added `*_BYPASS=` env-vars, and
the embedded deny body is BYTE-UNCHANGED. The change is the OPPOSITE of a weakening: it RE-ARMS the
`lazy-cycle-containment.sh` guard that the E2BIG bug had silently disarmed on Windows (the guard was
fail-opening on every invocation). Underlying-defect alternative (`/harden-harness` Prohibition #2):
there is no gate to strengthen instead — the fix IS the strengthening. Because the contract makes
gate_weakening never judgment-passable, this was routed to operator sign-off (Step 1g); the
`override` line above records the approval. Per-change, non-standing.

### complexity
Net-new defensive surface (see `retires:`). The mktemp shim is ~8 lines per hook; the ceiling test
is one AST-grep assertion + one constant. Both generalize beyond the two hooks fixed, so the added
surface catches the whole class rather than the two observed instances.
