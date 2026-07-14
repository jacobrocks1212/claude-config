#!/usr/bin/env python3
"""
cli_surface_gen.py — Aggregator + freshness gate for the state-CLI contract
registry (state-cli-contract-registry, D1/D3).

Shells each roster script's own ``--dump-cli-surface`` introspection
subcommand (never re-implements argparse semantics — a projection can never
drift from the parser it introspects) and merges the results into the
committed, key-sorted, byte-stable ``docs/cli/cli-surface.json``.

Usage:
    python3 user/scripts/cli_surface_gen.py --repo-root .            # regenerate
    python3 user/scripts/cli_surface_gen.py --repo-root . --check    # freshness gate

Exit codes: 0 clean/regenerated, 1 drift found under --check, 2 a roster
script's --dump-cli-surface subprocess failed (malformed input).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = 1

# Closed v1 roster (SPEC D1 "Scope roster"). Additions are one line here.
# `needs_repo_root` scripts REQUIRE --repo-root on their own parser (the
# aggregator always has a real repo_root to hand it); everything else's
# --repo-root is optional/defaulted so it is omitted for a smaller, more
# obviously-correct subprocess invocation.
ROSTER: tuple[dict, ...] = (
    {"file": "lazy-state.py", "needs_repo_root": False},
    {"file": "bug-state.py", "needs_repo_root": False},
    {"file": "surface_resolver.py", "needs_repo_root": True},
    {"file": "lazy_parity_audit.py", "needs_repo_root": True},
    {"file": "kpi-scorecard.py", "needs_repo_root": False},
    {"file": "lint-skills.py", "needs_repo_root": False},
    {"file": "doc-drift-lint.py", "needs_repo_root": False},
    {"file": "gate-battery.py", "needs_repo_root": False},
)

REGISTRY_REL_PATH = Path("docs") / "cli" / "cli-surface.json"


class CliSurfaceGenError(RuntimeError):
    """A roster script's --dump-cli-surface invocation failed."""


def _scripts_dir(repo_root: Path) -> Path:
    return repo_root / "user" / "scripts"


def dump_one(repo_root: Path, entry: dict, python_executable: str = None) -> dict:
    """Invoke one roster script's --dump-cli-surface and return its parsed dict."""
    script_path = _scripts_dir(repo_root) / entry["file"]
    if not script_path.is_file():
        raise CliSurfaceGenError(f"roster script not found: {script_path}")
    cmd = [python_executable or sys.executable, str(script_path), "--dump-cli-surface"]
    if entry["needs_repo_root"]:
        cmd.extend(["--repo-root", str(repo_root)])
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.returncode != 0:
        raise CliSurfaceGenError(
            f"{entry['file']} --dump-cli-surface failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CliSurfaceGenError(
            f"{entry['file']} --dump-cli-surface produced non-JSON stdout: {exc}"
        ) from exc
    return payload


def generate_registry(repo_root: Path, roster: tuple[dict, ...] = ROSTER,
                       python_executable: str = None) -> dict:
    """Regenerate the full registry dict (schema_version + scripts map).

    Deterministic / byte-stable: no wall-clock, no host-dependent values —
    dict keys sorted at serialization time (json.dumps(..., sort_keys=True)).
    """
    scripts: dict[str, dict] = {}
    for entry in roster:
        payload = dump_one(repo_root, entry, python_executable=python_executable)
        script_name = payload.get("script", entry["file"])
        scripts[script_name] = {"flags": payload["flags"]}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "cli_surface_gen.py",
        "scripts": scripts,
    }


def render_registry(registry: dict) -> str:
    return json.dumps(registry, indent=2, sort_keys=True) + "\n"


def write_registry(repo_root: Path, registry: dict) -> Path:
    target = repo_root / REGISTRY_REL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_registry(registry), encoding="utf-8", newline="\n")
    return target


def _diff_scripts(committed: dict, fresh: dict) -> list[str]:
    """Return human-readable per-script drift lines between two registries."""
    lines: list[str] = []
    committed_scripts = committed.get("scripts", {})
    fresh_scripts = fresh.get("scripts", {})
    all_names = sorted(set(committed_scripts) | set(fresh_scripts))
    for name in all_names:
        old = committed_scripts.get(name)
        new = fresh_scripts.get(name)
        if old == new:
            continue
        if old is None:
            lines.append(f"{name}: NEW in roster (not in committed registry)")
            continue
        if new is None:
            lines.append(f"{name}: REMOVED from roster (still in committed registry)")
            continue
        old_flags = {f["name"]: f for f in old.get("flags", [])}
        new_flags = {f["name"]: f for f in new.get("flags", [])}
        added = sorted(set(new_flags) - set(old_flags))
        removed = sorted(set(old_flags) - set(new_flags))
        changed = sorted(
            n for n in (set(new_flags) & set(old_flags))
            if new_flags[n] != old_flags[n]
        )
        if added:
            lines.append(f"{name}: added flag(s) {', '.join(added)}")
        if removed:
            lines.append(f"{name}: removed flag(s) {', '.join(removed)}")
        if changed:
            lines.append(f"{name}: changed flag(s) {', '.join(changed)}")
    return lines


def check_freshness(repo_root: Path, roster: tuple[dict, ...] = ROSTER,
                     python_executable: str = None) -> tuple[bool, list[str]]:
    """Regenerate in-memory and diff against the committed file.

    Returns (fresh, findings) — fresh=True iff byte-identical (findings empty).
    """
    committed_path = repo_root / REGISTRY_REL_PATH
    if not committed_path.is_file():
        return False, [f"{REGISTRY_REL_PATH} does not exist — run without --check to generate it"]
    try:
        committed = json.loads(committed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, [f"{REGISTRY_REL_PATH} is not valid JSON: {exc}"]

    fresh_registry = generate_registry(repo_root, roster=roster, python_executable=python_executable)
    if render_registry(committed) == render_registry(fresh_registry):
        return True, []
    return False, _diff_scripts(committed, fresh_registry)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Regenerate/verify the committed state-CLI contract registry "
                    "(docs/cli/cli-surface.json) by introspecting each roster "
                    "script's live ArgumentParser."
    )
    parser.add_argument("--repo-root", default=".",
                        help="claude-config repo root (default: cwd)")
    parser.add_argument("--check", action="store_true",
                        help="Freshness gate: regenerate to memory and diff against "
                             "the committed file; exit 1 naming any drift instead "
                             "of writing.")
    parser.add_argument("--python", default=None, metavar="EXE",
                        help="Python executable used to invoke each roster script's "
                             "--dump-cli-surface subprocess (default: sys.executable).")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    try:
        if args.check:
            fresh, findings = check_freshness(repo_root, python_executable=args.python)
            if fresh:
                print(f"OK — {REGISTRY_REL_PATH} is up to date "
                      f"({len(ROSTER)} roster script(s)).")
                return 0
            for line in findings:
                print(f"DRIFT: {line}")
            print(f"\ncli_surface_gen.py --check: {len(findings)} drift finding(s). "
                  f"Regenerate with: python3 user/scripts/cli_surface_gen.py "
                  f"--repo-root {args.repo_root}")
            return 1

        registry = generate_registry(repo_root, python_executable=args.python)
        target = write_registry(repo_root, registry)
        script_count = len(registry["scripts"])
        flag_count = sum(len(v["flags"]) for v in registry["scripts"].values())
        print(f"OK — wrote {target} ({script_count} script(s), {flag_count} flag(s)).")
        return 0
    except CliSurfaceGenError as exc:
        print(f"cli_surface_gen.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
