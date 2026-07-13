#!/usr/bin/env python3
"""doc-drift-lint.py — cross-check CLAUDE.md structured claims against reality.

Feature: doc-drift-linter (docs/features/doc-drift-linter/SPEC.md).

Four checks (SPEC D1), all pure-read, stdlib-only, deterministic:

  hooks          root CLAUDE.md `## Hooks` table  <->  user/settings.json hook registrations.
                 Bidirectional. Rows claiming a trigger must be registered under exactly that
                 event + matcher set; a hook wired under MULTIPLE events lists each as a
                 "; "-separated `Event (Matcher)` clause (the shape _fmt_events emits) and must
                 match the full registered event->matcher map; rows claiming "NOT registered"
                 must appear in no registered command; a registered hook script with no table
                 row is drift; a documented hook script must exist on disk (user/hooks/ or
                 user/scripts/).
  scripts        root CLAUDE.md `## Scripts` table + user/scripts/CLAUDE.md
                 `## Files in this directory` table  ->  user/scripts/ on disk.
                 Doc->disk existence only (both tables are curated, not exhaustive);
                 a trailing-slash entry is a directory check.
  coupled-pairs  root CLAUDE.md `### Coupled Skill Pairs` table  <->
                 user/scripts/lazy-parity-manifest.json pairs[] (unordered path pairs).
  manifest       manifest.psd1 Repos entries  <->  repos/<name>/ dirs. Non-Alias entries need
                 a repos/<name>/ dir; Alias entries need an existing target key (and no dir);
                 every repos/<name>/ dir needs an entry.

Deliberate divergences (SPEC D2) are annotated in place with DIVERGENCE_MARKER — in markdown
via an HTML comment on the claim row (or, for missing-row findings, a comment in the claim's
section naming the subject); in manifest.psd1 via a `#` comment naming the subject. Exempted
findings are reported but never affect the exit code.

Exit contract (SPEC D4): 0 clean, 1 >=1 drift finding, 2 malformed input.

Known v1 limitations (documented, deliberate):
  - Prose claims are out of scope — structured tables only (SPEC D1).
  - Hook registrations are recognized only when the command references a
    `hooks/<name>.sh|.ps1` path; inline `bash -c` commands with no hooks path are invisible.
  - The .psd1 reader is a minimal tolerant parser for THIS manifest's shape (single-quoted
    strings, `@()` arrays, `@{}` hashtables one level under `Repos`, `#` comments) — NOT a
    general PowerShell parser. Out-of-shape input (unbalanced braces, missing `Repos` block)
    is a malformed finding + exit 2, never a silent guess (SPEC D5).
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

# Insert this directory onto sys.path so `import cli_surface` resolves whether
# this script is run directly or loaded as a module in tests (mirrors the
# bug-state.py / lazy-state.py sibling-import guard).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli_surface

# SSOT divergence marker (the `<!-- verification-only -->` constant precedent).
DIVERGENCE_MARKER = "doc-drift:deliberate-divergence"

CHECK_NAMES = ("hooks", "scripts", "coupled-pairs", "manifest", "intervention-coverage")

_HOOK_PATH_RE = re.compile(r"[/\\]hooks[/\\]([A-Za-z0-9._-]+\.(?:sh|ps1))")
_NOT_REGISTERED_RE = re.compile(r"not\s+registered", re.IGNORECASE)
_TRIGGER_RE = re.compile(r"([A-Za-z][A-Za-z0-9]*)\s*\(([^)]*)\)")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")


class Row:
    """One markdown table row: parsed cells + the raw line (for marker detection)."""

    __slots__ = ("cells", "raw")

    def __init__(self, cells, raw):
        self.cells = cells
        self.raw = raw


class Finding:
    """kind: 'drift' | 'malformed'; exempted findings never affect the exit code."""

    __slots__ = ("check", "kind", "doc", "subject", "message", "exempted")

    def __init__(self, check, kind, doc, subject, message, exempted=False):
        self.check = check
        self.kind = kind
        self.doc = doc
        self.subject = subject
        self.message = message
        self.exempted = exempted

    def line(self):
        return "%s: %s — %s [%s]" % (self.check, self.subject, self.message, self.doc)

    def sort_key(self):
        return (self.check, self.subject, self.message)


# ---------------------------------------------------------------------------
# Markdown table extraction
# ---------------------------------------------------------------------------


def parse_markdown_tables(text):
    """Return a list of tables; each table is a list of Row (separator rows dropped)."""
    tables = []
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(_SEPARATOR_CELL_RE.match(c) for c in cells if c) and any(cells):
                continue  # header separator
            if current is None:
                current = []
                tables.append(current)
            current.append(Row(cells, line))
        else:
            current = None
    return tables


def section_text(text, heading):
    """Text of the section whose heading line is `#'s + heading` (any level), up to the
    next heading of the same-or-higher level. None when the heading is absent."""
    lines = text.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if m and m.group(2) == heading:
            start, level = i, len(m.group(1))
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        m = re.match(r"^(#{1,6})\s+", lines[j])
        if m and len(m.group(1)) <= level:
            return "\n".join(lines[start:j])
    return "\n".join(lines[start:])


def find_section_table(text, heading):
    """First markdown table inside the named section; None when heading/table absent.
    `heading` may include leading #'s (ignored — matched by title text)."""
    title = heading.lstrip("#").strip()
    sect = section_text(text, title)
    if sect is None:
        return None
    tables = parse_markdown_tables(sect)
    if not tables:
        return None
    return tables[0]


def backtick_tokens(cell):
    return _BACKTICK_RE.findall(cell)


def _marker_exempts_subject(sect, subject):
    """A comment line in the section carrying the marker AND the subject exempts a
    missing-row finding for that subject."""
    if not sect:
        return False
    for line in sect.splitlines():
        if DIVERGENCE_MARKER in line and subject in line:
            return True
    return False


def _read_text(path):
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# hooks check
# ---------------------------------------------------------------------------


def _registered_hooks(hooks_obj):
    """{basename: {event: set(matchers)}} from a settings.json `hooks` object.
    Matcher strings are |-split to sets; a group without a matcher contributes an
    empty set (meaning: matches all — compared loosely)."""
    reg = {}
    for event, groups in hooks_obj.items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            matchers = set()
            raw_matcher = group.get("matcher")
            if isinstance(raw_matcher, str) and raw_matcher:
                matchers = {m.strip() for m in raw_matcher.split("|") if m.strip()}
            for h in group.get("hooks", []) or []:
                cmd = h.get("command", "") if isinstance(h, dict) else ""
                for m in _HOOK_PATH_RE.finditer(cmd):
                    name = m.group(1)
                    reg.setdefault(name, {}).setdefault(event, set()).update(matchers)
    return reg


def _parse_matcher_list(text):
    return {t.strip() for t in re.split(r"[,|]", text) if t.strip()}


def _fmt_events(events):
    return "; ".join(
        "%s (%s)" % (ev, ", ".join(sorted(ms)) if ms else "*")
        for ev, ms in sorted(events.items())
    )


def check_hooks(repo_root):
    findings = []
    claude_path = repo_root / "CLAUDE.md"
    settings_path = repo_root / "user" / "settings.json"
    try:
        text = _read_text(claude_path)
    except OSError:
        return [Finding("hooks", "malformed", "CLAUDE.md", "CLAUDE.md",
                        "root CLAUDE.md missing/unreadable")]
    table = find_section_table(text, "## Hooks")
    if table is None or len(table) < 2:
        return [Finding("hooks", "malformed", "CLAUDE.md", "## Hooks",
                        "no `## Hooks` section table found in root CLAUDE.md")]
    try:
        settings = json.loads(_read_text(settings_path))
    except OSError:
        return [Finding("hooks", "malformed", "user/settings.json", "settings.json",
                        "user/settings.json missing/unreadable")]
    except ValueError as exc:
        return [Finding("hooks", "malformed", "user/settings.json", "settings.json",
                        "user/settings.json is not valid JSON (%s)" % exc)]
    registered = _registered_hooks(settings.get("hooks", {}) or {})
    sect = section_text(text, "Hooks")

    documented = set()
    for row in table[1:]:
        names = backtick_tokens(row.cells[0]) if row.cells else []
        if not names:
            continue
        name = names[0]
        documented.add(name)
        exempt = DIVERGENCE_MARKER in row.raw
        trigger = row.cells[1] if len(row.cells) > 1 else ""

        on_disk = (repo_root / "user" / "hooks" / name).is_file() or (
            repo_root / "user" / "scripts" / name
        ).is_file()
        if not on_disk:
            findings.append(Finding(
                "hooks", "drift", "CLAUDE.md", name,
                "documented in the Hooks table but not on disk "
                "(user/hooks/ or user/scripts/)", exempted=exempt))

        if _NOT_REGISTERED_RE.search(trigger):
            if name in registered:
                findings.append(Finding(
                    "hooks", "drift", "CLAUDE.md", name,
                    "documented as NOT registered but registered under %s "
                    "in user/settings.json" % _fmt_events(registered[name]),
                    exempted=exempt))
            continue

        clauses = _TRIGGER_RE.findall(trigger)
        if not clauses:
            findings.append(Finding(
                "hooks", "drift", "CLAUDE.md", name,
                "unparseable Trigger cell %r (expected `Event (Matcher, ...)` "
                "or `NOT registered`)" % trigger, exempted=exempt))
            continue

        # Multi-event form: a Trigger cell may list several `Event (Matcher)` clauses
        # separated by "; " (the shape _fmt_events already emits on the registered side)
        # for a hook wired under more than one event. Parse the full documented
        # event->matcher map and compare it against registered[name]. A single-clause
        # cell falls through to the byte-identical single-event path below.
        if len(clauses) > 1:
            doc_events = {ev: _parse_matcher_list(ms) for ev, ms in clauses}
            if name not in registered:
                findings.append(Finding(
                    "hooks", "drift", "CLAUDE.md", name,
                    "documented as '%s' but registered nowhere in user/settings.json"
                    % _fmt_events(doc_events), exempted=exempt))
                continue
            reg_events = registered[name]
            if set(reg_events) != set(doc_events):
                findings.append(Finding(
                    "hooks", "drift", "CLAUDE.md", name,
                    "documented under events %s but registered under %s"
                    % (_fmt_events(doc_events), _fmt_events(reg_events)),
                    exempted=exempt))
                continue
            for ev, doc_ms in sorted(doc_events.items()):
                reg_ms = reg_events[ev]
                # An empty registered matcher set means "matches all" — no matcher
                # comparison (same `*`-semantics as the single-event path).
                if reg_ms and reg_ms != doc_ms:
                    findings.append(Finding(
                        "hooks", "drift", "CLAUDE.md", name,
                        "documented matchers (%s) != registered matchers (%s) for event %s"
                        % (", ".join(sorted(doc_ms)), ", ".join(sorted(reg_ms)), ev),
                        exempted=exempt))
            continue

        m = _TRIGGER_RE.search(trigger)
        doc_event, doc_matchers = m.group(1), _parse_matcher_list(m.group(2))
        if name not in registered:
            findings.append(Finding(
                "hooks", "drift", "CLAUDE.md", name,
                "documented as '%s (%s)' but registered nowhere in user/settings.json"
                % (doc_event, ", ".join(sorted(doc_matchers))), exempted=exempt))
            continue
        reg_events = registered[name]
        if set(reg_events) != {doc_event}:
            findings.append(Finding(
                "hooks", "drift", "CLAUDE.md", name,
                "documented under event %s but registered under %s"
                % (doc_event, _fmt_events(reg_events)), exempted=exempt))
            continue
        reg_matchers = reg_events[doc_event]
        if reg_matchers and reg_matchers != doc_matchers:
            findings.append(Finding(
                "hooks", "drift", "CLAUDE.md", name,
                "documented matchers (%s) != registered matchers (%s)"
                % (", ".join(sorted(doc_matchers)), ", ".join(sorted(reg_matchers))),
                exempted=exempt))

    for name in sorted(set(registered) - documented):
        findings.append(Finding(
            "hooks", "drift", "CLAUDE.md", name,
            "registered under %s in user/settings.json but has no Hooks-table row"
            % _fmt_events(registered[name]),
            exempted=_marker_exempts_subject(sect, name)))
    return findings


# ---------------------------------------------------------------------------
# scripts check
# ---------------------------------------------------------------------------


def _check_script_table(repo_root, doc_rel, table, findings):
    for row in table[1:]:
        names = backtick_tokens(row.cells[0]) if row.cells else []
        if not names:
            continue
        name = names[0]
        exempt = DIVERGENCE_MARKER in row.raw
        target = repo_root / "user" / "scripts" / name.rstrip("/")
        ok = target.is_dir() if name.endswith("/") else target.is_file()
        if not ok:
            findings.append(Finding(
                "scripts", "drift", doc_rel, name,
                "documented in the scripts table but user/scripts/%s does not exist"
                % name, exempted=exempt))


def check_scripts(repo_root):
    findings = []
    specs = [
        ("CLAUDE.md", repo_root / "CLAUDE.md", "## Scripts"),
        ("user/scripts/CLAUDE.md", repo_root / "user" / "scripts" / "CLAUDE.md",
         "## Files in this directory"),
    ]
    for doc_rel, path, heading in specs:
        try:
            text = _read_text(path)
        except OSError:
            findings.append(Finding("scripts", "malformed", doc_rel, doc_rel,
                                    "%s missing/unreadable" % doc_rel))
            continue
        table = find_section_table(text, heading)
        if table is None or len(table) < 2:
            findings.append(Finding("scripts", "malformed", doc_rel, heading,
                                    "no `%s` section table found" % heading))
            continue
        _check_script_table(repo_root, doc_rel, table, findings)
    return findings


# ---------------------------------------------------------------------------
# coupled-pairs check
# ---------------------------------------------------------------------------


def check_coupled_pairs(repo_root):
    findings = []
    claude_path = repo_root / "CLAUDE.md"
    manifest_path = repo_root / "user" / "scripts" / "lazy-parity-manifest.json"
    try:
        text = _read_text(claude_path)
    except OSError:
        return [Finding("coupled-pairs", "malformed", "CLAUDE.md", "CLAUDE.md",
                        "root CLAUDE.md missing/unreadable")]
    table = find_section_table(text, "Coupled Skill Pairs")
    if table is None or len(table) < 2:
        return [Finding("coupled-pairs", "malformed", "CLAUDE.md", "Coupled Skill Pairs",
                        "no `Coupled Skill Pairs` section table found in root CLAUDE.md")]
    try:
        manifest = json.loads(_read_text(manifest_path))
    except OSError:
        return [Finding("coupled-pairs", "malformed",
                        "user/scripts/lazy-parity-manifest.json", "lazy-parity-manifest.json",
                        "lazy-parity-manifest.json missing/unreadable")]
    except ValueError as exc:
        return [Finding("coupled-pairs", "malformed",
                        "user/scripts/lazy-parity-manifest.json", "lazy-parity-manifest.json",
                        "lazy-parity-manifest.json is not valid JSON (%s)" % exc)]

    manifest_pairs = {}
    for entry in manifest.get("pairs", []) or []:
        can, der = entry.get("canonical"), entry.get("derived")
        if can and der:
            manifest_pairs[frozenset((can, der))] = (can, der)

    doc_pairs = {}
    for row in table[1:]:
        paths = [t for t in backtick_tokens(row.cells[1] if len(row.cells) > 1 else "")
                 if "/" in t]
        if len(paths) >= 2:
            doc_pairs[frozenset(paths[:2])] = (paths[0], paths[1], row)

    sect = section_text(text, "Coupled Skill Pairs")

    for key in sorted(manifest_pairs.keys() - doc_pairs.keys(),
                      key=lambda k: manifest_pairs[k]):
        can, der = manifest_pairs[key]
        exempt = _marker_exempts_subject(sect, can) or _marker_exempts_subject(sect, der)
        findings.append(Finding(
            "coupled-pairs", "drift", "CLAUDE.md", "%s <-> %s" % (can, der),
            "pair is in lazy-parity-manifest.json but missing from the "
            "Coupled Skill Pairs table", exempted=exempt))
    for key in sorted(doc_pairs.keys() - manifest_pairs.keys(),
                      key=lambda k: doc_pairs[k][:2]):
        a, b, row = doc_pairs[key]
        findings.append(Finding(
            "coupled-pairs", "drift", "CLAUDE.md", "%s <-> %s" % (a, b),
            "pair is in the Coupled Skill Pairs table but missing from "
            "lazy-parity-manifest.json", exempted=DIVERGENCE_MARKER in row.raw))
    return findings


# ---------------------------------------------------------------------------
# manifest check (minimal shape-bound .psd1 reader — see module docstring)
# ---------------------------------------------------------------------------

_PSD1_ENTRY_RE = re.compile(r"^\s*'([^']+)'\s*=\s*@\{")
_PSD1_ALIAS_RE = re.compile(r"^\s*Alias\s*=\s*'([^']+)'")


def parse_psd1_manifest(text):
    """Extract (repos, comment_lines) from THIS manifest's shape.

    repos: {name: {"alias": str|None}}. Raises ValueError on out-of-shape input
    (missing `Repos` block, unbalanced braces/parens)."""
    comments = [ln for ln in text.splitlines() if ln.strip().startswith("#")]
    repos = {}
    depth = 0            # combined @{ / @( nesting depth
    repos_inner = None   # depth INSIDE the Repos block (entry keys live here)
    current_entry = None
    saw_repos = False
    for raw in text.splitlines():
        if raw.strip().startswith("#"):
            continue  # full-line comment (collected above)
        line = raw
        # Matching against the PRE-line depth (an entry's own `@{` opens on its line).
        if repos_inner is not None and depth == repos_inner:
            m = _PSD1_ENTRY_RE.match(line)
            if m:
                current_entry = m.group(1)
                repos[current_entry] = {"alias": None}
        elif current_entry is not None and repos_inner is not None and depth == repos_inner + 1:
            m = _PSD1_ALIAS_RE.match(line)
            if m:
                repos[current_entry]["alias"] = m.group(1)
        if repos_inner is None and re.match(r"^\s*Repos\s*=\s*@\{", line):
            saw_repos = True
            repos_inner = depth + 1
        # Depth bookkeeping: '@{'/'@(' open; bare '}'/')' (outside quotes) close.
        unquoted = re.sub(r"'[^']*'", "''", line)
        depth += unquoted.count("@{") + unquoted.count("@(")
        depth -= sum(1 for ch in unquoted if ch in "})")
        if depth < 0:
            raise ValueError("unbalanced braces (extra close)")
        if repos_inner is not None and depth < repos_inner:
            repos_inner = None
        if current_entry is not None and (repos_inner is None or depth <= repos_inner):
            current_entry = None
    if depth != 0:
        raise ValueError("unbalanced braces at EOF (depth %d)" % depth)
    if not saw_repos:
        raise ValueError("no `Repos = @{ ... }` block found")
    return repos, comments


def check_manifest(repo_root):
    findings = []
    psd1_path = repo_root / "manifest.psd1"
    try:
        text = _read_text(psd1_path)
    except OSError:
        return [Finding("manifest", "malformed", "manifest.psd1", "manifest.psd1",
                        "manifest.psd1 missing/unreadable")]
    try:
        repos, comments = parse_psd1_manifest(text)
    except ValueError as exc:
        return [Finding("manifest", "malformed", "manifest.psd1", "manifest.psd1",
                        "unparseable by the minimal .psd1 reader: %s "
                        "(see doc-drift-lint.py header for the supported shape)" % exc)]

    def comment_exempts(subject):
        return any(DIVERGENCE_MARKER in c and subject in c for c in comments)

    repos_dir = repo_root / "repos"
    for name in sorted(repos):
        alias = repos[name]["alias"]
        if alias is not None:
            if alias not in repos:
                findings.append(Finding(
                    "manifest", "drift", "manifest.psd1", name,
                    "Alias target '%s' is not a Repos entry" % alias,
                    exempted=comment_exempts(name)))
            continue
        if not (repos_dir / name).is_dir():
            findings.append(Finding(
                "manifest", "drift", "manifest.psd1", name,
                "Repos entry has no repos/%s/ dir" % name,
                exempted=comment_exempts(name)))

    non_alias = {n for n, info in repos.items() if info["alias"] is None}
    if repos_dir.is_dir():
        for child in sorted(repos_dir.iterdir()):
            if not child.is_dir() or child.name.startswith(("_", ".")):
                continue
            if child.name not in non_alias:
                findings.append(Finding(
                    "manifest", "drift", "manifest.psd1", child.name,
                    "repos/%s/ exists but manifest.psd1 has no Repos entry for it"
                    % child.name, exempted=comment_exempts(child.name)))
    return findings


# ---------------------------------------------------------------------------
# --live mode (WU-5): tracked user/settings.json vs the live ~/.claude/settings.json.
#
# NOT part of the default `run_checks()` walk — this inspects the machine-local live
# settings path, which is host-specific and not something the hermetic default checks
# (hooks/scripts/coupled-pairs/manifest) should ever touch. Opt-in via `--live` only.
# ---------------------------------------------------------------------------


def _live_settings_path(repo_root):
    """Default live settings path. `repo_root` is accepted for symmetry with the
    other checks' signatures but unused — the live path is always under the real
    home directory, independent of which repo is being linted."""
    return Path.home() / ".claude" / "settings.json"


def check_live_settings(repo_root, live_path=None):
    """Pure-read comparison of the tracked SSOT (repo_root/user/settings.json)
    against the live settings path. Returns a list of Finding (check='live')."""
    if live_path is None:
        live_path = _live_settings_path(repo_root)
    live_path = Path(live_path)
    tracked = repo_root / "user" / "settings.json"

    try:
        tracked_bytes = tracked.read_bytes()
    except OSError:
        return [Finding("live", "malformed", "user/settings.json", "live-settings",
                        "tracked user/settings.json is missing/unreadable at %s"
                        % tracked)]

    # Missing entirely — not present, and not even a broken symlink.
    if not live_path.exists() and not live_path.is_symlink():
        return [Finding(
            "live", "drift", str(live_path), "live-settings",
            "live settings file %s does not exist; run `python3 setup.py repair` "
            "(or `.\\setup.ps1 repair`) to (re)create the symlink" % live_path)]

    if live_path.is_symlink():
        try:
            live_real = os.path.realpath(str(live_path))
            tracked_real = os.path.realpath(str(tracked))
        except OSError:
            return [Finding(
                "live", "drift", str(live_path), "live-settings",
                "live settings symlink %s could not be resolved; run "
                "`python3 setup.py repair` (or `.\\setup.ps1 repair`)" % live_path)]
        if live_real == tracked_real:
            return []
        return [Finding(
            "live", "drift", str(live_path), "live-settings",
            "live settings symlink %s resolves to '%s', not the tracked SSOT '%s'; "
            "run `python3 setup.py repair` (or `.\\setup.ps1 repair`)"
            % (live_path, live_real, tracked_real))]

    # A real (non-symlink) file — the legitimate copy-based / cloud-host case.
    try:
        live_bytes = live_path.read_bytes()
    except OSError:
        return [Finding(
            "live", "drift", str(live_path), "live-settings",
            "live settings file %s could not be read; run `python3 setup.py repair` "
            "(or `.\\setup.ps1 repair`)" % live_path)]

    if live_bytes == tracked_bytes:
        return []
    return [Finding(
        "live", "drift", str(live_path), "live-settings",
        "live settings file %s is a real file diverging from the tracked SSOT "
        "user/settings.json; run `python3 setup.py repair` (or `.\\setup.ps1 repair`) "
        "to resync it" % live_path)]


def live_settings_status(repo_root, live_path=None):
    """Thin wrapper over check_live_settings: (ok, detail) summary."""
    findings = check_live_settings(repo_root, live_path=live_path)
    ok = not any(f.kind in ("drift", "malformed") for f in findings)
    if ok:
        return True, "live settings reflect the tracked SSOT"
    return False, findings[0].message


# ---------------------------------------------------------------------------
# intervention coverage (hardening-log rounds <-> docs/interventions/ records)
# ---------------------------------------------------------------------------

_ROUND_HEADING_RE = re.compile(r"^##\s+Round\s+(\d+)\s+—.*$", re.MULTILINE)


def check_intervention_coverage(repo_root):
    """Cross-check the CURRENT month's `/harden-harness` hardening-log rounds against
    docs/interventions/ hypothesis records.

    A round whose body contains the literal `Mechanical fix applied:` is a coverage
    subject. It is COVERED iff any of: (a) a matching
    docs/interventions/harden-<ym>-r<N>.md record exists; (b) the round body contains
    the literal `**Intervention record:** none` (a no-harness-change round's explicit
    exemption); (c) the round body carries DIVERGENCE_MARKER (a known, tracked hole).
    A round with none of the three is a genuine coverage hole.

    Absent the current month's hardening-log file, there is nothing to check (returns
    []) — this check never fails on a repo/month with no hardening activity."""
    ym = datetime.date.today().strftime("%Y-%m")
    log_path = (repo_root / "docs" / "specs" / "turn-routing-enforcement" /
                "hardening-log" / ("%s.md" % ym))
    try:
        text = _read_text(log_path)
    except OSError:
        return []

    findings = []
    matches = list(_ROUND_HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        round_num = int(m.group(1))
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end]

        if "Mechanical fix applied:" not in body:
            continue  # not a coverage subject — nothing was mechanically shipped

        record_name = "harden-%s-r%d.md" % (ym, round_num)
        record_path = repo_root / "docs" / "interventions" / record_name
        covered = (
            record_path.is_file()
            or "**Intervention record:** none" in body
            or DIVERGENCE_MARKER in body
        )
        if not covered:
            findings.append(Finding(
                "intervention-coverage", "drift",
                "docs/specs/turn-routing-enforcement/hardening-log/%s.md" % ym,
                "Round %d" % round_num,
                "Mechanical fix applied but no intervention record found "
                "(expected docs/interventions/%s, a `**Intervention record:** none` "
                "exemption, or a %s marker)" % (record_name, DIVERGENCE_MARKER)))
    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_checks(repo_root):
    findings = []
    for fn in (check_hooks, check_scripts, check_coupled_pairs, check_manifest,
               check_intervention_coverage):
        findings.extend(fn(repo_root))
    findings.sort(key=Finding.sort_key)
    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cross-check CLAUDE.md structured claims against reality "
                    "(hooks/scripts/coupled-pairs/manifest). Pure-read.")
    parser.add_argument("--repo-root", default=".",
                        help="claude-config repo root (default: cwd)")
    parser.add_argument("--live", action="store_true",
                        help="also run the machine-local live-settings check "
                             "(tracked user/settings.json vs the live "
                             "~/.claude/settings.json). Opt-in; not part of the "
                             "default checks.")
    parser.add_argument("--live-path", default=None,
                        help="override the live settings path checked by --live "
                             "(default: ~/.claude/settings.json)")
    cli_surface.add_dump_cli_surface_flag(parser)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    _dump = cli_surface.maybe_handle_dump_cli_surface(args, parser, "doc-drift-lint.py")
    if _dump is not None:
        return _dump

    repo_root = Path(args.repo_root).resolve()

    findings = run_checks(repo_root)
    if args.live:
        live_path = Path(args.live_path) if args.live_path else None
        findings = findings + check_live_settings(repo_root, live_path=live_path)
    malformed = [f for f in findings if f.kind == "malformed"]
    drift = [f for f in findings if f.kind == "drift" and not f.exempted]
    exempted = [f for f in findings if f.kind == "drift" and f.exempted]

    for f in malformed + drift:
        print(f.line())
    for f in exempted:
        print("exempted: " + f.line())
    print("doc-drift-lint: %d checks, %d drift findings, %d exempted divergences%s"
          % (len(CHECK_NAMES), len(drift), len(exempted),
             ", %d MALFORMED input problems" % len(malformed) if malformed else ""))
    if malformed:
        return 2
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
