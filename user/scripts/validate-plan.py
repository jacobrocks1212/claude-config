#!/usr/bin/env python3
"""
validate-plan.py - Validate Claude plans against Cognito Forms coding rules

Checks plan content against rules from cognito-pr-review knowledge base.
Designed to run as a PreToolUse hook on ExitPlanMode.

Usage: python validate-plan.py <plan_file> <rules_dir>

Exit codes:
  0 - No issues found (or no plan/rules to check)
  1 - Issues found, plan should be updated
"""

import sys
import re
import os
from pathlib import Path
from typing import Optional

# PyYAML is optional - gracefully handle missing dependency
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def load_yaml_file(path: Path) -> Optional[dict]:
    """Load a YAML file, returning None on error."""
    if not HAS_YAML:
        # Fallback: basic YAML parsing for simple structure
        return parse_yaml_manually(path)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def parse_yaml_manually(path: Path) -> Optional[dict]:
    """
    Basic YAML parser for rule files (no dependencies).
    Only handles the specific structure we need from rule files.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        result = {'rules': [], 'file_patterns': [], 'category': ''}
        current_rule = None
        in_trigger_patterns = False
        in_file_patterns = False

        for line in content.split('\n'):
            stripped = line.strip()

            # Category
            if stripped.startswith('category:'):
                result['category'] = stripped.split(':', 1)[1].strip()
                continue

            # File patterns
            if stripped.startswith('file_patterns:'):
                in_file_patterns = True
                in_trigger_patterns = False
                continue

            # Rules section
            if stripped == 'rules:':
                in_file_patterns = False
                continue

            # New rule
            if stripped.startswith('- id:'):
                if current_rule:
                    result['rules'].append(current_rule)
                current_rule = {
                    'id': stripped.split(':', 1)[1].strip(),
                    'severity': 'minor',
                    'description': '',
                    'trigger_patterns': []
                }
                in_trigger_patterns = False
                in_file_patterns = False
                continue

            # Inside a rule
            if current_rule:
                if stripped.startswith('severity:'):
                    current_rule['severity'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('trigger_patterns:'):
                    in_trigger_patterns = True
                elif stripped.startswith('description:'):
                    desc = stripped.split(':', 1)[1].strip()
                    if desc.startswith('>'):
                        desc = ''  # Multi-line, we don't need full text
                    current_rule['description'] = desc
                elif in_trigger_patterns and stripped.startswith('- "'):
                    pattern = stripped[3:-1] if stripped.endswith('"') else stripped[3:]
                    current_rule['trigger_patterns'].append(pattern)
                elif in_trigger_patterns and not stripped.startswith('-'):
                    in_trigger_patterns = False

            # File patterns list items
            if in_file_patterns and stripped.startswith('- "'):
                pattern = stripped[3:-1] if stripped.endswith('"') else stripped[3:]
                result['file_patterns'].append(pattern)

        if current_rule:
            result['rules'].append(current_rule)

        return result
    except Exception:
        return None


def extract_file_extensions(plan_content: str) -> set:
    """Extract file extensions mentioned in the plan."""
    extensions = set()

    # Match file paths like path/to/file.cs, ./file.vue, file.ts
    file_pattern = r'[\w./\\-]+\.(cs|vue|ts|tsx|js|jsx|py|yaml|json|md|html|css|scss)'
    matches = re.findall(file_pattern, plan_content, re.IGNORECASE)
    extensions.update(ext.lower() for ext in matches)

    # Also check for explicit extension mentions
    ext_mention = r'\.(cs|vue|ts|tsx)\b'
    matches = re.findall(ext_mention, plan_content, re.IGNORECASE)
    extensions.update(ext.lower() for ext in matches)

    return extensions


def extract_code_blocks(plan_content: str) -> list:
    """Extract code blocks from markdown."""
    # Match ```lang ... ``` or indented code blocks
    code_pattern = r'```[\w]*\n(.*?)```'
    blocks = re.findall(code_pattern, plan_content, re.DOTALL)

    # Also include inline code that looks like code snippets
    inline_pattern = r'`([^`]+)`'
    inline = re.findall(inline_pattern, plan_content)

    return blocks + [i for i in inline if len(i) > 10]


def matches_file_patterns(patterns: list, extensions: set) -> bool:
    """Check if any file patterns match the detected extensions."""
    if not patterns:
        return True  # No patterns means always apply

    ext_map = {
        '.cs': 'cs', '.vue': 'vue', '.ts': 'ts', '.tsx': 'tsx',
        '.js': 'js', '.jsx': 'jsx', '.py': 'py'
    }

    for pattern in patterns:
        # Skip negation patterns for now
        if pattern.startswith('!'):
            continue

        # Check for extension match
        for ext in extensions:
            if f'.{ext}' in pattern or pattern.endswith(ext):
                return True
            if '*Controller.cs' in pattern and ext == 'cs':
                return True
            if '*.cs' in pattern and ext == 'cs':
                return True
            if '*.vue' in pattern and ext == 'vue':
                return True
            if '*.ts' in pattern and ext == 'ts':
                return True
            if '*.tsx' in pattern and ext == 'tsx':
                return True

    return False


def check_trigger_patterns(rule: dict, content: str, code_blocks: list) -> Optional[dict]:
    """Check if a rule's trigger patterns match the plan content."""
    trigger_patterns = rule.get('trigger_patterns', [])
    if not trigger_patterns:
        return None

    # Combine all content to search
    searchable = content + '\n' + '\n'.join(code_blocks)

    for pattern in trigger_patterns:
        try:
            # Escape special regex chars but keep the pattern intent
            escaped = re.escape(pattern).replace(r'\<', '<').replace(r'\>', '>')
            if re.search(escaped, searchable, re.IGNORECASE):
                # Find the location in the plan
                location = find_pattern_location(content, pattern)
                return {
                    'rule': rule,
                    'pattern': pattern,
                    'location': location
                }
        except re.error:
            # If regex fails, try literal match
            if pattern in searchable:
                location = find_pattern_location(content, pattern)
                return {
                    'rule': rule,
                    'pattern': pattern,
                    'location': location
                }

    return None


def find_pattern_location(content: str, pattern: str) -> str:
    """Find where in the plan a pattern matches (task number, section, etc)."""
    lines = content.split('\n')
    current_task = None
    current_section = None

    for i, line in enumerate(lines):
        # Track task headers
        if re.match(r'^###?\s*Task\s*\d+', line, re.IGNORECASE):
            current_task = line.strip('#').strip()
        elif re.match(r'^##\s+', line):
            current_section = line.strip('#').strip()

        # Check if pattern is on this line
        if pattern.lower() in line.lower():
            if current_task:
                return current_task
            elif current_section:
                return f"Section: {current_section}"
            else:
                return f"Line {i + 1}"

    return "Unknown location"


def format_output(issues: list, scope_desc: str, rules_checked: int, rule_sources: list) -> str:
    """Format the validation output."""
    lines = []

    if not issues:
        return ""

    lines.append("")
    lines.append("=" * 65)
    lines.append("  PLAN VALIDATION: Potential Issues Found")
    lines.append("=" * 65)
    lines.append("")
    lines.append(f"Scope: {scope_desc}")
    lines.append(f"Rules checked: {rules_checked} from {', '.join(rule_sources)}")
    lines.append("")
    lines.append("ISSUES TO CONSIDER:")
    lines.append("")

    for i, issue in enumerate(issues, 1):
        rule = issue['rule']
        severity = rule.get('severity', 'minor').upper()
        lines.append(f"{i}. [{rule['id']}] {severity}")
        lines.append(f"   Triggered by pattern: \"{issue['pattern']}\"")
        lines.append(f"   Location: {issue['location']}")
        if rule.get('description'):
            desc = rule['description'][:200]  # Truncate long descriptions
            lines.append(f"   Rule: {desc}")
        lines.append("")

    lines.append("-" * 65)
    lines.append("These patterns may indicate rule violations. Please review and")
    lines.append("update the plan if needed, then call ExitPlanMode again.")
    lines.append("=" * 65)

    return '\n'.join(lines)


# ===========================================================================
# --structural mode (plan-structure-authoring-gate)
# ===========================================================================
#
# Deterministic structural validator for lazy-pipeline plan parts and
# PHASES.md files, invoked at AUTHORING time by /write-plan and /spec-phases
# (and their derivatives) so a malformed plan/PHASES.md is refused before
# hand-off instead of surviving to a mid-run recovery dispatch. See
# docs/features/plan-structure-authoring-gate/SPEC.md for the full design.
#
# This is a NEW mode on the EXISTING "validate a plan" entry point (D1
# recommendation A: one entry point, two modes) — the legacy rules-mode
# above is completely untouched and has no dependency on anything below.
#
# Residency note (D1 follow-up): the SPEC's full recommendation places the
# structural CHECK FUNCTIONS inside lazy_core.py so the D4 pickup backstop
# (lazy-state.py / bug-state.py, at first `/execute-plan` routing) can call
# them in-process without shelling out to this script as a subprocess. That
# hoist is a lazy_core.py edit and is explicitly out of scope for the SKILLS
# lane that authored this mode — see the feature's PHASES.md Phase 4 /
# NEEDS_INPUT_PROVISIONAL.md. Everything below is therefore self-contained:
# it IMPORTS (never edits, never re-implements the substance of) a handful of
# already-existing, exception-free lazy_core parsers/constants for parity —
# _plan_wu_checkbox_counts, remaining_unchecked_are_verification_only,
# _VERIFICATION_ONLY_MARKER, _VERIFICATION_SECTION_RE, _DELIVERABLES_SECTION_RE,
# _PLAN_PART_RE — and reimplements ONLY the frontmatter-adjacent helpers that
# would otherwise risk an uncontrolled process exit (see
# _read_frontmatter_safe below) with lightweight, exception-safe siblings.

STRUCTURAL_ERROR = "ERROR"
STRUCTURAL_WARN = "WARN"


class StructuralFinding:
    """One structural-gate finding: a severity, a rule id, an optional line
    number, and a human-readable message naming the fix."""

    __slots__ = ("severity", "rule", "line", "message")

    def __init__(self, severity, rule, line, message):
        self.severity = severity
        self.rule = rule
        self.line = line
        self.message = message

    def format(self):
        loc = f":{self.line}" if self.line else ""
        return f"[{self.severity}] ({self.rule}){loc} {self.message}"


def _structural_scripts_dir():
    return Path(__file__).resolve().parent


def _load_lazy_core():
    """Import the lazy_core package from this script's own directory.

    lazy_core is now a package (user/scripts/lazy_core/) behind a PEP 562
    facade; sys.path-based import replaces the old flat-file
    spec_from_file_location so both direct-path and ~/.claude/scripts-symlink
    invocations resolve to the same real package. If lazy_core is already
    imported in this process (e.g. under pytest), the cached module is
    returned unchanged.
    """
    import importlib
    import sys

    scripts_dir = str(_structural_scripts_dir())
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return importlib.import_module("lazy_core")


_STRUCTURAL_FENCE = "---"


def _read_frontmatter_safe(path_or_text, is_text=False):
    """Non-throwing frontmatter reader.

    Mirrors lazy_core.parse_sentinel's tolerant-fence-then-YAML logic, but
    NEVER calls sys.exit() on a malformed file. A structural validator's job
    is to collect and report EVERY finding in one pass, including "the
    frontmatter itself is broken" — it must not abort the process on the
    first such file the way lazy_core's own `_die()`-backed parser does
    (that parser is correct for its own callers, which want a hard stop; a
    linter wants a reported ERROR/WARN and to keep going).

    Returns (meta_dict_or_None, error_str_or_None). meta == {} means "no
    frontmatter block at all" (a legacy file — NOT an error).
    """
    if is_text:
        raw = path_or_text
    else:
        try:
            raw = Path(path_or_text).read_text(encoding="utf-8")
        except OSError as exc:
            return None, f"cannot read file: {exc}"

    lines = raw.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != _STRUCTURAL_FENCE:
        return {}, None
    start = i + 1
    end = None
    for j in range(start, len(lines)):
        if lines[j].strip() == _STRUCTURAL_FENCE:
            end = j
            break
    if end is None:
        return None, "frontmatter missing closing '---'"
    yaml_body = "\n".join(lines[start:end])
    if not HAS_YAML:
        return None, "PyYAML not installed — cannot parse frontmatter"
    try:
        data = yaml.safe_load(yaml_body) or {}
    except Exception as exc:
        return None, f"invalid YAML frontmatter: {exc}"
    if not isinstance(data, dict):
        return None, "frontmatter must be a YAML mapping"
    return data, None


def _local_plan_series_index(path, lazy_core):
    """Exception-safe sibling of lazy_core._plan_series_index — same
    filename-suffix + optional series_index: frontmatter override logic,
    reusing the canonical _PLAN_PART_RE constant (imported, never
    re-declared) so filename parsing can never drift from the state
    machine's own reading of it."""
    meta, _err = _read_frontmatter_safe(path)
    if meta:
        raw = meta.get("series_index")
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
    m = lazy_core._PLAN_PART_RE.search(Path(path).name)
    if m:
        return int(m.group(1))
    return None


def _local_plan_phase_set(path):
    """Exception-safe sibling of lazy_core._plan_phase_set."""
    meta, _err = _read_frontmatter_safe(path)
    out = set()
    if not meta:
        return out
    raw = meta.get("phases")
    if not isinstance(raw, list):
        return out
    for entry in raw:
        try:
            out.add(int(entry))
            continue
        except (TypeError, ValueError):
            pass
        if isinstance(entry, str):
            m = re.match(r"^(\d+)", entry)
            if m:
                out.add(int(m.group(1)))
    return out


_ROW_RE = re.compile(r"^(\s*-\s*\[[ xX]\])\s*(.*)$")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
_BOLD_LEAD_RE = re.compile(r"^\*\*(.+?)\*\*")

# Verification-vocabulary detector for rule 2 (placement). Deliberately a
# SEPARATE regex from lazy_core._VERIFICATION_SECTION_RE (which detects
# SECTION HEADERS) — this one detects verification-SHAPED CHECKBOX ROWS
# regardless of where they sit, which is the whole point of a placement
# check.
#
# Deliberately NARROW (tuned against the real committed corpus — see the
# feature's PHASES.md Phase 1 corpus check). Two broader candidates were
# tried and dropped because they false-positived on ordinary, already-
# correct PHASES.md prose: a bare "runtime verification" match flags any row
# that merely CROSS-REFERENCES the section by name ("(see Runtime
# Verification below)" — a completely normal deliverable-row habit), and a
# bare "VALIDATED.md" match flags any row that merely NAMES that sentinel in
# an enumeration of pipeline filenames (extremely common prose in this
# repo's own PHASES.md files, which document the pipeline that produces
# VALIDATED.md). Both landed 13/13 false positives across the corpus with
# zero true positives. The retained vocabulary — "mcp integration test" /
# "mcp test assertion" / "mcp assertion" / "reachability smoke" — is the
# self-describing tag language the templates actually emit ON a verification
# row (phases-runtime-verification.md's own example rows), so a row genuinely
# misplaced under Deliverables still carries one of these phrases; a row that
# merely discusses verification concepts in passing does not.
_VERIFICATION_VOCAB_RE = re.compile(
    r"mcp\s+(?:integration\s+test|test\s+assertion|assertion)"
    r"|reachability\s+smoke",
    re.IGNORECASE,
)

# Unfilled template-placeholder detector (rule 3). The real skeleton rows in
# spec-phases/write-plan/phases-runtime-verification (grepped from the actual
# templates) are ALWAYS a whole-row placeholder span — the row's entire
# remaining text (after an optional short "Label: " prefix) is one bracket
# span with nothing else around it, e.g. "{Concrete code output 1}",
# "Tests: {What tests verify this phase}", "WU-N — <short title>". A NAIVE
# "does the row contain any {…}/<…> anywhere" search over-matches wildly on
# real committed rows — HTML comments like "<!-- verification-only -->" (a
# canonical marker THIS validator itself relies on) and ordinary prose
# mentioning a bracketed path/placeholder mid-sentence (`` `<slug>/` ``,
# `<real-checkout>`) both false-positive under that shape (measured against
# the full real corpus at authoring time — see the feature's PHASES.md
# Phase 1 corpus check). So this rule (a) strips HTML comments first, then
# (b) requires the row's ENTIRE remaining text to BE the placeholder span
# (anchored start-to-end), not merely contain one.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->")
_TEMPLATE_WHOLE_ROW_RE = re.compile(
    r"^\s*(?:[A-Za-z][\w /'-]{0,30}:\s*)?[{<][^{}<>]{1,160}[}>]\s*$"
)
_WU_GENERIC_TITLE_RE = re.compile(r"^WU-\S+\s*[—-]\s*<[^<>]{1,60}>\s*$")


def _is_template_row(row_text):
    """True iff `row_text` (the checkbox row's text, marker/prefix included)
    is one of the known unfilled-template-skeleton shapes, not merely a row
    that happens to contain a bracket somewhere."""
    cleaned = _HTML_COMMENT_RE.sub("", row_text).strip()
    if not cleaned:
        return False
    if _TEMPLATE_WHOLE_ROW_RE.match(cleaned):
        return True
    if _WU_GENERIC_TITLE_RE.match(cleaned):
        return True
    return False

# Gate-owned-row ban (rule 4) — the phases-runtime-verification.md /
# write-plan ISSUE-6 prose ban, mechanized. Deliberately narrow (requires
# BOTH a status/receipt/roadmap noun AND a completion verb nearby) so an
# ordinary doc-edit deliverable ("Update SPEC §4 wording") never trips it.
_GATE_OWNED_RE = re.compile(
    r"(?:update|flip|set)\s+.{0,60}?\b(?:status|spec\.md|phases\.md)\b.{0,40}?\bcomplete\b"
    r"|\bwrit(?:e|es|ing)\s+.{0,20}?\b(?:COMPLETED|FIXED)\.md\b"
    r"|\bmark(?:s|ing)?\s+.{0,20}?\bROADMAP(?:\.md)?\b.{0,20}?\b(?:complete|done|strike)\b"
    r"|\barchive\s+(?:the\s+)?(?:move|feature|bug)\b",
    re.IGNORECASE,
)

# Rule 5 (series-vs-dependency order) input parsing.
_ENTRY_CRITERIA_RE = re.compile(r"\*\*(?:Entry criteria|Prerequisites):\*\*\s*(.*)", re.IGNORECASE)

# A bare "Phase N" mention in Entry-criteria/Prerequisites prose is NOT
# reliably a dependency declaration in the "this part needs Phase N first"
# direction — real corpus content includes forward-looking prose like "Phase
# 3 establishes the pattern Phase 4 propagates" (Phase 3 is UPSTREAM of
# Phase 4, the opposite direction), which a bare "Phase N" scan mis-flags.
# Require a completion word closely following the mention, or a dependency
# verb closely preceding it — the two phrasings real Entry-criteria/
# Prerequisites content actually uses ("Foundation Phase 1 complete",
# "Phase 6 complete", "requires Phase 2", "blocked by Phase 3").
_PREREQ_PHASE_COMPLETE_RE = re.compile(
    r"\bphase\s+(\d+)\s+(?:is\s+)?(?:complete|completed|done|finished)\b",
    re.IGNORECASE,
)
_PREREQ_PHASE_VERB_RE = re.compile(
    r"\b(?:requires?|depends?\s+on|blocked\s+by|needs?|after)\s+phase\s+(\d+)\b",
    re.IGNORECASE,
)


def _extract_prereq_phases(criteria_text):
    nums = set()
    for m in _PREREQ_PHASE_COMPLETE_RE.finditer(criteria_text):
        nums.add(int(m.group(1)))
    for m in _PREREQ_PHASE_VERB_RE.finditer(criteria_text):
        nums.add(int(m.group(1)))
    return nums


def _iter_checkbox_rows(text, lazy_core):
    """Yield (line_no, raw_line, row_text, in_verification_scope) for every
    '- [ ]'/'- [x]' row in `text`, fence-aware.

    Section tracking mirrors the essential shape of
    lazy_core.remaining_unchecked_are_verification_only closely enough for a
    PLACEMENT check (a heading or bold-marker line matching
    _VERIFICATION_SECTION_RE — or carrying the canonical
    _VERIFICATION_ONLY_MARKER — enters verification scope; a bold marker
    matching _DELIVERABLES_SECTION_RE exits it). It is deliberately NOT a
    byte-identical reimplementation of that function's full Superseded/
    descoped-row bookkeeping (irrelevant to placement) — see the SPEC's
    "Recognizer parity" cross-check test for the fixtures this is validated
    against. All vocabulary regexes are IMPORTED from lazy_core, never
    re-declared, so the two can never silently diverge on WHICH words count.
    """
    in_fence = False
    in_verification = False
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = _HEADING_RE.match(stripped)
        if heading:
            marker_here = lazy_core._VERIFICATION_ONLY_MARKER in line
            in_verification = marker_here or bool(
                lazy_core._VERIFICATION_SECTION_RE.search(heading.group(1))
            )
            continue
        bold = _BOLD_LEAD_RE.match(stripped)
        if bold:
            inner = bold.group(1)
            marker_here = lazy_core._VERIFICATION_ONLY_MARKER in line
            if marker_here or lazy_core._VERIFICATION_SECTION_RE.search(inner):
                in_verification = True
                continue
            if lazy_core._DELIVERABLES_SECTION_RE.search(inner):
                in_verification = False
                continue
            continue
        m = _ROW_RE.match(line)
        if m:
            row_verif = in_verification or (lazy_core._VERIFICATION_ONLY_MARKER in line)
            yield i, line, m.group(2), row_verif


def rule_wu_checklist(plan_text, lazy_core):
    """Rule 1 (ERROR, plan parts only) — write-plan ISSUE-6: at least one
    parseable '- [ ] WU-N' / '- [x] WU-N' row must exist."""
    findings = []
    unchecked, checked = lazy_core._plan_wu_checkbox_counts(plan_text)
    if unchecked + checked == 0:
        findings.append(StructuralFinding(
            STRUCTURAL_ERROR, "wu-checklist", None,
            "No per-WU '- [ ] WU-N' checklist rows found. write-plan ISSUE-6 requires a "
            "'## Work Units' flat checklist with at least one '- [ ] WU-N' / '- [x] WU-N' "
            "row — verify-ledger reads these rows as the deliverables_done source of truth "
            "and /execute-plan resume reads them for resume granularity."
        ))
    return findings


def rule_verification_placement(text, lazy_core):
    """Rule 2 (ERROR, plans + PHASES) — a verification-vocabulary checkbox
    row must sit under a recognized Runtime Verification subsection."""
    findings = []
    for line_no, raw_line, row_text, in_verif in _iter_checkbox_rows(text, lazy_core):
        if in_verif:
            continue
        if _VERIFICATION_VOCAB_RE.search(row_text):
            findings.append(StructuralFinding(
                STRUCTURAL_ERROR, "verif-placement", line_no,
                "Verification/MCP-assertion checkbox outside a recognized 'Runtime "
                "Verification' / 'MCP Integration Test Assertions' subsection "
                f"(move it under that heading, tagged with the canonical "
                f"{lazy_core._VERIFICATION_ONLY_MARKER} marker): {raw_line.strip()!r}"
            ))
    return findings


def rule_template_rows(text, lazy_core):
    """Rule 3 (ERROR, plans + PHASES) — unfilled template placeholders."""
    findings = []
    for line_no, raw_line, row_text, _in_verif in _iter_checkbox_rows(text, lazy_core):
        if _is_template_row(row_text):
            findings.append(StructuralFinding(
                STRUCTURAL_ERROR, "template-row", line_no,
                f"Unfilled template placeholder in checkbox row: {raw_line.strip()!r}"
            ))
    return findings


def rule_gate_owned_rows(text, lazy_core):
    """Rule 4 (ERROR, plans + PHASES) — pipeline-owned actions (Status flip,
    receipt write, ROADMAP mark, archive move) are never checkbox rows."""
    findings = []
    for line_no, raw_line, row_text, _in_verif in _iter_checkbox_rows(text, lazy_core):
        if _GATE_OWNED_RE.search(row_text):
            findings.append(StructuralFinding(
                STRUCTURAL_ERROR, "gate-owned-row", line_no,
                "Pipeline-owned action authored as a checkbox row (Status flips, "
                "COMPLETED.md/FIXED.md receipt writes, ROADMAP marks, and archive "
                "moves are __mark_complete__/__mark_fixed__-gate-owned — author a "
                "prose '**Completion (gate-owned):**' note instead): "
                f"{raw_line.strip()!r}"
            ))
    return findings


def _sibling_glob_pattern(name, lazy_core):
    prefix = lazy_core._PLAN_PART_RE.sub("", name)
    return f"{prefix}-part-*.md"


def rule_series_dependency_order(plan_path, plan_text, lazy_core):
    """Rule 5 (ERROR, plan parts only) — a part's declared prerequisite
    (an Entry-criteria/Prerequisites 'Phase N' mention resolving to a
    SIBLING part's phase set) must live in a part whose series index does
    not exceed this part's — the authoring-side closure of the
    phase-number-inversion impasse _plan_sort_key's series-index ordering
    fix relies on producers upholding. N/A (no findings) for a plan with no
    '-part-K' series (single-part or legacy plan — no series to validate)."""
    findings = []
    plan_path = Path(plan_path)
    idx = _local_plan_series_index(plan_path, lazy_core)
    if idx is None:
        return findings
    pattern = _sibling_glob_pattern(plan_path.name, lazy_core)
    phase_to_series = {}
    for sib in sorted(plan_path.parent.glob(pattern)):
        sib_idx = _local_plan_series_index(sib, lazy_core)
        if sib_idx is None:
            continue
        for ph in _local_plan_phase_set(sib):
            phase_to_series[ph] = sib_idx
    own_phases = _local_plan_phase_set(plan_path)
    for m in _ENTRY_CRITERIA_RE.finditer(plan_text):
        criteria_text = m.group(1)
        line_no = plan_text.count("\n", 0, m.start()) + 1
        for phase_num in _extract_prereq_phases(criteria_text):
            if phase_num in own_phases:
                continue  # same-part reference — fine
            prereq_series = phase_to_series.get(phase_num)
            if prereq_series is None:
                continue  # not a phase any sibling part declares — out of scope
                          # (e.g. an upstream-feature phase reference)
            if prereq_series > idx:
                findings.append(StructuralFinding(
                    STRUCTURAL_ERROR, "series-order", line_no,
                    f"Entry criteria declares a prerequisite on Phase {phase_num} "
                    f"(scheduled in part-{prereq_series}), but this file is "
                    f"part-{idx} — the prerequisite's part must have a series "
                    f"index that does not exceed this part's ('Execute parts "
                    f"strictly in order' contract)."
                ))
    return findings


def rule_frontmatter_sanity(plan_path, plan_text, lazy_core):
    """Rule 6 (WARN, plan parts only) — parseable frontmatter, numeric-ish
    'phases:' entries, no duplicate WU numbers."""
    findings = []
    meta, err = _read_frontmatter_safe(plan_path)
    if err:
        findings.append(StructuralFinding(STRUCTURAL_WARN, "frontmatter", None, err))
        return findings
    if not meta:
        findings.append(StructuralFinding(
            STRUCTURAL_WARN, "frontmatter", None,
            "No parseable frontmatter block found (legacy plan)."
        ))
        return findings
    phases_raw = meta.get("phases")
    if phases_raw is not None:
        if not isinstance(phases_raw, list):
            findings.append(StructuralFinding(
                STRUCTURAL_WARN, "frontmatter", None,
                f"'phases:' is not a list: {phases_raw!r}"
            ))
        else:
            for entry in phases_raw:
                numeric_ish = isinstance(entry, int) or (
                    isinstance(entry, str) and re.match(r"^\d", entry)
                )
                if not numeric_ish:
                    findings.append(StructuralFinding(
                        STRUCTURAL_WARN, "frontmatter", None,
                        f"Non-numeric-ish 'phases:' entry: {entry!r}"
                    ))
    wu_nums = re.findall(r"-\s*\[[ xX]\]\s*WU-([A-Za-z0-9.]+)", plan_text)
    seen = set()
    dups = set()
    for n in wu_nums:
        if n in seen:
            dups.add(n)
        seen.add(n)
    for d in sorted(dups):
        findings.append(StructuralFinding(
            STRUCTURAL_WARN, "frontmatter", None, f"Duplicate WU number: WU-{d}"
        ))
    return findings


def _classify_structural_target(path):
    """Path-convention scope gate (the SPEC's "Failure states" carve-out):
    returns 'phases', 'plan', or None (out of scope — passes untouched).

    A `plans/cloud-*.md` file is /write-plan-cloud's output — a categorically
    different artifact (a self-contained GitHub-Copilot-cloud-agent briefing
    for a different repo/consumer) whose own contract explicitly BANS the
    checkbox format this gate's rules assume (see write-plan-cloud/SKILL.md
    Step 4 item 7: "No progress checkboxes"). Wiring these rules onto it
    would force an incompatible format onto a document engineered not to
    have it, so it is excluded by path convention like any other
    non-lazy-plan-shaped file.
    """
    name = path.name
    if name == "PHASES.md":
        return "phases"
    if path.parent.name == "plans" and path.suffix.lower() == ".md":
        if name.startswith("cloud-"):
            return None
        return "plan"
    return None


def run_structural_checks(path):
    """Run the full structural check set against `path`. Returns
    (report_lines, exit_code) — exit_code is 1 iff any ERROR finding fired,
    0 otherwise (WARN-only or clean). Never raises: an unreadable/unparseable
    file is reported as an ERROR finding, never a silent pass."""
    path = Path(path)
    if not path.exists():
        return ([f"[ERROR] (io) file not found: {path}"], 1)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ([f"[ERROR] (io) cannot read file: {exc}"], 1)

    kind = _classify_structural_target(path)
    if kind is None:
        return (
            [f"(out of scope — not a recognized lazy plan/PHASES file by path "
             f"convention: {path}) — passes untouched"],
            0,
        )

    try:
        lazy_core = _load_lazy_core()
    except Exception as exc:  # noqa: BLE001 — honor the never-raises contract
        # INFRASTRUCTURE failure: the gate MACHINERY is broken (lazy_core
        # unimportable), which is categorically different from "the plan is
        # imperfect". Report it as a loud ERROR finding — NEVER a silent
        # pass and NEVER a raise (the raise is exactly what let
        # plan_structural_backstop's broad fail-open silently disarm this
        # gate repo-wide when the flat lazy_core.py was deleted — see
        # docs/bugs/plan-structural-backstop-silent-disarm-on-infrastructure-failure).
        return (
            [f"[ERROR] (infrastructure) cannot load lazy_core (the "
             f"structural rules' shared parser source) — gate machinery "
             f"broken, plan NOT validated: {type(exc).__name__}: {exc}"],
            1,
        )
    findings = []
    if kind == "phases":
        findings += rule_verification_placement(text, lazy_core)
        findings += rule_template_rows(text, lazy_core)
        findings += rule_gate_owned_rows(text, lazy_core)
    else:
        # Rules 1 (WU checklist) and 5 (series order) assume the write-plan
        # implementation-plan/fix-plan shape (a flat '## Work Units' checklist,
        # a '-part-K' execution series). retro-plan / realign-plan carry a
        # DIFFERENT, deliberately checklist-free shape (see plan-frontmatter.md's
        # kind taxonomy) — applying those two rules to them would flag their
        # correct-by-design absence of a WU checklist as a defect. Rules 2-4 and
        # 6 (placement/template/gate-owned/frontmatter-sanity) are shape-agnostic
        # and still apply to every plan-part kind.
        meta, _err = _read_frontmatter_safe(path)
        plan_kind = (meta or {}).get("kind")
        applies_wu_rules = plan_kind not in ("retro-plan", "realign-plan")

        if applies_wu_rules:
            findings += rule_wu_checklist(text, lazy_core)
        findings += rule_verification_placement(text, lazy_core)
        findings += rule_template_rows(text, lazy_core)
        findings += rule_gate_owned_rows(text, lazy_core)
        if applies_wu_rules:
            findings += rule_series_dependency_order(path, text, lazy_core)
        findings += rule_frontmatter_sanity(path, text, lazy_core)

    lines = [f.format() for f in findings]
    has_error = any(f.severity == STRUCTURAL_ERROR for f in findings)
    return (lines, 1 if has_error else 0)


def main_structural(argv):
    if not argv:
        print("Usage: python validate-plan.py --structural <plan_or_phases_file>", file=sys.stderr)
        return 2
    target = argv[0]
    lines, code = run_structural_checks(target)
    if lines:
        print(f"\nSTRUCTURAL VALIDATION: {target}")
        for line in lines:
            print("  " + line)
        print()
    else:
        print(f"STRUCTURAL VALIDATION: {target} — clean (no findings)")
    return code


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--structural":
        sys.exit(main_structural(argv[1:]))

    if len(sys.argv) < 3:
        print("Usage: python validate-plan.py <plan_file> <rules_dir>", file=sys.stderr)
        sys.exit(0)  # Don't block on usage error

    plan_file = Path(sys.argv[1])
    rules_dir = Path(sys.argv[2])

    # Validate inputs
    if not plan_file.exists():
        sys.exit(0)  # No plan file, allow ExitPlanMode

    if not rules_dir.exists():
        print(f"Warning: Rules directory not found: {rules_dir}", file=sys.stderr)
        sys.exit(0)  # No rules, allow ExitPlanMode

    # Read plan content
    try:
        plan_content = plan_file.read_text(encoding='utf-8')
    except Exception as e:
        print(f"Warning: Could not read plan file: {e}", file=sys.stderr)
        sys.exit(0)

    # Detect scope from file extensions mentioned in plan
    extensions = extract_file_extensions(plan_content)
    code_blocks = extract_code_blocks(plan_content)

    # Determine scope description
    scope_parts = []
    if 'cs' in extensions:
        scope_parts.append('Backend (C#)')
    if any(e in extensions for e in ['vue', 'ts', 'tsx', 'js', 'jsx']):
        scope_parts.append('Frontend (Vue/TS)')
    scope_desc = ', '.join(scope_parts) if scope_parts else 'General'

    # Load relevant rule files
    issues = []
    rules_checked = 0
    rule_sources = []

    for rule_file in rules_dir.glob('*.yaml'):
        rule_data = load_yaml_file(rule_file)
        if not rule_data:
            continue

        # Check if this rule file applies to the detected scope
        file_patterns = rule_data.get('file_patterns', [])

        # Always include performance and security, code-consistency
        always_include = ['performance', 'security', 'code-consistency']
        category = rule_data.get('category', rule_file.stem)

        if category not in always_include:
            if not extensions or not matches_file_patterns(file_patterns, extensions):
                continue

        rule_sources.append(rule_file.stem)

        # Check each rule
        for rule in rule_data.get('rules', []):
            rules_checked += 1
            match = check_trigger_patterns(rule, plan_content, code_blocks)
            if match:
                # Only flag important/critical issues
                severity = rule.get('severity', 'minor')
                if severity in ['critical', 'important']:
                    issues.append(match)

    # Output results
    if issues:
        output = format_output(issues, scope_desc, rules_checked, rule_sources)
        print(output)
        sys.exit(1)  # Block ExitPlanMode

    sys.exit(0)  # Allow ExitPlanMode


if __name__ == '__main__':
    main()
