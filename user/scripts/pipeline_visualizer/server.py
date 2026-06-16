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
            self._send_json(200, state)

        def _api_queue(self) -> None:
            features = read_queue(repo_root / "docs" / "features" / "queue.json")
            bugs = read_queue(repo_root / "docs" / "bugs" / "queue.json")
            self._send_json(200, {"features": features, "bugs": bugs})

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
