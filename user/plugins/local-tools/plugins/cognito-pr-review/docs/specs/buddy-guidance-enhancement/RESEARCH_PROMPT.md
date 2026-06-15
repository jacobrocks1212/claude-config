## Project context

We are designing an enhancement to an AI-assisted, interactive code-review tool called **"buddy review."** A large language model agent walks a single human reviewer through a pull request (PR) one section at a time. For each section it (a) explains what changed and why, (b) shows pre-computed findings from automated analysis tools, (c) poses questions, and (d) records the reviewer's decision on each finding. The reviewer is an **experienced senior software engineer** reviewing PRs in a large, mixed-age C#/TypeScript codebase. The goal is to **maximize detection of real defects per PR** (thoroughness-first; speed is secondary), while building an accurate mental model of the change. We want to know whether our current "partitioning" (how the PR is sliced into review units and ordered) and "guiding" (the interaction loop that walks the reviewer through each unit) reflect best practices, and how to improve them.

---

# Research-backed best practices for (1) reviewing pull requests and (2) guiding an expert reviewer through a PR

## Research question

What does the empirical and practitioner literature say about how to **partition** a code change into review units (and order them), and how to **guide** an experienced reviewer through those units, so as to **maximize detection of real defects** and build a correct mental model of the change? Where our current design (below) diverges from the evidence, identify the divergence, the strength of evidence against it, and the better-supported alternative. Treat this as **discovery-weighted**: surface the strongest research-backed approaches even when they differ from what we do.

## Context — the system being improved

- **Audience:** one experienced senior engineer per review. Not a novice; not a group. Optimize for that expert. Note explicitly where guidance for experts differs from guidance for novices (e.g. expertise-reversal / redundancy effects), since most "how to review code" advice is written for general/novice audiences.
- **Medium:** a turn-by-turn conversational agent in a terminal. It can teach, ask questions, reveal or withhold tool findings, control ordering and pacing, and capture structured decisions. It is NOT a static checklist or a diff viewer — it can adapt sequencing and dialogue.
- **PR shape:** varies from a few files to many; backend C# services + Vue/TypeScript frontend; long-lived codebase with legacy seams. Changes mix core logic, API surface, generated types, and tests.
- **Automated findings already exist** before the human walk begins: bug/edge-case findings, rule/pattern hits, and code-reuse/duplication flags, each attached to specific files.

## Baseline being validated

**Partitioning (how the PR is sliced and ordered):**
- The PR is divided into ordered steps, each a *logical group of files* (not by directory).
- Each step lists: the files, "what to look for," and "key questions."
- Order: **core/critical changes first, tests last.** Files are tiered Critical / Important / Skim.
- On re-review: changed-since-last-iteration files first, then files with unresolved comments, then unchanged-critical, then the rest.

**Guiding (the per-unit interaction loop):**
1. **Teach** — the agent explains what changed in this unit and why it matters, before the reviewer reads.
2. **Surface findings** — the agent shows the pre-computed automated findings for this unit.
3. **Socratic prompt** — the agent poses the unit's "key questions" plus 1–2 of its own; it does not answer them.
4. **Capture verdict** — for each finding the reviewer picks: keep / dismiss / will-comment / add-own-observation.
5. **Checkpoint & advance** to the next unit.

## Research areas

Investigate each area; cite empirical studies (controlled experiments, large-scale mining studies at Google/Microsoft/Meta, eye-tracking and inspection research) where they exist, and clearly distinguish *empirical evidence* from *practitioner opinion/convention*.

### A. Code-review effectiveness fundamentals
- The classic software-inspection literature (Fagan inspections, Gilb/Graham, the "optimal" inspection rate and review-size findings) and what survives in the modern lightweight-PR era.
- Modern large-scale findings on what actually correlates with defect detection in PR review (review size/LOC, number of files, review duration, number of reviewers, author response). Quantify where possible (e.g. defect-detection vs. LOC curves, the often-cited ~200–400 LOC and ~60-minute thresholds — verify, date, and source these).
- Fatigue / vigilance decrement over a review session: how detection degrades with volume and time; recommended session length and break cadence.

### B. Partitioning — the review unit and its ordering
- What is the best *unit* of review: whole-file, hunk/change-set, by call-graph/dependency cluster, by behavior/objective, by risk, or "story-ordered" reorderings of the diff? Evidence for each.
- Evidence on **reordering the diff** for comprehension (e.g. presenting changes in a logical/dependency/narrative order vs. file-alphabetical or VCS order). Tools/research on "untangling" composite changes and reviewing one concern at a time.
- Ordering: core-first vs. data/control-flow order vs. risk-first vs. dependency order. Should tests be reviewed **last**, or **alongside** the code they exercise (tests as a spec/oracle for the change)?
- Evidence-based ceilings on the size of a single review unit (lines/files) before comprehension and defect detection drop, and how to split oversized units.

### C. Guiding an expert — interaction model, cognitive load, bias
- **Cognitive Load Theory & the expertise-reversal effect:** for an expert, does front-loading an explanation ("Teach" before they read) add value or cause redundancy/expertise-reversal harm? What's the right ratio of *telling* vs. *asking* for experts vs. novices?
- **Checklists & guided questions vs. open/ad-hoc reading:** does a checklist or perspective-/role-based reading (PBR) reliably improve defect detection, and by how much? Does effectiveness decay (checklist fatigue, rote-ing)? What makes a checklist/question set effective vs. noise?
- **Anchoring / automation bias:** if automated findings are shown *before* the reviewer forms an independent judgment, does this anchor them and *reduce* independent defect detection (missing what the tool missed)? Evidence on optimal timing of revealing tool output: before, during, or after the human reasons. Confirmation/automation-bias literature applied to static-analysis and AI-suggested findings.
- **Active vs. passive comprehension:** evidence for techniques that build a correct mental model — self-explanation, prediction ("what do you expect this function to return?"), summarization, asking the reviewer to restate intent, retrieval practice — and which transfer to expert code comprehension specifically.
- **Question design / Socratic method in technical mentoring:** what kinds of questions actually surface defects vs. feel like busywork; the risk of leading questions; how many questions per unit before diminishing returns.
- **Pacing & flow:** should the guide enforce pacing, chunk caps, or breaks, or let the expert self-pace? Evidence on interruption/checkpointing cost vs. benefit.

### D. Capturing reviewer judgment
- Is a fixed disposition vocabulary (keep / dismiss / will-comment / add-own) well-supported, or is there a better model for capturing reviewer decisions (e.g. severity, confidence, blocking vs. non-blocking, nit/suggestion/issue taxonomies used at scale)?
- Conventions for comment taxonomy and severity labeling in industrial review tools, and whether explicit severity/confidence capture improves downstream outcomes.

### E. AI/LLM-assisted and "buddy"/pair-review specifically
- Prior art in AI-assisted code review and AI pair-reviewing: what interaction patterns have been tried (summarize-then-review, walkthrough generation, guided tours of a change), and what evidence (even preliminary) exists for their effect on comprehension or defect detection.
- "Guided tour" / code-walkthrough tooling (e.g. narrative tours of a changeset) and any evidence they aid review.
- Risks unique to AI guidance: over-trust in the agent's framing, the agent's explanation masking a defect, hallucinated rationale. Mitigations.

## Specific questions to answer directly

1. Is **logical file-group** the best review unit, or does evidence favor a different unit (change-set/hunk, behavior, dependency cluster, risk)? Give a ranked recommendation with evidence.
2. Is **"core-first, tests-last"** optimal, or should ordering follow flow/risk/dependency — and should tests be read alongside the code they cover? Recommend an ordering rule.
3. What is the evidence-based **maximum size** of a single review unit (LOC/files) before defect detection degrades, and what's the recommended split strategy for larger units? Give concrete numbers with sources and dates.
4. What is the recommended **session length / number of units / break cadence** before fatigue materially lowers detection? Should the guide enforce it?
5. For an **expert**, should the agent **teach before** the reviewer reads, or ask first / teach on demand? Quantify the expertise-reversal risk and give a rule.
6. Should pre-computed **tool findings be revealed before, during, or after** the reviewer forms their own judgment, to avoid anchoring while still adding value? Give a concrete reveal-timing recommendation.
7. Do **checklists / guided questions** beat open reading for defect detection, and what design makes them effective rather than rote? Evaluate our "key questions" mechanism.
8. Which **active-comprehension techniques** (self-explanation, prediction, summarization, restating intent) most improve an expert's mental model of a change, and how should a conversational guide elicit them?
9. Is the **keep / dismiss / will-comment / add-own** disposition model well-supported, or is there a better-evidenced taxonomy (severity/confidence/blocking)? Recommend a vocabulary.
10. What does prior art in **AI-assisted / guided code review** suggest we adopt or avoid, and what are the specific failure modes of AI-guided review (over-trust, framing bias) plus mitigations?

## Output format requested

- Organize findings under the area headings (A–E) above, then a dedicated section answering the 10 specific questions one by one with a clear, actionable recommendation each.
- For every substantive claim, cite the source and note **type** (controlled experiment / large-scale mining study / eye-tracking / practitioner convention / opinion) and **date**, so we can weight recency and rigor. Flag where evidence is thin or contested.
- Where a number is given (LOC thresholds, review-rate, session length), state the original source and whether it has been replicated or merely repeated.
- Explicitly call out where best practice **for experts** differs from generic/novice advice.
- End with a prioritized, concrete **"what to change" list** for our partitioning rules and our guiding loop, ranked by strength of evidence and expected impact on defect detection, separating "well-supported, adopt" from "plausible, try and measure."
