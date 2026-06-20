# Stub-spec route loops at Step 4.5 until the queue.json `stub` flag is cleared — `/spec` Phase-1 batch contract never clears it — Investigation Spec

> When a feature is marked a stub via `queue.json` `"stub": true`, `lazy-state.py` routes it to `Step 4.5: stub-spec detected` and dispatches `/spec` to shape the baseline. But `/spec`'s Phase-1 `--batch` contract only drafts/locks the baseline SPEC — it does not clear the `queue.json` `stub` flag. So a stub-shaping cycle that drafts the baseline, commits, and returns leaves `is_stub_spec()` still true (it keys on `queue_entry.get("stub") is True`), and the next probe re-routes to Step 4.5 again. The loop is *commit-masked*: HEAD advances each cycle (`repeat_count` resets to 1) while routing never leaves the step (`step_repeat_count` climbs) — the exact "productive-looking oscillation" signature the step counter exists to catch.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-20
**Placement:** docs/bugs/stub-spec-route-loops-until-queue-stub-cleared
**Source:** First-hand reproduction in a live `/lazy-batch 25` run, claude-config self-edit, 2026-06-20 (feature `long-build-and-runtime-ownership`)
**Related:** `user/scripts/lazy-state.py` (`is_stub_spec` L823; queue-stub cross-check L859; Step 4.5 routing L1979–1983); `user/skills/spec/SKILL.md` ("Phase 1 under `--batch`" — drafts/locks baseline, no queue-stub clear); `user/skills/_components/lazy-batch-prompts/...` (stub→research-pending handoff); `user/skills/lazy-batch/SKILL.md` Step 1a (`step_repeat_count` oscillation tripwire is the only safety net)

---

## Verified Symptoms

1. **[VERIFIED — observed live this session]** A stub feature whose `queue.json` entry carries `"stub": true` re-routes to `Step 4.5: stub-spec detected` on consecutive cycles even after a `/spec` cycle drafted and committed a full baseline SPEC. Run: `/lazy-batch 25`, feature `long-build-and-runtime-ownership`, 2026-06-20. Cycle 1 ran `/spec` Phase 1, overwrote the stub with a structured baseline, committed `aa74af6` — and the very next probe returned `Step 4.5: stub-spec detected` again, `step_repeat_count: 2`, `repeat_count: 1`.
2. **[VERIFIED — root marker isolated]** The active stub marker was **`queue.json` `"stub": true`**, not a SPEC trailer. After cycle 1 the SPEC's `**Status:**` read `Draft (research stub — baseline drafted, pending Gemini)`, which does **not** match the exact legacy substring `**Status:** Draft (research stub)` (no closing paren) and is not the `> Draft (pre-Gemini)` form — so `is_stub_spec` fired solely via the `queue_entry.get("stub") is True` branch (`lazy-state.py:859`).
3. **[VERIFIED — loop broke only on explicit clear]** The route advanced to `Step 5: generate research prompt` only after a subsequent `/spec` cycle explicitly set `queue.json` `"stub": false` (and flipped the SPEC `**Status:**` to plain `Draft`), committed `b1fdb15`. `step_repeat_count` then reset to 1 and the pipeline proceeded normally to `RESEARCH_PROMPT.md` generation and the `needs-research` halt.
4. **[VERIFIED — containment was vigilance, not the contract]** The loop was caught at `step_repeat_count: 2` by the orchestrator manually inspecting `is_stub_spec` inputs, *below* the `>= 3` oscillation tripwire. Nothing in the `/spec` Phase-1 batch contract guaranteed the clear; absent operator/orchestrator vigilance the cycle would have continued consuming budget until the tripwire fired (and even then the tripwire only *halts* — it does not clear the flag).

## Reproduction Steps

1. Have a `docs/features/queue.json` entry with `"stub": true` for a feature with an auto-generated / pre-Gemini stub `SPEC.md`.
2. Run `/lazy-batch <N>` (or `/lazy`). The probe returns `Step 4.5: stub-spec detected` → dispatches `/spec --batch`.
3. The `/spec` cycle drafts/locks the baseline SPEC and commits — but does not touch `queue.json`.
4. Re-probe.

**Expected:** the stub→research-pending transition completes in one stub-shaping pass — the next probe advances to `Step 5: generate research prompt` (or `needs-research`).
**Actual:** the next probe returns `Step 4.5: stub-spec detected` again (`is_stub_spec` still true via the queue flag); the route loops until something explicitly clears `queue.json` `"stub"`.
**Consistency:** deterministic whenever the stub marker is the `queue.json` flag and the `/spec` cycle does not clear it.

## Evidence Collected (from this session's run)

- **Probe 1 (pre-cycle-1):** `current_step: "Step 4.5: stub-spec detected"`, `sub_skill: spec`.
- **Cycle 1 return:** baseline SPEC drafted, committed `aa74af6`; queue untouched; SPEC `**Status:**` left as `Draft (research stub — baseline drafted, pending Gemini)`.
- **Probe 2 (post-cycle-1):** `current_step: "Step 4.5: stub-spec detected"` (unchanged), `step_repeat_count: 2`, `repeat_count: 1` (HEAD advanced — commit-masked).
- **Manual diagnosis:** `is_stub_spec(spec_text, queue_entry)` — legacy SPEC-status substring did NOT match (open paren only); `queue_entry.get("stub") is True` DID → Step 4.5 fired (`lazy-state.py:859`, `:1979–1983`).
- **Cycle 3 return:** explicitly set `queue.json` `"stub": false` + SPEC `**Status:** Draft`, committed `b1fdb15`.
- **Probe 3 (post-cycle-3):** `current_step: "Step 5: generate research prompt"`, `step_repeat_count: 1` — loop cleared.

## Why this is friction

The stub→research-pending state transition has a clear/owner gap. `is_stub_spec` is a multi-marker OR (legacy SPEC status, `> Draft (pre-Gemini)` trailer, **or** `queue.json` `"stub": true`), and `/ingest-research` is documented as the thing that clears both the SPEC trailer and the queue flag — but that runs only *after* research arrives. Between stub-shaping and research arrival, **nobody is contractually responsible for clearing the queue flag**, yet `is_stub_spec` keeps it true, so the route cannot leave Step 4.5 to reach the `needs-research` gate. The only backstop is the `step_repeat_count >= 3` tripwire, which *halts* the run rather than *advancing* it — so even the safety net converts the bug into a stall, not a fix. Each looped cycle is a wasted `/spec` Opus dispatch.

## Seam Analysis

The stub→research-pending transition crosses three seams. The clear of `queue.json "stub"` has an **owner gap** between them.

| Seam | Owner | What it does with the stub flag | Evidence |
|------|-------|----------------------------------|----------|
| S1 — `is_stub_spec(spec_text, queue_entry)` | `lazy-state.py:823`, queue branch `:859` | READS the flag (`queue_entry.get("stub") is True`); multi-marker OR with two SPEC-text markers. Keeps Step 4.5 armed as long as ANY marker is true. | `lazy-state.py:840-860` |
| S2 — Step 4.5 routing | `lazy-state.py:1980-1990` | Dispatches `/spec` (stub-shaping) when `is_stub_spec` is true. Routes to Step 5 (research-prompt gen, `:2072-2081`) only once `is_stub_spec` is false. | `lazy-state.py:1980`, `:2072` |
| S3 — `/spec` Phase-1 `--batch` | `user/skills/spec/SKILL.md:57-69` | Drafts/locks the baseline SPEC, commits. Does **NOT** touch `queue.json`. No step in the Phase-1 batch contract clears the flag. | `spec/SKILL.md:57-69` |
| S4 — `/ingest-research` Step 3d | `user/skills/ingest-research/SKILL.md:186-188` | The **only** code that clears the queue stub flag (removes the `"stub"` key). Runs **after research arrives** — far downstream of S3. | `ingest-research/SKILL.md:3, 186-188` |

The flag is **set** somewhere upstream (stub-seeding) and **read** by S1, but the only **clear** (S4) is gated on research *already present*. Between baseline-shaping (S3) and research arrival (S4), nothing is contractually responsible for clearing the queue flag, so S1 stays true and S2 cannot advance.

## Theories

### Theory 1: Missing clear-owner in the stub→research-pending transition (ROOT CAUSE)
- **Hypothesis:** The stub flag is cleared only by `/ingest-research` (post-research), but `is_stub_spec` reads it from the moment the baseline is drafted. No seam between "baseline locked" and "research arrived" clears it, so Step 4.5 re-fires every cycle after the baseline is locked.
- **Supporting evidence:** Live repro (Verified Symptoms 1-3): cycle 1 locked the baseline + committed `aa74af6`, queue untouched; probe 2 returned Step 4.5 unchanged; loop broke only when a later cycle explicitly set `"stub": false` + committed `b1fdb15`. `/ingest-research`'s SKILL.md is the sole owner of the clear (S4) and runs post-research. `/spec` Phase-1 `--batch` contract (`spec/SKILL.md:57-69`) has no queue step.
- **Contradicting evidence:** None.
- **Status:** **Confirmed.**

### Theory 2: `is_stub_spec` conflates two distinct states
- **Hypothesis:** The `queue.json "stub": true` flag means "needs baseline shaping," but after Step-4.5 `/spec` locks the baseline the real state is "baseline locked, awaiting research." A single boolean cannot distinguish them, so the flag necessarily over-fires.
- **Supporting evidence:** The two SPEC-text stub markers (`> Draft (pre-Gemini)`, legacy `Draft (research stub)`) live *in the SPEC* and are naturally overwritten when `/spec` rewrites the SPEC body — so they self-clear on baseline lock. Only the `queue.json` flag, which lives *outside* the SPEC, survives the rewrite. This is why symptom 2 isolated the queue flag as the sole surviving marker.
- **Contradicting evidence:** This is a *framing* of Theory 1, not an independent root cause — a distinct queue state is one possible fix shape, not a separate defect. The minimal fix (clear the flag at baseline lock) resolves the loop without a new state.
- **Status:** Likely (informs fix-shape choice; subsumed by Theory 1).

### Theory 3 (ruled out as primary): the legacy SPEC-status substring brittleness
- **Hypothesis:** The loop is caused by `**Status:** Draft (research stub)` (closed-paren substring, `:840`) silently failing to match `Draft (research stub — …)`.
- **Supporting evidence:** Symptom 2 confirms the post-cycle-1 status `Draft (research stub — baseline drafted, pending Gemini)` did NOT match that substring.
- **Contradicting evidence:** Even if the SPEC-text match had fired, it too would have been cleared only when the SPEC was rewritten — it is not the *surviving* marker. The surviving marker is unambiguously the `queue.json` flag (symptom 2). The substring brittleness is a real but **separate, lower-severity** robustness gap, not the loop's cause.
- **Status:** **Ruled out as primary.** Logged as a secondary tightening (see Open Questions).

## Proven Findings

1. **Confirmed root cause (Theory 1):** the stub→research-pending transition has no clear-owner for the `queue.json "stub"` flag between baseline-lock (S3) and research-arrival (S4). `is_stub_spec` keeps reading the surviving flag, so Step 4.5 re-fires indefinitely (commit-masked: HEAD advances, route does not).
2. **The fix must be script-owned, not orchestrator-inline.** HARD CONSTRAINT 1 forbids the `/lazy-batch` orchestrator from hand-editing `queue.json`. The clear must live in `lazy-state.py` / `lazy_core` (the established pattern — `lazy_core.reorder_queue` + `_atomic_write`, `lazy_core.py:104, 130`, already mutate `queue.json` under the script's ownership via load→mutate→atomic-write).
3. **"Baseline locked" is the correct clear point** — not "after `RESEARCH_PROMPT.md` exists." The whole point of Step 4.5 is to produce the baseline; once `/spec` Phase-1 has overwritten the stub SPEC with a structured baseline, the item is in the "awaiting research" state and Step 5 (research-prompt generation) is where it should advance. Clearing at baseline-lock advances it there in one pass.
4. **The two SPEC-text markers self-clear; only the queue flag survives a SPEC rewrite** (Theory 2 evidence). Any fix that clears the queue flag at baseline-lock closes the loop for the surviving marker — the SPEC-text markers are already handled by the `/spec` rewrite.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| State machine — stub detection / Step-4.5→Step-5 boundary | `user/scripts/lazy-state.py` (`is_stub_spec` L823/L859; Step 4.5 L1980-1990; Step 5 L2072-2081) | Primary. The deterministic clear-and-advance belongs here (a script-owned step at the Step-4.5→Step-5 boundary, or a `lazy_core` clear helper invoked when the baseline is detected as locked). |
| Shared queue mutator | `user/scripts/lazy_core.py` (`_atomic_write` L104, `reorder_queue` L130 — the pattern to mirror) | A new `clear_queue_stub(repo_root, feature_id)`-style helper (load→pop `"stub"` key→atomic write), mirroring `reorder_queue`'s shape, keeps the mutation script-owned and parity-able across both state scripts. |
| `/spec` Phase-1 `--batch` contract | `user/skills/spec/SKILL.md:57-69` | Secondary / optional. If the clear is fully script-owned at the boundary, the Phase-1 contract needs no change. If the chosen fix instead makes `/spec` responsible for the clear, this contract must be amended — but per HARD CONSTRAINT 1 a script-owned clear is preferred, leaving this untouched. |
| Smoke fixtures | `lazy-state.py --test` in-file harness | A new fixture: queue `"stub": true` + a structured (non-stub-text) SPEC + no research ⇒ assert the route advances to Step 5 (research-prompt generation) and the flag is cleared, NOT a re-fire of Step 4.5. |

## How "baseline locked" is detected (fix-design note, not a pre-baked answer)

The boundary needs a deterministic "baseline is now locked" signal so the clear fires exactly once and only after `/spec` Phase-1 has done its job. Candidate signals (for `/plan-bug` / `/write-plan` to choose among): the SPEC no longer carries either SPEC-text stub marker (the `/spec` rewrite already drops them) **while** the queue flag is still set — i.e. the queue flag is the *lone surviving* marker — is the cleanest deterministic discriminator, since that state is reachable only after a baseline-shaping `/spec` cycle. This keeps the clear from firing on a true pre-baseline stub (where the SPEC-text marker is still present).

## Open Questions (secondary — do not block the fix)

- **Legacy substring brittleness (Theory 3):** tighten `**Status:** Draft (research stub)` (`:840`) so it matches `Draft (research stub — …)` variants? Low severity — the queue flag is the surviving marker, so this does not affect the loop. Worth a one-line regex tightening in the same fix or a follow-up. Not loop-causing; do not gate the primary fix on it.
- **`step_repeat_count` auto-recovery:** should commit-masked oscillation at Step 4.5 (caught at `step_repeat_count`) auto-route to the deterministic clear-and-advance rather than only halting at the `>= 3` tripwire? The primary fix (clear at baseline-lock) removes the loop entirely, making this moot for this signature — but it is a general hardening worth noting. Out of scope for this bug's fix unless trivially free.
