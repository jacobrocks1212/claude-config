#!/usr/bin/env python3
"""render_session.py — render ONE Claude Code .jsonl transcript to readable, greppable text.

Use this AFTER digest_sessions.py has narrowed the field to a few high-signal sessions.
It linearizes a transcript into one block per turn so you can grep/read regions instead
of loading multi-MB JSON. Tool calls are summarized (not dumped in full).

Usage:
    python render_session.py <session.jsonl> [--max-chars N] [--grep REGEX] [--ctx-min K] > out.txt

  --max-chars   truncate each turn's text to N chars (default 4000)
  --grep        only print turns whose rendered text matches REGEX (case-insensitive)
  --ctx-min     only print turns whose context footprint >= K thousand tokens

Each turn header: ===== [#idx role ctx=<tokens>] <<MARKERS>> =====
Markers: COMPACTION (continuation boundary), HUMAN (real user message, not a tool result
or slash-command), TOOL_ERROR. Extend the marker logic for your own investigation.
ctx = input_tokens + cache_read + cache_creation (the model's context size at that turn).
"""
import argparse, json, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

COMPACT = re.compile(r"(this session is being continued from a previous|"
                     r"conversation is being continued|compact summary)", re.I)


def blocks(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


def render(path, max_chars, grep, ctx_min):
    idx = 0
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        m = o.get("message")
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        idx += 1
        role = m.get("role")
        u = m.get("usage") or {}
        ctx = ((u.get("input_tokens", 0) or 0) + (u.get("cache_read_input_tokens", 0) or 0)
               + (u.get("cache_creation_input_tokens", 0) or 0))
        parts, markers, is_tool_result = [], [], False
        for b in blocks(m):
            bt = b.get("type")
            if bt == "text":
                parts.append(b.get("text", ""))
            elif bt == "tool_use":
                name = b.get("name", ""); inp = b.get("input", {}) or {}
                if name in ("Agent", "Task"):
                    parts.append(f"[Agent model={inp.get('model','?')} type={inp.get('subagent_type','')} "
                                 f"desc={inp.get('description','')!r}]\n  PROMPT_HEAD: {str(inp.get('prompt',''))[:500]}")
                elif name == "Skill":
                    parts.append(f"[Skill {inp.get('skill') or inp.get('command')} args={inp.get('args','')!r}]")
                elif name == "Bash":
                    parts.append(f"[Bash] {str(inp.get('command',''))[:400]}")
                elif name in ("Edit", "Write", "Read", "NotebookEdit"):
                    parts.append(f"[{name} {inp.get('file_path') or inp.get('notebook_path','')}]")
                elif name in ("TaskCreate", "TaskUpdate", "TaskList", "TaskGet"):
                    parts.append(f"[{name} {json.dumps(inp)[:300]}]")
                else:
                    parts.append(f"[{name} {json.dumps(inp)[:200]}]")
            elif bt == "tool_result":
                is_tool_result = True
                r = b.get("content"); s = ""
                if isinstance(r, str):
                    s = r
                elif isinstance(r, list):
                    s = "\n".join(x.get("text", "") for x in r if isinstance(x, dict) and x.get("type") == "text")
                if b.get("is_error"):
                    markers.append("TOOL_ERROR")
                parts.append(f"[RESULT]{' (ERROR)' if b.get('is_error') else ''} {s[:max_chars]}")
        txt = "\n".join(parts)
        if COMPACT.search(txt):
            markers.append("COMPACTION")
        if role == "user" and not is_tool_result and "<command-" not in txt and "<local-command" not in txt and txt.strip():
            markers.append("HUMAN")
        if ctx_min and ctx < ctx_min * 1000:
            continue
        if grep and not grep.search(txt):
            continue
        mk = (" <<" + ",".join(sorted(set(markers))) + ">>") if markers else ""
        print(f"\n===== [#{idx} {role} ctx={ctx}]{mk} =====")
        print(txt[:max_chars])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--max-chars", type=int, default=4000)
    ap.add_argument("--grep", default=None)
    ap.add_argument("--ctx-min", type=int, default=0)
    a = ap.parse_args()
    render(a.path, a.max_chars, re.compile(a.grep, re.I) if a.grep else None, a.ctx_min)


if __name__ == "__main__":
    main()
