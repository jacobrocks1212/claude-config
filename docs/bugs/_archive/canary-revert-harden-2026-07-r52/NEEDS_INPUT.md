---
kind: needs-input
feature_id: canary-revert-harden-2026-07-r52
written_by: spec-bug
class: product
stub_origin: true
divergence: structural
next_skill: spec-bug
decisions:
  - Disposition of the harden-2026-07-r52 canary trip — revert, redesign, or close-as-noise
date: 2026-07-18
---

## Decision Context

### 1. Disposition of the harden-2026-07-r52 canary trip — revert, redesign, or close-as-noise

**Problem:** On 2026-07-18 the harness-change *canary* for intervention `harden-2026-07-r52` tripped. That intervention (commit `bc03240e`) shipped **operator-authorized mid-run budget + park controls** for the `/lazy-batch` family — the `--set-max-cycles` / `--set-park` / `--set-park-provisional` CLI actions that let an operator retune a live run without restarting it. A canary "trips" when a targeted friction signal moves the wrong way inside the post-ship observation window; here the targeted signal `event:gate-refusal` (an aggregate count of gate-guard refusals across the pipeline) rose **+57.9%** vs its frozen baseline (4.75 → 7.5 events/run), past the ±25% band. The canary only *flags and enqueues* — nothing was reverted automatically (design decision D4). This decision picks the disposition. **It is product-class: reverting removes a shipped operator-facing feature**, so the harness parks it for you rather than auto-accepting. The investigation (`SPEC.md`) found the trip is almost certainly a **false-positive of a coarse target signal**: the new controls' refusal paths emit a *different* telemetry event (`containment-refusal`) or none at all (`_die`), never `gate-refusal` — traced surface→source in `SPEC.md` → Proven Findings — so the shipped code is *mechanically incapable* of producing the +57.9% rise. It was a **band-only** trip with **zero** attributed fresh incidents, over a small 4-run window, on a **bare, undivided** `event:gate-refusal` target that the efficacy machinery treats as confounded by every co-shipped hardening round. The one residual doubt (Theory 2) is an *unevidenced* indirect regression via the change's marker-folding edits — no incident points at it, but the frozen band-only evidence cannot fully rule it out, which is why this is your call and not an auto-close.

**Options:**
- **Close-as-noise + tune the canary (Recommended)** — Declare the trip a false-positive, disposition the bug `Won't-fix` (keep the shipped controls), and spin off a follow-up to make the signal precise: re-declare the intervention's `target_signal` as a specific `event:gate-refusal/<signature>` sub-signal (or a `kpi:` target) and/or widen the band, so this coarse aggregate stops false-tripping. **Tradeoff:** lowest cost and reversible; keeps a feature whose regression is mechanically un-attributable to it. Risk: if the unevidenced Theory-2 indirect regression is real, close-as-noise defers catching it to the ordinary ~20-run efficacy review (which still runs — a tripped canary does not skip the efficacy verdict). This is the disposition the `canary-trip-precision` KPI is designed to record. **The tuning follow-up is contingent on this option and would be spun off via `--enqueue-adhoc` when chosen — not created now.**
- **Redesign** — Keep the controls but change something about them or their signal wiring to address whatever the operator believes the trip surfaced (e.g. make the new mutators emit into the tracked signal on purpose, or split the intervention's hypothesis). **Tradeoff:** bounded corrective work; only warranted if you read the +57.9% as a *real* effect worth engineering against. Given the trace shows no mechanical link, redesign risks building against noise.
- **Revert** — `git revert bc03240e` across the **whole coupled pair** (`user/skills/{lazy-batch,lazy-bug-batch}/SKILL.md` + `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`) and end with a green `python3 user/scripts/lazy_parity_audit.py --repo-root .`. **Tradeoff:** removes the mid-run budget/park controls entirely — a real operator-facing capability regression — to eliminate a signal the change provably does not drive. Highest blast radius; only justified if you no longer want those controls for an independent reason.

**Recommendation:** Close-as-noise + tune the canary — the tripped signal is traced-un-attributable to the shipped change, the trip was band-only with zero incidents on a known-coarse target, and reverting would sacrifice a working operator feature to silence provable noise; the precise-signal follow-up prevents recurrence.
