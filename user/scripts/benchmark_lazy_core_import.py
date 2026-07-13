#!/usr/bin/env python3
"""benchmark_lazy_core_import.py — Phase-0 measurement harness for the
lazy-core-package-decomposition feature.

Pure-read, stdlib-only. Records the three KPI proxies the SPEC's KPI row names,
re-measurable in one command so every phase gate can stamp a fresh number into
its receipt:

  (1) full ``import lazy_core`` warm wall-ms (best-of-N cold subprocess imports)
  (2) pytest collection: test count + collect-only wall-s for the lazy_core suite
  (3) largest-module LoC census of lazy_core (the monolith today; the package
      submodules once the split lands — asserts "no post-split module >4K LoC")

``--hook-surface`` (Phase 2 WU-5, the post-facade follow-up this docstring
promised at Phase 0): best-of-N fresh-subprocess timing of ``import lazy_core``
PLUS touching exactly the three hook-touched names (``claude_state_dir``,
``_load_registry``, ``append_hook_event``) through the facade — the D4
hook-latency cut, printed beside the full-import number. The sample also
records whether ``lazy_core._monolith`` got imported (it must not; the honest
caveat: the guard's marker-reading paths still load ``_monolith`` — this mode
measures ONLY the statedir-resolved hook surface).

Usage:
  python3 user/scripts/benchmark_lazy_core_import.py [--repo-root .] [--iters 5]
                                                     [--json] [--no-collect]
                                                     [--hook-surface]

Exit 0 always (a benchmark never gates); malformed --repo-root -> exit 2.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def _scripts_dir(repo_root: Path) -> Path:
    return repo_root / "user" / "scripts"


def measure_import_ms(scripts_dir: Path, iters: int) -> dict:
    """Best-of-N *cold* imports: each iteration is a fresh subprocess so the
    number reflects real per-process import cost (what the PreToolUse hooks pay),
    not a warm re-import from a hot module cache."""
    code = (
        "import sys, time; sys.path.insert(0, %r); "
        "t = time.perf_counter(); import lazy_core; "
        "sys.stdout.write('%%.4f' %% ((time.perf_counter() - t) * 1000.0))"
        % str(scripts_dir)
    )
    samples: list[float] = []
    for _ in range(max(1, iters)):
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        out = (proc.stdout or "").strip()
        try:
            samples.append(float(out))
        except ValueError:
            samples.append(float("nan"))
    good = [s for s in samples if s == s]  # drop NaN
    return {
        "iters": len(samples),
        "best_ms": round(min(good), 2) if good else None,
        "median_ms": round(sorted(good)[len(good) // 2], 2) if good else None,
        "all_ms": [round(s, 2) for s in samples],
    }


def measure_hook_surface_ms(scripts_dir: Path, iters: int) -> dict:
    """Best-of-N *cold* hook-surface touches: ``import lazy_core`` + attribute
    access on exactly the three hook-touched names, each in a fresh subprocess.
    Records per-sample whether ``lazy_core._monolith`` was imported — the D4
    cut holds only while it is not (statedir resolves all three)."""
    code = (
        "import sys, time; sys.path.insert(0, %r); "
        "t = time.perf_counter(); import lazy_core; "
        "lazy_core.claude_state_dir; lazy_core._load_registry; "
        "lazy_core.append_hook_event; "
        "ms = (time.perf_counter() - t) * 1000.0; "
        "sys.stdout.write('%%.4f %%d' %% (ms, 1 if 'lazy_core._monolith' in sys.modules else 0))"
        % str(scripts_dir)
    )
    samples: list[float] = []
    monolith_hits = 0
    for _ in range(max(1, iters)):
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        parts = (proc.stdout or "").strip().split()
        try:
            samples.append(float(parts[0]))
            monolith_hits += int(parts[1])
        except (IndexError, ValueError):
            samples.append(float("nan"))
    good = [s for s in samples if s == s]  # drop NaN
    return {
        "iters": len(samples),
        "best_ms": round(min(good), 2) if good else None,
        "median_ms": round(sorted(good)[len(good) // 2], 2) if good else None,
        "all_ms": [round(s, 2) for s in samples],
        "monolith_loaded_samples": monolith_hits,
    }


def measure_collection(scripts_dir: Path) -> dict:
    """pytest --collect-only for the lazy_core suite: count + wall seconds."""
    target = scripts_dir / "test_lazy_core.py"
    if not target.exists():
        # Post-split the suite is a package dir; fall back to the tests dir.
        target = scripts_dir / "tests"
    t = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(target), "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    wall_s = time.perf_counter() - t
    count = None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.endswith("tests collected") or " tests collected in " in line:
            for tok in line.split():
                if tok.isdigit():
                    count = int(tok)
                    break
    return {
        "target": str(target.name),
        "count": count,
        "wall_s": round(wall_s, 2),
    }


def measure_loc(scripts_dir: Path) -> dict:
    """Largest-module LoC census: the monolith today, package submodules once
    the split lands. Flags any module >4000 LoC (the SPEC's no-new-monolith
    ceiling)."""
    modules: dict[str, int] = {}
    monolith = scripts_dir / "lazy_core.py"
    pkg = scripts_dir / "lazy_core"
    if monolith.exists():
        modules[monolith.name] = _count_lines(monolith)
    if pkg.is_dir():
        for py in sorted(pkg.rglob("*.py")):
            modules["lazy_core/" + str(py.relative_to(pkg)).replace("\\", "/")] = (
                _count_lines(py)
            )
    largest = max(modules.values()) if modules else 0
    over_ceiling = sorted(k for k, v in modules.items() if v > 4000)
    return {
        "modules": modules,
        "largest_loc": largest,
        "over_4k_ceiling": over_ceiling,
    }


def _count_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return -1


def build_report(
    repo_root: Path, iters: int, do_collect: bool, hook_surface: bool = False
) -> dict:
    scripts_dir = _scripts_dir(repo_root)
    report = {
        "repo_root": str(repo_root),
        "import": measure_import_ms(scripts_dir, iters),
        "loc": measure_loc(scripts_dir),
    }
    if hook_surface:
        report["hook_surface"] = measure_hook_surface_ms(scripts_dir, iters)
    if do_collect:
        report["collection"] = measure_collection(scripts_dir)
    return report


def render(report: dict) -> str:
    lines = ["lazy_core benchmark", "==================="]
    imp = report["import"]
    lines.append(
        f"import lazy_core (cold, best of {imp['iters']}): "
        f"best={imp['best_ms']} ms  median={imp['median_ms']} ms"
    )
    if "hook_surface" in report:
        hs = report["hook_surface"]
        lines.append(
            f"hook surface (import + 3 hook names, best of {hs['iters']}): "
            f"best={hs['best_ms']} ms  median={hs['median_ms']} ms  "
            f"monolith_loaded_samples={hs['monolith_loaded_samples']}"
        )
    if "collection" in report:
        col = report["collection"]
        lines.append(
            f"pytest --collect-only {col['target']}: "
            f"{col['count']} tests in {col['wall_s']} s"
        )
    loc = report["loc"]
    lines.append(f"largest module: {loc['largest_loc']} LoC")
    if loc["over_4k_ceiling"]:
        lines.append("  OVER 4K CEILING: " + ", ".join(loc["over_4k_ceiling"]))
    for name, n in sorted(loc["modules"].items(), key=lambda kv: -kv[1]):
        lines.append(f"    {n:>7} {name}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--iters", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-collect", action="store_true")
    ap.add_argument("--hook-surface", action="store_true")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / "user" / "scripts").is_dir():
        sys.stderr.write(
            f"benchmark_lazy_core_import: no user/scripts under {repo_root}\n"
        )
        return 2

    report = build_report(
        repo_root, args.iters,
        do_collect=not args.no_collect,
        hook_surface=args.hook_surface,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
