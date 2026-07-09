#!/usr/bin/env python3
"""Attribute a session's context footprint up to the first subagent dispatch.

For each transcript, walk turns in order until the first Agent/Task tool_use
(the "first dispatch"). Accumulate the BYTES each source contributed to the
conversation up to that point, bucketed by:

  - command-expansion   user turns carrying <command-name> (slash-command/skill body)
  - user-text           other human/harness user text (incl. continuation summaries)
  - assistant-text      assistant prose + thinking-visible text
  - tool:<name>         tool_result bytes, attributed to the emitting tool
                        (Read results additionally broken out per file path,
                         Bash per first command token)

Reports per-session: ctx tokens at turn 1 (startup baseline: system prompt +
tools + CLAUDE.md chain -- NOT attributable from the transcript), ctx tokens at
the dispatch turn, and the byte attribution of everything in between, plus the
top individual contributors (files / commands / expansions).

Aggregates across sessions at the end (median per-category bytes, top files).

Usage:
  python attribute_predispatch.py <session.jsonl> [...]
  python attribute_predispatch.py --from-digest digest.json --min-agents 1 --top-sessions 20
  Options: --until-tool Agent,Task   --top N (top contributors listed, default 15)
           --out attribution.json
"""
import argparse
import json
import os
import re
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CMD_RE = re.compile(r"<command-name>\s*(/?[\w:-]+)\s*</command-name>")


def _content_text(content):
    """Flatten a message content (str or block list) to text; return (text, blocks)."""
    if isinstance(content, str):
        return content, []
    if isinstance(content, list):
        texts, blocks = [], []
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                texts.append(b.get("text") or "")
            else:
                blocks.append(b)
        return "\n".join(texts), blocks
    return "", []


def _result_bytes(block):
    c = block.get("content")
    if isinstance(c, str):
        return len(c.encode("utf-8", "replace"))
    n = 0
    if isinstance(c, list):
        for sub in c:
            if isinstance(sub, dict) and sub.get("type") == "text":
                n += len((sub.get("text") or "").encode("utf-8", "replace"))
    return n


def _ctx_tokens(msg):
    u = (msg or {}).get("usage") or {}
    return (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (
        u.get("cache_creation_input_tokens") or 0
    )


def analyze(path, until_tools, full=False):
    """Return attribution dict for one session, or None if unreadable/no turns."""
    tool_use = {}        # id -> {name, label}
    cat = {}             # category -> bytes
    contrib = {}         # fine-grained label -> bytes
    first_ctx = None
    last_ctx = None
    dispatch_ctx = None
    dispatch_turn = None
    turn = 0
    started_from_summary = False
    dispatched = False

    def add(category, label, nbytes):
        cat[category] = cat.get(category, 0) + nbytes
        if label:
            contrib[label] = contrib.get(label, 0) + nbytes

    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rtype = rec.get("type")
            if rtype not in ("user", "assistant"):
                continue
            msg = rec.get("message") or {}
            text, blocks = _content_text(msg.get("content"))
            turn += 1

            if rtype == "assistant":
                ctx = _ctx_tokens(msg)
                if first_ctx is None and ctx:
                    first_ctx = ctx
                if ctx:
                    last_ctx = ctx
                # first dispatch?
                for b in blocks:
                    if b.get("type") == "tool_use":
                        name = b.get("name") or "?"
                        tool_use[b.get("id")] = {
                            "name": name,
                            "label": _tool_label(name, b.get("input") or {}),
                        }
                        if name in until_tools and not dispatched:
                            dispatched = True
                            dispatch_ctx = ctx or dispatch_ctx
                            dispatch_turn = turn
                if dispatched and not full:
                    if dispatch_ctx is None:
                        dispatch_ctx = ctx
                    break
                if text:
                    add("assistant-text", None, len(text.encode("utf-8", "replace")))
            else:  # user
                if text:
                    n = len(text.encode("utf-8", "replace"))
                    m = CMD_RE.search(text)
                    if m:
                        add("command-expansion", f"cmd:{m.group(1)}", n)
                    else:
                        if turn <= 2 and text.startswith("This session is being continued"):
                            started_from_summary = True
                        add("user-text", None, n)
                for b in blocks:
                    if b.get("type") == "tool_result":
                        tu = tool_use.get(b.get("tool_use_id")) or {}
                        name = tu.get("name", "?")
                        add(f"tool:{name}", tu.get("label"), _result_bytes(b))

    if turn == 0:
        return None
    if full:
        # full-transcript mode: the "dispatch" point is end-of-run
        dispatch_ctx = last_ctx
        dispatch_turn = turn
        dispatched = True
    return {
        "session": os.path.basename(path),
        "path": path,
        "dispatched": dispatched,
        "dispatch_turn": dispatch_turn,
        "first_ctx_tokens": first_ctx,
        "dispatch_ctx_tokens": dispatch_ctx,
        "started_from_summary": started_from_summary,
        "categories": dict(sorted(cat.items(), key=lambda kv: -kv[1])),
        "contributors": dict(sorted(contrib.items(), key=lambda kv: -kv[1])),
    }


def _tool_label(name, inp):
    if name == "Read":
        return f"read:{inp.get('file_path', '?')}"
    if name in ("Edit", "Write"):
        return f"{name.lower()}:{inp.get('file_path', '?')}"
    if name == "Bash":
        cmd = (inp.get("command") or "").strip().split("\n", 1)[0]
        return f"bash:{cmd[:80]}"
    if name in ("Grep", "Glob"):
        return f"{name.lower()}:{inp.get('pattern', '?')}"
    if name == "Skill":
        return f"skill:{inp.get('skill', '?')}"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sessions", nargs="*", help="transcript .jsonl paths")
    ap.add_argument("--from-digest", help="digest_sessions.py --out JSON; pulls session paths from it")
    ap.add_argument("--min-agents", type=int, default=1, help="with --from-digest: only sessions with >= N agent dispatches")
    ap.add_argument("--top-sessions", type=int, default=0, help="with --from-digest: cap sessions (0 = all)")
    ap.add_argument("--until-tool", default="Agent,Task", help="comma list of dispatch tool names")
    ap.add_argument("--full", action="store_true",
                    help="attribute the ENTIRE transcript (no dispatch cutoff) — e.g. subagent transcripts")
    ap.add_argument("--top", type=int, default=15, help="top contributors per aggregate list")
    ap.add_argument("--out", help="write full JSON here")
    args = ap.parse_args()

    paths = list(args.sessions)
    if args.from_digest:
        with open(args.from_digest, encoding="utf-8") as f:
            dig = json.load(f)
        rows = dig if isinstance(dig, list) else dig.get("sessions", [])
        rows = [
            r
            for r in rows
            if (r.get("agent_dispatches") or r.get("agents") or r.get("agent_count") or 0) >= args.min_agents
        ]
        if args.top_sessions:
            rows = rows[: args.top_sessions]
        for r in rows:
            p = r.get("path") or r.get("file")
            if p:
                paths.append(p)
    if not paths:
        ap.error("no sessions given (positional or --from-digest)")

    until = set(t.strip() for t in args.until_tool.split(",") if t.strip())
    results = []
    for p in paths:
        r = analyze(p, until, full=args.full)
        if r:
            results.append(r)

    dispatched = [r for r in results if r["dispatched"]]
    print(f"analyzed={len(results)}  with-dispatch={len(dispatched)}")
    if not dispatched:
        return

    # per-session table
    print(f"\n{'firstK':>7} {'dispK':>6} {'turn':>5} {'sum?':>4}  top categories (KB)")
    for r in dispatched:
        cats = "  ".join(
            f"{k}={v // 1024}K" for k, v in list(r["categories"].items())[:4]
        )
        print(
            f"{(r['first_ctx_tokens'] or 0) // 1000:>6}K {(r['dispatch_ctx_tokens'] or 0) // 1000:>5}K "
            f"{r['dispatch_turn']:>5} {'Y' if r['started_from_summary'] else '.':>4}  {cats}   [{r['session'][:8]}]"
        )

    # aggregate categories (median + total)
    all_cats = {}
    for r in dispatched:
        for k, v in r["categories"].items():
            all_cats.setdefault(k, []).append(v)
    print("\n=== category attribution across sessions (bytes in pre-dispatch window) ===")
    print(f"{'category':<28}{'sessions':>9}{'median KB':>11}{'total MB':>10}")
    for k, vals in sorted(all_cats.items(), key=lambda kv: -sum(kv[1])):
        print(f"{k:<28}{len(vals):>9}{statistics.median(vals) / 1024:>11.1f}{sum(vals) / 1048576:>10.2f}")

    # aggregate contributors
    all_contrib = {}
    count_contrib = {}
    for r in dispatched:
        for k, v in r["contributors"].items():
            all_contrib[k] = all_contrib.get(k, 0) + v
            count_contrib[k] = count_contrib.get(k, 0) + 1
    print(f"\n=== top {args.top} individual contributors (total bytes across sessions) ===")
    print(f"{'total KB':>9} {'sessions':>9}  contributor")
    for k, v in sorted(all_contrib.items(), key=lambda kv: -kv[1])[: args.top]:
        print(f"{v / 1024:>9.1f} {count_contrib[k]:>9}  {k}")

    med_first = statistics.median([r["first_ctx_tokens"] or 0 for r in dispatched])
    med_disp = statistics.median([r["dispatch_ctx_tokens"] or 0 for r in dispatched])
    print(
        f"\nmedian ctx: turn-1 = {med_first / 1000:.0f}K tokens (startup baseline, not in transcript), "
        f"first-dispatch = {med_disp / 1000:.0f}K tokens, delta = {(med_disp - med_first) / 1000:.0f}K"
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
