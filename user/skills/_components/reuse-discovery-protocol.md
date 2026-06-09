<!-- Shared, codebase-neutral reuse-discovery protocol core. Consumed by both /spec's reuse-first-discovery.md and the cognito-pr-review plugin's reuse agents. One source of truth — do not fork. -->

## Reuse-First Discovery — Protocol Core (codebase-neutral)

Before proposing architecture or a fix shape, you MUST inventory what already exists. The deliverable is
an auditable **Reuse Ledger**. You may not commit to a design until every load-bearing capability has a
ledger row backed by cited evidence. **Do not skip this because the change "obviously needs new code" —
that judgment is exactly what the ledger exists to verify.**

### Step R1 — Extract load-bearing capabilities

From the change request (feature request, or verified symptoms + affected area), list the distinct
capabilities the work touches: data types, services, UI surfaces, domain concepts, integration points.
Each becomes a ledger row to resolve.

### Step R2 — Dispatch parallel discovery subagents

Fan out one discovery subagent per capability cluster (group related capabilities; cap at ~6 agents).
Each subagent finds existing systems / types / components / conventions / patterns that already
implement — or sit adjacent to — its assigned capability, and returns ledger rows with cited evidence.

Ground each subagent in the **consuming context's** resource catalog — the consuming wrapper supplies the
concrete list. The generic categories are:

- **Domain / system-map skills** — skills that map the existing system's major subsystems, services, and
  persistence layers. Match each capability cluster to the skills that cover its area.
- **Architecture and pattern docs** — architectural guides, backend-pattern references, frontend-ownership
  maps, legacy-seam notes, and type/model rules applicable to the codebase.
- **Structural code-navigation tools** — AST-based tools (file structure outlines, symbol-usage queries,
  caller-graph / callee-graph lookups) plus Grep/Glob for naming conventions and sibling patterns.

**A subagent that finds nothing for its capability must return the explicit negative trail** — which
skills, docs, and symbols it searched — not an empty result.

### Step R3 — Assemble the Reuse Ledger

Merge the subagent rows into one table:

| Capability | Existing candidate (file:line / symbol) | What it does today | Verdict | Evidence | Confidence |
|---|---|---|---|---|---|
| \<capability\> | `path/to/File.ext:line` (`SymbolName`) | \<one line\> | reuse \| extend \| refactor \| wrap \| acceptable-new | \<skill / grep / tree-sitter trail\> | high \| med \| low |

Verdicts:
- **reuse** — existing code already does this; call it.
- **extend** — an existing type/service gains a member or case; no new system.
- **refactor** — existing code is the right home but must change shape; name its callers (caller-graph
  query) so blast radius is captured before any design is committed.
- **wrap** — compose existing pieces behind a thin new seam.
- **acceptable-new** — nothing suitable exists, and that has been proven via a recorded negative-search trail.

### Step R4 — 100%-confidence gate (BLOCKING)

You cannot leave discovery until BOTH hold:

1. **Every** load-bearing capability from R1 has at least one ledger row.
2. Every **acceptable-new** verdict carries a recorded **negative-search trail** — the specific skills,
   docs, and symbol searches that came back empty. An `acceptable-new` row without a trail is an
   unexamined default and is NOT allowed; send the subagent back to search.

### Negative-search-trail requirement (enforced at R4)

A subagent that finds nothing must return the explicit list of skills, docs, and symbols it searched —
not a bare "nothing found." This trail is the evidence that the search was thorough. Any `acceptable-new`
row missing a trail fails the R4 gate unconditionally.

### Persisting the ledger

Once the gate passes, persist the confirmed ledger into the consuming artifact (the destination is
determined by the consuming wrapper — e.g. a spec document, an investigation record, or a review
comment). Every downstream phase or fix shape cites the ledger rows it builds on.
