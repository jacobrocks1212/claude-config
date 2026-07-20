# Harden rounds fix docs/bugs items out-of-pipeline but never complete the docs/bugs/CLAUDE.md reconciliation contract

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-18
**Fixed:** 2026-07-18
**Fix commit:** 364d0525
**Related:** `docs/bugs/CLAUDE.md` (the "Fixing a bug OUT-OF-PIPELINE" reconciliation contract this
bug is about); `docs/bugs/_archive/dispatch-probe-and-inject-bypass-merged-head/`,
`docs/bugs/_archive/merged-head-excludes-parked-not-operator-deferred-deadlocks/`,
`docs/bugs/_archive/merged-head-includes-parked-items-deadlocks-park-run/` (the three un-reconciled harden
bug specs that surfaced this class); `docs/specs/turn-routing-enforcement/` (the hardening stage);
`user/skills/harden-harness/SKILL.md` (Step 2.5 authors the spec, Step 3 ships the fix — neither
reconciles it).

## Trigger

Orchestrator-observed friction across THREE consecutive pipeline cycles of one live `/lazy-batch`
run on claude-config (2026-07-18). Each cycle burned a full `/plan-bug` dispatch that discovered
the bug SPEC's ENTIRE fix scope was ALREADY implemented and committed by an earlier
`/harden-harness` round, with the SPEC still sitting at `**Status:** Concluded` — no `FIXED.md`
receipt, no `--archive-fixed`, no provenance link:

- `dispatch-probe-and-inject-bypass-merged-head` — fix shipped as `1af48e1d` (Round 54);
- `merged-head-excludes-parked-not-operator-deferred-deadlocks` — fix shipped as `84e656ec` (Round 57);
- `merged-head-includes-parked-items-deadlocks-park-run` — fix shipped as `a8140ff8` (Round 56);
  this one has since had a `PHASES.md` authored, so it is now genuinely mid-pipeline and completes
  via the normal tail (it is NOT part of the reconciliation instance-fix — do not archive it).

Two of the three (`dispatch-probe-...`, `merged-head-excludes-...`) had a `/plan-bug` cycle
write a `NEEDS_INPUT.md` recommending EXACTLY the reconciliation action (`--archive-fixed` +
`--link-provenance`) — the pipeline correctly diagnosed the un-reconciled state, but only after
spending a full plan-bug dispatch to do so.

## Verified symptom

`bug-state.py::load_bug_queue` auto-discovers every open `docs/bugs/<slug>/` dir. A
`/harden-harness` round authors its Step-2.5 investigation spec at `docs/bugs/<slug>/SPEC.md`
(`**Status:** Concluded`) and ships the fix as its Step-3 mechanical commit — but the fix lands
OUT-OF-PIPELINE (a `harden(script):`/`harden(skill-prose):` commit, never the bug pipeline's
`__mark_fixed__` path). Nothing then reconciles the spec, so it lingers at `Concluded` and the
merged-head unified driver re-drives it via `/plan-bug` as apparently-unfixed work.

`bug-state.py --fsck` does NOT catch this state: the spec sits at `**Status:** Concluded`, not
`Fixed`, so none of `--fsck`'s three checks (`unarchived-fixed` / `fixed-without-receipt` /
`stale-queue-entry`, all of which key on `**Status:** Fixed`) fire. Confirmed live this cycle:
`bug-state.py --repo-root . --fsck` → `{"ok": true, "violations": []}` while all three bugs sat
un-reconciled at `Concluded`.

## Root cause

**Class: missing-contract.** The reconciliation contract EXISTS — `docs/bugs/CLAUDE.md` →
"Fixing a bug OUT-OF-PIPELINE" mandates that a session fixing a `docs/bugs/<slug>/` defect outside
the bug pipeline MUST either FINISH the contract (write `FIXED.md` + `--archive-fixed`) or leave
`**Status:**` untouched. But `harden-harness/SKILL.md` has NO step that wires that contract into
the harden workflow: Step 2.5 authors the spec, Step 3 ships the fix, Step 4 writes the log — none
reconciles the spec the round just fixed. So harden rounds systematically leave a `Concluded`
spec with the fix already shipped, and nothing enforces otherwise.

A compounding structural constraint (verified live this cycle): a DISPATCHED harden round runs as
a **meta-cycle subagent** (the run's `lazy-cycle-active.json` carries `sub_skill: harden-harness`),
so the reconciliation's two mutating ops — `bug-state.py --archive-fixed` and
`lazy-state.py --link-provenance` — are **orchestrator-only** and are REFUSED for it
(`refuse_if_cycle_active` → exit 3; confirmed: `--link-provenance` returned
`REFUSED: ... orchestrator-only operation and you are a single cycle subagent`). Exempting those
ops for a hardening subagent would widen the containment bypass surface (a queue-mutating +
`git mv` op) — that is gate-weakening, out of bounds. So the reconciliation must be MODE-AWARE:
inline manual harden reconciles directly; a dispatched harden hands the two orchestrator-only ops
back to the orchestrator (authorized for them — the same ops it already runs on the normal
archive-on-fix path).

## Fix scope

1. **`user/skills/harden-harness/SKILL.md` — new Step-3 reconciliation subsection** stating the
   `docs/bugs/CLAUDE.md` contract, mode-aware (inline reconciles directly; dispatched hands back
   via a `reconcile:` Return field; partial / mid-pipeline leaves Status untouched with an explicit
   deferral). Never a silent `Concluded` exit with the fix shipped.
2. **`bug-state.py --fsck` added to the Step-3 gate list** (read-only; runs for a subagent) —
   surfaces any `unarchived-fixed` / `fixed-without-receipt` / `stale-queue-entry` debt each round
   (defence-in-depth for the half-reconciled state, complementing the SKILL contract which owns the
   `Concluded`-limbo state `--fsck` cannot see).
3. **Return format gains a `reconcile` field**; the Step-4 round template gains a
   `**Reconciliation:**` line.
4. **`lazy-batch` + `lazy-bug-batch` §1d.1 honor step** (coupled pair): after a harden dispatch
   returns, if its summary carries a `reconcile:` handback, the orchestrator runs the named
   `--archive-fixed` + `--link-provenance` (it is authorized — same ops as the normal
   archive-on-fix path), closing the contract for harden-authored bug specs.

**Instance fix (this round, handed back — the dispatched harden is cycle-blocked from the two
mutating ops):** reconcile `dispatch-probe-and-inject-bypass-merged-head` and
`merged-head-excludes-parked-not-operator-deferred-deadlocks` (both `NEEDS_INPUT.md`-recommended)
plus THIS spec via the orchestrator (`FIXED.md` + `--archive-fixed` + `--link-provenance`); leave
`merged-head-includes-parked-items-deadlocks-park-run` (mid-pipeline via its `PHASES.md`).
