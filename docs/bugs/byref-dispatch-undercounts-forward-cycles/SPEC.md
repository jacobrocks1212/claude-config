# By-reference dispatch undercounts forward_cycles → max-cycles cap cannot self-fire — Investigation Spec

> In real `/lazy-batch` runs, the only forward-advance trigger that fires for real-skill (by-reference) dispatch cycles — `advance_run_counters` — reads a NON-MONOTONIC dispatch oracle (`consumed_emission_count()`). Two mechanisms (the `advance_meta_cycle` watermark `+1`-absorb, and ring-cap eviction of consumed registry entries) freeze or regress that oracle below the persisted watermark, so `forward_cycles` stalls while real cycles keep running and the deterministic max-cycles cap never fires.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-06-19
**Placement:** docs/bugs/byref-dispatch-undercounts-forward-cycles
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/lazy_core.py` (`advance_run_counters` ~L7664, `advance_meta_cycle` ~L7746, `advance_forward_cycle` ~L7793, `consumed_emission_count` ~L7210, `_REGISTRY_RING_CAP=64` ~L5209, ring-cap eviction ~L7309); `user/scripts/lazy-state.py` (`--repeat-count` probe advance site ~L6647, `--apply-pseudo` state-change advance site ~L6546, `--emit-dispatch` meta advance site ~L6485); `user/skills/lazy-batch/SKILL.md` HARD CONSTRAINT 8 (~L87-89) + Step 1c cap (~L441) + Step 1d F2a by-reference dispatch (~L643); `user/scripts/CLAUDE.md` "Cycle-counter advance: two orthogonal triggers". Prior fixes that motivated the current (buggy) shape: ISSUE-5 forward-inflation fix (consume-gating, 2026-06-14) and Fix-A state-change advance (`lazy-batch-unified-driver-parity-and-accounting` Phase 1, 2026-06-17).

<!-- Status lifecycle:
  - Investigating → active investigation; bug-state.py routes to /spec-bug.
  - Concluded     → root cause proven; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

1. **[OBSERVED in logs]** `forward_cycles` counter freezes while real cycle-actions continue — session `5f227442` @ 2026-06-19: "forward counter has **stuck at 16** across parts 3–5 … my by-ref dispatches aren't registering consume-advances, so the script's max-cycles cap likely won't fire on its own. That's a harness undercount."
2. **[OBSERVED in logs]** `last_advance_consume_count` frozen, real cycle-actions exceed counted — session `5f227442` checkpoint report: "by-ref dispatch consumes stopped advancing forward_cycles after d7 part-3 (last_advance_consume_count frozen at 50) … Real cycle-actions ≈23. Worth a /harden-harness pass."
3. **[PROVEN — code analysis]** The dispatch-bound real-skill probe (`lazy-state.py --repeat-count`) advances `forward_cycles` ONLY via `advance_run_counters` (lazy-state.py ~L6647). The consume-independent state-change trigger `advance_forward_cycle` is wired ONLY into the `--apply-pseudo` inline-pseudo-skill path (~L6546) — NEVER the real-skill probe path. So real-skill (by-reference) forward cycles depend EXCLUSIVELY on the non-monotonic consume oracle.

## Reproduction Steps

The frozen-counter state arises in any sufficiently long `/lazy-batch` run that mixes meta dispatches with real by-reference cycles. Two independent contributors, both reproducible from the code:

**Contributor A — `advance_meta_cycle` watermark over-absorb:**
1. Run marker present; `last_advance_consume_count = W`, `consumed_emission_count() = C` (with `C == W`, the steady state after a forward advance).
2. A meta dispatch goes through `--emit-dispatch` → `advance_meta_cycle()` sets `last_advance_consume_count = consumed_emission_count() + 1 = C + 1` (the deliberate `+1` to pre-absorb the meta dispatch's own forthcoming guard-ALLOW consume — lazy_core.py ~L7771).
3. The meta dispatch is by-reference → guard consumes 1 nonce → `C → C+1`. Watermark and live count are now both `C+1` — break-even.
4. The NEXT real forward by-ref cycle: probe runs `advance_run_counters` BEFORE that cycle's Agent dispatch consumes. At probe time `consumed_emission_count() == C+1 == last_advance_consume_count`, so the gate `current_consume <= prior_consume` holds → **no advance**. The real forward cycle's own consume lands later (inside the guard), but the NEXT probe's `advance_meta_cycle`/intervening-meta interaction keeps the watermark at or ahead of the live count. Every meta dispatch interleaved with real cycles ratchets the watermark one step ahead, and `forward_cycles` stalls.

**Contributor B — ring-cap eviction regresses the oracle (the dominant long-run failure, matches "frozen at 50"):**
1. `consumed_emission_count()` SUMS the `consumed` entries CURRENTLY in `lazy-prompt-registry.json` (lazy_core.py ~L7231-7232). It is NOT a monotonic counter — it is a live census of surviving entries.
2. The registry ring cap is 64 (`_REGISTRY_RING_CAP`); `register_emission` evicts the oldest entry (index 0) when over cap (~L7309). In a long run (parts 3–5, 50+ dispatches) the oldest entries — many already `consumed` — get evicted.
3. Once cumulative emissions exceed ~64, each new emission evicts a consumed entry, so `consumed_emission_count()` PLATEAUS (and can drop) even as real dispatches keep happening.
4. `last_advance_consume_count` was last written at the plateau value (e.g. 50). From then on `current_consume <= prior_consume` is PERMANENTLY true → `advance_run_counters` no-ops forever → `forward_cycles` frozen at its last value (16) while ~23 real cycle-actions proceed. Exactly the observed signature.

**Expected:** `forward_cycles` advances once per real pipeline-advancing cycle, monotonically, so `forward_cycles >= max_cycles` (Step 1c) fires the deterministic clean stop.
**Actual:** `forward_cycles` freezes mid-run; the cap never fires; the operator must manually adjudicate the budget.
**Consistency:** Deterministic once either contributor's precondition is met (B is reached by any run exceeding the 64-entry ring cap; A by any meta-dispatch-interleaved cycle). Short runs (< ring cap, no meta interleave) never see it — which is why the smoke fixtures (single-advance, hermetic) pass.

## Evidence Collected

### Source Code

- **`advance_run_counters` (lazy_core.py ~L7664-7743)** — the consume-oracle trigger. Gate: `if current_consume <= prior_consume: return marker` (unchanged, no write). `current_consume = consumed_emission_count()`; `prior_consume = marker["last_advance_consume_count"]`. This is the ONLY forward-advance trigger reached by the real-skill dispatch-bound probe.
- **`consumed_emission_count` (lazy_core.py ~L7210-7232)** — `sum(1 for e in entries if e.get("consumed"))` over the LIVE registry. Non-monotonic by construction: ring-cap eviction of consumed entries lowers it. The docstring even notes eviction "would only *lower* the count" but reasons only about the F2 double-probe debounce (two adjacent probes), NOT about the run-lifetime `last_advance_consume_count` watermark that `advance_run_counters` compares against — that watermark persists across the whole run, so a one-time downward step strands it permanently.
- **`advance_meta_cycle` (lazy_core.py ~L7746-7774)** — sets `last_advance_consume_count = consumed_emission_count() + 1`. The `+1` over-absorb is correct in isolation (absorbs the meta dispatch's own consume) but compounds across many meta dispatches into a watermark that outruns the live consume count (Contributor A).
- **`advance_forward_cycle` (lazy_core.py ~L7793-7861)** — the CONSUME-INDEPENDENT, monotonic state-change trigger (keys on the `[feature_id, current_step, sub_skill]` tuple via `last_advance_state_key`). This is the robust mechanism that would NOT freeze. It is wired ONLY into `lazy-state.py --apply-pseudo` (~L6546-6552), i.e. it fires for inline pseudo-skills but NOT for real-skill by-reference cycles — the precise gap that leaves real cycles on the fragile consume oracle.
- **`lazy-state.py --repeat-count` advance site (~L6636-6648)** — `if args.repeat_count: lazy_core.advance_run_counters(state)`. The dispatch-bound real-skill probe calls `advance_run_counters` and NOTHING else. No `advance_forward_cycle` call on this path.
- **`lazy_guard.py` by-reference consume (~L596-633)** — `@@lazy-ref nonce=…` → `resolve_emission_by_nonce` → `consume_nonce`. By-reference dispatch DOES consume a nonce (so the oracle is fed), confirming the symptom is NOT "by-ref never consumes" but "the oracle the advance reads is non-monotonic and the watermark strands."

### Git History

The two prior fixes that produced today's shape: ISSUE-5 (2026-06-14) introduced consume-gating in `advance_run_counters` to fix forward-cycle INFLATION (the opposite failure — counter ran ahead). Fix-A (`lazy-batch-unified-driver-parity-and-accounting` Phase 1, 2026-06-17) added `advance_forward_cycle` to cover inline pseudo-skills the consume gate missed — but scoped its wiring to `--apply-pseudo` only, leaving real-skill cycles on the consume oracle. This bug is the residual: the robust trigger exists but is not wired to the path that needs it most.

### Related Documentation

- `user/scripts/CLAUDE.md` → "Cycle-counter advance: two orthogonal triggers" documents both triggers but states trigger 2 (`advance_forward_cycle`) "is wired into the `lazy-state.py --apply-pseudo` handler" — confirming, in the harness's own contract, that the state-change trigger does NOT cover the `--repeat-count` real-skill path.
- `lazy-batch/SKILL.md` HARD CONSTRAINT 8 (~L87): "Only `forward_cycles` is capped (at `max_cycles`)" — so a frozen `forward_cycles` disables the run's ONLY hard ceiling (meta is uncapped by design). This is why the undercount is P1, not cosmetic.

## Theories

### Theory 1: Watermark over-absorb by interleaved meta dispatches (Contributor A)
- **Hypothesis:** `advance_meta_cycle`'s `last_advance_consume_count = consume + 1` ratchets the watermark ahead of the live consume count each time a meta dispatch interleaves a real cycle, eventually stranding `advance_run_counters`.
- **Supporting evidence:** the `+1` is unconditional; real runs interleave many meta dispatches (recovery, coherence, hardening, apply-resolution) with real cycles.
- **Contradicting evidence:** a single forward consume normally re-passes the watermark next probe; A alone produces a one-cycle lag, not a permanent freeze, UNLESS meta dispatches outpace forward consumes. Sufficient to undercount, not always to fully freeze.
- **Status:** Confirmed (contributing).

### Theory 2: Ring-cap eviction regresses `consumed_emission_count` below the watermark (Contributor B)
- **Hypothesis:** once total emissions exceed the 64-entry ring cap, eviction of consumed entries plateaus/lowers `consumed_emission_count()` below the persisted `last_advance_consume_count`, making the advance gate permanently false → hard freeze.
- **Supporting evidence:** the "frozen at 50" / "stuck at 16" signature appears specifically in a long multi-part run (parts 3–5); 50 ≈ a plausible plateau near the 64 cap; `consumed_emission_count` is a live census, not a counter.
- **Contradicting evidence:** none found — the code path is unambiguous.
- **Status:** Confirmed (dominant in long runs).

### Theory 3: By-reference dispatch never consumes (the symptom's surface phrasing)
- **Hypothesis:** the log note "by-ref dispatches aren't registering consume-advances" means by-ref dispatch skips the consume.
- **Supporting evidence:** the operator's in-the-moment phrasing.
- **Contradicting evidence:** `lazy_guard.py` ~L607 calls `consume_nonce` on the by-reference allow path; by-ref DOES consume. The real fault is downstream — the non-monotonic oracle + stranded watermark, not a missing consume.
- **Status:** Ruled Out (re-framed as Theories 1+2).

## Proven Findings

- **Root cause:** real-skill (by-reference) forward cycles advance `forward_cycles` EXCLUSIVELY through `advance_run_counters`, whose gate compares the run-lifetime watermark `last_advance_consume_count` against `consumed_emission_count()` — a NON-MONOTONIC live census of the bounded (64-entry, TTL'd) prompt registry. Two mechanisms strand the watermark above the live count: (A) `advance_meta_cycle`'s `+1` over-absorb compounding across interleaved meta dispatches, and (B) ring-cap eviction of consumed entries plateauing/regressing the census. Once `consumed_emission_count() <= last_advance_consume_count` holds permanently, `forward_cycles` freezes while real cycles continue, disabling the only `max_cycles`-capped counter and silently breaking the clean-stop guarantee.
- **Why the robust trigger doesn't save it:** `advance_forward_cycle` (consume-INDEPENDENT, monotonic, keyed on the `[feature_id, current_step, sub_skill]` state tuple) already exists and would NOT freeze — but it is wired only into `--apply-pseudo`, so it never fires for real-skill probe cycles.

## Fix Scope (for `/plan-bug`)

The corrective direction (one converging design — both contributors collapse to "stop depending on a non-monotonic oracle for the real-skill forward advance"):

1. **Primary:** wire the monotonic state-change advance (`advance_forward_cycle`) into the real-skill dispatch-bound probe path (`lazy-state.py --repeat-count`, ~L6647) so real cycles advance on the `[feature_id, current_step, sub_skill]` change — independent of the consume census. This makes the real-skill path use the SAME robust trigger the inline-pseudo path already uses, and is the minimal change that defeats BOTH contributors (the watermark/census is no longer the forward-advance authority). Reconcile with the existing `advance_run_counters` call so the two triggers don't double-count a single cycle (the state-change tuple changes once per real cycle; the consume gate can be retired from forward-advance duty or kept only as a debounce — to be decided in planning).
2. **Hardening (defense-in-depth, even if (1) makes it moot for forward-advance):** make the watermark comparison robust to a non-monotonic oracle — e.g. clamp `last_advance_consume_count` to never exceed the live `consumed_emission_count()` it just observed, OR track emissions with a monotonic run-lifetime counter separate from the evictable registry census, so `advance_meta_cycle`'s `+1` and ring-cap eviction can no longer permanently strand the gate.
3. **Regression net:** add a `--test` fixture that simulates a long run crossing the ring cap (≥ 65 emissions) with interleaved meta dispatches and asserts `forward_cycles` keeps advancing for each real-skill state change (the exact scenario the current hermetic single-advance fixtures miss). Keep BOTH `lazy-state.py --test` and `bug-state.py --test` green (shared `lazy_core`).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Forward-advance trigger | `user/scripts/lazy_core.py` (`advance_run_counters`, `advance_meta_cycle`, `advance_forward_cycle`, `consumed_emission_count`) | Root cause: non-monotonic oracle + stranded watermark; robust trigger not wired to real-skill path |
| Probe dispatch site | `user/scripts/lazy-state.py` (~L6647 `--repeat-count`; ~L6546 `--apply-pseudo`) | The wiring gap — `advance_forward_cycle` must be added to the real-skill probe path |
| Bug-pipeline parity | `user/scripts/bug-state.py` (~L4537) | Inherits the same advance logic via `lazy_core`; fix must keep both pipelines correct |
| Orchestrator cap | `user/skills/lazy-batch/SKILL.md` (Step 1c ~L441, HARD CONSTRAINT 8) | Consumer of the frozen counter; the cap it enforces is the broken guarantee (no SKILL change expected — the fix is script-side) |
| Regression net | `user/scripts/test_lazy_core.py` + `--test` baselines | New long-run / ring-cap-crossing fixture required |

## Open Questions

(None block planning.) One design choice deferred to `/plan-bug`: whether to RETIRE `advance_run_counters` from forward-advance duty entirely (relying on `advance_forward_cycle` for the forward count and keeping the consume gate only for the F2 double-probe debounce) or to KEEP both with a reconciliation guard. Both reach the same product behavior (forward_cycles advances monotonically per real cycle); the choice is internal-mechanical, resolved during planning.
