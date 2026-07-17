"""Shared console-encoding helper for claude-config CLI scripts.

On Windows the default `sys.stdout`/`sys.stderr` codec is `cp1252`
(`locale.getpreferredencoding()`), which cannot encode the status markers the
pipeline prints (`→ ✓ ✗ ⚠ …`) — printing one raises `UnicodeEncodeError` and
crashes the run. Reconfiguring the streams to UTF-8 once at entry makes every
subsequent write safe without an ambient `PYTHONUTF8`/`PYTHONIOENCODING`.

Stdlib-only and dependency-free so any entrypoint (including ones that must not
pull in `lazy_core`) can call it.
"""

import sys


def enable_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 (best-effort, idempotent, safe).

    Call once at the top of a CLI ``main()``. No-op when the stream is not a
    reconfigurable ``TextIOWrapper`` (e.g. pytest capture replaces it) — those
    substitutes already handle UTF-8, so the ``AttributeError``/``ValueError``
    is swallowed rather than made fatal.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
