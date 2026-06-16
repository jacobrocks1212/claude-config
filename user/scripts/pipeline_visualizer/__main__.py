"""CLI entry — `python -m pipeline_visualizer`.

Boots the visualizer ThreadingHTTPServer and prints the serve URL.

    python -m pipeline_visualizer --repo-root <path> --port 8765 --host 127.0.0.1
"""

from __future__ import annotations

import argparse
import os
import sys

from .server import make_server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="pipeline_visualizer",
        description="Local web control-plane for the lazy feature/bug pipelines.",
    )
    parser.add_argument(
        "--repo-root", default=os.getcwd(),
        help="Repo whose docs/features + docs/bugs to visualize (default: cwd).",
    )
    parser.add_argument(
        "--port", type=int, default=8765,
        help="Port to bind (default: 8765; 0 = ephemeral).",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Host/interface to bind (default: 127.0.0.1).",
    )
    args = parser.parse_args(argv)

    httpd = make_server(repo_root=args.repo_root, host=args.host, port=args.port)
    bound_host, bound_port = httpd.server_address[0], httpd.server_address[1]
    print(f"Lazy Pipeline Visualizer serving at http://{bound_host}:{bound_port}/")
    print(f"  repo-root: {args.repo_root}")
    print("  endpoints: /api/state  /api/queue   (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
