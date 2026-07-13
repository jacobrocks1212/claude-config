# RESEARCH_SUMMARY — lazy-batch-skill-deflation

Inline recon performed 2026-07-12 directly against the working tree (no external research —
this feature has no `docs/gemini-sprint/` staging by design, per this repo's convention for
low-research-volume harness work; see `CLAUDE.md` "Research resume in claude-config").

## Re-verified baseline (2026-07-12, before any edit this session)

`wc -c` / long-line census (`>500` chars, matching the SPEC's method):

| File | Bytes | Long lines |
|------|------:|-----------:|
| `user/skills/lazy-batch/SKILL.md` | 255,725 | 148 |
| `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | 208,950 (post minor drift since SPEC's 206,395) | 125 |
| `user/skills/lazy-bug-batch/SKILL.md` | 101,387 | 36 |
| `user/skills/lazy/SKILL.md` | 28,599 | 14 |
| `user/skills/lazy-status/SKILL.md` | 9,790 | 1 |

The canonical file grew ~2.3KB / 1 additional long line between the SPEC's 2026-07-11 measurement
(251,832 B) and session start (255,725 B) from unrelated concurrent commits — confirms the SPEC's
"+57%/4wk, never reverses without a gate" framing is not a one-time anomaly; it kept growing
between the SPEC being drafted and this session executing against it. This is itself the
strongest argument for shipping Phase 3 (the ratchet) even before the full content diet lands.

## Finding: the four named hotspots are denser / more load-bearing than the SPEC's optimistic estimate

The SPEC characterizes §1d.0 (runtime pre-boot), §1c.5 (pseudo-skill handling), §1b/§1c.6
(terminal handling / PushNotification policy), and the model-selection prose as "~70%/~55%/~50%
restatement of script internals the orchestrator doesn't need." Full-text reading of these
sections this session (lines 383–822 of the canonical, ~700 lines / ~110KB) found this estimate
does **not** hold uniformly:

- §1d.0 in particular (the `--ensure-runtime` M4 verdict routing, ~34KB) carries a long sequence
  of **distinct, individually-incident-driven operational rules** — the cold-compile patient-wait,
  the pre-Vite boot-liveness patient-wait, the soft owned-unverified READY case, the sidecar-pipe
  readiness dimension, the guard-takeover long-build contract — each with its own named defect
  history and its own routing consequence. These are not restatement of `ensure_runtime`'s
  internals so much as **the orchestrator's routing table itself**, spelled out one distinguishable
  case at a time because the state space is genuinely large (5+ named states, several with
  sub-cases). Collapsing these to a terse routing table risks silently dropping a case an
  orchestrator subagent currently handles correctly only because the case is spelled out.
- §1c.6 (terminal handling + PushNotification policy, ~66 lines / ~19KB) is similarly dense:
  each terminal reason (`blocked`, `needs-input`, `needs-ratification`, `all-features-complete`,
  `queue-exhausted-*`, `device-queue-exhausted`, `host-capability-saturated`, ...) carries its own
  one-paragraph dispatch rule. The SPEC's proposed "5-row routing table" undercounts — the real
  surface is 15+ distinct terminals, several with their own multi-step sub-protocol (the
  option-(b) unified-driver fallthrough block alone is ~4 paragraphs of genuinely necessary
  routing logic, not narration).
- §1c.5 (pseudo-skill handling, ~45 lines / ~18.5KB) is closer to the SPEC's estimate — a
  meaningful fraction really is restatement of what `--apply-pseudo` does internally — but even
  here the T4 output-template binding and the `prev_cycle_signature` update rule are
  orchestrator-side contract, not restatable.

**Consequence for this session's scope:** a bulk mechanical excision of these three hotspots
under time pressure, without a dedicated per-rule rule-preservation checklist audited line by
line (the SPEC's own stated acceptance gate), is the single highest-risk way to violate this
feature's own **HARD SAFETY RAIL (a)** — behavior-preservation on the harness's most
safety-critical, production-driving prompt. This session scoped Phase 1 execution to the ONE
hotspot that genuinely matches the SPEC's characterization end-to-end (the model-selection
paragraph — see PHASES.md Phase 1) and left the three dense hotspots for a dedicated future
session that can build and audit the full rule-preservation checklist per the SPEC's Method
section, rather than rushing a risky bulk edit. This finding itself is worth feeding back into
the SPEC's Phase 1 sizing (the "~1–2 sessions" estimate for Phase 1 should probably be nearer
2–3 given the checklist granularity this recon surfaced).

## Dedup candidates confirmed safe (script-owned, no orchestrator restatement needed)

- **Model-selection prose** (`user/skills/lazy-batch/SKILL.md`, `lazy-batch-cloud/SKILL.md`) —
  confirmed pure restatement: the entire rule is "copy `cycle_model` verbatim; the script already
  decided." Excised this session (Phase 1 partial) — see PHASES.md.
- The rest of the SPEC's dependency list (`lazy-state.py`/`lazy_core.py` verdict surfaces, the
  probe's `cycle_prompt`/`cycle_prompt_ref`/`cycle_model`/`sub_skill_args` fields, pseudo-skill
  `--apply-pseudo`, `SANCTIONED_STOP_TERMINAL`) are confirmed as implemented, stable contracts —
  no drift found between the prose's description and the current `lazy_core.py` behavior as of
  this session (spot-checked against `user/scripts/CLAUDE.md`'s own up-to-date documentation of
  `--ensure-runtime`, `SANCTIONED_STOP_TERMINAL`, and the pseudo-skill classifier).

## Follow-up items (i)–(iii) recon

- **(i)** Confirmed both `long-build-ownership.md` and `cycle-prompt-addenda.md` are AlgoBooth-only
  files (`repos/algobooth/.claude/skill-config/`), referenced as bare prose pointers with no
  fallback from four sites across `lazy-batch/SKILL.md` (×2), `lazy-bug-batch/SKILL.md` (×1), and
  `_components/lazy-dispatch-template.md` (×1) — exactly the four `SUPPRESSIONS` entries in
  `lint-skill-config.py`. Fixed this session (see PHASES.md Phase 5).
- **(ii)** Confirmed via `docs/features/efficacy-signal-integrity/NEEDS_INPUT_PROVISIONAL.md`
  (ratified option A for D4) that the wanted edit is: mirror the existing "TWO-SCOPE flush"
  pattern (already used for `efficacy-eval.py` intervention records) to also regenerate
  `docs/kpi/SCORECARD.md` rooted at the claude-config checkout at the end-of-run flush, in
  ADDITION to (not replacing) the existing per-cycle per-repo-registry-gated regen. Implemented
  this session in both `lazy-batch` and `lazy-batch-cloud` (mirrored per the coupled-pair table);
  `lazy-bug-batch` carries no KPI-scorecard mention at all, so no mirror is owed there.
- **(iii)** Verified: the harness-change canary watch (`efficacy-eval.py --canary`) is already
  wired at the same end-of-run flush in both `lazy-batch` (3 mentions) and `lazy-batch-cloud`
  (5 mentions, incl. the cloud-specific TWO-SCOPE note). No duplication risk; no action taken.

## Coupled-pair mirroring status (D4 fallback)

Per this feature's D4 (LOCKED, fallback path — `coupled-pair-generation`'s premise of
token-substituted derived bodies is refuted, most derived blocks are `verbatim` overlay
entries): every edit this session was hand-mirrored into the coupled derived file(s) per the
existing divergence tables, then `generate-coupled-skills.py --extract` was re-run to refresh
the overlay JSONs and `--check` re-verified green. See PHASES.md Phase 4/5 for the per-edit
mirror table.
