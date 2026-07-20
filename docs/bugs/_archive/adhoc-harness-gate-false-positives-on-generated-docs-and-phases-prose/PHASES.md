# Implementation Phases — harness-gate.py false-positives on generated docs + PHASES.md prose

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Fixed

**MCP runtime:** not-required — claude-config has no Tauri/MCP runtime surface; `harness-gate.py` is pure stdlib detector logic validated by the `test_harness_gate.py` unit suite (mcp-testing "no runtime-observable surface" class).

## Touchpoint Audit (verified inline — dispatch unavailable in cycle subagent)

`verified: inline (dispatch unavailable)`

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/harness-gate.py` | yes | `run_checker` (:373, scopes only `in_scope` via `hits = scope_hits(...)` :375, then runs detectors over ALL `parse_diff` hunks :383-385), `scope_hits` (:166, returns POSIX-normalized `changed ∩ globs`), `parse_diff` (:188), `_Hunk` (:178; `.file`, `.added`, `.removed`, `.added_ctx`), `detect_overfit` (:230; case (a) at :236), `detect_gate_weakening` (:255), `_ALTERNATION_ADD_RE` (:84), `_QUOTED_RE` (:82) | refactor | S1/S2/S3: filter `hunks` to `h.file ∈ set(hits)` INSIDE `run_checker` immediately after :383, BEFORE the detectors — reuse `scope_hits`'s output (the manifest-membership SSOT), do NOT add a new is-code heuristic. Normalize `h.file` with `.replace("\\","/")` to match `hits` (POSIX). S4: tighten `detect_overfit` case (a) so a shell `\|\|`/pipe breadcrumb line is not misread as a regex-alternation matcher append. |
| `user/scripts/test_harness_gate.py` | yes (39 `def test_` fns) | in-file fixture harness (same-shape `Hk`-double / hunk fixtures the SPEC Reproduction Steps use) | modify | Add regression fixtures for all four FP shapes (S1/S2/S3 off-manifest scoping; S4 shell-breadcrumb overfit precision) mirroring the SPEC's deterministic repro asserts. |

**Contradiction check:** none. Both fix sites lie on the traced serving path (`run_checker`'s unfiltered `hunks` for S1/S2/S3; `_ALTERNATION_ADD_RE`/case-(a) for S4), exactly as SPEC Theory 1 (Confirmed, `traced`) and Theory 2 (Confirmed, `traced`) record. No SPEC premise is falsified.

## Validated Assumptions

- **Detector input scope is code-provable** — `run_checker` (:373-407) passes the full `parse_diff(diff_text)` hunk list to `detect_overfit`/`detect_gate_weakening` with no `h.file ∈ hits` filter; `hits` (:375) is used only for the `in_scope` early-return (:376-382). Read directly from source, not runtime-coupled. (Skip-gate rationale: this bug has no user-facing runtime surface — a pure-function detector over diff text — so the Runtime Assumption Validation gate is satisfied by source-provable classification.)
- **`scope_hits` is the manifest-membership SSOT** — returns POSIX-normalized changed paths matching ≥1 `control_surfaces ∪ gate_own` glob (`load_manifest` :134, `_glob_match` :154). Filtering detector input to this set needs no new "is this code" heuristic and keeps `docs/gate/control-surfaces.json` the single owner of what the gate inspects (SPEC Open Question "Scoping mechanism" — recommended manifest membership).

## SPEC-example capability audit

The SPEC's Reproduction Steps consume only `harness-gate.py`'s own public functions loaded via `importlib.util.spec_from_file_location` — `hg.detect_gate_weakening([h])`, `hg.detect_overfit([h])` — plus a minimal `_Hunk`-shaped double (`file`/`added`/`removed`/`added_ctx`). All verified present at the cited lines (`detect_overfit` :230, `detect_gate_weakening` :255, `_Hunk` :178). No rejected/`unimplemented`/`todo` capability consumed. `how-confirmed: read` (source lines above). MCP tool-existence audit: no `mcp-tool-catalog.md` configured for claude-config → no-op.

---

### Phase 1: Scope detector input to manifest control-surface hunks (S1 / S2 / S3)

**Scope:** Fix the primary root cause — `run_checker` runs the structural detectors over EVERY changed file's hunks once a diff is in scope. Filter the parsed hunks to only those whose file is a manifest control-surface hit (`h.file ∈ scope_hits`) BEFORE invoking `detect_overfit` / `detect_gate_weakening`, so off-manifest generated docs (`LAZY_QUEUE.md`), per-item `PHASES.md` prose, and unrelated `docs/{features,bugs}/<slug>/SPEC.md` files swept into a range are never inspected.

**Deliverables:**
- [x] In `run_checker` (`user/scripts/harness-gate.py:373-407`), after `hunks = parse_diff(diff_text)` (:383), filter to in-scope hunks: `hits_set = {h.replace("\\", "/") for h in hits}`; `hunks = [h for h in hunks if h.file.replace("\\", "/") in hits_set]`. Pass the filtered list to `detect_overfit` / `detect_gate_weakening` (:384-385). `detect_tautology` is unaffected (reads the SPEC dir, not hunks).
- [x] Preserve the `in_scope: True` verdict shape — `hits` still drives `in_scope`/`scope_hit`; only the detector INPUT narrows. A diff with a real control-surface edit plus off-manifest churn stays in scope, but the detectors see only the control-surface hunks.
- [x] Tests: add regression fixtures to `user/scripts/test_harness_gate.py` for S1 (`LAZY_QUEUE.md` `## Bugs (17)`→`(16)` renumber — no `gate_weakening` hit when off-manifest), S2 (`docs/bugs/x/PHASES.md` prose mentioning `BUILD_QUEUE_BYPASS=1` — no hit off-manifest), S3 (unrelated `docs/bugs/unrelated/SPEC.md` citing another slug's `docs/bugs/<slug>` path — no `overfit` flag off-manifest). Each fixture must drive a diff where an ON-manifest file IS also changed (so `in_scope` is True) yet the off-manifest hunk produces NO finding.
- [x] Tests: a POSITIVE-control fixture proving an ON-manifest file carrying the same offending shape (e.g. a real hook `.sh` with a `*_BYPASS` line) STILL hits — the scoping fix narrows input, it does not disarm the detectors.

**Minimum Verifiable Behavior:** `python3 user/scripts/test_harness_gate.py` (the in-file harness) passes with the new S1/S2/S3 off-manifest fixtures green AND the positive-control fixture still hitting. The SPEC Reproduction Steps' S1/S2/S3 asserts, re-run through `run_checker` with an off-manifest file, now return `pass`/no-flag.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior; pure detector-function unit coverage.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/harness-gate.py` — `run_checker`: filter `hunks` to `h.file ∈ hits` before the detectors.
- `user/scripts/test_harness_gate.py` — S1/S2/S3 off-manifest regression fixtures + positive control.

**Testing Strategy:** Unit fixtures against `run_checker` (full pipeline: manifest-scope → filter → detectors) and directly against `detect_overfit`/`detect_gate_weakening` for the positive control. Deterministic — pure functions of the diff text (SPEC "Consistency: Always").

**Integration Notes for Next Phase:**
- Phase 1 resolves S1/S2/S3 (all off-manifest). It does NOT resolve S4 — the breadcrumb FP fires on an ON-manifest hook file (`user/hooks/foo.sh`), so the scoping filter still passes that hunk to `detect_overfit`. Phase 2 owns the detector-precision fix.
- The filter reuses `scope_hits`'s existing POSIX normalization (`.replace("\\","/")` at :170) — match it exactly on both sides of the membership test so a Windows-separator `h.file` compares correctly.

---

### Phase 2: Precision-tighten the overfit alternation heuristic against shell breadcrumb pipes (S4)

**Scope:** Fix the secondary root cause — `detect_overfit` case (a) (`:236`) treats any added line with `|` + a matched `_ALTERNATION_ADD_RE` + a quoted literal as a regex-alternation matcher append. A legitimate fail-open shell breadcrumb line in an ON-manifest hook (`_HOOK_*_TS="$(date +%s 2>/dev/null || echo 0)"`) satisfies this via the shell `||` and the quoted `"$( … )"`, producing a persistent (judgment-passable but trust-eroding) `overfit=flag`. Tighten case (a) so a shell `||`/pipe in real hook code is not misread as a matcher alternation, WITHOUT over-narrowing the detector's genuine coverage (a literal appended to a real regex-alternation matcher).

**Deliverables:**
- [x] Tighten `detect_overfit` case (a) (`user/scripts/harness-gate.py:236`) so a shell logical-OR / pipe (`||`, or a shell `|` in a `$( … )` command substitution / redirection context) does NOT match as a regex-alternation append. Prefer keying on the genuine tell of a regex-alternation matcher append (the added `|`-fragment sits inside a regex/matcher-literal context — an alternation between quoted alternatives), and exclude the shell-operator shapes (`||`, ` | ` pipe between commands, `2>/dev/null`, `$( … )`). Keep the change minimal and structural; do not weaken the detection of a literal genuinely appended to a `re.compile`/alternation string.
- [x] Tests: add an S4 regression fixture to `user/scripts/test_harness_gate.py` — the SPEC's `user/hooks/foo.sh` breadcrumb line `_HOOK_NOPY_TS="$(date +%s 2>/dev/null || echo 0)"` (an ON-manifest hook) now returns `detect_overfit(...)['result'] == 'pass'`.
- [x] Tests: a POSITIVE-control fixture proving a TRUE regex-alternation matcher append (a quoted literal added into an actual `|`-alternation matcher, the detector's real coverage) STILL flags — guarding against over-narrowing (SPEC Open Question FP3/S4: "Guard against over-narrowing the overfit detector").

**Minimum Verifiable Behavior:** `python3 user/scripts/test_harness_gate.py` passes with the S4 shell-breadcrumb fixture returning `pass` AND the genuine-alternation positive-control fixture still returning `flag`. The SPEC S4 repro assert now yields no flag.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior; pure detector-function unit coverage.

**Prerequisites:**
- Phase 1: the scoping filter is in place (S1/S2/S3 resolved). S4 is orthogonal (on-manifest) but both phases touch `harness-gate.py` + `test_harness_gate.py` — serialize (one writer per file).

**Files likely modified:**
- `user/scripts/harness-gate.py` — `detect_overfit` case (a) / `_ALTERNATION_ADD_RE` precision.
- `user/scripts/test_harness_gate.py` — S4 shell-breadcrumb regression fixture + genuine-alternation positive control.

**Testing Strategy:** Unit fixtures against `detect_overfit` directly (the SPEC repro shape). Positive + negative controls bound the change: the breadcrumb no longer flags; a real matcher-alternation append still flags.

**Integration Notes for Next Phase:**
- Terminal phase. After Phase 2, all four SPEC symptoms (S1–S4) are resolved and pinned by regression fixtures.
- The harness-change-gate (`_components/harness-change-gate.md`) + these regression fixtures own the over-narrowing risk called out in the SPEC's FP3/S4 Open Question — the positive-control fixture is the mechanical guard.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed, writes `FIXED.md`, and archives the bug dir once both phases' work lands and the validation tail passes. This PHASES.md never flips top-level status itself.
