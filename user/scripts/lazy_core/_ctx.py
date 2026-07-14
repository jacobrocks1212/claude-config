"""lazy_core._ctx — shared mutable context + kernel for the lazy_core package.

Owns the state that is genuinely process-global and mutable across the
package: the shared ``_DIAGNOSTICS`` list, the diagnostics helpers that
mutate it, the atomic-write kernel primitive, and accessor-based storage for
the two rebindable globals (``_active_repo_root`` / ``_legacy_state_migrated``)
that used to live directly on the monolith module.

Every other ``lazy_core`` submodule may import this module. This module
imports NO submodule of the package (never ``_monolith``, never any future
sibling) — that asymmetry is what keeps the package's import graph acyclic:
``_ctx`` is the leaf every branch can depend on.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Anchor for sibling-script/template/skill path resolution: the user/scripts/
# directory that used to be Path(__file__).parent when lazy_core was a flat
# module. _ctx.py lives one level deeper (user/scripts/lazy_core/), hence
# .parent.parent.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

# Diagnostics collected across helper calls. compute_state() in lazy-state.py
# resets this at the start of each invocation via clear_diagnostics(), and
# merges the list into the returned state dict before returning. Callers in
# lazy-state.py reference lazy_core._diag / lazy_core.clear_diagnostics so
# they mutate THIS list, not a separate copy.
_DIAGNOSTICS: list[str] = []


def _diag(msg: str) -> None:
    """Append a diagnostic message to the shared _DIAGNOSTICS list."""
    _DIAGNOSTICS.append(msg)


def clear_diagnostics() -> None:
    """Reset the shared _DIAGNOSTICS list (call once per compute_state invocation)."""
    _DIAGNOSTICS.clear()


# ---------------------------------------------------------------------------
# Infrastructure helpers
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically (temp file in the same dir + replace)."""
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
# Rebindable globals: active repo root + legacy-migration one-shot guard
# ---------------------------------------------------------------------------

# The active repo root for this process. None = fall back to the cwd's git
# toplevel (set via the statedir public wrapper set_active_repo_root(), which
# is the precise binding done at main()).
_active_repo_root: str | None = None


def get_active_repo_root() -> str | None:
    return _active_repo_root


def set_active_repo_root_value(repo_root: str | None) -> None:
    global _active_repo_root
    _active_repo_root = str(repo_root) if repo_root else None


# One-shot guard so the legacy-base-dir migration runs at most once per process.
_legacy_state_migrated: bool = False


def legacy_state_migrated() -> bool:
    return _legacy_state_migrated


def set_legacy_state_migrated(value: bool) -> None:
    global _legacy_state_migrated
    _legacy_state_migrated = bool(value)


# lazy-core-package-decomposition Phase 5 WU-3: `_die` (the CLI error-exit
# kernel helper) moved here from _monolith.py — verbatim.

def _die(msg: str, path: Path | None = None) -> None:
    """Emit error JSON to stdout and exit 2."""
    out = {
        "error": msg,
        "path": str(path) if path else None,
    }
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    sys.exit(2)
