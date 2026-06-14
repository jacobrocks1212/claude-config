# Lazy Pipeline — Two-Stage Product-Decision Steering Gates — Feature Specification

> Insert two operator steering gates into the lazy feature pipeline — a pre-research gate (fundamental product decisions, before the `needs-research` halt) and a post-research gate (research-informed product decisions, after `/ingest-research` and before any implementation plan is written) — so product calls are confirmed via `AskUserQuestion` before they're baked into SPEC/PHASES.

**Status:** Rejected
**Priority:** P1
**Last updated:** 2026-06-14
**Rejected:** 2026-06-14
**Research:** none (process/tooling spec — drafted from first principles, no Gemini round)

**Depends on:** (none)

---

## ❌ Rejected — Evidence

**Verdict:** The motivating premise — "product decisions get baked into PHASES/plans without operator confirmation, causing rework" — did **not** hold when measured against the actual `audio-rate-modulation` run that prompted this spec. The existing pipeline already steered the operator adequately, with negligible rework. Building the two-gate re-architecture is disproportionate to the problem it solves.

**What actually happened on `audio-rate-modulation`** (AlgoBooth `origin/main`, commits in order):

| Commit | Event |
|--------|-------|
| `1eae6b66` | `/ingest-research` lands research |
| `a965b6fd` | `plan-feature` writes `PHASES.md` + **all 5 implementation plans** |
| `fb80e6e1` | Step 1d.5 input-audit writes `NEEDS_INPUT.md` — surfaces 3 producer-facing decisions |
| `57d64a33` | Operator resolution applied to SPEC/PHASES |

**Were product decisions lost?** Largely no. The post-`plan-feature` input-audit surfaced and the operator resolved the 3 producer-facing calls: producer syntax (`.audioRate()`), ineligible-param behavior (explicit non-silent error), and M>4 overrun (fail compile + error + keep prior graph). Only the **M=4 cap value** and the **v1 node set** were adopted from the research recommendation without an explicit confirm — the "strong research recommendation" class.

**Was there significant rework?** No — effectively zero. The resolved sentinel states verbatim: *"chosen options match the recommendation (and the plan's baked choice) — the plan does not need changes."* The resolution was `PHASES.md` +17 / `SPEC.md` +12 lines of doc tightening; **all 5 implementation plans were untouched. No code, no plan regeneration.**

**Why the deferred-to-after-planning timing cost nothing here:**

1. The existing Step 1d.5 input-audit + Step 1g `AskUserQuestion` already constitute a real decision gate — just *after* `plan-feature` rather than before.
2. `spec-phases` / `write-plan` authored the plans at the right altitude (referenced `.audioRate` and "method chaining" abstractly, not a hardcoded rejected form), so the late decision did not invalidate them.
3. The operator's choices matched the plan's baked assumptions, so applying the resolution was a localized doc edit.

**Residual gap (real but small):** research-recommended **scope / hard-cap** decisions (the `M=4` cap, the v1 node set) were adopted silently rather than confirmed. The proportionate fix is **not** this spec — it is a one-line addition to the Step 1d.5 audit's product-behavior classification checklist: *"research recommendations that set v1 scope or hard numeric caps are `product-behavior` — surface them via `NEEDS_INPUT.md`."* That reuses machinery already proven to work, at near-zero cost. Tracked as a candidate follow-up; not pursued here.

**Cost the spec would have added** (for context on the rejection): a new `lazy-state.py` Step 5.5 routing node, a contract change relaxing `/ingest-research` from side-effect-free to halt-capable, a new `DECISIONS.md` ledger artifact + append discipline, and a new halt on every research-backed feature — against ~17 lines of avoided doc churn in the one case observed.

The full design below is retained as-is for the record; it was the design before the empirical check above superseded it.

<!-- Sibling (not a dependency): docs/specs/lazy-bug-family — the bug-pipeline analog over bug-state.py. Once this lands, the same two-gate pattern is a candidate to mirror into /lazy-bug + /lazy-bug-batch. Tracked as a follow-up, not authored here. -->

---

## Why This Exists (origin)

This spec was triggered by a concrete failure of operator steering on the **`audio-rate-modulation`** feature (AlgoBooth, `docs/features/audio/audio-rate-modulation/`).

Sequence observed (commits on AlgoBooth `origin/main`):

1. `0ef137a0` — `/spec` baseline-lock over the auto-generated stub. It autonomously shaped scope, UX, and technical design with **no `AskUserQuestion` and no `NEEDS_INPUT.md`**.
2. `3fac370c` — `NEEDS_RESEARCH.md`, strict research halt.
3. (operator uploads a Gemini research report in chat — Step 5 in-session resume.)
4. `1eae6b66` — `/ingest-research` lands `RESEARCH.md` + `RESEARCH_SUMMARY.md`. The report is **dense with settled "Recommendations"**: a hard `M=4` audio-rate-modulator cap, `.with_audio_rate_mod(Param, src)` producer syntax, which DSP nodes ship audio-rate in v1, and overrun behavior (LSP error vs. silent fallback) — all product-behavior calls.
5. The next cycle routed **straight to `/plan-feature`** (PHASES + write-plan). No decision gate fired between research landing and planning.

Root cause (verified against `lazy-state.py` + the lazy-batch skill contract):

- `NEEDS_INPUT.md` is written **only** by the Step 1d.5 input-audit subagent, which runs **only after a `/spec` or `plan-feature` cycle** — never after `/ingest-research` (a mechanical step). It is consumed by Step 1g (`AskUserQuestion`) on the next cycle.
- `lazy-state.py` routing: the Step 5 research-integration gate (`lazy-state.py:1134-1186`) produces `RESEARCH_SUMMARY.md`; the **very next** routing node, Step 6 (`lazy-state.py:1188+`), dispatches `/plan-feature` the moment `PHASES.md` is absent. **There is no decision gate between them.**

So the densest source of product decisions — the research report — enters through the one pipeline step with no audit, and its recommendations are planned against without operator confirmation. Symmetrically, the pre-research `/spec` baseline can bake fundamental product decisions (v1 scope, ownership, core UX) with no confirmation.

The operator's requirement:

1. **Fundamental** product decisions answered **pre-research** (during/after the `/spec` baseline cycle), before the `needs-research` halt.
2. **Remaining** product decisions answered **post-research** — after `/ingest-research`, **before** any implementation plan (`/spec-phases` / `/write-plan` / `/plan-feature`) — so research context informs the answer **and** no planning rework is incurred from late decisions.

## Scope

**In scope:**

- A **post-research steering gate** ("Step 5.5") in `lazy-state.py`: after `RESEARCH_SUMMARY.md` exists and before `/plan-feature` is dispatched, route through a product-decision audit. Idempotency is enforced by a tracked receipt sentinel `RESEARCH_DECISIONS_RESOLVED.md`.
- The post-research audit itself is **folded into `/ingest-research`** (operator decision Q1) as a decision-audit tail — `/ingest-research` classifies the research's product-behavior recommendations and writes `NEEDS_INPUT.md` (or the receipt, when none surface).
- A **pre-research steering gate**: `/spec` Phase-1 baseline must emit `NEEDS_INPUT.md` for baseline-gating product decisions, **with** the existing Step 1d.5 post-`/spec` input-audit retained as an independent backstop (operator decision Q2 — defense in depth).
- An **answerability partition + `DECISIONS.md` ledger** (operator decision Q3) so a decision is asked at exactly one gate: pre-research asks only research-*unanswerable* calls and defers research-*answerable* ones into `RESEARCH_PROMPT.md`; the post-research audit reads the ledger and asks only still-open decisions.
- Lockstep propagation across the four consumers of `lazy-state.py`: `/lazy-batch`, `/lazy-batch-cloud`, `/lazy`, `/lazy-cloud`.

**Out of scope:**

- The bug pipeline (`bug-state.py`, `/lazy-bug*`). Mirroring the pattern there is a tracked follow-up.
- Changing the `needs-research` halt itself, the in-session resume protocol (Step 5), or `--allow-research-skip` batching semantics — the gates compose with them unchanged.
- Re-litigating decisions on features already past planning (`PHASES.md` present). The gate only fires when `PHASES.md` is absent, so completed/planned features are never re-gated.

## User Experience

The operator runs `/lazy-batch` (or `/lazy`, cloud variants) as today. The change is **two new pause points**, each surfaced through the existing Step 1g `AskUserQuestion` flow (rich `## Decision Context` re-printed to chat, picker options 1:1 with chat, recommendation pre-highlighted):

1. **Pre-research pause** — after the stub `/spec` baseline cycle, before the `needs-research` halt. The operator confirms fundamental calls: what ships in v1, which subsystem owns the surface, the core UX shape, user-facing defaults. Research-answerable questions are *not* asked here — they're routed into the research prompt.
2. **Post-research pause** — after `/ingest-research`, before any planning. The operator confirms the research's product-behavior recommendations (the `M=4` cap, the syntax surface, the v1 node set, overrun behavior — to use the motivating example), each presented with the research's recommendation as the lead option.

When a gate's audit surfaces **no** product decisions, it writes the receipt and the loop proceeds silently — no spurious halt. Resolved decisions accrue in a per-feature `DECISIONS.md` so neither gate re-asks a settled call.

## Technical Design

### 1. `lazy-state.py` — new Step 5.5 routing node (post-research gate)

Insert between the Step 5 research-integration gate (ends `lazy-state.py:1186`) and the Step 6 PHASES node (`lazy-state.py:1188`):

```
# Step 5.5: Post-research product-decision gate
#   Preconditions to reach here: RESEARCH.md AND RESEARCH_SUMMARY.md both exist
#   (the Step 5 branches above guarantee it), PHASES.md absent (checked at Step 6).
receipt = spec_path / "RESEARCH_DECISIONS_RESOLVED.md"
needs_input = spec_path / "NEEDS_INPUT.md"
if not (spec_path / "PHASES.md").exists() and not receipt.exists():
    # A pending NEEDS_INPUT is handled by the existing needs-input node (Step 3.5)
    # — do not double-route. Only when neither receipt nor a pending decision
    # sentinel exists do we (re-)run the ingest audit tail.
    if not needs_input.exists():
        return _state(
            **common,
            current_step="Step 5.5: post-research decision audit",
            sub_skill="ingest-research",
            sub_skill_args=f"{spec_path_str} --audit-only",
        )
# else: receipt present → fall through to Step 6 (plan-feature) as before.
```

Key properties:

- **Receipt-gated, not state-inferred.** `RESEARCH_DECISIONS_RESOLVED.md` is a git-tracked sentinel (mirrors `NEEDS_RESEARCH.md` / `RETRO_DONE.md` / `VALIDATED.md`), so it survives cloud container reclaim. The gate is satisfied iff the receipt is on disk.
- **Self-healing for already-ingested features.** A feature whose research landed *before* this gate shipped has `RESEARCH_SUMMARY.md` but no receipt; the gate re-dispatches `/ingest-research --audit-only`, which runs only the new audit tail (it must be idempotent — skip re-writing `RESEARCH.md`/`RESEARCH_SUMMARY.md` when present). This retro-covers in-flight features without a special migration.
- **No new terminal reason.** The gate routes to an existing dispatch (`ingest-research`) or, once that writes `NEEDS_INPUT.md`, the existing `needs-input` node (`lazy-state.py:1052`, `terminal_reason="needs-input"`) handles it — which Step 1g resolves inline (non-halting). No change to the terminal-reason vocabulary.

### 2. `/ingest-research` — decision-audit tail + `--audit-only` mode (post-research gate generator)

Per operator decision **Q1 (Extend `/ingest-research`)**, the post-research audit lives inside `/ingest-research` rather than a separate skill. After its existing mechanical work (write `RESEARCH.md` + `RESEARCH_SUMMARY.md`, drop the `> Draft (pre-Gemini)` trailer, clear `queue.json "stub": true`, move consumed `.txt` to `_consumed/`), it runs a **decision-audit tail**:

1. Read `RESEARCH_SUMMARY.md` (and `RESEARCH.md` as needed), `SPEC.md`, and the `DECISIONS.md` ledger if present.
2. Classify each research recommendation as `product-behavior` vs `mechanical-internal` using the **same checklist `/spec --batch` Phase 3 already defines** (defaults, v1 scope, UX shape, copy/labels, error/empty states, workflow shape, configurability boundary, research-multi-option calls, behavioral-mode toggles). Reuse that component verbatim so the two gates classify identically.
3. Filter out any decision already resolved in `DECISIONS.md` (answerability partition — see §4).
4. **If any still-open `product-behavior` decision remains:** write `NEEDS_INPUT.md` (canonical `kind: needs-input` schema, rich `## Decision Context` body, ≤4 cap, each option carrying the research's recommendation as the lead/`**Recommendation:**`). Do **not** write the receipt. Return.
5. **If none remain:** write `RESEARCH_DECISIONS_RESOLVED.md` (receipt) and return — the loop proceeds to planning with no halt.

`--audit-only` mode skips steps that mutate research artifacts and runs steps 1-5 only (used by the Step 5.5 self-heal dispatch). Plain invocation (Step 0.5 staged ingest, Step 5 in-session resume) runs the full mechanical body **then** the audit tail.

**Contract change (explicit):** `/ingest-research` is no longer "purely mechanical / side-effect-free." It may now end a cycle with a `NEEDS_INPUT.md` sentinel. This composes with the existing pipeline because Step 1g is **non-halting** — the orchestrator resolves the decision via `AskUserQuestion` and continues. The in-session resume protocol (Step 5) and pre-loop ingest (Step 0.5) require no change: after they dispatch `/ingest-research`, the next state probe simply sees either the receipt (→ plan) or `NEEDS_INPUT.md` (→ Step 1g). Every skill doc asserting "ingest is mechanical" must be updated to state the audit-tail exception.

### 3. Pre-research gate — harden `/spec` Phase 1 + retain Step 1d.5 backstop

Per operator decision **Q2 (defense in depth)**:

- **`/spec` Phase-1 (`--batch`) contract** already specifies: baseline-gating `product-behavior` decisions → `NEEDS_INPUT.md`; research-answerable → `RESEARCH_PROMPT.md`; mechanical-internal → auto-accept. The failure on `audio-rate-modulation` was non-compliance, not a missing contract. Hardening = make the Decision-Classification Ledger return **mandatory and machine-checkable**, and make the orchestrator treat a missing/empty ledger from a stub `/spec` cycle as an audit trigger (not a pass).
- **Step 1d.5 input-audit** (in `/lazy-batch` + `/lazy-batch-cloud`) is **retained and runs after the stub `/spec` baseline cycle** as the independent verifier. It re-classifies the SPEC diff against the returned ledger and writes its own `NEEDS_INPUT.md` for any `product-behavior` decision `/spec` baked in as `mechanical-internal` or omitted. This is exactly the check that would have caught `0ef137a0`.

No change to *where* Step 1d.5 lives — only an assertion that it must fire on the stub→`/spec` baseline cycle (it is dispatched "after every `/spec` or `plan-feature` cycle"; confirm the stub `/spec` cycle is not exempted).

### 4. Answerability partition + `DECISIONS.md` ledger (no double-asking)

Per operator decision **Q3**:

- **Partition rule.** A product decision is *research-unanswerable* (→ pre-research gate) when the operator holds final authority regardless of evidence: v1 scope boundary, subsystem ownership, core UX shape, user-facing defaults. It is *research-answerable* (→ deferred into `RESEARCH_PROMPT.md`, asked at the post-research gate) when external evidence narrows the choice: technical-option selection among defensible alternatives, parameter values, algorithm/interpolation choices, industry-convention conformance. This mirrors `/spec`'s existing "research-answerable questions go into `RESEARCH_PROMPT.md`, never `NEEDS_INPUT.md`" rule — it is generalized into the explicit partition.
- **`DECISIONS.md` ledger.** A per-feature, git-tracked, append-only ledger at `{spec_dir}/DECISIONS.md`. Each row: decision title, classification, gate (pre/post), status (`deferred-to-research` | `resolved`), chosen option, date. Writers:
  - `/spec` Phase 1 appends fundamental decisions (resolved or `deferred-to-research`).
  - The Step 1g **apply-resolution subagent** appends `resolved` rows when the operator answers (at either gate) — alongside its existing job of propagating the answer into SPEC/PHASES.
  - `/ingest-research`'s audit reads the ledger to skip resolved/deferred-already-asked decisions and to *re-surface* `deferred-to-research` rows now that research exists.
- **Receipt + ledger relationship.** `RESEARCH_DECISIONS_RESOLVED.md` records "the post-research audit ran and all surfaced decisions are resolved." `DECISIONS.md` is the full trail. The receipt is the machine-checkable gate; the ledger is the dedup source of truth.

### 5. Lockstep across the four `lazy-state.py` consumers

`lazy-state.py` is the single routing source of truth, so the Step 5.5 node propagates to `/lazy-batch`, `/lazy-batch-cloud`, `/lazy`, and `/lazy-cloud` automatically. Each orchestrator skill doc still needs:

- Acknowledgment of the Step 5.5 dispatch in its state-machine description.
- The `/ingest-research` contract-change note (audit tail may produce `NEEDS_INPUT`).
- For `/lazy-batch` + `/lazy-batch-cloud`: confirmation that Step 1d.5 fires on the stub `/spec` cycle.

`--cloud` parity: the gate is docs/sentinel-only (no Tauri/MCP), so it runs identically in cloud. The receipt and `DECISIONS.md` are git-tracked → durable across container reclaim.

## Implementation Phases

1. **`lazy-state.py` Step 5.5 node + tests.** Add the routing node, the receipt check, the `--audit-only` dispatch, and the self-heal-when-no-receipt path. Unit tests for: receipt present → plan-feature; no receipt + no NEEDS_INPUT → ingest-research `--audit-only`; NEEDS_INPUT pending → needs-input node (no double-route); PHASES present → never gated.
2. **`/ingest-research` audit tail + `--audit-only`.** Add the classification tail (reuse the shared classification component), `NEEDS_INPUT.md`/receipt write logic, ledger read/skip, and idempotent `--audit-only` mode.
3. **`DECISIONS.md` ledger + apply-resolution writer.** Define the schema; wire `/spec` Phase 1 and the Step 1g apply-resolution subagent to append; wire `/ingest-research` to read.
4. **Pre-research hardening.** Make `/spec` Phase-1 ledger return mandatory/checkable; confirm Step 1d.5 fires on the stub `/spec` cycle in both batch orchestrators.
5. **Four-skill doc lockstep + contract-change sweep.** Update `/lazy-batch`, `/lazy-batch-cloud`, `/lazy`, `/lazy-cloud` state-machine docs; sweep every "ingest is mechanical" assertion to note the audit-tail exception.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Post-research gate blocks planning until decisions resolved | `lazy-state.py` on a feature with `RESEARCH_SUMMARY.md`, no `PHASES.md`, no receipt | `next_action.sub_skill == "ingest-research"`, args include `--audit-only` | `lazy-state.py` unit test |
| Gate passes once receipt present | Same feature + `RESEARCH_DECISIONS_RESOLVED.md` on disk | `next_action.sub_skill == "plan-feature"` | `lazy-state.py` unit test |
| No spurious halt when research has no product calls | `/ingest-research --audit-only` on research with only mechanical-internal recs | Receipt written, no `NEEDS_INPUT.md`, loop proceeds to plan | `/ingest-research` audit-tail test |
| Product recs surface as decisions | `/ingest-research` on research with ≥1 product-behavior rec (e.g. an `M=4`-style cap) | `NEEDS_INPUT.md` written, rich body, recommendation as lead option, no receipt | `/ingest-research` audit-tail test |
| Self-heal for pre-existing ingests | Feature with `RESEARCH_SUMMARY.md` but no receipt (legacy) | Gate dispatches `--audit-only`; `RESEARCH.md`/`RESEARCH_SUMMARY.md` not rewritten | `lazy-state.py` + ingest idempotency test |
| No double-asking | Decision resolved pre-research and present in `DECISIONS.md` | Post-research audit omits it from `NEEDS_INPUT.md` | `/ingest-research` ledger-dedup test |
| Pre-research gate catches baseline product calls | Stub `/spec` baseline cycle that bakes a scope/UX decision | Step 1d.5 audit writes `NEEDS_INPUT.md`; Step 1g asks before `needs-research` halt | `/lazy-batch` integration / Step 1d.5 audit test |
| Planned features never re-gated | `lazy-state.py` on a feature with `PHASES.md` present | Step 5.5 skipped; routes to phase completion as before | `lazy-state.py` unit test |
| Cloud parity | `lazy-state.py --cloud` on a gated feature | Identical Step 5.5 routing; receipt/ledger git-tracked | `lazy-state.py --cloud` test |

## Open Questions

- **`--audit-only` reuse vs. a thin internal entrypoint.** Folding the audit into `/ingest-research` (Q1) means `--audit-only` re-enters the skill purely for the tail. Confirm during Phase 2 that this is cleaner than a small internal helper the full path and the gate both call — the behavior is identical; this is a code-organization call for implementation.
- **`DECISIONS.md` vs. an in-SPEC `## Decisions` section.** The ledger is a separate tracked file. If doc-lint or existing tooling already expects a decisions section in SPEC.md, reconcile (the ledger can be the machine-readable mirror of a human-readable SPEC section).
- **Step 1d.5 cost on every stub `/spec` cycle.** Confirm the extra Opus input-audit per stub baseline is acceptable batch overhead, or gate it to stub cycles that returned a non-empty product-behavior ledger.

## Research References

None — this spec was drafted from first-principles exploration of `lazy-state.py`, the `/spec` / `/ingest-research` / `/lazy-batch` skill contracts, and the `audio-rate-modulation` failure trace. No Gemini research round was run (operator opted out).
