#!/usr/bin/env python3
"""
Dependencies (no requirements.txt in this repo):
    pip install keyring requests pyyaml

ado-sync.py -- Deterministic Azure DevOps WIQL poller.

Polls an ADO project for work items matching a WIQL query, hydrates each item
via the batch API, and writes a fully-merged snapshot to docs/work/ado-mirror.json.
Runs are incremental: a watermark (the maximum changedDate seen) gates each
WIQL query so only items changed since the last run are fetched, then merged into
the on-disk snapshot. The output is byte-identical for equal inputs (deterministic
sort + json.dumps with sort_keys) so the file can be committed and diff'd cleanly.
Personal Access Token is stored via the system keyring and retrieved by get_pat().

Config file: <repo_root>/.claude/skill-config/ado-doc-integration.yml
  - wiql_identity.areaPath: WIQL area path filter
  - github_repo.pr_artifact_repo_guid: GUID used in vstfs ArtifactLink URLs
  - pool.pool_size: concurrency hint (not used in --once mode)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

_DIAGNOSTICS: list[str] = []


def _diag(msg: str) -> None:
    """Append a diagnostic message to the shared _DIAGNOSTICS list."""
    _DIAGNOSTICS.append(msg)
    print(f"[diag] {msg}", file=sys.stderr)


def clear_diagnostics() -> None:
    """Reset the shared _DIAGNOSTICS list."""
    _DIAGNOSTICS.clear()


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


# ---------------------------------------------------------------------------
# Pure helper stubs (impl agent fills these in; run_self_tests calls them)
# ---------------------------------------------------------------------------

def chunk_ids(ids: list[int], size: int = 200) -> list[list[int]]:
    """Split ids into ordered batches each of length <= size. Order preserved; union == input."""
    if not ids:
        return []
    return [ids[i:i + size] for i in range(0, len(ids), size)]


def parse_linked_prs(relations: list[dict], repo: str = "cognitoforms/cognito") -> list[dict]:
    """Parse ArtifactLink relations of url form
    vstfs:///GitHub/PullRequest/<repoGuid>%2f<prNumber> into
    [{"prNumber": int, "repo": "cognitoforms/cognito"}]. Ignore non-PR relations."""
    result: list[dict] = []
    if not relations:
        return result
    # Pattern: vstfs:///GitHub/PullRequest/<guid>%2f<prNumber>
    # %2f is URL-encoded '/' separating repoGuid from prNumber
    _PR_RE = re.compile(
        r"vstfs:///GitHub/PullRequest/[^%]+%2f(\d+)",
        re.IGNORECASE,
    )
    for rel in relations:
        url = rel.get("url", "")
        m = _PR_RE.search(url)
        if m:
            result.append({"prNumber": int(m.group(1)), "repo": repo})
    return result


def map_custom_fields(fields: dict) -> dict:
    """Map ADO custom fields verbatim to mirror keys:
    Custom.PR->pr, Custom.PRStatus->prStatus, Custom.AutotestStatus->autotestStatus,
    Custom.AutotestBuildID->autotestBuildId, Custom.AutotestRun->autotestRun.
    Missing fields -> None for that key. Returns a dict with exactly those 5 keys."""
    return {
        "pr":               fields.get("Custom.PR"),
        "prStatus":         fields.get("Custom.PRStatus"),
        "autotestStatus":   fields.get("Custom.AutotestStatus"),
        "autotestBuildId":  fields.get("Custom.AutotestBuildID"),
        "autotestRun":      fields.get("Custom.AutotestRun"),
    }


def merge_work_items(prior: list[dict], delta: list[dict]) -> list[dict]:
    """Merge delta into prior, keyed by 'id'. Delta entries replace prior entries with the
    same id; new ids are added; prior entries not in delta are preserved unchanged.
    Returns a NEW list in deterministic canonical order: sorted by int(id) ascending."""
    merged: dict[int, dict] = {}
    for item in prior:
        merged[int(item["id"])] = item
    for item in delta:
        merged[int(item["id"])] = item
    return [merged[k] for k in sorted(merged.keys())]


def compute_watermark(items: list[dict], prior: str | None) -> str:
    """Return the maximum 'changedDate' (ISO-8601 UTC+Z string) across items and prior.
    Lexicographic max works for normalized 'YYYY-MM-DDTHH:MM:SSZ' strings. If items empty,
    return prior (or '' if prior is None)."""
    candidates: list[str] = []
    if prior:
        candidates.append(prior)
    for item in items:
        cd = item.get("changedDate")
        if cd:
            candidates.append(cd)
    if not candidates:
        return prior if prior is not None else ""
    return max(candidates)


def serialize_mirror(mirror: dict) -> str:
    """Serialize a mirror dict to a deterministic JSON string: json.dumps(..., indent=2,
    sort_keys=True, ensure_ascii=False). Must be byte-identical for equal inputs."""
    return json.dumps(mirror, indent=2, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Optional stubs (impl agent fills in; not called from run_self_tests)
# ---------------------------------------------------------------------------

def get_pat() -> str:
    """Retrieve ADO PAT from system keyring.

    Imports keyring lazily so --test never requires it installed.
    Exits non-zero with a clear error message if the credential is missing.
    """
    try:
        import keyring as _keyring  # lazy import — not needed for --test
    except ImportError:
        print(
            "ERROR: keyring is not installed. Run: pip install keyring",
            file=sys.stderr,
        )
        sys.exit(1)

    pat = _keyring.get_password("ado-local-poller", "vso_pat_readonly")
    if pat is None:
        print(
            "ERROR: No PAT found in keyring. Store it with:\n"
            '  python -c "import keyring; keyring.set_password('
            "'ado-local-poller', 'vso_pat_readonly', '<YOUR_PAT>')\"\n"
            "Get a read-only PAT from: https://dev.azure.com/<org>/_usersSettings/tokens",
            file=sys.stderr,
        )
        sys.exit(1)
    return pat


def _normalize_changed_date(raw: str | None) -> str | None:
    """Normalize an ADO changedDate string to 'YYYY-MM-DDTHH:MM:SSZ'.

    ADO returns ISO-8601 strings like '2026-01-05T00:00:00.123Z' or
    '2026-01-05T00:00:00+00:00'. Strip sub-seconds and normalize timezone to Z.
    """
    if not raw:
        return None
    # Strip fractional seconds if present
    normalized = re.sub(r"\.\d+", "", raw)
    # Normalize +00:00 to Z
    normalized = re.sub(r"\+00:00$", "Z", normalized)
    # If it doesn't end in Z, attempt to parse and re-emit
    if not normalized.endswith("Z"):
        try:
            dt = datetime.fromisoformat(normalized)
            dt_utc = dt.astimezone(timezone.utc)
            normalized = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError):
            pass
    return normalized


def work_item_from_api(raw: dict) -> dict:
    """Transform a raw ADO work-item API response dict ($expand=all) into the
    mirror schema dict. Uses map_custom_fields and parse_linked_prs internally."""
    fields = raw.get("fields", {})
    relations = raw.get("relations") or []
    custom = map_custom_fields(fields)
    linked_prs = parse_linked_prs(relations)

    # Assigned-to: prefer displayName, fall back to uniqueName, then None
    assigned_to_raw = fields.get("System.AssignedTo")
    if isinstance(assigned_to_raw, dict):
        assigned_to = assigned_to_raw.get("displayName") or assigned_to_raw.get("uniqueName")
    else:
        assigned_to = assigned_to_raw  # string or None

    # URL: prefer _links.html.href, fall back to top-level url field
    url = None
    links = raw.get("_links", {})
    if isinstance(links, dict):
        html_link = links.get("html", {})
        if isinstance(html_link, dict):
            url = html_link.get("href")
    if not url:
        url = raw.get("url")

    changed_date = _normalize_changed_date(fields.get("System.ChangedDate"))

    return {
        "id":                 raw.get("id"),
        "type":               fields.get("System.WorkItemType"),
        "title":              fields.get("System.Title"),
        "state":              fields.get("System.State"),
        "assignedTo":         assigned_to,
        "areaPath":           fields.get("System.AreaPath"),
        "iteration":          fields.get("System.IterationPath"),
        "parentId":           fields.get("System.Parent"),
        "url":                url,
        "acceptanceCriteria": fields.get("Microsoft.VSTS.Common.AcceptanceCriteria"),
        "description":        fields.get("System.Description"),
        "changedDate":        changed_date,
        "linkedPRs":          linked_prs,
        "pr":                 custom["pr"],
        "prStatus":           custom["prStatus"],
        "autotestStatus":     custom["autotestStatus"],
        "autotestBuildId":    custom["autotestBuildId"],
        "autotestRun":        custom["autotestRun"],
        "materialized":       False,
        "boardColumn":        fields.get("System.BoardColumn") or "",
        "boardColumnDone":    bool(fields.get("System.BoardColumnDone", False)),
    }


def build_wiql_url(org: str, project: str) -> str:
    """WIQL POST endpoint. timePrecision=true is REQUIRED so date comparisons
    accept a time component (watermark carries seconds) — without it ADO 400s
    with 'cannot supply a time with the date when running a query using date precision'."""
    return f"https://dev.azure.com/{org}/{project}/_apis/wit/wiql?api-version=7.1&timePrecision=true"


def build_wiql(area_path: str, watermark: str) -> str:
    """Return the WIQL query string for fetching work items changed since watermark.

    ADO requires bracketed [System.*] reference names (bare names cause TF51005).
    If watermark is empty, falls back to the epoch so all items are returned.
    """
    if not watermark:
        watermark = "1970-01-01T00:00:00Z"
    return (
        f"SELECT [System.Id] FROM workitems "
        f"WHERE ([System.AssignedTo] = @Me OR [System.AreaPath] UNDER '{area_path}') "
        f"AND [System.ChangedDate] >= '{watermark}' "
        f"ORDER BY [System.ChangedDate] ASC"
    )


# Display name / email forms that identify the current user in stored mirror
# records. Mirrors work-status.py's _MY_IDENTITIES (minus the @Me query token,
# which is never a stored value).
_MY_IDENTITIES = frozenset({"jacob madsen", "jacob@cognitoforms.com"})


def _looks_like_me(assigned_to: str | None) -> bool:
    """True if a stored assignedTo value identifies the current user."""
    if not assigned_to:
        return False
    return assigned_to.strip().lower() in _MY_IDENTITIES


def reconcile_assigned_ids(mirror_items: list[dict], current_mine_ids) -> set[int]:
    """Return work-item ids whose 'assigned to me' state in the mirror is stale
    and must be re-hydrated.

    The incremental delta query matches `AssignedTo = @Me OR AreaPath UNDER <team>`.
    It cannot observe an item LEAVING that scope: unassigning yourself from an
    item outside the team area satisfies neither clause, so the delta never
    returns it again and the mirror keeps the stale assignment indefinitely.

    Two drift classes, reconciled against ADO's live @Me set each sync:
      - ghosts:    mirror says mine, ADO no longer does -> re-hydrate to clear.
      - newcomers: ADO says mine, mirror does not reflect it -> hydrate to add.
    """
    current = {int(i) for i in current_mine_ids}
    by_id = {wi.get("id"): wi for wi in mirror_items}
    ghosts = {
        wid
        for wid, wi in by_id.items()
        if _looks_like_me(wi.get("assignedTo")) and wid not in current
    }
    newcomers = {
        wid
        for wid in current
        if not _looks_like_me(by_id.get(wid, {}).get("assignedTo"))
    }
    return ghosts | newcomers


def fetch_mine_ids(pat: str, org: str, project: str) -> list[int]:
    """Return all work-item ids currently assigned to @Me, unbounded by watermark
    or area path. Used to reconcile assignment drift the delta query can't see.
    """
    try:
        import requests as _requests  # lazy import
    except ImportError:
        print("ERROR: requests is not installed. Run: pip install requests", file=sys.stderr)
        sys.exit(1)

    import base64

    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    wiql = "SELECT [System.Id] FROM workitems WHERE [System.AssignedTo] = @Me"
    url = build_wiql_url(org, project)
    resp = _requests.post(url, headers=headers, json={"query": wiql}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [item["id"] for item in data.get("workItems", [])]


def fetch_delta_ids(pat: str, org: str, project: str, area_path: str, watermark: str) -> list[int]:
    """Run a WIQL query filtered by area path and changedDate >= watermark; return work-item ids.

    Uses requests (lazy import). Watermark MUST be UTC+Z format.
    """
    try:
        import requests as _requests  # lazy import
    except ImportError:
        print("ERROR: requests is not installed. Run: pip install requests", file=sys.stderr)
        sys.exit(1)

    import base64

    # Build basic-auth header: PAT is the password, username is empty
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    wiql = build_wiql(area_path, watermark)

    url = build_wiql_url(org, project)
    resp = _requests.post(url, headers=headers, json={"query": wiql}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [item["id"] for item in data.get("workItems", [])]


def hydrate(pat: str, org: str, ids: list[int]) -> list[dict]:
    """Fetch full work-item details for the given ids via the ADO batch API.

    Chunks ids into batches of 200, fetches each chunk, and collects results.
    """
    try:
        import requests as _requests  # lazy import
    except ImportError:
        print("ERROR: requests is not installed. Run: pip install requests", file=sys.stderr)
        sys.exit(1)

    import base64

    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
    }

    chunks = chunk_ids(ids)
    _diag(f"hydrate: fetching {len(ids)} items in {len(chunks)} chunk(s)")

    all_items: list[dict] = []
    for i, chunk in enumerate(chunks):
        ids_csv = ",".join(str(x) for x in chunk)
        url = (
            f"https://dev.azure.com/{org}/_apis/wit/workitems"
            f"?ids={ids_csv}&$expand=all&api-version=7.1"
        )
        resp = _requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        for raw in data.get("value", []):
            all_items.append(work_item_from_api(raw))
        _diag(f"hydrate: chunk {i + 1}/{len(chunks)} done ({len(chunk)} items)")

    return all_items


def build_mirror(
    prior_items: list[dict],
    delta_items: list[dict],
    prior_watermark: str | None,
    query_meta: dict,
    synced_at: str,
) -> dict:
    """Build the full mirror dict by merging delta into prior and computing the new watermark."""
    work_items = merge_work_items(prior_items, delta_items)
    watermark = compute_watermark(work_items, prior_watermark)
    return {
        "syncedAt":  synced_at,
        "watermark": watermark,
        "query":     query_meta,
        "workItems": work_items,
    }


def install_task(repo_root: Path) -> None:
    """Install a Windows Scheduled Task that refreshes the mirror AND re-renders
    DASHBOARD.md periodically.

    Generates a wrapper .cmd that runs `ado-sync.py --once` followed by
    `work-status.py --markdown`, then schedules it via schtasks with a
    minute-interval trigger. Pointing the task at the wrapper avoids schtasks'
    fragile nested-quote handling for multi-command triggers. The wrapper is
    machine-specific (absolute python + repo paths) so it is gitignored, not
    committed. The task runs headless as the current user; interval is derived
    from config pool.heartbeat_interval_seconds (default 600s = 10 min).
    """
    script_path = Path(__file__).resolve()
    scripts_dir = script_path.parent
    render_script = scripts_dir / "work-status.py"
    python_exe = sys.executable

    # Load config to get interval
    config = _load_config(repo_root)
    pool = config.get("pool", {})
    interval_seconds = pool.get("heartbeat_interval_seconds", 600)
    interval_minutes = max(1, interval_seconds // 60)

    # Wrapper chains sync -> render. PYTHONUTF8=1 so Unicode in ADO titles does
    # not crash the cp1252 console under the headless task host.
    wrapper_path = scripts_dir / "_ado-mirror-sync.cmd"
    wrapper = (
        "@echo off\r\n"
        "set PYTHONUTF8=1\r\n"
        f'"{python_exe}" "{script_path}" --once --repo-root "{repo_root}"\r\n'
        f'"{python_exe}" "{render_script}" --markdown --repo-root "{repo_root}"\r\n'
    )
    wrapper_path.write_text(wrapper, encoding="ascii")

    task_name = "AdoMirrorSync"
    # Register via PowerShell's ScheduledTasks module rather than schtasks: schtasks
    # cannot clear the default battery start-conditions, which leave the task stuck
    # "Queued" on a laptop (DisallowStartIfOnBatteries / StopIfGoingOnBatteries).
    # -StartWhenAvailable catches up a missed run after the machine wakes from sleep;
    # -ExecutionTimeLimit caps a hung instance so IgnoreNew never wedges the schedule.
    ps_script = f"""$ErrorActionPreference = 'Stop'
$action   = New-ScheduledTaskAction -Execute '{wrapper_path}'
$trigger  = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes {interval_minutes})
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName '{task_name}' -Action $action -Trigger $trigger -Settings $settings -User "$env:USERNAME" -Force | Out-Null
"""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".ps1", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(ps_script)
        ps_path = handle.name

    print(f"Installing scheduled task '{task_name}' (sync + render every {interval_minutes} min)...")
    print(f"Wrapper: {wrapper_path}")
    try:
        exit_code = os.system(
            f'powershell -NoProfile -ExecutionPolicy Bypass -File "{ps_path}"'
        )
    finally:
        try:
            os.unlink(ps_path)
        except OSError:
            pass
    if exit_code != 0:
        print(
            f"ERROR: PowerShell task registration returned exit code {exit_code}.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        f"Task '{task_name}' installed successfully "
        f"(runs on battery, catches up after sleep)."
    )


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_config(repo_root: Path) -> dict:
    """Load ado-doc-integration.yml from <repo_root>/.claude/skill-config/."""
    config_path = repo_root / ".claude" / "skill-config" / "ado-doc-integration.yml"
    if not config_path.exists():
        print(
            f"ERROR: Config not found at {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    raw = config_path.read_text(encoding="utf-8")

    if _YAML_AVAILABLE:
        return _yaml.safe_load(raw) or {}

    # Minimal YAML fallback (key: "value" only — no nested maps or lists)
    # This handles simple scalar mappings but not the full config shape.
    # For production use: pip install pyyaml
    print(
        "WARNING: PyYAML not installed; using minimal YAML parser. "
        "Install with: pip install pyyaml",
        file=sys.stderr,
    )
    result: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            val = val.strip().strip('"').strip("'")
            result[key.strip()] = val
    return result


def _load_mirror(mirror_path: Path) -> dict:
    """Load existing mirror from disk, or return an empty mirror."""
    if not mirror_path.exists():
        return {"syncedAt": "", "watermark": "", "query": {}, "workItems": []}
    try:
        data = json.loads(mirror_path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as exc:
        _diag(f"WARNING: could not read prior mirror ({exc}); starting fresh")
        return {"syncedAt": "", "watermark": "", "query": {}, "workItems": []}


# ---------------------------------------------------------------------------
# Self-test harness
# ---------------------------------------------------------------------------

def run_self_tests() -> int:
    """Run three built-in fixtures. Returns number of failures (0 = all pass)."""
    failures = 0

    # ------------------------------------------------------------------
    # Fixture 1: chunk_ids
    # ------------------------------------------------------------------
    try:
        ids = list(range(1, 211))  # 210 ids
        chunks = chunk_ids(ids)

        assert len(chunks) >= 2, "expected at least 2 chunks for 210 ids with size=200"
        for i, chunk in enumerate(chunks):
            assert len(chunk) <= 200, f"chunk {i} has length {len(chunk)} > 200"
        # Order preserved: concatenation equals original list
        flat = []
        for chunk in chunks:
            flat.extend(chunk)
        assert flat == ids, "concatenation of chunks does not equal original ids list"
        # Union equals input set
        union: set[int] = set()
        for chunk in chunks:
            union.update(chunk)
        assert union == set(ids), "union of chunks does not equal set(ids)"

        print("PASS fixture1_chunk_ids")
    except Exception as exc:
        print(f"FAIL fixture1_chunk_ids: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 2: merge_work_items + compute_watermark
    # ------------------------------------------------------------------
    try:
        prior = [
            {"id": 1, "title": "A", "state": "Active",   "changedDate": "2026-01-01T00:00:00Z", "materialized": False},
            {"id": 2, "title": "B", "state": "New",      "changedDate": "2026-01-02T00:00:00Z", "materialized": False},
        ]
        prior_watermark = "2026-01-02T00:00:00Z"
        delta = [
            {"id": 1, "title": "A2", "state": "Resolved", "changedDate": "2026-01-05T00:00:00Z", "materialized": False},
            {"id": 3, "title": "C",  "state": "New",      "changedDate": "2026-01-04T00:00:00Z", "materialized": False},
        ]

        merged = merge_work_items(prior, delta)

        assert [w["id"] for w in merged] == [1, 2, 3], \
            f"expected ids [1,2,3] got {[w['id'] for w in merged]}"

        id1 = next(w for w in merged if w["id"] == 1)
        assert id1["title"] == "A2", f"expected title 'A2' got '{id1['title']}'"
        assert id1["state"] == "Resolved", f"expected state 'Resolved' got '{id1['state']}'"

        id2 = next(w for w in merged if w["id"] == 2)
        assert id2["title"] == "B", f"expected title 'B' got '{id2['title']}'"
        assert id2["state"] == "New", f"expected state 'New' got '{id2['state']}'"

        id3 = next(w for w in merged if w["id"] == 3)
        assert id3["title"] == "C", f"expected title 'C' got '{id3['title']}'"

        wm = compute_watermark(merged, prior_watermark)
        assert wm == "2026-01-05T00:00:00Z", \
            f"expected watermark '2026-01-05T00:00:00Z' got '{wm}'"

        print("PASS fixture2_merge_and_watermark")
    except Exception as exc:
        print(f"FAIL fixture2_merge_and_watermark: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 3: serialize_mirror determinism
    # ------------------------------------------------------------------
    try:
        prior = [
            {"id": 1, "title": "A", "state": "Active",   "changedDate": "2026-01-01T00:00:00Z", "materialized": False},
            {"id": 2, "title": "B", "state": "New",      "changedDate": "2026-01-02T00:00:00Z", "materialized": False},
        ]
        delta = [
            {"id": 1, "title": "A2", "state": "Resolved", "changedDate": "2026-01-05T00:00:00Z", "materialized": False},
            {"id": 3, "title": "C",  "state": "New",      "changedDate": "2026-01-04T00:00:00Z", "materialized": False},
        ]

        # Build two independent mirror dicts from the same inputs
        mirror_a = {
            "syncedAt": "IGNORED",
            "watermark": "2026-01-05T00:00:00Z",
            "query": {"areaPath": "Cognito Forms\\Poseidon"},
            "workItems": merge_work_items(prior, delta),
        }
        mirror_b = {
            "syncedAt": "IGNORED",
            "watermark": "2026-01-05T00:00:00Z",
            "query": {"areaPath": "Cognito Forms\\Poseidon"},
            "workItems": merge_work_items(prior, delta),
        }

        json_a = serialize_mirror(mirror_a)
        json_b = serialize_mirror(mirror_b)

        parsed_a = json.loads(json_a)
        parsed_b = json.loads(json_b)

        wi_a = json.dumps(parsed_a["workItems"], sort_keys=True)
        wi_b = json.dumps(parsed_b["workItems"], sort_keys=True)
        assert wi_a == wi_b, "workItems not byte-identical across two equal serializations"

        # Same dict serialized twice must be identical
        assert serialize_mirror(mirror_a) == serialize_mirror(mirror_a), \
            "serialize_mirror is not idempotent on the same dict"

        print("PASS fixture3_serialize_determinism")
    except Exception as exc:
        print(f"FAIL fixture3_serialize_determinism: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 4: build_wiql uses bracketed [System.*] field references
    # ------------------------------------------------------------------
    try:
        wiql = build_wiql("Cognito Forms\\\\Poseidon", "2026-01-01T00:00:00Z")

        assert "[System.AssignedTo]" in wiql, \
            f"expected [System.AssignedTo] in wiql, got: {wiql!r}"
        assert "[System.AreaPath]" in wiql, \
            f"expected [System.AreaPath] in wiql, got: {wiql!r}"
        assert "[System.ChangedDate]" in wiql, \
            f"expected [System.ChangedDate] in wiql, got: {wiql!r}"
        assert "ORDER BY [System.ChangedDate]" in wiql, \
            f"expected 'ORDER BY [System.ChangedDate]' in wiql, got: {wiql!r}"
        # Bare field names in WHERE/ORDER-BY position must not be present
        assert "AssignedTo = @Me" not in wiql, \
            f"bare 'AssignedTo' field ref found in wiql (ADO TF51005): {wiql!r}"
        assert "AreaPath UNDER" not in wiql, \
            f"bare 'AreaPath' field ref found in wiql (ADO TF51005): {wiql!r}"
        assert "ORDER BY ChangedDate" not in wiql, \
            f"bare 'ChangedDate' in ORDER BY found in wiql (ADO TF51005): {wiql!r}"
        # Watermark default: empty string should resolve to epoch
        wiql_default = build_wiql("Cognito Forms\\\\Poseidon", "")
        assert "1970-01-01T00:00:00Z" in wiql_default, \
            f"expected epoch watermark fallback in default wiql, got: {wiql_default!r}"

        print("PASS fixture4_build_wiql_bracketed_fields")
    except Exception as exc:
        print(f"FAIL fixture4_build_wiql_bracketed_fields: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 5: build_wiql_url includes timePrecision=true
    # ------------------------------------------------------------------
    try:
        url = build_wiql_url("cognitoforms", "Cognito Forms")

        assert url.startswith("https://dev.azure.com/cognitoforms/Cognito Forms/_apis/wit/wiql"), \
            f"expected URL to start with ADO WIQL base, got: {url!r}"
        assert "api-version=7.1" in url, \
            f"expected api-version=7.1 in url, got: {url!r}"
        assert "timePrecision=true" in url, \
            f"expected timePrecision=true in url (required for timestamp watermarks), got: {url!r}"

        print("PASS fixture5_build_wiql_url_time_precision")
    except Exception as exc:
        print(f"FAIL fixture5_build_wiql_url_time_precision: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 6: work_item_from_api captures boardColumn / boardColumnDone
    # ------------------------------------------------------------------
    try:
        # On-board case: both fields present
        raw_on_board = {
            "id": 42,
            "fields": {
                "System.WorkItemType": "User Story",
                "System.Title": "Test board column capture",
                "System.State": "Active",
                "System.BoardColumn": "In Progress",
                "System.BoardColumnDone": True,
            },
        }
        result_on = work_item_from_api(raw_on_board)
        assert result_on["boardColumn"] == "In Progress", \
            f"expected boardColumn='In Progress', got {result_on['boardColumn']!r}"
        assert result_on["boardColumnDone"] is True, \
            f"expected boardColumnDone=True, got {result_on['boardColumnDone']!r}"

        # Off-board case: neither field present — must not raise, must use safe defaults
        raw_off_board = {
            "id": 43,
            "fields": {
                "System.WorkItemType": "Task",
                "System.Title": "No board column",
                "System.State": "New",
            },
        }
        result_off = work_item_from_api(raw_off_board)
        assert result_off["boardColumn"] == "", \
            f"expected boardColumn='' (empty string), got {result_off['boardColumn']!r}"
        assert result_off["boardColumnDone"] is False, \
            f"expected boardColumnDone=False, got {result_off['boardColumnDone']!r}"

        # Regression: all 19 pre-existing keys must still be present
        expected19 = {
            "id", "type", "title", "state", "assignedTo", "areaPath",
            "iteration", "parentId", "url", "acceptanceCriteria", "description",
            "changedDate", "linkedPRs", "pr", "prStatus", "autotestStatus",
            "autotestBuildId", "autotestRun", "materialized",
        }
        missing = expected19 - set(result_on.keys())
        assert not missing, \
            f"regression: pre-existing keys missing from result: {missing}"

        print("PASS fixture6_board_column_capture")
    except Exception as exc:
        print(f"FAIL fixture6_board_column_capture: {exc}")
        failures += 1

    # ------------------------------------------------------------------
    # Fixture 7: reconcile_assigned_ids detects ghosts and newcomers
    # ------------------------------------------------------------------
    try:
        mirror_items = [
            # ghost: mirror says mine, ADO no longer lists it -> re-hydrate
            {"id": 27005, "assignedTo": "Jacob Madsen"},
            # still mine and still in current set -> no action
            {"id": 56080, "assignedTo": "Jacob Madsen"},
            # someone else's item, not in current set -> no action
            {"id": 999, "assignedTo": "Laython Childers"},
            # unassigned item already reflected -> no action
            {"id": 111, "assignedTo": None},
        ]
        # current @Me set: 56080 stays, 27005 dropped, 222 is a newcomer not yet
        # in the mirror as mine
        current_mine = [56080, 222]
        drift = reconcile_assigned_ids(mirror_items, current_mine)
        assert drift == {27005, 222}, f"expected {{27005, 222}}, got {drift}"
        # Idempotency: once the mirror reflects the live set, nothing drifts
        settled = [
            {"id": 56080, "assignedTo": "Jacob Madsen"},
            {"id": 222, "assignedTo": "jacob@cognitoforms.com"},
            {"id": 27005, "assignedTo": None},
        ]
        assert reconcile_assigned_ids(settled, [56080, 222]) == set(), \
            "expected no drift once mirror matches the live @Me set"
        print("PASS fixture7_reconcile_assigned_ids")
    except Exception as exc:
        print(f"FAIL fixture7_reconcile_assigned_ids: {exc}")
        failures += 1

    # Summary
    total = 7
    passed = total - failures
    print(f"\n{passed}/{total} fixtures passed")
    return failures


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic ADO WIQL poller -> docs/work/ado-mirror.json"
    )
    parser.add_argument("--test", action="store_true", help="Run self-tests and exit")
    parser.add_argument("--repo-root", type=Path, default=None, help="Path to repo root")
    parser.add_argument("--config", type=Path, default=None, help="Path to config JSON")
    parser.add_argument("--once", action="store_true", help="Run once and exit (no loop)")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Ignore the stored watermark and re-hydrate every item in the area "
        "path (backfills fields added to the parser after items were last synced, "
        "e.g. boardColumn). Slower; intended for occasional manual refresh.",
    )
    parser.add_argument("--install-task", action="store_true", help="Install scheduled task")
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

    if args.install_task:
        install_task(repo_root)
        sys.exit(0)

    if args.once or args.full:
        config = _load_config(repo_root)
        wiql = config.get("wiql_identity", {})
        org = "cognitoforms"
        project = wiql.get("project", "Cognito Forms")
        area_path = wiql.get("areaPath", "Cognito Forms\\Poseidon")

        mirror_path = repo_root / "docs" / "work" / "ado-mirror.json"
        prior_mirror = _load_mirror(mirror_path)
        prior_items: list[dict] = prior_mirror.get("workItems", [])
        # --full ignores the watermark so every item is re-fetched and re-parsed.
        prior_watermark: str = "" if args.full else prior_mirror.get("watermark", "")

        query_meta = {
            "areaPath": area_path,
            "project": project,
        }

        pat = get_pat()

        _diag(f"Fetching delta IDs since watermark: {prior_watermark!r}")
        ids = fetch_delta_ids(pat, org, project, area_path, prior_watermark)
        _diag(f"Found {len(ids)} updated work item(s)")

        delta_items: list[dict] = []
        if ids:
            delta_items = hydrate(pat, org, ids)

        synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        mirror = build_mirror(prior_items, delta_items, prior_watermark, query_meta, synced_at)

        # Reconcile assignment drift the delta query structurally cannot see (items
        # unassigned-from-me while outside the team area path). Re-hydrate any
        # ghosts/newcomers so the inbox reflects ADO's live @Me set.
        mine_ids = fetch_mine_ids(pat, org, project)
        reconcile_ids = sorted(reconcile_assigned_ids(mirror["workItems"], mine_ids))
        if reconcile_ids:
            _diag(f"Reconciling {len(reconcile_ids)} assignment-drift item(s)")
            reconciled = hydrate(pat, org, reconcile_ids)
            mirror = build_mirror(
                mirror["workItems"], reconciled, mirror["watermark"], query_meta, synced_at
            )

        content = serialize_mirror(mirror) + "\n"
        _atomic_write(mirror_path, content)
        _diag(f"Mirror written to {mirror_path} ({len(mirror['workItems'])} items)")
        sys.exit(0)

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
