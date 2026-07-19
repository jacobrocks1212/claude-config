"""Tests for the execute-plan pause-vs-terminal liveness discriminator
(docs/bugs/adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke,
Phase 1 — Gap 2).

Two surfaces are exercised:

  * WU-1 — the pure ``lazy_core.execute_plan_liveness(repo_root, plan_path)``
    helper, driven against REAL on-disk execute-plan marker files in a temp
    state dir (LAZY_STATE_DIR override — the same hermetic seam the hook
    pipe-tests use), NOT a mock. This is the orchestrator<->script boundary
    slice: marker present + plan not Complete => ``paused``; marker absent or
    plan Complete => ``terminal``; an unreadable / missing plan file =>
    ``terminal`` (fail-safe — never suppress a legitimate recovery on an
    unreadable signal).

  * WU-2 — the ``--execute-plan-liveness --plan <p> --repo-root <r>`` CLI flag
    on BOTH state scripts (``lazy-state.py`` and ``bug-state.py`` — the
    execute-plan marker is pipeline-agnostic, so the flag is a parity-audited
    coupled-pair surface), invoked via subprocess and asserting the JSON
    verdict + exit 0 (a probe never gates).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

import lazy_core  # type: ignore[import]  # noqa: E402

_LAZY_STATE_PY = _SCRIPTS_DIR / "lazy-state.py"
_BUG_STATE_PY = _SCRIPTS_DIR / "bug-state.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _execute_plan_marker_path(base: Path, repo_root: str) -> Path:
    """Reproduce the SKILL Step-1d recipe:
    ``<base>/execute-plan/<md5(repo_root)[:12]>.json`` (md5 of the repo-root
    STRING, first 12 hex chars — mirrors ``printf '%s' "$root" | md5sum |
    cut -c1-12``)."""
    key = hashlib.md5(repo_root.encode("utf-8")).hexdigest()[:12]
    return base / "execute-plan" / f"{key}.json"


def _write_marker(base: Path, repo_root: str, plan_path: str) -> Path:
    p = _execute_plan_marker_path(base, repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"plan": plan_path, "repo_root": repo_root}) + "\n",
        encoding="utf-8",
    )
    return p


def _write_plan(plan_path: Path, status: str) -> None:
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        "---\n"
        "kind: implementation-plan\n"
        "feature_id: fixture\n"
        f"status: {status}\n"
        "---\n\n"
        "# Fixture plan\n",
        encoding="utf-8",
    )


class _StateDirEnv:
    """Context manager: point LAZY_STATE_DIR at *base* (restored on exit)."""

    def __init__(self, base: Path) -> None:
        self._base = base
        self._prev: str | None = None

    def __enter__(self) -> "_StateDirEnv":
        self._prev = os.environ.get("LAZY_STATE_DIR")
        os.environ["LAZY_STATE_DIR"] = str(self._base)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._prev is None:
            os.environ.pop("LAZY_STATE_DIR", None)
        else:
            os.environ["LAZY_STATE_DIR"] = self._prev


# ---------------------------------------------------------------------------
# WU-1 — the pure helper against real marker files
# ---------------------------------------------------------------------------

class TestExecutePlanLivenessHelper(unittest.TestCase):

    def test_marker_present_status_ready_is_paused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "state"
            repo_root = str(Path(td) / "repo")
            plan = Path(td) / "plan.md"
            _write_plan(plan, "Ready")
            _write_marker(base, repo_root, str(plan))
            with _StateDirEnv(base):
                r = lazy_core.execute_plan_liveness(repo_root, str(plan))
            self.assertTrue(r["marker_present"])
            self.assertEqual(r["plan_status"], "Ready")
            self.assertEqual(r["verdict"], "paused")

    def test_marker_present_status_inprogress_is_paused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "state"
            repo_root = str(Path(td) / "repo")
            plan = Path(td) / "plan.md"
            _write_plan(plan, "In-progress")
            _write_marker(base, repo_root, str(plan))
            with _StateDirEnv(base):
                r = lazy_core.execute_plan_liveness(repo_root, str(plan))
            self.assertEqual(r["verdict"], "paused")
            self.assertEqual(r["plan_status"], "In-progress")

    def test_marker_present_status_complete_is_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "state"
            repo_root = str(Path(td) / "repo")
            plan = Path(td) / "plan.md"
            _write_plan(plan, "Complete")
            _write_marker(base, repo_root, str(plan))
            with _StateDirEnv(base):
                r = lazy_core.execute_plan_liveness(repo_root, str(plan))
            self.assertTrue(r["marker_present"])
            self.assertEqual(r["plan_status"], "Complete")
            self.assertEqual(r["verdict"], "terminal")

    def test_marker_absent_is_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "state"
            base.mkdir(parents=True, exist_ok=True)
            repo_root = str(Path(td) / "repo")
            plan = Path(td) / "plan.md"
            _write_plan(plan, "Ready")
            # No marker written.
            with _StateDirEnv(base):
                r = lazy_core.execute_plan_liveness(repo_root, str(plan))
            self.assertFalse(r["marker_present"])
            self.assertEqual(r["verdict"], "terminal")

    def test_missing_plan_file_is_terminal_failsafe(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "state"
            repo_root = str(Path(td) / "repo")
            plan = Path(td) / "does-not-exist.md"
            _write_marker(base, repo_root, str(plan))
            with _StateDirEnv(base):
                r = lazy_core.execute_plan_liveness(repo_root, str(plan))
            # Marker present, but the plan is unreadable -> fail-safe terminal.
            self.assertTrue(r["marker_present"])
            self.assertEqual(r["verdict"], "terminal")

    def test_result_keys_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "state"
            repo_root = str(Path(td) / "repo")
            plan = Path(td) / "plan.md"
            _write_plan(plan, "Ready")
            _write_marker(base, repo_root, str(plan))
            with _StateDirEnv(base):
                r = lazy_core.execute_plan_liveness(repo_root, str(plan))
            for key in ("marker_present", "plan_status", "verdict"):
                self.assertIn(key, r)


# ---------------------------------------------------------------------------
# WU-2 — the --execute-plan-liveness CLI flag on both state scripts
# ---------------------------------------------------------------------------

def _run_cli(script: Path, repo_root: str, plan: str, base: Path):
    env = dict(os.environ)
    env["LAZY_STATE_DIR"] = str(base)
    return subprocess.run(
        [sys.executable, str(script),
         "--repo-root", repo_root,
         "--execute-plan-liveness", "--plan", plan],
        capture_output=True, text=True, env=env,
    )


class TestExecutePlanLivenessCli(unittest.TestCase):

    def _assert_verdict(self, script: Path) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "state"
            repo_root = str(Path(td) / "repo")
            plan = Path(td) / "plan.md"
            _write_plan(plan, "Ready")
            _write_marker(base, repo_root, str(plan))
            # paused (marker present + not Complete)
            res = _run_cli(script, repo_root, str(plan), base)
            self.assertEqual(res.returncode, 0, res.stderr)
            out = json.loads(res.stdout.strip())
            self.assertEqual(out["verdict"], "paused", res.stdout)
            # terminal (marker removed)
            _execute_plan_marker_path(base, repo_root).unlink()
            res2 = _run_cli(script, repo_root, str(plan), base)
            self.assertEqual(res2.returncode, 0, res2.stderr)
            out2 = json.loads(res2.stdout.strip())
            self.assertEqual(out2["verdict"], "terminal", res2.stdout)

    def test_lazy_state_cli_verdict(self) -> None:
        self._assert_verdict(_LAZY_STATE_PY)

    def test_bug_state_cli_verdict(self) -> None:
        self._assert_verdict(_BUG_STATE_PY)


if __name__ == "__main__":
    unittest.main()
