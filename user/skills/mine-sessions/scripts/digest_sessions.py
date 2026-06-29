#!/usr/bin/env python3
"""digest_sessions.py — quantitative signal extractor for Claude Code session transcripts.

Claude Code stores one .jsonl transcript per session under:
    ~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl
where <encoded-cwd> is the absolute cwd with separators/colons replaced by '-'
(e.g. C:\\Users\\me\\source\\repos\\Foo  ->  C--Users-me-source-repos-Foo).
A git worktree has its own cwd, so it gets its own sibling project dir.

This script scans many transcripts WITHOUT loading them into an agent's context,
and emits a compact per-session digest (JSON + a printed table) so an agent can
decide which sessions to deep-read with render_session.py.

Usage:
    python digest_sessions.py [--projects-dir DIR] [--match SUBSTR]
                              [--command NAME] [--grep REGEX]
                              [--out digest.json] [--top N] [--frustration]

  --projects-dir  base dir of project transcript folders (default ~/.claude/projects)
  --match         only scan project dirs whose name contains SUBSTR (repeatable)
  --command       only include sessions that invoked /NAME (e.g. execute-plan).
                  Matches the <command-name>/NAME</command-name> marker. Repeatable (OR).
  --grep          only include sessions whose raw text matches REGEX (case-insensitive)
  --out           write the full digest as JSON here (default: print only)
  --top           print this many rows of the table (default 40; 0 = all)
  --frustration   also collect candidate human-frustration/correction messages
  --include-subagents  also scan <session-uuid>/subagents/*.jsonl (where Agent/Task
                  subagents' internal turns live — the real work if a session delegates
                  builds/edits to subagents). Off by default.

NOTE: duration_min is raw first->last wall-clock and includes idle gaps (a session left
open overnight reads as ~1500 min with ~100 min of real work). active_min gap-filters
gaps > 30 min and is the better "effort" proxy.

No external deps. No jq required. Pure stdlib. UTF-8 safe on Windows.
"""
import argparse, glob, json, os, re, sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FRUSTRATION = re.compile(
    r"\b(that's wrong|that is wrong|you (didn't|did not|should have|forgot|missed|broke)|"
    r"why did you|that's not (right|what)|incorrect|revert that|undo that|you keep|"
    r"this is wrong|not what i (asked|wanted)|stop\b)", re.I)
# A real compaction injects a continuation preface as a NEW user turn.
COMPACT_BOUNDARY = re.compile(
    r"(this session is being continued from a previous|"
    r"conversation is being continued|"
    r"^\s*This session is being continued)", re.I)


def blocks(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


def text_of(msg):
    out = []
    for b in blocks(msg):
        t = b.get("type")
        if t == "text":
            out.append(b.get("text", ""))
        elif t == "tool_result":
            r = b.get("content")
            if isinstance(r, str):
                out.append(r)
            elif isinstance(r, list):
                out.extend(x.get("text", "") for x in r if isinstance(x, dict) and x.get("type") == "text")
    return "\n".join(out)


def ctx_tokens(usage):
    u = usage or {}
    return ((u.get("input_tokens", 0) or 0)
            + (u.get("cache_read_input_tokens", 0) or 0)
            + (u.get("cache_creation_input_tokens", 0) or 0))


def analyze(path, want_frustration):
    rows = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    r = {
        "path": path,
        "size": os.path.getsize(path),
        "lines": len(rows),
        "user_msgs": 0, "asst_msgs": 0,
        "first_ctx": None, "median_ctx": 0, "max_ctx": 0,
        "tool_use": {},            # tool name -> count
        "commands": [],            # /slash commands invoked
        "agent_dispatches": 0, "agent_models": {},
        "tool_errors": 0,
        "compactions": 0,
        "duration_min": None,
        "frustration": [],
    }
    ctx_series = []
    ts0 = ts1 = None
    for o in rows:
        m = o.get("message")
        ts = o.get("timestamp")
        if ts:
            ts0 = ts0 or ts
            ts1 = ts
        if o.get("isCompactSummary") or o.get("type") in ("summary", "compact"):
            r["compactions"] += 1
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "user":
            r["user_msgs"] += 1
            txt = text_of(m)
            for cmd in re.findall(r"<command-name>(/[\w:-]+)</command-name>", txt):
                r["commands"].append(cmd)
            is_tool = any(b.get("type") == "tool_result" for b in blocks(m))
            if not is_tool and "<command-" not in txt and "<local-command" not in txt:
                if COMPACT_BOUNDARY.search(txt[:300]):
                    r["compactions"] += 1
                if want_frustration:
                    s = txt.strip().replace("\n", " ")
                    if s and FRUSTRATION.search(s[:400]):
                        r["frustration"].append(s[:240])
        elif role == "assistant":
            r["asst_msgs"] += 1
            c = ctx_tokens(m.get("usage"))
            if c:
                ctx_series.append(c)
                if r["first_ctx"] is None:
                    r["first_ctx"] = c
            for b in blocks(m):
                if b.get("type") == "tool_use":
                    name = b.get("name", "?")
                    r["tool_use"][name] = r["tool_use"].get(name, 0) + 1
                    if name in ("Agent", "Task"):
                        r["agent_dispatches"] += 1
                        inp = b.get("input", {}) or {}
                        mdl = inp.get("model") or inp.get("subagent_type") or "?"
                        r["agent_models"][mdl] = r["agent_models"].get(mdl, 0) + 1
                elif b.get("type") == "tool_result" and b.get("is_error"):
                    r["tool_errors"] += 1
            # tool_results can also appear in user turns
        if role == "user":
            for b in blocks(m):
                if b.get("type") == "tool_result" and b.get("is_error"):
                    r["tool_errors"] += 1
    if ctx_series:
        s = sorted(ctx_series)
        r["median_ctx"] = s[len(s) // 2]
        r["max_ctx"] = s[-1]
    try:
        from datetime import datetime
        p = lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))
        if ts0 and ts1:
            r["duration_min"] = round((p(ts1) - p(ts0)).total_seconds() / 60, 1)
        # active_min: sum of inter-event gaps, ignoring idle gaps > 30 min
        active = 0.0
        prev = None
        for o in rows:
            t = o.get("timestamp")
            if not t:
                continue
            cur = p(t)
            if prev is not None:
                gap = (cur - prev).total_seconds() / 60
                if gap <= 30:
                    active += gap
            prev = cur
        r["active_min"] = round(active, 1)
    except Exception:
        pass
    r["command_set"] = sorted(set(r["commands"]))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects-dir", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--match", action="append", default=[])
    ap.add_argument("--command", action="append", default=[])
    ap.add_argument("--grep", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--frustration", action="store_true")
    ap.add_argument("--include-subagents", action="store_true")
    a = ap.parse_args()

    paths = glob.glob(os.path.join(a.projects_dir, "*", "*.jsonl"))
    if a.include_subagents:
        paths += glob.glob(os.path.join(a.projects_dir, "*", "*", "subagents", "*.jsonl"))
    grep = re.compile(a.grep, re.I) if a.grep else None
    cmd_markers = [f"<command-name>{c if c.startswith('/') else '/' + c}</command-name>" for c in a.command]

    results = []
    for path in paths:
        parent = os.path.basename(os.path.dirname(path))
        if a.match and not any(s in parent for s in a.match):
            continue
        try:
            raw = open(path, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        if cmd_markers and not any(mk in raw for mk in cmd_markers):
            continue
        if grep and not grep.search(raw):
            continue
        results.append(analyze(path, a.frustration))

    results.sort(key=lambda x: -x["size"])

    print(f"{'kind':>10} {'MB':>5} {'firstK':>6} {'maxK':>6} {'cmpct':>5} "
          f"{'agt':>4} {'errs':>4} {'dur':>7}  session")
    shown = results if a.top == 0 else results[:a.top]
    for r in shown:
        kind = "".join(sorted({c.lstrip('/').split(':')[-1][:3] for c in r["command_set"]}))[:10] or "-"
        print(f"{kind:>10} {r['size']/1e6:>5.1f} {(r['first_ctx'] or 0)/1000:>6.0f} "
              f"{r['max_ctx']/1000:>6.0f} {r['compactions']:>5} {r['agent_dispatches']:>4} "
              f"{r['tool_errors']:>4} {str(r['duration_min']):>7}  {os.path.basename(r['path'])[:18]}")

    agg = Counter()
    tools = Counter()
    models = Counter()
    for r in results:
        agg["agents"] += r["agent_dispatches"]
        agg["compactions"] += r["compactions"]
        agg["tool_errors"] += r["tool_errors"]
        for k, v in r["tool_use"].items():
            tools[k] += v
        for k, v in r["agent_models"].items():
            models[k] += v
    print(f"\nsessions={len(results)}  totals: {dict(agg)}")
    print(f"agent models/types: {dict(models)}")
    print(f"tool histogram (top): {dict(tools.most_common(12))}")

    if a.out:
        json.dump(results, open(a.out, "w", encoding="utf-8"), indent=1)
        print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
