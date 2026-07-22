---
kind: fixed
feature_id: prep-pr-main-module-guard-symlink-noop
date: 2026-07-22
provenance: backfilled-unverified
validated_via: cognito-pr-review plugin test suites (prep-pr.test.ts 12/12 incl. 4 new symlink-invariance tests; post-process + disposition-calibration 29/29) + tsc --noEmit OK + end-to-end symlink repro (usage banner + exit 1); NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

prep-pr-main-module-guard-symlink-noop marked Fixed on 2026-07-22 during an inline manual
`/harden-harness` round (Round 130). This receipt was written by the harden round, not the bug
pipeline's `__mark_fixed__` gate — provenance is `backfilled-unverified`.

## Notes

Root cause: `prep-pr.ts` guarded its CLI dispatch with a raw file-URL equality
(`import.meta.url === pathToFileURL(process.argv[1]).href`) that is false when the module is
reached through the documented `~/.claude/plugins/...` symlink (import.meta.url = realpath,
argv[1] = symlink path), silently skipping the entire dispatch (exit 0, no output).

Fix (commit `641ce631`): extracted an exported pure `isMainModuleInvocation(moduleUrl, argv1)`
that resolves both sides through `fs.realpathSync.native` before comparing, with a
normalized-`path.resolve` fallback; removed the now-unused `pathToFileURL` import; added four
regression tests (symlink / direct / imported-by-different-entry / missing-argv). Only
`prep-pr.ts` used this guard — the sibling scripts call `main()` unconditionally and were
unaffected.

Verification: `npx tsx --test prep-pr.test.ts` → 12/12; sibling suites 29/29; `tsc --noEmit`
exit 0; end-to-end symlink invocation now prints the usage banner and exits 1.
