# Weight Calibration & Review-Feedback Loop — Investigation Spec

> The review pipeline over-produces (operator dismisses ~73% of surfaced findings), weights only
> govern one of four finding sources, weight edits are half-applied due to a split-brain between the
> sweep agent and post-processor, and the richest operator-feedback signal (buddy dispositions) is
> never fed back into calibration.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-06-22
**Placement:** `docs/specs/weight-calibration-feedback-loop/` (cognito-pr-review plugin, v2.7.0)
**Related:** `docs/specs/cognito-pr-review-v2/`, `docs/specs/buddy-guidance-enhancement/`, `commands/learn-from-pr.md`, `commands/weights.md`, `commands/rebuild-agents.md`

<!-- Investigation complete: root causes proven with file:line citations; design forks decided
     with the operator. Ready for /plan-bug or /fix. -->

---

## Source Data

Mined from operator (Jacob) usage of `/cognito-pr-review:review-pr-buddy`:

- **9 persisted buddy sessions** — paired `buddy-session.json` (operator dispositions) + `processed-findings.json` (system findings) under `cog-docs/docs/{bugs,features}/*/.pr-review/pr-cache/<pr>/`. PRs: 16198, 16627, 16650, 16653, 16674, 16683, 16687, 16693, 16694.
- **~38 buddy-run session transcripts** — `~/.claude/projects/C--Users-JacobMadsen-source-repos-Cognito-Forms*/*.jsonl`.

---

## Verified Symptoms

1. **[VERIFIED]** The operator dismisses the large majority of surfaced findings — **40 of 55 dispositioned (73%) dismissed**, only 15 kept, across the 9 sessions. The tool over-produces relative to what the reviewer considers actionable.
2. **[VERIFIED]** Dismiss rate is worst for `sweep` (88%, 15/17) but the largest dismissal *volume* is `investigation` (17) + `intrafile` (6) — sources that **bypass weighting entirely**.
3. **[VERIFIED]** Weight edits do not fully take effect without `/rebuild-agents` (operator's side-question; confirmed split-brain below).
4. **[VERIFIED]** Buddy walks are routinely abandoned mid-review ("just complete the review now", "fast track the rest, no input from me") — 16627, 16674, 16683, 16687.
5. **[VERIFIED]** A `buddy-session.json` was written with malformed JSON (unescaped Windows backslash), breaking checkpoint reload and forcing a re-walk the operator declined (16683, 7/15 findings dispositioned).
6. **[REPORTED]** Investigation findings were grounded against `main` rather than the PR diff, mislabeling a live `priority:true` branch as dead code (16683).

---

## Evidence Collected

### Source Code (all citations: plugin v2.7.0 source under `claude-config/user/plugins/local-tools/plugins/cognito-pr-review/`)

**Weights gate only one source.** `scripts/post-process.ts`:
- `:219 computeEffectiveWeight()` — `rule_weight × category_multiplier`, applied **only to sweep findings**.
- `:320, :346, :372` — investigation / intrafile / reuse findings hardcoded `effective_weight: 1.0`.
- `:399 step2_dropBelowThreshold` — `if (f.source === "sweep" && f.effective_weight < MIN_EFFECTIVE_WEIGHT)` (`:167` `MIN_EFFECTIVE_WEIGHT = 0.3`). Non-sweep sources are never threshold-dropped.
- `:427` — "Opus-lane sources (investigation, reuse, intrafile) beat sweep" in ranking.

**Split-brain weights.** The sweep agent filters at *generation* time against weights **embedded in its prompt** — `agents/sweep.md` contains literal `**Weight:** 0.7 | **Effective:** 0.70` per rule, and the tier gate (`≥0.5` important / `≥0.7` skim, `sweep.md:42-43`) reads those embedded numbers (`sweep.md:47` "Look up the rule's weight from the embedded rules below"). `commands/rebuild-agents.md:75` regenerates them from `weights.yaml`. Meanwhile `post-process.ts:177` reads `weights.yaml` live. ⇒ A weight edit is honored by post-process's `0.3` floor but ignored by the sweep agent's tighter `0.5/0.7` gate until `/rebuild-agents` runs.

**Both pipelines share the weight system.** `commands/review-pr-buddy.md:47` — Phase 0 "delegates entirely to `commands/review-pr.md` Steps 1–8". So sweep + post-process (and thus weights) run identically for buddy and non-buddy.

**Calibration exists but reads the wrong signal.** `commands/learn-from-pr.md` §2.5.4 implements EMA: `new_weight = α·signal + (1-α)·old_weight`, `α = 0.25` (`weights.yaml:4 ema_alpha`), `signal = 1.0` TP / `0.0` FP. TP/FP are derived by Haiku-matching findings to **GitHub comments** (§2.5.2). Grep confirms **neither `learn-from-pr.md` nor `calibrate.md` references `buddy-session.json` or dispositions** — the operator's explicit per-finding verdicts are never consumed.

### Quantitative — system vs. operator (9 sessions)

Per-rule sweep signal (only weight-addressable findings; data is thin, mostly n=1):

| Rule | Keep | Dismiss | Read |
|---|---|---|---|
| `verify-assertions-match-behavior` | 2 | 1 | Earns its keep — **do not lower** |
| `loading-state-finally` | 0 | 1 | clean FP |
| `method-name-reflects-behavior` | 0 | 1 | clean FP |
| `update-all-callers-on-signature-change` | 0 | 1 | clean FP |
| `defensive-null-checks` | 0 | 1 | clean FP |
| `reuse-service-duplication` | 0 | 1 | clean FP |
| `consistent-indentation` | 0 | 1 | clean FP |
| `consolidate-parameterized-tests` | 0 | 1 | clean FP |
| `consistent-helper-usage` | 0 | 1 | clean FP (currently 0.775) |

EMA note: one dismissal moves `0.7 → 0.525`, still ≥ the `0.5` important-tier threshold — two consecutive FPs are needed to silence a rule. The EMA is intentionally conservative; thin single-datapoint evidence barely moves the needle. **No weight changes applied — pending operator approval.**

### Friction Inventory (from transcripts)

| # | Friction | Evidence (PR) | Implied fix |
|---|---|---|---|
| 1 | Disposition question spam — 6–16 one-at-a-time asks/session; batching inconsistent | all | Batch a step's findings into one multi-disposition prompt by default |
| 2 | Inconsistent disposition vocabulary/order across versions (`Keep/Will-comment/Dismiss/Add-own` vs `Blocking/Important/Suggestion/Dismiss`; "Blocking" sometimes omitted); drifting finding IDs (`F0`, `①`, `[F0]`, `Q2`) | all | Fix one canonical taxonomy + stable finding IDs |
| 3 | Orientation/teach narrates internal state, not user action / why-the-change / violated invariant | 16574, 16683 | Teach the user-facing action and the invariant a finding claims is violated |
| 4 | Confidence not surfaced; operator must demand "spawn subagents to confirm these are real" | 16687, 16694 | Label findings CONFIRMED/UNVERIFIED before dispositioning |
| 5 | No early auto-disposition escape hatch for dismiss-heavy reviews | 16627, 16674, 16683, 16687 | Offer "auto-disposition remaining at recommended severities" early |
| 6 | Malformed `buddy-session.json` breaks resume; dropped findings re-asked; `<task-notification>` leaks into stream | 16683 | Escape paths on write; completeness sweep before synthesis; suppress task-notification echo |
| 7 | Investigation reads `main`, not the PR diff | 16683 | Ground investigation against PR head (same class as the `GetFieldPath` bug, PR #16543) |
| 8 | Re-litigates already-commented findings; stale Copilot threads not reconciled against later commits | 16622, 17890 | Record "already commented" and skip; cross-check thread resolution vs. subsequent SHAs |

### Dismiss-reasoning patterns (calibration signal)

Recurring grounds the operator used to reject findings: pre-existing / not-a-regression; author's counter-case / intentional; legacy-only / unreachable under feature flag; verified-safe by lifecycle scoping (per-page-reload, idempotent); reuse premise false (no existing shape to reuse); sweep hedge-phrases ("may produce…") over-firing; behavior-neutral style/naming/symmetry nits.

---

## Proven Findings (root causes)

1. **Weighting is scoped to sweep only.** Investigation/intrafile/reuse findings — the bulk of dismissals — cannot be tuned because `post-process.ts` pins them to `1.0` and never threshold-drops them.
2. **Split-brain weight reads** mean recalibration is half-applied until `/rebuild-agents`.
3. **The feedback loop is open.** Operator dispositions (the cleanest TP/FP signal, with recoverable `rule_id`) are captured in `buddy-session.json` but never fed to the EMA; calibration only ever runs manually against noisier GitHub comments.
4. **`buddy-session.json` serialization is unsafe** (unescaped Windows paths) → resume fragility → walk abandonment.
5. **UX friction** (question spam, vocabulary drift, weak orientation, no confidence labels, no escape hatch) compounds abandonment, which truncates the very disposition data calibration needs.

---

## Reuse Ledger

| Capability | Existing system (cite) | Verdict | Confirmed |
|---|---|---|---|
| EMA weight update | `learn-from-pr.md` §2.5.4 | **Extend** — add buddy dispositions as a signal source | R5 |
| Effective-weight compute | `post-process.ts:219` (sweep only) | **Refactor** — generalize to all sources | R5 |
| Source bypass | `post-process.ts:320/346/372/399` | **Refactor** — the R1 gap | R5 |
| Weight store | `weights.yaml` (rule + category multipliers) | **Extend** — add source-level weights + confidence | R5 |
| Sweep agent weights | embedded in `sweep.md` (`/rebuild-agents`) | **Refactor** — live read | R5 |
| Disposition capture | `buddy-session.json` schema | **Reuse as-is** (after serialization fix) | — |
| Confidence ranking | `post-process.ts` tier > severity > effective_weight | **Extend** — fold per-finding confidence into the gate | R5 |

---

## Proposed Fix Direction (operator-confirmed forks, 2026-06-22)

- **R1 — Whole-pipeline weighting:** add **source-level weights** to `weights.yaml` (investigation/intrafile/reuse) **and** have each agent emit a `0–1` confidence; gate on `weight × confidence` for every source (replaces the hardcoded `1.0`). A low-confidence investigation finding can drop without silencing the source.
- **R3 — Unify to a single live read:** the sweep agent reads `weights.yaml` at runtime instead of embedded values, so **recalibration alone is sufficient** — no `/rebuild-agents` step, one source of truth. (Removes the split-brain root cause.)
- **R2 — Auto-recalibrate on completion, asymmetric signal:** **buddy** recalibrates immediately from dispositions (dismiss → signal 0, kept → 1, per recovered `rule_id`/source); **non-buddy** writes a `pending-calibration` marker and recalibrates later when `/learn-from-pr` runs against GitHub comments. No fabricated signal.
- **Serialization & resume:** JSON-escape all paths in `buddy-session.json`; add a completeness sweep so no finding reaches synthesis undispositioned; stop echoing `<task-notification>` into the user stream.
- **Investigation grounding:** diff against PR head, not `main`.
- **UX:** one canonical disposition taxonomy (`Blocking / Important / Suggestion / Dismiss`, always all four, stable order) + stable finding IDs; batch per-step dispositions into one prompt; surface `CONFIRMED/UNVERIFIED` confidence pre-disposition; offer an early "auto-disposition remaining at recommended" escape hatch; record "already commented" findings without re-litigating severity.

**Weight recommendation (NOT yet applied):** nudge the 8 clean-FP sweep rules above per the existing EMA (`0.7 → 0.525`; `consistent-helper-usage 0.775 → 0.581`); leave `verify-assertions-match-behavior` at `0.7`. Prefer wiring R2 so this happens automatically from disposition data rather than hand-setting.

---

## Affected Area

| Component | Files | Impact |
|---|---|---|
| Post-processing | `scripts/post-process.ts` | Generalize weighting to all sources; fold in confidence |
| Weight store | `knowledge/weights.yaml` | Add source-level weights + `ema_alpha` reuse |
| Calibration | `commands/learn-from-pr.md`, `commands/calibrate.md` | Add buddy-disposition signal source; auto-invoke on completion |
| Buddy command | `commands/review-pr-buddy.md` | Serialization fix, completeness sweep, recalibration hook, UX |
| Non-buddy command | `commands/review-pr.md` | `pending-calibration` marker on completion |
| Sweep agent | `agents/sweep.md` | Live weights read (drop embedded values) |
| Investigation agent | `agents/investigation.md` | Diff-vs-head grounding; emit confidence |
| Other agents | `agents/{intrafile,consistency-checker,...}.md` | Emit `0–1` confidence |

---

## Open Questions

- Source-level default weights for investigation/intrafile/reuse — start at `0.9 / 0.7 / 0.7`, or calibrate from the 9-session dismiss rates (investigation 0.32 keep, intrafile 0.33 keep, reuse 0.67 keep)?
- Confidence scale — discrete (`CONFIRMED`=1.0 / `UNVERIFIED`=0.5) or continuous `0–1` per agent?
- Should buddy auto-recalibration require an explicit operator opt-in per session, or run silently at Phase 2?
- Does folding confidence into the gate change the `MIN_EFFECTIVE_WEIGHT` floor, or stay at `0.3`?
