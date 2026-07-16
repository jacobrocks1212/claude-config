# lazy-cycle-containment second-feature tripwire misparses GROUPED feature paths — Investigation Spec

> `lazy-cycle-containment.sh`'s marker-gated second-feature-commit tripwire decides whether a
> staged path belongs to the active dispatch's feature by extracting a single path segment with
> `_FEATURE_DIR_RE = re.compile(r"docs/(?:features|bugs)/([^/]+)/")` and comparing `group(1)` to
> the marker's `feature_id`. `group(1)` is only the FIRST path segment after
> `docs/(features|bugs)/`. For a GROUPED feature — the layout AlgoBooth uses overwhelmingly
> (`docs/features/audio/<slug>/`, `docs/features/mixer/<slug>/`, …) — that segment is the DOMAIN
> GROUP (`audio`), NOT the feature slug. The marker's `feature_id` is the queue item's bare slug
> (`audio-quality-analysis-visualization`), so `group(1)` (`audio`) never equals it. Result: the
> feature's OWN staged paths are misclassified as a DIFFERENT feature, the carve-out fails, and the
> C2 second-feature tripwire FALSE-DENIES legitimate same-feature cycle-subagent commits.

**Status:** Concluded
**Priority:** P1
**Last updated:** 2026-07-16
**Related:** `docs/specs/turn-routing-enforcement/` (owns the containment hook + the hardening stage that surfaced this — Round in `hardening-log/2026-07.md`). Distinct from the Round-35 finding (`second-feature tripwire over-broad for the /harden-harness Step 2.5 path` — a harden subagent commits a bug spec under a *different* feature dir): that is about cross-workstream harden commits; THIS is about the tripwire mis-parsing the feature's OWN grouped path.

## Verified Symptom

Live AlgoBooth `/lazy-batch` run, item `audio-quality-analysis-visualization`, this cycle (2026-07-16). The apply-resolution cycle subagent's legitimate same-feature `git commit` was DENIED by the containment hook's second-feature-commit tripwire; the subagent had to work around it (unstage-then-stage-with-commit).

Ground truth of the layout (AlgoBooth `docs/features/queue.json`):

```json
{ "id": "audio-quality-analysis-visualization",
  "spec_dir": "audio/audio-quality-analysis-visualization" }
```

- Marker `feature_id` (written by `write_cycle_marker` at `--cycle-begin`, from the queue item `id`) = `audio-quality-analysis-visualization` (bare slug).
- On-disk feature dir = `docs/features/audio/audio-quality-analysis-visualization/…` (grouped).

Reproduction of the mis-parse:

```python
>>> import re
>>> RE = re.compile(r"docs/(?:features|bugs)/([^/]+)/")
>>> RE.search("docs/features/audio/audio-quality-analysis-visualization/SPEC.md").group(1)
'audio'          # ← the DOMAIN GROUP, not the feature slug
```

Because `'audio' != 'audio-quality-analysis-visualization'`:
- `_is_carve_out(path, feature_id)` returns `False` for the feature's OWN paths (carve-out fails).
- the `offending` list comprehension's `_FEATURE_DIR_RE.search(...).group(1) != feature_id` guard is `True`, so every same-feature staged file lands in `offending` → `_deny("second-feature commit tripwire …")`.

Ungrouped features (e.g. `managed-llm-credits` at `docs/features/managed-llm-credits/…`) are unaffected — there `group(1)` IS the slug — which is why every prior test (`feat-A` at `docs/features/feat-A/`) passed and the defect stayed latent. AlgoBooth features are overwhelmingly grouped, so this bit nearly every cycle-subagent commit in the run.

## Root Cause

**Class: hook-defect.** `user/hooks/lazy-cycle-containment.sh`, embedded Python:

- `_FEATURE_DIR_RE` (line ~341) captures only the first segment after `docs/(features|bugs)/`.
- `_is_carve_out` (line ~486) compares `m.group(1) == feature_id`.
- the offending comprehension (line ~630) compares `_FEATURE_DIR_RE.search(p).group(1) != feature_id`.

All three assume a FLAT layout (`docs/features/<slug>/`). The harness's own queue supports a
GROUPED layout via `spec_dir` (`docs/features/<group>/<slug>/`); the tripwire was never made
group-aware. This is a structural mismatch between the segment-extraction membership test and the
two on-disk layouts the queue actually produces — not a missing literal.

## Fix Scope

Make feature membership group-aware, keyed on the marker's `feature_id` (the bare slug), matching
the slug as a FULL path segment whether the feature is grouped (one optional group segment) or
ungrouped:

- Add `_path_under_feature(path, feature_id)` → `re.search(r"docs/(?:features|bugs)/(?:[^/]+/)?" + re.escape(feature_id) + r"/", norm)`.
- `_is_carve_out` delegates feature-membership to `_path_under_feature` (group-aware).
- The `offending` comprehension drops the buggy `.group(1) != feature_id` comparison and relies on
  `_FEATURE_DIR_RE` solely as an "is this path under SOME feature/bug dir?" predicate, with
  `not _is_carve_out(...)` (now group-aware) as the sole membership authority for "a DIFFERENT
  feature."

Boundary (kept tight per the generalization bound): allow exactly ZERO or ONE group segment before
the slug — subsumes the observed grouped instance and its ungrouped near-neighbor; multi-level
grouping is not a layout the queue produces and is deliberately out of scope. `re.escape` +
`/`-boundaries anchor the slug as a full segment so it can never partial-match a longer sibling.

Regression tests (`test_hooks.py`): a grouped same-feature commit must ALLOW; a grouped
different-feature commit must still DENY. Both registered in `_TESTS`.
