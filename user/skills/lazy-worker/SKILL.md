---
name: lazy-worker
description: One worker session that claims a leased queue item and worktree slot, runs implement → open GH PR, concurrent with other workers bounded by pool_size.
argument-hint: [optional: "--feature-id <slug>" or "--bug-id <id>" to pin this worker to one item]
plan-mode: never
---

# Lazy Worker — Single-Item Worker Session

One worker runs one queue item end-to-end: claim lease → implement → open PR. Multiple workers run concurrently; `pool_size` (read from config) caps the number of simultaneous slots. This is the implement-to-PR back-half of the pipeline, driven by a single leased item rather than the full orchestration loop that `/lazy-batch` manages.

---

## Step 0: Parse Arguments

Tokenize `$ARGUMENTS` on whitespace:

- `--feature-id <slug>` — pin this worker to a specific feature queue entry (`lazy-state.py --feature-id <slug>`).
- `--bug-id <id>` — pin this worker to a specific bug queue entry (`bug-state.py --bug-id <id>`).
- Both absent → claim the highest-priority actionable item in the queue.

Unknown tokens are an error: report them and STOP.

---

## Step 1: Acquire Global Lock

```python
acquire_lock(lock_dir)
# lock_dir = <COG_DOCS>/docs/work/global.lock.d
# Implemented via atomic os.mkdir — NTFS-safe, no fcntl/flock.
# Raises TimeoutError after 10 s.
```

All shared-state mutations in Steps 2–4 happen under this lock. The implement-and-PR work (Step 5) runs OUTSIDE the lock.

---

## Step 2: Reclaim Expired Leases

Before claiming anything, sweep dead leases and scrub their slots:

```python
reclaim_expired(leases_path, pool_dir)
# leases_path = <COG_DOCS>/docs/work/leases.json
# pool_dir    = worktree pool root
# Removes entries where heartbeat_epoch + ttl_seconds < now;
# shutil.rmtree()s the corresponding pool_dir/<slot> (errors tolerated).
# Returns a list of reclaimed wi_id strings.
```

---

## Step 3: Select an Item

Choose the highest-priority actionable queue entry that has no live lease:

- Actionable = front-half ready (spec/plan phase) or implement-ready.
- If `--feature-id <slug>` was supplied, constrain to that entry (`lazy-state.py --feature-id <slug>`).
- If `--bug-id <id>` was supplied, constrain to that entry (`bug-state.py --bug-id <id>`).
- If no item is available (queue empty, all leased, or pinned item not actionable), release the lock and STOP with a clear status message.

---

## Step 4: Acquire Lease + Worktree Slot

```python
entry = acquire_lease(leases_path, wi_id, worker_pid, slot, ttl_seconds)
# wi_id       = work-item ID string
# worker_pid  = os.getpid()
# slot        = next free slot name (e.g. "wt-00")
# ttl_seconds = from config (e.g. 1800)
# Returns the new entry dict (with term_token) or None if already held.
# Internally: reclaims expired entries, then writes new entry atomically.
```

Capture the returned `term_token` — every subsequent mutation must carry it:

```python
term_token = entry["term_token"]
```

If `acquire_lease` returns `None` (another worker raced in), release the lock and STOP.

---

## Step 5: Release Lock — Do Real Work Outside It

```python
release_lock(lock_dir)
```

The global lock is held only during Steps 2–4 (short shared-state mutations). The implement-and-PR work below runs without holding the lock.

---

## Step 6: Worktree Prep (scrub-to-clean sequence)

Before starting implementation, reset the slot to a clean state from `origin/main`. Execute in order — NO submodule step:

1. Remove stale index lock (with exponential-backoff retry):
   ```
   rm .git/worktrees/<slot>/index.lock   # if exists
   ```
2. Fetch under lock:
   ```python
   acquire_lock(lock_dir)
   git fetch origin
   release_lock(lock_dir)
   ```
3. Detach to remote tip:
   ```
   git checkout --detach origin/main
   ```
4. Hard-reset:
   ```
   git reset --hard origin/main
   ```
5. Wipe untracked files:
   ```
   git clean -fdx
   ```
6. Create the work branch:
   ```
   git checkout -b p/<wi_id>-<slug>
   ```
   Branch naming is **mandatory**: `p/<wi_id>-<slug>` (e.g. `p/16507-subject-verification`).

---

## Step 7: Implement

Run the appropriate sub-skill inside the worktree slot:

- **Implement-ready items** → invoke `/execute-plan` (or the relevant phase skill).
- **Front-half / short work** → may be done in-lock (no worktree slot required); skip Steps 4–6 if no implementation is needed.

Periodically refresh the lease while work is in progress (long-running sessions):

```python
heartbeat(leases_path, wi_id, expected_token=term_token)
# Raises FencingError if term_token was superseded — a reclaim or
# competing acquire happened. Abort the session immediately on FencingError.
```

Heartbeat interval: every ~300 s (or ≤ ttl/3, whichever is shorter).

---

## Step 8: Open the Pull Request

Open the PR via the `.agents/skills/pull-request/SKILL.md` skill and the `gh` CLI.

**PR shepherding is DEFERRED.** The worker opens the PR and STOPS. It does NOT:
- Poll CI or wait for checks.
- Auto-reply to reviewer comments.
- Auto-merge under any condition.

---

## Step 9: Finalize Under Lock

Re-acquire the global lock and complete all shared-state mutations atomically:

```python
acquire_lock(lock_dir)
```

### 9a. Fencing check — MANDATORY before any queue.json mutation

```python
verify_fencing(leases_path, wi_id, expected_token=term_token)
# Raises FencingError if the lease was reclaimed and re-claimed by another
# worker while this session was implementing.
```

If `FencingError` is raised: the worker is a zombie whose work was superseded. Release the lock, log the abort, and STOP — do NOT write to `queue.json`.

### 9b. Flip queue item state

Transition the item's state (e.g. `implement-ready` → `pr-open`) in `queue.json`.

### 9c. Release lease

```python
release_lease(leases_path, wi_id, expected_token=term_token)
# Verifies fencing internally before removing the entry.
# Raises FencingError on mismatch.
```

### 9d. Free + scrub the slot

Remove the `pool_dir/<slot>` directory (or defer to the next `reclaim_expired` sweep).

### 9e. Update materialized.json

Write the PR link and new status to `materialized.json` so `/work-status` reflects the landed work.

### 9f. Release lock

```python
release_lock(lock_dir)
```

---

## Invariants (non-negotiable)

- **One writer under lock.** Every mutation of `leases.json`, `queue.json`, and `materialized.json` happens under `acquire_lock` / `release_lock`. No concurrent writers.
- **Fencing before every queue.json mutation.** Call `verify_fencing(leases_path, wi_id, expected_token=term_token)` in Step 9a BEFORE writing queue state. A stale/zombie worker whose `term_token` was superseded must detect this and abort.
- **Branch convention.** All work branches follow `p/<wi_id>-<slug>` exactly. This is how `/work-status` auto-discovers PR links.
- **Never auto-merge.** The worker opens the PR and stops; merge is a human action.
- **Never auto-reply to PR comments.** Review interactions are out of scope for the worker session.
