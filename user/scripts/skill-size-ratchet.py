#!/usr/bin/env python3
"""skill-size-ratchet.py — per-file byte + long-line ratchet lint for skill files.

lazy-batch-skill-deflation Phase 3 (D3): the observed failure mode is that a skill
file's growth curve (+57% in four weeks, 126 commits, on `user/skills/lazy-batch/SKILL.md`
alone) never reverses without a gate — advisory output "demonstrably does not hold
this line" (SPEC D3). This script is that gate: a small, opt-in, committed baseline
JSON (`user/scripts/skill-size-baseline.json`) records a byte ceiling + a long-line
(>500 chars) count ceiling per file; `--check` fails loudly (named file + metric +
current vs. ceiling) when either is exceeded.

Semantics (mirrors the AlgoBooth composite-score gate precedent):
  - Growth past baseline FAILS `--check` (exit 1). This is the whole point.
  - Improvement (current <= ceiling on BOTH metrics) never auto-lowers the
    ceiling — that requires an explicit `--lock-in <path>` (or `--lock-in --all`),
    so a transient deletion can't silently set an unreachable bar for the next
    legitimate addition.
  - `--lock-in` REFUSES to raise a ceiling — it only ever sets
    new_ceiling = min(current, existing_ceiling). Deliberately RAISING a ceiling
    (a legitimate new HARD CONSTRAINT that grows the file) is a manual, reviewable
    edit to the baseline JSON, never a CLI mutation.
  - Opt-in per file: a file not listed in the baseline is invisible to this gate
    (ordinary small skills carry no ceremony). Listing a new file is a manual
    baseline-JSON edit (`--lock-in --new <path>` seeds an entry at the file's
    CURRENT size so a first-time enrollment never fails its own gate).

Long-line census matches the SPEC's method: a "long line" is a line whose length
(character count, not byte count) exceeds 500 — the same threshold used in the
SPEC's inline recon.

Stdlib only. Read-only except `--lock-in`, whose write goes through
`lazy_core._atomic_write` (the repo's one-writer convention for structured JSON).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import lazy_core  # noqa: E402  (sibling import, path bootstrap above)

SCHEMA_VERSION = 1
LONG_LINE_THRESHOLD = 500
DEFAULT_BASELINE_NAME = "skill-size-baseline.json"


def default_baseline_path() -> Path:
    return _SCRIPTS_DIR / DEFAULT_BASELINE_NAME


def load_baseline(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "files": {}}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "files" not in data or not isinstance(data["files"], dict):
        raise ValueError(f"malformed baseline JSON at {path}: expected {{'files': {{...}}}}")
    return data


def measure(repo_root: Path, rel_path: str) -> tuple[int, int]:
    """Return (byte_count, long_line_count) for a file, or raise FileNotFoundError."""
    full = repo_root / rel_path
    data = full.read_bytes()
    text = data.decode("utf-8", errors="replace")
    long_lines = sum(1 for line in text.splitlines() if len(line) > LONG_LINE_THRESHOLD)
    return len(data), long_lines


def check(repo_root: Path, baseline: dict) -> list[dict]:
    """Return a list of finding dicts (empty == clean). Each finding names the
    file, the metric, the current value, and the recorded ceiling."""
    findings: list[dict] = []
    for rel_path, entry in sorted(baseline["files"].items()):
        ceiling_bytes = entry.get("byte_ceiling")
        ceiling_lines = entry.get("long_line_ceiling")
        try:
            cur_bytes, cur_long_lines = measure(repo_root, rel_path)
        except FileNotFoundError:
            findings.append({
                "file": rel_path, "metric": "missing",
                "current": None, "ceiling": None,
            })
            continue
        if ceiling_bytes is not None and cur_bytes > ceiling_bytes:
            findings.append({
                "file": rel_path, "metric": "byte_ceiling",
                "current": cur_bytes, "ceiling": ceiling_bytes,
            })
        if ceiling_lines is not None and cur_long_lines > ceiling_lines:
            findings.append({
                "file": rel_path, "metric": "long_line_ceiling",
                "current": cur_long_lines, "ceiling": ceiling_lines,
            })
    return findings


def lock_in(repo_root: Path, baseline_path: Path, baseline: dict, rel_path: str, *, seed_new: bool = False) -> dict:
    """Update (or seed) one file's ceiling. Returns a result dict with the
    outcome — never silently no-ops without saying so."""
    cur_bytes, cur_long_lines = measure(repo_root, rel_path)
    entry = baseline["files"].get(rel_path)
    if entry is None:
        if not seed_new:
            return {"file": rel_path, "action": "refused", "reason": "not in baseline — pass --new to seed"}
        entry = {"byte_ceiling": cur_bytes, "long_line_ceiling": cur_long_lines}
        baseline["files"][rel_path] = entry
        _write(baseline_path, baseline)
        return {"file": rel_path, "action": "seeded", "byte_ceiling": cur_bytes, "long_line_ceiling": cur_long_lines}

    old_bytes = entry.get("byte_ceiling")
    old_lines = entry.get("long_line_ceiling")
    new_bytes = cur_bytes if old_bytes is None else min(cur_bytes, old_bytes)
    new_lines = cur_long_lines if old_lines is None else min(cur_long_lines, old_lines)

    if new_bytes == old_bytes and new_lines == old_lines:
        return {"file": rel_path, "action": "noop", "reason": "no improvement over recorded ceiling"}

    if (old_bytes is not None and cur_bytes > old_bytes) or (old_lines is not None and cur_long_lines > old_lines):
        # At least one metric got worse — --lock-in NEVER raises a ceiling.
        # Report what it DID do (the other metric may still have improved) —
        # min() above already refused to raise either individually.
        pass

    entry["byte_ceiling"] = new_bytes
    entry["long_line_ceiling"] = new_lines
    _write(baseline_path, baseline)
    return {
        "file": rel_path, "action": "lowered",
        "byte_ceiling": new_bytes, "long_line_ceiling": new_lines,
        "prior_byte_ceiling": old_bytes, "prior_long_line_ceiling": old_lines,
    }


def _write(path: Path, data: dict) -> None:
    lazy_core._atomic_write(path, json.dumps(data, indent=2) + "\n")


def _resolve_repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parents[2]  # user/scripts/<this> -> repo root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--baseline", default=None, help="path to baseline JSON (default: sibling of this script)")
    parser.add_argument("--check", action="store_true", help="check all baseline files against their ceilings (default action)")
    parser.add_argument("--lock-in", metavar="PATH", default=None, help="lower one file's ceiling to its current size (never raises)")
    parser.add_argument("--new", action="store_true", help="with --lock-in on a file NOT yet in the baseline, seed it at its current size")
    args = parser.parse_args()

    repo_root = _resolve_repo_root(args.repo_root)
    baseline_path = Path(args.baseline).resolve() if args.baseline else default_baseline_path()
    baseline = load_baseline(baseline_path)

    if args.lock_in:
        result = lock_in(repo_root, baseline_path, baseline, args.lock_in, seed_new=args.new)
        print(json.dumps(result, indent=2))
        return 0 if result["action"] != "refused" else 1

    findings = check(repo_root, baseline)
    if not findings:
        print(f"OK — {len(baseline['files'])} skill file(s) within their recorded size ceilings.")
        return 0

    for f in findings:
        if f["metric"] == "missing":
            print(f"MISSING  {f['file']} — listed in baseline but not found on disk")
        else:
            print(f"OVER-CEILING  {f['file']}  {f['metric']}={f['current']} > ceiling={f['ceiling']}")
    print(f"\n{len(findings)} ratchet finding(s). Re-bloat detected — trim the file "
          f"or, for a deliberate legitimate growth, hand-edit {baseline_path.name} "
          f"(never auto-raised).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
