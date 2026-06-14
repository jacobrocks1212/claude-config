"""
validation_readiness.py — F5 validation-readiness pre-screen CLI.

For each feature in <repo-root>/docs/features/queue.json that carries a
DEFERRED_NON_CLOUD.md sentinel, determine whether its MCP test scenarios
assert tools that are already registered in the target repo.  Prints a
per-feature verdict table (ready | needs-work) and always exits 0 — the
verdict is advisory, not a hard gate.

The heavy lifting (grep + regex) is delegated to surface_resolver.py so
that F5 and F8 (Phase 5) share a single resolver implementation.

Spec: docs/specs/lazy-validation-readiness/SPEC.md §F5
"""

import json
import sys
from pathlib import Path

# Import the shared surface resolver from the same scripts directory.
# When run as a script the resolver lives alongside this file; when
# imported from tests the directory is already on sys.path.
try:
    from surface_resolver import unresolved_tools
except ImportError:
    # Fallback: add the directory of this file to sys.path so the import
    # resolves regardless of the caller's working directory.
    _here = Path(__file__).parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    from surface_resolver import unresolved_tools


# ---------------------------------------------------------------------------
# Queue parsing
# ---------------------------------------------------------------------------

def _load_queue(repo_root: Path) -> list[dict]:
    """Load docs/features/queue.json and return the queue list.

    Returns an empty list (not an error) when the file is absent — the
    caller prints a note and exits 0.  Raises ValueError on malformed JSON.
    """
    queue_path = repo_root / "docs" / "features" / "queue.json"
    if not queue_path.exists():
        return []
    text = queue_path.read_text(encoding="utf-8")
    data = json.loads(text)
    # Shape: { "queue": [ { "id": ..., "name": ..., "tier": ..., "spec_dir": ... }, ... ] }
    return data.get("queue", [])


# ---------------------------------------------------------------------------
# Scenario discovery
# ---------------------------------------------------------------------------

def _find_scenarios(feature_dir: Path) -> list[Path]:
    """Return scenario .md files for a feature.

    Looks for an ``mcp-tests/`` sub-directory under ``feature_dir`` and
    returns all *.md files found there.  Returns an empty list when the
    directory does not exist.

    The files may be Windows git-symlink pointers (mode 120000 stored as
    tiny text files containing a relative target path) — surface_resolver's
    ``unresolved_tools`` follows them transparently.
    """
    mcp_tests_dir = feature_dir / "mcp-tests"
    if not mcp_tests_dir.is_dir():
        return []
    # Collect only *.md files; ignore hidden files or directories.
    return sorted(mcp_tests_dir.glob("*.md"))


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------

def _verdict_for_feature(
    feature_entry: dict,
    features_root: Path,
    repo_root: Path,
) -> dict:
    """Compute the verdict for a single feature entry from queue.json.

    Returns a dict with keys:
      feature_id   — string
      status       — "ready" | "ready (no scenarios)" | "needs-work" | "skip"
      missing      — list[str] of missing tool names (empty when ready)
      note         — optional string explanation
    """
    feature_id: str = feature_entry.get("id", "<unknown>")
    spec_dir: str = feature_entry.get("spec_dir", "")

    # Resolve the feature directory.
    feature_dir = features_root / spec_dir
    if not feature_dir.is_dir():
        return {
            "feature_id": feature_id,
            "status": "skip",
            "missing": [],
            "note": f"spec_dir not found on disk: {spec_dir}",
        }

    # Only process features that carry DEFERRED_NON_CLOUD.md.
    deferred_sentinel = feature_dir / "DEFERRED_NON_CLOUD.md"
    if not deferred_sentinel.exists():
        return {
            "feature_id": feature_id,
            "status": "skip",
            "missing": [],
            "note": "no DEFERRED_NON_CLOUD.md — not a front-load candidate",
        }

    # Find scenarios.
    scenarios = _find_scenarios(feature_dir)
    if not scenarios:
        # No mcp-tests/ scenarios — can't assert anything is missing;
        # report as "ready (no scenarios)" so the operator knows coverage
        # is absent but there's nothing we can statically verify.
        return {
            "feature_id": feature_id,
            "status": "ready (no scenarios)",
            "missing": [],
            "note": "DEFERRED_NON_CLOUD present but no mcp-tests/ scenarios found",
        }

    # Run the surface resolver against every scenario.
    all_missing: list[str] = []
    for scenario_path in scenarios:
        try:
            missing = unresolved_tools(scenario_path, repo_root)
        except (FileNotFoundError, OSError) as exc:
            # A scenario that can't be read is treated as missing evidence.
            missing = [f"<unreadable scenario: {exc}>"]
        all_missing.extend(missing)

    # Deduplicate and sort for stable output.
    unique_missing = sorted(set(all_missing))

    if unique_missing:
        return {
            "feature_id": feature_id,
            "status": "needs-work",
            "missing": unique_missing,
            "note": None,
        }
    return {
        "feature_id": feature_id,
        "status": "ready",
        "missing": [],
        "note": None,
    }


# ---------------------------------------------------------------------------
# Table formatting
# ---------------------------------------------------------------------------

def _format_table(verdicts: list[dict]) -> str:
    """Format verdict rows into a human-readable table string."""
    # Filter out skipped features (not DEFERRED_NON_CLOUD).
    rows = [v for v in verdicts if v["status"] != "skip"]

    if not rows:
        return "  (no DEFERRED_NON_CLOUD features in queue)\n"

    lines = []
    # Header
    lines.append(
        f"  {'FEATURE':<40}  {'VERDICT':<22}  MISSING TOOLS"
    )
    lines.append(f"  {'-'*40}  {'-'*22}  {'-'*30}")

    for v in rows:
        fid = v["feature_id"]
        status = v["status"]
        missing_str = ", ".join(v["missing"]) if v["missing"] else ""
        lines.append(f"  {fid:<40}  {status:<22}  {missing_str}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    """CLI entry point.

    Usage:
        python validation_readiness.py --repo-root <algobooth-root>

    Reads <root>/docs/features/queue.json, checks each DEFERRED_NON_CLOUD
    feature's mcp-tests/ scenarios against the repo's registered tools, and
    prints a verdict table.  Always exits 0 (advisory).
    """
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "validation_readiness.py — F5 pre-screen: print a ready/needs-work "
            "verdict for every DEFERRED_NON_CLOUD feature in queue.json.  "
            "Advisory — always exits 0."
        )
    )
    parser.add_argument(
        "--repo-root",
        required=True,
        metavar="ROOT",
        help=(
            "Root of the target AlgoBooth repository.  Must contain "
            "docs/features/queue.json and src-tauri/src/ipc/mcp/registrations/."
        ),
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    features_root = repo_root / "docs" / "features"

    # Load queue.
    try:
        queue = _load_queue(repo_root)
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"validation_readiness: cannot read queue.json — {exc}",
            file=sys.stderr,
        )
        return 0

    if not queue:
        print(
            "validation_readiness: docs/features/queue.json absent or empty — "
            "no features to screen."
        )
        return 0

    # Compute verdicts.
    verdicts = []
    for entry in queue:
        verdict = _verdict_for_feature(entry, features_root, repo_root)
        verdicts.append(verdict)

    # Print table.
    print("validation_readiness — DEFERRED_NON_CLOUD pre-screen verdict")
    print("=" * 70)
    print(_format_table(verdicts))
    print("advisory: operator may still front-load a needs-work feature.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
