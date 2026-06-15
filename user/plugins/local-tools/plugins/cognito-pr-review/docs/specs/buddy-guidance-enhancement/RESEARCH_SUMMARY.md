# Research Summary — Buddy Guidance Enhancement

Source: `RESEARCH.md` (Gemini Deep Research, 2026-06-15). Discovery-weighted, optimizing for defect detection by an **expert** reviewer.

## Headline: the research is sharply critical of our current loop ordering

The single strongest, most counterintuitive finding: **our per-chunk loop is ordered backwards for an expert.** We currently **Teach → Surface findings → Ask → Capture verdict.** The evidence says, for an expert, this both (a) imposes expertise-reversal harm (front-loaded teaching) and (b) induces anchoring/automation bias (findings shown before independent judgment), causing the reviewer to focus on the shallow issues the tool *did* catch and miss the deep logic bugs the tool inherently *misses*.

## Key findings relevant to our baseline

- **Anchoring / automation bias (strong, multi-source).** Showing tool findings before the human forms an independent judgment anchors them to superficial hits. LLM static analysis suffers "Abstraction Bias" (NDSS 2026, Familiar Pattern Attacks) — it overlooks deterministic logic errors (off-by-one, flipped boolean) hidden in familiar boilerplate. Real-world LLM review acceptance is only ~7–8% direct (RevMate study, Mozilla/Ubisoft, 587 reviews), though ~15–20% more are "valuable tips." Conclusion: **never let the AI's findings frame the human's first pass; reveal them as reconciliation after.**
- **Expertise-reversal effect (strong, CLT canon).** Front-loaded explanations/walkthroughs help novices but *harm* experts by adding extraneous load that conflicts with their schemas. Shift from *telling* to *eliciting*; explanations on-demand only.
- **Empirical ceilings (SmartBear/Cisco, ~2006, widely replicated).** Defect density drops sharply past **400 LOC**; best detection under **200 LOC** (70–90% of defects). Inspection rate should stay **<300–500 LOC/hr**. Detection collapses after **60 min** (max 90) of sustained review — vigilance decrement, physiological not motivational.
- **Partition unit (Tier 2, moderate evidence).** File/directory grouping is suboptimal; 29–39% of commits are "tangled." Semantic/behavioral/dependency clustering (SmartCommit, EpiceaUntangler, Tao MSR2015) improves comprehension at equal time. Review one behavioral thread across architectural layers at a time.
- **Tests ordering (controlled experiment, Bacchelli ICSE2019).** "Tests last" is contradicted — Test-Driven Code Review (tests first/alongside) finds more defects in tests and gives the reviewer an executable spec/oracle before reading implementation. Late tests get reviewed when cognition is most depleted.
- **Checklists → PBR (multiple inspection studies).** Checklists beat ad-hoc reading (up to ~66% better), but Perspective-Based Reading (adopt a persona: security auditor, DBA, perf tester) beats generic checklists by focusing attention and limiting load. Socratic questions should be **predictive/boundary-condition** ("if this txn is interrupted before commit, what happens?"), not descriptive.
- **Disposition vocabulary.** Our keep/dismiss/will-comment/add-own is not severity-aware. Industry standard (Google/Microsoft/GitLab, Conventional Comments) is **Blocking / Important / Suggestion(Nit)** + Dismiss. Only ~15% of review comments are logic defects; severity labels filter noise.
- **AI role scoping.** Use the AI for mechanical triage, cross-file dependency mapping, context-on-demand, and generating Socratic questions — **not** as the arbiter of business-logic correctness. Human remains sole arbiter of algorithmic integrity.

## Ideas to adopt from the research

**Tier 1 (well-supported, adopt):** delay tool findings to a post-judgment reconciliation step; enforce/respect 400 LOC + 60 min ceilings; severity-based disposition taxonomy; remove mandatory Teach (opt-in context).
**Tier 2 (try and measure):** semantic/behavioral partitioning; tests alongside code; PBR personas + predictive Socratic prompts.

## Concerns / tensions to resolve

- **"Verdict before findings" doesn't map cleanly onto our model**, because our "verdict" *is* the disposition of pre-computed findings. A literal reorder is incoherent. The sane synthesis is a **two-pass chunk loop**: Pass 1 = reviewer reads cold + records own observations (no findings shown); Pass 2 = reveal tool findings as reconciliation + disposition them. This needs an explicit decision.
- **Orientation vs. teaching.** Expertise-reversal targets explaining *code the expert can read*. Orienting to a chunk's *intent/objective* (which the reviewer didn't author) may still be valuable. Decision: keep a one-line objective orientation, drop deep teaching to opt-in.
- **Cost of semantic partitioning.** Full AST/data-flow untangling (SmartCommit-style) is a large build. A prompt-level "cluster by behavior/dependency narrative" instruction to the journey-planner is cheap and captures most of the benefit. Decision: how far to push.
- **Pacing enforcement for a solo expert.** Hard-halting an expert at 60 min/400 LOC may be paternalistic; chunk-size *splitting* (partitioning rule) is uncontroversial, but session *halting* should likely be advisory. Decision needed.

## Baseline decisions to revisit

Open Questions in SPEC.md map 1:1 to the decisions surfaced post-research below (loop ordering, teach, findings timing, partition unit, tests ordering, chunk/session ceilings, Socratic/PBR, disposition taxonomy).
