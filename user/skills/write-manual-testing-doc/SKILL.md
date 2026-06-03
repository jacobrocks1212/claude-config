---
name: write-manual-testing-doc
description: Write manual testing docs (usually informed by SPEC and PHASES docs) focused on behavior, not implementation
argument-hint: [path-to-feature-dir or description]
---

# Manual Testing Doc Writer

Write manual testing documents for features that are ready for QA or PO review. The output is a **behavior-focused** checklist suitable for non-technical stakeholders — no implementation jargon, no code references, no internal decision numbers.

## When to Use

- A feature has completed implementation and needs a testing doc
- An existing testing doc needs to be rewritten for a non-technical audience
- A PO, QA engineer, or stakeholder needs a test plan they can follow in the UI

## Step 1: Gather Context

Read the feature's source documents. Look for these in the feature directory (or ask the user where they are):

1. **SPEC.md** — what the feature does, decisions made, edge cases
2. **PHASES.md** — what was actually built, bug fixes applied, scope changes
3. **Existing MANUAL_TESTING.md** — if one exists, use it as a starting point for structure

If PHASES.md shows completed phases with bug fixes or scope changes, the testing doc must reflect the **final shipped behavior**, not the original plan.

## Step 2: Identify What to Test

From the source docs, extract:

- **Happy paths** — the core feature working as intended
- **Configuration options** — settings the user can toggle and their effects
- **Boundary conditions** — what happens at limits (quantity limits, missing data, empty fields)
- **Failure modes** — what happens when things go wrong (deleted config, unavailable resources)
- **Edge cases** — concurrent operations, already-processed items, optional fields

Discard anything a non-technical user cannot observe or verify:
- Telemetry/observability events (App Insights, custom events)
- Internal indexing behavior
- Database/storage implementation details
- Code paths, method names, class names
- Spec decision numbers (Decision #1, etc.)

## Step 3: Organize by User Journey

Structure the doc in this order:

1. **What This Feature Does** — 2-3 sentence plain-English summary
2. **Setup** — numbered steps to create the test environment (forms, fields, settings)
3. **Configuration** — testing the settings UI (visibility, persistence, clearing)
4. **Core Behavior** — happy path scenarios
5. **Triggers and Timing** — when does the behavior fire, what doesn't trigger it
6. **Limits and Validation** — boundary conditions, error handling
7. **Audit / History** — if the feature produces audit records visible to users
8. **Edge Cases** — unusual but possible scenarios

Omit sections that don't apply. Don't force every feature into all 8 sections.

## Step 4: Write the Doc

### Formatting Rules

- **H1 title**: `# Manual Testing — {Feature Name}`
- **Summary block**: "What This Feature Does" paragraph before any test sections
- **H2 for major sections**, **H3 for individual scenarios**
- **Checkbox format** (`- [ ]`) for every verifiable step
- **Bold** for expected outcomes: "Verify the entry is **not** created"
- Keep each checkbox to one observable action or verification

### Language Rules

- Describe what the user **sees and does**, not what the code does
- Use UI terminology: "open the form builder", "check the entries list", "look at the audit trail"
- Say "person entry" not "entry with `SubmitterPersonEntryId` set"
- Say "linked" not "PersonSubmissionIndex created"
- Say "no error is shown" not "fails silently"
- Never reference: class names, method names, property names, database fields, spec decision numbers, phase numbers, submission behavior flags, index names

### Setup Section Rules

- Number the steps (not checkboxes — these are prerequisites, not verifications)
- Be specific about what forms/fields to create
- Mention any non-obvious configuration (e.g. "the People form needs at least one workflow action")

### Scenario Rules

- Each scenario should be self-contained — a tester can run it without reading other scenarios
- State the precondition, the action, and the expected result
- If a scenario depends on state from a previous scenario (e.g. "using the person created in 2.1"), say so explicitly
- Group related scenarios under a shared H2

## Step 5: Cross-Check Against Source

Before presenting the doc, verify:

1. Every completed phase in PHASES.md has corresponding test coverage
2. Bug fixes that changed behavior are reflected (e.g. if a bug fix made compound fields work, there should be a scenario testing compound fields)
3. Removed/descoped features are NOT in the testing doc
4. Requirements changes noted in PHASES.md are reflected in the current behavior, not the old behavior
5. The "Setup" section creates an environment that actually supports all the scenarios

## Step 6: Present and Iterate

Show the draft to the user. Common feedback:
- "This scenario isn't possible anymore" — remove it
- "Missing a scenario for X" — add it
- "Too much detail in setup" — simplify
- "The PO won't know what {term} means" — rephrase
