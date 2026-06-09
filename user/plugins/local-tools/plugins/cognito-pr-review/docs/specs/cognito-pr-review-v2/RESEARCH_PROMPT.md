# Research Prompt: Multi-Agent LLM Code Review Pipeline Design

## Research Question

What are the best practices, proven patterns, and pitfalls for designing a multi-agent LLM pipeline that performs code review with investigation-level depth, triage-driven prioritization, iterative calibration against human feedback, and first-class re-review support?

## Context

### System Overview
We're redesigning an existing Claude Code plugin that reviews pull requests for a monorepo (C# .NET backend + Vue 2.7/TypeScript frontend, ~500K lines). The current system (v1) runs 6 specialist agents in parallel, each scanning for YAML rule violations, then aggregates findings via a lightweight synthesizer. After ~30 reviews, the system catches small inconsistencies well but produces significant noise and fails to deeply investigate critical changes.

### Current Architecture (v1)
```
Deterministic Prep Script (TypeScript) → ADO API data + file cache
    ↓
6 Specialist Agents (parallel, Opus) → rule-based scanning
    ↓
Haiku Synthesizer → deduplicate + filter → markdown review
```

### Proposed Architecture (v2)
```
Enhanced Prep Script → data + timeline + re-review detection
    ↓
Journey Agent (Opus) → persistent PR lifecycle document + review guide
    ↓
Triage Agent (Opus) → classify changes as critical/important/skim
    ↓
Investigation Agents (parallel, Opus, 1 per critical area)
    + Sweep Agent (Sonnet, full rules on non-critical files)
    ↓
Deterministic post-processing → weight application + dedup
    ↓
Sonnet Synthesizer → narrative review
```

### Key Design Decisions Already Made
- Investigation agents have full codebase read access (local repo = main branch, not PR branch)
- Per-rule weights × category multipliers, calibrated against actual human review comments
- Re-review auto-detected; journey file accumulates across iterations
- No caps on investigation agent count or codebase reads
- Triage combines PR objective alignment with code complexity/blast radius

### Technology Stack
- Claude Code plugin (runs as Claude Code subagents via the Agent tool)
- Models: Claude Opus for investigation/journey/triage, Claude Sonnet for sweep/synthesis
- TypeScript prep script for deterministic data gathering
- Azure DevOps REST API for PR metadata
- YAML rule files (~100 rules across 8 categories)

## Baseline Spec Summary

The v2 plugin restructures from "scan everything for rule violations" to "understand → prioritize → investigate critical → sweep the rest." Key innovations:

1. **Journey Agent** produces a persistent document mapping PR objectives to file changes, providing a manual review guide, and tracking PR lifecycle across re-reviews.
2. **Triage Agent** classifies changes by criticality (objective alignment × blast radius) to allocate review depth.
3. **Investigation Agents** deep-dive critical areas with full codebase access, considering alternatives and validating approaches with evidence.
4. **Weight System** (per-rule + category multiplier) calibrated via bulk analysis of actual human review comments across 30+ historical PRs.
5. **Re-Review** is first-class: auto-detected, iteration-aware, comment-resolution-tracking, with priority boosting for changed/unresolved areas.

## Research Areas

### 1. Multi-Agent LLM Pipeline Orchestration
- What are proven patterns for orchestrating sequential + parallel LLM agent pipelines?
- How do production systems handle agent-to-agent context passing (full context vs. summarized handoff)?
- What are the failure modes of multi-step LLM pipelines and how are they mitigated?
- How do systems like Devin, SWE-Agent, OpenHands, or Codex handle multi-agent task decomposition for code understanding?

### 2. LLM-Based Code Review Systems
- What research exists on LLM-based code review tools (academic papers, industry tools)?
- How do tools like CodeRabbit, Sourcery, Qodo Merge (formerly PR-Agent), Ellipsis, Bito, etc. structure their review pipelines?
- What approaches work for distinguishing "important" findings from noise in automated code review?
- How do these systems handle re-reviews / incremental reviews?
- What prompt engineering techniques improve code review quality (chain-of-thought, few-shot examples, structured output)?

### 3. Triage and Criticality Classification
- What approaches exist for automatically classifying code change criticality?
- How do code review tools determine which files/changes deserve deeper attention?
- Are there proven heuristics for "blast radius" estimation in code changes?
- How do systems combine semantic understanding (what the PR does) with structural analysis (what code is affected)?

### 4. Investigation-Depth Review with Codebase Exploration
- How do LLM agents effectively explore large codebases for context?
- What strategies prevent agents from going on tangents when given broad read access?
- How do retrieval-augmented generation (RAG) approaches apply to code review context gathering?
- What are the tradeoffs of giving agents full codebase access vs. pre-curated context?

### 5. Calibration Against Human Feedback
- What approaches exist for calibrating automated review systems against human reviewer behavior?
- How do recommendation systems handle the "matching" problem (aligning automated output with human intent when they use different language)?
- What weight/scoring systems are used in automated review tools to tune finding relevance?
- How do systems like GitHub's code scanning handle false positive suppression and tuning?
- Is there research on using human review comments as training signal for LLM-based review improvement?

### 6. Re-Review and Incremental Review Patterns
- How do existing code review tools handle re-reviews (subsequent iterations of the same PR)?
- What's the best approach for diffing iterations (diff-of-diffs vs. full re-analysis)?
- How do tools track comment resolution status and integrate it into subsequent reviews?
- What UX patterns exist for presenting incremental review results?

### 7. Large File Review Strategies
- How do code review tools handle reviewing changes to very large files (10K+ lines)?
- What structural analysis approaches help agents understand large file changes?
- Are there effective ways to provide "just enough" context without reading entire large files?
- How do IDE-like structural indexes (outline view, symbol table) translate to LLM context?

### 8. Prompt Engineering for Code Review Agents
- What prompt structures produce the best code review output from LLMs?
- How should agent prompts differ for investigation (open-ended, exploratory) vs. sweep (rule-matching, systematic)?
- What role does the "persona" or "reviewer identity" play in review quality?
- How do few-shot examples in prompts affect code review quality and consistency?

## Specific Questions

1. **Pipeline failure handling:** In a 5-phase sequential pipeline, if Phase 3 (triage) produces poor classification, it cascades through investigation and sweep. What circuit-breaker or self-correction patterns exist for multi-agent pipelines?

2. **Context compression:** The journey file accumulates across re-reviews. When it gets large, how should it be compressed for injection into agent prompts without losing critical information? Are there proven summarization patterns for this?

3. **Calibration matching:** When comparing a plugin finding ("prefer abstract class over lambda-based strategy pattern") against a human comment ("this is a funky pattern, could we use an abstract class?"), how can we reliably determine these refer to the same issue? Semantic similarity? File:line matching? Hybrid?

4. **Investigation agent grounding:** How do we prevent investigation agents from hallucinating alternatives that don't work in the specific codebase? What "grounding" techniques ensure suggestions are validated against real code?

5. **Weight convergence:** With a per-rule weight system updated via running average, how many data points are typically needed for weights to converge to useful values? Should we use exponential moving average instead to weight recent feedback more heavily?

6. **Triage accuracy:** If the triage agent misclassifies a critical area as "skim," it gets superficial review. What confidence calibration or validation techniques can improve triage accuracy? Should investigation agents be able to "escalate" a finding from sweep tier?

7. **Cost optimization:** The v2 pipeline has more agent calls than v1 (journey + triage + N investigation + sweep + synthesizer). What are practical strategies for controlling cost while maintaining quality? Token budgets? Model selection per phase? Caching between re-reviews?

8. **Agent specialization vs. generalization:** v1 had 6 domain-specialist agents. v2 has investigation agents that are generalists assigned to critical areas. Research on when specialization (expert agents per domain) outperforms generalization (capable agents per task area)?

9. **Evaluation metrics:** How should we measure whether v2 is actually better than v1? Beyond precision/recall of findings vs. human comments, what qualitative metrics matter for code review systems?

10. **Incremental adoption:** Can we phase the v2 rollout to run v1 and v2 in parallel for comparison, or is the architectural change too fundamental? What A/B testing approaches work for code review tools?

## Output Format Request

Please structure findings as:

1. **Executive Summary** (1 page) — Key takeaways and recommendations
2. **Per-Research-Area Findings** — For each of the 8 research areas:
   - Current state of the art
   - Most relevant prior art / tools / papers
   - Specific recommendations for our system
   - Pitfalls to avoid
3. **Specific Question Answers** — Direct answers to the 10 specific questions, with citations
4. **Recommended Architecture Adjustments** — Based on research, what should we change about our proposed v2 design?
5. **Risk Register** — Top 5 risks and mitigations for the v2 approach
6. **References** — All cited sources with brief annotations
