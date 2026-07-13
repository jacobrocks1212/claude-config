"""lazy_core.statedir — the hook-touched per-repo state-dir surface.

Extracted VERBATIM from lazy_core/_monolith.py (lazy-core-package-decomposition
Phase 2, Batch 5, WU-5) — a move-only refactor with zero behavior change. This
is the module that REALIZES the SPEC D4 hook-latency cut: the three
hook-touched names (`claude_state_dir`, `_load_registry`, `append_hook_event`)
plus their minimal private closure (`repo_key`, `migrate_legacy_state_dir`,
`active_repo_root`/`set_active_repo_root`, the state-dir filename constants)
import from stdlib + `_ctx` ONLY, so a hook probe that touches exactly these
names never pays the ~17K-line `_monolith` import
(test_hook_surface_imports_without_monolith is the mechanical pin).

The ONE exception is deliberately deferred, not top-level: `active_repo_root`'s
cwd-git-toplevel FALLBACK does a function-local `from ._monolith import _git`
— the fallback only runs when no repo binding was made (`set_active_repo_root`
at each script's main()), which the hook path always does via `--repo-root`.
Anything marker-plane (`read_run_marker`, staleness) stays in `_monolith`
until Phase 5 — the guard's marker-reading paths still pay `_monolith`.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from . import _ctx

# Marker filename inside the state dir.
_MARKER_FILENAME = "lazy-run-marker.json"


# Registry filename inside the state dir.
_REGISTRY_FILENAME = "lazy-prompt-registry.json"


# incident-auto-capture Phase 1 (D2): hook-events filename (JSONL, append-only).
# Countable history of hook deny/error events — the single overwritten
# hook-error.json breadcrumb stays byte-identical (it remains the at-a-glance
# "is a hook broken" file); this file is what makes recurrence observable for
# incident-scan.py.
_HOOK_EVENTS_FILENAME = "hook-events.jsonl"

# Phase 7: max characters retained for the ledger's reason_head / prompt_head
# summary fields (keeps the JSONL line bounded regardless of prompt size).
_LEDGER_HEAD_CHARS: int = 200


# Run-scoped state filenames that live directly under the state dir and must
# migrate together from the legacy (un-keyed) base dir into the keyed subdir.
_LEGACY_STATE_FILENAMES: tuple[str, ...] = (
    "lazy-run-marker.json",
    "lazy-prompt-registry.json",
    "lazy-deny-ledger.jsonl",
    "lazy-cycle-active.json",
    "lazy-run-checkpoint.json",
)


def set_active_repo_root(repo_root: str | None) -> None:
    """Bind the active repo root for this process (called once at main()).

    Passing a falsy value clears the binding, reverting active_repo_root() to
    the cwd-git-toplevel fallback.  Idempotent within a process.
    """
    _ctx.set_active_repo_root_value(repo_root)


def active_repo_root() -> str:
    """Return the active repo root: the explicit binding, else the cwd's git
    toplevel, else the cwd itself.  Always returns a non-empty string."""
    from ._monolith import _git  # Phase-5 re-point (git helper still monolith-resident)
    bound = _ctx.get_active_repo_root()
    if bound:
        return bound
    try:
        cp = _git(Path.cwd(), "rev-parse", "--show-toplevel")
        top = (cp.stdout or "").strip()
        if cp.returncode == 0 and top:
            return top
    except Exception:  # noqa: BLE001
        pass
    return str(Path.cwd())


def repo_key(repo_root: str) -> str:
    """The ONE canonical per-repo state-dir key.  SHA-1 of the normalized real
    path (resolve symlinks → forward slashes → strip trailing slash → lowercase
    a Windows drive letter).  Single source of truth — the bash hooks never
    re-derive this; they call ``lazy-state.py --marker-present`` which routes
    through here.  Normalization-invariant: trailing-slash / separator /
    drive-case variants of the same path collapse to one key."""
    norm = os.path.realpath(str(repo_root)).replace("\\", "/").rstrip("/")
    if len(norm) >= 2 and norm[1] == ":":  # lowercase a Windows drive letter
        norm = norm[0].lower() + norm[1:]
    if not norm:  # realpath of an empty string can normalize to cwd; guard anyway
        norm = "/"
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def migrate_legacy_state_dir(base: Path) -> bool:
    """Move legacy un-keyed base-dir run state into the per-repo keyed subdir.

    Runs at most once per process (the ``_ctx.legacy_state_migrated()`` guard).
    Best-effort and idempotent:
      - No legacy ``lazy-run-marker.json`` in ``base`` → nothing to migrate
        (fresh machine / already migrated) → returns False.
      - A legacy marker whose ``repo_root`` cannot be resolved → the marker is
        treated as stale and removed; no subdir is created.
      - Otherwise the five run-scoped files are moved into
        ``base/<repo_key(marker.repo_root)>/`` (a file already present at the
        target wins; the legacy copy is dropped).

    NEVER called for a LAZY_STATE_DIR-overridden dir (that path returns the
    override verbatim before reaching here), so hermetic tests are untouched.
    """
    if _ctx.legacy_state_migrated():
        return False
    _ctx.set_legacy_state_migrated(True)
    legacy_marker = base / _MARKER_FILENAME
    if not legacy_marker.exists():
        return False
    try:
        m = json.loads(legacy_marker.read_text(encoding="utf-8"))
        rr = m.get("repo_root") if isinstance(m, dict) else None
    except (OSError, json.JSONDecodeError, ValueError):
        rr = None
    if not rr:
        # Unresolvable owner — the marker belongs to no readable repo; drop it.
        try:
            legacy_marker.unlink()
        except OSError:
            pass
        return False
    target = base / repo_key(rr)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    moved = False
    for name in _LEGACY_STATE_FILENAMES:
        src = base / name
        if not (src.exists() and src.is_file()):
            continue
        dst = target / name
        try:
            if dst.exists():
                src.unlink()  # target already populated — drop the legacy copy
            else:
                src.replace(dst)
            moved = True
        except OSError:
            pass
    return moved


def claude_state_dir(create: bool = True) -> Path:
    """Return the Claude state directory, optionally creating it on demand.

    Default resolution: ``~/.claude/state/``.

    Override: set the ``LAZY_STATE_DIR`` environment variable to any absolute
    path — the function will use that directory instead of the default.  This
    env-var override exists for two purposes:
      1. **Hermetic unit tests** (test_lazy_core.py): each test that touches
         the state dir sets ``LAZY_STATE_DIR`` to a ``tempfile.TemporaryDirectory``
         and clears it afterward, so tests never touch ``~/.claude/state/``.
      2. **Hook pipe-tests** (Phase 2): the inject/validate hooks can point at a
         fixture state dir via env var for scriptable, reproducible pipe-test runs
         on both Windows (git-bash) and WSL without affecting the live session.

    Args:
        create: when True (default) create the directory if absent — used by
                write paths (write_run_marker, register_emission, etc.).
                Pass ``create=False`` from read-only paths (read_run_marker,
                _load_registry, lookup_emission, delete_run_marker, etc.) so a
                probe that finds no marker never creates ``~/.claude/state/``
                as a side-effect.  A missing directory on a read path simply
                means "no state" — callers treat a missing path the same as an
                empty result.
    """
    override = os.environ.get("LAZY_STATE_DIR")
    if override:
        # Hermetic override: return the exact dir (tests + hook pipe-tests).
        # No per-repo keying, no migration — preserves byte-for-byte path
        # semantics for every test that sets LAZY_STATE_DIR.
        d = Path(override)
    else:
        # Production: scope the state dir per repo so concurrent runs in
        # different repos are isolated.  Migrate any legacy un-keyed base-dir
        # state into the keyed subdir once, then resolve the active repo's dir.
        base = Path.home() / ".claude" / "state"
        migrate_legacy_state_dir(base)
        d = base / repo_key(active_repo_root())
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _load_registry() -> dict:
    """Load the prompt registry from disk.  Returns ``{"entries": []}`` on any
    read/parse error (fail-open — the validate hook also fails open separately).

    Corrupt registry → start fresh so a bad write never bricks subsequent
    sessions.  The old file is left in place; the next write (via
    register_emission) will atomically replace it with a clean copy.

    Read-only path: passes ``create=False`` to ``claude_state_dir()`` so a
    registry probe never creates ``~/.claude/state/`` as a side-effect.
    """
    # Read-only — do not create the directory if absent; treat as empty.
    registry_path = claude_state_dir(create=False) / _REGISTRY_FILENAME
    if not registry_path.exists():
        return {"entries": []}
    try:
        raw = registry_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    # Corrupt / wrong shape — start fresh.
    return {"entries": []}


def append_hook_event(
    kind: str,
    hook: str,
    signature: str,
    detail: str,
    repo_root: str | None = None,
    now: float | None = None,
) -> bool:
    """Append one hook deny/error event to ``hook-events.jsonl`` (JSONL).

    incident-auto-capture Phase 1 (D2): the shared, best-effort appender that
    makes hook-level denies and fail-open errors COUNTABLE. The single
    overwritten ``hook-error.json`` breadcrumb keeps being written byte-
    identically by its existing writers; this append-only file is the countable
    history the ``incident-scan.py`` collector clusters over.

    Entry shape (one JSON object per line):
        {"ts": <epoch float>, "kind": "error"|"deny", "hook": <str>,
         "repo_root": <str — best-effort attribution, may be "">,
         "signature": <≤200 chars — the hook's own deny-signature token /
         classified op / takeover signature; "" for errors>,
         "detail": <≤500 chars — human-readable specifics>}

    Best-effort / fail-open — the SAME sacred contract as
    ``append_deny_ledger_entry`` / ``append_friction_ledger_entry``: an append
    failure can NEVER change a hook's deny/allow output. This function swallows
    its own write errors and returns False rather than raising, and callers
    additionally wrap it, so it is safe to call from any deny/error site.

    The file lives beside the deny ledger in ``claude_state_dir()`` — the keyed
    per-repo dir in production (repo resolvable via the active-repo binding),
    the exact ``LAZY_STATE_DIR`` dir in hermetic tests, and the un-keyed base
    dir when no repo is resolvable (matching the breadcrumbs' residency rules).

    Args:
        kind: "deny" or "error" (the collector's kind discriminator).
        hook: the emitting hook's name (e.g. "lazy-cycle-containment").
        signature: the hook's per-class cluster signature (D4); "" for errors.
        detail: human-readable specifics (deny reason head / error message).
        repo_root: best-effort repo attribution recorded on the entry; None → "".
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "kind": kind,
            "hook": hook,
            "repo_root": repo_root or "",
            "signature": (signature or "")[:_LEDGER_HEAD_CHARS],
            # Detail gets a slightly larger cap than the ledger heads: raw deny
            # reasons are the collector's capsule evidence, but the line must
            # stay bounded.
            "detail": (detail or "")[:500],
        }
        events_path = claude_state_dir() / _HOOK_EVENTS_FILENAME
        # Plain append (not _atomic_write): append-only file whose reader is
        # corrupt-line-tolerant — same rationale as the deny ledger.
        with events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: an events write must never propagate.
        return False
