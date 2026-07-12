#!/usr/bin/env python3
"""
skill_repos.py — shared repo-discovery helpers for the skill plane.

The repo-scoped skills / skill-config are git-tracked INSIDE claude-config at
`<claude-config>/repos/<name>/.claude/...`. On the operator's dev machines and in
WSL, `~/source/repos/<name>` is a symlink into that internal tree, so scanning
`~/source/repos/*` happens to resolve them — but that layout is machine-specific.
On a machine where only `claude-config` is checked out under `~/source/repos`, a
scan of `~/source/repos` alone SILENTLY misses every internal repo.

Both `lint-skills.py` (D1 planner resolution) and `project-skills.py` (per-repo
projection) previously grew their own copy of the "scan the UNION of the passed
repos_dir and the canonical internal repos/" logic. This module is the single
source of truth for that union so the two callers cannot drift.

Deliberately stdlib-only (no `lazy_core` dependency) — both callers are lean,
standalone lint/projection tools and must stay import-cheap.
"""

from pathlib import Path
from typing import Iterator, Optional


def resolve_internal_repos_root() -> Path:
    """Return the canonical, git-tracked `<claude-config>/repos/` directory.

    Derived from THIS module's own location so it is machine-independent:
    `user/scripts/skill_repos.py` → `parents[2]` == `<claude-config>`. This is the
    always-present source of truth for repo-scoped skills, regardless of whether
    sibling working copies exist under `~/source/repos`.
    """
    return Path(__file__).resolve().parents[2] / "repos"


def iter_config_repos(
    repos_dir: Optional[Path],
    internal_repos_dir: Optional[Path],
    marker: str,
) -> Iterator[Path]:
    """Yield repo directories from the UNION of two bases, deduplicated.

    A "config repo" is any immediate subdirectory of a base that contains the
    relative path `marker` (e.g. ".claude/skills" or ".claude/skill-config").

    Args:
        repos_dir: the passed base (typically `~/source/repos` sibling checkouts).
            May be None or non-existent — treated as empty.
        internal_repos_dir: the canonical internal base (typically the result of
            `resolve_internal_repos_root()`). May be None or non-existent —
            treated as empty. Callers make the internal scan an EXPLICIT opt-in so
            the function has no hidden `__file__`-derived global state (keeps it
            hermetically testable); production callers pass
            `resolve_internal_repos_root()`.
        marker: the relative path (slash-separated) that must exist under a repo
            for it to qualify.

    Dedup: by the RESOLVED path of `repo/<marker>`, so a sibling working copy that
    symlinks INTO an internal repo resolves to the same file and is yielded once.
    The passed `repos_dir` is scanned first, so on a collision the sibling wins.
    Yield order within each base is sorted by directory name.
    """
    marker_parts = [p for p in marker.split("/") if p]
    seen: set = set()
    for base in (repos_dir, internal_repos_dir):
        if base is None or not base.exists():
            continue
        try:
            for repo in sorted(base.iterdir()):
                if not repo.is_dir():
                    continue
                marker_path = repo.joinpath(*marker_parts)
                if not marker_path.exists():
                    continue
                key = marker_path.resolve()
                if key in seen:
                    continue
                seen.add(key)
                yield repo
        except OSError:
            # A base that races away / is unreadable contributes nothing rather
            # than crashing the whole scan (mirrors prior per-caller behavior).
            pass
