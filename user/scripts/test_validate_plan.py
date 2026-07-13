#!/usr/bin/env python3
"""Tests for validate-plan.py's --structural mode (plan-structure-authoring-gate).

Covers the six D2 rules (WU checklist, verification-row placement, template-row
rejection, gate-owned-row ban, dependency-ordered series, frontmatter sanity),
the recognizer-parity cross-check against lazy_core's own
remaining_unchecked_are_verification_only, and a real-corpus check against every
plan part / PHASES.md committed in this repo (pre-existing violations are
ENUMERATED here, not silently accepted — see the module docstring in
validate-plan.py's --structural section).

Run with: python -m pytest user/scripts/test_validate_plan.py -q
"""
from __future__ import annotations

import glob
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

_vp_spec = importlib.util.spec_from_file_location(
    "validate_plan", os.path.join(HERE, "validate-plan.py")
)
vp = importlib.util.module_from_spec(_vp_spec)
_vp_spec.loader.exec_module(vp)

# lazy_core is now a package (user/scripts/lazy_core/) behind a PEP 562 facade
# (lazy-core-package-decomposition Phase 1) — import it as a package instead of
# the retired flat-file spec_from_file_location load.
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import lazy_core  # noqa: E402


def _write(tmp_path, name, content):
    p = Path(tmp_path) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestRuleWuChecklist(unittest.TestCase):
    def test_missing_wu_checklist_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "plans/all-phases-foo.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [1]\n---\n\n# Plan\n\nNo WU rows here at all.\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 1)
            self.assertTrue(any("wu-checklist" in l for l in lines))

    def test_present_wu_checklist_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "plans/all-phases-foo.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [1]\n---\n\n# Plan\n\n## Work Units\n"
                "- [ ] WU-1 — do the thing\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)

    def test_retro_plan_kind_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "plans/retro-foo.md", (
                "---\nkind: retro-plan\nfeature_id: foo\nstatus: Ready\n---\n\n"
                "# Retro Plan\n\nNo WU checklist by design.\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)

    def test_realign_plan_kind_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "plans/realign-2026-01-01.md", (
                "---\nkind: realign-plan\nfeature_id: foo\nstatus: Ready\n---\n\n"
                "# Realign Plan\n\nNo WU checklist by design.\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)


class TestRuleVerificationPlacement(unittest.TestCase):
    def test_misplaced_verification_row_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", (
                "# Implementation Phases — Foo\n\n"
                "### Phase 1: Foo\n\n"
                "**Deliverables:**\n"
                "- [ ] reachability smoke: MCP call to new_tool returns a non-error response\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 1)
            self.assertTrue(any("verif-placement" in l for l in lines))

    def test_properly_placed_verification_row_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", (
                "# Implementation Phases — Foo\n\n"
                "### Phase 1: Foo\n\n"
                "**Deliverables:**\n"
                "- [x] build the thing\n\n"
                "**Runtime Verification** *(checked by integration test)*:\n"
                "- [ ] <!-- verification-only --> reachability smoke: MCP call to "
                "new_tool returns a non-error response\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)

    def test_cross_reference_mention_is_not_flagged(self):
        """A deliverable row merely NAMING the Runtime Verification section
        (real corpus pattern: "(see Runtime Verification below)") must not
        trip rule 2 — it is not a verification-vocabulary row itself."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", (
                "# Implementation Phases — Foo\n\n"
                "### Phase 1: Foo\n\n"
                "**Deliverables:**\n"
                "- [x] Ran the mandated gates this pass (see Runtime Verification "
                "below) — all green\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)

    def test_bare_validated_md_mention_is_not_flagged(self):
        """A row merely naming VALIDATED.md as a sentinel filename in prose
        (extremely common in this repo's own PHASES.md) must not trip rule 2."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", (
                "# Implementation Phases — Foo\n\n"
                "### Phase 1: Foo\n\n"
                "**Deliverables:**\n"
                "- [x] Denies a Write whose target is a sentinel "
                "(NEEDS_INPUT.md, BLOCKED.md, VALIDATED.md) on a stray branch\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)


class TestRuleTemplateRows(unittest.TestCase):
    def test_unfilled_brace_placeholder_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", (
                "# Implementation Phases — Foo\n\n### Phase 1: Foo\n\n"
                "**Deliverables:**\n- [ ] {Concrete code output 1}\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 1)
            self.assertTrue(any("template-row" in l for l in lines))

    def test_unfilled_labeled_placeholder_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", (
                "# Implementation Phases — Foo\n\n### Phase 1: Foo\n\n"
                "**Deliverables:**\n- [ ] Tests: {What tests verify this phase}\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 1)
            self.assertTrue(any("template-row" in l for l in lines))

    def test_wu_generic_title_placeholder_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "plans/all-phases-foo.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [1]\n---\n\n## Work Units\n- [ ] WU-N — <short title>\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 1)
            self.assertTrue(any("template-row" in l for l in lines))

    def test_real_filled_row_with_html_comment_marker_passes(self):
        """The canonical <!-- verification-only --> marker itself must NEVER
        be mistaken for a template placeholder (the dominant real-corpus
        false-positive class this rule was tuned against)."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", (
                "# Implementation Phases — Foo\n\n### Phase 1: Foo\n\n"
                "**Runtime Verification** *(checked)*:\n"
                "- [x] <!-- verification-only --> A misnamed blocker under "
                "`docs/features/<slug>/` still denies.\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)

    def test_real_prose_row_with_angle_bracket_path_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", (
                "# Implementation Phases — Foo\n\n### Phase 1: Foo\n\n"
                "**Deliverables:**\n"
                "- [x] Run against `<real-checkout>` and confirm it reaches READY\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)


class TestRuleGateOwnedRows(unittest.TestCase):
    def test_status_flip_row_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", (
                "# Implementation Phases — Foo\n\n### Phase 1: Foo\n\n"
                "**Deliverables:**\n"
                "- [x] Flip `**Status:**` to `Fixed` in `SPEC.md` and this "
                "`PHASES.md`; write `FIXED.md`.\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 1)
            self.assertTrue(any("gate-owned-row" in l for l in lines))

    def test_ordinary_doc_edit_row_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", (
                "# Implementation Phases — Foo\n\n### Phase 1: Foo\n\n"
                "**Deliverables:**\n- [ ] Update SPEC §4 wording for clarity\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)


class TestRuleSeriesDependencyOrder(unittest.TestCase):
    def test_inverted_series_order_errors(self):
        """Reproduces the e076ed30 inversion shape: part-1 = Phase 5 (the
        dependent), part-2 = Phase 6 (its prerequisite) — the prerequisite
        is scheduled AFTER the dependent, contradicting 'Execute parts
        strictly in order'."""
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "plans/all-phases-foo-part-1.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [5]\n---\n\n## Work Units\n- [ ] WU-1 — thing\n\n"
                "**Entry criteria:** Phase 6 complete\n"
            ))
            p2 = _write(tmp, "plans/all-phases-foo-part-2.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [6]\n---\n\n## Work Units\n- [ ] WU-1 — thing\n"
            ))
            lines1, code1 = vp.run_structural_checks(Path(tmp) / "plans/all-phases-foo-part-1.md")
            self.assertEqual(code1, 1)
            self.assertTrue(any("series-order" in l for l in lines1))

    def test_valid_high_phase_prerequisite_passes(self):
        """part-1 = Phase 6 (the prerequisite), part-2 = Phase 5 (depends on
        Phase 6) — series index (1 < 2) matches dependency order, so this
        must PASS despite the phase numbers being inverted."""
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "plans/all-phases-foo-part-1.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [6]\n---\n\n## Work Units\n- [ ] WU-1 — thing\n"
            ))
            p2 = _write(tmp, "plans/all-phases-foo-part-2.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [5]\n---\n\n## Work Units\n- [ ] WU-1 — thing\n\n"
                "**Entry criteria:** Phase 6 complete\n"
            ))
            lines2, code2 = vp.run_structural_checks(p2)
            self.assertEqual(code2, 0)

    def test_forward_looking_mention_not_flagged(self):
        """Real corpus false-positive shape (plan-skills-redesign part-3):
        'Entry criteria: None; establishes the pattern Phase 4 propagates.'
        names a LATER phase in passing without declaring a dependency on it
        — must not trip rule 5."""
        with tempfile.TemporaryDirectory() as tmp:
            p1 = _write(tmp, "plans/all-phases-foo-part-1.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [3]\n---\n\n## Work Units\n- [ ] WU-1 — thing\n\n"
                "**Entry criteria:** None; establishes the pattern Phase 4 propagates.\n"
            ))
            _write(tmp, "plans/all-phases-foo-part-2.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [4]\n---\n\n## Work Units\n- [ ] WU-1 — thing\n"
            ))
            lines1, code1 = vp.run_structural_checks(p1)
            self.assertEqual(code1, 0)

    def test_single_part_plan_rule_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "plans/all-phases-foo.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [1, 2]\n---\n\n## Work Units\n- [ ] WU-1 — thing\n\n"
                "**Entry criteria:** Phase 99 complete\n"
            ))
            lines, code = vp.run_structural_checks(p)
            # No -part-K suffix -> series index is None -> rule 5 is N/A,
            # even though "Phase 99" resolves to no sibling (out of scope too).
            self.assertEqual(code, 0)


class TestRuleFrontmatterSanity(unittest.TestCase):
    def test_non_numeric_phases_entry_warns_not_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "plans/all-phases-foo.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [\"all\"]\n---\n\n## Work Units\n- [ ] WU-1 — thing\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)  # WARN only, never blocks
            self.assertTrue(any("frontmatter" in l and "WARN" in l for l in lines))

    def test_duplicate_wu_number_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "plans/all-phases-foo.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [1]\n---\n\n## Work Units\n"
                "- [ ] WU-1 — thing\n- [ ] WU-1 — thing again\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)
            self.assertTrue(any("Duplicate WU number" in l for l in lines))

    def test_malformed_frontmatter_warns_never_crashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "plans/all-phases-foo.md", (
                "---\nkind: implementation-plan\n  bad indentation: [unterminated\n---\n\n"
                "## Work Units\n- [ ] WU-1 — thing\n"
            ))
            # Must not raise — malformed frontmatter is a reported WARN.
            lines, code = vp.run_structural_checks(p)
            self.assertIsInstance(lines, list)


class TestScopeAndIo(unittest.TestCase):
    def test_out_of_scope_file_passes_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "docs/README.md", "# Not a plan or PHASES file\n")
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)
            self.assertTrue(any("out of scope" in l for l in lines))

    def test_cloud_plan_out_of_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "plans/cloud-foo.md", (
                "---\nkind: cloud-implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "---\n\n## Work Units (execute in this order)\n1. WU-1 — thing\n"
            ))
            lines, code = vp.run_structural_checks(p)
            self.assertEqual(code, 0)
            self.assertTrue(any("out of scope" in l for l in lines))

    def test_missing_file_is_an_error_never_silent(self):
        lines, code = vp.run_structural_checks("/nonexistent/path/PHASES.md")
        self.assertEqual(code, 1)
        self.assertTrue(any("file not found" in l for l in lines))

    def test_broken_lazy_core_loader_reports_infrastructure_error_never_raises(self):
        """A lazy_core import failure (gate machinery broken — e.g. the
        module deleted/moved) honors the never-raises contract: it is
        reported as a loud [ERROR] (infrastructure) finding with exit 1,
        never a raise (which once let plan_structural_backstop's broad
        fail-open silently disarm this gate repo-wide — see
        docs/bugs/plan-structural-backstop-silent-disarm-on-infrastructure-failure)."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "plans/all-phases-foo.md", (
                "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
                "phases: [1]\n---\n\n## Work Units\n- [ ] WU-1 — do the thing\n"
            ))

            def _boom():
                raise FileNotFoundError("lazy_core.py: retired flat file")

            real_loader = vp._load_lazy_core
            vp._load_lazy_core = _boom
            try:
                lines, code = vp.run_structural_checks(p)
            finally:
                vp._load_lazy_core = real_loader
            self.assertEqual(code, 1)
            self.assertTrue(
                any("(infrastructure)" in l for l in lines),
                f"expected a loud infrastructure ERROR finding; got {lines}",
            )

    def test_cli_exit_code_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", (
                "# Implementation Phases — Foo\n\n### Phase 1: Foo\n\n"
                "**Deliverables:**\n- [ ] {unfilled}\n"
            ))
            result = subprocess.run(
                [sys.executable, os.path.join(HERE, "validate-plan.py"), "--structural", str(p)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)


class TestRecognizerParityCrossCheck(unittest.TestCase):
    """Validation Criteria row: 'Recognizer parity | file passing the gate |
    remaining_unchecked_are_verification_only() agrees (same function)'."""

    def test_clean_file_agrees_with_consumer_recognizer(self):
        text = (
            "# Implementation Phases — Foo\n\n### Phase 1: Foo\n\n"
            "**Deliverables:**\n- [x] build the thing\n\n"
            "**Runtime Verification** *(checked)*:\n"
            "- [ ] <!-- verification-only --> reachability smoke: MCP call ok\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", text)
            lines, code = vp.run_structural_checks(p)
        self.assertEqual(code, 0)
        self.assertTrue(lazy_core.remaining_unchecked_are_verification_only(text))

    def test_misplaced_file_disagrees_with_consumer_recognizer(self):
        text = (
            "# Implementation Phases — Foo\n\n### Phase 1: Foo\n\n"
            "**Deliverables:**\n"
            "- [ ] reachability smoke: MCP call to new_tool returns a non-error response\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, "PHASES.md", text)
            lines, code = vp.run_structural_checks(p)
        self.assertEqual(code, 1)
        # The consumer-side recognizer ALSO sees this row as non-exempt
        # (it is not under a recognized subsection) — both sides agree the
        # row is unresolved implementation-shaped work, never silently pass
        # each other by.
        self.assertFalse(lazy_core.remaining_unchecked_are_verification_only(text))


class TestRealCorpusCheck(unittest.TestCase):
    """Runs --structural against every committed plan part / PHASES.md in
    this repo. Pre-existing violations are ENUMERATED (an explicit allowlist
    below), not silently accepted — per the SPEC's Phase 1 scope. A NEW
    violation appearing here (a file not in the allowlist) fails the test,
    forcing a deliberate decision (fix it, or add it to the allowlist with a
    one-line reason) rather than letting the corpus silently drift.
    """

    # (repo-relative POSIX path) -> one-line reason it's a known pre-existing
    # violation, predating this gate (all from archived/Complete historical
    # bugs/features — the gate is authoring-time-forward, not retroactive).
    _KNOWN_VIOLATIONS = {
        "docs/bugs/_archive/build-queue-enforce-cd-prefix-bypass/plans/all-phases-2026-07-06.md":
            "pre-ISSUE-6 legacy plan (Complete before write-plan mandated the WU checklist)",
        "docs/bugs/_archive/crlf-hook-blanket-enforce-mixed-eol/PHASES.md":
            "pre-gate gate-owned Status-flip row, historical/Complete",
        "docs/bugs/_archive/noncanonical-blocker-filename-invisible-to-state-machine/plans/all-phases-implementation.md":
            "pre-ISSUE-6 legacy plan (Complete before write-plan mandated the WU checklist)",
        "docs/features/coupled-pair-generation/plans/implementation.md":
            "pre-ISSUE-6 legacy plan (Complete before write-plan mandated the WU checklist)",
    }

    def test_full_corpus_has_only_known_pre_existing_violations(self):
        patterns = [
            "docs/features/**/plans/*.md",
            "docs/bugs/**/plans/*.md",
            "docs/features/**/PHASES.md",
            "docs/bugs/**/PHASES.md",
        ]
        files = []
        for pattern in patterns:
            files += glob.glob(os.path.join(REPO_ROOT, pattern), recursive=True)
        files = sorted(set(files))
        self.assertGreater(len(files), 50, "sanity check: corpus glob found suspiciously few files")

        unexpected = []
        for f in files:
            rel = os.path.relpath(f, REPO_ROOT).replace(os.sep, "/")
            lines, code = vp.run_structural_checks(f)
            if code == 1 and rel not in self._KNOWN_VIOLATIONS:
                unexpected.append((rel, lines))

        if unexpected:
            report = "\n".join(f"{rel}:\n  " + "\n  ".join(lines) for rel, lines in unexpected)
            self.fail(
                f"{len(unexpected)} NEW structural violation(s) not in the known-violations "
                f"allowlist (fix them, or if genuinely pre-existing/out-of-scope, add a "
                f"one-line reason to _KNOWN_VIOLATIONS):\n{report}"
            )


if __name__ == "__main__":
    unittest.main()
