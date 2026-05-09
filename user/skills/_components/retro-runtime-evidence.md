### Subagent E: Spec Alignment Validator (when runtime evidence available)

**Only launch if** runtime evidence exists (running app, API responses, integration test output). Skip if code-level analysis only.

**Prompt:** Compare SPEC.md's expected observable behavior against actual runtime evidence. For each spec section that defines observable output:
- Check available runtime evidence (test output, API responses, logs) against spec expectations
- Produce a confidence-scored alignment table:

| Spec Requirement | Evidence Found | Confidence | Notes |
|-----------------|----------------|------------|-------|
| {expected behavior} | {actual evidence} | {0-100%} | {explanation} |

Confidence levels: 100% (verified working), 75% (evidence present but partial), 50% (code exists but unverified at runtime), 25% (code exists but evidence contradicts), 0% (no evidence or contradicted)
