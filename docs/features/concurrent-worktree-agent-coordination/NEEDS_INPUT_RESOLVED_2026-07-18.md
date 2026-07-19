---
kind: needs-input
feature_id: concurrent-worktree-agent-coordination
written_by: spec
class: product
stub_origin: true
decisions:
  - Lock granularity — per-file vs per-directory vs per-queue-item
  - Semantic-vs-non-semantic conflict discriminator
  - Temp-worktree merge-back lifecycle
  - Cross-agent communication channel for the merge-back path
date: 2026-07-18
next_skill: spec
---

# /spec --batch — Needs Input

This is a stub/pre-baseline `/spec` Phase-1 halt: the four decisions below shape a baseline the operator has never seen (the ad-hoc brief names them explicitly as "design forks to surface at /spec"). Each changes observable coordination behavior, so each is surfaced rather than auto-accepted. Research (Phase 2) can inform them but cannot decide them — they are product-authority calls.

## Decision Context

### 1. Lock granularity — per-file vs per-directory vs per-queue-item

**Problem:** The FIFO file-lock (Requirement 3) makes contending agents proceed in turn by waiting on a lock before writing. The lock's GRANULARITY decides what actually serializes: too coarse and unrelated concurrent work is needlessly blocked (throughput loss); too fine and the lock misses real conflicts on the same logical artifact. This is the load-bearing knob for how much concurrency the system actually permits, and it is observable (agents visibly wait, or visibly don't). The lock substrate is the existing `lazy_coord.py` `os.mkdir` global lock + fencing leases (`leases.json`), keyed today at the queue-item level for lanes.

**Options:**
- **Per-queue-item lock (Recommended)** — one lock per feature/bug item (the unit `lazy_coord.py` already leases for parallel lanes). Coarser but reuses the existing lease keying with near-zero new surface; two agents on the SAME item serialize, two agents on DIFFERENT items never block. Cost: two agents editing different files *within the same item* serialize unnecessarily — acceptable because same-item concurrent work is rare and usually genuinely conflicting. Lowest complexity, strongest reuse, reversible (granularity can be refined later without changing the substrate).
- **Per-file lock** — one lock per file path. Maximum concurrency (only true same-file contention blocks). Cost: a lock namespace keyed on every path, stale-holder reclamation per path, and it still misses *semantic* conflicts that span files (two agents editing different files that are logically coupled) — so it needs the semantic discriminator (Decision 2) to carry more weight. Highest complexity.
- **Per-directory lock** — one lock per directory (e.g. a feature dir, `user/scripts/`). Middle ground: coarser than per-file, finer than per-item; a natural fit for "one writer per doc surface." Cost: directory boundaries don't align cleanly with logical artifacts (a change often spans `user/scripts/` + `user/skills/`), so it both over- and under-blocks depending on layout.

**Recommendation:** Per-queue-item lock — it reuses the `lazy_coord.py` lease keying verbatim, matches the "one writer per work item" mental model the pipeline already enforces, and keeps v1 simple; per-file is a documented vN refinement if same-item throughput becomes a real constraint.

### 2. Semantic-vs-non-semantic conflict discriminator

**Problem:** When a write conflict is detected, the system must classify it: a NON-semantic conflict routes to the non-halting path (retry/queue, or temp-worktree merge-back) and a SEMANTIC conflict HALTS with `NEEDS_INPUT.md` (class `product`, never auto-accepted). This discriminator is the single most behavior-defining decision in the feature — it decides when a run pauses for a human vs. proceeds autonomously. A wrong "non-semantic" call silently merges logically-incompatible work; a wrong "semantic" call halts a run that could have proceeded.

**Options:**
- **Git-mergeability + coupled-surface heuristic (Recommended)** — treat a conflict as NON-semantic when git can auto-merge it (no conflict markers) OR the conflicting hunks touch disjoint logical surfaces (different files/decision-doc sections with no shared symbol); treat it as SEMANTIC when git reports an un-auto-resolvable conflict on the SAME logical artifact (same function, same Locked-Decision row, same sentinel). Deterministic, cheap, reuses git as the first-pass oracle; conservative (an ambiguous case falls to SEMANTIC/halt — the fail-safe direction, mirroring the Spike-FAIL "unknown → don't auto-accept" bias). Cost: the coupled-surface heuristic needs a small, maintained notion of "same logical artifact."
- **Git-textual-only** — non-semantic iff git auto-merges cleanly; any conflict marker = semantic/halt. Simplest and fully deterministic. Cost: over-halts — two agents appending to the same changelog/queue produce a textual conflict that is trivially non-semantic, yet this always halts; loses the "large non-semantic conflict → merge-back" value entirely.
- **Operator-flagged only** — every conflict is non-semantic (retry/merge-back) unless an agent explicitly raises a semantic flag. Maximizes autonomy/throughput. Cost: fail-OPEN in the dangerous direction — silently merges incompatible work unless someone noticed; contradicts the brief's "genuine semantic conflict → HALT, no auto-accept" requirement.

**Recommendation:** Git-mergeability + coupled-surface heuristic — it is deterministic, conservative in the safe direction (ambiguous → halt), and preserves the merge-back path for the common trivially-non-semantic case (concurrent appends) that git-textual-only would needlessly halt.

### 3. Temp-worktree merge-back lifecycle

**Problem:** For a large/complex but NON-semantic conflict, the orchestrator completes the work in a temporary worktree, then merges back and resolves. The LIFECYCLE — who creates the worktree, when, on which branch, and how the merge-back resolves — must be pinned. This governs orchestrator behavior and where a run's git history lands. The harness already has two relevant precedents: `lazy_coord.py`'s lane machinery (`lanes.json` ledger, `merge_order`, `merge_lane_branch` with abort-and-demote) and `lazy_core.run_transient_build`'s orchestrator-owned transient worktree.

**Options:**
- **Reuse `lazy_coord.py` lane machinery (Recommended)** — spin the temp worktree as a coordinator lane (`lane/<item-id>` + lane marker + fencing lease), do the work there, and merge back in queue order via the existing `merge_lane_branch` (abort-and-demote on conflict, lane branch preserved). Maximum reuse of a tested, sanctioned merge-back path; the `lanes.json` ledger already records claims/merges/demotions for audit. Cost: lane machinery is workstation-only v1 and feature-pipeline-shaped — a cloud/bug path needs the two-implementation treatment or a documented scope limit.
- **Orchestrator-owned transient worktree (`run_transient_build` precedent)** — the orchestrator creates a throwaway worktree (the long-build takeover precedent), completes the work, merges back inline, discards the worktree. Lighter than the full lane ledger; already the sanctioned "orchestrator owns the isolated build" contract. Cost: no built-in queue-order merge / demote-on-conflict ledger — that logic would be re-authored.
- **Inline stash + rebase (no worktree)** — no separate worktree; stash local work, fetch/rebase onto the conflicting agent's commit, re-apply. Cheapest. Cost: rebasing a large/complex change in the live worktree is exactly the risky path the brief wants to AVOID for large conflicts (it mutates the shared tree mid-conflict); best reserved for the small-conflict retry path, not the large one.

**Recommendation:** Reuse the `lazy_coord.py` lane machinery — it is the only precedent that already carries queue-order merge + demote-on-conflict + an audit ledger, which is exactly the large-non-semantic-merge-back shape; the workstation-only limit is acceptable for v1 with the cloud path documented as a follow-up.

### 4. Cross-agent communication channel for the merge-back path

**Problem:** When this agent beats the conflicting agent to the merge, it must COMMUNICATE to the other agent that conflicts should be expected and how to resolve them. The CHANNEL determines whether the other agent reliably receives the message. The other agent is a separate session that will `git fetch`/rebase and re-observe the shared tree; the channel must be something it is bound to see.

**Options:**
- **Commit-message convention the other agent reads on fetch/rebase (Recommended)** — the merging agent writes a structured marker into its commit message (e.g. a `Concurrent-Merge-Back:` trailer naming the affected paths + resolution guidance). The conflicting agent, which must fetch/rebase to push, sees it in the incoming history it is bound to process. Zero new state files, survives across sessions and clones, naturally scoped to the exact commits that caused the conflict. Cost: parsing a convention out of commit messages is slightly less structured than a dedicated file; needs a documented trailer grammar.
- **Sentinel/marker file in the shared tree (e.g. `CONCURRENT_CONFLICT.md`)** — the merging agent drops a sentinel the other agent reads at cycle start. Structured, easy to schema-validate, fits the existing sentinel-driven state machine. Cost: a shared-tree file is itself contended (the exact problem this feature solves), risks being clobbered/merged, and must be cleaned up — adding a lifecycle to manage.
- **Deny-ledger / `hook-events.jsonl` append** — record the merge-back + guidance in the per-repo keyed event ledger the other agent's tooling already reads. Structured, out-of-tree (no shared-file contention). Cost: the ledger is per-repo-keyed state, not guaranteed to be read by an arbitrary concurrent session at the right moment; it is an observability channel, not a coordination one.

**Recommendation:** Commit-message convention — it rides the fetch/rebase the conflicting agent MUST perform to push, needs no new contended state, and is scoped to exactly the conflicting commits; a documented trailer grammar makes it parseable enough for the resolution guidance.
