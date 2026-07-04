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
        # The seed set is exactly the six D8 rows.
        assert len(registry["kpis"]) == 6

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
