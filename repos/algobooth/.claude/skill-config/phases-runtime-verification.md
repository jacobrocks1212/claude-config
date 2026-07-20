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

<!-- Runtime-proof Spike phase declaration (harden Round 80; docs/specs/spike-pipeline-role) -->

**`**Spike:**` phase declaration — when a phase's completion RESTS on a runtime proof.**
A phase is not done until its runtime claim is PROVEN (a sustained measurement, a GO/NO-GO
verdict, a confirm/deny of real behavior). Such a phase carries a `**Spike:**` header line
directly under its `### Phase N:` heading, mirroring `**MCP runtime:**`:

```
**Spike:** required — <one-line proof goal, e.g. "measure sustained projector fps; GO iff >=60">
```

This is ROUTING, not a waiver: the pipeline routes that phase's completion through a runtime-proof
**Spike** cycle (orchestrator-owned runtime, exactly like `/mcp-test`). On **PASS** the plan's
prescribed next cycle proceeds (document it in the phase — e.g. "Phase 10 builds the single-render
architecture"); on **FAIL** the Spike updates the results doc + this phase, writes `NEEDS_INPUT.md`
presenting the prescribed NO-GO fork, and HALTS — a Spike FAIL is NEVER auto-accepted, even under
park-provisional (the feature PARKS). A `**Spike:**` phase should also carry a normal
`- [ ]` runtime-verification row (marked `<!-- verification-only -->`) for the proof the Spike
ticks on PASS. The Spike verdict MUST cite REAL observed evidence — never a fabricated number or a
static-trace substitute. Distinguish from `**MCP runtime:**`: MCP-test runs a fixed pass/fail
assertion suite; a Spike PROVES an open runtime question (often a measurement or an architectural
GO/NO-GO) and can itself use `/investigate`. See `docs/specs/spike-pipeline-role/SPEC.md`.
