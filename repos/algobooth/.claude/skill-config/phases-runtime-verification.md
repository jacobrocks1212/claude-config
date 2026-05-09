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
