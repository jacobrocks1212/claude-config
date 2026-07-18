# Bug: run marker never arms park at run-start + forward_cycles inflates on non-dispatch inject turns

**Status:** Fixed
**Fixed:** 2026-07-18
**Fix commit:** beae3aa0
**Trigger:** observed-friction (orchestrator-observed mid-run, live overnight `/lazy-batch 25 --park --park-provisional`, 2026-07-17)
**Item in flight:** adhoc-hydra-sidecar-dist-esm-no-frames
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage), `docs/bugs/_archive/dispatch-probe-and-inject-bypass-merged-head/` (same run, Round 54), `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Round 55

Two independent run-marker defects observed during ONE overnight autonomous run. They are
unrelated in mechanism (park arming vs. forward-cycle counting) but were both surfaced by the
same run, so they are investigated together and their fixes are dispositioned separately:
DEFECT 2 is a mechanical harness fix; DEFECT 1 is a gate-semantics design fork routed to
`NEEDS_INPUT.md`.

---

## DEFECT 2 — park mode is OFF at run-start under a `--park` invocation (MECHANICAL)

### Verified symptom

The overnight run was invoked `/lazy-batch 25 --park --park-provisional`. The run marker
(`~/.claude/state/<repokey>/lazy-run-marker.json`) was written with
`park_needs_input=false, park_blocked=false, park_provisional=false`. Park mode was therefore
effectively OFF for an overnight `--park` run until the orchestrator manually toggled it via
`--set-park` mid-run. A blocker/needs-input hit before that toggle would have HALTED the queue
(the exact failure `--park` exists to prevent on an unattended overnight run).

### Root cause — `ambiguous-prose` / missing flag forwarding in the SKILL

The CLI is NOT the defect. `lazy-state.py --run-start` (and `bug-state.py --run-start`) ALREADY
accept `--park-needs-input` / `--park-blocked` / `--park-provisional` and thread them into
`write_run_marker` (`lazy-state.py` ~line 12516-12518; `bug-state.py` ~line 8415-8417). The
marker's park fields are documented RUN_FRESH_FIELDS "re-supplied at run-start from the
invocation `--park` flags" (`lazy_core/markers.py` §RUN_FRESH_FIELDS comment).

The gap is in the SKILL. `lazy-batch/SKILL.md` Step 0.55 runs:

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --run-start --max-cycles {max_cycles} \
  --repo-root {cwd}
```

— with NO park flags, unconditionally, even when the operator passed `/lazy-batch --park`. So
the operator's park intent is dropped at run-start. The same omission exists verbatim in the
two coupled derived skills (`lazy-bug-batch/SKILL.md`, `lazy-batch-cloud/SKILL.md`).

Secondary friction: the operator invocation flag is the single umbrella `--park` (= both
`park_needs_input` AND `park_blocked`, mirroring `--set-park on`), but the CLI exposes only the
two granular flags. Forwarding therefore required the orchestrator to TRANSLATE `--park` into
two flags in prose — a translation that was simply forgotten, and that could be forgotten again.

### Fix scope (implemented)

1. **Add a `--park` umbrella CLI flag** to `lazy-state.py` AND `bug-state.py` (coupled-pair CLI
   parity) that arms BOTH `park_needs_input` and `park_blocked`, normalized early (before the
   `--park-provisional requires --park-needs-input` pairing guard) so every downstream read sees
   the same shape whether the umbrella or the two granular flags were passed. This mirrors the
   existing `--set-park on` umbrella and makes the SKILL forward the operator's `--park` token
   VERBATIM (no re-translation to forget).
2. **Step 0.55 forwards park** in all three skills: `--run-start … {park_flags}`, where
   `{park_flags}` is `--park` when `park_mode`, plus `--park-provisional` when
   `park_provisional_mode`, else empty. Byte-identical to today when neither is passed.
3. Regression fixture (`tests/test_lazy_core/test_markers.py`, subprocess against BOTH real
   scripts): `--run-start --park` → marker `park_needs_input=true, park_blocked=true`;
   `--run-start --park --park-provisional` → all three true; bare `--run-start` → all false.

### Target signal

`event:run-start` (ledger) — the future-run recurrence surface. After the fix a `--park`
overnight run's `run-start` marker carries park armed; the recurrence of a park-invoked run
whose marker is born park-OFF should go to zero.

---

## DEFECT 1 — forward_cycles inflates on non-dispatch inject-hook turns (DESIGN FORK → NEEDS_INPUT)

### Verified symptom

After ONE real dispatch (cycle 1, execute-plan `hydra-overlay`) the marker showed
`forward_cycles=3`, with `per_feature_forward_cycles = {hydra-overlay: 2 (dispatched once),
adhoc-hydra-sidecar-dist-esm-no-frames: 1 (never dispatched)}`. The increments line up 1:1 with
`lazy-route-inject.sh` LAZY-ROUTE banner emissions across UserPromptSubmit turns (turns 2+4
routed hydra → hydra=2; turn 5 routed the bug → bug=1) — i.e. forward_cycles advanced at
banner-EMISSION time on turns where NO dispatch occurred (background-agent-completion
NOTIFICATION turns), rather than at actual dispatch / registry-consume time. On a long overnight
run with many notification turns this balloons forward_cycles and FALSE-hits `max_cycles`,
ending the run early — the opposite of intended.

### Root cause — `script-defect` located, but the fix is a gate-semantics FORK

The inject hook (`lazy_inject.py::_run_probe`) runs the FULL probe `--repeat-count --probe
--emit-prompt` on EVERY UserPromptSubmit turn while a marker is present. `--repeat-count` calls
`lazy_core.advance_forward_cycle(state, consume_gate=True)` (`lazy-state.py` ~line 13538).

`advance_forward_cycle` advances on `state_changed OR consume_rose`. On a notification turn the
routed `(feature_id, current_step, sub_skill)` tuple CHANGES (a completed background dispatch
flipped queue state), so `state_changed` is true with NO consume → a false forward advance. This
is systematic: notification turns are exactly the turns where the route changes without a
this-turn dispatch.

The prescribed fix (gate forward advance on consume, drop the bare state-change trigger on the
`consume_gate=True` inject path) **directly conflicts with two deliberate, one-day-old prior
decisions, each with a pinned test**:

- `test_advance_forward_cycle_consume_gate_advances_multicycle_same_step` (byref-forward-cycles-
  frozen-on-multicycle-same-step, **2026-07-16**) asserts that on the `consume_gate=True` path
  the FIRST probe advances via the state-change trigger at census 0 / no consume
  (`test_markers.py` ~line 5724-5726).
- `test_advance_forward_cycle_verbatim_real_skill_theory_1b` (Theory-1b) asserts a real-skill
  state change advances even on a consume-MISSED (verbatim) dispatch.

The two named failure modes are SYMMETRIC catastrophes: DEFECT 1 (over-count → false early
halt) vs. byref-forward-cycles-frozen / Theory-1b (under-count → `max_cycles` never trips →
unbounded overnight run). The consume oracle under-counts (non-monotonic under ring-cap
eviction / consume-missed verbatim dispatch); the state-change oracle over-counts (notification
turns). Neither oracle alone distinguishes "first probe of a genuine dispatch cycle" from
"notification turn" — both present as `state_changed AND no consume`.

Choosing consume-only (per the evidence) REVERSES a 2026-07-16 operator-sanctioned decision and
requires inverting/retargeting its pinned tests. Per `/harden-harness` Step 3 tiering and
Prohibition #2, a hardening agent must NOT silently bake a gate-semantics fork nor invert a
deliberate prior decision to make a symptom pass. → routed to
`docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` (with a concrete Recommendation: move the
advance off the inject/banner-emission path to actual dispatch time, so it is neither
state-change-on-notification nor consume-missed — see the sentinel).

### Fix scope

None implemented in this round (design fork). See
`docs/specs/turn-routing-enforcement/NEEDS_INPUT.md`.
