# Bug: `/lazy-batch-parallel` round-2 harness gaps (serial-tail merged-head withhold for lease-held items; `--ensure-runtime` killed under background launch)

**Status:** Concluded
**Reported via:** `/harden-harness` discovered-defect-batch dispatch (2026-07-18, item in flight `parallel-run-harness-gaps-round-2`, AlgoBooth `/lazy-batch-parallel` run, parent marker `2026-07-18T03:38:27Z`, blocking=true). Gap 8 is run-blocking (the coordinator serial tail cannot emit its `mcp-test` dispatch for a merged, lease-held item).
**Root-cause class:** batch — `script-defect` (gap 8), `missing-contract` (gap 9).
**Related:** `docs/bugs/lazy-batch-parallel-run-harness-gaps` (round-1 batch — gap 8 is the direct follow-on to that spec's Gap 1, which fixed the LANE probe form and explicitly noted lease-exclusion was insufficient *there*); `docs/bugs/dispatch-probe-and-inject-bypass-merged-head` (introduced the merged-head guard); `docs/specs/turn-routing-enforcement/` (hardening stage); `user/skills/lazy-batch-parallel/SKILL.md` (the parallel coordinator contract); `user/scripts/CLAUDE.md` (the `--ensure-runtime` reference).

## Context

Continuing the same first-real `/lazy-batch-parallel` run that surfaced the round-1 batch, two
further harness defects surfaced once the run reached the **post-merge validation tail**. Both
live in `claude-config` scripts/skills. Gap 8 is run-blocking (the coordinator's serial tail
cannot dispatch validation for a merged, lease-held item). Gap 9 is an operational-friction /
missing-contract defect on `--ensure-runtime`.

---

## Gap 8 — merged-head guard withholds the coordinator's SERIAL-TAIL emission for a merged, lease-held item (RUN-BLOCKING)

**Symptom (verified).** After lanes merged in queue order, the coordinator ran the serial
validation tail at the MAIN root, one merged item at a time. For a merged, lease-held item, the
dispatch-bound `--emit-prompt --feature-id polyphonic-parameter-modulation` probe returned
`route_overridden_by: merged-head-diverged` and WITHHELD the forward route, so the tail could not
emit its `mcp-test` cycle dispatch. Live probe JSON:
`{"route_overridden_by": "merged-head-diverged", "probed": "polyphonic-parameter-modulation",
"context": "main-root serial-tail emission; item lease-held and lane-merged"}`. The merged head
had become `inspector-track-dashboard` (freshly research-ingested → newly dispatchable and higher
priority), which diverged from the tail item.

**Root cause (`script-defect`).** Round-1 Gap 1 exempted the merged-head guard for the LANE probe
form: a lane marker carries a non-null `parent_run`, so `_emit_is_lane` short-circuits the guard
(`user/scripts/lazy-state.py:14021`, mirrored `bug-state.py:9667`). But the **post-merge
validation tail** probes run at the MAIN root against the PARENT marker, whose `parent_run` is
`null` — so `_emit_is_lane` is `False` and the serial-run priority-inversion guard runs. When a
freshly-dispatchable item became the merged head, the guard withheld the tail's route for the
merged, lease-held item, even though completing that item is the coordinator's obligation BEFORE
any new head work. The tail item holds a LIVE `lazy_coord` lease (`leases.json` in the main-root
state dir) and its lane branch is already merged; a live lease on the PROBED item means it is
actively-owned in-flight work (heartbeat fresh), never the stale route the guard exists to catch.

Round-1's Gap 1 spec explicitly noted that "also excluding LIVE-leased items from the merged-head
exclusion set" was INSUFFICIENT *for the lane case* — because the divergent head there
(`hydra-overlay`) was a serial-held item holding no lease, so lease-exclusion would not remove it.
The TAIL case is the mirror image: here the divergent head is a fresh non-leased item, so
excluding *other* lease-held items also would not clear it. The correct remedy is the second
alternative the round-1 evidence named: **exempt the probe when the probed `feature_id` itself
holds a live lease** — the exact analog of the lane exemption (a lane exempts on the
coordinator-arbitrated claim; the tail exempts on the probed item's own live lease, the
coordinator's in-flight completion obligation).

**Fix scope.**
- Add a pure, read-only `lazy_coord.has_live_lease(leases_path, wi_id, *, now=None) -> bool`
  helper that reuses `claim_shardable`'s exact liveness predicate (missing file/key → False;
  present-but-unreadable entry → True, conservative).
- In both emit blocks (`lazy-state.py` and its coupled-pair mirror `bug-state.py`), when the run
  marker is present, NOT a lane (`parent_run` null), and the probed `feature_id` holds a live
  lease in `claude_state_dir()/leases.json`, skip `merged_head_override` (leave
  `_merged_override = None`) with an observability diagnostic — structurally identical to the
  round-1 lane exemption. Fail-safe: any read error / no `leases.json` / no live lease → False →
  the guard runs exactly as before (byte-identical for every non-parallel serial run, which has no
  `leases.json`).
- Document the tail-emission lease exemption in `lazy-batch-parallel/SKILL.md`'s serial-tail step.

---

## Gap 9 — `--ensure-runtime` is killed when launched via a background shell (`run_in_background`)

**Symptom (verified).** `lazy-state.py --ensure-runtime` was KILLED when launched via the Bash
`run_in_background` mechanism (two consecutive kills, zero output bytes, instant termination); the
IDENTICAL foreground invocation succeeded (`state: READY`, `health_code: 200`). An earlier
background invocation hours before had succeeded, so the failure is STATE-DEPENDENT (an active run
marker was present at the time of the kills).

**Root cause (`missing-contract`).** `--ensure-runtime` is a Persistent-Service owner that already
does its OWN backgrounding internally: on a non-READY classification its recovery path spawns
`npm run dev:restart` (which runs a process-tree-killing `kill-dev.js` step in the target repo)
and then SYNCHRONOUSLY polls `/health` to 200 on a cold-compile-sized budget (up to ~7.5 min — see
`runtimeplane.restart()`, `user/scripts/lazy_core/runtimeplane.py:696`). The subcommand is
therefore contracted to run in the FOREGROUND as a blocking `Bash` call, with the orchestrator
owning it across the subagent turn boundary (`lazy-batch/SKILL.md:761`). Launching it *itself* via
`run_in_background` violates that implicit contract: (a) the synchronous health poll no longer
blocks the orchestrator as intended; (b) the recovery path's `dev:restart`/`kill-dev.js` process
sweep can reach the background launcher's own process tree, killing the `--ensure-runtime` process
before it writes any output (the observed instant, zero-byte kill under an active marker). The
foreground/background asymmetry is exactly this: the foreground call is a direct blocking child
that returns its verdict; the background launch is a detached tree the recovery sweep can catch.

The two contributing mechanisms — the target-repo `kill-dev.js` process-match set and the Claude
Code `run_in_background` process-tree lifecycle — are OUT of claude-config's edit scope (the
former is target-repo AGPL/product source, Prohibition #1; the latter is undocumented platform
behavior this session cannot dispatch `claude-code-guide` to confirm). Per the harden-harness rule
"prefer a design that does not depend on the undocumented behavior," the correct claude-config
resolution is the evidence-sanctioned **documented foreground-only contract** — which removes the
dependency on both mechanisms entirely rather than shipping load-bearing logic on an assumption
about either.

**Fix scope.** Make the foreground-only requirement EXPLICIT (it was implicit — never stated as a
prohibition):
- `user/scripts/CLAUDE.md` `--ensure-runtime` reference: add a FOREGROUND-ONLY contract sentence
  (the subcommand owns its own background `dev:restart` + a synchronous multi-minute health poll;
  never launch it via `run_in_background` — under an active marker the recovery `dev:restart`
  `kill-dev.js` sweep can kill a background launcher's own process tree).
- `lazy-batch-parallel/SKILL.md` serial-tail step: state that the tail's `--ensure-runtime` call is
  a FOREGROUND blocking `Bash` call, never backgrounded.

This is a documented contract, not a mechanical enforcement: `--ensure-runtime` has no reliable
in-process signal for "am I running detached in a background shell" (that is precisely the
undocumented platform behavior), so a prose contract at the invocation SSOT is the honest,
non-gate-weakening resolution the evidence explicitly offered ("a fix OR a documented
foreground-only contract").

---

## Verification

- Gap 8: a subprocess `lazy-state.py --repeat-count --probe --emit-prompt --feature-id <item>`
  with a SERIAL parent marker (parent_run null), a divergent P0/higher-priority merged head, AND a
  live lease on `<item>` in `leases.json` must NOT withhold (`route_overridden_by !=
  merged-head-diverged`); the SAME fixture with NO lease must still withhold (lease-gating proof).
  Plus a `lazy_coord.has_live_lease` unit fixture (live / expired / missing-key / missing-file).
- Gap 9: no code path to test (documented contract); verified by the `--ensure-runtime` reference +
  parallel serial-tail step carrying the explicit foreground-only prohibition.
