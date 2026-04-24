# Gemini Deep Research Guide

Use this guide when researching a new project idea with Gemini Deep Research.

## What to Research

When starting a new project, ask Gemini to research:

### 1. Problem Space
- What problem are you solving?
- Who has this problem? (target users)
- How do they currently solve it?
- What are the pain points with current solutions?

### 2. Technical Approaches
- What are the main technical approaches to solve this?
- What are the trade-offs between approaches?
- What do similar products/projects use?
- Are there any emerging patterns or technologies?

### 3. Technology Stack
- What languages/frameworks are best suited?
- What databases/storage solutions fit the use case?
- What are the deployment options?
- What are the cost implications?

### 4. Architecture Patterns
- Monolith vs microservices vs serverless?
- Frontend architecture (SPA, SSR, static)?
- API design (REST, GraphQL, RPC)?
- State management approaches?

### 5. Risks and Challenges
- What are the technical hurdles?
- What are the common failure modes?
- What security considerations apply?
- What are the scalability concerns?

### 6. Best Practices
- What patterns do successful implementations use?
- What should be avoided?
- What testing strategies work best?
- What are the maintenance considerations?

---

## Example Gemini Prompt

```
I want to build [PROJECT DESCRIPTION].

Please research:
1. The problem space and target users
2. Technical approaches and their trade-offs
3. Recommended technology stack with justification
4. Architecture patterns that fit this use case
5. Common risks, challenges, and how to mitigate them
6. Best practices from similar successful projects

For each area, provide specific recommendations with reasoning.
Include any open questions I should consider before implementation.
```

---

## After Research

1. Save Gemini's output to a file (e.g., `project-research.md`)

2. Run the synthesis command:
   ```
   /vibe-research "C:\path\to\project-research.md"
   ```

3. Answer clarifying questions as Claude synthesizes the research into:
   - `specs/PRD.md` - User stories and requirements
   - `specs/TECH_SPEC.md` - Architecture and technical details
   - `specs/current_plan.md` - Implementation roadmap

4. Start implementation:
   ```
   /vibe-work        # Next task
   /vibe-work all    # Complete phase
   ```

---

## Tips for Better Research

- **Be specific** about your constraints (budget, timeline, team size)
- **Mention context** (enterprise vs startup, existing systems to integrate)
- **Ask for trade-offs** not just recommendations
- **Request examples** of similar successful projects
- **Include scale expectations** (users, data volume, traffic)
