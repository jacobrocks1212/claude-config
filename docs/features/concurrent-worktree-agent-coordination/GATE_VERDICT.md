---
kind: gate-verdict
feature_id: concurrent-worktree-agent-coordination
gate_version: 1
date: 2026-07-19
scope_hit:
  - user/scripts/lazy-state.py
  - user/scripts/lazy_coord.py
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/docmodel.py
  - user/scripts/lazy_core/markers.py
  - user/scripts/lazy_core/runtimeplane.py
  - user/skills/_components/sentinel-frontmatter.md
  - user/skills/lazy-batch-parallel/SKILL.md
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
checks:
  overfit: pass
  tautology: pass
  gate_weakening: pass
  complexity: declared
retires: net-new coordination capability (per-item FIFO lock, conflict discriminator, temp-worktree merge-back) — AND a genuine retire: part-6 removes the `self_edit_mode → foreground/await` serialization coupling in `lazy-batch` / `lazy-bug-batch` / `lazy-batch-cloud`, replacing defensive pre-serialization with coordination-layer trust.
---

## Adversarial answers

### overfit
`harness-gate.py --range bc36d130..HEAD` reported **zero flags** (`flags: null`). No literal was
appended to any matcher (alternation / list / set / allow-list), and no incident-shaped literal
(a `docs/{features,bugs}/<slug>` id, a date, a session id) was introduced. The change adds NEW
Python symbols behind the PEP-562 facade (`git_safe_push`, `acquire_item_lock`/`release_item_lock`,
`classify_conflict`, `merge_back_lanes`, the `Concurrent-Merge-Back:` trailer helpers) and NEW
prose contracts — it does not narrow an existing matcher to an observed instance. There is no
near-neighbour recurrence to construct because no pattern was fit to a single incident: the
coordination primitives key on structural invariants (lease/fencing-token identity, git
mergeability, coupled-surface overlap), not on any literal drawn from a specific run.

### tautology
No `## Intervention Hypothesis` tautology flag fired (the change is capability, not a
self-observing gate). If the coordination layer were BROKEN, its success metric would NOT look
identical to working: a broken FIFO lock surfaces as concurrent same-key holders (caught by the
`same-key-serialize` / `live-holder-no-false-reclaim` Pester+pytest fixtures), a broken
`git_safe_push` surfaces as a non-ff push rejection escaping the retry bound (caught by
`test_git_safe_push_never_composes_force` + the retry fixtures), and a broken merge-back surfaces
as a lane branch left unmerged or a lost commit (caught by the `merge_back_lanes` fixtures).
The independent signals are the deterministic unit fixtures (347+ `lazy_core` tests, 28
`lazy_coord --test` fixtures, 8 Pester cases) — none emitted or suppressed by the change itself.

### gate_weakening
No gate-weakening hit (`gate_weakening_hit: false`, `flags: null`). The diff deletes no `def
test_*`, changes no numeric literal on a gate line, grows no sanction/exemption set, introduces no
`*_BYPASS` env-var, and removes no `permissionDecision: deny` / `refuse_*` / `exit 3` branch. The
one behavioural REMOVAL — retiring the `self_edit_mode → foreground/await` serialization coupling
(part-6) — is not a gate: it was defensive pre-serialization of parallel dispatch, and its removal
is the feature's explicit operator-authorized Requirement 7 ("rely on the dispatched subagents
correctly handling write conflicts, not prevent parallel work"). The governing-file RELOAD
discipline (self-edit C8) was retained unchanged in all three skills (grep-anchored: removal empty,
retention present ×3).

### complexity
`retires:` (frontmatter) — the added surface pays for itself two ways. (1) Genuine retire: the
`self_edit_mode` foreground-await coupling is removed from three coupled skills, so parallel
self-edits are no longer serialized behind a defensive await. (2) net-new: the per-item FIFO lock
(`acquire_item_lock`), conflict discriminator (`classify_conflict`), and temp-worktree merge-back
(`merge_back_lanes`) are the substrate the `lazy-batch-parallel` coordinator needs to run
independent queue items in concurrent worktree lanes safely — capability that did not previously
exist. Every new primitive reuses the existing lease/lane machinery (no new state substrate) and
git-as-oracle classification (no new heuristic), keeping the added surface bounded.
