# {PROJECT_NAME} - Product Requirements Document

## Vision

<!-- 1-2 sentences: What problem does this solve? Who is it for? -->

## User Stories

<!--
Each story follows Gherkin format for direct conversion to tests.
Group related stories under Epics.
-->

### Epic: Core Functionality

#### Story: [Story Name]

```gherkin
Feature: [Feature Name]
  As a [role]
  I want [capability]
  So that [benefit]

  Scenario: [Happy path scenario name]
    Given [precondition]
    When [action]
    Then [expected result]

  Scenario: [Edge case scenario name]
    Given [precondition]
    When [action]
    Then [expected result]
```

### Epic: [Additional Epic]

#### Story: [Story Name]

```gherkin
Feature: [Feature Name]
  As a [role]
  I want [capability]
  So that [benefit]

  Scenario: [Scenario name]
    Given [precondition]
    When [action]
    Then [expected result]
```

## Acceptance Criteria

<!-- Binary, testable criteria. Each maps to at least one test. -->

- [ ] Criterion 1: [Specific, measurable outcome]
- [ ] Criterion 2: [Specific, measurable outcome]
- [ ] Criterion 3: [Specific, measurable outcome]

## Non-Functional Requirements

### Performance
- [ ] [Response time target, e.g., "API responses < 200ms at p95"]
- [ ] [Throughput target, e.g., "Handle 1000 concurrent users"]

### Security
- [ ] [Auth requirement, e.g., "All endpoints require authentication"]
- [ ] [Data protection, e.g., "PII encrypted at rest"]

### Accessibility
- [ ] [Standard, e.g., "WCAG 2.1 AA compliance"]

### Reliability
- [ ] [Uptime target, e.g., "99.9% availability"]

## Out of Scope

<!-- Explicitly state what we will NOT build to prevent scope creep -->

- Item 1: [Feature explicitly excluded]
- Item 2: [Feature explicitly excluded]

## Open Questions

<!-- Capture unresolved decisions for later discussion -->

- [ ] Question 1?
- [ ] Question 2?

---

**Last Updated:** {DATE}
**Status:** Draft | In Review | Approved
