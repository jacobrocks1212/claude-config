# `setup.py` Windows extended-length-path prefix breaks symlink target comparison — Investigation Spec

> On Windows, `os.readlink()` reports a symlink's stored target with the NT extended-length
> prefix (`\\?\`, or its UNC variant `\\?\UNC\`) prepended, even when the symlink was created
> from a plain absolute path with no such prefix. `setup.py`'s `_resolve_target`/`_targets_equal`
> compared the raw `os.readlink()` output against the prefix-free repo path, so every
> correctly-linked mapping on Windows reported `WRONG` instead of `OK` — `cmd_check` never
> converged to 0 broken, `cmd_repair` re-relinked already-correct links every run (non-idempotent),
> and `TestEndToEnd::test_bootstrap_is_idempotent` (and 7 sibling tests) failed on this host.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-13
**Fixed:** 2026-07-13
**Fix commit:** e4c7d5e0
**Placement:** docs/bugs/setup-py-windows-extended-path-prefix-mismatch
**Related:** `docs/features/cross-platform-setup/` (the feature that introduced `setup.py`)

---

## Verified Symptoms

1. **[VERIFIED — reproduced]** `python -m pytest user/scripts/test_setup_py.py -q` on this Windows
   10 workstation: 8 failures, including `TestLinkPrimitivesPosix::test_create_and_detect_symlink`,
   `TestCheck::test_ok_and_exit_0`, `TestRepair::test_repair_then_check_roundtrip`, and
   `TestEndToEnd::test_bootstrap_is_idempotent`.
2. **[VERIFIED — code-traced]** `setup.py:_create_link` calls `os.symlink(repo, live, ...)` with a
   plain absolute `repo` path (no `\\?\` prefix). `setup.py:_resolve_target` then calls
   `_readlink(link_path)` → bare `os.readlink(path)` and compares the result (verbatim, via
   `os.path.normcase(os.path.normpath(os.path.abspath(target)))`) against the repo path. Live
   repro: creating a symlink to `C:\Users\...\repo-side.txt` and immediately reading it back
   returned `\\?\C:\Users\...\repo-side.txt` — Windows itself adds the prefix to the reparse
   point's stored substitute name; `os.path.abspath` does not strip it (the path is already
   absolute by `os.path.isabs`'s own test, so `abspath` short-circuits without normalizing away
   the prefix).

## Root Cause

**Class: script-defect** (setup.py, Windows-only branch). `_readlink` (the patchable seam wrapping
`os.readlink`) returned the raw OS value including the extended-length prefix; every downstream
comparison and the `WRONG` diagnostic print inherited the un-normalized value with no stripping
step.

## Fix Scope

- `setup.py:_readlink` now strips the `\\?\` / `\\?\UNC\` prefix on Windows via a new
  `_strip_extended_prefix` helper before returning, so `_resolve_target`, `_targets_equal`, and the
  `cmd_check` `WRONG` print all see the prefix-free target consistently — cross-platform behavior
  restored (POSIX untouched; `_WINDOWS` guard scopes the strip).
- All 66 tests in `user/scripts/test_setup_py.py` pass (previously 58/66; the 8 failures traced
  above are all fixed by this one change — no test-side workaround needed, the symptom was a real
  bug on the host `setup.py` must run on).

## Proven Findings

- The fix is a 15-line addition (`_strip_extended_prefix` + one call site in `_readlink`); no test
  assumption was wrong and no capability is genuinely privilege-gated here — Developer Mode /
  admin privilege for symlink creation is a SEPARATE, already-handled path (`_create_link`'s
  `OSError` → junction fallback / actionable error), not the cause of these 8 failures.
