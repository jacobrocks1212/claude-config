# Stub-spec route loops at Step 4.5 until the queue.json `stub` flag is cleared — `/spec` Phase-1 batch contract never clears it — Investigation Spec (stub)

> When a feature is marked a stub via `queue.json` `"stub": true`, `lazy-state.py` routes it to `Step 4.5: stub-spec detected` and dispatches `/spec` to shape the baseline. But `/spec`'s Phase-1 `--batch` contract only drafts/locks the baseline SPEC — it does not clear the `queue.json` `stub` flag. So a stub-shaping cycle that drafts the baseline, commits, and returns leaves `is_stub_spec()` still true (it keys on `queue_entry.get("stub") is True`), and the next probe re-routes to Step 4.5 again. The loop is *commit-masked*: HEAD advances each cycle (`repeat_count` resets to 1) while routing never leaves the step (`step_repeat_count` climbs) — the exact "productive-looking oscillation" signature the step counter exists to catch.

**Status:** Investigating
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

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)

- Who should own clearing `queue.json` `"stub"` in the stub→research-pending transition — the `/spec` Phase-1 `--batch` cycle (when it locks the baseline), a deterministic `lazy-state.py` step at the Step-4.5→Step-5 boundary, or a new pseudo-skill? (Note HARD CONSTRAINT 1: the `/lazy-batch` orchestrator may not edit `queue.json` directly, so a *script-owned* clear is likely the right shape.)
- Should `/spec`'s Phase-1 `--batch` contract explicitly require clearing the stub marker when it finalizes the baseline, and is "finalize baseline" even the right cycle to clear it (vs. after `RESEARCH_PROMPT.md` exists)?
- Is the underlying defect that `is_stub_spec` conflates two distinct states — "needs baseline shaping" vs. "baseline locked, awaiting research" — that the `queue.json` flag cannot distinguish? Would a `baseline_locked` / distinct queue state remove the ambiguity?
- Should `step_repeat_count`-detected commit-masked oscillation at Step 4.5 auto-route to a deterministic recovery (clear-and-advance) rather than only halting at the tripwire?
- Why does the legacy SPEC-status substring check (`**Status:** Draft (research stub)`) silently fail to match `Draft (research stub — …)` — is that a separate brittleness worth tightening, or intended?

> **Stub — root cause NOT yet investigated.** This spec records a verified reproduction + evidence only. `/spec-bug` owns seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
