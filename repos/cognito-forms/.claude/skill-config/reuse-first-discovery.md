### Reuse-First Discovery (Cognito Forms) — BLOCKING before any new design

Before proposing architecture (in `/spec`) or a fix shape (in `/spec-bug`), you MUST inventory what
already exists. The deliverable is an auditable **Reuse Ledger**. You may not commit to a design until
every load-bearing capability has a ledger row backed by cited evidence. **Do not skip this because the
feature "obviously needs new code" — that judgment is exactly what the ledger exists to verify.**

The protocol mechanics (R1–R4, the ledger, verdicts, the confidence gate, and the negative-search-trail rule) are the shared codebase-neutral core:
!`cat ~/.claude/skills/_components/reuse-discovery-protocol.md`

#### Cognito grounding resources (for the R2 discovery subagents)

Give each subagent the grounding resources that match its capability:

- **Domain skills (the authoritative map of existing systems).** Match the capability to the catalog:
  `cognito-storage` (persistence / `StorageContext`), `cognito-auth` (roles / permissions / SSO),
  `cognito-expressions` (calc + conditional logic), `cognito-payments`, `cognito-entry-indexing`,
  `cognito-queue-jobs`, `linked-lookups`, `cognito-person-fields`, `cognito-form-builder` (builder UI),
  `forms-service` (index for the 9,600-line `FormsService.cs`), `build-js` (index for the 22K-line
  `build.js`), `exoweb` + model.js (reactive entity framework), `csharp-cognito`,
  `core-controller-endpoints`.
- **Agent docs.** `.agents/agent-docs/backend-patterns.md` (which backend pattern to copy),
  `frontend-architecture.md` (which app/lib owns this), `legacy-patterns.md` (what must stay compatible
  vs. not spread further), `types-and-models.md` (server/client type rules).
- **Structural tools.** tree-sitter MCP `get_file_structure` (outline before opening large files),
  `find_symbol_usages` / `get_callers` / `get_callees` (locate existing implementations + blast radius).
  Grep/Glob for naming conventions and sibling patterns.
- **Repo map.** `.claude/skill-config/onboarding-repo-map.md` for entry points and the request trace.

In `/spec-bug`, the ledger has an extra job: identify the existing **correct** implementations the fix
should converge toward. Prefer "refactor the buggy code to match existing pattern X" over "add new code"
whenever X already exists — record X as the candidate even when the verdict is refactor.

#### Step R5 — Surface and confirm (interactive)

Present the full ledger in chat — it is the audit trail; do not abbreviate it. Then **confirm every
`build-new` and `refactor` verdict with the user via `AskUserQuestion`** before any architecture or fix
shape is committed. These are the verdicts most likely to be wrong and most expensive to get wrong;
`reuse-as-is` / `extend` / `wrap` rows at high confidence may be stated rather than asked. Match the chat
block to the picker 1:1 (the Global Rule at the top of `/spec`).

#### Step R6 — Persist the ledger

Write the confirmed ledger into the SPEC under a `## Reuse Ledger` section (in `/spec`) or into the
investigation spec's Evidence (in `/spec-bug`). `/spec-phases` consumes it: every phase will cite the
ledger rows it builds on.

**Under `--batch`:** run R1–R4 mechanically (recon is analysis, not preference) and write the ledger into
the SPEC. Skip the R5 picker. If any `build-new` / `refactor` verdict is genuinely a *product-behavior*
fork (it changes what the user gets), surface it via `NEEDS_INPUT.md` per this skill's batch halting rule;
otherwise record the verdict and proceed.
