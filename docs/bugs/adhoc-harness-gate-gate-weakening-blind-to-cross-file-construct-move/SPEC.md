# harness-gate `gate_weakening` blind to a cross-file construct move — Investigation Spec

> `detect_gate_weakening`'s per-file net-count reconciliation flags a false-positive `hit` when a behavior-preserving refactor MOVES a gate-refusal construct out of one file into a shared sibling within the same change.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-18
**Placement:** docs/bugs/adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move
**Related:** `docs/features/anti-overfit-design-gate/` (the gate this checker implements) · `docs/bugs/adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose` (DISTINCT sibling — path-scoping fix, does NOT apply here) · `user/scripts/harness-gate.py` · `user/skills/_components/harness-change-gate.md`

---

## Verified Symptoms

1. **[REPORTED]** `harness-gate.py`'s `gate_weakening` detector emits `"<hook>.sh: gate-refusal construct removed without replacement (net 1; 1 removed, 0 added)"` and returns `result: "hit"` for a behavior-PRESERVING refactor that moves a deny/refusal construct from a hook into the shared `hook-prelude.sh` / `hook_lib.py` — forcing a redundant operator `GATE_VERDICT.md` sign-off. Source: the ADHOC_BRIEF live case (batch-mode dispatch; no interactive operator this run).
2. **[VERIFIED]** The live case is real and reproducible in git history — the `shared-hook-lib` completion (commits `f7f9493d`..`f08f83ba`, 2026-07-18) migrated 5 enforcement hooks onto the shared prelude; the operator-signed `GATE_VERDICT.md` at commit `1d33c956` records the forced sign-off for this exact `gate_weakening` false positive. Confirmed by inspecting the diffs (e.g. `65f709ec` removes `"permissionDecision": "deny",` from `block-sentinel-write-on-stray-branch.sh` while the construct now lives in the shared lib). Behavior preservation was independently proven green by `test_hooks.py` 266/266 + `test_hook_lib.py`.

## Reproduction Steps

Deterministic — a pure function over a synthetic diff; no runtime, build, or MCP surface.

1. From the repo root, run this one-shot Python reproduction (uses the checker's own diff parser):
   ```bash
   python3 - <<'PY'
   import importlib.util, pathlib
   p = pathlib.Path("user/scripts/harness-gate.py")
   spec = importlib.util.spec_from_file_location("hg", p)
   hg = importlib.util.module_from_spec(spec); spec.loader.exec_module(hg)
   # A construct MOVED from a hook into a shared sibling within ONE change:
   diff = (
     "--- a/user/hooks/block-sentinel-write-on-stray-branch.sh\n"
     "+++ b/user/hooks/block-sentinel-write-on-stray-branch.sh\n"
     "@@ -10,3 +10,1 @@\n"
     '-    "permissionDecision": "deny",\n'
     "     other unchanged line\n"
     "--- a/user/hooks/hook-prelude.sh\n"
     "+++ b/user/hooks/hook-prelude.sh\n"
     "@@ -1,1 +1,2 @@\n"
     '+    "permissionDecision": "deny",\n'
     "     other unchanged line\n"
   )
   print(hg.detect_gate_weakening(hg.parse_diff(diff)))
   PY
   ```
2. Observe the output.

**Expected:** `{'result': 'pass', 'evidence': []}` — the deny construct removed from the hook is re-added in `hook-prelude.sh` within the same change (net-zero across the diff = a MOVE, not a removal).
**Actual:** `{'result': 'hit', 'evidence': ['user/hooks/block-sentinel-write-on-stray-branch.sh: gate-refusal construct removed without replacement (net 1; 1 removed, 0 added)']}` — the per-file loop nets `+1` on the hook and never sees the re-add in the sibling file.
**Consistency:** Always (deterministic).

## Evidence Collected

### Source Code

Root cause is in `detect_gate_weakening` (`user/scripts/harness-gate.py:255`):

- The removed/added deny-construct tallies are built **keyed per file** (`h.file`): `removed_deny[h.file] += len(_DENY_BRANCH_RE.findall(body))` for removed bodies, symmetrically for added (lines 284–289).
- The net-removal check iterates one file at a time and reconciles **only against the same file's adds**: `net = removed_deny[f] - added_deny.get(f, 0)` → flags when `net > 0` (lines 298–304). The identical shape governs the `def test_*` tally (lines 290–297).
- `_DENY_BRANCH_RE = permissionDecision…deny | \bexit 3\b | refuse_[a-z_]+\s*\(` (line 94) — the migrated `"permissionDecision": "deny"` line matches, so a hook that loses it to the shared lib nets `+1`.
- The already-shipped same-file reconciliation (fixture `test_gate_weakening_reformatted_refuse_call_not_flagged`, test file line 277) proves the *net-count* idea works **within one file** (a single-line→multi-line `refuse_*()` reformat is net-zero). The gap is strictly the **cross-file** case: the reconciliation denominator is same-file only, so a construct that leaves file A for file B is uncounted.

### Runtime Evidence

None applicable — `harness-gate.py` is stdlib, READ-ONLY over git, not on any state-script path; the defect is a pure deterministic diff-analysis result, not runtime-coupled.

### Git History

`bdcd743f chore(bugs): enqueue harness-gate cross-file gate_weakening false-positive` seeded this bug. The triggering work is the `shared-hook-lib` feature: `f7f9493d`/`65f709ec`/`64bf8653`/`f08f83ba` (the WU-1..4 hook migrations) each strip shared boilerplate — including deny-shaped lines — into `hook-prelude.sh`/`hook_lib.py`; `1d33c956` is the operator-signed `GATE_VERDICT.md` overriding this false positive; `98509dff` marked the feature Complete.

### Related Documentation

- Root `CLAUDE.md` Scripts table + `user/scripts/CLAUDE.md` `harness-gate.py` row: `gate_weakening` is "diff-level, NEVER judgment-passable, routes to operator sign-off (SPEC D4)". A false positive here is not merely noise — it mandates a human sign-off, so it directly taxes the operator.
- `harness-change-gate.md` (the adversarial half) records the `GATE_VERDICT.md`; blocking authority is at the completion-gate ship seam (`lazy_core.gate_verdict_ok`).
- **DISTINCT from** `adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose`: that bug's fix restricts scanning to code/manifest paths. These hooks ARE code files, so path-scoping does NOT address this — the fix must reconcile removed-vs-added constructs across the change's file set.

## Theories

### Theory 1: Per-file reconciliation denominator cannot see a cross-file move
- **Hypothesis:** the net-removal check reconciles a file's removed deny constructs only against **that same file's** additions, so a construct relocated into a sibling file within the same change nets `+1` on the source file and is misread as an unreplaced removal.
- **Supporting evidence:** direct code read (lines 284–304); the one-shot reproduction; the git-confirmed live incident with a green behavior-preservation test suite.
- **Contradicting evidence:** none.
- **Status:** **Confirmed** — cause label **`traced`** (serving path cited below, fix site on-path; not runtime-coupled, static read sufficient).

## Proven Findings

**Root cause (label: `traced`).** Serving path of the false-positive `hit`, surface → source:

```
detect_gate_weakening(...) result == "hit"          user/scripts/harness-gate.py:328
  ← evidence "…removed without replacement (net 1…)" user/scripts/harness-gate.py:301-304
  ← net = removed_deny[f] - added_deny.get(f, 0)     user/scripts/harness-gate.py:298-299  ← per-FILE reconciliation (the defect)
  ← removed_deny/added_deny keyed on h.file          user/scripts/harness-gate.py:284-289
  ← detect_gate_weakening(hunks) called              user/scripts/harness-gate.py:385 (run_checker)
```

**Fix site (on the traced path):** the `for f in removed_deny:` net loop (lines 298–304) — its added-construct denominator is same-file (`added_deny.get(f, 0)`) where it must be a whole-change total. The structurally-identical `def test_*` loop (lines 290–297) has the same blindness and should be fixed in lockstep (a test def moved between test files is the same shape).

**Fix vector (for `/plan-bug`; not locked here):** reconcile removed-vs-added gate-refusal constructs (and test defs) **across the whole change's file set** — a construct removed from file A but added in file B within the same commit range is a MOVE (net-zero across the diff), not a removal. Add a regression fixture for the cross-file-move shape (the `test_hooks`-migration diff is the archetype), keeping the existing same-file net fixtures and the true-positive fixtures (`test_gate_weakening_removed_refuse_construct_still_hits`, `..._genuine_test_removal_still_hits`) green.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| `gate_weakening` detector | `user/scripts/harness-gate.py` (`detect_gate_weakening`, lines 255–328) | Per-file net reconciliation → false-positive `hit` on a cross-file construct move |
| Regression fixtures | `user/scripts/test_harness_gate.py` | Add a cross-file-move FP fixture; preserve existing same-file + true-positive fixtures |

## Open Questions

- **(Design fork — for `/plan-bug`, PRODUCT-class: false-negative surface of a security gate.)** Whole-change reconciliation admits two shapes with different false-negative risk: (a) **aggregate net** (sum removed across all files vs sum added across all files) — simplest, but a genuine removal in file A masked by an *unrelated* deny construct added in file B nets to zero and evades the gate; (b) **content-identity move detection** (reconcile a removal in A only when the same construct text is added in B) — precise, near-zero false-negative surface, more code. `/plan-bug`'s SEAM A findings gate and the anti-overfit/`harness-change-gate` (this fix edits a control surface AND relaxes a detector — it will itself route to operator sign-off) should decide (b) vs (a). Recommendation: **(b)**, to avoid weakening the gate-weakening detector.

## Locked Decisions

1. **Cross-file reconciliation shape for `gate_weakening`** (`NEEDS_INPUT.md`, operator-accepted
   2026-07-19, recorded via `bug-state.py --record-decision`): **(b) Content-identity move
   detection** — reconcile a removal in file A only when the same construct text is added in file
   B within the same change; anything else still counts as a removal. Locked for `/plan-bug`: do
   NOT implement (a) aggregate-net or (c) exemption-marker shapes.
