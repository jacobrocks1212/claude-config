# Bug: live-settings probe false-reports "missing settings" in a consumer repo

**Status:** Fixed
**Fixed:** 2026-07-18
**Fix commit:** 2be204cb
**Reported via:** `/harden-harness` observed-friction dispatch (2026-07-17, item in flight `hydra-overlay`, AlgoBooth `/lazy-batch`, blocking=true)
**Root-cause class:** `script-defect` (cross-repo SSOT resolution)
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage); `user/scripts/doc-drift-lint.py` (`check_live_settings` / `live_settings_status`); `user/scripts/lazy-state.py` (`live_settings_probe`, `--probe`); `user/scripts/lazy_inject.py` (`_live_settings_banner`); bug `live-settings-split-brain-disarms-enforcement-plane` (the probe this facet mis-scopes).

## Symptom (verified)

`lazy-state.py --probe` emits `live_settings_ok=false` with detail
`tracked user/settings.json is missing/unreadable at <repo>/user/settings.json` on EVERY probe
whenever `/lazy-batch` runs in a CONSUMER repo (AlgoBooth). The live `~/.claude/settings.json`
symlink is in fact correct (it points at the claude-config checkout's `user/settings.json`), so
the alarming "missing settings" report is a pure false positive — noise on every cycle of every
consumer-repo run.

## Root cause

**`script-defect` — the tracked settings SSOT is resolved against the wrong repo.**
`doc-drift-lint.check_live_settings(repo_root, …)` computes `tracked = repo_root / "user" /
"settings.json"`. The probe entry point `live_settings_probe(repo_root)` in `lazy-state.py`
(and the `_live_settings_banner` in `lazy_inject.py`) pass the RUN's `repo_root` — AlgoBooth.
But the tracked settings SSOT exists ONLY in the claude-config checkout
(`~/source/repos/claude-config/user/settings.json`), which is exactly where the live
`~/.claude/settings.json` symlink correctly points. AlgoBooth has no `user/` dir, so
`tracked.read_bytes()` raises `OSError` → the "missing/unreadable" finding → `live_settings_ok=false`.

The live path is machine-global and repo-independent (`_live_settings_path` ignores `repo_root`
and always returns `~/.claude/settings.json`), but the TRACKED side was left repo-scoped — a
two-scope mismatch. The correct behavior mirrors the two-scope resolution the
efficacy/canary/intervention-coverage flush already uses: harness artifacts (the settings SSOT,
the hardening log, intervention records) resolve to the claude-config checkout, not to the run's
target repo.

## Fix scope

Add `settings_ssot_root(repo_root)` (backed by `_config_checkout_root()` = `Path(__file__).resolve().parents[2]`,
the claude-config root resolved through the `~/.claude/scripts` symlink) to `doc-drift-lint.py`:
when `repo_root` already carries `user/settings.json` (claude-config itself, or a hermetic test
fixture) it is returned unchanged; a consumer repo (no `user/settings.json`) falls back to the
claude-config checkout. Wire it into both probe callers — `live_settings_probe` (lazy-state.py)
and `_live_settings_banner` (lazy_inject.py). `check_live_settings` / `live_settings_status` stay
PURE functions of their `repo_root` argument (the `--live` CLI and the hermetic
`test_doc_drift_lint.py` fixtures depend on that). Both callers remain fail-open. Add probe tests
(a consumer repo resolves the SSOT to claude-config → `ok=True`; a repo carrying the SSOT is used
unchanged). `_config_checkout_root` is factored as a monkeypatchable seam so the tests stay
hermetic.
