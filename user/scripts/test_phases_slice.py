#!/usr/bin/env python3
"""Tests for phases-slice.py — deterministic scoped PHASES.md reader."""
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("phases_slice", os.path.join(HERE, "phases-slice.py"))
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)

PHASES = """# Feature X — Phases

**Status:** In progress
Some preamble line.

## Phase 1: Foundation
**Status:** Complete
- [x] scaffold the module
- [x] wire DI

## Phase 2 — Core logic (#123)
**Status:** Ready
- [x] first deliverable
- [ ] second deliverable
- [ ] third deliverable

### Phase 2.5: Follow-up
- [ ] corrective item

## Phase Summary
Not a phase (no id).
"""

NOTES = """# Feature X — Implementation Notes

## Phase 1 — Foundation
**Completed:** 2026-01-01
gotcha: watch the DI order.

## Phase 2 — Core logic
partial notes here.
"""


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    old = sys.argv
    sys.argv = ["phases-slice.py", *argv]
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = ps.main()
    finally:
        sys.argv = old
    return code, out.getvalue(), err.getvalue()


class ParseTests(unittest.TestCase):
    def test_parse_phases_boundaries_and_tallies(self):
        lines = PHASES.splitlines()
        preamble_end, phases = ps.parse_phases(lines)
        self.assertEqual([p["id"] for p in phases], ["1", "2", "2.5"])
        self.assertEqual(preamble_end, phases[0]["start"])
        p2 = phases[1]
        self.assertEqual((p2["done"], p2["total"]), (1, 3))
        self.assertEqual(p2["status"], "Ready")
        # "## Phase Summary" is NOT a phase but ends Phase 2.5's slice
        self.assertTrue(lines[phases[2]["end"] - 1].strip() != "")

    def test_phase_summary_heading_is_not_a_phase(self):
        _, phases = ps.parse_phases(PHASES.splitlines())
        self.assertNotIn("Summary", [p["id"] for p in phases])

    def test_notes_sections(self):
        sections = ps.parse_notes_sections(NOTES.splitlines())
        self.assertEqual([s["id"] for s in sections], ["1", "2"])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.phases_path = os.path.join(self.dir.name, "PHASES.md")
        with open(self.phases_path, "w", encoding="utf-8") as f:
            f.write(PHASES)
        with open(os.path.join(self.dir.name, "IMPLEMENTATION_NOTES.md"), "w", encoding="utf-8") as f:
            f.write(NOTES)

    def tearDown(self):
        self.dir.cleanup()

    def test_default_prints_active_phase_slice(self):
        code, out, _ = run_cli(self.phases_path)
        self.assertEqual(code, 0)
        self.assertIn("Phase 2 — Core logic", out)      # active (first with unchecked)
        self.assertIn("second deliverable", out)
        self.assertNotIn("corrective item", out)        # Phase 2.5 body not printed
        self.assertIn("phase index", out)
        self.assertIn("IMPLEMENTATION_NOTES.md index", out)

    def test_feature_dir_target_resolves_phases_md(self):
        code, out, _ = run_cli(self.dir.name)
        self.assertEqual(code, 0)
        self.assertIn("phase index", out)

    def test_explicit_phase_selection(self):
        code, out, _ = run_cli(self.phases_path, "--phase", "2.5")
        self.assertEqual(code, 0)
        self.assertIn("corrective item", out)
        self.assertNotIn("second deliverable", out.split("--- slice:")[1])

    def test_missing_phase_exits_2(self):
        code, _, err = run_cli(self.phases_path, "--phase", "99")
        self.assertEqual(code, 2)
        self.assertIn("99", err)

    def test_index_only_prints_no_body(self):
        code, out, _ = run_cli(self.phases_path, "--index-only")
        self.assertEqual(code, 0)
        self.assertNotIn("--- slice:", out)
        self.assertIn("[    1/3]", out)

    def test_checklist_mode(self):
        code, out, _ = run_cli(self.phases_path, "--phase", "2", "--checklist")
        self.assertEqual(code, 0)
        body = out.split("--- checklist:")[1]
        self.assertIn("- [ ] second deliverable", body)
        self.assertNotIn("**Status:**", body)

    def test_notes_section_print(self):
        code, out, _ = run_cli(self.phases_path, "--phase", "2", "--notes", "1")
        self.assertEqual(code, 0)
        self.assertIn("watch the DI order", out)

    def test_notes_all(self):
        code, out, _ = run_cli(self.phases_path, "--notes", "all")
        self.assertEqual(code, 0)
        self.assertIn("partial notes here", out)

    def test_all_checked_reports_no_active(self):
        done = PHASES.replace("- [ ]", "- [x]")
        p = os.path.join(self.dir.name, "DONE.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(done)
        code, out, _ = run_cli(p)
        self.assertEqual(code, 0)
        self.assertIn("no active phase", out)

    def test_missing_file_exits_1(self):
        code, _, err = run_cli(os.path.join(self.dir.name, "nope", "PHASES.md"))
        self.assertEqual(code, 1)
        self.assertIn("ERROR", err)


class LockstepTests(unittest.TestCase):
    """Mechanical pin for phases-slice.py's private regex copies.

    phases-slice.py deliberately does NOT import lazy_core (standalone pure-read
    tool), so it carries a private copy of the canonical phase-heading marker under
    a keep-byte-identical comment contract. This test IS that contract's enforcement
    (the `test_ruvonly_marker_lockstep_producers_match_ssot` pattern) — comment
    discipline alone proved insufficient once the canonical started moving between
    lazy_core submodules (lazy-core-package-decomposition; see
    docs/bugs/phases-slice-heading-regex-sync-unpinned).
    """

    def test_phase_heading_re_lockstep_with_lazy_core(self):
        # Import via the package facade, NOT a submodule path, so this test
        # survives the remaining decomposition phases wherever the definition
        # lands (lazy_core/__init__.py re-exports _PHASE_HEADING_RE).
        sys.path.insert(0, HERE)
        try:
            import lazy_core
        finally:
            sys.path.remove(HERE)
        self.assertEqual(
            ps._PHASE_HEADING_RE.pattern,
            lazy_core._PHASE_HEADING_RE.pattern,
            "phases-slice.py's private _PHASE_HEADING_RE has drifted from the "
            "canonical lazy_core._PHASE_HEADING_RE — keep the two byte-identical "
            "(see phases-slice.py:39 and the reciprocal comment at the lazy_core "
            "definition site).",
        )
        self.assertEqual(
            ps._PHASE_HEADING_RE.flags,
            lazy_core._PHASE_HEADING_RE.flags,
            "phases-slice.py's private _PHASE_HEADING_RE compiles with different "
            "flags than the canonical lazy_core._PHASE_HEADING_RE.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
