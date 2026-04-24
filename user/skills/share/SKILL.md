---
description: Translate session findings into a response for teammates in Jacob's voice.
model: opus
name: share
---

# Share

Translate the findings from this session into a response Jacob can send to a teammate who asked a question.

## Context

Jacob's teammates often ask him technical questions. He researches solutions with Claude, then needs to respond in his own words. This command generates that response—ready to copy-paste.

## Instructions

1. **Identify the original question** the teammate asked (from conversation context)

2. **Extract the answer/findings** from this session:
   - The solution or recommendation
   - Key technical details they need to know
   - Any caveats, gotchas, or things to watch out for
   - Next steps if applicable

3. **Apply the human-writing skill** with Jacob's personal style:
   - Read `~/.claude/skills/human-writing/SKILL.md` for general principles
   - Read `~/.claude/skills/human-writing/jacob-style.md` for Jacob's specific voice
   - This is critical—the output must sound like Jacob wrote it

4. **Key style rules from jacob-style.md**:
   - NO greeting—jump straight into the answer
   - Direct and concise—get the point across without excess information
   - Use contractions naturally (I'll, that's, we're, didn't)
   - Use code blocks (```language) with pseudo-code or real code when it communicates the solution efficiently
   - Acknowledge uncertainty when appropriate: "My hunch is...", "I'm not sure if..."
   - Use "Gotcha", "Yeah", "Sounds good" naturally
   - End with "Lmk if you run into any issues" or similar if relevant
   - NEVER use "excited", "thrilled", "I hope this helps", or corporate buzzwords

5. **Prioritize clarity over completeness**—include only what they need to act on it

## Output Format

The response should be ready to copy-paste directly into Slack/Teams. No markdown headers, just the message content. Code blocks are encouraged when helpful.

## Example

If teammate asked about updating snapshots for failing tests:

```
Yeah those are snapshot tests. To update them, go to the tests and add the [Snapper.Attributes.UpdateSnapshots] attribute. That will cause the test to pass & update the snapshot, which you can see as a json file in your git changes.

Make sure to double-check the updated snapshots to verify the updates make sense. Then remove the attribute and commit the json files.
```

## Example 2

If teammate asked about a complex technical approach:

```
Gotcha. I like your idea about validate returning information about what was invalid. Building off that, here's what I'd recommend:

Instead of having Validate() modify data, introduce a return value:

\`\`\`csharp
public enum LookupViewValidationResult
{
    Valid,
    SourceFormMissing,
    FilterInvalid
}
\`\`\`

Then GetLookupViews() can check for FilterInvalid and call a separate RepairFilter() method.

Lmk if you run into any issues.
```
