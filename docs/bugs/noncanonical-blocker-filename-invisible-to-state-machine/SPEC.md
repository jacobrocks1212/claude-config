# Subagent-written non-canonical blocker filenames are invisible to the state machine → infinite loop risk — Investigation Spec

> In a real `/lazy-batch` run, a cycle-subagent wrote its blocker file under a descriptive, date-suffixed name instead of the canonical `BLOCKED.md`. Because `lazy-state.py` keys halt detection on the exact filename `BLOCKED.md`, the halt was invisible and the state machine re-routed straight back to the same wall — an infinite-loop trigger that was only caught by chance.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-06-19
**Placement:** docs/bugs/noncanonical-blocker-filename-invisible-to-state-machine
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/lazy-state.py` Step 3 (halt detection keys on literal `BLOCKED.md`, line 1504-1529); `user/scripts/bug-state.py` Step 3 (mirror, line 835-859); `user/scripts/lazy_core.py` (shared sentinel readers — natural home for the detector); `user/skills/_components/sentinel-frontmatter.md` (canonical-name contract, prose-only); `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` Hard contract #1 (prose canonical-name instruction, line 323/350).

<!-- Status lifecycle: Concluded — root cause proven, fix scope understood. bug-state.py routes to /plan-bug. -->

---

## Verified Symptoms

1. **[OBSERVED in logs]** A cycle-subagent wrote a date-suffixed blocker name (`BLOCKED_2026-06-09-track-source-silent.md`) instead of `BLOCKED.md`; the halt went undetected and the state machine re-routed back to `/mcp-test` — session `8ae22371` @ ~line 134: "lazy-state doesn't see the halt and re-routes to mcp-test — which would loop on the same silent-source wall."
2. **[VERIFIED by code inspection]** `lazy-state.py` Step 3 (`blocked_file = spec_path / "BLOCKED.md"; if blocked_file.exists()`) keys halt detection on the EXACT literal filename. Any other name in the same directory is invisible — confirmed at `lazy-state.py:1504-1505` and the mirror at `bug-state.py:835-836`.
3. **[VERIFIED by code inspection]** No mechanical guard exists at write time or read time. The canonical-name expectation lives ONLY in prose (`cycle-base-prompt.md` Hard contract #1; `sentinel-frontmatter.md`). A subagent that ignores or paraphrases the prose produces a file the state scripts never look at.

## Reproduction Steps

1. In a feature/bug dir, place a blocker file under any name other than `BLOCKED.md` (e.g. `BLOCKED_2026-06-09-foo.md`, `blocked.md`, `BLOCKED-NOTES.md`).
2. Run `python3 lazy-state.py --repo-root <repo>` (or `bug-state.py`).
3. **Observed:** Step 3 does not fire (the literal `BLOCKED.md` is absent). The state machine falls through to whatever step the prior state implies (e.g. re-dispatch `/mcp-test`), routing the cycle straight back into the wall the subagent tried to halt on.

**Expected:** The pipeline detects that a halt was *intended* (a `BLOCKED*`-shaped file is present) and either (a) treats it as the canonical halt, or (b) surfaces a distinct "malformed/mis-named blocker" terminal so a human reconciles — never silently re-routes into a loop.
**Actual:** The mis-named file is invisible; the machine re-routes into the same wall → infinite-loop risk. Caught in the observed run only by chance (the orchestrator happened to read the directory).
**Consistency:** Deterministic — reproduces whenever a blocker file is written under any non-canonical name.

## Evidence Collected

### Source Code
- `lazy-state.py:1504-1529` — Step 3 BLOCKED detection: `blocked_file = spec_path / "BLOCKED.md"; if blocked_file.exists():`. Literal-filename match; no glob, no variant tolerance, no "stray blocker-shaped file" detection.
- `bug-state.py:835-859` — exact mirror in the bug pipeline. Same literal match, same blind spot.
- `lazy-state.py:1549-1552` — the only place the directory is scanned for "other files" is the no-SPEC fall-through, which explicitly *excludes* `BLOCKED.md`/`NEEDS_INPUT.md` and is unrelated to halt detection. Nothing inventories the dir for blocker-shaped strays.
- `lazy_core.py` — owns the shared sentinel readers (`parse_sentinel`, etc.) imported by both state machines. It has NO helper that detects mis-named sentinels. Grep for `BLOCKED_`/`startswith`/`noncanonical` returns no detector — confirmed absent.

### Related Documentation
- `cycle-base-prompt.md:323-327` and `:350-354` — Hard contract #1 "CANONICAL SENTINEL FILENAMES" already warns subagents in BOTH the workstation and cloud variants: "a mis-named sentinel is invisible to the state scripts and silently loops the pipeline." This is the prose mitigation that the observed run proves is insufficient — prose does not bind a subagent mechanically.
- `sentinel-frontmatter.md` — canonical schema; lists `BLOCKED.md` → `kind: blocked` but provides no write-time validation hook.

### Git History
- The dispatch prompts already mirror the canonical-name warning into all `/lazy*` wrappers (recent `probe-full-read-before-dispatch` commits hardened a *different* prose clause across the same six wrappers), confirming the pattern of prose-contract drift the subagents do not reliably honor.

## Theories

### Theory 1: Literal-filename halt detection with no fallback (CONFIRMED)
- **Hypothesis:** Step 3 keys on the exact string `BLOCKED.md`; a non-canonical name bypasses it, and because nothing else inventories the directory for blocker-shaped strays, the halt is invisible and the machine re-routes into the same wall.
- **Supporting evidence:** `lazy-state.py:1505` / `bug-state.py:836` literal match; session `8ae22371` observed re-route; no detector in `lazy_core.py`.
- **Contradicting evidence:** None.
- **Status:** Confirmed.

### Theory 2: The canonical-name contract is prose-only, so it depends on subagent compliance (CONFIRMED)
- **Hypothesis:** The only enforcement of the filename contract is the prose Hard-contract #1 in the cycle prompt + `sentinel-frontmatter.md`. There is no write-time gate (hook) and no read-time tolerance, so a single non-compliant subagent silently breaks the invariant.
- **Supporting evidence:** `cycle-base-prompt.md:323` prose warning already present yet the observed run still mis-named the file; no `BLOCKED_*` glob anywhere; no PreToolUse hook validates sentinel filenames at Write time.
- **Contradicting evidence:** None.
- **Status:** Confirmed.

## Proven Findings

The infinite-loop risk is real and mechanically reproducible. Root cause = **literal-filename halt detection with no detector for blocker-shaped strays**, combined with a **prose-only filename contract** that a non-compliant subagent silently violates. The fix must add a *mechanical* backstop that does not depend on subagent compliance.

### Recommended Fix Scope

A read-time **stray-blocker detector** in the shared layer, so both pipelines inherit it from one writer (mirrors how every other shared invariant lives in `lazy_core.py`):

1. **Add a shared helper** to `lazy_core.py` (e.g. `detect_noncanonical_blocker(spec_dir) -> Optional[Path]`) that scans the item directory for blocker-shaped strays — a filename matching `BLOCKED*.{md}` (case-insensitive) that is NOT the canonical `BLOCKED.md` and NOT an already-neutralized `BLOCKED_RESOLVED_<date>.md` (the existing `--neutralize-sentinel` audit-trail name, which MUST be excluded so resolved blockers don't re-halt). Returns the first offending path, or `None`.
2. **Wire it into Step 3 of BOTH state machines**, immediately adjacent to the canonical `BLOCKED.md` check (`lazy-state.py:1504`, `bug-state.py:835`). When the canonical file is absent but a stray is present, return a **distinct terminal** (proposed `terminal_reason="blocked-misnamed"` / `current_step="Step 3: mis-named blocker"`) whose `notify_message` names the offending file and instructs the human to rename it to `BLOCKED.md` (or neutralize it). A distinct terminal — rather than silently treating the stray AS the canonical halt — is the safer default: it surfaces the contract violation for repair instead of masking it, and it cannot be confused with an unrelated `BLOCKED_*` artifact.
3. **Park-mode parity:** under `--park-blocked`, a detected stray parks the same way a canonical `BLOCKED.md` does (so the queue advances), keeping the two flags' semantics aligned.
4. **Smoke-test fixtures** in both in-file `--test` harnesses: (a) a stray `BLOCKED_<date>-foo.md` with no canonical file → `blocked-misnamed` terminal; (b) a `BLOCKED_RESOLVED_<date>.md` present alone → does NOT halt (excluded); (c) both canonical `BLOCKED.md` AND a stray present → canonical precedence (no false distinct terminal). Re-baseline both byte-pinned `--test` baselines via the `_normalize_smoke_output` helper.

**Open decision deferred to `/plan-bug`:** whether to ALSO add a PreToolUse Write hook that rejects a mis-named sentinel at write time (defense-in-depth, prevents the stray from ever landing) in addition to the read-time detector. The read-time detector alone closes the loop risk; the write-time hook is a stronger but larger second layer. Both converge on the same end-state (mis-named blockers never silently loop), so this is a sizing/completeness call for the planning cycle, not a product-behavior fork.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Feature state machine | `user/scripts/lazy-state.py` (Step 3, ~line 1504) | Add stray-blocker check + distinct terminal |
| Bug state machine | `user/scripts/bug-state.py` (Step 3, ~line 835) | Mirror the same check |
| Shared layer | `user/scripts/lazy_core.py` | New `detect_noncanonical_blocker` helper (single writer) |
| Smoke tests | in-file `--test` harnesses + `tests/baselines/*.txt` | New fixtures; re-baseline |
| Schema doc (optional) | `user/skills/_components/sentinel-frontmatter.md` | Note the read-time detector + the `BLOCKED_RESOLVED_` exclusion |

## Open Questions

- (Deferred to `/plan-bug`, see Recommended Fix Scope) Add a PreToolUse Write hook for write-time rejection as a second layer, or rely on the read-time detector alone?
- Should the detector also cover mis-named `NEEDS_INPUT*` strays (same blind-spot class), or scope this bug strictly to `BLOCKED`? (Leaning: scope to `BLOCKED` here; file a follow-up for `NEEDS_INPUT` if the class is confirmed in logs — avoids scope creep on a P1 loop fix.)
