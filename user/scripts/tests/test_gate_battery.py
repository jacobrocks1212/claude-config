#!/usr/bin/env python3
"""
test_gate_battery.py — TDD RED tests for gate-battery.py (generalized-build-test-runner-skills,
Phase 1, WU-2).

`user/scripts/gate-battery.py` DOES NOT EXIST YET at the time this file is written — these tests
are deliberately RED. A separate implementation agent makes them green.

The banner grammar under test is quoted VERBATIM from the SSOT component,
``user/skills/_components/runner-outcome-contract.md`` (Leg 1, the ``gate-battery:`` instance):

    gate-battery: run=<id> op=battery RESULT=<PASS|FAIL> cmds=<n> failed=<k> (elapsed=<s>s) [-> first failing gate: <id>]

Locked contract pinned here (see the WU-2 task brief for the full decision list):
  1. CLI: ``python gate-battery.py [--repo-root PATH] [--state-root PATH]``. Every test passes an
     explicit tmp ``--state-root`` — the real ``~/.claude/state`` is never touched.
  2. Repo toplevel = ``git rev-parse --show-toplevel`` from ``--repo-root``; on failure (not a git
     repo) ``--repo-root`` itself is the toplevel — so fixture repos are plain tmp dirs, no
     ``git init`` needed.
  3. Manifest: ``<toplevel>/.claude/skill-config/gate-battery.json``,
     ``{"version": 1, "gates": [{"id", "cmd", "cwd"?}]}``. String ``cmd`` -> ``shlex.split()``;
     list ``cmd`` -> argv verbatim; never ``shell=True``.
  4. No manifest / malformed JSON -> exit 2, one-line reason, ZERO files/dirs under the state root.
  5. Gates run sequentially; a failing gate does not stop the battery (first failing id recorded).
  6. Banner is the LAST stdout line; all-green -> RESULT=PASS/failed=0/no ``->`` suffix/exit 0;
     any failure -> RESULT=FAIL/failed=<k>/``-> first failing gate: <id>``/exit 1.
  7. Results file at ``<state-root>/gate-battery/<repo-key>/results/<run-id>.json`` with at least
     ``run_id``, ``banner``, ``exit_code``, ``gates: [{id, exit_code, duration_seconds}]``. Run-id
     shape: ``\\d{8}-[0-9a-f]{4}`` (UTC yyyymmdd + 4 hex).
  8. Repo-key parity: the runner keeps a PRIVATE ``_repo_key()`` copy of the canonical convention;
     this test file imports the CANONICAL ``lazy_core.statedir.repo_key`` (never asserts the
     runner imports lazy_core — it must stay stdlib-only) and asserts the results dir the runner
     actually used matches ``repo_key(fixture_repo)``.
  9. State-root unwritable (state-root path is an existing regular FILE, so ``mkdir`` under it
     fails cross-platform): gates still run, the banner is still the last stdout line and contains
     the substring ``await unavailable``, exit code still reflects the gates (0 if green).
 10. Cloud-compatibility mechanical proxy: the runner source text must contain neither the token
     ``powershell`` nor ``pwsh`` (case-insensitive) ANYWHERE — this is the SPEC's cloud-compat
     validation row's deterministic stand-in, not a full behavioral test.

``--await`` is explicitly OUT of scope here (a later work unit, WU-3, owns those tests).

Run: python -m pytest user/scripts/tests/test_gate_battery.py -q
Stdlib + pytest only. Every test is hermetic: tmp_path fixture repos + tmp_path fixture state
roots; nothing here ever touches the real ``~/.claude/state`` or the real repo manifest.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# user/scripts/ is two directories up from this file (tests/test_gate_battery.py ->
# tests/ -> user/scripts/) — add it to sys.path so `import lazy_core` resolves, mirroring
# the sys.path bootstrap in tests/test_lazy_core/conftest.py (parents[2] there because that
# conftest lives one directory deeper, under test_lazy_core/).
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lazy_core.statedir import repo_key  # noqa: E402  (import used ONLY in this test file)

RUNNER_PATH = Path(__file__).resolve().parents[1] / "gate-battery.py"

GREEN_CMD = [sys.executable, "-c", "pass"]
RED_CMD = [sys.executable, "-c", "import sys; sys.exit(1)"]

RUN_ID_RE = r"\d{8}-[0-9a-f]{4}"
BANNER_PASS_RE = re.compile(
    r"^gate-battery: run=" + RUN_ID_RE + r" op=battery RESULT=PASS cmds=(\d+) failed=0 \(elapsed=\d+s\)$"
)
BANNER_FAIL_RE = re.compile(
    r"^gate-battery: run=" + RUN_ID_RE
    + r" op=battery RESULT=FAIL cmds=(\d+) failed=(\d+) \(elapsed=\d+s\) -> first failing gate: (?P<gate_id>[\w.-]+)$"
)
RUN_ID_EXTRACT_RE = re.compile(r"run=(" + RUN_ID_RE + r")")


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_manifest(repo_root: Path, gates: list) -> Path:
    cfg_dir = repo_root / ".claude" / "skill-config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cfg_dir / "gate-battery.json"
    manifest_path.write_text(json.dumps({"version": 1, "gates": gates}), encoding="utf-8")
    return manifest_path


def _gate(gate_id, cmd, cwd=None):
    g = {"id": gate_id, "cmd": cmd}
    if cwd is not None:
        g["cwd"] = cwd
    return g


def _run_battery(repo_root: Path, state_root: Path, extra_args=None):
    cmd = [
        sys.executable,
        str(RUNNER_PATH),
        "--repo-root",
        str(repo_root),
        "--state-root",
        str(state_root),
    ]
    if extra_args:
        cmd += extra_args
    return subprocess.run(cmd, capture_output=True, text=True)


def _last_stdout_line(result) -> str:
    lines = result.stdout.strip("\n").splitlines()
    assert lines, f"expected at least one stdout line; got stdout={result.stdout!r} stderr={result.stderr!r}"
    return lines[-1]


def _results_dir(state_root: Path, repo_root: Path) -> Path:
    return state_root / "gate-battery" / repo_key(str(repo_root)) / "results"


# ---------------------------------------------------------------------------
# Manifest-absence / malformed-manifest refusal
# ---------------------------------------------------------------------------

def test_manifest_less_repo_exits_2_with_one_line_reason_and_zero_state(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir()

    result = _run_battery(repo, state_root)

    assert result.returncode == 2
    combined = (result.stdout + result.stderr).lower()
    assert "manifest" in combined, (
        f"exit-2 reason must mention the manifest path/word; got stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert list(state_root.iterdir()) == [], "no manifest -> zero files/dirs under the state root"


def test_malformed_manifest_json_exits_2_naming_the_defect_and_zero_state(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg_dir = repo / ".claude" / "skill-config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "gate-battery.json").write_text("{not valid json", encoding="utf-8")
    state_root = tmp_path / "state"
    state_root.mkdir()

    result = _run_battery(repo, state_root)

    assert result.returncode == 2
    combined = (result.stdout + result.stderr).lower()
    assert any(word in combined for word in ("json", "malformed", "invalid")), (
        f"exit-2 reason must name the JSON defect; got stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert list(state_root.iterdir()) == [], "malformed manifest -> zero files/dirs under the state root"


# ---------------------------------------------------------------------------
# All-green / one-failing-gate banner shape
# ---------------------------------------------------------------------------

def test_all_green_battery_banner_matches_exact_pass_grammar(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_manifest(repo, [_gate("gate-a", GREEN_CMD), _gate("gate-b", GREEN_CMD)])
    state_root = tmp_path / "state"
    state_root.mkdir()

    result = _run_battery(repo, state_root)

    last_line = _last_stdout_line(result)
    m = BANNER_PASS_RE.fullmatch(last_line)
    assert m, f"last stdout line did not match the PASS grammar: {last_line!r}"
    assert m.group(1) == "2"
    assert result.returncode == 0


def test_one_forced_red_gate_reports_fail_with_its_id_and_exit_1(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_manifest(
        repo,
        [_gate("gate-green", GREEN_CMD), _gate("gate-red", RED_CMD)],
    )
    state_root = tmp_path / "state"
    state_root.mkdir()

    result = _run_battery(repo, state_root)

    last_line = _last_stdout_line(result)
    m = BANNER_FAIL_RE.fullmatch(last_line)
    assert m, f"last stdout line did not match the FAIL grammar: {last_line!r}"
    assert m.group(2) == "1"
    assert m.group("gate_id") == "gate-red"
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# Sequential execution — a failing gate never stops the battery
# ---------------------------------------------------------------------------

def test_failing_gate_does_not_stop_the_battery_both_gates_run(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_manifest(
        repo,
        [_gate("gate-red", RED_CMD), _gate("gate-green", GREEN_CMD)],
    )
    state_root = tmp_path / "state"
    state_root.mkdir()

    result = _run_battery(repo, state_root)

    last_line = _last_stdout_line(result)
    run_id_match = RUN_ID_EXTRACT_RE.search(last_line)
    assert run_id_match, f"could not parse run id out of banner: {last_line!r}"
    run_id = run_id_match.group(1)

    results_path = _results_dir(state_root, repo) / f"{run_id}.json"
    assert results_path.is_file(), f"expected results file at {results_path}"
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    gate_ids = {g["id"] for g in payload["gates"]}
    assert gate_ids == {"gate-red", "gate-green"}, "BOTH gates must have run despite the red one"


# ---------------------------------------------------------------------------
# Results file shape + repo-key parity
# ---------------------------------------------------------------------------

def test_results_file_shape_and_repo_key_parity_with_lazy_core(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_manifest(repo, [_gate("gate-a", GREEN_CMD), _gate("gate-b", GREEN_CMD)])
    state_root = tmp_path / "state"
    state_root.mkdir()

    result = _run_battery(repo, state_root)
    last_line = _last_stdout_line(result)
    run_id_match = RUN_ID_EXTRACT_RE.search(last_line)
    assert run_id_match, f"could not parse run id out of banner: {last_line!r}"
    run_id = run_id_match.group(1)

    expected_results_dir = state_root / "gate-battery" / repo_key(str(repo)) / "results"
    results_path = expected_results_dir / f"{run_id}.json"
    assert results_path.is_file(), (
        f"results file not found at the canonical repo_key-derived path {results_path}"
    )

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == run_id
    assert payload["banner"] == last_line
    assert payload["exit_code"] == result.returncode
    assert isinstance(payload["gates"], list) and len(payload["gates"]) == 2
    for gate_entry in payload["gates"]:
        assert set(("id", "exit_code", "duration_seconds")).issubset(gate_entry.keys())
        assert isinstance(gate_entry["duration_seconds"], (int, float))


# ---------------------------------------------------------------------------
# String-form cmd (shlex.split) support
# ---------------------------------------------------------------------------

def test_string_form_cmd_is_shlex_split_and_executed(tmp_path):
    if shutil.which("python") is None:
        pytest.skip("no bare 'python' resolvable on PATH — string-form fixture needs a "
                    "space/backslash-free argv[0]; see WU-2 task brief caveat")

    repo = tmp_path / "repo"
    repo.mkdir()
    _write_manifest(
        repo,
        [_gate("gate-string", "python -c pass"), _gate("gate-list", GREEN_CMD)],
    )
    state_root = tmp_path / "state"
    state_root.mkdir()

    result = _run_battery(repo, state_root)

    last_line = _last_stdout_line(result)
    m = BANNER_PASS_RE.fullmatch(last_line)
    assert m, f"string-form cmd battery did not report all-green PASS: {last_line!r}"
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Per-gate cwd honored
# ---------------------------------------------------------------------------

def test_gate_cwd_is_honored(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sub").mkdir()
    cwd_check_cmd = [
        sys.executable,
        "-c",
        "import os, sys; sys.exit(0 if os.path.basename(os.getcwd()) == 'sub' else 1)",
    ]
    _write_manifest(repo, [_gate("gate-cwd", cwd_check_cmd, cwd="sub")])
    state_root = tmp_path / "state"
    state_root.mkdir()

    result = _run_battery(repo, state_root)

    last_line = _last_stdout_line(result)
    m = BANNER_PASS_RE.fullmatch(last_line)
    assert m, f"gate cwd was not honored (expected PASS): {last_line!r}"
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# State-root unwritable degrades gracefully
# ---------------------------------------------------------------------------

def test_state_root_unwritable_still_prints_banner_last_and_reports_await_unavailable(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_manifest(repo, [_gate("gate-a", GREEN_CMD), _gate("gate-b", GREEN_CMD)])

    # A pre-existing regular FILE at the --state-root path makes any mkdir-under-it fail
    # on every OS — the cross-platform trick to force unwritability.
    unwritable_state_root = tmp_path / "state_root_is_a_file"
    unwritable_state_root.write_text("not a directory", encoding="utf-8")

    result = _run_battery(repo, unwritable_state_root)

    last_line = _last_stdout_line(result)
    assert last_line.startswith("gate-battery:"), f"banner still expected as last line: {last_line!r}"
    assert "await unavailable" in last_line, (
        f"state-root-unwritable banner must contain 'await unavailable': {last_line!r}"
    )
    assert result.returncode == 0, "gates were all green; exit code must still reflect that"


# ---------------------------------------------------------------------------
# Cloud-compatibility mechanical proxy — no powershell/pwsh tokens in source
# ---------------------------------------------------------------------------

def test_runner_source_contains_no_powershell_or_pwsh_tokens():
    """Mechanical proxy for the SPEC's cloud-compatibility validation row: the stdlib-Python
    battery runner must never shell out to PowerShell/pwsh (workstation-only tooling) — that
    would silently break it on a cloud/non-Windows host. This is a source-text scan, not a
    behavioral guarantee."""
    source_text = RUNNER_PATH.read_text(encoding="utf-8")
    lowered = source_text.lower()
    assert "powershell" not in lowered, "gate-battery.py source must not mention 'powershell'"
    assert "pwsh" not in lowered, "gate-battery.py source must not mention 'pwsh'"


# ---------------------------------------------------------------------------
# --await (WU-3) — TDD RED: gate-battery.py has no --await flag yet, so every
# test below fails against argparse's own "unrecognized arguments" exit 2.
# Locked contract (SPEC D1 item 2; mirrors user/scripts/build-queue-await.ps1):
#   - result present  -> re-emit the recorded run's banner VERBATIM as the LAST
#     stdout line; process exit = the recorded run's own exit_code.
#   - result absent (in-flight / unknown run-id / missing results dir / unknown
#     repo key) -> exit 124. 124 is NEVER success (no "RESULT=PASS" anywhere).
#   - result file present but corrupted/truncated JSON -> exit 125.
#   - --timeout-seconds (optional, default 0 = single-shot): with 0 and no
#     result, returns 124 immediately.
#   - --await must NOT require a manifest (no .claude/skill-config/ needed).
# ---------------------------------------------------------------------------

def _await_battery(repo_root: Path, state_root: Path, run_id: str, extra_args=None):
    cmd = [
        sys.executable,
        str(RUNNER_PATH),
        "--await",
        run_id,
        "--repo-root",
        str(repo_root),
        "--state-root",
        str(state_root),
    ]
    if extra_args:
        cmd += extra_args
    return subprocess.run(cmd, capture_output=True, text=True)


def _write_results_file(state_root: Path, repo_root: Path, run_id: str, payload: dict) -> Path:
    results_dir = _results_dir(state_root, repo_root)
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / f"{run_id}.json"
    results_path.write_text(json.dumps(payload), encoding="utf-8")
    return results_path


def test_await_with_result_present_recording_exit_0_reemits_banner_verbatim_and_exits_0(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir()
    run_id = "20260714-abcd"
    banner = (
        f"gate-battery: run={run_id} op=battery RESULT=PASS cmds=2 failed=0 (elapsed=3s)"
    )
    _write_results_file(
        state_root,
        repo,
        run_id,
        {
            "run_id": run_id,
            "banner": banner,
            "exit_code": 0,
            "gates": [
                {"id": "gate-a", "exit_code": 0, "duration_seconds": 1.0},
                {"id": "gate-b", "exit_code": 0, "duration_seconds": 2.0},
            ],
        },
    )

    result = _await_battery(repo, state_root, run_id)

    last_line = _last_stdout_line(result)
    assert last_line == banner, f"await must re-emit the recorded banner verbatim: {last_line!r}"
    assert result.returncode == 0, f"await must exit with the recorded run's own exit_code: {result!r}"


def test_await_with_result_present_recording_exit_1_reemits_banner_and_exits_1(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir()
    run_id = "20260714-beef"
    banner = (
        f"gate-battery: run={run_id} op=battery RESULT=FAIL cmds=2 failed=1 "
        "(elapsed=4s) -> first failing gate: gate-red"
    )
    _write_results_file(
        state_root,
        repo,
        run_id,
        {
            "run_id": run_id,
            "banner": banner,
            "exit_code": 1,
            "gates": [
                {"id": "gate-green", "exit_code": 0, "duration_seconds": 1.0},
                {"id": "gate-red", "exit_code": 1, "duration_seconds": 1.5},
            ],
        },
    )

    result = _await_battery(repo, state_root, run_id)

    last_line = _last_stdout_line(result)
    assert last_line == banner, f"await must re-emit the recorded banner verbatim: {last_line!r}"
    assert result.returncode == 1, f"await must exit with the recorded run's own exit_code: {result!r}"


def test_await_with_result_absent_exits_124_with_no_pass_vocabulary(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir()
    # Results dir exists (a battery has run for this repo before) but this specific
    # run-id has never been written -- the in-flight / unknown-run-id case.
    _results_dir(state_root, repo).mkdir(parents=True, exist_ok=True)

    result = _await_battery(repo, state_root, "20260714-0000")

    combined = result.stdout + result.stderr
    assert result.returncode == 124, f"result-absent await must exit 124: {result!r}"
    assert "RESULT=PASS" not in combined, (
        f"124 must never carry success vocabulary: stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_await_with_unknown_repo_key_or_missing_results_dir_exits_124_not_2_or_crash(tmp_path):
    # A repo that has never had a battery run at all -- no gate-battery/<repo-key>/ dir
    # under the state root whatsoever. Must be treated as "not yet", not its own error class.
    repo = tmp_path / "repo"
    repo.mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir()
    assert not (state_root / "gate-battery").exists()

    result = _await_battery(repo, state_root, "20260714-1234")

    assert result.returncode == 124, (
        f"missing results dir / unknown repo key must exit 124 (not 2, not a crash): {result!r}"
    )
    combined = result.stdout + result.stderr
    assert "RESULT=PASS" not in combined


def test_await_with_corrupted_json_exits_125(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir()
    run_id = "20260714-dead"
    results_dir = _results_dir(state_root, repo)
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"{run_id}.json").write_text('{"run_id": "x", trunc', encoding="utf-8")

    result = _await_battery(repo, state_root, run_id)

    assert result.returncode == 125, f"corrupted/truncated results JSON must exit 125: {result!r}"


def test_await_timeout_seconds_zero_with_no_result_returns_124_immediately(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir()

    result = _await_battery(repo, state_root, "20260714-9999", extra_args=["--timeout-seconds", "0"])

    assert result.returncode == 124, f"--timeout-seconds 0 with no result must exit 124: {result!r}"
    combined = result.stdout + result.stderr
    assert "RESULT=PASS" not in combined


def test_await_does_not_require_a_manifest_in_a_manifest_less_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    # Deliberately NO .claude/skill-config/gate-battery.json anywhere under repo --
    # await must never route through the manifest-load refusal path.
    assert not (repo / ".claude").exists()
    state_root = tmp_path / "state"
    state_root.mkdir()
    run_id = "20260714-cafe"
    banner = (
        f"gate-battery: run={run_id} op=battery RESULT=PASS cmds=1 failed=0 (elapsed=1s)"
    )
    _write_results_file(
        state_root,
        repo,
        run_id,
        {
            "run_id": run_id,
            "banner": banner,
            "exit_code": 0,
            "gates": [{"id": "gate-a", "exit_code": 0, "duration_seconds": 0.5}],
        },
    )

    result = _await_battery(repo, state_root, run_id)

    last_line = _last_stdout_line(result)
    assert last_line == banner, (
        f"await must work in a manifest-less repo (never require gate-battery.json): {last_line!r}"
    )
    assert result.returncode == 0
