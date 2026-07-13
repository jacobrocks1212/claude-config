#!/usr/bin/env python3
"""
test_kpi_scorecard.py — Tests for the friction KPI registry lint + scorecard renderer.

Covers the friction-kpi-registry feature:
  - Phase 1 (WU-1.*): registry schema lint — red on each fixture violation (named row +
    field), green on the seeded real registry; review_by rot is a WARNING, not an error.
  - Phase 2 (WU-2.*): computable-today signal selectors (build-queue-results, deny-ledger,
    sentinel-scan), the availability-vs-zero honesty contract, the D4-A status engine,
    byte-stable rendering, NO-DATA / PENDING-BASELINE honesty.
  - Phase 3 (WU-3.*): telemetry-ledger selectors (containment trips, halt dwell,
    cycles-per-completion) + Regressions flags (WARN/BREACH, both directions).
  - Phase 4 (WU-4.*): the `--lint --spec` gate validator + `--capture-baseline` provenance.

The renderer is a PURE function of (registry, readings, today) — tests build fixture
registries/signal dirs directly and inject `now`/`today`, so they are hermetic. The deny +
telemetry ledgers are placed via LAZY_STATE_DIR (the house hermetic-state fixture); the
build-queue results dir via the KPI_BUILD_QUEUE_DIR env override.

Run with: python -m pytest user/scripts/test_kpi_scorecard.py -q
Stdlib + pytest only.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_REPO_ROOT = _SCRIPTS_DIR.parent.parent


def _load_module():
    """Import the dash-named module via importlib (not a valid identifier)."""
    import importlib.util

    path = _SCRIPTS_DIR / "kpi-scorecard.py"
    spec = importlib.util.spec_from_file_location("kpi_scorecard", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ksc = _load_module()

_TODAY = datetime.date(2026, 7, 4)
_NOW = 1783296000.0  # 2026-07-04T00:00:00Z-ish epoch anchor for fixtures


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _row(**overrides):
    """A fully-valid KPI row (telemetry-backed) that overrides mutate."""
    row = {
        "id": "sample-kpi",
        "system": "containment",
        "title": "Sample KPI",
        "friction": "Sample friction sentence.",
        "signal": {"source": "telemetry-ledger",
                   "selector": "containment-refusal-count"},
        "unit": "count/30d",
        "direction": "down-is-good",
        "baseline": {"value": 2, "captured_at": "2026-06-01", "window": "30d",
                     "provenance": "retro-derived"},
        "band": {"warn": 4, "breach": 8},
        "review_by": "2026-12-01",
    }
    row.update(overrides)
    return row


def _registry(*rows):
    return {"schema_version": 1, "kpis": list(rows)}


def _write_registry(tmp_path: Path, registry: dict) -> Path:
    kpi_dir = tmp_path / "docs" / "kpi"
    kpi_dir.mkdir(parents=True, exist_ok=True)
    p = kpi_dir / "registry.json"
    p.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return p


def _lint(registry):
    return ksc.lint_registry(registry, today=_TODAY)


# ---------------------------------------------------------------------------
# Phase 1 — WU-1.1: registry lint
# ---------------------------------------------------------------------------

class TestLintGreen:
    def test_valid_registry_no_errors(self):
        errors, warnings = _lint(_registry(_row()))
        assert errors == []
        assert warnings == []

    def test_pending_row_with_null_value_and_band_is_valid(self):
        row = _row(baseline={"value": None, "captured_at": None,
                             "window": "30d", "provenance": "pending"},
                   band=None)
        errors, _ = _lint(_registry(row))
        assert errors == []

    def test_real_seeded_registry_lints_green(self):
        path = _REPO_ROOT / "docs" / "kpi" / "registry.json"
        registry = ksc.load_registry(path)
        errors, warnings = ksc.lint_registry(registry, today=_TODAY)
        assert errors == []
        # The six D8 rows + harness-change-canary-rollback's trip-precision +
        # skill-config-broken-reference-reads + the three
        # efficacy-signal-integrity intervention-records rows + the
        # mcp-validation-round-trips-per-feature follow-up row (state batch 2).
        assert len(registry["kpis"]) == 12
        ids = {r["id"] for r in registry["kpis"]}
        assert "canary-trip-precision" in ids
        assert {"efficacy-verdicts-produced", "confounded-verdict-ratio",
                "canary-closure-latency-p50"} <= ids

    def test_up_is_good_band_ordering_valid(self):
        row = _row(direction="up-is-good", band={"warn": 90, "breach": 80})
        errors, _ = _lint(_registry(row))
        assert errors == []


class TestLintRed:
    def _assert_error_names(self, registry, *needles):
        errors, _ = _lint(registry)
        assert errors, "expected lint errors, got none"
        joined = "\n".join(errors)
        for needle in needles:
            assert needle in joined, f"{needle!r} not named in: {joined}"

    def test_bad_schema_version(self):
        self._assert_error_names({"schema_version": 99, "kpis": [_row()]},
                                 "schema_version")

    def test_bad_id_regex(self):
        self._assert_error_names(_registry(_row(id="Bad_ID!")), "Bad_ID!", "id")

    def test_duplicate_id(self):
        self._assert_error_names(_registry(_row(), _row()),
                                 "sample-kpi", "duplicate")

    def test_unknown_source(self):
        row = _row(signal={"source": "crystal-ball", "selector": "x"})
        self._assert_error_names(_registry(row), "sample-kpi", "crystal-ball")

    def test_unknown_selector_for_source(self):
        row = _row(signal={"source": "telemetry-ledger",
                           "selector": "not-a-selector"})
        self._assert_error_names(_registry(row), "sample-kpi", "not-a-selector")

    def test_bad_direction(self):
        self._assert_error_names(_registry(_row(direction="sideways")),
                                 "sample-kpi", "direction")

    def test_bad_provenance(self):
        row = _row(baseline={"value": 1, "captured_at": "2026-06-01",
                             "window": "30d", "provenance": "vibes"})
        self._assert_error_names(_registry(row), "sample-kpi", "provenance")

    def test_inverted_band_down_is_good(self):
        # down-is-good: warn must be <= breach.
        row = _row(band={"warn": 8, "breach": 4})
        self._assert_error_names(_registry(row), "sample-kpi", "band")

    def test_inverted_band_up_is_good(self):
        # up-is-good: warn must be >= breach.
        row = _row(direction="up-is-good", band={"warn": 80, "breach": 90})
        self._assert_error_names(_registry(row), "sample-kpi", "band")

    def test_band_with_pending_baseline_is_error(self):
        row = _row(baseline={"value": None, "captured_at": None,
                             "window": "30d", "provenance": "pending"},
                   band={"warn": 4, "breach": 8})
        self._assert_error_names(_registry(row), "sample-kpi", "band")

    def test_non_pending_baseline_requires_value_and_captured_at(self):
        row = _row(baseline={"value": None, "captured_at": None,
                             "window": "30d", "provenance": "measured"})
        self._assert_error_names(_registry(row), "sample-kpi", "baseline")

    def test_malformed_review_by(self):
        self._assert_error_names(_registry(_row(review_by="next quarter")),
                                 "sample-kpi", "review_by")

    def test_missing_required_field(self):
        row = _row()
        del row["friction"]
        self._assert_error_names(_registry(row), "sample-kpi", "friction")

    def test_bad_window(self):
        row = _row(baseline={"value": 1, "captured_at": "2026-06-01",
                             "window": "a fortnight", "provenance": "measured"})
        self._assert_error_names(_registry(row), "sample-kpi", "window")


class TestLintRotWarning:
    def test_past_review_by_is_warning_not_error(self):
        errors, warnings = _lint(_registry(_row(review_by="2026-01-01")))
        assert errors == []
        assert any("review_by" in w and "sample-kpi" in w for w in warnings)


class TestLintCli:
    def test_cli_lint_green_exits_zero(self, tmp_path):
        _write_registry(tmp_path, _registry(_row()))
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "kpi-scorecard.py"),
             "--lint", "--repo-root", str(tmp_path)],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_cli_lint_red_exits_one_and_names_row(self, tmp_path):
        row = _row(signal={"source": "crystal-ball", "selector": "x"})
        _write_registry(tmp_path, _registry(row))
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "kpi-scorecard.py"),
             "--lint", "--repo-root", str(tmp_path)],
            capture_output=True, text=True)
        assert proc.returncode == 1
        assert "sample-kpi" in proc.stdout

    def test_cli_lint_missing_registry_exits_one(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "kpi-scorecard.py"),
             "--lint", "--repo-root", str(tmp_path)],
            capture_output=True, text=True)
        assert proc.returncode == 1
        assert "registry" in (proc.stdout + proc.stderr).lower()


# ---------------------------------------------------------------------------
# Phase 2 — signal layer, status engine, renderer (WU-2.*)
# ---------------------------------------------------------------------------

def _bq_record(seq, *, build_fidelity=None, ended_at=None, extra=None):
    rec = {"seq": seq, "exit_code": 0,
           "ended_at": ended_at or "2026-07-03T12:00:00+00:00"}
    if build_fidelity is not None:
        rec["hygiene"] = {"build_fidelity": build_fidelity}
    if extra:
        rec.update(extra)
    return rec


def _write_bq_results(tmp_path: Path, records) -> Path:
    results = tmp_path / "build-queue" / "results"
    results.mkdir(parents=True, exist_ok=True)
    for rec in records:
        (results / f"{rec['seq']}.json").write_text(
            json.dumps(rec), encoding="utf-8")
    return tmp_path / "build-queue"


def _bq_row(selector="false-green-rate", **overrides):
    unit = "percent" if selector == "false-green-rate" else "seconds"
    return _row(id=f"bq-{selector}", system="build-queue",
                signal={"source": "build-queue-results", "selector": selector},
                unit=unit, **overrides)


class TestBuildQueueSelectors:
    def test_false_green_rate_computed(self, tmp_path, monkeypatch):
        bq = _write_bq_results(tmp_path, [
            _bq_record(1, build_fidelity="verified"),
            _bq_record(2, build_fidelity="verified"),
            _bq_record(3, build_fidelity="verified"),
            _bq_record(4, build_fidelity="no-output"),
        ])
        monkeypatch.setenv("KPI_BUILD_QUEUE_DIR", str(bq))
        value, note = ksc.compute_reading(_bq_row(), repo_root=tmp_path,
                                          now=_NOW)
        assert value == 25.0

    def test_false_green_excludes_na_records(self, tmp_path, monkeypatch):
        bq = _write_bq_results(tmp_path, [
            _bq_record(1, build_fidelity="log-failure-override"),
            _bq_record(2, build_fidelity="verified"),
            _bq_record(3, build_fidelity="n/a"),  # test op — excluded
        ])
        monkeypatch.setenv("KPI_BUILD_QUEUE_DIR", str(bq))
        value, _ = ksc.compute_reading(_bq_row(), repo_root=tmp_path, now=_NOW)
        assert value == 50.0

    def test_false_green_window_excludes_old_records(self, tmp_path, monkeypatch):
        bq = _write_bq_results(tmp_path, [
            _bq_record(1, build_fidelity="no-output",
                       ended_at="2025-01-01T00:00:00+00:00"),  # out of window
            _bq_record(2, build_fidelity="verified"),
        ])
        monkeypatch.setenv("KPI_BUILD_QUEUE_DIR", str(bq))
        value, _ = ksc.compute_reading(_bq_row(), repo_root=tmp_path, now=_NOW)
        assert value == 0.0  # real zero: source present, one verified record

    def test_results_dir_absent_is_no_data_not_zero(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KPI_BUILD_QUEUE_DIR",
                           str(tmp_path / "nope" / "build-queue"))
        value, note = ksc.compute_reading(_bq_row(), repo_root=tmp_path,
                                          now=_NOW)
        assert value is None
        assert note  # honest reason

    def test_queue_wait_no_timestamps_is_no_data(self, tmp_path, monkeypatch):
        bq = _write_bq_results(tmp_path, [_bq_record(1, build_fidelity="verified")])
        monkeypatch.setenv("KPI_BUILD_QUEUE_DIR", str(bq))
        value, note = ksc.compute_reading(
            _bq_row(selector="queue-wait-p50-seconds"),
            repo_root=tmp_path, now=_NOW)
        assert value is None
        assert "queued_at" in note

    def test_queue_wait_computes_when_runner_adds_timestamps(self, tmp_path,
                                                             monkeypatch):
        # Forward-compat: once the workstation runner follow-up persists the
        # pair, the selector computes without a code change.
        bq = _write_bq_results(tmp_path, [
            _bq_record(1, build_fidelity="verified",
                       extra={"queued_at": "2026-07-03T11:59:00+00:00",
                              "started_at": "2026-07-03T12:00:00+00:00"}),
            _bq_record(2, build_fidelity="verified",
                       extra={"queued_at": "2026-07-03T11:00:00+00:00",
                              "started_at": "2026-07-03T11:05:00+00:00"}),
        ])
        monkeypatch.setenv("KPI_BUILD_QUEUE_DIR", str(bq))
        value, _ = ksc.compute_reading(
            _bq_row(selector="queue-wait-p50-seconds"),
            repo_root=tmp_path, now=_NOW)
        assert value == 180.0  # median of 60s and 300s


def _deny_row(selector, **overrides):
    return _row(id=f"deny-{selector}", system="containment",
                signal={"source": "deny-ledger", "selector": selector},
                unit="count/30d", **overrides)


def _write_deny_ledger(state_dir: Path, entries) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    p = state_dir / "lazy-deny-ledger.jsonl"
    p.write_text("".join(json.dumps(e) + "\n" for e in entries),
                 encoding="utf-8")
    return p


class TestDenyLedgerSelectors:
    def test_ledger_absent_is_no_data(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LAZY_STATE_DIR", str(tmp_path / "state"))
        value, note = ksc.compute_reading(
            _deny_row("guard-deny-count"), repo_root=tmp_path, now=_NOW)
        assert value is None
        assert note

    def test_guard_vs_friction_partition_and_window(self, tmp_path, monkeypatch):
        state = tmp_path / "state"
        _write_deny_ledger(state, [
            {"ts": _NOW - 100, "reason_head": "x", "acked": False},
            {"ts": _NOW - 200, "reason_head": "y", "acked": True},
            {"ts": _NOW - 100, "kind": "process-friction", "reason_head": "z"},
            {"ts": _NOW - 90 * 86400, "reason_head": "ancient"},  # out of window
        ])
        monkeypatch.setenv("LAZY_STATE_DIR", str(state))
        guard, _ = ksc.compute_reading(_deny_row("guard-deny-count"),
                                       repo_root=tmp_path, now=_NOW)
        friction, _ = ksc.compute_reading(_deny_row("process-friction-count"),
                                          repo_root=tmp_path, now=_NOW)
        assert guard == 2.0
        assert friction == 1.0

    def test_build_queue_deny_signature_filter(self, tmp_path, monkeypatch):
        state = tmp_path / "state"
        _write_deny_ledger(state, [
            {"ts": _NOW - 100,
             "reason_head": "BUILD-QUEUE enforcement: raw dotnet build denied"},
            {"ts": _NOW - 100, "reason_head": "some other deny"},
        ])
        monkeypatch.setenv("LAZY_STATE_DIR", str(state))
        value, _ = ksc.compute_reading(
            _deny_row("build-queue-enforce-deny-count"),
            repo_root=tmp_path, now=_NOW)
        assert value == 1.0


class TestSentinelScanSelector:
    def test_open_halt_count(self, tmp_path):
        (tmp_path / "docs" / "features" / "f1").mkdir(parents=True)
        (tmp_path / "docs" / "features" / "f1" / "BLOCKED.md").write_text("x")
        (tmp_path / "docs" / "bugs" / "b1").mkdir(parents=True)
        (tmp_path / "docs" / "bugs" / "b1" / "NEEDS_INPUT.md").write_text("x")
        # Resolved sentinels do NOT count.
        (tmp_path / "docs" / "bugs" / "b1"
         / "NEEDS_INPUT_RESOLVED_2026-07-01.md").write_text("x")
        row = _row(id="halt-open", system="halt-handling",
                   signal={"source": "sentinel-scan",
                           "selector": "open-halt-count"},
                   unit="count/30d")
        value, _ = ksc.compute_reading(row, repo_root=tmp_path, now=_NOW)
        assert value == 2.0

    def test_missing_docs_trees_is_no_data(self, tmp_path):
        row = _row(id="halt-open", system="halt-handling",
                   signal={"source": "sentinel-scan",
                           "selector": "open-halt-count"},
                   unit="count/30d")
        value, note = ksc.compute_reading(row, repo_root=tmp_path, now=_NOW)
        assert value is None
        assert note


class TestStatusEngine:
    def _status(self, value, *, direction="down-is-good", warn=4, breach=8,
                provenance="retro-derived"):
        row = _row(direction=direction,
                   baseline={"value": 1, "captured_at": "2026-06-01",
                             "window": "30d", "provenance": provenance},
                   band=None if provenance == "pending"
                        else {"warn": warn, "breach": breach})
        return ksc.row_status(row, value)

    def test_no_data(self):
        assert self._status(None) == "NO-DATA"

    def test_pending_baseline_beats_band_comparison(self):
        assert self._status(99, provenance="pending") == "PENDING-BASELINE"

    def test_null_band_is_pending(self):
        row = _row(band=None)
        assert ksc.row_status(row, 5) == "PENDING-BASELINE"

    def test_down_is_good_thresholds(self):
        assert self._status(3.9) == "OK"
        assert self._status(4) == "WARN"      # exact warn edge
        assert self._status(7.9) == "WARN"
        assert self._status(8) == "BREACH"    # exact breach edge
        assert self._status(20) == "BREACH"

    def test_up_is_good_thresholds(self):
        kw = dict(direction="up-is-good", warn=90, breach=80)
        assert self._status(95, **kw) == "OK"
        assert self._status(90, **kw) == "WARN"
        assert self._status(85, **kw) == "WARN"
        assert self._status(80, **kw) == "BREACH"
        assert self._status(10, **kw) == "BREACH"


class TestRenderScorecard:
    def _render(self, registry, readings):
        return ksc.render_scorecard(registry, readings, today=_TODAY)

    def test_no_data_renders_dash_and_note_never_zero(self):
        row = _row(baseline={"value": None, "captured_at": None,
                             "window": "30d", "provenance": "pending"},
                   band=None)
        doc = self._render(_registry(row),
                           {"sample-kpi": (None, "telemetry ledger absent")})
        assert "NO-DATA" in doc
        assert "telemetry ledger absent" in doc
        line = next(l for l in doc.splitlines() if "Sample KPI" in l)
        assert "0" not in line.split("|")[2]  # current cell carries no zero

    def test_pending_baseline_rendered_for_present_value(self):
        row = _row(baseline={"value": None, "captured_at": None,
                             "window": "30d", "provenance": "pending"},
                   band=None)
        doc = self._render(_registry(row), {"sample-kpi": (3.0, None)})
        assert "PENDING-BASELINE" in doc

    def test_ok_row_renders_value_baseline_band_and_glyph(self):
        doc = self._render(_registry(_row()), {"sample-kpi": (3.0, None)})
        line = next(l for l in doc.splitlines() if "Sample KPI" in l)
        assert "3/30d" in line
        assert "2/30d (retro-derived 2026-06-01)" in line
        assert "4 / 8" in line
        assert "OK ▼" in line

    def test_regressions_section_lists_warn_and_breach(self):
        r1 = _row()
        r2 = _row(id="second-kpi", title="Second KPI", direction="up-is-good",
                  unit="percent",
                  baseline={"value": 95, "captured_at": "2026-06-01",
                            "window": "30d", "provenance": "measured"},
                  band={"warn": 90, "breach": 80})
        doc = self._render(_registry(r1, r2),
                           {"sample-kpi": (5.0, None),      # WARN (down)
                            "second-kpi": (75.0, None)})    # BREACH (up)
        reg = doc.split("## Regressions", 1)[1].split("##", 1)[0]
        assert "containment/sample-kpi WARN" in reg
        assert "containment/second-kpi BREACH" in reg
        assert "(none)" not in reg

    def test_regressions_none_line_when_clean(self):
        doc = self._render(_registry(_row()), {"sample-kpi": (1.0, None)})
        reg = doc.split("## Regressions", 1)[1].split("##", 1)[0]
        assert "(none)" in reg

    def test_registry_health_flags_past_review_by(self):
        doc = self._render(_registry(_row(review_by="2026-01-01")),
                           {"sample-kpi": (1.0, None)})
        health = doc.split("## Registry health", 1)[1]
        assert "sample-kpi" in health
        assert "2026-01-01" in health

    def test_byte_stable_double_render(self):
        registry = _registry(_row(), _row(id="second-kpi", title="Second"))
        readings = {"sample-kpi": (3.0, None), "second-kpi": (None, "absent")}
        a = self._render(registry, readings)
        b = self._render(registry, readings)
        assert a == b
        assert a.endswith("\n") and not a.endswith("\n\n")
        assert "20" not in a.split("## Notes")[0].split("|", 1)[0]  # no date in H1

    def test_home_paths_abbreviated_in_notes(self):
        home_note = f"results dir absent ({Path.home()}/x)"
        doc = self._render(_registry(_row()), {"sample-kpi": (None, home_note)})
        assert str(Path.home()) not in doc.split("## Notes", 1)[1]
        assert "~/x" in doc


class TestRenderCli:
    def test_default_writes_scorecard_and_stdout_prints(self, tmp_path,
                                                        monkeypatch):
        _write_registry(tmp_path, _registry(_row()))
        env = dict(os.environ,
                   LAZY_STATE_DIR=str(tmp_path / "state"),
                   KPI_BUILD_QUEUE_DIR=str(tmp_path / "bq"))
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "kpi-scorecard.py"),
             "--repo-root", str(tmp_path), "--stdout"],
            capture_output=True, text=True, env=env)
        assert proc.returncode == 0, proc.stderr
        assert "# Friction KPI Scorecard" in proc.stdout
        assert not (tmp_path / "docs" / "kpi" / "SCORECARD.md").exists()

        proc2 = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "kpi-scorecard.py"),
             "--repo-root", str(tmp_path)],
            capture_output=True, text=True, env=env)
        assert proc2.returncode == 0, proc2.stderr
        out = tmp_path / "docs" / "kpi" / "SCORECARD.md"
        assert out.exists()
        # Byte-stability across CLI runs (no wall-clock embed).
        first = out.read_text(encoding="utf-8")
        subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "kpi-scorecard.py"),
             "--repo-root", str(tmp_path)],
            capture_output=True, text=True, env=env)
        assert out.read_text(encoding="utf-8") == first


# ---------------------------------------------------------------------------
# Phase 3 — telemetry-ledger selectors (WU-3.*)
# ---------------------------------------------------------------------------

def _tel_event(event, *, ts, item_id=None, data=None, run_id="2026-07-01T00:00:00Z",
               pipeline="feature"):
    return {"v": 1, "ts": ts, "run_id": run_id, "pipeline": pipeline,
            "event": event, "item_id": item_id, "data": data or {}}


def _write_telemetry(state_dir: Path, events) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    p = state_dir / "lazy-telemetry.jsonl"
    p.write_text("".join(json.dumps(e) + "\n" for e in events),
                 encoding="utf-8")
    return p


def _tel_row(selector, **overrides):
    unit = {"containment-refusal-count": "count/30d",
            "halt-dwell-p50-seconds": "seconds",
            "cycles-per-completion": "ratio"}[selector]
    return _row(id=f"tel-{selector}",
                signal={"source": "telemetry-ledger", "selector": selector},
                unit=unit, **overrides)


class TestTelemetrySelectors:
    def test_ledger_absent_is_no_data(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LAZY_STATE_DIR", str(tmp_path / "state"))
        value, note = ksc.compute_reading(
            _tel_row("containment-refusal-count"), repo_root=tmp_path, now=_NOW)
        assert value is None
        assert note

    def test_containment_refusal_count_windowed(self, tmp_path, monkeypatch):
        state = tmp_path / "state"
        _write_telemetry(state, [
            _tel_event("containment-refusal", ts=_NOW - 100),
            _tel_event("containment-refusal", ts=_NOW - 200),
            _tel_event("containment-refusal", ts=_NOW - 90 * 86400),  # out
            _tel_event("gate-refusal", ts=_NOW - 100),  # different event
        ])
        monkeypatch.setenv("LAZY_STATE_DIR", str(state))
        value, _ = ksc.compute_reading(
            _tel_row("containment-refusal-count"), repo_root=tmp_path, now=_NOW)
        assert value == 2.0

    def test_halt_dwell_p50(self, tmp_path, monkeypatch):
        state = tmp_path / "state"
        _write_telemetry(state, [
            _tel_event("halt", ts=_NOW - 10000, item_id="f1",
                       data={"terminal_reason": "blocked"}),
            _tel_event("sentinel-resolved", ts=_NOW - 6400, item_id="f1"),
            _tel_event("halt", ts=_NOW - 5000, item_id="f2",
                       data={"terminal_reason": "needs-input"}),  # unresolved
        ])
        monkeypatch.setenv("LAZY_STATE_DIR", str(state))
        value, _ = ksc.compute_reading(
            _tel_row("halt-dwell-p50-seconds"), repo_root=tmp_path, now=_NOW)
        assert value == 3600.0  # the one resolved dwell; open halt excluded

    def test_halt_dwell_no_resolved_halts_is_no_data(self, tmp_path, monkeypatch):
        state = tmp_path / "state"
        _write_telemetry(state, [
            _tel_event("halt", ts=_NOW - 5000, item_id="f2",
                       data={"terminal_reason": "blocked"}),
        ])
        monkeypatch.setenv("LAZY_STATE_DIR", str(state))
        value, note = ksc.compute_reading(
            _tel_row("halt-dwell-p50-seconds"), repo_root=tmp_path, now=_NOW)
        assert value is None
        assert "resolved" in note

    def test_cycles_per_completion(self, tmp_path, monkeypatch):
        state = tmp_path / "state"
        _write_telemetry(state, [
            _tel_event("cycle-begin", ts=_NOW - 400, data={"kind": "real"}),
            _tel_event("cycle-begin", ts=_NOW - 300, data={"kind": "real"}),
            _tel_event("cycle-begin", ts=_NOW - 200, data={"kind": "meta"}),
            _tel_event("pseudo-applied", ts=_NOW - 100,
                       data={"pseudo": "__mark_complete__"}),
        ])
        monkeypatch.setenv("LAZY_STATE_DIR", str(state))
        value, _ = ksc.compute_reading(
            _tel_row("cycles-per-completion"), repo_root=tmp_path, now=_NOW)
        assert value == 3.0

    def test_cycles_no_completions_is_no_data_not_fabricated(self, tmp_path,
                                                             monkeypatch):
        state = tmp_path / "state"
        _write_telemetry(state, [
            _tel_event("cycle-begin", ts=_NOW - 400, data={"kind": "real"}),
        ])
        monkeypatch.setenv("LAZY_STATE_DIR", str(state))
        value, note = ksc.compute_reading(
            _tel_row("cycles-per-completion"), repo_root=tmp_path, now=_NOW)
        assert value is None
        assert "completion" in note


# ---------------------------------------------------------------------------
# Phase 4 (WU-9) — canary-trip-precision selector
# ---------------------------------------------------------------------------

def _canary_row(**overrides):
    return _row(id="canary-trip-precision", system="harness-canary",
                title="Canary trip precision",
                signal={"source": "telemetry-ledger",
                        "selector": "canary-trip-precision"},
                unit="percent", direction="up-is-good",
                baseline={"value": None, "captured_at": None,
                          "window": "90d", "provenance": "pending"},
                band=None, **overrides)


def _write_intervention(repo_root: Path, rid: str, *, canary_status="tripped",
                        opened="2026-07-01", enqueued="2026-07-02") -> None:
    d = repo_root / "docs" / "interventions"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["---", "kind: intervention", f"intervention_id: {rid}",
             "canary:", f"  status: {canary_status}", f"  opened: '{opened}'"]
    if enqueued is not None:
        lines.append(f"canary_revert_enqueued: '{enqueued}'")
    lines += ["---", "", "body", ""]
    (d / f"{rid}.md").write_text("\n".join(lines), encoding="utf-8")


def _write_revert_bug(repo_root: Path, rid: str, *, status: str,
                      archived: bool = False) -> None:
    revert_id = f"canary-revert-{rid}"
    base = repo_root / "docs" / "bugs"
    d = (base / "_archive" / revert_id) if archived else (base / revert_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "SPEC.md").write_text(
        f"# {revert_id}\n\n**Status:** {status}\n", encoding="utf-8")


class TestCanaryTripPrecision:
    def test_no_interventions_ledger_is_no_data(self, tmp_path):
        value, note = ksc.compute_reading(_canary_row(), repo_root=tmp_path,
                                          now=_NOW)
        assert value is None
        assert "never tripped" in note

    def test_open_canary_no_trips_is_no_data_not_zero(self, tmp_path):
        _write_intervention(tmp_path, "still-open", canary_status="open",
                            enqueued=None)
        value, note = ksc.compute_reading(_canary_row(), repo_root=tmp_path,
                                          now=_NOW)
        assert value is None                       # NEVER a fabricated 0
        assert "no canary trips" in note

    def test_precision_computed_from_trips_and_noise(self, tmp_path):
        for i in range(4):
            _write_intervention(tmp_path, f"trip-{i}")
        _write_revert_bug(tmp_path, "trip-0", status="Won't-fix")    # noise
        _write_revert_bug(tmp_path, "trip-1", status="Fixed")        # real revert
        _write_revert_bug(tmp_path, "trip-2", status="In-progress")  # real, open
        # trip-3 has no revert bug on disk → not noise (counts toward precision)
        value, note = ksc.compute_reading(_canary_row(), repo_root=tmp_path,
                                          now=_NOW)
        assert note is None
        assert value == 75.0                       # 3 of 4 not closed-as-noise

    def test_archived_wont_fix_counts_as_noise(self, tmp_path):
        _write_intervention(tmp_path, "arch-trip")
        _write_revert_bug(tmp_path, "arch-trip", status="Won't-fix",
                          archived=True)
        value, note = ksc.compute_reading(_canary_row(), repo_root=tmp_path,
                                          now=_NOW)
        assert note is None
        assert value == 0.0                        # single trip, closed-as-noise

    def test_trip_outside_window_excluded_is_no_data(self, tmp_path):
        _write_intervention(tmp_path, "old-trip", opened="2020-01-01",
                            enqueued="2020-01-02")
        value, note = ksc.compute_reading(_canary_row(), repo_root=tmp_path,
                                          now=_NOW)
        assert value is None
        assert "no canary trips" in note

    def test_stdout_renders_canary_row_as_no_data(self):
        doc = ksc.render_scorecard(
            _registry(_canary_row()),
            {"canary-trip-precision": (None, "no canary trips in the window")},
            today=_TODAY)
        assert "Canary trip precision" in doc
        assert "NO-DATA" in doc
        line = next(l for l in doc.splitlines()
                    if "Canary trip precision" in l)
        assert "0" not in line.split("|")[2]       # current cell carries no zero


# ---------------------------------------------------------------------------
# efficacy-signal-integrity Phase 3 — vantage / WRONG-VANTAGE
# ---------------------------------------------------------------------------

class TestVantageLint:
    def test_absent_vantage_is_valid(self):
        errors, _ = _lint(_registry(_row()))
        assert errors == []

    def test_valid_vantage_object(self):
        row = _row(vantage={"repo": "claude-config", "host": "workstation"})
        errors, _ = _lint(_registry(row))
        assert errors == []

    def test_invalid_host_enum(self):
        row = _row(vantage={"repo": "claude-config", "host": "laptop"})
        errors, _ = _lint(_registry(row))
        assert any("vantage.host" in e for e in errors)

    def test_vantage_must_be_object(self):
        row = _row(vantage="claude-config")
        errors, _ = _lint(_registry(row))
        assert any("vantage must be an object" in e for e in errors)

    def test_vantage_repo_must_be_nonempty_string(self):
        row = _row(vantage={"repo": "", "host": "any"})
        errors, _ = _lint(_registry(row))
        assert any("vantage.repo" in e for e in errors)


class TestVantageStatus:
    def test_no_data_matching_vantage_stays_no_data(self, tmp_path):
        row = _row(vantage={"repo": tmp_path.name, "host": "workstation"})
        status = ksc.row_status(row, None, repo_root=tmp_path, host="workstation")
        assert status == "NO-DATA"

    def test_no_data_wrong_repo_is_wrong_vantage(self, tmp_path):
        row = _row(vantage={"repo": "some-other-repo", "host": "any"})
        status = ksc.row_status(row, None, repo_root=tmp_path, host="workstation")
        assert status == "WRONG-VANTAGE"

    def test_no_data_wrong_host_is_wrong_vantage(self, tmp_path):
        row = _row(vantage={"repo": "any", "host": "cloud"})
        status = ksc.row_status(row, None, repo_root=tmp_path, host="workstation")
        assert status == "WRONG-VANTAGE"

    def test_any_vantage_never_wrong(self, tmp_path):
        row = _row(vantage={"repo": "any", "host": "any"})
        status = ksc.row_status(row, None, repo_root=tmp_path, host="workstation")
        assert status == "NO-DATA"

    def test_value_present_ignores_vantage(self, tmp_path):
        row = _row(vantage={"repo": "some-other-repo", "host": "cloud"})
        status = ksc.row_status(row, 3.0, repo_root=tmp_path, host="workstation")
        assert status in ("OK", "WARN", "BREACH")

    def test_omitted_repo_root_host_never_wrong_vantage(self):
        """Old callers (--lint, or any caller that never passes repo_root/host)
        get byte-identical NO-DATA — never a surprise WRONG-VANTAGE."""
        row = _row(vantage={"repo": "some-other-repo", "host": "cloud"})
        status = ksc.row_status(row, None)
        assert status == "NO-DATA"

    def test_render_wrong_vantage(self, tmp_path):
        row = _row(vantage={"repo": "some-other-repo", "host": "any"})
        doc = ksc.render_scorecard(
            _registry(row), {"sample-kpi": (None, "not observable here")},
            today=_TODAY, repo_root=tmp_path, host="workstation")
        assert "WRONG-VANTAGE" in doc


# ---------------------------------------------------------------------------
# efficacy-signal-integrity Phase 3 — intervention-records selectors
# ---------------------------------------------------------------------------

def _ivr_row(selector, **overrides):
    unit = {"conclusive-verdict-count": "count/90d",
            "confounded-verdict-ratio": "percent",
            "canary-closure-latency-p50-days": "days"}[selector]
    row = _row(id=f"ivr-{selector}",
              signal={"source": "intervention-records", "selector": selector},
              unit=unit)
    row.update(overrides)
    return row


def _write_review_record(repo_root: Path, rid: str, reviews: list) -> None:
    """A minimal, hand-written (never through the real evaluator — this suite
    tests kpi-scorecard.py's OWN read, not efficacy-eval.py) intervention
    record carrying `## Review <date>` sections, mirroring the shape
    efficacy-eval.py's `_review_record` actually appends."""
    d = repo_root / "docs" / "interventions"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["---", "kind: intervention", f"intervention_id: {rid}",
             "status: open", "---", ""]
    for r in reviews:
        suffix = " (confounded cap)" if r.get("confounded") else ""
        lines.append(f"## Review {r['date']}")
        lines.append("")
        lines.append(f"- verdict: {r['verdict']}{suffix}")
        if r.get("confounded"):
            lines.append(
                "- reason: confounded — same-signal overlap with other-id "
                "(raw: movement +50.0% vs band ±20% (direction decrease))")
        else:
            lines.append(
                "- reason: movement -50.0% vs band ±20% (direction decrease)")
        lines.append("")
    (d / f"{rid}.md").write_text("\n".join(lines), encoding="utf-8")


class TestConclusiveVerdictCount:
    def test_no_interventions_dir_is_no_data(self, tmp_path):
        value, note = ksc.compute_reading(
            _ivr_row("conclusive-verdict-count"), repo_root=tmp_path, now=_NOW)
        assert value is None
        assert note

    def test_counts_confirmed_and_refuted_not_inconclusive(self, tmp_path):
        _write_review_record(tmp_path, "rec-a",
                             [{"date": "2026-07-03", "verdict": "CONFIRMED"}])
        _write_review_record(tmp_path, "rec-b",
                             [{"date": "2026-07-03", "verdict": "REFUTED"}])
        _write_review_record(tmp_path, "rec-c",
                             [{"date": "2026-07-03", "verdict": "INCONCLUSIVE"}])
        value, note = ksc.compute_reading(
            _ivr_row("conclusive-verdict-count"), repo_root=tmp_path, now=_NOW)
        assert note is None
        assert value == 2.0

    def test_window_excludes_old_reviews(self, tmp_path):
        _write_review_record(tmp_path, "rec-old",
                             [{"date": "2020-01-01", "verdict": "CONFIRMED"}])
        value, note = ksc.compute_reading(
            _ivr_row("conclusive-verdict-count"), repo_root=tmp_path, now=_NOW)
        assert value is None
        assert "no reviews" in note


class TestConfoundedVerdictRatio:
    def test_no_reviews_is_no_data(self, tmp_path):
        value, note = ksc.compute_reading(
            _ivr_row("confounded-verdict-ratio"), repo_root=tmp_path, now=_NOW)
        assert value is None

    def test_ratio_over_due_reviews(self, tmp_path):
        _write_review_record(tmp_path, "rec-a", [
            {"date": "2026-07-03", "verdict": "INCONCLUSIVE", "confounded": True}])
        _write_review_record(tmp_path, "rec-b",
                             [{"date": "2026-07-03", "verdict": "CONFIRMED"}])
        _write_review_record(tmp_path, "rec-c",
                             [{"date": "2026-07-03", "verdict": "REFUTED"}])
        _write_review_record(tmp_path, "rec-d",
                             [{"date": "2026-07-03", "verdict": "INCONCLUSIVE"}])
        value, note = ksc.compute_reading(
            _ivr_row("confounded-verdict-ratio"), repo_root=tmp_path, now=_NOW)
        assert note is None
        assert value == 25.0        # 1 of 4 due reviews confounded


def _write_canary_record(repo_root: Path, rid: str, *, status: str,
                         opened: str, canary_section_date=None,
                         enqueued=None, baseline_last_run_id=None) -> None:
    d = repo_root / "docs" / "interventions"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["---", "kind: intervention", f"intervention_id: {rid}"]
    if baseline_last_run_id is not None:
        lines += ["baseline:", "  status: frozen",
                  f"  last_run_id: '{baseline_last_run_id}'"]
    lines += ["canary:", f"  status: {status}", f"  opened: '{opened}'"]
    if enqueued is not None:
        lines.append(f"canary_revert_enqueued: '{enqueued}'")
    lines += ["---", ""]
    if canary_section_date is not None:
        lines.append(f"## Canary {canary_section_date}")
        lines.append("")
        lines.append(
            "- window: closed after 4/4 observed post-ship run(s) "
            "(matured: True)")
        lines.append("")
    (d / f"{rid}.md").write_text("\n".join(lines), encoding="utf-8")


class TestCanaryClosureLatency:
    def test_no_interventions_dir_is_no_data(self, tmp_path):
        value, note = ksc.compute_reading(
            _ivr_row("canary-closure-latency-p50-days"), repo_root=tmp_path,
            now=_NOW)
        assert value is None

    def test_closed_clean_latency_median(self, tmp_path):
        _write_canary_record(tmp_path, "clean-a", status="closed-clean",
                             opened="2026-06-20",
                             canary_section_date="2026-06-25")   # 5 days
        _write_canary_record(tmp_path, "clean-b", status="closed-clean",
                             opened="2026-06-15",
                             canary_section_date="2026-06-25")   # 10 days
        value, note = ksc.compute_reading(
            _ivr_row("canary-closure-latency-p50-days"), repo_root=tmp_path,
            now=_NOW)
        assert note is None
        assert value == 7.5

    def test_no_data_close_excluded(self, tmp_path):
        _write_canary_record(tmp_path, "nodata",
                             status="closed-clean (no-data)",
                             opened="2026-06-01",
                             canary_section_date="2026-07-01")
        value, note = ksc.compute_reading(
            _ivr_row("canary-closure-latency-p50-days"), repo_root=tmp_path,
            now=_NOW)
        assert value is None

    def test_tripped_uses_revert_enqueued_date(self, tmp_path):
        _write_canary_record(tmp_path, "tripped-a", status="tripped",
                             opened="2026-06-20", enqueued="2026-06-30")
        value, note = ksc.compute_reading(
            _ivr_row("canary-closure-latency-p50-days"), repo_root=tmp_path,
            now=_NOW)
        assert note is None
        assert value == 10.0

    def test_open_canary_not_counted(self, tmp_path):
        _write_canary_record(tmp_path, "still-open", status="open",
                             opened="2026-06-01")
        value, note = ksc.compute_reading(
            _ivr_row("canary-closure-latency-p50-days"), repo_root=tmp_path,
            now=_NOW)
        assert value is None


# ---------------------------------------------------------------------------
# efficacy-signal-integrity Phase 2/3 — Canary health section
# ---------------------------------------------------------------------------

class TestCanaryHealthSummary:
    def test_no_open_canaries_is_all_zero(self, tmp_path):
        ch = ksc._canary_health_summary(tmp_path, _TODAY)
        assert ch["open_count"] == 0
        assert ch["oldest_age_days"] == 0
        assert ch["projected_no_data_close_count"] == 0

    def test_open_canary_ages_and_projects_no_data(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LAZY_STATE_DIR", str(tmp_path / "state"))
        _write_canary_record(tmp_path, "stale-one", status="open",
                             opened="2026-06-09")   # 25 days before _TODAY
        ch = ksc._canary_health_summary(tmp_path, _TODAY)
        assert ch["open_count"] == 1
        assert ch["oldest_age_days"] == 25
        assert ch["projected_no_data_close_count"] == 1

    def test_open_canary_with_observed_run_not_projected(self, tmp_path,
                                                         monkeypatch):
        state = tmp_path / "state"
        monkeypatch.setenv("LAZY_STATE_DIR", str(state))
        _write_canary_record(tmp_path, "stale-but-observed", status="open",
                             opened="2026-06-09",
                             baseline_last_run_id="2026-06-01T00:00:00Z")
        _write_telemetry(state, [
            _tel_event("run-start", ts=_NOW, run_id="2026-07-01T00:00:00Z"),
        ])
        ch = ksc._canary_health_summary(tmp_path, _TODAY)
        assert ch["open_count"] == 1
        assert ch["projected_no_data_close_count"] == 0

    def test_render_includes_canary_health_section(self):
        doc = ksc.render_scorecard(
            _registry(_row()), {"sample-kpi": (1.0, None)}, today=_TODAY,
            canary_health={"open_count": 2, "oldest_age_days": 24,
                          "projected_no_data_close_count": 1})
        section = doc.split("## Canary health", 1)[1]
        assert ("2 canaries open, oldest 24d, 1 will no-data-close within 7d"
               in section)
        assert "⚠" in section

    def test_render_no_open_canaries(self):
        doc = ksc.render_scorecard(_registry(_row()), {"sample-kpi": (1.0, None)},
                                   today=_TODAY)
        section = doc.split("## Canary health", 1)[1].split("##", 1)[0]
        assert "(none open)" in section


# ---------------------------------------------------------------------------
# Phase 4 — `/spec` measurability gate validator (WU-4.1) + baseline capture
# ---------------------------------------------------------------------------

_SPEC_HEADER = (
    "# Sample Feature — Feature Specification\n\n"
    "> One-line summary\n\n"
    "**Status:** Draft\n**Priority:** P1\n**Last updated:** 2026-07-04\n\n"
)


def _spec(*, classification=None, keywords=False, declaration=None, body=""):
    """Build a SPEC.md body with an optional classification line + declaration."""
    text = _SPEC_HEADER
    if classification is not None:
        text += f"**Friction-reduction feature:** {classification}\n\n"
    text += "---\n\n## Executive Summary\n\n"
    if keywords:
        text += ("This feature reduces friction and wasted cycles, cutting "
                 "retry toil across the harness.\n\n")
    else:
        text += "A perfectly ordinary feature with a plain user purpose.\n\n"
    text += body
    if declaration is not None:
        text += "\n## KPI Declaration\n\n" + declaration + "\n"
    text += "\n## Open Questions\n\n- (none)\n"
    return text


class TestSpecClassificationParse:
    def test_yes(self):
        assert ksc.parse_spec_classification(
            _spec(classification="yes")) == "yes"

    def test_no(self):
        assert ksc.parse_spec_classification(
            _spec(classification="no")) == "no"

    def test_missing_is_none(self):
        assert ksc.parse_spec_classification(_spec()) is None

    def test_case_insensitive(self):
        assert ksc.parse_spec_classification(
            _spec(classification="YES")) == "yes"


class TestLintSpec:
    def _lint(self, spec_text, registry=None):
        if registry is None:
            registry = _registry(_row(id="build-queue-false-green-rate"))
        return ksc.lint_spec(spec_text, registry, today=_TODAY)

    def test_missing_classification_is_error(self):
        errors, _ = self._lint(_spec())
        assert errors
        assert any("Friction-reduction feature" in e for e in errors)

    def test_no_ordinary_spec_is_clean(self):
        errors, warnings = self._lint(_spec(classification="no"))
        assert errors == []
        assert warnings == []

    def test_no_with_friction_keywords_is_advisory_warning(self):
        errors, warnings = self._lint(
            _spec(classification="no", keywords=True))
        assert errors == []  # non-blocking
        assert warnings
        assert any("friction" in w.lower() for w in warnings)

    def test_yes_without_declaration_section_is_error(self):
        errors, _ = self._lint(_spec(classification="yes"))
        assert errors
        assert any("KPI Declaration" in e for e in errors)

    def test_yes_with_resolving_id_is_clean(self):
        errors, _ = self._lint(
            _spec(classification="yes",
                  declaration="- kpi: build-queue-false-green-rate"))
        assert errors == []

    def test_yes_with_unresolved_id_is_error(self):
        errors, _ = self._lint(
            _spec(classification="yes",
                  declaration="- kpi: no-such-registered-kpi"))
        assert errors
        assert any("no-such-registered-kpi" in e for e in errors)

    def test_yes_with_valid_json_draft_row_is_clean(self):
        draft = json.dumps(_row(id="drafted-new-kpi"), indent=2)
        errors, _ = self._lint(
            _spec(classification="yes",
                  declaration=f"```json\n{draft}\n```"))
        assert errors == []

    def test_yes_with_invalid_json_draft_row_is_error(self):
        bad = json.dumps(_row(id="Bad_ID!"), indent=2)  # bad id regex
        errors, _ = self._lint(
            _spec(classification="yes",
                  declaration=f"```json\n{bad}\n```"))
        assert errors
        assert any("Bad_ID!" in e or "draft" in e.lower() for e in errors)

    def test_yes_with_malformed_json_is_error(self):
        errors, _ = self._lint(
            _spec(classification="yes",
                  declaration="```json\n{ not valid json \n```"))
        assert errors
        assert any("json" in e.lower() for e in errors)

    def test_yes_with_empty_declaration_is_error(self):
        errors, _ = self._lint(
            _spec(classification="yes", declaration="(nothing here)"))
        assert errors


class TestLintSpecCli:
    def _run(self, tmp_path, spec_text, registry=None):
        if registry is None:
            registry = _registry(_row(id="build-queue-false-green-rate"))
        _write_registry(tmp_path, registry)
        spec = tmp_path / "SPEC.md"
        spec.write_text(spec_text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "kpi-scorecard.py"),
             "--lint", "--spec", str(spec), "--repo-root", str(tmp_path)],
            capture_output=True, text=True)

    def test_friction_spec_without_declaration_exits_one(self, tmp_path):
        proc = self._run(tmp_path, _spec(classification="yes"))
        assert proc.returncode == 1
        assert "KPI Declaration" in proc.stdout

    def test_ordinary_no_spec_exits_zero_untouched(self, tmp_path):
        proc = self._run(tmp_path, _spec(classification="no"))
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_no_with_keywords_advisory_exits_zero(self, tmp_path):
        proc = self._run(tmp_path, _spec(classification="no", keywords=True))
        assert proc.returncode == 0, proc.stdout
        assert "WARNING" in proc.stdout or "advisory" in proc.stdout.lower()

    def test_resolving_declaration_exits_zero(self, tmp_path):
        proc = self._run(
            tmp_path,
            _spec(classification="yes",
                  declaration="- kpi: build-queue-false-green-rate"))
        assert proc.returncode == 0, proc.stdout

    def test_unresolved_id_exits_one(self, tmp_path):
        proc = self._run(
            tmp_path,
            _spec(classification="yes", declaration="- kpi: nope-not-real"))
        assert proc.returncode == 1
        assert "nope-not-real" in proc.stdout

    def test_missing_classification_exits_one(self, tmp_path):
        proc = self._run(tmp_path, _spec())
        assert proc.returncode == 1


# ---------------------------------------------------------------------------
# Phase 4 — `--capture-baseline` (WU-4.1)
# ---------------------------------------------------------------------------

class TestCaptureBaseline:
    def _capture(self, tmp_path, kpi_id, env):
        return subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "kpi-scorecard.py"),
             "--capture-baseline", kpi_id, "--repo-root", str(tmp_path)],
            capture_output=True, text=True, env=env)

    def test_stamps_measured_and_captured_at(self, tmp_path):
        # A build-queue false-green row + a fixture results dir with data.
        row = _bq_row(baseline={"value": None, "captured_at": None,
                                "window": "30d", "provenance": "pending"},
                      band=None)
        _write_registry(tmp_path, _registry(row))
        bq = _write_bq_results(tmp_path, [
            _bq_record(1, build_fidelity="verified"),
            _bq_record(2, build_fidelity="no-output",
                       ended_at=datetime.datetime.now(
                           datetime.timezone.utc).isoformat()),
            _bq_record(1, build_fidelity="verified",
                       ended_at=datetime.datetime.now(
                           datetime.timezone.utc).isoformat()),
        ])
        env = dict(os.environ, KPI_BUILD_QUEUE_DIR=str(bq),
                   LAZY_STATE_DIR=str(tmp_path / "state"))
        proc = self._capture(tmp_path, "bq-false-green-rate", env)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        reg = ksc.load_registry(
            tmp_path / "docs" / "kpi" / "registry.json")
        b = reg["kpis"][0]["baseline"]
        assert b["provenance"] == "measured"
        assert b["value"] is not None
        assert b["captured_at"] == datetime.date.today().isoformat()
        # Registry remains lint-green after capture.
        errors, _ = ksc.lint_registry(reg, today=datetime.date.today())
        assert errors == []

    def test_refuses_on_no_data(self, tmp_path):
        row = _bq_row(baseline={"value": None, "captured_at": None,
                                "window": "30d", "provenance": "pending"},
                      band=None)
        _write_registry(tmp_path, _registry(row))
        env = dict(os.environ,
                   KPI_BUILD_QUEUE_DIR=str(tmp_path / "nope"),
                   LAZY_STATE_DIR=str(tmp_path / "state"))
        proc = self._capture(tmp_path, "bq-false-green-rate", env)
        assert proc.returncode == 1
        # Baseline unchanged (still pending / null).
        reg = ksc.load_registry(
            tmp_path / "docs" / "kpi" / "registry.json")
        assert reg["kpis"][0]["baseline"]["provenance"] == "pending"
        assert reg["kpis"][0]["baseline"]["value"] is None

    def test_unknown_id_refuses(self, tmp_path):
        _write_registry(tmp_path, _registry(_row()))
        env = dict(os.environ, LAZY_STATE_DIR=str(tmp_path / "state"))
        proc = self._capture(tmp_path, "no-such-kpi", env)
        assert proc.returncode == 1
