"""RED-phase tests for the live-settings-split-brain enforcement wiring
(bug: live-settings-split-brain-disarms-enforcement-plane, Phase 5).

Pins two NEW helper functions that Phase 5 impl agents will add:

- ``live_settings_probe(repo_root, live_path=None)`` in ``lazy-state.py``
  (hyphenated module, loaded via importlib) — wraps
  ``doc-drift-lint.py``'s ``live_settings_status`` for the probe JSON.
- ``_live_settings_advisory(repo_root, live_path=None)`` in ``lazy_inject.py``
  — produces a one-line advisory string surfaced at cycle-dispatch time.

Both must fail open (never raise; benign default) if doc-drift-lint cannot
be loaded, via a monkeypatchable ``_load_doc_drift_module`` attribute on
each host module.

These tests are expected to FAIL until the Phase 5 implementation lands
(the helpers do not exist yet).
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent


def _load(mod_name, filename):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(mod_name, str(SCRIPTS / filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _lazy_state():
    return _load("_lazy_state_probe_test", "lazy-state.py")


def _lazy_inject():
    return _load("_lazy_inject_probe_test", "lazy_inject.py")


@pytest.fixture()
def lazy_state_mod():
    return _lazy_state()


@pytest.fixture()
def lazy_inject_mod():
    return _lazy_inject()


# ---------------------------------------------------------------------------
# Fixture builder: a minimal repo with a tracked settings.json + fabricated
# live paths (clean / drift), mirroring test_doc_drift_lint.py's make_repo.
# ---------------------------------------------------------------------------


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "user").mkdir(parents=True)
    (repo / "user" / "settings.json").write_text(
        json.dumps({"hooks": {}}), encoding="utf-8"
    )
    return repo


def _clean_live_path(repo, tmp_path):
    """A live settings path that live_settings_status treats as CLEAN:
    prefer a real symlink to the tracked file; on a host where symlink
    creation is unavailable/unprivileged, degrade to a byte-identical
    real-file copy (also treated as clean)."""
    tracked = repo / "user" / "settings.json"
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    live_path = live_dir / "settings.json"
    try:
        os.symlink(tracked, live_path)
    except (OSError, NotImplementedError):
        live_path.write_bytes(tracked.read_bytes())
    return live_path


def _drift_live_path(tmp_path):
    """A live settings path with content that differs from the tracked
    SSOT — a real file, not a symlink, so drift is unambiguous."""
    live_dir2 = tmp_path / "live2"
    live_dir2.mkdir()
    live_path = live_dir2 / "settings.json"
    live_path.write_text(json.dumps({"hooks": {"x": 1}}), encoding="utf-8")
    return live_path


# ---------------------------------------------------------------------------
# live_settings_probe (lazy-state.py)
# ---------------------------------------------------------------------------


def test_probe_clean_reports_ok_true(lazy_state_mod, tmp_path):
    repo = _make_repo(tmp_path)
    live_path = _clean_live_path(repo, tmp_path)

    ok, detail = lazy_state_mod.live_settings_probe(repo, live_path=live_path)

    assert ok is True
    assert isinstance(detail, str)


def test_probe_drift_realfile_reports_false(lazy_state_mod, tmp_path):
    repo = _make_repo(tmp_path)
    live_path = _drift_live_path(tmp_path)

    ok, detail = lazy_state_mod.live_settings_probe(repo, live_path=live_path)

    assert ok is False
    assert isinstance(detail, str)
    assert detail != ""


def test_probe_failopen_benign_default_on_loader_error(lazy_state_mod, tmp_path):
    repo = _make_repo(tmp_path)
    live_path = _drift_live_path(tmp_path)

    def _raise():
        raise RuntimeError("boom")

    lazy_state_mod._load_doc_drift_module = _raise

    ok, detail = lazy_state_mod.live_settings_probe(repo, live_path=live_path)

    assert ok is True
    assert isinstance(detail, str)


# ---------------------------------------------------------------------------
# live-settings-probe-false-positive-in-consumer-repo (Gap 2): the tracked
# settings SSOT lives ONLY in the claude-config checkout; a run TARGETING a
# consumer repo (AlgoBooth: no user/settings.json) must resolve the SSOT to
# claude-config, not the run's repo_root, or every probe false-reports
# 'missing settings'.
# ---------------------------------------------------------------------------


def test_settings_ssot_root_falls_back_for_consumer_repo(lazy_state_mod, tmp_path):
    """A consumer repo (no user/settings.json) resolves to the claude-config
    checkout; a repo that HAS user/settings.json is used unchanged."""
    ddl = lazy_state_mod._load_doc_drift_module()
    cc = tmp_path / "cc"
    (cc / "user").mkdir(parents=True)
    (cc / "user" / "settings.json").write_text("{}", encoding="utf-8")
    ddl._config_checkout_root = lambda: cc

    consumer = tmp_path / "consumer"
    consumer.mkdir()

    # Consumer repo → falls back to the claude-config checkout.
    assert Path(ddl.settings_ssot_root(consumer)) == cc
    # A repo that already carries the SSOT (claude-config itself / a hermetic
    # fixture) → used unchanged, so --live CLI + hermetic tests stay identical.
    assert Path(ddl.settings_ssot_root(cc)) == cc


def test_probe_consumer_repo_resolves_ssot_to_claude_config(lazy_state_mod, tmp_path):
    """End-to-end: probing from a consumer repo whose live symlink correctly
    points at the claude-config SSOT reports ok=True (pre-fix: false 'missing
    user/settings.json' because tracked resolved to the consumer repo)."""
    cc = tmp_path / "claude-config"
    (cc / "user").mkdir(parents=True)
    (cc / "user" / "settings.json").write_text(
        json.dumps({"hooks": {}}), encoding="utf-8"
    )
    live_path = _clean_live_path(cc, tmp_path)  # symlink → cc's tracked SSOT

    consumer = tmp_path / "consumer"
    consumer.mkdir()  # AlgoBooth-like: no user/ dir at all

    # Pre-patch the config-checkout resolver on a loaded ddl and feed it through
    # the probe's loader seam (the probe re-loads fresh each call otherwise).
    ddl = lazy_state_mod._load_doc_drift_module()
    ddl._config_checkout_root = lambda: cc
    lazy_state_mod._load_doc_drift_module = lambda: ddl

    ok, detail = lazy_state_mod.live_settings_probe(consumer, live_path=live_path)

    assert ok is True, (
        f"consumer-repo probe must resolve the SSOT to claude-config and report "
        f"ok=True; got ok={ok!r} detail={detail!r}"
    )


# ---------------------------------------------------------------------------
# _live_settings_advisory (lazy_inject.py)
# ---------------------------------------------------------------------------


def test_advisory_drift_returns_line_with_repair(lazy_inject_mod, tmp_path):
    repo = _make_repo(tmp_path)
    live_path = _drift_live_path(tmp_path)

    advisory = lazy_inject_mod._live_settings_advisory(repo, live_path=live_path)

    assert isinstance(advisory, str)
    assert "repair" in advisory


def test_advisory_clean_returns_none(lazy_inject_mod, tmp_path):
    repo = _make_repo(tmp_path)
    live_path = _clean_live_path(repo, tmp_path)

    advisory = lazy_inject_mod._live_settings_advisory(repo, live_path=live_path)

    assert advisory is None


def test_advisory_failopen_returns_none_on_loader_error(lazy_inject_mod, tmp_path):
    repo = _make_repo(tmp_path)
    live_path = _drift_live_path(tmp_path)

    def _raise():
        raise RuntimeError("boom")

    lazy_inject_mod._load_doc_drift_module = _raise

    advisory = lazy_inject_mod._live_settings_advisory(repo, live_path=live_path)

    assert advisory is None


# ---------------------------------------------------------------------------
# Serving-path smoke: the real CLI probe JSON carries the new key.
# Value depends on the real machine's live settings — assert presence/type
# only, never the boolean value.
# ---------------------------------------------------------------------------


def test_probe_cli_emits_live_settings_ok_key(tmp_path):
    repo_root = SCRIPTS.parent.parent
    env = {**os.environ, "LAZY_STATE_DIR": str(tmp_path / "state")}

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "lazy-state.py"), "--probe",
         "--repo-root", str(repo_root)],
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        env=env,
    )

    try:
        parsed = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        if result.returncode != 0:
            pytest.skip(
                "probe subprocess did not emit parseable JSON and exited "
                "non-zero (unrelated terminal state): "
                + result.stdout + result.stderr
            )
        raise

    assert "live_settings_ok" in parsed
    assert isinstance(parsed["live_settings_ok"], bool)
