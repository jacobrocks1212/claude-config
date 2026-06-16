# Park mode halts on BLOCKED instead of parking it — Investigation Spec

> `--park` mode parks `NEEDS_INPUT.md` features and advances the queue, but a `BLOCKED.md` feature is still selected and returns `terminal_reason="blocked"`, forcing the orchestrator into Step 1h resolution instead of deferring it. In an (unattended) park run that is an interruption — park mode should park the blocked feature and move on.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-16
**Placement:** docs/bugs/park-mode-halts-on-blocked
**Related:** `docs/specs/lazy-pipeline-ergonomics/` (park-and-continue), `user/scripts/CLAUDE.md`, sibling harness bugs `docs/bugs/_archive/hardening-blind-to-process-friction/`, `docs/bugs/research-gate-ignores-existing-phases/`

---

## Verified Symptoms

1. **[VERIFIED]** With `--park` active, a feature carrying `BLOCKED.md` is **not** parked — the script returns `terminal_reason="blocked"` and the queue does not advance past it. — operator report; confirmed in `lazy-state.py` below.
2. **[REPORTED]** The operator expects `--park` to treat a blocked feature like a parked `NEEDS_INPUT` one: skip it into `parked[]`, continue to the next queue item, and surface it at the end-of-run flush — never interrupt the unattended loop. — operator statement.

## Reproduction Steps

1. Queue ≥2 features; the current/earlier one carries `BLOCKED.md`, a later one is workable.
2. Run `/lazy-batch <N> --park`.
3. The Step 2 selection loop skips parked `NEEDS_INPUT` features but **not** the blocked one (it is explicitly excluded from parking); the blocked feature is selected as `current` and Step 3 returns `blocked`.

**Expected:** in park mode the blocked feature is parked (`parked[]`), the queue advances to the next workable feature, and the block is deferred to the flush.
**Actual:** the script returns `terminal_reason="blocked"`; the orchestrator enters Step 1h blocked-resolution (auto-resolve or `AskUserQuestion`) — an interruption that defeats unattended park-and-continue.
**Consistency:** deterministic whenever a `BLOCKED.md` feature is reached under `--park`.

## Evidence Collected

### Source Code

**Parking lives at the Step 2 selection loop; BLOCKED detection lives at Step 3 (post-selection):**

- Step 2 park skip (`lazy-state.py:1248–1263`) parks an unresolved `NEEDS_INPUT.md` via `_PARKED.append(build_parked_entry(...))` + `continue`, **but only when the feature does NOT also have BLOCKED.md**:
  ```python
  if (
      park_needs_input
      and (spec_path / "NEEDS_INPUT.md").exists()
      and not (spec_path / "BLOCKED.md").exists()   # :1256 — BLOCKED excluded from parking
  ):
      _PARKED.append(...); continue
  ```
  Comment `:1251–1252`: "BLOCKED.md retains precedence: a feature carrying BOTH BLOCKED.md and NEEDS_INPUT.md must still halt as 'blocked', not be silently parked."
- A `BLOCKED.md`-only feature is never tested in the Step 2 loop — it falls through, is selected as `current` (`:1264–1271`), and **Step 3** (`lazy-state.py:1345–1367`) returns `terminal_reason="blocked"`.
- `user/scripts/CLAUDE.md` documents the current intent verbatim: `--park-needs-input … (BLOCKED still halts; output byte-identical without the flag)`.

**Orchestrator layer:** `lazy-batch/SKILL.md` Step 1h (`:370`) treats `blocked` as "**Not a terminal halt anymore**" — it classifies the blocker and either auto-resolves (sequencing-only) or runs `AskUserQuestion`, then continues; only operator-chosen "Halt for manual fix" stops. In an **unattended** park run, that `AskUserQuestion` is itself the interruption the operator is reporting as "halting."

**Park flag plumbing:** `lazy-batch/SKILL.md:360` — in `--park` mode the orchestrator appends `--park-needs-input` to every probe; `:64` defines `--park`. The script flag is `park_needs_input` (`lazy-state.py:1063`); `parked[]` is emitted only in park mode (`:142–146`). The parked-entry helper `lazy_core.build_parked_entry(item_id, sentinel_path)` (`lazy_core.py:463`) accepts **any** sentinel path — so it can already build an entry from `BLOCKED.md`.

### Related Documentation

`user/skills/_components/` park/flush components (`parked-flush.md`, T5 park line in `orchestrator-voice.md`) — the flush UX is currently decision-oriented (`NEEDS_INPUT`); blocked-parked items may need a distinct resolution affordance (see Open Questions).

## Theories

### Theory 1: Park is a Step-2 selection-loop concern; BLOCKED is gated one stage too late (PRIMARY)
- **Hypothesis:** Parking must happen in the queue-walk (skip + `continue`) to advance the queue. BLOCKED is only evaluated at Step 3 after `current` is fixed, and line 1256 deliberately keeps BLOCKED out of the Step 2 park branch — so a blocked feature can never be parked; it always returns the `blocked` terminal.
- **Supporting evidence:** `:1256` exclusion; Step 3 at `:1345`; CLAUDE.md "BLOCKED still halts."
- **Contradicting evidence:** none — this is the explicit current design, which the operator now wants changed for park mode.
- **Status:** Confirmed.

## Proven Findings

1. **Root-cause class: `missing-contract` / deliberate-design-now-revised.** Park-and-continue was scoped to `NEEDS_INPUT` only; `BLOCKED` was intentionally excluded. The operator is revising that scope: in park mode, a feature-local block should park and the queue should advance.
2. **The fix spans script + skill:** the script must park `BLOCKED.md` in the Step 2 loop (symmetric with `NEEDS_INPUT`), and the `--park` skill path must enable it and route blocked-parked items to the flush rather than Step 1h.

## Locked Decisions (proposed — operator to confirm at /plan-bug)

- **D1 — Park mode parks feature-local BLOCKED.** Under `--park`, a feature carrying `BLOCKED.md` is parked into `parked[]` at the Step 2 selection loop and the queue advances to the next workable feature; the block is surfaced at the end-of-run flush, not via an inline Step 1h interruption. (Operator's stated intent.)
- **D2 — Global/environment terminals still halt.** Only the *per-feature* `BLOCKED.md` (Step 3) is parked. Global terminals computed when `current is None` — `cloud-queue-exhausted`, `device-queue-exhausted`, `queue-blocked-on-research`, `queue-missing` — are unaffected and still halt (no feature can proceed; parking would be dishonest). The fix must not touch those.
- **D3 — Honest all-parked terminal.** When every remaining feature is parked (`NEEDS_INPUT` or `BLOCKED`) so `current is None` with a non-empty `_PARKED`, return a distinct terminal (e.g. `queue-exhausted-all-parked`) — **not** `all-features-complete`, which would be a false completion. (This also fixes the latent same-shaped gap for the existing NEEDS_INPUT-only park path.)
- **D4 — Flag shape (recommend a companion flag).** Add `--park-blocked`; `--park` mode passes both `--park-needs-input --park-blocked`. This keeps `--park-needs-input` byte-identical for any existing caller and avoids overloading its name. (Alternative: generalize to `--park-all` — finalize at planning.)
- **D5 — Park all blocker kinds in park mode (recommended).** Including `blocker_kind: mcp-validation` / `validation_escalation` blocks: park mode's contract is "defer everything parkable; flush at the end," so escalated blocks are deferred-and-surfaced, not resolved inline. (Confirm — the alternative is to still resolve escalation blocks inline even under park.)

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Step 2 park skip | `user/scripts/lazy-state.py:1248–1263` (the `:1256` BLOCKED exclusion), `:1273–1323` (`current is None` terminals) | Add a BLOCKED park branch symmetric with NEEDS_INPUT; add the honest all-parked terminal. |
| Park flag | `user/scripts/lazy-state.py:1063` (`park_needs_input` param), `lazy_core.build_parked_entry` (`:463`) | Add `park_blocked` param/flag; `build_parked_entry` already accepts a BLOCKED.md path (add a sentinel-kind field if the flush needs to distinguish). |
| Orchestrator | `user/skills/lazy-batch/SKILL.md` (`:360` probe-flag append, `:370` Step 1h, `:402` park notification, parked-flush component) | In `--park`, pass the blocked-park flag; ensure Step 1h does not fire for park-mode blocked features; route blocked-parked items into the flush. |
| Cloud mirror (lockstep) | `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | Mirror the park-flag + flush changes per the coupled-pair rule. |
| Tests | `user/scripts/test_lazy_core.py` (park fixture WU-1-park ~`:4718`), `lazy-state.py --test` baseline | New fixtures: BLOCKED feature under `--park-blocked` → parked + next feature dispatched; all-parked → the new honest terminal; default (no flag) byte-identical. |

## Open Questions

- Does the bug pipeline want the same change? `bug-state.py` has its own BLOCKED handling — confirm whether `--park-blocked` should mirror there (likely yes, for `/lazy-bug-batch` parity).
- Flush UX: the parked flush is `NEEDS_INPUT`-decision shaped. Does a blocked-parked item need a distinct resolution prompt (add-phase / defer / spin-off) at flush, or is "surface + let the operator re-run resolution" sufficient? (Planning decision; ties to D4's sentinel-kind field.)
- Is there a recent `--park` session where this halt was observed, to attach as runtime evidence? (Behavior is structural/deterministic from the code; a session quote would strengthen Symptom 1 from REPORTED→VERIFIED for the orchestrator-interruption half.)
