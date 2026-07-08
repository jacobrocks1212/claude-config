### Subagent E: Spec Alignment Validator (when runtime evidence available)

**Only launch if** runtime evidence exists (session logs, running app, API responses). Skip if code-level analysis only.

**Prompt:** Compare SPEC.md's expected observable behavior against actual runtime evidence. For each spec section that defines observable output:
- Read session logs (`logs/session-*/session.jsonl`) and check: are the expected events present? Do their schemas match the spec?
- If an MCP server is running (`localhost:3333/health`), query relevant endpoints and compare responses to spec expectations
- Produce a confidence-scored alignment table:

| Spec Requirement | Evidence Found | Confidence | Notes |
|-----------------|----------------|------------|-------|
| "keyboard_*_fired events" | 0 events in session.jsonl | 0% | EventBus not wired |
| "audio_rms_batch in TOON format" | 0 events | 0% | Feature flag inactive |

Confidence levels: 100% (verified working), 75% (evidence present but partial), 50% (code exists but unverified at runtime), 25% (code exists but evidence contradicts), 0% (no evidence or contradicted)
