"""
test_stale_binary.py — hermetic unit tests for stale_binary.py

Tests build a temporary git repository from scratch using tmp_path so they
are fully self-contained and never touch the real AlgoBooth repo.

Test coverage (per Phase 6 spec)
---------------------------------
1. Boot BEFORE the commit  → True  (binary is stale; restart warranted)
2. Boot AFTER  the commit  → False (binary is current; no restart needed)
3. Commit touches ONLY a non-native path (e.g. docs/)
   → False (no native commit; fail-safe)
4. Non-git / bogus repo_root → False (fail-safe; no raise)
5. Unparseable boot_iso    → False (fail-safe; no raise)

All test cases assert the fail-safe contract: errors / no-native-commits
→ False; never a spurious True.

Run with:
  cd C:/Users/Jacob/source/repos/claude-config
  python -m pytest user/scripts/test_stale_binary.py -q
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stale_binary import native_source_newer_than


# ---------------------------------------------------------------------------
# Helpers — build a minimal tmp git repo
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git subcommand inside cwd and return the result."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        check=True,
    )


def _setup_repo(tmp_path: Path) -> Path:
    """
    Initialise a fresh git repo at tmp_path with a commit-safe config.
    Returns the repo root path.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    _git(["init"], repo)
    # Required so `git commit` never prompts / fails on identity.
    _git(["config", "user.name", "Test User"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    # Keep tests fast and deterministic regardless of global hooks.
    _git(["config", "commit.gpgSign", "false"], repo)

    return repo


def _commit_file(repo: Path, rel_path: str, content: str = "x") -> str:
    """
    Create a file at rel_path (creating parent dirs), add it, and commit it.
    Returns the ISO-8601 committer timestamp of that commit (for assertions).
    """
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)

    _git(["add", rel_path], repo)
    _git(["commit", "-m", f"add {rel_path}"], repo)

    # Read back the committer timestamp via the same format the predicate uses.
    result = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%cI"],
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        check=True,
    )
    return result.stdout.strip()


def _offset_iso(iso: str, delta: timedelta) -> str:
    """
    Return an ISO-8601 string that is `iso` shifted by `delta`.
    Used to produce "one hour before/after" a known timestamp.
    """
    normalized = iso.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    shifted = dt + delta
    return shifted.isoformat()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNativeSourceNewerThan:

    def test_boot_before_native_commit_returns_true(self, tmp_path: Path):
        """
        Binary booted BEFORE a native-source commit → stale → True.
        The predicate must detect that src-tauri/ changed after the runtime started.
        """
        repo = _setup_repo(tmp_path)
        commit_iso = _commit_file(repo, "src-tauri/foo.rs")

        # Boot stamp is one hour BEFORE the commit.
        boot_iso = _offset_iso(commit_iso, -timedelta(hours=1))

        result = native_source_newer_than(boot_iso, repo)

        assert result is True, (
            f"Expected True (stale) but got False.\n"
            f"  boot_iso   = {boot_iso}\n"
            f"  commit_iso = {commit_iso}"
        )

    def test_boot_after_native_commit_returns_false(self, tmp_path: Path):
        """
        Binary booted AFTER the native-source commit → current → False.
        health=200 is sufficient; no restart needed.
        """
        repo = _setup_repo(tmp_path)
        commit_iso = _commit_file(repo, "src-tauri/bar.rs")

        # Boot stamp is one hour AFTER the commit.
        boot_iso = _offset_iso(commit_iso, +timedelta(hours=1))

        result = native_source_newer_than(boot_iso, repo)

        assert result is False, (
            f"Expected False (fresh) but got True.\n"
            f"  boot_iso   = {boot_iso}\n"
            f"  commit_iso = {commit_iso}"
        )

    def test_only_non_native_commits_returns_false(self, tmp_path: Path):
        """
        Commits exist, but they touch ONLY a non-native path (docs/).
        git log -- src-tauri crates returns empty.
        Fail-safe: return False (no native change → no restart needed).
        """
        repo = _setup_repo(tmp_path)
        commit_iso = _commit_file(repo, "docs/x.md", content="documentation")

        # Boot stamp is one hour BEFORE the docs commit (so any stale
        # detection on native sources would return True — but there are none).
        boot_iso = _offset_iso(commit_iso, -timedelta(hours=1))

        result = native_source_newer_than(boot_iso, repo)

        assert result is False, (
            "Expected False (no native commits → fail-safe) but got True."
        )

    def test_bogus_repo_root_returns_false(self, tmp_path: Path):
        """
        A non-git directory (or a path that doesn't exist) should never raise;
        it must return False (fail-safe).
        """
        non_repo = tmp_path / "not_a_git_repo"
        non_repo.mkdir()  # exists but not a git repo

        result = native_source_newer_than("2020-01-01T00:00:00Z", non_repo)

        assert result is False, (
            "Expected False (non-git dir → fail-safe) but got True or raised."
        )

    def test_nonexistent_path_returns_false(self, tmp_path: Path):
        """A path that doesn't exist at all must also return False, never raise."""
        missing = tmp_path / "does_not_exist"

        result = native_source_newer_than("2020-01-01T00:00:00Z", missing)

        assert result is False

    def test_unparseable_boot_iso_returns_false(self, tmp_path: Path):
        """
        An unparseable boot_iso (garbage string) must return False (fail-safe),
        never raise.
        """
        repo = _setup_repo(tmp_path)
        _commit_file(repo, "src-tauri/c.rs")

        result = native_source_newer_than("not-a-timestamp-!!!", repo)

        assert result is False, (
            "Expected False (bad boot_iso → fail-safe) but got True or raised."
        )

    def test_boot_iso_trailing_z_is_accepted(self, tmp_path: Path):
        """
        Trailing 'Z' in boot_iso must be parsed correctly (Python 3.7–3.10
        fromisoformat does not accept it without normalisation).
        """
        repo = _setup_repo(tmp_path)
        commit_iso = _commit_file(repo, "crates/lib.rs")

        # Use trailing-Z form explicitly for the boot stamp one hour before.
        dt = datetime.fromisoformat(commit_iso.replace("Z", "+00:00"))
        boot_z = (dt - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        result = native_source_newer_than(boot_z, repo)

        assert result is True, (
            f"Expected True (stale; trailing-Z accepted) but got False.\n"
            f"  boot_z     = {boot_z}\n"
            f"  commit_iso = {commit_iso}"
        )

    def test_custom_globs_respected(self, tmp_path: Path):
        """
        With a custom glob list, only the specified paths are checked.
        A commit to src-tauri/ is ignored when globs=['custom-native'].
        """
        repo = _setup_repo(tmp_path)
        commit_iso = _commit_file(repo, "src-tauri/d.rs")

        # Boot stamp is one hour before the src-tauri commit.
        boot_iso = _offset_iso(commit_iso, -timedelta(hours=1))

        # But we only watch 'custom-native' — src-tauri commit is invisible.
        result = native_source_newer_than(boot_iso, repo, globs=["custom-native"])

        assert result is False, (
            "Expected False (custom glob doesn't include src-tauri) but got True."
        )

    def test_equal_timestamps_returns_false(self, tmp_path: Path):
        """
        Boot at the EXACT same second as the commit is treated as 'not stale'
        (strict > comparison; fail-safe at the boundary).
        """
        repo = _setup_repo(tmp_path)
        commit_iso = _commit_file(repo, "src-tauri/e.rs")

        # Use the exact commit timestamp as the boot stamp.
        result = native_source_newer_than(commit_iso, repo)

        assert result is False, (
            "Expected False (boot == commit → not stale) but got True."
        )
