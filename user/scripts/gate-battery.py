#!/usr/bin/env python3
"""gate-battery.py — stdlib-only cross-platform gate-battery runner.

Feature: generalized-build-test-runner-skills (Phase 1, WU-2).

Runs a manifest-declared, sequential battery of "gates" (build/lint/test commands) for a
repo and reports a single machine-parseable outcome banner as the LAST stdout line, per the
Runner-Outcome Contract SSOT (Leg 1, the ``gate-battery:`` instance):

    ~/.claude/skills/_components/runner-outcome-contract.md

    gate-battery: run=<id> op=battery RESULT=<PASS|FAIL> cmds=<n> failed=<k> (elapsed=<s>s) [-> first failing gate: <id>]

This runner is the cross-platform/cloud-capable half of that contract (a separate
Windows-only shell plane is the workstation-only half) — it MUST stay stdlib-only
(argparse/subprocess/json/pathlib/hashlib/shlex/time/os/sys) and MUST NEVER shell out to
that Windows-only shell (a source-text scan in the test suite enforces this).

Manifest: ``<repo-toplevel>/.claude/skill-config/gate-battery.json``::

    {"version": 1, "gates": [{"id": "<str>", "cmd": "<str>" | ["<argv>", ...], "cwd": "<optional str>"}]}

Gates run SEQUENTIALLY in manifest order; a failing gate does NOT stop the battery — the
FIRST failing gate's id is recorded in the banner. Each gate's exit code + wall-clock
duration is recorded in a results JSON file written to
``<state-root>/gate-battery/<repo-key>/results/<run-id>.json`` (state-root defaults to
``~/.claude/state``; overridable via ``--state-root`` — the test seam, so hermetic tests
never touch the real state root).

Exit-code vocabulary:
  0   — all gates passed (all-green)
  1   — at least one gate failed, OR an unexpected internal error occurred
  2   — manifest missing or malformed (zero state written on this path)
  124/125 — RESERVED for a later ``--await`` work unit (WU-3); NOT implemented here.

``--await`` is explicitly out of scope for this work unit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for gate-battery.py.

    A plain ``argparse.ArgumentParser`` built in this module-level function — a later work
    unit swaps in a shared parser class (state-cli-contract-registry style), so the shape
    is kept simple and isolated here on purpose.
    """
    parser = argparse.ArgumentParser(
        prog="gate-battery.py",
        description="Run the manifest-declared gate battery for a repo and report a "
        "single last-line outcome banner.",
    )
    parser.add_argument(
        "--repo-root",
        default=os.getcwd(),
        help="Repo root to resolve the git toplevel + manifest from (default: cwd).",
    )
    parser.add_argument(
        "--state-root",
        default=None,
        help="Base state directory (default: ~/.claude/state). Results are written under "
        "<state-root>/gate-battery/<repo-key>/results/<run-id>.json.",
    )
    return parser


# ---------------------------------------------------------------------------
# repo-key (private copy — keep-in-sync)
# ---------------------------------------------------------------------------

def _repo_key(repo_root: str) -> str:
    # PRIVATE copy of lazy_core/statedir.py::repo_key — keep in sync (the runner must stay
    # stdlib-only per SPEC L4; same precedent as phases-slice.py's private regex copy).
    norm = os.path.realpath(str(repo_root)).replace("\\", "/").rstrip("/")
    if len(norm) >= 2 and norm[1] == ":":
        norm = norm[0].lower() + norm[1:]
    if not norm:
        norm = "/"
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# toplevel + manifest resolution
# ---------------------------------------------------------------------------

def _resolve_toplevel(repo_root: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            out = proc.stdout.strip()
            if out:
                return out
    except Exception:
        pass
    return repo_root


def _load_manifest(toplevel: str):
    """Return (gates, error_message). gates is None on any failure."""
    manifest_path = Path(toplevel) / ".claude" / "skill-config" / "gate-battery.json"
    if not manifest_path.is_file():
        return None, f"gate-battery: manifest not found at {manifest_path}"

    try:
        raw_text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"gate-battery: could not read manifest at {manifest_path}: {exc}"

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return None, f"gate-battery: manifest is malformed json at {manifest_path}: {exc}"

    if not isinstance(payload, dict):
        return None, f"gate-battery: manifest at {manifest_path} is malformed (invalid shape, expected an object)"

    gates = payload.get("gates")
    if not isinstance(gates, list):
        return None, f"gate-battery: manifest at {manifest_path} is malformed (invalid \"gates\" field, expected a list)"

    for entry in gates:
        if not isinstance(entry, dict) or "id" not in entry or "cmd" not in entry:
            return None, (
                f"gate-battery: manifest at {manifest_path} is malformed (invalid gate entry, "
                "each gate requires \"id\" and \"cmd\")"
            )
        cmd = entry["cmd"]
        if not isinstance(cmd, (str, list)):
            return None, (
                f"gate-battery: manifest at {manifest_path} is malformed (invalid \"cmd\" for gate "
                f"{entry.get('id')!r}, expected a string or list)"
            )

    return gates, None


# ---------------------------------------------------------------------------
# gate execution
# ---------------------------------------------------------------------------

def _build_argv(cmd):
    if isinstance(cmd, list):
        return list(cmd)
    return shlex.split(cmd)


def _run_gate(gate: dict, toplevel: str):
    gate_id = gate["id"]
    cwd_value = gate.get("cwd")
    cwd = str(Path(toplevel) / cwd_value) if cwd_value else toplevel

    argv = _build_argv(gate["cmd"])

    started = time.time()
    try:
        proc = subprocess.run(argv, cwd=cwd)
        exit_code = proc.returncode
    except Exception:
        exit_code = 127
    duration_seconds = time.time() - started

    return {
        "id": gate_id,
        "exit_code": exit_code,
        "duration_seconds": duration_seconds,
    }


# ---------------------------------------------------------------------------
# run id
# ---------------------------------------------------------------------------

def _make_run_id() -> str:
    return time.strftime("%Y%m%d", time.gmtime()) + "-" + os.urandom(2).hex()


# ---------------------------------------------------------------------------
# results file
# ---------------------------------------------------------------------------

def _results_path(state_root: str, repo_root: str, run_id: str) -> Path:
    return Path(state_root) / "gate-battery" / _repo_key(repo_root) / "results" / f"{run_id}.json"


def _write_results(results_path: Path, payload: dict):
    """Write the results file atomically. Returns True on success, False on any OSError
    (the caller degrades the banner gracefully rather than crashing)."""
    try:
        results_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = results_path.with_suffix(results_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(str(tmp_path), str(results_path))
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = args.repo_root
    state_root = args.state_root or str(Path.home() / ".claude" / "state")

    toplevel = _resolve_toplevel(repo_root)

    gates, error_message = _load_manifest(toplevel)
    if gates is None:
        print(error_message)
        return 2

    run_id = _make_run_id()
    started_at = time.time()
    gate_results = []
    first_failing_id = None

    try:
        for gate in gates:
            result = _run_gate(gate, toplevel)
            gate_results.append(result)
            if result["exit_code"] != 0 and first_failing_id is None:
                first_failing_id = result["id"]

        failed_count = sum(1 for r in gate_results if r["exit_code"] != 0)
        cmds_count = len(gate_results)
        elapsed_seconds = time.time() - started_at
        elapsed_int = int(round(elapsed_seconds))

        if failed_count == 0:
            exit_code = 0
            banner = (
                f"gate-battery: run={run_id} op=battery RESULT=PASS "
                f"cmds={cmds_count} failed=0 (elapsed={elapsed_int}s)"
            )
        else:
            exit_code = 1
            banner = (
                f"gate-battery: run={run_id} op=battery RESULT=FAIL "
                f"cmds={cmds_count} failed={failed_count} (elapsed={elapsed_int}s) "
                f"-> first failing gate: {first_failing_id}"
            )

        results_payload = {
            "run_id": run_id,
            "repo_root": repo_root,
            "started_at": started_at,
            "elapsed_seconds": elapsed_seconds,
            "banner": banner,
            "exit_code": exit_code,
            "gates": gate_results,
        }

        results_path = _results_path(state_root, repo_root, run_id)
        wrote_results = _write_results(results_path, results_payload)
        if not wrote_results:
            if " -> " in banner:
                banner += "; await unavailable: results not written"
            else:
                banner += " -> await unavailable: results not written"

        return exit_code
    except Exception as exc:  # pragma: no cover - defensive last-resort banner
        elapsed_seconds = time.time() - started_at
        elapsed_int = int(round(elapsed_seconds))
        cmds_count = len(gate_results)
        banner = (
            f"gate-battery: run={run_id} op=battery RESULT=FAIL "
            f"cmds={cmds_count} failed={cmds_count if cmds_count else 1} "
            f"(elapsed={elapsed_int}s) -> internal error: {exc}"
        )
        print(f"gate-battery: internal error: {exc}", file=sys.stderr)
        return 1
    finally:
        sys.stdout.flush()
        print(banner)
        sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
