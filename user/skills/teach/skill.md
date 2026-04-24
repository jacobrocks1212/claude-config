---
name: teach
description: "Generate teaching reference documents for presenting codebase systems/topics to coworkers. Researches the topic via subagents, proposes structure, and clarifies with user before writing."
---

# Teaching Document Generator

## Overview

Create comprehensive teaching reference documents for mentoring sessions. These documents help you present complex codebase systems to teammates, starting with foundational concepts and building to advanced topics.

## Input

The user will provide a topic, which can be:
- A system or feature area (e.g., "the payment processing system", "entry indexing")
- A file path or directory to focus on (e.g., "Cognito.Core/Services/Forms/")
- A concept or pattern (e.g., "how lookup fields work", "the workflow engine")

## Process

### Phase 1: Research (Parallel Subagents)

Spawn 2-3 Explore subagents in parallel to research the topic:

1. **Core Architecture Agent**: Find the main classes, interfaces, and data models. Identify the "entry points" to the system.

2. **Flow & Integration Agent**: Trace how data flows through the system. Find where it integrates with other systems.

3. **Edge Cases Agent** (if topic warrants): Find error handling, edge cases, configuration options, and advanced features.

**Example prompt for subagent:**
```
Research the [TOPIC] in this codebase. Focus on:
- Key classes, interfaces, and their responsibilities
- Entry points and main methods
- Data flow and state management
- File locations (absolute paths with line numbers)

Return a structured summary with:
1. Core components (file:line for each)
2. Main flows (step by step)
3. Key integration points
4. Terminology used in the code
```

### Phase 2: Synthesize & Propose Structure

After research completes, synthesize findings into a proposed document structure:

1. Review all subagent results
2. Identify the logical learning progression (basics → advanced)
3. Draft a Table of Contents with 6-10 main sections
4. Note which sections need diagrams, tables, or code samples

### Phase 3: Clarify Scope with User

Use AskUserQuestion to confirm the structure before writing. Present:

- **Proposed Table of Contents** (show all sections)
- **Scope questions:**
  - Any sections to add or remove?
  - Target audience level (new hire, experienced dev, cross-team)?
  - Specific use cases to emphasize?
  - Related systems to include/exclude?

**IMPORTANT**: Do NOT write the document until the user approves the structure.

### Phase 4: Write the Document

Generate the teaching document following this structure:

```markdown
# [Topic] - Teaching Guide

**Purpose**: Guide for mentoring session on [topic]
**Date**: [Current date]
**Branch Context**: [If relevant]

---

## Table of Contents
[Generated from approved structure]

---

## 1. Introduction: The Problem We're Solving
- Why does this system exist?
- What problems does it solve?
- Use cases it serves

## 2. End-to-End Walkthrough
- Start with a minimal, concrete example (a small class, a single request, etc.)
- Trace it through every layer of the system
- Show what's present AND what's absent at each layer
- End with a side-by-side summary table

## 3-N. [Topic Sections - deep dives]
- Explain concepts with ASCII diagrams
- Include code references (file:line)
- Use tables for quick reference
- Build on previous sections
- Reference back to the walkthrough example where relevant

## N+1. Key File Reference
| File | Lines | Purpose |
|------|-------|---------|
| path/to/file.cs | 10-50 | Description |

## N+2. Discussion Questions
- Questions to check understanding
- Spark deeper conversation
- Reveal edge cases and trade-offs
```

### Phase 5: Save the Document

Save to: `.claude.local/teaching/[Topic] - Teaching Guide.md`

Create the `.claude.local/teaching/` directory if it doesn't exist.

## Document Guidelines

### Structure Principles
- **Start with "why"**: Always explain the problem before the solution
- **Progressive complexity**: Each section should build on the previous
- **End-to-end walkthrough first**: Before diving into details, trace a concrete example through the entire system. This gives the reader a mental model to anchor the details against. Place this walkthrough early in the document (after the overview, before the deep-dive sections).
- **File references**: Include `file.cs:line` for all key code mentions
- **Visual aids**: Use ASCII diagrams for architecture and data flow
- **Tables**: Use for quick reference (methods, files, concepts)
- **Discussion questions**: End with 5-7 questions to check understanding

### End-to-End Walkthrough Pattern

Every teaching document should include a **concrete example** that traces one piece of data or one operation through all layers of the system. This is the single most effective tool for building understanding.

**How to write a good walkthrough:**
1. **Start with a minimal, realistic input** — a small C# class, a simple form, a single API call. Just enough to exercise the system without overwhelming detail.
2. **Walk through each layer** — show what happens at each step, with the actual code or data representation at that layer. Number the layers so the reader can track progression.
3. **Show what's present AND what's absent** — if the system filters, transforms, or excludes things, explicitly call out what disappears and why. This is often where the real learning happens.
4. **End with a side-by-side summary** — a table or multi-column comparison showing the same data in each representation. This cements the mental model.

**Example structure:**
```markdown
## End-to-End Walkthrough

### The Starting Point
[Minimal code example — the input to the system]

### Layer 1: [First transformation]
[What happens, with actual output/representation]

### Layer 2: [Second transformation]
[What happens, what changes, what gets filtered out]

### Layer N: [Final output]
[What the consumer sees]

### Side-by-Side Summary
[Table or diagram showing input → each layer → output]
```

**What makes a bad walkthrough:**
- Too abstract (talks about "types" generically instead of showing `string Name`)
- Skips layers (jumps from C# to browser without showing the JSON on the wire)
- Only shows the happy path (doesn't call out what gets excluded or filtered)
- Too large an example (10 properties when 3 would suffice)

### Writing Style
- Clear, direct explanations (no fluff)
- Use the terminology from the code itself
- Explain jargon when first introduced
- Show don't tell - include code structure diagrams
- Keep code samples short and focused

### ASCII Diagram Examples

**Architecture:**
```
+-------------+     +---------------+     +-------------+
| Component A | --> | Component B   | --> | Component C |
+-------------+     +---------------+     +-------------+
```

**Flow:**
```
Action
    |
    v
+--------+
| Step 1 |
+--------+
    |
    +-- Success --> Continue
    |
    +-- Failure --> Handle error
```

**Hierarchy:**
```
BaseClass
  |
  +-- ChildA
  |     +-- GrandchildA1
  |     +-- GrandchildA2
  |
  +-- ChildB
```

## Key Principles

- **Research before writing** - Never guess; use subagents to find facts
- **Clarify scope first** - Use AskUserQuestion before writing anything
- **File:line references** - Every significant code mention needs a location
- **Build progressively** - Each section should unlock understanding of the next
- **End with questions** - Help the presenter gauge comprehension
