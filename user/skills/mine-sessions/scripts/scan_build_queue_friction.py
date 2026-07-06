#!/usr/bin/env python3
"""scan_build_queue_friction.py — extract Cognito build-queue friction signals.

Streams every JSONL transcript under one or more project dirs (top-level sessions
AND their <parent>/subagents/*.jsonl children) and pulls out two distinct signals,
each with enough surrounding context to classify it — WITHOUT reading raw
transcripts into an agent's context:

  1. HOOK DENY  — a tool_result carrying the build-queue-enforce deny message
     ("BUILD QUEUE ENFORCED"). For each, captures the *triggering* Bash command
     (the immediately-preceding tool_use in the same assistant turn / file) so a
     read-only inspection false-positive (cat/grep/tail of results or a
     *-filtered.ps1 reference) can be told apart from a real build invocation.

  2. OUTCOME CONFUSION — an assistant text block that reasons about not knowing
     what a build/test invocation did (regex over a curated phrase set: "red
     flag", "tautological", "log capture", "no-output", "zero test", "can't tell
     whether", "ambiguous", "matched nothing", "exit 0 ... red", inspecting
     results/<seq>.json, etc.).

Pure stdlib, UTF-8-safe, streaming (constant memory per line).

Usage:
  python scan_build_queue_friction.py --root <projects-dir> [--root ...] \
      [--out findings.json] [--max-cmd 400] [--context-chars 600]

If no --root is given, defaults to every ~/.claude/projects/*ognito* dir.
Prints a per-signal summary table + a classified breakdown; --out writes full JSON.
"""
import argparse
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DENY_MARKER = "BUILD QUEUE ENFORCED"

# Curated confusion phrases (case-insensitive). Kept deliberately specific to the
# "I don't know what the build/test did" friction.
CONFUSION_RE = re.compile(
    r"("
    r"red flag"
    r"|tautolog"
    r"|log capture"
    r"|no[- ]output"
    r"|zero (?:test|output)"
    r"|matched nothing"
    r"|can'?t tell (?:whether|if)"
    r"|ambiguous"
    r"|exit\s*(?:code\s*)?0[^\n]{0,40}(?:red|fail|suspicious|unexpected)"
    r"|(?:filter|it) matched (?:zero|nothing|no)"
    r"|empty(?: log| output)?[^\n]{0,30}(?:same|as the|green|red)"
    r"|results/\d+\.json"
    r"|result_fidelity"
    r"|build_fidelity"
    r"|inspect the (?:runner|log|result)"
    r"|why (?:the|this) (?:build|test|red)"
    r")",
    re.IGNORECASE,
)

# A command is a READ-ONLY inspector if its invoked verbs are inspection tools and
# it does NOT actually invoke a build/queue wrapper. Heuristic classifier for the
# deny's triggering command.
READONLY_VERB_RE = re.compile(
    r"\b(cat|less|head|tail|grep|rg|type|Get-Content|Select-String|Format-|ConvertFrom-Json|jq|wc|stat|ls|dir|Test-Path)\b",
    re.IGNORECASE,
)
REAL_BUILD_RE = re.compile(
    r"(dotnet\s+(?:build|test)|(?:npx\s+)?nx\s+(?:build|test|run-many)|powershell[^\n]*-File[^\n]*filtered\.ps1|(?<![\w-])(?:build|test|client-build|client-test)-filtered\.ps1\b(?![\s\S]{0,80}(?:cat|tail|head|grep|Get-Content|results)))",
    re.IGNORECASE,
)


def iter_transcripts(root):
    for p in glob.glob(os.path.join(root, "*.jsonl")):
        yield p
    for p in glob.glob(os.path.join(root, "*", "subagents", "*.jsonl")):
        yield p


def text_of(content):
    """Flatten a message.content (str or block list) to text + collect tool_use/tool_result blocks."""
    texts, tool_uses, tool_results = [], [], []
    if isinstance(content, str):
        texts.append(content)
        return texts, tool_uses, tool_results
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t == "text":
                texts.append(b.get("text", ""))
            elif t == "tool_use":
                tool_uses.append(b)
            elif t == "tool_result":
                tool_results.append(b)
    return texts, tool_uses, tool_results


def result_text(block):
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(
            b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def classify_cmd(cmd):
    if not cmd:
        return "unknown"
    has_real = bool(REAL_BUILD_RE.search(cmd))
    has_readonly = bool(READONLY_VERB_RE.search(cmd))
    # Wrapper (sanctioned) invocation would not normally be denied; ignore.
    if has_real and not has_readonly:
        return "real-build"
    if has_readonly and not has_real:
        return "readonly-inspect"
    if has_readonly and has_real:
        return "mixed-inspect-ref"  # inspection that references a build token → the false-positive class
    return "other"


def scan_file(path, max_cmd, ctx):
    denies, confusions = [], []
    # Track the last Bash command seen (tool_use id → command) so a tool_result
    # carrying the deny can be joined to its trigger.
    last_bash_by_id = {}
    last_bash_cmd = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") not in ("user", "assistant"):
                    continue
                msg = rec.get("message") or {}
                texts, tool_uses, tool_results = text_of(msg.get("content"))

                for tu in tool_uses:
                    if tu.get("name") == "Bash":
                        cmd = (tu.get("input") or {}).get("command", "")
                        last_bash_by_id[tu.get("id")] = cmd
                        last_bash_cmd = cmd

                for tr in tool_results:
                    rt = result_text(tr)
                    if DENY_MARKER in rt:
                        cmd = last_bash_by_id.get(tr.get("tool_use_id")) or last_bash_cmd or ""
                        denies.append({
                            "file": os.path.basename(path),
                            "line": lineno,
                            "trigger_cmd": cmd[:max_cmd],
                            "classification": classify_cmd(cmd),
                        })

                for txt in texts:
                    if not txt:
                        continue
                    m = CONFUSION_RE.search(txt)
                    if m and rec.get("type") == "assistant":
                        start = max(0, m.start() - ctx // 3)
                        confusions.append({
                            "file": os.path.basename(path),
                            "line": lineno,
                            "phrase": m.group(0)[:80],
                            "excerpt": txt[start:start + ctx].replace("\n", " "),
                        })
    except Exception as e:
        return denies, confusions, str(e)
    return denies, confusions, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", default=[])
    ap.add_argument("--out")
    ap.add_argument("--max-cmd", type=int, default=400)
    ap.add_argument("--context-chars", type=int, default=600)
    args = ap.parse_args()

    roots = args.root or glob.glob(
        os.path.join(os.path.expanduser("~"), ".claude", "projects", "*ognito*")
    )

    all_denies, all_conf = [], []
    files_scanned = 0
    for root in roots:
        for path in iter_transcripts(root):
            files_scanned += 1
            d, c, err = scan_file(path, args.max_cmd, args.context_chars)
            all_denies.extend(d)
            all_conf.extend(c)

    by_class = {}
    for d in all_denies:
        by_class[d["classification"]] = by_class.get(d["classification"], 0) + 1

    print(f"files scanned: {files_scanned}")
    print(f"\n=== HOOK DENYS: {len(all_denies)} total ===")
    print("by classification:", json.dumps(by_class, indent=None))
    print("\n-- deny triggers (classification | cmd) --")
    for d in all_denies:
        print(f"[{d['classification']:>17}] {d['trigger_cmd']}")

    print(f"\n=== OUTCOME-CONFUSION hits: {len(all_conf)} total ===")
    phrase_hist = {}
    for c in all_conf:
        key = c["phrase"].lower()[:24]
        phrase_hist[key] = phrase_hist.get(key, 0) + 1
    for k, v in sorted(phrase_hist.items(), key=lambda kv: -kv[1]):
        print(f"  {v:>4}  {k}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"denies": all_denies, "confusions": all_conf,
                       "by_class": by_class, "files_scanned": files_scanned}, fh, indent=2)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
