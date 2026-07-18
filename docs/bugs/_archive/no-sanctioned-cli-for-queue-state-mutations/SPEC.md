# No sanctioned CLI for many feature/bug queue/state mutations

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-16
**Fixed:** 2026-07-18
**Fix commit:** 9da09f32
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage);
`docs/bugs/lazy-batch-no-mid-run-budget-or-park-controls/` (the coupled-pair mid-run
control precedent this fix mirrors); `docs/features/state-cli-contract-registry/`
(the `cli-surface.json` discoverability substrate).

## Trigger

Manual `/harden-harness` invocation (operator-directed, 2026-07-16), during a live
`/lazy-batch` run on AlgoBooth. The operator asked to promote a queued bug from P2 → P1
(and later → P0). There was **no clean CLI path** to do it:

- `--enqueue-adhoc --severity P1` on an already-queued id **no-ops** (returns
  `status: "duplicate"`, severity unchanged).
- `--reorder-queue` moves the queue **position**, but `merged_priority` is
  severity/tier-based, so moving position does **not** change effective (merged-view)
  priority — the bug stays ranked at its old severity.
- `--pin` only **deprioritizes** to `severity: null`; there is no inverse (promote)
  and no `--unpin`.

The orchestrator must NEVER hand-edit `queue.json` (HARD CONSTRAINT 1), so it was stuck:
a trivial mutation forced either an illegal hand-edit or a full subagent cycle.

## Root cause

**`root_cause_class: missing-contract`** (a sanctioned mutation exists as a *concept* —
priority/deps are first-class queue fields — but has no CLI command; the only writers are
`enqueue_adhoc` at creation time, `reorder_queue` for position, `pin_bug_severity` for the
one-way null-pin, and `sync_deps` for SPEC-projected deps).

Divergence point: **operator-directed mid-run queue mutation**. The queue-mutation CLI
surface (`--enqueue-adhoc`, `--reorder-queue`, `--pin`, `--sync-deps`) covers *creation*,
*position*, *deprioritize*, and *SPEC-projection* — but not *in-place priority change*,
*post-hoc arbitrary dependency edits*, or *un-pin*. Each such op was reachable only by a
forbidden hand-edit of `queue.json` or a subagent round-trip.

### Two-regime ordering model (the load-bearing detail)

Both queues have TWO orderings that must be kept coherent:

1. **Single-queue pipeline order** = `queue.json` **listed order** (position). `load_queue`
   (features) and `load_bug_queue` (bugs) both return *queued entries in listed order*;
   the pipeline works the head first. `--reorder-queue` mutates this.
2. **Merged cross-queue view** = `lazy_core.merged_priority` (feature `tier`, bug
   `severity`, age-escalated). `merged_worklist` / `next_merged` consume this.

A severity/tier change moves an item in regime 2 but, without a reorder, leaves regime 1
(listed order / what the single-queue pipeline actually works next) **stale**. **This is
the bug the operator hit**: changing effective priority without changing listed position
means "promote to P0" doesn't actually make the pipeline work it sooner. Therefore a
priority mutation MUST atomically re-position the entry in listed order to match its new
`merged_priority` — same write, never a two-step "mutate then maybe reorder".

## Inventory — every feature/bug queue/state mutation

Reachable via CLI on `lazy-state.py` (feature) / `bug-state.py` (bug) as of this commit:

| Operation | Field(s) | Before | After |
|---|---|---|---|
| Create queue entry | id/name/tier/severity/deps | ✅ `--enqueue-adhoc` (`--deps`/`--stub`/`--at`/`--tier`/`--severity` at create time) | (unchanged) |
| Move queue position | listed order | ✅ `--reorder-queue --id --to head\|tail\|remove\|N` | (unchanged) |
| Project SPEC hard-deps → queue | `deps` | ✅ `--sync-deps --id` (SPEC-driven only) | (unchanged) |
| Deprioritize bug (null-pin) | `severity:null`+`pinned_*` | ✅ `--pin` (bug only) | (unchanged) |
| Mid-run budget / park | run marker | ✅ `--set-max-cycles`/`--set-park`/`--set-park-provisional` | (unchanged) |
| **Change a bug's severity (promote/demote)** | `severity` | ❌ hand-edit/subagent only | ✅ **`--set-severity <id> <P0\|P1\|P2\|Low>`** (bug) |
| **Change a feature's tier** | `tier` | ❌ hand-edit/subagent only | ✅ **`--set-tier <id> <int>`** (feature) |
| **Add queue deps post-hoc (arbitrary, not SPEC-driven)** | `deps` | ❌ (`--deps` only at enqueue; `--sync-deps` only from SPEC) | ✅ **`--add-deps <id> --deps a,b`** (both) |
| **Remove queue deps post-hoc** | `deps` | ❌ hand-edit/subagent only | ✅ **`--remove-deps <id> --deps a,b`** (both) |
| **Un-pin a bug (inverse of `--pin`)** | clear `pinned_*`, restore `severity` | ❌ no inverse existed | ✅ **`--unpin <id>`** (bug) |
| Discover the right command for an op | — | ❌ no search surface | ✅ **`--search-ops <query>` / `--list-ops`** (both) |

Coupled-pair note: `--set-severity` (bug) and `--set-tier` (feature) are the
domain-appropriate analogs of one another (both mutate effective priority via the
pipeline's own ordering field). `--add-deps`/`--remove-deps`/`--list-ops`/`--search-ops`
are identical on both scripts. `--unpin` is bug-only — the exact inverse of the already
bug-only `--pin` (features have no severity-null pin concept; a justified divergence, like
`--pin` itself, un-audited by `lazy_parity_audit.py` which audits SKILL prose, not flags).

## Fix scope

1. **`lazy_core/depdag.py`** (the shared queue plane):
   - `reposition_by_priority(items, item_id, item_type, *, today=None)` — reposition the
     single mutated entry to its correct **listed-order** slot per `merged_priority`
     (stable: FIFO within equal priority). The atomic reorder engine.
   - `set_queue_priority(queue_path, item_id, item_type, new_value, *, today=None,
     queue_label=...)` — validate (`severity ∈ {P0,P1,P2,Low}` for bug; `tier` int for
     feature), set the field, clear pin fields on an explicit bug severity (supersedes a
     null-pin), **reposition in the same `_atomic_write`**, return old/new value +
     old/new position + `reordered`.
   - `mutate_queue_deps(queue_path, item_id, *, add=None, remove=None, queue_label=...)` —
     union/difference the `deps` list, validate ids (regex + reserved-prefix), post-mutation
     `detect_dep_cycle` guard, byte-stable no-op when unchanged, remove the key when empty.
     No reposition (deps gate readiness, not priority).
2. **`bug-state.py`**: `unpin_bug_severity(repo_root, bug_id, *, today=None)` — clear
   `pinned_*`, restore `severity` from the SPEC's `**Severity:**` line, reposition. Lives
   in `bug-state.py` (needs `bug_severity()`), mirroring `pin_bug_severity`'s location.
3. **CLI (both scripts, coupled-pair lockstep)**: each new mutator is
   `refuse_if_cycle_active` FIRST (exit 3, zero side effects for a cycle subagent — the
   `--reorder-queue`/`--pin` contract) **and** requires `--operator-authorized` (these are
   operator-directed mid-run priority/dependency changes — the same authorization posture
   as `--set-max-cycles`/`--set-park`). They do NOT require an active run marker (a queue
   mutation is valid before a run starts, unlike the marker controls).
4. **Discoverability (`cli_surface.py`, shared)**: `--list-ops` / `--search-ops <query>`
   introspect the **live** `ArgumentParser` (deterministic, stdlib-only, self-updating,
   both scripts) and return matching `{name, usage, help_head}` ranked by token overlap
   against name + help — so the orchestrator can answer "set bug severity" → `--set-severity`
   without reading source.
5. **Regression tests** (`tests/test_lazy_core/test_depdag.py`, pytest `tmp_path`): assert
   `--set-severity`/`--set-tier` **actually change listed order** (the load-bearing atomic
   reorder); deps add/remove + cycle refusal; `--unpin` restore+reposition;
   `--operator-authorized` gate + `refuse_if_cycle_active` refusal; `--search-ops` finds the
   command for a natural-language query.
6. **`user/skills/lazy-batch/SKILL.md`** prose documenting the new operator-authorized
   mutators (bug-batch + cloud inherit by reference; parity audit stays 0 — no new heading).
7. **`docs/cli/cli-surface.json`** regenerated via `cli_surface_gen.py`.

## Verification

- Regression tests green (asserting order changes on priority mutation).
- `lazy-state.py --test` / `bug-state.py --test` smoke suites green.
- `lazy_parity_audit.py` exit 0.
- `cli_surface_gen.py --check` clean after regeneration.
- Intervention record with a measurable `target_signal`.
