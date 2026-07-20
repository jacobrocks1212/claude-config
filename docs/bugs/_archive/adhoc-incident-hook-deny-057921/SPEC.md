# lazy-cycle-containment second-feature tripwire false-denies concurrent-lane commits (reads the whole shared index) — Investigation Spec

> `lazy-cycle-containment.sh`'s second-feature-commit tripwire sources its staged-path set from
> `git diff --cached --name-only` — the ENTIRE shared-worktree index. Under sanctioned concurrent
> same-worktree writers (parallel `/lazy-batch` lanes, a second interactive/scheduled session, a
> background harden dispatch), that index carries OTHER lanes' staged-but-uncommitted sentinel
> files (`docs/bugs/<other>/FIXED.md`, `SPEC.md`, `GATE_VERDICT.md`). Those foreign paths are not
> carve-outs for THIS dispatch's `feature_id`, so they land in `offending` and the tripwire denies
> a cycle subagent's commit as a "second-feature commit" — even when the subagent staged only its
> own paths. The tripwire has no notion of the commit's own pathspec; it assumes `git commit` will
> flush the whole index.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-19
**Fixed:** 2026-07-19
**Fix commit:** f965cb2d
**Placement:** docs/bugs/adhoc-incident-hook-deny-057921
**Related:** `docs/bugs/_archive/lazy-cycle-containment-misparses-grouped-feature-paths/` (a DIFFERENT root cause on the same tripwire — grouped-path `group(1)` misparse, fixed 2026-07-18 at `e66c02f6`; this bug is the SHARED-INDEX cross-contamination case, orthogonal to grouping). `docs/specs/turn-routing-enforcement/` (owns the containment hook + hardening stage). `docs/specs/concurrent-worktree-agent-coordination/` and the CLAUDE.md `<orchestration>` "sanctioned concurrent writers outside that tree are expected, not a defect" contract this tripwire violates.

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

<!-- Auto-captured incident (no interactive operator present — park-mode batch). Symptoms are
     VERIFIED against the incident-scan evidence capsule (INCIDENT.md), which records the hook's
     own deny ledger lines verbatim — the deny is the hook's own machine-emitted output, so the
     ledger IS ground truth for "the deny fired", not a user report of it. -->

1. **[VERIFIED]** The `lazy-cycle-containment` hook denied `git commit` with signature
   `second-feature-commit` **3 times** between `2026-07-19T03:38:49Z` and `2026-07-19T08:17:57Z`
   (incident_key `claude-config|hook-deny|lazy-cycle-containment|second-feature-commit`) — verified
   from the hook's own deny-ledger lines captured verbatim in `INCIDENT.md`.
2. **[VERIFIED]** In every occurrence, the staged path(s) named in the deny detail were `FIXED.md`
   / `SPEC.md` / `GATE_VERDICT.md` under a DIFFERENT bug dir than the active dispatch's `feature_id`
   — verified from the deny `detail` fields:
   - active `feature_id: concurrent-worktree-agent-coordination`, offending paths under
     `adhoc-decision-key-relative-absolute-mismatch/` and
     `adhoc-subagent-wedge-hook-overfires-globs-all-plans/` (both `FIXED.md`+`SPEC.md`).
   - active `feature_id: byref-updatedinput-unapplied-on-background-agent-dispatch` (×2), offending
     paths under `merged-head-oracle-deadlocks-.../` (`FIXED.md`+`GATE_VERDICT.md`+`SPEC.md`).
3. **[VERIFIED]** All three denies carry the SAME `repo_root`
   (`C:\Users\Jacob\source\repos\claude-config`) — i.e. one shared worktree, not per-lane
   worktrees. The offending paths are OTHER completed bugs' receipt/sentinel files, consistent with
   a concurrent completion lane having staged its receipt into the shared index.

## Reproduction Steps

1. In a single shared worktree, arm a cycle marker for feature A:
   `python3 ~/.claude/scripts/bug-state.py --repo-root . --cycle-begin --bug-id A ...`
   (or drive it via `/lazy-bug-batch`, whose per-cycle marker sets `feature_id: A`).
2. Stage a sibling lane's sentinel into the SHARED index (simulating a concurrent completion lane):
   `git add docs/bugs/B/FIXED.md` (B ≠ A), leaving it staged and uncommitted.
3. As the feature-A cycle subagent, stage ONLY A's own path and attempt a pathspec-scoped commit:
   `git add docs/bugs/A/SPEC.md && git commit docs/bugs/A/SPEC.md -m "..."`.
4. Observe: the `git commit` PreToolUse call is DENIED with signature `second-feature-commit`,
   naming `docs/bugs/B/FIXED.md` as a path "under a different feature than the active dispatch",
   **even though the commit's pathspec never includes B's file**.

Deterministic unit-level repro (no git, exercises the exact decision path):

```bash
LAZY_CYCLE_STAGED_PATHS=$'docs/bugs/A/SPEC.md\ndocs/bugs/B/FIXED.md' \
  # with a marker whose feature_id=A → offending == ['docs/bugs/B/FIXED.md'] → deny
```

**Expected:** A cycle subagent that stages/commits only its own feature's paths is ALLOWED, even
when a concurrent lane's files sit staged in the shared index. Concurrent same-worktree writers are
a sanctioned, documented condition (CLAUDE.md `<orchestration>`), not a defect.
**Actual:** The tripwire evaluates the WHOLE shared index and denies, because a sibling lane's
staged sentinel is not a carve-out for this dispatch's `feature_id`.
**Consistency:** Deterministic given the shared-index precondition — fires whenever another lane
has an uncommitted staged file under a foreign `docs/{features,bugs}/<slug>/` dir at the moment
this subagent's `git commit` is inspected. Latent otherwise (a solo run never populates the index
with foreign paths), which is why it surfaced only during the concurrent-completion burst.

## Evidence Collected

### Source Code

Serving path of the symptom (each hop `file:line`, all in
`user/hooks/lazy-cycle-containment.sh`):

```
deny{signature:"second-feature-commit"}          lazy-cycle-containment.sh:723-728  (_deny call)
  ← offending list non-empty                       lazy-cycle-containment.sh:717-721
  ← staged = _staged_paths()                        lazy-cycle-containment.sh:716
  ← git diff --cached --name-only (WHOLE INDEX)     lazy-cycle-containment.sh:539-549  ← FIX SITE
      (returns every path staged in the shared worktree, incl. concurrent lanes')
  ← each foreign path matches _FEATURE_DIR_RE       lazy-cycle-containment.sh:440
    AND fails _is_carve_out(p, feature_id)          lazy-cycle-containment.sh:552-559
      (feature_id != the sibling lane's slug → _path_under_feature False; not in
       CARVE_OUT_PATHS at line 405) → path lands in `offending`
```

- `_staged_paths()` (lines 539-549) is the sole source of the evaluated set and reads
  `git diff --cached --name-only` — the entire shared index, with NO filter to the paths the
  pending `git commit` will actually include. The tripwire never inspects the `git commit`
  command's own pathspec (a `git commit <paths>` commits only `<paths>`; a bare `git commit`
  flushes the whole index — the tripwire cannot distinguish them and treats both as "the whole
  index is this commit").
- `CARVE_OUT_PATHS` (line 405) only exempts shared roots (`docs/features/queue.json`,
  `docs/features/ROADMAP.md`, `CLAUDE.md`) — a sibling lane's `FIXED.md`/`SPEC.md` is not exempt.
- `COMMIT_CEILING` (line 219) and the grouped-path carve-out (the already-fixed sibling bug) are
  unrelated to this failure mode.

### Runtime Evidence

`INCIDENT.md` (kind `incident-capture`) records the three verbatim deny-ledger lines — the hook's
own `hook-events.jsonl`/deny-ledger output, clustered by `incident-scan.py`. `git log` around the
window shows a dense burst of independent `fix(...): mark fixed and archive — FIXED.md receipt
gated` commits for many distinct bug slugs (e.g. `adhoc-cycle-return-omits-decision-classification-ledger`,
`adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke`,
`subagent-wedge-backstop-dirty-tree-predicate-repo-wide`), corroborating that multiple completion
lanes were staging receipts into the shared worktree concurrently.

### Git History

The fix that landed the sibling grouped-path defect (`e66c02f6`, 2026-07-18) hardened
`_is_carve_out` to be group-aware — it did NOT touch `_staged_paths()`'s whole-index source, so
this concurrency-driven false-deny survives that fix untouched.

### Related Documentation

- CLAUDE.md `<orchestration>`: "Sanctioned concurrent writers outside that tree are expected, not a
  defect ... an unexpected commit / moved HEAD is expected." The turn-end contract also mandates
  pathspec-scoped staging ("Stage ONLY the paths YOU changed — NEVER a blanket `git add -A`, which
  under a shared worktree can absorb a concurrent writer's staged files"). This tripwire is the
  mechanical backstop for that rule but is itself blind to the pathspec, so it penalizes even a
  compliant pathspec-scoped commit.
- `user/hooks/CLAUDE.md`: documents the tripwire as marker-gated commit containment; no note that
  its staged-path source is index-wide rather than commit-scoped.

## Theories

### Theory 1: Whole-shared-index evaluation (CONFIRMED)
- **Hypothesis:** The tripwire denies because `_staged_paths()` returns the entire shared index
  (`git diff --cached`), which under concurrent same-worktree lanes includes foreign-feature staged
  sentinel files that are not carve-outs for the active `feature_id`.
- **Cause label:** `traced` — serving-path chain cited above `file:line`; fix site
  (`_staged_paths()`, line 539) is on the path (it is the direct producer of the `offending` set).
- **Supporting evidence:** All three denies name foreign completed-bug receipt files; all share one
  `repo_root`; the window coincides with a concurrent-completion burst; static trace shows the
  offending set is sourced index-wide with no pathspec filter.
- **Contradicting evidence:** None. (The alternative — a single subagent genuinely doing blanket
  `git add -A` and about to absorb the sibling files in a BARE commit — is a REAL cross-contamination
  the tripwire SHOULD catch; but it shares the identical root: the tripwire cannot tell a
  pathspec-scoped commit from a bare one because it never reads the commit's pathspec. Either way
  the defect is the index-wide, pathspec-blind evaluation.)
- **Status:** Confirmed.

### Theory 2: Grouped-path misparse (RULED OUT)
- **Hypothesis:** Same as the archived sibling bug (`group(1)` = domain group ≠ slug).
- **Contradicting evidence:** claude-config bug dirs are UNGROUPED (`docs/bugs/<slug>/`), and the
  grouped-path fix already landed at `e66c02f6`. The offending slugs here ARE distinct real
  features, not the active dispatch's own grouped path.
- **Status:** Ruled Out.

## Proven Findings

The `second-feature-commit` tripwire in `lazy-cycle-containment.sh` sources its evaluated
staged-path set from the entire shared-worktree index (`git diff --cached --name-only`,
`_staged_paths()` line 539) and has no awareness of the pending `git commit`'s own pathspec. Under
sanctioned concurrent same-worktree writers, a foreign lane's staged-but-uncommitted sentinel files
sit in that shared index; being outside the active dispatch's `feature_id` dir and not in
`CARVE_OUT_PATHS`, they populate `offending` and the tripwire false-denies a cycle subagent's
commit — including a fully compliant, pathspec-scoped one. This directly contradicts the
harness's own "concurrent writers are expected, not a defect" contract.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Containment hook — staged-path source | `user/hooks/lazy-cycle-containment.sh` (`_staged_paths()` L539-549; tripwire L716-728) | Index-wide, pathspec-blind evaluation; the fix site. |
| Hook tests | `user/hooks/test_hooks.py` (or the containment test module) | A concurrent-lane-staged-foreign-file regression test is missing; add red→green. |
| Hook docs | `user/hooks/CLAUDE.md` | Should note the tripwire now scopes to the commit's effective pathspec (post-fix). |

## Intervention Hypothesis

- **Hypothesis:** Scoping the second-feature-commit tripwire to the commit's effective pathspec
  eliminates false-DENY of compliant concurrent-lane pathspec-scoped commits WITHOUT reducing
  true-positive catches (bare/`-a`/ambiguity still deny whole-index).
- **If BROKEN:** the metric would look like a DROP in the second-feature-commit deny-recurrence
  count AND a rise in uncaught cross-feature commits (a bare/ambiguous commit that should have
  denied silently allowing) — the two are distinguishable, so "denies stopped" alone would NOT
  read as "working" (the canonical self-emitted tautology this declaration guards against).
- signal_independence: independent — the `INCIDENT.md` incident_key deny-recurrence count in the
  deny ledger (`claude-config|hook-deny|lazy-cycle-containment|second-feature-commit`), an
  independent ledger observable this change does not itself emit or suppress. Expected: the
  false-deny signature (pathspec-scoped commit denied for a foreign concurrent-lane staged path)
  drops to zero recurrence, while the genuine bare/`-a` catch is unaffected (no new signature
  needed to observe the negative case — its absence over subsequent concurrent-completion bursts
  is the confirming signal).

## Open Questions

- **(fix-design, deferred to `/plan-bug`)** Which scoping is correct for the tripwire's evaluated
  set? Candidates: (A) parse the `git commit` command's own pathspec and evaluate ONLY the paths
  that commit will actually include (a bare `git commit`/`-a` still evaluates the whole index —
  preserving the genuine bare-blanket-commit catch; a `git commit <paths>` evaluates only
  `<paths>`); (B) intersect the staged set with paths this tool call explicitly stages; (C)
  suppress denies for foreign paths belonging to a KNOWN concurrent lane. Option A is the natural
  candidate (it keeps the real catch while fixing the false-deny), but the choice — and whether to
  weaken vs. re-scope the gate — is a fix-design decision the harness-change/gate-weakening gate
  must review at planning time. **This is fix-scope, not investigation-scope; not gating for
  conclusion.**
