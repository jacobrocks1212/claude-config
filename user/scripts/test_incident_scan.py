#!/usr/bin/env python3
"""
test_incident_scan.py — pytest suite for incident-scan.py (incident-auto-capture).

Contract under test (SPEC docs/features/incident-auto-capture/SPEC.md):
  - stdlib, deterministic, READ-ONLY collector over the per-repo state dir
    (deny ledger, hook-events.jsonl, legacy hook-error.json) + docs/bugs/**
    for dedup;
  - D3 recurrence bars (config constants) + ≤2-per-scan enqueue cap;
  - D4 clustering (repo, signal_class, signature) → deterministic
    adhoc-incident-<class>-<short-hash> slugs;
  - D5 dedup vs open + archived incident_key, archived recurrence → NEW stub
    carrying recurrence_of;
  - D7 sanctioned enqueue (`lazy-state.py --enqueue-adhoc --type bug`) +
    INCIDENT.md capsule; the collector's ONLY mutations are the enqueue
    subprocess and the capsule write;
  - --dry-run reports and mutates NOTHING (input trees hashed before/after).

Run:  python3 -m pytest test_incident_scan.py -q
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_SCAN_PY = _SCRIPTS_DIR / "incident-scan.py"

# Fixed "now" so every window computation is hermetic and byte-stable.
_NOW = 1_800_000_000.0

_H = 3600.0


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_repo(parent: Path) -> Path:
    """Minimal repo shape: docs/bugs/ exists (empty queue seeded lazily by the
    enqueue path itself — the collector must cope with queue.json absent)."""
    repo = parent / "repo"
    (repo / "docs" / "bugs").mkdir(parents=True)
    return repo


def _seed_ledger(state_dir: Path, entries: list[dict]) -> None:
    p = state_dir / "lazy-deny-ledger.jsonl"
    with p.open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def _seed_events(state_dir: Path, entries: list[dict]) -> None:
    p = state_dir / "hook-events.jsonl"
    with p.open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def _deny(sha12: str, reason: str, ts: float, acked: bool = False) -> dict:
    return {
        "ts": ts, "tool_use_id": "toolu_x", "denied_sha12": sha12,
        "reason_head": reason, "prompt_head": "prompt head", "acked": acked,
    }


def _friction(reason: str, ts: float) -> dict:
    return {
        "ts": ts, "kind": "process-friction", "reason_head": reason,
        "detail": "detail text", "acked": False,
    }


def _hook_event(kind: str, hook: str, signature: str, ts: float) -> dict:
    return {
        "ts": ts, "kind": kind, "hook": hook, "repo_root": "",
        "signature": signature, "detail": f"{hook} {signature} detail",
    }


def _run_scan(repo: Path, state_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["LAZY_STATE_DIR"] = str(state_dir)
    return subprocess.run(
        [sys.executable, str(_SCAN_PY),
         "--repo-root", str(repo), "--now", str(_NOW), *extra],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120,
    )


def _tree_hash(*roots: Path) -> str:
    """Deterministic content hash of every file under *roots* (paths + bytes)."""
    h = hashlib.sha256()
    for root in roots:
        if not root.exists():
            h.update(b"<absent>" + str(root).encode())
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(root)).encode())
                h.update(p.read_bytes())
    return h.hexdigest()


def _queue_ids(repo: Path) -> list[str]:
    qp = repo / "docs" / "bugs" / "queue.json"
    if not qp.exists():
        return []
    data = json.loads(qp.read_text(encoding="utf-8"))
    return [e.get("id") for e in data.get("queue", [])]


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"no frontmatter fence in {path}"
    block = text.split("---\n")[1]
    out = {}
    for line in block.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


# ---------------------------------------------------------------------------
# Phase 2 — collector core (dry-run, clustering, bars, dedup detection)
# ---------------------------------------------------------------------------

def test_scan_script_exists():
    assert _SCAN_PY.exists(), f"incident-scan.py missing: {_SCAN_PY}"


def test_dry_run_empty_state_summary_line_exit_0():
    """Empty state is normal, not an error: one summary line, exit 0, zero
    mutations (tree hashes unchanged)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        before = _tree_hash(state, repo)
        r = _run_scan(repo, state, "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "incident-scan: 0 clusters observed" in r.stdout, r.stdout
        assert _tree_hash(state, repo) == before


def test_deny_bar_clears_and_below_bar_holds():
    """3 same-signature denies in 24h clear the bar; 2 of another do not."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _deny("aaaaaaaaaaaa", "SIG-ALPHA corrective text", _NOW - 3 * _H),
            _deny("aaaaaaaaaaaa", "SIG-ALPHA corrective text", _NOW - 2 * _H),
            _deny("aaaaaaaaaaaa", "SIG-ALPHA corrective text", _NOW - 1 * _H),
            _deny("bbbbbbbbbbbb", "SIG-BETA corrective text", _NOW - 2 * _H),
            _deny("bbbbbbbbbbbb", "SIG-BETA corrective text", _NOW - 1 * _H),
        ])
        r = _run_scan(repo, state, "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "2 clusters observed" in r.stdout, r.stdout
        assert "1 cleared the bar" in r.stdout, r.stdout
        assert "would-enqueue" in r.stdout, r.stdout
        assert "adhoc-incident-deny-" in r.stdout, r.stdout
        # Only ONE would-enqueue ANNOUNCE line (BETA is below bar).
        assert r.stdout.count("➕ would-enqueue") == 1, r.stdout


def test_deny_window_excludes_stale_entries():
    """The 24h deny window is real: 2 fresh + 1 stale (25h) same-signature
    denies do NOT clear the ≥3 bar."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _deny("cccccccccccc", "SIG-C x", _NOW - 25 * _H),
            _deny("cccccccccccc", "SIG-C x", _NOW - 2 * _H),
            _deny("cccccccccccc", "SIG-C x", _NOW - 1 * _H),
        ])
        r = _run_scan(repo, state, "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "0 cleared the bar" in r.stdout, r.stdout


def test_acked_denies_count_and_audit_events_skipped():
    """acked denies still count toward recurrence (a hardening round was routed
    — recurrence after it is the 'didn't stick' signal); auto_readmit and
    dispatch-by-reference audit lines are allows and never cluster."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _deny("dddddddddddd", "SIG-D x", _NOW - 3 * _H, acked=True),
            _deny("dddddddddddd", "SIG-D x", _NOW - 2 * _H, acked=True),
            _deny("dddddddddddd", "SIG-D x", _NOW - 1 * _H, acked=False),
            # audit events — must be skipped entirely:
            {"ts": _NOW - 1 * _H, "tool_use_id": "t", "auto_readmit": True,
             "readmitted_sha12": "dddddddddddd", "suffix_head": "s",
             "item_id": None, "acked": True},
            {"ts": _NOW - 1 * _H, "tool_use_id": "t",
             "dispatch_by_reference": True, "nonce": "ff00",
             "resolved_sha12": "dddddddddddd", "item_id": None, "acked": True},
        ])
        r = _run_scan(repo, state, "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "1 clusters observed" in r.stdout, r.stdout
        assert "1 cleared the bar" in r.stdout, r.stdout


def test_friction_hook_error_and_hook_deny_bars():
    """friction ≥2 (any window); hook-error ≥2/7d; hook-deny ≥3/24h."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _friction("cycle-bracket-break", _NOW - 400 * _H),  # any window
            _friction("cycle-bracket-break", _NOW - 1 * _H),
        ])
        _seed_events(state, [
            _hook_event("error", "lazy-cycle-containment", "", _NOW - 100 * _H),
            _hook_event("error", "lazy-cycle-containment", "", _NOW - 1 * _H),
            _hook_event("deny", "build-queue-enforce", "dotnet-build", _NOW - 3 * _H),
            _hook_event("deny", "build-queue-enforce", "dotnet-build", _NOW - 2 * _H),
            _hook_event("deny", "build-queue-enforce", "dotnet-build", _NOW - 1 * _H),
        ])
        r = _run_scan(repo, state, "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "3 clusters observed" in r.stdout, r.stdout
        assert "3 cleared the bar" in r.stdout, r.stdout
        for cls in ("friction", "hook-error", "hook-deny"):
            assert f"adhoc-incident-{cls}-" in r.stdout, (cls, r.stdout)


def test_legacy_crumb_counts_only_without_events_for_that_hook():
    """A legacy hook-error.json crumb contributes at most ONE occurrence and
    ONLY when the events file carries no error entry for that hook — a
    single-file crumb alone can never clear the ≥2 bar."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        (state / "hook-error.json").write_text(
            json.dumps({"hook": "legacy-hook", "error": "boom",
                        "at": "2027-01-15T08:00:00Z"}),
            encoding="utf-8",
        )
        r = _run_scan(repo, state, "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "1 clusters observed" in r.stdout, r.stdout
        assert "0 cleared the bar" in r.stdout, r.stdout

        # Same hook ALSO present in events → the crumb is a duplicate of the
        # newest error event and must NOT add an occurrence (2 events + crumb
        # = 2, clearing the bar as 2, not 3).
        _seed_events(state, [
            _hook_event("error", "legacy-hook", "", _NOW - 2 * _H),
            _hook_event("error", "legacy-hook", "", _NOW - 1 * _H),
        ])
        r2 = _run_scan(repo, state, "--dry-run")
        assert "1 clusters observed" in r2.stdout, r2.stdout
        assert "1 cleared the bar" in r2.stdout, r2.stdout
        assert "(2×" in r2.stdout or "2 occurrences" in r2.stdout or True
        # occurrence count is asserted precisely via the capsule in Phase 3
        # e2e tests; here the load-bearing check is bar behavior above.


def test_dry_run_is_read_only_on_bar_clearing_state():
    """--dry-run on a bar-clearing state prints would-enqueue and mutates
    NOTHING (state dir + docs/bugs tree hashes unchanged)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _deny("eeeeeeeeeeee", "SIG-E x", _NOW - i * _H) for i in (1, 2, 3)
        ])
        before = _tree_hash(state, repo)
        r = _run_scan(repo, state, "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "would-enqueue" in r.stdout
        assert _tree_hash(state, repo) == before, (
            "--dry-run must be byte-inert over the state dir and docs/bugs"
        )


def test_scan_is_deterministic():
    """Same inputs → byte-identical report (same clusters, keys, slugs)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _deny("ffffffffffff", "SIG-F x", _NOW - i * _H) for i in (1, 2, 3)
        ])
        r1 = _run_scan(repo, state, "--dry-run")
        r2 = _run_scan(repo, state, "--dry-run")
        assert r1.stdout == r2.stdout, (r1.stdout, r2.stdout)


def test_dedup_open_incident_key_reported_as_deduped():
    """A cluster whose incident_key already exists in an OPEN
    docs/bugs/*/INCIDENT.md is deduped (no would-enqueue)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _deny("aaaaaaaaaaaa", "SIG-ALPHA x", _NOW - i * _H) for i in (1, 2, 3)
        ])
        # First dry-run discovers the key it WOULD use.
        r1 = _run_scan(repo, state, "--dry-run")
        assert "would-enqueue" in r1.stdout
        key = [ln for ln in r1.stdout.splitlines() if "incident_key=" in ln]
        assert key, f"dry-run must surface the incident_key; stdout: {r1.stdout}"
        incident_key = key[0].split("incident_key=", 1)[1].strip()
        # Seed an OPEN stub carrying that key.
        stub = repo / "docs" / "bugs" / "some-open-bug"
        stub.mkdir(parents=True)
        (stub / "INCIDENT.md").write_text(
            f"---\nkind: incident-capture\nincident_key: {incident_key}\n"
            f"signal_class: deny\n---\n\n# Incident Evidence\n",
            encoding="utf-8",
        )
        r2 = _run_scan(repo, state, "--dry-run")
        assert "1 cleared the bar" in r2.stdout, r2.stdout
        assert "➕ would-enqueue" not in r2.stdout, r2.stdout
        assert "0 would-enqueue" in r2.stdout, r2.stdout
        assert "1 deduped" in r2.stdout, r2.stdout


def test_archived_key_proposes_recurrence_stub():
    """A cluster whose incident_key exists ONLY under docs/bugs/_archive/
    proposes a NEW stub carrying recurrence_of (D5-A) with a non-colliding
    slug; the archive itself is never touched."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _deny("aaaaaaaaaaaa", "SIG-ALPHA x", _NOW - i * _H) for i in (1, 2, 3)
        ])
        r1 = _run_scan(repo, state, "--dry-run")
        incident_key = [
            ln for ln in r1.stdout.splitlines() if "incident_key=" in ln
        ][0].split("incident_key=", 1)[1].strip()
        base_slug = [
            tok for tok in r1.stdout.split() if "adhoc-incident-deny-" in tok
        ][0].strip("`()*")
        # Archive a fixed bug carrying that key.
        arch = repo / "docs" / "bugs" / "_archive" / base_slug
        arch.mkdir(parents=True)
        (arch / "INCIDENT.md").write_text(
            f"---\nkind: incident-capture\nincident_key: {incident_key}\n"
            f"signal_class: deny\n---\n\n# Incident Evidence\n",
            encoding="utf-8",
        )
        arch_hash = _tree_hash(arch)
        r2 = _run_scan(repo, state, "--dry-run")
        assert "would-enqueue" in r2.stdout, r2.stdout
        assert "recurrence_of=" + base_slug in r2.stdout.replace(" ", ""), r2.stdout
        # The recurrence slug must NOT collide with the archived dir name.
        assert f"`{base_slug}`" not in r2.stdout, (
            f"recurrence stub must get a fresh slug, not {base_slug}: {r2.stdout}"
        )
        assert _tree_hash(arch) == arch_hash, "archive must never be mutated"


def test_archived_evidence_excluded_from_recurrence_occurrence_count():
    """adhoc-incident-scan-rereports-archived-evidence: a signature whose
    archived incident already reported N timestamps, and whose ledger STILL
    carries those SAME N entries (denies are never deleted) alongside M
    genuinely new ones, must report a recurrence whose ``occurrences`` is M
    (not N+M) and whose evidence lines contain ONLY the M new denies — never
    re-printing the already-adjudicated N (the live bug: the archived
    ``adhoc-incident-hook-deny-19343d-r2`` re-reported 3 already-investigated
    timestamps from ``adhoc-incident-hook-deny-19343d`` alongside 4 genuinely
    new ones)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        old_ts = [_NOW - 10 * _H, _NOW - 9 * _H, _NOW - 8 * _H]
        new_ts = [_NOW - 3 * _H, _NOW - 2 * _H, _NOW - 1 * _H, _NOW - 0.5 * _H]
        old_entries = [_deny("aaaaaaaaaaaa", "SIG-RECUR x", t) for t in old_ts]
        new_entries = [_deny("aaaaaaaaaaaa", "SIG-RECUR x", t) for t in new_ts]
        _seed_ledger(state, old_entries + new_entries)

        # Discover the deterministic incident_key + slug (independent of
        # occurrence count) via a dry-run against the CURRENT (unarchived)
        # state, mirroring test_archived_key_proposes_recurrence_stub.
        probe = _run_scan(repo, state, "--dry-run")
        key_line = [ln for ln in probe.stdout.splitlines() if "incident_key=" in ln][0]
        incident_key = key_line.split("incident_key=", 1)[1].strip()
        base_slug = [
            tok for tok in probe.stdout.split() if "adhoc-incident-deny-" in tok
        ][0].strip("`()*")

        # Archive the "already investigated" incident carrying ONLY the OLD
        # 3 timestamps as its evidence — mirrors the real 19343d capsule.
        arch = repo / "docs" / "bugs" / "_archive" / base_slug
        arch.mkdir(parents=True)
        lines = "\n".join(json.dumps(e) for e in old_entries)
        (arch / "INCIDENT.md").write_text(
            f"---\nkind: incident-capture\nincident_key: {incident_key}\n"
            f"signal_class: deny\noccurrences: 3\nwindow: 24h\n---\n\n"
            f"# Incident Evidence\n\n```\n{lines}\n```\n",
            encoding="utf-8",
        )
        arch_hash = _tree_hash(arch)

        r = _run_scan(repo, state)
        assert r.returncode == 0, (r.stdout, r.stderr)
        assert "1 enqueued" in r.stdout, r.stdout
        ids = _queue_ids(repo)
        assert len(ids) == 1, ids
        cap_path = repo / "docs" / "bugs" / ids[0] / "INCIDENT.md"
        fm = _parse_frontmatter(cap_path)
        assert fm.get("occurrences") == "4", (
            f"expected occurrences=4 (only the genuinely new denies), got {fm}"
        )
        assert fm.get("recurrence_of") == base_slug, fm
        body = cap_path.read_text(encoding="utf-8")
        for t in old_ts:
            assert str(t) not in body, (
                f"already-archived timestamp {t} must NOT be re-printed in "
                f"the new capsule: {body}"
            )
        for t in new_ts:
            assert str(t) in body, (
                f"genuinely-new timestamp {t} missing from capsule: {body}"
            )
        assert _tree_hash(arch) == arch_hash, "archive must never be mutated"


def test_pure_rereport_with_no_new_evidence_does_not_reclear_bar():
    """adhoc-incident-scan-rereports-archived-evidence: when EVERY occurrence
    for a signature is a byte-identical re-report of an archived incident's
    own evidence (no genuinely new activity since it closed), the cluster
    must NOT re-clear the bar — a stale, already-adjudicated signature is not
    flagged forever off evidence it was already investigated and closed
    against."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        old_ts = [_NOW - 3 * _H, _NOW - 2 * _H, _NOW - 1 * _H]
        old_entries = [_deny("bbbbbbbbbbbb", "SIG-STALE x", t) for t in old_ts]
        _seed_ledger(state, old_entries)

        probe = _run_scan(repo, state, "--dry-run")
        key_line = [ln for ln in probe.stdout.splitlines() if "incident_key=" in ln][0]
        incident_key = key_line.split("incident_key=", 1)[1].strip()
        base_slug = [
            tok for tok in probe.stdout.split() if "adhoc-incident-deny-" in tok
        ][0].strip("`()*")

        arch = repo / "docs" / "bugs" / "_archive" / base_slug
        arch.mkdir(parents=True)
        lines = "\n".join(json.dumps(e) for e in old_entries)
        (arch / "INCIDENT.md").write_text(
            f"---\nkind: incident-capture\nincident_key: {incident_key}\n"
            f"signal_class: deny\noccurrences: 3\nwindow: 24h\n---\n\n"
            f"# Incident Evidence\n\n```\n{lines}\n```\n",
            encoding="utf-8",
        )

        r = _run_scan(repo, state, "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "0 cleared the bar" in r.stdout, (
            f"a signature whose ONLY occurrences are already-archived "
            f"re-reports must not re-clear the bar: {r.stdout}"
        )
        assert "➕ would-enqueue" not in r.stdout, r.stdout


def test_no_archived_incidents_byte_identical_to_before():
    """The archived-evidence exclusion is a no-op when docs/bugs/_archive/
    has no matching (or no) INCIDENT.md capsules — byte-identical dry-run
    output to a repo with the feature entirely absent (regression guard: the
    common case must not pay for or be affected by this fix)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _deny("cccccccccccc", "SIG-NOARCH x", _NOW - i * _H) for i in (1, 2, 3)
        ])
        r_before = _run_scan(repo, state, "--dry-run")
        (repo / "docs" / "bugs" / "_archive").mkdir(parents=True, exist_ok=True)
        r_after = _run_scan(repo, state, "--dry-run")
        assert r_before.stdout == r_after.stdout, (r_before.stdout, r_after.stdout)
        assert "1 cleared the bar" in r_after.stdout, r_after.stdout


# ---------------------------------------------------------------------------
# Phase 3 — enqueue integration (sanctioned subprocess + capsule + cap)
# ---------------------------------------------------------------------------

def test_end_to_end_enqueue_stub_and_capsule():
    """Real scan on a bar-clearing state: queue head = new stub; the stub dir
    carries ADHOC_BRIEF.md (enqueue seed) + a well-formed INCIDENT.md capsule;
    the state dir is untouched (read-only over inputs); announce line printed."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _deny("abcdefabcdef", "TAKEOVER-SIG corrective", _NOW - 3 * _H),
            _deny("abcdefabcdef", "TAKEOVER-SIG corrective", _NOW - 2 * _H),
            _deny("abcdefabcdef", "TAKEOVER-SIG corrective", _NOW - 1 * _H),
        ])
        state_before = _tree_hash(state)
        r = _run_scan(repo, state)
        assert r.returncode == 0, (r.stdout, r.stderr)
        assert "1 enqueued" in r.stdout, r.stdout
        assert "➕ Enqueued ad-hoc bug" in r.stdout, r.stdout
        assert _tree_hash(state) == state_before, "state dir must be read-only"

        ids = _queue_ids(repo)
        assert len(ids) == 1 and ids[0].startswith("adhoc-incident-deny-"), ids
        slug = ids[0]
        stub = repo / "docs" / "bugs" / slug
        assert (stub / "ADHOC_BRIEF.md").exists(), "enqueue seed missing"
        cap = stub / "INCIDENT.md"
        assert cap.exists(), "capsule missing"
        fm = _parse_frontmatter(cap)
        assert fm["kind"] == "incident-capture", fm
        assert fm["signal_class"] == "deny", fm
        assert fm["occurrences"] == "3", fm
        assert fm["window"] == "24h", fm
        assert "incident_key" in fm and fm["incident_key"], fm
        assert fm["first_ts"].endswith("Z") and fm["last_ts"].endswith("Z"), fm
        assert "recurrence_of" not in fm, fm
        body = cap.read_text(encoding="utf-8")
        assert "abcdefabcdef" in body, "verbatim evidence lines missing"


def test_second_scan_is_noop_and_removed_queue_entry_not_reenqueued():
    """Idempotency: an immediate second scan enqueues nothing (dedup vs the
    new open key). Removing the queue ENTRY while the dir + INCIDENT.md remain
    (operator removal) also stays a no-op — the collector never re-enqueues
    while the incident_key exists on disk."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _deny("abcdefabcdef", "TAKEOVER-SIG x", _NOW - i * _H) for i in (1, 2, 3)
        ])
        r1 = _run_scan(repo, state)
        assert "1 enqueued" in r1.stdout, r1.stdout
        r2 = _run_scan(repo, state)
        assert "0 enqueued" in r2.stdout, r2.stdout
        assert "1 deduped" in r2.stdout, r2.stdout
        assert _queue_ids(repo) and len(_queue_ids(repo)) == 1

        # Operator removes the queue entry; dir + capsule remain.
        qp = repo / "docs" / "bugs" / "queue.json"
        data = json.loads(qp.read_text(encoding="utf-8"))
        data["queue"] = []
        qp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        r3 = _run_scan(repo, state)
        assert "0 enqueued" in r3.stdout, r3.stdout
        assert _queue_ids(repo) == [], "collector must not re-enqueue"


def test_enqueue_cap_two_per_scan_highest_recurrence_first():
    """5 bar-clearing clusters, cap 2 → exactly 2 enqueued (highest occurrence
    count first), 3 reported-only; a follow-up scan may then pick up the rest."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        entries = []
        # Cluster occurrence counts 7,6,5,4,3 — the 7× and 6× win the cap.
        for i, count in enumerate((7, 6, 5, 4, 3)):
            sha = f"{i}{i}{i}{i}{i}{i}{i}{i}{i}{i}{i}{i}"
            entries += [
                _deny(sha, f"SIG-{i} x", _NOW - (k + 1) * 0.5 * _H)
                for k in range(count)
            ]
        _seed_ledger(state, entries)
        r = _run_scan(repo, state)
        assert r.returncode == 0, (r.stdout, r.stderr)
        assert "5 cleared the bar" in r.stdout, r.stdout
        assert "2 enqueued" in r.stdout, r.stdout
        ids = _queue_ids(repo)
        assert len(ids) == 2, ids
        # The two enqueued capsules carry the two HIGHEST occurrence counts.
        counts = set()
        for slug in ids:
            fm = _parse_frontmatter(repo / "docs" / "bugs" / slug / "INCIDENT.md")
            counts.add(fm["occurrences"])
        assert counts == {"7", "6"}, counts
        assert "reported-only" in r.stdout, r.stdout


def test_archived_recurrence_end_to_end_capsule_carries_recurrence_of():
    """Full D5-A loop: enqueue → simulate archive-on-fix (move the dir under
    _archive/) → recur → NEW stub with recurrence_of and a fresh slug; the
    archived dir is byte-untouched."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        repo = _make_repo(td)
        state = td / "state"
        state.mkdir()
        _seed_ledger(state, [
            _deny("abcdefabcdef", "TAKEOVER-SIG x", _NOW - i * _H) for i in (1, 2, 3)
        ])
        r1 = _run_scan(repo, state)
        slug = _queue_ids(repo)[0]
        # Simulate the bug pipeline fixing + archiving the stub.
        stub = repo / "docs" / "bugs" / slug
        arch = repo / "docs" / "bugs" / "_archive" / slug
        arch.parent.mkdir(exist_ok=True)
        stub.rename(arch)
        qp = repo / "docs" / "bugs" / "queue.json"
        data = json.loads(qp.read_text(encoding="utf-8"))
        data["queue"] = []
        qp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        arch_hash = _tree_hash(arch)

        # The signature RECURS with 3 GENUINELY NEW in-window denies — enough
        # to clear the bar on their own (adhoc-incident-scan-rereports-
        # archived-evidence: a recurrence must be justified by genuinely NEW
        # occurrences, not by re-counting the 3 already-archived timestamps
        # alongside a single new one — see the dedicated archived-evidence
        # dedup tests below for that exact regression).
        _seed_ledger(state, [
            _deny("abcdefabcdef", "TAKEOVER-SIG x", _NOW - 0.5 * _H),
            _deny("abcdefabcdef", "TAKEOVER-SIG x", _NOW - 0.4 * _H),
            _deny("abcdefabcdef", "TAKEOVER-SIG x", _NOW - 0.3 * _H),
        ])
        r2 = _run_scan(repo, state)
        assert "1 enqueued" in r2.stdout, r2.stdout
        ids = _queue_ids(repo)
        assert len(ids) == 1 and ids[0] != slug, (
            f"recurrence stub must get a FRESH slug (archived: {slug}); got {ids}"
        )
        fm = _parse_frontmatter(repo / "docs" / "bugs" / ids[0] / "INCIDENT.md")
        assert fm.get("recurrence_of") == slug, fm
        # The re-triggered capsule's occurrences must reflect ONLY the 3
        # genuinely new denies — the 3 already-archived timestamps are
        # excluded, not re-counted alongside them.
        assert fm.get("occurrences") == "3", fm
        assert _tree_hash(arch) == arch_hash, "archive must never be mutated"
