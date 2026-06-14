"""
stale_binary.py — F7 / lazy-validation-readiness

Predicate: is the running dev-runtime binary stale relative to the latest
native-source commit in the repo?

Problem context (F7)
--------------------
After a Rust MCP tool is added in a new commit, the already-running dev
runtime is a stale binary.  Step 1d.0 of /lazy-batch historically only
checked `GET /health == 200` — which a stale binary passes.  A run without
explicit operator judgment would therefore dispatch /mcp-test against a binary
that does not yet have the new tool, producing a 404 BLOCK for a tool that
actually exists in source.

This module provides the GENERIC policy predicate.  The AlgoBooth-specific
wiring (reading the boot stamp from the session-log and calling this from
Step 1d.0) is documented in the lazy-batch SKILL.md.

Fail-safe direction (HARD REQUIREMENT)
---------------------------------------
On ANY error — git not found, path is not a repo, git log returns empty output
(no commits touch the configured globs), timestamp parse failure, unexpected
exception — `native_source_newer_than` returns **False**.

Rationale: returning False means "looks fresh / can't tell → trust health=200
and proceed."  A spurious False wastes nothing; the existing health=200 gate
is still the primary guard.  A spurious True, by contrast, would trigger an
unnecessary `dev:restart` that re-compiles the entire Rust project (~3–7 min)
on every mcp-test cycle.  Fail safe = fail in the direction that never adds
gratuitous build time.

The predicate is pure and read-only; it never raises.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


_DEFAULT_GLOBS: list[str] = ["src-tauri", "crates"]


def _parse_iso(ts: str) -> datetime | None:
    """
    Parse an ISO-8601 timestamp string robustly.

    Handles:
      - Trailing 'Z'  (e.g. "2024-01-15T10:30:00Z")
      - UTC offsets   (e.g. "2024-01-15T10:30:00+00:00")
      - Naive strings (treated as UTC)

    Returns a timezone-aware datetime, or None on any parse failure.
    datetime.fromisoformat() in Python 3.7–3.10 does not support the
    trailing-Z form, so we normalise it first.
    """
    try:
        normalized = ts.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        # Attach UTC if still naive (shouldn't happen with well-formed ISO-8601,
        # but defend anyway).
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def native_source_newer_than(
    boot_iso: str,
    repo_root: Path,
    *,
    globs: list[str] | None = None,
) -> bool:
    """
    Return True when the newest git commit touching the native-source globs
    is STRICTLY NEWER than the timestamp given in `boot_iso`.

    This implies the running binary was built before that commit landed, so
    the binary is stale and a restart is warranted before running /mcp-test.

    Parameters
    ----------
    boot_iso : str
        ISO-8601 timestamp of when the currently-running dev runtime booted.
        Typically sourced from the session-log boot stamp or a health-payload
        `boot_time` field (AlgoBooth-side, documented in lazy-batch SKILL.md).
    repo_root : Path
        Root directory of the target git repository.
    globs : list[str] | None
        Path prefixes (relative to repo_root) that constitute "native source"
        — i.e. paths whose change requires a Rust recompile and binary restart.
        Defaults to ["src-tauri", "crates"] (the AlgoBooth native roots).
        Override to make the predicate non-AlgoBooth-specific.

    Returns
    -------
    bool
        True  → native source advanced AFTER `boot_iso` → restart needed.
        False → boot is current, no native commits exist, or any error
                (fail-safe; see module docstring).
    """
    # --- Resolve active glob list ------------------------------------------
    active_globs = globs if globs is not None else _DEFAULT_GLOBS

    # --- Parse the boot timestamp first (cheap; fail-safe if bad) -----------
    boot_dt = _parse_iso(boot_iso)
    if boot_dt is None:
        # Unparseable boot stamp: fail safe — do not force a restart.
        return False

    # --- Ask git for the newest commit touching the native-source paths ------
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                "-1",
                "--format=%cI",  # committer date, strict ISO-8601 with tz offset
                "--",
                *active_globs,
            ],
            capture_output=True,
            text=True,
            timeout=15,  # git should respond immediately; guard against stalls
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        # git binary not found, timed out, or other OS-level error.
        # Fail safe.
        return False

    # git exits non-zero for a non-repo or permission error.
    if result.returncode != 0:
        return False

    raw_commit_ts = result.stdout.strip()
    if not raw_commit_ts:
        # No commits touch the configured globs — the native source has never
        # been committed under these paths.  Nothing to compare; fail safe.
        return False

    # --- Parse the commit timestamp ------------------------------------------
    commit_dt = _parse_iso(raw_commit_ts)
    if commit_dt is None:
        # git returned an unexpected format.  Fail safe.
        return False

    # --- The stale-binary decision -------------------------------------------
    # STRICTLY NEWER: if the commit landed at exactly the same second as boot,
    # that is ambiguous but we lean toward "not stale" (fail-safe direction).
    return commit_dt > boot_dt


# ---------------------------------------------------------------------------
# Minimal CLI (informational; --exit-code makes it scriptable)
# ---------------------------------------------------------------------------

def main() -> None:
    """
    CLI wrapper around native_source_newer_than.

    Prints STALE or FRESH and exits 0 by default (informational).
    Pass --exit-code to exit 1 when STALE (for scripting / shell guards).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Detect whether the running dev-runtime binary is stale relative "
            "to the latest commit touching native source.  "
            "Part of F7 / lazy-validation-readiness; see SPEC.md."
        )
    )
    parser.add_argument(
        "--repo-root",
        required=True,
        help="Absolute path to the target git repository root.",
    )
    parser.add_argument(
        "--boot-iso",
        required=True,
        help=(
            "ISO-8601 timestamp of when the currently-running runtime booted "
            "(e.g. 2024-01-15T10:30:00Z or 2024-01-15T10:30:00+00:00)."
        ),
    )
    parser.add_argument(
        "--glob",
        action="append",
        dest="globs",
        metavar="PATH",
        help=(
            "Native-source path prefix to check (relative to repo root).  "
            "May be repeated.  "
            "Defaults to ['src-tauri', 'crates'] when not provided."
        ),
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        default=False,
        help="Exit with code 1 when STALE (default: always exit 0).",
    )
    args = parser.parse_args()

    stale = native_source_newer_than(
        boot_iso=args.boot_iso,
        repo_root=Path(args.repo_root),
        globs=args.globs,  # None when not provided → uses default
    )

    print("STALE" if stale else "FRESH")
    if args.exit_code and stale:
        sys.exit(1)


if __name__ == "__main__":
    main()
