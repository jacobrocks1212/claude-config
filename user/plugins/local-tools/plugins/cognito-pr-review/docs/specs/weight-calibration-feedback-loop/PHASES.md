# Implementation Phases — Weight Calibration & Review-Feedback Loop

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this deliverable is a Claude Code plugin (markdown commands + agents, a deterministic `tsx` post-processor, and a YAML weight store). It exposes no MCP-reachable app surface; verification is via running `post-process.ts` on fixtures and exercising the review commands, not a dev runtime / MCP HTTP server.

## Validated Decisions (operator-confirmed, 2026-06-22)

These resolve the SPEC's Open Questions and bind the phase design below:

- **Confidence scale = discrete.** Agents emit `CONFIRMED` (→ `1.0`) or `UNVERIFIED` (→ `0.5`). The gate consumes the numeric mapping; the buddy UI shows the label. No continuous `0–1` scores.
- **Source-level default weights = `0.9 / 0.7 / 0.7`** for investigation / intrafile / reuse. Conservative seed; R2's EMA pulls them toward reality from real dispositions rather than hand-seeding from thin (mostly n=1) dismiss data.
- **`MIN_EFFECTIVE_WEIGHT` stays `0.3`.** The floor is unchanged; `weight × confidence` does the gating. (e.g. an `UNVERIFIED` reuse finding = `0.7 × 0.5 = 0.35` survives; an `UNVERIFIED` sweep rule already at `0.525 × 0.8 category × 0.5 = 0.21` drops.) Revisit only if real data shows the floor mis-tuned.
- **Buddy auto-recalibration runs silently at Phase 2** with a printed summary — no per-session opt-in prompt. Maximizes the disposition signal currently lost to mid-walk abandonment.

## Reuse Ledger Honored

Each phase below extends/refactors the systems named in the SPEC's Reuse Ledger; no new parallel scoring or calibration system is introduced. Phase ↔ ledger mapping: Phase 1 → "Effective-weight compute" + "Source bypass" + "Weight store"; Phase 2 → agent confidence (new field on existing finding schemas) + "Confidence ranking"; Phase 3 → "Sweep agent weights"; Phase 4 → "EMA weight update" + "Disposition capture".

---

### Phase 1: Generalize the scoring engine (R1 — engine half)

**Scope:** Make `post-process.ts` weight *every* finding source, not just sweep. Add source-level weights to `weights.yaml`. Compute `effective_weight = source/rule weight × confidence` for all sources, with confidence defaulting to `1.0` when an agent does not yet emit it (back-compat so this phase ships before Phase 2 wires real confidence). Generalize the threshold drop to all sources. This is the dependency root and is currently **untested** — this phase adds the first tests for the file.

**Deliverables:**
- [x] `weights.yaml`: new `source_weights` block — `investigation: 0.9`, `intrafile: 0.7`, `reuse: 0.7` (sweep keeps `rule_weight × category_multiplier`). Document the keys.
- [ ] `post-process.ts`: generalize `computeEffectiveWeight()` (`:218-224`) so non-sweep sources resolve `source_weights[source]` instead of the hardcoded `1.0` at `:320/:346/:372`; multiply every source by `confidence ?? 1.0`.
- [ ] `post-process.ts`: generalize `step2_dropBelowThreshold` (`:391-407`) to apply `MIN_EFFECTIVE_WEIGHT` (`0.3`) to **all** sources, removing the `f.source === "sweep"` guard at `:399`.
- [ ] Preserve the ranking invariant: Opus-lane sources still outrank sweep on ties (`step3`/`step4` `:427-465`) — generalizing the *weight* must not collapse the source-precedence dedup.
- [ ] Tests: a fixture `combined-findings.json` (one finding per source, mixed weights/confidence) driven through `post-process.ts`, asserting per-source `effective_weight` and which findings drop. Add a `package.json` test script / `tsx` test harness (none exists today).

**Minimum Verifiable Behavior:** `npx tsx scripts/post-process.ts --input <fixture-combined-findings.json> --manifest <fixture-manifest.json>` emits `processed-findings.json` where (a) an investigation finding carries `effective_weight: 0.9` (not `1.0`), and (b) a sub-`0.3` non-sweep finding is absent from `processed_findings` and counted in `dropped_count`.

**Runtime Verification** *(checked by the test harness — NOT by the implementation agent):*
- [ ] Fixture run: each source's `effective_weight` equals `source_weight × confidence` (sweep: `rule_weight × category_multiplier × confidence`).
- [ ] Fixture run: a non-sweep finding below `0.3` is dropped and reflected in `dropped_count`.
- [ ] Fixture run: Opus-vs-sweep dedup precedence on a colliding `file:line` is unchanged from current behavior.

**MCP Integration Test Assertions:** N/A — no runtime-observable app surface; verification is the deterministic `tsx` fixture run above.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `scripts/post-process.ts` — generalize weight compute + threshold drop. *Reuse:* extend `computeEffectiveWeight()` / `getCategoryMultiplier()` (`:206-224`); do NOT add a parallel scorer.
- `knowledge/weights.yaml` — add `source_weights`. *Reuse:* extend the existing store; reuse `ema_alpha`/`category_multipliers`.
- `scripts/__tests__/post-process.test.ts` (or equivalent `tsx` harness) — **net-new (create)**, plus fixtures.
- `package.json` — **net-new test script** if absent.

**Testing Strategy:** Pure-function fixture tests on the deterministic post-processor. No mocks needed — inputs are JSON files, output is JSON. This is the highest-leverage, most-isolatable unit in the feature.

**Integration Notes for Next Phase:**
- The engine reads `confidence` off each finding and defaults missing values to `1.0`. Phase 2 makes agents emit it; nothing else in the engine changes.
- `source_weights` keys are `investigation | intrafile | reuse`; sweep is intentionally absent (it uses rule × category). Keep this asymmetry — Phase 4 calibrates both shapes.
- Confidence numeric mapping (`CONFIRMED=1.0`, `UNVERIFIED=0.5`) is owned by the engine/parse layer, not the agents — agents emit the *label*; the engine maps it. Decide where the label→number mapping lives (post-process parse) and document it so Phase 2 agents only emit the string.

#### Implementation Notes

**2026-06-22 — Batch 1 (WU-1): `source_weights` added to `weights.yaml`.**
- Inserted a top-level `source_weights` mapping (`investigation: 0.9`, `intrafile: 0.7`, `reuse: 0.7`) at `weights.yaml:16`, between `category_multipliers` and `rule_weights`, one blank line on each side. No `sweep` key (sweep keeps `rule_weight × category_multiplier` — the asymmetry is by design).
- Verified: YAML parses cleanly; `js-yaml` returns `{investigation:0.9, intrafile:0.7, reuse:0.7}`.
- Propagation: additive top-level key; no other script that reads `weights.yaml` (`calibrate-weights.ts`, `aggregate-findings.ts`) is affected. The `WeightsConfig` type addition lands in WU-2.
- **Review verdict:** PASS (ground-truth verified: yes).
- Files modified: `knowledge/weights.yaml`.

---

### Phase 2: Agents emit confidence + investigation grounding (R1 producers + R7)

**Scope:** The four weighting-relevant agents emit a `confidence` label (`CONFIRMED`/`UNVERIFIED`) on every finding, feeding the gate Phase 1 built. Simultaneously fix investigation grounding to diff against the PR head instead of `main` (SPEC friction #7 / symptom #6). Both investigation changes co-located here to keep a single writer on `investigation.md`.

**Deliverables:**
- [ ] `agents/sweep.md`: emit `confidence: CONFIRMED|UNVERIFIED` per finding; define the rubric (hedge-phrase / "may produce…" findings → `UNVERIFIED`).
- [ ] `agents/investigation.md`: emit `confidence`; Solver-Verifier-confirmed hypotheses → `CONFIRMED`, otherwise `UNVERIFIED`.
- [ ] `agents/cognito-intra-file-consistency.md` + `agents/cognito-consistency-checker.md`: emit `confidence`; fold the existing prose "confidence 80" gate into the emitted label.
- [ ] `agents/investigation.md`: ground analysis against the **PR head** (the diff under review), not local `main` (`:53-62`). Document the base ref it must use.
- [ ] Confirm the Phase-1 engine maps the emitted labels correctly end-to-end (no engine change expected; verify).

**Minimum Verifiable Behavior:** A review run (or a captured `combined-findings.json` from a real run) shows each of the four sources carrying a `confidence` field, and an `UNVERIFIED` finding receives a reduced `effective_weight` in `processed-findings.json` per Phase 1's gate.

**Runtime Verification** *(checked by a review run / captured fixture — NOT by the implementation agent):*
- [ ] Every finding from the four agents carries `confidence ∈ {CONFIRMED, UNVERIFIED}`.
- [ ] An `UNVERIFIED` finding's `effective_weight` is half its `CONFIRMED` equivalent.
- [ ] Investigation findings reference the PR-head diff, not `main` (no dead-code mislabel of a live branch — the 16683 symptom).

**MCP Integration Test Assertions:** N/A — agent output is JSON consumed by the post-processor; verified via the fixture/review-run above.

**Prerequisites:**
- Phase 1: the engine must already consume `confidence` and apply `source_weights` (otherwise emitted confidence is inert).

**Files likely modified:**
- `agents/sweep.md`, `agents/investigation.md`, `agents/cognito-intra-file-consistency.md`, `agents/cognito-consistency-checker.md` — add `confidence` to each output schema. *Reuse:* extend existing finding JSON schemas; the prose confidence gates in the two consistency agents already exist — formalize, don't reinvent.

**Testing Strategy:** Capture (or fabricate) a `combined-findings.json` with confidence values and re-run Phase 1's fixture harness to confirm the gate responds. Agent prompt changes are otherwise validated by a real review run.

**Integration Notes for Next Phase:**
- Phase 3 also edits `sweep.md` — it runs *after* this phase to avoid two concurrent writers on that file.
- Phase 5's `CONFIRMED/UNVERIFIED` pre-disposition label reads the same field emitted here; keep the label strings identical so buddy can surface them verbatim.

---

### Phase 3: Single live weight read (R3 — kill the split-brain)

**Scope:** Remove the split-brain where the sweep agent gates on weights *embedded in its prompt* while `post-process.ts` reads `weights.yaml` live. Have `sweep.md` read `weights.yaml` at runtime (drop the embedded `**Weight:**/**Effective:**` values and the `≥0.5/≥0.7` embedded-number gate); stop `rebuild-agents.md` from embedding weights. After this, a weight edit takes effect with recalibration alone — `/rebuild-agents` is no longer required for weights.

**Deliverables:**
- [ ] `agents/sweep.md`: replace "look up the rule's weight from the embedded rules below" (`:47`) with a live read of `knowledge/weights.yaml`; remove per-rule embedded weight literals; keep the tier-gate *logic* but source the numbers live.
- [ ] `commands/rebuild-agents.md`: remove the weight-embedding special case for sweep (`:71-76`); `/rebuild-agents` continues to regenerate *rule content* but no longer bakes in weights.
- [ ] Confirm post-process (`loadWeights()` `:175-185`) and sweep now read the **same** source of truth — document that weights.yaml is now the single authority.

**Minimum Verifiable Behavior:** Edit a rule weight in `weights.yaml`, run the sweep path **without** `/rebuild-agents`, and confirm the new weight governs the tier gate (a rule pushed below the important-tier threshold is now skim/dropped) — matching what `post-process.ts` already does live.

**Runtime Verification** *(checked by a review run — NOT by the implementation agent):*
- [ ] A `weights.yaml` edit changes sweep gating behavior on the next review with no `/rebuild-agents` invocation.
- [ ] `sweep.md` contains no embedded numeric weight literals after the change.

**MCP Integration Test Assertions:** N/A — markdown/agent-prompt change; verified by review run.

**Prerequisites:**
- Phase 2: `sweep.md` is edited there for confidence; sequence Phase 3 after it (one writer at a time on `sweep.md`).

**Files likely modified:**
- `agents/sweep.md` — live weights read; drop embedded values. *Reuse:* the live-read path mirrors `post-process.ts loadWeights()`; point sweep at the same file.
- `commands/rebuild-agents.md` — drop the sweep weight-embedding step.

**Testing Strategy:** Manual review run with a deliberately edited weight; assert behavior changed without a rebuild. Grep `sweep.md` for residual `**Weight:**`/`**Effective:**` literals (should be zero).

**Integration Notes for Next Phase:**
- After this phase, "recalibration is sufficient" is true — Phase 4's auto-recalibration can rely on weight edits taking effect immediately, with no rebuild step in the loop.

---

### Phase 4: Close the feedback loop (R2 — disposition-driven recalibration)

**Scope:** Feed operator dispositions into the EMA. Buddy recalibrates **immediately** from dispositions at Phase 2 (dismiss → signal `0`, kept → `1`, per `rule_id`/`source` recovered from `processed-findings.json`); non-buddy `review-pr` writes a `pending-calibration` marker to recalibrate later when `/learn-from-pr` runs. No fabricated signal — only real verdicts move weights. Recalibration runs **silently with a printed summary** (no opt-in prompt).

**Deliverables:**
- [ ] `commands/learn-from-pr.md` (and/or `calibrate.md`): add a **buddy-disposition signal source** alongside the existing Haiku→GitHub-comment matching (`§2.5.2/§2.5.4`). Read `buddy-session.json` dispositions, recover `rule_id`/`source` by joining `finding_ref`+`source` against `processed-findings.json`, derive signal (`dismiss=0`, kept=`1`), apply the existing EMA (`new = α·signal + (1-α)·old`, `α=0.25`). Update both rule weights and the new `source_weights`.
- [ ] `commands/review-pr-buddy.md` Phase 2: auto-invoke disposition recalibration at completion; print a summary of weight deltas; no prompt.
- [ ] `commands/review-pr.md`: on completion (near the REVIEWED.md sentinel `:477-504`), write a `pending-calibration` marker recording the cache dir / PR so a later `/learn-from-pr` consumes it.
- [ ] `/learn-from-pr`: consume and clear the `pending-calibration` marker when run.

**Minimum Verifiable Behavior:** Run (or replay) a buddy session containing at least one `dismiss`; confirm `weights.yaml` shows the EMA-updated weight for the dismissed rule/source (e.g. a clean-FP rule `0.7 → 0.525`) and the printed summary names the delta. Confirm a non-buddy `review-pr` run leaves a `pending-calibration` marker and that `/learn-from-pr` clears it.

**Runtime Verification** *(checked by a buddy/non-buddy run — NOT by the implementation agent):*
- [ ] After a buddy session with a dismissal, `weights.yaml` is EMA-updated for the recovered `rule_id`/`source`.
- [ ] Kept findings push their rule/source weight upward (signal `1.0`); dismissed push down (signal `0.0`).
- [ ] Non-buddy completion writes `pending-calibration`; `/learn-from-pr` consumes and removes it.
- [ ] No weight moves when a session has zero dispositions (no fabricated signal).

**MCP Integration Test Assertions:** N/A — command-orchestration + YAML mutation; verified by the runs above.

**Prerequisites:**
- Phase 1: `source_weights` must exist to be calibrated.
- Phase 3 (soft): with the split-brain gone, recalibrated weights take effect without a rebuild — closes the loop end-to-end.

**Files likely modified:**
- `commands/learn-from-pr.md`, `commands/calibrate.md` — add disposition signal source. *Reuse:* extend the existing EMA (`§2.5.4`) and `ema_alpha`; do not write a second calibration path.
- `commands/review-pr-buddy.md` — Phase 2 recalibration hook. *Reuse:* dispositions already captured in `buddy-session.json` (`finding_ref`+`source`); recovery join uses existing `processed-findings.json` `rule_id`/`source`.
- `commands/review-pr.md` — `pending-calibration` marker on completion.

**Testing Strategy:** Replay a captured `buddy-session.json` + `processed-findings.json` pair (real ones exist for PRs 16198/16627/16650/…) through the recalibration logic; diff `weights.yaml` before/after. Non-buddy path verified by marker presence/clearing.

**Integration Notes for Next Phase:**
- Phase 5's completeness sweep guarantees every finding is dispositioned before synthesis — which is also what makes this phase's signal complete. Note the coupling: abandoned/undispositioned findings yield no signal (correct — no fabrication), so Phase 5's escape hatch must still record explicit dispositions, not silently skip.

---

### Phase 5: Buddy resilience + UX

**Scope:** Remove the friction that truncates the disposition data Phase 4 depends on, and harden session persistence. All changes are in `commands/review-pr-buddy.md`. Largest phase by volume but lowest architectural risk.

**Deliverables:**
- [ ] **Serialization fix:** JSON-escape all paths written into `buddy-session.json` (the unescaped-Windows-backslash bug that broke resume in 16683). Verify reload survives Windows paths.
- [ ] **Completeness sweep:** before Phase 2 synthesis, assert no finding reaches synthesis undispositioned (dropped-finding re-ask bug, 16683).
- [ ] **Suppress `task-notification` echo** into the user stream.
- [ ] **Stable finding IDs:** one canonical ID scheme (no `F0`/`①`/`[F0]`/`Q2` drift).
- [ ] **Canonical disposition taxonomy:** enforce `Blocking / Important / Suggestion / Dismiss`, always all four, stable order (already present at `:145-154` — make it invariant, not drifting across versions).
- [ ] **Batch dispositions:** present a step's findings in one multi-disposition prompt by default instead of one-at-a-time.
- [ ] **Surface confidence pre-disposition:** label each finding `CONFIRMED`/`UNVERIFIED` (from Phase 2's emitted field) before asking for a disposition.
- [ ] **Early escape hatch:** offer "auto-disposition remaining at recommended severities" early in dismiss-heavy reviews (records explicit dispositions — see Phase 4 coupling note).
- [ ] **Already-commented handling:** record findings already commented and skip re-litigating severity; cross-check stale Copilot threads against later SHAs.

**Minimum Verifiable Behavior:** A buddy session resumes cleanly after writing a Windows path (no JSON parse error on reload); a multi-finding step presents one batched disposition prompt; each finding shows its `CONFIRMED/UNVERIFIED` label; the early escape hatch records explicit dispositions for all remaining findings.

**Runtime Verification** *(checked by a buddy run — NOT by the implementation agent):*
- [ ] `buddy-session.json` written with a Windows path reloads without a JSON error.
- [ ] No finding reaches Phase 2 synthesis undispositioned.
- [ ] No `task-notification` text appears in the user stream.
- [ ] Disposition prompt is batched per step and shows confidence labels.
- [ ] Escape hatch produces explicit dispositions (feeds Phase 4 signal).

**MCP Integration Test Assertions:** N/A — interactive command behavior; verified by a buddy run.

**Prerequisites:**
- Phase 2: the `CONFIRMED/UNVERIFIED` field must be emitted before it can be surfaced.
- Phase 4 (soft): the completeness sweep + escape hatch are what keep Phase 4's disposition signal complete; can land in either order but document the coupling.

**Files likely modified:**
- `commands/review-pr-buddy.md` — serialization, completeness sweep, stream hygiene, ID scheme, taxonomy invariant, batching, confidence surfacing, escape hatch, already-commented. *Reuse:* extend the existing Phase-1 chunk loop / checkpoint logic (`:74-182`) and disposition schema (`:204-217`); do not rewrite the walk.

**Testing Strategy:** Manual buddy run with a Windows-path-bearing cache dir and a dismiss-heavy chunk; verify resume, batching, labels, and escape-hatch disposition completeness. Replay the malformed 16683 session to confirm the serialization fix resolves it.

**Integration Notes for Next Phase:** Final phase. After this, the loop is closed end-to-end: complete disposition data (P5) → silent recalibration (P4) → weights that take effect immediately (P3) → applied to confidence-gated, all-source findings (P1+P2).

---

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC (only `**Related:**`), so there are no hard upstream dependencies to reality-check. The related specs (`cognito-pr-review-v2`, `buddy-guidance-enhancement`) are context, not blocking contracts.
