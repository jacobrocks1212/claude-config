---
title: "cognito-pr-review prep-pr.ts silently no-ops when invoked via the documented ~/.claude/plugins symlink path"
status: Fixed
priority: Critical
date: 2026-07-22
---

## Verified Symptom

`prep-pr.ts` (the `cognito-pr-review` plugin's deterministic PR-prep script) exits 0 with
**zero stdout/stderr** and never runs its CLI dispatch when invoked via the path documented in
the command skills:

```
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/prep-pr.ts {pr_id}
```

This is Step 1 of every `/cognito-pr-review:review-pr` and `/cognito-pr-review:spot-check` run
(`commands/review-pr.md` lines 116/122, `commands/spot-check.md` lines 81/87). The silent no-op
makes the documented invocation appear to hang / do nothing with no diagnostic — a silent
failure at the very first step of every PR review.

**Reproduced (2026-07-22):**
- Via the documented **symlink** path: no output, `EXIT=0`.
- Via the **realpath** (`.../claude-config/user/plugins/.../prep-pr.ts`): prints the usage banner
  and `EXIT=1` (correct — the CLI dispatch ran).

## Root Cause

`~/.claude/plugins/...` is a symlink chain into `claude-config/user/plugins/...`. The CLI entry
point is guarded by:

```ts
const isMainModule = import.meta.url === pathToFileURL(process.argv[1] ?? "").href;
```

When invoked through the symlinked path, `tsx`/node resolves `import.meta.url` to the module's
**realpath** (`.../claude-config/user/plugins/.../prep-pr.ts`) while `process.argv[1]` remains the
**symlink path** (`.../.claude/plugins/.../prep-pr.ts`) exactly as typed on the command line. The
two `file://` URLs differ, so `isMainModule` is `false`, the `if (isMainModule) { ... }` block
(the entire CLI dispatch — `parseArgs`, `process.chdir`, `prepPR`/`prepLocal`) is skipped, and the
module loads to completion with no output and exit code 0.

The guard exists for a real reason: `prep-pr.test.ts` imports `detectReReview`, `readReviewedSha`,
and `computeIterationDiff` from `./prep-pr.ts`, and must be able to do so without triggering
`process.chdir`/`process.exit`. The defect is only that the equality test is not symlink-agnostic.

## Classification

**Root cause class:** script-defect

**Files affected:**
- `user/plugins/local-tools/plugins/cognito-pr-review/scripts/prep-pr.ts` (line 2235 — the
  `isMainModule` guard).

**Files checked and NOT affected (task-directed sibling audit):** `aggregate-findings.ts`,
`post-process.ts`, `emit-chunk-index.ts`, `disposition-calibration.ts` do **not** use the
`import.meta.url === pathToFileURL(process.argv[1]).href` guard at all — each calls `main()`
unconditionally at module end and has **no** `import.meta` reference. Their test files
(`post-process.test.ts`, `disposition-calibration.test.ts`) shell the scripts via `execSync`
rather than importing them, so an unconditional `main()` is safe. Because they run
unconditionally, they are **not** subject to the symlink no-op — the fix is scoped to
`prep-pr.ts` alone. (The task's premise that the siblings share the guard is incorrect;
verified by grep across the whole `scripts/` dir — only `prep-pr.ts` matches.)

## Proposed Fix Scope

Make the main-module detection symlink-agnostic: resolve both `fileURLToPath(import.meta.url)` and
`process.argv[1]` through `fs.realpathSync.native` before comparing, so the documented
`~/.claude/...` invocation matches the realpath the module actually loaded from. Fall back to a
`path.resolve` comparison if `realpathSync` throws (e.g. argv[1] not a real file). Preserve the
existing intent: the guard must remain `false` when the module is imported by a test (whose
entry file / argv[1] is the test runner, not `prep-pr.ts`).

Add a regression test asserting the detection is symlink-invariant, and run the existing
`prep-pr.test.ts` suite.

## Related

- `docs/specs/turn-routing-enforcement/` — hardening stage / hardening-log home for this fix.

**Fixed:** 2026-07-22
**Fix commit:** 669609be
