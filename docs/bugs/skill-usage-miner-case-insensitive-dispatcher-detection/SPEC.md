# `skill-usage-miner.py` hygiene-sweep case-variant detection unreachable on case-insensitive filesystems — Investigation Spec

> `hygiene_sweep`'s dispatcher-classification branch tested `(entry / "SKILL.md").is_file()` to
> decide whether a skill dir has the canonical dispatcher before falling back to a case-variant
> check. On a case-insensitive filesystem (NTFS/APFS default mounts — this machine included),
> `Path.is_file()` resolves `"SKILL.md"` against an on-disk `skill.md` too, so a lowercase-only
> dispatcher is silently treated as if the canonical file existed. The dir then falls into the
> frontmatter-parsing branch instead of the `case-variant-dispatcher` branch, making that
> hygiene class unreachable on Windows/macOS — the exact platforms most of this tree's skills
> live on.

**Status:** Fixed
**Severity:** P3
**Discovered:** 2026-07-13
**Placement:** docs/bugs/skill-usage-miner-case-insensitive-dispatcher-detection
**Related:** `docs/features/skill-usage-miner/` (the feature that introduced `hygiene_sweep`)

---

## Verified Symptoms

1. **[VERIFIED — reproduced]** `test_hygiene_sweep_flags_all_four_classes` failed on this Windows
   workstation with `'malformed-frontmatter' == 'case-variant-dispatcher'` for a fixture dir
   containing only a lowercase `local-site/skill.md`.
2. **[VERIFIED — code-traced]** `skill-usage-miner.py:hygiene_sweep`'s dir branch: `if (entry /
   "SKILL.md").is_file(): ...` — this check succeeds for a lowercase `skill.md` on a
   case-insensitive mount, so the intended `case_variant = [... p.name.lower() == "skill.md" ...]`
   fallback below it is never reached.

## Root Cause

**Class: script-defect** (skill-usage-miner.py, cross-platform). The canonical-dispatcher
existence check relied on `Path.is_file()`'s default OS case-sensitivity instead of an explicit
exact-case membership test over the directory listing.

## Fix Scope

- `hygiene_sweep` now lists the directory once (`entry.iterdir()`), collects every file whose
  name lowercases to `skill.md`, and picks the EXACT-CASE `"SKILL.md"` match (if any) as canonical
  — a case-variant-only dir (no exact-case match) now correctly falls into
  `case-variant-dispatcher` on every platform, not just case-sensitive ones.
- `test_hygiene_sweep_flags_all_four_classes` also had a separate, unrelated Windows-only
  assertion bug (comparing a dangling-symlink `detail` string with forward slashes against
  `os.readlink()`'s backslash-normalized output) — fixed test-side with a separator-insensitive
  comparison; this part is a test-assumption fix, not a production defect.

## Proven Findings

- `python -m pytest user/scripts/test_skill_usage_miner.py -q` went from 26 passed / 1 failed to
  27 passed / 0 failed on this Windows workstation.
- The production fix (exact-case membership check) is the harness defect; the separator
  comparison is a legitimate test-only fix (Windows `os.readlink()` normalizing separators is
  expected OS behavior, not a bug to work around in production code).
