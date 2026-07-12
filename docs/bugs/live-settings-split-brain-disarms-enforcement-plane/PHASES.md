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

**Scope:** Merge the turn-routing pair into tracked `user/settings.json` so it becomes the single source of truth carrying ALL 12 hooks — the core un-split. This is the load-bearing prerequisite for the symlink restore (Phase 3): restoring the symlink BEFORE this merge would strip `lazy-route-inject`/`lazy-dispatch-guard` off the live laptop. Because these two hooks become newly-registered, they must also be documented in the root `CLAUDE.md` Hooks table (else `doc-drift-lint.py check_hooks` flags registered-but-undocumented drift), and asserted present by `test_hooks.py` (mirroring the existing straybranch/longbuild registration tests). No behavior change on any machine: the lazy hooks are marker-gated per-repo (`lazy-state.py --marker-present`, fail-open, marker-absent fast path), so universal registration is safe (SPEC Fix Scope 1).

**Deliverables:**
- [ ] `user/settings.json`: add `UserPromptSubmit` → `lazy-route-inject.sh` (timeout 90) and `PostCompact` → `lazy-route-inject.sh` (timeout 90) top-level keys; add `lazy-route-inject.sh` (timeout 90) into the SessionStart `compact` matcher path; add a `PreToolUse` matcher `Agent|Task` block → `lazy-dispatch-guard.sh` (timeout 30). Copy the exact command strings from the live file (`bash ~/.claude/hooks/<name>.sh`). Preserve all 10 existing hooks byte-for-byte.
- [ ] Root `CLAUDE.md` `## Hooks` table: add one row each for `lazy-route-inject.sh` (SessionStart-compact / UserPromptSubmit / PostCompact — the turn-routing banner injector) and `lazy-dispatch-guard.sh` (PreToolUse Agent|Task — the marker-gated verbatim-dispatch guard), consistent with the existing per-repo-scoping note that already describes both.
- [ ] `user/scripts/test_hooks.py`: add `test_routeinject_registered_in_settings` + `test_dispatchguard_registered_in_settings` asserting the tracked `user/settings.json` registers each (same ad-hoc `_REPO_ROOT / "user" / "settings.json"` resolution + event/matcher assertions as the existing two registration tests).
- [ ] Tests: the two new `test_hooks.py` registration assertions; `doc-drift-lint.py --repo-root .` stays exit 0 (its `check_hooks` self-check + `test_doc_drift_lint.py::test_this_repo_is_clean` both green with the new CLAUDE.md rows).

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

---

### Phase 2: `--live` drift-detection mode in `doc-drift-lint.py`

**Scope:** Add a `--live` check mode to `doc-drift-lint.py` (SPEC Fix Scope 4): PASS iff the live `~/.claude/settings.json` is a symlink AND resolves to the repo's `user/settings.json`; content-identical is the accepted fallback for copy-based hosts (cloud/non-symlink-capable). This is the detection primitive that makes the split self-announce instead of waiting for a manual `setup.ps1` run — and the reusable helper D2's surfacing (Phase 5) calls. Factor the check as a standalone helper (e.g. `check_live_settings(repo_root) -> list[finding]` plus a thin `live_settings_status(repo_root) -> (ok: bool, detail: str)` the banner/probe can import) so Phase 5 does not re-implement it.

**Deliverables:**
- [ ] `doc-drift-lint.py`: `--live` argparse flag; `check_live_settings(repo_root)` returning structured findings (live path missing → finding; real-file-not-symlink → drift finding naming the corrective `setup repair`; symlink resolving elsewhere → drift; content-identical non-symlink → PASS with an advisory note; symlink→tracked → clean).
- [ ] A small importable `live_settings_status(repo_root)` helper (bool + human detail) so Phase 5's banner/probe reuse the SAME logic (no re-derivation).
- [ ] `--live` is opt-in: default `run_checks` (the repo-only cross-check) is unchanged and stays exit-0 on this repo; `--live` is NOT added to the default check set (it inspects machine-local state, so `test_this_repo_is_clean` must not depend on it).
- [ ] Tests: `test_doc_drift_lint.py` — symlink-intact PASS, real-file FAIL (names `setup repair`), symlink-to-wrong-target FAIL, content-identical-copy PASS, missing-live-file finding. Follow the `tmp_path` + `ddl`-fixture convention; fabricate a fake HOME/live path via monkeypatch or an explicit `--live-path` test seam rather than touching the real `~`.

**Minimum Verifiable Behavior:** `python3 user/scripts/doc-drift-lint.py --live --repo-root .` runs and returns a structured verdict; on THIS laptop pre-Phase-3 it exits non-zero naming the real-file split (that non-zero is the correct, intended detection — it flips to PASS once Phase 3 restores the symlink).

**Prerequisites:** None strictly (independent of Phase 1's content), but sequence AFTER Phase 1 so the tracked SSOT the `--live` check compares against is already the complete one.

**Files likely modified:**
- `user/scripts/doc-drift-lint.py` (exists) — new `--live` flag + `check_live_settings` + `live_settings_status` helper, registered alongside `check_hooks`/`check_scripts`/etc. but gated behind `--live` (not in the default `run_checks` tuple).
- `user/scripts/test_doc_drift_lint.py` (exists) — new `test_live_*` block using a monkeypatched/parameterized live path so it never reads the real `~/.claude`.

**Testing Strategy:** `python3 -m pytest user/scripts/test_doc_drift_lint.py` fully green including the new live-mode cases and the unchanged `test_this_repo_is_clean` (proves `--live` did not leak into the default check set).

**Integration Notes for Next Phase:**
- Expose the check as an importable helper — Phase 3's setup-check extension and Phase 5's banner/probe both call it; do NOT let those re-implement the symlink-resolve logic.
- The content-identical fallback is deliberate: copy-based hosts (cloud bootstrap) can't symlink, so byte-equality must count as PASS or the cloud will always report drift.

---

### Phase 3: Restore the live symlink + fold per-machine content + extend the setup checks

**Scope:** Un-break THIS laptop and harden the setup-time check (SPEC Fix Scope 2 + 5, D1). First reconcile the live file's genuinely-per-machine content (D1): the pwsh `statusLine` and `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`. Fold acceptable values into the tracked SSOT where it already tolerates machine-specific content, or move the truly-divergent pwsh statusLine into the manifest-mapped `settings.local.json` overlay — after confirming Claude Code's settings.json↔settings.local.json merge precedence for `statusLine` (D1 open sub-question; a validation step, surfaced not blocking). Then restore the symlink via `setup.py repair` / `setup.ps1 repair` (real file → `.bak`, symlink created). Finally extend `setup.ps1`'s warn pass (:215-259) — and add the parallel check to `setup.py` — to verify the FULL tracked hook set is live, ideally by delegating to `doc-drift-lint.py --live` rather than re-listing hook names (the current two-hook check passes on exactly this failure).

**Deliverables:**
- [ ] D1 resolution recorded: decide per-machine home for the pwsh `statusLine` + `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` (fold into tracked SSOT vs `settings.local.json` overlay), with the settings.local.json `statusLine` merge-precedence question resolved and the answer noted inline. If precedence is genuinely ambiguous and blocks a safe choice, that is the one NEEDS_INPUT-eligible fork in this plan.
- [ ] Live `~/.claude/settings.json` symlink restored to `user/settings.json` (via `setup.py repair` or `setup.ps1 repair`); prior real file preserved as `.bak`; any folded per-machine content landed in its chosen home first so the restore loses nothing.
- [ ] `setup.ps1` warn pass (:215-259) verifies the FULL tracked hook set is live (or delegates to `doc-drift-lint.py --live`), not just the two turn-routing hooks.
- [ ] `setup.py` gains the parallel live hook/symlink check (currently absent — `cmd_check` only compares symlink resolution).
- [ ] Tests: any pure-logic portion of the extended check (hook-set diff / delegation wiring) covered where unit-testable; the live restore itself is a machine operation verified by MVB below.

**Minimum Verifiable Behavior:** after restore, `python3 user/scripts/doc-drift-lint.py --live --repo-root .` exits 0 (symlink resolves to tracked SSOT), AND `Get-Item ~/.claude/settings.json` shows `LinkType: SymbolicLink`, AND a fresh read of the resolved file shows all 12 hooks registered.

**Prerequisites:**
- Phase 1: the tracked SSOT MUST already carry all 12 hooks — restoring the symlink before Phase 1 would disarm the laptop's turn-routing pair.
- Phase 2: `--live` is the verification vehicle and the setup-check delegation target.

**Files likely modified:**
- `~/.claude/settings.json` (live, machine op) — symlink restored; `.bak` retained.
- `user/settings.json` and/or `user/settings.local.json` (exists / manifest-mapped :15) — folded per-machine content per D1.
- `setup.ps1` (exists) — extend the :215-259 warn pass to the full hook set / delegate to `--live`.
- `setup.py` (exists) — add the parallel live check.

**Testing Strategy:** Run `setup.py check` (or `setup.ps1 check`) → reports the settings mapping OK (no `REAL`); `doc-drift-lint.py --live` exit 0; confirm statusLine/env still render correctly in a live session after the fold. Unit-test the extended check's hook-set comparison where it is pure.

**Integration Notes for Next Phase:**
- Once restored, this laptop reads the reconciled SSOT — the D4-sibling bugs can safely edit `user/settings.json` and see it live without re-splitting.
- Keep the `.bak` until a session confirms statusLine + autocompact override behave; the fold is the only reversible-sensitive step.

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
- **One NEEDS_INPUT-eligible fork:** D1's settings.local.json `statusLine` merge-precedence question (Phase 3). If unresolvable from docs/observation, surface it — every other decision in the SPEC is already resolved.
