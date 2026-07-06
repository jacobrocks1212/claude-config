---
kind: implemented
feature_id: skip-mcp-test-frontmatter-unquoted-colon
date: 2026-07-06
provenance: pipeline-gated
derivation: message-grep
commits: [4b2bb66, 46bb6cb, 4601fbb, d650926, f9e30b7, 3b736ac, 501ac8c]
decisions: []
---

# Implementation Ledger

**What shipped:** A `SKIP_MCP_TEST.md` waiver whose YAML frontmatter carries an **unquoted colon-space inside a value** (e.g. `reason: blocked by X: no host device`, or a `skipped_by:` line naming a `key: value` pair) makes the strict PyYAML-backed sentinel reader (`parse_sentinel`) raise a `ScannerError`, which `_die()`s the whole state script (exit 2). Because the completion / Step-9 leg reads the waiver through that strict parser, a colon a human naturally typed into a prose reason HARD-HALTS the pipeline at the finish line — a fully-waived feature cannot certify. The current mitigation is prose discipline ("quote colon-bearing values"), exactly the human-remembered invariant the harness mission says to replace with a mechanical guarantee.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
