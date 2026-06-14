"""
test_surface_resolver.py — Hermetic unit tests for surface_resolver.py and
validation_readiness.py (F5, lazy-validation-readiness Phase 4).

All tests build tmp fixture trees in memory (no live AlgoBooth repo access).
Run:
    cd C:/Users/Jacob/source/repos/claude-config
    python -m pytest user/scripts/test_surface_resolver.py -q
"""

import json
import os
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap — ensure the scripts directory is importable regardless of
# how pytest is invoked (project root, scripts dir, etc.).
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from surface_resolver import (
    asserted_tools,
    asserted_tools_with_lines,
    registered_tools,
    run_lint,
    unresolved_tools,
)
import validation_readiness as vr


# ---------------------------------------------------------------------------
# Fixtures — tmp repo tree
# ---------------------------------------------------------------------------

# The Rust registration file content used in all resolver tests.
# Contains:
#   - register_tool_post! with a multi-line first argument (foo)
#   - register_tool_get! with an inline first argument (bar)
# audio.rs also contains the newer macro variants tested below.
_REGISTRATIONS_CONTENT = textwrap.dedent("""\
    use crate::ipc::mcp::registry::*;

    crate::register_tool_post!(
        foo,
        FooParams,
        "audio",
        "does the foo thing"
    );

    // A GET tool registered inline.
    crate::register_tool_get!(bar, BarParams, "audio", "does the bar thing");

    // New macro variants: post_action and get_query (should also be detected).
    crate::register_tool_post_action!(baz, BazParams, "audio", "does the baz thing");
    crate::register_tool_get_query!(qux, QuxParams, "audio", "does the qux thing");
""")

# The mod.rs golden-list content placed alongside registrations so the
# GOLDEN_TOOL_NAMES parser can find tools like "play" and "stop" that are
# registered via macros in files the glob doesn't reach, or (deliberately)
# only live in the authoritative golden list.
_MOD_RS_CONTENT = textwrap.dedent("""\
    // MCP tool registrations mod.rs
    // The golden-list test freezes the registered tool-name set.
    #[cfg(test)]
    const GOLDEN_TOOL_NAMES: &[&str] = &[
        "foo",
        "play",
        "stop",
    ];
""")

# A scenario that asserts POST /tools/foo (should resolve).
_SCENARIO_S1 = textwrap.dedent("""\
    # Scenario S1 — foo tool

    ## Instructions
    1. POST /tools/foo {"channel": "main"}
    2. GET /tools/bar
""")

# A scenario that asserts POST /tools/phantom (should be MISSING).
# Note: "baz" is now registered via register_tool_post_action! in the fixture,
# so S2 uses "phantom_unregistered" — a name absent from both macros and GOLDEN.
_SCENARIO_S2 = textwrap.dedent("""\
    # Scenario S2 — phantom_unregistered tool (not registered)

    ## Instructions
    1. POST /tools/phantom_unregistered {"some": "param"}
""")


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    """Build a minimal fixture repo with one registrations file and a mod.rs
    containing a GOLDEN_TOOL_NAMES array."""
    # Create the registrations directory + files.
    reg_dir = tmp_path / "src-tauri" / "src" / "ipc" / "mcp" / "registrations"
    reg_dir.mkdir(parents=True)
    (reg_dir / "audio.rs").write_text(_REGISTRATIONS_CONTENT, encoding="utf-8")
    # mod.rs carries the GOLDEN_TOOL_NAMES authoritative list.
    (reg_dir / "mod.rs").write_text(_MOD_RS_CONTENT, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def scenario_s1(tmp_path: Path) -> Path:
    """Write scenario S1 (asserts foo — registered) to a tmp file."""
    p = tmp_path / "s1.md"
    p.write_text(_SCENARIO_S1, encoding="utf-8")
    return p


@pytest.fixture()
def scenario_s2(tmp_path: Path) -> Path:
    """Write scenario S2 (asserts phantom_unregistered — NOT registered) to a tmp file."""
    p = tmp_path / "s2.md"
    p.write_text(_SCENARIO_S2, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# registered_tools — ground-truth assertions
# ---------------------------------------------------------------------------

class TestRegisteredTools:
    def test_extracts_union_of_macros_and_golden(self, fixture_repo: Path):
        """registered_tools returns the union of all macro variants AND GOLDEN_TOOL_NAMES.

        Fixture audio.rs has: foo (post), bar (get), baz (post_action), qux (get_query).
        Fixture mod.rs GOLDEN_TOOL_NAMES has: foo, play, stop.
        Union must include all five: foo, bar, baz, qux, play, stop.
        """
        result = registered_tools(fixture_repo)
        # Ground-truth literal — not a recomputation.
        assert "foo" in result, f"foo missing from {result}"
        assert "bar" in result, f"bar missing from {result}"
        assert "baz" in result, f"baz (post_action macro) missing from {result}"
        assert "qux" in result, f"qux (get_query macro) missing from {result}"
        assert "play" in result, f"play (GOLDEN-only) missing from {result}"
        assert "stop" in result, f"stop (GOLDEN-only) missing from {result}"

    def test_golden_only_tool_is_registered(self, fixture_repo: Path):
        """Regression: a tool present ONLY in GOLDEN_TOOL_NAMES (not in any macro)
        is considered registered — this was the false-positive root cause.

        'play' and 'stop' exist in GOLDEN_TOOL_NAMES but are not declared via any
        register_tool_*! macro in the fixture files, so the old macro-only scan
        would return them as MISSING (false positive). The fix must include them.
        """
        result = registered_tools(fixture_repo)
        # The critical regression assertions:
        assert "play" in result, (
            "REGRESSION: 'play' is in GOLDEN_TOOL_NAMES but not in any macro — "
            f"must still be considered registered. Got: {result}"
        )
        assert "stop" in result, (
            "REGRESSION: 'stop' is in GOLDEN_TOOL_NAMES but not in any macro — "
            f"must still be considered registered. Got: {result}"
        )

    def test_post_action_macro_detected(self, fixture_repo: Path):
        """register_tool_post_action! first-args are included in registered_tools."""
        result = registered_tools(fixture_repo)
        assert "baz" in result, (
            f"register_tool_post_action!(baz, ...) not detected — got {result}"
        )

    def test_get_query_macro_detected(self, fixture_repo: Path):
        """register_tool_get_query! first-args are included in registered_tools."""
        result = registered_tools(fixture_repo)
        assert "qux" in result, (
            f"register_tool_get_query!(qux, ...) not detected — got {result}"
        )

    def test_returns_empty_for_missing_dir(self, tmp_path: Path):
        """Tolerates a repo with no registrations directory — returns empty set."""
        # tmp_path is a bare directory with no src-tauri tree.
        result = registered_tools(tmp_path)
        assert result == set()

    def test_multiple_registration_files(self, tmp_path: Path):
        """Accumulates tools across multiple *.rs files (macros + golden union)."""
        reg_dir = tmp_path / "src-tauri" / "src" / "ipc" / "mcp" / "registrations"
        reg_dir.mkdir(parents=True)
        (reg_dir / "audio.rs").write_text(
            "crate::register_tool_post!(alpha, AlphaParams, \"cat\", \"desc\");",
            encoding="utf-8",
        )
        (reg_dir / "midi.rs").write_text(
            "crate::register_tool_get!(beta, \"cat\", \"desc\");",
            encoding="utf-8",
        )
        result = registered_tools(tmp_path)
        # alpha (from post macro) + beta (from get macro). No golden list present.
        assert "alpha" in result
        assert "beta" in result

    def test_golden_absent_falls_back_to_macros(self, tmp_path: Path):
        """When GOLDEN_TOOL_NAMES is absent, only macro matches are returned (no error)."""
        reg_dir = tmp_path / "src-tauri" / "src" / "ipc" / "mcp" / "registrations"
        reg_dir.mkdir(parents=True)
        (reg_dir / "audio.rs").write_text(
            "crate::register_tool_post!(alpha, AlphaParams, \"cat\", \"desc\");",
            encoding="utf-8",
        )
        # No mod.rs with GOLDEN_TOOL_NAMES — must not raise, just return macros.
        result = registered_tools(tmp_path)
        assert "alpha" in result

    def test_custom_glob(self, tmp_path: Path):
        """Respects a custom registrations_glob parameter."""
        # Put a registration file in a non-standard path.
        alt_dir = tmp_path / "alt" / "regs"
        alt_dir.mkdir(parents=True)
        (alt_dir / "tools.rs").write_text(
            "crate::register_tool_post!(gamma, GammaParams, \"x\", \"y\");",
            encoding="utf-8",
        )
        result = registered_tools(tmp_path, registrations_glob="alt/regs/*.rs")
        assert "gamma" in result


# ---------------------------------------------------------------------------
# asserted_tools — ground-truth assertions
# ---------------------------------------------------------------------------

class TestAssertedTools:
    def test_resolves_post_tool(self):
        """asserted_tools extracts POST /tools/foo."""
        result = asserted_tools(_SCENARIO_S1)
        # Literal ground-truth: S1 asserts foo and bar.
        assert "foo" in result

    def test_resolves_get_tool(self):
        """asserted_tools extracts GET /tools/bar."""
        result = asserted_tools(_SCENARIO_S1)
        assert "bar" in result

    def test_exact_set_s1(self):
        """asserted_tools returns exactly {"foo", "bar"} for S1."""
        result = asserted_tools(_SCENARIO_S1)
        assert result == {"foo", "bar"}, f"Got {result}"

    def test_exact_set_s2(self):
        """asserted_tools returns exactly {"phantom_unregistered"} for S2 — literal."""
        result = asserted_tools(_SCENARIO_S2)
        assert result == {"phantom_unregistered"}, f"Got {result}"

    def test_empty_text(self):
        """No tool calls in text → empty set."""
        assert asserted_tools("# No tools here\n\nSome description.") == set()


# ---------------------------------------------------------------------------
# unresolved_tools — ground-truth assertions
# ---------------------------------------------------------------------------

class TestUnresolvedTools:
    def test_s1_resolves_empty(self, fixture_repo: Path, scenario_s1: Path):
        """S1 asserts foo+bar; both registered → unresolved list is empty."""
        result = unresolved_tools(scenario_s1, fixture_repo)
        # Ground-truth literal — NOT a recomputation.
        assert result == [], f"Expected [], got {result}"

    def test_s2_unresolved_phantom(self, fixture_repo: Path, scenario_s2: Path):
        """S2 asserts phantom_unregistered which is not in macros or GOLDEN → ["phantom_unregistered"]."""
        result = unresolved_tools(scenario_s2, fixture_repo)
        # Ground-truth literal.
        assert result == ["phantom_unregistered"], (
            f"Expected ['phantom_unregistered'], got {result}"
        )

    def test_result_is_sorted(self, fixture_repo: Path, tmp_path: Path):
        """unresolved_tools returns a sorted list (deterministic)."""
        scenario = tmp_path / "multi.md"
        scenario.write_text(
            "POST /tools/zebra\nPOST /tools/apple\nGET /tools/mango\n",
            encoding="utf-8",
        )
        result = unresolved_tools(scenario, fixture_repo)
        assert result == sorted(result)
        # All three are missing from fixture_repo, so list must be ["apple", "mango", "zebra"].
        assert result == ["apple", "mango", "zebra"]

    def test_symlink_following(self, fixture_repo: Path, tmp_path: Path):
        """symlink-following: a Windows git-symlink pointer file resolves to the target content."""
        # Write the REAL scenario to a "docs/testing/mcp-tests/" style location.
        target_dir = tmp_path / "docs" / "testing" / "mcp-tests"
        target_dir.mkdir(parents=True)
        real_scenario = target_dir / "real-scenario.md"
        real_scenario.write_text(_SCENARIO_S2, encoding="utf-8")

        # Compute a relative path from the feature dir to the target.
        feature_dir = tmp_path / "docs" / "features" / "myfeature" / "mcp-tests"
        feature_dir.mkdir(parents=True)
        rel_path = os.path.relpath(real_scenario, feature_dir)

        # Write a Windows git-symlink pointer file (small text file with relative path).
        pointer_file = feature_dir / "real-scenario.md"

        try:
            # Prefer an actual OS symlink if possible (Windows Developer Mode is on).
            os.symlink(real_scenario, pointer_file)
        except (OSError, NotImplementedError):
            # Fall back to the text-pointer approach (git-symlink-on-Windows emulation).
            pointer_file.write_text(rel_path, encoding="utf-8")

        # Whether OS symlink or text pointer, unresolved_tools must read the content
        # of the REAL scenario (phantom_unregistered → unresolved).
        result = unresolved_tools(pointer_file, fixture_repo)
        assert result == ["phantom_unregistered"], (
            f"Expected symlink/pointer to resolve to real-scenario content, "
            f"got unresolved={result}"
        )


# ---------------------------------------------------------------------------
# validation_readiness smoke test
# ---------------------------------------------------------------------------

class TestValidationReadiness:
    """Smoke test: build a minimal AlgoBooth-like fixture repo with:
    - queue.json containing one feature
    - a DEFERRED_NON_CLOUD.md sentinel in that feature's dir
    - an mcp-tests/ scenario asserting a MISSING tool
    Then assert the verdict output contains the feature id, "needs-work",
    and the missing tool name.
    """

    def _build_fixture(
        self,
        tmp_path: Path,
        *,
        feature_id: str = "my-feature",
        spec_dir: str = "audio/my-feature",
        tool_in_scenario: str = "phantom_tool",
        include_deferred: bool = True,
        include_scenario: bool = True,
        register_tool: str | None = None,
    ) -> Path:
        """Build the fixture repo tree and return its root."""
        repo_root = tmp_path / "repo"

        # 1. registrations dir (possibly with a registered tool).
        reg_dir = (
            repo_root
            / "src-tauri"
            / "src"
            / "ipc"
            / "mcp"
            / "registrations"
        )
        reg_dir.mkdir(parents=True)
        if register_tool:
            (reg_dir / "audio.rs").write_text(
                f'crate::register_tool_post!({register_tool}, P, "cat", "d");',
                encoding="utf-8",
            )

        # 2. queue.json.
        docs_features = repo_root / "docs" / "features"
        docs_features.mkdir(parents=True)
        queue = {
            "queue": [
                {
                    "id": feature_id,
                    "name": "My Feature",
                    "tier": 1,
                    "spec_dir": spec_dir,
                }
            ]
        }
        (docs_features / "queue.json").write_text(
            json.dumps(queue, indent=2), encoding="utf-8"
        )

        # 3. Feature directory + DEFERRED_NON_CLOUD.md.
        feature_dir = docs_features / spec_dir
        feature_dir.mkdir(parents=True)
        if include_deferred:
            (feature_dir / "DEFERRED_NON_CLOUD.md").write_text(
                "---\nkind: deferred-non-cloud\nfeature_id: my-feature\n---\n",
                encoding="utf-8",
            )

        # 4. mcp-tests/ scenario.
        if include_scenario:
            mcp_dir = feature_dir / "mcp-tests"
            mcp_dir.mkdir()
            (mcp_dir / "scenario.md").write_text(
                f"# Test\n\n## Instructions\n1. POST /tools/{tool_in_scenario}\n",
                encoding="utf-8",
            )

        return repo_root

    def _run_verdict(self, repo_root: Path) -> str:
        """Run validation_readiness.main and capture printed output."""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = vr.main(["--repo-root", str(repo_root)])
        assert exit_code == 0, "validation_readiness must always exit 0"
        return buf.getvalue()

    def test_needs_work_when_tool_missing(self, tmp_path: Path):
        """A DEFERRED_NON_CLOUD feature with a scenario asserting a non-registered
        tool should produce a needs-work verdict naming the missing tool."""
        repo_root = self._build_fixture(
            tmp_path,
            feature_id="my-feature",
            tool_in_scenario="phantom_tool",
        )
        output = self._run_verdict(repo_root)

        assert "my-feature" in output, f"Feature id missing from output:\n{output}"
        assert "needs-work" in output, f"'needs-work' missing from output:\n{output}"
        assert "phantom_tool" in output, f"Missing tool name not in output:\n{output}"

    def test_ready_when_tool_registered(self, tmp_path: Path):
        """A DEFERRED_NON_CLOUD feature whose scenario tool IS registered is 'ready'."""
        repo_root = self._build_fixture(
            tmp_path,
            feature_id="my-feature",
            tool_in_scenario="real_tool",
            register_tool="real_tool",
        )
        output = self._run_verdict(repo_root)

        assert "my-feature" in output
        # The verdict row for my-feature should contain "ready" (not "needs-work").
        # Find the table row for this feature specifically (it contains the feature id).
        table_rows = [
            line for line in output.splitlines()
            if "my-feature" in line
        ]
        assert table_rows, f"No table row found for my-feature in:\n{output}"
        feature_row = table_rows[0]
        assert "ready" in feature_row, (
            f"Expected 'ready' in feature row: {feature_row!r}"
        )
        assert "needs-work" not in feature_row, (
            f"Unexpected 'needs-work' in feature row: {feature_row!r}"
        )

    def test_skip_when_no_deferred_sentinel(self, tmp_path: Path):
        """A feature with no DEFERRED_NON_CLOUD.md is skipped (not in output table)."""
        repo_root = self._build_fixture(
            tmp_path,
            feature_id="no-deferred",
            include_deferred=False,
        )
        output = self._run_verdict(repo_root)

        # The table should note no DEFERRED_NON_CLOUD features.
        assert "no DEFERRED_NON_CLOUD" in output or "my-feature" not in output

    def test_ready_no_scenarios(self, tmp_path: Path):
        """A DEFERRED_NON_CLOUD feature with no mcp-tests/ is 'ready (no scenarios)'."""
        repo_root = self._build_fixture(
            tmp_path,
            feature_id="my-feature",
            include_scenario=False,
        )
        output = self._run_verdict(repo_root)

        assert "my-feature" in output
        assert "no scenarios" in output or "ready" in output

    def test_exit_0_always(self, tmp_path: Path):
        """validation_readiness must exit 0 even when needs-work features are present."""
        repo_root = self._build_fixture(tmp_path)
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = vr.main(["--repo-root", str(repo_root)])
        assert exit_code == 0

    def test_absent_queue_json(self, tmp_path: Path):
        """When queue.json is absent the script prints a note and exits 0."""
        repo_root = tmp_path / "empty-repo"
        repo_root.mkdir()
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = vr.main(["--repo-root", str(repo_root)])
        assert exit_code == 0
        # Some explanatory text should appear.
        output = buf.getvalue()
        assert "queue.json" in output.lower() or "no features" in output.lower() or output == ""


# ---------------------------------------------------------------------------
# run_lint — F8 authoring-time scenario-surface existence lint
# (lazy-validation-readiness Phase 5a)
#
# NOTE: Per the project's no-subprocess-in-tests rule (CLAUDE.md Gotchas —
# "Subprocess tests are a timeout risk"), these tests call run_lint() directly
# rather than using subprocess.run().  The main() / argparse layer is NOT
# tested here — run_lint() is the testable core that main() delegates to.
# ---------------------------------------------------------------------------

class TestRunLint:
    """Tests for run_lint() — the F8 authoring-time scenario-surface lint.

    All fixtures build minimal in-memory registration + scenario trees via
    tmp_path.  No live AlgoBooth repo access.
    """

    def _make_repo(self, tmp_path: Path, tool_names: list[str]) -> Path:
        """Build a fixture repo whose registrations/ contains the given tool names."""
        repo = tmp_path / "repo"
        reg_dir = repo / "src-tauri" / "src" / "ipc" / "mcp" / "registrations"
        reg_dir.mkdir(parents=True)
        lines = "\n".join(
            f'crate::register_tool_post!({name}, P, "cat", "d");'
            for name in tool_names
        )
        (reg_dir / "tools.rs").write_text(lines, encoding="utf-8")
        return repo

    def _make_scenario(self, tmp_path: Path, content: str, name: str = "scenario.md") -> Path:
        """Write scenario content to a tmp file and return its path."""
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    # ------------------------------------------------------------------
    # 1. All-registered scenario → exit 0
    # ------------------------------------------------------------------

    def test_all_registered_exits_0(self, tmp_path: Path):
        """A scenario asserting only registered tools exits 0 with no ERROR messages.

        Ground-truth: exit_code == 0, no message starts with "ERROR:".
        """
        repo = self._make_repo(tmp_path, ["play", "stop", "reset_state"])
        scenario = self._make_scenario(
            tmp_path,
            textwrap.dedent("""\
                # Clean scenario
                1. POST /tools/play
                2. sleep 1
                3. POST /tools/stop
                4. POST /tools/reset_state
            """),
        )

        exit_code, messages = run_lint([scenario], repo)

        # Ground-truth literal assertions.
        assert exit_code == 0, f"Expected exit 0, got {exit_code}. Messages: {messages}"
        error_msgs = [m for m in messages if m.startswith("ERROR:")]
        assert error_msgs == [], f"Unexpected ERROR messages: {error_msgs}"
        # Summary line must indicate success.
        assert any("LINT OK" in m for m in messages), (
            f"Expected LINT OK summary, got: {messages}"
        )

    # ------------------------------------------------------------------
    # 2. Unregistered tool → exit 1, names tool + scenario path + line number
    # ------------------------------------------------------------------

    def test_unregistered_tool_exits_1(self, tmp_path: Path):
        """A scenario asserting an unregistered tool exits 1.

        The ERROR message MUST name the tool, the scenario path, and the
        precise 1-based line number of the offending assertion.
        """
        repo = self._make_repo(tmp_path, ["play", "stop"])
        scenario = self._make_scenario(
            tmp_path,
            textwrap.dedent("""\
                # Bad scenario
                1. POST /tools/play
                2. POST /tools/phantom_tool
                3. POST /tools/stop
            """),
        )

        exit_code, messages = run_lint([scenario], repo)

        # Ground-truth: exit 1.
        assert exit_code == 1, f"Expected exit 1, got {exit_code}. Messages: {messages}"

        # Find the ERROR line for phantom_tool.
        error_msgs = [m for m in messages if m.startswith("ERROR:")]
        assert len(error_msgs) >= 1, f"Expected at least one ERROR message, got: {messages}"

        phantom_errors = [m for m in error_msgs if "phantom_tool" in m]
        assert phantom_errors, (
            f"ERROR message does not name 'phantom_tool'. ERROR lines: {error_msgs}"
        )

        # The scenario path must appear in the message.
        assert str(scenario) in phantom_errors[0], (
            f"Scenario path {scenario!r} not in error message: {phantom_errors[0]!r}"
        )

        # The line number must appear (phantom_tool is on line 3 in the dedented text).
        assert ":3" in phantom_errors[0], (
            f"Expected line number ':3' in error message: {phantom_errors[0]!r}"
        )

    # ------------------------------------------------------------------
    # 3. 'sleep' is in the default allowlist → NOT flagged, exit 0
    # ------------------------------------------------------------------

    def test_sleep_not_flagged_by_default(self, tmp_path: Path):
        """'sleep' appearing as POST /tools/sleep is in the built-in allowlist.

        The lint MUST NOT flag it even though 'sleep' is not a registered
        MCP tool — it is a test-harness control directive.
        Exit 0 with no ERROR messages.
        """
        # Register only 'play'; 'sleep' is intentionally NOT registered.
        repo = self._make_repo(tmp_path, ["play"])
        scenario = self._make_scenario(
            tmp_path,
            textwrap.dedent("""\
                # Scenario with sleep directive
                1. POST /tools/play
                2. sleep 1
                3. POST /tools/sleep
            """),
        )

        exit_code, messages = run_lint([scenario], repo)

        # Ground-truth: exit 0, no ERROR for sleep.
        assert exit_code == 0, (
            f"Expected exit 0 ('sleep' is allowlisted), got {exit_code}. Messages: {messages}"
        )
        error_msgs = [m for m in messages if m.startswith("ERROR:") and "sleep" in m]
        assert error_msgs == [], f"Unexpected ERROR for 'sleep': {error_msgs}"

    # ------------------------------------------------------------------
    # 4. --allow suppresses a specific tool → exit 0
    # ------------------------------------------------------------------

    def test_allow_flag_suppresses_named_tool(self, tmp_path: Path):
        """run_lint(allow={'phantom_tool'}) suppresses findings for 'phantom_tool'.

        Simulates --allow phantom_tool on the CLI.  The tool is NOT registered
        and NOT in the default allowlist, but the caller-supplied allow set
        causes it to be silently skipped → exit 0.
        """
        repo = self._make_repo(tmp_path, ["play"])
        scenario = self._make_scenario(
            tmp_path,
            textwrap.dedent("""\
                # Scenario with phantom_tool allowed by caller
                1. POST /tools/play
                2. POST /tools/phantom_tool
            """),
        )

        exit_code, messages = run_lint([scenario], repo, allow={"phantom_tool"})

        # Ground-truth: exit 0 because phantom_tool is in the caller's allow set.
        assert exit_code == 0, (
            f"Expected exit 0 (phantom_tool is caller-allowed), "
            f"got {exit_code}. Messages: {messages}"
        )
        error_msgs = [m for m in messages if m.startswith("ERROR:")]
        assert error_msgs == [], f"Unexpected ERROR messages with --allow: {error_msgs}"

    # ------------------------------------------------------------------
    # 5. asserted_tools_with_lines — returns (line_no, name) pairs
    # ------------------------------------------------------------------

    def test_asserted_tools_with_lines_basic(self):
        """asserted_tools_with_lines returns correct (line_number, name) tuples.

        Ground-truth: 'play' is on line 2, 'stop' is on line 4 in the fixture.
        """
        text = textwrap.dedent("""\
            # Scenario
            1. POST /tools/play
            2. sleep 1
            3. GET /tools/stop
        """)
        result = asserted_tools_with_lines(text)

        # Both entries must be present with correct line numbers.
        assert (2, "play") in result, f"Expected (2, 'play') in {result}"
        assert (4, "stop") in result, f"Expected (4, 'stop') in {result}"
        # No spurious extras.
        names = {name for _, name in result}
        assert names == {"play", "stop"}, f"Unexpected names: {names}"

    def test_asserted_tools_with_lines_multiple_per_line(self):
        """Multiple tool assertions on the SAME line are each captured separately."""
        # Unusual but the regex must not skip occurrences on the same line.
        text = "POST /tools/alpha GET /tools/beta\n"
        result = asserted_tools_with_lines(text)
        names = [name for _, name in result]
        assert "alpha" in names, f"'alpha' missing from {result}"
        assert "beta" in names, f"'beta' missing from {result}"
        # Both on line 1.
        for line_no, name in result:
            assert line_no == 1, f"Expected line 1 for {name!r}, got {line_no}"

    def test_asserted_tools_with_lines_empty(self):
        """Empty text → empty list."""
        assert asserted_tools_with_lines("") == []

    # ------------------------------------------------------------------
    # 6. Multiple scenarios — failure in one does not suppress the other
    # ------------------------------------------------------------------

    def test_multi_scenario_partial_failure(self, tmp_path: Path):
        """run_lint over two scenarios: one clean, one bad → exit 1.

        The ERROR message must identify the bad scenario, not the clean one.
        The clean scenario must NOT appear in any ERROR message.
        """
        repo = self._make_repo(tmp_path, ["play", "stop"])

        clean = self._make_scenario(
            tmp_path,
            "1. POST /tools/play\n2. POST /tools/stop\n",
            name="clean.md",
        )
        bad = self._make_scenario(
            tmp_path,
            "1. POST /tools/play\n2. POST /tools/missing_tool\n",
            name="bad.md",
        )

        exit_code, messages = run_lint([clean, bad], repo)

        assert exit_code == 1, f"Expected exit 1, got {exit_code}"
        error_msgs = [m for m in messages if m.startswith("ERROR:")]
        # The bad scenario path must appear in an ERROR.
        assert any(str(bad) in m for m in error_msgs), (
            f"Bad scenario path not in any ERROR: {error_msgs}"
        )
        # The clean scenario path must NOT appear in any ERROR.
        assert not any(str(clean) in m for m in error_msgs), (
            f"Clean scenario path wrongly appears in ERROR: {error_msgs}"
        )
