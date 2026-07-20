#!/usr/bin/env python3
"""
test_lazy_queue_doc.py — Tests for the GitHub-mobile LAZY_QUEUE.md generator.

Covers the mobile-queue-control feature:
  - Phase 1 (WU-3): render_doc state-fidelity, byte-stability, triage, SPEC links,
    freshness header.
  - Phase 2 (WU-6): inline curated summary (status · phase N/M · next · exec
    summary), phase-progress reader, relative-vs-absolute link forms.
  - Phase 3 (WU-7): byte-stable no-op acceptance (re-asserts byte-stability as the
    pipeline-integration gate).

The renderer is a PURE function of the probe_state() aggregate dict — tests build
fixture state dicts directly (no shelling the real state scripts), so they are
hermetic. One optional integration-shaped test shells the real generator against
this very repo and asserts it parses.

Run with: python -m pytest user/scripts/test_lazy_queue_doc.py -q
Stdlib + pytest only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Insert the scripts directory on sys.path so `import` of the dash-named module
# (loaded via importlib below) and the pipeline_visualizer package resolve.
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def _load_module():
    """Import the dash-named generator module via importlib (it is not a valid
    identifier for a plain `import`)."""
    import importlib.util

    path = _SCRIPTS_DIR / "lazy-queue-doc.py"
    spec = importlib.util.spec_from_file_location("lazy_queue_doc", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lqd = _load_module()


# ---------------------------------------------------------------------------
# Fixture builders — the probe_state() aggregate shape
# ---------------------------------------------------------------------------

def _feature(fid, current_step, curated_stage, *, tier=1, terminal_reason=None,
             spec_path=None, name=None):
    return {
        "feature_id": fid,
        "feature_name": name or fid,
        "current_step": current_step,
        "terminal_reason": terminal_reason,
        "curated_stage": curated_stage,
        "queue_meta": {"tier": tier, "adhoc": False, "stub": None},
        "spec_path": spec_path,
        "error": None,
    }


def _bug(bid, current_step, curated_stage, *, severity="P1", terminal_reason=None,
         spec_path=None, name=None):
    return {
        "feature_id": bid,  # bug-state.py emits feature_id key too
        "bug_id": bid,
        "feature_name": name or bid,
        "current_step": current_step,
        "terminal_reason": terminal_reason,
        "curated_stage": curated_stage,
        "queue_meta": {"tier": None, "adhoc": False, "severity": severity},
        "spec_path": spec_path,
        "error": None,
    }


def _state(features=None, bugs=None):
    return {
        "features": features or [],
        "bugs": bugs or [],
        "leases": [],
        "roadmap": {},
        "server_time": "2026-06-22T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Phase 1 — WU-3: tables, state fidelity, byte-stability, triage, links, header
# ---------------------------------------------------------------------------

class TestRenderTables:
    def test_features_table_rows_match_fixture(self, tmp_path):
        state = _state(features=[
            _feature("d8-effect-chains", "Step 7a: execute plan", "Implement", tier=1),
            _feature("waveform-zoom", None, "Blocked", tier=2,
                     terminal_reason="blocked"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "## Features (2)" in doc
        # Each feature name appears as a row with its curated state cell.
        assert "d8-effect-chains" in doc
        assert "Implement" in doc
        assert "waveform-zoom" in doc
        assert "Blocked" in doc
        # tier cells present.
        assert "T1" in doc
        assert "T2" in doc

    def test_bugs_table_rows_match_fixture(self, tmp_path):
        state = _state(bugs=[
            _bug("marker-race", "Step 7a: execute plan", "Implement", severity="P1"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "## Bugs (1)" in doc
        assert "marker-race" in doc
        assert "P1" in doc

    def test_empty_queues_show_zero_counts(self, tmp_path):
        doc = lqd.render_doc(_state(), tmp_path, run_active=False)
        assert "## Features (0)" in doc
        assert "## Bugs (0)" in doc

    def test_state_cell_is_curated_stage_verbatim(self, tmp_path):
        state = _state(features=[
            _feature("f1", "Step 5: integrate research", "Research"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "Research" in doc


class TestBugAgingColumn:
    """bug-queue-aging-backpressure D4-A: the bug table's "aging" column
    (Discovered date + pin/escalation marker). Features table is unchanged
    (no "aging" column, no Discovered analog)."""

    def _write_bug_spec(self, tmp_path, bid, *, severity="P2", discovered=None):
        d = tmp_path / "docs" / "bugs" / bid
        d.mkdir(parents=True, exist_ok=True)
        lines = [f"# {bid}", "", "**Status:** Concluded", f"**Severity:** {severity}"]
        if discovered:
            lines.append(f"**Discovered:** {discovered}")
        (d / "SPEC.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_bugs_table_has_aging_column_header(self, tmp_path):
        state = _state(bugs=[_bug("b1", "Step 7a: execute plan", "Implement")])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "| aging |" in doc

    def test_features_table_has_no_aging_column(self, tmp_path):
        state = _state(features=[_feature("f1", "Step 5", "Research")])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        # Features header row is exactly the 4-column shape (no aging).
        assert "| # | item | state | tier |" in doc
        assert "| # | item | state | tier | aging |" not in doc

    def test_bug_row_renders_discovered_date(self, tmp_path):
        self._write_bug_spec(tmp_path, "aged-bug", discovered="2026-06-22")
        state = _state(bugs=[_bug("aged-bug", "Step 7a: execute plan", "Implement",
                                   severity="P2")])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "2026-06-22" in doc

    def test_bug_row_renders_pin_marker_when_active(self, tmp_path):
        self._write_bug_spec(tmp_path, "pinned-bug", discovered="2026-06-01",
                            severity="P1")
        bug = _bug("pinned-bug", "Step 7a: execute plan", "Implement", severity=None)
        bug["queue_meta"]["pinned_at"] = "2026-07-10"
        bug["queue_meta"]["pinned_until"] = "2099-01-01"  # far future — always active
        state = _state(bugs=[bug])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "pinned" in doc

    def test_bug_row_no_discovered_renders_empty_aging_cell_not_crash(self, tmp_path):
        # No SPEC.md written at all — the aging cell must render empty, never crash.
        state = _state(bugs=[_bug("no-spec-bug", "Step 1", "Pending")])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "## Bugs (1)" in doc

    def test_aging_render_byte_stable_across_same_day_runs(self, tmp_path):
        self._write_bug_spec(tmp_path, "stable-bug", discovered="2026-06-22",
                            severity="P2")
        state = _state(bugs=[_bug("stable-bug", "Step 7a: execute plan",
                                   "Implement", severity="P2")])
        doc1 = lqd.render_doc(state, tmp_path, run_active=False)
        doc2 = lqd.render_doc(state, tmp_path, run_active=False)
        assert doc1 == doc2


class TestByteStability:
    def test_two_renders_identical(self, tmp_path):
        state = _state(
            features=[_feature("f1", "Step 7a: execute plan", "Implement")],
            bugs=[_bug("b1", "Step 4: investigate bug", "Spec")],
        )
        a = lqd.render_doc(state, tmp_path, run_active=False)
        b = lqd.render_doc(state, tmp_path, run_active=False)
        assert a == b

    def test_no_walltime_in_body(self, tmp_path):
        # The doc must embed NO wall-clock — server_time must not leak into output.
        state = _state(features=[_feature("f1", "Step 7a: execute plan", "Implement")])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "2026-06-22T00:00:00Z" not in doc


class TestTriage:
    def test_blocked_item_surfaces_in_needs_attention(self, tmp_path):
        state = _state(features=[
            _feature("ok", "Step 7a: execute plan", "Implement"),
            _feature("stuck", None, "Blocked", terminal_reason="blocked"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "## Needs attention" in doc
        # The blocked item is named under the section.
        idx = doc.index("## Needs attention")
        assert "stuck" in doc[idx:]

    def test_needs_input_item_surfaces(self, tmp_path):
        state = _state(features=[
            _feature("ni", None, "Needs-input", terminal_reason="needs-input"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "## Needs attention" in doc
        assert "ni" in doc[doc.index("## Needs attention"):]

    def test_clean_queue_omits_section(self, tmp_path):
        state = _state(features=[
            _feature("ok", "Step 7a: execute plan", "Implement"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "## Needs attention" not in doc


class TestSpecLinks:
    def test_link_resolves_to_feature_spec(self, tmp_path):
        state = _state(features=[_feature("myfeat", "Step 4: no SPEC, no research", "Spec")])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "docs/features/myfeat/SPEC.md" in doc
        # Markdown link form.
        assert "[myfeat](docs/features/myfeat/SPEC.md)" in doc

    def test_bug_link_resolves_to_bug_spec(self, tmp_path):
        state = _state(bugs=[_bug("mybug", "Step 4: investigate bug", "Spec")])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "docs/bugs/mybug/SPEC.md" in doc

    def test_spec_path_authoritative_when_present(self, tmp_path):
        # When the state script emits an absolute spec_path, the link is relative
        # to repo root derived from it.
        spec_path = str(tmp_path / "docs" / "features" / "weird-dir" / "SPEC.md")
        state = _state(features=[
            _feature("logical-id", "Step 4: no SPEC, no research", "Spec",
                     spec_path=spec_path),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "docs/features/weird-dir/SPEC.md" in doc


class TestFreshnessHeader:
    def test_run_active_marker(self, tmp_path):
        doc = lqd.render_doc(_state(), tmp_path, run_active=True)
        first_line = doc.splitlines()[0]
        assert first_line.startswith("# Lazy Queue")
        assert "run active" in first_line
        assert "\U0001F512" in first_line  # 🔒

    def test_idle_marker(self, tmp_path):
        doc = lqd.render_doc(_state(), tmp_path, run_active=False)
        first_line = doc.splitlines()[0]
        assert "idle" in first_line
        assert "\U0001F512" not in first_line

    def test_repo_name_in_header(self, tmp_path):
        repo = tmp_path / "my-cool-repo"
        repo.mkdir()
        doc = lqd.render_doc(_state(), repo, run_active=False)
        assert "my-cool-repo" in doc.splitlines()[0]


# ---------------------------------------------------------------------------
# Phase 2 — WU-6: inline summary, phase N/M, exec summary, link modes
# ---------------------------------------------------------------------------

def _seed_item_dir(tmp_path, pipeline, item_id, *, spec_body=None, phases_body=None):
    d = tmp_path / "docs" / pipeline / item_id
    d.mkdir(parents=True)
    if spec_body is not None:
        (d / "SPEC.md").write_text(spec_body, encoding="utf-8")
    if phases_body is not None:
        (d / "PHASES.md").write_text(phases_body, encoding="utf-8")
    return d


class TestPhaseProgress:
    def test_three_phase_one_checked(self, tmp_path):
        body = (
            "# Phases\n\n"
            "### Phase 1: A\n- [x] a1\n- [x] a2\n\n"
            "### Phase 2: B\n- [ ] b1\n\n"
            "### Phase 3: C\n- [ ] c1\n"
        )
        p = tmp_path / "PHASES.md"
        p.write_text(body, encoding="utf-8")
        checked, total = lqd.phase_progress(p)
        assert total == 3
        assert checked == 1

    def test_missing_file_returns_none(self, tmp_path):
        assert lqd.phase_progress(tmp_path / "nope.md") == (None, None)

    def test_all_checked(self, tmp_path):
        body = (
            "### Phase 1: A\n- [x] a1\n\n"
            "### Phase 2: B\n- [x] b1\n"
        )
        p = tmp_path / "PHASES.md"
        p.write_text(body, encoding="utf-8")
        assert lqd.phase_progress(p) == (2, 2)


class TestInlineSummary:
    def test_phase_token_rendered(self, tmp_path):
        phases = (
            "### Phase 1: A\n- [x] a1\n\n"
            "### Phase 2: B\n- [ ] b1\n\n"
            "### Phase 3: C\n- [ ] c1\n"
        )
        spec = "# Feat\n\n> A one-line summary sentence. More detail here.\n"
        _seed_item_dir(tmp_path, "features", "feat-x", spec_body=spec, phases_body=phases)
        state = _state(features=[
            _feature("feat-x", "Step 7a: execute plan", "Implement"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "phase 1/3" in doc

    def test_phase_token_omitted_without_phases(self, tmp_path):
        # An item with no PHASES.md omits the phase N/M token, no exception.
        _seed_item_dir(tmp_path, "features", "feat-y",
                       spec_body="# Y\n\n> Some summary.\n")
        state = _state(features=[
            _feature("feat-y", "Step 4: no SPEC, no research", "Spec"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "feat-y" in doc
        assert "phase " not in doc.lower() or "phase 1/" not in doc

    def test_exec_summary_first_sentence(self, tmp_path):
        spec = "# Feat\n\n> First sentence here. Second one ignored.\n"
        _seed_item_dir(tmp_path, "features", "feat-z", spec_body=spec)
        state = _state(features=[
            _feature("feat-z", "Step 7a: execute plan", "Implement"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "First sentence here." in doc
        assert "Second one ignored." not in doc

    def test_missing_spec_no_exception(self, tmp_path):
        # No SPEC.md at all → empty exec-summary token, never an exception.
        state = _state(features=[
            _feature("ghost", "Step 7a: execute plan", "Implement"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "ghost" in doc

    def test_status_and_next_action_present(self, tmp_path):
        state = _state(features=[
            _feature("feat-s", "Step 7a: execute plan", "Implement"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        # The inline summary names the curated status.
        assert "Implement" in doc
        assert "next:" in doc


class TestLinkModes:
    def test_relative_is_default(self, tmp_path):
        state = _state(features=[_feature("f1", "Step 4: no SPEC, no research", "Spec")])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "docs/features/f1/SPEC.md" in doc
        assert "github.com" not in doc

    def test_absolute_mode_emits_blob_url(self, tmp_path):
        state = _state(features=[_feature("f1", "Step 4: no SPEC, no research", "Spec")])
        doc = lqd.render_doc(
            state, tmp_path, run_active=False, link_mode="absolute",
            remote_url="https://github.com/owner/repo.git", branch="main",
        )
        assert "github.com/owner/repo/blob/main/docs/features/f1/SPEC.md" in doc

    def test_absolute_mode_handles_ssh_remote(self, tmp_path):
        state = _state(features=[_feature("f1", "Step 4: no SPEC, no research", "Spec")])
        doc = lqd.render_doc(
            state, tmp_path, run_active=False, link_mode="absolute",
            remote_url="git@github.com:owner/repo.git", branch="dev",
        )
        assert "github.com/owner/repo/blob/dev/docs/features/f1/SPEC.md" in doc


class TestRemoteParsing:
    def test_https_remote(self):
        assert lqd.parse_owner_repo("https://github.com/owner/repo.git") == ("owner", "repo")

    def test_https_no_suffix(self):
        assert lqd.parse_owner_repo("https://github.com/owner/repo") == ("owner", "repo")

    def test_ssh_remote(self):
        assert lqd.parse_owner_repo("git@github.com:owner/repo.git") == ("owner", "repo")

    def test_unparseable_returns_none(self):
        assert lqd.parse_owner_repo("not a url") is None


# ---------------------------------------------------------------------------
# Phase 3 — WU-7: byte-stable no-op acceptance gate
# ---------------------------------------------------------------------------

class TestNoOpCommitGate:
    def test_unchanged_state_byte_identical(self, tmp_path):
        # The Phase-3 acceptance gate: re-render with no state change → identical
        # bytes, so a no-op cycle adds nothing to the commit.
        state = _state(
            features=[_feature("f1", "Step 7a: execute plan", "Implement")],
            bugs=[_bug("b1", "Step 9: run MCP tests", "Validate")],
        )
        first = lqd.render_doc(state, tmp_path, run_active=True)
        second = lqd.render_doc(state, tmp_path, run_active=True)
        assert first.encode("utf-8") == second.encode("utf-8")

    def test_state_advance_changes_output(self, tmp_path):
        before = _state(features=[_feature("f1", "Step 6: plan feature (phases + plan)", "Plan")])
        after = _state(features=[_feature("f1", "Step 7a: execute plan", "Implement")])
        assert lqd.render_doc(before, tmp_path, run_active=False) != \
            lqd.render_doc(after, tmp_path, run_active=False)


# ---------------------------------------------------------------------------
# Integration — shell the real generator against THIS repo (smoke)
# ---------------------------------------------------------------------------

class TestRealRepoSmoke:
    def test_stdout_runs_and_parses(self):
        repo_root = _SCRIPTS_DIR.parent.parent  # claude-config root
        if not (repo_root / "docs" / "features" / "queue.json").exists():
            pytest.skip("not run from claude-config repo root layout")
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "lazy-queue-doc.py"),
             "--repo-root", str(repo_root), "--stdout"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        out = proc.stdout
        assert out.startswith("# Lazy Queue")
        assert "## Features (" in out
        assert "## Bugs (" in out

    def test_help_invokable(self):
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "lazy-queue-doc.py"), "--help"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        assert proc.returncode == 0
        assert "--repo-root" in proc.stdout
        assert "--stdout" in proc.stdout


# ---------------------------------------------------------------------------
# Phase 4 — End-to-end regression guard
# (bug-state-scoped-query-loses-deferred-bug-identity)
#
# A repo whose docs/bugs/ contains a DEFERRED.md bug must render that bug as
# [<bug-id>](docs/bugs/<bug-id>/SPEC.md) with the ⏸ Deferred glyph and a working
# SPEC link — and the generated output must contain ZERO docs/bugs/unknown/SPEC.md.
# This closes the loop across all three layers: bug-state.py scoped identity
# (Part 1) → curated Deferred rollup (Part 3 / Phase 3) → generator render. The
# downstream renderers (probe.py / lazy-queue-doc.py) need NO production change.
# ---------------------------------------------------------------------------

# probe_state shells the real state scripts, so import it lazily inside the tests
# to keep the pure-render tests above import-light.

def _write_sentinel(path: Path, kind: str, **fields) -> None:
    """Minimal YAML-frontmatter sentinel writer (mirrors the state scripts'
    _write_yaml_sentinel fallback shape; PyYAML-independent)."""
    pairs = "\n".join(f"{k}: {v}" for k, v in {"kind": kind, **fields}.items())
    path.write_text(f"---\n{pairs}\n---\n\n# Sentinel\n", encoding="utf-8")


def _seed_deferred_bug_repo(tmp_path: Path) -> str:
    """Build a hermetic temp repo with one DEFERRED.md bug + SPEC.md. Returns the
    bug id."""
    bid = "deferred-audio-bug"
    bugs_dir = tmp_path / "docs" / "bugs"
    bug_dir = bugs_dir / bid
    bug_dir.mkdir(parents=True)
    (bugs_dir / "queue.json").write_text(
        json.dumps({"queue": [
            {"id": bid, "name": "Deferred Audio Bug", "spec_dir": bid},
        ]}),
        encoding="utf-8",
    )
    (bug_dir / "SPEC.md").write_text(
        "# Deferred Audio Bug\n\n"
        "**Status:** Open\n\n"
        "**Severity:** P1\n\n"
        "**Discovered:** 2026-06-01\n",
        encoding="utf-8",
    )
    _write_sentinel(
        bug_dir / "DEFERRED.md", "deferred",
        bug_id=bid,
        reason="Needs human audio audition — cannot be validated autonomously.",
        deferred_at="2026-06-01",
    )
    return bid


class TestDeferredBugEndToEndRegression:
    def test_deferred_bug_renders_real_spec_link_not_unknown(self, tmp_path):
        from pipeline_visualizer.probe import probe_state

        bid = _seed_deferred_bug_repo(tmp_path)
        state = probe_state(tmp_path)
        doc = lqd.render_doc(state, tmp_path, run_active=False)

        # The reproduced symptom: a broken [unknown](docs/bugs/unknown/SPEC.md)
        # link. The fix must emit ZERO such substring.
        assert "docs/bugs/unknown/SPEC.md" not in doc
        assert "unknown" not in doc
        # The real SPEC link is emitted with the bug's own id.
        assert f"docs/bugs/{bid}/SPEC.md" in doc
        assert f"[{bid}](docs/bugs/{bid}/SPEC.md)" in doc

    def test_deferred_bug_curated_stage_is_deferred_glyph(self, tmp_path):
        from pipeline_visualizer.probe import probe_state

        bid = _seed_deferred_bug_repo(tmp_path)
        state = probe_state(tmp_path)

        # The probed bug carries its own identity + the scoped deferred terminal
        # (Part 1) rolling up to the Deferred curated node (Phase 3).
        bugs = state["bugs"]
        assert len(bugs) == 1
        bug = bugs[0]
        assert bug.get("feature_id") == bid or bug.get("bug_id") == bid
        assert bug["terminal_reason"] == "operator-deferred"
        assert bug["curated_stage"] == "Deferred"

        # The rendered doc carries the ⏸ Deferred glyph.
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "⏸" in doc  # ⏸

    def test_unknown_fallback_retained_in_source_but_not_reached(self):
        # The _item_id / _rel_spec_path "unknown" fallback in lazy-queue-doc.py
        # is RETAINED as defensive last-resort code (still defined), but is not
        # reached for the deferred case (asserted via the absence of "unknown"
        # in the rendered output above).
        src = (_SCRIPTS_DIR / "lazy-queue-doc.py").read_text(encoding="utf-8")
        assert 'or "unknown"' in src  # the defensive fallback survives

    def test_feature_side_deferred_renders_feature_id(self, tmp_path):
        # Opportunistic feature-side mirror (Part 2): a host-capability-deferred
        # feature renders its own id, exercising the feature-pipeline twin
        # through the generator. We drive the renderer directly with a feature
        # carrying the scoped feature-side deferred terminal (the curated stage
        # is computed by the same probe layer / curated_stage mapping).
        from pipeline_visualizer.curated_stage import curated_stage

        stage = curated_stage(None, "host-capability-saturated-scoped", "feature")
        assert stage == "Deferred"
        state = _state(features=[
            _feature("zimtohrli-feat", None, stage,
                     terminal_reason="host-capability-saturated-scoped"),
        ])
        doc = lqd.render_doc(state, tmp_path, run_active=False)
        assert "docs/features/zimtohrli-feat/SPEC.md" in doc
        assert "docs/features/unknown/SPEC.md" not in doc


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
