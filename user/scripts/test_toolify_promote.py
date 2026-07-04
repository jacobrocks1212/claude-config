#!/usr/bin/env python3
"""
test_toolify_promote.py — Tests for toolify-promote.py (toolify-auto-promotion).

The materializer converts one above-bar toolify-miner candidate into a stub
feature SPEC + a queue entry (via `lazy-state.py --enqueue-adhoc --tier 2
--stub --at tail`), records promoted/declined outcomes in a central ledger,
and reports acceptance rates. These tests lock in:

  Phase 3: the D5 stub-template marker round-trip pinned against the REAL
        `lazy-state.py::_spec_text_has_stub_marker`; the D7/D10 refusal chain
        (unknown id, below-bar naming the failed predicate, missing --id/--name,
        malformed slug, promoted-dup, declined-dup sans --force, --force sans
        --reason) with NO writes on any refusal path; the happy paths (promote
        fresh-mine + --from-json, decline, forced re-promote of a declined id);
        the failure-safe ordering (SPEC write failure leaves a routable queue
        item and NO ledger entry; re-run refused loudly); the scratch-repo
        probe (a materialized stub routes Step 4.5 stub branch).
  Phase 4: the report-only --acceptance-report (totals, rates, SAMPLE SIZES,
        receipt-derived shipped) and the --status join.

Run with: python3 user/scripts/test_toolify_promote.py   (exit 0 on pass)
Also pytest-discoverable (every `test_*` function is a standalone test).
No third-party dependencies — stdlib only.

RED STATE (today): import toolify_promote fails — the module doesn't exist yet.
GREEN STATE: all assertions pass.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent


def _load_hyphenated(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        module_name, str(_SCRIPTS_DIR / filename)
    )
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass type-resolution can find the module.
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Import the hyphenated modules under clean names.
# ---------------------------------------------------------------------------
_IMPORT_ERROR = None
toolify_promote = None
toolify_miner = None
lazy_state = None
try:
    toolify_miner = _load_hyphenated("toolify_miner", "toolify-miner.py")
    lazy_state = _load_hyphenated("lazy_state_for_promote_tests", "lazy-state.py")
    toolify_promote = _load_hyphenated("toolify_promote", "toolify-promote.py")
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _ModuleMissing(Exception):
    pass


def _guard():
    if _IMPORT_ERROR is not None:
        raise _ModuleMissing(f"toolify-promote.py not importable: {_IMPORT_ERROR}")


# ---------------------------------------------------------------------------
# Fixture builders — synthesize a transcript corpus (mirrors the miner tests).
# ---------------------------------------------------------------------------

def _assistant_turn(tool_calls):
    content = [
        {"type": "tool_use", "id": "tu_x", "name": name, "input": inp}
        for name, inp in tool_calls
    ]
    return {
        "type": "assistant",
        "uuid": "u",
        "message": {"role": "assistant", "content": content},
    }


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def _runtime_ensure_dance(host="3333"):
    """Deterministic 3-call dance; value-variant across runs → above-bar."""
    return [
        ("Bash", {"command": f"curl -s localhost:{host}/health", "description": "probe health"}),
        ("Bash", {"command": "npm run dev:restart", "description": "restart dev"}),
        ("Bash", {"command": f"curl --retry 5 localhost:{host}/health", "description": "wait for 200"}),
    ]


def _judgment_sequence():
    return [
        ("Read", {"file_path": "/x/verdict.json"}),
        ("AskUserQuestion", {"question": "salvageable?"}),
        ("Bash", {"command": "git commit -m x", "description": "commit"}),
    ]


def _single_run_dance():
    """A distinct deterministic dance that appears in only ONE run."""
    return [
        ("Glob", {"pattern": "src/**/*.rs"}),
        ("Read", {"file_path": "/x/lib.rs"}),
        ("Edit", {"file_path": "/x/lib.rs", "new_string": "b", "old_string": "a"}),
    ]


def _tiny_call():
    """Deterministic + repeated but below the token-heavy threshold."""
    return [("TaskStop", {"task_id": "t"})]


def _build_corpus(td: Path) -> Path:
    """Two-run corpus: the dance (above-bar), a judgment sequence (below-bar,
    judgment), a single-run dance (below-bar, run-count), and a tiny repeated
    call (below-bar, score)."""
    logs = td / "projects"
    proj = logs / "C--proj-A"
    _write_jsonl(
        proj / "session-1.jsonl",
        [_assistant_turn([c]) for c in _runtime_ensure_dance("3333")]
        + [_assistant_turn([c]) for c in _judgment_sequence()]
        + [_assistant_turn([c]) for c in _single_run_dance()]
        + [_assistant_turn([c]) for c in _tiny_call()],
    )
    _write_jsonl(
        proj / "session-2.jsonl",
        [_assistant_turn([c]) for c in _runtime_ensure_dance("4444")]
        + [_assistant_turn([c]) for c in _judgment_sequence()]
        + [_assistant_turn([c]) for c in _tiny_call()],
    )
    return logs


def _dance_cid() -> str:
    return toolify_miner.candidate_id(
        toolify_miner.signature(_runtime_ensure_dance("3333"))
    )


def _make_scratch_repo(td: Path, name="scratch-repo") -> Path:
    repo = td / name
    (repo / "docs" / "features").mkdir(parents=True, exist_ok=True)
    return repo


def _empty_ledger(td: Path, name="toolify-ledger.json") -> Path:
    p = td / name
    p.write_text(json.dumps({"entries": {}}, indent=2) + "\n", encoding="utf-8")
    return p


def _run(argv, env_state_dir=None):
    """Invoke toolify_promote.main(argv) in-process; return (rc, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    prev = os.environ.get("LAZY_STATE_DIR")
    tmp_state = None
    if env_state_dir is None:
        tmp_state = tempfile.TemporaryDirectory(prefix="promote-state-")
        env_state_dir = tmp_state.name
    os.environ["LAZY_STATE_DIR"] = str(env_state_dir)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = toolify_promote.main(argv)
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 1
    finally:
        if prev is None:
            os.environ.pop("LAZY_STATE_DIR", None)
        else:
            os.environ["LAZY_STATE_DIR"] = prev
        if tmp_state is not None:
            tmp_state.cleanup()
    return rc, out.getvalue(), err.getvalue()


def _promote_args(logs, ledger, repo, cid=None, slug="demo-dance",
                  name="Promote the demo dance", extra=()):
    return [
        "--promote", cid or _dance_cid(),
        "--id", slug, "--name", name,
        "--logs", str(logs), "--ledger", str(ledger),
        "--repo-root", str(repo),
        *extra,
    ]


# ===========================================================================
# WU-3.1/3.2 — module + template round-trip against the REAL detector
# ===========================================================================

def test_module_importable():
    _guard()
    assert toolify_promote is not None


def test_template_roundtrip_against_real_stub_detector():
    """THE D5 GATE-PRESERVATION INVARIANT: the rendered stub template carries
    the in-SPEC stub markers the REAL `_spec_text_has_stub_marker` accepts, and
    a /spec-style rewrite (markers stripped) flips it False — pinned against
    the state machine's actual detector, not a copied string."""
    _guard()
    cand = {
        "candidate_id": "abc123def456",
        "signature": "Bash(command,description) -> Bash(command,description)",
        "occurrences": 8, "run_count": 3,
        "est_tokens_per_occurrence": 360, "score": 2880,
        "deterministic": True, "above_bar": True,
        "sample_tools": ["Bash", "Bash"],
    }
    rendered = toolify_promote.render_stub_spec(cand, "demo-dance", "Demo Dance")
    assert lazy_state._spec_text_has_stub_marker(rendered) is True, (
        "rendered template MUST carry an in-SPEC stub marker"
    )
    # A /spec Phase-1 rewrite drops the Status stub value and the blockquote
    # trailer; simulate it and assert the detector flips False.
    stripped = "\n".join(
        line for line in rendered.splitlines()
        if "Draft (pre-Gemini)" not in line
    )
    stripped = stripped.replace("**Status:**", "**Status:** Draft", 1)
    assert lazy_state._spec_text_has_stub_marker(stripped) is False, (
        "marker-stripped rewrite must NOT read as a stub"
    )


def test_template_embeds_evidence_and_excludes_decided_artifacts():
    """The stub embeds the miner evidence (id, signature, counts) and contains
    no decided-looking sections (no Locked Decisions)."""
    _guard()
    cand = {
        "candidate_id": "abc123def456",
        "signature": "Read(file_path) -> Edit(file_path,new_string,old_string)",
        "occurrences": 5, "run_count": 2,
        "est_tokens_per_occurrence": 240, "score": 1200,
        "deterministic": True, "above_bar": True,
        "sample_tools": ["Read", "Edit"],
    }
    rendered = toolify_promote.render_stub_spec(cand, "demo-dance", "Demo Dance")
    assert "abc123def456" in rendered
    assert "Read(file_path)" in rendered
    assert "1200" in rendered
    assert "Locked Decisions" not in rendered
    assert "deliberately not locked" in rendered


# ===========================================================================
# WU-3.3 — refusal chain (loud, exit 2, side-effect-free)
# ===========================================================================

def _assert_no_writes(repo: Path, ledger: Path, ledger_before: str):
    assert not (repo / "docs" / "features" / "queue.json").exists(), (
        "refusal must not write queue.json"
    )
    assert ledger.read_text(encoding="utf-8") == ledger_before, (
        "refusal must not touch the ledger"
    )


def test_promote_unknown_candidate_refused():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        ledger = _empty_ledger(td)
        before = ledger.read_text(encoding="utf-8")
        repo = _make_scratch_repo(td)
        rc, _out, err = _run(_promote_args(logs, ledger, repo, cid="deadbeef0000"))
        assert rc == 2, f"unknown candidate_id must exit 2; got {rc}"
        assert "deadbeef0000" in err and ("re-min" in err or "mine" in err), err
        _assert_no_writes(repo, ledger, before)


def test_promote_below_bar_refused_naming_predicate():
    """Each below-bar class is refused with the FAILED PREDICATE named:
    judgment / run-count / score. No writes."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        ledger = _empty_ledger(td)
        before = ledger.read_text(encoding="utf-8")
        repo = _make_scratch_repo(td)
        cases = [
            (_judgment_sequence(), "judgment"),
            (_single_run_dance(), "run-count"),
            (_tiny_call(), "score"),
        ]
        for seq, predicate in cases:
            cid = toolify_miner.candidate_id(toolify_miner.signature(seq))
            rc, _out, err = _run(_promote_args(logs, ledger, repo, cid=cid))
            assert rc == 2, f"below-bar ({predicate}) must exit 2; got {rc}"
            assert predicate in err, (
                f"refusal must name the failed predicate {predicate!r}; got {err!r}"
            )
        _assert_no_writes(repo, ledger, before)


def test_promote_requires_id_and_name_and_valid_slug():
    """D10: --id/--name are the operator's judgment inputs — required; the slug
    must be kebab-case."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        ledger = _empty_ledger(td)
        before = ledger.read_text(encoding="utf-8")
        repo = _make_scratch_repo(td)
        base = ["--promote", _dance_cid(), "--logs", str(logs),
                "--ledger", str(ledger), "--repo-root", str(repo)]
        rc, _o, err = _run(base)  # neither --id nor --name
        assert rc == 2 and "--id" in err and "--name" in err, (rc, err)
        rc, _o, err = _run(base + ["--id", "ok-slug"])  # missing --name
        assert rc == 2, rc
        rc, _o, err = _run(base + ["--id", "Bad_Slug!", "--name", "X"])
        assert rc == 2 and "kebab" in err, (rc, err)
        _assert_no_writes(repo, ledger, before)


def test_promote_duplicate_promoted_hard_refused():
    """D7-B: a `promoted` ledger record is a HARD refusal — even with --force."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        ledger = td / "ledger.json"
        cid = _dance_cid()
        ledger.write_text(json.dumps({"entries": {cid: {
            "signature": "x", "status": "promoted",
            "feature_id": "prior-dance", "target_repo": str(td),
            "decided_at": "2026-07-01", "reason": "", "forced": False,
            "evidence": {},
        }}}, indent=2) + "\n", encoding="utf-8")
        before = ledger.read_text(encoding="utf-8")
        repo = _make_scratch_repo(td)
        for extra in ((), ("--force", "--reason", "trying anyway")):
            rc, _o, err = _run(_promote_args(logs, ledger, repo, extra=extra))
            assert rc == 2, f"promoted dup must exit 2 (extra={extra}); got {rc}"
            assert "prior-dance" in err, f"refusal must print the prior record: {err!r}"
        _assert_no_writes(repo, ledger, before)


def test_promote_declined_needs_force_with_reason():
    """D7-B: declined re-promotes only with --force AND --reason."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        ledger = td / "ledger.json"
        cid = _dance_cid()
        ledger.write_text(json.dumps({"entries": {cid: {
            "signature": "x", "status": "declined",
            "feature_id": None, "target_repo": None,
            "decided_at": "2026-07-01", "reason": "too few occurrences",
            "forced": False, "evidence": {},
        }}}, indent=2) + "\n", encoding="utf-8")
        before = ledger.read_text(encoding="utf-8")
        repo = _make_scratch_repo(td)
        rc, _o, err = _run(_promote_args(logs, ledger, repo))  # no --force
        assert rc == 2 and "--force" in err, (rc, err)
        rc, _o, err = _run(_promote_args(logs, ledger, repo, extra=("--force",)))
        assert rc == 2 and "--reason" in err, (rc, err)
        _assert_no_writes(repo, ledger, before)


def test_decline_requires_reason_and_known_candidate():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        ledger = _empty_ledger(td)
        before = ledger.read_text(encoding="utf-8")
        rc, _o, err = _run(["--decline", _dance_cid(), "--logs", str(logs),
                            "--ledger", str(ledger)])
        assert rc == 2 and "--reason" in err, (rc, err)
        rc, _o, err = _run(["--decline", "deadbeef0000", "--reason", "x",
                            "--logs", str(logs), "--ledger", str(ledger)])
        assert rc == 2, rc
        assert ledger.read_text(encoding="utf-8") == before


# ===========================================================================
# WU-3.4 — happy paths (promote / decline / forced re-promote)
# ===========================================================================

def test_promote_materializes_queue_stub_spec_and_ledger():
    """The full D4-B + D5 + D6 happy path: tail/tier-2/stub queue entry +
    ADHOC_BRIEF + marker-bearing evidence-embedding stub SPEC + `promoted`
    ledger entry; summary block printed."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        ledger = _empty_ledger(td)
        repo = _make_scratch_repo(td)
        # Pre-existing queue entry so "tail" is observable.
        qp = repo / "docs" / "features" / "queue.json"
        qp.write_text(json.dumps({"queue": [
            {"id": "feat-first", "name": "First", "spec_dir": "feat-first",
             "tier": 1}
        ]}, indent=2) + "\n", encoding="utf-8")
        cid = _dance_cid()
        rc, out, err = _run(_promote_args(logs, ledger, repo, cid=cid))
        assert rc == 0, f"promote failed: {err!r}"
        q = json.loads(qp.read_text(encoding="utf-8"))
        entry = q["queue"][-1]
        assert entry["id"] == "demo-dance" and entry.get("stub") is True \
            and entry.get("tier") == 2, entry
        assert q["queue"][0]["id"] == "feat-first", "must land at the TAIL"
        spec_md = repo / "docs" / "features" / "demo-dance" / "SPEC.md"
        assert spec_md.exists(), "stub SPEC.md must be written"
        spec_text = spec_md.read_text(encoding="utf-8")
        assert lazy_state._spec_text_has_stub_marker(spec_text) is True
        assert cid in spec_text and "occurrences" in spec_text, (
            "mined evidence must be embedded"
        )
        assert (repo / "docs" / "features" / "demo-dance"
                / "ADHOC_BRIEF.md").exists()
        led = json.loads(ledger.read_text(encoding="utf-8"))
        rec = led["entries"][cid]
        assert rec["status"] == "promoted" and rec["feature_id"] == "demo-dance"
        assert rec["target_repo"] == str(repo.resolve())
        assert rec["forced"] is False
        assert rec["evidence"]["occurrences"] >= 2
        # No decided-looking artifacts beside the stub.
        listed = {p.name for p in (repo / "docs" / "features" / "demo-dance").iterdir()}
        assert "RESEARCH.md" not in listed and "PHASES.md" not in listed
        # Summary block: queue position + stub path + baseline-lock reminder.
        assert "tail" in out and "SPEC.md" in out and "Step 4.5" in out, out


def test_promote_from_json_report_recomputes_above_bar():
    """--from-json works offline AND a tampered above_bar=true on a below-bar
    row is ignored (recomputed from the miner's constants)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        report = td / "report.json"
        rows = json.loads(toolify_miner.render_json(toolify_miner.mine(logs)))
        # Tamper: mark the judgment sequence above_bar.
        judg_sig = toolify_miner.signature(_judgment_sequence())
        for r in rows:
            if r["signature"] == judg_sig:
                r["above_bar"] = True
        report.write_text(json.dumps(rows), encoding="utf-8")
        ledger = _empty_ledger(td)
        repo = _make_scratch_repo(td)
        judg_cid = toolify_miner.candidate_id(judg_sig)
        rc, _o, err = _run([
            "--promote", judg_cid, "--id", "judgment-dance", "--name", "J",
            "--from-json", str(report), "--ledger", str(ledger),
            "--repo-root", str(repo),
        ])
        assert rc == 2 and "judgment" in err, (
            f"tampered above_bar must be recomputed and refused: {rc}, {err!r}"
        )
        # The genuinely above-bar dance promotes fine from the same report.
        rc, _o, err = _run([
            "--promote", _dance_cid(), "--id", "demo-dance", "--name", "Demo",
            "--from-json", str(report), "--ledger", str(ledger),
            "--repo-root", str(repo),
        ])
        assert rc == 0, f"from-json promote failed: {err!r}"
        assert (repo / "docs" / "features" / "demo-dance" / "SPEC.md").exists()


def test_decline_records_reason_and_forced_repromote_works():
    """Decline writes a `declined` ledger entry (no repo writes); a later
    --force --reason re-promote succeeds and records forced: true."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        ledger = _empty_ledger(td)
        repo = _make_scratch_repo(td)
        cid = _dance_cid()
        rc, out, err = _run(["--decline", cid, "--reason", "not a real dance",
                             "--logs", str(logs), "--ledger", str(ledger)])
        assert rc == 0, err
        led = json.loads(ledger.read_text(encoding="utf-8"))
        assert led["entries"][cid]["status"] == "declined"
        assert led["entries"][cid]["reason"] == "not a real dance"
        assert not (repo / "docs" / "features" / "queue.json").exists()
        # Duplicate decline refused with the prior record shown.
        rc, _o, err = _run(["--decline", cid, "--reason", "again",
                            "--logs", str(logs), "--ledger", str(ledger)])
        assert rc == 2 and "declined" in err, (rc, err)
        # Forced re-promote of the declined candidate.
        rc, out, err = _run(_promote_args(
            logs, ledger, repo,
            extra=("--force", "--reason", "corpus grew; dance is hot"),
        ))
        assert rc == 0, f"forced re-promote failed: {err!r}"
        led = json.loads(ledger.read_text(encoding="utf-8"))
        rec = led["entries"][cid]
        assert rec["status"] == "promoted" and rec["forced"] is True
        assert "corpus grew" in rec["reason"]


# ===========================================================================
# WU-3.5 — failure-safe ordering
# ===========================================================================

def test_spec_write_failure_leaves_routable_item_and_no_ledger_entry():
    """Enqueue → SPEC write → ledger. A SPEC-write failure exits 1 (degraded,
    loud), the queue entry + ADHOC_BRIEF still route the item to /spec, and
    the ledger is UNWRITTEN; a re-run refuses via the duplicate-id enqueue."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        ledger = _empty_ledger(td)
        before = ledger.read_text(encoding="utf-8")
        repo = _make_scratch_repo(td)
        real_writer = toolify_promote._write_stub_spec

        def _boom(path, text):
            raise OSError("disk full (simulated)")

        toolify_promote._write_stub_spec = _boom
        try:
            rc, _o, err = _run(_promote_args(logs, ledger, repo))
        finally:
            toolify_promote._write_stub_spec = real_writer
        assert rc == 1, f"degraded partial failure must exit 1; got {rc}"
        assert "ADHOC_BRIEF" in err or "degraded" in err, (
            f"stderr must name the degraded state: {err!r}"
        )
        q = json.loads((repo / "docs" / "features" / "queue.json")
                       .read_text(encoding="utf-8"))
        assert q["queue"][-1]["id"] == "demo-dance", "queue entry must survive"
        assert (repo / "docs" / "features" / "demo-dance"
                / "ADHOC_BRIEF.md").exists(), "brief must keep the item routable"
        assert ledger.read_text(encoding="utf-8") == before, (
            "ledger must NOT record a half-materialized promote"
        )
        # Re-run (writer restored): loud duplicate-id refusal from the enqueue.
        rc, _o, err = _run(_promote_args(logs, ledger, repo))
        assert rc == 2, f"re-run must refuse loudly; got {rc}"
        assert "demo-dance" in err, err


# ===========================================================================
# WU-3.6 — scratch-repo probe + --status join
# ===========================================================================

def test_materialized_stub_routes_step_4_5_probe():
    """DEFERRED-EMPIRICAL CHECK (SPEC): with BOTH ADHOC_BRIEF.md and the stub
    SPEC.md present, `lazy-state.py --repo-root <scratch>` dispatches /spec at
    Step 4.5 (stub branch) — not the Step-4 brief branch, not a Step-5
    fall-through."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        ledger = _empty_ledger(td)
        repo = _make_scratch_repo(td)
        rc, _o, err = _run(_promote_args(logs, ledger, repo))
        assert rc == 0, err
        with tempfile.TemporaryDirectory(prefix="probe-state-") as state_dir:
            probe = subprocess.run(
                [sys.executable, str(_SCRIPTS_DIR / "lazy-state.py"),
                 "--repo-root", str(repo)],
                capture_output=True, text=True,
                env={**os.environ, "LAZY_STATE_DIR": state_dir},
            )
        assert probe.returncode == 0, probe.stderr
        state = json.loads(probe.stdout)
        assert state.get("sub_skill") == "spec", state
        assert state.get("current_step") == "Step 4.5: stub-spec detected", (
            f"expected the stub branch, got {state.get('current_step')!r}"
        )


def test_status_join_marks_new_promoted_declined_shipped():
    """--status marks each above-bar candidate NEW / promoted → <feature_id> /
    declined (<reason>) / shipped (receipt-derived)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        logs = _build_corpus(td)
        ledger = _empty_ledger(td)
        repo = _make_scratch_repo(td)
        cid = _dance_cid()
        rc, _o, err = _run(_promote_args(logs, ledger, repo, cid=cid))
        assert rc == 0, err
        # Freshly promoted, no receipt → "promoted →".
        rc, out, err = _run(["--status", "--logs", str(logs),
                             "--ledger", str(ledger)])
        assert rc == 0, err
        assert "promoted" in out and "demo-dance" in out, out
        # Receipt lands → derived "shipped" (never stored in the ledger).
        receipt_dir = repo / "docs" / "features" / "demo-dance"
        (receipt_dir / "COMPLETED.md").write_text(
            "---\nkind: completed\n---\n", encoding="utf-8")
        rc, out, _e = _run(["--status", "--logs", str(logs),
                            "--ledger", str(ledger)])
        assert "shipped" in out, out
        led_text = ledger.read_text(encoding="utf-8")
        assert "shipped" not in led_text, "shipped must NEVER be stored"


# ---------------------------------------------------------------------------
# Self-contained runner (mirrors test_toolify_miner.py's pattern).
# ---------------------------------------------------------------------------

_TESTS = [(n, f) for n, f in sorted(globals().items())
          if n.startswith("test_") and callable(f)]

_PASSES: list[str] = []
_FAILURES: list[str] = []


def _run_test(name, fn):
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


def main() -> int:
    print("=" * 60)
    print("test_toolify_promote.py — toolify promote/materializer tests")
    print("=" * 60)
    if _IMPORT_ERROR is not None:
        print(f"\nMODULE NOT YET PRESENT (expected RED): {_IMPORT_ERROR}\n")
    print()
    for name, fn in _TESTS:
        _run_test(name, fn)
    total, passed, failed = len(_TESTS), len(_PASSES), len(_FAILURES)
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if _FAILURES:
        print("\nFailed tests:")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
