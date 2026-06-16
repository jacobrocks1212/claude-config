"""server — a ThreadingHTTPServer serving the visualizer API.

Subclasses SimpleHTTPRequestHandler so static frontend assets (Phase 2) can be
deferred to super(); the API routes (/api/state, /api/queue) are handled
explicitly here. /api/state is served through a read-through TTL cache so the
heavy probe runs at most once per TTL window (SPEC "Cache debounces probe").

`probe_state` is referenced as a module attribute so tests can monkeypatch it
with a call-counter (the cache-debounce server test reuses the WU-2 counter).
"""

from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .cache import TtlCache
from .probe import probe_state, read_queue  # noqa: F401 (probe_state monkeypatched in tests)
from .queue_writer import PermutationError, QueueWriteError, reorder_queue


def _run_marker_present() -> bool:
    """True iff a fresh batch run-marker is present (a /lazy-batch run is live).

    Detection delegates to lazy_core.read_run_marker() — the single source of
    truth for the global run marker (it applies all staleness guards). Reorder
    writes are refused entirely while it is present (Decisions 6 + 11). If
    lazy_core is unimportable (e.g. a stripped deployment), fail OPEN to closed:
    treat as no marker so the tool stays usable, since the run marker is an
    optimization gate, not a correctness gate (the atomic write is still safe).
    """
    try:
        import lazy_core
    except ImportError:
        return False
    try:
        return lazy_core.read_run_marker() is not None
    except Exception:
        return False


# The frontend assets live alongside this module, under static/.
STATIC_ROOT = Path(__file__).resolve().parent / "static"


def make_server(repo_root, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Build (but do not start) a ThreadingHTTPServer bound to (host, port).

    Pass port=0 to bind an ephemeral port (read it back from server_address).

    Routing: /api/state and /api/queue are handled explicitly (and matched BEFORE
    any static fallthrough so API never collides with a file path). Everything
    else is served from the bundled static/ directory by SimpleHTTPRequestHandler:
    `/` serves static/index.html; `/static/<x>` is rewritten to `/<x>` and served
    from static/. The handler is rooted at static/ (directory= kwarg), so the
    SimpleHTTPRequestHandler path normalization confines reads to that tree —
    `/static/../server.py` cannot escape to the backend source.
    """
    repo_root = Path(repo_root)
    cache = TtlCache()
    static_root = str(STATIC_ROOT)

    class Handler(SimpleHTTPRequestHandler):
        # repo_root + cache are closed over so each request reads live state.
        def __init__(self, *args, **kwargs):
            # Root the static file server at the bundled static/ directory.
            super().__init__(*args, directory=static_root, **kwargs)
        def _send_json(self, status: int, payload) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _api_state(self) -> None:
            # Served through the cache: concurrent GETs within the TTL window
            # trigger exactly one underlying probe. The module-level name is
            # re-read so tests that monkeypatch server.probe_state are honored.
            import pipeline_visualizer.server as _self_mod
            state = cache.get(lambda: _self_mod.probe_state(repo_root))
            # queue_locked is computed at RESPONSE time (NOT cached with the heavy
            # probe) so a run-marker appearing/clearing reflects on the next poll,
            # not up to one TTL window late. Decisions 6 + 11.
            payload = dict(state)
            payload["queue_locked"] = _self_mod._run_marker_present()
            self._send_json(200, payload)

        def _api_queue(self) -> None:
            features = read_queue(repo_root / "docs" / "features" / "queue.json")
            bugs = read_queue(repo_root / "docs" / "bugs" / "queue.json")
            self._send_json(200, {"features": features, "bugs": bugs})

        def _queue_path_for(self, pipeline: str):
            """Map a posted pipeline name to its queue.json path. Returns None
            for an unknown pipeline."""
            if pipeline in ("features", "feature"):
                return repo_root / "docs" / "features" / "queue.json"
            if pipeline in ("bugs", "bug"):
                return repo_root / "docs" / "bugs" / "queue.json"
            return None

        def _api_queue_post(self) -> None:
            # The single guarded write path. Body: {pipeline, order:[ids...]}.
            import pipeline_visualizer.server as _self_mod
            # Refuse entirely while a batch run-marker is present (one writer rule).
            if _self_mod._run_marker_present():
                self._send_json(409, {
                    "error": "queue locked — orchestrator run in progress",
                    "queue_locked": True,
                })
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, {"error": "request body is not valid JSON"})
                return
            pipeline = body.get("pipeline")
            order = body.get("order")
            qpath = self._queue_path_for(pipeline)
            if qpath is None:
                self._send_json(400, {"error": f"unknown pipeline: {pipeline!r}"})
                return
            if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
                self._send_json(400, {"error": "order must be a list of string IDs"})
                return
            if not qpath.exists():
                self._send_json(404, {"error": f"no queue.json for {pipeline}"})
                return
            try:
                reorder_queue(qpath, order)
            except PermutationError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except QueueWriteError as exc:
                self._send_json(503, {"error": str(exc)})
                return
            self._send_json(200, {"ok": True, "pipeline": pipeline, "order": order})

        def do_POST(self):  # noqa: N802 (BaseHTTPRequestHandler API)
            route = self.path.split("?", 1)[0]
            if route == "/api/queue":
                self._api_queue_post()
                return
            self.send_response(404)
            self.end_headers()

        def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
            # API routes are matched BEFORE the static fallthrough so they never
            # collide with a file path (regression: /api/state must stay JSON).
            # Compare on the path component only (ignore any query string).
            route = self.path.split("?", 1)[0]
            if route == "/api/state":
                self._api_state()
                return
            if route == "/api/queue":
                self._api_queue()
                return
            # Static frontend assets, rooted at static/. `/static/<x>` is the
            # canonical asset prefix in the HTML; strip it so the file resolves
            # under static/. `/` falls through to SimpleHTTPRequestHandler's
            # index.html behavior.
            if route.startswith("/static/"):
                self.path = self.path[len("/static"):]  # "/static/app.js" -> "/app.js"
            super().do_GET()

        def log_message(self, *args):  # silence default request logging in tests
            pass

    return ThreadingHTTPServer((host, port), Handler)
