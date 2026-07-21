# lazy-cycle-containment's agent_id trip denies --enqueue-adhoc for a standalone (non-lazy-run) dispatched subagent

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-20 (manual trigger 5 — discovered mid-round during a separate, already-completed `/harden-harness` invocation; recorded as a follow-up in `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Round 132)
**Fixed:** 2026-07-20
**Fix commit:** 0bcc34c8
**Related:** `turn-routing-enforcement` (`lazy-cycle-containment.sh` C2 / `lazy_core.markers.refuse_if_cycle_active` C3); `hardening-blind-to-process-friction` (the D4 arming-free agent_id-targeted redesign); `dispatched-harden-record-intervention-refused-by-containment` (the prior, structurally analogous fix for `--record-intervention`)

## Trigger

`user/hooks/lazy-cycle-containment.sh`'s agent_id-targeted D4 trip (`LOOP_FORMATION_FLAGS`,
which includes `--enqueue-adhoc`) denies `lazy-state.py --enqueue-adhoc` (and every other
`LOOP_FORMATION_FLAGS` member) for **any** dispatched subagent (`is_subagent =
bool(payload.get("agent_id"))`) **unconditionally, with no cycle-marker check** ("arming-free"
by explicit design — see the hook's own header comment, lines ~8-20).

This conflicts with `~/.claude/skills/harden-harness/SKILL.md`'s own documented "Over-fit
spin-off" step (§Step 3), which instructs: "invoke the generalization skill via the
`adhoc-enqueue` protocol... Use the `--type bug` front-enqueue path" — i.e. run `lazy-state.py
--enqueue-adhoc --type bug ...` directly. That instruction is **unreachable** any time
`/harden-harness` itself runs as a dispatched Agent/Task subagent (`agent_id` present) with **no
live lazy-pipeline run marker** — which is exactly the deployment shape `~/.claude/CLAUDE.md`'s
auto-invoke directive prescribes for the common case: "NO marker active (standalone session, or
after `--run-end`): dispatch a plain general-purpose `Agent` subagent whose prompt invokes
`/harden-harness`."

### Reproduction (confirmed live 2026-07-20, dispatched-subagent context)

With no `lazy-run-marker.json` present (`lazy-state.py --marker-present --repo-root .` exits 1)
and no `lazy-cycle-active.json` cycle marker present, running:

```
python3 user/scripts/lazy-state.py --enqueue-adhoc --type bug --id "<slug>" --name "<name>" \
  --brief "<brief>" --repo-root .
```

via the Bash tool was DENIED by the PreToolUse hook with:

> "you are a single cycle subagent — STOP after your commit+push+report; routing the next
> cycle is the orchestrator's job. This op (lazy-state.py routing/lifecycle, dev:kill/restart,
> a /lazy* skill or nested batch invocation, or a second-feature/over-ceiling commit) is DENIED
> in-flight while a cycle dispatch is active."

— even though no cycle dispatch was in fact active (no marker of either kind existed).
Contrast: `--archive-fixed` and `--link-provenance` (NOT in `LOOP_FORMATION_FLAGS`) succeeded
fine from the same subagent context in the same session — this is a `LOOP_FORMATION_FLAGS`-
specific gap, not a blanket containment-vs-subagent problem.

This exact gap was first surfaced (not fixed) in `hardening-log/2026-07.md` Round 132, whose
own over-fit spin-off attempt (`--enqueue-adhoc --type bug`) tripped this same defect — Round
132 recorded the recommended fix text and deferred implementation to a dedicated follow-up
round (this bug / Round 133) rather than rider-fixing a containment/deny mechanism inline.

## Reconstructed route (divergence point)

- `lazy-cycle-containment.sh` main(): `is_subagent = bool(payload.get("agent_id"))`. When
  `is_subagent` is True, the loop-formation branch (`_STATE_PY_INVOKE_RE` match →
  `LOOP_FORMATION_FLAGS` membership check) denies **regardless of `marker`** (the cycle marker
  read earlier in `main()` is consulted only for the 2nd-feature/commit-ceiling tripwires
  further down, never for this branch).
- `/harden-harness/SKILL.md` §Step 3 "Over-fit spin-off" instructs an `--enqueue-adhoc --type
  bug` (or `--type feature` via `/spec`) front-enqueue as part of its documented, mandatory
  spin-off protocol — with **no branch for "I am a standalone dispatched subagent with no
  orchestrator to hand back to."**
- `~/.claude/CLAUDE.md`'s own `<auto-invoke>` block prescribes dispatching `/harden-harness` as
  exactly that: a plain, unmanaged `Agent` subagent, with **no lazy run marker**, for the common
  "gap discovered outside any marked run" case.

**Divergence point:** the C2 hook's `is_subagent` discriminator conflates two distinct
concepts — "this call comes from *any* dispatched subagent" (which is all `agent_id` presence
actually proves) vs. "this call comes from a subagent that is *part of an active lazy pipeline
cycle*" (the actual threat the hook exists to contain). Every real /lazy-batch(-bug-batch)(-cloud)
cycle subagent is, by construction, dispatched while a **run marker** is live (the run marker is
written once at `--run-start`, before any cycle dispatch, and cleared once at `--run-end`) — but
the hook's `LOOP_FORMATION_FLAGS` branch never consults that fact, so it also catches subagents
dispatched completely outside any lazy run (e.g. a standalone `/harden-harness` invocation).

## Root cause

**`root_cause_class: missing-contract`** — the D4 "arming-free" redesign
(`hardening-blind-to-process-friction` Phase 1) was scoped, by its own SPEC text, to "the
literal incident": a subagent dispatched *by a live `/lazy-batch` cycle* attempting to
self-route. It did not anticipate a legitimately-dispatched subagent that is **not** part of any
lazy pipeline run at all needing one of the exact ops on the deny list — a genuinely novel
situation the original design had no contract for (structurally identical in shape to the prior
`dispatched-harden-record-intervention-refused-by-containment` fix, which closed the analogous
gap for `--record-intervention` on the **C3** side by keying an exemption off the cycle marker's
`sub_skill`; this bug is the **C2** counterpart, but the marker `sub_skill` keying doesn't apply
here since the reported scenario has *no marker at all*).

Contrast with the C3 script-level discipline (`lazy_core.markers.refuse_if_cycle_active`,
`user/scripts/CLAUDE.md` "C3 refuse-by-construction"): it decides subagent-vs-orchestrator via
`LAZY_ORCHESTRATOR` env → `LAZY_CYCLE_SUBAGENT` env → cycle-marker-present fallback. With no env
vars set and no cycle marker present, C3 falls through and **allows** — it would **not** have
refused the reproduced call. The C2 hook is *stricter* than the C3 script it exists to provide
defense-in-depth for, in a way that breaks a documented, sanctioned workflow instead of only
catching genuine runaways.

## Fix scope

Narrow `--enqueue-adhoc`'s denial — and **only** `--enqueue-adhoc`'s — to fire for a subagent
only while a **live RUN marker** (`lazy-run-marker.json`, resolved via
`lazy_core.read_run_marker()`, the same read `lazy-state.py --marker-present` performs) is
present for the current repo. A new `RUN_MARKER_GATED_FLAGS = frozenset({"--enqueue-adhoc"})`
constant plus a `_run_marker_present(cwd)` helper (fail-**closed** toward "a run is active" on
any resolution error, so a broken read never weakens the deny, it only ever loses the
relaxation) implement this in `lazy-cycle-containment.sh`.

**Why the RUN marker and not the CYCLE marker:** the D4 redesign's whole point was to stop
depending on the per-dispatch `--cycle-begin`/`--cycle-end` bracket ("arming-free") because an
orchestrator that forgets to bracket a dispatch would otherwise leave a genuine runaway
undetected. The RUN marker is written once at `--run-start` (before *any* cycle dispatch) and
cleared once at `--run-end`, spanning a run's *whole* lifetime — so gating on it does **not**
reintroduce that arming gap: even if the orchestrator forgets a single dispatch's
`--cycle-begin`, the RUN marker is still present for the run's duration, and a genuine runaway
cycle subagent's `--enqueue-adhoc` calls stay denied exactly as before. Only the genuinely
orthogonal case — **no lazy run active anywhere in this repo** — is relaxed, and in that case
there is no orchestrator loop or queue-priority ordering to protect from a subagent's
`--enqueue-adhoc` (it can only append a stub item + `ADHOC_BRIEF.md`/SPEC for a *future* run to
pick up under the exact same containment; it cannot advance or hijack a run that does not
exist).

**Every other `LOOP_FORMATION_FLAGS` member stays unconditionally (arming-free) denied for a
subagent** — `--probe`, `--emit-prompt`, `--repeat-count`, `--repeat-count-peek`, `--run-start`,
`--run-end`, `--apply-pseudo`, `--emit-dispatch`, `--cycle-begin`, `--cycle-end`. None of them
has a legitimate standalone-subagent use (unlike `--enqueue-adhoc`, which is the one op
`/harden-harness`'s own documented contract calls directly), and — critically — `--run-start`
itself must never become callable by a bare dispatched subagent with no run marker present
(that would let *any* subagent bootstrap a brand-new lazy run), so it is deliberately excluded
from `RUN_MARKER_GATED_FLAGS`.

C3 (`refuse_if_cycle_active`) is **unchanged** — it already behaves correctly for the reported
scenario (see above); no divergence between C2 and C3 is introduced by this fix for the
untouched flags, and the fix brings `--enqueue-adhoc` specifically into closer (though not
identical — C3 gates on the cycle marker, C2 now gates on the run marker, deliberately, per the
arming-gap rationale above) alignment between the two layers.

## Verified symptom → target signal

- **Before:** a dispatched subagent (any `agent_id`) with no lazy run marker present, running
  `lazy-state.py --enqueue-adhoc ...`, is denied (`loop-formation-flag` signature).
- **After (target):** the identical invocation, still with no run marker present, is **allowed**
  (falls through to the "real state-script invocation, no denied routing flag → allow" path). A
  dispatched subagent's `--enqueue-adhoc` call while a run marker **is** live for this repo
  still denies exactly as before (unchanged). Every other `LOOP_FORMATION_FLAGS` member's
  unconditional denial for a subagent is byte-identical to before, with or without a run marker.
  Measured signal: `event:containment-refusal` / `loop-formation-flag` count for `--enqueue-adhoc`
  specifically decreases to zero for the no-run-marker case; unchanged for the live-run case.
