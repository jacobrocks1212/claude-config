#!/usr/bin/env python3
"""
test_depdag.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_depdag.py
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



from _util import _ModuleMissing  # noqa: E402




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





# ---------------------------------------------------------------------------
# queue-dependency-dag Phase 1 — deps schema, relocated parse_dep_block, cycle
# detection, load-time validation (D1/D4/D6/D9).
# ---------------------------------------------------------------------------

_DEP_SPEC_FORM_A = (
    "# Spec\n\n**Status:** Draft\n\n"
    "**Depends on:**\n"
    "- feat-up-one — hard — needs the upstream contract\n"
    "- feat-up-two — soft — nice to have\n"
    "- feat-up-three — composes — builds atop it\n"
    "- Bad_Id — hard — invalid id is skipped\n"
    "- feat-up-four — wrongkind — invalid kind is skipped\n"
)




def test_parse_dep_block_relocated_to_lazy_core():
    """queue-dependency-dag D9: parse_dep_block lives in lazy_core (shared by
    both state scripts) with the exact prior lazy-state.py behavior: Form A
    parses valid lines into {feature_id, kind, reason}; malformed lines are
    skipped; Form B '(none)' and a missing block return []."""
    _guard()
    deps = lazy_core.parse_dep_block(_DEP_SPEC_FORM_A)
    assert [d["feature_id"] for d in deps] == [
        "feat-up-one", "feat-up-two", "feat-up-three"
    ], deps
    assert [d["kind"] for d in deps] == ["hard", "soft", "composes"], deps
    assert deps[0]["reason"] == "needs the upstream contract", deps
    # Form B — (none).
    assert lazy_core.parse_dep_block(
        "# Spec\n\n**Depends on:** (none)\n"
    ) == []
    # Missing block entirely.
    assert lazy_core.parse_dep_block("# Spec\n\n**Status:** Draft\n") == []




def test_dep_ids_shape_tolerant_queue_read():
    """dep_ids(queue_entry) reads the optional flat `deps` field (D1):
    absent/None entry/non-list/non-string members all degrade to [] — the
    shape-tolerance rail that keeps dep-less entries byte-identical."""
    _guard()
    assert lazy_core.dep_ids(None) == []
    assert lazy_core.dep_ids({}) == []
    assert lazy_core.dep_ids({"id": "x"}) == []
    assert lazy_core.dep_ids({"deps": None}) == []
    assert lazy_core.dep_ids({"deps": "not-a-list"}) == []
    assert lazy_core.dep_ids({"deps": ["a", 3, "b", None]}) == ["a", "b"]
    assert lazy_core.dep_ids({"deps": ["queue-dependency-dag"]}) == [
        "queue-dependency-dag"
    ]




def test_detect_dep_cycle_clean_and_dangling_edges():
    """detect_dep_cycle returns None for a clean DAG; edges pointing OUTSIDE
    the queued id set (dangling deps) are NOT graph edges (they are the D4
    walk-time BLOCKED surface, not a load-time cycle)."""
    _guard()
    entries = [
        {"id": "a", "deps": ["b"]},
        {"id": "b"},
        {"id": "c", "deps": ["not-queued"]},
    ]
    assert lazy_core.detect_dep_cycle(entries) is None




def test_detect_dep_cycle_two_cycle_self_loop_and_chain():
    """detect_dep_cycle names the members of an A<->B cycle, a self-loop, and
    a 3-chain cycle (Kahn's residue), sorted for determinism."""
    _guard()
    assert lazy_core.detect_dep_cycle([
        {"id": "a", "deps": ["b"]},
        {"id": "b", "deps": ["a"]},
        {"id": "c"},
    ]) == ["a", "b"]
    assert lazy_core.detect_dep_cycle([
        {"id": "a", "deps": ["a"]},
    ]) == ["a"]
    assert lazy_core.detect_dep_cycle([
        {"id": "a", "deps": ["c"]},
        {"id": "b", "deps": ["a"]},
        {"id": "c", "deps": ["b"]},
    ]) == ["a", "b", "c"]




def _dep_die_exit_code(fn) -> tuple:
    """Run fn expecting lazy_core._die's SystemExit(2); return (code, stdout)."""
    import contextlib
    import io as _io
    buf = _io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            fn()
    except SystemExit as exc:
        return (exc.code, buf.getvalue())
    raise AssertionError("expected SystemExit from _die, none raised")




def test_validate_queue_deps_die_cases(tmp_path):
    """validate_queue_deps _die()s (exit 2) on: non-list deps, a
    regex-violating id, a reserved bug:/feature: prefix (D6, reserved for vN),
    and a dependency cycle (D4, naming members). pytest-only (tmp_path)."""
    _guard()
    qp = tmp_path / "queue.json"

    code, out = _dep_die_exit_code(lambda: lazy_core.validate_queue_deps(
        [{"id": "a", "deps": "not-a-list"}], qp))
    assert code == 2 and "deps" in out

    code, out = _dep_die_exit_code(lambda: lazy_core.validate_queue_deps(
        [{"id": "a", "deps": ["Bad_Id"]}], qp))
    assert code == 2 and "Bad_Id" in out

    code, out = _dep_die_exit_code(lambda: lazy_core.validate_queue_deps(
        [{"id": "a", "deps": ["bug:some-bug"]}], qp))
    assert code == 2 and "reserved" in out and "bug:some-bug" in out

    code, out = _dep_die_exit_code(lambda: lazy_core.validate_queue_deps(
        [{"id": "a", "deps": ["feature:x"]}], qp))
    assert code == 2 and "reserved" in out

    code, out = _dep_die_exit_code(lambda: lazy_core.validate_queue_deps(
        [{"id": "a", "deps": ["b"]}, {"id": "b", "deps": ["a"]}], qp))
    assert code == 2 and "cycle" in out.lower() and "'a'" in out and "'b'" in out




def test_validate_queue_deps_clean_pass_is_silent_noop(tmp_path):
    """A queue whose entries carry no deps — or valid acyclic deps — passes
    validation with zero output and zero mutation (byte-identity rail).
    pytest-only (tmp_path)."""
    _guard()
    qp = tmp_path / "queue.json"
    # No deps anywhere (the universal legacy case).
    assert lazy_core.validate_queue_deps(
        [{"id": "a"}, {"id": "b"}], qp) is None
    # Valid acyclic deps, incl. a dangling edge (walk-time surface, not load).
    assert lazy_core.validate_queue_deps(
        [{"id": "a", "deps": ["b"]}, {"id": "b"},
         {"id": "c", "deps": ["not-queued"]}, "not-a-dict"], qp) is None




# ---------------------------------------------------------------------------
# queue-dependency-dag Phase 2 — receipt-gated dep-completion classifier (D3)
# and the unknown-dependency blocker body (D4).
# ---------------------------------------------------------------------------

def _dep_write_feature(root, fid, status, *, receipt=False, spec_dir=None):
    d = root / "docs" / "features" / (spec_dir or fid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "SPEC.md").write_text(
        f"# {fid}\n\n**Status:** {status}\n", encoding="utf-8"
    )
    if receipt:
        (d / "COMPLETED.md").write_text(
            "---\nkind: completed\nfeature_id: " + fid +
            "\nprovenance: mark-complete\n---\n\n# Completed\n",
            encoding="utf-8",
        )
    return d




def _dep_write_bug(root, bid, status, *, receipt=False, archived=False):
    base = root / "docs" / "bugs"
    if archived:
        base = base / "_archive"
    d = base / bid
    d.mkdir(parents=True, exist_ok=True)
    (d / "SPEC.md").write_text(
        f"# {bid}\n\n**Status:** {status}\n", encoding="utf-8"
    )
    if receipt:
        (d / "FIXED.md").write_text(
            "---\nkind: fixed\nbug_id: " + bid +
            "\nprovenance: mark-fixed\n---\n\n# Fixed\n",
            encoding="utf-8",
        )
    return d




def test_dep_completion_status_feature_pipeline(tmp_path):
    """D3 (feature): complete iff SPEC **Status:** Complete AND a content-valid
    COMPLETED.md receipt exists. Draft/receiptless-Complete → incomplete;
    Superseded → unsatisfiable-superseded (the work never happened); no dir
    anywhere → missing. pytest-only (tmp_path)."""
    _guard()
    root = tmp_path
    _dep_write_feature(root, "dep-done", "Complete", receipt=True)
    _dep_write_feature(root, "dep-draft", "Draft")
    _dep_write_feature(root, "dep-claimed", "Complete", receipt=False)
    _dep_write_feature(root, "dep-super", "Superseded")
    f = lambda i, **kw: lazy_core.dep_completion_status(
        i, root, pipeline="feature", **kw)
    assert f("dep-done") == "complete"
    assert f("dep-draft") == "incomplete"
    assert f("dep-claimed") == "incomplete"
    assert f("dep-super") == "unsatisfiable-superseded"
    assert f("dep-nowhere") == "missing"
    # spec_dir hint (queued entry whose dir name differs from its id).
    _dep_write_feature(root, "dep-hinted", "Complete", receipt=True,
                       spec_dir="custom-dir")
    hint = {"dep-hinted": root / "docs" / "features" / "custom-dir"}
    assert f("dep-hinted") == "missing"
    assert f("dep-hinted", id_dir_map=hint) == "complete"




def test_dep_completion_status_bug_pipeline_archive_aware(tmp_path):
    """D3/D9 divergence 2 (bug): resolution consults docs/bugs/<id>/ THEN
    docs/bugs/_archive/<id>/ (__mark_fixed__ archives on fix). Fixed + valid
    FIXED.md → complete (open or archived); Won't-fix → unsatisfiable-wont-fix
    (bug-side analog of Superseded); Open → incomplete; no dir → missing.
    pytest-only (tmp_path)."""
    _guard()
    root = tmp_path
    _dep_write_bug(root, "bug-open", "Open")
    _dep_write_bug(root, "bug-fixed-open", "Fixed", receipt=True)
    _dep_write_bug(root, "bug-archived", "Fixed", receipt=True, archived=True)
    _dep_write_bug(root, "bug-wontfix", "Won't-fix")
    _dep_write_bug(root, "bug-claimed", "Fixed", receipt=False)
    f = lambda i: lazy_core.dep_completion_status(i, root, pipeline="bug")
    assert f("bug-open") == "incomplete"
    assert f("bug-fixed-open") == "complete"
    assert f("bug-archived") == "complete"
    assert f("bug-wontfix") == "unsatisfiable-wont-fix"
    assert f("bug-claimed") == "incomplete"
    assert f("bug-nowhere") == "missing"




def _dep_write_feature_nested(root, fid, status, rel_parent, *, receipt=False):
    """Write a feature spec at a domain-nested path
    docs/features/<rel_parent>/<fid>/ (a Complete feature stays in place — no
    _archive — so it must be found by the recursive-by-id fallback)."""
    d = root / "docs" / "features" / Path(rel_parent) / fid
    d.mkdir(parents=True, exist_ok=True)
    (d / "SPEC.md").write_text(
        f"# {fid}\n\n**Status:** {status}\n", encoding="utf-8"
    )
    if receipt:
        (d / "COMPLETED.md").write_text(
            "---\nkind: completed\nfeature_id: " + fid +
            "\nprovenance: mark-complete\n---\n\n# Completed\n",
            encoding="utf-8",
        )
    return d




def test_dep_completion_status_feature_nested_complete_resolves(tmp_path):
    """Regression: a Complete feature dep at a domain-nested path (leaves
    queue.json ⇒ absent from id_dir_map; no _archive/) must resolve via the
    recursive-by-id fallback and classify 'complete', NOT 'missing' (which
    would write a spurious unknown-dependency BLOCKED.md on the dependent on
    every probe). A genuinely absent id still → 'missing'; a nested working
    (receiptless) feature → 'incomplete'. pytest-only (tmp_path)."""
    _guard()
    root = tmp_path
    _dep_write_feature_nested(
        root, "f1-global-scale", "Complete",
        "mixer/dj-capabilities/domains", receipt=True)
    _dep_write_feature_nested(
        root, "f2-nested-wip", "Draft", "mixer/dj-capabilities/domains")
    f = lambda i: lazy_core.dep_completion_status(
        i, root, pipeline="feature")
    # Nested Complete feature is FOUND and classified complete (not missing).
    assert f("f1-global-scale") == "complete"
    # No regression: a genuinely dangling id still classifies missing.
    assert f("f-does-not-exist") == "missing"
    # Nested working feature (no receipt) classifies incomplete.
    assert f("f2-nested-wip") == "incomplete"
    # Fallback must NOT match a bare nested dir named <id> with no SPEC.md.
    bare = root / "docs" / "features" / "group" / "f3-bare"
    bare.mkdir(parents=True, exist_ok=True)
    assert f("f3-bare") == "missing"




def test_format_unknown_dependency_blocker_names_everything():
    """D4: the BLOCKED.md body names the dependent, the offending dep id, WHY
    it is unsatisfiable (missing vs superseded vs wont-fix), and the known
    queued-id set — the format_unknown_host_capability_blocker shape."""
    _guard()
    body = lazy_core.format_unknown_dependency_blocker(
        "feat-downstream", "feat-ghost", "missing", ["feat-a", "feat-b"]
    )
    assert "feat-downstream" in body
    assert "feat-ghost" in body
    assert "missing" in body
    assert "feat-a" in body and "feat-b" in body
    assert "unknown-dependency" in body
    body2 = lazy_core.format_unknown_dependency_blocker(
        "feat-downstream", "feat-old", "unsatisfiable-superseded", []
    )
    assert "superseded" in body2.lower()




def test_sanctioned_stop_terminal_has_dependency_gated():
    """D4: queue-exhausted-dependency-gated is a sanctioned clean terminal
    (the host-capability-saturated / queue-exhausted-all-parked shape)."""
    _guard()
    assert "queue-exhausted-dependency-gated" in lazy_core.SANCTIONED_STOP_TERMINAL




# ---------------------------------------------------------------------------
# queue-dependency-dag Phase 4 — the --sync-deps feeder (D5): SPEC dep-block →
# queue `deps` projection, script-owned, idempotent, byte-stable no-op.
# ---------------------------------------------------------------------------

def _sync_fixture(tmp_path, spec_block, *, entry_deps=None, spec_dir=None):
    """Build docs/features/{queue.json + <dir>/SPEC.md} for sync_deps tests."""
    feats = tmp_path / "docs" / "features"
    d = feats / (spec_dir or "feat-sync")
    d.mkdir(parents=True, exist_ok=True)
    (d / "SPEC.md").write_text(
        "# feat-sync\n\n**Status:** Draft\n\n" + spec_block, encoding="utf-8"
    )
    entry = {"id": "feat-sync", "name": "Sync", "spec_dir": spec_dir or "feat-sync",
             "tier": 1}
    if entry_deps is not None:
        entry["deps"] = entry_deps
    qp = feats / "queue.json"
    qp.write_text(json.dumps({"queue": [
        entry,
        {"id": "feat-up", "name": "Up", "spec_dir": "feat-up", "tier": 2},
    ]}, indent=2) + "\n", encoding="utf-8")
    return qp, feats




def test_sync_deps_writes_then_noops_byte_stable(tmp_path):
    """First run projects the SPEC's HARD deps (soft/composes excluded, SPEC
    order, deduped) into the entry's `deps`; a second identical run returns
    noop: true with a byte-identical file. pytest-only (tmp_path)."""
    _guard()
    qp, feats = _sync_fixture(
        tmp_path,
        "**Depends on:**\n"
        "- feat-up — hard — needs it\n"
        "- feat-soft — soft — nice to have\n"
        "- feat-comp — composes — extends it\n"
        "- feat-up — hard — duplicate line\n",
    )
    res = lazy_core.sync_deps(qp, "feat-sync", feats)
    assert res.get("synced") is True and res.get("noop") is False, res
    data = json.loads(qp.read_text(encoding="utf-8"))
    assert data["queue"][0]["deps"] == ["feat-up"], data["queue"][0]
    first_bytes = qp.read_bytes()
    res2 = lazy_core.sync_deps(qp, "feat-sync", feats)
    assert res2.get("noop") is True, res2
    assert qp.read_bytes() == first_bytes, "noop must be byte-stable"




def test_sync_deps_empty_hard_set_removes_key(tmp_path):
    """A SPEC with no hard deps removes an existing `deps` key (restoring the
    byte-identical no-deps state); absent key → pure noop. pytest-only."""
    _guard()
    qp, feats = _sync_fixture(
        tmp_path, "**Depends on:** (none)\n", entry_deps=["feat-up"]
    )
    res = lazy_core.sync_deps(qp, "feat-sync", feats)
    assert res.get("synced") is True, res
    data = json.loads(qp.read_text(encoding="utf-8"))
    assert "deps" not in data["queue"][0], data["queue"][0]
    res2 = lazy_core.sync_deps(qp, "feat-sync", feats)
    assert res2.get("noop") is True, res2




def test_sync_deps_die_on_missing_id_or_spec(tmp_path):
    """A missing queue id or a missing SPEC.md _die()s exit 2 with zero
    mutation. pytest-only."""
    _guard()
    qp, feats = _sync_fixture(tmp_path, "**Depends on:** (none)\n")
    before = qp.read_bytes()
    code, out = _dep_die_exit_code(
        lambda: lazy_core.sync_deps(qp, "feat-ghost", feats))
    assert code == 2 and "feat-ghost" in out
    assert qp.read_bytes() == before
    # Missing SPEC.md (entry present, dir/SPEC absent).
    data = json.loads(qp.read_text(encoding="utf-8"))
    data["queue"].append(
        {"id": "feat-nospec", "name": "NoSpec", "spec_dir": "feat-nospec"})
    qp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    code, out = _dep_die_exit_code(
        lambda: lazy_core.sync_deps(qp, "feat-nospec", feats))
    assert code == 2 and "SPEC.md" in out




def test_sync_deps_refuses_self_dep_and_written_cycle(tmp_path):
    """sync_deps fails fast (zero mutation) rather than writing poison: a SPEC
    hard-dep on the item itself, or a projection that would create a queue
    cycle (which would brick every subsequent probe at load). pytest-only."""
    _guard()
    # Self-dep.
    qp, feats = _sync_fixture(
        tmp_path, "**Depends on:**\n- feat-sync — hard — itself\n")
    before = qp.read_bytes()
    code, out = _dep_die_exit_code(
        lambda: lazy_core.sync_deps(qp, "feat-sync", feats))
    assert code == 2 and "itself" in out
    assert qp.read_bytes() == before
    # Written cycle: feat-up already deps feat-sync; feat-sync's SPEC hard-deps
    # feat-up → projecting would close the cycle.
    qp2, feats2 = _sync_fixture(
        tmp_path / "c2", "**Depends on:**\n- feat-up — hard — needs it\n")
    data = json.loads(qp2.read_text(encoding="utf-8"))
    data["queue"][1]["deps"] = ["feat-sync"]
    qp2.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    before2 = qp2.read_bytes()
    code, out = _dep_die_exit_code(
        lambda: lazy_core.sync_deps(qp2, "feat-sync", feats2))
    assert code == 2 and "cycle" in out.lower()
    assert qp2.read_bytes() == before2


_TESTS = [
    ("test_parse_dep_block_relocated_to_lazy_core", test_parse_dep_block_relocated_to_lazy_core),
    ("test_dep_ids_shape_tolerant_queue_read", test_dep_ids_shape_tolerant_queue_read),
    ("test_detect_dep_cycle_clean_and_dangling_edges", test_detect_dep_cycle_clean_and_dangling_edges),
    ("test_detect_dep_cycle_two_cycle_self_loop_and_chain", test_detect_dep_cycle_two_cycle_self_loop_and_chain),
    ("test_format_unknown_dependency_blocker_names_everything", test_format_unknown_dependency_blocker_names_everything),
    ("test_sanctioned_stop_terminal_has_dependency_gated", test_sanctioned_stop_terminal_has_dependency_gated),
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
