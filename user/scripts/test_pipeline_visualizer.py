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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
