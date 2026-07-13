# docs/bugs/ — claude-config harness defect investigations

Investigation specs for **defects in the harness itself** (skills, scripts, hooks,
templates) discovered from real `/lazy*` runs. This is the bug-pipeline analog of
`docs/specs/` (which holds harness *feature* work).

## Naming

One directory per defect: `docs/bugs/<slug>/SPEC.md`, where `<slug>` is a short
kebab-case description of the defect (e.g. `hardening-blind-to-process-friction`).
There is no work-item tracker for the harness repo, so slugs are descriptive.

## Lifecycle

Same investigation-spec contract as `/spec-bug`:

- `**Status:** Investigating` — active investigation; root cause not yet proven.
- `**Status:** Concluded` — root cause proven, affected area + fix scope understood;
  ready for `/plan-bug` (authors `PHASES.md`) → `/fix` / `/execute-plan`.

Prior-art harness specs live under `docs/specs/` — cross-link them in `**Related:**`
(notably `turn-routing-enforcement/` for the hardening stage and `lazy-hardening/`).

## Research resume

claude-config has **no `docs/gemini-sprint/` staging structure by design** — the repo
has negligible research volume, so the full staging machinery (results/, prompts/ symlinks,
_consumed/) would be unused.

The **blessed research-resume route** for this repo is a **direct `RESEARCH.md` drop** into
the canonical feature or bug directory (e.g. `docs/features/<slug>/RESEARCH.md` or
`docs/bugs/<slug>/RESEARCH.md`). `lazy-state.py` Step 5 detects it and routes to `/spec`
Phase 3 naturally — no ingestion step needed.

Both staging consumers already degrade gracefully when the staging dir is absent:
- `/lazy*` Step 0.5: `find docs/gemini-sprint/results …` returns empty → silently skips
  to the main loop.
- `/ingest-research` (no args, missing staging dir): exits 0 with "nothing to ingest"
  — an explicit no-op, not an error.

**Escape hatch:** should a future high-research-volume self-edit workflow ever warrant the
full staging structure, see `user/skills/ingest-research/SKILL.md` line ~65 ("per-repo
adoption" note) — parameterize the staging path via `.claude/skill-config/gemini-sprint.md`.

## Fixing a bug OUT-OF-PIPELINE (harden-harness, manual in-session fixes)

`__mark_fixed__ → --archive-fixed` is two separate script-owned acts: the receipt write +
`**Status:** Fixed` flip, then `git mv` into `_archive/` (+ queue trim). `/lazy-bug-batch` runs
both. A session that fixes a `docs/bugs/<slug>/` defect **outside** that pipeline (a
`harden-harness` round, an in-session manual fix, a batch commit touching multiple bugs) MUST do
ONE of:

- **Finish the contract:** write the receipt (`FIXED.md`, `kind: fixed`) and run
  `python3 user/scripts/bug-state.py --repo-root . --archive-fixed docs/bugs/<slug>` — the ONE
  script-owned mover (evidence header, `git mv` with retry, inbound-ref repoint, queue trim, one
  commit). Never `git mv` the dir by hand.
- **Leave `**Status:**` untouched** and let the bug pipeline drive completion normally.

**Never** a bare `**Status:** Fixed` flip with no receipt and no archive — that is precisely the
state `bug-state.py --fsck` (below) flags, and it silently pollutes every open-backlog view
(incident-scan dedup, the reconsider/canary once-ever guards, future spec authors checking for
prior art) until someone greps it out by hand
(`docs/bugs/_archive/fixed-bugs-unarchived-fsck/` — the 18-dir debris this rule now prevents).

### `bug-state.py --fsck` — the invariant checker

Read-only, mutates nothing. Run standalone, at `--run-end`, or as a future
`docs/features/claude-config-ci/` lane:

```bash
python3 user/scripts/bug-state.py --repo-root . --fsck
```

Fails (exit 1, named violations) on:
- `unarchived-fixed` — `**Status:** Fixed` + a valid `FIXED.md` receipt sitting outside
  `_archive/` (the `--archive-fixed` step never ran). Remedy: `--archive-fixed docs/bugs/<slug>`.
- `fixed-without-receipt` — `**Status:** Fixed` with no valid receipt (and not `Won't-fix`).
  Remedy: `--backfill-receipts` (grandfathers as `provenance: backfilled-unverified` — honest debt,
  never silenced) or re-disposition to `Won't-fix` if the fix claim cannot be evidenced.
- `stale-queue-entry` — a `docs/bugs/queue.json` row pointing at a `Fixed` or already-archived dir
  (the archive step's queue-trim missed it, or a manual queue edit went stale).

### Aging + pinning (`bug-queue-aging-backpressure`, PROVISIONAL)

Bug-only (no feature-axis analog — features have no `**Discovered:**` field). Two mechanisms,
both pure functions of `**Discovered:**` / an explicit pin, never fabricated state:

- **Age-escalation** (`lazy_core.age_escalated_rank`) — a queued bug's effective severity rank
  escalates one notch toward 0 (more urgent) per 7 days since `**Discovered:**`, capped at rank 1
  (a genuine P0 always outranks mere age). Applies automatically at ordering time; no operator
  action needed.
- **`--pin`** (`bug-state.py --pin --id <id> [--until YYYY-MM-DD] [--reason <text>]`) — the
  sanctioned replacement for hand-editing `queue.json` to `"severity": null`: deprioritizes a bug
  behind a reviewable, expiring pin (`lazy_core.pin_is_active`; default max pin age 90 days if
  `--until` is omitted). Creates the queue entry if not already queued.

Both feed `lazy_core.merged_priority` — never re-implemented per-caller. Landed PROVISIONAL (D1
parked pending ratification); see the feature's `NEEDS_INPUT_PROVISIONAL.md`.
