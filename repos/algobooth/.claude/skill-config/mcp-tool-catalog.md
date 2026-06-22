## MCP Tool Catalog (AlgoBooth)

> **Catalog absent → MCP tool-existence audit is a no-op.** This file declares WHERE
> AlgoBooth's live MCP tool surface is enumerated so the shared (repo-agnostic)
> `/spec-phases` capability audit (`phases-runtime-validation.md`, Step 2.7) can grep the
> right registry paths. A repo WITHOUT this file gets no MCP tool-existence audit — the
> audit degrades to a recorded skip, never an error — exactly as the SPEC-example
> capability audit skips when its source is unconfigured. Only repos with a live MCP
> surface (AlgoBooth is the only one today) configure this catalog.

### Live-registry source paths (the audit greps these — never a stale copy)

The registered-tool-name set is derived by grepping the two **live registration sources**.
There is no generated manifest: the registrations ARE the live surface, so a generated copy
would only add a build-order dependency and a staleness risk for no fidelity gain.

| # | Source path (AlgoBooth repo-relative) | Language | What it registers | How the audit derives tool names |
|---|---------------------------------------|----------|-------------------|----------------------------------|
| 1 | `scripts/mcp-test/tool-methods.ts` | TypeScript | The authoritative tool-name → HTTP-method map the deterministic mcp-test engine consumes | Each entry's tool-name string-literal key (the left-hand side of the method map) is a registered tool name. |
| 2 | `src-tauri/src/ipc/mcp/registrations/` (Rust module dir; entrypoint `mod.rs`) | Rust | The native tool registrations submitted at compile time via `inventory::submit!` | Each `inventory::submit!` site carries the tool-name string literal it exposes; that literal is a registered tool name. Grep the macro sites for the name argument. |

> **Path-resolution note (this catalog was authored in `claude-config`, not in the live
> AlgoBooth tree).** The two paths above are the proven AlgoBooth registration sites named in
> the bug's SPEC (Proven Finding 4) and corroborated by the repo's own existing skill-config
> docs (`.claude/skills/mcp-test/SKILL.md` — `tool-methods.ts` map + `inventory::submit!`
> compile-time registration; `.claude/skill-config/investigation-runtime.md` and
> `phases-runtime-validation.md` — `src-tauri/src/ipc/mcp/registrations/`). When the audit runs
> IN the live AlgoBooth tree, it should confirm each path resolves before grepping; if a path
> has drifted (e.g. `registrations/mod.rs` vs a flat `registrations.rs`), the audit records the
> ACTUAL resolved path it grepped and never invents one. The Rust registration macro is
> `inventory::submit!`; if the live tree has migrated to a different registration macro
> (`register_tool`, a tool-registry module), grep that real site instead and record it.

### Grep contract — the per-tool ledger the audit consumes

For each MCP tool the SPEC's validation NAMES (see `phases-runtime-validation.md`'s
"MCP tool-existence audit"), the audit greps both source paths above for the tool-name
registration and records exactly one ledger row per tool:

| tool-name | registered? | source (file:line, or "no hits") |
|-----------|-------------|----------------------------------|
| `load_test_tone` | yes | `scripts/mcp-test/tool-methods.ts:42` |
| `set_slip_pad_template` | no | no hits in either source — required-but-missing → auto-author a build phase |

- **`registered? = yes`** iff the tool-name literal appears in EITHER source (the TS method map
  OR a Rust `inventory::submit!` site). Cite the first hit's `file:line`.
- **`registered? = no`** iff the tool-name literal has zero hits in BOTH sources. A `no` row is
  a required-but-missing tool: the audit auto-authors a "build MCP tool X" phase up front
  (per `phases-runtime-validation.md` / Locked Decision 2), NOT a late `/mcp-test` discovery.

This is the SAME enumerate→grep→record-ledger-row shape the existing SPEC-example capability
audit uses for API surfaces — applied to the MCP tool catalog declared here.
