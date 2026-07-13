---
kind: investigation-spec
bug_id: adhoc-blocker-write-hook-overbroad-scope
---

# block-noncanonical-blocker-write.sh denies ANY blocker-shaped basename anywhere in the tree, with no directory scoping — Investigation Spec

> Observed 2026-07-12 by a concurrent lane: a legitimate Write to the skill
> component `user/skills/_components/blocked-resolution.md` was denied by
> `block-noncanonical-blocker-write.sh` (PreToolUse Write/Edit hook) purely
> because its basename is blocker-shaped, with no connection to the pipeline
> sentinel this hook exists to guard.

**Status:** Fixed
**Severity:** Low
**Discovered:** 2026-07-12
**Concluded:** 2026-07-12
**Placement:** docs/bugs/adhoc-blocker-write-hook-overbroad-scope
**Related:** `user/hooks/block-noncanonical-blocker-write.sh` (the hook);
`user/scripts/lazy_core.py::detect_noncanonical_blocker` (the read-time
sibling this hook mirrors — correctly scoped by its CALLER, which only ever
passes a `docs/features/<slug>/` or `docs/bugs/<slug>/` dir); `docs/bugs/_archive/noncanonical-blocker-filename-invisible-to-state-machine`
(the feature that introduced this write-time hook, if archived under that
name — the write-time layer was always meant to be the mechanical complement
of the read-time detector, which is inherently path-scoped by its call site).

## Reconstructed Route (surface → source)

```
surface: PreToolUse deny — permissionDecision="deny",
  signature="noncanonical-blocker" — fired on a Write/Edit whose target
  basename merely LOOKS blocker-shaped, anywhere in the repository tree.
  ↓
  block-noncanonical-blocker-write.sh :124-131 (pre-fix) — the match rule,
  `_is_noncanonical_blocker(basename)`:
    return (
        basename.upper().startswith("BLOCKED")
        and basename.lower().endswith(".md")
        and basename != "BLOCKED.md"
        and "_RESOLVED_" not in basename
    )
  ↓
  block-noncanonical-blocker-write.sh :134-148 (pre-fix) — `main()` calls
  `_is_noncanonical_blocker(basename)` where `basename` is
  `os.path.basename(file_path)` — the LAST PATH COMPONENT ONLY. No check of
  the containing directory anywhere in the function.
```

`user/skills/_components/blocked-resolution.md` → basename
`blocked-resolution.md` → `"BLOCKED-RESOLUTION.MD".startswith("BLOCKED")` is
True, ends in `.md`, is not exactly `BLOCKED.md`, and does not contain the
literal `_RESOLVED_` (it contains `-resolution`, not `_RESOLVED_`) — so the
pre-fix rule denies a legitimate skill-component edit that has nothing to do
with the lazy/bug pipeline.

## Root Cause

**Cause label: `missing-contract` (a scoping check the hook was never given).**
The read-time sibling this hook mirrors, `lazy_core.detect_noncanonical_blocker`,
is inherently scoped because its ONLY caller (`lazy-state.py`/`bug-state.py`
Step 3) always passes a specific item directory (`docs/features/<slug>/` or
`docs/bugs/<slug>/`) — the function itself never needs a path check because it
is never invoked over the whole tree. The write-time hook, by contrast, fires
on **every** Write/Edit across the entire repo (any `file_path` the harness
touches), so it inherited the read-time match rule verbatim WITHOUT the
scoping its sibling gets for free from its caller. Pipeline sentinels
(`BLOCKED.md` and its mis-named variants) only ever have a reason to exist
under `docs/features/<slug>/` or `docs/bugs/<slug>/` (including
`docs/bugs/_archive/<slug>/`) — any blocker-shaped basename outside those two
trees is definitionally unrelated to the state machine and must never be
denied.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Write-time blocker-name guard | `user/hooks/block-noncanonical-blocker-write.sh` (`_is_noncanonical_blocker` + `main()`) | False-deny on ANY Write/Edit anywhere in the repo whose basename happens to be blocker-shaped, regardless of directory — observed instance: `user/skills/_components/blocked-resolution.md` |

## Fix Scope

Scope the deny to targets under `docs/features/**` and `docs/bugs/**` (the
only trees pipeline sentinels live in) — match the FULL (backslash-normalized)
`file_path` against `(?:^|/)docs/(?:features|bugs)/`, not just the basename.
Keep fail-OPEN throughout (a scope-check error must never turn an allow into a
deny). Add pipe-test legs: deny for `docs/features/x/BLOCKED_foo.md` (in
scope, must still deny — no regression of the load-bearing case) and allow for
`user/skills/_components/blocked-resolution.md` plus any other blocker-shaped
basename outside the two trees.

**Recommendation:** ship the path-scope regex above. Low severity (the hook
is fail-open and the false-deny only ever blocks a rare coincidental filename
match outside the pipeline trees), pure correctness/friction fix — no
containment-safety regression risk (every existing in-scope deny is
preserved).
