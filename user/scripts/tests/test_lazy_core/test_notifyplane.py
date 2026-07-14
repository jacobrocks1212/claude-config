#!/usr/bin/env python3
"""
test_notifyplane.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_notifyplane.py
Exit 0 on pass, non-zero on any failure. No third-party dependencies.
"""

from __future__ import annotations

import ast
import difflib
import inspect
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# This file lives 2 directories deeper than the original flat
# test_lazy_core.py (user/scripts/tests/test_lazy_core/ vs. user/scripts/),
# so parents[2] is the scripts dir where lazy_core/ actually lives:
# parents[0]=test_lazy_core/, parents[1]=tests/, parents[2]=user/scripts.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))



from _util import _ModuleMissing, _clear_state_dir, _set_state_dir  # noqa: E402




# ---------------------------------------------------------------------------
# Attempt the import — RED today, GREEN after extraction.
# ---------------------------------------------------------------------------

_IMPORT_ERROR: Exception | None = None


lazy_core = None



try:
    import lazy_core  # type: ignore[import]
except ImportError as exc:
    _IMPORT_ERROR = exc




# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

_FAILURES: list[str] = []


_PASSES: list[str] = []




def _guard() -> None:
    """Raise _ModuleMissing if lazy_core hasn't been extracted yet.

    Call at the top of every test function so that, while in RED state, each
    test cleanly fails with a consistent reason rather than an AttributeError
    on the None module.
    """
    if _IMPORT_ERROR is not None:
        raise _ModuleMissing(f"lazy_core not importable: {_IMPORT_ERROR}")




def _run_test(name: str, fn) -> None:
    """Run a single test, recording PASS or FAIL."""
    try:
        fn()
        _PASSES.append(name)
        print(f"  PASS  {name}")
    except _ModuleMissing as exc:
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")
    except AssertionError as exc:
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")





# ===========================================================================
# operator-halt-notifications — script-owned halt notifier (Phases 1-2)
# ===========================================================================
#
# lazy_core.notify_halt(state, repo_root, *, pipeline, sender=None, now=None)
# is the fail-OPEN, config-gated, dedup-ledgered operator pager called by both
# state scripts at the terminal-emission chokepoint. Hermetic discipline:
# LAZY_STATE_DIR temp dirs (ledger/breadcrumb), a temp HOME (config file), and
# explicit LAZY_NOTIFY_URL / LAZY_NOTIFY_DISABLE env control via
# _notify_push_env/_notify_pop_env. NO test here performs network I/O — the
# sender is always injected (the SPEC's injected-collaborator seam) or urlopen
# is monkeypatched.
# ---------------------------------------------------------------------------

def _notify_push_env(**pairs):
    """Set/clear env vars; return the saved prior values for _notify_pop_env."""
    saved = {k: os.environ.get(k) for k in pairs}
    for k, v in pairs.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return saved




def _notify_pop_env(saved) -> None:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v




def _notify_halt_state(td: Path, *, terminal_reason="needs-input",
                       feature_id="feat-n", with_sentinel=True,
                       decisions=None) -> dict:
    """Build a minimal halt-state dict + on-disk item dir under td."""
    spec_dir = td / "docs" / "features" / feature_id
    spec_dir.mkdir(parents=True, exist_ok=True)
    if with_sentinel and terminal_reason == "needs-input":
        ds = decisions if decisions is not None else ["Pick channel", "Pick scope"]
        lines = ["---", "kind: needs-input", f"feature_id: {feature_id}",
                 "written_by: spec", "decisions:"]
        lines += [f"  - {d}" for d in ds]
        lines += ["date: 2026-07-04", "---", "", "## Decision Context", "body"]
        (spec_dir / "NEEDS_INPUT.md").write_text("\n".join(lines) + "\n",
                                                 encoding="utf-8")
    if with_sentinel and terminal_reason == "blocked":
        (spec_dir / "BLOCKED.md").write_text(
            "---\nkind: blocked\nfeature_id: " + feature_id +
            "\nphase: x\nblocked_at: 2026-07-04T00:00:00Z\nretry_count: 0\n---\n",
            encoding="utf-8",
        )
    return {
        "feature_id": feature_id,
        "feature_name": feature_id,
        "spec_path": str(spec_dir),
        "current_step": "Step 3.5: needs-input",
        "sub_skill": None,
        "sub_skill_args": None,
        "terminal_reason": terminal_reason,
        "notify_message": f"NEEDS INPUT: {feature_id} — spec halted on an ambiguous decision.",
        "diagnostics": [],
    }




def test_notify_symbols_present():
    """All operator-halt-notifications Phase 1 symbols exist; the D3 locked
    attention set is EXACTLY the 11 approved terminals; the clean-stop opt-in
    set is EXACTLY the 5 named clean stops; the attention set is NOT the
    complement of SANCTIONED_STOP_TERMINAL (needs-research is in both)."""
    _guard()
    expected = [
        "_NOTIFY_ATTENTION_TERMINALS",
        "_NOTIFY_CLEAN_STOP_TERMINALS",
        "_NOTIFY_CONFIG_FILENAME",
        "_NOTIFY_LEDGER_FILENAME",
        "_NOTIFY_ERROR_FILENAME",
        "_NOTIFY_SEND_TIMEOUT_SECONDS",
        "_load_notify_config",
        "_notify_identity",
        "_load_notify_ledger",
        "_compose_notify_payload",
        "_normalize_git_remote_url",
        "_ntfy_send",
        "_rfc2047_header",
        "notify_halt",
    ]
    missing = [s for s in expected if not hasattr(lazy_core, s)]
    assert not missing, f"missing notify symbols: {missing}"
    assert lazy_core.notifyplane._NOTIFY_ATTENTION_TERMINALS == frozenset({
        "blocked", "blocked-misnamed", "needs-input", "needs-spec-input",
        "needs-research", "queue-blocked-on-research", "completion-unverified",
        "stale_upstream", "queue-exhausted-all-parked",
        "queue-exhausted-budget-deferred", "queue-missing",
    }), lazy_core.notifyplane._NOTIFY_ATTENTION_TERMINALS
    assert lazy_core.notifyplane._NOTIFY_CLEAN_STOP_TERMINALS == frozenset({
        "all-features-complete", "all-bugs-fixed", "cloud-queue-exhausted",
        "device-queue-exhausted", "host-capability-saturated",
    }), lazy_core.notifyplane._NOTIFY_CLEAN_STOP_TERMINALS
    # Sibling-not-complement (SPEC Technical Design): sanctioned stops that
    # still demand operator action ARE attention terminals.
    for r in ("needs-research", "queue-blocked-on-research", "queue-missing"):
        assert r in lazy_core.SANCTIONED_STOP_TERMINAL
        assert r in lazy_core.notifyplane._NOTIFY_ATTENTION_TERMINALS
    # queue-exhausted-dependency-gated is deliberately in NEITHER set (holds
    # re-open by themselves as deps complete).
    assert "queue-exhausted-dependency-gated" not in lazy_core.notifyplane._NOTIFY_ATTENTION_TERMINALS
    assert "queue-exhausted-dependency-gated" not in lazy_core.notifyplane._NOTIFY_CLEAN_STOP_TERMINALS
    assert lazy_core.notifyplane._NOTIFY_SEND_TIMEOUT_SECONDS == 5
    assert lazy_core.notifyplane._NOTIFY_CONFIG_FILENAME == "notify.json"
    assert lazy_core.notifyplane._NOTIFY_LEDGER_FILENAME == "notify-ledger.json"
    assert lazy_core.notifyplane._NOTIFY_ERROR_FILENAME == "notify-error.json"




def test_notify_config_precedence():
    """D7: absent → None; LAZY_NOTIFY_DISABLE kills everything; LAZY_NOTIFY_URL
    alone configures; file alone configures; env url OVERRIDES the file url but
    keeps the file's notify_on_clean_stop; malformed file degrades to env-only
    (fail-open, never raises)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        (home / ".claude").mkdir(parents=True)
        saved = _notify_push_env(HOME=str(home), USERPROFILE=str(home),
                                 LAZY_NOTIFY_URL=None, LAZY_NOTIFY_DISABLE=None)
        try:
            # 1) absent both → None (the feature does not exist).
            assert lazy_core._load_notify_config() is None
            # 2) env url alone → config with that url.
            os.environ["LAZY_NOTIFY_URL"] = "https://ntfy.sh/env-topic"
            cfg = lazy_core._load_notify_config()
            assert cfg is not None and cfg["url"] == "https://ntfy.sh/env-topic"
            assert cfg.get("notify_on_clean_stop") is False
            # 3) kill switch dominates everything.
            os.environ["LAZY_NOTIFY_DISABLE"] = "1"
            assert lazy_core._load_notify_config() is None
            os.environ.pop("LAZY_NOTIFY_DISABLE")
            # 4) file alone.
            os.environ.pop("LAZY_NOTIFY_URL")
            cfg_path = home / ".claude" / "notify.json"
            cfg_path.write_text(json.dumps({
                "channel": "ntfy", "url": "https://ntfy.sh/file-topic",
                "notify_on_clean_stop": True,
            }), encoding="utf-8")
            cfg = lazy_core._load_notify_config()
            assert cfg is not None and cfg["url"] == "https://ntfy.sh/file-topic"
            assert cfg["notify_on_clean_stop"] is True
            # 5) env url overrides the file url; file booleans survive.
            os.environ["LAZY_NOTIFY_URL"] = "https://ntfy.sh/env-topic"
            cfg = lazy_core._load_notify_config()
            assert cfg is not None and cfg["url"] == "https://ntfy.sh/env-topic"
            assert cfg["notify_on_clean_stop"] is True
            # 6) malformed file → fail-open: env-only config, no raise.
            cfg_path.write_text("{not json", encoding="utf-8")
            cfg = lazy_core._load_notify_config()
            assert cfg is not None and cfg["url"] == "https://ntfy.sh/env-topic"
            # 7) malformed file + no env → None (still no raise).
            os.environ.pop("LAZY_NOTIFY_URL")
            assert lazy_core._load_notify_config() is None
        finally:
            _notify_pop_env(saved)




def test_notify_identity_sentinel_and_dateless():
    """D4/D8: sentinel-backed terminals key on (pipeline, item, reason,
    mtime_ns, size) — a rewrite is a NEW identity; sentinel-less terminals key
    on the date; blocked-misnamed keys on the stray file."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state = _notify_halt_state(td_path)
        id1 = lazy_core._notify_identity(state, "feature")
        id2 = lazy_core._notify_identity(state, "feature")
        assert id1 == id2, "same sentinel bytes → stable identity"
        assert id1.startswith("feature|feat-n|needs-input|"), id1
        assert lazy_core._notify_identity(state, "bug") != id1, "pipeline is part of the key"
        # Rewrite the sentinel (different size ⇒ different identity even if
        # mtime granularity is coarse).
        sp = td_path / "docs" / "features" / "feat-n" / "NEEDS_INPUT.md"
        sp.write_text(sp.read_text(encoding="utf-8") + "\nmore body\n",
                      encoding="utf-8")
        id3 = lazy_core._notify_identity(state, "feature")
        assert id3 != id1, "sentinel rewrite must refresh the identity"
        # Sentinel-less terminal (queue-missing) → date-keyed.
        qm_state = {"feature_id": None, "spec_path": None,
                    "terminal_reason": "queue-missing", "diagnostics": []}
        idq = lazy_core._notify_identity(qm_state, "feature", now=1750000000.0)
        assert idq == "feature||queue-missing|d:2025-06-15", idq
        # blocked-misnamed → the stray file is the identity carrier.
        stray_dir = td_path / "docs" / "features" / "feat-stray"
        stray_dir.mkdir(parents=True)
        (stray_dir / "BLOCKED_2026-07-04-foo.md").write_text(
            "---\nkind: blocked\n---\n", encoding="utf-8")
        ms = {"feature_id": "feat-stray", "spec_path": str(stray_dir),
              "terminal_reason": "blocked-misnamed", "diagnostics": []}
        idm = lazy_core._notify_identity(ms, "feature")
        assert idm.startswith("feature|feat-stray|blocked-misnamed|"), idm
        assert "|d:" not in idm, "stray file present → stat-keyed, not date-keyed"




def test_notify_ledger_roundtrip_prune_and_atomic():
    """D8: the ledger lives at claude_state_dir()/notify-ledger.json, is
    written via lazy_core.notifyplane._atomic_write, and drops entries older than 30 days
    on write; a corrupt ledger reads as empty (fail-open)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now = 1751600000.0
            assert lazy_core._load_notify_ledger() == {}
            # Spy on _atomic_write to prove the ledger write goes through it.
            real_aw = lazy_core.notifyplane._atomic_write
            written: list = []

            def _spy(path, content):
                written.append(Path(path).name)
                real_aw(path, content)

            lazy_core.notifyplane._atomic_write = _spy
            try:
                lazy_core._record_notify_send(
                    "feature|a|needs-input|1|2",
                    {"feature_id": "a", "terminal_reason": "needs-input"},
                    "feature", now=now - (40 * 86400),
                )
                lazy_core._record_notify_send(
                    "feature|b|blocked|3|4",
                    {"feature_id": "b", "terminal_reason": "blocked"},
                    "feature", now=now,
                )
            finally:
                lazy_core.notifyplane._atomic_write = real_aw
            assert written == ["notify-ledger.json", "notify-ledger.json"], written
            entries = lazy_core._load_notify_ledger()
            # The 40-day-old entry was pruned by the second write.
            assert set(entries) == {"feature|b|blocked|3|4"}, entries
            assert entries["feature|b|blocked|3|4"]["notified_at"] == now
            # Corrupt ledger → {} (never raises).
            (Path(td) / "notify-ledger.json").write_text("{corrupt",
                                                         encoding="utf-8")
            assert lazy_core._load_notify_ledger() == {}
        finally:
            _clear_state_dir()




def test_notify_remote_url_normalization():
    """D5: SSH / ssh:// / HTTPS (+credentials, +.git) remote forms normalize to
    a plain https URL; garbage → None (omit link, still send)."""
    _guard()
    cases = [
        ("git@github.com:owner/repo.git", "https://github.com/owner/repo"),
        ("git@github.com:owner/repo", "https://github.com/owner/repo"),
        ("ssh://git@github.com/owner/repo.git", "https://github.com/owner/repo"),
        ("ssh://git@github.com:22/owner/repo.git", "https://github.com/owner/repo"),
        ("https://github.com/owner/repo.git", "https://github.com/owner/repo"),
        ("https://user@github.com/owner/repo.git", "https://github.com/owner/repo"),
        ("http://local_proxy@127.0.0.1:41729/git/owner/repo",
         "http://127.0.0.1:41729/git/owner/repo"),
        ("", None),
        ("   ", None),
        ("file:///c/repos/x", None),
    ]
    for raw, want in cases:
        got = lazy_core._normalize_git_remote_url(raw)
        assert got == want, f"{raw!r} → {got!r}, want {want!r}"




def test_notify_payload_rich_shape():
    """D5: title = notify_message verbatim; body = repo · pipeline · item ·
    kind + needs-input decision one-liners (≤4) + the LAZY_QUEUE/answer-path
    pointer; link = normalized remote + /tree/main/<item dir>; no remote ⇒
    link None (still composes); malformed sentinel ⇒ no decision lines
    (tolerant read — never dies)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state = _notify_halt_state(
            td_path, decisions=["One", "Two", "Three", "Four", "Five"])
        # A real git repo with a github-style remote.
        subprocess.run(["git", "init", "-q", str(td_path)], check=True)
        subprocess.run(["git", "-C", str(td_path), "remote", "add", "origin",
                        "git@github.com:owner/claude-config.git"], check=True)
        title, body, link = lazy_core._compose_notify_payload(
            state, str(td_path), "feature")
        assert title == state["notify_message"], title
        lines = body.splitlines()
        assert lines[0] == f"{td_path.name} · feature · feat-n · needs-input", lines
        # decisions capped at 4 (schema max), numbered.
        assert lines[1:5] == ["1. One", "2. Two", "3. Three", "4. Four"], lines
        assert "5." not in body
        assert lines[-1] == "Queue: LAZY_QUEUE.md · answer in the Claude app / next session"
        assert link == ("https://github.com/owner/claude-config/tree/main/"
                        "docs/features/feat-n"), link
        # Malformed sentinel → tolerant: no decision lines, still a payload.
        sp = td_path / "docs" / "features" / "feat-n" / "NEEDS_INPUT.md"
        sp.write_text("---\n: not yaml : [\n---\nbody\n", encoding="utf-8")
        _t2, body2, _l2 = lazy_core._compose_notify_payload(
            state, str(td_path), "feature")
        assert "1." not in body2, body2
    with tempfile.TemporaryDirectory() as td2:
        # No git repo at all → link None, payload still composed.
        state2 = _notify_halt_state(Path(td2))
        t3, _b3, l3 = lazy_core._compose_notify_payload(state2, td2, "feature")
        assert t3 == state2["notify_message"]
        assert l3 is None




def test_notify_halt_inert_without_config():
    """SPEC Validation row 2: no config/env ⇒ notify_halt is a COMPLETE no-op —
    the state dict is deep-equal untouched, the state dir gains no files, and
    the injected sender is never called."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        home = td_path / "home"
        (home / ".claude").mkdir(parents=True)
        saved = _notify_push_env(HOME=str(home), USERPROFILE=str(home),
                                 LAZY_NOTIFY_URL=None, LAZY_NOTIFY_DISABLE=None)
        try:
            state = _notify_halt_state(td_path)
            import copy
            before = copy.deepcopy(state)
            calls: list = []
            for _ in range(3):
                lazy_core.notify_halt(
                    state, str(td_path), pipeline="feature",
                    sender=lambda t, b, l: calls.append((t, b, l)))
            assert calls == [], "no config → sender never invoked"
            assert state == before, "inert path must not mutate the state dict"
            assert list(state_dir.iterdir()) == [], "inert path writes nothing"
            # The kill switch is equally inert even WITH a url present.
            os.environ["LAZY_NOTIFY_URL"] = "https://ntfy.sh/x"
            os.environ["LAZY_NOTIFY_DISABLE"] = "1"
            lazy_core.notify_halt(state, str(td_path), pipeline="feature",
                                  sender=lambda t, b, l: calls.append(1))
            assert calls == [] and state == before
            assert list(state_dir.iterdir()) == []
        finally:
            _notify_pop_env(saved)
            _clear_state_dir()




def test_notify_halt_attention_gating_and_clean_stop_optin():
    """D3: attention terminals page; clean stops page ONLY under
    notify_on_clean_stop; non-terminal states and unlisted terminals never
    page (queue-exhausted-dependency-gated stays silent even with the opt-in)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        home = td_path / "home"
        (home / ".claude").mkdir(parents=True)
        saved = _notify_push_env(HOME=str(home), USERPROFILE=str(home),
                                 LAZY_NOTIFY_URL="https://ntfy.sh/t",
                                 LAZY_NOTIFY_DISABLE=None)
        try:
            calls: list = []
            sender = lambda t, b, l: calls.append(t)  # noqa: E731
            # (a) a forward-route state (no terminal) never pages.
            route = {"feature_id": "f", "spec_path": None, "sub_skill": "spec",
                     "terminal_reason": None, "notify_message": None,
                     "diagnostics": []}
            lazy_core.notify_halt(route, str(td_path), pipeline="feature",
                                  sender=sender)
            assert calls == []
            # (b) clean stop without opt-in → silent.
            done = {"feature_id": None, "spec_path": None, "sub_skill": None,
                    "terminal_reason": "all-features-complete",
                    "notify_message": "All features complete.",
                    "diagnostics": []}
            lazy_core.notify_halt(done, str(td_path), pipeline="feature",
                                  sender=sender)
            assert calls == []
            # (c) clean stop WITH opt-in (file config) → pages once.
            (home / ".claude" / "notify.json").write_text(json.dumps({
                "url": "https://ntfy.sh/t", "notify_on_clean_stop": True,
            }), encoding="utf-8")
            lazy_core.notify_halt(done, str(td_path), pipeline="feature",
                                  sender=sender)
            assert len(calls) == 1, calls
            # (d) dependency-gated exhaustion is in NEITHER set → silent even
            # with the opt-in on.
            dep = dict(done, terminal_reason="queue-exhausted-dependency-gated")
            lazy_core.notify_halt(dep, str(td_path), pipeline="feature",
                                  sender=sender)
            assert len(calls) == 1, calls
            # (e) attention terminal pages regardless of the opt-in.
            state = _notify_halt_state(td_path)
            lazy_core.notify_halt(state, str(td_path), pipeline="feature",
                                  sender=sender)
            assert len(calls) == 2, calls
        finally:
            _notify_pop_env(saved)
            _clear_state_dir()




def test_notify_halt_dedup_and_identity_refresh():
    """SPEC Validation rows 1+4: one halt pages exactly once across repeated
    probes (ledger holds one entry); neutralizing the sentinel and writing a
    NEW one re-arms (second send, new identity)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        home = td_path / "home"
        (home / ".claude").mkdir(parents=True)
        saved = _notify_push_env(HOME=str(home), USERPROFILE=str(home),
                                 LAZY_NOTIFY_URL="https://ntfy.sh/t",
                                 LAZY_NOTIFY_DISABLE=None)
        try:
            state = _notify_halt_state(td_path)
            calls: list = []
            sender = lambda t, b, l: calls.append((t, b, l))  # noqa: E731
            for _ in range(3):
                lazy_core.notify_halt(state, str(td_path), pipeline="feature",
                                      sender=sender)
            assert len(calls) == 1, f"one halt must page exactly once, got {len(calls)}"
            assert len(lazy_core._load_notify_ledger()) == 1
            # Resolution: neutralize (rename) the sentinel → dead identity;
            # a re-halt writes a NEW sentinel → new identity → new page.
            sp = td_path / "docs" / "features" / "feat-n" / "NEEDS_INPUT.md"
            sp.rename(sp.with_name("NEEDS_INPUT_RESOLVED_2026-07-04.md"))
            sp.write_text("---\nkind: needs-input\nfeature_id: feat-n\n"
                          "written_by: spec\ndecisions:\n  - New question\n"
                          "date: 2026-07-05\n---\nfresh halt body\n",
                          encoding="utf-8")
            lazy_core.notify_halt(state, str(td_path), pipeline="feature",
                                  sender=sender)
            assert len(calls) == 2, "a re-halt (new sentinel) must page again"
            assert len(lazy_core._load_notify_ledger()) == 2
        finally:
            _notify_pop_env(saved)
            _clear_state_dir()




def test_notify_halt_fail_open_breadcrumb_and_retry():
    """D9: a raising sender never propagates, never mutates terminal fields;
    notify-error.json is written; NO ledger entry is recorded (so the next
    observation retries); a 'why no page' line lands in state['diagnostics'];
    a later successful send records the ledger entry."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        home = td_path / "home"
        (home / ".claude").mkdir(parents=True)
        saved = _notify_push_env(HOME=str(home), USERPROFILE=str(home),
                                 LAZY_NOTIFY_URL="https://ntfy.sh/t",
                                 LAZY_NOTIFY_DISABLE=None)
        try:
            state = _notify_halt_state(td_path)

            def _boom(t, b, l):
                raise OSError("connection refused")

            lazy_core.notify_halt(state, str(td_path), pipeline="feature",
                                  sender=_boom)  # must NOT raise
            assert state["terminal_reason"] == "needs-input"
            assert state["notify_message"].startswith("NEEDS INPUT")
            crumb = state_dir / "notify-error.json"
            assert crumb.exists(), "send failure must write notify-error.json"
            crumb_data = json.loads(crumb.read_text(encoding="utf-8"))
            assert "connection refused" in crumb_data.get("error", "")
            assert lazy_core._load_notify_ledger() == {}, \
                "failed send must NOT be ledgered (retry on next observation)"
            assert any("notify" in d for d in state["diagnostics"]), \
                state["diagnostics"]
            # Retry path: next observation with a working sender sends + ledgers.
            calls: list = []
            lazy_core.notify_halt(state, str(td_path), pipeline="feature",
                                  sender=lambda t, b, l: calls.append(t))
            assert len(calls) == 1
            assert len(lazy_core._load_notify_ledger()) == 1
        finally:
            _notify_pop_env(saved)
            _clear_state_dir()




def test_notify_event_inert_without_config():
    """mechanize-prose-only-orchestrator-contracts (d): notify_event is a
    COMPLETE no-op — sender never invoked, zero writes — without config."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        home = td_path / "home"
        (home / ".claude").mkdir(parents=True)
        saved = _notify_push_env(HOME=str(home), USERPROFILE=str(home),
                                 LAZY_NOTIFY_URL=None, LAZY_NOTIFY_DISABLE=None)
        try:
            calls: list = []
            lazy_core.notify_event(
                "park", "feat-x parked", str(td_path), item_id="feat-x",
                sender=lambda t, b, l: calls.append((t, b, l)),
            )
            assert calls == []
            assert list(state_dir.iterdir()) == []
        finally:
            _notify_pop_env(saved)
            _clear_state_dir()




def test_notify_event_dedup_exactly_once_and_distinguishes_events():
    """D — exactly-once dedup: the SAME (kind, pipeline, item_id, detail)
    observed repeatedly pages only ONCE; a DIFFERENT item (or different
    detail) is a distinct identity and pages again."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        home = td_path / "home"
        (home / ".claude").mkdir(parents=True)
        saved = _notify_push_env(HOME=str(home), USERPROFILE=str(home),
                                 LAZY_NOTIFY_URL="https://ntfy.sh/t",
                                 LAZY_NOTIFY_DISABLE=None)
        try:
            calls: list = []
            def _sender(t, b, l):
                calls.append((t, b, l))

            # First observation of feat-x parked -> sends.
            lazy_core.notify_event(
                "park", "feat-x parked", str(td_path),
                item_id="feat-x", detail="unresolved NEEDS_INPUT.md",
                sender=_sender,
            )
            assert len(calls) == 1

            # SAME event re-observed (e.g. re-probing the same still-parked
            # feature next cycle) -> no second page.
            lazy_core.notify_event(
                "park", "feat-x parked", str(td_path),
                item_id="feat-x", detail="unresolved NEEDS_INPUT.md",
                sender=_sender,
            )
            assert len(calls) == 1, "repeated observation of the SAME event must dedup"

            # A DIFFERENT item parking -> distinct identity, pages again.
            lazy_core.notify_event(
                "park", "feat-y parked", str(td_path),
                item_id="feat-y", detail="unresolved NEEDS_INPUT.md",
                sender=_sender,
            )
            assert len(calls) == 2

            # SAME item, DIFFERENT kind (budget trip vs park) -> distinct too.
            lazy_core.notify_event(
                "budget-trip", "feat-x budget deferred", str(td_path),
                item_id="feat-x", detail="ceiling=5",
                sender=_sender,
            )
            assert len(calls) == 3
            assert len(lazy_core._load_notify_ledger()) == 3
        finally:
            _notify_pop_env(saved)
            _clear_state_dir()




def test_notify_event_fail_open_on_send_error():
    """D9 (shared with notify_halt): a raising sender never propagates and
    is never ledgered (so the next observation retries); a breadcrumb is
    written."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        home = td_path / "home"
        (home / ".claude").mkdir(parents=True)
        saved = _notify_push_env(HOME=str(home), USERPROFILE=str(home),
                                 LAZY_NOTIFY_URL="https://ntfy.sh/t",
                                 LAZY_NOTIFY_DISABLE=None)
        try:
            def _boom(t, b, l):
                raise OSError("connection refused")

            lazy_core.notify_event(
                "flush", "run flush", str(td_path), item_id=None,
                sender=_boom,
            )  # must NOT raise
            crumb = state_dir / "notify-error.json"
            assert crumb.exists()
            assert lazy_core._load_notify_ledger() == {}, (
                "failed send must NOT be ledgered (retry on next observation)"
            )

            calls: list = []
            lazy_core.notify_event(
                "flush", "run flush", str(td_path), item_id=None,
                sender=lambda t, b, l: calls.append(t),
            )
            assert len(calls) == 1
            assert len(lazy_core._load_notify_ledger()) == 1
        finally:
            _notify_pop_env(saved)
            _clear_state_dir()




def test_notify_ntfy_send_headers_and_rfc2047():
    """D1: the ntfy sender is one urllib POST — body = message, Title/Click
    headers, timeout=5. Non-latin-1 titles (em-dashes are routine in
    notify_message) are RFC-2047 encoded so http.client never raises; ASCII
    titles pass through verbatim; Click present iff a link exists."""
    _guard()
    import urllib.request as _ur
    seen: list = []

    def _fake_urlopen(req, timeout=None):
        seen.append((req, timeout))

        class _Resp:
            def read(self):
                return b"ok"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    real = _ur.urlopen
    _ur.urlopen = _fake_urlopen
    try:
        lazy_core._ntfy_send("https://ntfy.sh/topic", "Plain title",
                             "body text", "https://github.com/o/r")
        req, timeout = seen[0]
        assert timeout == 5, timeout
        assert req.get_method() == "POST"
        assert req.data == b"body text"
        assert req.get_header("Title") == "Plain title"
        assert req.get_header("Click") == "https://github.com/o/r"
        # Non-latin-1 title → RFC 2047; no UnicodeEncodeError anywhere.
        lazy_core._ntfy_send("https://ntfy.sh/topic",
                             "NEEDS INPUT: x — halted", "b", None)
        req2, _ = seen[1]
        t2 = req2.get_header("Title")
        assert t2.startswith("=?UTF-8?B?") and t2.endswith("?="), t2
        import base64
        assert base64.b64decode(t2[10:-2]).decode("utf-8") == "NEEDS INPUT: x — halted"
        assert req2.get_header("Click") is None
    finally:
        _ur.urlopen = real
    # The pure helper: latin-1-safe values pass through unchanged.
    assert lazy_core._rfc2047_header("abc") == "abc"
    assert lazy_core._rfc2047_header("café") == "café"  # latin-1 encodable
    assert lazy_core._rfc2047_header("a — b").startswith("=?UTF-8?B?")




class _FakeTimeSentinel:
    """Minimal module stand-in for `lazy_core.notifyplane.time` exposing only
    `.time()` — the smallest double that can prove a submodule function's
    module-level `time.time()` call actually consults whatever object is
    bound to the module's `time` name (the patch-TARGET-effectiveness
    mechanism the 5 existing `test_ensure_runtime_production_*` sites all
    rely on via `lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time =
    fake_sub, fake_time`)."""

    def __init__(self, sentinel_ts: float):
        self._sentinel_ts = sentinel_ts

    def time(self):
        return self._sentinel_ts




def test_monolith_patch_target_effective():
    """Permanent regression pin (mechanism-3): patching
    `lazy_core.notifyplane.time` is the EFFECTIVE way to control the clock a
    submodule function reads via its module-level `time.time()` call.

    Reuses the exact patch idiom of the 5 existing
    `test_ensure_runtime_production_*` sites (e.g.
    test_ensure_runtime_production_boot_alive_dead_handle_recovers at line
    ~25430, all of which do `lazy_core.runtimeplane.subprocess,
    lazy_core.runtimeplane.time = fake_sub, fake_time`) but against a much
    cheaper function-under-test: `_notify_identity`'s sentinel-less,
    date-keyed identity branch needs no tempfile/subprocess/config fixture at
    all — passing a state dict with no `spec_path` key short-circuits
    `_notify_sentinel_path` to `None` with zero file I/O, landing directly on
    `ts = time.time() if now is None else float(now)`.

    LOAD-BEARING since the decomposition moved `_notify_identity` to
    `notifyplane` (this pin's own re-point rode Phase-2 WU-4): if a moved
    function stops reading the module `time` object this test patches, a
    future revision of this pin must patch the NEW owning submodule too —
    a silent divergence here would mean tests are patching a clock nobody
    reads anymore.
    """
    _guard()
    sentinel_ts = 946684800.0  # 2000-01-01T00:00:00Z — cross-checked via
    # datetime.datetime.fromtimestamp(946684800.0, tz=timezone.utc)
    _real_time = lazy_core.notifyplane.time
    lazy_core.notifyplane.time = _FakeTimeSentinel(sentinel_ts)
    try:
        identity = lazy_core._notify_identity(
            {"terminal_reason": "blocked", "feature_id": "wu2-patch-target-probe"},
            "feature",
        )
    finally:
        lazy_core.notifyplane.time = _real_time

    assert identity == "feature|wu2-patch-target-probe|blocked|d:2000-01-01", (
        "expected the fake sentinel clock to be consulted for the "
        f"sentinel-less date-keyed identity branch; got {identity!r}"
    )


_TESTS = [
    ("test_notify_symbols_present", test_notify_symbols_present),
    ("test_notify_config_precedence", test_notify_config_precedence),
    ("test_notify_identity_sentinel_and_dateless", test_notify_identity_sentinel_and_dateless),
    ("test_notify_ledger_roundtrip_prune_and_atomic", test_notify_ledger_roundtrip_prune_and_atomic),
    ("test_notify_remote_url_normalization", test_notify_remote_url_normalization),
    ("test_notify_payload_rich_shape", test_notify_payload_rich_shape),
    ("test_notify_halt_inert_without_config", test_notify_halt_inert_without_config),
    ("test_notify_halt_attention_gating_and_clean_stop_optin", test_notify_halt_attention_gating_and_clean_stop_optin),
    ("test_notify_halt_dedup_and_identity_refresh", test_notify_halt_dedup_and_identity_refresh),
    ("test_notify_halt_fail_open_breadcrumb_and_retry", test_notify_halt_fail_open_breadcrumb_and_retry),
    ("test_notify_event_inert_without_config", test_notify_event_inert_without_config),
    ("test_notify_event_dedup_exactly_once_and_distinguishes_events", test_notify_event_dedup_exactly_once_and_distinguishes_events),
    ("test_notify_event_fail_open_on_send_error", test_notify_event_fail_open_on_send_error),
    ("test_notify_ntfy_send_headers_and_rfc2047", test_notify_ntfy_send_headers_and_rfc2047),
    ("test_monolith_patch_target_effective", test_monolith_patch_target_effective),
]





def main() -> int:
    print("=" * 60)
    print("test_lazy_core.py — characterization tests")
    print("=" * 60)

    if _IMPORT_ERROR is not None:
        print(f"\nREQUIRED MODULE MISSING: {_IMPORT_ERROR}")
        print("This is the expected RED state — lazy_core has not been extracted yet.\n")

    print()
    for name, fn in _TESTS:
        _run_test(name, fn)

    total = len(_TESTS)
    passed = len(_PASSES)
    failed = len(_FAILURES)

    print()
    print("=" * 60)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if _FAILURES:
        print("\nFailed tests:")
        for f in _FAILURES:
            print(f"  - {f}")
        print()
        if _IMPORT_ERROR is not None:
            print("FIX: extract lazy_core.py from lazy-state.py and re-run.")
        return 1
    print("\nAll tests passed.")
    return 0



if __name__ == "__main__":
    sys.exit(main())
