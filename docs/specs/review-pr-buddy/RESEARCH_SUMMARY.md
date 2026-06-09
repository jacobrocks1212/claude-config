# Research Summary — Interactive PR Review Buddy & Reuse-Candidacy Stage

**Research conducted:** No — explicitly skipped (`/spec (no research)`).

This feature was specced without a Gemini deep-research pass. It is an internal-tooling change to the
`cognito-pr-review` plugin and the `/spec` reuse component — there is no external prior art or
product-UX question that research would resolve. The baseline is grounded entirely in **direct source
reading** during the originating brainstorm:

- The full `review-pr` pipeline (`commands/review-pr.md`, 12 steps) and its agents
  (`journey-planner`, `triage`, `investigation`, `sweep`, `synthesizer-v2`, the orphaned
  `cognito-consistency-checker`).
- The deterministic scripts (`prep-pr.ts`, `aggregate-findings.ts`, `post-process.ts`) and the
  `knowledge/rules` + `weights.yaml` corpus.
- The `/spec` reuse-first-discovery component built the prior session.

**Key findings driving the design (all code-grounded, see SPEC § Reuse Ledger):**

1. The journey-planner's **Manual Review Guide** is already a human-walkthrough script — the buddy
   performs it rather than inventing one. (reuse-as-is)
2. Reuse/duplication detection ~60% exists but is split between an **orphaned** `cognito-consistency-checker`
   (not in the pipeline) and a shallow file-vs-baseline "Consistency Pass" in investigation — neither
   asks the capability-level reuse question. (refactor + wire-in)
3. The **cache boundary** dictates placement: only investigation has local-codebase access, so the
   reuse stage must inherit that carve-out; sweep (cache-only) can only flag heuristics and escalate.
4. The findings schema (`aggregate-findings.ts` / `post-process.ts`) and rule corpus extend cleanly
   to a new `reuse` source/category — no new weighting machinery needed.

**Open questions** (carried into PHASES, not research-answerable): buddy Phase-0 delegation vs.
duplication; grow-vs-supersede the orphaned checker; reuse-verdict → severity mapping in post-process.

No pitfalls surfaced that block the baseline.
