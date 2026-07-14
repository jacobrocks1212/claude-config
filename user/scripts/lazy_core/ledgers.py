"""lazy_core.ledgers — the append-only ledger / provenance / telemetry / intervention plane.

Extracted VERBATIM from lazy_core/_monolith.py (lazy-core-package-decomposition
Phase 4, WU-2) — a move-only refactor with zero behavior change. Owns the
deny/friction ledger (append / read / ack / same-cause dedup + the hardening
emit-command composition over the oldest unacked deny), the hook-events
reader + guard-plane heartbeat, the commit-bracket ledger, the provenance
plane (``write_provenance`` distillate + reverse index, link / backfill /
lint), the auto-readmit + transcription-slip deny-ledger entries, the
efficacy breadcrumbs, the telemetry ledger (append / read / rotate / cloud
flush), the intervention-hypothesis capture (``record_intervention`` + the
canary arming block, incl. ``_CANARY_CONTROL_SURFACES_FALLBACK`` carrying the
Phase-1 ``user/scripts/lazy_core/**`` glob), and the intervention constants.

Write-path move sanctioned by the two archived bug receipts (SPEC D2
Constraint 3): docs/bugs/_archive/mark-complete-partial-apply-noop-unrecoverable/
FIXED.md and docs/bugs/_archive/production-sentinel-writes-bypass-atomic-write/
FIXED.md. All writes here go through ``_ctx._atomic_write``.

Deferred function-local imports (this module must not import ``_monolith`` at
top level — circular, since ``_monolith`` imports FROM this module): the
marker/registry-plane names (``read_run_marker`` / ``read_cycle_marker`` /
``head_sha_snapshot`` / ``_MARKER_STALE_SECONDS`` / ``REGISTRY_ENTRY_TTL_SECONDS``,
Phase-5 re-point), ``_parse_locked_decisions`` (gate-coverage plane, Phase-5),
and ``normalize_prompt_for_hash`` (dispatch/registry plane — re-pointed to
``.dispatch`` at Phase 4 WU-3). ``build_hardening_emit_command``'s
``registry_summary`` is a PARAMETER (caller-supplied summary string), not the
module-level registry function — no import.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shlex
import subprocess
import time

import yaml

from pathlib import Path

from ._ctx import _atomic_write, _diag
from .docmodel import parse_sentinel
from .statedir import (
    _HOOK_EVENTS_FILENAME,
    _LEDGER_HEAD_CHARS,
    _MARKER_FILENAME,
    _load_registry,
    active_repo_root,
    claude_state_dir,
    repo_key,
)


# Phase 7 WU-7.1: deny-ledger filename (one JSON object per line; JSONL).
# The guard appends one entry on EVERY deny; --emit-dispatch hardening acks the
# oldest unacked entry (FIFO); --run-end refuses on unacked entries unless
# --ack-unhardened is passed.
_DENY_LEDGER_FILENAME = "lazy-deny-ledger.jsonl"


# ---------------------------------------------------------------------------
# Phase 7 WU-7.1 — Deny ledger (routed hardening debt)
# ---------------------------------------------------------------------------
#
# Every guard deny appends one JSON line to lazy-deny-ledger.jsonl (best-effort,
# fail-open — the guard's own writer wraps this in try/except so a ledger failure
# never changes the deny response).  The ledger is the ground truth for "how many
# denials this run still owe a hardening round": --emit-dispatch hardening acks
# the OLDEST unacked entry (FIFO, one per emission), and --run-end refuses to
# retire the marker while unacked entries remain unless --ack-unhardened is passed.
#
# The deny path is the ONLY writer of new entries; allows never write.  Reads and
# acks tolerate a missing or partially-corrupt file: unparseable lines are skipped
# rather than treated as a fatal error (a single bad append must not brick the
# whole ledger).


def append_deny_ledger_entry(
    tool_use_id: str,
    denied_sha12: str,
    reason_head: str,
    prompt_head: str,
    now: float | None = None,
) -> bool:
    """Append one deny entry to the deny ledger (JSONL), best-effort.

    Called by lazy_guard.py on EVERY deny.  The caller wraps this in its own
    try/except so a ledger-write failure never changes the guard's deny output
    or exit code (fail-open is sacred) — this function additionally swallows its
    own write errors and returns False rather than raising, so it is safe to call
    from any context.

    Entry shape (one JSON object per line):
        {"ts": <epoch float>, "tool_use_id": <str>, "denied_sha12": <12 hex>,
         "reason_head": <≤200 chars>, "prompt_head": <≤200 chars>, "acked": false}

    Args:
        tool_use_id: the denied Agent dispatch's tool_use_id (may be "").
        denied_sha12: the first 12 hex chars of the computed prompt sha256.
        reason_head: the deny reason, truncated to the first ~200 chars.
        prompt_head: the dispatched prompt, truncated to the first ~200 chars.
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "tool_use_id": tool_use_id,
            "denied_sha12": denied_sha12,
            "reason_head": (reason_head or "")[:_LEDGER_HEAD_CHARS],
            "prompt_head": (prompt_head or "")[:_LEDGER_HEAD_CHARS],
            "acked": False,
            # Residual gap B (loop-detector-false-positives-probes-and-cross-run-state):
            # stamp the entry with the LIVE run marker's identity (None when no
            # marker exists — e.g. a manual/no-marker deny). `pending_hardening()`
            # et al. compare this against the CURRENT live marker so a crashed
            # run's leftover unacked entries no longer force the NEXT run to
            # drain debt it never saw. Non-destructive read — never creates the
            # state dir as a side effect.
            "run_started_at": _raw_marker_started_at(),
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        # Append a single compact JSON line.  Plain append (not _atomic_write):
        # the ledger is append-only and a torn final line is tolerated by the
        # corrupt-line-skipping reader, so the atomic-rewrite ceremony would only
        # add a read-modify-write race window with the ack path.
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate.
        return False


def append_friction_ledger_entry(
    reason_head: str,
    detail: str,
    now: float | None = None,
) -> bool:
    """Append one process-friction entry to the SAME deny ledger (JSONL).

    hardening-blind-to-process-friction Phase 2 (D1): when --cycle-end detects a
    torn cycle bracket or unexpected commits, it records the friction as
    hardening debt by appending to ``lazy-deny-ledger.jsonl`` — the SAME file the
    guard's denies use. A ``kind: "process-friction"`` discriminator lets a single
    reader walk denies + friction, while the existing consumers
    (``pending_hardening()`` / ``oldest_unacked_deny()`` / the ``--run-end`` gate /
    the ``--emit-prompt`` probe's withholding) count any unacked entry unchanged —
    so a runaway self-announces as hardening debt with NO new routing machinery.

    Entry shape (one JSON object per line):
        {"ts": <epoch float>, "kind": "process-friction",
         "reason_head": <≤200 chars — the signal: cycle-bracket-break /
         unexpected-commits>, "detail": <≤200 chars — the human-readable
         specifics>, "acked": false}

    Best-effort / fail-open — identical contract to append_deny_ledger_entry: the
    caller wraps this, and it additionally swallows its own write errors and
    returns False rather than raising, so a ledger-write failure never derails the
    --cycle-end marker clear.

    Args:
        reason_head: the friction signal name (e.g. "cycle-bracket-break"),
            truncated to the head-char cap.
        detail: the human-readable specifics of the friction, truncated to the cap.
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "kind": "process-friction",
            "reason_head": (reason_head or "")[:_LEDGER_HEAD_CHARS],
            "detail": (detail or "")[:_LEDGER_HEAD_CHARS],
            "acked": False,
            # Residual gap B — same run-identity stamp as append_deny_ledger_entry
            # (None when no live run marker exists, e.g. the torn-bracket case
            # where the marker is already gone by the time --cycle-end runs).
            "run_started_at": _raw_marker_started_at(),
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate.
        return False


def read_hook_events() -> list[dict]:
    """Read all ``hook-events.jsonl`` entries, skipping any unparseable lines.

    Mirrors ``read_deny_ledger``'s corrupt-line-tolerant shape (a torn final
    append must not brick the whole read). A missing file → empty list
    (no hook deny/error events recorded yet).
    """
    events_path = claude_state_dir(create=False) / _HOOK_EVENTS_FILENAME
    if not events_path.exists():
        return []
    try:
        raw = events_path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            entries.append(obj)
    return entries


# guard-fail-open-leaves-no-trace item 4 (STATE-lane descoped residual,
# docs/bugs/_archive/guard-fail-open-leaves-no-trace) — a REPORT-ONLY, never-
# halting fail-open "dead guard plane" advisory. SPEC D2 left the exact shape
# genuinely undecided ("decide at planning: inject-banner vs --probe vs
# both"); FIXED.md recommends "a follow-up STATE-lane bug/enhancement". This
# is the cheapest state-script-visible proxy without a HOOKS-lane change
# (out of this seam's scope — no per-invocation heartbeat WRITE exists on
# the hook side; hook-events.jsonl only fires on a DENY or an ERROR, never a
# healthy silent ALLOW, by the bug's own Fix Scope item 1 design).
_GUARD_PLANE_HEARTBEAT_MIN_CYCLES = 5


def guard_plane_heartbeat(*, now: float | None = None) -> "dict | None":
    """Surface the SPEC's literal ask — "guards executed 0 times this run"
    (Fix Scope item 4) — as a report-only probe diagnostic. PURE READ; never
    raises; NEVER gates or halts anything.

    Counts ``hook-events.jsonl`` entries (``kind: deny|error`` — the HOOKS-
    lane fix for this same bug's Verified Symptoms (a)/(b)/(c)) timestamped
    at-or-after the LIVE run marker's ``started_at``. Returns ``None`` (too
    early / nothing to assess) when there is no live run marker, or the
    marker's own ``forward_cycles + meta_cycles`` has not yet reached
    ``_GUARD_PLANE_HEARTBEAT_MIN_CYCLES`` — a run that just started
    legitimately has zero guard events regardless of health.

    Returns ``{"events_this_run": int, "cycles_this_run": int, "quiet":
    bool}`` otherwise (``quiet`` iff ``events_this_run == 0``).

    **HONESTY CAVEAT (documented, not silent):** this is a WEAK, ADVISORY
    signal, not a reliable dead-plane detector. A genuinely healthy multi-
    cycle run can legitimately see zero denies/errors for its entire
    duration — most guard hooks fast-path-ALLOW silently by design, and only
    a deny or a crash is countable in ``hook-events.jsonl``. ``quiet: True``
    means "worth a glance", never "confirmed dead". Any read/parse error
    (corrupt marker, unreadable ledger) degrades to ``None`` — fail-open,
    exactly like every other diagnostic-only helper in this module.
    """
    from ._monolith import read_run_marker  # Phase-5 re-point (marker plane still monolith-resident)
    if now is None:
        now = time.time()
    try:
        marker = read_run_marker(now=now)
        if marker is None:
            return None
        forward = int(marker.get("forward_cycles") or 0)
        meta = int(marker.get("meta_cycles") or 0)
    except Exception:  # noqa: BLE001
        return None
    cycles_this_run = forward + meta
    if cycles_this_run < _GUARD_PLANE_HEARTBEAT_MIN_CYCLES:
        return None
    started_at_str = marker.get("started_at", "")
    try:
        started_dt = datetime.datetime.strptime(started_at_str, "%Y-%m-%dT%H:%M:%SZ")
        started_epoch = (
            started_dt - datetime.datetime(1970, 1, 1)
        ).total_seconds()
    except (ValueError, TypeError):
        return None
    try:
        events = read_hook_events()
    except Exception:  # noqa: BLE001
        return None
    count = 0
    for e in events:
        try:
            ts = float(e.get("ts"))
        except (TypeError, ValueError):
            continue
        if ts >= started_epoch:
            count += 1
    return {
        "events_this_run": count,
        "cycles_this_run": cycles_this_run,
        "quiet": count == 0,
    }


# ---------------------------------------------------------------------------
# Commit-bracket ledger (code-doc-provenance-linkage Phase 1 / SPEC D4-A)
#
# Per-cycle commit brackets are the deterministic raw material for the
# provenance producer's touched-file-set derivation: at --cycle-end (BOTH state
# scripts — coupled pair) the cycle marker's begin_head_sha → current-HEAD span
# is appended as {feature_id, begin_sha, end_sha, ts} to
# ``lazy-commit-brackets.jsonl`` in the per-repo keyed state dir. Append-only,
# FAIL-OPEN — the identical contract to append_friction_ledger_entry: a write
# failure returns False and never blocks the --cycle-end marker clear.
# ---------------------------------------------------------------------------

_COMMIT_BRACKETS_FILENAME = "lazy-commit-brackets.jsonl"


def append_commit_bracket(
    feature_id: str,
    begin_sha: str,
    end_sha: str,
    now: float | None = None,
) -> bool:
    """Append one commit-bracket record to the state-dir bracket ledger.

    Entry shape (one JSON object per line):
        {"ts": <epoch float>, "feature_id": <str>,
         "begin_sha": <str>, "end_sha": <str>}

    Best-effort / fail-open: swallows its own write errors and returns False
    rather than raising, so a ledger-write failure never derails the
    --cycle-end marker clear (identical to append_friction_ledger_entry).

    Returns:
        True if the line was appended; False on any write failure.
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "feature_id": feature_id,
            "begin_sha": begin_sha,
            "end_sha": end_sha,
        }
        ledger_path = claude_state_dir() / _COMMIT_BRACKETS_FILENAME
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate.
        return False


def read_commit_brackets(item_id: str) -> list[dict]:
    """Return the recorded commit brackets for ``item_id`` (pure read).

    Reads ``lazy-commit-brackets.jsonl`` from the state dir and filters by the
    ``feature_id`` field (the bug pipeline records its bug ids in the same
    field — the cycle marker's id slot is shared). Malformed lines are skipped;
    a missing ledger / any read error degrades to ``[]`` (never raises, never
    creates the state dir).
    """
    try:
        ledger_path = claude_state_dir(create=False) / _COMMIT_BRACKETS_FILENAME
        if not ledger_path.is_file():
            return []
        out: list[dict] = []
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and entry.get("feature_id") == item_id:
                out.append(entry)
        return out
    except Exception:  # noqa: BLE001
        return []


def record_cycle_commit_bracket(
    repo_root: Path | None = None,
    now: float | None = None,
) -> dict | None:
    """--cycle-end bracket recording (called by BOTH state scripts' handlers
    immediately BEFORE clear_cycle_marker — coupled pair).

    Reads the live cycle marker (the --cycle-begin snapshot), resolves the
    current HEAD, and appends the {feature_id, begin_sha, end_sha} bracket to
    the ledger via append_commit_bracket.

    Degradations (all return None; NEVER raise — the clear must proceed):
      - no/partial cycle marker (no feature_id or no begin_head_sha snapshot);
      - HEAD unresolvable (non-git tree);
      - begin == end (an empty bracket contributes no touched files and would
        only bloat the ledger — skipped);
      - the append itself failing (fail-open, returns False).

    Returns:
        The recorded bracket dict {feature_id, begin_sha, end_sha}, or None.
    """
    from ._monolith import head_sha_snapshot, read_cycle_marker  # Phase-5 re-point (marker plane still monolith-resident)
    try:
        marker = read_cycle_marker()
        if not isinstance(marker, dict):
            return None
        feature_id = marker.get("feature_id")
        begin_sha = marker.get("begin_head_sha")
        if not feature_id or not begin_sha:
            return None
        root = repo_root or Path.cwd()
        end_sha = head_sha_snapshot(root)
        if not end_sha or end_sha == begin_sha:
            return None
        if not append_commit_bracket(feature_id, begin_sha, end_sha, now=now):
            return None
        return {
            "feature_id": feature_id,
            "begin_sha": begin_sha,
            "end_sha": end_sha,
        }
    except Exception:  # noqa: BLE001
        # Fail-open: bracket bookkeeping must never block the marker clear.
        return None


# ---------------------------------------------------------------------------
# Provenance producer (code-doc-provenance-linkage Phase 2)
#
# ONE WRITER, TWO TRIGGERS (SPEC D1-B): write_provenance is the SOLE author of
# the per-item IMPLEMENTED.md distillate (D2-A) and the committed per-repo
# reverse index docs/provenance-index.json (D3-A). It is called from:
#   1. the __mark_complete__/__mark_fixed__ branch of apply_pseudo (the
#      automatic completion-gate trigger, provenance: pipeline-gated), and
#   2. the --link-provenance / --backfill-provenance CLI handlers (the manual
#      trigger, provenance: manual | backfilled).
# The provenance enum (D9): pipeline-gated | manual (+ linked_by) | backfilled.
# The derivation enum (D4): commit-brackets | commit-range | message-grep.
# ---------------------------------------------------------------------------

_PROVENANCE_VALUES = ("pipeline-gated", "manual", "backfilled")
_PROVENANCE_KINDS = ("feature", "bug")


def _provenance_index_path(repo_root: Path) -> Path:
    """The committed per-repo reverse-index location (D3-A)."""
    return Path(repo_root) / "docs" / "provenance-index.json"


def _normalize_index_key(repo_root: Path, path_str: str) -> str:
    """Normalize a file path to the index's repo-relative POSIX key form."""
    s = str(path_str).replace("\\", "/").strip()
    # Strip an absolute repo_root prefix when present.
    root_posix = str(Path(repo_root)).replace("\\", "/").rstrip("/")
    if root_posix and s.startswith(root_posix + "/"):
        s = s[len(root_posix) + 1:]
    while s.startswith("./"):
        s = s[2:]
    return s.strip("/")


def _spec_summary_paragraph(item_dir: Path) -> str | None:
    """Extract the SPEC's leading ``>`` blockquote summary paragraph, verbatim
    (unwrapped to a single flowing paragraph). None when SPEC.md is absent or
    carries no leading blockquote."""
    spec_md_path = Path(item_dir) / "SPEC.md"
    if not spec_md_path.is_file():
        return None
    try:
        lines = spec_md_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    quote: list[str] = []
    seen_quote = False
    for ln in lines:
        s = ln.strip()
        if s.startswith(">"):
            seen_quote = True
            quote.append(s.lstrip(">").strip())
        elif seen_quote:
            break  # the first blockquote block ended
        elif s.startswith("#") or not s:
            continue  # title / blanks before the summary
        else:
            break  # prose before any blockquote → no leading summary
    text = " ".join(q for q in quote if q).strip()
    return text or None


def _git_capture_lines(repo_root: Path, args: list[str]) -> list[str] | None:
    """Run a git command under repo_root and return stdout lines, or None on
    any failure (non-git tree, bad revision, git unavailable). Never raises."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root)] + args,
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return None
        return r.stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return None


def derive_touched_from_range(repo_root: Path, rev_range: str) -> dict | None:
    """Derive {commits, files} from a git revision range (e.g. ``A..B``).

    commits = authored (merge-excluded) short shas in the range, oldest first;
    files = the range's ``git diff --name-only`` set, sorted. None when the
    range cannot be resolved (the caller decides the fallback)."""
    commits = _git_capture_lines(
        repo_root, ["rev-list", "--no-merges", "--reverse", rev_range])
    files = _git_capture_lines(repo_root, ["diff", "--name-only", rev_range])
    if commits is None or files is None:
        return None
    return {
        "commits": [c.strip()[:7] for c in commits if c.strip()],
        "files": sorted({f.strip() for f in files if f.strip()}),
    }


def derive_touched_from_brackets(repo_root: Path, item_id: str) -> dict | None:
    """Union {commits, files} over the item's recorded commit brackets (D4-A,
    the pipeline-primary derivation). None when no bracket resolves (no
    brackets recorded, or every recorded sha is unreachable) — the caller
    falls back to message-grep with an honest derivation label."""
    brackets = read_commit_brackets(item_id)
    if not brackets:
        return None
    commits: list[str] = []
    files: set[str] = set()
    any_resolved = False
    for b in brackets:
        begin = b.get("begin_sha")
        end = b.get("end_sha")
        if not begin or not end:
            continue
        r = derive_touched_from_range(repo_root, f"{begin}..{end}")
        if r is None:
            continue
        any_resolved = True
        for c in r["commits"]:
            if c not in commits:
                commits.append(c)
        files.update(r["files"])
    if not any_resolved:
        return None
    return {"commits": commits, "files": sorted(files)}


def derive_touched_from_grep(repo_root: Path, item_id: str) -> dict:
    """Message-grep fallback derivation (D4-B, explicitly degraded): commits
    whose message contains the item id literal (fixed-string), plus their
    touched files. Empty lists when nothing matches / not a git tree."""
    out = _git_capture_lines(
        repo_root,
        ["log", "--no-merges", "--fixed-strings", f"--grep={item_id}",
         "--name-only", "--pretty=format:%H"],
    )
    if out is None:
        return {"commits": [], "files": []}
    commits: list[str] = []
    files: set[str] = set()
    sha_re = re.compile(r"^[0-9a-f]{40}$")
    for ln in out:
        s = ln.strip()
        if not s:
            continue
        if sha_re.match(s):
            short = s[:7]
            if short not in commits:
                commits.append(short)
        else:
            files.add(s)
    return {"commits": commits, "files": sorted(files)}


def write_provenance(
    repo_root: Path,
    item_dir: Path,
    item_id: str,
    kind: str,
    commits: list[str],
    files: list[str],
    *,
    provenance: str = "pipeline-gated",
    derivation: str = "commit-brackets",
    date: str | None = None,
    body: str | None = None,
    linked_by: str | None = None,
    validated_line: str | None = None,
    dry_run: bool = False,
) -> dict:
    """THE provenance producer — sole author of IMPLEMENTED.md + the index.

    Writes (atomically, via _atomic_write):
      1. ``item_dir/IMPLEMENTED.md`` — the D2-A distillate: frontmatter
         (kind: implemented, feature_id, date, provenance, [linked_by,]
         derivation, commits, decisions) + a deterministic body (the SPEC's
         leading ``>`` summary verbatim, the Locked-Decision id — title rows
         via _parse_locked_decisions, and the receipt-facts line). A manual
         ``body`` (the D8 operator-approved prose) replaces the deterministic
         body; the producer still owns the frontmatter and the index either way.
      2. ``repo_root/docs/provenance-index.json`` — the D3-A reverse index:
         repo-relative POSIX path → sorted [{id, type, provenance}] rows. This
         item's existing rows are REPLACED (re-linking never duplicates);
         other items' rows are preserved byte-for-byte modulo canonical
         ordering. The index write is skipped entirely when the item touches
         no files AND no index exists yet (nothing to record, nothing to trim).

    ``dry_run=True`` computes everything (including ``distillate_preview``)
    and writes NOTHING.

    Returns a dict: {ok, refused, wrote, files, commits, decisions, dry_run}
    (+ distillate_preview on dry_run). Any write/parse failure returns
    ok: False with the refusal text — callers inside the completion gate fold
    that into warnings[]; the manual CLI surfaces it verbatim.
    """
    from ._monolith import _parse_locked_decisions  # Phase-5 re-point (gate-coverage plane still monolith-resident)
    if date is None:
        date = datetime.date.today().isoformat()
    if kind not in _PROVENANCE_KINDS:
        return {"ok": False, "refused": f"unknown item kind {kind!r} "
                f"(expected one of {_PROVENANCE_KINDS})", "wrote": []}
    if provenance not in _PROVENANCE_VALUES:
        return {"ok": False, "refused": f"unknown provenance {provenance!r} "
                f"(expected one of {_PROVENANCE_VALUES})", "wrote": []}

    repo_root = Path(repo_root)
    item_dir = Path(item_dir)

    # Canonicalize inputs (deterministic, byte-stable re-runs).
    norm_files: list[str] = sorted({
        _normalize_index_key(repo_root, f) for f in (files or []) if str(f).strip()
    })
    norm_commits: list[str] = []
    for c in commits or []:
        c = str(c).strip()
        if c and c not in norm_commits:
            norm_commits.append(c)

    # Decisions from the SPEC's canonical Locked-Decision surface (zero new
    # parsing — the same enumeration gate_coverage uses).
    spec_md = ""
    spec_md_path = item_dir / "SPEC.md"
    if spec_md_path.is_file():
        try:
            spec_md = spec_md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            spec_md = ""
    decisions = _parse_locked_decisions(spec_md)
    decision_ids = [d["id"] for d in decisions]

    # --- Assemble the distillate ---
    commits_inline = yaml.safe_dump(
        norm_commits, default_flow_style=True).strip() if norm_commits else "[]"
    decisions_inline = yaml.safe_dump(
        decision_ids, default_flow_style=True).strip() if decision_ids else "[]"
    linked_by_line = f"linked_by: {linked_by}\n" if linked_by else ""
    fm = (
        "---\n"
        "kind: implemented\n"
        f"feature_id: {item_id}\n"
        f"date: {date}\n"
        f"provenance: {provenance}\n"
        f"{linked_by_line}"
        f"derivation: {derivation}\n"
        f"commits: {commits_inline}\n"
        f"decisions: {decisions_inline}\n"
        "---\n"
        "\n"
    )
    if body is not None:
        body_text = "# Implementation Ledger\n\n" + body.strip() + "\n"
    else:
        summary = _spec_summary_paragraph(item_dir) or "(no SPEC summary available)"
        if decisions:
            decision_rows = "\n".join(
                f"- {d['id']} — {d['title']}" for d in decisions)
            decisions_block = f"**Decisions that drove it:**\n{decision_rows}\n"
        else:
            decisions_block = (
                "**Decisions that drove it:** (none — the SPEC carries "
                "no Locked-Decision surface)\n"
            )
        validated_block = f"\n**{validated_line}**\n" if validated_line else ""
        body_text = (
            "# Implementation Ledger\n"
            "\n"
            f"**What shipped:** {summary}\n"
            "\n"
            f"{decisions_block}"
            f"{validated_block}"
        )
    distillate = fm + body_text

    # --- Merge the index (load → replace-this-item's-rows → serialize) ---
    index_path = _provenance_index_path(repo_root)
    try:
        index: dict = {}
        if index_path.is_file():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(index, dict):
                return {"ok": False, "refused":
                        f"{index_path} is not a JSON object — refusing to "
                        "merge; fix the index by hand", "wrote": []}
        merged: dict = {}
        for key, rows in index.items():
            if not isinstance(rows, list):
                continue
            kept = [
                r for r in rows
                if not (isinstance(r, dict)
                        and r.get("id") == item_id and r.get("type") == kind)
            ]
            if kept:
                merged[key] = kept
        for f in norm_files:
            merged.setdefault(f, []).append(
                {"id": item_id, "type": kind, "provenance": provenance})
        # Canonical form: sorted keys; per-key rows sorted by (type, id) and
        # rebuilt to the canonical field order — byte-stable re-runs.
        canonical = {}
        for key in sorted(merged):
            rows = sorted(
                merged[key],
                key=lambda r: (str(r.get("type")), str(r.get("id"))),
            )
            canonical[key] = [
                {"id": r.get("id"), "type": r.get("type"),
                 "provenance": r.get("provenance")}
                for r in rows
            ]
        index_serialized = json.dumps(canonical, indent=2) + "\n"
        # Nothing to record and nothing on disk to trim → skip the index write.
        index_write_needed = bool(canonical) or index_path.is_file()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "refused": f"provenance index could not be "
                f"merged ({exc})", "wrote": []}

    result_base = {
        "files": norm_files,
        "commits": norm_commits,
        "decisions": decision_ids,
        "dry_run": dry_run,
    }
    if dry_run:
        return {"ok": True, "refused": None, "wrote": [],
                "distillate_preview": distillate,
                "index_preview": index_serialized if index_write_needed else None,
                **result_base}

    # --- Writes (atomic; a failure surfaces as ok: False, refused) ---
    wrote: list[str] = []
    try:
        item_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(item_dir / "IMPLEMENTED.md", distillate)
        wrote.append("IMPLEMENTED.md")
        if index_write_needed:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(index_path, index_serialized)
            try:
                wrote.append(str(index_path.relative_to(repo_root)).replace("\\", "/"))
            except ValueError:
                wrote.append(str(index_path))
    except (OSError, ValueError) as exc:
        return {"ok": False, "refused": f"provenance write failed ({exc})",
                "wrote": wrote, **result_base}
    return {"ok": True, "refused": None, "wrote": wrote, **result_base}


def _resolve_provenance_item_dir(repo_root: Path, item_id: str) -> tuple[Path, str]:
    """Resolve an item id to its docs dir + type for the manual link path.

    Search order: docs/features/<id> (feature) → docs/bugs/<id> (bug) →
    docs/bugs/_archive/<id> (bug). When none exists, D8 says the manual path
    creates a MINIMAL decision-record dir — docs/features/<id>/ with the
    distillate as its primary doc (never a fabricated SPEC); the producer's
    mkdir handles the creation.
    """
    repo_root = Path(repo_root)
    candidates: list[tuple[Path, str]] = [
        (repo_root / "docs" / "features" / item_id, "feature"),
        (repo_root / "docs" / "bugs" / item_id, "bug"),
        (repo_root / "docs" / "bugs" / "_archive" / item_id, "bug"),
    ]
    for cand, kind in candidates:
        if cand.is_dir():
            return cand, kind
    return candidates[0]


def _resolve_pr_range(repo_root: Path, pr: int) -> tuple[str | None, str | None]:
    """Resolve a PR number to a ``base..head`` range via `gh pr view` (the D8
    `--pr` sugar). Returns (range, None) on success or (None, refusal) —
    degrading CLEANLY when gh is absent/unauthenticated (the refusal names the
    --commits fallback)."""
    try:
        r = subprocess.run(
            ["gh", "pr", "view", str(pr), "--json", "baseRefOid,headRefOid"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, (f"gh is unavailable ({exc}) — resolve the PR range "
                      "yourself and pass --commits <base>..<head>")
    if r.returncode != 0:
        return None, (f"gh pr view {pr} failed ({(r.stderr or '').strip()[:200]}) "
                      "— pass --commits <base>..<head> instead")
    try:
        data = json.loads(r.stdout)
        base = data["baseRefOid"]
        head = data["headRefOid"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return None, (f"gh pr view {pr} returned an unexpected payload ({exc}) "
                      "— pass --commits <base>..<head> instead")
    return f"{base}..{head}", None


def link_provenance(
    repo_root: Path,
    item_id: str,
    *,
    commit_range: str | None = None,
    pr: int | None = None,
    body_file: Path | None = None,
    linked_by: str | None = None,
    date: str | None = None,
    dry_run: bool = False,
) -> dict:
    """The MANUAL trigger of the one-writer producer (D8-A+C, D9).

    Addressing is commit-range-primary (``--commits A..B``); ``--pr <n>`` is
    sugar resolved via `gh pr view` to a range (clean refusal when gh is
    absent). The touched-file set and commit list are derived from the range
    (derivation: commit-range) and written THROUGH write_provenance with
    ``provenance: manual`` + ``linked_by:`` — so manual entries are
    shape-identical to pipeline entries by construction.

    ``body_file`` carries the operator-APPROVED distillate prose (the
    `/link-provenance` skill's draft-then-approve loop); omitted → the
    deterministic extract. ``dry_run`` derives + previews, writes nothing.
    """
    repo_root = Path(repo_root)

    def _refused(msg: str) -> dict:
        return {"ok": False, "refused": msg, "wrote": [], "dry_run": dry_run}

    if pr is not None and commit_range:
        return _refused("--commits and --pr are mutually exclusive — pass one")
    if pr is not None:
        commit_range, err = _resolve_pr_range(repo_root, pr)
        if err:
            return _refused(err)
    if not commit_range:
        return _refused("--link-provenance requires --commits <A..B> or --pr <n>")

    derived = derive_touched_from_range(repo_root, commit_range)
    if derived is None:
        return _refused(
            f"could not resolve commit range {commit_range!r} under "
            f"{repo_root} — nothing was written"
        )
    if not derived["commits"] and not derived["files"]:
        return _refused(
            f"commit range {commit_range!r} is empty (no authored commits, "
            "no touched files) — nothing to link"
        )

    body: str | None = None
    if body_file is not None:
        try:
            body = Path(body_file).read_text(encoding="utf-8")
        except OSError as exc:
            return _refused(f"--body-file could not be read ({exc})")

    item_dir, kind = _resolve_provenance_item_dir(repo_root, item_id)
    result = write_provenance(
        repo_root, item_dir, item_id, kind,
        derived["commits"], derived["files"],
        provenance="manual", derivation="commit-range",
        date=date, body=body,
        linked_by=(linked_by or "operator"),
        dry_run=dry_run,
    )
    result["commit_range"] = commit_range
    result["kind"] = kind
    try:
        result["item_dir"] = str(item_dir.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        result["item_dir"] = str(item_dir)
    return result


def _provenance_doc_path(repo_root: Path, item_id: str, kind: str) -> str:
    """Resolve an index row's distillate doc path (repo-relative POSIX),
    honoring archive residency for bugs. Falls back to the canonical
    non-archive location string when nothing exists on disk."""
    repo_root = Path(repo_root)
    if kind == "bug":
        candidates = [
            f"docs/bugs/{item_id}/IMPLEMENTED.md",
            f"docs/bugs/_archive/{item_id}/IMPLEMENTED.md",
        ]
    else:
        candidates = [f"docs/features/{item_id}/IMPLEMENTED.md"]
    for rel in candidates:
        if (repo_root / rel).is_file():
            return rel
    return candidates[0]


def provenance_lookup(repo_root: Path, path_str: str) -> dict:
    """PURE READ (D6-A): which decision records govern ``path_str``?

    Loads docs/provenance-index.json, normalizes the query to the index's
    repo-relative POSIX key form, and returns::

        {"path": <key>, "governed_by": [
            {"id", "type", "doc", "decisions", "provenance"}, ...]}

    ``doc`` is the item's IMPLEMENTED.md (archive residency resolved);
    ``decisions`` come from that distillate's frontmatter ([] when unreadable).
    Never mutates, never creates directories, never re-infers state — a
    missing/malformed index degrades to an empty ``governed_by`` (the consumer
    step is a no-op where no index exists)."""
    repo_root = Path(repo_root)
    key = _normalize_index_key(repo_root, path_str)
    out: dict = {"path": key, "governed_by": []}
    index_path = _provenance_index_path(repo_root)
    if not index_path.is_file():
        return out
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return out
    rows = index.get(key) if isinstance(index, dict) else None
    if not isinstance(rows, list):
        return out
    for r in rows:
        if not isinstance(r, dict):
            continue
        item_id = str(r.get("id"))
        kind = str(r.get("type"))
        doc_rel = _provenance_doc_path(repo_root, item_id, kind)
        decisions: list[str] = []
        doc_meta = parse_sentinel(repo_root / doc_rel)
        if doc_meta and isinstance(doc_meta.get("decisions"), list):
            decisions = [str(d) for d in doc_meta["decisions"]]
        out["governed_by"].append({
            "id": item_id,
            "type": kind,
            "doc": doc_rel,
            "decisions": decisions,
            "provenance": r.get("provenance"),
        })
    return out


# Churn-lint defaults (D10) — placeholder thresholds, tunable in one place:
# a file with >= _PROVENANCE_CHURN_THRESHOLD authored commits in the last
# _PROVENANCE_CHURN_DAYS days and NO index rows is a hotspot (the prompt to
# run the manual --link-provenance pass over teammate churn).
_PROVENANCE_CHURN_DAYS = 90
_PROVENANCE_CHURN_THRESHOLD = 5


def _iter_receipted_item_dirs(repo_root: Path):
    """Yield (item_dir, kind, receipt_name) for every dir holding a valid
    completion receipt: docs/features/*/COMPLETED.md (feature),
    docs/bugs/*/FIXED.md and docs/bugs/_archive/*/FIXED.md (bug)."""
    repo_root = Path(repo_root)
    roots = [
        (repo_root / "docs" / "features", "feature", "COMPLETED.md", "completed"),
        (repo_root / "docs" / "bugs", "bug", "FIXED.md", "fixed"),
        (repo_root / "docs" / "bugs" / "_archive", "bug", "FIXED.md", "fixed"),
    ]
    for base, kind, receipt_name, receipt_kind in roots:
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            meta = parse_sentinel(d / receipt_name)
            if meta is not None and meta.get("kind") == receipt_kind:
                yield d, kind, receipt_name


def backfill_provenance(repo_root: Path, date: str | None = None) -> dict:
    """One-shot backfill (D7-A): distill every already-receipted item through
    the ONE producer with honest degraded provenance.

    Walks items with a valid COMPLETED.md/FIXED.md (features, bugs, AND
    docs/bugs/_archive/), skips items already carrying IMPLEMENTED.md
    (idempotent — never clobbers a richer pipeline/manual distillate), derives
    the touched-file set via message-grep (no commit brackets exist for
    pre-feature history), and writes provenance: backfilled +
    derivation: message-grep. A zero-hit slug still gets a distillate
    (commits: []) and contributes no index rows — honest, never silent.
    """
    repo_root = Path(repo_root)
    backfilled: list[str] = []
    skipped_existing: list[str] = []
    no_commit_matches: list[str] = []
    failures: list[str] = []
    for item_dir, kind, receipt_name in _iter_receipted_item_dirs(repo_root):
        item_id = item_dir.name
        if (item_dir / "IMPLEMENTED.md").exists():
            skipped_existing.append(item_id)
            continue
        derived = derive_touched_from_grep(repo_root, item_id)
        receipt_meta = parse_sentinel(item_dir / receipt_name) or {}
        receipt_prov = receipt_meta.get("provenance", "gated")
        if not derived["commits"]:
            no_commit_matches.append(item_id)
            validated_line = (
                f"Backfilled: message-grep resolved NO commits for this slug "
                f"(pre-feature history). Receipt: {receipt_name} "
                f"(provenance: {receipt_prov})."
            )
        else:
            validated_line = (
                f"Backfilled from message-grep history. Receipt: "
                f"{receipt_name} (provenance: {receipt_prov})."
            )
        result = write_provenance(
            repo_root, item_dir, item_id, kind,
            derived["commits"], derived["files"],
            provenance="backfilled", derivation="message-grep",
            date=date, validated_line=validated_line,
        )
        if result.get("ok"):
            backfilled.append(item_id)
        else:
            failures.append(f"{item_id}: {result.get('refused')}")
    out = {
        "ok": not failures,
        "backfilled": backfilled,
        "skipped_existing": skipped_existing,
        "no_commit_matches": no_commit_matches,
        "count": len(backfilled),
    }
    if failures:
        out["failures"] = failures
    return out


def lint_provenance(
    repo_root: Path,
    churn_days: int = _PROVENANCE_CHURN_DAYS,
    churn_threshold: int = _PROVENANCE_CHURN_THRESHOLD,
) -> dict:
    """Maintenance lint (D10) — PURE READ, report only, never mutates.

    Three checks:
      (a) dead_rows — index keys whose path no longer exists in the working
          tree (D5's rename/delete correction prompt: re-link or accept the
          tombstone);
      (b) churn_hotspots — files with >= churn_threshold authored commits in
          the last churn_days days and NO index rows (the prompt to run the
          manual pass over teammate churn). ``docs/**`` paths are excluded —
          decision records/queues churn by design and are not governed code;
      (c) cross_orphans — distillates (with a non-empty commits list) that
          have no index rows, and index rows citing a missing distillate.
    """
    repo_root = Path(repo_root)
    index_path = _provenance_index_path(repo_root)
    index: dict = {}
    index_error: str | None = None
    if index_path.is_file():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                index = loaded
            else:
                index_error = "index is not a JSON object"
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            index_error = f"index unreadable ({exc})"

    # (a) dead rows.
    dead_rows: list[dict] = []
    for key in sorted(index):
        if not (repo_root / key).exists():
            ids = [r.get("id") for r in index[key] if isinstance(r, dict)]
            dead_rows.append({"path": key, "ids": ids})

    # (b) churn hotspots with no rows.
    churn_hotspots: list[dict] = []
    out = _git_capture_lines(
        repo_root,
        ["log", "--no-merges", f"--since={churn_days} days ago",
         "--name-only", "--pretty=format:"],
    )
    if out is not None:
        counts: dict[str, int] = {}
        for ln in out:
            s = ln.strip()
            if s:
                counts[s] = counts.get(s, 0) + 1
        for path, n in sorted(counts.items()):
            if n < churn_threshold:
                continue
            if path in index:
                continue
            if path.startswith("docs/"):
                continue  # decision records / queues churn by design
            if not (repo_root / path).exists():
                continue  # deleted since — not an actionable hotspot
            churn_hotspots.append({"path": path, "commits": n})

    # (c) cross-orphans.
    ids_with_rows: set[tuple[str, str]] = set()
    for rows in index.values():
        if not isinstance(rows, list):
            continue
        for r in rows:
            if isinstance(r, dict):
                ids_with_rows.add((str(r.get("id")), str(r.get("type"))))
    distillates_without_rows: list[str] = []
    known_distillate_ids: set[str] = set()
    dist_globs = [
        ("docs/features", "feature"),
        ("docs/bugs", "bug"),
        ("docs/bugs/_archive", "bug"),
    ]
    for rel_base, kind in dist_globs:
        base = repo_root / rel_base
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            doc = d / "IMPLEMENTED.md"
            meta = parse_sentinel(doc)
            if meta is None or meta.get("kind") != "implemented":
                continue
            known_distillate_ids.add(d.name)
            commits = meta.get("commits")
            has_commits = isinstance(commits, list) and len(commits) > 0
            if has_commits and (d.name, kind) not in ids_with_rows:
                distillates_without_rows.append(
                    str(doc.relative_to(repo_root)).replace("\\", "/"))
    rows_without_distillate: list[dict] = []
    seen_missing: set[tuple[str, str]] = set()
    for key in sorted(index):
        rows = index[key]
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            item_id = str(r.get("id"))
            kind = str(r.get("type"))
            if (item_id, kind) in seen_missing:
                continue
            doc_rel = _provenance_doc_path(repo_root, item_id, kind)
            if not (repo_root / doc_rel).is_file():
                seen_missing.add((item_id, kind))
                rows_without_distillate.append(
                    {"path": key, "id": item_id, "type": kind})
    report = {
        "ok": True,
        "index_present": index_path.is_file(),
        "dead_rows": dead_rows,
        "churn_hotspots": churn_hotspots,
        "cross_orphans": {
            "distillates_without_rows": distillates_without_rows,
            "rows_without_distillate": rows_without_distillate,
        },
        "thresholds": {
            "churn_days": churn_days,
            "churn_threshold": churn_threshold,
        },
    }
    if index_error:
        report["index_error"] = index_error
    return report


def append_auto_readmit_event(
    tool_use_id: str,
    readmitted_sha12: str,
    suffix_head: str,
    item_id: str | None = None,
    now: float | None = None,
) -> bool:
    """Append one ``auto_readmit: true`` event to the deny ledger (JSONL).

    F1b (lazy-pipeline-ergonomics Phase 1): when the validate-deny guard
    auto-readmits a pure trailing-suffix superset of a fresh cycle-class entry
    (instead of denying it), it MUST write an auditable record so the readmit is
    never silent — the retro grader reads the same JSONL stream as the denies.

    The event reuses the deny-ledger shape so a single reader walks both denies
    and auto-readmits, distinguished by the ``auto_readmit`` flag:

        {"ts": <epoch float>, "tool_use_id": <str>, "auto_readmit": true,
         "readmitted_sha12": <12 hex of the MATCHED entry>,
         "suffix_head": <≤200 chars of the appended trailing suffix>,
         "item_id": <str|None>, "acked": true}

    ``acked`` is True because an auto-readmit owes NO hardening debt (the dispatch
    was allowed, not denied) — it must never inflate ``pending_hardening()`` or
    block ``--run-end``.

    Best-effort / fail-open: identical contract to append_deny_ledger_entry — the
    caller wraps this, and it additionally swallows its own write errors and
    returns False rather than raising.

    Args:
        tool_use_id: the auto-readmitted Agent dispatch's tool_use_id.
        readmitted_sha12: first 12 hex chars of the MATCHED entry's prompt_sha256.
        suffix_head: the appended trailing suffix, truncated to the head-char cap.
        item_id: the matched entry's feature/bug id (optional).
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "tool_use_id": tool_use_id,
            "auto_readmit": True,
            "readmitted_sha12": readmitted_sha12,
            "suffix_head": (suffix_head or "")[:_LEDGER_HEAD_CHARS],
            "item_id": item_id,
            # Auto-readmits owe no hardening debt — pre-acked so they never count
            # toward pending_hardening() / --run-end refusal.
            "acked": True,
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate.
        return False


def find_auto_readmit_entry(
    prompt: str,
    now: float | None = None,
) -> dict | None:
    """Find an unconsumed, fresh, ``class == "cycle"`` registry entry whose stored
    normalized prompt text is a PURE TRAILING-SUFFIX PREFIX of *prompt*.

    F1b (lazy-pipeline-ergonomics Phase 1): the common validate-deny accident is
    an ORCHESTRATOR NOTE appended to a script-emitted ``cycle_prompt``.  The full
    hash misses (lookup_emission → None), so the guard would deny.  This helper
    lets the guard instead AUTO-READMIT the dispatch when the only difference is a
    trailing suffix appended to a sanctioned cycle prompt.

    Match criteria (ALL must hold):
      - the entry is unconsumed AND within REGISTRY_ENTRY_TTL_SECONDS AND
        (when a run marker exists) emitted at/after the run's started_at — the
        SAME freshness gate as lookup_emission, so a stale entry never readmits;
      - the entry's ``class`` is exactly ``"cycle"`` — NEVER ``"hardening"``
        (the depth-1 cap stays intact) and never any other ad-hoc class;
      - ``dispatched_norm.startswith(entry_norm)`` after identical
        normalize_prompt_for_hash normalization, with a NON-EMPTY remainder
        (a pure suffix superset — an exact equal would have hit lookup_emission,
        and an in-body edit is not a prefix so it never matches).

    Returns the matched entry dict (the FIRST qualifying entry in insertion
    order), or None when nothing qualifies.  Read-only — does NOT consume; the
    caller consumes the nonce on a successful readmit.

    Args:
        prompt: the dispatched prompt text (normalized before comparison).
        now: epoch float for the TTL/run-start gate (injectable for tests).

    Returns:
        The matching entry dict, or None.
    """
    from ._monolith import REGISTRY_ENTRY_TTL_SECONDS, read_run_marker  # Phase-5 re-point (marker plane still monolith-resident)
    from ._monolith import normalize_prompt_for_hash  # Phase-4 WU-3 re-point (dispatch/registry plane)
    if now is None:
        now = time.time()
    dispatched_norm = normalize_prompt_for_hash(prompt)

    # Compute the run-start epoch the same way lookup_emission does so the
    # freshness gate is identical (entries predating the current run never
    # readmit).
    marker = read_run_marker(now=now)
    run_started_epoch: float | None = None
    if marker is not None:
        started_at_str = marker.get("started_at", "")
        try:
            started_dt = datetime.datetime.strptime(
                started_at_str, "%Y-%m-%dT%H:%M:%SZ"
            )
            run_started_epoch = (
                started_dt - datetime.datetime(1970, 1, 1)
            ).total_seconds()
        except (ValueError, TypeError):
            run_started_epoch = None

    for entry in _load_registry()["entries"]:
        # Hard class exclusion FIRST — never readmit anything but a cycle entry.
        if entry.get("class") != "cycle":
            continue
        if entry.get("consumed", True):
            continue
        entry_norm = entry.get("prompt_norm")
        # Legacy entries (registered before F1b) have no prompt_norm — skip them
        # (they can still be denied; auto-readmit just doesn't apply).
        if not isinstance(entry_norm, str) or not entry_norm:
            continue
        emitted_at = entry.get("emitted_at", 0.0)
        if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
            continue
        if run_started_epoch is not None and emitted_at < run_started_epoch:
            continue
        # Pure trailing-suffix superset: the dispatched prompt must START WITH the
        # registered prompt AND add a non-empty trailing remainder.  An exact
        # match (no remainder) would already have hit lookup_emission, and an
        # in-body edit is not a prefix so it never qualifies.
        if dispatched_norm.startswith(entry_norm) and len(dispatched_norm) > len(entry_norm):
            return entry
    return None


def find_transcription_slip_entry(
    prompt: str,
    *,
    now: float | None = None,
    threshold: float = 0.97,
) -> dict | None:
    """F2c (lazy-validation-readiness Phase 2): find a registry entry that the
    dispatched *prompt* is a TRANSCRIPTION SLIP of.

    A transcription slip is an otherwise-faithful reproduction of a script-emitted
    prompt that was mangled by cosmetic editing (e.g. one word retyped, an NBSP
    introduced) in a way that F2b's dash/quote/NBSP folding does NOT cover.  The
    high similarity ratio (>= *threshold*, default 0.97) means the orchestrator was
    clearly trying to dispatch a KNOWN registered prompt — the body is almost
    identical — but the bytes differ just enough to miss the hash gate.

    When this function returns an entry, the corrective action is always:
      re-run the Step 1a probe and dispatch the registered ``cycle_prompt``
      **verbatim or by-reference** — do NOT hand-edit the prompt again.

    A genuinely unregistered / hand-composed prompt has NO close registered entry
    (the difflib ratio is low) and falls through to the existing corrective deny
    with hardening debt (the no-match case returns None, so the caller continues to
    ``_deny_and_ledger``).

    Scope (F2c applies ONLY here):
      - Only applies when a valid run marker is present (this is a marked-run
        concern; if no marker, return None immediately — fail-safe for unmarked
        runs and ``--test`` baselines which must remain byte-identical).
      - Scans only entries emitted in the CURRENT run (emitted_at >= run-start
        epoch from ``read_run_marker``), mirroring ``lookup_emission``'s run-start
        gate, so stale cross-run entries cannot mis-classify a real gap.
      - EXCLUDES ``class == "hardening"`` entries unconditionally — the depth-1
        hardening cap must stay fully intact; a slip against a hardening-class
        entry must still go to ``_deny_and_ledger`` (which writes hardening debt).
      - Uses ``difflib.SequenceMatcher`` against the NFC-normalized text (stored
        as ``prompt_norm`` on the entry; falls back to normalizing a raw prompt
        field if ``prompt_norm`` is missing; skips the entry if neither is
        available).

    FAIL-SAFE / FAIL-OPEN contract:
      - Read-only; does NOT consume any nonce or write any state.
      - Any exception is caught and returns None so the caller falls through to
        the existing deny path — a slip-check error must NEVER turn a deny into
        a spurious allow and must NEVER cause an unhandled exception in the guard.

    Args:
        prompt: the dispatched prompt text (normalized before comparison).
        now: epoch float for the TTL / run-start gate (injectable for tests;
             defaults to time.time()).
        threshold: minimum SequenceMatcher ratio to classify as a slip (default
                   0.97 — very high so only near-verbatim copies qualify).

    Returns:
        The highest-ratio entry whose ratio >= *threshold*, or None.
    """
    # Fail-safe: all errors return None (never raise from a guard sub-path).
    from ._monolith import REGISTRY_ENTRY_TTL_SECONDS, read_run_marker  # Phase-5 re-point (marker plane still monolith-resident)
    from ._monolith import normalize_prompt_for_hash  # Phase-4 WU-3 re-point (dispatch/registry plane)
    try:
        if now is None:
            now = time.time()

        # Marker-gated: F2c is a marked-run concern.  No marker → not applicable.
        marker = read_run_marker(now=now)
        if marker is None:
            return None

        # Compute the run-start epoch (same logic as lookup_emission).
        run_started_epoch: float | None = None
        started_at_str = marker.get("started_at", "")
        try:
            started_dt = datetime.datetime.strptime(started_at_str, "%Y-%m-%dT%H:%M:%SZ")
            run_started_epoch = (
                started_dt - datetime.datetime(1970, 1, 1)
            ).total_seconds()
        except (ValueError, TypeError):
            run_started_epoch = None

        # Normalize the dispatched prompt for comparison.
        dispatched_norm = normalize_prompt_for_hash(prompt)

        import difflib as _difflib  # stdlib; imported lazily to keep startup cost low

        best_entry: dict | None = None
        best_ratio: float = 0.0

        for entry in _load_registry().get("entries", []):
            try:
                # Hard class exclusion: never classify a hardening-class entry as a
                # slip — the depth-1 cap must stay intact regardless.
                if entry.get("class") == "hardening":
                    continue

                # Run-start gate: only consider entries from the CURRENT run.
                emitted_at = entry.get("emitted_at", 0.0)
                if run_started_epoch is not None and emitted_at < run_started_epoch:
                    continue

                # TTL gate: entries beyond the TTL window are never candidates.
                if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
                    continue

                # Consumed entries can still be slip candidates — we only want to
                # classify the DENY path (the slip did not get an ALLOW), so the
                # relevant registered entries may or may not be consumed.
                # (If the exact-sha match had succeeded, the guard would already
                # have allowed via lookup_emission or _find_entry_by_sha, so we
                # only reach here when the sha did NOT match.)

                # Retrieve normalized form for comparison.
                entry_norm = entry.get("prompt_norm")
                if not isinstance(entry_norm, str) or not entry_norm:
                    # Legacy entry without prompt_norm — skip (no text to compare).
                    continue

                # SequenceMatcher similarity ratio.
                ratio = _difflib.SequenceMatcher(
                    None, dispatched_norm, entry_norm
                ).ratio()
                if ratio >= threshold and ratio > best_ratio:
                    best_ratio = ratio
                    best_entry = entry
            except Exception:  # noqa: BLE001
                # Skip a single bad entry — don't abort the scan.
                continue

        return best_entry

    except Exception:  # noqa: BLE001
        # Fail-open: any outer exception → return None so the caller falls through
        # to the existing deny path.  Never raise from a guard sub-path.
        return None


def read_deny_ledger() -> list[dict]:
    """Read all deny-ledger entries, skipping any unparseable lines.

    A missing ledger file → empty list (no denials yet).  A corrupt line (e.g.
    a torn final append) is skipped rather than aborting the whole read.

    Returns:
        The list of parsed entry dicts in file (FIFO insertion) order.
    """
    ledger_path = claude_state_dir(create=False) / _DENY_LEDGER_FILENAME
    if not ledger_path.exists():
        return []
    entries: list[dict] = []
    try:
        raw = ledger_path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            # Skip an unparseable line — a single torn append must not brick
            # the whole ledger.
            continue
        if isinstance(obj, dict):
            entries.append(obj)
    return entries


def pending_hardening(*, current_run_only: bool = True) -> int:
    """Return the count of unacked deny-ledger entries (the routed hardening debt).

    An entry is "pending" when its ``acked`` field is falsy.  A missing or empty
    ledger → 0.

    ``current_run_only`` (Residual gap B,
    loop-detector-false-positives-probes-and-cross-run-state; default True): when
    a LIVE run marker exists, count only unacked entries whose ``run_started_at``
    matches the live marker's ``started_at`` — i.e. debt this run actually owes.
    An unacked entry stamped with a DIFFERENT run's identity (or no identity at
    all — a legacy/pre-fix entry) belongs to a run that already ended (a crash
    left it undrained); it remains in the ledger for retro/incident mining but no
    longer forces the NEXT run to dispatch a hardening round for a denial it
    never saw (symptom 4). When NO live marker exists, there is no run identity
    to scope against, so this returns the unfiltered total — byte-identical to
    the pre-fix behavior for every no-marker caller/test. Pass
    ``current_run_only=False`` for the informational/retro total.
    """
    entries = [e for e in read_deny_ledger() if not e.get("acked", False)]
    if not current_run_only:
        return len(entries)
    current_started = _raw_marker_started_at()
    if current_started is None:
        return len(entries)
    return sum(1 for e in entries if e.get("run_started_at") == current_started)


def pending_denial_reasons(*, current_run_only: bool = True) -> list[str]:
    """Return the ``reason_head`` strings of all unacked deny-ledger entries, in
    FIFO order.  Used to surface ``pending_denials`` in the marker-gated probe
    enrichment so the orchestrator sees WHAT it still owes a hardening round for.

    ``current_run_only`` mirrors ``pending_hardening`` — see its docstring for the
    Residual-gap-B run-scoping contract.
    """
    entries = [e for e in read_deny_ledger() if not e.get("acked", False)]
    if current_run_only:
        current_started = _raw_marker_started_at()
        if current_started is not None:
            entries = [e for e in entries if e.get("run_started_at") == current_started]
    return [e.get("reason_head", "") for e in entries]


def prior_run_pending_hardening() -> int:
    """Return the count of unacked deny-ledger entries that belong to a run OTHER
    than the live one (Residual gap B — the informational T6 counterpart to
    ``pending_hardening()``'s now run-scoped mandatory debt).

    ``pending_hardening()`` (default ``current_run_only=True``) excludes these
    from the MANDATORY hardening-withholding count; this helper surfaces them
    separately so the orchestrator can report "N denial(s) from a prior/crashed
    run remain unacked" as an informational line, never a blocking one. When no
    live marker exists, returns 0 (there is no "other run" to compare against —
    ``pending_hardening()`` itself falls back to the unfiltered total in that
    case, so nothing is silently hidden).
    """
    current_started = _raw_marker_started_at()
    if current_started is None:
        return 0
    return sum(
        1 for e in read_deny_ledger()
        if not e.get("acked", False) and e.get("run_started_at") != current_started
    )


# ---------------------------------------------------------------------------
# efficacy-future-check-unenforced-orchestrator-prose (D1) — the end-of-run
# efficacy-flush breadcrumb + gate.
#
# The self-improving-harness observability loop (efficacy-eval.py review,
# efficacy-eval.py --canary, incident-scan.py — the "trio") is designed to run
# ONCE per run at the §1c.6 end-of-run flush, BEFORE --run-end.  That invocation
# was orchestrator PROSE only — nothing enforced it, and it WAS skipped at a real
# checkpoint --run-end.  This breadcrumb gate MIRRORS the unacked-hardening gate:
# each trio member drops a RUN-SCOPED breadcrumb when invoked (even on a clean
# no-op), and --run-end REFUSES (exit 1, marker kept) unless the breadcrumb is
# present OR --efficacy-skip-authorized retro-grades a deliberate skip.  The trio
# + the commit stay orchestrator-owned (D1, over run-end-invokes-the-trio) so the
# run's telemetry context is intact when the scripts read it and the terminal
# commit ordering is preserved.
#
# RUN-SCOPING: the breadcrumb records the current run marker's ``started_at``
# (the run identity used throughout the telemetry ledger — see
# efficacy-eval.py).  --run-end matches the breadcrumb's ``run_started_at``
# against the LIVE marker, so a stale breadcrumb left by a crashed prior run
# (different started_at) never satisfies the next run's gate.
# ---------------------------------------------------------------------------

_EFFICACY_BREADCRUMB_FILENAME = "lazy-efficacy-flush.json"


def _raw_marker_started_at() -> str | None:
    """RAW, NON-destructive read of the live run marker's ``started_at`` (the run
    identity), or None when no well-formed marker exists.

    Unlike ``read_run_marker`` this NEVER deletes a stale/corrupt marker and NEVER
    applies staleness or session gating — the efficacy gate reads it from the
    --run-end path (which must not double-delete) and the trio scripts drop the
    breadcrumb from any session.  A degraded/absent marker yields None.
    """
    try:
        marker_path = claude_state_dir(create=False) / _MARKER_FILENAME
        if not marker_path.exists():
            return None
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if not isinstance(marker, dict):
            return None
        started_at = marker.get("started_at")
        return started_at if isinstance(started_at, str) and started_at else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _run_marker_state_dir(*, now: float | None = None) -> "tuple[Path, str] | None":
    """Resolve the LIVE run marker's state dir: the active repo's dir when it
    holds a live marker, else the most-recent live marker found in a keyed
    sibling subdir of the state base (interventions-telemetry-repo-scope-split-brain
    WU-2).

    The active (flat) state dir can hold NO marker at all when the run
    originated for a DIFFERENT repo than the one currently bound as active —
    the same split-brain ``_originating_telemetry_paths`` was built to close,
    whose scan approach this helper reuses (state base = ``LAZY_STATE_DIR`` if
    set else ``~/.claude/state``; enumerate subdirs; RAW-read each marker;
    age-filter via ``_MARKER_STALE_SECONDS``).

    RAW, NON-destructive reads only (never ``read_run_marker``, which deletes
    stale markers); no state-dir creation on this read path. Fully fail-open —
    any error yields None.

    Returns:
        ``(state_dir, started_at)`` for the most-recent live marker found, or
        None when no live marker exists anywhere.
    """
    from ._monolith import _MARKER_STALE_SECONDS  # Phase-5 re-point (marker plane still monolith-resident)
    if now is None:
        now = time.time()
    try:
        active = claude_state_dir(create=False)
        try:
            marker_path = active / _MARKER_FILENAME
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            if isinstance(marker, dict):
                started_at_str = marker.get("started_at", "")
                started_dt = datetime.datetime.strptime(
                    started_at_str, "%Y-%m-%dT%H:%M:%SZ"
                )
                started_epoch = (
                    started_dt - datetime.datetime(1970, 1, 1)
                ).total_seconds()
                if now - started_epoch <= _MARKER_STALE_SECONDS:
                    return (active, started_at_str)
        except Exception:  # noqa: BLE001 — fall through to the sibling scan
            pass

        override = os.environ.get("LAZY_STATE_DIR")
        base = Path(override) if override else (Path.home() / ".claude" / "state")
        if not base.is_dir():
            return None
        best_dir: Path | None = None
        best_started: float | None = None
        best_started_str: str | None = None
        for d in sorted(base.iterdir(), key=lambda p: p.name):
            if not d.is_dir():
                continue
            try:
                marker_path = d / _MARKER_FILENAME
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                if not isinstance(marker, dict):
                    continue
                started_at_str = marker.get("started_at", "")
                started_dt = datetime.datetime.strptime(
                    started_at_str, "%Y-%m-%dT%H:%M:%SZ"
                )
                started_epoch = (
                    started_dt - datetime.datetime(1970, 1, 1)
                ).total_seconds()
                if now - started_epoch > _MARKER_STALE_SECONDS:
                    continue  # stale
            except Exception:  # noqa: BLE001
                continue  # unparseable marker in this subdir — skip it
            if best_started is None or started_epoch > best_started:
                best_started = started_epoch
                best_dir = d
                best_started_str = started_at_str
        if best_dir is None or best_started_str is None:
            return None
        return (best_dir, best_started_str)
    except Exception:  # noqa: BLE001
        return None


def _repo_is_interventions_bearing(repo_root) -> bool:
    """True iff ``repo_root`` opts into interventions capture: the
    ``docs/features/queue.json`` ``interventions: true`` flag, OR a
    ``docs/interventions/*.md`` hypothesis-ledger file other than
    ``CLAUDE.md``/``README.md``.

    Read-only, defensive: any error (missing dir, malformed queue.json, a
    permission error) yields False rather than raising — a scope-coverage
    breadcrumb must never wedge on a bad repo path.
    """
    try:
        root = Path(repo_root)
        if _interventions_queue_flag(root):
            return True
        interventions_dir = root / "docs" / "interventions"
        if interventions_dir.is_dir():
            for p in interventions_dir.glob("*.md"):
                if p.name not in ("CLAUDE.md", "README.md"):
                    return True
        return False
    except Exception:  # noqa: BLE001
        return False


def drop_efficacy_breadcrumb(
    covered_repo_root: str | None = None, *, now: float | None = None
) -> bool:
    """Drop the run-scoped "efficacy flush ran this run" breadcrumb that the
    --run-end gate checks (efficacy-future-check-unenforced-orchestrator-prose).

    Called by EACH trio member (efficacy-eval.py review + --canary, incident-scan)
    on a real (non-dry-run) invocation, EVEN on a clean no-op — running the flush
    is what discharges the gate.  MARKER-GATED (no live run marker anywhere —
    neither the active repo's state dir nor any keyed sibling — → no write,
    return False) and FAIL-OPEN (any error → False; the flush must never wedge
    on a breadcrumb write).

    interventions-telemetry-repo-scope-split-brain WU-2: the breadcrumb now
    ALSO records covered repo-scope(s) — which repo(s) this run's flush(es)
    actually covered (``covered_scopes``, a sorted list of ``repo_key``s) and
    whether ANY covered scope opts into interventions capture
    (``interventions_covered``) — so a flush that never covers the
    interventions-bearing repo can be told apart from one that genuinely did.
    The breadcrumb is written into the LIVE run marker's OWN state dir (see
    ``_run_marker_state_dir`` — this may differ from the active repo's dir),
    read-merged (accumulated) across calls sharing the SAME ``run_started_at``.

    Args:
        covered_repo_root: the repo whose scope this call covers. Defaults to
            the active repo (back-compat for the legacy no-arg call — e.g.
            incident-scan.py, which binds the active repo before calling).
        now: epoch float for the ``ts`` field (injectable for hermetic tests).

    Returns:
        True when the breadcrumb was written; False when marker-gated or on any
        write failure.
    """
    if now is None:
        now = time.time()
    loc = _run_marker_state_dir(now=now)
    if loc is None:
        return False
    try:
        run_dir, started_at = loc
        covered_root = covered_repo_root
        if covered_root is None:
            # Prefer the LIVE marker's OWN recorded repo_root — the run's
            # authoritative scope — over the process-global active_repo_root()
            # cwd fallback, which can diverge from the marker's repo when the
            # caller never bound it via set_active_repo_root/--repo-root
            # (interventions-telemetry-repo-scope-split-brain: a divergent cwd
            # fallback must never be mistaken for the run's actual scope).
            try:
                marker = json.loads(
                    (run_dir / _MARKER_FILENAME).read_text(encoding="utf-8")
                )
                if isinstance(marker, dict) and marker.get("repo_root"):
                    covered_root = marker["repo_root"]
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            if covered_root is None:
                covered_root = active_repo_root()
        covered_key = repo_key(str(covered_root))
        interventions_bearing = _repo_is_interventions_bearing(covered_root)

        crumb_path = run_dir / _EFFICACY_BREADCRUMB_FILENAME
        covered: set = set()
        interv = False
        try:
            if crumb_path.exists():
                prev = json.loads(crumb_path.read_text(encoding="utf-8"))
                if isinstance(prev, dict) and prev.get("run_started_at") == started_at:
                    covered = set(prev.get("covered_scopes") or [])
                    interv = bool(prev.get("interventions_covered"))
        except (OSError, ValueError, json.JSONDecodeError):
            pass

        covered.add(covered_key)
        interv = interv or interventions_bearing

        body = json.dumps({
            "run_started_at": started_at,
            "ts": now,
            "covered_scopes": sorted(covered),
            "interventions_covered": interv,
        }) + "\n"
        _atomic_write(crumb_path, body)
        return True
    except Exception:  # noqa: BLE001 — fail-open: a breadcrumb write never wedges
        return False


def efficacy_breadcrumb_present(now: float | None = None) -> bool:
    """Return True iff the end-of-run efficacy flush ran for the CURRENT run
    AND covered an interventions-bearing scope — i.e. a breadcrumb exists whose
    ``run_started_at`` matches the LIVE run marker's ``started_at`` (run-scoped:
    a stale breadcrumb from a prior run never satisfies the gate) AND whose
    ``interventions_covered`` flag is True (coverage-scoped: a flush that only
    ever touched non-interventions-bearing scopes never satisfies the gate —
    closing the interventions-telemetry-repo-scope-split-brain COVERAGE hole;
    the sibling gate that inspects the trio's INVOCATION verified only that the
    flush ran, never that it ran against a scope where intervention records
    actually live).

    Returns True when there is NO live run marker — the gate is then MOOT (a
    --run-end with no marker is an idempotent no-op that must not be refused).
    Any read/parse error → False (fail-safe: a degraded breadcrumb does not
    satisfy the gate, exactly as a degraded deny-ledger never clears hardening
    debt).
    """
    started_at = _raw_marker_started_at()
    if started_at is None:
        return True  # no live run to have flushed — gate is moot
    try:
        crumb_path = claude_state_dir(create=False) / _EFFICACY_BREADCRUMB_FILENAME
        if not crumb_path.exists():
            return False
        crumb = json.loads(crumb_path.read_text(encoding="utf-8"))
        if not isinstance(crumb, dict):
            return False
        if crumb.get("run_started_at") != started_at:
            return False
        return crumb.get("interventions_covered") is True
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def clear_efficacy_breadcrumb() -> None:
    """Remove the efficacy-flush breadcrumb (best-effort).  Called by --run-end
    AFTER the gate passes and the marker is deleted, so the next run starts clean
    (run-scoping already prevents a stale breadcrumb from satisfying a later gate;
    this is tidy-up, not correctness)."""
    try:
        crumb_path = claude_state_dir(create=False) / _EFFICACY_BREADCRUMB_FILENAME
        if crumb_path.exists():
            crumb_path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# harness-telemetry-ledger — the telemetry ledger (sibling of the deny ledger).
#
# An append-only JSONL ledger of the pipeline's deterministic chokepoint events
# (run/cycle brackets, dispatches, halts, gate/containment refusals, pseudo-skill
# completions, sentinel resolutions — the D4-B vocabulary), written by BOTH state
# scripts through this ONE shared emitter (D2-A: parity by construction) into the
# per-repo keyed state dir beside lazy-deny-ledger.jsonl.
#
# Contract (clones the deny-ledger precedent wholesale):
#   - MARKER-GATED (D3-A): no live run marker → no write, no file, return False.
#     Bare probes and unmarked interactive invocations stay side-effect-free.
#     The marker read here is RAW and NON-DESTRUCTIVE (never read_run_marker,
#     whose stale path DELETES the marker) — emission also fires from exit-3
#     refusal paths that promise ZERO side effects.
#   - FAIL-OPEN (D2-A): plain `open(..., "a")` append (never _atomic_write — an
#     atomic rewrite adds a read-modify-write race on an append-only file whose
#     torn final line the reader already tolerates); every exception is
#     swallowed → False. The emitter NEVER calls _diag — a failed append must
#     not perturb the diagnostics[] surface of the op it rides on.
#   - RAW EVENTS ONLY (D9-A): metrics are derived reader-side
#     (pipeline_visualizer/trends.py); nothing here aggregates.
#   - ROTATION (D6-B): at emit time an over-cap active file rotates to `.1`
#     (shifting `.1`→`.2` … and dropping the oldest beyond
#     _TELEMETRY_ROTATED_SEGMENTS); a rotation failure degrades to plain append.
# ---------------------------------------------------------------------------

_TELEMETRY_LEDGER_FILENAME = "lazy-telemetry.jsonl"
_TELEMETRY_SCHEMA_VERSION = 1
_TELEMETRY_ROTATE_BYTES = 10 * 1024 * 1024  # D6-B: 10 MB active-file cap
_TELEMETRY_ROTATED_SEGMENTS = 4             # D6-B: .1 (newest) … .4 (oldest)

# D4-B: the dispatch terminal_reasons that ALSO emit a `halt` event (the
# halt-dwell start marker; the matching `sentinel-resolved` ends the dwell).
TELEMETRY_HALT_TERMINAL_REASONS: frozenset[str] = frozenset({
    "blocked",
    "needs-input",
    "needs-spec-input",
    "needs-research",
    "completion-unverified",
    "blocked-misnamed",
})


def _telemetry_run_marker(now: float | None = None) -> dict | None:
    """RAW, NON-destructive run-marker read for telemetry gating (D3-A).

    Returns the marker dict when a well-formed, age-fresh (≤24h) marker exists;
    otherwise None. Unlike ``read_run_marker`` this NEVER deletes a stale or
    corrupt marker and NEVER applies session-id gating — the emitter is called
    from refusal paths whose contract is "zero side effects", and from any
    session that runs a marker-gated op (the run identity is the marker's, not
    the caller's). Mirrors ``refuse_run_start_clobber``'s own raw read.

    Args:
        now: epoch float for the age check (injectable for hermetic tests).
    """
    from ._monolith import _MARKER_STALE_SECONDS  # Phase-5 re-point (marker plane still monolith-resident)
    if now is None:
        now = time.time()
    try:
        marker_path = claude_state_dir(create=False) / _MARKER_FILENAME
        if not marker_path.exists():
            return None
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if not isinstance(marker, dict):
            return None
        started_at_str = marker.get("started_at", "")
        started_dt = datetime.datetime.strptime(
            started_at_str, "%Y-%m-%dT%H:%M:%SZ"
        )
        started_epoch = (
            started_dt - datetime.datetime(1970, 1, 1)
        ).total_seconds()
        if now - started_epoch > _MARKER_STALE_SECONDS:
            return None  # age-stale → gated; deletion is read_run_marker's job
        return marker
    except Exception:  # noqa: BLE001
        # Fail-open gate: any read/parse error means "no live run" → no emit.
        return None


def _rotate_telemetry_segments(ledger_path: Path) -> None:
    """D6-B size-based rollover, called at emit time BEFORE the append.

    When the active file is at/over ``_TELEMETRY_ROTATE_BYTES``: drop the oldest
    segment (``.N``), shift ``.i`` → ``.i+1``, and rename the active file to
    ``.1``. Best-effort — any failure returns silently so the caller degrades to
    a plain append on the (over-cap) active file rather than losing the event.
    """
    try:
        if not ledger_path.exists():
            return
        if ledger_path.stat().st_size < _TELEMETRY_ROTATE_BYTES:
            return
        oldest = Path(f"{ledger_path}.{_TELEMETRY_ROTATED_SEGMENTS}")
        if oldest.exists():
            oldest.unlink()
        for i in range(_TELEMETRY_ROTATED_SEGMENTS - 1, 0, -1):
            src = Path(f"{ledger_path}.{i}")
            if src.exists():
                src.rename(Path(f"{ledger_path}.{i + 1}"))
        ledger_path.rename(Path(f"{ledger_path}.1"))
    except OSError:
        # Degrade to plain append on the over-cap active file — never raise.
        return


def append_telemetry_event(
    event: str,
    *,
    item_id: str | None = None,
    data: dict | None = None,
    now: float | None = None,
) -> bool:
    """Append one telemetry event to the telemetry ledger (JSONL), best-effort.

    The ONE shared writer both state scripts (and the shared exit-3 refusal
    helpers) call at their CLI write-path chokepoints (D2-A / D3-A). Envelope
    (D1-A), one compact JSON object per line:

        {"v": 1, "ts": <epoch float>, "run_id": <marker started_at>,
         "pipeline": "feature"|"bug", "event": "<type>",
         "item_id": <str|None>, "data": {…}}

    MARKER-GATED: no live (age-fresh) run marker → nothing is written and False
    is returned — bare probes / unmarked interactive invocations never create
    the ledger. FAIL-OPEN: swallows every exception and returns False; callers
    never branch on the return value (telemetry can never block the pipeline).
    The ledger line is observability, not state — a refused op that emits one
    still has zero STATE side effects.

    Args:
        event: the D4-B event type (e.g. "run-start", "dispatch", "gate-refusal").
        item_id: the feature/bug id the event concerns (None for run-level events).
        data: small per-event payload map (untyped by design — D1-A).
        now: epoch float for ts + the marker age gate (injectable for tests).

    Returns:
        True iff a line was appended; False when gated or on any write failure.
    """
    if now is None:
        now = time.time()
    try:
        marker = _telemetry_run_marker(now=now)
        if marker is None:
            return False  # D3-A: no live run → no emit
        entry = {
            "v": _TELEMETRY_SCHEMA_VERSION,
            "ts": now,
            "run_id": marker.get("started_at"),
            "pipeline": marker.get("pipeline"),
            "event": event,
            "item_id": item_id,
            "data": data or {},
        }
        ledger_path = claude_state_dir() / _TELEMETRY_LEDGER_FILENAME
        _rotate_telemetry_segments(ledger_path)
        # Plain append (not _atomic_write) — deny-ledger precedent: append-only
        # file, torn final line tolerated by the reader.
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a telemetry write must never propagate.
        return False


def read_telemetry_events(
    paths: "list[Path] | None" = None,
    with_provenance: bool = False,
) -> list[dict]:
    """Read telemetry events, skipping unparseable lines and unknown ``v``.

    Default path set: the rotated segments OLDEST-first (``.4`` → ``.1``) then
    the active file, so the returned list is in chronological append order
    across the whole retained window (D6-B). A missing file / unreadable path /
    torn line / non-dict line / line whose ``v`` is not a known schema version
    is skipped, never fatal (D1-A: tolerate what you don't understand).

    Args:
        paths: explicit files to read (e.g. committed cloud segments); None →
            the state-dir default set.
        with_provenance: when True, stamp ``_source`` (str path) and ``_line``
            (1-based physical line number) onto each event for the retro's
            per-figure ledger citations (D8). Default False keeps the envelope
            pure for aggregation.

    Returns:
        The list of parsed event dicts in file/line order.
    """
    if paths is None:
        base = claude_state_dir(create=False)
        active = base / _TELEMETRY_LEDGER_FILENAME
        paths = [
            Path(f"{active}.{i}")
            for i in range(_TELEMETRY_ROTATED_SEGMENTS, 0, -1)
        ] + [active]
    events: list[dict] = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for lineno, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue  # torn append — skip, never brick the ledger
            if not isinstance(obj, dict):
                continue
            if obj.get("v") != _TELEMETRY_SCHEMA_VERSION:
                continue  # unknown schema version — a future writer's line
            if with_provenance:
                obj = dict(obj)
                obj["_source"] = str(p)
                obj["_line"] = lineno
            events.append(obj)
    return events


def flush_cloud_telemetry_segment(
    repo_root: Path,
    *,
    now: float | None = None,
) -> dict | None:
    """D5-B cloud run-end flush: persist the live cloud run's ledger segment
    into the repo so it survives the container.

    Called by both scripts' ``--run-end`` handlers AFTER the run-end emission
    and BEFORE ``delete_run_marker`` (the marker supplies the run identity).
    Gated on a live marker with ``cloud: true`` — workstation runs return None
    untouched. Filters the state-dir ledger to lines whose ``run_id`` equals
    the marker's ``started_at`` and writes them (one-shot, via _atomic_write —
    this is a segment REWRITE, not an append-only file) to:

        <repo_root>/docs/telemetry/cloud/<run_id with colons stripped>.jsonl

    The colon-strip keeps the committed filename legal on a Windows checkout
    (run_id is ``2026-07-04T09:12:03Z``); each line's ``run_id`` FIELD is
    unchanged, so aggregation keys on content, never the filename. Zero
    matching events → None (nothing to persist; pre-feature byte-identity).
    Fail-open: any error returns None and never blocks the run-end.

    Args:
        repo_root: the repo the segment lands in (rides the final cloud push).
        now: epoch float for the marker age gate (injectable for tests).

    Returns:
        {"path": <str>, "events": <int>} when a segment was written, else None.
    """
    try:
        marker = _telemetry_run_marker(now=now)
        if marker is None or not marker.get("cloud"):
            return None
        run_id = marker.get("started_at")
        if not run_id:
            return None
        lines = [
            e for e in read_telemetry_events() if e.get("run_id") == run_id
        ]
        if not lines:
            return None
        seg_dir = Path(repo_root) / "docs" / "telemetry" / "cloud"
        seg_dir.mkdir(parents=True, exist_ok=True)
        seg_path = seg_dir / (run_id.replace(":", "") + ".jsonl")
        _atomic_write(
            seg_path, "\n".join(json.dumps(e) for e in lines) + "\n"
        )
        return {"path": str(seg_path), "events": len(lines)}
    except Exception:  # noqa: BLE001
        # Fail-open: the flush must never block --run-end.
        return None


# ---------------------------------------------------------------------------
# intervention-efficacy-tracking — the hypothesis ledger (capture half).
#
# Every shipped harness change is an implicit hypothesis ("this change will
# move friction signal X in direction D"). Capture writes a deterministic,
# script-owned intervention record (a frontmatter-sentinel markdown file at
# docs/interventions/<id>.md — committed, durable, GitHub-mobile readable;
# D4-A central residency) at the completion chokepoint:
#
#   * apply_pseudo __mark_complete__ / __mark_fixed__ — ONE shared call site,
#     so both pipelines inherit capture by construction (D1-A). Eligibility:
#     a top-level `"interventions": true` in docs/features/queue.json (the
#     `"autodiscover": true` precedent — only claude-config sets it) OR a
#     present `## Intervention Hypothesis` SPEC block. Otherwise the
#     completion is byte-identical to pre-feature (no keys, no file).
#   * the orchestrator-only `--record-intervention` CLI on BOTH state scripts
#     (the /harden-harness round path, manual capture, and the D9 opt-in
#     backfill — `--shipped-commit`/`--shipped-date` stamp
#     `provenance: backfilled`, mirroring `backfilled-unverified` honesty).
#
# The baseline is FROZEN into the record at capture time (D3): the raw
# telemetry ledger is untracked + rotation-eligible, so verdicts must never
# depend on raw-event retention. Missing/undeclared inputs degrade honestly
# (`unavailable` / `not-computable` / `target_signal: undeclared`) — capture
# NEVER errors a completion (D2-A: fail-open to a warnings entry).
#
# The evaluation half lives OFF the state-script compute path in
# user/scripts/efficacy-eval.py (the toolify-miner/lazy-queue-doc precedent),
# which re-reads these records via parse_sentinel and re-writes them through
# the same _render_intervention_record serializer (diff-stable field order).
# ---------------------------------------------------------------------------

# D5-A declared defaults — one block, per-record overridable via the
# `## Intervention Hypothesis` block (baseline_runs / review_after_runs /
# min_sample / band_pct). Starting points to be tuned by this feature's own
# ledger, not laws.
INTERVENTION_BASELINE_RUNS = 20
INTERVENTION_REVIEW_AFTER_RUNS = 20
INTERVENTION_MIN_SAMPLE = 5
INTERVENTION_BAND_PCT = 20

_INTERVENTIONS_DIRNAME = "interventions"

_INTERVENTION_HYPOTHESIS_HEADING_RE = re.compile(
    r"(?mi)^##\s+Intervention Hypothesis\s*$"
)
_INTERVENTION_FIELD_RE = re.compile(r"^[-*]\s*([a-z_]+)\s*:\s*(.+?)\s*$")
# The three signal_independence enum heads (D3); the justification sentence
# rides in `signal_independence_note` and the record body.
_INTERVENTION_INDEPENDENCE_ENUM = ("independent", "self-emitted", "mixed")
_INTERVENTION_INT_FIELDS = (
    "review_after_runs", "baseline_runs", "min_sample", "band_pct",
    "canary_window_runs",
)


def parse_intervention_hypothesis(spec_text: str) -> dict | None:
    """Parse a SPEC's ``## Intervention Hypothesis`` block (D2-A).

    Returns a dict of the declared fields, or None when the heading is absent
    (the degrade-on-absence discriminator — an absent block still captures,
    as ``target_signal: undeclared``). Recognized list-item fields:
    ``target_signal``, ``expected_direction``, ``signal_independence`` (enum
    head extracted to the field; the full raw value — including a wrapped
    justification continuation line — lands in ``signal_independence_note``),
    ``review_after_runs`` and the optional D5 overrides ``baseline_runs`` /
    ``min_sample`` / ``band_pct`` (ints; a malformed int is OMITTED, never
    raised — capture must never break a completion).
    """
    m = _INTERVENTION_HYPOTHESIS_HEADING_RE.search(spec_text or "")
    if m is None:
        return None
    fields: dict = {}
    raw: dict[str, str] = {}
    current: str | None = None
    for line in spec_text[m.end():].splitlines():
        if line.startswith("##"):
            break  # next section — the block has ended
        stripped = line.strip()
        if not stripped:
            current = None
            continue
        fm = _INTERVENTION_FIELD_RE.match(stripped)
        if fm:
            current = fm.group(1)
            raw[current] = fm.group(2)
            continue
        if current is not None and line[:1] in (" ", "\t"):
            # Wrapped continuation of the previous list item (the SPEC's UX
            # example wraps the signal_independence justification).
            raw[current] = raw[current] + " " + stripped
            continue
        current = None  # non-field prose — stop folding
    for key in ("target_signal", "expected_direction",
                "canary_degraded_revert_note"):
        if key in raw:
            fields[key] = raw[key]
    # canary_revert_unsafe (bool, D5 degraded-note trigger): tolerant truthy.
    if "canary_revert_unsafe" in raw:
        fields["canary_revert_unsafe"] = (
            raw["canary_revert_unsafe"].strip().lower()
            in ("true", "yes", "1", "on")
        )
    if "signal_independence" in raw:
        value = raw["signal_independence"]
        head = value.split()[0].rstrip(":,;") if value.split() else value
        fields["signal_independence"] = (
            head if head in _INTERVENTION_INDEPENDENCE_ENUM else value
        )
        fields["signal_independence_note"] = value
    for key in _INTERVENTION_INT_FIELDS:
        if key in raw:
            try:
                fields[key] = int(raw[key])
            except (TypeError, ValueError):
                pass  # malformed int → omitted (defaults apply downstream)
    return fields


def _intervention_signal_event(target_signal: str) -> str | None:
    """Return the ledger event type for an ``event:<type>`` target, else None.

    ``kpi:<system>.<kpi-id>`` targets are carried VERBATIM on the record and
    resolve through the friction-kpi-registry (soft dep) at evaluation time —
    this helper deliberately does NOT resolve them (the evaluator owns the
    resolution seam and degrades a miss to ``INCONCLUSIVE (kpi-unresolvable)``).

    A sub-signal target (``event:<type>/<signature>``,
    efficacy-signal-integrity D1) resolves to the SAME bare ``<type>`` here —
    mirrors efficacy-eval.py's ``_resolve_target_signal`` contract exactly, so
    the ledger event-type counting key never carries a ``/<signature>``
    suffix that could never match a real ``event`` field. The signature
    component (if any) is read separately via ``_intervention_signal_signature``
    and folded into the baseline count by the caller.
    """
    if isinstance(target_signal, str) and target_signal.startswith("event:"):
        ev = target_signal[len("event:"):]
        if "/" in ev:
            ev = ev.split("/", 1)[0]
        return ev or None
    return None


def _intervention_signal_signature(target_signal: str) -> str | None:
    """Return the ``<signature>`` component of an ``event:<type>/<signature>``
    sub-signal target, else ``None`` (bare ``event:<type>``, non-event,
    ``undeclared``, or ``invalid``). Pure string parsing, mirrors
    efficacy-eval.py's ``_target_signature`` — DUPLICATED rather than
    imported (efficacy-eval.py imports lazy_core, not the reverse; capture
    validation and evaluation counting are separate lanes kept in lockstep by
    hand)."""
    if isinstance(target_signal, str) and target_signal.startswith("event:"):
        rest = target_signal[len("event:"):]
        if "/" in rest:
            _, sig = rest.split("/", 1)
            return sig or None
    return None


# The CLOSED vocabulary of telemetry event types (intervention-target-signal-
# validation). These are the exact string literals passed as the FIRST
# POSITIONAL argument to every ``append_telemetry_event(...)`` call site
# across lazy_core.py / lazy-state.py / bug-state.py — the D4-B ledger
# vocabulary plus ``sentinel-provisionalized``. Kept in lockstep with the
# real emitters by the AST-driven lock test
# ``test_intervention_event_vocabulary_matches_live_emit_set`` (never edit
# this set without re-running that test — a silent drift here would let
# ``validate_intervention_target_signal`` accept/reject the wrong things).
_INTERVENTION_EVENT_VOCABULARY: frozenset[str] = frozenset({
    "run-start",
    "run-end",
    "cycle-begin",
    "cycle-end",
    "pseudo-applied",
    "dispatch",
    "halt",
    "sentinel-resolved",
    "gate-refusal",
    "containment-refusal",
    "sentinel-provisionalized",
})


# The CLOSED set of gate-refusal sub-signal signatures (the `data.gate`
# values every `append_telemetry_event("gate-refusal", data={"gate": <sig>,
# ...})` call site passes). DUPLICATED from efficacy-eval.py's
# `_GATE_REFUSAL_SIGNATURES` (that module imports lazy_core, not the
# reverse — a capture-side validator cannot import the evaluator without a
# cycle). Keep both sets in lockstep by hand; efficacy-eval.py's own comment
# names this exact seam ("the capture-side vocabulary check that would also
# validate <signature> against this set is a STATE-lane seam").
_GATE_REFUSAL_SIGNATURES: frozenset[str] = frozenset({
    "gate-coverage",
    "unacked-hardening",
    "efficacy-coverage-missing",
    "checkpoint-auth",
    "apply-pseudo",
    "verify-ledger",
})

# Per-event-type closed sub-signal vocabulary for `event:<type>/<signature>`
# targets (efficacy-signal-integrity D1). Only `gate-refusal` has a verified
# sub-signal vocabulary in v1 (its `data.gate` field); an event type absent
# from this map accepts no sub-signal component (bare `event:<type>` only).
_INTERVENTION_SUB_SIGNAL_VOCABULARY: "dict[str, frozenset[str]]" = {
    "gate-refusal": _GATE_REFUSAL_SIGNATURES,
}


def validate_intervention_target_signal(target_signal: str) -> str | None:
    """Validate an intervention hypothesis ``target_signal`` string. PURE.

    Only ``event:<type>`` targets are checked against the closed
    ``_INTERVENTION_EVENT_VOCABULARY``: an unknown type returns a
    human-readable error string naming the valid set. A ``kpi:<sys>.<id>``
    target, the literal ``"undeclared"``, or any other non-``event:`` string
    is always valid (returns ``None``) — kpi targets resolve later through
    the friction-kpi-registry, and ``undeclared`` is the honest no-hypothesis
    default.

    A sub-signal target (``event:<type>/<signature>``,
    efficacy-signal-integrity D1) validates the bare ``<type>`` against the
    same vocabulary AND, when a ``<signature>`` component is present,
    additionally requires ``<type>`` to declare a sub-signal vocabulary
    (``_INTERVENTION_SUB_SIGNAL_VOCABULARY``) AND ``<signature>`` to be a
    member of it. A bare ``event:<type>`` target (no ``/``) is unaffected —
    byte-identical to pre-D1 behavior.
    """
    if isinstance(target_signal, str) and target_signal.startswith("event:"):
        rest = target_signal[len("event:"):]
        ev_type, sep, signature = rest.partition("/")
        if ev_type not in _INTERVENTION_EVENT_VOCABULARY:
            valid = ", ".join(sorted(_INTERVENTION_EVENT_VOCABULARY))
            return (
                f"unknown intervention event type {ev_type!r}; "
                f"valid event types: {valid}"
            )
        if sep and signature:
            allowed = _INTERVENTION_SUB_SIGNAL_VOCABULARY.get(ev_type)
            if not allowed:
                supported = ", ".join(sorted(_INTERVENTION_SUB_SIGNAL_VOCABULARY))
                return (
                    f"event type {ev_type!r} declares no sub-signal vocabulary "
                    f"(event:{ev_type}/{signature!r} is invalid); event types "
                    f"with a sub-signal vocabulary: {supported}"
                )
            if signature not in allowed:
                valid_sigs = ", ".join(sorted(allowed))
                return (
                    f"unknown {ev_type} sub-signal {signature!r}; "
                    f"valid {ev_type} sub-signals: {valid_sigs}"
                )
        return None
    return None


def _originating_telemetry_paths(current_repo_root, *, now: float | None = None) -> "list[Path]":
    """Resolve the telemetry-ledger paths of the run's ORIGINATING TARGET repo
    (interventions-telemetry-repo-scope-split-brain D1 v1).

    The interventions-bearing repo (claude-config) must be evaluated against the
    TARGET repo's runs' telemetry, which appends to the TARGET's repo_key-keyed
    state dir (the split-brain). Find the MOST-RECENT live (age <= _MARKER_STALE_SECONDS)
    run marker in a keyed sibling state dir whose recorded repo_root differs from
    current_repo_root, and return that keyed dir's telemetry ledger + rotated
    segments, OLDEST-first (matching read_telemetry_events' default ordering).

    RAW, NON-destructive marker reads (never read_run_marker — its age gate
    deletes a stale marker). No state-dir creation on this read path. FAIL-OPEN:
    any error contributes nothing -> returns [].
    """
    from ._monolith import _MARKER_STALE_SECONDS  # Phase-5 re-point (marker plane still monolith-resident)
    if now is None:
        now = time.time()
    try:
        override = os.environ.get("LAZY_STATE_DIR")
        base = Path(override) if override else (Path.home() / ".claude" / "state")
        if not base.is_dir():
            return []
        current_key = repo_key(str(current_repo_root))
        best_dir: Path | None = None
        best_started: float | None = None
        for d in sorted(base.iterdir(), key=lambda p: p.name):
            if not d.is_dir():
                continue
            try:
                marker_path = d / _MARKER_FILENAME
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                if not isinstance(marker, dict):
                    continue
                started_at_str = marker.get("started_at", "")
                started_dt = datetime.datetime.strptime(
                    started_at_str, "%Y-%m-%dT%H:%M:%SZ"
                )
                started_epoch = (
                    started_dt - datetime.datetime(1970, 1, 1)
                ).total_seconds()
                if now - started_epoch > _MARKER_STALE_SECONDS:
                    continue  # stale
                marker_repo_root = marker.get("repo_root")
                if repo_key(str(marker_repo_root)) == current_key:
                    continue  # self-exclusion
            except Exception:  # noqa: BLE001
                continue  # unparseable marker in this subdir — skip it
            if best_started is None or started_epoch > best_started:
                best_started = started_epoch
                best_dir = d
        if best_dir is None:
            return []
        active = best_dir / _TELEMETRY_LEDGER_FILENAME
        return [
            Path(f"{active}.{i}")
            for i in range(_TELEMETRY_ROTATED_SEGMENTS, 0, -1)
        ] + [active]
    except Exception:  # noqa: BLE001
        return []


def read_intervention_telemetry(repo_root: Path) -> list[dict]:
    """Merged, deduped, chronological telemetry read for intervention windows.

    State-dir ledger (``read_telemetry_events`` — rotated segments + active
    file) PLUS any committed cloud segments under
    ``<repo_root>/docs/telemetry/cloud/*.jsonl`` (the trends-aggregator read
    pattern — cloud runs' events survive only as committed segments) PLUS the
    run's originating target repo's keyed-sibling ledger (see
    ``_originating_telemetry_paths`` — interventions-telemetry-repo-scope-split-brain
    D1 v1). Deduped on ``(run_id, ts, event, item_id)``; sorted by
    ``(run_id, ts)`` so consumers see run-grouped chronological order.
    Read-only and fail-open — any error contributes nothing rather than raising.
    """
    events = list(read_telemetry_events())
    try:
        seg_dir = Path(repo_root) / "docs" / "telemetry" / "cloud"
        if seg_dir.is_dir():
            seg_paths = sorted(seg_dir.glob("*.jsonl"))
            if seg_paths:
                events += read_telemetry_events(paths=seg_paths)
    except OSError:
        pass
    try:
        sibling_paths = _originating_telemetry_paths(repo_root)
        if sibling_paths:
            events += read_telemetry_events(paths=sibling_paths)
    except OSError:
        pass
    seen: set = set()
    merged: list[dict] = []
    for e in events:
        key = (e.get("run_id"), e.get("ts"), e.get("event"), e.get("item_id"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(e)
    merged.sort(key=lambda e: (e.get("run_id") or "", e.get("ts") or 0.0))
    return merged


# The record's frontmatter field order — ONE serializer owns it so capture
# writes and evaluator re-writes stay diff-stable.
_INTERVENTION_FIELD_ORDER = (
    "kind", "intervention_id", "pipeline", "provenance", "shipped_date",
    "shipped_commit", "commit_set", "target_signal", "expected_direction",
    "signal_independence", "baseline", "review_after_runs", "min_sample",
    "band_pct", "review_count", "status", "escalated",
    "reconsideration_enqueued",
)


def _render_intervention_record(meta: dict, body: str) -> str:
    """Serialize an intervention record (frontmatter sentinel form, D3).

    Field order follows ``_INTERVENTION_FIELD_ORDER`` (unknown extras append
    in insertion order). ``yaml.safe_dump`` handles the nested ``baseline:``
    map, None → ``null``, and QUOTES strings that would otherwise re-parse as
    timestamps (run ids / dates) — so ``parse_sentinel`` round-trips every
    value type-preserved (the SPEC's formerly-deferred empirical check).
    """
    ordered: dict = {}
    for key in _INTERVENTION_FIELD_ORDER:
        if key in meta:
            ordered[key] = meta[key]
    for key, value in meta.items():
        if key not in ordered:
            ordered[key] = value
    fm = yaml.safe_dump(
        ordered, sort_keys=False, default_flow_style=False,
        allow_unicode=True,
    ).strip()
    return f"---\n{fm}\n---\n\n{body.rstrip()}\n"


# ---------------------------------------------------------------------------
# harness-change-canary-rollback Phase 1 — canary registration helpers.
#
# A shipped control-surface change enters a canary observation window: at
# capture time (record_intervention below), if the change's touched-file set
# (from the provenance change->commit-set mapping) intersects the
# control-surface manifest, the record gains a `canary:` sub-map. All the
# defaults live in ONE constants block; the manifest, when present, takes
# precedence over the canary-owned fallback glob constant (which mirrors the
# anti-overfit-design-gate's initial control-surface set until
# docs/gate/control-surfaces.json ships). Read-only + fail-open throughout —
# capture must NEVER error a completion.
# ---------------------------------------------------------------------------

# Window defaults (D2-A): next 10 completed runs after ship, 30-day ceiling.
CANARY_WINDOW_RUNS_DEFAULT = 10
CANARY_WINDOW_DAYS_CEILING = 30

# The canary-owned fallback control-surface set — used only when
# docs/gate/control-surfaces.json is absent (anti-overfit-design-gate ships
# that manifest; the manifest takes precedence when present). Mirrors the
# anti-overfit SPEC's initial set. Segment-aware glob semantics: `**` crosses
# directory separators, `*`/`?` stay within a path segment.
_CANARY_CONTROL_SURFACES_FALLBACK: tuple[str, ...] = (
    "user/hooks/**",
    "user/scripts/lazy-state.py",
    "user/scripts/bug-state.py",
    "user/scripts/lazy_core/**",
    "user/scripts/lazy_guard.py",
    "user/scripts/lazy_inject.py",
    "user/scripts/lazy-parity-manifest.json",
    "user/scripts/build-queue*.ps1",
    "user/skills/lazy*/**",
    "user/skills/harden-harness/**",
    "user/skills/_components/*gate*.md",
    "user/settings.json",
)

_CANARY_CONTROL_SURFACES_FILE = ("docs", "gate", "control-surfaces.json")


def _canary_control_surfaces(repo_root: Path) -> list[str] | tuple[str, ...]:
    """Resolve the control-surface glob set (manifest-when-present, else the
    fallback constant).

    Reads ``docs/gate/control-surfaces.json`` when present — a dict carrying a
    ``globs`` / ``surfaces`` / ``control_surfaces`` list, or a bare list. Any
    read/parse failure or an unrecognized shape degrades to the fallback
    constant (never raises)."""
    manifest_path = Path(repo_root).joinpath(*_CANARY_CONTROL_SURFACES_FILE)
    try:
        if manifest_path.is_file():
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            globs: list | None = None
            if isinstance(data, list):
                globs = data
            elif isinstance(data, dict):
                for key in ("globs", "surfaces", "control_surfaces"):
                    if isinstance(data.get(key), list):
                        globs = data[key]
                        break
            if globs is not None:
                cleaned = [str(g).strip() for g in globs if str(g).strip()]
                if cleaned:
                    return cleaned
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return _CANARY_CONTROL_SURFACES_FALLBACK


def _canary_glob_to_re(glob: str) -> "re.Pattern":
    """Compile a control-surface glob to an anchored regex with segment-aware
    semantics: ``**`` crosses ``/`` (any depth), ``*`` matches within a segment,
    ``?`` matches one non-separator char."""
    out: list[str] = []
    i = 0
    n = len(glob)
    while i < n:
        if glob[i:i + 2] == "**":
            out.append(".*")
            i += 2
            if i < n and glob[i] == "/":
                i += 1  # swallow the trailing slash so `a/**` matches `a/x`
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def _canary_touched_files(repo_root: Path, commit_set) -> list[str]:
    """Derive the sorted, repo-relative POSIX file set touched by a commit set.

    Reuses the provenance git helper ``_git_capture_lines`` (NOT an ad-hoc
    subprocess) — one ``git show --name-only`` per sha, unioned. Any
    unresolvable sha / non-git tree contributes nothing; the result is empty
    rather than an error."""
    files: set[str] = set()
    for sha in commit_set or []:
        sha = str(sha).strip()
        if not sha:
            continue
        lines = _git_capture_lines(
            repo_root, ["show", "--name-only", "--pretty=format:", sha])
        if not lines:
            continue
        for ln in lines:
            s = ln.strip()
            if s:
                files.add(_normalize_index_key(repo_root, s))
    return sorted(files)


def _canary_intersects(touched_files, surfaces) -> tuple[bool, list[str]]:
    """Return (arm, matched_surfaces): whether any touched file matches a
    control-surface glob, and the sorted list of the matching touched files
    (the resolved file-identity ``surfaces:`` the watcher's D3 attribution
    matches incident surfaces against — repo-relative POSIX paths)."""
    pats = [_canary_glob_to_re(g) for g in (surfaces or [])]
    hits = sorted({
        f for f in (touched_files or [])
        if any(p.match(f) for p in pats)
    })
    return (bool(hits), hits)


# The coupled-pair table from the root CLAUDE.md, folded in as DATA for any
# pair absent from lazy-parity-manifest.json (D5 — the pair scope must be
# computable even for pairs the machine-readable manifest does not carry).
# Kept in lockstep with the root CLAUDE.md "Coupled Skill Pairs" table.
_CANARY_CLAUDE_MD_PAIRS: tuple[tuple[str, str], ...] = (
    ("user/skills/lazy/SKILL.md",
     "repos/algobooth/.claude/skills/lazy-cloud/SKILL.md"),
    ("user/skills/lazy-batch/SKILL.md",
     "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md"),
    ("user/skills/lazy/SKILL.md", "user/skills/lazy-bug/SKILL.md"),
    ("user/skills/lazy-batch/SKILL.md", "user/skills/lazy-bug-batch/SKILL.md"),
    ("user/skills/lazy-status/SKILL.md",
     "user/skills/lazy-bug-status/SKILL.md"),
)


def _canary_load_parity_pairs(manifest_path: Path) -> list[tuple[str, str]]:
    """Read (canonical, derived) pairs from lazy-parity-manifest.json. Any
    read/parse failure or unexpected shape degrades to an empty list (the
    caller still folds in the CLAUDE.md pairs-table data)."""
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    pairs: list[tuple[str, str]] = []
    for p in (data.get("pairs") if isinstance(data, dict) else None) or []:
        if not isinstance(p, dict):
            continue
        canonical = p.get("canonical")
        derived = p.get("derived")
        if isinstance(canonical, str) and isinstance(derived, str):
            pairs.append((canonical, derived))
    return pairs


_CANARY_DEFAULT_REVERT_UNSAFE_NOTE = (
    "Change flagged revert-unsafe at ship time (e.g. it migrated on-disk state "
    "or a schema). A plain `git revert` of the commit set may not fully back it "
    "out — the bug pipeline must determine actual revert feasibility with the "
    "repo checked out (v1 records this note; no `git revert` dry-run machinery)."
)


def _maybe_arm_canary(
    repo_root: Path,
    intervention_id: str,
    shipped_commit: str | None,
    hyp: dict,
    opened_date: str,
) -> dict | None:
    """Build the canary sub-map for a shipped change, or None when the change
    does not touch the control-surface manifest (D1/D5).

    Derives the touched-file + commit sets from the provenance change->commit-set
    mapping (bracket-primary, message-grep fallback, single-commit last resort),
    intersects them with the control-surface manifest, and — on a scope hit —
    returns ``{opened, window_runs, surfaces, commit_set, pair_scope,
    degraded_revert_note, status: open}`` (the frozen Phase-2 key set). Read-only
    and fail-open: any derivation miss simply yields None (no canary)."""
    touched = (derive_touched_from_brackets(repo_root, intervention_id)
               or derive_touched_from_grep(repo_root, intervention_id))
    commit_set = list(touched.get("commits") or [])
    files = list(touched.get("files") or [])
    if not commit_set and shipped_commit and shipped_commit != "unknown":
        commit_set = [shipped_commit]
    if not files:
        files = _canary_touched_files(repo_root, commit_set)
    arm, surfaces = _canary_intersects(files, _canary_control_surfaces(repo_root))
    if not arm:
        return None
    manifest_path = (
        Path(repo_root) / "user" / "scripts" / "lazy-parity-manifest.json"
    )
    pair_scope = _compute_pair_scope(files, manifest_path)
    window_runs = hyp.get("canary_window_runs")
    if not isinstance(window_runs, int) or window_runs <= 0:
        window_runs = CANARY_WINDOW_RUNS_DEFAULT
    note = hyp.get("canary_degraded_revert_note")
    if not note and hyp.get("canary_revert_unsafe"):
        note = _CANARY_DEFAULT_REVERT_UNSAFE_NOTE
    return {
        "opened": opened_date,
        "window_runs": window_runs,
        "surfaces": surfaces,
        "commit_set": commit_set,
        "pair_scope": pair_scope,
        "degraded_revert_note": note if note else None,
        "status": "open",
    }


def _compute_pair_scope(touched_files, manifest_path: Path) -> list[str]:
    """Compute the coupled-pair scope for a set of touched files (D5).

    A touched file matching EITHER half of a coupled pair yields BOTH halves in
    the scope (reverting one half of a parity-guarded pair breaks the audit).
    Pairs come from ``lazy-parity-manifest.json`` UNIONed with the root
    CLAUDE.md pairs-table entries (folded in as data for any pair the manifest
    does not carry). Result is de-duplicated, order-stable."""
    pairs = _canary_load_parity_pairs(manifest_path)
    seen_pairs = {frozenset(p) for p in pairs}
    for p in _CANARY_CLAUDE_MD_PAIRS:
        if frozenset(p) not in seen_pairs:
            pairs.append(p)
            seen_pairs.add(frozenset(p))
    touched = set(touched_files or [])
    scope: list[str] = []
    for canonical, derived in pairs:
        if canonical in touched or derived in touched:
            for half in (canonical, derived):
                if half not in scope:
                    scope.append(half)
    return scope


def record_intervention(
    repo_root: Path,
    intervention_id: str,
    *,
    pipeline: str,
    spec_path: Path | None = None,
    date: str | None = None,
    shipped_commit: str | None = None,
    shipped_date: str | None = None,
    provenance: str = "gated",
    hypothesis_overrides: dict | None = None,
) -> dict:
    """Write the intervention record for a shipped harness change (capture, D1-A).

    Freezes the baseline window from the telemetry ledger AT THIS MOMENT into
    the record (D3 — the raw ledger is untracked and rotation-eligible; the
    baseline must not depend on raw-event retention) and atomically writes the
    frontmatter-sentinel record to ``docs/interventions/<id>.md`` (D4-A).

    Hypothesis inputs, in precedence order: the ``## Intervention Hypothesis``
    block of ``spec_path``'s SPEC.md (when given), then ``hypothesis_overrides``
    (the CLI's no-SPEC path — hardening rounds). Absent both → the record is
    written ``target_signal: undeclared`` (INCONCLUSIVE-by-construction,
    surfaced for triage; completion NEVER blocked — D2-A).

    Baseline degradation is honest, never an error: ``frozen`` (trailing
    ``baseline_runs`` distinct run_ids counted for an ``event:`` target),
    ``unavailable`` (no ledger data), ``not-computable`` (undeclared or
    non-``event:`` target — kpi targets resolve at evaluation time).
    ``last_run_id`` (the post-window boundary) is recorded in every case.

    Idempotent and never-clobbering: an EXISTING file at the record path →
    noop (``{"recorded": False, "noop": True}``) — a prior capture/backfill is
    never overwritten. All writes go through ``_atomic_write``. This function
    never raises for missing/degraded inputs and never calls ``_die``; callers
    on the completion path additionally wrap it fail-open.

    Args:
        repo_root: repo the record lands in (``docs/interventions/``).
        intervention_id: item slug or ``harden-<YYYY-MM>-r<N>`` (D3).
        pipeline: ``feature`` | ``bug`` | ``hardening``.
        spec_path: the item's spec DIR (or a SPEC.md file) to read the
            hypothesis block from; None for the no-SPEC paths.
        date: ISO capture date (defaults to today).
        shipped_commit: HEAD override (D9 backfill); defaults to the repo's
            current HEAD (None on a non-git tree → recorded ``unknown``).
        shipped_date: ship-date override (D9 backfill); defaults to ``date``.
        provenance: ``gated`` (completion gate) | ``manual`` (CLI) |
            ``backfilled`` (CLI with shipped-* overrides).
        hypothesis_overrides: dict merged OVER the parsed SPEC block.

    Returns:
        ``{"recorded": bool, "noop": bool, "path": str, "target_signal": str,
        "baseline_status": str}``.
    """
    from ._monolith import head_sha_snapshot  # Phase-5 re-point (marker plane still monolith-resident)
    repo_root = Path(repo_root)
    if date is None:
        date = datetime.date.today().isoformat()
    record_path = (
        repo_root / "docs" / _INTERVENTIONS_DIRNAME / f"{intervention_id}.md"
    )
    if record_path.exists():
        # Never clobber a prior capture/backfill — idempotency by existence.
        return {
            "recorded": False,
            "noop": True,
            "path": str(record_path),
            "target_signal": None,
            "baseline_status": None,
        }

    # --- Hypothesis resolution (SPEC block, then overrides) ---
    hyp: dict = {}
    if spec_path is not None:
        spec_md = Path(spec_path)
        if spec_md.is_dir():
            spec_md = spec_md / "SPEC.md"
        try:
            parsed = parse_intervention_hypothesis(
                spec_md.read_text(encoding="utf-8")
            )
        except OSError:
            parsed = None
        if parsed:
            hyp.update(parsed)
    if hypothesis_overrides:
        hyp.update(
            {k: v for k, v in hypothesis_overrides.items() if v is not None}
        )
    target_signal = hyp.get("target_signal") or "undeclared"
    _rejected_target = target_signal
    _target_err = validate_intervention_target_signal(target_signal)
    if _target_err is not None:
        target_signal = "undeclared"
        _diag(
            f"record_intervention: unknown event target "
            f"'{_rejected_target}' degraded to undeclared ({_target_err})"
        )
    expected_direction = hyp.get("expected_direction") or "undeclared"
    signal_independence = hyp.get("signal_independence") or "undeclared"

    def _cfg_int(key: str, default: int) -> int:
        try:
            return int(hyp.get(key, default))
        except (TypeError, ValueError):
            return default

    review_after_runs = _cfg_int(
        "review_after_runs", INTERVENTION_REVIEW_AFTER_RUNS)
    baseline_runs_cfg = _cfg_int("baseline_runs", INTERVENTION_BASELINE_RUNS)
    min_sample = _cfg_int("min_sample", INTERVENTION_MIN_SAMPLE)
    band_pct = _cfg_int("band_pct", INTERVENTION_BAND_PCT)

    if shipped_commit is None:
        shipped_commit = head_sha_snapshot(repo_root)
    if shipped_date is None:
        shipped_date = date

    # --- Baseline freeze (read-only over the merged ledger; fail-open) ---
    try:
        events = read_intervention_telemetry(repo_root)
    except Exception:  # noqa: BLE001 — capture must never error a completion
        events = []
    run_ids = sorted({
        e.get("run_id") for e in events if e.get("run_id")
    })
    last_run_id = run_ids[-1] if run_ids else None
    ev_type = _intervention_signal_event(target_signal)
    ev_signature = _intervention_signal_signature(target_signal)
    if ev_type is None:
        baseline: dict = {
            "status": "not-computable",
            "reason": ("undeclared" if target_signal == "undeclared"
                       else "non-event-target"),
            "last_run_id": last_run_id,
        }
    elif not run_ids:
        baseline = {
            "status": "unavailable",
            "reason": "no-ledger-data",
            "last_run_id": None,
        }
    else:
        window = run_ids[-baseline_runs_cfg:]
        window_set = set(window)
        count = sum(
            1 for e in events
            if e.get("run_id") in window_set and e.get("event") == ev_type
            and (ev_signature is None
                 or (e.get("data") or {}).get("gate") == ev_signature)
        )
        baseline = {
            "status": "frozen",
            "runs": len(window),
            "events": count,
            "value": round(count / len(window), 4),
            "window_start_run": window[0],
            "window_end_run": window[-1],
            "last_run_id": last_run_id,
        }

    meta = {
        "kind": "intervention",
        "intervention_id": intervention_id,
        "pipeline": pipeline,
        "provenance": provenance,
        "shipped_date": shipped_date,
        "shipped_commit": shipped_commit or "unknown",
        # v1 commit_set = the capture commit; enriched to the full
        # change→commit-set mapping when code-doc-provenance-linkage ships.
        "commit_set": shipped_commit or "unknown",
        "target_signal": target_signal,
        "expected_direction": expected_direction,
        "signal_independence": signal_independence,
        "baseline": baseline,
        "review_after_runs": review_after_runs,
        "min_sample": min_sample,
        "band_pct": band_pct,
        "review_count": 0,
        "status": "open",
        "escalated": False,
        "reconsideration_enqueued": None,
    }
    note = hyp.get("signal_independence_note") or ""
    body_lines = [
        f"# Intervention: {intervention_id}",
        "",
        (f"Hypothesis: shipping `{intervention_id}` ({pipeline} pipeline) "
         f"moves `{target_signal}` in direction `{expected_direction}` "
         f"within {review_after_runs} post-ship runs."),
    ]
    if note:
        body_lines += ["", f"Signal independence: {note}"]
    body_lines += [
        "",
        "Reviews are appended below by `user/scripts/efficacy-eval.py` "
        "(`## Review <date>` sections). Do not hand-edit the frontmatter — "
        "the evaluator is its sole post-capture writer.",
    ]
    # --- Canary registration post-step (harness-change-canary-rollback D1/D5) ---
    # Arm a canary window when the shipped change touches the control-surface
    # manifest. Fail-open — a canary failure must never error a completion; a
    # non-scoped change registers no canary (byte-identical to before).
    try:
        canary = _maybe_arm_canary(
            repo_root, intervention_id, shipped_commit, hyp, shipped_date)
        if canary is not None:
            meta["canary"] = canary
    except Exception:  # noqa: BLE001 — capture must never error a completion
        pass

    _atomic_write(
        record_path, _render_intervention_record(meta, "\n".join(body_lines))
    )
    return {
        "recorded": True,
        "noop": False,
        "path": str(record_path),
        "target_signal": target_signal,
        "baseline_status": baseline["status"],
    }


def _interventions_queue_flag(repo_root: Path) -> bool:
    """True iff docs/features/queue.json carries top-level ``interventions: true``.

    The repo-opt-in capture flag (the ``autodiscover`` precedent — top-level
    sibling of ``queue``, set only by claude-config; every other repo omits it
    and completion output stays byte-identical). Read-only, defensive: a
    missing/malformed queue.json ⇒ False. The flag lives in the FEATURE queue
    for BOTH pipelines (one repo-level switch, not per-queue).
    """
    queue_path = Path(repo_root) / "docs" / "features" / "queue.json"
    if not queue_path.exists():
        return False
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(data, dict) and data.get("interventions") is True


def oldest_unacked_deny(*, current_run_only: bool = True) -> dict | None:
    """Return the OLDEST (FIFO) unacked deny-ledger entry, or None when there is
    no pending debt.

    Phase 8 WU-8.2: the probe's routed-hardening-debt override pre-composes a
    ``--emit-dispatch hardening`` command whose ``--context`` bindings are derived
    from this entry (``prompt_head`` → denied_prompt_summary, ``reason_head`` →
    denial_reason).  Read-only — does NOT mutate the ledger (the guard's
    allow-time ack is the only mutator now).

    ``current_run_only`` (Residual gap B, default True): mirrors
    ``pending_hardening()`` — when a live run marker exists, skip an unacked
    entry whose ``run_started_at`` does not match it (a prior/crashed run's
    leftover), so the entry bound into the hardening-dispatch command is always
    the one that actually drove ``pending_hardening() > 0`` for THIS run. When no
    live marker exists, behavior is unchanged (oldest unacked overall).
    """
    current_started = _raw_marker_started_at() if current_run_only else None
    for entry in read_deny_ledger():
        if entry.get("acked", False):
            continue
        if current_started is not None and entry.get("run_started_at") != current_started:
            continue
        return entry
    return None


def build_hardening_emit_command(
    state_script_name: str,
    *,
    item_id: str,
    oldest_deny: dict | None,
    probe_summary: str,
    registry_summary: str,
    cwd: str,
    observed_friction: dict | None = None,
) -> str:
    """Pre-compose the single-line shell command that dispatches a hardening
    round (Phase 8 WU-8.2; observed-friction branch:
    no-mid-run-observed-friction-harden-dispatch).

    The returned string is meant to be pasted verbatim into bash by the
    orchestrator when the probe withholds the forward route over pending
    hardening debt.  Every ``--context`` VALUE is shell-quoted via ``shlex.quote``
    (POSIX single-quote escaping) so embedded spaces, quotes, and newlines round-
    trip safely regardless of the host platform — the command targets ``bash`` /
    ``python3`` on the operator's machine, not the Windows host that emits it.

    Args:
        state_script_name: ``"lazy-state.py"`` or ``"bug-state.py"`` — the script
            whose ``--emit-dispatch hardening`` retires this debt.
        item_id: the current feature/bug id (becomes ``--context item_id=...``).
        oldest_deny: the oldest unacked deny-ledger entry (from
            ``oldest_unacked_deny()``), or None.  Its ``prompt_head`` /
            ``reason_head`` bind denied_prompt_summary / denial_reason; absent →
            empty strings.
        probe_summary: a compact one-line summary of the withholding probe.
        registry_summary: a short registry-state summary (e.g. "N entries, M
            unconsumed" or "empty").
        cwd: the repo root the dispatch should run against.
        observed_friction: when supplied (a dict with ``friction_summary`` /
            ``friction_detail`` / ``blocking``), build the OBSERVED-FRICTION
            command instead — ``trigger_kind=observed-friction`` driven by
            ORCHESTRATOR-SUPPLIED context, NOT a deny-ledger entry
            (no-mid-run-observed-friction-harden-dispatch §1). The emitted
            ``--context friction_summary`` / ``friction_detail`` / ``blocking``
            keys are re-bound into the template's shared @requires evidence keys
            by ``normalize_hardening_dispatch_context`` when the command runs, so
            the dispatch-hardening.md template resolves. ``oldest_deny`` is
            ignored in this mode.

    Returns:
        A single shell command string, safe to paste into bash.
    """
    def _ctx(key: str, value: str) -> str:
        # shlex.quote escapes the VALUE only; the key=value join stays literal.
        return f"--context {key}={shlex.quote(value)}"

    # no-mid-run-observed-friction-harden-dispatch §1: the observed-friction
    # branch is driven by ORCHESTRATOR-SUPPLIED context (a mid-run harness gap
    # the orchestrator named through its own reasoning), NOT a deny/friction
    # ledger entry — there is no probe withholding behind it.  The command emits
    # the friction-specific keys (friction_summary / friction_detail / blocking);
    # normalize_hardening_dispatch_context re-binds them into the shared
    # @requires evidence keys (friction_summary → denied_prompt_summary,
    # friction_detail → denial_reason) and injects observed-friction placeholders
    # for probe_json / registry_state when the emitted command actually runs, so
    # emit_dispatch_prompt does not refuse on a missing @requires key.
    if observed_friction is not None:
        friction_summary = observed_friction.get("friction_summary", "") or ""
        friction_detail = observed_friction.get("friction_detail", "") or ""
        blocking_raw = observed_friction.get("blocking", False)
        blocking_str = (
            "true"
            if (blocking_raw is True or str(blocking_raw).strip().lower() == "true")
            else "false"
        )
        parts = [
            f"python3 ~/.claude/scripts/{state_script_name}",
            "--emit-dispatch hardening",
            _ctx("trigger_kind", "observed-friction"),
            _ctx("item_id", item_id or ""),
            _ctx("friction_summary", friction_summary),
            _ctx("friction_detail", friction_detail),
            _ctx("blocking", blocking_str),
            _ctx("cwd", cwd or ""),
        ]
        return " ".join(parts)

    entry = oldest_deny or {}

    # hardening-blind-to-process-friction Phase 2: a process-friction entry
    # (kind: "process-friction", from a torn cycle bracket / unexpected commits)
    # binds trigger_kind=process-friction and surfaces the friction reason+detail.
    #
    # The dispatch-hardening.md template @requires the SHARED evidence keys
    # (denied_prompt_summary / denial_reason) for EVERY trigger_kind — it has a
    # single evidence section, not a friction-specific one.  So the friction
    # reason+detail MUST be bound INTO those keys (friction_reason →
    # denied_prompt_summary, friction_detail → denial_reason), exactly as the
    # template header + hardening-dispatch.md document.  Emitting friction-specific
    # context keys instead left denied_prompt_summary/denial_reason unbound, and
    # emit_dispatch_prompt refused the whole route ("requires context key
    # 'denied_prompt_summary' which is absent") — the broken-hardening-route defect.
    if entry.get("kind") == "process-friction":
        friction_reason = entry.get("reason_head", "") or ""
        friction_detail = entry.get("detail", "") or ""
        parts = [
            f"python3 ~/.claude/scripts/{state_script_name}",
            "--emit-dispatch hardening",
            _ctx("trigger_kind", "process-friction"),
            _ctx("item_id", item_id or ""),
            _ctx("denied_prompt_summary", friction_reason),
            _ctx("denial_reason", friction_detail),
            _ctx("probe_json", probe_summary),
            _ctx("registry_state", registry_summary),
            _ctx("cwd", cwd or ""),
        ]
        return " ".join(parts)

    denied_prompt_summary = entry.get("prompt_head", "") or ""
    denial_reason = entry.get("reason_head", "") or ""

    parts = [
        f"python3 ~/.claude/scripts/{state_script_name}",
        "--emit-dispatch hardening",
        _ctx("trigger_kind", "validate-deny"),
        _ctx("item_id", item_id or ""),
        _ctx("denied_prompt_summary", denied_prompt_summary),
        _ctx("denial_reason", denial_reason),
        _ctx("probe_json", probe_summary),
        _ctx("registry_state", registry_summary),
        _ctx("cwd", cwd or ""),
    ]
    return " ".join(parts)


# Observed-friction placeholders for the two template @requires evidence keys
# that have no meaning behind an ORCHESTRATOR-OBSERVED harness gap (there is no
# probe withholding + no registry state driving it).  Bound as literals so the
# dispatch-hardening.md template resolves for trigger_kind=observed-friction.
_OBSERVED_FRICTION_PROBE_PLACEHOLDER = (
    "observed-friction: no probe (orchestrator-observed mid-run harness gap)"
)
_OBSERVED_FRICTION_REGISTRY_PLACEHOLDER = (
    "observed-friction: n/a (not a routing/deny failure)"
)


def normalize_hardening_dispatch_context(context: dict) -> dict:
    """Normalize the ``--context`` dict for an ``--emit-dispatch hardening`` call
    so the dispatch-hardening.md template's @requires keys resolve regardless of
    trigger_kind (no-mid-run-observed-friction-harden-dispatch §1).

    Two entry shapes converge on the same template:

      * AUTO-TRIGGER (validate-deny / no-route / inject-hook-error /
        process-friction): ``build_hardening_emit_command`` already pre-binds the
        shared evidence keys (denied_prompt_summary / denial_reason / probe_json /
        registry_state), so this normalizer only defaults ``blocking`` for them.

      * OBSERVED-FRICTION (an orchestrator-observed mid-run harness gap): the
        orchestrator supplies ``friction_summary`` / ``friction_detail`` /
        ``blocking`` / ``item_id`` / ``cwd`` in place of the denial-specific keys.
        This normalizer performs the SAME rebind ``build_hardening_emit_command``'s
        process-friction branch does — friction_summary → denied_prompt_summary,
        friction_detail → denial_reason — and injects observed-friction
        placeholders for ``probe_json`` / ``registry_state`` (there is no probe or
        registry behind an observed gap), so ``emit_dispatch_prompt`` does not
        refuse on a missing @requires key.  This coupling mirrors the
        process-friction binding the existing regression test guards, so the two
        cannot silently drift.

    Non-destructive: returns a NEW dict; the caller's ``context`` is unchanged.
    A non-observed-friction context passes through with only the ``blocking``
    default added — the auto-trigger paths keep binding the shared evidence keys
    exactly as before, and the template's shared ``{blocking}`` token never goes
    unbound for them.  An explicit override of any target key is never clobbered
    (fill-only-when-absent), so the operator/composer stays authoritative.
    """
    ctx = dict(context)
    if ctx.get("trigger_kind") == "observed-friction":
        if "denied_prompt_summary" not in ctx and "friction_summary" in ctx:
            ctx["denied_prompt_summary"] = ctx["friction_summary"]
        if "denial_reason" not in ctx and "friction_detail" in ctx:
            ctx["denial_reason"] = ctx["friction_detail"]
        ctx.setdefault("probe_json", _OBSERVED_FRICTION_PROBE_PLACEHOLDER)
        ctx.setdefault("registry_state", _OBSERVED_FRICTION_REGISTRY_PLACEHOLDER)
    # `blocking` is an observed-friction concept (foreground-await vs
    # backgrounded — the §3 block/background policy); the auto-triggers have no
    # block policy.  Default it so a shared {blocking} token in the template
    # never goes unbound for the auto-trigger paths (which never supply it).
    ctx.setdefault("blocking", "n/a (auto-trigger)")
    return ctx


def ack_oldest_deny(now: float | None = None) -> dict | None:
    """Ack the OLDEST unacked deny-ledger entry (FIFO), rewriting the ledger.

    Called once per successful ``--emit-dispatch hardening`` emission so the
    one-dispatch-per-deny cadence (locked decision 4) is preserved: each hardening
    dispatch retires exactly one unit of routed hardening debt.

    The oldest unacked entry's ``acked`` flips to True and gains an ``acked_ts``.
    The whole ledger is then rewritten atomically (the file is small — one line
    per deny, bounded by run length).

    Args:
        now: epoch float for acked_ts (injectable for hermetic tests).

    Returns:
        The entry dict that was acked, or None when there were no pending
        entries (no-op — not an error).
    """
    if now is None:
        now = time.time()
    entries = read_deny_ledger()
    target: dict | None = None
    for entry in entries:
        if not entry.get("acked", False):
            entry["acked"] = True
            entry["acked_ts"] = now
            target = entry
            break
    if target is None:
        # Nothing pending — no-op, no rewrite.
        return None
    # Rewrite the whole ledger (one JSON object per line) atomically.
    try:
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        body = "".join(json.dumps(e) + "\n" for e in entries)
        _atomic_write(ledger_path, body)
    except Exception:  # noqa: BLE001
        # A rewrite failure leaves the on-disk ledger unchanged; report the ack
        # as not-applied so callers do not over-count.  The next emission retries.
        return None
    return target


def ack_all_unacked_denies(now: float | None = None) -> int:
    """Ack EVERY unacked deny-ledger entry (operator override), rewriting the ledger.

    The operator-override counterpart to ``ack_oldest_deny`` (which retires exactly
    ONE unit of debt per hardening dispatch).  Called by the ``--run-end
    --ack-unhardened`` path: when the operator explicitly authorizes retiring the
    run while hardening debt is still pending, that authorization must actually
    CLEAR the debt — otherwise the entries stay ``acked: false`` on disk and the
    NEXT run's advancing probe keeps withholding the forward route over
    ``pending-hardening-debt`` that the operator already discharged (the
    unclearable-debt deadlock — turn-routing-enforcement hardening Round 20).

    The override clears ALL unacked entries REGARDLESS of kind (validate-deny
    denials AND ``kind: process-friction`` entries) and REGARDLESS of any
    ``session_id`` field — ``pending_hardening()`` itself never filtered by
    session, so a session-less process-friction entry (written by ``--cycle-end``
    with no session_id) is exactly the entry that previously could never be
    discharged by the operator.  The operator override is a deliberate, audited
    blanket ack; it is the ONLY ack path that retires more than one entry.

    Args:
        now: epoch float for acked_ts (injectable for hermetic tests).

    Returns:
        The number of entries that were flipped from unacked → acked (0 when the
        ledger was already clean — a no-op, not an error).  On a rewrite failure
        the on-disk ledger is left unchanged and 0 is returned (the caller must
        not over-report the discharge).
    """
    if now is None:
        now = time.time()
    entries = read_deny_ledger()
    acked_count = 0
    for entry in entries:
        if not entry.get("acked", False):
            entry["acked"] = True
            entry["acked_ts"] = now
            acked_count += 1
    if acked_count == 0:
        # Nothing pending — no-op, no rewrite.
        return 0
    # Rewrite the whole ledger (one JSON object per line) atomically.
    try:
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        body = "".join(json.dumps(e) + "\n" for e in entries)
        _atomic_write(ledger_path, body)
    except Exception:  # noqa: BLE001
        # A rewrite failure leaves the on-disk ledger unchanged; report 0 acked so
        # the caller does not claim a discharge that did not persist.
        return 0
    return acked_count


def _deny_entry_same_cause_key(entry: dict) -> tuple | None:
    """Return a hashable "same cause" key for a deny-ledger entry, or ``None``
    when the entry carries no usable identity (meta-dispatch-not-by-reference-
    and-ack-overpriced Fix Scope §2).

    Prefers ``denied_sha12`` (the sha256-of-prompt identity a validate-deny
    entry always carries — a byte-identical repeat denial). Falls back to
    ``(kind, reason_head)`` for entries with no ``denied_sha12`` (e.g.
    ``kind: process-friction``, which has no dispatched-prompt sha at all) —
    an identical kind+reason repeat is the SPEC's named fallback identity.
    """
    sha = entry.get("denied_sha12")
    if sha:
        return ("sha", sha)
    reason = entry.get("reason_head")
    if reason:
        return ("reason", entry.get("kind"), reason)
    return None


def ack_deny_by_selector(
    selector: str, resolution: str, *, now: float | None = None
) -> dict:
    """Cheaply retire unacked deny-ledger entries by SELECTOR, WITHOUT a full
    hardening dispatch (meta-dispatch-not-by-reference-and-ack-overpriced Fix
    Scope §1+§2 — the ``--ack-deny <selector> --resolution <text>`` CLI).

    Unlike ``ack_oldest_deny`` (called ONLY from a hardening dispatch reaching
    guard-allow — one full Opus round per entry), this is a cheap, audited,
    gate-free ledger operation for the two cases where a full round is
    wasteful: (a) the entry's root cause was already fixed by an earlier round
    THIS run (the redundant-second-dispatch case), (b) an explicit, recorded
    no-fix classification. It must be invoked from a CLI handler that calls
    ``refuse_if_cycle_active`` first (never reachable from a cycle subagent) —
    this function itself performs no cycle check, matching the other
    ledger-mutation helpers in this module (the CLI layer owns the guard).

    Args:
        selector: ``"oldest"`` (the FIFO-oldest unacked entry, mirroring
            ``ack_oldest_deny``'s default ordering) or a ``denied_sha12``
            value/prefix (case-insensitive, >=1 hex char) matched against the
            first unacked entry whose ``denied_sha12`` starts with it.
        resolution: REQUIRED non-empty audit note — who/why this entry is
            being retired without a hardening round. Recorded verbatim on the
            acked entry (and, deduped-mirrored, on every same-cause sibling)
            so ``/lazy-batch-retro`` can grade the op for abuse.
        now: epoch float for ``acked_ts`` (injectable for hermetic tests).

    Same-cause dedup (Fix Scope §2): after resolving the selected target entry,
    every OTHER unacked entry sharing the same cause key
    (``_deny_entry_same_cause_key`` — identical ``denied_sha12``, or identical
    ``kind``+``reason_head`` when no sha exists) is acked in the SAME ledger
    rewrite, with ``ack_method: "manual-ack-dedup"`` and a resolution note that
    cross-references the primary ack — so one oscillating cause never costs
    more than one unit of retirement effort, regardless of how many times it
    was denied.

    Returns:
        ``{"ok": bool, "acked": <entry dict> | None, "deduped": [<entry dict>, ...],
        "error": str | None}``. ``ok`` is False (ledger untouched) when
        ``resolution`` is blank, no unacked entry exists at all, or (sha12
        selector) no unacked entry's ``denied_sha12`` matches.
    """
    if not resolution or not resolution.strip():
        return {
            "ok": False, "acked": None, "deduped": [],
            "error": "resolution must be a non-empty audit note",
        }
    if now is None:
        now = time.time()
    entries = read_deny_ledger()

    target: dict | None = None
    if selector == "oldest":
        for entry in entries:
            if not entry.get("acked", False):
                target = entry
                break
    else:
        sel = selector.strip().lower()
        for entry in entries:
            if entry.get("acked", False):
                continue
            sha = str(entry.get("denied_sha12") or "")
            if sha and sha.lower().startswith(sel):
                target = entry
                break

    if target is None:
        return {
            "ok": False, "acked": None, "deduped": [],
            "error": f"no unacked deny-ledger entry matches selector {selector!r}",
        }

    resolution = resolution.strip()
    target["acked"] = True
    target["acked_ts"] = now
    target["ack_method"] = "manual-ack"
    target["resolution"] = resolution

    deduped: list[dict] = []
    cause_key = _deny_entry_same_cause_key(target)
    if cause_key is not None:
        for entry in entries:
            if entry is target or entry.get("acked", False):
                continue
            if _deny_entry_same_cause_key(entry) == cause_key:
                entry["acked"] = True
                entry["acked_ts"] = now
                entry["ack_method"] = "manual-ack-dedup"
                entry["resolution"] = (
                    f"same-cause dedup of the entry acked at {now}: {resolution}"
                )
                deduped.append(entry)

    try:
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        body = "".join(json.dumps(e) + "\n" for e in entries)
        _atomic_write(ledger_path, body)
    except Exception:  # noqa: BLE001
        return {
            "ok": False, "acked": None, "deduped": [],
            "error": "ledger rewrite failed",
        }
    return {"ok": True, "acked": target, "deduped": deduped, "error": None}
