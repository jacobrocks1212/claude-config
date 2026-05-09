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
