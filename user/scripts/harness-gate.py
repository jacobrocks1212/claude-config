#!/usr/bin/env python3
"""harness-gate.py — mechanical anti-overfit / tautology / gate-weakening / complexity
checker for claude-config harness self-modifications.

Feature: anti-overfit-design-gate (docs/features/anti-overfit-design-gate/SPEC.md).

A self-improving harness can overfit to single incidents, silently weaken its own gates,
and grade itself with metrics it controls. This checker is the mechanical FLOOR of the
design gate (SPEC D2): it inspects a git diff against a committed control-surface manifest
(docs/gate/control-surfaces.json, SPEC D1 option A) and reports per-check findings. A flag
is NOT a verdict — the adversarial half (recorded prose in GATE_VERDICT.md, per the
_components/harness-change-gate.md protocol) decides. Blocking authority lives ONLY at the
completion gate (SPEC D3 option A); this script only reports.

Detectors are deliberately STRUCTURAL, not incident-literal — the checker must pass its own
overfit check (its files are on the manifest's gate_own list). Each keys on diff SHAPES:

  overfit         An added quoted literal appended to a matcher construct (regex alternation,
                  list/set element, keyword/allow-list), OR an added literal that matches a
                  docs/{features,bugs}/<slug> id or a dated/session-shaped path. Fitting to
                  the observed instance, not the structure. -> result: "flag".
                  Named regression fixtures: the _VERIFICATION_SECTION_RE phrase-append.
  tautology       Presence check over the item's SPEC ## Intervention Hypothesis block: the
                  signal_independence declaration must be present and not `self-emitted`
                  (without justification) for a scoped change. -> "flag" (missing) /
                  "self-emitted" / "pass".
  gate_weakening  Diff-level, NEVER judgment-passable (routes to operator sign-off, SPEC D4):
                  deletion of a `def test_*` without replacement; a numeric-literal-only change
                  on a gate-code line; an addition to a sanction/exemption set (e.g.
                  SANCTIONED_STOP_TERMINAL, _FAIL_CLOSED_EVIDENCE_SENTINELS, hook allow-prefix
                  lists); a new bypass env-var (the *_BYPASS shape); removal of a
                  `permissionDecision: deny` branch, a `refuse_*` call site, or an `exit 3`
                  refusal. -> result: "hit".
                  Named regression fixture: the GAP-2 exemption-add + gate-test deletion.
  complexity      Presence check: a scoped change must carry a `retires:` declaration in its
                  verdict (names a retired rule/surface, or `net-new` + justification). The
                  checker cannot read the not-yet-written verdict, so it emits
                  "declaration-required" whenever in scope — the ship seam asserts the verdict
                  actually carries the line. -> "declaration-required" (in scope) / "pass".

Exit codes (match the state-script conventions): 0 = pass / out-of-scope, 1 = verdict-required
findings, 2 = malformed input (bad manifest / git failure). Read-only: shells `git diff` /
`git diff --name-only`; never writes.

CLI:
  harness-gate.py --repo-root . --range origin/main..HEAD [--json]
  harness-gate.py --repo-root . --staged [--json]
  harness-gate.py --repo-root . --range A..B --feature-dir docs/features/<slug> [--json]

`--feature-dir` (optional) points at the item dir whose SPEC.md the tautology detector reads;
absent, tautology reports `pass` with a note (no SPEC to inspect — the ship seam supplies it).
"""

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

MANIFEST_REL = "docs/gate/control-surfaces.json"

# Exemption/sanction set names whose growth is gate-weakening (SPEC D2). Structural: the
# detector keys on an added string element in a hunk that mentions one of these identifiers,
# NOT on any incident literal. Extend deliberately (adding a name here is itself a scoped change).
_EXEMPTION_SET_NAMES = (
    "SANCTIONED_STOP_TERMINAL",
    "_FAIL_CLOSED_EVIDENCE_SENTINELS",
    "_NOTIFY_ATTENTION_TERMINALS",
    "_NOTIFY_CLEAN_STOP_TERMINALS",
    "_DEFINITIVE_MCP_VERDICTS",
    "_FORWARD_ADVANCING_PSEUDO_SKILLS",
    "_MULTI_COMMIT_DISPATCH_SKILLS",
    "ALLOW_PREFIX",
    "ALLOWED",
    "allow_prefixes",
    "SAFE_VARIANTS",
)

# A quoted string literal (single or double quotes), non-greedy body.
_QUOTED_RE = re.compile(r"""(['"])(?P<body>(?:\\.|(?!\1).)*)\1""")
# A regex-alternation append: an added fragment introducing a new `|...` alternative.
_ALTERNATION_ADD_RE = re.compile(r"\|\s*[\w\\\s.\-+*?()\[\]'\"]")
# A bare list/set string element line: `+    'foo',` / `+  "bar"` (optional trailing comma).
_LIST_ELEMENT_RE = re.compile(r"""^\+\s*(['"]).*\1\s*,?\s*$""")
# docs/{features,bugs}/<slug> id, dated path, or session-shaped path — overfit-to-incident tells.
_INCIDENT_LITERAL_RE = re.compile(
    r"docs/(?:features|bugs)/[a-z0-9][a-z0-9-]+|\d{4}-\d{2}-\d{2}|session[-_][0-9A-Za-z]{6,}"
)
# A new bypass env-var: an added `*_BYPASS` token (assignment, getenv, or comparison).
_BYPASS_ENV_RE = re.compile(r"\b[A-Z][A-Z0-9_]*_BYPASS(?:=|['\"\s)\]]|$)")
# Gate-refusal constructs whose REMOVAL is weakening.
_DENY_BRANCH_RE = re.compile(r"permissionDecision['\"\s:]+.*deny|\bexit\s+3\b|\brefuse_[a-z_]+\s*\(")
# A `def test_*` definition line.
_TEST_DEF_RE = re.compile(r"^\s*def\s+test_[A-Za-z0-9_]+\s*\(")
# A numeric literal (int or float).
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
# A triple-quoted (docstring) delimiter anywhere on the line. A docstring line is
# never a membership-set element — excluded from the list-element check so an added
# docstring is not misread as an allowlist/enum growth (gap 2 FP: the recurring
# `membership added: """` false positive, e.g. hardening-log Round 67).
_TRIPLE_QUOTE_RE = re.compile(r'"""|' + r"'''")
# The exemption set name appears in a COLLECTION-OPENING / EXTENSION position on a
# context line — an assignment whose RHS opens a collection literal (`NAME = {`,
# `NAME = (`, `NAME = [`, `NAME: T = [`, `NAME = frozenset({`, `NAME = set([`). This
# distinguishes a set genuinely being defined/grown from a bare REFERENCE to the name
# (`assert x in NAME`, an import, a call arg) that a test fixture may sit beside (gap 2
# FP: a list-literal fixture near an exemption-name mention misread as membership growth).
def _exemption_opens_collection(nearby_line: str, name: str) -> bool:
    return re.search(
        r"\b" + re.escape(name) + r"\b[^\n=]*=\s*[\w.]*[\[{(]",
        nearby_line,
    ) is not None


def _die(msg: str) -> "int":
    sys.stderr.write(f"harness-gate: {msg}\n")
    return 2


def _run_git(repo_root: Path, args: list) -> "tuple[int, str, str]":
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError) as exc:  # git absent, bad args
        return 1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def load_manifest(repo_root: Path) -> dict:
    """Read + validate the control-surface manifest. Raises ValueError on malformed input."""
    path = repo_root / MANIFEST_REL
    if not path.exists():
        raise ValueError(f"manifest not found: {MANIFEST_REL}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"manifest unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("manifest is not a JSON object")
    surfaces = data.get("control_surfaces")
    gate_own = data.get("gate_own", [])
    if not isinstance(surfaces, list) or not all(isinstance(g, str) for g in surfaces):
        raise ValueError("manifest.control_surfaces must be a list of glob strings")
    if not isinstance(gate_own, list) or not all(isinstance(g, str) for g in gate_own):
        raise ValueError("manifest.gate_own must be a list of glob strings")
    return {"globs": list(surfaces) + list(gate_own)}


def _glob_match(path: str, glob: str) -> bool:
    """fnmatch with '**' spanning separators. A trailing '/**' also matches the dir itself."""
    path = path.replace("\\", "/")
    glob = glob.replace("\\", "/")
    if "**" in glob:
        # Translate '**' -> match-anything (incl. '/'); other tokens via fnmatch.translate.
        regex = re.escape(glob).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*")
        regex = regex.replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
        return re.fullmatch(regex, path) is not None
    return fnmatch.fnmatch(path, glob)


def scope_hits(changed: list, globs: list) -> list:
    """The subset of changed paths matching >=1 manifest glob (POSIX, normalized)."""
    hits = []
    for f in changed:
        fn = f.replace("\\", "/")
        if any(_glob_match(fn, g) for g in globs):
            hits.append(fn)
    return hits


# --- diff parsing -----------------------------------------------------------------

class _Hunk:
    __slots__ = ("file", "added", "removed", "added_ctx")

    def __init__(self, file):
        self.file = file
        self.added = []       # added line bodies (without the leading '+')
        self.removed = []     # removed line bodies (without the leading '-')
        self.added_ctx = []   # (added_body, [context lines in this hunk]) for near-set detection


def parse_diff(diff_text: str) -> list:
    """Parse `git diff` unified output into per-file added/removed line sets."""
    hunks = []
    cur = None
    ctx_window = []
    cur_file = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            cur_file = None
            cur = None
            ctx_window = []
            continue
        if line.startswith("+++ b/"):
            cur_file = line[6:]
            cur = _Hunk(cur_file)
            hunks.append(cur)
            ctx_window = []
            continue
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("@@"):
            ctx_window = []
            continue
        if cur is None:
            continue
        if line.startswith("+"):
            body = line[1:]
            cur.added.append(body)
            cur.added_ctx.append((body, list(ctx_window)))
            ctx_window.append(body)
        elif line.startswith("-"):
            cur.removed.append(line[1:])
            ctx_window.append(line[1:])
        else:
            ctx_window.append(line[1:] if line[:1] == " " else line)
        if len(ctx_window) > 8:
            ctx_window = ctx_window[-8:]
    return hunks


# --- detectors --------------------------------------------------------------------

def detect_overfit(hunks: list) -> dict:
    evidence = []
    for h in hunks:
        for body, ctx in h.added_ctx:
            plus = "+" + body
            # (a) regex-alternation append: the added fragment introduces a new `|...`
            if "|" in body and _ALTERNATION_ADD_RE.search(body) and _QUOTED_RE.search(body):
                evidence.append(f"{h.file}: alternation literal appended: {body.strip()[:80]}")
                continue
            # (b) bare quoted list/set element added into a membership construct
            if _LIST_ELEMENT_RE.match(plus):
                nearby = " ".join(ctx[-6:])
                # membership context: a bracket/brace/set-name nearby OR the element sits in a list
                if ("[" in nearby or "{" in nearby or "(" in nearby
                        or any(name in nearby for name in _EXEMPTION_SET_NAMES)):
                    evidence.append(f"{h.file}: literal element appended to a membership construct: {body.strip()[:80]}")
                    continue
            # (c) an added literal matching a docs slug / dated / session path (incident tell)
            for m in _QUOTED_RE.finditer(body):
                if _INCIDENT_LITERAL_RE.search(m.group("body")):
                    evidence.append(f"{h.file}: incident-shaped literal added: {m.group('body')[:80]}")
                    break
    return {"result": "flag" if evidence else "pass", "evidence": evidence}


def detect_gate_weakening(hunks: list) -> dict:
    evidence = []
    # Per-file test-def rename/strengthen guard (gap 2 FP: a renamed test def).
    # A `def test_old` -> `def test_new` rename removes AND adds one test def; a
    # split (1 removed, N>=1 added) preserves-or-strengthens coverage. Aggregate
    # per file and flag ONLY the NET removal (removed - added > 0) — a rename (1/1)
    # or split (1/2) is coverage-neutral-or-strengthening and never a weakening,
    # while a genuine removal with no replacement (1/0) still HITs unchanged.
    removed_test_defs: "dict[str, int]" = {}
    added_test_defs: "dict[str, int]" = {}
    for h in hunks:
        removed_test_defs[h.file] = removed_test_defs.get(h.file, 0) + sum(
            1 for body in h.removed if _TEST_DEF_RE.match(body)
        )
        added_test_defs[h.file] = added_test_defs.get(h.file, 0) + sum(
            1 for body in h.added if _TEST_DEF_RE.match(body)
        )
    for f in removed_test_defs:
        net = removed_test_defs[f] - added_test_defs.get(f, 0)
        if net > 0:
            evidence.append(
                f"{f}: gate-test definition removed without replacement "
                f"(net {net}; {removed_test_defs[f]} removed, "
                f"{added_test_defs.get(f, 0)} added)"
            )

    for h in hunks:
        for body in h.removed:
            if _DENY_BRANCH_RE.search(body):
                evidence.append(f"{h.file}: gate-refusal construct removed: {body.strip()[:80]}")
        for body, ctx in h.added_ctx:
            if _BYPASS_ENV_RE.search(body):
                evidence.append(f"{h.file}: new bypass env-var introduced: {body.strip()[:80]}")
            plus = "+" + body
            # A triple-quoted (docstring) line is never a membership element (gap 2 FP).
            if _TRIPLE_QUOTE_RE.search(body):
                continue
            if _LIST_ELEMENT_RE.match(plus):
                # A membership-set GROWTH weakens a gate only when the exemption set
                # is genuinely being defined/extended nearby (a collection-opening
                # assignment), NOT when its name merely appears as a bare reference a
                # fixture may sit beside (gap 2 FP: a list-literal test fixture).
                nearby_lines = ctx[-6:] + [body]
                if any(
                    _exemption_opens_collection(line, name)
                    for line in nearby_lines
                    for name in _EXEMPTION_SET_NAMES
                ):
                    evidence.append(f"{h.file}: exemption/sanction-set membership added: {body.strip()[:80]}")
        # numeric-literal-only change: a removed line and an added line identical but for a number
        _numeric_literal_change(h, evidence)
    return {"result": "hit" if evidence else "pass", "evidence": evidence}


def _numeric_literal_change(h: "_Hunk", evidence: list) -> None:
    rem_norm = {}
    for body in h.removed:
        key = _NUM_RE.sub("#", body).strip()
        if key and _NUM_RE.search(body):
            rem_norm.setdefault(key, body)
    for body in h.added:
        key = _NUM_RE.sub("#", body).strip()
        if key in rem_norm and _NUM_RE.search(body):
            rold = _NUM_RE.findall(rem_norm[key])
            rnew = _NUM_RE.findall(body)
            if rold != rnew:
                evidence.append(
                    f"{h.file}: numeric-literal change on a gate line: "
                    f"{rem_norm[key].strip()[:50]} -> {body.strip()[:50]}"
                )


_HYP_BLOCK_RE = re.compile(r"^##\s+Intervention Hypothesis\s*$", re.MULTILINE)
_SIGNAL_INDEP_RE = re.compile(r"^\s*[-*]\s*signal_independence\s*:\s*(?P<val>\S+)", re.MULTILINE)


def detect_tautology(feature_dir: "Path | None") -> dict:
    if feature_dir is None:
        return {"result": "pass", "evidence": [], "note": "no feature-dir supplied; ship seam supplies the SPEC"}
    spec = feature_dir / "SPEC.md"
    if not spec.exists():
        return {"result": "flag", "evidence": [f"SPEC.md missing in {feature_dir}"], "note": "cannot verify signal independence"}
    text = spec.read_text(encoding="utf-8")
    if not _HYP_BLOCK_RE.search(text):
        return {"result": "flag", "evidence": ["no `## Intervention Hypothesis` block"],
                "note": "a scoped change must declare its measurement hypothesis (SPEC D6)"}
    m = _SIGNAL_INDEP_RE.search(text)
    if not m:
        return {"result": "flag", "evidence": ["`signal_independence` absent from the hypothesis block"], "note": ""}
    val = m.group("val").strip().lower().rstrip(".,")
    if val in ("self-emitted", "self_emitted"):
        return {"result": "self-emitted", "evidence": ["signal_independence: self-emitted"],
                "note": "the success metric may be tautological — the change emits its own signal"}
    return {"result": "pass", "evidence": [], "note": f"signal_independence: {val}"}


def run_checker(repo_root: Path, diff_text: str, changed: list,
                feature_dir: "Path | None", globs: list) -> dict:
    hits = scope_hits(changed, globs)
    if not hits:
        return {
            "in_scope": False,
            "scope_hit": [],
            "checks": {},
            "verdict_required": False,
        }
    hunks = parse_diff(diff_text)
    overfit = detect_overfit(hunks)
    gate_weak = detect_gate_weakening(hunks)
    taut = detect_tautology(feature_dir)
    complexity = {"result": "declaration-required",
                  "note": "the verdict MUST carry a `retires:` line (a retired rule/surface, or `net-new` + justification)"}
    checks = {
        "overfit": overfit,
        "tautology": taut,
        "gate_weakening": gate_weak,
        "complexity": complexity,
    }
    verdict_required = (
        overfit["result"] != "pass"
        or gate_weak["result"] != "pass"
        or taut["result"] != "pass"
        or complexity["result"] != "pass"
    )
    return {
        "in_scope": True,
        "scope_hit": hits,
        "checks": checks,
        "verdict_required": verdict_required,
        "gate_weakening_hit": gate_weak["result"] == "hit",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Anti-overfit / gate-weakening design-gate checker.")
    ap.add_argument("--repo-root", default=".")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--range", help="git revision range A..B (default origin/main..HEAD)")
    grp.add_argument("--staged", action="store_true", help="inspect the staged diff")
    ap.add_argument("--feature-dir", help="item dir whose SPEC.md the tautology check reads")
    ap.add_argument("--json", action="store_true", help="emit JSON (default)")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    feature_dir = Path(args.feature_dir).resolve() if args.feature_dir else None

    try:
        manifest = load_manifest(repo_root)
    except ValueError as exc:
        return _die(str(exc))

    if args.staged:
        diff_args = ["diff", "--staged"]
        name_args = ["diff", "--staged", "--name-only"]
    else:
        rng = args.range or "origin/main..HEAD"
        diff_args = ["diff", rng]
        name_args = ["diff", rng, "--name-only"]

    rc, names_out, err = _run_git(repo_root, name_args)
    if rc != 0:
        return _die(f"git {' '.join(name_args)} failed: {err.strip()}")
    changed = [l.strip() for l in names_out.splitlines() if l.strip()]

    rc, diff_out, err = _run_git(repo_root, diff_args)
    if rc != 0:
        return _die(f"git {' '.join(diff_args)} failed: {err.strip()}")

    result = run_checker(repo_root, diff_out, changed, feature_dir, manifest["globs"])
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["in_scope"]:
        return 0
    return 1 if result["verdict_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
