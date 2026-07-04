#!/usr/bin/env python3
"""
test_pipeline_visualizer.py — Tests for the lazy-pipeline-visualizer backend.

Covers the Phase 1 backend read layer:
  - WU-1: curated_stage rollup (display mapping) + leases freshness
  - WU-2: probe (shell state scripts + read queue/leases/roadmap) + TTL cache
  - WU-3: ThreadingHTTPServer + API routing + CLI entry

Pure-function units (curated_stage, leases freshness) are tested directly. The
cache is tested with an injected fake clock + a call counter (NO real sleeps).
The server is tested by binding an ephemeral port (port 0) in a daemon thread
and issuing real HTTP requests via http.client.

Run with: python -m pytest user/scripts/test_pipeline_visualizer.py -q
Stdlib + pytest only.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

# Insert the scripts directory on sys.path so `import pipeline_visualizer.*`
# resolves regardless of cwd (matches the repo's other test_*.py convention).
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# WU-1 — curated_stage rollup
# ---------------------------------------------------------------------------

class TestCuratedStageFeature:
    """curated_stage(current_step, terminal_reason, pipeline='feature')."""

    def test_pending_unknown_step(self):
        from pipeline_visualizer.curated_stage import curated_stage
        # Unknown/None step → Pending (the dedicated entry node), NOT Spec.
        assert curated_stage(None, None, "feature") == "Pending"
        assert curated_stage("", None, "feature") == "Pending"
        assert curated_stage("Step 99: not a real step", None, "feature") == "Pending"

    def test_spec_steps(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 4: no SPEC, no research", None, "feature") == "Spec"
        assert curated_stage("Step 4: ad-hoc brief → spec", None, "feature") == "Spec"
        assert curated_stage("Step 4: SPEC missing, research files present", None, "feature") == "Spec"
        assert curated_stage("Step 4.5: stub-spec detected", None, "feature") == "Spec"
        assert curated_stage("Step 4.6: upstream realign needed", None, "feature") == "Spec"

    def test_research_steps(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 5: generate research prompt", None, "feature") == "Research"
        assert curated_stage("Step 5: prompt exists, awaiting research", None, "feature") == "Research"
        assert curated_stage("Step 5: integrate research", None, "feature") == "Research"
        assert curated_stage("Step 5: needs-research (persistent)", None, "feature") == "Research"

    def test_plan_steps(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 6: plan feature (phases + plan)", None, "feature") == "Plan"
        assert curated_stage("Step 7a: write plan", None, "feature") == "Plan"

    def test_implement_steps(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 7a: execute plan", None, "feature") == "Implement"
        assert curated_stage(
            "Step 7a: flip plan Complete (cloud-saturated)", None, "feature"
        ) == "Implement"
        assert curated_stage(
            "Step 7a: flip plan Complete (stale — all referenced implementation deliverables already checked)",
            None, "feature",
        ) == "Implement"

    def test_validate_steps(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 9: run MCP tests", None, "feature") == "Validate"
        assert curated_stage("Step 9b: write validated", None, "feature") == "Validate"
        assert curated_stage("Step 9: skip-mcp-test → validated", None, "feature") == "Validate"
        assert curated_stage("Step 9: stale MCP results — re-verify", None, "feature") == "Validate"

    def test_complete_step(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 10: mark complete", None, "feature") == "Complete"

    def test_side_state_blocked(self):
        from pipeline_visualizer.curated_stage import curated_stage
        # terminal_reason dominates the curated rollup for side-states.
        assert curated_stage("Step 3: blocked", "blocked", "feature") == "Blocked"
        assert curated_stage(None, "blocked", "feature") == "Blocked"

    def test_side_state_needs_input(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage(None, "needs-input", "feature") == "Needs-input"
        assert curated_stage(None, "needs-research", "feature") == "Needs-input"
        assert curated_stage(None, "needs-spec-input", "feature") == "Needs-input"

    def test_side_state_deferred(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage(None, "cloud-queue-exhausted", "feature") == "Deferred"
        assert curated_stage(None, "device-queue-exhausted", "feature") == "Deferred"

    def test_global_all_remaining_deferred_maps_to_deferred(self):
        # bug-state-scoped-query-loses-deferred-bug-identity P3 — the global
        # unscoped deferral terminal must roll up to Deferred (previously
        # fell through to Pending, the original symptom on the unscoped path).
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage(None, "all-remaining-deferred", "feature") == "Deferred"

    def test_scoped_deferred_terminals_map_to_deferred(self):
        # P3 — the scoped per-feature deferred terminals from Part 2 (feature
        # side; cloud/device/host-capability axes) roll up to Deferred.
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage(None, "cloud-queue-exhausted-scoped", "feature") == "Deferred"
        assert curated_stage(None, "device-queue-exhausted-scoped", "feature") == "Deferred"
        assert curated_stage(None, "host-capability-saturated-scoped", "feature") == "Deferred"
        # The unscoped host-capability axis is the host-axis mirror of device.
        assert curated_stage(None, "host-capability-saturated", "feature") == "Deferred"

    def test_scoped_park_terminals_map_to_their_side_state(self):
        # P3 — a parked scoped match is in a blocked/needs-input side-state,
        # NOT a deferred one.
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage(None, "blocked-scoped", "feature") == "Blocked"
        assert curated_stage(None, "needs-input-scoped", "feature") == "Needs-input"

    def test_terminal_reason_precedence_over_step(self):
        from pipeline_visualizer.curated_stage import curated_stage
        # Even with a workflow step, a side-state terminal_reason wins.
        assert curated_stage("Step 7a: execute plan", "blocked", "feature") == "Blocked"


class TestCuratedStageBug:
    """curated_stage(..., pipeline='bug') — bug track omits Research."""

    def test_pending_unknown_step(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage(None, None, "bug") == "Pending"
        assert curated_stage("Step 99: nope", None, "bug") == "Pending"

    def test_spec_investigate(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 4: investigate bug", None, "bug") == "Spec"

    def test_plan_step(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 6: spec phases", None, "bug") == "Plan"
        assert curated_stage("Step 7a: write plan", None, "bug") == "Plan"

    def test_implement_step(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 7a: execute plan", None, "bug") == "Implement"

    def test_validate_step(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 9: run MCP tests", None, "bug") == "Validate"
        assert curated_stage("Step 9b: write validated", None, "bug") == "Validate"

    def test_complete_step(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 10: mark fixed", None, "bug") == "Complete"

    def test_side_states(self):
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage("Step 3: blocked", "blocked", "bug") == "Blocked"
        assert curated_stage(None, "needs-input", "bug") == "Needs-input"
        assert curated_stage(None, "cloud-queue-exhausted", "bug") == "Deferred"

    def test_global_all_remaining_deferred_maps_to_deferred(self):
        # P3 — the unscoped bug deferral terminal (the reproduced symptom path)
        # must roll up to Deferred, not Pending.
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage(None, "all-remaining-deferred", "bug") == "Deferred"

    def test_scoped_deferred_terminals_map_to_deferred(self):
        # P3 — the scoped per-bug deferred terminals from Part 1 (bug side;
        # operator-deferred / cloud / device axes) roll up to Deferred.
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage(None, "operator-deferred", "bug") == "Deferred"
        assert curated_stage(None, "cloud-queue-exhausted-scoped", "bug") == "Deferred"
        assert curated_stage(None, "device-queue-exhausted-scoped", "bug") == "Deferred"

    def test_scoped_park_terminals_map_to_their_side_state(self):
        # P3 — a parked scoped bug match sits in blocked/needs-input.
        from pipeline_visualizer.curated_stage import curated_stage
        assert curated_stage(None, "blocked-scoped", "bug") == "Blocked"
        assert curated_stage(None, "needs-input-scoped", "bug") == "Needs-input"


# ---------------------------------------------------------------------------
# WU-1 — leases freshness
# ---------------------------------------------------------------------------

class TestLeaseView:
    """lease_view(entry, now) computes heartbeat_fresh per lazy_coord rule:
    fresh iff heartbeat_epoch + ttl_seconds >= now."""

    @staticmethod
    def _entry(ts="2026-06-15T12:00:00Z", ttl=300):
        return {
            "worker_pid": 1234,
            "worktree_slot": "wt-01",
            "term_token": 3,
            "heartbeat_timestamp": ts,
            "ttl_seconds": ttl,
        }

    def _epoch(self, ts):
        from pipeline_visualizer.leases import _parse_iso
        return _parse_iso(ts)

    def test_fresh_well_within_ttl(self):
        from pipeline_visualizer.leases import lease_view
        entry = self._entry()
        now = self._epoch("2026-06-15T12:00:00Z") + 10
        v = lease_view("wi-7", entry, now)
        assert v["heartbeat_fresh"] is True

    def test_boundary_exactly_at_expiry_is_fresh(self):
        from pipeline_visualizer.leases import lease_view
        entry = self._entry(ttl=300)
        now = self._epoch("2026-06-15T12:00:00Z") + 300  # exactly at expiry
        v = lease_view("wi-7", entry, now)
        assert v["heartbeat_fresh"] is True

    def test_one_second_past_expiry_is_stale(self):
        from pipeline_visualizer.leases import lease_view
        entry = self._entry(ttl=300)
        now = self._epoch("2026-06-15T12:00:00Z") + 301
        v = lease_view("wi-7", entry, now)
        assert v["heartbeat_fresh"] is False

    def test_surfaces_full_shape(self):
        from pipeline_visualizer.leases import lease_view
        entry = self._entry()
        now = self._epoch("2026-06-15T12:00:00Z") + 5
        v = lease_view("wi-7", entry, now)
        assert v["wi_id"] == "wi-7"
        assert v["worker_pid"] == 1234
        assert v["worktree_slot"] == "wt-01"
        assert v["term_token"] == 3
        assert v["heartbeat_fresh"] is True
        assert abs(v["age_seconds"] - 5) < 0.001

    def test_parse_iso_matches_lazy_coord(self):
        # The ISO 'Z' parse must agree with lazy_coord._parse_iso exactly.
        from pipeline_visualizer.leases import _parse_iso as pv_parse
        import lazy_coord
        ts = "2026-06-15T12:34:56Z"
        assert pv_parse(ts) == lazy_coord._parse_iso(ts)


# ---------------------------------------------------------------------------
# WU-2 — TTL cache
# ---------------------------------------------------------------------------

class _FakeClock:
    def __init__(self, start=1000.0):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class TestTtlCache:
    def test_single_probe_within_window(self):
        from pipeline_visualizer.cache import TtlCache
        clock = _FakeClock()
        calls = {"n": 0}

        def producer():
            calls["n"] += 1
            return {"v": calls["n"]}

        cache = TtlCache(ttl=2.0, clock=clock)
        # Many reads within one TTL window → producer invoked exactly once.
        for _ in range(5):
            cache.get(producer)
        assert calls["n"] == 1

    def test_reinvoke_after_ttl(self):
        from pipeline_visualizer.cache import TtlCache
        clock = _FakeClock()
        calls = {"n": 0}

        def producer():
            calls["n"] += 1
            return calls["n"]

        cache = TtlCache(ttl=2.0, clock=clock)
        assert cache.get(producer) == 1
        clock.advance(1.9)
        assert cache.get(producer) == 1  # still within window
        clock.advance(0.2)  # now 2.1s elapsed
        assert cache.get(producer) == 2  # re-invoked

    def test_double_checked_lock_two_reads_same_time(self):
        from pipeline_visualizer.cache import TtlCache
        clock = _FakeClock()
        calls = {"n": 0}

        def producer():
            calls["n"] += 1
            return calls["n"]

        cache = TtlCache(ttl=2.0, clock=clock)
        # Two reads at the same fake time → exactly 1 producer call.
        cache.get(producer)
        cache.get(producer)
        assert calls["n"] == 1

    def test_default_ttl_is_2s(self):
        from pipeline_visualizer.cache import TtlCache, DEFAULT_TTL_SECONDS
        assert DEFAULT_TTL_SECONDS == 2.0
        cache = TtlCache()
        assert cache.ttl == 2.0


# ---------------------------------------------------------------------------
# WU-2 — probe
# ---------------------------------------------------------------------------

def _seed_feature_repo(tmp_path: Path, feature_id="demo-feat") -> Path:
    """Seed a minimal repo-root with a features queue + SPEC so the real
    lazy-state.py produces a parseable per-item state."""
    features = tmp_path / "docs" / "features"
    features.mkdir(parents=True)
    (features / "queue.json").write_text(
        json.dumps({"queue": [
            {"id": feature_id, "name": "Demo Feature",
             "spec_dir": feature_id, "tier": 1}
        ]}, indent=2) + "\n",
        encoding="utf-8",
    )
    (features / "ROADMAP.md").write_text("# Roadmap\n\n- demo-feat\n", encoding="utf-8")
    spec_dir = features / feature_id
    spec_dir.mkdir()
    (spec_dir / "SPEC.md").write_text(
        "# Demo Feature\n\n**Status:** Draft\n", encoding="utf-8"
    )
    return tmp_path


class TestProbeParsing:
    def test_parse_state_json_attaches_curated_stage(self):
        from pipeline_visualizer.probe import parse_item_state
        raw = {
            "feature_id": "demo-feat",
            "feature_name": "Demo Feature",
            "current_step": "Step 7a: execute plan",
            "terminal_reason": None,
        }
        item = parse_item_state(raw, pipeline="feature")
        assert item["feature_id"] == "demo-feat"
        assert item["current_step"] == "Step 7a: execute plan"
        assert item["terminal_reason"] is None
        assert item["curated_stage"] == "Implement"

    def test_malformed_output_flagged_not_crash(self):
        from pipeline_visualizer.probe import parse_state_output
        # Non-JSON stdout must not crash — the item is flagged with an error.
        item = parse_state_output("not json at all {", item_id="x", pipeline="feature")
        assert item["error"] is not None
        assert item["curated_stage"] == "Pending"

    def test_read_queue_returns_order(self, tmp_path):
        from pipeline_visualizer.probe import read_queue
        qpath = tmp_path / "queue.json"
        qpath.write_text(json.dumps({"queue": [
            {"id": "a"}, {"id": "b"}, {"id": "c"},
        ]}) + "\n", encoding="utf-8")
        ids = [e["id"] for e in read_queue(qpath)]
        assert ids == ["a", "b", "c"]

    def test_read_queue_missing_is_empty(self, tmp_path):
        from pipeline_visualizer.probe import read_queue
        assert read_queue(tmp_path / "nope.json") == []

    def test_read_leases_returns_views(self, tmp_path):
        from pipeline_visualizer.probe import read_leases
        lpath = tmp_path / "leases.json"
        lpath.write_text(json.dumps({
            "wi-1": {
                "worker_pid": 11, "worktree_slot": "wt-00", "term_token": 1,
                "heartbeat_timestamp": "2026-06-15T12:00:00Z", "ttl_seconds": 300,
            }
        }), encoding="utf-8")
        from pipeline_visualizer.leases import _parse_iso
        now = _parse_iso("2026-06-15T12:00:10Z")
        views = read_leases(lpath, now=now)
        assert len(views) == 1
        assert views[0]["wi_id"] == "wi-1"
        assert views[0]["heartbeat_fresh"] is True

    def test_read_leases_missing_is_empty(self, tmp_path):
        from pipeline_visualizer.probe import read_leases
        assert read_leases(tmp_path / "nope.json") == []

    def test_probe_against_real_lazy_state(self, tmp_path):
        # At least one test drives the REAL lazy-state.py against a temp fixture
        # so a contract drift surfaces as a failure (SPEC "Token on correct stage").
        from pipeline_visualizer.probe import probe_state
        repo_root = _seed_feature_repo(tmp_path)
        state = probe_state(repo_root)
        assert "features" in state
        assert "bugs" in state
        assert "leases" in state
        assert "roadmap" in state
        assert "server_time" in state
        feats = state["features"]
        assert len(feats) == 1
        assert feats[0]["feature_id"] == "demo-feat"
        # A freshly-specced-but-unplanned item should be on Spec or Pending —
        # the key contract is that curated_stage is present and valid.
        assert feats[0]["curated_stage"] in {
            "Pending", "Spec", "Research", "Plan", "Implement",
            "Validate", "Complete", "Blocked", "Needs-input", "Deferred",
        }


# ---------------------------------------------------------------------------
# WU-3 — ThreadingHTTPServer + API routing
# ---------------------------------------------------------------------------

import http.client


def _start_server(repo_root: Path):
    from pipeline_visualizer.server import make_server
    httpd = make_server(repo_root=repo_root, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, httpd.server_address[1]


class TestServer:
    def test_api_state_200_json(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path)
        httpd, port = _start_server(repo_root)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
            conn.request("GET", "/api/state")
            resp = conn.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read())
            assert isinstance(body["features"], list)
            assert isinstance(body["bugs"], list)
            assert isinstance(body["leases"], list)
            assert body["features"][0]["curated_stage"] in {
                "Pending", "Spec", "Research", "Plan", "Implement",
                "Validate", "Complete", "Blocked", "Needs-input", "Deferred",
            }
        finally:
            httpd.shutdown()

    def test_api_queue_200_order(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path)
        httpd, port = _start_server(repo_root)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
            conn.request("GET", "/api/queue")
            resp = conn.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read())
            assert [e["id"] for e in body["features"]] == ["demo-feat"]
            assert body["bugs"] == []
        finally:
            httpd.shutdown()

    def test_unknown_path_404(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path)
        httpd, port = _start_server(repo_root)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
            conn.request("GET", "/nope")
            resp = conn.getresponse()
            resp.read()
            assert resp.status == 404
        finally:
            httpd.shutdown()

    def test_state_served_through_cache(self, tmp_path):
        # Concurrent/sequential GETs within the TTL window → 1 underlying probe.
        from pipeline_visualizer import server as server_mod
        repo_root = _seed_feature_repo(tmp_path)
        calls = {"n": 0}
        real_probe = server_mod.probe_state

        def counting_probe(root):
            calls["n"] += 1
            return real_probe(root)

        server_mod.probe_state = counting_probe
        try:
            httpd, port = _start_server(repo_root)
            try:
                for _ in range(5):
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
                    conn.request("GET", "/api/state")
                    conn.getresponse().read()
                assert calls["n"] == 1
            finally:
                httpd.shutdown()
        finally:
            server_mod.probe_state = real_probe


# ---------------------------------------------------------------------------
# WU-4 — static-asset serving (Phase 2)
# ---------------------------------------------------------------------------

class TestStaticServing:
    """The server serves the bundled static frontend; API routes still win."""

    def _get(self, port, path):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        return resp, body

    def test_root_serves_index_html(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path)
        httpd, port = _start_server(repo_root)
        try:
            resp, body = self._get(port, "/")
            assert resp.status == 200
            ctype = resp.getheader("Content-Type") or ""
            assert "text/html" in ctype
            # The shipped index.html, not a directory listing.
            assert b"<html" in body.lower() or b"<!doctype html" in body.lower()
        finally:
            httpd.shutdown()

    def test_app_js_served(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path)
        httpd, port = _start_server(repo_root)
        try:
            resp, body = self._get(port, "/static/app.js")
            assert resp.status == 200
            ctype = resp.getheader("Content-Type") or ""
            assert "javascript" in ctype or "ecmascript" in ctype
            assert len(body) > 0
        finally:
            httpd.shutdown()

    def test_styles_css_served(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path)
        httpd, port = _start_server(repo_root)
        try:
            resp, body = self._get(port, "/static/styles.css")
            assert resp.status == 200
            ctype = resp.getheader("Content-Type") or ""
            assert "css" in ctype
        finally:
            httpd.shutdown()

    def test_vendored_cytoscape_served(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path)
        httpd, port = _start_server(repo_root)
        try:
            resp, body = self._get(port, "/static/cytoscape.umd.js")
            assert resp.status == 200
            assert len(body) > 0
        finally:
            httpd.shutdown()

    def test_api_state_still_wins_over_static(self, tmp_path):
        # Regression: API routes must be matched BEFORE the static fallthrough,
        # so /api/state returns JSON (not a 404 file-not-found).
        repo_root = _seed_feature_repo(tmp_path)
        httpd, port = _start_server(repo_root)
        try:
            resp, body = self._get(port, "/api/state")
            assert resp.status == 200
            ctype = resp.getheader("Content-Type") or ""
            assert "application/json" in ctype
            parsed = json.loads(body)
            assert isinstance(parsed["features"], list)
        finally:
            httpd.shutdown()

    def test_api_queue_still_wins_over_static(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path)
        httpd, port = _start_server(repo_root)
        try:
            resp, body = self._get(port, "/api/queue")
            assert resp.status == 200
            assert "application/json" in (resp.getheader("Content-Type") or "")
        finally:
            httpd.shutdown()

    def test_path_traversal_does_not_serve_source(self, tmp_path):
        # GET /static/../server.py must NOT serve the backend source file.
        repo_root = _seed_feature_repo(tmp_path)
        httpd, port = _start_server(repo_root)
        try:
            resp, body = self._get(port, "/static/../server.py")
            # Either normalized away (404) or redirected — never the source bytes.
            assert b"ThreadingHTTPServer" not in body
            assert b"def make_server" not in body
        finally:
            httpd.shutdown()


# ---------------------------------------------------------------------------
# WU-6 — receipt_present (Phase 3 backend slice)
# ---------------------------------------------------------------------------

_VALID_COMPLETED = (
    "---\n"
    "kind: completed\n"
    "feature_id: demo-feat\n"
    "provenance: gate-verified\n"
    "date: 2026-06-15\n"
    "---\n\n# Completed\n"
)
_VALID_FIXED = (
    "---\n"
    "kind: fixed\n"
    "bug_id: demo-bug\n"
    "provenance: gate-verified\n"
    "date: 2026-06-15\n"
    "---\n\n# Fixed\n"
)


def _seed_completed_feature_repo(tmp_path: Path, feature_id="demo-feat",
                                 receipt: str | None = None) -> Path:
    """Seed a feature repo and, when `receipt` is given, drop a COMPLETED.md
    into the item's spec dir so probe should report receipt_present=True."""
    repo_root = _seed_feature_repo(tmp_path, feature_id=feature_id)
    if receipt is not None:
        spec_dir = repo_root / "docs" / "features" / feature_id
        (spec_dir / "COMPLETED.md").write_text(receipt, encoding="utf-8")
    return repo_root


def _seed_bug_repo(tmp_path: Path, bug_id="demo-bug", receipt: str | None = None) -> Path:
    bugs = tmp_path / "docs" / "bugs"
    bugs.mkdir(parents=True)
    (bugs / "queue.json").write_text(
        json.dumps({"queue": [
            {"id": bug_id, "name": "Demo Bug", "spec_dir": bug_id, "tier": 1,
             "severity": "high"}
        ]}, indent=2) + "\n",
        encoding="utf-8",
    )
    spec_dir = bugs / bug_id
    spec_dir.mkdir()
    (spec_dir / "SPEC.md").write_text(
        "# Demo Bug\n\n**Status:** Draft\n", encoding="utf-8"
    )
    if receipt is not None:
        (spec_dir / "FIXED.md").write_text(receipt, encoding="utf-8")
    # A features dir must exist for probe_state to not error on the queue read.
    (tmp_path / "docs" / "features").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "features" / "queue.json").write_text(
        json.dumps({"queue": []}, indent=2) + "\n", encoding="utf-8"
    )
    return tmp_path


class TestReceiptPresent:
    """probe attaches per-item receipt_present (COMPLETED.md / FIXED.md stat).

    receipt_present is the signal Phase 3's UI uses to drop a completed token.
    It is a read-only stat check — no state-script change.
    """

    def test_feature_without_receipt_is_false(self, tmp_path):
        from pipeline_visualizer.probe import probe_state
        repo_root = _seed_completed_feature_repo(tmp_path, receipt=None)
        state = probe_state(repo_root)
        feat = state["features"][0]
        assert feat["receipt_present"] is False

    def test_feature_with_completed_receipt_is_true(self, tmp_path):
        from pipeline_visualizer.probe import probe_state
        repo_root = _seed_completed_feature_repo(tmp_path, receipt=_VALID_COMPLETED)
        state = probe_state(repo_root)
        feat = state["features"][0]
        assert feat["receipt_present"] is True

    def test_bug_without_receipt_is_false(self, tmp_path):
        from pipeline_visualizer.probe import probe_state
        repo_root = _seed_bug_repo(tmp_path, receipt=None)
        state = probe_state(repo_root)
        bug = state["bugs"][0]
        assert bug["receipt_present"] is False

    def test_bug_with_fixed_receipt_is_true(self, tmp_path):
        from pipeline_visualizer.probe import probe_state
        repo_root = _seed_bug_repo(tmp_path, receipt=_VALID_FIXED)
        state = probe_state(repo_root)
        bug = state["bugs"][0]
        assert bug["receipt_present"] is True

    def test_receipt_present_is_per_item_path(self, tmp_path):
        # The stat must target the item's OWN spec dir — a receipt in feature A's
        # dir must not mark feature B as receipted.
        from pipeline_visualizer.probe import probe_state
        features = tmp_path / "docs" / "features"
        features.mkdir(parents=True)
        (features / "queue.json").write_text(
            json.dumps({"queue": [
                {"id": "feat-a", "name": "Feat A", "spec_dir": "feat-a", "tier": 1},
                {"id": "feat-b", "name": "Feat B", "spec_dir": "feat-b", "tier": 1},
            ]}, indent=2) + "\n",
            encoding="utf-8",
        )
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        for fid in ("feat-a", "feat-b"):
            d = features / fid
            d.mkdir()
            (d / "SPEC.md").write_text("# x\n\n**Status:** Draft\n", encoding="utf-8")
        (features / "feat-a" / "COMPLETED.md").write_text(
            _VALID_COMPLETED.replace("demo-feat", "feat-a"), encoding="utf-8"
        )
        state = probe_state(tmp_path)
        by_id = {f["feature_id"]: f for f in state["features"]}
        assert by_id["feat-a"]["receipt_present"] is True
        assert by_id["feat-b"]["receipt_present"] is False


# ---------------------------------------------------------------------------
# WU-7 — queue_writer (permutation-validated atomic reorder + AV-lock retry)
# ---------------------------------------------------------------------------

def _write_queue(path: Path, ids):
    path.write_text(
        json.dumps({"queue": [{"id": i, "name": i, "spec_dir": i, "tier": 1}
                              for i in ids]}, indent=2) + "\n",
        encoding="utf-8",
    )


class TestQueueWriterPermutation:
    """reorder_queue validates the posted order is a true permutation."""

    def test_true_permutation_accepted(self, tmp_path):
        from pipeline_visualizer.queue_writer import reorder_queue
        qp = tmp_path / "queue.json"
        _write_queue(qp, ["a", "b", "c"])
        reorder_queue(qp, ["c", "a", "b"])
        data = json.loads(qp.read_text(encoding="utf-8"))
        assert [e["id"] for e in data["queue"]] == ["c", "a", "b"]

    def test_added_id_rejected_no_write(self, tmp_path):
        from pipeline_visualizer.queue_writer import reorder_queue, PermutationError
        qp = tmp_path / "queue.json"
        _write_queue(qp, ["a", "b"])
        before = qp.read_bytes()
        with pytest.raises(PermutationError):
            reorder_queue(qp, ["a", "b", "c"])  # added id
        assert qp.read_bytes() == before

    def test_dropped_id_rejected_no_write(self, tmp_path):
        from pipeline_visualizer.queue_writer import reorder_queue, PermutationError
        qp = tmp_path / "queue.json"
        _write_queue(qp, ["a", "b", "c"])
        before = qp.read_bytes()
        with pytest.raises(PermutationError):
            reorder_queue(qp, ["a", "b"])  # dropped id
        assert qp.read_bytes() == before

    def test_duplicate_id_rejected_no_write(self, tmp_path):
        from pipeline_visualizer.queue_writer import reorder_queue, PermutationError
        qp = tmp_path / "queue.json"
        _write_queue(qp, ["a", "b"])
        before = qp.read_bytes()
        with pytest.raises(PermutationError):
            reorder_queue(qp, ["a", "a"])  # dupe
        assert qp.read_bytes() == before


class TestQueueWriterAtomic:
    """The write matches lazy-state.py's _atomic_write convention so /lazy reads
    it cleanly: indent=2 + a single trailing newline, via temp + os.replace."""

    def test_round_trip_format_matches_convention(self, tmp_path):
        from pipeline_visualizer.queue_writer import reorder_queue
        qp = tmp_path / "queue.json"
        _write_queue(qp, ["a", "b", "c"])
        reorder_queue(qp, ["b", "c", "a"])
        text = qp.read_text(encoding="utf-8")
        # Valid JSON, ends with exactly one trailing newline, indent=2.
        data = json.loads(text)
        assert [e["id"] for e in data["queue"]] == ["b", "c", "a"]
        assert text.endswith("}\n")
        assert not text.endswith("}\n\n")
        assert text == json.dumps(data, indent=2) + "\n"

    def test_preserves_sibling_keys_and_entry_fields(self, tmp_path):
        # A reorder must not drop other top-level keys or per-entry fields.
        from pipeline_visualizer.queue_writer import reorder_queue
        qp = tmp_path / "queue.json"
        qp.write_text(json.dumps({
            "schema": 2,
            "queue": [
                {"id": "a", "name": "A", "tier": 1, "stub": True},
                {"id": "b", "name": "B", "tier": 2},
            ],
        }, indent=2) + "\n", encoding="utf-8")
        reorder_queue(qp, ["b", "a"])
        data = json.loads(qp.read_text(encoding="utf-8"))
        assert data["schema"] == 2
        assert [e["id"] for e in data["queue"]] == ["b", "a"]
        a = next(e for e in data["queue"] if e["id"] == "a")
        assert a["stub"] is True and a["name"] == "A"


class TestQueueWriterRetry:
    """os.replace AV-lock retry: PermissionError [WinError 32] twice then OK."""

    def test_retry_succeeds_within_three_tries(self, tmp_path, monkeypatch):
        from pipeline_visualizer import queue_writer
        qp = tmp_path / "queue.json"
        _write_queue(qp, ["a", "b"])
        real_replace = queue_writer.os.replace
        calls = {"n": 0}

        def flaky_replace(src, dst):
            calls["n"] += 1
            if calls["n"] <= 2:
                err = PermissionError("locked")
                err.winerror = 32
                raise err
            return real_replace(src, dst)

        monkeypatch.setattr(queue_writer.os, "replace", flaky_replace)
        queue_writer.reorder_queue(qp, ["b", "a"], retry_sleep=0)
        assert calls["n"] == 3
        data = json.loads(qp.read_text(encoding="utf-8"))
        assert [e["id"] for e in data["queue"]] == ["b", "a"]

    def test_exhausted_retries_raises(self, tmp_path, monkeypatch):
        from pipeline_visualizer import queue_writer
        qp = tmp_path / "queue.json"
        _write_queue(qp, ["a", "b"])

        def always_locked(src, dst):
            err = PermissionError("locked")
            err.winerror = 32
            raise err

        monkeypatch.setattr(queue_writer.os, "replace", always_locked)
        with pytest.raises(queue_writer.QueueWriteError):
            queue_writer.reorder_queue(qp, ["b", "a"], retry_sleep=0)


# ---------------------------------------------------------------------------
# WU-7 — POST /api/queue route + run-marker refusal + queue_locked flag
# ---------------------------------------------------------------------------

import contextlib
import os as _os


@contextlib.contextmanager
def _isolated_state_dir(tmp_path, marker: bool):
    """Point lazy_core.read_run_marker at a temp state dir; optionally seed a
    fresh run marker so the server detects an active run."""
    state_dir = tmp_path / "_state"
    state_dir.mkdir(exist_ok=True)
    prev = _os.environ.get("LAZY_STATE_DIR")
    _os.environ["LAZY_STATE_DIR"] = str(state_dir)
    try:
        marker_path = state_dir / "lazy-run-marker.json"
        if marker:
            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            marker_path.write_text(json.dumps({
                "pipeline": "feature", "started_at": now,
                "session_id": None, "pid": 1234,
            }), encoding="utf-8")
        elif marker_path.exists():
            marker_path.unlink()
        yield
    finally:
        if prev is None:
            _os.environ.pop("LAZY_STATE_DIR", None)
        else:
            _os.environ["LAZY_STATE_DIR"] = prev


def _post(port, path, payload):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    body = json.dumps(payload)
    conn.request("POST", path, body=body,
                 headers={"Content-Type": "application/json",
                          "Content-Length": str(len(body))})
    resp = conn.getresponse()
    data = resp.read()
    return resp, data


class TestPostQueueRoute:
    def test_idle_reorder_persists(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path, feature_id="demo-feat")
        # Add a second feature so a reorder is observable.
        qp = repo_root / "docs" / "features" / "queue.json"
        _write_queue(qp, ["one", "two", "three"])
        with _isolated_state_dir(tmp_path, marker=False):
            httpd, port = _start_server(repo_root)
            try:
                resp, _ = _post(port, "/api/queue",
                                {"pipeline": "features", "order": ["three", "one", "two"]})
                assert resp.status == 200
            finally:
                httpd.shutdown()
        data = json.loads(qp.read_text(encoding="utf-8"))
        assert [e["id"] for e in data["queue"]] == ["three", "one", "two"]

    def test_run_marker_refuses_409_byte_identical(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path, feature_id="demo-feat")
        qp = repo_root / "docs" / "features" / "queue.json"
        _write_queue(qp, ["one", "two", "three"])
        before = qp.read_bytes()
        with _isolated_state_dir(tmp_path, marker=True):
            httpd, port = _start_server(repo_root)
            try:
                resp, _ = _post(port, "/api/queue",
                                {"pipeline": "features", "order": ["three", "two", "one"]})
                assert resp.status == 409
            finally:
                httpd.shutdown()
        assert qp.read_bytes() == before  # byte-identical — refused, not written

    def test_state_reports_queue_locked_under_marker(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path, feature_id="demo-feat")
        with _isolated_state_dir(tmp_path, marker=True):
            httpd, port = _start_server(repo_root)
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
                conn.request("GET", "/api/state")
                body = json.loads(conn.getresponse().read())
                assert body["queue_locked"] is True
            finally:
                httpd.shutdown()

    def test_state_reports_unlocked_when_idle(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path, feature_id="demo-feat")
        with _isolated_state_dir(tmp_path, marker=False):
            httpd, port = _start_server(repo_root)
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
                conn.request("GET", "/api/state")
                body = json.loads(conn.getresponse().read())
                assert body["queue_locked"] is False
            finally:
                httpd.shutdown()

    def test_post_bad_permutation_400(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path, feature_id="demo-feat")
        qp = repo_root / "docs" / "features" / "queue.json"
        _write_queue(qp, ["one", "two"])
        with _isolated_state_dir(tmp_path, marker=False):
            httpd, port = _start_server(repo_root)
            try:
                resp, _ = _post(port, "/api/queue",
                                {"pipeline": "features", "order": ["one", "two", "x"]})
                assert resp.status == 400
            finally:
                httpd.shutdown()


# ---------------------------------------------------------------------------
# multi-repo-concurrent-runs (Phase 3 WU-3.3) — per-repo keyed marker lookup
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _keyed_home(tmp_path):
    """Point HOME/USERPROFILE at a throwaway dir, clear LAZY_STATE_DIR, and
    reset lazy_core's per-process migration + active-repo globals so the
    production keyed-state-dir path (~/.claude/state/<repo_key>/) is exercised
    instead of the LAZY_STATE_DIR override."""
    import lazy_core
    home = tmp_path / "_home"
    home.mkdir(exist_ok=True)
    keys = ("HOME", "USERPROFILE", "LAZY_STATE_DIR")
    prev = {k: _os.environ.get(k) for k in keys}
    _os.environ["HOME"] = str(home)
    _os.environ["USERPROFILE"] = str(home)
    _os.environ.pop("LAZY_STATE_DIR", None)
    lazy_core._legacy_state_migrated = False
    lazy_core.set_active_repo_root(None)
    try:
        yield home
    finally:
        for k, v in prev.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v
        lazy_core._legacy_state_migrated = False
        lazy_core.set_active_repo_root(None)


class TestKeyedMarkerLookup:
    """WU-3.3: with LAZY_STATE_DIR unset (production), _run_marker_present binds
    the visualized repo so it reads THAT repo's keyed state subdir — a marker in
    repo A is seen for A and NOT for B (per-repo isolation)."""

    def test_marker_present_only_for_owning_repo_keyed(self, tmp_path):
        import lazy_core
        from pipeline_visualizer.server import _run_marker_present

        repo_a = tmp_path / "repoA"
        repo_b = tmp_path / "repoB"
        repo_a.mkdir()
        repo_b.mkdir()

        with _keyed_home(tmp_path):
            # Write a live feature marker into repo A's keyed subdir.
            lazy_core.set_active_repo_root(str(repo_a))
            lazy_core.write_run_marker(pipeline="feature", cloud=False,
                                       repo_root=str(repo_a), max_cycles=20)
            # The visualizer, rendering repo A, sees the marker...
            assert _run_marker_present(repo_a) is True
            # ...and rendering repo B (a different keyed subdir) does not.
            assert _run_marker_present(repo_b) is False

    def test_no_marker_absent_for_any_repo_keyed(self, tmp_path):
        from pipeline_visualizer.server import _run_marker_present
        repo = tmp_path / "repoFresh"
        repo.mkdir()
        with _keyed_home(tmp_path):
            assert _run_marker_present(repo) is False


# ---------------------------------------------------------------------------
# harness-telemetry-ledger Phase 3 — pipeline_visualizer.trends
#
# Pure-read aggregation (D9-A) over the telemetry ledger (+ the deny ledger),
# an /api/trends route through its own TtlCache, and the D8 retro CLI
# (`python -m pipeline_visualizer.trends --run-id <id> --repo-root <repo>`).
# Aggregates are asserted against HAND-COMPUTED values over a fixture ledger.
# ---------------------------------------------------------------------------

import subprocess as _tl_subprocess


def _tl_event(ts, event, run_id="R1", pipeline="feature", item_id=None, data=None):
    return {"v": 1, "ts": ts, "run_id": run_id, "pipeline": pipeline,
            "event": event, "item_id": item_id, "data": data or {}}


def _tl_fixture_events():
    """Two-run fixture. Hand-computed expectations:
    R1: duration 120s; 2 cycle-begins (1 real + 1 meta); 1 completion
        (__mark_complete__) → cycles/completion = 2.0; 1 gate-refusal;
        1 containment-refusal; 1 halt (f2, needs-input) resolved after 20s.
    R2: run-start only (no run-end → duration None); 1 unresolved halt (f3)."""
    return [
        _tl_event(100.0, "run-start"),
        _tl_event(110.0, "cycle-begin", item_id="f1",
                  data={"kind": "real", "sub_skill": "execute-plan"}),
        _tl_event(120.0, "cycle-end", item_id="f1", data={"cleared": True}),
        _tl_event(130.0, "dispatch", item_id="f1",
                  data={"current_step": "Step 7a: execute plan",
                        "sub_skill": "execute-plan", "terminal_reason": None}),
        _tl_event(140.0, "gate-refusal", item_id="f1",
                  data={"gate": "verify-ledger", "failing_check": "clean_tree"}),
        _tl_event(150.0, "cycle-begin", item_id="f1",
                  data={"kind": "meta", "sub_skill": "__mark_complete__"}),
        _tl_event(160.0, "cycle-end", item_id="f1", data={"cleared": True}),
        _tl_event(170.0, "pseudo-applied", item_id="f1",
                  data={"pseudo": "__mark_complete__"}),
        _tl_event(180.0, "halt", item_id="f2",
                  data={"terminal_reason": "needs-input"}),
        _tl_event(200.0, "sentinel-resolved", item_id="f2",
                  data={"sentinel": "NEEDS_INPUT.md"}),
        _tl_event(210.0, "containment-refusal", item_id="f1",
                  data={"op": "--apply-pseudo",
                        "guard": "refuse_if_cycle_active"}),
        _tl_event(220.0, "run-end", data={"reason": "terminal"}),
        _tl_event(300.0, "run-start", run_id="R2"),
        _tl_event(310.0, "halt", run_id="R2", item_id="f3",
                  data={"terminal_reason": "blocked"}),
    ]


_TL_FIXTURE_DENIES = [
    {"ts": 1.0, "tool_use_id": "tu-1", "denied_sha12": "a" * 12,
     "reason_head": "deny", "prompt_head": "p", "acked": False},
    {"ts": 2.0, "kind": "process-friction", "reason_head": "cycle-bracket-break",
     "detail": "d", "acked": False},
    {"ts": 3.0, "tool_use_id": "tu-2", "auto_readmit": True,
     "readmitted_sha12": "b" * 12, "suffix_head": "s", "item_id": None,
     "acked": True},
]


class TestTrendsAggregates:
    """Pure functions over hand-built event lists (no I/O)."""

    def test_runs_grouping(self):
        from pipeline_visualizer.trends import runs
        got = runs(_tl_fixture_events())
        assert [r["run_id"] for r in got] == ["R1", "R2"]
        r1 = got[0]
        assert r1["pipeline"] == "feature"
        assert r1["first_ts"] == 100.0 and r1["last_ts"] == 220.0
        assert r1["event_counts"]["cycle-begin"] == 2
        assert r1["event_counts"]["run-end"] == 1

    def test_run_durations(self):
        from pipeline_visualizer.trends import run_durations
        got = run_durations(_tl_fixture_events())
        by_id = {r["run_id"]: r for r in got}
        assert by_id["R1"]["duration_seconds"] == 120.0
        assert by_id["R2"]["duration_seconds"] is None  # no run-end → honest None

    def test_cycles_per_completion(self):
        from pipeline_visualizer.trends import cycles_per_completion
        got = cycles_per_completion(_tl_fixture_events())
        assert got["cycles"] == 2
        assert got["forward_cycles"] == 1
        assert got["meta_cycles"] == 1
        assert got["completions"] == 1
        assert got["cycles_per_completion"] == 2.0

    def test_cycles_per_completion_zero_completions_is_none(self):
        from pipeline_visualizer.trends import cycles_per_completion
        got = cycles_per_completion([_tl_event(1.0, "cycle-begin", item_id="x",
                                               data={"kind": "real"})])
        assert got["completions"] == 0
        assert got["cycles_per_completion"] is None  # never a fabricated zero

    def test_refusal_counts(self):
        from pipeline_visualizer.trends import refusal_counts
        got = refusal_counts(_tl_fixture_events(), _TL_FIXTURE_DENIES)
        assert got["gate_refusals"] == 1
        assert got["containment_refusals"] == 1
        assert got["by_gate"] == {"verify-ledger": 1}
        assert got["guard_denies"] == 1        # the plain deny entry only
        assert got["process_friction"] == 1
        assert got["auto_readmits"] == 1
        assert got["unacked_denies"] == 2      # deny + friction (both unacked)

    def test_halt_dwell_pairing(self):
        from pipeline_visualizer.trends import halt_dwell
        got = halt_dwell(_tl_fixture_events())
        assert len(got) == 2
        resolved = [h for h in got if h["item_id"] == "f2"][0]
        assert resolved["dwell_seconds"] == 20.0
        assert resolved["resolved_ts"] == 200.0
        assert resolved["terminal_reason"] == "needs-input"
        unresolved = [h for h in got if h["item_id"] == "f3"][0]
        assert unresolved["resolved_ts"] is None
        assert unresolved["dwell_seconds"] is None  # honest unresolved, not 0


class TestTrendsPayload:
    """trends_payload(repo_root) — the /api/trends aggregate over real files."""

    def _write_ledger(self, state_dir, events):
        ledger = state_dir / "lazy-telemetry.jsonl"
        ledger.write_text(
            "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        return ledger

    def test_payload_over_fixture_ledger(self, tmp_path):
        from pipeline_visualizer.trends import trends_payload
        repo = tmp_path / "repo"
        repo.mkdir()
        with _isolated_state_dir(tmp_path, marker=False):
            state_dir = tmp_path / "_state"
            self._write_ledger(state_dir, _tl_fixture_events())
            (state_dir / "lazy-deny-ledger.jsonl").write_text(
                "".join(json.dumps(d) + "\n" for d in _TL_FIXTURE_DENIES),
                encoding="utf-8")
            payload = trends_payload(repo)
        assert payload["telemetry_available"] is True
        assert [r["run_id"] for r in payload["runs"]] == ["R1", "R2"]
        r1 = [r for r in payload["runs"] if r["run_id"] == "R1"][0]
        assert r1["forward_cycles"] == 1
        assert r1["meta_cycles"] == 1
        assert r1["completions"] == 1
        assert r1["cycles_per_completion"] == 2.0
        assert r1["gate_refusals"] == 1
        assert r1["containment_refusals"] == 1
        assert r1["halts"] == 1
        assert r1["duration_seconds"] == 120.0
        assert payload["totals"]["cycles"] == 2
        assert payload["deny_ledger"]["unacked_denies"] == 2

    def test_payload_empty_ledger_is_honest(self, tmp_path):
        from pipeline_visualizer.trends import trends_payload
        repo = tmp_path / "repo"
        repo.mkdir()
        with _isolated_state_dir(tmp_path, marker=False):
            payload = trends_payload(repo)
        assert payload["telemetry_available"] is False
        assert "no telemetry" in payload["message"].lower()
        assert payload["runs"] == []

    def test_payload_merges_committed_cloud_segments(self, tmp_path):
        from pipeline_visualizer.trends import trends_payload
        repo = tmp_path / "repo"
        cloud_dir = repo / "docs" / "telemetry" / "cloud"
        cloud_dir.mkdir(parents=True)
        cloud_events = [
            _tl_event(500.0, "run-start", run_id="RC"),
            _tl_event(600.0, "run-end", run_id="RC"),
        ]
        (cloud_dir / "RC.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in cloud_events),
            encoding="utf-8")
        with _isolated_state_dir(tmp_path, marker=False):
            payload = trends_payload(repo)
        assert payload["telemetry_available"] is True
        rc = [r for r in payload["runs"] if r["run_id"] == "RC"][0]
        assert rc["duration_seconds"] == 100.0


class TestTrendsServerRoute:
    def test_api_trends_200_json(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path)
        with _isolated_state_dir(tmp_path, marker=False):
            state_dir = tmp_path / "_state"
            (state_dir / "lazy-telemetry.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in _tl_fixture_events()),
                encoding="utf-8")
            httpd, port = _start_server(repo_root)
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
                conn.request("GET", "/api/trends")
                resp = conn.getresponse()
                assert resp.status == 200
                assert "application/json" in (resp.getheader("Content-Type") or "")
                body = json.loads(resp.read())
                assert body["telemetry_available"] is True
                assert [r["run_id"] for r in body["runs"]] == ["R1", "R2"]
            finally:
                httpd.shutdown()

    def test_api_trends_empty_state_honest(self, tmp_path):
        repo_root = _seed_feature_repo(tmp_path)
        with _isolated_state_dir(tmp_path, marker=False):
            httpd, port = _start_server(repo_root)
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
                conn.request("GET", "/api/trends")
                body = json.loads(conn.getresponse().read())
                assert body["telemetry_available"] is False
            finally:
                httpd.shutdown()

    def test_trends_served_through_cache(self, tmp_path):
        # Sequential GETs within the TTL window → ONE underlying aggregation
        # (the trends producer is a module attribute, like probe_state).
        from pipeline_visualizer import server as server_mod
        repo_root = _seed_feature_repo(tmp_path)
        calls = {"n": 0}
        real_trends = server_mod.trends_payload

        def counting_trends(root):
            calls["n"] += 1
            return real_trends(root)

        server_mod.trends_payload = counting_trends
        try:
            with _isolated_state_dir(tmp_path, marker=False):
                httpd, port = _start_server(repo_root)
                try:
                    for _ in range(5):
                        conn = http.client.HTTPConnection("127.0.0.1", port,
                                                          timeout=30)
                        conn.request("GET", "/api/trends")
                        conn.getresponse().read()
                    assert calls["n"] == 1
                finally:
                    httpd.shutdown()
        finally:
            server_mod.trends_payload = real_trends


class TestTrendsRetroCli:
    """The D8 retro CLI: python -m pipeline_visualizer.trends --run-id <id>."""

    def _run_cli(self, tmp_path, args):
        state_dir = tmp_path / "_state"
        env = dict(_os.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)
        return _tl_subprocess.run(
            [sys.executable, "-m", "pipeline_visualizer.trends"] + args,
            capture_output=True, text=True, env=env,
            cwd=str(Path(__file__).parent),
        )

    def test_run_summary_shape_and_citations(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        state_dir = tmp_path / "_state"
        state_dir.mkdir()
        (state_dir / "lazy-telemetry.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in _tl_fixture_events()),
            encoding="utf-8")
        r = self._run_cli(tmp_path, ["--repo-root", str(repo), "--run-id", "R1"])
        assert r.returncode == 0, r.stderr
        summary = json.loads(r.stdout)
        assert summary["found"] is True
        assert summary["run_id"] == "R1"
        assert summary["forward_cycles"] == 1
        assert summary["meta_cycles"] == 1
        assert summary["completions"] == 1
        assert summary["gate_refusals"][0]["gate"] == "verify-ledger"
        assert summary["containment_refusals"][0]["op"] == "--apply-pseudo"
        # Per-figure ledger citations: the run's physical line window.
        lines = summary["ledger_lines"]
        assert lines and all("first" in w and "last" in w for w in lines.values())
        (halt,) = summary["halts"]
        assert halt["item_id"] == "f2" and halt["dwell_seconds"] == 20.0
        assert halt["citation"]["line"] == 9  # 9th physical ledger line

    def test_run_summary_honest_miss(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (tmp_path / "_state").mkdir()
        r = self._run_cli(tmp_path, ["--repo-root", str(repo),
                                     "--run-id", "NO-SUCH-RUN"])
        assert r.returncode == 0, r.stderr
        summary = json.loads(r.stdout)
        assert summary["found"] is False
        assert "no telemetry" in summary["message"].lower()

    def test_cli_without_run_id_prints_payload(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (tmp_path / "_state").mkdir()
        r = self._run_cli(tmp_path, ["--repo-root", str(repo)])
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["telemetry_available"] is False


# ---------------------------------------------------------------------------
# cross-repo-fleet-view Phase 1 — pipeline_visualizer.fleet (shallow read layer)
#
# Pure-read fleet library: D1 discovery (registry glob + lazy-repos.json
# pins/excludes + live-marker union), the raw NEVER-DELETING marker read + D3
# badge grading, D5 shallow rows (queue depths + halt-sentinel presence), and
# D7 slug assignment. Zero state-script subprocesses anywhere in this layer.
# ---------------------------------------------------------------------------

import datetime as _fl_datetime


def _fl_iso(epoch: float) -> str:
    """ISO-8601 UTC 'Z' string for an epoch float (the marker's format)."""
    return (_fl_datetime.datetime(1970, 1, 1)
            + _fl_datetime.timedelta(seconds=epoch)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fl_seed_repo(base: Path, name: str, features=(), bugs=(),
                  lazy_queue_doc: bool = False) -> Path:
    """Seed a minimal lazy-enabled repo: queue.json + item dirs per pipeline."""
    repo = base / name
    for pipeline, ids in (("features", features), ("bugs", bugs)):
        pdir = repo / "docs" / pipeline
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "queue.json").write_text(
            json.dumps({"queue": [
                {"id": i, "name": i, "spec_dir": i, "tier": 1} for i in ids
            ]}, indent=2) + "\n", encoding="utf-8")
        for i in ids:
            d = pdir / i
            d.mkdir(exist_ok=True)
            (d / "SPEC.md").write_text("# x\n\n**Status:** Draft\n",
                                       encoding="utf-8")
    if lazy_queue_doc:
        (repo / "LAZY_QUEUE.md").write_text("# Lazy Queue\n", encoding="utf-8")
    return repo


def _fl_write_marker(state_base: Path, repo_root: Path, started_epoch: float,
                     pipeline="feature", work_branch="lazy/run-branch") -> Path:
    """Write a keyed run marker (production layout: <state_base>/<repo_key>/)."""
    import lazy_core
    d = state_base / lazy_core.repo_key(str(repo_root))
    d.mkdir(parents=True, exist_ok=True)
    marker = {
        "pipeline": pipeline, "cloud": False, "repo_root": str(repo_root),
        "session_id": None, "started_at": _fl_iso(started_epoch),
        "work_branch": work_branch, "max_cycles": 20,
    }
    p = d / "lazy-run-marker.json"
    p.write_text(json.dumps(marker), encoding="utf-8")
    return p


_FL_NOW = 1_800_000_000.0  # fixed injected 'now' for age grading


class TestFleetDiscovery:
    """discover_repos: registry glob ∪ pins ∪ live-marker roots, realpath-
    deduped, excludes applied last."""

    def test_registry_glob_finds_lazy_repos_only(self, tmp_path):
        from pipeline_visualizer.fleet import discover_repos
        base = tmp_path / "repos"
        base.mkdir()
        a = _fl_seed_repo(base, "repo-a", features=("f1",))
        b = _fl_seed_repo(base, "repo-b", bugs=("b1",))
        (base / "not-a-repo").mkdir()  # no docs/ → not discovered
        got = discover_repos(repos_base=base,
                             lazy_repos_path=tmp_path / "no-config.json",
                             state_base=tmp_path / "no-state")
        assert set(got) == {_os.path.realpath(str(a)), _os.path.realpath(str(b))}

    def test_pins_added_and_excludes_removed(self, tmp_path):
        from pipeline_visualizer.fleet import discover_repos
        base = tmp_path / "repos"
        base.mkdir()
        a = _fl_seed_repo(base, "repo-a", features=("f1",))
        b = _fl_seed_repo(base, "repo-b", features=("f1",))
        # An out-of-tree pinned repo (not under repos_base).
        c = _fl_seed_repo(tmp_path / "elsewhere", "repo-c", features=("f1",))
        cfg = tmp_path / "lazy-repos.json"
        cfg.write_text(json.dumps({
            "pins": [str(c)],
            "excludes": [str(b)],
        }), encoding="utf-8")
        got = discover_repos(repos_base=base, lazy_repos_path=cfg,
                             state_base=tmp_path / "no-state")
        assert set(got) == {_os.path.realpath(str(a)), _os.path.realpath(str(c))}

    def test_live_marker_union_adds_out_of_tree_repo(self, tmp_path):
        from pipeline_visualizer.fleet import discover_repos
        base = tmp_path / "repos"
        base.mkdir()
        a = _fl_seed_repo(base, "repo-a", features=("f1",))
        # A live run in a nonstandard root, discoverable only via its marker.
        d = _fl_seed_repo(tmp_path / "outside", "repo-d", features=("f1",))
        state_base = tmp_path / "state"
        _fl_write_marker(state_base, d, _FL_NOW - 60)
        got = discover_repos(repos_base=base,
                             lazy_repos_path=tmp_path / "no-config.json",
                             state_base=state_base)
        assert set(got) == {_os.path.realpath(str(a)), _os.path.realpath(str(d))}

    def test_union_dedups_by_realpath(self, tmp_path):
        from pipeline_visualizer.fleet import discover_repos
        base = tmp_path / "repos"
        base.mkdir()
        a = _fl_seed_repo(base, "repo-a", features=("f1",))
        # Pin the SAME repo via a non-canonical path form (trailing slash) AND
        # give it a live marker — still one entry.
        cfg = tmp_path / "lazy-repos.json"
        cfg.write_text(json.dumps({"pins": [str(a) + _os.sep]}), encoding="utf-8")
        state_base = tmp_path / "state"
        _fl_write_marker(state_base, a, _FL_NOW - 60)
        got = discover_repos(repos_base=base, lazy_repos_path=cfg,
                             state_base=state_base)
        assert got == [_os.path.realpath(str(a))]

    def test_missing_sources_and_malformed_config_fail_open(self, tmp_path):
        from pipeline_visualizer.fleet import discover_repos
        base = tmp_path / "repos"
        base.mkdir()
        a = _fl_seed_repo(base, "repo-a", features=("f1",))
        bad_cfg = tmp_path / "lazy-repos.json"
        bad_cfg.write_text("{ not json", encoding="utf-8")
        got = discover_repos(repos_base=base, lazy_repos_path=bad_cfg,
                             state_base=tmp_path / "absent-state")
        assert got == [_os.path.realpath(str(a))]


class TestFleetMarkerRawRead:
    """read_marker_raw: raw keyed-path read; NEVER deletes (the ≥24h marker
    survival is the load-bearing D3 invariant)."""

    def test_absent_returns_none(self, tmp_path):
        from pipeline_visualizer.fleet import read_marker_raw
        repo = tmp_path / "repo"
        repo.mkdir()
        assert read_marker_raw(repo, state_base=tmp_path / "state") is None

    def test_present_returns_raw_fields(self, tmp_path):
        from pipeline_visualizer.fleet import read_marker_raw
        repo = tmp_path / "repo"
        repo.mkdir()
        state_base = tmp_path / "state"
        _fl_write_marker(state_base, repo, _FL_NOW - 120, pipeline="bug",
                         work_branch="lazy/bugs-x")
        raw = read_marker_raw(repo, state_base=state_base)
        assert raw["pipeline"] == "bug"
        assert raw["work_branch"] == "lazy/bugs-x"
        assert raw["repo_root"] == str(repo)

    def test_stale_marker_survives_repeated_reads(self, tmp_path):
        # THE invariant: a ≥24h-old marker is still on disk (bytes unchanged)
        # after every fleet read path has run over it, repeatedly.
        from pipeline_visualizer.fleet import (
            fleet_row, marker_fresh_present, marker_view, read_marker_raw)
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "docs" / "features").mkdir(parents=True)
        state_base = tmp_path / "state"
        mp = _fl_write_marker(state_base, repo, _FL_NOW - 25 * 3600)
        before = mp.read_bytes()
        for _ in range(3):
            raw = read_marker_raw(repo, state_base=state_base)
            view = marker_view(raw, now=_FL_NOW)
            assert view["badge"] == "stale-marker"
            assert marker_fresh_present(repo, state_base=state_base,
                                        now=_FL_NOW) is False
            fleet_row(repo, state_base=state_base, now=_FL_NOW)
        assert mp.exists()
        assert mp.read_bytes() == before

    def test_corrupt_marker_flagged_not_deleted(self, tmp_path):
        # lazy_core.read_run_marker DELETES a corrupt marker; the fleet read
        # must flag it and leave it on disk.
        from pipeline_visualizer.fleet import (marker_fresh_present,
                                               marker_view, read_marker_raw)
        import lazy_core
        repo = tmp_path / "repo"
        repo.mkdir()
        state_base = tmp_path / "state"
        d = state_base / lazy_core.repo_key(str(repo))
        d.mkdir(parents=True)
        mp = d / "lazy-run-marker.json"
        mp.write_text("{ not json", encoding="utf-8")
        raw = read_marker_raw(repo, state_base=state_base)
        assert raw is not None and raw.get("unreadable") is True
        view = marker_view(raw, now=_FL_NOW)
        assert view["present"] is True
        assert view["badge"] == "stale-marker"
        assert view["age_seconds"] is None
        assert marker_fresh_present(repo, state_base=state_base,
                                    now=_FL_NOW) is False
        assert mp.exists()  # never deleted

    def test_lazy_state_dir_flat_layout_honored(self, tmp_path, monkeypatch):
        # With no explicit state_base and LAZY_STATE_DIR set, the marker is
        # read flat from that dir (claude_state_dir override semantics).
        from pipeline_visualizer.fleet import read_marker_raw
        repo = tmp_path / "repo"
        repo.mkdir()
        flat = tmp_path / "flat-state"
        flat.mkdir()
        (flat / "lazy-run-marker.json").write_text(json.dumps({
            "pipeline": "feature", "repo_root": str(repo),
            "started_at": _fl_iso(_FL_NOW - 60),
        }), encoding="utf-8")
        monkeypatch.setenv("LAZY_STATE_DIR", str(flat))
        raw = read_marker_raw(repo)
        assert raw is not None and raw["pipeline"] == "feature"


class TestFleetMarkerView:
    """D3 badge grading over an injected now. Warn threshold 2h; stale 24h
    (aligned with lazy_core._MARKER_STALE_SECONDS)."""

    def _raw(self, age_seconds):
        return {"pipeline": "feature", "started_at": _fl_iso(_FL_NOW - age_seconds),
                "work_branch": "lazy/x", "repo_root": "/r"}

    def test_idle_when_no_marker(self):
        from pipeline_visualizer.fleet import marker_view
        view = marker_view(None, now=_FL_NOW)
        assert view == {"present": False, "age_seconds": None, "badge": "idle",
                        "pipeline": None, "work_branch": None}

    def test_run_active_within_warn_threshold(self):
        from pipeline_visualizer.fleet import marker_view
        view = marker_view(self._raw(60), now=_FL_NOW)
        assert view["badge"] == "run-active"
        assert view["present"] is True
        assert abs(view["age_seconds"] - 60) < 0.001
        assert view["pipeline"] == "feature"
        assert view["work_branch"] == "lazy/x"

    def test_run_silent_past_warn_threshold(self):
        from pipeline_visualizer.fleet import marker_view
        view = marker_view(self._raw(3 * 3600), now=_FL_NOW)
        assert view["badge"] == "run-silent"
        assert abs(view["age_seconds"] - 3 * 3600) < 0.001

    def test_stale_marker_past_24h(self):
        from pipeline_visualizer.fleet import marker_view
        view = marker_view(self._raw(25 * 3600), now=_FL_NOW)
        assert view["badge"] == "stale-marker"
        assert abs(view["age_seconds"] - 25 * 3600) < 0.001

    def test_thresholds_align_with_lazy_core(self):
        from pipeline_visualizer import fleet
        import lazy_core
        assert fleet.STALE_SECONDS == lazy_core._MARKER_STALE_SECONDS
        assert fleet.WARN_SECONDS == 2 * 3600

    def test_unparseable_started_at_is_stale_with_null_age(self):
        from pipeline_visualizer.fleet import marker_view
        view = marker_view({"pipeline": "feature", "started_at": "yesterday-ish"},
                           now=_FL_NOW)
        assert view["present"] is True
        assert view["badge"] == "stale-marker"
        assert view["age_seconds"] is None


class TestFleetSlugs:
    def test_slugify_kebab_cases(self):
        from pipeline_visualizer.fleet import slugify
        assert slugify("My_Repo!") == "my-repo"
        assert slugify("claude-config") == "claude-config"
        assert slugify("...") == "repo"  # never empty

    def test_assign_unique_basenames_keep_plain_slugs(self, tmp_path):
        from pipeline_visualizer.fleet import assign_slugs
        a = tmp_path / "alpha"
        b = tmp_path / "beta"
        a.mkdir()
        b.mkdir()
        slugs = assign_slugs([str(a), str(b)])
        assert slugs[str(a)] == "alpha"
        assert slugs[str(b)] == "beta"

    def test_basename_collision_gets_repo_key_suffix(self, tmp_path):
        from pipeline_visualizer.fleet import assign_slugs
        import lazy_core
        a = tmp_path / "one" / "same-name"
        b = tmp_path / "two" / "same-name"
        a.mkdir(parents=True)
        b.mkdir(parents=True)
        slugs = assign_slugs([str(a), str(b)])
        assert slugs[str(a)] != slugs[str(b)]
        for root, slug in slugs.items():
            assert slug.startswith("same-name-")
            assert slug == "same-name-" + lazy_core.repo_key(root)[:8]


class TestFleetRow:
    """fleet_row: shallow shape — depths, halt presence, marker view, doc flag,
    error-row degradation. No state-script subprocess anywhere."""

    def test_depths_match_queue_lengths(self, tmp_path):
        from pipeline_visualizer.fleet import fleet_row
        repo = _fl_seed_repo(tmp_path, "repo-a",
                             features=("f1", "f2", "f3"), bugs=("b1", "b2"))
        row = fleet_row(repo, state_base=tmp_path / "state", now=_FL_NOW)
        assert row["features"]["depth"] == 3
        assert row["bugs"]["depth"] == 2
        assert row["error"] is None
        assert row["name"] == "repo-a"
        assert row["slug"] == "repo-a"
        assert row["repo_root"] == str(repo)

    def test_halt_sentinel_presence_listed_with_kind(self, tmp_path):
        from pipeline_visualizer.fleet import fleet_row
        repo = _fl_seed_repo(tmp_path, "repo-a",
                             features=("f1", "f2"), bugs=("b1",))
        (repo / "docs" / "features" / "f2" / "NEEDS_INPUT.md").write_text(
            "---\nkind: needs-input\n---\n", encoding="utf-8")
        (repo / "docs" / "bugs" / "b1" / "BLOCKED.md").write_text(
            "---\nkind: blocked\n---\n", encoding="utf-8")
        row = fleet_row(repo, state_base=tmp_path / "state", now=_FL_NOW)
        assert row["features"]["halts"] == [{"id": "f2", "kind": "needs-input"}]
        assert row["bugs"]["halts"] == [{"id": "b1", "kind": "blocked"}]

    def test_marker_view_embedded(self, tmp_path):
        from pipeline_visualizer.fleet import fleet_row
        repo = _fl_seed_repo(tmp_path, "repo-a", features=("f1",))
        state_base = tmp_path / "state"
        _fl_write_marker(state_base, repo, _FL_NOW - 300)
        row = fleet_row(repo, state_base=state_base, now=_FL_NOW)
        assert row["marker"]["present"] is True
        assert row["marker"]["badge"] == "run-active"
        assert row["marker"]["pipeline"] == "feature"
        assert row["marker"]["work_branch"] == "lazy/run-branch"

    def test_lazy_queue_doc_flag(self, tmp_path):
        from pipeline_visualizer.fleet import fleet_row
        with_doc = _fl_seed_repo(tmp_path, "repo-a", features=("f1",),
                                 lazy_queue_doc=True)
        without = _fl_seed_repo(tmp_path, "repo-b", features=("f1",))
        sb = tmp_path / "state"
        assert fleet_row(with_doc, state_base=sb, now=_FL_NOW)["lazy_queue_doc"] is True
        assert fleet_row(without, state_base=sb, now=_FL_NOW)["lazy_queue_doc"] is False

    def test_internal_error_degrades_to_error_row(self, tmp_path, monkeypatch):
        # A broken repo renders an explicit error row, never a raise/omission.
        from pipeline_visualizer import fleet
        repo = _fl_seed_repo(tmp_path, "repo-a", features=("f1",))

        def boom(path):
            raise OSError("permission denied (fixture)")

        monkeypatch.setattr(fleet, "read_queue", boom)
        row = fleet.fleet_row(repo, state_base=tmp_path / "state", now=_FL_NOW)
        assert row["error"] is not None
        assert "permission denied" in row["error"]
        assert row["slug"] == "repo-a"
        assert row["repo_root"] == str(repo)
        assert row["features"]["depth"] == 0  # shape stays renderable


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
