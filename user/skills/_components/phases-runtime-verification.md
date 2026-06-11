<!--
  ╔══════════════════════════════════════════════════════════════════════════╗
  ║  PLACEMENT RULE — enforced by lazy_core state-script heuristic          ║
  ╚══════════════════════════════════════════════════════════════════════════╝

  **Runtime-verification / MCP-assertion checkboxes (`- [ ]`) MUST live under
  a dedicated `## Runtime Verification` heading (or under a recognized bold-
  marker subsection: `**Runtime Verification**` / `**MCP Integration Test
  Assertions:**`). They MUST NEVER appear under a phase's `### Deliverables`
  list.**

  Rationale: `lazy_core`'s `remaining_unchecked_are_verification_only()`
  heuristic decides whether all remaining unchecked rows are verification-only
  so it can route the phase forward to the retro→MCP gate (Step 8→9) instead
  of looping back on write-plan/execute-plan. A `- [ ]` checkbox placed under
  `### Deliverables` is read as an outstanding IMPLEMENTATION item — this
  misclassification causes spurious write-plan/execute-plan churn (this exact
  misplacement cost two Sonnet recoveries + two pipeline stalls in production).

  Additionally: `- [ ]` rows shown INSIDE ``` fenced code blocks are treated
  as illustrative examples and are NOT counted as deliverables or verification
  rows by the state script.

  AUTHORING CAUTION — line-leading bold inside a Runtime Verification section.
  The lazy_core state machine's `remaining_unchecked_are_verification_only`
  heuristic treats ANY line-leading `**bold**` paragraph as a *subsection
  header* and re-evaluates verification scope from its text. It stays "in
  verification scope" only while that bold text matches the verification regex
  (`runtime verification` | `mcp (integration test|test assertion|assertion)`,
  case-insensitive). A line-leading bold lead that does NOT match — e.g. a
  prose paragraph opening `**Assessment: ...**` or `**Note: ...**` — silently
  *exits* verification scope, so the intentionally-unticked `- [ ]` runtime
  rows below it are misread as remaining IMPLEMENTATION work and the pipeline
  loops back to write-plan instead of falling through to the retro/MCP gate.

  RULE: keep every line-leading bold paragraph inside a Runtime Verification
  section matching the verification regex (start it with the literal words
  "Runtime Verification", e.g. `**Runtime Verification assessment: ...**`), OR
  demote the prose to a non-bold line / blockquote / list item (`- **x**` is a
  list item, not a header, and is safe). Do NOT open an RV subsection with an
  unrelated bold lead. The unticked RV boxes themselves are correct and must
  stay `- [ ]` — they belong to the mcp-test cycle, not the implementer.
-->
**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] {Observable runtime behavior 1 — e.g., "API returns expected response after action"}
- [ ] {Observable runtime behavior 2 — e.g., "database contains expected records"}

**MCP Integration Test Assertions:**
{If the feature's SPEC.md has a Validation Criteria table, extract the rows relevant to this phase and express them as concrete assertions a test agent can verify at runtime. Format:}
```
ASSERTIONS:
1. After {trigger action}: {observable evidence} MUST {condition}
2. ...
```
{If no runtime-observable behavior in this phase (e.g., pure types, config), write "N/A — no runtime-observable behavior in this phase"}
