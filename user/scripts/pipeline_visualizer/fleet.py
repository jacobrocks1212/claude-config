"""fleet — the cross-repo shallow read layer (cross-repo-fleet-view).

A PURE READ over script-owned state. This module discovers lazy-enabled repo
roots (SPEC D1), reads each repo's run marker RAW (never `read_run_marker`,
which is delete-on-read at its 24h age gate — D3 forbids any mutation from a
read view), grades a display badge (D3), and builds one shallow row per repo
(D5): queue depths + halt-sentinel *presence* + marker view. No state-script
subprocess is ever spawned here — per-item stage fidelity belongs to the
drill-in's `probe.probe_state`, one click away.

Hard invariants (load-bearing — see SPEC "House invariants honored"):
  - NEVER call ``lazy_core.read_run_marker`` (delete-on-read).
  - NEVER call ``lazy_core.claude_state_dir`` with its default ``create=True``
    (a read view must not create state dirs) — marker paths are composed raw
    from ``lazy_core.repo_key``.
  - NEVER flip ``lazy_core.set_active_repo_root`` (a per-request flip under
    ThreadingHTTPServer is a data race across repos).
  - NEVER write or delete anything. A corrupt marker is flagged
    (``unreadable``) and LEFT ON DISK — reclamation is script-owned.
  - Any per-repo failure degrades to an explicit error row, never a raise —
    a silently-omitted repo is a fleet page lying by omission.

``~/.claude/lazy-repos.json`` schema (D1 — this module is its FIRST consumer;
the file is optional and user-local, never git-tracked):

    {
      "pins":     ["<abs path to repo root>", ...],   // always included
      "excludes": ["<abs path to repo root>", ...]    // removed LAST (wins
    }                                                 //  over every source)

Paths are ``~``-expanded and matched by ``os.path.realpath``. A missing or
malformed file is ignored (fail-open discovery — a broken config must not
blank the fleet page).
"""

from __future__ import annotations

import datetime
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from .probe import read_queue

# D3 badge thresholds. STALE_SECONDS is deliberately the same 24h boundary the
# state scripts use (lazy_core._MARKER_STALE_SECONDS) — the fleet view must not
# invent a second staleness definition. Asserted equal in the test suite.
WARN_SECONDS: float = 2 * 3600          # run-active → run-silent boundary
STALE_SECONDS: float = 24 * 3600        # run-silent → stale-marker boundary

# The fleet aggregate's own TTL (D5): distinct from — and ≥ — the per-repo
# probe cache's DEFAULT_TTL_SECONDS (2.0s).
FLEET_TTL_SECONDS: float = 5.0

_MARKER_FILENAME = "lazy-run-marker.json"

# Halt sentinels whose *presence* (a plain stat, the `receipt_present`
# precedent) marks a queued item as needing attention. Presence, not parsing —
# the authoritative interpretation stays in the state scripts.
_HALT_SENTINELS = (("NEEDS_INPUT.md", "needs-input"), ("BLOCKED.md", "blocked"))


def _repo_key(repo_root) -> Optional[str]:
    """lazy_core.repo_key — the ONE canonical keyed-state-dir derivation.
    Lazily imported (server.py precedent); unimportable → None (fail open:
    the marker simply reads as absent)."""
    try:
        import lazy_core
    except ImportError:
        return None
    return lazy_core.repo_key(str(repo_root))


def _default_repos_base() -> Path:
    return Path.home() / "source" / "repos"


def _default_lazy_repos_path() -> Path:
    return Path.home() / ".claude" / "lazy-repos.json"


def marker_path(repo_root, state_base=None) -> Optional[Path]:
    """Compose the run-marker path for a repo WITHOUT creating anything.

    Explicit ``state_base`` → the production keyed layout
    ``<state_base>/<repo_key>/lazy-run-marker.json`` (hermetic tests).
    ``state_base=None`` → honor ``LAZY_STATE_DIR`` exactly as
    ``lazy_core.claude_state_dir`` does (a FLAT, un-keyed dir), else the real
    ``~/.claude/state/<repo_key>/`` keyed layout. Returns None when the key
    cannot be derived (lazy_core unimportable).
    """
    if state_base is None:
        override = os.environ.get("LAZY_STATE_DIR")
        if override:
            return Path(override) / _MARKER_FILENAME
        state_base = Path.home() / ".claude" / "state"
    key = _repo_key(repo_root)
    if key is None:
        return None
    return Path(state_base) / key / _MARKER_FILENAME


def read_marker_raw(repo_root, state_base=None) -> Optional[dict]:
    """Raw run-marker read: parse the file, NEVER delete, NEVER write.

    Returns the marker dict; ``None`` when absent; ``{"unreadable": True,
    "error": <msg>}`` for a corrupt/unparseable file (which — unlike
    ``lazy_core.read_run_marker`` — is LEFT ON DISK). Follows the
    ``write_run_checkpoint`` raw-read precedent.
    """
    path = marker_path(repo_root, state_base=state_base)
    if path is None:
        return None
    try:
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"unreadable": True, "error": f"marker unreadable: {exc}"}
    if not isinstance(raw, dict):
        return {"unreadable": True, "error": "marker root is not a JSON object"}
    return raw


def _started_epoch(marker: dict) -> Optional[float]:
    """Parse the marker's ISO-8601 UTC 'Z' started_at (the exact format
    lazy_core writes); unparseable → None (graded stale, age unknown)."""
    started = marker.get("started_at")
    if not isinstance(started, str):
        return None
    try:
        dt = datetime.datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return (dt - datetime.datetime(1970, 1, 1)).total_seconds()


def marker_view(raw: Optional[dict], now: Optional[float] = None) -> dict:
    """Grade a raw marker into the D3 display view.

    Badges: ``idle`` (no marker) / ``run-active`` (age < 2h) / ``run-silent``
    (2h ≤ age ≤ 24h — live or wedged, look closer) / ``stale-marker``
    (age > 24h, the script-aligned presumed-dead boundary; also any marker
    whose age cannot be determined — unreadable file or unparseable
    ``started_at``, shown with ``age_seconds: None``). Age is always carried.
    """
    if raw is None:
        return {"present": False, "age_seconds": None, "badge": "idle",
                "pipeline": None, "work_branch": None}
    epoch = None if raw.get("unreadable") else _started_epoch(raw)
    if epoch is None:
        age = None
        badge = "stale-marker"
    else:
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        age = now - epoch
        if age > STALE_SECONDS:
            badge = "stale-marker"
        elif age >= WARN_SECONDS:
            badge = "run-silent"
        else:
            badge = "run-active"
    return {
        "present": True,
        "age_seconds": age,
        "badge": badge,
        "pipeline": raw.get("pipeline"),
        "work_branch": raw.get("work_branch"),
    }


def marker_fresh_present(repo_root, state_base=None,
                         now: Optional[float] = None) -> bool:
    """True iff a fresh (< 24h) marker is present — the fleet-mode substitute
    for ``server._run_marker_present``. Same verdicts as
    ``lazy_core.read_run_marker`` for the presence/age axes (a corrupt marker
    reads as not-fresh), but race-free across threads (no
    ``set_active_repo_root`` flip) and NEVER deleting."""
    view = marker_view(read_marker_raw(repo_root, state_base=state_base),
                       now=now)
    return view["badge"] in ("run-active", "run-silent")


def slugify(name: str) -> str:
    """Kebab-case a repo basename into a URL slug; never empty (D7)."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    return slug or "repo"


def assign_slugs(roots) -> dict:
    """Map each repo root → its URL slug (D7): basename slug when unique; on a
    basename collision EVERY collider gets a short ``repo_key`` suffix (stable
    regardless of discovery order). Server-owned — `repo_key` derivation never
    leaves Python."""
    roots = [str(r) for r in roots]
    by_slug: dict = {}
    for root in roots:
        by_slug.setdefault(slugify(Path(root).name), []).append(root)
    out = {}
    for slug, members in by_slug.items():
        if len(members) == 1:
            out[members[0]] = slug
        else:
            for i, root in enumerate(members):
                key = _repo_key(root)
                suffix = key[:8] if key else str(i)
                out[root] = f"{slug}-{suffix}"
    return out


def _queue_summary(pipeline_dir: Path) -> dict:
    """Shallow per-pipeline summary: queue depth + halt-sentinel presence per
    queued item (stat of NEEDS_INPUT.md / BLOCKED.md in the item's dir,
    resolved the same way probe._item_dir falls back:
    ``<pipeline_dir>/<spec_dir or id>``)."""
    entries = read_queue(pipeline_dir / "queue.json")
    halts = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("id")
        if not item_id:
            continue
        item_dir = pipeline_dir / (entry.get("spec_dir") or item_id)
        for filename, kind in _HALT_SENTINELS:
            try:
                present = (item_dir / filename).exists()
            except OSError:
                present = False
            if present:
                halts.append({"id": item_id, "kind": kind})
    return {"depth": len(entries), "halts": halts}


def fleet_row(repo_root, slug: Optional[str] = None,
              now: Optional[float] = None, state_base=None) -> dict:
    """One shallow fleet row (D5). Reads: queue.json ×2, the raw marker, and
    per-item sentinel stats. Zero subprocesses. Any internal failure degrades
    to an explicit error row (shape preserved, ``error`` set)."""
    repo_root = Path(repo_root)
    name = repo_root.name
    row = {
        "slug": slug if slug is not None else slugify(name),
        "repo_root": str(repo_root),
        "name": name,
        "marker": marker_view(None),
        "features": {"depth": 0, "halts": []},
        "bugs": {"depth": 0, "halts": []},
        "lazy_queue_doc": False,
        "lazy_queue_url": None,
        "error": None,
    }
    try:
        row["marker"] = marker_view(
            read_marker_raw(repo_root, state_base=state_base), now=now)
        row["features"] = _queue_summary(repo_root / "docs" / "features")
        row["bugs"] = _queue_summary(repo_root / "docs" / "bugs")
        row["lazy_queue_doc"] = (repo_root / "LAZY_QUEUE.md").exists()
        if row["lazy_queue_doc"]:
            row["lazy_queue_url"] = lazy_queue_url(repo_root)
    except Exception as exc:  # noqa: BLE001 — error ROW, never a crashed poll
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def _read_repos_config(lazy_repos_path) -> dict:
    """Read ~/.claude/lazy-repos.json (schema in the module docstring).
    Missing/malformed → empty config (fail-open discovery)."""
    p = Path(lazy_repos_path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {"pins": [], "excludes": []}
    if not isinstance(data, dict):
        return {"pins": [], "excludes": []}
    def _paths(key):
        vals = data.get(key, [])
        if not isinstance(vals, list):
            return []
        return [os.path.expanduser(str(v)) for v in vals if isinstance(v, str)]
    return {"pins": _paths("pins"), "excludes": _paths("excludes")}


def _scan_marker_roots(state_base) -> list:
    """Scan a state base for run markers and return their recorded
    ``repo_root`` fields (raw reads — the only way back from a one-way
    ``repo_key`` subdir to a root). Handles both the production keyed layout
    (``<base>/<key>/lazy-run-marker.json``) and a flat ``LAZY_STATE_DIR``-style
    dir (``<base>/lazy-run-marker.json``). Never deletes."""
    base = Path(state_base)
    roots = []
    candidates = []
    try:
        if (base / _MARKER_FILENAME).exists():
            candidates.append(base / _MARKER_FILENAME)
        if base.is_dir():
            for sub in base.iterdir():
                p = sub / _MARKER_FILENAME
                if p.exists():
                    candidates.append(p)
    except OSError:
        return roots
    for p in candidates:
        try:
            marker = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue  # unreadable marker: not discoverable, still not deleted
        if isinstance(marker, dict):
            root = marker.get("repo_root")
            if isinstance(root, str) and root:
                roots.append(root)
    return roots


def discover_repos(repos_base=None, lazy_repos_path=None,
                   state_base=None) -> list:
    """D1 discovery: registry convention ∪ pins ∪ live-marker roots, deduped
    by realpath, ``excludes`` applied LAST (an excluded repo never renders,
    whatever source named it). Returns sorted realpath strings.

    Sources:
      a) ``<repos_base>/*/docs/{features,bugs}/queue.json`` glob
         (default ``~/source/repos`` — the mobile-queue-control convention);
      b) ``lazy-repos.json`` ``pins`` (default ``~/.claude/lazy-repos.json``);
      c) ``repo_root`` recorded in run markers under ``state_base``
         (default: ``LAZY_STATE_DIR`` if set, else ``~/.claude/state``) —
         covers a live run in a nonstandard root.
    """
    if repos_base is None:
        repos_base = _default_repos_base()
    if lazy_repos_path is None:
        lazy_repos_path = _default_lazy_repos_path()
    if state_base is None:
        state_base = os.environ.get("LAZY_STATE_DIR") or (
            Path.home() / ".claude" / "state")

    candidates = []
    base = Path(repos_base)
    try:
        for pattern in ("*/docs/features/queue.json", "*/docs/bugs/queue.json"):
            for q in base.glob(pattern):
                candidates.append(str(q.parents[2]))
    except OSError:
        pass
    config = _read_repos_config(lazy_repos_path)
    candidates.extend(config["pins"])
    candidates.extend(_scan_marker_roots(state_base))

    excluded = {os.path.realpath(p) for p in config["excludes"]}
    seen = set()
    result = []
    for c in candidates:
        real = os.path.realpath(c)
        if real in seen or real in excluded:
            continue
        seen.add(real)
        result.append(real)
    return sorted(result)


# ---------------------------------------------------------------------------
# Phase 4 — aggregation + LAZY_QUEUE.md GitHub-link derivation
# ---------------------------------------------------------------------------

def lazy_queue_url(repo_root) -> Optional[str]:
    """GitHub blob URL for the repo's committed LAZY_QUEUE.md, derived from
    PLAIN FILE READS only (no git subprocess on the shallow poll):
    ``.git/config`` → origin URL (https or ssh, normalized) and ``.git/HEAD``
    → branch. A worktree ``.git`` *file* (``gitdir: …``) is followed one level
    for HEAD. Any parse failure → None (no link, never an error)."""
    repo_root = Path(repo_root)
    try:
        if not (repo_root / "LAZY_QUEUE.md").exists():
            return None
        git = repo_root / ".git"
        git_dir = git
        if git.is_file():
            first = git.read_text(encoding="utf-8").strip()
            if not first.startswith("gitdir:"):
                return None
            git_dir = Path(first[len("gitdir:"):].strip())
            if not git_dir.is_absolute():
                git_dir = repo_root / git_dir
        # config lives in the COMMON dir for worktrees (…/.git), which is the
        # gitdir's grandparent for the standard worktrees/<name> layout.
        config_path = git_dir / "config"
        if not config_path.exists() and git_dir.name != ".git":
            common = git_dir.parent.parent
            if (common / "config").exists():
                config_path = common / "config"
        origin_url = _origin_url(config_path)
        if origin_url is None:
            return None
        branch = _head_branch(git_dir / "HEAD")
        if branch is None:
            return None
        return f"{origin_url}/blob/{branch}/LAZY_QUEUE.md"
    except OSError:
        return None


def _origin_url(config_path: Path) -> Optional[str]:
    """Extract + normalize [remote "origin"] url from a git config file.
    Supports https://github.com/o/r(.git) and git@github.com:o/r(.git)."""
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return None
    in_origin = False
    url = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_origin = stripped.replace('"', "").replace(" ", "") == "[remoteorigin]"
            continue
        if in_origin and stripped.startswith("url"):
            _, _, value = stripped.partition("=")
            url = value.strip()
            break
    if not url:
        return None
    m = re.match(r"^git@([^:]+):(.+?)(?:\.git)?$", url)
    if m:
        return f"https://{m.group(1)}/{m.group(2)}"
    m = re.match(r"^(https?://[^/]+/.+?)(?:\.git)?/?$", url)
    if m:
        return m.group(1)
    return None


def _head_branch(head_path: Path) -> Optional[str]:
    """Branch name from .git/HEAD (``ref: refs/heads/<branch>``); detached or
    unreadable → None."""
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    prefix = "ref: refs/heads/"
    if head.startswith(prefix):
        return head[len(prefix):] or None
    return None


def fleet_payload(repos_base=None, lazy_repos_path=None, state_base=None,
                  now: Optional[float] = None, max_workers: int = 8) -> dict:
    """The /api/fleet aggregate: discover → shallow rows in parallel
    (stdlib ThreadPoolExecutor — the fan-out is stat-bound, D5), sorted by
    slug. Zero state-script subprocesses; a broken repo yields an error row."""
    roots = discover_repos(repos_base=repos_base,
                           lazy_repos_path=lazy_repos_path,
                           state_base=state_base)
    slugs = assign_slugs(roots)
    rows = []
    if roots:
        workers = max(1, min(max_workers, len(roots)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(
                lambda root: fleet_row(root, slug=slugs[root], now=now,
                                       state_base=state_base),
                roots))
    rows.sort(key=lambda r: r["slug"])
    server_time = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    return {"repos": rows, "fleet_ttl_seconds": FLEET_TTL_SECONDS,
            "server_time": server_time}
