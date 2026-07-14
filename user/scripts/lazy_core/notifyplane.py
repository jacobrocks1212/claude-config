"""lazy_core.notifyplane — the operator-halt notifier (ntfy channel).

Extracted VERBATIM from lazy_core/_monolith.py (lazy-core-package-decomposition
Phase 2, Batch 4, WU-4) — a move-only refactor with zero behavior change,
PLUS the operator-ratified (2026-07-13, Option C) retirement of the Phase-1
facade-patch resolver shim: `notify_halt`/`notify_event` now
resolve `_ntfy_send` as a plain module-global of THIS module (ordinary
mechanism-3 resolution), and every patcher — including the two state scripts'
`[notify-halt-call-site]` smoke fixtures — patches
`lazy_core.notifyplane._ntfy_send`. Mechanism-3 is the SINGLE
patch-visibility rule for all callers.

Owns notify config/ledger/error I/O, halt identity + dedup, payload
composition, the ntfy sender, and the notify_halt/notify_event entry points.
See the operator-halt-notifications feature docs for the D1-D10 ledger.

Sibling-seam dependencies are resolved via function-local deferred
imports (kept function-local so this module's import surface stays light):
`claude_state_dir` (`.statedir`) and `detect_noncanonical_blocker`
(`.docmodel`).
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import re
import subprocess
import time
from pathlib import Path

import yaml

from ._ctx import _atomic_write

# ---------------------------------------------------------------------------
# operator-halt-notifications — the script-owned halt notifier
# ---------------------------------------------------------------------------
#
# A NEEDS_INPUT.md/BLOCKED.md halt is honest but passive: it sits silently
# until the operator checks in.  notify_halt() pages the operator's phone at
# the terminal-emission chokepoint — called as ONE line by BOTH state scripts'
# main() immediately before the state-JSON write (D2; parity surface #7 in
# lazy_parity_audit.py).  Contracts (SPEC docs/features/operator-halt-notifications,
# all decisions operator-approved 2026-07-04):
#
#   D1  ntfy behind a minimal channel seam: notify_halt dispatches through an
#       injected `sender(title, body, link)` callable (hermetic tests inject a
#       fake); production binds _ntfy_send — one stdlib urllib POST to the
#       configured topic URL.
#   D3  Attention terminals only (_NOTIFY_ATTENTION_TERMINALS, the locked
#       11-terminal list) page by default; the 5 named clean stops
#       (_NOTIFY_CLEAN_STOP_TERMINALS) page only under notify_on_clean_stop.
#       NOTE: a sibling of SANCTIONED_STOP_TERMINAL, NOT its complement —
#       needs-research / queue-blocked-on-research / queue-missing are
#       sanctioned stops that still demand operator action.  The telemetry
#       TELEMETRY_HALT_TERMINAL_REASONS set is a DIFFERENT vocabulary
#       (halt-dwell recording) and deliberately not shared.
#   D4  Notify-once per sentinel identity (_notify_identity): sentinel-backed
#       terminals key on (pipeline, item, reason, mtime_ns, size) — a
#       --neutralize-sentinel rename retires the identity, a re-halt's new
#       sentinel re-arms; sentinel-less terminals key on the UTC date.
#   D5  Rich payload: title = notify_message verbatim; body = repo basename ·
#       pipeline · item · halt kind (+ needs-input `decisions:` one-liners via
#       a TOLERANT frontmatter read — parse_sentinel would _die() on a
#       malformed file, corrupting the halt JSON, so it is NOT used here);
#       link = the normalized GitHub remote + /tree/main/<item dir> (remote
#       derivation failure ⇒ link omitted, still send).
#   D7  Config: ~/.claude/notify.json (untracked; {channel, url,
#       notify_on_clean_stop, reping_hours}) with LAZY_NOTIFY_URL overriding
#       the url and LAZY_NOTIFY_DISABLE=1 as the kill switch.  Absent config ⇒
#       notify_halt is a COMPLETE no-op (byte-identical probe, zero writes).
#   D8  Dedup ledger notify-ledger.json in claude_state_dir() (per-repo keyed;
#       LAZY_STATE_DIR-hermetic), written via _atomic_write, entries older
#       than 30 days dropped on write; updated ONLY on a successful send.
#   D9  Fail-OPEN: nothing here may raise, print to stdout, or change the exit
#       code.  Send failure → notify-error.json breadcrumb (single overwritten
#       file, the hook-error.json pattern) + a "why no page" line appended to
#       state["diagnostics"] (the dict's own list — a _diag() call after
#       compute_state cannot reach the printed JSON), NO ledger entry (the
#       next observation retries).
#   D10 Environment-agnostic: no --cloud branch; cloud containers provision
#       LAZY_NOTIFY_URL via env.
# ---------------------------------------------------------------------------

_NOTIFY_CONFIG_FILENAME = "notify.json"          # under ~/.claude/ (untracked)
_NOTIFY_LEDGER_FILENAME = "notify-ledger.json"   # under claude_state_dir()
_NOTIFY_ERROR_FILENAME = "notify-error.json"     # under claude_state_dir()
# Same bound as _default_sidecar_probe / _default_frontend_probe (D9).
_NOTIFY_SEND_TIMEOUT_SECONDS = 5
_NOTIFY_LEDGER_MAX_AGE_SECONDS = 30 * 24 * 3600  # D8: 30-day prune on write

# D3 (locked 2026-07-04): the terminals where the operator's action is the
# unblocker — these page by default.
_NOTIFY_ATTENTION_TERMINALS: frozenset[str] = frozenset({
    "blocked",
    "blocked-misnamed",
    "needs-input",
    "needs-spec-input",
    "needs-research",
    "queue-blocked-on-research",
    "completion-unverified",
    "stale_upstream",
    "queue-exhausted-all-parked",
    "queue-exhausted-budget-deferred",
    "queue-missing",
})

# D3: clean run-end terminals — page ONLY when the config sets
# notify_on_clean_stop: true.  Everything in neither set never pages (e.g.
# queue-exhausted-dependency-gated: holds re-open by themselves as deps
# complete; scoped per-item terminals: the run continues past them).
_NOTIFY_CLEAN_STOP_TERMINALS: frozenset[str] = frozenset({
    "all-features-complete",
    "all-bugs-fixed",
    "cloud-queue-exhausted",
    "device-queue-exhausted",
    "host-capability-saturated",
})

# D4: terminal → candidate sentinel basenames (first existing wins) for the
# identity stat.  blocked-misnamed is special-cased onto the stray file via
# detect_noncanonical_blocker.
_NOTIFY_SENTINEL_CANDIDATES: dict[str, tuple[str, ...]] = {
    "blocked": ("BLOCKED.md",),
    "needs-input": ("NEEDS_INPUT.md",),
    "needs-research": ("NEEDS_RESEARCH.md", "RESEARCH_PROMPT.md"),
}


def _load_notify_config() -> dict | None:
    """Resolve the notifier config (D7), or None ⇒ the feature does not exist.

    Precedence: LAZY_NOTIFY_DISABLE truthy → None (kill switch, dominates
    everything); else merge ~/.claude/notify.json (when readable/valid — a
    malformed file degrades silently, fail-open) with the LAZY_NOTIFY_URL env
    override (env wins on `url`; file booleans survive).  No usable url ⇒
    None.  Never raises, never writes.
    """
    if os.environ.get("LAZY_NOTIFY_DISABLE"):
        return None
    cfg: dict = {}
    try:
        cfg_path = Path.home() / ".claude" / _NOTIFY_CONFIG_FILENAME
        if cfg_path.is_file():
            loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg.update(loaded)
    except Exception:  # noqa: BLE001 — malformed/unreadable file is fail-open
        pass
    env_url = os.environ.get("LAZY_NOTIFY_URL")
    if env_url:
        cfg["url"] = env_url
    url = cfg.get("url")
    if not isinstance(url, str) or not url.strip():
        return None
    cfg.setdefault("channel", "ntfy")
    cfg["notify_on_clean_stop"] = bool(cfg.get("notify_on_clean_stop"))
    return cfg


def _notify_sentinel_path(state: dict, terminal_reason: str) -> Path | None:
    """Resolve the halt's sentinel file from the state's spec_path (D4).

    Returns the first existing candidate for the terminal (the stray file for
    blocked-misnamed), or None for sentinel-less terminals (queue-missing,
    exhaustion terminals, needs-spec-input's empty dir, …).  Never raises.
    """
    from .docmodel import detect_noncanonical_blocker  # deferred (docmodel plane; function-local avoids import cycle)
    spec = state.get("spec_path")
    if not spec:
        return None
    try:
        spec_dir = Path(spec)
        if terminal_reason == "blocked-misnamed":
            return detect_noncanonical_blocker(spec_dir)
        for name in _NOTIFY_SENTINEL_CANDIDATES.get(terminal_reason, ()):
            candidate = spec_dir / name
            if candidate.is_file():
                return candidate
    except OSError:
        pass
    return None


def _notify_identity(state: dict, pipeline: str, *, now: float | None = None) -> str:
    """The D4 dedup key: one halt, one page, no matter how many probes see it.

    Sentinel-backed: ``{pipeline}|{item}|{reason}|{mtime_ns}|{size}`` — a
    rename (--neutralize-sentinel) kills the identity, a rewritten sentinel is
    a NEW identity (re-arm).  Sentinel-less: ``{pipeline}|{item}|{reason}|d:{UTC date}``
    (bounded: at most one page per day per such terminal).
    """
    reason = state.get("terminal_reason") or ""
    item = state.get("feature_id") or ""
    sentinel = _notify_sentinel_path(state, reason)
    if sentinel is not None:
        try:
            st = sentinel.stat()
            return f"{pipeline}|{item}|{reason}|{st.st_mtime_ns}|{st.st_size}"
        except OSError:
            pass
    ts = time.time() if now is None else float(now)
    day = datetime.datetime.fromtimestamp(
        ts, tz=datetime.timezone.utc
    ).strftime("%Y-%m-%d")
    return f"{pipeline}|{item}|{reason}|d:{day}"


def _load_notify_ledger() -> dict:
    """Read notify-ledger.json entries ({identity: {notified_at, …}}).

    Read-only (create=False — a probe that never sends must not create the
    state dir).  Corrupt/absent ⇒ {} (fail-open).
    """
    from .statedir import claude_state_dir  # re-pointed at WU-5 (statedir extraction)
    try:
        path = claude_state_dir(create=False) / _NOTIFY_LEDGER_FILENAME
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("entries") if isinstance(data, dict) else None
        return entries if isinstance(entries, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _record_notify_send(identity: str, state: dict, pipeline: str,
                        *, now: float | None = None) -> None:
    """Ledger a successful send (D8) via _atomic_write, pruning entries older
    than 30 days.  The schema is re-ping-ready: notified_at is the timestamp a
    future reping_hours key would compare against (D4-B, additive later)."""
    from .statedir import claude_state_dir  # re-pointed at WU-5 (statedir extraction)
    ts = time.time() if now is None else float(now)
    cutoff = ts - _NOTIFY_LEDGER_MAX_AGE_SECONDS
    entries = {
        k: v for k, v in _load_notify_ledger().items()
        if isinstance(v, dict)
        and isinstance(v.get("notified_at"), (int, float))
        and v["notified_at"] >= cutoff
    }
    entries[identity] = {
        "notified_at": ts,
        "pipeline": pipeline,
        "item_id": state.get("feature_id"),
        "terminal_reason": state.get("terminal_reason"),
    }
    payload = {"v": 1, "entries": entries}
    _atomic_write(
        claude_state_dir() / _NOTIFY_LEDGER_FILENAME,
        json.dumps(payload, indent=2) + "\n",
    )


def _write_notify_error(message: str, identity: str | None,
                        *, now: float | None = None) -> None:
    """Overwrite the notify-error.json breadcrumb (the hook-error.json
    pattern: a single at-a-glance 'why no page' file, D9)."""
    from .statedir import claude_state_dir  # re-pointed at WU-5 (statedir extraction)
    entry = {
        "ts": time.time() if now is None else float(now),
        "source": "notify_halt",
        "error": str(message)[:500],
        "identity": identity,
    }
    _atomic_write(
        claude_state_dir() / _NOTIFY_ERROR_FILENAME,
        json.dumps(entry, indent=2) + "\n",
    )


def _notify_decisions(sentinel_path: Path) -> list[str]:
    """Tolerant read of a NEEDS_INPUT.md frontmatter ``decisions:`` list (≤4).

    Deliberately NOT parse_sentinel: that helper _die()s (error JSON on stdout
    + exit 2) on a malformed file, which would corrupt the halt this notifier
    merely observes (D9).  Any problem ⇒ [] (notify without decision lines).
    """
    try:
        lines = sentinel_path.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines) or lines[i].strip() != "---":
            return []
        end = None
        for j in range(i + 1, len(lines)):
            if lines[j].strip() == "---":
                end = j
                break
        if end is None:
            return []
        data = yaml.safe_load("\n".join(lines[i + 1:end])) or {}
        if not isinstance(data, dict):
            return []
        decisions = data.get("decisions")
        if not isinstance(decisions, list):
            return []
        return [str(d).strip() for d in decisions if str(d).strip()][:4]
    except Exception:  # noqa: BLE001
        return []


def _normalize_git_remote_url(raw: str | None) -> str | None:
    """Normalize a git remote URL to a plain browsable http(s) URL (D5).

    Handles scp-style SSH (git@host:owner/repo.git), ssh:// (optional user +
    port), and http(s) (credentials stripped, .git suffix dropped).  Anything
    else (file://, empty, garbage) ⇒ None — the caller omits the link and
    still sends.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    m = re.match(r"^git@([^:/]+):(.+)$", raw)
    if m:
        raw = f"https://{m.group(1)}/{m.group(2)}"
    elif raw.startswith("ssh://"):
        m2 = re.match(r"^ssh://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", raw)
        if not m2:
            return None
        raw = f"https://{m2.group(1)}/{m2.group(2)}"
    if not (raw.startswith("http://") or raw.startswith("https://")):
        return None
    scheme, rest = raw.split("://", 1)
    authority, _, tail = rest.partition("/")
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]  # strip credentials
    raw = f"{scheme}://{authority}" + (f"/{tail}" if tail else "")
    if raw.endswith(".git"):
        raw = raw[: -len(".git")]
    return raw.rstrip("/")


def _github_remote_url(repo_root: str) -> str | None:
    """``git config --get remote.origin.url`` → normalized URL, or None."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "config", "--get",
             "remote.origin.url"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode != 0:
            return None
        return _normalize_git_remote_url(proc.stdout.strip())
    except Exception:  # noqa: BLE001
        return None


def _compose_notify_payload(state: dict, repo_root: str,
                            pipeline: str) -> tuple[str, str, str | None]:
    """Build the D5 rich payload: (title, body, link).

    title = the script's composed notify_message verbatim (already
    item-naming); body = repo basename · pipeline · item · halt kind, the
    needs-input ``decisions:`` one-liners, and the LAZY_QUEUE/answer-path
    pointer; link = normalized remote + /tree/main/<item dir> (None when the
    remote cannot be derived — omit link, still send).
    """
    reason = state.get("terminal_reason") or ""
    title = state.get("notify_message") or f"PIPELINE HALT: {reason}"
    try:
        repo_name = Path(repo_root).name or str(repo_root)
    except Exception:  # noqa: BLE001
        repo_name = str(repo_root)
    item = state.get("feature_id") or "(no item)"
    body_lines = [f"{repo_name} · {pipeline} · {item} · {reason}"]
    if reason == "needs-input":
        sentinel = _notify_sentinel_path(state, reason)
        if sentinel is not None:
            for n, decision in enumerate(_notify_decisions(sentinel), 1):
                body_lines.append(f"{n}. {decision}")
    body_lines.append(
        "Queue: LAZY_QUEUE.md · answer in the Claude app / next session"
    )
    link = None
    base = _github_remote_url(repo_root)
    if base:
        link = base
        spec = state.get("spec_path")
        if spec:
            try:
                rel = Path(spec).resolve().relative_to(
                    Path(repo_root).resolve()
                ).as_posix()
                link = f"{base}/tree/main/{rel}"
            except Exception:  # noqa: BLE001 — spec outside root → repo link
                pass
    return title, "\n".join(body_lines), link


def _rfc2047_header(value: str) -> str:
    """Encode a header value as RFC 2047 UTF-8 Base64 when it is not
    latin-1-safe (http.client raises UnicodeEncodeError otherwise — and
    notify_message strings routinely carry em-dashes).  ntfy documents RFC
    2047 support for its Title/Click headers.  Latin-1-safe values pass
    through verbatim."""
    try:
        value.encode("latin-1")
        return value
    except UnicodeEncodeError:
        import base64
        encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
        return f"=?UTF-8?B?{encoded}?="


def _ntfy_send(url: str, title: str, body: str, link: str | None = None) -> None:
    """The v1 ntfy channel (D1): one stdlib urllib POST to the topic URL —
    message = body, Title/Click headers, timeout=5.  Raises on failure (the
    notify_halt wrapper owns fail-OPEN)."""
    import urllib.request
    headers = {"Title": _rfc2047_header(" ".join(title.split()))}
    if link:
        headers["Click"] = _rfc2047_header(link.strip())
    req = urllib.request.Request(
        url, data=body.encode("utf-8"), headers=headers, method="POST",
    )
    with urllib.request.urlopen(  # noqa: S310 — operator-configured URL
        req, timeout=_NOTIFY_SEND_TIMEOUT_SECONDS
    ) as resp:
        resp.read()


def notify_halt(state: dict, repo_root: str, *, pipeline: str = "feature",
                sender=None, now: float | None = None) -> None:
    """Page the operator about an attention-terminal halt.  Fail-OPEN observer:
    NEVER raises, never prints to stdout, never changes the exit code, and is
    a complete no-op (zero writes, state dict untouched) without config.

    Called by BOTH state scripts' main() immediately before the state-JSON
    write (D2 — the one chokepoint every halt passes through; parity-audited).
    ``sender(title, body, link)`` is the injected channel seam (tests inject a
    fake; production binds _ntfy_send to the configured topic URL).
    """
    identity: str | None = None
    try:
        config = _load_notify_config()
        if config is None:
            return  # D7: absent config ⇒ the feature does not exist.
        reason = state.get("terminal_reason")
        if not reason:
            return  # forward routes never page
        if reason in _NOTIFY_ATTENTION_TERMINALS:
            pass
        elif (reason in _NOTIFY_CLEAN_STOP_TERMINALS
                and config.get("notify_on_clean_stop")):
            pass
        else:
            return  # D3: everything else never pages
        identity = _notify_identity(state, pipeline, now=now)
        if identity in _load_notify_ledger():
            return  # D4: already paged this halt
        title, body, link = _compose_notify_payload(state, repo_root, pipeline)
        if sender is None:
            url = config["url"]
            def sender(t, b, l, _url=url):  # noqa: E731 — production binding
                _ntfy_send(_url, t, b, l)
        diagnostics = state.get("diagnostics")
        try:
            sender(title, body, link)
        except Exception as send_exc:  # noqa: BLE001 — D9 fail-OPEN
            _write_notify_error(
                f"{send_exc.__class__.__name__}: {send_exc}", identity, now=now,
            )
            if isinstance(diagnostics, list):
                diagnostics.append(
                    "notify_halt: send failed "
                    f"({send_exc.__class__.__name__}: {send_exc}) — "
                    "notify-error.json written; halt unaffected, "
                    "no ledger entry (next observation retries)"
                )
            return
        _record_notify_send(identity, state, pipeline, now=now)
        if isinstance(diagnostics, list):
            diagnostics.append(
                f"notify_halt: paged terminal_reason={reason} "
                "(recorded in notify-ledger.json)"
            )
    except Exception as exc:  # noqa: BLE001 — D9: nothing may propagate
        try:
            _write_notify_error(
                f"internal error: {exc.__class__.__name__}: {exc}",
                identity, now=now,
            )
        except Exception:  # noqa: BLE001 — even the breadcrumb is best-effort
            pass


def notify_event(
    kind: str,
    message: str,
    repo_root: str,
    *,
    pipeline: str = "feature",
    item_id: str | None = None,
    detail: str | None = None,
    sender=None,
    now: float | None = None,
) -> None:
    """mechanize-prose-only-orchestrator-contracts (d) / D4-A: generalize the
    ``notify_halt`` seam to non-halt event points — parks, budget-guard
    trip/extension, the run-end flush, and provisional-accepts (SPEC §1c.6
    points that previously paged only when the ORCHESTRATOR remembered to
    call ``PushNotification``).

    Unlike ``notify_halt`` (which observes ``state["terminal_reason"]`` at
    the ONE terminal-emission chokepoint every halt passes through),
    ``notify_event`` is called INLINE at the exact state-transition site that
    OBSERVES a park / budget-guard / flush / provisional-accept event — so
    the page can no longer be forgotten by orchestrator prose. It reuses
    every piece of ``notify_halt``'s infrastructure (config, ledger, error
    breadcrumb, ntfy sender) — one notifier, two call shapes.

    Dedup identity is CONTENT-based: ``event|{kind}|{pipeline}|{item_id}|
    {detail}`` — no timestamp component, so a REPEATED observation of the
    SAME event (e.g. re-probing a still-parked feature on every subsequent
    cycle) never double-pages; a genuinely NEW event (a different item, or
    the same item with different detail) gets its own identity and pages
    once. This mirrors notify_halt's D4 dedup precedent without needing a
    sentinel-mtime or day-bucket fallback (there is no sentinel to key on for
    a park/budget/flush event in general).

    Fail-OPEN, same absolute contract as notify_halt: never raises, never
    prints to stdout, never changes any caller's return value or exit code,
    and is a COMPLETE no-op (zero writes) without ``~/.claude/notify.json`` /
    ``LAZY_NOTIFY_URL`` configured.

    Args:
        kind: the event kind tag (e.g. "park", "budget-trip",
            "budget-extension", "flush", "provisional-accept") — becomes
            part of the dedup identity and the notification body.
        message: the notification TITLE (event-specific, caller-composed).
        repo_root: the repo this event occurred in (for the body/link).
        pipeline: "feature" or "bug".
        item_id: the feature/bug id this event concerns, if any.
        detail: optional extra body text (e.g. a park reason, a budget
            ceiling, a flush summary line).
        sender: injected ``sender(title, body, link)`` seam (tests inject a
            fake; production binds ``_ntfy_send`` to the configured topic).
        now: epoch float (injectable for hermetic tests).
    """
    identity: str | None = None
    try:
        config = _load_notify_config()
        if config is None:
            return  # D7 precedent: absent config ⇒ the feature does not exist.
        identity = f"event|{kind}|{pipeline}|{item_id or ''}|{detail or ''}"
        if identity in _load_notify_ledger():
            return  # exactly-once per distinct event
        try:
            repo_name = Path(repo_root).name or str(repo_root)
        except Exception:  # noqa: BLE001
            repo_name = str(repo_root)
        title = message
        body_lines = [f"{repo_name} · {pipeline} · {item_id or '(no item)'} · {kind}"]
        if detail:
            body_lines.append(detail)
        body = "\n".join(body_lines)
        link = _github_remote_url(repo_root)
        if sender is None:
            url = config["url"]
            def sender(t, b, l, _url=url):  # noqa: E731 — production binding
                _ntfy_send(_url, t, b, l)
        try:
            sender(title, body, link)
        except Exception as send_exc:  # noqa: BLE001 — fail-OPEN
            _write_notify_error(
                f"{send_exc.__class__.__name__}: {send_exc}", identity, now=now,
            )
            return
        # Reuse the ONE ledger schema/writer notify_halt uses — a synthetic
        # state dict carries this event's identity fields into the same
        # notify-ledger.json (terminal_reason repurposed to hold `kind`).
        _record_notify_send(
            identity, {"feature_id": item_id, "terminal_reason": kind},
            pipeline, now=now,
        )
    except Exception as exc:  # noqa: BLE001 — nothing may propagate
        try:
            _write_notify_error(
                f"internal error: {exc.__class__.__name__}: {exc}",
                identity, now=now,
            )
        except Exception:  # noqa: BLE001 — even the breadcrumb is best-effort
            pass
