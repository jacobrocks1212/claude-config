# Deep Research: Safe Concurrent Multi-Agent Work on a Shared Git Worktree/Branch

## Research Question

We are building coordination primitives that let **multiple autonomous AI-agent sessions operate concurrently on the SAME git worktree and branch** (e.g. a long-running autonomous pipeline session while a human operator — or a second scheduled session — also commits to the same `main`) **without false-panic, data loss, or unnecessary halts**. What are the proven prior-art patterns, protocols, and pitfalls for (1) concurrent-writer awareness, (2) race-safe git operations, (3) cross-platform FIFO/queue file-locking, and (4) automated conflict classification and resolution (write vs. semantic vs. large-non-semantic) — and how should a deterministic, single-machine-plus-cloud agent harness apply them?

## Context

**System under design.** An autonomous software-building harness ("the pipeline") that walks work items (features/bugs) from spec → plan → implement → validate, one agent "cycle" at a time, committing to a shared branch after each cycle. It is built from these existing, reusable concurrency primitives (we intend to REUSE, not reinvent):

- A **cross-process global lock** via atomic `os.mkdir` (atomic on NTFS and POSIX), with **fencing-token leases** (monotonic watermark counters persisted to JSON) and **stale-holder reclamation** (a lock holder is reclaimable only when its pid is confirmed dead OR its recorded kernel process-start-time no longer matches — guarding against pid reuse). Heartbeat/expiry and a worktree-pool provisioner sit on top.
- A **machine-global single-slot FIFO build serializer** (PowerShell): an `active.lock` file plus monotonically increasing sequence numbers, confirmed-dead stale-lock reclaim, and one authoritative last-line outcome banner.
- A **fail-closed "provisional auto-accept" predicate**: certain decision classes are permanently excluded from unattended auto-acceptance and always halt for a human.
- A documented **two-implementation runner-outcome contract**: the same behavioral grammar is implemented independently in PowerShell (Windows workstation plane) and in stdlib-only Python (cloud/Linux plane) — no shared code, conformance by contract.

**Environment.** Primary plane: Windows 10 + NTFS + Git Bash + PowerShell, single workstation. Secondary plane: Linux cloud containers (stdlib Python only, no PowerShell). Git is the only shared-state substrate between concurrent sessions on the same machine; a remote `origin` is the substrate across machines/sessions. Agents are non-interactive most of the time (autonomous runs) but can halt to a human via a sentinel file.

**Motivating incident.** A concurrent operator session committed ~28 files to `main` mid-cycle while an autonomous run was active. The run's process-friction/anomaly detector treated the unexpected commits + moved HEAD as a defect signal and nearly fired a false breach alarm. The autonomous cycle also uses blanket `git add -A`, which risks absorbing a concurrent writer's staged files into the wrong commit.

## Baseline Spec Summary (decisions already tentatively locked — validate or challenge these)

The feature spans four axes:

1. **Awareness** — inject into every agent's prompt/context that other agents may be committing to the same worktree/branch concurrently, so an unexpected commit or moved HEAD is *expected*, not anomalous.
2. **Git safety** — fetch + fast-forward before every push; bounded push-retry on non-fast-forward rejection (never `--force`); prefer append-only / pathspec-scoped commits over blanket `git add -A` so a concurrent writer's staged files are never absorbed.
3. **FIFO file-lock** — agents detect write contention and coordinate through a cross-platform queue lock (two conforming implementations: PowerShell workstation + stdlib-Python cloud), each proceeding in turn.
4. **Conflict handling — three routes:**
   - **Write conflict → non-halting:** retry/queue via the lock, log, continue.
   - **Semantic conflict → HALT:** logically incompatible work → write a human-halt sentinel (class `product`), never auto-accept.
   - **Large non-semantic conflict → temp-worktree merge-back:** the orchestrator completes the work in a temporary worktree, merges back in queue order, resolves, and communicates to the conflicting agent.

**Tentatively-locked design choices (challenge these with evidence):**
- Lock granularity = **per-work-item** (not per-file): two agents on the same item serialize; different items never block.
- Semantic-vs-non-semantic discriminator = **git-mergeability + coupled-surface heuristic**: NON-semantic when git auto-merges cleanly OR conflicting hunks touch disjoint logical surfaces; SEMANTIC when git reports an un-auto-resolvable conflict on the SAME logical artifact (same function / same decision-doc row / same file region with shared symbols). Ambiguous cases fall to SEMANTIC/halt (fail-safe).
- Merge-back lifecycle = reuse the existing coordinator-lane machinery (temp worktree as a lane branch, merge in queue order, abort-and-demote on conflict).
- Cross-agent communication channel = a structured **commit-message trailer** (`Concurrent-Merge-Back:` naming affected paths + resolution guidance) that the conflicting agent reads in the history it must fetch/rebase before it can push. Zero new contended state.

## Research Areas

Investigate each with concrete prior art, cited protocols, and named failure modes:

1. **Concurrent-writer awareness & anomaly-detection reconciliation.** How do systems that expect concurrent writers (collaborative editors, CI runners sharing a checkout, multi-agent coding frameworks) distinguish a *sanctioned* concurrent change from a genuine anomaly? What signals reliably separate "another authorized writer" from "corruption/attack/runaway"?

2. **Race-safe git push/commit protocols.** Best practice for `fetch` + fast-forward-only + bounded retry on non-fast-forward; safe alternatives to `--force` (`--force-with-lease`, `--force-if-includes`); how to scope commits to only the agent's own changes (pathspec staging, `git stash` isolation, `git commit -- <pathspec>`, index hygiene) so a concurrent writer's staged files are never captured. Pitfalls of `git add -A` in shared checkouts. How Gerrit/GitHub/GitLab handle the push race server-side and what clients should mirror.

3. **Cross-platform FIFO / queue file-locking.** Proven patterns for a fair (FIFO) advisory lock that works on BOTH NTFS/Windows and POSIX/Linux using only filesystem primitives (atomic `mkdir`, `O_EXCL` create, rename-based locks, lock directories with sequence tickets — the classic ticket-lock / bakery-algorithm on a filesystem). Fairness guarantees, thundering-herd avoidance, and — critically — **stale-lock / crashed-holder detection** (pid liveness, process-start-time fencing, lease expiry, fencing tokens per Martin Kleppmann's "How to do distributed locking"). What breaks fencing on a single machine vs. across machines?

4. **Automated conflict classification (the hard part).** Prior art on programmatically distinguishing a *textual/mechanical* merge conflict from a *semantic* one: git rerere, structured/semantic merge tools (e.g. Mergiraf, GumTree, semantic-merge, IntelliMerge, language-aware 3-way merge), operational transformation vs. CRDTs for text, and research on "semantic conflicts that merge cleanly but break behavior." How reliable is "git auto-merged cleanly" as a proxy for "no semantic conflict"? What is the false-negative rate (clean merge that is nonetheless semantically broken) and how do mature systems mitigate it (build/test gate after auto-merge)?

5. **Temp-worktree / staging-area merge-back protocols.** Patterns for completing work in an isolated worktree/branch and merging it back into a shared branch in a defined order (queue-order / stacked-diffs / merge-train / Gerrit submit-strategy / GitLab merge-trains / Graphite/Phabricator stacked PRs). Abort-and-retry semantics, preserving the isolated branch on conflict, and audit trails.

6. **Cross-agent / cross-process signaling without new contended state.** Precedent for using the git object graph itself as the message bus: commit-message trailers (`git interpret-trailers`, the `Signed-off-by`/`Co-authored-by`/`Change-Id` conventions), git notes, refs-based signaling. Reliability of "the other party reads it when they fetch/rebase to push." Failure modes: rebased-away trailers, squash-merge loss, the reader never fetching.

7. **Multi-agent coding harness prior art.** How do existing multi-agent / parallel-agent coding systems (agent swarms, parallel-worktree orchestrators, background-agent products, CI merge queues) coordinate concurrent writes to shared branches? What did they get wrong first and fix later? Named systems and their coordination model.

8. **Pitfalls, accessibility of failure, and observability.** Deadlock/livelock in FIFO file-locks, clock-skew effects on lease expiry, NTFS vs. POSIX atomicity differences (`mkdir`, `rename`, `O_EXCL`), the ABA/pid-reuse problem in stale-holder reclamation, and how to make lock contention observable without itself becoming contended state.

## Specific Questions

1. Is "git auto-merges with no conflict markers" a *safe* proxy for "non-semantic conflict"? Quantify the known false-negative risk and name the standard mitigation (post-merge build/test gate) — should our discriminator REQUIRE a green build/test after a clean auto-merge before trusting "non-semantic"?
2. For a fair FIFO advisory lock using only filesystem primitives that must work on both NTFS and POSIX, what is the most robust, widely-validated algorithm (lock-directory ticket scheme? rename-based? `flock` where available with a portable fallback?), and what are its documented edge cases?
3. What is the current best practice for safe non-force pushing under a push race — `--force-with-lease` vs `--force-if-includes` vs pure fetch-ff-retry — and what bounded-retry / backoff policy do mature merge-queue systems use?
4. How do production merge queues (GitHub merge queue, GitLab merge trains, Gerrit, Zuul, Bors/Homu) order and serialize concurrent merges, detect a poisoned/conflicting change, and evict it without stalling the whole queue? Which of their strategies maps onto a single-machine agent orchestrator?
5. Are commit-message trailers a reliable one-way signaling channel between two processes racing to push to the same branch, or will rebase/squash/force-with-lease routinely destroy the signal? What is a more robust alternative that still adds zero contended mutable state (git notes? a dedicated `refs/` namespace? an append-only log object)?
6. What is the correct fencing-token discipline for stale-lock reclamation on a SINGLE machine (where a lock service isn't available) — is process-start-time + pid sufficient to defeat pid reuse, and what does Kleppmann's fencing-token argument imply we still cannot guarantee without a monotonic external counter?
7. What semantic-merge or conflict-classification tooling is mature enough (2024–2026) to consult or embed, and what are the tradeoffs of a language-agnostic textual heuristic vs. an AST-aware tool for a harness that edits Markdown, Python, PowerShell, Rust, and TypeScript?
8. What concrete anti-patterns have burned other multi-agent-on-shared-branch systems (silent lost updates, false-positive anomaly alarms on legitimate concurrent commits, deadlocked file-locks, force-push clobbers, absorbed foreign staged files) — and what guardrails prevented each?
9. Where should the boundary sit between "retry/queue silently" and "halt for a human" so the system neither panics on the routine nor silently proceeds through a genuine incompatibility? What decision rule do comparable systems use?
10. For the cloud (stdlib-Python, Linux) plane vs. the workstation (PowerShell, NTFS) plane, which of these mechanisms are portable as-is, which need a distinct implementation, and where do the two planes' guarantees legitimately differ?

## Output Format Request

Provide a structured report with these sections:

1. **Executive summary** — the 5–8 highest-leverage findings, each one sentence.
2. **Per-research-area findings** — one subsection per Research Area (1–8 above), each with: named prior art / protocols (with citations or links), the concrete pattern, and its documented failure modes.
3. **Direct answers to the 10 Specific Questions** — numbered to match, each with a clear recommendation and the evidence behind it.
4. **Validation / challenge of our tentatively-locked decisions** — for each of the four locked design choices (lock granularity, semantic discriminator, merge-back lifecycle, commit-trailer channel), state whether prior art SUPPORTS, REFINES, or CONTRADICTS it, and what to change.
5. **Recommended design** — a concise, actionable recommendation for each of the four axes, calling out any place we should diverge from the baseline spec.
6. **Pitfall checklist** — a bulleted list of concrete failure modes to guard against, each paired with the guardrail that prevents it.
7. **Open risks** — anything that cannot be resolved by research and needs a human product decision.

Prefer concrete, named prior art and cited sources over generic advice. Where a recommendation depends on our specific constraints (single machine + cloud, filesystem-only locking, git-as-substrate, deterministic/non-interactive agents), say so explicitly.
