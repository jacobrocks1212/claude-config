# Meta-dispatch prompts could not be dispatched by reference; denial-ack is overpriced — Investigation Spec

> The `@@lazy-ref` by-reference mechanism originally covered only CYCLE prompts, forcing the
> orchestrator to hand-transcribe multi-KB `--emit-dispatch` META prompts byte-exactly (12
> "not script-emitted" + 4 "transcription slip" denials in one run). The by-ref half is NOW
> FIXED in current code (every `--emit-dispatch` class emits `dispatch_prompt_ref`). The
> REMAINING defect: retiring a deny-ledger entry still costs one full Opus `/harden-harness`
> dispatch per entry — even for explicit no-fix / already-fixed denials — with no cheap
> ack-only ledger operation.

**Status:** Concluded
**Priority:** P2
**Last updated:** 2026-07-11
**Related:** `docs/specs/turn-routing-enforcement/` (owns the guard, `--emit-dispatch`, the deny ledger, and "locked decision 4" — the inline-unbounded one-hardening-per-deny cadence this spec re-opens); `docs/specs/lazy-validation-readiness/` (F2a dispatch-by-reference, F2b/F2c transcription-slip decoupling, Phase 7A meta dispatch-by-reference); `docs/specs/lazy-pipeline-ergonomics/` (F1a deny-reason customization path, F1b auto-readmit); `docs/bugs/no-mid-run-observed-friction-harden-dispatch/` (owns the mid-run ad-hoc reachability slice — scoped OUT here; its fix `c46ed80` landed 2026-07-11); `docs/bugs/_archive/hardening-blind-to-process-friction/` (D-C bare-ref deny); `docs/bugs/_archive/stale-marker-arms-validate-deny-on-unrelated-dispatches/` (D2 pre-bind no-debt deny).

## Verified Symptom

Live AlgoBooth `/lazy-batch` run, session `e076ed30-8dcf-429a` (ended 2026-06-15, ~8000 transcript lines):

- **12 "dispatch prompt not script-emitted" denials + 4 "transcription slip" denials** across the run — the orchestrator repeatedly failed to reproduce multi-KB `--emit-dispatch` META prompts byte-exactly.
- The **d7 apply-resolution dispatch was denied TWICE for reflowed line-wraps**; the orchestrator resorted to writing both prompts (emitted vs about-to-dispatch) to files and diffing until "IDENTICAL — safe to dispatch" (turns ~3034–3058) — a manual reimplementation of what the nonce mechanism exists to do.
- An **83-turn meta detour** (recovery→deny→hardening→deny→hardening→recovery→drain) over an em-dash normalization difference (turns ~2086–2169).
- **Denial-ack overpricing:** each denial appended a deny-ledger entry whose ONLY in-run drain is a full Opus `/harden-harness` dispatch reaching guard-allow (FIFO ack). Many of those rounds were explicit **no-fix rounds dispatched solely to FIFO-ack ledger debt** (Rounds 1, 4, 6, 7, 9, 13; turn ~4744). One **redundant second hardening dispatch** existed only because the first round fixed the gap but did not ack the ledger entry (turns ~125–182).
- **Mid-run ad-hoc dispatch unreachability** (turns ~4647–4658): a legitimate ad-hoc dispatch for a run-blocking defect required `--run-end --operator-authorized --ack-unhardened` to kill the whole run first. — SCOPED OUT: the `trigger_kind=observed-friction` emit path (commit `c46ed80`, 2026-07-11) addresses exactly this reachability slice; see `docs/bugs/no-mid-run-observed-friction-harden-dispatch/`.

## Root Cause

**Classification: `fixed-in-part` / `missing-affordance` (the residual).** Two independent mechanisms; one is closed in current code, one is open.

### Half 1 — meta prompts not dispatchable by reference: **FIXED in current code**

At the time of the field evidence, `--emit-prompt` (cycle prompts) surfaced `cycle_prompt_ref` but `--emit-dispatch <class>` surfaced only the verbatim `dispatch_prompt` — the orchestrator had to retype it, and the guard (`user/scripts/lazy_guard.py`) hash-denies any byte drift. Current-code characterization (verified 2026-07-11):

- `register_emission()` (`user/scripts/lazy_core.py` ~12516) stores `prompt_raw` for EVERY class; the guard's F2a branch (`lazy_guard.py` ~650–693) resolves `@@lazy-ref nonce=<hex>` against **any registered class** (it even hardening-acks via `_ack_if_hardening` on the ref path) and rewrites the Agent tool input via `updatedInput`.
- The `--emit-dispatch` handler in **both** `lazy-state.py` (~12154–12189) and `bug-state.py` (~7464–7490) registers the emission and surfaces `dispatch_prompt_ref: "@@lazy-ref nonce=<hex>"` (null only under no-marker peek semantics). Landed in commit `49e8142` ("Phase 7A — … meta dispatch-by-reference", **2026-06-13** — mid-way through the evidence session, which explains the field pain).
- `user/skills/lazy-batch/SKILL.md` (~line 735) now mandates: "PREFER `dispatch_prompt_ref` at ALL `--emit-dispatch` sites … applies uniformly to every emit site."
- Transcription-slip fallout was independently de-fanged: F2b Unicode normalization + F2c slip-deny-without-ledger-debt (`f54380c`, 2026-06-13 — the em-dash class), F1b pure-trailing-suffix auto-readmit (`8e8606b`, 2026-06-13), D2 pre-bind no-debt deny (`8bc204b`, 2026-06-19).

No further fix work for this half; the regression surface to protect is "every current AND FUTURE emit path that produces a dispatchable prompt also produces a ref token" (see Fix Scope §3).

### Half 2 — ack-only denial resolution is overpriced: **OPEN**

Pinned in current code:

- Every genuine deny appends an unacked entry to `lazy-deny-ledger.jsonl` (`_deny_and_ledger`, `lazy_guard.py` ~495). `pending_hardening()` (`lazy_core.py` ~15564) counts unacked entries; the advancing probe withholds the forward route and `--run-end` refuses while any remain.
- The ONLY ack paths are: (a) `ack_oldest_deny()` (`lazy_core.py` ~16865), called exclusively from `lazy_guard._ack_if_hardening` **when a hardening-class dispatch reaches guard-allow** — i.e. one full Opus `/harden-harness` subagent (spec-bug authoring + fixes + full gates) per ledger entry, per "locked decision 4" (one-dispatch-per-deny, inline, unbounded, no dedup); and (b) `ack_all_unacked_denies()` (`lazy_core.py` ~16908), reachable only via `--run-end --ack-unhardened` (operator blanket, run-terminating).
- There is **no per-entry ack CLI**, no "no-fix ack" verdict a hardening round can leave without running gates, and **no dedup**: N denials of the same root cause book N entries requiring N full dispatches, even when round 1 fixed the cause (the turns ~125–182 redundant dispatch, and no-fix Rounds 1/4/6/7/9/13).
- The debt-INFLOW has since been reduced (F2c/F1b/D2 above + Half 1 removing the transcription class), but the unit price of retiring one entry is unchanged.

## Fix Scope (Concluded)

1. **Cheap ack-only ledger operation** — a sanctioned CLI path (e.g. `lazy-state.py --ack-deny <selector> --resolution <text>`) that retires a specific unacked entry with an audited resolution note, WITHOUT a full hardening dispatch, for the two cheap cases: (a) the entry's root cause was already fixed by an earlier round this run (the redundant-second-dispatch case), (b) an explicit, recorded no-fix classification. Guard-rail: the op must be audited in the ledger (who/why/when) so `/lazy-batch-retro` can grade abuse; it must NOT be reachable from a cycle subagent (`refuse_if_cycle_active`).
2. **Same-cause dedup at deny time or ack time** — collapse repeat denials with an identical `denied_sha12` (or identical `reason_head` + item) into one unit of debt, so an oscillating deny does not multiply full hardening rounds.
3. **Ref-token contract for future emit paths** — a `test_lazy_core.py` invariant asserting every class in `DISPATCH_CLASSES` round-trips through register→`dispatch_prompt_ref`→guard-resolve, so a future emit path cannot regress to transcription-only (Half 1 stays closed).
4. **Coupled-pair mirroring** (`bug-state.py` gets the same ack CLI) + SKILL prose for when the cheap ack is sanctioned vs when a full hardening round remains required (a NOVEL gap always gets the full round — the cheap ack is for duplicate/no-fix/already-fixed entries only).

## Decisions

- **D1 — Locked decision 4 conflict (NEEDS OPERATOR):** turn-routing-enforcement's locked decision 4 mandates "one hardening dispatch per deny — inline, unbounded, no dedup". Fix Scope §1/§2 deliberately relax it for the duplicate/no-fix/already-fixed classes. This is a change to a LOCKED decision and needs explicit operator sign-off before `/plan-bug`.
- **D2 — Ack selector shape (fix-planning):** FIFO-oldest vs `denied_sha12`-addressed vs interactive listing. Mechanical-internal; resolve at `/plan-bug`.
- **D3 — Scope boundary (RESOLVED):** mid-run ad-hoc hardening reachability is owned by `docs/bugs/no-mid-run-observed-friction-harden-dispatch/` (fix landed `c46ed80`); this spec does not touch trigger kinds or emit classes.
