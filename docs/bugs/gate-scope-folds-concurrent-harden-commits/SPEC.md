# Completion-gate scope derivation folds a concurrent harden workstream's commits into the active item — Investigation Spec

> `gate_verdict_ok` (anti-overfit-design-gate D3 ship seam) re-derives an item's control-surface
> scope from its commit set via `_item_commit_touched_files` → `derive_touched_from_brackets`.
> The bracket ledger records each cycle as a `begin_sha..end_sha` RANGE, and
> `derive_touched_from_range` sweeps up EVERY commit in that range — including
> foreground observed-friction `harden(...)` commits the orchestrator lands mid-run, which are a
> DIFFERENT workstream from the queue item. A feature whose OWN shipped work touches ZERO control
> surfaces is therefore dragged into gate scope by the harden workstream's commits and refused at
> `__mark_complete__` for a `GATE_VERDICT.md` it should never have owed.

**Status:** Concluded
**Priority:** P1
**Last updated:** 2026-07-13
**Related:** `docs/features/anti-overfit-design-gate/` (owns `gate_verdict_ok` + the control-surface manifest; STRUCTURALLY PROVISIONAL, `NEEDS_INPUT_PROVISIONAL.md` pending); `docs/specs/turn-routing-enforcement/` (owns the hardening stage that surfaced this — Round 36); `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` (the sibling gap-1 design fork this fix does NOT close: no sanctioned route authors `GATE_VERDICT.md` for a genuinely-in-scope pipeline feature). Sibling of `docs/bugs/descoped-marker-blind-completion-coherence-gate/` (Round 35 — the PRIOR completion gate on the SAME feature; this feature advanced past it into the next gate).

## Verified Symptom

Live claude-config `/lazy-batch` run, item `state-cli-contract-registry`, this session (2026-07-13). `--apply-pseudo __mark_complete__` refused:

```json
{"name": "__mark_complete__", "ok": false,
 "refused": "harness-change design gate: scoped change missing GATE_VERDICT.md — author/repair GATE_VERDICT.md (see _components/harness-change-gate.md) before completion",
 "wrote": [], "deleted": [], "noop": false}
```

`gate_verdict_ok(spec_path, repo_root)` returned `{ok: False, in_scope: True, reason: "scoped change missing GATE_VERDICT.md"}` with `scope_hit = [user/hooks/CLAUDE.md, user/hooks/block-terminal-kill.sh, user/scripts/lazy_core.py]`.

**Every path in `scope_hit` comes from a foreign `harden(...)` commit — NONE from the feature's own work.** Verified via `git show --stat`:

| Commit | Subject | Files (all control-surface hits) |
|--------|---------|----------------------------------|
| `b77b5b23` | `harden(hook): make block-terminal-kill.sh quote-aware` | `user/hooks/block-terminal-kill.sh`, `user/hooks/CLAUDE.md`, `CLAUDE.md`, `user/scripts/test_hooks.py` |
| `84f4a030` | `harden(script): honor canonical descoped marker in completion-coherence gate` | `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py` |

The feature's OWN commits in this run touch ONLY docs (zero control surfaces):

| Commit | Subject | Files |
|--------|---------|-------|
| `6a4af018` | `chore(state-cli-contract-registry): write VALIDATED.md` | `docs/features/state-cli-contract-registry/VALIDATED.md`, `LAZY_QUEUE.md` |
| `dc504eba` | `chore(state-cli-contract-registry): grant structural MCP-skip` | `docs/features/.../SKIP_MCP_TEST.md`, `LAZY_QUEUE.md`, `docs/kpi/SCORECARD.md` |
| `3411b457` | `fix(state-cli-contract-registry): descope-mark deferred Phase 4 rows` | `docs/features/.../PHASES.md`, `LAZY_QUEUE.md` |
| `fb8e8132` | `chore(state-cli-contract-registry): mark plan part 1 Complete` | plan file, `LAZY_QUEUE.md`, `docs/kpi/SCORECARD.md` |

With the two `harden(...)` commits correctly excluded, the feature's scope hits ZERO control-surface globs → `gate_verdict_ok` should return `{ok: True, in_scope: False}` and completion should proceed with no `GATE_VERDICT.md` owed.

## Root Cause

**Classification: `script-defect`** (`user/scripts/lazy_core.py`).

The completion-gate scope reader `_item_commit_touched_files(spec_path, repo_root)` (L3296) resolves the item's touched-file set via `derive_touched_from_brackets(repo_root, item_id)` (L16415). That helper unions, per recorded cycle bracket, `derive_touched_from_range(repo_root, "begin_sha..end_sha")` (L16398), whose file set is `git diff --name-only begin_sha..end_sha` — the RANGE's cumulative diff.

The bracket ledger attributes a cycle to its `feature_id` by recording `begin_head_sha` (snapshot at `--cycle-begin`) → HEAD (at `--cycle-end`). A foreground observed-friction harden dispatch the orchestrator runs BETWEEN feature cycles lands its `harden(...)` commits inside the git-log window a later feature bracket spans — so the range diff folds those foreign-workstream files into the feature's derived scope. There is no per-commit workstream tag in the ledger; the ONLY structural signal that a commit belongs to the harden workstream (not the queue item) is its commit-message prefix `harden(`, which the harden-harness Commit discipline MANDATES on every harden commit ("All commits made by this skill use the prefix `harden(<area>):`").

This is scope OVER-attribution, not a gate design flaw: the gate fires correctly for a genuinely-in-scope item (one whose OWN commit touches a control surface); it mis-fires only when the sole control-surface hits are foreign harden commits swept into the range.

## Fix Scope

Exclude foreign `harden(...)`-prefixed commits from an item's completion-gate scope derivation, single-source in `lazy_core`:

1. `_commit_subject_is_foreign_harden(repo_root, sha)` — reads the commit subject (`git show -s --format=%s`); True iff it matches `^\s*harden\(`. FAIL-OPEN: an unreadable subject → `False` (treated as NOT foreign, so a real item commit is never silently dropped → the gate is never weakened).
2. `_files_from_commits(repo_root, shas)` — the touched-file union from the named commits' own `git show --name-only --format=` diffs (per-commit, not range).
3. `_item_commit_touched_files` partitions the bracket/grep-derived commit set into item vs. foreign-harden. When NO foreign commit is present (the common case), it returns the pre-existing range-derived file set **byte-identically** (no behavior change, no re-derivation). Only when ≥1 foreign harden commit is filtered does it recompute the file set from the surviving item commits.

Blast radius is confined to the completion gate's scope reader. `write_provenance`'s use of `derive_touched_from_brackets` is deliberately UNCHANGED this cycle (a feature's `IMPLEMENTED.md` falsely claiming harden commits is a real but separate provenance concern, out of this dispatch's observed friction — noted for a follow-up, not folded in here).

**Not a gate-weakening (Prohibition #2).** The fix removes a FALSE positive (foreign-commit misattribution); a genuinely-in-scope item still triggers `gate_verdict_ok`. `harness-gate.py` is run over the diff and its verdict cited in the hardening round.

**Sibling gap NOT closed here (gap 1).** For a feature whose OWN commit touches a control surface, `gate_verdict_ok` correctly requires a `GATE_VERDICT.md`, yet no sanctioned emit-dispatch class authors one in-pipeline (`coherence-recovery` is PHASES.md-only; the orchestrator's Write is sentinel-scoped; the dispatch guard denies a hand-composed Agent). That is an operator-owned design fork surfaced separately in `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` — it is not a mechanical defect and is out of scope for this fix.
