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
"""

import re
import sys

__all__ = ["SetupError", "parse_psd1", "main"]


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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
