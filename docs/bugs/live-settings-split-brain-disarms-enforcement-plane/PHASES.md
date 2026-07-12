# Implementation Phases — Live settings split-brain disarms the enforcement plane

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is a config/scripts/docs harness repo with no app runtime or MCP server; every deliverable here is a tracked settings/script/doc edit plus one live-machine symlink restore, all structurally outside MCP reach (mcp-testing SPEC "no app integration" class).

## Root-Cause Trace (SEAM A — recorded, `traced`)

The causal finding is **`traced`**, not `asserted` — the symptom's serving path was read surface→source and the fix site lies on it:

```
symptom: enforcement hooks (containment/sentinel/build/push/kill) never fire on this laptop;
         dispatch guard unwired wherever the symlink IS intact
  → Claude Code fires only hooks registered in the LIVE ~/.claude/settings.json   (hook interface)
  → live ~/.claude/settings.json is a REAL file (not the symlink)                 C:\Users\Jacob\.claude\settings.json  (LinkType empty, mtime 2026-06-11 23:24)
  → its `hooks` object registers ONLY the turn-routing pair                       ~/.claude/settings.json:13-60 (lazy-route-inject, lazy-dispatch-guard)
  → the tracked SSOT registers the OTHER 10 hooks but never the guard             user/settings.json:24-119
  → manifest declares the live path a symlink to the tracked file (never restored) manifest.psd1:14
data source: the two hook sets were never reconciled in either direction
```

**Fix site on path:** the fix changes the exact nodes on this path — merge the turn-routing pair into the tracked SSOT (`user/settings.json`), restore the live symlink so Claude Code reads the reconciled SSOT, and add a live-vs-tracked drift check so the split re-announces. Each is *on* the serving path, not merely related to it. Root cause classified in SPEC as `config-split-brain`.

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC — this bug has no hard upstream feature dependencies (the `--sync-deps` projection is therefore a no-op and was skipped). The `**Related:**` items are sequencing/context, not build dependencies:

- **`docs/specs/turn-routing-enforcement/` (context):** SPEC.md:114 §"Settings placement" is the design this bug retires (it deliberately declared per-machine hook registration and deferred unification). `REGISTRATION.md` is the paste-fragment operationalization retired here. Both are **edited** by Phase 4, not consumed as a build contract.
- **`docs/bugs/legacy-tool-input-env-hooks-dead/` + `docs/bugs/powershell-tool-bypasses-bash-matched-guards/` (downstream siblings, D4 sequencing):** both edit the SAME reconciled `user/settings.json` SSOT. Per SPEC D4, land THIS reconciliation FIRST so the revived/widened registrations those bugs add are never re-split. This bug does not implement their fixes; it only establishes the single SSOT they build on.

## Validated Assumptions

Ground-truth confirmed live 2026-07-11/12 via a read-only touchpoint audit (all corroborated, zero contradictions):

- **Live `~/.claude/settings.json` is a plain file, not a symlink.** `Get-Item` → `LinkType` empty, `Attributes: Archive` (not `ReparsePoint`); 1851 bytes, mtime 2026-06-11 23:24:22. Its `hooks` object contains exactly `lazy-route-inject.sh` (UserPromptSubmit :14-24, SessionStart matcher `compact` :25-36, PostCompact :37-47) + `lazy-dispatch-guard.sh` (PreToolUse `Agent|Task` :48-59). It also carries genuinely-per-machine content: a pwsh one-liner `statusLine` (:2-5) and `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=75` (:10-12).
- **Tracked `user/settings.json` (178 lines) registers 10 distinct hook scripts** (`lazy-cycle-containment.sh` twice — Bash :78 + Skill :98) across SessionStart (:25-51), PreToolUse Read/Bash/Skill/Write|Edit (:52-118); `PostToolUse: []` (:119). Neither `lazy-route-inject.sh` nor `lazy-dispatch-guard.sh` appears. It has NO `UserPromptSubmit` and NO `PostCompact` keys; its `statusLine` is `ccstatusline` (:121-125), no `env` block. `git log -S lazy-dispatch-guard -- user/settings.json` → zero commits.
- **`manifest.psd1:14`** (under `# File symlinks`, :11): `@{ Live = '~\.claude\settings.json'; Repo = 'user\settings.json'; Type = 'File' }`. **`:15`** maps `settings.local.json` the same way (relevant to D1's overlay option).
- **`doc-drift-lint.py::check_hooks` (:202)** reads ONLY `repo_root / "user" / "settings.json"` (:205) — the live file is out of scope. Sibling checks `check_scripts` (:313), `check_coupled_pairs` (:341), `check_manifest` (:451) dispatch from `run_checks` (:505-506); CLI `main` (:511) argparse takes only `--repo-root` (:512-517); exit 2 malformed / 1 drift / 0 clean. No `--live` flag exists today.
- **`setup.ps1`:** the mapping loop reports `REAL ... (not symlinked)` and increments `$broken` (:195-198); a warn-only pass (:215-259) checks ONLY `@('lazy-route-inject.sh','lazy-dispatch-guard.sh')` (:220) are present in the live file, never the other 10, and runs only on a manual `setup.ps1 check`. **`setup.py`** has `cmd_check` (:507) with identical symlink logic but NO hook-content/warn pass and no `--live` — a `--live` mode is net-new in both.
- **`test_hooks.py`** derives `settings_path = _REPO_ROOT / "user" / "settings.json"` ad hoc inside each of `test_straybranch_registered_in_settings` (:4677) and `test_longbuild_guard_registered_in_settings` (:4832) — no shared fixture. **`test_doc_drift_lint.py`** loads the module via a `ddl` fixture + a `run_lint(repo_root)` subprocess helper, hermetic `tmp_path` trees, and ends with `test_this_repo_is_clean()` (:604).

---

### Phase 1: Reconcile hook registration into the tracked SSOT

**Status:** Complete

**Scope:** Merge the turn-routing pair into tracked `user/settings.json` so it becomes the single source of truth carrying ALL 12 hooks — the core un-split. This is the load-bearing prerequisite for the symlink restore (Phase 3): restoring the symlink BEFORE this merge would strip `lazy-route-inject`/`lazy-dispatch-guard` off the live laptop. Because these two hooks become newly-registered, they must also be documented in the root `CLAUDE.md` Hooks table (else `doc-drift-lint.py check_hooks` flags registered-but-undocumented drift), and asserted present by `test_hooks.py` (mirroring the existing straybranch/longbuild registration tests). No behavior change on any machine: the lazy hooks are marker-gated per-repo (`lazy-state.py --marker-present`, fail-open, marker-absent fast path), so universal registration is safe (SPEC Fix Scope 1).

**Deliverables:**
- [x] `user/settings.json`: add `UserPromptSubmit` → `lazy-route-inject.sh` (timeout 90) and `PostCompact` → `lazy-route-inject.sh` (timeout 90) top-level keys; add `lazy-route-inject.sh` (timeout 90) into the SessionStart `compact` matcher path; add a `PreToolUse` matcher `Agent|Task` block → `lazy-dispatch-guard.sh` (timeout 30). Copy the exact command strings from the live file (`bash ~/.claude/hooks/<name>.sh`). Preserve all 10 existing hooks byte-for-byte.
- [x] Root `CLAUDE.md` `## Hooks` table: add one row each for `lazy-route-inject.sh` (SessionStart-compact / UserPromptSubmit / PostCompact — the turn-routing banner injector) and `lazy-dispatch-guard.sh` (PreToolUse Agent|Task — the marker-gated verbatim-dispatch guard), consistent with the existing per-repo-scoping note that already describes both.
- [x] `user/scripts/test_hooks.py`: add `test_routeinject_registered_in_settings` + `test_dispatchguard_registered_in_settings` asserting the tracked `user/settings.json` registers each (same ad-hoc `_REPO_ROOT / "user" / "settings.json"` resolution + event/matcher assertions as the existing two registration tests).
- [x] Tests: the two new `test_hooks.py` registration assertions; `doc-drift-lint.py --repo-root .` stays exit 0 (its `check_hooks` self-check + `test_doc_drift_lint.py::test_this_repo_is_clean` both green with the new CLAUDE.md rows).

**Minimum Verifiable Behavior:** `python3 -c "import json; h=json.load(open('user/settings.json'))['hooks']; assert any('lazy-dispatch-guard' in x['command'] for m in h['PreToolUse'] for x in m['hooks']); assert 'UserPromptSubmit' in h and 'PostCompact' in h"` exits 0, AND `python3 user/scripts/doc-drift-lint.py --repo-root .` prints clean / exit 0.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/settings.json` (exists) — merge turn-routing pair into the existing `hooks` object; reuse the exact live-file command strings.
- `CLAUDE.md` (root, exists) — two new rows in the `## Hooks` table.
- `user/scripts/test_hooks.py` (exists) — two new registration tests following the `test_straybranch_registered_in_settings` (:4677) pattern.

**Testing Strategy:** Run `python3 -m pytest user/scripts/test_hooks.py -k registered_in_settings` (4 tests: 2 existing + 2 new all green) and `python3 user/scripts/doc-drift-lint.py --repo-root .` (exit 0). A JSON-parse smoke asserts the merged object is well-formed and the guard/route-inject blocks resolve.

**Integration Notes for Next Phase:**
- After this phase the tracked SSOT is complete — Phase 3's symlink restore is now SAFE (restoring earlier would disarm the turn-routing pair on the laptop). This ordering is a HARD constraint.
- `doc-drift-lint check_hooks` compares BOTH directions — the two hooks are now registered, so their CLAUDE.md rows are mandatory, not optional; a missing row fails the lint.
- The reconciled `user/settings.json` is the single SSOT the two D4-sibling bugs (`legacy-tool-input-env-hooks-dead`, `powershell-tool-bypasses-bash-matched-guards`) will stack on.

**Implementation Notes (2026-07-12):**
- **Work completed:** Merged the turn-routing pair into tracked `user/settings.json` — added top-level `UserPromptSubmit` and `PostCompact` blocks (both `lazy-route-inject.sh` timeout 90), a second `SessionStart` `matcher: "compact"` block for `lazy-route-inject.sh`, and a `PreToolUse` `matcher: "Agent|Task"` block for `lazy-dispatch-guard.sh` (timeout 30). All 10 pre-existing hooks preserved byte-for-byte. Command strings copied verbatim from the live `~/.claude/settings.json`. Merged object now carries 16 hook commands across 5 events (UserPromptSubmit 1, SessionStart 4, PostCompact 1, PreToolUse 10, PostToolUse 0). Added two CLAUDE.md `## Hooks` rows and two `test_hooks.py` registration tests (`test_routeinject_registered_in_settings`, `test_dispatchguard_registered_in_settings`).
- **Files modified:** `user/settings.json`, `CLAUDE.md` (root), `user/scripts/test_hooks.py`.
- **Pitfall / harness gap surfaced (`check_hooks` is single-event-per-hook):** `doc-drift-lint.py::check_hooks` models each hook as registered under exactly ONE event (`set(reg_events) != {doc_event}` ⇒ drift). `lazy-route-inject.sh` is legitimately wired to THREE events (UserPromptSubmit + SessionStart-compact + PostCompact), which no single-event Trigger cell can represent. Resolved in-plan with the sanctioned `doc-drift:deliberate-divergence` marker on that row (honest reason inline); the row's prose still names all three events. A `/harden-harness` dispatch is queued to extend `check_hooks` to model multi-event hooks so the marker can later be retired.
- **Matcher-cell gotcha:** a literal `|` in a Markdown table cell splits the column and `\|` leaves a stray backslash the parser chokes on — so `lazy-dispatch-guard.sh`'s `Agent|Task` matcher is documented as `PreToolUse (Agent, Task)` (comma form; `_parse_matcher_list` splits on `[,|]`, matching the registered `{Agent, Task}` set cleanly, no divergence marker needed).
- **Gates:** `pytest test_hooks.py test_doc_drift_lint.py` → 195 passed; `doc-drift-lint.py --repo-root .` → exit 0 (0 drift findings, 2 exempted); `lint-skills.py` → exit 0.

---

### Phase 2: `--live` drift-detection mode in `doc-drift-lint.py`

**Status:** Complete

**Scope:** Add a `--live` check mode to `doc-drift-lint.py` (SPEC Fix Scope 4): PASS iff the live `~/.claude/settings.json` is a symlink AND resolves to the repo's `user/settings.json`; content-identical is the accepted fallback for copy-based hosts (cloud/non-symlink-capable). This is the detection primitive that makes the split self-announce instead of waiting for a manual `setup.ps1` run — and the reusable helper D2's surfacing (Phase 5) calls. Factor the check as a standalone helper (e.g. `check_live_settings(repo_root) -> list[finding]` plus a thin `live_settings_status(repo_root) -> (ok: bool, detail: str)` the banner/probe can import) so Phase 5 does not re-implement it.

**Deliverables:**
- [x] `doc-drift-lint.py`: `--live` argparse flag; `check_live_settings(repo_root)` returning structured findings (live path missing → finding; real-file-not-symlink → drift finding naming the corrective `setup repair`; symlink resolving elsewhere → drift; content-identical non-symlink → PASS with an advisory note; symlink→tracked → clean).
- [x] A small importable `live_settings_status(repo_root)` helper (bool + human detail) so Phase 5's banner/probe reuse the SAME logic (no re-derivation).
- [x] `--live` is opt-in: default `run_checks` (the repo-only cross-check) is unchanged and stays exit-0 on this repo; `--live` is NOT added to the default check set (it inspects machine-local state, so `test_this_repo_is_clean` must not depend on it).
- [x] Tests: `test_doc_drift_lint.py` — symlink-intact PASS, real-file FAIL (names `setup repair`), symlink-to-wrong-target FAIL, content-identical-copy PASS, missing-live-file finding. Follow the `tmp_path` + `ddl`-fixture convention; fabricate a fake HOME/live path via monkeypatch or an explicit `--live-path` test seam rather than touching the real `~`.

**Minimum Verifiable Behavior:** `python3 user/scripts/doc-drift-lint.py --live --repo-root .` runs and returns a structured verdict; on THIS laptop pre-Phase-3 it exits non-zero naming the real-file split (that non-zero is the correct, intended detection — it flips to PASS once Phase 3 restores the symlink).

**Prerequisites:** None strictly (independent of Phase 1's content), but sequence AFTER Phase 1 so the tracked SSOT the `--live` check compares against is already the complete one.

**Files likely modified:**
- `user/scripts/doc-drift-lint.py` (exists) — new `--live` flag + `check_live_settings` + `live_settings_status` helper, registered alongside `check_hooks`/`check_scripts`/etc. but gated behind `--live` (not in the default `run_checks` tuple).
- `user/scripts/test_doc_drift_lint.py` (exists) — new `test_live_*` block using a monkeypatched/parameterized live path so it never reads the real `~/.claude`.

**Testing Strategy:** `python3 -m pytest user/scripts/test_doc_drift_lint.py` fully green including the new live-mode cases and the unchanged `test_this_repo_is_clean` (proves `--live` did not leak into the default check set).

**Integration Notes for Next Phase:**
- Expose the check as an importable helper — Phase 3's setup-check extension and Phase 5's banner/probe both call it; do NOT let those re-implement the symlink-resolve logic.
- The content-identical fallback is deliberate: copy-based hosts (cloud bootstrap) can't symlink, so byte-equality must count as PASS or the cloud will always report drift.

**Implementation Notes (2026-07-12):**
- **Work completed (TDD, test-first):** Added `--live` mode to `doc-drift-lint.py` (94 lines): `_live_settings_path(repo_root)` (default `~/.claude/settings.json`, the test seam fallback), `check_live_settings(repo_root, live_path=None) -> list[Finding]` (`check="live"`), and the importable `live_settings_status(repo_root, live_path=None) -> (ok, detail)` helper Phase 5 will reuse. `main()` gained `--live` (store_true) + `--live-path` override; `--live` findings flow through the existing malformed/drift/exit-code accounting. Symlink target comparison via `os.path.realpath`; content comparison via `read_bytes()`.
- **Verdict logic:** symlink→tracked = clean; real-file-content-differs = drift (message names `setup.py repair` / `setup.ps1 repair`); symlink→wrong-target = drift; real-file-content-identical = clean PASS (copy-based/cloud-host case, NOT drift); live-file-missing = finding. Exit codes: 0 clean / 1 drift / 2 malformed (missing tracked SSOT).
- **Opt-in guarantee (HARD):** `check_live_settings` is deliberately NOT in the default `run_checks` tuple; `CHECK_NAMES` stays the 4-tuple. Two leak-guard tests pin it (`test_live_check_name_not_in_default_check_names`, `test_default_run_checks_never_emits_live_finding`), so the default `doc-drift-lint.py --repo-root .` (no `--live`) stays byte-identical + exit 0 and never touches `~/.claude`.
- **Files modified:** `user/scripts/doc-drift-lint.py`, `user/scripts/test_doc_drift_lint.py` (8 new `--live` tests; symlink cases guard `os.symlink` OSError with `pytest.skip` for Windows-without-Developer-Mode safety).
- **Live-machine confirmation (informational):** `doc-drift-lint.py --live --repo-root .` on this laptop exits 1, correctly flagging `~/.claude/settings.json` as a real file diverging from the tracked SSOT — exactly the split this bug fixes. That is the intended detection; the machine state is left as-is (Phase 3's symlink restore is the remedy, out of part-1 scope).
- **Gates:** `pytest test_doc_drift_lint.py` → 44 passed (8 new); `pytest test_hooks.py test_doc_drift_lint.py` → 203 passed; `doc-drift-lint.py --repo-root .` (default) → exit 0; `lint-skills.py` → exit 0.

---

### Phase 3: Restore the live symlink + fold per-machine content + extend the setup checks

**Status:** Complete

**Scope:** Un-break THIS laptop and harden the setup-time check (SPEC Fix Scope 2 + 5, D1). D1 is now **RESOLVED** (`NEEDS_INPUT.md`, 2026-07-12): the `settings.local.json` overlay is confirmed non-viable (project-scoped-only, no user-level merge); `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is already folded into the tracked SSOT (Phase 1). For `statusLine`, the tracked `ccstatusline` default is **kept as-is** — this machine installs/configures `ccstatusline` rather than folding the pwsh one-liner into the shared SSOT (avoids a cross-machine Windows/pwsh regression on any non-Windows/cloud session sharing this tracked file). Once `ccstatusline` is confirmed working here, restore the symlink via `setup.py repair` / `setup.ps1 repair` (real file → `.bak`, symlink created). Then extend `setup.ps1`'s warn pass (:215-259) to verify the FULL tracked hook set is live, ideally by delegating to `doc-drift-lint.py --live` rather than re-listing hook names (the current two-hook check passes on exactly this failure). **The `setup.py` parallel-check deliverable (WU-8) is DROPPED** (decision 2, `NEEDS_INPUT.md` resolution, 2026-07-12): it would silently override `cross-platform-setup` Locked Decision D6 (`setup.py check`'s ported surface is symlink-state only — "a deliberate, permanent divergence"); `doc-drift-lint.py --live` (Phase 2) already satisfies the cross-platform parity need without touching `setup.py`.

**Deliverables:**
- [x] D1 resolved (`NEEDS_INPUT.md`, 2026-07-12): `settings.local.json` overlay confirmed non-viable (project-scoped only, no user-level merge); `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` already folded into tracked SSOT (Phase 1). `statusLine` choice: KEEP the tracked `ccstatusline` default as-is — do NOT fold the pwsh one-liner into the shared SSOT (cross-machine Windows/pwsh regression risk). This machine must install/configure `ccstatusline` before/with the symlink restore so the restore does not degrade the status line.
- [x] `ccstatusline` installed and confirmed working on this machine (accepted replacement display) — `npm install -g ccstatusline` (2.2.23), on PATH, produces live output (`Model: ... | ⎇ main | (+0,-0)`; the fresh-install default config also includes a `context-length` widget — model/branch/context parity with the prior pwsh one-liner via the package's own sensible defaults, no interactive TUI session needed).
- [x] Live `~/.claude/settings.json` symlink restored to `user/settings.json` (via `.\setup.ps1 repair -Target User`); prior real file preserved as `.bak` at `~/.claude/settings.json.bak`; restore proceeds with the tracked `ccstatusline` default intact (no per-machine `statusLine` content to fold). `.\setup.ps1 check -Target User` now reports `OK User | settings.json`, `LinkType: SymbolicLink`, target resolves to tracked `user/settings.json`.
- [x] `setup.ps1` warn pass (:215-259) now verifies the FULL tracked hook set is live by shelling `python3 user/scripts/doc-drift-lint.py --live --repo-root <RepoRoot>` and reporting its verdict (OK/WARN + drift lines), replacing the hardcoded 2-hook `$hookScripts` list — single SSOT for hook names. REGISTRATION.md citation updated to note registration now ships tracked and that part 3 (Phase 4) finalizes the doc's retirement.
- [ ] ~~`setup.py` gains the parallel live hook/symlink check~~ **DROPPED** (decision 2, `NEEDS_INPUT.md` resolution, 2026-07-12): would silently override `cross-platform-setup` Locked Decision D6 (`setup.py check`'s ported surface is symlink-state only, "a deliberate, permanent divergence"). `doc-drift-lint.py --live` (Phase 2) already provides equivalent cross-platform live-drift parity without touching `setup.py`. Scope note only — no code deliverable here.
- [x] Tests: the warn-pass extension is thin glue (delegates ALL hook-set logic to `doc-drift-lint.py`, already unit-tested by `test_doc_drift_lint.py`, 48 passing); no new pure logic was introduced to unit-test separately. Verified instead by a smoke pass: `.\setup.ps1 check -Target User` exit-0 success path (`OK live settings.json reflects the tracked SSOT`) plus a direct `doc-drift-lint.py --live --live-path <divergent-file>` invocation confirming the exit-1/WARN path the ps1 branch forwards.

**Minimum Verifiable Behavior:** after restore, `python3 user/scripts/doc-drift-lint.py --live --repo-root .` exits 0 (symlink resolves to tracked SSOT), AND `Get-Item ~/.claude/settings.json` shows `LinkType: SymbolicLink`, AND a fresh read of the resolved file shows all 12 hooks registered.

**Prerequisites:**
- Phase 1: the tracked SSOT MUST already carry all 12 hooks — restoring the symlink before Phase 1 would disarm the laptop's turn-routing pair.
- Phase 2: `--live` is the verification vehicle and the setup-check delegation target.

**Files likely modified:**
- `~/.claude/settings.json` (live, machine op) — symlink restored; `.bak` retained.
- `setup.ps1` (exists) — extend the :215-259 warn pass to the full hook set / delegate to `--live`.
- ~~`user/settings.json` and/or `user/settings.local.json` — folded per-machine content~~ **no longer applicable**: D1 resolved with NO fold (tracked `ccstatusline` default kept as-is; `env` override already landed Phase 1).
- ~~`setup.py` (exists) — add the parallel live check.~~ **dropped** (decision 2 — respects `cross-platform-setup` D6; see deliverables above).

**Testing Strategy:** Run `setup.py check` / `setup.ps1 check` → reports the settings mapping OK (no `REAL`); `doc-drift-lint.py --live` exit 0; confirm `ccstatusline` renders correctly (branch/model/context%) in a live session after install + restore. Unit-test the `setup.ps1` warn-pass extension's hook-set comparison where it is pure (no `setup.py` unit-test deliverable — WU-8 dropped).

**Integration Notes for Next Phase:**
- Once restored, this laptop reads the reconciled SSOT — the D4-sibling bugs can safely edit `user/settings.json` and see it live without re-splitting.
- Keep the `.bak` until a session confirms statusLine + autocompact override behave; the fold is the only reversible-sensitive step.

**Implementation Notes (2026-07-12, `/execute-plan` part-2 cycle — partial, halted on NEEDS_INPUT):**
- Landed: `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE: "75"` folded into tracked `user/settings.json` (unambiguous per the plan's WU-6 design-fork note — env folding "never halts").
- **Halted before the rest of WU-6.** Dispatched a `claude-code-guide` research agent for D1's open sub-question (settings.json↔settings.local.json merge precedence for `statusLine`): confirmed `settings.local.json` is a **project-scoped-only** Claude Code concept — no user-level (`~/.claude/settings.local.json`) merge exists per official docs, so the overlay option the plan flagged is not viable. Separately confirmed `ccstatusline` (the tracked default) is **not installed** on this machine (`npx ccstatusline --version` fails — no cached package), so restoring the symlink as-is would silently break this machine's currently-working pwsh statusLine. Wrote `NEEDS_INPUT.md` per the plan's explicit instruction ("do NOT guess the overlay behavior") — did NOT restore the live symlink this cycle.
- **New finding surfaced in the same halt:** `--provenance-lookup setup.py` before touching it for WU-8 surfaced `docs/features/cross-platform-setup/SPEC.md` Decision **D6** — a previously-Locked Decision stating `setup.py check`'s ported surface is symlink-state only, "a deliberate, permanent divergence" from `setup.ps1`'s warn-only advisories (which include hook-registration checking — exactly what WU-8 asks `setup.py` to gain). Neither this bug's SPEC.md nor PHASES.md/plan shows awareness of D6. Folded into the same `NEEDS_INPUT.md` as decision 2 rather than silently overriding a cross-feature Locked Decision.
- Batch 2 (WU-7 `setup.ps1` warn-pass extension, WU-8 `setup.py` parallel check) was **not started** — both are `Blocked by: WU-6` in the plan's Execution Schedule, and WU-6 did not complete this cycle.
- Plan-part frontmatter flipped `Ready` → `In-progress` (see `plans/fix-settings-split-brain-part-2.md`). Resume: once `NEEDS_INPUT.md` is resolved, re-run `/execute-plan` against the same plan part.

**Implementation Notes (2026-07-12, `/execute-plan` part-2 cycle — resume after NEEDS_INPUT resolution, completes Phase 3):**
- Resolution confirmed (`NEEDS_INPUT_RESOLVED_2026-07-12.md`): install `ccstatusline` + keep tracked default (decision 1); drop WU-8, rely on `doc-drift-lint.py --live` (decision 2).
- `npm install -g ccstatusline` (2.2.23) landed globally; `ccstatusline --version` confirms it's on PATH. A fresh-install run (piped a synthetic Claude Code stdin payload) auto-wrote `~/.config/ccstatusline/settings.json` with sensible defaults (model, context-length, git-branch, git-changes widgets) and produced live output — no interactive TUI session was needed to reach parity with the prior pwsh display's intent (branch/model/context).
- Restored the live symlink via `.\setup.ps1 repair -Target User` (scoped — NOT the unscoped `-Target All`, see caution below). `~/.claude/settings.json` is now `LinkType: SymbolicLink` → tracked `user/settings.json`; the prior real file is preserved at `~/.claude/settings.json.bak`.
- **Caution / self-correction:** an initial `-Target All` repair run (before I re-scoped to `-Target User`) discovered a **pre-existing stale-username defect**: `manifest.psd1`'s `cognito-forms*`/`cognito-docs` `Repo` mappings hardcode `C:\Users\JacobMadsen\source\repos\...` (a different/legacy username than this machine's real `Jacob`), and those repos are genuinely absent here. `setup.ps1 repair -Target All` does not skip absent-repo targets — it happily created an entire stray `C:\Users\JacobMadsen\...\Cognito Forms\...` directory tree (settings.json, skills, hooks, etc., pulled in via the tracked repo files) trying to satisfy those mappings. I detected this immediately (fresh `CreationTime` on the stray root) and removed the whole tree (`Remove-Item -Recurse -Force`) before it could be mistaken for real content; `git status --short` in this repo stayed clean throughout (the stray tree was outside this repo, at the OS filesystem level). No harm to this repo's tracked files. Re-ran scoped to `-Target User` only, which correctly touched just the 11 User-scope mappings (all `OK` after, incl. `settings.json`).
- Extended `setup.ps1`'s warn pass (:215-259) per WU-7: replaced the hardcoded `$hookScripts = @('lazy-route-inject.sh', 'lazy-dispatch-guard.sh')` two-hook list with a shell-out to `python3 user/scripts/doc-drift-lint.py --live --repo-root <RepoRoot>`, reporting OK/WARN off its exit code + forwarding its output lines on drift. Falls back to `python` if `python3` is absent from PATH, and to a `WARN ... skipped` line if neither exists. Updated the REGISTRATION.md citation to reflect tracked registration + point at part 3 (Phase 4) for the doc's full retirement.
- WU-8 (`setup.py` parallel check) confirmed DROPPED per the resolution — no code change; PHASES.md deliverable already carries the disposition from the prior halt.
- Quality Gates run and green: `.\setup.ps1 check -Target User` → `11 OK, 0 broken, 0 absent` + `OK live settings.json reflects the tracked SSOT`; `python3 user/scripts/doc-drift-lint.py --live --repo-root .` → exit 0; `python3 user/scripts/doc-drift-lint.py --repo-root .` (default, no `--live`) → exit 0; `python3 -m pytest user/scripts/test_doc_drift_lint.py -q` → 48 passed. No Pester test exists for `setup.ps1` (only `test_setup_py.py` covers the Python port) — substituted the plan's specified dry `setup.ps1 check` smoke.
- **Separate finding routed to harden-harness (not fixed in this cycle — out of this bug's scope):** `python3 setup.py check` (git-bash/native-Windows-Python) misreports EVERY correctly-symlinked User-scope entry as `WRONG` (13 broken, 0 OK on this machine, vs. `setup.ps1 check`'s correct `11 OK, 0 broken`). Root cause traced to `setup.py::_resolve_target` mishandling the `\\?\` extended-length-path prefix Windows' `os.readlink()` returns for symlinks — `os.path.abspath` on a `\\?\`-prefixed string mangles it into `C:\?\C:\...` instead of stripping the prefix, so `_targets_equal` never matches even a byte-identical target. Confirmed pre-existing (reproduces on the already-good `user/skills` symlink, untouched by this cycle) and unrelated to WU-6/7/8. `settings.json` itself correctly shows `WRONG` (not `REAL`) post-restore, so this bug's own MVB is unaffected — but the defect undermines `setup.py check`'s reliability on native Windows generally. Per the harden-harness auto-invoke policy, spinning this off via the marker-gated `--emit-dispatch hardening` path (a `/lazy-bug-batch` run marker is live for this repo) rather than hand-composing an `Agent` dispatch.

---

### Phase 4: Retire the per-machine registration design + annotate the blind window

**Scope:** Documentation reconciliation (SPEC Fix Scope 3 + 6, D3). Rewrite/retire `REGISTRATION.md`'s paste-this-fragment per-machine design now that registration ships in the tracked SSOT (keep its 2026-06-11 pipe-test run records as historical evidence). Amend `docs/specs/turn-routing-enforcement/SPEC.md` §"Settings placement" (:114) to state registration is now tracked, not per-machine. Add a machine-scoped blind-window annotation (Jun 11 → fix date) wherever hook-derived signals are consumed (`incident-scan.py` / efficacy / retro grading), so that window reads as partially-blind, not zero-friction (D3: annotate only — backfill is impossible, silent-ignore re-poisons baselines).

**Deliverables:**
- [ ] `docs/specs/turn-routing-enforcement/REGISTRATION.md`: converted to a historical/retired doc (per-machine paste instruction removed or marked superseded; pipe-test records preserved) with a pointer to the tracked-SSOT registration.
- [ ] `docs/specs/turn-routing-enforcement/SPEC.md` §"Settings placement" (:114): amended to reflect tracked-file registration; the deferred-unification note updated/closed.
- [ ] Blind-window annotation recorded where hook-event consumers read it (a machine-scoped `blind_window` note for the Jun 11 → fix-date range near incident-scan/efficacy's hook-event consumption), so consumers treat the window as partially-blind.
- [ ] Any doc that references `REGISTRATION.md` as a live instruction (e.g. `setup.ps1` warn message :253 citing it — now that Phase 3 rewrote the pass) updated to stop pointing at a retired design.

**Minimum Verifiable Behavior:** `grep -rn "paste this fragment\|each machine's live settings" docs/specs/turn-routing-enforcement/` returns no live-instruction hits (only historical/superseded framing); the SPEC §Settings-placement text no longer claims per-machine registration is required.

**Prerequisites:**
- Phase 1 (registration now genuinely in the tracked file — the doc claims must be TRUE when written).
- Phase 3 (setup.ps1 warn message rewritten, so its REGISTRATION.md citation is updated in step).

**Files likely modified:**
- `docs/specs/turn-routing-enforcement/REGISTRATION.md`, `docs/specs/turn-routing-enforcement/SPEC.md` (exist) — edits.
- The hook-event-consumer surface for the blind-window note (near `incident-scan.py` / efficacy read paths; a small documented annotation, not a code path change).

**Testing Strategy:** Doc-review + grep assertions; `doc-drift-lint.py --repo-root .` stays exit 0 (no new script/hook rows implied). Confirm no remaining live pointer to the retired paste-fragment design.

**Integration Notes for Next Phase:**
- The blind-window is annotate-only by design — do NOT attempt to synthesize the missing events.
- With the design retired, D4-siblings inherit a single documented registration story.

---

### Phase 5: Surface the `--live` check through a runtime vehicle (D2)

**Scope:** Make drift self-announce at runtime (SPEC Fix Scope 4 "surface it through an existing periodic surface", D2). Wire the Phase-2 `live_settings_status` helper into: (a) the `lazy-route-inject` banner (fires every prompt-submit in marked runs — a cheap symlink+resolve stat) as one advisory line when drift is detected, and (b) a `lazy-state --probe` field. Both call the SAME helper (no re-derivation). A SessionStart hook is deliberately NOT used (it would live in the very file being checked → bootstrap circularity); the banner + probe are the reinforcement surfaces.

**Deliverables:**
- [ ] `lazy-route-inject.sh` (or its Python helper): when `live_settings_status` reports drift, emit one advisory banner line naming the split + corrective (`setup repair`); silent/no-op when clean or when the helper is unavailable (fail-open, must never break the banner).
- [ ] `lazy-state.py --probe`: a `live_settings_ok` (or equivalent) field sourced from the same helper; absent-helper / non-workstation → benign default (never a hard error).
- [ ] Both call the single `doc-drift-lint.py` helper from Phase 2 — no duplicated symlink-resolve logic.
- [ ] Tests: helper-integration unit coverage for the probe field (drift → field false + detail; clean → true); banner path exercised where testable (fail-open on helper error asserted).

**Minimum Verifiable Behavior:** with the symlink intentionally broken in a scratch HOME, `lazy-state.py --probe` reports the `live_settings_ok=false` field and the banner emits its advisory line; with the symlink intact, the field is true and the banner stays silent. Helper-missing → both degrade to benign (no crash).

**Prerequisites:** Phase 2 (`live_settings_status` helper must exist and be importable).

**Files likely modified:**
- `user/hooks/lazy-route-inject.sh` (exists) — one advisory line on drift; fail-open.
- `user/scripts/lazy-state.py` (exists) — a probe field from the helper.
- The relevant `test_*` for the probe field.

**Testing Strategy:** Unit-test the probe field both ways against a fabricated live path; assert the banner is fail-open (helper raising → banner still emits its normal routing content, no drift line, no crash). `doc-drift-lint.py --repo-root .` stays exit 0.

**Integration Notes for Next Phase:** None (terminal phase). The banner/probe are reinforcement; the load-bearing detection is Phase 2's `--live` and Phase 3's setup-check delegation.

---

## Notes

- **MCP runtime not-required** is a routing hint only — there is no MCP surface in claude-config; every phase is verified by pytest, `doc-drift-lint.py`, JSON/grep smoke checks, and (Phase 3) a live symlink stat.
- **Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` and writes `FIXED.md` once the symptom-reproduction gate is satisfied — the ORIGINAL symptom (guards unregistered on the live machine / dispatch guard unwired on symlink-intact machines) is gone at its reported surface: the live `~/.claude/settings.json` resolves to the reconciled SSOT carrying all 12 hooks, and `doc-drift-lint.py --live` returns clean. That is the serving-path regression evidence, not a unit-green-on-internal-target claim. Do NOT author a checkbox row for the status flip or the receipt write.
- **Hard ordering:** Phase 1 → Phase 3 is a strict prerequisite (restoring the symlink before the SSOT carries the turn-routing pair would disarm the laptop). Phase 2 precedes Phase 3 (verification vehicle) and Phase 5 (helper source). Phase 4 follows Phase 1 (doc claims must be true) and Phase 3 (setup message rewrite).
- **One NEEDS_INPUT-eligible fork:** D1's settings.local.json `statusLine` merge-precedence question (Phase 3) — **resolved** via `NEEDS_INPUT.md` (2026-07-12): overlay non-viable, tracked `ccstatusline` default kept, install `ccstatusline` on this machine. A second question (setup.py WU-8 vs. `cross-platform-setup` D6) surfaced in the same halt and was resolved the same cycle: WU-8 dropped.
