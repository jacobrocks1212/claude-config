# harness-gate.py false-positives on generated docs + PHASES.md prose — Investigation Spec

> harness-gate.py runs its structural detectors over EVERY file in the diff range, so off-manifest generated docs (LAZY_QUEUE.md), PHASES.md prose rows, and unrelated bug/feature SPEC.md files swept into a range produce `gate_weakening=hit` / `overfit=flag` false positives — forcing redundant operator sign-off on plane-strengthening changes.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-18
**Fixed:** 2026-07-19
**Fix commit:** 2a2fb10b
**Placement:** docs/bugs/adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose
**Related:** docs/features/anti-overfit-design-gate/SPEC.md · user/skills/_components/harness-change-gate.md · user/scripts/harness-gate.py

<!-- Status lifecycle: Investigating -> Concluded (root cause traced; ready for /plan-bug). -->

---

## Verified Symptoms

1. **[VERIFIED]** A `/lazy-batch` run whose diff touches ≥1 real control-surface file AND also regenerates `LAZY_QUEUE.md` gets `gate_weakening=hit` on the queue-count renumber line (`## Bugs (17)` → `## Bugs (16)`), via the numeric-literal-change detector. — reproduced against the live detector (below).
2. **[VERIFIED]** A PHASES.md prose row that merely mentions a `*_BYPASS` env-var (e.g. documenting `BUILD_QUEUE_BYPASS=1` as a deliberate override) gets `gate_weakening=hit` via the new-bypass-env-var detector. — reproduced against the live detector.
3. **[VERIFIED]** An unrelated `docs/{features,bugs}/<slug>/SPEC.md` swept into the same diff range gets `overfit=flag` (`incident-shaped literal added`) when its prose cites another slug's `docs/bugs/<slug>` path. — reproduced against the live detector.
4. **[VERIFIED]** A fail-open breadcrumb shell line in an ON-manifest hook (`_HOOK_*_TS="$(date … || echo 0)"`) gets `overfit=flag` (`alternation literal appended`) because the shell `||` + a quoted `$( … )` satisfies the regex-alternation heuristic. — reproduced against the live detector.
5. **[VERIFIED]** Symptoms 1–2 set `verdict_required: true` (`gate_weakening` is `hit`, never judgment-passable), forcing an operator sign-off round on a change that only STRENGTHENED the plane. Two live occurrences in one run (2026-07-18): the containment-hook fix and the subagent-wedge-backstop-hook completion. — reported in ADHOC_BRIEF.md; mechanism confirmed by trace.

## Reproduction Steps

Deterministic, against the live detectors (`python3` on this repo):

```python
import importlib.util, os
spec = importlib.util.spec_from_file_location('hg', os.path.expanduser('~/.claude/scripts/harness-gate.py'))
hg = importlib.util.module_from_spec(spec); spec.loader.exec_module(hg)

class Hk:  # minimal hunk double
    def __init__(s, f, a): s.file=f; s.added=a; s.removed=[]; s.added_ctx=[(x, []) for x in a]

# S2 (FP1): PHASES.md prose mentioning a *_BYPASS env-var
h = Hk('docs/bugs/x/PHASES.md', ['the deliberate one-off override is BUILD_QUEUE_BYPASS=1 leading the segment'])
assert hg.detect_gate_weakening([h])['result'] == 'hit'

# S1 (FP2): LAZY_QUEUE.md queue-count renumber
h = Hk('LAZY_QUEUE.md', ['## Bugs (16)']); h.removed = ['## Bugs (17)']
assert hg.detect_gate_weakening([h])['result'] == 'hit'

# S3 (FP4): unrelated SPEC.md citing another slug's path
h = Hk('docs/bugs/unrelated/SPEC.md', ["  - see 'docs/bugs/some-other-incident-slug' for prior art"])
assert hg.detect_overfit([h])['result'] == 'flag'

# S4 (FP3): on-manifest hook breadcrumb line (shell || + quoted $( ))
h = Hk('user/hooks/foo.sh', ['  _HOOK_NOPY_TS="$(date +%s 2>/dev/null || echo 0)"'])
assert hg.detect_overfit([h])['result'] == 'flag'
```

**Expected:** Off-manifest generated docs / PHASES.md prose / unrelated SPEC.md files swept into a range are NOT inspected by the structural detectors; a shell breadcrumb pipe in real code is not misread as a matcher-alternation append.
**Actual:** All four produce a flag/hit; S1–S2 escalate to `verdict_required: true`.
**Consistency:** Always (pure functions of the diff text).

## Evidence Collected

### Source Code

Root cause is a **scope mismatch in `run_checker`** (`user/scripts/harness-gate.py:373-407`):

- `hits = scope_hits(changed, globs)` (line 375) filters the changed-PATH list to the manifest control-surface subset — but is used ONLY for the `in_scope` decision (lines 376-382).
- `hunks = parse_diff(diff_text)` (line 383) parses the **entire** `git diff <range>` — one `_Hunk` per file for EVERY changed file, including off-manifest ones.
- `detect_overfit(hunks)` / `detect_gate_weakening(hunks)` (lines 384-385) iterate **all** hunks; they never filter by `h.file ∈ hits`.

So once a diff is in scope (one legitimate control-surface edit suffices), every OTHER file's hunks are scanned too. The specific detector sites that then fire on off-target content:

| FP | Detector site | Why it fires |
|----|---------------|--------------|
| S2 (BYPASS on PHASES prose) | `detect_gate_weakening` line 308 `_BYPASS_ENV_RE.search(body)` (`:92`) | any added line mentioning `…_BYPASS` matches; PHASES.md prose is not code |
| S1 (LAZY_QUEUE renumber) | `_numeric_literal_change` (`:331`, called `:327`) | removed `## Bugs (17)` + added `## Bugs (16)` normalize to the same key, numbers differ → hit; LAZY_QUEUE.md is a generated doc regenerated every cycle |
| S3 (unrelated SPEC literal) | `detect_overfit` case (c) lines 248-251 `_INCIDENT_LITERAL_RE` (`:88`) | a `docs/bugs/<slug>` literal in an unrelated SPEC swept into the range |
| S4 (hook breadcrumb) | `detect_overfit` case (a) line 236 `_ALTERNATION_ADD_RE` (`:84`) + `_QUOTED_RE` | shell `|| echo 0` + quoted `"$( … )"` satisfies the regex-alternation-append heuristic |

Manifest (`docs/gate/control-surfaces.json`): `control_surfaces` + `gate_own` are code/gate files (`user/hooks/**`, `user/scripts/lazy*`, `user/skills/lazy*/**`, settings, etc.). `LAZY_QUEUE.md`, `docs/kpi/SCORECARD.md`, per-item `PHASES.md`, and `docs/{features,bugs}/<slug>/SPEC.md` are **not** on the manifest — the exact off-target surfaces the detectors should never have inspected.

### Git History

`harness-gate.py` has two prior hardening rounds (`7dd6ad78` rename/docstring/fixture FPs; `cf105d9a` deny-construct-reformat net-count) — both tightened detectors against FPs *inside* code files. Neither addressed the file-scope mismatch (detectors scanning off-manifest files), which is this bug.

### Related Documentation

`user/scripts/CLAUDE.md` and root `CLAUDE.md` both describe the gate as scoped by "changed paths that are code (or on the manifest)" — the scoping the code does NOT actually apply at the detector layer. The design intent ("keyed on diff SHAPES … its files are on the manifest's `gate_own` block") assumes detectors see only manifest-relevant content.

## Theories

### Theory 1: Detectors scan the whole diff, not the manifest subset (PRIMARY)
- **Hypothesis:** `run_checker` restricts only `in_scope`, then runs detectors over all hunks; off-manifest files (LAZY_QUEUE.md, PHASES.md, unrelated SPEC.md) are inspected and flag/hit.
- **Supporting evidence:** trace above (`:375` used for scope only; `:383-385` unfiltered); S1/S2/S3 all reproduce on off-manifest files.
- **Contradicting evidence:** none.
- **Status:** Confirmed (`traced` — serving path `main:445 → run_checker:383-385 → detect_*`; fix site = the unfiltered `hunks` passed to the detectors, which is ON the path).

### Theory 2: overfit alternation heuristic over-matches shell code (SECONDARY)
- **Hypothesis:** `detect_overfit` case (a) treats any `|` + quoted-literal added line as a matcher-alternation append, catching legitimate shell `||`/pipe breadcrumb lines in ON-manifest hooks.
- **Supporting evidence:** S4 reproduces on `user/hooks/foo.sh` (an on-manifest file — NOT fixed by the Theory-1 scoping fix).
- **Contradicting evidence:** `overfit` is a `flag` (judgment-passable), not a `hit`, so S4 alone does not force operator sign-off — lower blast radius than S1/S2.
- **Status:** Confirmed (`traced` — `detect_overfit:236`; fix site = the `_ALTERNATION_ADD_RE` heuristic, on-path).

## Proven Findings

- **Both causes are `traced`, not asserted.** Each of the four symptoms was reproduced against the live detector functions with the offending hunk shape, and each fix site lies on the traced serving path (`run_checker`'s unfiltered `hunks` for S1/S2/S3; the `_ALTERNATION_ADD_RE` heuristic for S4).
- **Scope-fix coverage:** filtering detector input to hunks whose `h.file ∈ hits` (the manifest control-surface subset) resolves S1, S2, S3 (all off-manifest). It does **not** resolve S4 (the hook file is on-manifest) — S4 needs a detector-precision change to the overfit alternation heuristic.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Detector scope gate | `user/scripts/harness-gate.py` (`run_checker` `:373-407`; `parse_diff` `:188`) | primary fix: filter hunks to `hits` before detection (S1/S2/S3) |
| overfit alternation heuristic | `user/scripts/harness-gate.py` (`detect_overfit` `:236`; `_ALTERNATION_ADD_RE` `:84`) | secondary fix: don't fire on shell `||`/pipe breadcrumb lines (S4) |
| Regression fixtures | `user/scripts/test_harness_gate.py` | add fixtures for all four FP shapes |

## Open Questions

- **FP3/S4 fix scope (fix-shape decision for /plan-bug, NOT a cause gap).** Options: (A) fix only the off-manifest scoping (S1/S2/S4-off-target), leaving the overfit heuristic to keep flagging on-manifest hook breadcrumb lines — a judgment-passable flag, low blast radius; (B) ALSO tighten `_ALTERNATION_ADD_RE`/case-(a) so a shell `||`/pipe in a real hook is not misread as a matcher-alternation append. ⚖ policy: FP3 fix scope → recommend **B (complete)** — the brief explicitly lists the breadcrumb-line FP among the defects to fix, and a persistent noisy flag erodes trust in the gate. Guard against over-narrowing the overfit detector (its real coverage is a literal appended to a genuine regex-alternation matcher) — the harness-change-gate + regression fixtures own that risk at plan time.
- **Scoping mechanism.** Whether to filter by `h.file ∈ hits` (manifest membership — the SSOT already lists the real gate files) OR by a code-vs-doc file-extension heuristic. Recommend the former (manifest membership) — it reuses the existing `scope_hits`/`_glob_match` SSOT, needs no new "is this code" heuristic, and keeps `docs/gate/control-surfaces.json` the single owner of what the gate inspects. A future genuine gate-doc surface added to the manifest is then covered for free.
