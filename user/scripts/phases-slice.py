#!/usr/bin/env python3
"""phases-slice.py — deterministic scoped reader for PHASES.md (+ IMPLEMENTATION_NOTES.md).

Why this exists: /execute-plan orchestrators are contractually required to read only the
current-phase SLICE of PHASES.md (plus a compact index), but the prose mandate (grep for
phase headings, then ranged Read) was measurably ignored in the field — sessions kept
reading 40-100KB PHASES.md files whole at every batch boundary and compaction recovery.
This script makes the scoped read a single deterministic command, so the cheap path is
also the easy path.

Output (default): the file's preamble (everything before the first phase heading, capped),
a one-line-per-phase index (heading, line range, **Status:**, checkbox tally), the ACTIVE
phase's full slice (first phase in file order with an unchecked `- [ ]` deliverable), and
— when a sibling IMPLEMENTATION_NOTES.md exists — its per-phase section index.

Phase boundaries reuse the canonical harness marker (lazy_core._PHASE_HEADING_RE):
a level-2-or-3 heading whose text begins `Phase <id>` — never a bespoke delimiter.

Usage:
  python phases-slice.py <PHASES.md | feature-dir> [options]
    --phase <id>      slice a specific phase instead of the active one (repeatable;
                      matches the id token: 3, 3.5, 12, ...)
    --index-only      print preamble + index only (no phase body)
    --checklist       print only the deliverable checkbox lines for the selected phase(s)
    --notes <id|all>  additionally print IMPLEMENTATION_NOTES.md section(s) for phase <id>
                      (repeatable) or the whole notes file ('all')
    --no-preamble     skip the preamble block
    --preamble-limit N   max preamble lines to print (default 60; 0 = all)

Exit codes: 0 ok, 1 usage/file error, 2 requested phase not found.
"""
import argparse
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Canonical phase-heading marker — keep byte-identical to lazy_core._PHASE_HEADING_RE
# (mechanically pinned by test_phases_slice.py::LockstepTests).
_PHASE_HEADING_RE = re.compile(
    r"^#{2,3}\s+Phase\s+(?:[A-Za-z.+]*\d[A-Za-z0-9.+]*|[A-Za-z0-9.+]+\s*[:—-])"
)
# The id token right after "Phase" (for --phase matching): "3", "3.5", "4.6", "12" ...
_PHASE_ID_RE = re.compile(r"^#{2,4}\s+Phase\s+([A-Za-z0-9.+]+)")
_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$")
_CHECKBOX_RE = re.compile(r"^\s*-\s\[( |x|X)\]")
# Notes files use `## Phase N — title` (level 2-4 tolerated).
_NOTES_HEADING_RE = re.compile(r"^#{2,4}\s+Phase\s+([A-Za-z0-9.+]+)")


def _read_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def _phase_id(heading_line):
    m = _PHASE_ID_RE.match(heading_line)
    if not m:
        return None
    return m.group(1).rstrip(":—-")


def parse_phases(lines):
    """Return (preamble_end, [ {id, title, start, end, status, done, total, unchecked} ]).

    start/end are 0-based line indexes; end is exclusive (next heading or EOF).
    """
    heads = [i for i, ln in enumerate(lines) if _PHASE_HEADING_RE.match(ln)]
    phases = []
    for n, i in enumerate(heads):
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        status, done, total = None, 0, 0
        for ln in lines[i:end]:
            if status is None:
                m = _STATUS_RE.match(ln)
                if m:
                    status = m.group(1)
            m = _CHECKBOX_RE.match(ln)
            if m:
                total += 1
                if m.group(1) in "xX":
                    done += 1
        phases.append(
            {
                "id": _phase_id(lines[i]) or "?",
                "title": lines[i].lstrip("# ").strip(),
                "start": i,
                "end": end,
                "status": status or "-",
                "done": done,
                "total": total,
                "unchecked": total - done,
            }
        )
    preamble_end = heads[0] if heads else len(lines)
    return preamble_end, phases


def parse_notes_sections(lines):
    heads = [i for i, ln in enumerate(lines) if _NOTES_HEADING_RE.match(ln)]
    sections = []
    for n, i in enumerate(heads):
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        m = _NOTES_HEADING_RE.match(lines[i])
        sections.append({"id": m.group(1).rstrip(":—-"), "title": lines[i].lstrip("# ").strip(), "start": i, "end": end})
    return sections


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="PHASES.md path, or a feature dir containing one")
    ap.add_argument("--phase", action="append", default=[], help="phase id(s) to slice (default: active phase)")
    ap.add_argument("--index-only", action="store_true")
    ap.add_argument("--checklist", action="store_true", help="print only checkbox lines for selected phase(s)")
    ap.add_argument("--notes", action="append", default=[], help="notes section id(s), or 'all'")
    ap.add_argument("--no-preamble", action="store_true")
    ap.add_argument("--preamble-limit", type=int, default=40, help="max preamble lines (0 = all)")
    ap.add_argument("--preamble-line-chars", type=int, default=300,
                    help="truncate each preamble line to N chars (0 = no truncation); the preamble is a PREVIEW — range-Read the file for full lines")
    args = ap.parse_args()

    path = args.target
    if os.path.isdir(path):
        path = os.path.join(path, "PHASES.md")
    if not os.path.isfile(path):
        print(f"ERROR: no PHASES.md at {path}", file=sys.stderr)
        return 1

    lines = _read_lines(path)
    preamble_end, phases = parse_phases(lines)
    total_lines = len(lines)

    print(f"# phases-slice: {path}  ({total_lines} lines, {len(phases)} phases)")

    if not args.no_preamble and preamble_end > 0:
        cap = args.preamble_limit if args.preamble_limit > 0 else preamble_end
        shown = min(preamble_end, cap)
        clipped = 0
        out = []
        for ln in lines[:shown]:
            if args.preamble_line_chars and len(ln) > args.preamble_line_chars:
                ln = ln[: args.preamble_line_chars] + " …[truncated]"
                clipped += 1
            out.append(ln)
        print(f"\n--- preamble PREVIEW (lines 1-{shown} of {preamble_end}"
              + (f"; {clipped} long lines truncated — range-Read lines 1-{preamble_end} for full content" if clipped else "")
              + ") ---")
        print("\n".join(out))
        if shown < preamble_end:
            print(f"... ({preamble_end - shown} more preamble lines — Read lines {shown + 1}-{preamble_end} if needed)")

    print("\n--- phase index ---")
    for p in phases:
        tally = f"{p['done']}/{p['total']}" if p["total"] else "-"
        print(f"L{p['start'] + 1:>5}-{p['end']:>5}  [{tally:>7}]  status={p['status'][:60]:<12}  {p['title']}")

    selected = []
    if args.phase:
        wanted = set(args.phase)
        selected = [p for p in phases if p["id"] in wanted]
        missing = wanted - {p["id"] for p in selected}
        if missing:
            print(f"\nERROR: phase id(s) not found: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
    elif not args.index_only:
        active = next((p for p in phases if p["unchecked"] > 0), None)
        if active:
            selected = [active]
        else:
            print("\n(no active phase — every deliverable checkbox is ticked)")

    for p in selected:
        if args.index_only:
            break
        label = "checklist" if args.checklist else "slice"
        print(f"\n--- {label}: {p['title']} (lines {p['start'] + 1}-{p['end']}) ---")
        body = lines[p["start"]: p["end"]]
        if args.checklist:
            body = [ln for ln in body if _CHECKBOX_RE.match(ln)]
        print("\n".join(body))

    notes_path = os.path.join(os.path.dirname(os.path.abspath(path)), "IMPLEMENTATION_NOTES.md")
    if os.path.isfile(notes_path):
        nlines = _read_lines(notes_path)
        sections = parse_notes_sections(nlines)
        print(f"\n--- IMPLEMENTATION_NOTES.md index ({len(nlines)} lines, {len(sections)} sections) ---")
        for s in sections:
            print(f"L{s['start'] + 1:>5}-{s['end']:>5}  {s['title']}")
        if args.notes:
            if "all" in args.notes:
                print("\n--- IMPLEMENTATION_NOTES.md (full) ---")
                print("\n".join(nlines))
            else:
                wanted = set(args.notes)
                hit = [s for s in sections if s["id"] in wanted]
                for s in hit:
                    print(f"\n--- notes: {s['title']} (lines {s['start'] + 1}-{s['end']}) ---")
                    print("\n".join(nlines[s["start"]: s["end"]]))
                missing = wanted - {s["id"] for s in hit}
                if missing:
                    print(f"\nWARNING: notes section(s) not found: {', '.join(sorted(missing))}", file=sys.stderr)
    elif args.notes:
        print(f"\nWARNING: --notes given but no IMPLEMENTATION_NOTES.md beside {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
