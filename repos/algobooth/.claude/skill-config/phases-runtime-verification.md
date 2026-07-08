<!--
  AUTHORING CAUTION — line-leading bold inside a Runtime Verification section.
  bug-state.py / lazy-state.py share `lazy_core.remaining_unchecked_are_verification_only`,
  which treats ANY line-leading `**bold**` paragraph as a *subsection header* and
  re-evaluates verification scope from its text. It stays "in verification scope"
  only while that bold text matches the verification regex (`runtime verification`
  | `mcp (integration test|test assertion|assertion)`, case-insensitive). A
  line-leading bold lead that does NOT match — e.g. a prose paragraph opening
  `**Assessment: ...**` or `**Note: ...**` — silently *exits* verification scope,
  so the intentionally-unticked `- [ ]` runtime rows below it are misread as
  remaining IMPLEMENTATION work and the pipeline loops back to write-plan instead
  of falling through to the retro/MCP gate. (Observed on the
  sidecar-health-monitoring-in-djstore bug: an `**Assessment: ...**` RV lead
  caused a spurious write-plan loop; fixed by rewording to
  `**Runtime Verification assessment: ...**`.)

  RULE: keep every line-leading bold paragraph inside a Runtime Verification
  section matching the verification regex (start it with the literal words
  "Runtime Verification", e.g. `**Runtime Verification assessment: ...**`), OR
  demote the prose to a non-bold line / blockquote / list item (`- **x**` is a
  list item, not a header, and is safe). Do NOT open an RV subsection with an
  unrelated bold lead. The unticked RV boxes themselves are correct and must stay
  `- [ ]` — they belong to the mcp-test cycle, not the implementer.
-->
**Runtime Verification** *(checked by MCP integration test or manual testing — NOT by the implementation agent):*
- [ ] {Observable runtime behavior 1 — e.g., "session.jsonl contains keyboard_*_fired events"}
- [ ] {Observable runtime behavior 2 — e.g., "session-meta.json has sample_rate field"}

**MCP Integration Test Assertions:**
{If the feature's SPEC.md has a Validation Criteria table, extract the rows relevant to this phase and express them as concrete assertions the MCP test agent can verify at runtime. Format:}
```
ASSERTIONS:
1. After {trigger action via MCP tool}: {observable evidence} MUST {condition}
2. ...
```
{If no runtime-observable behavior in this phase (e.g., pure types, config), write "N/A — no runtime-observable behavior in this phase"}
