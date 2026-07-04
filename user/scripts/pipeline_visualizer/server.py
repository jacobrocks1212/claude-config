"""server — a ThreadingHTTPServer serving the visualizer API.

Subclasses SimpleHTTPRequestHandler so static frontend assets (Phase 2) can be
deferred to super(); the API routes (/api/state, /api/queue) are handled
explicitly here. /api/state is served through a read-through TTL cache so the
heavy probe runs at most once per TTL window (SPEC "Cache debounces probe").

`probe_state` is referenced as a module attribute so tests can monkeypatch it
with a call-counter (the cache-debounce server test reuses the WU-2 counter).

cross-repo-fleet-view: `make_server` gains a fleet mode (D2-A) — one instance
serving the fleet home at `/`, `/api/fleet` behind its own TtlCache (D5), and
the SAME per-repo handlers nested under `/repo/<slug>/…` with `repo_root`
resolved from a server-owned slug map (D7) instead of the closure. Single-repo
`--repo-root` mode constructs exactly the pre-fleet handler — its behavior is
pinned byte-identical by the pre-existing test suite. In fleet mode the
run-marker check for `queue_locked` / reorder refusal uses the RAW keyed-path
read (`fleet.marker_fresh_present`) — never `lazy_core.read_run_marker`
(delete-on-read) and never a per-request `set_active_repo_root` flip, which
would be a data race across repos under ThreadingHTTPServer.
"""

from __future__ import annotations

import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import fleet as fleet_mod
from .cache import TtlCache
from .fleet import fleet_payload  # noqa: F401 (monkeypatched in tests, like probe_state)
from .probe import probe_state, read_queue  # noqa: F401 (probe_state monkeypatched in tests)
from .queue_writer import PermutationError, QueueWriteError, reorder_queue
from .trends import trends_payload  # noqa: F401 (monkeypatched in tests, like probe_state)


def _run_marker_present(repo_root=None) -> bool:
    """True iff a fresh batch run-marker is present for the visualized repo (a
    /lazy-batch run is live in it).

    Detection delegates to lazy_core.read_run_marker() — the single source of
    truth for the run marker (it applies all staleness guards). Reorder
    writes are refused entirely while it is present (Decisions 6 + 11). If
    lazy_core is unimportable (e.g. a stripped deployment), fail OPEN to closed:
    treat as no marker so the tool stays usable, since the run marker is an
    optimization gate, not a correctness gate (the atomic write is still safe).

    multi-repo-concurrent-runs (Phase 3 WU-3.3): run-scoped state is now keyed
    per repo under ``~/.claude/state/<repo_key>/``.  read_run_marker() resolves
    its dir via lazy_core.claude_state_dir() → active_repo_root(), so the
    visualizer MUST bind the active repo to the repo it is rendering — otherwise
    it would read whatever repo the cwd-git-toplevel fallback resolves to (often
    the wrong subdir) and miss the live marker.  We bind ``repo_root`` here on
    every check so the per-poll marker read targets the visualized repo's keyed
    subdir.  When LAZY_STATE_DIR is set (the test/pipe-test path) the override
    wins inside claude_state_dir() regardless of the binding, so existing
    fixtures are byte-for-byte unaffected.

    SINGLE-REPO MODE ONLY (cross-repo-fleet-view): the set_active_repo_root
    binding is safe with one closed-over repo, but not per-request across
    repos — fleet mode uses fleet.marker_fresh_present (raw read) instead.
    """
    try:
        import lazy_core
    except ImportError:
        return False
    try:
        if repo_root is not None:
            # Bind the active repo so the keyed state dir matches the rendered
            # repo (no-op for path resolution when LAZY_STATE_DIR is set).
            lazy_core.set_active_repo_root(str(repo_root))
        return lazy_core.read_run_marker() is not None
    except Exception:
        return False


# The frontend assets live alongside this module, under static/.
STATIC_ROOT = Path(__file__).resolve().parent / "static"


# ---------------------------------------------------------------------------
# Shared request helpers (used by BOTH the single-repo and fleet handlers so
# the two modes cannot drift; the single-repo response contract is pinned by
# the pre-existing suite).
# ---------------------------------------------------------------------------

def _send_json(handler, status: int, payload) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _state_payload(repo_root: Path, cache: TtlCache, locked_fn) -> dict:
    """The /api/state payload: heavy probe through the given cache, plus
    queue_locked computed at RESPONSE time (NOT cached with the probe) so a
    run-marker appearing/clearing reflects on the next poll (Decisions 6+11).
    The module-level probe_state is re-read so test monkeypatches are honored."""
    import pipeline_visualizer.server as _self_mod
    state = cache.get(lambda: _self_mod.probe_state(repo_root))
    payload = dict(state)
    payload["queue_locked"] = locked_fn()
    return payload


def _queue_payload(repo_root: Path) -> dict:
    features = read_queue(repo_root / "docs" / "features" / "queue.json")
    bugs = read_queue(repo_root / "docs" / "bugs" / "queue.json")
    return {"features": features, "bugs": bugs}


def _trends_payload_cached(repo_root: Path, cache: TtlCache) -> dict:
    """harness-telemetry-ledger: pure-read ledger aggregation through its own
    TtlCache; trends_payload re-read from the module for monkeypatching."""
    import pipeline_visualizer.server as _self_mod
    return cache.get(lambda: _self_mod.trends_payload(repo_root))


def _queue_path_for(repo_root: Path, pipeline: str):
    """Map a posted pipeline name to its queue.json path. Returns None for an
    unknown pipeline."""
    if pipeline in ("features", "feature"):
        return repo_root / "docs" / "features" / "queue.json"
    if pipeline in ("bugs", "bug"):
        return repo_root / "docs" / "bugs" / "queue.json"
    return None


def _queue_post(handler, repo_root: Path, locked: bool) -> None:
    """The single guarded write path. Body: {pipeline, order:[ids...]}.
    Refused entirely (409) while `locked` — the caller computes it from the
    mode-appropriate run-marker read (one writer rule, Decisions 6 + 11)."""
    if locked:
        _send_json(handler, 409, {
            "error": "queue locked — orchestrator run in progress",
            "queue_locked": True,
        })
        return
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b""
    try:
        body = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        _send_json(handler, 400, {"error": "request body is not valid JSON"})
        return
    pipeline = body.get("pipeline")
    order = body.get("order")
    qpath = _queue_path_for(repo_root, pipeline)
    if qpath is None:
        _send_json(handler, 400, {"error": f"unknown pipeline: {pipeline!r}"})
        return
    if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
        _send_json(handler, 400, {"error": "order must be a list of string IDs"})
        return
    if not qpath.exists():
        _send_json(handler, 404, {"error": f"no queue.json for {pipeline}"})
        return
    try:
        reorder_queue(qpath, order)
    except PermutationError as exc:
        _send_json(handler, 400, {"error": str(exc)})
        return
    except QueueWriteError as exc:
        _send_json(handler, 503, {"error": str(exc)})
        return
    _send_json(handler, 200, {"ok": True, "pipeline": pipeline, "order": order})


def make_server(repo_root=None, host: str = "127.0.0.1", port: int = 8765, *,
                fleet: bool = False, repos_base=None, lazy_repos_path=None,
                state_base=None) -> ThreadingHTTPServer:
    """Build (but do not start) a ThreadingHTTPServer bound to (host, port).

    Pass port=0 to bind an ephemeral port (read it back from server_address).

    Single-repo mode (default, `repo_root` required): exactly the shipped
    behavior — /api/state, /api/queue (GET+guarded POST), /api/trends, static
    assets. Routing: API routes are matched BEFORE any static fallthrough so
    API never collides with a file path. Everything else is served from the
    bundled static/ directory by SimpleHTTPRequestHandler: `/` serves
    static/index.html; `/static/<x>` is rewritten to `/<x>` and served from
    static/. The handler is rooted at static/ (directory= kwarg), so the
    SimpleHTTPRequestHandler path normalization confines reads to that tree —
    `/static/../server.py` cannot escape to the backend source.

    Fleet mode (`fleet=True`, cross-repo-fleet-view D2-A): `/` serves the
    fleet home (static/fleet.html); `GET /api/fleet` serves the shallow
    aggregate through its OWN TtlCache (fleet.FLEET_TTL_SECONDS ≥ the per-repo
    TTL); the per-repo views nest under `/repo/<slug>/…` with per-repo probe/
    trends caches allocated lazily on first drill-in. The fleet layer is pure
    read (D6): the ONLY POST route is the per-repo `/repo/<slug>/api/queue`
    reorder, refused via the raw (never-deleting) marker read. The
    `repos_base` / `lazy_repos_path` / `state_base` kwargs parameterize
    discovery + marker reads for hermetic tests; production passes None
    (fleet.py defaults: ~/source/repos, ~/.claude/lazy-repos.json,
    ~/.claude/state).
    """
    static_root = str(STATIC_ROOT)

    if fleet:
        return _make_fleet_server(host, port, static_root,
                                  repos_base=repos_base,
                                  lazy_repos_path=lazy_repos_path,
                                  state_base=state_base)

    repo_root = Path(repo_root)
    cache = TtlCache()
    # harness-telemetry-ledger Phase 3: /api/trends gets its OWN TtlCache so a
    # polling Trends tab re-reads the ledgers at most once per TTL window,
    # independent of the /api/state probe cache.
    trends_cache = TtlCache()

    class Handler(SimpleHTTPRequestHandler):
        # repo_root + cache are closed over so each request reads live state.
        def __init__(self, *args, **kwargs):
            # Root the static file server at the bundled static/ directory.
            super().__init__(*args, directory=static_root, **kwargs)

        def _api_state(self) -> None:
            # Served through the cache: concurrent GETs within the TTL window
            # trigger exactly one underlying probe. queue_locked is computed at
            # RESPONSE time via lazy_core.read_run_marker (single-repo mode —
            # the one closed-over repo makes the active-repo binding safe).
            import pipeline_visualizer.server as _self_mod
            payload = _state_payload(
                repo_root, cache,
                lambda: _self_mod._run_marker_present(repo_root))
            _send_json(self, 200, payload)

        def _api_queue(self) -> None:
            _send_json(self, 200, _queue_payload(repo_root))

        def _api_trends(self) -> None:
            _send_json(self, 200, _trends_payload_cached(repo_root, trends_cache))

        def _api_queue_post(self) -> None:
            # Refuse entirely while a batch run-marker is present (one writer
            # rule) — the marker is read BEFORE the body, as shipped.
            import pipeline_visualizer.server as _self_mod
            _queue_post(self, repo_root,
                        _self_mod._run_marker_present(repo_root))

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
            if route == "/api/trends":
                self._api_trends()
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


def _make_fleet_server(host: str, port: int, static_root: str, *,
                       repos_base=None, lazy_repos_path=None,
                       state_base=None) -> ThreadingHTTPServer:
    """The fleet-mode server (see make_server docstring)."""
    fleet_cache = TtlCache(ttl=fleet_mod.FLEET_TTL_SECONDS)
    slug_map: dict = {}          # slug -> repo_root str (refreshed w/ payload)
    repo_caches: dict = {}       # repo_root str -> {"state": TtlCache, "trends": TtlCache}
    caches_lock = threading.Lock()

    def _refresh_fleet() -> dict:
        # fleet_payload is re-read from the module so tests can monkeypatch
        # server.fleet_payload with a call counter (probe_state pattern).
        import pipeline_visualizer.server as _self_mod
        payload = _self_mod.fleet_payload(repos_base=repos_base,
                                          lazy_repos_path=lazy_repos_path,
                                          state_base=state_base)
        fresh = {row["slug"]: row["repo_root"]
                 for row in payload.get("repos", []) if row.get("slug")}
        slug_map.clear()
        slug_map.update(fresh)
        return payload

    def _get_fleet() -> dict:
        return fleet_cache.get(_refresh_fleet)

    def _resolve_slug(slug: str):
        # A slug not yet known may belong to a just-appeared repo — refresh
        # (TTL-bounded) before giving up.
        if slug not in slug_map:
            _get_fleet()
        return slug_map.get(slug)

    def _caches_for(root: str) -> dict:
        # One TtlCache pair per repo, allocated lazily on first drill-in.
        with caches_lock:
            pair = repo_caches.get(root)
            if pair is None:
                pair = {"state": TtlCache(), "trends": TtlCache()}
                repo_caches[root] = pair
            return pair

    def _locked_fn(root: str):
        # Fleet-mode run-marker check: RAW keyed-path read (presence +
        # freshness only) — no set_active_repo_root flip, never deletes.
        return lambda: fleet_mod.marker_fresh_present(root,
                                                      state_base=state_base)

    class FleetHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=static_root, **kwargs)

        def _repo_route(self, route: str):
            """Parse /repo/<slug>/<sub>; returns (slug, sub) or None."""
            rest = route[len("/repo/"):]
            slug, _, sub = rest.partition("/")
            return slug, sub

        def do_GET(self):  # noqa: N802
            route = self.path.split("?", 1)[0]
            if route == "/api/fleet":
                _send_json(self, 200, _get_fleet())
                return
            if route.startswith("/repo/"):
                rest = route[len("/repo/"):]
                if "/" not in rest:
                    # /repo/<slug> → /repo/<slug>/ so the page's RELATIVE api/
                    # asset URLs resolve under the slug prefix.
                    self.send_response(301)
                    self.send_header("Location", route + "/")
                    self.end_headers()
                    return
                slug, sub = self._repo_route(route)
                root = _resolve_slug(slug)
                if root is None:
                    _send_json(self, 404,
                               {"error": f"unknown repo slug: {slug!r}"})
                    return
                if sub == "api/state":
                    caches = _caches_for(root)
                    payload = _state_payload(Path(root), caches["state"],
                                             _locked_fn(root))
                    _send_json(self, 200, payload)
                    return
                if sub == "api/queue":
                    _send_json(self, 200, _queue_payload(Path(root)))
                    return
                if sub == "api/trends":
                    caches = _caches_for(root)
                    _send_json(self, 200, _trends_payload_cached(
                        Path(root), caches["trends"]))
                    return
                # Nested per-repo frontend: same bundled assets.
                if sub == "":
                    self.path = "/index.html"
                elif sub.startswith("static/"):
                    self.path = "/" + sub[len("static/"):]
                else:
                    self.path = "/" + sub
                super().do_GET()
                return
            if route == "/":
                # The fleet home page (D4-B).
                self.path = "/fleet.html"
                super().do_GET()
                return
            if route.startswith("/static/"):
                self.path = self.path[len("/static"):]
            super().do_GET()

        def do_POST(self):  # noqa: N802
            # D6: the fleet layer is pure read. The ONLY POST route is the
            # per-repo reorder, nested under its slug.
            route = self.path.split("?", 1)[0]
            if route.startswith("/repo/"):
                slug, sub = self._repo_route(route)
                if sub == "api/queue":
                    root = _resolve_slug(slug)
                    if root is None:
                        _send_json(self, 404,
                                   {"error": f"unknown repo slug: {slug!r}"})
                        return
                    _queue_post(self, Path(root), _locked_fn(root)())
                    return
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):  # silence default request logging in tests
            pass

    return ThreadingHTTPServer((host, port), FleetHandler)
