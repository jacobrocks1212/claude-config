#!/usr/bin/env python3
"""
work-status.py -- Read-only cross-source terminal dashboard.

Aggregates artifacts from docs/work/ (ado-mirror.json, materialized.json,
leases.json) and docs/features/queue.json / docs/bugs/queue.json, then renders
a five-panel terminal summary:

  1. My queue     — items from feature/bug queue.json assigned to me
  2. In flight    — active leases from leases.json
  3. My ADO inbox — mirror WIs assigned to me that are NOT yet materialized
  4. Team         — teammates' WIs with pr/prStatus/autotestStatus from mirror
  5. Pool & sync  — mirror freshness, stale-upstream counts, missing artifacts

Optional: --markdown writes <repo_root>/docs/work/DASHBOARD.md.

This script NEVER mutates any artifact except (optionally) DASHBOARD.md.

Dependencies: stdlib only (no third-party requirements for --test).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any


DEFAULT_BOARD_COLUMNS = ["New", "Next", "In Progress", "PR Review", "Ready for Testing", "Reviewing", "Merged"]


# ---------------------------------------------------------------------------
# Infrastructure helpers
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically (temp file in same dir + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> Any:
    """Read and parse a JSON file; return None if missing or malformed."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _scan_stale_upstream(base: Path) -> list[Path]:
    """Recursively find all STALE_UPSTREAM.md files under base."""
    if not base.exists():
        return []
    result: list[Path] = []
    for root, _dirs, files in os.walk(base):
        for fname in files:
            if fname == "STALE_UPSTREAM.md":
                result.append(Path(root) / fname)
    return result


# ---------------------------------------------------------------------------
# Pure stub functions (implementation agent fills these in)
# ---------------------------------------------------------------------------

def load_sources(repo_root: Path) -> dict:
    """Load all dashboard artifacts from repo_root with graceful degradation.

    Reads (all optional — missing file yields sensible empty/None, never raises):
      - docs/work/ado-mirror.json  -> sources["mirror"]    (dict or None)
      - docs/features/queue.json   -> sources["feat_queue"] (dict or None)
      - docs/bugs/queue.json       -> sources["bug_queue"]  (dict or None)
      - docs/work/materialized.json-> sources["materialized"] (dict or None)
      - docs/work/leases.json      -> sources["leases"]     (dict or None)
      - stale marker files         -> sources["stale_paths"] (list[Path])

    Returns a dict with exactly these keys, plus sources["repo_root"] = repo_root.
    Never raises; bad files are silently treated as None.
    """
    work_dir = repo_root / "docs" / "work"
    feat_dir = repo_root / "docs" / "features"
    bug_dir = repo_root / "docs" / "bugs"

    stale_paths: list[Path] = []
    stale_paths.extend(_scan_stale_upstream(feat_dir))
    stale_paths.extend(_scan_stale_upstream(bug_dir))

    return {
        "repo_root": repo_root,
        "mirror": _read_json(work_dir / "ado-mirror.json"),
        "feat_queue": _read_json(feat_dir / "queue.json"),
        "bug_queue": _read_json(bug_dir / "queue.json"),
        "materialized": _read_json(work_dir / "materialized.json"),
        "leases": _read_json(work_dir / "leases.json"),
        "stale_paths": stale_paths,
    }


# Identities that represent the current user in a WI's assignedTo. ADO WIQL
# uses the literal "@Me", but the mirror stores resolved display names, so the
# display name and email must match too (compared case-insensitively).
_MY_IDENTITIES = frozenset({"@me", "jacob madsen", "jacob@cognitoforms.com"})


def _is_mine(assigned_to: str | None) -> bool:
    """Return True if the assignedTo value represents the current user."""
    if assigned_to is None:
        return False
    return assigned_to.strip().lower() in _MY_IDENTITIES


def render_dashboard(
    sources: dict,
    current_branch: str | None = None,
    board_columns: list[str] | None = None,
) -> str:
    """Build the board-centric terminal dashboard text from pre-loaded sources.

    Panels (each separated by a blank line and a header line):
      POSEIDON BOARD — story-level cards grouped by working column (mirrors the
                       markdown board: New backlog and portfolio parents excluded)
      MY QUEUE     — queue.json items assigned to me (feat + bug)
      IN FLIGHT    — active leases
      MY ADO INBOX — mirror WIs assigned to current user, not yet materialized
      POOL & SYNC  — mirror freshness (syncedAt), stale-upstream count, missing artifacts

    Graceful degradation: absent sources show informational text (e.g.
    "No leases" when leases.json missing) rather than raising.

    Returns a single string suitable for print().
    """
    if board_columns is None:
        board_columns = DEFAULT_BOARD_COLUMNS
    lines: list[str] = []

    mirror: dict | None = sources.get("mirror")
    feat_queue: dict | None = sources.get("feat_queue")
    bug_queue: dict | None = sources.get("bug_queue")
    leases: dict | None = sources.get("leases")
    stale_paths: list[Path] = sources.get("stale_paths") or []

    work_items: list[dict] = []
    if mirror and isinstance(mirror.get("workItems"), list):
        work_items = mirror["workItems"]

    # Build a lookup from wi_id -> mirror WI for queue cross-referencing
    wi_by_id: dict[int, dict] = {int(wi["id"]): wi for wi in work_items}

    # Determine what "self PR" is linked from the current branch
    # branch pattern: p/<wi_id>-...  -> match PR from mirror WI's linkedPRs
    self_pr: dict | None = None
    branch_wi_id: int | None = None
    if current_branch:
        m = re.match(r"^p/(\d+)-", current_branch)
        if m:
            branch_wi_id = int(m.group(1))
            wi = wi_by_id.get(branch_wi_id)
            if wi:
                linked_prs = wi.get("linkedPRs") or []
                self_pr = match_self_pr(current_branch, linked_prs)

    # ------------------------------------------------------------------
    # Panel 0: POSEIDON BOARD — story-level cards grouped by working column.
    # New backlog, portfolio parents, and terminal-state ghosts are excluded
    # (see on_board_cards), mirroring the markdown board.
    # ------------------------------------------------------------------
    lines.append("=== POSEIDON BOARD ===")
    working_columns = [c for c in board_columns if c.strip().lower() != "new"]
    board_buckets = on_board_cards(work_items, working_columns)
    board_total = sum(len(v) for v in board_buckets.values())
    if mirror is None:
        lines.append("  Mirror not yet initialized")
    elif board_total == 0:
        lines.append("  (no cards on the board)")
    else:
        for col in working_columns:
            items = board_buckets.get(col) or []
            if not items:
                continue
            lines.append(f"  {col} ({len(items)})")
            for wi in items:
                wi_id = wi.get("id", "?")
                title = wi.get("title", "(no title)")
                assigned = wi.get("assignedTo") or "Unassigned"
                parts = [f"    [{wi_id}] {title}  assigned={assigned}"]
                pr_nums = [
                    str(lp.get("prNumber"))
                    for lp in (wi.get("linkedPRs") or [])
                    if lp.get("prNumber")
                ]
                if pr_nums:
                    parts.append(f"  PR#{','.join(pr_nums)}")
                pr_status = wi.get("prStatus") or ""
                if pr_status:
                    parts.append(f"  prStatus={pr_status}")
                autotest = wi.get("autotestStatus") or ""
                if autotest:
                    parts.append(f"  autotestStatus={autotest}")
                lines.append("".join(parts))

    lines.append("")

    # ------------------------------------------------------------------
    # Panel 1: MY QUEUE
    # ------------------------------------------------------------------
    lines.append("=== MY QUEUE ===")
    queue_items: list[dict] = []
    for q in [feat_queue, bug_queue]:
        if q and isinstance(q.get("items"), list):
            queue_items.extend(q["items"])

    if not queue_items:
        lines.append("  (no items in queue)")
    else:
        for item in queue_items:
            wi_id = item.get("wi_id")
            title = item.get("title", "(no title)")
            priority = item.get("priority", "")
            pr_info = ""
            # If this queue item matches the current branch's WI, surface the PR
            if wi_id is not None and wi_id == branch_wi_id and self_pr is not None:
                pr_num = self_pr.get("prNumber")
                pr_repo = self_pr.get("repo", "")
                pr_info = f"  -> PR #{pr_num} ({pr_repo})"
            lines.append(f"  [{wi_id}] {title} (priority: {priority}){pr_info}")

    lines.append("")

    # ------------------------------------------------------------------
    # Panel 2: IN FLIGHT
    # ------------------------------------------------------------------
    lines.append("=== IN FLIGHT ===")
    if leases is None:
        lines.append("  No leases yet (leases.json not found)")
    else:
        lease_list = leases.get("leases") or []
        if not lease_list:
            lines.append("  No active leases")
        else:
            for lease in lease_list:
                wi_id = lease.get("wi_id", "?")
                branch = lease.get("branch", "?")
                started = lease.get("startedAt", "?")
                worker = lease.get("worker_pid", lease.get("slot", "?"))
                stage = lease.get("stage", "")
                heartbeat = lease.get("heartbeat", "")
                stale_flag = " [STALE]" if lease.get("stale") else ""
                parts = [f"  [{wi_id}] {branch}  started={started}"]
                if worker != "?":
                    parts.append(f"  worker={worker}")
                if stage:
                    parts.append(f"  stage={stage}")
                if heartbeat:
                    parts.append(f"  heartbeat={heartbeat}")
                lines.append("".join(parts) + stale_flag)

    lines.append("")

    # ------------------------------------------------------------------
    # Panel 3: MY ADO INBOX
    # ------------------------------------------------------------------
    lines.append("=== MY ADO INBOX ===")
    if mirror is None:
        lines.append("  Mirror not yet initialized")
    else:
        my_wis = [
            wi for wi in work_items
            if _is_mine(wi.get("assignedTo"))
            and not wi.get("materialized", False)
            and (wi.get("state") or "").strip().lower() not in _TERMINAL_STATES
        ]
        if not my_wis:
            lines.append("  (no unmaterilaized WIs assigned to you)")
        else:
            for wi in my_wis:
                wi_id = wi.get("id", "?")
                title = wi.get("title", "(no title)")
                state = wi.get("state", "?")
                url = wi.get("url", "")
                pr = wi.get("pr") or ""
                pr_status = wi.get("prStatus") or ""
                pr_info = f"  PR: {pr_status}" if pr_status else ""
                lines.append(f"  [{wi_id}] {title}  state={state}{pr_info}")
                if url:
                    lines.append(f"    {url}")

    lines.append("")

    # ------------------------------------------------------------------
    # Panel 5: POOL & SYNC
    # ------------------------------------------------------------------
    lines.append("=== POOL & SYNC ===")
    if mirror is None:
        lines.append("  Mirror not yet initialized")
    else:
        synced_at = mirror.get("syncedAt", "(unknown)")
        lines.append(f"  Mirror synced at: {_fmt_local(synced_at)}")
        lines.append(f"  Work items: {len(work_items)}")
        lines.append(f"  Stale upstream: {len(stale_paths)} marker(s)")
        if stale_paths:
            for p in stale_paths:
                lines.append(f"    {p}")

    # Collect missing-artifact notes
    missing: list[str] = []
    if feat_queue is None:
        missing.append("docs/features/queue.json")
    if bug_queue is None:
        missing.append("docs/bugs/queue.json")
    if leases is None:
        missing.append("docs/work/leases.json")
    if missing:
        lines.append("  Missing artifacts: " + ", ".join(missing))

    return "\n".join(lines)


def match_self_pr(branch: str, linked_prs: list[dict]) -> dict | None:
    """Apply regex ^p/(\\d+)- to branch name; find the PR in linked_prs whose
    prNumber matches the captured group.  Return the matching PR dict or None.

    Args:
        branch:     git branch name, e.g. "p/123-add-feature"
        linked_prs: list of dicts with at least {"prNumber": int, "repo": str}

    Returns:
        The matching linked_pr dict ({"prNumber": N, "repo": "..."}) or None.
    """
    m = re.match(r"^p/(\d+)-", branch)
    if not m:
        return None
    pr_number = int(m.group(1))
    for pr in linked_prs:
        if pr.get("prNumber") == pr_number:
            return pr
    return None


_TERMINAL_STATES = frozenset({"closed", "removed", "done", "resolved"})

# Portfolio backlog levels carry their own board columns (on the Features/Epics
# board) whose names can collide with the Stories board (e.g. "In Progress").
# Excluding them keeps the Poseidon Board view to actual story/bug/defect cards.
_PORTFOLIO_TYPES = frozenset({"Feature", "Epic", "Objective"})


def on_board_cards(
    work_items: list[dict],
    working_columns: list[str],
) -> dict[str, list[dict]]:
    """Group story-level cards by their board column.

    A card qualifies when its boardColumn is one of working_columns, its type is
    not a portfolio level (Feature/Epic/Objective), and its state is not terminal
    (guards against stale board columns left on closed items). Returns an ordered
    dict keyed by working_columns; empty columns map to empty lists.
    """
    buckets: dict[str, list[dict]] = {c: [] for c in working_columns}
    allowed = set(working_columns)
    for wi in work_items:
        col = wi.get("boardColumn") or ""
        if col not in allowed:
            continue
        if (wi.get("type") or "") in _PORTFOLIO_TYPES:
            continue
        if (wi.get("state") or "").strip().lower() in _TERMINAL_STATES:
            continue
        buckets[col].append(wi)
    return buckets


def filter_recent_team(
    team_wis: list[dict],
    synced_at: str,
    window_days: int = 5,
) -> tuple[list[dict], int]:
    """Keep WIs that are still active, plus terminal-state WIs changed within
    window_days of synced_at. Returns (kept, hidden_count).

    'now' reference is synced_at (the mirror timestamp) — deterministic, no clock reads.
    Terminal states (case-insensitive): Closed, Removed, Done, Resolved.
    If synced_at is missing/unparseable, return (team_wis, 0) — graceful, hide nothing.
    A WI with a missing/unparseable changedDate that is terminal is treated as OLD (hidden).
    """
    if not synced_at:
        return (team_wis, 0)

    try:
        synced_dt = datetime.datetime.fromisoformat(synced_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return (team_wis, 0)

    cutoff = synced_dt - datetime.timedelta(days=window_days)

    kept: list[dict] = []
    hidden = 0
    for wi in team_wis:
        state = (wi.get("state") or "").strip().lower()
        if state not in _TERMINAL_STATES:
            kept.append(wi)
            continue
        # Terminal state — keep only if recently changed
        changed_raw = wi.get("changedDate") or ""
        try:
            changed_dt = datetime.datetime.fromisoformat(
                changed_raw.replace("Z", "+00:00")
            )
            if changed_dt >= cutoff:
                kept.append(wi)
            else:
                hidden += 1
        except (ValueError, AttributeError):
            # Missing/unparseable changedDate on a terminal WI → treat as old
            hidden += 1

    return (kept, hidden)


# Board columns that represent completed work (vs. the in-flight working
# columns). ADO stamps closed items with boardColumn "Closed" and merged-but-
# open items with "Merged"; both are surfaced in the Recently Completed bucket.
_COMPLETED_COLUMNS = frozenset({"Merged", "Closed"})


def recently_completed_cards(
    work_items: list[dict],
    synced_at: str,
    window_hours: int = 24,
) -> list[dict]:
    """Return non-portfolio cards in a completed board column (Merged/Closed)
    that changed within window_hours of synced_at, most-recent first.

    'now' reference is synced_at (the mirror timestamp) — deterministic, no clock
    reads, consistent with filter_recent_team. Returns [] if synced_at is missing
    or unparseable. Cards with a missing/unparseable changedDate are excluded.
    """
    if not synced_at:
        return []
    try:
        synced_dt = datetime.datetime.fromisoformat(synced_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return []

    cutoff = synced_dt - datetime.timedelta(hours=window_hours)
    scored: list[tuple[datetime.datetime, dict]] = []
    for wi in work_items:
        if (wi.get("type") or "") in _PORTFOLIO_TYPES:
            continue
        if (wi.get("boardColumn") or "") not in _COMPLETED_COLUMNS:
            continue
        try:
            changed_dt = datetime.datetime.fromisoformat(
                (wi.get("changedDate") or "").replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            continue
        if changed_dt >= cutoff:
            scored.append((changed_dt, wi))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [wi for _, wi in scored]


def _escape_md_pipe(text: str) -> str:
    """Escape pipe characters in text so they don't break Markdown tables."""
    return text.replace("|", r"\|")


# Base for constructing an ADO work-item edit URL when a mirror record's own
# `url` is absent (e.g. queue/lease items that aren't hydrated from ADO).
_ADO_EDIT_BASE = (
    "https://dev.azure.com/cognitoforms/"
    "54d9f307-1306-430c-b206-1a55b294a94b/_workitems/edit/"
)


def _wi_link(wi_id, url: str | None = None) -> str:
    """Render a work-item id as a Markdown link to the item in ADO.

    Prefers the record's own `url`; falls back to the canonical edit URL built
    from the id. Returns "" for a missing id so table cells stay empty.
    """
    if wi_id is None or wi_id == "":
        return ""
    href = url or f"{_ADO_EDIT_BASE}{wi_id}"
    return f"[{wi_id}]({href})"


# GitHub repo backing linked PRs when a record omits its own repo slug.
_DEFAULT_GH_REPO = "cognitoforms/cognito"


def _pr_link(pr_number, repo: str | None = None) -> str:
    """Render a PR number as a Markdown link to the pull request on GitHub."""
    slug = (repo or _DEFAULT_GH_REPO).strip("/")
    return f"[#{pr_number}](https://github.com/{slug}/pull/{pr_number})"


def _fmt_local(ts: str, tz: datetime.tzinfo | None = None) -> str:
    """Format a UTC ISO-8601 timestamp ('...Z') as a friendly local time.

    Renders as 'dd/mm at H:MM AM/PM' in the machine's local timezone (tz=None
    uses the system tz, so it adapts to DST and timezone changes automatically).
    Returns the input unchanged if it is empty or can't be parsed.
    """
    if not ts:
        return ts
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ts
    local = dt.astimezone(tz)
    hour12 = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{local.strftime('%d/%m')} at {hour12}:{local.strftime('%M')} {ampm}"


def order_board(wis: list[dict], board_columns: list[str]) -> "OrderedDict[str, list]":
    """Bucket WIs into an ordered mapping keyed by board_columns + '(no column)'.

    Keys are always exactly [*board_columns, "(no column)"] in that order, even
    when a bucket is empty.  A WI whose boardColumn is missing, None, "", or not
    in board_columns goes into "(no column)".  Input order within each bucket is
    preserved.  No WI is ever dropped.
    """
    result: OrderedDict[str, list] = OrderedDict()
    for col in board_columns:
        result[col] = []
    result["(no column)"] = []

    column_set = set(board_columns)
    for wi in wis:
        col = wi.get("boardColumn")
        if col and col in column_set:
            result[col].append(wi)
        else:
            result["(no column)"].append(wi)

    return result


def group_by_feature(
    team_wis: list[dict],
    active_feature_id: int | None,
    mirror_index: dict,
) -> list[dict]:
    """Group WIs by their root feature via parentId chain traversal.

    Attribution algorithm per WI:
      - No parentId → orphan (feature_id None).
      - Walk the parentId chain through mirror_index; if the active_feature_id is
        encountered, attribute to it.  Otherwise attribute to the topmost reachable
        known ancestor (chain[-1]).  If the immediate parent is absent from
        mirror_index, attribute as orphan.

    Output order:
      1. Active feature group FIRST (included even with zero WIs) when
         active_feature_id is not None.
      2. All other feature groups with >=1 WI, sorted ascending by feature_id.
      3. Orphan group LAST (feature_id=None, title="(no parent)") only if >=1 orphan.

    Title resolution: mirror_index[fid]["title"] if fid in mirror_index, else
    "Feature {fid}".
    """
    # Buckets: feature_id -> list[wi]
    feature_buckets: dict[int | None, list] = {}
    if active_feature_id is not None:
        feature_buckets[active_feature_id] = []

    for wi in team_wis:
        pid = wi.get("parentId")
        if pid is None:
            # No parent → orphan
            feature_buckets.setdefault(None, []).append(wi)
            continue

        # Walk the chain
        cur: int | None = pid
        visited: set = set()
        chain: list = []
        attributed: int | None = None

        while cur is not None and cur in mirror_index and cur not in visited:
            visited.add(cur)
            chain.append(cur)
            if active_feature_id is not None and cur == active_feature_id:
                attributed = active_feature_id
                break
            cur = mirror_index[cur].get("parentId")

        if attributed is not None:
            # Rolled up to active feature
            feature_buckets[active_feature_id].append(wi)  # type: ignore[index]
        elif chain:
            # Topmost reachable known ancestor
            root_fid = chain[-1]
            feature_buckets.setdefault(root_fid, []).append(wi)
        else:
            # Immediate parent absent from mirror_index → orphan
            feature_buckets.setdefault(None, []).append(wi)

    # Build output list
    groups: list[dict] = []

    def _title(fid: int) -> str:
        entry = mirror_index.get(fid)
        if entry:
            return entry.get("title") or f"Feature {fid}"
        return f"Feature {fid}"

    # 1. Active feature group first
    if active_feature_id is not None:
        groups.append({
            "feature_id": active_feature_id,
            "title": _title(active_feature_id),
            "wis": feature_buckets.get(active_feature_id, []),
        })

    # 2. Other feature groups (>=1 WI), sorted by feature_id ascending
    other_fids = sorted(
        fid for fid in feature_buckets
        if fid is not None and fid != active_feature_id and feature_buckets[fid]
    )
    for fid in other_fids:
        groups.append({
            "feature_id": fid,
            "title": _title(fid),
            "wis": feature_buckets[fid],
        })

    # 3. Orphan group last (only if >=1 orphan)
    orphans = feature_buckets.get(None, [])
    if orphans:
        groups.append({
            "feature_id": None,
            "title": "(no parent)",
            "wis": orphans,
        })

    return groups


def render_markdown(
    sources: dict,
    current_branch: str | None = None,
    *,
    all_team: bool = False,
    board_columns: list[str] | None = None,
    active_feature_id: int | None = None,
) -> str:
    """Render the five-panel dashboard as GitHub-flavored Markdown.

    Produces real GFM (tables, headers) rather than the terminal-style text
    from render_dashboard.  Data-selection logic mirrors render_dashboard exactly
    (mine vs team via _is_mine, branch→PR via match_self_pr, degradation messages).
    """
    if board_columns is None:
        board_columns = DEFAULT_BOARD_COLUMNS
    lines: list[str] = []

    mirror: dict | None = sources.get("mirror")
    feat_queue: dict | None = sources.get("feat_queue")
    bug_queue: dict | None = sources.get("bug_queue")
    leases: dict | None = sources.get("leases")
    stale_paths: list[Path] = sources.get("stale_paths") or []

    work_items: list[dict] = []
    if mirror and isinstance(mirror.get("workItems"), list):
        work_items = mirror["workItems"]

    wi_by_id: dict[int, dict] = {int(wi["id"]): wi for wi in work_items}

    self_pr: dict | None = None
    branch_wi_id: int | None = None
    if current_branch:
        m = re.match(r"^p/(\d+)-", current_branch)
        if m:
            branch_wi_id = int(m.group(1))
            wi = wi_by_id.get(branch_wi_id)
            if wi:
                linked_prs = wi.get("linkedPRs") or []
                self_pr = match_self_pr(current_branch, linked_prs)

    # Header
    synced_at = mirror.get("syncedAt", "") if mirror else ""
    lines.append("# Work Dashboard")
    if mirror is None:
        lines.append("_Mirror not yet initialized_")
    else:
        lines.append(f"_Synced: {_fmt_local(synced_at)} · {len(work_items)} work items_")
    lines.append("")

    # ------------------------------------------------------------------
    # Section 1: My Queue
    # ------------------------------------------------------------------
    lines.append("## My Queue")
    lines.append("")
    queue_items: list[dict] = []
    for q in [feat_queue, bug_queue]:
        if q and isinstance(q.get("items"), list):
            queue_items.extend(q["items"])

    if queue_items:
        lines.append("| WI | Title | Priority | PR |")
        lines.append("| --- | --- | --- | --- |")
        for item in queue_items:
            wi_id = item.get("wi_id", "")
            title = _escape_md_pipe(item.get("title") or "(no title)")
            priority = item.get("priority", "")
            pr_info = ""
            if wi_id is not None and wi_id == branch_wi_id and self_pr is not None:
                pr_info = _pr_link(self_pr.get("prNumber"), self_pr.get("repo"))
            lines.append(f"| {_wi_link(wi_id, item.get('url'))} | {title} | {priority} | {pr_info} |")
    else:
        lines.append("_(none)_")
    lines.append("")

    # ------------------------------------------------------------------
    # Section 2: In Flight
    # ------------------------------------------------------------------
    lines.append("## In Flight")
    lines.append("")
    if leases is None:
        lines.append("_No leases yet (leases.json not found)_")
    else:
        lease_list = leases.get("leases") or []
        if not lease_list:
            lines.append("_No active leases_")
        else:
            lines.append("| WI | Branch | Started | Worker | Stage |")
            lines.append("| --- | --- | --- | --- | --- |")
            for lease in lease_list:
                wi_id = lease.get("wi_id", "?")
                branch = _escape_md_pipe(lease.get("branch") or "?")
                started = lease.get("startedAt", "?")
                worker = lease.get("worker_pid", lease.get("slot", ""))
                stage = _escape_md_pipe(lease.get("stage") or "")
                stale_flag = " **[STALE]**" if lease.get("stale") else ""
                lines.append(
                    f"| {_wi_link(wi_id, lease.get('url'))} | {branch} | {started} | {worker} | {stage}{stale_flag} |"
                )
    lines.append("")

    # ------------------------------------------------------------------
    # Section 3: Poseidon Board — story-level cards grouped by working column.
    # Working columns render in a fixed priority order (In Progress, PR Review,
    # Next) followed by any other non-empty working column. The "New" backlog
    # and the "Merged" done-column are omitted here; completed work appears in
    # Recently Completed (Merged/Closed cards changed within 24h). Portfolio
    # parents and terminal-state ghosts are excluded by on_board_cards.
    # ------------------------------------------------------------------
    lines.append("## Poseidon Board")
    lines.append("")

    def _pr_cell(wi: dict) -> str:
        pr_links = [
            _pr_link(lp.get("prNumber"), lp.get("repo"))
            for lp in (wi.get("linkedPRs") or [])
            if lp.get("prNumber")
        ]
        pr_status = (wi.get("prStatus") or "").strip()
        if pr_links:
            cell = ", ".join(pr_links)
            if pr_status:
                cell += f" ({_escape_md_pipe(pr_status)})"
            return cell
        return _escape_md_pipe(pr_status)

    def _emit_card_table(heading: str, items: list[dict]) -> None:
        lines.append(f"### {heading} ({len(items)})")
        lines.append("")
        lines.append("| WI | Title | Assignee | PR | Autotest |")
        lines.append("| --- | --- | --- | --- | --- |")
        for wi in items:
            lines.append(
                f"| {_wi_link(wi.get('id'), wi.get('url'))} "
                f"| {_escape_md_pipe(wi.get('title') or '(no title)')} "
                f"| {_escape_md_pipe(wi.get('assignedTo') or 'Unassigned')} "
                f"| {_pr_cell(wi)} "
                f"| {_escape_md_pipe((wi.get('autotestStatus') or '').strip())} |"
            )
        lines.append("")

    _board_priority = ["In Progress", "PR Review", "Next"]
    working_columns = [
        c for c in board_columns if c.strip().lower() not in ("new", "merged")
    ]
    board_buckets = on_board_cards(work_items, working_columns)
    # Priority columns first, then any remaining working column so nothing is
    # silently dropped if a card lands in an unlisted column.
    display_columns = [c for c in _board_priority if c in board_buckets] + [
        c for c in working_columns if c not in _board_priority
    ]
    completed = recently_completed_cards(work_items, synced_at)
    board_total = sum(len(v) for v in board_buckets.values())

    if board_total == 0 and not completed:
        lines.append(
            "_No cards on the board — run `/dashboard --refresh` to update board columns._"
        )
        lines.append("")
    else:
        for col in display_columns:
            items = board_buckets.get(col) or []
            if not items:
                continue
            _emit_card_table(col, items)
        if completed:
            _emit_card_table("Recently Completed", completed)

    # ------------------------------------------------------------------
    # Section 4: My ADO Inbox
    # ------------------------------------------------------------------
    lines.append("## My ADO Inbox")
    lines.append("")
    if mirror is None:
        lines.append("_Mirror not yet initialized_")
    else:
        my_wis = [
            wi for wi in work_items
            if _is_mine(wi.get("assignedTo"))
            and not wi.get("materialized", False)
            and (wi.get("state") or "").strip().lower() not in _TERMINAL_STATES
        ]
        if not my_wis:
            lines.append("_(none)_")
        else:
            lines.append("| WI | Title | State | PR Status |")
            lines.append("| --- | --- | --- | --- |")
            for wi in my_wis:
                wi_link = _wi_link(wi.get("id"), wi.get("url"))
                title = _escape_md_pipe(wi.get("title") or "(no title)")
                state = wi.get("state", "?")
                pr_status = _escape_md_pipe(wi.get("prStatus") or "")
                lines.append(f"| {wi_link} | {title} | {state} | {pr_status} |")
    lines.append("")

    # ------------------------------------------------------------------
    # Section 5: Pool & Sync
    # ------------------------------------------------------------------
    lines.append("## Pool & Sync")
    lines.append("")
    if mirror is None:
        lines.append("_Mirror not yet initialized_")
    else:
        synced_at = mirror.get("syncedAt", "(unknown)")
        lines.append(f"- **Mirror synced at:** {_fmt_local(synced_at)}")
        lines.append(f"- **Work items:** {len(work_items)}")
        lines.append(f"- **Stale upstream:** {len(stale_paths)} marker(s)")
        if stale_paths:
            for p in stale_paths:
                lines.append(f"  - `{p}`")

    missing: list[str] = []
    if feat_queue is None:
        missing.append("`docs/features/queue.json`")
    if bug_queue is None:
        missing.append("`docs/bugs/queue.json`")
    if leases is None:
        missing.append("`docs/work/leases.json`")
    if missing:
        lines.append(f"- **Missing artifacts:** {', '.join(missing)}")

    return "\n".join(lines)


def load_board_config(repo_root: Path) -> "tuple[list[str], int | None]":
    """Read board_columns + active_feature_id from the skill-config YAML.

    Returns (board_columns, active_feature_id); falls back to
    (DEFAULT_BOARD_COLUMNS, None) on any error / missing file / missing keys.
    """
    try:
        import yaml
        cfg_path = Path(repo_root) / ".claude" / "skill-config" / "ado-doc-integration.yml"
        with open(cfg_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        cols = cfg.get("board_columns") or DEFAULT_BOARD_COLUMNS
        return (cols, cfg.get("active_feature_id"))
    except Exception:
        return (DEFAULT_BOARD_COLUMNS, None)


def write_markdown(repo_root: Path, text: str) -> Path:
    """Write dashboard text to docs/work/DASHBOARD.md atomically.

    Uses _atomic_write so the write is never partially visible.
    Returns the absolute Path of the written file.

    MUST NOT modify any other file.
    """
    md_path = repo_root / "docs" / "work" / "DASHBOARD.md"
    _atomic_write(md_path, text)
    return md_path.resolve()


# ---------------------------------------------------------------------------
# Self-test harness
# ---------------------------------------------------------------------------

def run_self_tests() -> int:
    """Run twelve built-in fixtures. Returns number of failures (0 = all pass)."""
    failures = 0

    # ------------------------------------------------------------------
    # Fixture A — mirror-only degradation
    # Seed only ado-mirror.json; no leases/materialized/queue.
    # Assert render_dashboard returns a string; MY ADO INBOX has >=1 row
    # from the mirror; other panels show degradation text; no exception.
    # ------------------------------------------------------------------
    try:
        tmp_a = tempfile.mkdtemp(prefix="ws_test_a_")
        repo_a = Path(tmp_a)
        work_dir = repo_a / "docs" / "work"
        work_dir.mkdir(parents=True, exist_ok=True)

        mirror_data = {
            "syncedAt": "2026-06-01T10:00:00Z",
            "watermark": "2026-06-01T10:00:00Z",
            "query": {"areaPath": "Cognito Forms\\Poseidon"},
            "workItems": [
                {
                    "id": 1001,
                    "type": "User Story",
                    "title": "Inbox item alpha",
                    "state": "Active",
                    "assignedTo": "@Me",
                    "areaPath": "Cognito Forms\\Poseidon",
                    "iteration": "Cognito Forms\\Sprint 42",
                    "parentId": None,
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/1001",
                    "acceptanceCriteria": None,
                    "description": None,
                    "changedDate": "2026-06-01T09:00:00Z",
                    "linkedPRs": [],
                    "pr": None,
                    "prStatus": None,
                    "autotestStatus": None,
                    "autotestBuildId": None,
                    "autotestRun": None,
                    "materialized": False,
                }
            ],
        }
        (work_dir / "ado-mirror.json").write_text(
            json.dumps(mirror_data, indent=2), encoding="utf-8"
        )

        sources = load_sources(repo_a)
        dashboard = render_dashboard(sources)

        assert isinstance(dashboard, str), \
            f"render_dashboard should return str, got {type(dashboard)}"
        assert len(dashboard) > 0, "render_dashboard returned empty string"

        # MY ADO INBOX panel must reference the mirror WI
        assert "1001" in dashboard or "Inbox item alpha" in dashboard, \
            "MY ADO INBOX panel must reference mirror WI 1001"

        # No leases file => degradation text for IN FLIGHT
        assert "No leases" in dashboard or "leases" in dashboard.lower(), \
            "IN FLIGHT panel should show degradation text when leases.json absent"

        print("PASS fixture_a_mirror_only_degradation")
    except Exception as exc:
        print(f"FAIL fixture_a_mirror_only_degradation: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture B — teammate PR/CI from mirror
    # Seed a mirror WI assigned to a teammate with pr/prStatus/autotestStatus.
    # Assert TEAM panel contains those values.
    # ------------------------------------------------------------------
    try:
        tmp_b = tempfile.mkdtemp(prefix="ws_test_b_")
        repo_b = Path(tmp_b)
        work_dir_b = repo_b / "docs" / "work"
        work_dir_b.mkdir(parents=True, exist_ok=True)

        mirror_b = {
            "syncedAt": "2026-06-01T10:00:00Z",
            "watermark": "2026-06-01T10:00:00Z",
            "query": {"areaPath": "Cognito Forms\\Poseidon"},
            "workItems": [
                {
                    "id": 2001,
                    "type": "User Story",
                    "title": "Teammate feature",
                    "state": "Active",
                    "assignedTo": "Alice Smith",
                    "boardColumn": "In Progress",
                    "areaPath": "Cognito Forms\\Poseidon",
                    "iteration": "Cognito Forms\\Sprint 42",
                    "parentId": None,
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/2001",
                    "acceptanceCriteria": None,
                    "description": None,
                    "changedDate": "2026-06-01T09:00:00Z",
                    "linkedPRs": [{"prNumber": 555, "repo": "cognitoforms/cognito"}],
                    "pr": "https://github.com/cognitoforms/cognito/pull/555",
                    "prStatus": "Review Required",
                    "autotestStatus": "Passed",
                    "autotestBuildId": "build-42",
                    "autotestRun": "run-99",
                    "materialized": True,
                }
            ],
        }
        (work_dir_b / "ado-mirror.json").write_text(
            json.dumps(mirror_b, indent=2), encoding="utf-8"
        )

        sources_b = load_sources(repo_b)
        dashboard_b = render_dashboard(sources_b)

        assert isinstance(dashboard_b, str), "render_dashboard must return str"

        # The board panel must surface the teammate card's pr/prStatus/autotest
        assert "=== POSEIDON BOARD ===" in dashboard_b, \
            "render_dashboard must contain the board panel"
        assert "Review Required" in dashboard_b, \
            "board card must contain prStatus 'Review Required'"
        assert "Passed" in dashboard_b, \
            "board card must contain autotestStatus 'Passed'"
        assert "555" in dashboard_b or "Alice Smith" in dashboard_b, \
            "board card must reference teammate WI 2001 / PR 555"

        print("PASS fixture_b_teammate_pr_ci")
    except Exception as exc:
        print(f"FAIL fixture_b_teammate_pr_ci: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture C — self-link via branch regex
    # queue.json with wi_id matching a mirror WI that has linkedPRs with
    # prNumber=300, and current_branch="p/300-add-widget".
    # Assert match_self_pr returns the correct PR dict.
    # Assert MY QUEUE panel surfaces that PR link.
    # ------------------------------------------------------------------
    try:
        tmp_c = tempfile.mkdtemp(prefix="ws_test_c_")
        repo_c = Path(tmp_c)
        work_dir_c = repo_c / "docs" / "work"
        work_dir_c.mkdir(parents=True, exist_ok=True)
        feat_dir = repo_c / "docs" / "features"
        feat_dir.mkdir(parents=True, exist_ok=True)

        mirror_c = {
            "syncedAt": "2026-06-01T10:00:00Z",
            "watermark": "2026-06-01T10:00:00Z",
            "query": {},
            "workItems": [
                {
                    "id": 3001,
                    "type": "User Story",
                    "title": "Add widget",
                    "state": "Active",
                    "assignedTo": "@Me",
                    "areaPath": "Cognito Forms\\Poseidon",
                    "iteration": "Cognito Forms\\Sprint 42",
                    "parentId": None,
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/3001",
                    "acceptanceCriteria": None,
                    "description": None,
                    "changedDate": "2026-06-01T09:00:00Z",
                    "linkedPRs": [{"prNumber": 300, "repo": "cognitoforms/cognito"}],
                    "pr": "https://github.com/cognitoforms/cognito/pull/300",
                    "prStatus": "Draft",
                    "autotestStatus": None,
                    "autotestBuildId": None,
                    "autotestRun": None,
                    "materialized": False,
                }
            ],
        }
        (work_dir_c / "ado-mirror.json").write_text(
            json.dumps(mirror_c, indent=2), encoding="utf-8"
        )

        feat_queue = {
            "items": [
                {"wi_id": 3001, "title": "Add widget", "priority": 1}
            ]
        }
        (feat_dir / "queue.json").write_text(
            json.dumps(feat_queue, indent=2), encoding="utf-8"
        )

        # Test match_self_pr directly
        linked_prs = [{"prNumber": 300, "repo": "cognitoforms/cognito"}]
        matched = match_self_pr("p/300-add-widget", linked_prs)
        assert matched is not None, \
            "match_self_pr('p/300-add-widget', ...) must return a dict, got None"
        assert matched["prNumber"] == 300, \
            f"match_self_pr must return PR with prNumber=300, got {matched}"

        # Also verify non-matching branch returns None
        no_match = match_self_pr("feature/unrelated", linked_prs)
        assert no_match is None, \
            f"match_self_pr('feature/unrelated', ...) must return None, got {no_match}"

        # MY QUEUE panel must surface PR link when branch matches
        sources_c = load_sources(repo_c)
        dashboard_c = render_dashboard(sources_c, current_branch="p/300-add-widget")
        assert isinstance(dashboard_c, str), "render_dashboard must return str"
        assert "300" in dashboard_c, \
            "MY QUEUE panel must surface PR link (prNumber 300) when branch matches"

        print("PASS fixture_c_self_link_branch_regex")
    except Exception as exc:
        print(f"FAIL fixture_c_self_link_branch_regex: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture D — --markdown no-mutation
    # Seed leases.json and queue.json; record their mtimes; call write_markdown;
    # assert DASHBOARD.md created AND leases.json/queue.json mtimes unchanged.
    # ------------------------------------------------------------------
    try:
        tmp_d = tempfile.mkdtemp(prefix="ws_test_d_")
        repo_d = Path(tmp_d)
        work_dir_d = repo_d / "docs" / "work"
        work_dir_d.mkdir(parents=True, exist_ok=True)
        feat_dir_d = repo_d / "docs" / "features"
        feat_dir_d.mkdir(parents=True, exist_ok=True)

        leases_data = {
            "leases": [
                {"wi_id": 4001, "branch": "p/4001-my-task", "startedAt": "2026-06-01T08:00:00Z"}
            ]
        }
        leases_path = work_dir_d / "leases.json"
        leases_path.write_text(json.dumps(leases_data, indent=2), encoding="utf-8")

        queue_data = {"items": [{"wi_id": 4002, "title": "Queue item", "priority": 2}]}
        queue_path = feat_dir_d / "queue.json"
        queue_path.write_text(json.dumps(queue_data, indent=2), encoding="utf-8")

        # Record mtimes before
        leases_mtime_before = os.stat(leases_path).st_mtime_ns
        queue_mtime_before = os.stat(queue_path).st_mtime_ns

        # Write markdown
        dashboard_text = "# Dashboard\nSome content for fixture D"
        md_path = write_markdown(repo_d, dashboard_text)

        # Assert DASHBOARD.md was created
        expected_md = repo_d / "docs" / "work" / "DASHBOARD.md"
        assert expected_md.exists(), \
            f"DASHBOARD.md not created at {expected_md}"
        assert md_path == expected_md or md_path.resolve() == expected_md.resolve(), \
            f"write_markdown returned {md_path}, expected {expected_md}"
        content_written = expected_md.read_text(encoding="utf-8")
        assert "Dashboard" in content_written, \
            "DASHBOARD.md content missing expected text"

        # Assert input files NOT mutated
        leases_mtime_after = os.stat(leases_path).st_mtime_ns
        queue_mtime_after = os.stat(queue_path).st_mtime_ns

        assert leases_mtime_before == leases_mtime_after, \
            "leases.json mtime changed — write_markdown must not mutate inputs"
        assert queue_mtime_before == queue_mtime_after, \
            "queue.json mtime changed — write_markdown must not mutate inputs"

        print("PASS fixture_d_markdown_no_mutation")
    except Exception as exc:
        print(f"FAIL fixture_d_markdown_no_mutation: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture E — filter_recent_team: active kept, recent-closed kept, old-closed hidden
    # synced_at = 2026-06-02T20:00:00Z, window_days=5 → cutoff = 2026-05-28T20:00:00Z
    # ------------------------------------------------------------------
    try:
        synced_at_e = "2026-06-02T20:00:00Z"
        team_wis_e = [
            {
                "id": 5001,
                "title": "Active item",
                "state": "Active",
                "assignedTo": "Bob",
                "changedDate": "2026-06-01T10:00:00Z",
            },
            {
                "id": 5002,
                "title": "Recent closed",
                "state": "Closed",
                "assignedTo": "Carol",
                "changedDate": "2026-05-30T10:00:00Z",  # within 5d → kept
            },
            {
                "id": 5003,
                "title": "Old closed",
                "state": "Closed",
                "assignedTo": "Dave",
                "changedDate": "2026-01-01T00:00:00Z",  # old → hidden
            },
        ]
        kept_e, hidden_e = filter_recent_team(team_wis_e, synced_at_e, 5)
        kept_ids = {wi["id"] for wi in kept_e}

        assert 5001 in kept_ids, f"Active WI 5001 must be kept, got kept={kept_ids}"
        assert 5002 in kept_ids, f"Recent-closed WI 5002 must be kept, got kept={kept_ids}"
        assert 5003 not in kept_ids, f"Old-closed WI 5003 must be hidden, got kept={kept_ids}"
        assert hidden_e == 1, f"hidden_count must be 1, got {hidden_e}"

        # Empty synced_at → all kept, hidden 0
        kept_empty, hidden_empty = filter_recent_team(team_wis_e, "", 5)
        assert len(kept_empty) == len(team_wis_e), \
            f"Empty synced_at must keep all WIs, got {len(kept_empty)}"
        assert hidden_empty == 0, \
            f"Empty synced_at must have hidden=0, got {hidden_empty}"

        print("PASS fixture_e_filter_recent_team")
    except Exception as exc:
        print(f"FAIL fixture_e_filter_recent_team: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture F — filter_recent_team: missing changedDate on terminal WI → hidden
    # ------------------------------------------------------------------
    try:
        team_wis_f = [
            {
                "id": 6001,
                "title": "Done no date",
                "state": "Done",
                "assignedTo": "Eve",
                "changedDate": None,
            },
        ]
        kept_f, hidden_f = filter_recent_team(team_wis_f, "2026-06-02T20:00:00Z", 5)
        assert len(kept_f) == 0, \
            f"Terminal WI with no changedDate must be hidden, got kept={[w['id'] for w in kept_f]}"
        assert hidden_f == 1, f"hidden_count must be 1, got {hidden_f}"

        print("PASS fixture_f_filter_missing_date")
    except Exception as exc:
        print(f"FAIL fixture_f_filter_missing_date: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture G — render_markdown: top-level structure
    # Assert starts with "# Work Dashboard", contains all five ## sections,
    # and subtitle line with syncedAt.
    # ------------------------------------------------------------------
    try:
        tmp_g = tempfile.mkdtemp(prefix="ws_test_g_")
        repo_g = Path(tmp_g)
        work_dir_g = repo_g / "docs" / "work"
        work_dir_g.mkdir(parents=True, exist_ok=True)

        mirror_g = {
            "syncedAt": "2026-06-01T10:00:00Z",
            "watermark": "2026-06-01T10:00:00Z",
            "query": {},
            "workItems": [
                {
                    "id": 7001,
                    "title": "Team item",
                    "type": "Bug",
                    "state": "Active",
                    "assignedTo": "Frank",
                    "boardColumn": "In Progress",
                    "changedDate": "2026-06-01T09:00:00Z",
                    "linkedPRs": [],
                    "pr": None,
                    "prStatus": None,
                    "autotestStatus": None,
                    "autotestBuildId": None,
                    "autotestRun": None,
                    "materialized": False,
                }
            ],
        }
        (work_dir_g / "ado-mirror.json").write_text(
            json.dumps(mirror_g, indent=2), encoding="utf-8"
        )
        sources_g = load_sources(repo_g)
        md_g = render_markdown(sources_g)

        assert md_g.startswith("# Work Dashboard"), \
            f"render_markdown must start with '# Work Dashboard', got: {md_g[:60]!r}"
        for section in ["## Poseidon Board", "## My Queue", "## In Flight", "## My ADO Inbox", "## Pool & Sync"]:
            assert section in md_g, f"render_markdown must contain '{section}'"
        assert "## Team" not in md_g, \
            "Team section was dropped from markdown (board cards already show assignees)"
        assert _fmt_local("2026-06-01T10:00:00Z") in md_g, \
            "Subtitle must contain syncedAt rendered as friendly local time"
        assert "2026-06-01T10:00:00Z" not in md_g, \
            "Raw UTC syncedAt must be converted to local time, not shown verbatim"

        print("PASS fixture_g_render_markdown_structure")
    except Exception as exc:
        print(f"FAIL fixture_g_render_markdown_structure: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture H — render_markdown: pipe in title is escaped
    # ------------------------------------------------------------------
    try:
        tmp_h = tempfile.mkdtemp(prefix="ws_test_h_")
        repo_h = Path(tmp_h)
        work_dir_h = repo_h / "docs" / "work"
        work_dir_h.mkdir(parents=True, exist_ok=True)

        mirror_h = {
            "syncedAt": "2026-06-02T10:00:00Z",
            "watermark": "2026-06-02T10:00:00Z",
            "query": {},
            "workItems": [
                {
                    "id": 8001,
                    "title": "A | B title",
                    "type": "Bug",
                    "state": "Active",
                    "assignedTo": "Grace",
                    "boardColumn": "In Progress",
                    "changedDate": "2026-06-02T08:00:00Z",
                    "linkedPRs": [],
                    "pr": None,
                    "prStatus": None,
                    "autotestStatus": None,
                    "autotestBuildId": None,
                    "autotestRun": None,
                    "materialized": False,
                }
            ],
        }
        (work_dir_h / "ado-mirror.json").write_text(
            json.dumps(mirror_h, indent=2), encoding="utf-8"
        )
        sources_h = load_sources(repo_h)
        md_h = render_markdown(sources_h)

        assert r"A \| B title" in md_h, \
            f"Pipe in title must be escaped as '\\|', got relevant section: {md_h!r}"

        print("PASS fixture_h_pipe_escape")
    except Exception as exc:
        print(f"FAIL fixture_h_pipe_escape: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture I — render_markdown: terminal-state guard on stale board column.
    # A Closed item that still carries a working board column (stale, e.g. it
    # was closed without being dragged off the board) must NOT appear as a card.
    # ------------------------------------------------------------------
    try:
        tmp_i = tempfile.mkdtemp(prefix="ws_test_i_")
        repo_i = Path(tmp_i)
        work_dir_i = repo_i / "docs" / "work"
        work_dir_i.mkdir(parents=True, exist_ok=True)

        mirror_i = {
            "syncedAt": "2026-06-02T20:00:00Z",
            "watermark": "2026-06-02T20:00:00Z",
            "query": {},
            "workItems": [
                {
                    "id": 9001,
                    "title": "Closed item with stale board column",
                    "type": "Bug",
                    "state": "Closed",
                    "assignedTo": "Hank",
                    "boardColumn": "In Progress",  # stale — item is Closed
                    "changedDate": "2026-01-01T00:00:00Z",
                    "linkedPRs": [],
                    "pr": None,
                    "prStatus": None,
                    "autotestStatus": None,
                    "autotestBuildId": None,
                    "autotestRun": None,
                    "materialized": False,
                }
            ],
        }
        (work_dir_i / "ado-mirror.json").write_text(
            json.dumps(mirror_i, indent=2), encoding="utf-8"
        )
        sources_i = load_sources(repo_i)
        md_i = render_markdown(sources_i)

        assert "[9001]" not in md_i, \
            f"Closed item with stale board column must not render as a card; got:\n{md_i}"
        assert "No cards on the board" in md_i, \
            f"Board must report no cards when only a closed/stale item is present; got:\n{md_i}"

        print("PASS fixture_i_terminal_board_guard")
    except Exception as exc:
        print(f"FAIL fixture_i_terminal_board_guard: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture J — order_board: canonical column order + unknown/empty/missing bucket
    # ------------------------------------------------------------------
    try:
        board_columns_j = ["New", "In Progress", "Merged"]
        wis_j = [
            {"id": 1, "boardColumn": "New"},
            {"id": 2, "boardColumn": "Merged"},
            {"id": 3, "boardColumn": "In Progress"},
            {"id": 4, "boardColumn": ""},
            {"id": 5, "boardColumn": "Bogus"},
            {"id": 6},  # no boardColumn key
        ]
        result_j = order_board(wis_j, board_columns_j)
        actual_keys_j = list(result_j.keys())
        expected_keys_j = ["New", "In Progress", "Merged", "(no column)"]
        assert actual_keys_j == expected_keys_j, \
            f"order_board keys must be {expected_keys_j}, got {actual_keys_j}"
        assert [wi["id"] for wi in result_j["New"]] == [1], \
            f"'New' bucket must contain id 1 only, got {[wi['id'] for wi in result_j['New']]}"
        assert [wi["id"] for wi in result_j["Merged"]] == [2], \
            f"'Merged' bucket must contain id 2 only, got {[wi['id'] for wi in result_j['Merged']]}"
        assert [wi["id"] for wi in result_j["In Progress"]] == [3], \
            f"'In Progress' bucket must contain id 3 only, got {[wi['id'] for wi in result_j['In Progress']]}"
        no_col_ids_j = [wi["id"] for wi in result_j["(no column)"]]
        assert set(no_col_ids_j) == {4, 5, 6}, \
            f"'(no column)' bucket must contain ids {{4, 5, 6}}, got {no_col_ids_j}"
        total_bucketed_j = sum(len(v) for v in result_j.values())
        assert total_bucketed_j == 6, \
            f"Total bucketed WIs must be 6 (none dropped), got {total_bucketed_j}"
        print("PASS fixture_j_order_board")
    except Exception as exc:
        print(f"FAIL fixture_j_order_board: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture K — group_by_feature: active pinned first + title resolution + orphan floor
    # ------------------------------------------------------------------
    try:
        mirror_index_k = {
            54423: {"id": 54423, "title": "Active Feature Title", "parentId": None},
            999: {"id": 999, "title": "Other Feature", "parentId": None},
        }
        team_wis_k = [
            {"id": 100, "parentId": 54423},
            {"id": 101, "parentId": 54423},
            {"id": 200, "parentId": 999},
            {"id": 300, "parentId": None},
        ]
        groups_k = group_by_feature(team_wis_k, 54423, mirror_index_k)

        # Active feature group must be first
        assert groups_k[0]["feature_id"] == 54423, \
            f"groups[0] must be the active feature (54423), got feature_id={groups_k[0]['feature_id']}"
        assert groups_k[0]["title"] == "Active Feature Title", \
            f"Active group title must be 'Active Feature Title', got {groups_k[0]['title']!r}"
        active_ids_k = [wi["id"] for wi in groups_k[0]["wis"]]
        assert active_ids_k == [100, 101], \
            f"Active group must contain ids [100, 101], got {active_ids_k}"

        # Other feature group
        other_groups_k = [g for g in groups_k if g["feature_id"] == 999]
        assert len(other_groups_k) == 1, \
            f"Expected exactly one group with feature_id=999, got {[g['feature_id'] for g in groups_k]}"
        assert other_groups_k[0]["title"] == "Other Feature", \
            f"Other group title must be 'Other Feature', got {other_groups_k[0]['title']!r}"
        assert [wi["id"] for wi in other_groups_k[0]["wis"]] == [200], \
            f"Other group must contain id 200, got {[wi['id'] for wi in other_groups_k[0]['wis']]}"

        # Orphan group must be last
        assert groups_k[-1]["feature_id"] is None, \
            f"Last group must be orphan (feature_id=None), got {groups_k[-1]['feature_id']}"
        assert groups_k[-1]["title"] == "(no parent)", \
            f"Orphan group title must be '(no parent)', got {groups_k[-1]['title']!r}"
        assert [wi["id"] for wi in groups_k[-1]["wis"]] == [300], \
            f"Orphan group must contain id 300, got {[wi['id'] for wi in groups_k[-1]['wis']]}"

        # Title fallback when active id is not in mirror_index
        groups_k_empty = group_by_feature(team_wis_k, 54423, {})
        assert groups_k_empty[0]["feature_id"] == 54423, \
            f"Active group must still be first with empty mirror_index, got feature_id={groups_k_empty[0]['feature_id']}"
        assert groups_k_empty[0]["title"] == "Feature 54423", \
            f"Active group title must fall back to 'Feature 54423' when not in mirror_index, got {groups_k_empty[0]['title']!r}"

        print("PASS fixture_k_group_by_feature")
    except Exception as exc:
        print(f"FAIL fixture_k_group_by_feature: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture L — group_by_feature: 3-level parentId chain rolls up to active feature
    # Story Bug (700) → User Story (600) → Active Feature (54423)
    # ------------------------------------------------------------------
    try:
        mirror_index_l = {
            54423: {"id": 54423, "title": "Active", "parentId": None},
            600: {"id": 600, "title": "User Story", "parentId": 54423},
        }
        team_wis_l = [{"id": 700, "parentId": 600}]
        groups_l = group_by_feature(team_wis_l, 54423, mirror_index_l)

        assert groups_l[0]["feature_id"] == 54423, \
            f"groups[0] must be the active feature (54423), got feature_id={groups_l[0]['feature_id']}"
        active_wis_l = [wi["id"] for wi in groups_l[0]["wis"]]
        assert 700 in active_wis_l, \
            f"WI 700 must roll up two levels to the active feature; got active wis={active_wis_l}"

        print("PASS fixture_l_chain_walk")
    except Exception as exc:
        print(f"FAIL fixture_l_chain_walk: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture M — render_markdown: Poseidon Board section + Recently Completed
    # Section order is My Queue -> In Flight -> Poseidon Board -> My ADO Inbox.
    # Working columns render In Progress/PR Review/Next (no count subtitle, New /
    # no-column / portfolio excluded). Merged + Closed cards changed within 24h
    # of synced_at surface under Recently Completed (older ones are dropped).
    # ------------------------------------------------------------------
    try:
        mirror_m = {
            "syncedAt": "2026-06-01T10:00:00Z",
            "watermark": "2026-06-01T10:00:00Z",
            "query": {},
            "workItems": [
                {"id": 1, "title": "WI One",   "type": "Bug",        "state": "Active", "assignedTo": "Someone Else", "parentId": None, "boardColumn": "In Progress", "linkedPRs": []},
                {"id": 2, "title": "WI Two",   "type": "User Story", "state": "Active", "assignedTo": "Someone Else", "parentId": None, "boardColumn": "In Progress", "linkedPRs": []},
                {"id": 3, "title": "WI Three", "type": "Bug",        "state": "Active", "assignedTo": "Someone Else", "parentId": None, "boardColumn": "New",         "linkedPRs": []},
                {"id": 4, "title": "WI Four",  "type": "Bug",        "state": "Active", "assignedTo": "Someone Else", "parentId": None, "boardColumn": "",            "linkedPRs": []},
                # Recently Completed candidates
                {"id": 5, "title": "WI Five",  "type": "Bug",        "state": "Active", "assignedTo": "Someone Else", "parentId": None, "boardColumn": "Merged", "changedDate": "2026-06-01T09:00:00Z", "linkedPRs": []},
                {"id": 6, "title": "WI Six",   "type": "Bug",        "state": "Closed", "assignedTo": "Someone Else", "parentId": None, "boardColumn": "Closed", "changedDate": "2026-05-28T10:00:00Z", "linkedPRs": []},
                {"id": 7, "title": "WI Seven", "type": "Bug",        "state": "Closed", "assignedTo": "Someone Else", "parentId": None, "boardColumn": "Closed", "changedDate": "2026-06-01T08:00:00Z", "linkedPRs": []},
            ],
        }
        sources_m = {"mirror": mirror_m, "feat_queue": None, "bug_queue": None, "leases": None, "stale_paths": []}
        out_m = render_markdown(
            sources_m,
            board_columns=["New", "Next", "In Progress", "PR Review", "Ready for Testing", "Reviewing", "Merged"],
            active_feature_id=None,
        )
        assert "## Poseidon Board" in out_m, \
            f"Expected '## Poseidon Board' in output, got: {out_m!r}"
        assert "### In Progress (2)" in out_m, \
            f"Expected 'In Progress (2)' column header in output, got: {out_m!r}"
        assert "[1](" in out_m and "[2](" in out_m, \
            f"Expected linked id cards [1] and [2] in output, got: {out_m!r}"
        assert "AB#" not in out_m, \
            f"Card ids must render as plain linked ids, not AB# prefixed, got: {out_m!r}"
        assert "card(s) on board" not in out_m, \
            f"Board count subtitle must be dropped, got: {out_m!r}"
        assert "WI Three" not in out_m, \
            f"New-column card must be excluded from board view, got: {out_m!r}"
        assert "WI Four" not in out_m, \
            f"No-column card must be excluded from board view, got: {out_m!r}"
        # Recently Completed: Merged (id5) + recent Closed (id7); old Closed (id6) dropped.
        assert "### Recently Completed (2)" in out_m, \
            f"Expected 'Recently Completed (2)' header, got: {out_m!r}"
        assert "WI Five" in out_m and "WI Seven" in out_m, \
            f"Merged + recent Closed cards must appear in Recently Completed, got: {out_m!r}"
        assert "WI Six" not in out_m, \
            f"Closed card older than 24h must be excluded, got: {out_m!r}"
        assert "### Merged" not in out_m, \
            f"Merged must not render as a working column, got: {out_m!r}"
        # Section order: My Queue -> In Flight -> Poseidon Board -> My ADO Inbox
        queue_pos = out_m.index("## My Queue")
        flight_pos = out_m.index("## In Flight")
        board_pos = out_m.index("## Poseidon Board")
        inbox_pos = out_m.index("## My ADO Inbox")
        assert queue_pos < flight_pos < board_pos < inbox_pos, \
            f"Section order must be Queue<Flight<Board<Inbox, got {queue_pos},{flight_pos},{board_pos},{inbox_pos}"
        print("PASS fixture_m_poseidon_board_section")
    except Exception as exc:
        print(f"FAIL fixture_m_poseidon_board_section: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture N — render_markdown: portfolio exclusion + New hiding + PR cell
    # A portfolio parent (Feature) carrying a working board column must be
    # excluded; the New-column child must be hidden; the In Progress child must
    # render as a card with its PR number.
    # ------------------------------------------------------------------
    try:
        mirror_n = {
            "syncedAt": "2026-06-01T10:00:00Z",
            "watermark": "2026-06-01T10:00:00Z",
            "query": {},
            "workItems": [
                {"id": 54423, "title": "Board Feature", "type": "Feature",    "state": "Active", "assignedTo": "Someone Else", "parentId": None,  "boardColumn": "In Progress", "linkedPRs": []},
                {"id": 100,   "title": "Child A",       "type": "User Story", "state": "Active", "assignedTo": "Someone Else", "parentId": 54423, "boardColumn": "In Progress", "linkedPRs": [{"prNumber": 555, "repo": "cognitoforms/cognito"}]},
                {"id": 101,   "title": "Child B",       "type": "Bug",        "state": "Active", "assignedTo": "Someone Else", "parentId": 54423, "boardColumn": "New",         "linkedPRs": []},
            ],
        }
        sources_n = {"mirror": mirror_n, "feat_queue": None, "bug_queue": None, "leases": None, "stale_paths": []}
        out_n = render_markdown(
            sources_n,
            board_columns=["New", "Next", "In Progress", "PR Review", "Ready for Testing", "Reviewing", "Merged"],
            active_feature_id=54423,
        )
        assert "\U0001f3af" not in out_n, \
            f"Active-feature section must be gone (no 🎯 header), got: {out_n!r}"
        assert "[54423]" not in out_n, \
            f"Portfolio parent (Feature) must be excluded from board, got: {out_n!r}"
        assert "[101]" not in out_n, \
            f"New-column child must be hidden from board, got: {out_n!r}"
        assert "[100](" in out_n, \
            f"Expected In Progress child card linked id [100] in output, got: {out_n!r}"
        assert "[#555](https://github.com/cognitoforms/cognito/pull/555)" in out_n, \
            f"Expected linked PR #555 for Child A in output, got: {out_n!r}"
        print("PASS fixture_n_board_excludes_portfolio_and_new")
    except Exception as exc:
        print(f"FAIL fixture_n_board_excludes_portfolio_and_new: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture O — render_markdown: graceful empty board (no on-board cards)
    # WIs without a working board column; assert graceful notice and no
    # active-feature section.
    # ------------------------------------------------------------------
    try:
        mirror_o = {
            "syncedAt": "2026-06-01T10:00:00Z",
            "watermark": "2026-06-01T10:00:00Z",
            "query": {},
            "workItems": [
                {"id": 1, "title": "Old item", "type": "Bug", "state": "Active", "assignedTo": "Someone Else", "parentId": None},
            ],
        }
        sources_o = {"mirror": mirror_o, "feat_queue": None, "bug_queue": None, "leases": None, "stale_paths": []}
        out_o = render_markdown(sources_o, active_feature_id=None)
        assert isinstance(out_o, str), \
            f"render_markdown must return str, got {type(out_o)}"
        assert "No cards on the board" in out_o, \
            f"Expected 'No cards on the board' graceful notice in output, got: {out_o!r}"
        assert "\U0001f3af" not in out_o, \
            f"Expected no 🎯 active-feature section, got: {out_o!r}"
        print("PASS fixture_o_graceful_empty_board")
    except Exception as exc:
        print(f"FAIL fixture_o_graceful_empty_board: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture P — load_board_config: reads YAML config; falls back on missing file
    # RED: load_board_config does not yet exist (NameError).
    # ------------------------------------------------------------------
    try:
        yaml_available = True
        try:
            import yaml  # noqa: F401
        except ImportError:
            yaml_available = False

        if not yaml_available:
            print("PASS fixture_p_config_loader (skipped: no yaml)")
        else:
            import tempfile as _tempfile
            import os as _os

            # Case 1: file present with both keys
            tmp_p = _tempfile.mkdtemp(prefix="ws_test_p_")
            skill_dir = _os.path.join(tmp_p, ".claude", "skill-config")
            _os.makedirs(skill_dir, exist_ok=True)
            yaml_path = _os.path.join(skill_dir, "ado-doc-integration.yml")
            with open(yaml_path, "w", encoding="utf-8") as fh:
                fh.write("active_feature_id: 777\nboard_columns:\n  - A\n  - B\n  - C\n")
            result_p = load_board_config(Path(tmp_p))
            assert result_p == (["A", "B", "C"], 777), \
                f"Expected (['A','B','C'], 777) from load_board_config, got {result_p!r}"

            # Case 2: file absent → fallback to DEFAULT_BOARD_COLUMNS, None
            tmp_p2 = _tempfile.mkdtemp(prefix="ws_test_p2_")
            result_p2 = load_board_config(Path(tmp_p2))
            expected_default = ["New", "Next", "In Progress", "PR Review", "Ready for Testing", "Reviewing", "Merged"]
            assert result_p2[1] is None, \
                f"Expected active_feature_id=None for missing file, got {result_p2[1]!r}"
            assert result_p2[0] == expected_default, \
                f"Expected default board_columns {expected_default!r}, got {result_p2[0]!r}"

            print("PASS fixture_p_config_loader")
    except Exception as exc:
        print(f"FAIL fixture_p_config_loader: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture Q — render_dashboard is board-centric
    # Terminal renderer groups story cards by working column, hides the New
    # backlog and no-column items, drops the Team panel, and emits no markdown.
    # ------------------------------------------------------------------
    try:
        mirror_q = {
            "syncedAt": "2026-06-01T10:00:00Z",
            "watermark": "2026-06-01T10:00:00Z",
            "query": {},
            "workItems": [
                {"id": 1, "title": "WI One",   "type": "Bug",        "state": "Active", "assignedTo": "Someone Else", "parentId": None, "boardColumn": "In Progress", "linkedPRs": []},
                {"id": 2, "title": "WI Two",   "type": "User Story", "state": "Active", "assignedTo": "Someone Else", "parentId": None, "boardColumn": "In Progress", "linkedPRs": []},
                {"id": 3, "title": "WI Three", "type": "Bug",        "state": "Active", "assignedTo": "Someone Else", "parentId": None, "boardColumn": "New",         "linkedPRs": []},
            ],
        }
        sources_q = {"mirror": mirror_q, "feat_queue": None, "bug_queue": None, "leases": None, "stale_paths": []}
        term_q = render_dashboard(sources_q)
        assert isinstance(term_q, str), \
            f"render_dashboard must return str, got {type(term_q)}"
        assert "=== POSEIDON BOARD ===" in term_q, \
            f"render_dashboard must contain the board panel, got: {term_q!r}"
        assert "In Progress (2)" in term_q, \
            f"board panel must show 'In Progress (2)', got: {term_q!r}"
        assert "WI Three" not in term_q, \
            f"New-column card must be hidden from the board panel, got: {term_q!r}"
        assert "=== TEAM ===" not in term_q, \
            f"Team panel must be dropped from the terminal renderer, got: {term_q!r}"
        assert "## Poseidon Board" not in term_q and "\U0001f3af" not in term_q, \
            f"render_dashboard must not emit markdown markup, got: {term_q!r}"
        print("PASS fixture_q_render_dashboard_board_centric")
    except Exception as exc:
        print(f"FAIL fixture_q_render_dashboard_board_centric: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture R — _fmt_local: UTC ISO -> friendly local 'dd/mm at H:MM AM/PM'.
    # Pin an explicit tz so the expected string is deterministic regardless of
    # the test machine's timezone. Also assert graceful passthrough.
    # ------------------------------------------------------------------
    try:
        tz_central = datetime.timezone(datetime.timedelta(hours=-6))
        # 2026-06-03T15:14:51Z -> 09:14 local (-06:00)
        out_r = _fmt_local("2026-06-03T15:14:51Z", tz=tz_central)
        assert out_r == "03/06 at 9:14 AM", \
            f"_fmt_local afternoon-UTC case wrong: {out_r!r}"
        # Noon/PM + 12-hour wrap: 2026-06-03T23:05:00Z -> 17:05 local -> 5:05 PM
        out_r_pm = _fmt_local("2026-06-03T23:05:00Z", tz=tz_central)
        assert out_r_pm == "03/06 at 5:05 PM", \
            f"_fmt_local pm case wrong: {out_r_pm!r}"
        # Midnight wrap: 00:30 local -> 12:30 AM
        out_r_mid = _fmt_local("2026-06-03T06:30:00Z", tz=tz_central)
        assert out_r_mid == "03/06 at 12:30 AM", \
            f"_fmt_local midnight case wrong: {out_r_mid!r}"
        # Graceful passthrough on empty / unparseable input.
        assert _fmt_local("") == "", "_fmt_local('') must return ''"
        assert _fmt_local("not-a-date") == "not-a-date", \
            "_fmt_local must return unparseable input unchanged"
        print("PASS fixture_r_fmt_local")
    except Exception as exc:
        print(f"FAIL fixture_r_fmt_local: {exc}")
        failures += 1

    # Summary
    total = 18
    passed = total - failures
    print(f"\n{passed}/{total} fixtures passed")
    return failures


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only cross-source terminal dashboard for work status"
    )
    parser.add_argument("--test", action="store_true", help="Run self-tests and exit")
    parser.add_argument(
        "--repo-root", type=Path, default=None,
        help="Path to repo root (defaults to two levels up from this script)"
    )
    parser.add_argument(
        "--markdown", action="store_true",
        help="Write GFM DASHBOARD.md (--out path or docs/work/DASHBOARD.md)"
    )
    parser.add_argument(
        "--all-team", action="store_true",
        help="Include all team WIs in markdown output (disables recent-terminal filter)"
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Write markdown to this path instead of the default docs/work/DASHBOARD.md"
    )
    parser.add_argument(
        "--current-branch", default=None,
        help="Current git branch name (used to auto-link My Queue items to PRs)"
    )
    parser.add_argument(
        "--feature", default=None,
        help="Active feature WI id; overrides config active_feature_id"
    )
    args = parser.parse_args()

    if args.test:
        failures = run_self_tests()
        sys.exit(failures)

    # Resolve repo root
    repo_root: Path
    if args.repo_root:
        repo_root = args.repo_root.resolve()
    else:
        # Default: two levels up from this script (scripts/ -> user/ -> claude-config/)
        repo_root = Path(__file__).resolve().parent.parent.parent

    sources = load_sources(repo_root)
    cfg_cols, cfg_active = load_board_config(repo_root)
    text = render_dashboard(
        sources, current_branch=args.current_branch, board_columns=cfg_cols
    )
    print(text)

    if args.markdown:
        active = args.feature if args.feature is not None else cfg_active
        if isinstance(active, str) and active.strip().lstrip("-").isdigit():
            active = int(active)
        md_text = render_markdown(
            sources,
            current_branch=args.current_branch,
            all_team=args.all_team,
            board_columns=cfg_cols,
            active_feature_id=active,
        )
        if args.out:
            out_path = args.out.resolve()
            _atomic_write(out_path, md_text)
            md_path = out_path
        else:
            md_path = write_markdown(repo_root, md_text)
        print(f"\nDashboard written to {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
