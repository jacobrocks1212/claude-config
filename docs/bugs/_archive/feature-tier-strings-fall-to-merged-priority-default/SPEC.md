# Feature tier strings fall to MERGED_PRIORITY_DEFAULT, sorting real features dead-last

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-17
**Fixed:** 2026-07-18
**Fix commit:** 2bd559ee
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage);
`docs/bugs/_archive/no-sanctioned-cli-for-queue-state-mutations/` (the `--set-tier` /
`--set-severity` mutator this extends); `docs/bugs/bug-queue-aging-backpressure/`
(the bug-severity axis of `merged_priority` that features are now unified onto).

## Trigger

Manual `/harden-harness` invocation (operator-directed, 2026-07-17). Jacob observed that
`lazy_core.merged_priority` maps a bug's `severity` (P0/P1/P2/Low) and a feature's `tier`
onto one integer scale (lower = higher priority), but the `tier` normalizer only accepts a
bare integer or a numeric string. Every NON-integer feature-tier string in real use —
`milestone`, `commercialization`, `major-initiative`, `follow-up`, `non-audio`, `4a`, `4b`
— fails `int()` parse and falls through to `MERGED_PRIORITY_DEFAULT = 99`, so those features
sort **dead-last** in the merged worklist regardless of their intended priority.

## Root cause

**`root_cause_class: missing-contract`** — the feature axis of the unified priority scale was
only ever specified for integer tiers. `merged_priority("feature", …)` (`depdag.py`) does:

```python
if isinstance(tier, int): return tier
if isinstance(tier, str):
    try: return int(tier.strip())
    except (ValueError, AttributeError): return MERGED_PRIORITY_DEFAULT
return MERGED_PRIORITY_DEFAULT
```

There is no named-enum vocabulary for feature tiers parallel to the bug side's
`_MERGED_SEVERITY_RANK = {"P0":0,"P1":1,"P2":2,"Low":3}`. A feature author who wrote an
intent-carrying tier name (the natural thing to do) silently got the worst possible
priority — a false-deprioritization that is invisible until you inspect the merged sort.

## Verified symptom

`merged_priority("feature", {"tier": "milestone"}) == 99` today (== `MERGED_PRIORITY_DEFAULT`),
identical to a feature with **no tier at all** — the intent is completely lost. Confirmed by
reading the normalizer and by the absence of any `_FEATURE_TIER_*` map anywhere in
`lazy_core`.

## Fix scope

Unify the feature-tier system with the bug-severity system on one integer scale:

1. **Named feature-tier enums** (`_FEATURE_TIER_ENUM`) parallel to `_MERGED_SEVERITY_RANK`,
   each mapping to an integer priority on the SAME scale (lower = higher priority).
2. **Multi-enum features:** a `tier` may be a single enum name OR a list of enum names (and
   may still mix bare ints / numeric strings). Effective priority = **MIN** of the resolved
   values (highest-priority enum wins).
3. **`pre-release` → 1** (== P1). Load-bearing ordering: `merged_priority(P0 bug) = 0 <
   merged_priority(pre-release feature) = 1 < merged_priority(P2 bug) = 2`.
4. **Coherent integer values for the legacy strings** currently defaulting to 99. The exact
   legacy-string → int mapping is a genuine PRODUCT decision (it reorders which real features
   outrank which), so it is implemented as a **recommended provisional** mapping and surfaced
   for operator ratification via `NEEDS_INPUT_PROVISIONAL.md` (park-provisional disposition,
   grade `contained` — a wrong pick is a one-constant redirect, no data/architecture fork).
   `pre-release = 1` is NOT provisional (operator-locked by requirement 3).
5. **Backward compat (HARD):** bare int tiers, bug severity, and null/missing fields keep
   byte-identical behavior. A feature with no tier still defaults to last. Only the previously
   `→ 99` legacy STRING tiers change (the entire point).
6. **`--set-tier` mutator** accepts enum names (single, comma-separated, or list) in addition
   to bare ints, validating against the enum vocabulary.
7. **Queue-doc badge** (`lazy-queue-doc.py`) renders enum-name / list tiers with their
   effective priority (bare-int tiers keep the historic `T<n>` form).
8. **Documentation** of the enum → int table on the `depdag.py` / `user/scripts/CLAUDE.md`
   surface.

## Recommended provisional legacy mapping (surfaced for ratification)

| Tier enum            | Int | Rationale (recommended — operator ratifies)                          |
|----------------------|-----|----------------------------------------------------------------------|
| `pre-release`        | 1   | **LOCKED** by requirement 3 (== P1). NOT provisional.                |
| `commercialization`  | 2   | Revenue/commercial work — business-critical, just below pre-release. |
| `milestone`          | 3   | A delivery milestone.                                                |
| `major-initiative`   | 4   | Large strategic initiative, longer horizon.                          |
| `4a`                 | 4   | Legacy phase-4 sub-tier a → tier-4 band.                             |
| `4b`                 | 5   | Legacy phase-4 sub-tier b → after 4a.                               |
| `follow-up`          | 6   | Deferred follow-up work — low.                                       |
| `non-audio`          | 7   | Non-audio work — lowest of the named set (audio-first product).      |

Bare integer tiers (`0`, `1`, `5`, `6`, …) keep their literal values; enum values are chosen
to slot coherently into that same scale.
