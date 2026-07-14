#!/usr/bin/env python3
"""Cross-platform symlink setup for claude-config — Python port of setup.ps1.

Reads the EXISTING manifest.psd1 (single source of truth — SPEC D1) through a
minimal, tolerant psd1 parser scoped to the manifest's actual grammar, and
mirrors setup.ps1's bootstrap/check/repair semantics one-for-one (normative
parity table in docs/features/cross-platform-setup/SPEC.md).

Stdlib-only; imports nothing from user/scripts/ — this script must run on a
bare clone (e.g. a cloud container) before any symlink layout exists.

Usage:
    python3 setup.py check                     # exit 0 iff no broken mapping
    python3 setup.py bootstrap --target User   # materialize ~/.claude/* links
    python3 setup.py repair                    # fix broken/wrong links
    python3 setup.py bootstrap --target Repos --repos-root ~/source/repos

Deliberate divergences from setup.ps1 (all SPEC-locked):
  - check exits 0 iff broken == 0 (setup.ps1 never propagated its bool);
  - a Repos entry whose base Path is absent is skipped whole (D5), never
    materialized into a non-existent worktree;
  - the warn-only advisories (hook registration, Cognito doc drift) and the
    add-repo verb are NOT ported (D6/D2) — setup.ps1 keeps them on Windows.

Machine-keyed entries (docs/specs/machine-keyed-manifest-projection): any
manifest entry may carry an optional Machine = '<hostname>' key. An entry
whose Machine does not match the local hostname (case-insensitive;
platform.node() here, $env:COMPUTERNAME in setup.ps1 — identical on Windows)
is skipped; for the same Live path a Machine-matching entry WINS over a
machine-agnostic one. Semantics are mirrored one-for-one in setup.ps1.
"""

import os
import platform
import re
import sys
from dataclasses import dataclass

__all__ = ["SetupError", "parse_psd1", "expand_mappings", "expand_live_path", "main"]

_WINDOWS = os.name == "nt"


class SetupError(Exception):
    """Loud failure — any manifest/parse/link error. CLI maps it to exit 2."""


def _die(msg, line=None):
    raise SetupError(f"line {line}: {msg}" if line is not None else msg)


# ---------------------------------------------------------------------------
# psd1 parser (SPEC D1) — scoped to manifest.psd1's actual grammar:
# hashtable literals @{..}, arrays @(..), nested hashtables, single-quoted
# strings ('' escape), double-quoted strings (NO interpolation — '$'/'`' die),
# bare-word + quoted keys, '#' comments, newline/','/';' separators.
# Anything else dies loudly with a line number — never silent tolerance.
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*")


def _tokenize(text):
    """Return a list of (kind, value, line) tokens. kinds:
    '@{', '@(', '}', ')', '=', 'sep' (comma/semicolon), 'nl', 'str', 'word', 'eof'.
    """
    tokens = []
    i, n, line = 0, len(text), 1
    while i < n:
        c = text[i]
        if c == "\n":
            tokens.append(("nl", None, line))
            line += 1
            i += 1
        elif c in " \t\r":
            i += 1
        elif c == "#":
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("@{", i):
            tokens.append(("@{", None, line))
            i += 2
        elif text.startswith("@(", i):
            tokens.append(("@(", None, line))
            i += 2
        elif c == "}":
            tokens.append(("}", None, line))
            i += 1
        elif c == ")":
            tokens.append((")", None, line))
            i += 1
        elif c == "=":
            tokens.append(("=", None, line))
            i += 1
        elif c in ",;":
            tokens.append(("sep", None, line))
            i += 1
        elif c == "'":
            start_line = line
            j = i + 1
            buf = []
            while True:
                if j >= n:
                    _die("unterminated single-quoted string", start_line)
                ch = text[j]
                if ch == "'":
                    if j + 1 < n and text[j + 1] == "'":  # '' escape
                        buf.append("'")
                        j += 2
                        continue
                    break
                if ch == "\n":
                    line += 1
                buf.append(ch)
                j += 1
            tokens.append(("str", "".join(buf), start_line))
            i = j + 1
        elif c == '"':
            start_line = line
            j = i + 1
            buf = []
            while True:
                if j >= n:
                    _die("unterminated double-quoted string", start_line)
                ch = text[j]
                if ch == '"':
                    if j + 1 < n and text[j + 1] == '"':  # "" escape
                        buf.append('"')
                        j += 2
                        continue
                    break
                if ch in "$`":
                    _die(
                        "interpolation ({!r}) in double-quoted string is not "
                        "supported in this data file — use single quotes".format(ch),
                        start_line,
                    )
                if ch == "\n":
                    line += 1
                buf.append(ch)
                j += 1
            tokens.append(("str", "".join(buf), start_line))
            i = j + 1
        else:
            m = _WORD_RE.match(text, i)
            if not m:
                _die(f"unsupported psd1 construct starting at {text[i]!r}", line)
            tokens.append(("word", m.group(0), line))
            i = m.end()
    tokens.append(("eof", None, line))
    return tokens


class _Psd1Parser:
    def __init__(self, tokens):
        self._toks = tokens
        self._i = 0

    def _peek(self):
        return self._toks[self._i]

    def _next(self):
        tok = self._toks[self._i]
        self._i += 1
        return tok

    def _skip_separators(self):
        while self._peek()[0] in ("nl", "sep"):
            self._next()

    def parse_document(self):
        self._skip_separators()
        kind, _, line = self._peek()
        if kind != "@{":
            _die("expected a top-level hashtable literal '@{'", line)
        self._next()
        result = self._parse_hashtable_body()
        self._skip_separators()
        kind, _, line = self._peek()
        if kind != "eof":
            _die("unexpected content after the top-level hashtable", line)
        return result

    def _parse_hashtable_body(self):
        """Parse entries until '}'. Opening '@{' already consumed."""
        table = {}
        while True:
            self._skip_separators()
            kind, value, line = self._peek()
            if kind == "}":
                self._next()
                return table
            if kind not in ("word", "str"):
                _die(f"expected a hashtable key, got {kind!r}", line)
            key = self._next()[1]
            kind, _, line = self._peek()
            if kind != "=":
                _die(f"expected '=' after key {key!r}", line)
            self._next()
            table[key] = self._parse_value()

    def _parse_value(self):
        # '=' may be followed by a newline before the value in hand-edited files.
        while self._peek()[0] == "nl":
            self._next()
        kind, value, line = self._peek()
        if kind == "@{":
            self._next()
            return self._parse_hashtable_body()
        if kind == "@(":
            self._next()
            return self._parse_array_body()
        if kind == "str":
            self._next()
            return value
        if kind == "word":
            _die(
                f"unquoted value {value!r} — this manifest only uses quoted "
                "strings, arrays, and hashtables",
                line,
            )
        _die(f"expected a value, got {kind!r}", line)

    def _parse_array_body(self):
        """Parse values until ')'. Opening '@(' already consumed."""
        items = []
        while True:
            self._skip_separators()
            kind, _, line = self._peek()
            if kind == ")":
                self._next()
                return items
            if kind == "eof":
                _die("unterminated array — expected ')'", line)
            items.append(self._parse_value())


def parse_psd1(text):
    """Parse a psd1 document (manifest.psd1's grammar subset) into plain
    dict/list/str values. Dies loudly (SetupError, with a line number) on any
    construct outside that grammar."""
    return _Psd1Parser(_tokenize(text)).parse_document()


# ---------------------------------------------------------------------------
# Mapping expansion — mirrors setup.ps1's Get-AllMappings (SPEC parity table).
# ---------------------------------------------------------------------------


@dataclass
class Mapping:
    live: str          # absolute host path of the live location
    repo: str          # absolute path inside this repo
    type: str          # 'File' | 'Directory'
    section: str       # 'User' | 'Personal' | 'Workspace' | 'Repo:<name>'
    skip_absent: bool = False   # Repos entry whose base Path is absent (D5)
    skip_reason: str = ""

    @property
    def label(self):
        return f"{self.section} | {os.path.basename(self.live)}"


def _norm_seps(path):
    """Normalize manifest '\\'-separated paths to the host separator."""
    return path.replace("\\", os.sep).replace("/", os.sep)


def _platform_home():
    if _WINDOWS:
        return os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.environ.get("HOME") or os.path.expanduser("~")


def expand_live_path(path, home=None):
    """Port of Expand-LivePath: a leading '~' becomes the platform home
    (USERPROFILE on Windows, HOME on POSIX); separators host-normalized."""
    if home is None:
        home = _platform_home()
    path = _norm_seps(path)
    if path == "~" or path.startswith("~" + os.sep):
        path = home + path[1:]
    return path


def _path_basename(manifest_path):
    """Last component of a manifest Path regardless of separator style."""
    return _norm_seps(manifest_path).rstrip(os.sep).rsplit(os.sep, 1)[-1]


_SCOPE_SECTIONS = ("User", "Personal", "Workspace")
TARGETS = ("All", "User", "Personal", "Workspace", "Repos")


def _local_machine():
    """Local hostname for Machine-keyed entry selection. platform.node() is
    the documented source (matches $env:COMPUTERNAME on the Windows boxes
    this manifest serves); comparison is always case-insensitive."""
    return platform.node()


def expand_mappings(manifest, repo_root, target="All", repos_root=None, home=None,
                    machine=None):
    """Flatten the manifest into Mapping records (setup.ps1 Get-AllMappings).

    repos_root: optional override — each Repos entry's Path is remapped to
    <repos_root>/<basename(Path)> so a non-Windows host can link checkouts
    living under a different root (SPEC D2/D5).
    A Repos entry whose base Path dir is absent is flagged skip_absent for
    the whole entry — verbs render it as a skip, never broken (SPEC D5).

    machine: local hostname override (tests); default _local_machine().
    Machine-keyed entries (machine-keyed-manifest-projection): an entry whose
    Machine key mismatches `machine` (case-insensitive) is skipped; within a
    scope section, a Machine-matching entry WINS over a machine-agnostic
    entry for the same Live path. On Repos entries Machine is skip-only
    (whole entry; read from the entry itself, never inherited via Alias).
    """
    if target not in TARGETS:
        _die(f"unknown target {target!r} (expected one of {', '.join(TARGETS)})")
    repo_root = os.path.abspath(repo_root)
    if machine is None:
        machine = _local_machine()
    machine_cf = (machine or "").casefold()
    mappings = []

    for section in _SCOPE_SECTIONS:
        if target not in ("All", section):
            continue
        entries = [e for e in manifest.get(section, [])
                   if "Machine" not in e
                   or str(e["Machine"]).casefold() == machine_cf]
        machine_lives = {_norm_seps(e["Live"]).casefold()
                         for e in entries if "Machine" in e}
        for entry in entries:
            if ("Machine" not in entry
                    and _norm_seps(entry["Live"]).casefold() in machine_lives):
                continue  # a Machine-matching entry wins this Live path
            mappings.append(Mapping(
                live=expand_live_path(entry["Live"], home=home),
                repo=os.path.join(repo_root, _norm_seps(entry["Repo"])),
                type=entry["Type"],
                section=section,
            ))

    if target in ("All", "Repos"):
        repos = manifest.get("Repos", {})
        for name in sorted(repos):
            cfg = repos[name]
            if ("Machine" in cfg
                    and str(cfg["Machine"]).casefold() != machine_cf):
                continue  # entry pinned to another machine (skip-only)
            live_base = _norm_seps(cfg["Path"])
            if repos_root is not None:
                live_base = os.path.join(
                    os.path.abspath(repos_root), _path_basename(cfg["Path"]))
            config_name = cfg.get("Alias") or name
            src_cfg = repos.get(config_name)
            if src_cfg is None:
                _die(f"Repos entry {name!r} aliases unknown repo {config_name!r}")
            skip_absent = not os.path.isdir(live_base)
            skip_reason = f"repo absent: {live_base}" if skip_absent else ""
            section = f"Repo:{name}"

            def _add(live_rel, repo_rel, mtype):
                mappings.append(Mapping(
                    live=os.path.join(live_base, _norm_seps(live_rel)),
                    repo=os.path.join(repo_root, "repos", config_name,
                                      _norm_seps(repo_rel)),
                    type=mtype,
                    section=section,
                    skip_absent=skip_absent,
                    skip_reason=skip_reason,
                ))

            for f in src_cfg.get("RootFiles", []):
                _add(f, f, "File")
            for f in src_cfg.get("DotClaudeFiles", []):
                _add(os.path.join(".claude", _norm_seps(f)),
                     os.path.join(".claude", _norm_seps(f)), "File")
            for d in src_cfg.get("DotClaudeDirs", []):
                _add(os.path.join(".claude", _norm_seps(d)),
                     os.path.join(".claude", _norm_seps(d)), "Directory")

    return mappings


# ---------------------------------------------------------------------------
# Link primitives (SPEC D3) — POSIX: plain symlinks. Windows: symlink-first
# (matching setup.ps1's New-Item SymbolicLink); on a privilege error, fall
# back to a directory junction (no privilege needed) or die actionably for
# files. _symlink/_readlink/_create_junction are patchable seams so the
# Windows-only branch is unit-testable with a mocked platform.
# ---------------------------------------------------------------------------


def _symlink(target, live, is_dir):
    os.symlink(target, live, target_is_directory=is_dir)


def _strip_extended_prefix(path):
    """Strip the Windows extended-length path prefix ('\\\\?\\', or its UNC
    variant '\\\\?\\UNC\\') from a raw os.readlink() result.

    Windows symlinks/junctions created from a plain absolute target are
    still reported back by os.readlink() with this prefix prepended (an NT
    kernel object-namespace artifact, not something the caller asked for).
    Left unstripped, every downstream comparison/print sees a spurious
    mismatch against the prefix-free repo path — a real cross-platform bug,
    not a test quirk (docs/bugs/setup-py-windows-extended-path-prefix-mismatch).
    """
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[len("\\\\?\\UNC\\"):]
    if path.startswith("\\\\?\\"):
        return path[len("\\\\?\\"):]
    return path


def _readlink(path):
    target = os.readlink(path)
    if _WINDOWS:
        target = _strip_extended_prefix(target)
    return target


def _create_junction(target, live):  # pragma: no cover - Windows-only
    import _winapi
    _winapi.CreateJunction(str(target), str(live))


def _is_link(path):
    """True for symlinks everywhere; on Windows also for junctions (any
    readable reparse target) — consistent with setup.ps1's ReparsePoint test."""
    if os.path.islink(path):
        return True
    if _WINDOWS:
        try:
            _readlink(path)
            return True
        except OSError:
            return False
    return False


def _read_link_target(path):
    return _readlink(path)


def _resolve_target(link_path):
    """Resolve a link's stored target against the link's parent dir
    (port of Resolve-Absolute) and normalize for comparison."""
    target = _readlink(link_path)
    if not os.path.isabs(target):
        target = os.path.join(os.path.dirname(link_path), target)
    return os.path.normcase(os.path.normpath(os.path.abspath(target)))


def _targets_equal(link_path, repo_path):
    return _resolve_target(link_path) == os.path.normcase(
        os.path.normpath(os.path.abspath(repo_path)))


def _create_link(live, repo, is_dir):
    """Create the live→repo link. Returns 'symlink' or 'junction'."""
    if not _WINDOWS:
        _symlink(repo, live, is_dir)
        return "symlink"
    try:
        _symlink(repo, live, is_dir)
        return "symlink"
    except OSError as exc:
        if is_dir:
            _create_junction(repo, live)
            return "junction"
        raise SetupError(
            f"cannot create file symlink at {live}: {exc}. "
            "Enable Windows Developer Mode (Settings > For developers) or run "
            "elevated, then re-run.")


# ---------------------------------------------------------------------------
# Verbs — one-for-one port of setup.ps1's Invoke-Bootstrap / Invoke-Check /
# Invoke-Repair (normative parity table in the SPEC). Deliberate divergences:
# skip_absent rendering (D5) and check's real exit code.
# ---------------------------------------------------------------------------


def _remove_link(path):
    try:
        os.unlink(path)
    except OSError:  # Windows directory symlink/junction
        os.rmdir(path)


def _ensure_parent(path):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def cmd_bootstrap(mappings):
    import shutil
    moved = linked = skipped = warned = 0
    for m in mappings:
        label = m.label
        if m.skip_absent:
            print(f"  SKIP     {label} ({m.skip_reason})")
            skipped += 1
            continue
        live, repo = m.live, m.repo
        is_dir = m.type == "Directory"

        # Already correctly linked
        if _is_link(live) and _targets_equal(live, repo):
            print(f"  SKIP     {label}")
            skipped += 1
            continue

        _ensure_parent(repo)

        if _is_link(live):
            # Symlink pointing at the wrong target
            if os.path.exists(repo):
                _remove_link(live)
                _create_link(live, repo, is_dir)
                print(f"  RELINK   {label}")
                linked += 1
            elif os.path.exists(live):  # referent alive -> preserve its content
                if is_dir:
                    shutil.copytree(live, repo)
                else:
                    shutil.copy2(live, repo)
                _remove_link(live)
                _create_link(live, repo, is_dir)
                print(f"  COPYLINK {label}")
                linked += 1
            else:  # dangling link, nothing to recover on either side
                _remove_link(live)
                print(f"  NONE     {label} (dangling link removed)")
                skipped += 1
        elif os.path.lexists(live):
            # Real file/directory
            if os.path.exists(repo):
                print(f"  WARN     {label} (both live and repo exist)")
                warned += 1
                continue
            shutil.move(live, repo)
            _create_link(live, repo, is_dir)
            print(f"  MOVE     {label}")
            moved += 1
        elif os.path.exists(repo):
            _ensure_parent(live)
            _create_link(live, repo, is_dir)
            print(f"  LINK     {label} (recovery)")
            linked += 1
        else:
            print(f"  NONE     {label}")
            skipped += 1

    print(f"\nBootstrap: {moved} moved, {linked} linked, {skipped} skipped, "
          f"{warned} warnings")
    return 0


def cmd_check(mappings):
    ok = broken = absent = 0
    for m in mappings:
        label = m.label
        if m.skip_absent:
            print(f"  SKIP     {label} ({m.skip_reason})")
            absent += 1
            continue
        live, repo = m.live, m.repo
        if not os.path.lexists(live):
            if os.path.exists(repo):
                print(f"  MISSING  {label}")
                broken += 1
            else:
                print(f"  ABSENT   {label}")
                absent += 1
            continue
        if not _is_link(live):
            print(f"  REAL     {label} (not symlinked)")
            broken += 1
            continue
        if _targets_equal(live, repo):
            print(f"  OK       {label}")
            ok += 1
        else:
            print(f"  WRONG    {label} -> {_read_link_target(live)}")
            broken += 1

    print(f"\nCheck: {ok} OK, {broken} broken, {absent} absent")
    # Hardening over setup.ps1 (which never propagated its bool): real exit code.
    return 0 if broken == 0 else 1


def cmd_repair(mappings):
    import shutil
    repaired = skipped = 0
    for m in mappings:
        label = m.label
        if m.skip_absent:
            print(f"  SKIP     {label} ({m.skip_reason})")
            skipped += 1
            continue
        live, repo = m.live, m.repo
        if not os.path.exists(repo):
            skipped += 1
            continue
        if _is_link(live):
            if _targets_equal(live, repo):
                skipped += 1
                continue
            _remove_link(live)
        elif os.path.lexists(live):
            shutil.move(live, live + ".bak")
            print(f"  BACKUP   {label}")
        _ensure_parent(live)
        _create_link(live, repo, m.type == "Directory")
        print(f"  REPAIR   {label}")
        repaired += 1

    print(f"\nRepair: {repaired} fixed, {skipped} OK")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="setup.py",
        description="Cross-platform symlink bootstrap/check/repair for "
                    "claude-config (Python port of setup.ps1; reads the same "
                    "manifest.psd1).")
    parser.add_argument("command", choices=("bootstrap", "check", "repair"))
    parser.add_argument("--target", choices=TARGETS, default="All",
                        help="scope to one manifest section (default: All)")
    parser.add_argument("--repos-root", default=None,
                        help="remap each Repos entry's Path to "
                             "<repos-root>/<basename(Path)> (host-local checkouts)")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits 2 on usage errors already
        return exc.code

    repo_root = os.path.dirname(os.path.abspath(__file__))
    try:
        manifest_path = os.path.join(repo_root, "manifest.psd1")
        if not os.path.isfile(manifest_path):
            _die(f"manifest not found: {manifest_path}")
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = parse_psd1(fh.read())
        repos_root = args.repos_root
        if repos_root is not None:
            repos_root = os.path.abspath(os.path.expanduser(repos_root))
            if not os.path.isdir(repos_root):
                _die(f"--repos-root does not exist: {repos_root}")
        mappings = expand_mappings(manifest, repo_root, target=args.target,
                                   repos_root=repos_root)

        print("\n=== Claude Config Setup ===")
        print(f"Command: {args.command} | Target: {args.target} | Root: {repo_root}\n")
        print(f"Mappings: {len(mappings)}\n")

        dispatch = {"bootstrap": cmd_bootstrap, "check": cmd_check,
                    "repair": cmd_repair}
        return dispatch[args.command](mappings)
    except SetupError as exc:
        print(f"setup.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
