"""Persistence layer for the interview-prep plugin v2.

Manages the ~/.interview-prep/ directory:
    work-log.jsonl      — append-only skill work log
    features.jsonl      — append-only feature-level entries with upsert support
    import-index.jsonl  — content hash registry for idempotent import
    config.json         — user preferences
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_DEFAULT_BASE = Path.home() / ".interview-prep"

# ---------------------------------------------------------------------------
# WorkLogWriter
# ---------------------------------------------------------------------------


class WorkLogWriter:
    """Append-only JSONL log of skill work-log entries."""

    _REQUIRED_FIELDS = frozenset({"skill", "project", "title", "summary", "files_modified"})

    def __init__(self, base_path: Path = _DEFAULT_BASE, auto_commit: bool = True) -> None:
        self._base = base_path
        self._auto_commit = auto_commit
        self._log_file = self._base / "work-log.jsonl"

    def append(self, entry: dict[str, Any]) -> Path:
        """Validate required fields, stamp timestamp, append as JSON line.

        Returns the path to the log file.
        """
        missing = self._REQUIRED_FIELDS - entry.keys()
        if missing:
            raise ValueError(f"Missing required fields: {sorted(missing)}")
        for field in self._REQUIRED_FIELDS:
            if not entry[field]:
                raise ValueError(f"Required field is empty: {field!r}")

        entry["timestamp"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._base.mkdir(parents=True, exist_ok=True)
        with self._log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        if self._auto_commit:
            self._git_commit(f"work-log: {entry.get('title', 'append')}")
        return self._log_file

    def _git_commit(self, message: str) -> None:
        """Stage work-log.jsonl and commit if self._base is a git repo.

        Silently skips when not a git repo. Logs a warning on git failure but
        never raises — a git error must not break the caller.
        """
        if not (self._base / ".git").exists():
            return

        try:
            add = subprocess.run(
                ["git", "add", "work-log.jsonl"],
                capture_output=True,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                cwd=self._base,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            _logger.warning("git add timed out")
            return
        if add.returncode != 0:
            _logger.warning("git add failed: %s", add.stderr.decode(errors="replace"))
            return

        try:
            commit = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                cwd=self._base,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            _logger.warning("git commit timed out")
            return
        if commit.returncode != 0:
            _logger.warning("git commit failed: %s", commit.stderr.decode(errors="replace"))

    def query(
        self,
        skill: str | None = None,
        project: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return entries matching all supplied criteria."""
        if not self._log_file.exists():
            return []

        results: list[dict[str, Any]] = []
        with self._log_file.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                record: dict[str, Any] = json.loads(line)

                ts: str = str(record.get("timestamp", ""))
                if date_from is not None and ts < date_from:
                    continue
                if date_to is not None and ts > date_to:
                    continue
                if skill is not None and record.get("skill") != skill:
                    continue
                if project is not None and record.get("project") != project:
                    continue

                results.append(record)
        return results

    def count(self) -> int:
        """Return total entry count."""
        if not self._log_file.exists():
            return 0
        with self._log_file.open("r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())


# ---------------------------------------------------------------------------
# FeaturesWriter
# ---------------------------------------------------------------------------


class FeaturesWriter:
    """Append-only JSONL log of feature-level entries with UUID, upsert, and query."""

    _REQUIRED_FIELDS = frozenset({"slug", "project", "title", "summary"})

    def __init__(self, base_path: Path = _DEFAULT_BASE, auto_commit: bool = True) -> None:
        self._base = base_path
        self._auto_commit = auto_commit
        self._log_file = self._base / "features.jsonl"

    def append(self, entry: dict[str, Any]) -> Path:
        """Validate, assign UUID if missing, stamp timestamps, append as JSON line.

        If ``entry["id"]`` is provided and matches an existing entry, this acts as
        an upsert — the new record supersedes the old one (both remain in the file,
        but query returns only the latest).

        Returns the path to the log file.
        """
        missing = self._REQUIRED_FIELDS - entry.keys()
        if missing:
            raise ValueError(f"Missing required fields: {sorted(missing)}")

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if "id" not in entry:
            entry["id"] = str(uuid.uuid4())
            entry["created"] = now
        entry["updated"] = now

        self._base.mkdir(parents=True, exist_ok=True)
        with self._log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        if self._auto_commit:
            self._git_commit(f"feature: {entry.get('title', 'append')}")
        return self._log_file

    def query(
        self,
        slug: str | None = None,
        project: str | None = None,
        feature_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return features matching all supplied criteria.

        When multiple records share the same UUID (upsert scenario),
        only the latest (last in file) is returned.
        """
        if not self._log_file.exists():
            return []

        # Read all, deduplicate by id (last wins)
        by_id: dict[str, dict[str, Any]] = {}
        with self._log_file.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                record: dict[str, Any] = json.loads(line)
                by_id[record["id"]] = record

        results: list[dict[str, Any]] = []
        for record in by_id.values():
            if slug is not None and record.get("slug") != slug:
                continue
            if project is not None and record.get("project") != project:
                continue
            if feature_id is not None and record.get("id") != feature_id:
                continue
            results.append(record)
        return results

    def _git_commit(self, message: str) -> None:
        """Stage features.jsonl and commit if self._base is a git repo."""
        if not (self._base / ".git").exists():
            return

        try:
            add = subprocess.run(
                ["git", "add", "features.jsonl"],
                capture_output=True,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                cwd=self._base,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            _logger.warning("git add timed out")
            return
        if add.returncode != 0:
            _logger.warning("git add failed: %s", add.stderr.decode(errors="replace"))
            return

        try:
            commit = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                cwd=self._base,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            _logger.warning("git commit timed out")
            return
        if commit.returncode != 0:
            _logger.warning("git commit failed: %s", commit.stderr.decode(errors="replace"))


# ---------------------------------------------------------------------------
# ImportIndexWriter
# ---------------------------------------------------------------------------


class ImportIndexWriter:
    """Content-hash-based import index for idempotent artifact ingestion."""

    def __init__(self, base_path: Path = _DEFAULT_BASE, auto_commit: bool = True) -> None:
        self._base = base_path
        self._auto_commit = auto_commit
        self._index_file = self._base / "import-index.jsonl"

    @staticmethod
    def compute_hash(file_path: Path) -> str:
        """Compute SHA-256 hash of file contents, prefixed with 'sha256:'."""
        h = hashlib.sha256(file_path.read_bytes()).hexdigest()
        return f"sha256:{h}"

    def add(
        self,
        source_path: str,
        content_hash: str,
        project: str,
        artifact_type: str,
    ) -> dict[str, str]:
        """Add or deduplicate an import entry.

        Returns dict with 'status' key:
          - 'skipped': exact hash already exists for this path
          - 'evolved': same path, different hash → new entry with same UUID
          - 'created': new path + new hash → fresh UUID
        """
        existing = self._load_entries()

        # Check for exact hash match (same path + same hash)
        for entry in existing:
            if entry["source_path"] == source_path and entry["content_hash"] == content_hash:
                return {"status": "skipped", "uuid": entry["uuid"]}

        # Check for evolution (same path, different hash)
        existing_uuid: str | None = None
        for entry in existing:
            if entry["source_path"] == source_path:
                existing_uuid = entry["uuid"]

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry_uuid = existing_uuid or str(uuid.uuid4())

        new_entry: dict[str, str] = {
            "uuid": entry_uuid,
            "source_path": source_path,
            "content_hash": content_hash,
            "imported_at": now,
            "project": project,
            "artifact_type": artifact_type,
        }

        self._base.mkdir(parents=True, exist_ok=True)
        with self._index_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(new_entry) + "\n")

        if self._auto_commit:
            self._git_commit(f"import: {source_path}")

        status = "evolved" if existing_uuid else "created"
        return {"status": status, "uuid": entry_uuid}

    def _load_entries(self) -> list[dict[str, str]]:
        """Load all entries from the index file."""
        if not self._index_file.exists():
            return []
        entries: list[dict[str, str]] = []
        with self._index_file.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                entries.append(json.loads(line))
        return entries

    def has_hash(self, content_hash: str) -> bool:
        """Check if a content hash already exists in the index."""
        return any(entry["content_hash"] == content_hash for entry in self._load_entries())

    def _git_commit(self, message: str) -> None:
        """Stage import-index.jsonl and commit if self._base is a git repo."""
        if not (self._base / ".git").exists():
            return

        try:
            add = subprocess.run(
                ["git", "add", "import-index.jsonl"],
                capture_output=True,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                cwd=self._base,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            _logger.warning("git add timed out")
            return
        if add.returncode != 0:
            _logger.warning("git add failed: %s", add.stderr.decode(errors="replace"))
            return

        try:
            commit = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                cwd=self._base,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            _logger.warning("git commit timed out")
            return
        if commit.returncode != 0:
            _logger.warning("git commit failed: %s", commit.stderr.decode(errors="replace"))


# ---------------------------------------------------------------------------
# ConfigReader
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: dict[str, Any] = {
    "relevance_threshold": 0.7,
    "stale_days": 30,
}


class ConfigReader:
    """Reads user preferences from config.json, returning defaults on absence."""

    def __init__(self, base_path: Path = _DEFAULT_BASE) -> None:
        self._config_file = base_path / "config.json"

    def load(self) -> dict[str, Any]:
        """Return config dict, falling back to defaults when file is missing."""
        if not self._config_file.exists():
            return dict(_DEFAULT_CONFIG)

        with self._config_file.open("r", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)

        return data
