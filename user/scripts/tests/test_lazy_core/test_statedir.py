#!/usr/bin/env python3
"""
test_statedir.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_statedir.py
Exit 0 on pass, non-zero on any failure. No third-party dependencies.
"""

from __future__ import annotations

import ast
import difflib
import inspect
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# This file lives 2 directories deeper than the original flat
# test_lazy_core.py (user/scripts/tests/test_lazy_core/ vs. user/scripts/),
# so parents[2] is the scripts dir where lazy_core/ actually lives:
# parents[0]=test_lazy_core/, parents[1]=tests/, parents[2]=user/scripts.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))



import _util  # noqa: E402  (module handle — test_clear_state_dir_restores_process_launch_override patches _util._ORIGINAL_LAZY_STATE_DIR, the binding _clear_state_dir actually reads)
from _util import _ModuleMissing, _ORIGINAL_LAZY_STATE_DIR, _STATE_A, _clear_state_dir, _collect_orphaned_test_names, _mrcr_restore_env, _mrcr_with_temp_home, _os_env, _set_state_dir, _write_marker_in  # noqa: E402




# ---------------------------------------------------------------------------
# Attempt the import — RED today, GREEN after extraction.
# ---------------------------------------------------------------------------

_IMPORT_ERROR: Exception | None = None


lazy_core = None



try:
    import lazy_core  # type: ignore[import]
except ImportError as exc:
    _IMPORT_ERROR = exc




# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

_FAILURES: list[str] = []


_PASSES: list[str] = []




def _guard() -> None:
    """Raise _ModuleMissing if lazy_core hasn't been extracted yet.

    Call at the top of every test function so that, while in RED state, each
    test cleanly fails with a consistent reason rather than an AttributeError
    on the None module.
    """
    if _IMPORT_ERROR is not None:
        raise _ModuleMissing(f"lazy_core not importable: {_IMPORT_ERROR}")




def _run_test(name: str, fn) -> None:
    """Run a single test, recording PASS or FAIL."""
    try:
        fn()
        _PASSES.append(name)
        print(f"  PASS  {name}")
    except _ModuleMissing as exc:
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")
    except AssertionError as exc:
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")





def test_update_repeat_counts_debounce_peek_never_advances():
    """peek discipline intact under the debounce: a marked peek probe never
    persists and never advances — the consume-count key is not written under
    peek, and a subsequent real advance starts fresh.

    RED: an impl that persisted the consume-count under peek would mutate state.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        _write_marker_in(state_dir, repo_root)
        _set_state_dir(state_dir)
        try:
            p1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path, peek=True)
            peek_created = sig_path.exists()
            p2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path, peek=True)
            a1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert not peek_created, "peek must NOT create the state file (debounce path included)"
    assert p1["step_repeat_count"] == 1, f"first peek → 1, got {p1!r}"
    assert p2["step_repeat_count"] == 1, f"second peek → 1 (no mutation), got {p2!r}"
    assert a1["step_repeat_count"] == 1, (
        f"first real advance starts at 1 (peeks didn't advance), got {a1!r}"
    )




def test_update_repeat_counts_debounce_legacy_file_without_consume_key():
    """A persisted file written WITHOUT the new consume-count key (a probe that
    predates Phase 2, or a marked write that never recorded one) is tolerated:
    on the next marked probe with no prior consume-count key, the debounce
    cannot prove a re-read, so step_count behaves as before (increments) and the
    new key is added on that write — mirroring the head / step_* migrations.

    RED: an impl that KeyErrors on the missing consume-count key, or that holds
    step_count when it cannot prove a re-read.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        # Hand-write a Phase-10 shape file (step keys present, NO consume key).
        legacy_sig = [
            _STATE_A["feature_id"],
            _STATE_A["sub_skill"],
            _STATE_A["sub_skill_args"],
            _STATE_A["current_step"],
        ]
        legacy_step_sig = [_STATE_A["feature_id"], _STATE_A["current_step"]]
        sig_path.write_text(
            json.dumps({
                "signature": legacy_sig, "count": 1, "head": None,
                "step_signature": legacy_step_sig, "step_count": 1,
            }),
            encoding="utf-8",
        )
        _write_marker_in(state_dir, repo_root)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            persisted = json.loads(sig_path.read_text(encoding="utf-8"))
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 2, (
        f"legacy file with no consume-count key → debounce cannot prove a re-read, "
        f"so step_count increments as before (1 → 2), got {r1!r}"
    )
    assert "consume_count" in persisted, (
        f"the new consume-count key must be added on the next marked write, got {persisted!r}"
    )




def test_f1_repeat_count_debounce_legacy_file_without_consume_key():
    """F1 invariant 5 — Legacy-tolerant (prior file with no consume_count key).

    A state file written without consume_count (a probe predating F1/F2, or an
    unmarked write) cannot prove a re-read, so repeat_count increments as
    before (1 → 2) — same migration tolerance as head / step_* keys.

    RED: an impl that errors on the missing key, or incorrectly holds when it
    cannot prove a re-read.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        # Hand-write a legacy Phase-10 shape (step keys present, NO consume key).
        prior_sig = [
            _STATE_A["feature_id"],
            _STATE_A["sub_skill"],
            _STATE_A["sub_skill_args"],
            _STATE_A["current_step"],
        ]
        prior_step_sig = [_STATE_A["feature_id"], _STATE_A["current_step"]]
        sig_path.write_text(
            json.dumps({
                "signature": prior_sig, "count": 1, "head": None,
                "step_signature": prior_step_sig, "step_count": 1,
            }),
            encoding="utf-8",
        )
        _write_marker_in(state_dir, repo_root)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            persisted = json.loads(sig_path.read_text(encoding="utf-8"))
        finally:
            _clear_state_dir()
    assert r1["repeat_count"] == 2, (
        f"legacy file with no consume_count key → debounce cannot prove a re-read, "
        f"so repeat_count increments as before (1 → 2), got {r1!r}"
    )
    assert "consume_count" in persisted, (
        f"the consume_count key must be added to the persisted record on next "
        f"marked write, got {persisted!r}"
    )




def test_repo_key_present_and_normalization_invariant():
    """repo_key is stable and collapses trailing-slash / separator / drive-case
    variants of the same path to one key; distinct repos → distinct keys."""
    _guard()
    assert hasattr(lazy_core, "repo_key"), "lazy_core.repo_key must exist"
    k = lazy_core.repo_key("/tmp/repoA")
    assert k == lazy_core.repo_key("/tmp/repoA"), "deterministic"
    assert k == lazy_core.repo_key("/tmp/repoA/"), "trailing slash collapses"
    assert k == lazy_core.repo_key("/tmp/repoA\\"), "backslash trailing collapses"
    assert k != lazy_core.repo_key("/tmp/repoB"), "distinct repos → distinct keys"
    assert isinstance(k, str) and len(k) >= 16, "key is a non-trivial hex digest"




def test_claude_state_dir_env_override_is_exact():
    """LAZY_STATE_DIR set → claude_state_dir returns it EXACTLY (no per-repo
    keying), preserving every hermetic test's path semantics byte-for-byte."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.set_active_repo_root("/some/repo")  # must NOT affect override
            got = lazy_core.claude_state_dir()
            assert Path(got) == Path(td), (got, td)
        finally:
            _clear_state_dir()
            lazy_core.set_active_repo_root(None)




def test_claude_state_dir_keyed_per_repo_when_unset():
    """LAZY_STATE_DIR unset → claude_state_dir is ~/.claude/state/<repo_key>/,
    distinct per active repo."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        prior = _mrcr_with_temp_home(td)
        try:
            lazy_core.set_active_repo_root("/tmp/repoA")
            da = lazy_core.claude_state_dir()
            lazy_core.set_active_repo_root("/tmp/repoB")
            db = lazy_core.claude_state_dir()
            assert da != db, (da, db)
            assert da.name == lazy_core.repo_key("/tmp/repoA"), da
            assert db.name == lazy_core.repo_key("/tmp/repoB"), db
            assert da.parent == Path(td) / ".claude" / "state", da
        finally:
            _mrcr_restore_env(prior)




def test_migrate_legacy_state_dir_moves_and_removes():
    """A legacy un-keyed base-dir marker (+ siblings) migrates into the keyed
    subdir for its repo_root and the base copies are removed."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        prior = _mrcr_with_temp_home(td)
        try:
            base = Path(td) / ".claude" / "state"
            base.mkdir(parents=True, exist_ok=True)
            (base / "lazy-run-marker.json").write_text(
                json.dumps({"pipeline": "feature", "repo_root": "/tmp/legacyRepo",
                            "started_at": "2999-01-01T00:00:00Z"}),
                encoding="utf-8")
            (base / "lazy-prompt-registry.json").write_text("{}", encoding="utf-8")
            (base / "lazy-deny-ledger.jsonl").write_text("", encoding="utf-8")
            moved = lazy_core.migrate_legacy_state_dir(base)
            assert moved is True
            keyed = base / lazy_core.repo_key("/tmp/legacyRepo")
            assert (keyed / "lazy-run-marker.json").exists(), "marker migrated"
            assert (keyed / "lazy-prompt-registry.json").exists(), "registry migrated"
            assert not (base / "lazy-run-marker.json").exists(), "base marker removed"
            assert not (base / "lazy-prompt-registry.json").exists(), "base registry removed"
        finally:
            _mrcr_restore_env(prior)




def test_migrate_legacy_unresolvable_repo_root_removes_marker():
    """A legacy marker whose repo_root cannot be resolved is treated as stale and
    removed; no keyed subdir is created."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        prior = _mrcr_with_temp_home(td)
        try:
            base = Path(td) / ".claude" / "state"
            base.mkdir(parents=True, exist_ok=True)
            (base / "lazy-run-marker.json").write_text(
                json.dumps({"pipeline": "feature"}), encoding="utf-8")  # no repo_root
            moved = lazy_core.migrate_legacy_state_dir(base)
            assert moved is False
            assert not (base / "lazy-run-marker.json").exists(), "stale marker removed"
        finally:
            _mrcr_restore_env(prior)




def test_migrate_legacy_noop_when_absent():
    """No legacy marker → migration is a no-op returning False (fresh machine)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        prior = _mrcr_with_temp_home(td)
        try:
            base = Path(td) / ".claude" / "state"
            base.mkdir(parents=True, exist_ok=True)
            assert lazy_core.migrate_legacy_state_dir(base) is False
        finally:
            _mrcr_restore_env(prior)




def test_dead_coverage_guard_detects_orphan_by_name():
    """WU-5(b): negative fixture — feed synthetic module source containing a
    ``def test_orphan`` that is NOT in its registry, and assert the collector
    reports ``test_orphan`` by name (proving the guard would catch a real
    orphan, not vacuously pass)."""
    _guard()
    synthetic_source = (
        "def test_registered_one():\n"
        "    pass\n"
        "\n"
        "def test_orphan():\n"  # defined but NOT registered below
        "    pass\n"
        "\n"
        '_TESTS = [("test_registered_one", test_registered_one)]\n'
    )
    registered = {"test_registered_one"}
    orphans = _collect_orphaned_test_names(synthetic_source, registered)
    assert orphans == ["test_orphan"], (
        f"the guard must report the unregistered test_orphan by name; got {orphans}"
    )




# ---------------------------------------------------------------------------
# byref-dispatch-undercounts-forward-cycles Phase 1 — WU-3 (the WIRING regression).
# ---------------------------------------------------------------------------
#
# The helper advance_forward_cycle is already characterized above (state-change
# advance, idempotence, Theory-1b). WU-3 covers the WIRING the bug is about: the
# real-skill `--repeat-count` dispatch-bound probe path must advance forward_cycles
# via the consume-INDEPENDENT advance_forward_cycle, so a by-reference dispatch that
# does NOT bump the consume census (the FROZEN-census / Theory-1b case) still counts
# toward the forward budget. Pre-WU-1/WU-2 the `--repeat-count` handler called ONLY
# advance_run_counters, which gates on a consume rise → forward_cycles stays 0 on a
# frozen census → the max-cycles cap can never fire (the bug). These tests drive the
# ACTUAL CLI handler (not the helper directly) over a temp repo so a revert of the
# wiring re-RED-s them.


def _build_repeat_count_real_skill_repo(root: "Path") -> None:
    """Materialize a minimal feature repo whose computed state is a REAL skill
    (execute-plan) — the by-reference dispatch path the bug is about.

    Mirrors lazy-state.py's `mid-implementation` smoke fixture: a single queued
    feature past research with an In-progress PHASES.md + a plan present → the
    state machine routes to `/execute-plan` (a real, non-`__` sub_skill).
    """
    features = root / "docs" / "features"
    features.mkdir(parents=True, exist_ok=True)
    (features / "queue.json").write_text(json.dumps({
        "queue": [
            {"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}
        ]
    }), encoding="utf-8")
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-c"
    fdir.mkdir()
    (fdir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n", encoding="utf-8")
    (fdir / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
    (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (fdir / "PHASES.md").write_text(
        "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n",
        encoding="utf-8")
    (fdir / "plans").mkdir()
    (fdir / "plans" / "all-phases-c.md").write_text("# Plan\n", encoding="utf-8")




def test_repeat_count_real_skill_frozen_census_advances_forward(
    _script_name: str = "lazy-state.py",
) -> None:
    """A real-skill frozen-census cycle advances forward_cycles to 1 — but the
    increment now happens at the DISPATCH BRACKET, not the probe.

    BEHAVIOR MOVED (cycle-budget-counters-double-count-on-probes-and-inject-hook):
    the budget advance used to fire on the `--repeat-count` probe path
    (advance_forward_cycle keyed on the state tuple / consume census). That coupled
    the budget to EVERY probe — inspection probes AND the per-turn inject hook —
    inflating forward_cycles with no dispatch. The advance is now decoupled: the
    probe is budget-NEUTRAL, and a completed `--cycle-begin --kind real / --cycle-end`
    bracket (one bracket == one real Agent dispatch) is the sole authority.

    This test retains its name + gate identity but asserts the NEW contract:
      (2) a real-skill `--repeat-count` probe leaves forward_cycles at 0 (decoupled);
      (3) closing the real bracket advances forward_cycles to 1 (+ per-feature bump);
      (4) a further probe does NOT advance again (still bracket-gated).
    A revert that re-couples the budget to the probe re-RED-s step (2).
    """
    _guard()
    script = _SCRIPTS_DIR / _script_name
    assert script.exists(), f"{_script_name} missing"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        state_dir = Path(td) / "state"
        state_dir.mkdir(parents=True)
        _build_repeat_count_real_skill_repo(root)

        # LAZY_ORCHESTRATOR=1 immunizes the --cycle-begin/--cycle-end bracket
        # against the cycle-containment guard; a stale inherited LAZY_CYCLE_SUBAGENT
        # is stripped so the isolated bracket is not falsely refused.
        env = {k: v for k, v in _os_env.environ.items()
               if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
        env["LAZY_STATE_DIR"] = str(state_dir)
        env["LAZY_ORCHESTRATOR"] = "1"

        def run(extra):
            return subprocess.run(
                [sys.executable, str(script), "--repo-root", str(root)] + extra,
                capture_output=True, text=True, env=env,
            )

        # 1) --run-start writes the marker with forward_cycles == 0 (no consume yet).
        rs = run(["--run-start", "--max-cycles", "25"])
        assert rs.returncode == 0, f"--run-start failed: {rs.stderr[:400]!r}"
        marker_path = state_dir / lazy_core._MARKER_FILENAME
        assert marker_path.exists(), "--run-start must write the run marker"
        m0 = json.loads(marker_path.read_text(encoding="utf-8"))
        assert m0.get("forward_cycles", 0) == 0, f"marker should start at 0: {m0!r}"

        # 2) --repeat-count over a REAL-skill state — the probe is now BUDGET-NEUTRAL.
        #    Pre-fix this advanced forward_cycles to 1 (the double-count bug); the
        #    budget is decoupled from the probe path, so it must stay 0.
        rc = run(["--repeat-count"])
        assert rc.returncode == 0, f"--repeat-count failed: {rc.stderr[:400]!r}"
        probe = json.loads(rc.stdout)
        # Sanity: the computed state really is the real (non-pseudo) execute-plan
        # skill — otherwise this test would not be exercising the by-ref path.
        assert probe.get("sub_skill") == "execute-plan", (
            f"fixture must route to the real execute-plan skill, got "
            f"{probe.get('sub_skill')!r} (state={probe!r})"
        )
        feature_id = probe.get("feature_id")
        assert feature_id, f"probe must carry a feature_id, got {probe!r}"
        m_probe = json.loads(marker_path.read_text(encoding="utf-8"))
        assert m_probe.get("forward_cycles", 0) == 0, (
            f"a real-skill --repeat-count PROBE must NOT advance the forward budget "
            f"(the advance moved to the dispatch bracket); got forward_cycles="
            f"{m_probe.get('forward_cycles')!r} (marker={m_probe!r})"
        )

        # 3) A real dispatch BRACKET advances forward_cycles to 1 (+ per-feature bump)
        #    at --cycle-end — the new budget authority.
        cb = run(["--cycle-begin", "--kind", "real", "--feature-id", str(feature_id),
                  "--nonce", "nonce-real-frozen", "--sub-skill", "execute-plan"])
        assert cb.returncode == 0, f"--cycle-begin failed: {cb.stderr[:400]!r}"
        ce = run(["--cycle-end"])
        assert ce.returncode == 0, f"--cycle-end failed: {ce.stderr[:400]!r}"
        m1 = json.loads(marker_path.read_text(encoding="utf-8"))
        assert m1.get("forward_cycles") == 1, (
            f"a closed real bracket must advance forward_cycles to 1; got "
            f"forward_cycles={m1.get('forward_cycles')!r} (marker={m1!r})"
        )
        assert m1.get("per_feature_forward_cycles", {}).get(str(feature_id)) == 1, (
            f"the real bracket must bump per_feature_forward_cycles[{feature_id!r}] "
            f"to 1; got {m1.get('per_feature_forward_cycles')!r}"
        )

        # 4) A further --repeat-count probe (no new bracket) does NOT advance again —
        #    the budget stays bracket-gated, never probe-driven.
        rc2 = run(["--repeat-count"])
        assert rc2.returncode == 0, f"second --repeat-count failed: {rc2.stderr[:400]!r}"
        m2 = json.loads(marker_path.read_text(encoding="utf-8"))
        assert m2.get("forward_cycles") == 1, (
            f"a probe after the bracket must NOT advance the budget again "
            f"(bracket-gated, not probe-driven), got forward_cycles="
            f"{m2.get('forward_cycles')!r}"
        )




def test_repeat_count_real_skill_frozen_census_advances_forward_bug_state() -> None:
    """WU-2 parity, RECONCILED to the bracket-coupled budget: bug-state.py's
    `--repeat-count` probe is BUDGET-NEUTRAL (identical to the feature pipeline),
    and a real dispatch BRACKET advances forward_cycles.

    BEHAVIOR MOVED (cycle-budget-counters-double-count-on-probes-and-inject-hook):
    the coupled-pair advance that used to fire in bug-state.py's `if
    args.repeat_count:` block was REMOVED; the parity claim is now that bug-state.py
    carries the identical advance_cycle_bracket_counter call at `--cycle-end` (kept
    in lockstep with lazy-state.py by lazy_parity_audit.py). This test retains its
    name + gate identity but asserts the NEW contract: the probe leaves
    forward_cycles at 0, and closing a `--kind real` bracket advances it to 1.
    """
    _guard()
    script = _SCRIPTS_DIR / "bug-state.py"
    assert script.exists(), "bug-state.py missing"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        state_dir = Path(td) / "state"
        state_dir.mkdir(parents=True)
        # A bug at the execute-plan step (real skill) under docs/bugs/.
        bugs = root / "docs" / "bugs"
        bugs.mkdir(parents=True, exist_ok=True)
        (bugs / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-c", "name": "Bug C", "spec_dir": "bug-c",
                 "severity": "P2"}
            ]
        }), encoding="utf-8")
        bdir = bugs / "bug-c"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Concluded\n\n**Depends on:** (none)\n",
            encoding="utf-8")
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] Fix the thing\n- [ ] Tests\n",
            encoding="utf-8")
        (bdir / "plans").mkdir()
        (bdir / "plans" / "all-phases-bug-c.md").write_text("# Plan\n", encoding="utf-8")

        # LAZY_ORCHESTRATOR=1 immunizes the bracket against the containment guard;
        # a stale inherited LAZY_CYCLE_SUBAGENT is stripped.
        env = {k: v for k, v in _os_env.environ.items()
               if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
        env["LAZY_STATE_DIR"] = str(state_dir)
        env["LAZY_ORCHESTRATOR"] = "1"

        def run(extra):
            return subprocess.run(
                [sys.executable, str(script), "--repo-root", str(root)] + extra,
                capture_output=True, text=True, env=env,
            )

        rs = run(["--run-start", "--max-cycles", "25"])
        assert rs.returncode == 0, f"bug-state --run-start failed: {rs.stderr[:400]!r}"
        marker_path = state_dir / lazy_core._MARKER_FILENAME
        assert marker_path.exists(), "bug-state --run-start must write the run marker"

        # The probe is budget-neutral regardless of the route it computes.
        rc = run(["--repeat-count"])
        assert rc.returncode == 0, f"bug-state --repeat-count failed: {rc.stderr[:400]!r}"
        m_probe = json.loads(marker_path.read_text(encoding="utf-8"))
        assert m_probe.get("forward_cycles", 0) == 0, (
            f"a bug-state --repeat-count PROBE must NOT advance the forward budget "
            f"(decoupled from the probe path); got forward_cycles="
            f"{m_probe.get('forward_cycles')!r}"
        )

        # A real dispatch bracket advances forward_cycles to 1 (+ per-feature bump)
        # at --cycle-end — the coupled-pair mirror of the feature-pipeline authority.
        cb = run(["--cycle-begin", "--kind", "real", "--bug-id", "bug-c",
                  "--nonce", "nonce-bug-frozen", "--sub-skill", "execute-plan"])
        assert cb.returncode == 0, f"bug-state --cycle-begin failed: {cb.stderr[:400]!r}"
        ce = run(["--cycle-end"])
        assert ce.returncode == 0, f"bug-state --cycle-end failed: {ce.stderr[:400]!r}"
        m1 = json.loads(marker_path.read_text(encoding="utf-8"))
        assert m1.get("forward_cycles") == 1, (
            f"a closed bug real bracket must advance forward_cycles to 1 (parity "
            f"with the feature pipeline); got forward_cycles={m1.get('forward_cycles')!r}"
        )
        assert m1.get("per_feature_forward_cycles", {}).get("bug-c") == 1, (
            f"the bug real bracket must bump per_feature_forward_cycles[bug-c] to 1; "
            f"got {m1.get('per_feature_forward_cycles')!r}"
        )




# ---------------------------------------------------------------------------
# incident-auto-capture Phase 1 (D2) — append_hook_event: the shared fail-open
# hook-events.jsonl appender (Python form). Contract mirror of
# append_friction_ledger_entry: swallow-everything, never raise, never change
# the caller's behavior.
# ---------------------------------------------------------------------------

def test_append_hook_event_shape_and_fail_open():
    """incident-auto-capture WU-1.1: append_hook_event appends ONE parseable
    JSONL line {ts, kind, hook, repo_root, signature, detail} to
    hook-events.jsonl in the state dir; detail is truncated to the ledger head
    cap; and it FAILS OPEN (returns False, never raises) when the events path
    is unwritable (a directory squatting on the filename)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            ok = lazy_core.append_hook_event(
                "deny", "long-build-ownership-guard",
                "LONG-BUILD-OWNERSHIP-TAKEOVER",
                "cargo build --release redirected",
                repo_root="/repo/a",
                now=123.0,
            )
            assert ok is True
            events_path = Path(td) / "hook-events.jsonl"
            assert events_path.exists(), "hook-events.jsonl not created"
            lines = events_path.read_text(encoding="utf-8").splitlines()
            assert len(lines) == 1, lines
            e = json.loads(lines[0])
            assert e["ts"] == 123.0, e
            assert e["kind"] == "deny", e
            assert e["hook"] == "long-build-ownership-guard", e
            assert e["repo_root"] == "/repo/a", e
            assert e["signature"] == "LONG-BUILD-OWNERSHIP-TAKEOVER", e
            assert "redirected" in e["detail"], e

            # Second append → append-only (2 lines, first untouched).
            assert lazy_core.append_hook_event(
                "error", "lazy-dispatch-guard", "", "boom", now=124.0,
            ) is True
            lines = events_path.read_text(encoding="utf-8").splitlines()
            assert len(lines) == 2, lines
            assert json.loads(lines[1])["kind"] == "error"

            # Truncation: an over-long detail is capped (never a multi-KB line).
            lazy_core.append_hook_event("deny", "h", "s", "x" * 5000, now=125.0)
            last = json.loads(
                events_path.read_text(encoding="utf-8").splitlines()[-1]
            )
            assert len(last["detail"]) <= 500, len(last["detail"])
        finally:
            _clear_state_dir()

    # Fail-open: events filename occupied by a DIRECTORY → open() fails →
    # returns False, raises nothing, caller unaffected.
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            (Path(td) / "hook-events.jsonl").mkdir()
            ok = lazy_core.append_hook_event("deny", "h", "s", "d")
            assert ok is False
        finally:
            _clear_state_dir()




def test_repo_key_lane_worktree_distinct():
    """Per-worktree isolation primitive (D2-A): the main root and each sibling
    `<repo>-lanes/wt-NN` worktree resolve to pairwise-DISTINCT repo keys, so
    every lane gets its own keyed state dir (marker/registry/ledger) for free."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        main_root = Path(td) / "repo"
        lanes_dir = Path(td) / "repo-lanes"
        wt0 = lanes_dir / "wt-00"
        wt1 = lanes_dir / "wt-01"
        for p in (main_root, wt0, wt1):
            p.mkdir(parents=True)
        keys = {
            lazy_core.repo_key(str(main_root)),
            lazy_core.repo_key(str(wt0)),
            lazy_core.repo_key(str(wt1)),
        }
        assert len(keys) == 3, "main root + each lane must key distinct state dirs"




# ---------------------------------------------------------------------------
# Regression: _clear_state_dir() must RESTORE the process-launch LAZY_STATE_DIR
# override, not unconditionally strip it (clear-state-dir-teardown-strips-
# lazy-state-dir-override). The documented mitigation for running the full suite
# DURING a live lazy cycle is a process-level LAZY_STATE_DIR=<temp>; an
# unconditional pop in an early cycle-marker test's teardown would strip that
# override mid-suite and route later guard reads at the REAL state dir (false
# fail on the live cycle marker).
# ---------------------------------------------------------------------------

def test_clear_state_dir_restores_process_launch_override():
    """_clear_state_dir() restores the process-launch LAZY_STATE_DIR value when
    one was present at import, and pops (legacy behavior) when none was."""
    _guard()
    live = _os_env.environ.get("LAZY_STATE_DIR")   # whatever is live right now
    saved_original = _util._ORIGINAL_LAZY_STATE_DIR
    try:
        # Case 1: an operator override was present at process launch -> RESTORE.
        _util._ORIGINAL_LAZY_STATE_DIR = "/operator/override/state"
        _set_state_dir(Path("/some/per-test/temp"))   # a test set its own temp
        _clear_state_dir()                            # teardown
        assert _os_env.environ.get("LAZY_STATE_DIR") == "/operator/override/state", (
            "teardown must RESTORE the process-launch override, not strip it; "
            f"got {_os_env.environ.get('LAZY_STATE_DIR')!r}"
        )
        # Case 2: no override at launch -> pop (byte-identical legacy behavior).
        _util._ORIGINAL_LAZY_STATE_DIR = None
        _set_state_dir(Path("/some/per-test/temp2"))
        _clear_state_dir()
        assert "LAZY_STATE_DIR" not in _os_env.environ, (
            "with no process-launch override, teardown must pop as before; "
            f"got {_os_env.environ.get('LAZY_STATE_DIR')!r}"
        )
    finally:
        _util._ORIGINAL_LAZY_STATE_DIR = saved_original
        if live is None:
            _os_env.environ.pop("LAZY_STATE_DIR", None)
        else:
            _os_env.environ["LAZY_STATE_DIR"] = live




def test_hook_surface_imports_without_monolith():
    """D4 mechanical pin (lazy-core-package-decomposition Phase 2 WU-5;
    STRENGTHENED at Phase 5 WU-4 when `_monolith.py` was deleted): the hook
    fast path — touching `lazy_core.claude_state_dir`,
    `lazy_core._load_registry`, and `lazy_core.append_hook_event` through the
    facade — must load NOTHING beyond the facade + `_ctx` + `statedir`
    (stdlib-only modules). This is the realized D4 hook-latency cut; a future
    edit that makes `statedir` (or the facade) import a heavy seam module
    turns this RED.

    Fresh subprocess so this session's own imports cannot contaminate
    `sys.modules`.
    """
    _guard()
    probe = (
        "import sys; sys.path.insert(0, {scripts!r}); import lazy_core; "
        "lazy_core.claude_state_dir; lazy_core._load_registry; "
        "lazy_core.append_hook_event; "
        "loaded = sorted(m for m in sys.modules if m.startswith('lazy_core')); "
        "allowed = {{'lazy_core', 'lazy_core._ctx', 'lazy_core.statedir'}}; "
        "extra = [m for m in loaded if m not in allowed]; "
        "print(','.join(extra)); "
        "sys.exit(1 if extra else 0)"
    ).format(scripts=str(_SCRIPTS_DIR))
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "hook-surface facade touch loaded modules beyond "
        "{lazy_core, _ctx, statedir}: "
        f"{result.stdout.strip()!r}; stderr: {result.stderr[-500:]}"
    )


_TESTS = [
    ("test_update_repeat_counts_debounce_peek_never_advances", test_update_repeat_counts_debounce_peek_never_advances),
    ("test_update_repeat_counts_debounce_legacy_file_without_consume_key", test_update_repeat_counts_debounce_legacy_file_without_consume_key),
    ("test_f1_repeat_count_debounce_legacy_file_without_consume_key", test_f1_repeat_count_debounce_legacy_file_without_consume_key),
    ("test_repo_key_present_and_normalization_invariant", test_repo_key_present_and_normalization_invariant),
    ("test_claude_state_dir_env_override_is_exact", test_claude_state_dir_env_override_is_exact),
    ("test_claude_state_dir_keyed_per_repo_when_unset", test_claude_state_dir_keyed_per_repo_when_unset),
    ("test_migrate_legacy_state_dir_moves_and_removes", test_migrate_legacy_state_dir_moves_and_removes),
    ("test_migrate_legacy_unresolvable_repo_root_removes_marker", test_migrate_legacy_unresolvable_repo_root_removes_marker),
    ("test_migrate_legacy_noop_when_absent", test_migrate_legacy_noop_when_absent),
    ("test_dead_coverage_guard_detects_orphan_by_name", test_dead_coverage_guard_detects_orphan_by_name),
    ("test_repeat_count_real_skill_frozen_census_advances_forward_bug_state", test_repeat_count_real_skill_frozen_census_advances_forward_bug_state),
    ("test_append_hook_event_shape_and_fail_open", test_append_hook_event_shape_and_fail_open),
    ("test_repo_key_lane_worktree_distinct", test_repo_key_lane_worktree_distinct),
    ("test_clear_state_dir_restores_process_launch_override", test_clear_state_dir_restores_process_launch_override),
    ("test_hook_surface_imports_without_monolith", test_hook_surface_imports_without_monolith),
]





def main() -> int:
    print("=" * 60)
    print("test_lazy_core.py — characterization tests")
    print("=" * 60)

    if _IMPORT_ERROR is not None:
        print(f"\nREQUIRED MODULE MISSING: {_IMPORT_ERROR}")
        print("This is the expected RED state — lazy_core has not been extracted yet.\n")

    print()
    for name, fn in _TESTS:
        _run_test(name, fn)

    total = len(_TESTS)
    passed = len(_PASSES)
    failed = len(_FAILURES)

    print()
    print("=" * 60)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if _FAILURES:
        print("\nFailed tests:")
        for f in _FAILURES:
            print(f"  - {f}")
        print()
        if _IMPORT_ERROR is not None:
            print("FIX: extract lazy_core.py from lazy-state.py and re-run.")
        return 1
    print("\nAll tests passed.")
    return 0



if __name__ == "__main__":
    sys.exit(main())
