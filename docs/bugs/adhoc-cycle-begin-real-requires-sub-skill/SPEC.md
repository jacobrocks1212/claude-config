# `--cycle-begin --kind real` must require/validate `--sub-skill` (write-side durable fix) — Investigation Spec

> A real cycle marker written with `sub_skill=None` (orchestrator omitted `--sub-skill`) makes the `--cycle-end` commit-budget indeterminate — the recurring unexpected-commits false-positive class. Harden the WRITE side so the marker can never be born sub_skill-less on a real cycle.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-06
**Placement:** docs/bugs/adhoc-cycle-begin-real-requires-sub-skill
**Related:** `docs/bugs/skip-mcp-test-frontmatter-unquoted-colon` (Round 3 parent — shipped the read-side guard, commit `d650926`); `docs/bugs/adhoc-derive-multi-commit-budget-from-dispatch-sites` (open, out of scope); `docs/bugs/_archive/adhoc-derive-cycle-commit-budget` (the `_MULTI_COMMIT_DISPATCH_SKILLS` SSOT that derives branch-3 budget)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug
                    (which authors PHASES.md from this concluded spec).
-->

---

## Verified Symptoms

<!-- Sourced from the ad-hoc brief + the shipped Round-3 read-side guard commit; this is a
     harness self-defect spin-off, so the "user" is the pipeline's own friction ledger. -->

1. **[VERIFIED]** A recurring `unexpected-commits` process-friction false-positive fires at `--cycle-end` on legitimately multi-commit REAL cycles (notably `/execute-plan` landing one sanctioned commit per work-unit) — confirmed by the recurrence history cited in the brief (harden Rounds 15/16/17/19 + Round 3) and by the read-side guard's own comment (`lazy_core.py:10980-10982`: "an /execute-plan cycle whose --cycle-begin recorded sub_skill=None landed 3 sanctioned per-WU commits and tripped budget=1").
2. **[VERIFIED]** The common denominator across every occurrence is a cycle marker written with `sub_skill=None` because the orchestrator omitted `--sub-skill` at `--cycle-begin` — confirmed by the shipped Round-3 fix targeting exactly that input (commit `d650926`, "make detect_cycle_bracket_friction fail-open on a sub_skill-less real cycle").
3. **[REPORTED]** Round 3 shipped a READ-side fail-open guard (disable signal (b) when `sub_skill` is falsy) that stops the false-positive but at the cost of losing genuine-runaway detection on any real cycle whose marker is sub_skill-less. The durable fix is write-side (this item).

## Reproduction Steps

<!-- Followable recipe against the live state scripts. -->

1. Ensure a live run marker exists (`python3 user/scripts/lazy-state.py --run-start --repo-root <repo>` with `LAZY_ORCHESTRATOR=1`).
2. Begin a cycle WITHOUT a sub-skill:
   `LAZY_ORCHESTRATOR=1 python3 user/scripts/lazy-state.py --cycle-begin --feature-id feat-x --nonce deadbeef --kind real --repo-root <repo>`
3. Observe stdout: the emitted marker JSON carries `"sub_skill": null` — the command **succeeds (exit 0)** even though it is a `--kind real` dispatch with no dispatch identity.

**Expected:** `--cycle-begin --kind real` refuses (non-zero exit, corrective stderr) when `--sub-skill` is missing, so a real cycle marker can never be born with `sub_skill=None`; `--kind meta` still accepts an absent `--sub-skill` (meta cycles legitimately carry none and are exempt from signal (b)).
**Actual:** The handler validates only `--feature-id`/`--bug-id` and `--nonce`; `--sub-skill` is unvalidated, so a real cycle silently records `sub_skill=None`.
**Consistency:** Always — the missing validation is unconditional in both state scripts.

## Evidence Collected

### Source Code

**Serving path traced surface → source (each hop `file:line`):**

1. **Argument surface — `--sub-skill` is optional, default `None`.**
   `lazy-state.py:10665` (`parser.add_argument("--sub-skill", default=None, …)`), mirror `bug-state.py:6454`.
2. **`--cycle-begin` handler validates only id + nonce (the defect site).**
   `lazy-state.py:11012-11015`:
   ```python
   if args.cycle_begin:
       lazy_core.refuse_cycle_marker_mutation_if_subagent("--cycle-begin")
       if not args.feature_id or not args.nonce:
           _die("--cycle-begin requires --feature-id and --nonce")
   ```
   Mirror `bug-state.py:6629-6632` (`_die("--cycle-begin requires --bug-id and --nonce")`). Neither checks `args.sub_skill`, and neither branches on `args.kind`.
3. **Marker written sub_skill-less.**
   `lazy-state.py:11053-11057` passes `sub_skill=args.sub_skill` (=`None`) into `lazy_core.write_cycle_marker`; mirror `bug-state.py:6666-6668`. `write_cycle_marker` (`lazy_core.py:10413`) persists `"sub_skill": None` into the marker (`lazy_core.py:10528`).
4. **`--cycle-end` budget is indeterminate → the symptom surface.**
   `detect_cycle_bracket_friction` signal (b) (`lazy_core.py:10940-11019`) reads `sub_skill` from the marker. With a falsy `sub_skill`, the pre-Round-3 code fell to `_CYCLE_COMMIT_BUDGET_DEFAULT = 1` (`lazy_core.py:10596`) and tripped `unexpected-commits` on `commits_since > 1`. Round 3 inserted the fail-open branch at `lazy_core.py:10972-10993` that DISABLES signal (b) for a sub_skill-less real cycle.

**Fix-site-on-path confirmation:** the proposed validation lands at hop 2 (`lazy-state.py:11014` / `bug-state.py:6632`) — directly on the marker-write serving path, gating the write at hop 3 before the indeterminate read at hop 4. The fix site is ON the traced path.

### Runtime Evidence

No new runtime spike required — the runtime-coupled claim (the orchestrator omits `--sub-skill` on some real dispatches) is already evidenced by the SHIPPED Round-3 read-side guard (`d650926`), which exists solely to absorb that exact input. This investigation confirms the write-side origin in code.

### Git History

- `d650926 harden(script): make detect_cycle_bracket_friction fail-open on a sub_skill-less real cycle` — the Round-3 read-side guard (`lazy_core.py:10972-10993`). It is a fail-open workaround, not the durable fix.
- Prior rounds (15/16/17/19, per the brief) chased the same symptom via per-sub_skill budget rows and mandatory `--sub-skill` PROSE in the orchestrator skills — none mechanically enforced the contract at the write boundary.

### Related Documentation

- `user/scripts/CLAUDE.md` → "Per-sub_skill commit budget is DERIVED" + the `--cycle-begin` CLI reference: documents that the marker carries `sub_skill` and that the friction detector budgets from it, and that the orchestrator prose "MANDATES --sub-skill on every real --cycle-begin" — a prose contract with no script enforcement (the gap this bug closes).
- Root `CLAUDE.md` Coupled Skill Pairs / `lazy-parity-manifest.json`: `--cycle-begin` is a coupled-pair CLI on both state scripts; the fix and its smoke fixtures must be mirrored (parity-audited).

## Theories

### Theory 1: Missing write-side validation of `--sub-skill` on real cycles
- **Hypothesis:** Because `--cycle-begin` never validates `--sub-skill`, a real cycle marker can be born with `sub_skill=None`, which makes the `--cycle-end` commit budget indeterminate and drove the recurring `unexpected-commits` false-positive class.
- **Supporting evidence:** The full serving-path trace above; the Round-3 read-side guard that exists specifically to absorb the sub_skill-less real-cycle input; the brief's recurrence history.
- **Contradicting evidence:** None found.
- **Status:** Confirmed (traced).

## Proven Findings

- **Root cause (traced):** `--cycle-begin` in both `lazy-state.py` (11012-11015) and `bug-state.py` (6629-6632) validates only the item-id and nonce, leaving `--sub-skill` unvalidated. A `--kind real` dispatch that omits it writes a marker with `sub_skill=None`, and the `--cycle-end` friction detector cannot derive a commit budget for it.
- **Recommended fix (for `/plan-bug`):** In BOTH state scripts' `--cycle-begin` handler, after the existing id+nonce check, add: `if args.kind == "real" and not (args.sub_skill or "").strip(): _die("--cycle-begin --kind real requires --sub-skill")`. `--kind meta` remains exempt (meta cycles legitimately omit `--sub-skill` and are exempt from signal (b) — see `lazy_core.py:10962`). This is the ONLY option that satisfies the brief's stated goal ("the marker can never be written sub_skill-less" for a real cycle) — a warn-and-proceed variant would still persist the sub_skill-less marker, so a hard `_die` is the correct complete path.
  - ⚖ policy: require vs warn on missing --sub-skill → hard `_die` (only "never sub_skill-less" satisfies the brief's goal).
- **Relationship to the Round-3 read-side guard:** The write-side require is the DURABLE fix; the read-side fail-open guard (`lazy_core.py:10972-10993`) becomes pure defense-in-depth for legacy/meta/degraded markers and should be RETAINED (do not remove it — it still fail-opens correctly for `--kind meta` and legacy markers).
- **Coupled-pair + parity:** The change and its `--test` smoke fixtures are a coupled-pair edit on both scripts (`lazy_parity_audit.py --repo-root .` must stay exit 0). Existing `--cycle-begin` fixtures already pass `--sub-skill execute-plan` (e.g. `lazy-state.py:9628`, `bug-state.py:5230`), so they remain green; new fixtures must assert (a) a real cycle without `--sub-skill` exits non-zero with zero marker mutation, and (b) a meta cycle without `--sub-skill` still succeeds.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Feature state-machine `--cycle-begin` handler | `user/scripts/lazy-state.py` (~11012-11015) | Add `--kind real` requires `--sub-skill` validation |
| Bug state-machine `--cycle-begin` handler | `user/scripts/bug-state.py` (~6629-6632) | Coupled-pair mirror of the same validation |
| Smoke fixtures | in-file `--test` harnesses of both scripts | New fixtures: real-without-sub-skill refuses; meta-without-sub-skill succeeds |
| Read-side guard (unchanged) | `user/scripts/lazy_core.py` (10972-10993) | RETAINED as defense-in-depth; not modified |
| Docs | `user/scripts/CLAUDE.md` `--cycle-begin` reference | Promote the prose "MANDATES --sub-skill" to a documented hard enforcement |

## Open Questions

- None blocking. Scope is bounded by the brief: the write-side `--sub-skill` contract on both state scripts + smoke fixtures. Explicitly OUT of scope: budget thresholds, the `_MULTI_COMMIT_DISPATCH_SKILLS` registry class (`adhoc-derive-multi-commit-budget-from-dispatch-sites`), and removal of the already-shipped read-side guard.
