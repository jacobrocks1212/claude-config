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


def main():
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
