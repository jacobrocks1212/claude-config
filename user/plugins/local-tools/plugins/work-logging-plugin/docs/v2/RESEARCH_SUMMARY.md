# Interview Prep Plugin v2 — Research Summary

## Key Findings

### 1. Cognitive Foundation: Self-Reference Effect (SRE)
The entire v2 approach is validated by cognitive science. Information encoded through self-related processing is retained with significantly higher accuracy. In interview contexts, candidates who map abstract concepts to their own localized experience recall nuances with higher fidelity, greater credibility, and reduced anxiety. This is the core value proposition — not just organizing notes, but leveraging a documented mnemonic advantage.

### 2. Domain-Specific Story Formats (Major Spec Impact)
Research strongly recommends **different narrative templates per domain**, not a one-size-fits-all approach:

| Domain | Recommended Format | Key Addition vs. Generic STAR |
|--------|-------------------|-------------------------------|
| Behavioral | **(I)STAR(T)** — Introduction, Situation, Task, Action, Result, Takeaway | Hook intro + retrospective takeaway showing maturity |
| System Design | **Architecture Decision Records (ADRs)** — Context, Baseline, Bottleneck, Decision/Tradeoffs, Operational Reality | Proactively surfaces tradeoffs before interviewer asks |
| OOD | **Entity → Pattern → Extensibility** — Core entities, GoF pattern applied, SOLID justification | Maps real modules to canonical patterns |
| All | **Rule of Three** — max 3 core challenges per narrative | Prevents cognitive overload |

Target: **8-10 deeply prepared behavioral stories** mapped to common dimensions (leadership, ambiguity, conflict, failure). **1-3 work examples per topic** (enough for redundancy, avoids dilution).

### 3. Obsidian Vault Architecture (Refines Baseline)
- **Flat, tag-driven structure** over deep folders — concepts are multi-disciplinary
- **4 primary collections** by structural role: Knowledge Bank, Work History, Features, Interview Stories
- **Managed Block pattern** — all LLM-generated content inside `<!-- BEGIN/END -->` HTML comment delimiters to preserve user annotations across regeneration cycles
- **DAG link topology** — Work History → Features → Interview Stories → Knowledge Bank topics. No direct links from granular work to abstract concepts. Prevents graph hairball.
- **Dataview-compatible frontmatter** — strict YAML metadata enables dynamic dashboards (coverage heatmaps, weak area identification)
- **SRS plugin compatibility** — format flashcards with `::` delimiter syntax for Obsidian Spaced Repetition plugin. Don't build custom SRS.

### 4. Feature Synthesis: Hybrid Approach Confirmed
Research validates Approach C with specifics:
- **Tag at log time** when feature context is known (optional field on work_log_append)
- **LLM semantic clustering** for orphaned/untagged entries during /interview-synthesize
- **Cold start solution**: Import 491 planning artifacts directly as Features (bypass granular log), using map-reduce summarization
- Artifacts imported as Features get immediately correlated to topics, producing useful study material from day one

### 5. Topic Correlation: Two-Stage LLM-as-a-Judge
- **Stage 1 — Candidate Retrieval**: Lightweight semantic search against 154 KB topics, retrieve top 10 candidates per feature
- **Stage 2 — LLM Judge Evaluation**: Strict 0-2 rubric (0=irrelevant, 1=tangential, 2=strong match). Only Score 2 persisted as correlation.
- **Cap**: Max 3 feature matches per topic in the vault to prevent graph hairball
- **Bidirectional**: Topic → Work (for study) AND Work → Topic (for story mining)

### 6. Idempotent Import: Content Hash + Path UUID
- SHA-256 hash of file contents for dedup
- Path metadata for tracking document origin
- If same path, different hash → document evolved, new entry with same UUID
- Pure append-only log preserved while supporting document updates

### 7. MCP Tool Surface: Composite + Atomic
Research recommends splitting into two layers:
- **User-facing composite skills**: /interview-generate, /interview-import, /interview-synthesize (macro orchestrations)
- **LLM-facing atomic tools**: read_log, get_topic, write_managed_block, evaluate_match, calculate_hash (fine-grained primitives the LLM uses to orchestrate generation)
- Vault generation should be **LLM-orchestrated** (not a monolithic script), allowing dynamic adaptation and error handling

### 8. Async Progress Reporting
Long-running operations (vault generation, bulk import) must use MCP progress notifications to prevent timeout. FastMCP yields progress tokens with current/total counts and human-readable status messages.

## Ideas to Adopt from Research

1. **Managed Block pattern** — critical for vault regeneration safety. Must implement.
2. **(I)STAR(T) framework** for behavioral stories — strictly better than plain STAR.
3. **ADR format** for system design narratives — matches how senior engineers actually communicate.
4. **SRS plugin compatibility** — free spaced repetition without building custom scheduling.
5. **DAG link topology** — prevents the #1 failure mode of generated Obsidian vaults.
6. **Map-reduce for cold start** — solve the 491-artifact backfill elegantly.
7. **Two-stage correlation** — efficient and high-precision topic matching.

## Baseline Decisions to Revisit

1. **Vault directory structure**: Research proposes 4 collections (KB, Work History, Features, Interview Stories) vs our baseline's 5 (topics, projects, features, study, dashboard). The research structure is better — separates "raw evidence" from "synthesized study material."
2. **Study format**: Research resolves this decisively — domain-specific templates (ISTART, ADR, Entity-Pattern-Extensibility), not a generic hybrid.
3. **Feature synthesis**: Research confirms hybrid with cold-start-specific ingestion path.
4. **MCP tool surface**: Research proposes more granular atomic tools than we had considered. Worth evaluating whether this complexity is justified given Claude Code's current tool orchestration capabilities.

## Potential Pitfalls

1. **LLM hallucination** — Must enforce extraction-only mode in generation prompts. No fabricated metrics or architectural details.
2. **Over-engineering the atomic tool layer** — Research proposes many fine-grained LLM tools. Risk: Claude Code may not orchestrate 10+ atomic tools as reliably as 3-4 well-designed composite tools. Evaluate pragmatically.
3. **Graph hairball** — Must enforce strict link topology from day one. Hard to fix retroactively.
4. **Token costs** — Correlating hundreds of features against 154 topics with LLM-as-a-judge is token-expensive. The two-stage pipeline (embed → top-10 → judge) is essential.
