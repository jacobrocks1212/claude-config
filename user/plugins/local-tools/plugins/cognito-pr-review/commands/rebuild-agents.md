---
description: "Regenerate agent prompts from the current rules file"
argument-hint: ""
allowed-tools: ["Read", "Write", "Edit"]
---

# Rebuild Agents

Regenerate agent prompts after rules have been updated in the YAML rules files.

**Plugin root:** `~/.claude/plugins/local-tools/plugins/cognito-pr-review`

## Source of Truth

Rules are stored as YAML files in `{plugin_root}/knowledge/rules/`:

| YAML File | Target Agent(s) |
|-----------|-----------------|
| csharp-architecture.yaml | cognito-architecture, sweep |
| api-design.yaml | cognito-api-design, sweep |
| frontend-vue.yaml | cognito-frontend, sweep |
| performance.yaml | cognito-architecture, sweep |
| testing.yaml | cognito-test-coverage, sweep |
| code-consistency.yaml | cognito-consistency-checker, sweep |
| security.yaml | cognito-architecture, sweep |
| template-binding.yaml | cognito-frontend, sweep |

Agent files are in `{plugin_root}/agents/`.

## Workflow

### 1. Read All YAML Rules

For each YAML file in `{plugin_root}/knowledge/rules/`:
- Parse the `rules:` list
- Note the `category` field
- Count rules per file

### 2. Map Rules to Agents

Using the table above, group rules by target agent. Some agents receive rules from multiple YAML files:

- **cognito-architecture**: csharp-architecture + performance + security
- **cognito-api-design**: api-design
- **cognito-frontend**: frontend-vue + template-binding
- **cognito-test-coverage**: testing
- **cognito-consistency-checker**: code-consistency
- **sweep**: ALL categories (csharp-architecture + api-design + frontend-vue + performance + testing + code-consistency + security + template-binding)

Agents NOT updated by this process (they have different review approaches):
- **cognito-behavior** — reviews against PR description/work item, no static rules
- **review-synthesizer** — aggregates findings, no domain rules
- **journey-planner** — produces journey files and validates triage, no static rules
- **triage** — classifies files into tiers based on PR context, no static rules
- **investigation** — deep-dive investigation with Solver-Verifier protocol, no static rules
- **synthesizer-v2** — narrative synthesis from post-processed findings, no static rules

### 3. Update Agent Files

For each agent that receives rules:
1. Read the current agent file from `{plugin_root}/agents/{agent-name}.md`
2. Locate the rules section (e.g., `## Architecture Rules`, `## Frontend Rules`, etc.)
3. Regenerate the rules section from the YAML data:
   - Convert each YAML rule into a markdown subsection
   - Include anti_pattern/correct_pattern as code blocks
   - Preserve severity indicators
   - Skip `source:` fields — do not embed attribution into agent prompts
4. **Preserve everything else**: frontmatter, intro text, review scope, cache instructions, output format
5. Write the updated agent file

**Special handling for sweep.md:**
- Locate the `<!-- RULES_START -->` and `<!-- RULES_END -->` markers in the file
- Replace everything between the markers with the full rule set from ALL 8 YAML categories
- Organize rules by category using H3 headings (e.g., `### Architecture Rules`, `### API Design Rules`, `### Frontend Rules`, `### Performance Rules`, `### Testing Rules`, `### Code Consistency Rules`, `### Security Rules`, `### Template Binding Rules`)
- Include the rule weight from `weights.yaml` alongside each rule
- Preserve everything outside the markers (frontmatter, threshold instructions, escalation section, output format)

### 4. Report Changes

After updating, report:

```markdown
## Agent Rebuild Summary

**Rules processed**: X total rules across Y categories

**Agents updated**:
- cognito-architecture: [count] rules (from csharp-architecture, performance, security)
- cognito-api-design: [count] rules (from api-design)
- cognito-frontend: [count] rules (from frontend-vue, template-binding)
- cognito-test-coverage: [count] rules (from testing)
- cognito-consistency-checker: [count] rules (from code-consistency)
- sweep: [count] rules (from ALL categories)

**Agents unchanged**: cognito-behavior, review-synthesizer, synthesizer-v2, journey-planner, triage, investigation

**Rebuild complete!**
```

## Notes

- Always preserve agent frontmatter (name, description, model, color)
- Preserve cache-based file access instructions and scope boundary sections
- Preserve output format sections
- Don't remove agent-specific guidance (review philosophy, context notes)
- Convert YAML `anti_pattern`/`correct_pattern` into fenced code blocks in markdown
- If a YAML file has new rules not previously in the agent, add them under the appropriate heading
- Never embed `source:` fields from YAML rules into agent prompts — rules are anonymous
