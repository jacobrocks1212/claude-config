### Concurrent-Lock Contract — the one documented per-queue-item FIFO file-lock grammar

This is the ONE documented contract for the concurrent multi-agent **per-queue-item FIFO file
lock**: a single documented grammar that any coordination plane conforms to independently. The
cross-plane seam is **this documented grammar, not shared code** — the stdlib-Python plane
(`user/scripts/lazy_coord.py`) and the PowerShell workstation plane
(`user/scripts/concurrent-lock.ps1`) each implement it on their own, sharing no implementation
(the same *documented-grammar-not-shared-code* pattern as `runner-outcome-contract.md`). A plane
"conforms" when it satisfies all five legs below.

The lock is built ON the existing concurrency plane (`lazy_coord.py`'s global `os.mkdir` lock +
fencing-token leases + `_confirmed_dead_owner` reclamation) — it invents **no new locking
substrate** (parallel-worktree-batch-execution D-reuse). It is the FIRST conflict route: two
agents that would otherwise clobber the same queue item's shared state instead proceed in turn.
Per-file granularity is an explicit vN refinement (SPEC Locked Decision 1); v1 is per-item.

#### Leg 1 — Per-queue-item grain (Locked Decision 1)

The lock key is the **queue-item id** (`wi_id` — a feature/bug item), reusing the `lazy_coord`
lease keying VERBATIM. Two agents contending on the **same** item key serialize; two agents on
**different** item keys never block each other. There is exactly one lock per feature/bug item —
never a coarser whole-repo lock, never (in v1) a finer per-file lock.

#### Leg 2 — Acquire = wait-for-unlock FIFO

Acquire attempts to claim the item's lease. While a **live** holder holds it, the caller WAITS
(bounded exponential backoff) for the lock to unlock rather than stealing it; when the holder
releases, a waiting contender claims it and proceeds in turn. Contenders on one item key are
serialized — a released lock is taken by a waiter on its next poll. (Like the `build-queue.ps1`
`active.lock` precedent, the ordering guarantee is *mutual exclusion + proceed-on-unlock*, not a
strict cross-waiter ticket order — a ticket substrate is explicitly out of scope.)

#### Leg 3 — Fencing-token release

A successful acquire returns a monotonic **fencing token** (the lease `term_token`). The holder
carries that token and the release verifies it before unlocking — a superseded holder (token
changed underneath it) is refused and MUST NOT release someone else's lock. Fencing-token
monotonicity survives reclamation/release (the sibling watermark store), so a zombie holder's
stale token can never pass a later fencing check.

#### Leg 4 — Stale-holder reclaim via confirmed-dead only

A holder that dies without releasing does not deadlock the item forever. Reclamation is
**confirmed-dead only** (never a bare guess): the lease's own TTL-expiry reclaim (a holder that
stopped heart-beating) plus the global lock's `_confirmed_dead_owner` (the recorded pid is gone,
OR was reused — a live kernel start-time mismatching the recorded one). An **ambiguous** holder
(pid alive, start-time unreadable, or inside a bounded metadata grace window) is NEVER reclaimed —
safety over liveness, mirroring the `build-queue` `active.lock` precedent
(`Get-ActiveLockStatusFromText` / `Test-ShouldReclaimLock`: an unreadable pid classifies
`unknown`, never `dead`). A genuinely live holder still times out within the acquire budget — no
false reclaim.

#### Leg 5 — Authoritative acquire/timeout outcome

Acquire has a bounded timeout budget. On exhaustion it surfaces an **authoritative** timeout
outcome (Python: raises `ItemLockTimeout`; PowerShell: `RESULT=TIMEOUT` on the banner, a distinct
exit code) — a timeout is **never** reported as a successful acquire. The PowerShell plane, as a
runner in this workspace, emits its outcome on a `runner-outcome-contract.md`-conforming
LAST-stdout-line banner:

```
concurrent-lock: item=<id> op=<acquire|release> RESULT=<ACQUIRED|RECLAIMED|TIMEOUT|RELEASED|FENCING-STALE> [holder=<pid>] (elapsed=<s>s) [-> next-action]
```

#### The two conforming implementations

- **`user/scripts/lazy_coord.py`** (stdlib-Python, cloud-capable) — `acquire_item_lock` /
  `release_item_lock`, a polling mutex over `acquire_lease` / `verify_fencing` / `release_lease`
  keyed by `wi_id`; injected `now`/clock/sleep so the in-file `--test` fixtures are hermetic. The
  reclamation is the lease TTL-expiry `_reclaim` plus the global lock's `_confirmed_dead_owner`.
- **`user/scripts/concurrent-lock.ps1`** (PowerShell, workstation-only) — an `active.lock`-style
  per-item lock file with confirmed-dead reclaim + fencing token, mirroring `build-queue.ps1`;
  silently inert off-Windows. Pester suite: `concurrent-lock.Tests.ps1`.

#### Seam statement

The composition seam between the two planes is exactly this documented grammar. They conform to
Legs 1–5 **independently** — they share no code, do not shell one another, and do not import each
other's state. Both key on the same queue-item id, so a lock taken by one plane is observable to
the other only through the shared on-disk lease/lock state, never through shared code.
