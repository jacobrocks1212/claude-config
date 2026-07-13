---
kind: implemented
feature_id: parallel-worktree-batch-execution
date: 2026-07-12
provenance: operator-directed-interactive
derivation: message-grep
commits: [47d2e582, 65b340fd, 5bd4cae9, dde89eac, 40406497, 0c40bd7b, 208644bd, dae1977c,
  3fbbf02e, 9126dad1, 4ddca35f, 1a3dffd1, 4015bb78, 5ff570bf, 0e899e30]
decisions: [D1, D2, D3, D4, D5, D6, D7, D8, D9, D10]
---

# Implementation Ledger

**What shipped:** A sanctioned coordinator (`/lazy-batch-parallel`, `user/skills/lazy-batch-parallel/SKILL.md`)
that shards dependency-independent, `independent: true`-marked feature queue items across git
worktree lanes and coordinates them to completion, extending — never weakening — every existing
arbitration layer (`refuse_run_start_clobber`, born-owner-bound single-slot marker ownership,
per-repo keyed state dirs, the containment hook family). Each lane is an isolated worktree
checkout with its own branch, its own per-worktree keyed state dir, its own lane run marker
(born owner-bound to the coordinator session, stamped with a `parent_run` identity field), and a
`lazy_coord.py` fencing-token lease. The coordinator remains the single writer of every contended
resource (`queue.json`, ROADMAP, `LAZY_QUEUE.md`, the work branch) and merges completed lane
branches back in deterministic queue order, demoting any conflicting item to a serial re-run on
the merged tree. `user/scripts/lazy_coord.py` gained the whole concurrency plane's lane layer:
`claim_shardable` (conservative dep-ready ∧ `independent:true` ∧ no-live-lease predicate),
`lanes.json` ledger + atomic writers, `merge_order` (deterministic queue-order), `merge_lane_branch`
(real git merge with abort-and-demote on conflict), `flush_summary`, `effective_lanes` /
`lane_budget_slice` (budget arithmetic), and `lane_branch` / `lane_pool_dir` conventions, plus a
D10 param-generalization of the pre-existing `provision_pool`/`scrub_slot` worktree-pool machinery
(byte-compatible defaults for the Cognito/`lazy-worker` callers). `lazy_core.py`'s
`write_run_marker` gained the `parent_run` identity field (always minted, `null` on serial runs,
classified `RUN_FRESH_FIELDS`); both state scripts thread `--parent-run <json>` on `--run-start`
(coupled-pair mirror). `/lazy-status` renders lane rows from the ledger when one exists;
`/lazy-batch-retro` Step 6f reads `lanes.json` and flags every `demoted: serial` entry as a
false-`independent`-marker audit finding. `user/scripts/CLAUDE.md` documents the whole plane under
"Concurrency plane — sanctioned parallel worktree lanes"; root `CLAUDE.md` notes the skill as a
composed family member of the `/lazy-batch` family (not a coupled pair, since it composes the
serial contract by reference rather than mirroring its prose). Feature-pipeline-only,
workstation-only v1 (claude-config + AlgoBooth) — both documented, justified divergences.

All six phases (Phase 1 shardability predicate + lane ledger; Phase 2 worktree lanes + lane
markers; Phase 3 lane execution-loop support incl. the zombie-lane fencing fail-safe; Phase 4
queue-order merge + abort-and-demote; Phase 5 failure isolation + flush accounting + per-lane
friction fixtures; Phase 6 the coordinator skill + status/retro surfaces + docs) landed across
prior checkpointed sessions culminating in a direct-to-`main` finalization after the 2026-07-04
spend-limit checkpoint (see `HANDOFF.md`). This session verified the full gate suite green
(`lazy_coord.py --test` 21/21, `lazy_parity_audit.py` exit 0, `generate-coupled-skills.py --check`
byte-identical, `lint-skills.py --check-projected --check-capabilities` clean, `project-skills.py`
clean across all discovered repo projections), confirmed zero remaining unchecked PHASES
deliverables, ticked the two Phase 6 `<!-- verification-only -->` rows against that evidence, and
closed the one open gap (this feature's own SPEC lacked the self-referential
`**Friction-reduction feature:**` classification + `## KPI Declaration` its own gate would demand
of any other friction-reduction feature).

**Decisions that drove it:** D1 (new coordinator skill `/lazy-batch-parallel`, workstation-only v1:
claude-config + AlgoBooth — composes rather than edits the frozen serial `/lazy-batch` contract) ·
D2 (per-worktree keyed lane markers born owner-bound to the coordinator session under one parent
marker + `lazy_coord` fencing leases per item — every existing single-slot-ownership invariant
applies verbatim per lane) · D3 (independence = dep-DAG readiness ∧ `independent: true` marker ∧
no live lease; NO file-overlap prediction — merge-conflict demotion is the deterministic safety
net) · D4 (lanes run spec→implementation; the coordinator owns validation + completion; queue-order
merge, never completion-order; conflict ⇒ abort + demote-to-serial with the lane branch preserved)
· D5 (park-on-sentinel: a halting lane parks, siblings continue, the sentinel is ported verbatim to
the canonical tree at flush) · D6 (lane count = `min(requested, shardable count, pool_size)`; the
parent `max_cycles` is the aggregate budget SSOT; each lane gets a per-lane ceiling slice) · D7
(contended-resource single-writer: only the coordinator, at the main root, under the global lock,
after fencing) · D8 (heavy-build arbitration reuses existing machinery — `build-queue.ps1` FIFO /
`long-build-ownership-guard.sh` takeover — no new machinery) · D9 (containment hooks unchanged,
armed per lane; the one new obligation is per-lane `--cycle-end` friction-detector fixtures) · D10
(worktree-pool generalization: `cognito_root` → `repo_root`, parameterized branch template +
detach target, `lazy_coord.py` stays stdlib-only and never imports `lazy_core`).

**Receipt: COMPLETED.md (provenance: operator-directed-interactive).**
