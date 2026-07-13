# PR-review plugin cache split-brain — runtime loads a frozen versioned cache while calibration writes the repo copy — Investigation Spec

> Claude Code serves the cognito-pr-review plugin from the versioned install cache (`~/.claude/plugins/cache/local-tools/cognito-pr-review/2.9.0/`, snapshotted 2026-06-30), while the calibration writers (`disposition-calibration.ts`, invoked with an explicit symlink path) mutate the claude-config repo copy — so `knowledge/` (weights + rules) exists in two silently divergent versions, and repo-side weight/rule edits are invisible to cache-served consumers until a version bump reinstalls the plugin.

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-09
**Placement:** docs/bugs/pr-review-plugin-cache-split-brain-freezes-weights
**Related:** `docs/bugs/pr-review-source-weights-drift-zeroes-opus-lane` (the threshold half of the weights failure; its 0.7 stopgap floor landed only in the repo copy — the cache still carries drifted values); `docs/bugs/pr-review-ema-calibration-statistical-design-drives-lane-death` (why the values drift at all); `docs/bugs/pr-review-pending-calibration-marker-unconsumable-nonbuddy`; planned feature SPECs `docs/features/pr-review-plugin-repo-scoping-and-orphan-purge` and `docs/features/pr-review-sweep-rule-sharding-and-read-dedup` (both edit plugin files and inherit this staleness hazard until fixed)

---

## Verified Symptoms

1. **[VERIFIED]** The installed plugin loads from the versioned cache, not the authored repo: `~/.claude/plugins/installed_plugins.json` records `"installPath": "C:\\Users\\JacobMadsen\\.claude\\plugins\\cache\\local-tools\\cognito-pr-review\\2.9.0"`, `"lastUpdated": "2026-06-30T17:38:00.117Z"` — confirmed by direct read on 2026-07-09.
2. **[VERIFIED]** The two copies of `knowledge/weights.yaml` diverge materially: cache `source_weights` = `investigation: 0.1919 / intrafile: 0.3707 / reuse: 0.3938` (drifted, below or near the 0.3 drop threshold); repo copy = all three stopgap-floored to `0.7` (with the bug-warning comment from the sibling bug). Confirmed by reading both files on 2026-07-09.
3. **[VERIFIED]** `diff -rq` between cache 2.9.0 and the repo plugin dir shows `knowledge/weights.yaml`, `knowledge/rules/csharp-architecture.yaml`, and `knowledge/rules/testing.yaml` differ; `commands/` and `agents/` are (currently) identical. Rule edits made in the repo after 2026-06-30 are absent from the served copy.
4. **[VERIFIED]** Reporter (Jacob) confirmed the user-facing symptom in the originating session: "The EMA weight recalibration system … was intended to iteratively align the review plugin's issue surfacing to my own issue surfacing, but it seems to be broken."

## Reproduction Steps

1. Read the live install pointer: `python -c "import json;d=json.load(open(r'C:\Users\JacobMadsen\.claude\plugins\installed_plugins.json'));print(d['plugins']['cognito-pr-review@local-tools'][0]['installPath'])"` → the cache 2.9.0 path.
2. `diff ~/.claude/plugins/cache/local-tools/cognito-pr-review/2.9.0/knowledge/weights.yaml ~/.claude/plugins/local-tools/plugins/cognito-pr-review/knowledge/weights.yaml` → non-empty diff (`source_weights` 0.1919/0.3707/0.3938 vs 0.7/0.7/0.7).
3. Run any `/cognito-pr-review:review-pr-buddy <id>` to completion — Phase 2's auto-recalibration invokes `npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/disposition-calibration.ts --weights ~/.claude/plugins/local-tools/plugins/cognito-pr-review/knowledge/weights.yaml` (review-pr-buddy.md:394-399), mutating the **repo** copy only.
4. Re-run step 2.

**Expected:** One authoritative `weights.yaml`; a calibration write is observed by every subsequent consumer.
**Actual:** The diff persists (and grows with every calibration write); the cache copy is frozen at its 2026-06-30 snapshot until a version bump + reinstall.
**Consistency:** Always — structural, not timing-dependent.

## Evidence Collected

### Source Code — root-cause trace (`traced`)

All plugin paths relative to `user/plugins/local-tools/plugins/cognito-pr-review/` in claude-config unless prefixed.

**Write path (calibration → repo copy):**

```
buddy Phase 2 "Auto-Recalibrate from Dispositions"
  → npx tsx {plugin_root}/scripts/disposition-calibration.ts
        --weights {plugin_root}/knowledge/weights.yaml        commands/review-pr-buddy.md:394-399
  → {plugin_root} = ~/.claude/plugins/local-tools/plugins/
        cognito-pr-review                                     commands/review-pr-buddy.md:13
  → ~/.claude/plugins/local-tools/plugins/cognito-pr-review
        is a symlink → claude-config repo plugin dir          verified: ls -la (lrwxrwxrwx, 2026-06-08)
  → writeFileSync(weightsPath, text)                          scripts/disposition-calibration.ts:278
  ⇒ calibration mutates the REPO copy                          ← one side of the split
```

(Same for `/learn-from-pr` — commands/learn-from-pr.md:13 declares the identical plugin root; its §2.5.7 helper invocation at :152-156 passes the same `--weights` path. `calibrate-weights.ts` hardcodes the same symlink path at scripts/calibrate-weights.ts:20-22, though nothing invokes it.)

**Read path (runtime definitions → cache copy):**

```
Claude Code plugin loader
  → installPath = …\plugins\cache\local-tools\
        cognito-pr-review\2.9.0                               ~/.claude/plugins/installed_plugins.json ("cognito-pr-review@local-tools")
  → command bodies, agent definitions (incl. sweep.md with
        its embedded RULES block), and the knowledge/ tree
        are served from that snapshot                          cache dir listing; snapshot mtime 2026-06-30
  → cache knowledge/weights.yaml carries the pre-stopgap
        drifted source_weights (0.1919 / 0.3707 / 0.3938)     cache …/2.9.0/knowledge/weights.yaml:16-19
  ⇒ repo-side edits to knowledge/ (and any future command/
        agent edit) are INVISIBLE to the served plugin
        until a version bump + reinstall                       ← the other side of the split; fix-site on path
```

**Which copy each weights consumer actually reads (verified per consumer):**

| Consumer | Resolution | Copy read |
|----------|-----------|-----------|
| `post-process.ts` `loadWeights()` | `resolve(scriptDir, "..", "knowledge", "weights.yaml")` (scripts/post-process.ts:179-181); invoked via the explicit symlink path (commands/review-pr.md:406) | **repo** |
| `disposition-calibration.ts` (default fallback) | `resolve(scriptDir, "..", …)` (scripts/disposition-calibration.ts:102-104); buddy passes `--weights` explicitly anyway | **repo** |
| `calibrate-weights.ts` | absolute symlink path hardcoded (scripts/calibrate-weights.ts:20-22) | **repo** (orphaned — no invoker) |
| sweep agent (runtime weights read) | prose-relative instruction "Read `knowledge/weights.yaml` (sibling to this file's parent directory)" (agents/sweep.md:47) — no `${CLAUDE_PLUGIN_ROOT}`, no absolute path; the executing agent's cwd is the work repo, so it must *guess* a plugin root, and both the cache and symlink roots exist | **ambiguous** (see Open Questions) |
| sweep agent (embedded rule content) | `RULES_START/END` block inside the agent definition itself, served from the cache snapshot | **cache** |

No file in the plugin references `${CLAUDE_PLUGIN_ROOT}` (grep across commands/ + agents/: zero hits), so nothing resolves the install path uniformly.

### Runtime Evidence

- The cache's drifted values differ from BOTH the pre-stopgap repo values recorded in the sibling bug (0.2933/0.2681) and the current floored repo values (0.7) — i.e., at least three generations of `weights.yaml` have existed since 2026-06-01, and which one a consumer saw depended on which copy it resolved.
- Session mining in the originating investigation (~40 review runs) shows reviews ran throughout this window with the operator believing one weights file was in effect.

### Git History

- Repo `weights.yaml` stopgap floor committed 2026-07-09 (uncommitted working-tree edit at investigation time, referencing the sibling bug). Cache snapshot predates it (2026-06-30T17:38Z per `installed_plugins.json`); cache is not git-tracked.

### Related Documentation

- Plugin `CLAUDE.md` ("weights.yaml is the **single source of truth** for weights, read live at runtime") — the single-source claim is violated by the install mechanism itself.
- `docs/bugs/pr-review-source-weights-drift-zeroes-opus-lane/SPEC.md` — its "Stopgap Applied" section floored only the repo copy; this bug means that stopgap does not reach cache-served consumers.

## Theories

### Theory 1: Versioned-cache install semantics with no invalidation on source edit
- **Hypothesis:** Claude Code's marketplace installer snapshots the plugin into `plugins/cache/<marketplace>/<plugin>/<version>/` at install/update time and serves from there; editing the marketplace source (the symlinked repo) does not invalidate the snapshot, and the version string (2.9.0) hasn't changed since 2026-06-30, so no re-snapshot occurred.
- **Supporting evidence:** `installed_plugins.json` installPath + lastUpdated; three cached versions present (2.7.0, 2.8.0, 2.9.0) tracking `plugin.json` version bumps; diff confirms post-snapshot repo edits absent from cache.
- **Status:** Confirmed (mechanism observed directly; the exact loader code is Claude Code internal, but every observable agrees).

### Theory 2: The plugin's path discipline makes the split silent
- **Hypothesis:** Because scripts are invoked by explicit symlink path while definitions load from the cache, each half of the pipeline sees a self-consistent world and nothing ever compares the two — so the divergence produces no error, only drift in behavior.
- **Supporting evidence:** The consumer table above; no `${CLAUDE_PLUGIN_ROOT}` usage; sweep's prose-relative weights path.
- **Status:** Confirmed.

## Proven Findings

- **CONFIRMED:** Two divergent copies of `knowledge/` exist simultaneously (diff evidence), with calibration writing one and the plugin loader serving the other. Any repo-side fix to weights or rules (including the sibling bug's 0.7 floor) is inert for cache-served consumers until `plugin.json` is version-bumped and the plugin updated.
- **CONFIRMED:** The write path and the definition-serving path resolve different physical files by construction (trace above) — this is the root cause of "recalibration seems broken": the loop writes, but the served snapshot never learns.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Install/serve mechanism | `~/.claude/plugins/installed_plugins.json`; `~/.claude/plugins/cache/local-tools/cognito-pr-review/2.9.0/**` | Frozen snapshot serves agents/commands/knowledge |
| Calibration writers | `scripts/disposition-calibration.ts` (:102-104, :278), `commands/learn-from-pr.md` (:13, :152-156), `scripts/calibrate-weights.ts` (:20-22) | All write the repo copy only |
| Weights readers | `scripts/post-process.ts` (:179-181), `agents/sweep.md` (:47 + embedded RULES block) | Mixed repo/cache/ambiguous resolution |
| Rule pipeline | `knowledge/rules/*.yaml`, `/rebuild-agents` | Repo rule edits invisible to served sweep.md until version bump |

## Candidate Root Fixes (for /plan-bug)

1. **Move mutable state out of the plugin entirely** — relocate `weights.yaml` to a stable, version-independent absolute path (e.g. `~/.claude/state/cognito-pr-review/weights.yaml`), read/written by `post-process.ts`, `disposition-calibration.ts`, and the sweep agent's instruction via that one absolute path (with a one-time migration copy + a tombstone comment in the plugin's knowledge/ copy). Calibration then survives version bumps and the cache/repo question becomes irrelevant for weights. Preferred: it separates *mutable state* from *shipped definition*, which is the actual design error.
2. **Version-bump discipline (short-term operational fix)** — treat any `knowledge/` or command/agent edit as requiring a `plugin.json` version bump + plugin update so the cache re-snapshots; add a check (doc-drift-lint-style) that fails when the cache copy diverges from the repo at the same version.
3. **Resolve every internal path through one root** — replace prose-relative paths (sweep.md:47) and per-file absolute paths with `${CLAUDE_PLUGIN_ROOT}` so at least all *definition-side* reads are self-consistent with the served snapshot, and scripts receive the root explicitly. (Complements fix 1; does not by itself un-freeze the cache.)
4. **Convert to an in-place-loaded plugin form** *(docs-confirmed viable 2026-07-09)* — Claude Code has NO serve-from-source mode for marketplace plugins (the cache is always the serving location), but two in-place forms exist: `--plugin-dir <path>` (per-session, not persisted) and **`@skills-dir` plugins** (a plugin living under `~/.claude/skills/<name>/` with `.claude-plugin/plugin.json`, discovered in place with no caching; `/reload-plugins` picks up non-SKILL.md edits). Migrating cognito-pr-review to the `@skills-dir` form would eliminate the cache entirely — the strongest structural resolution, at the cost of a marketplace→skills-dir migration and re-verifying agent/command registration behavior. Evaluate against fix 1 at `/plan-bug` (fix 1 solves only the mutable-state half; fix 4 solves definitions too).

## Open Questions

- Which physical `weights.yaml` does the sweep agent resolve in live runs — the cache root or the symlink root? (Both exist; the instruction at agents/sweep.md:47 names neither. Answerable by mining a sweep subagent transcript's Read paths; irrelevant once fix 1 lands, since both would point at the state path.)
- ~~Does Claude Code offer a "development/linked" plugin install mode that serves directly from the marketplace path?~~ **ANSWERED (2026-07-09, Claude Code docs):** No — marketplace plugins always serve from the versioned cache; there is no linked/dev serving mode. The in-place alternatives are `--plugin-dir` (per-session) and `@skills-dir` plugins — captured as Candidate Root Fix 4 above.
