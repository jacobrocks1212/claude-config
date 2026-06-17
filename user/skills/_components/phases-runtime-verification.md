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
  so it can route the phase forward to the MCP gate (Step 9 — retro at Step 8
  is unwired, 2026-06) instead of looping back on write-plan/execute-plan.
  A `- [ ]` checkbox placed under
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

  MARKER-FIRST (harness-hardening-retro-fixes Phase 2 — SUPERSEDES the old
  regex-lockstep). The detector now keys off the STRUCTURAL canonical marker
  `<!-- verification-only -->` (SSOT: `lazy_core:_VERIFICATION_ONLY_MARKER`),
  NOT the subsection header's free text. So a NEW verification/escalation
  subsection-header convention NO LONGER needs a new regex alternative — just
  emit the per-row marker on its `- [ ]` rows (as this component and
  `blocked-resolution.md` now do) and the gate recognizes them regardless of the
  header phrasing. Do NOT grow `_VERIFICATION_SECTION_RE` — it is now a
  DEPRECATION SHIM that merely warns (a `_DIAGNOSTICS` entry) when a row was
  exempted by header-text alone with the marker absent (i.e. an un-migrated
  producer). The shim still covers: "Runtime Verification", "MCP Integration
  Test" / "MCP (test) assertion(s)", "Reachability smoke", and the retry_count>=2
  escalation "Full-chain seam audit" / "seam audit" / "seam re-validation" family
  — but those are the LEGACY un-migrated cases, not the path new conventions take.
  (Two consecutive single-phrase regex gaps in one run, 2026-06-16, motivated the
  move to the structural marker.)

  ╔══════════════════════════════════════════════════════════════════════════╗
  ║  GATE-OWNED ROW BAN — pipeline-owned actions are never checkbox rows     ║
  ╚══════════════════════════════════════════════════════════════════════════╝

  Pipeline-owned actions are NEVER authored as checkbox rows — not in
  Deliverables, not under Runtime Verification. The class: SPEC.md / PHASES.md
  top-level `**Status:**` flips, COMPLETED.md / FIXED.md receipt writes, ROADMAP
  completion marks, and archive moves. These are owned by the
  `__mark_complete__` / `__mark_fixed__` gate (which now auto-flips coherent
  phases and REFUSES incoherent ones); a checkbox for them is unplannable,
  untickable work that loops the state machine's routing. (Live incident
  2026-06-11: a `- [ ] Update SPEC.md status to "Complete"` row in
  d8-live-looping's Phase 6 deliverables routed write-plan repeatedly until a
  manual recovery relocated it.) Author such facts as a prose
  **Completion (gate-owned):** note instead — e.g.
  `**Completion (gate-owned):** the __mark_complete__ gate flips SPEC.md
  **Status:** to Complete and writes COMPLETED.md once this phase's runtime
  verification passes.` Ordinary doc-edit deliverables ("Update SPEC §X
  wording") remain legitimate checkboxes — the ban is on pipeline-owned
  STATUS / receipt / archive actions only.

  ╔══════════════════════════════════════════════════════════════════════════╗
  ║  REACHABILITY SMOKE — every new API surface carries one in-phase smoke   ║
  ╚══════════════════════════════════════════════════════════════════════════╝

  Any phase that introduces a NEW user-facing API surface (a new MCP tool, a
  new pattern-language method/builder, a new IPC command, a new UI-reachable
  action) MUST carry one in-phase **reachability smoke** row under Runtime
  Verification: a single MCP call proving the surface is callable end-to-end
  (reachable, not behaviorally correct — behavioral validation stays in the
  feature's Step-9 scenario). Tag the row `(reachability-smoke —
  workstation-eligible)` so cloud deferral lists it individually instead of
  batching it silently behind DEFERRED_NON_CLOUD.md. Motivating incident:
  d8-live-looping reached its Step-9 MCP gate with the documented
  `track(...).record()` API never reachable (0/16 BLOCKED) after eight phases
  — the gap was detectable from the first API phase with one smoke call.
  Example row (note the canonical marker right after the checkbox):
  `- [ ] <!-- verification-only --> reachability smoke (reachability-smoke —
  workstation-eligible): MCP call to <new tool/command> returns a non-error
  response (surface is callable end-to-end; behavioral correctness is asserted
  in the Step-9 scenario).`

  ╔══════════════════════════════════════════════════════════════════════════╗
  ║  TERMINAL-MCP-STACKING BAN — integration cannot all land in one phase     ║
  ╚══════════════════════════════════════════════════════════════════════════╝

  Decomposition red flag: MORE THAN TWO consecutive phases declaring
  `MCP Integration Test Assertions: N/A` while ALL integration assertions land
  in a single terminal phase. That shape guarantees defects stack silently and
  are discovered SERIALLY at end-of-feature validation — one full corrective
  round per layer. (Motivating incident: 5 of d8-live-looping's 6 original
  phases were `N/A — engine-only`, all built in cloud sessions where every
  runtime check defers; terminal validation then found three stacked defects
  across three ~1M-token BLOCKED→add-phase rounds.) When the breakdown has this
  shape, the author MUST place a **vertical tracer-bullet smoke** at the
  EARLIEST phase where the user-surface → engine → observable chain minimally
  exists: one Runtime Verification row driving the SPEC's canonical code
  example end-to-end live (≥1 assertion — reachable AND minimally observable),
  tagged `(reachability-smoke — workstation-eligible)` like the smoke rows
  above. Pure-engine prefix phases (no chain yet) remain legitimately N/A —
  the ban is on deferring the FIRST end-to-end probe past the phase where the
  chain first exists.
-->
<!--
  ╔══════════════════════════════════════════════════════════════════════════╗
  ║  CANONICAL VERIFICATION-ONLY MARKER (harness-hardening-retro-fixes Ph 2)  ║
  ╚══════════════════════════════════════════════════════════════════════════╝

  Every verification / runtime / MCP-assertion / reachability-smoke `- [ ]`
  checkbox this component authors MUST carry the canonical per-row marker
  `<!-- verification-only -->` (an HTML comment, invisible in rendered markdown).
  The state-script detector `remaining_unchecked_are_verification_only()` keys
  off THIS marker — structurally, independent of the subsection header's free
  text — so a novel header phrasing no longer gaps the gate (and the legacy
  `_VERIFICATION_SECTION_RE` is now only a deprecation shim that WARNS when a row
  is exempted by header-text alone, with the marker absent).

  SSOT: the marker string is owned by `lazy_core:_VERIFICATION_ONLY_MARKER`
  (`user/scripts/lazy_core.py`). Do NOT re-hardcode a divergent string here — the
  lockstep test (`test_ruvonly_marker_lockstep_producers_match_ssot`) asserts the
  value below equals that constant. If the marker form ever changes, change the
  constant and re-sync this value (and `blocked-resolution.md`).

  Place the marker at the START of each verification row (right after `- [ ] `).
  A marker on the subsection HEADER line also works (header-scope: exempts every
  row beneath until the next phase/section boundary) — but the per-row form is
  preferred for robustness.
-->
**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> {Observable runtime behavior 1 — e.g., "API returns expected response after action"}
- [ ] <!-- verification-only --> {Observable runtime behavior 2 — e.g., "database contains expected records"}

**MCP Integration Test Assertions:**
{If the feature's SPEC.md has a Validation Criteria table, extract the rows relevant to this phase and express them as concrete assertions a test agent can verify at runtime. Format:}
```
ASSERTIONS:
1. After {trigger action}: {observable evidence} MUST {condition}
2. ...
```
{If no runtime-observable behavior in this phase (e.g., pure types, config), write "N/A — no runtime-observable behavior in this phase"}
