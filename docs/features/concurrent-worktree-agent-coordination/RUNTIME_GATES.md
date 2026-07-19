# Runtime Gates — concurrent-worktree-agent-coordination

Manual/integration runtime-verification rows deferred past plan-part completion. This feature
declares **MCP runtime: not-required** — there is NO downstream `/mcp-test` gate, so **this
ledger is the ONLY owner of these rows**. The operator working this ledger is the sole remaining
mechanism; no pipeline gate will hold them.

## Phase 5 — Temp-worktree merge-back + `Concurrent-Merge-Back:` trailer

| Gate row text | How to run it | Owning phase | Date deferred |
|---|---|---|---|
| A real large non-semantic conflict on the workstation: the temp worktree is created, work merges back, the run CONTINUES (no halt), and the conflicting agent's next fetch/rebase surfaces the `Concurrent-Merge-Back:` trailer. | On the workstation, drive a `/lazy-batch-parallel` run (or a hand-built two-worktree scenario) that manufactures a large but non-semantic write conflict between two lanes touching disjoint surfaces of the same feature. Confirm: (1) the losing lane's work is completed in a temp worktree spun as a lane and `merge_back_lanes` merges it back in queue order; (2) the run does NOT halt; (3) the conflicting agent's fetch/rebase (`git log <remote>/<branch>..HEAD`) shows a `Concurrent-Merge-Back:` trailer, and `lazy_core.read_concurrent_merge_back_trailers(<root>, "<remote>/<branch>..HEAD")` recovers its affected paths + guidance. | Phase 5 | 2026-07-19 |
