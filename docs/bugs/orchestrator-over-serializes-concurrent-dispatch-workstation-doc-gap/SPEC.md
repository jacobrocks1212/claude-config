# orchestrator-over-serializes-concurrent-dispatch-workstation-doc-gap

**Status:** Concluded
**Kind:** bug (harness friction — missing durable contract)
**Pipeline:** claude-config (out-of-pipeline `/harden-harness` fix)

## Symptom (observed friction)

The lazy orchestrator on this workstation (DESKTOP-GHTC5K6) defensively **over-serializes
concurrent dispatches** — e.g. it holds a background `/harden-harness` (or another concurrent
worker) until an in-flight cycle's boundary — on the **mere possibility** of write contention
against the shared claude-config worktree. This is redundant defensive serialization: the
concurrent-writer coordination layer already handles genuine contention robustly, so the delay
buys nothing and costs throughput.

## Root cause (classification: `missing-contract`)

The user-global `<orchestration>` policy and the `/lazy-batch` HARD CONSTRAINT 11
("Concurrent-writer awareness — no monsters-in-the-closet serialization", SKILL.md line 40)
already state the correct behavior: dispatch concurrently, trust the coordination layer, treat a
moved HEAD / incoming commit as EXPECTED. But **this machine's workspace CLAUDE.md**
(`workspace/CLAUDE.DESKTOP-GHTC5K6.md`, projected to `~/source/repos/CLAUDE.md` on this box) —
the doc an orchestrator working *in this worktree* reads for local pipeline context — carries **no
durable statement** of that policy. The local contract is absent, so the orchestrator falls back
to a cautious serialize-on-possibility posture instead of the sanctioned concurrent-dispatch one.

The shipped `concurrent-worktree-agent-coordination` feature is what makes concurrent dispatch
safe: the FIFO per-item file-lock (`lazy_coord.py` `acquire_item_lock` / `release_item_lock`; the
PowerShell plane `concurrent-lock.ps1`; one documented grammar in
`user/skills/_components/concurrent-lock-contract.md`) + git-safety + conflict-routing
(`lazy_core.py`) serialize genuine write contention and halt only on a true SEMANTIC conflict.
That safety is real but was **not discoverable** from the workstation doc.

## Verified

- HARD CONSTRAINT 11 present at `user/skills/lazy-batch/SKILL.md:40` (canonical policy SSOT).
- User-global `<orchestration>` "Concurrent-writer awareness" block present in `~/.claude/CLAUDE.md`.
- `concurrent-lock-contract.md` present under `user/skills/_components/`.
- `workspace/CLAUDE.DESKTOP-GHTC5K6.md` had **no** concurrent-writer / coordination subsection
  (grep miss) prior to this fix.

## Fix scope

Add a tight `### Concurrent-writer coordination` subsection to
`workspace/CLAUDE.DESKTOP-GHTC5K6.md` (near the Scheduled Autonomous Runs / pipeline content)
that durably records:

1. This worktree has robust multi-writer coordination from the shipped
   `concurrent-worktree-agent-coordination` feature (FIFO per-item file-lock + git-safety +
   conflict-routing; `lazy_coord.py` / `lazy_core.py`, `concurrent-lock-contract.md`) — genuine
   contention is serialized; only a true SEMANTIC conflict halts.
2. THEREFORE the orchestrator must NOT pre-serialize or delay a dispatch on the mere possibility
   of contention — dispatch concurrently and trust the layer; a moved HEAD / incoming commit is
   EXPECTED, not a defect. Cross-references the global `<orchestration>` policy + HARD CONSTRAINT
   11 rather than duplicating them wholesale.
3. The ONE real caveat: the single-slot cycle-active marker
   (`~/.claude/state/lazy-cycle-active.json`) — a concurrently-dispatched background worker must
   NOT open a competing `--cycle-begin` bracket while an in-flight cycle holds it (that clobbers
   the running cycle's `--cycle-end` accounting); dispatch the concurrent worker via the
   registered emit-dispatch path WITHOUT a competing bracket instead.

Doc/config change only — no code path, no ledger signal.

## Locked Decisions

1. Record the policy as a **cross-reference** to the global SSOT, not a wholesale duplicate — the
   workstation doc points at `<orchestration>` + HARD CONSTRAINT 11 so the policy has one home.
2. Scope the fix to the workstation workspace doc only. The machine-agnostic `workspace/CLAUDE.md`
   (work laptop) is out of scope for this observed friction (the friction was observed on this box).
