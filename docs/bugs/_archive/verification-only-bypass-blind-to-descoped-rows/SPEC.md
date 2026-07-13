# Step-7 verification-only bypass blind to descoped (struck-through DROPPED) PHASES rows — Investigation Spec

> `remaining_unchecked_are_verification_only()` exempts three unchecked-row classes
> (per-row/header `<!-- verification-only -->` marker, the legacy `_VERIFICATION_SECTION_RE`
> header shim, and Superseded-phase rows) and returns `False` otherwise. A deliberately-DROPPED
> deliverable authored as a struck-through checklist row (`- [ ] ~~<text>~~ **DROPPED** (...)`)
> is none of those, so a fully-implemented item whose SOLE remaining unchecked box is that
> descope note loops `write-plan` forever.

**Status:** Fixed
**Priority:** P2
**Last updated:** 2026-07-12
**Related:** `docs/specs/turn-routing-enforcement/` (owns the hardening stage + the Step-7 bypass); hardening-log Rounds 24 (`d8d02ef` reachability-smoke) / 25 (`f2b1552` seam-audit) + the 2026-07 recording-panel round — the same "Step-7 bypass returns `False` on a not-to-be-done row it does not recognize" class, previously hit through `_VERIFICATION_SECTION_RE` header phrasings; `user/scripts/lazy_core.py:_VERIFICATION_ONLY_MARKER` (the canonical structural-marker precedent this bug's generalization follows).

## Verified Symptom

Live instance, this run (claude-config `/lazy-bug-batch`, bug `live-settings-split-brain-disarms-enforcement-plane`, 2026-07-12): all 5 PHASES phases `**Status:** Complete`, all 3 implementation plan parts `status: Complete`, SPEC `**Status:** Concluded` (correct for pre-`__mark_fixed__`). The ONLY remaining unchecked box is `PHASES.md` line 128:

```
- [ ] ~~`setup.py` gains the parallel live hook/symlink check~~ **DROPPED** (decision 2, `NEEDS_INPUT.md` resolution, 2026-07-12): ...scope note only — no code deliverable here.
```

Because every implementation plan part is `Complete`, `find_implementation_plans` filters them out (`plans == []`), and the Step-7 verification bypass is gated on `remaining_unchecked_are_verification_only(phases_text)`. That helper returns `False` for the struck-through DROPPED row (it is not a marker row, not under a `_VERIFICATION_SECTION_RE` header, not in a Superseded phase), so the `elif not plans` branch dispatches `write-plan` on an already-done bug — a no-progress loop whose `repeat_count` / `step_repeat` climb toward a false `LOOP DETECTED` / max-cycles halt.

## Root Cause

**Classification: `script-defect`.** `user/scripts/lazy_core.py::remaining_unchecked_are_verification_only` (def ~line 2237). Its exempt classes are enumerated at the `- [ ]` row branch (~line 2355): per-row / header `_VERIFICATION_ONLY_MARKER`, the legacy `_VERIFICATION_SECTION_RE` header shim, and `in_superseded_phase` rows (`saw_superseded_unchecked`). A DELIBERATELY-DROPPED deliverable — struck through with `~~...~~` AND tagged `**DROPPED**` — is unambiguously not-to-be-done, exactly like a Superseded-phase row, but matches none of those classes, so the row falls through to the `return False` implementation-row path. Both pipelines inherit the defect (shared `lazy_core`; the bypass is gated on this helper at `bug-state.py` ~:1452 and its `lazy-state.py` mirror).

This is the SAME root-cause class the hardening log has repeatedly hit on this exact symbol (Round 24 reachability-smoke, Round 25 seam-audit, the recording-panel round) — the Step-7 bypass returning `False` on a row that is genuinely not remaining implementation work. Prior instances were verification rows reached through header phrasings; this instance is a descope-in-place row.

## Fix Scope (Concluded)

**Instance fix (this round, mechanical):** treat an unchecked row that is BOTH markdown-struck-through (`~~...~~`) AND carries an explicit descope marker (`**DROPPED**` / `**DESCOPED**` / `**WON'T-FIX**`, case-insensitive) as exempt — count it toward the all-remaining-exempt → `True` return like a Superseded-phase row. Conservative by construction: a plain unchecked row still returns `False`, and a struck row WITHOUT a descope marker still returns `False` (never over-exempt genuine work). Shared helper in `lazy_core.py`, so both pipelines inherit it. Regression fixtures in `test_lazy_core.py`: struck DROPPED note → `True`; plain unchecked → `False`; struck-without-marker → `False`. The in-flight bug's `PHASES.md` is NOT touched (scope containment) — the guard fix resolves the instance via routing.

**Generalization (spun off, not this round):** the descope-marker vocabulary is a keyword set (over-fit signal 1) on a symbol whose "not-to-be-done row unrecognized" class has recurred (signal 2). The durable fix mirrors the `<!-- verification-only -->` precedent: producers emit a CANONICAL STRUCTURAL descope marker (e.g. `<!-- descoped -->`) and the free-text `~~...~~ **DROPPED**` form becomes a deprecation shim (parallel to `_VERIFICATION_SECTION_RE`). Front-enqueued as its own `/spec-bug` item; see the hardening-log round's `Over-fit spin-off` line.

## Decisions

- **D1 — Both conditions required (conservatism):** strikethrough alone does not exempt (a struck row may be mere reformatting); the descope marker alone does not exempt (must be a struck-out deliverable). Requiring BOTH avoids over-exempting genuine work.
- **D2 — Descope-marker vocabulary this round:** `DROPPED` / `DESCOPED` / `WON'T-FIX` (case-insensitive), matching the proposed fix. Broader vocabulary + a canonical structural marker are deferred to the spun-off generalization, not widened speculatively here.
- **D3 — Completion-time gate untouched:** the fix is scoped to the mid-feature Step-7 bypass (`remaining_unchecked_are_verification_only`). `_phase_completion_plan` / `classify_blocking_unchecked_rows` completion-time strictness is deliberately NOT relaxed (the live instance is pre-`__mark_fixed__` and loops at routing, never reaching completion).

## Resolution (2026-07-12 — mechanical fix shipped)

Instance fix landed via `/harden-harness` (observed-friction trigger), hardening-log Round 30 (`docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`). `_row_is_descoped_in_place` + `_DESCOPE_STRIKETHROUGH_RE`/`_DESCOPE_MARKER_RE` added to shared `lazy_core.py` and wired into `remaining_unchecked_are_verification_only` (new `saw_descoped_unchecked` flag). Spec committed first at `0628422` (Step 2.5); fix + 3 regression tests at `6012c72`. Gates green (test_lazy_core +3/0-fail, test_hooks 153/153, lint OK, both state-script `--test` OK, parity exit 0). The over-fit generalization (canonical structural descope marker) is front-enqueued as `descoped-row-recognition-needs-canonical-marker` (deferred to the orchestrator; containment-refused in-flight) — see the Round 30 `Over-fit spin-off` line.
