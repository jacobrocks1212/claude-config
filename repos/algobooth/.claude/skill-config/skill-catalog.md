### algobooth Skill Catalog (for /fix Step 6a)

Map failure categories to relevant project skills:
- **ui-ux-polish** → `algobooth-ui`, `frontend-design`, `vue`, `tailwind-design-system`
- **environment-platform** → `tauri-patterns`, `rust-best-practices`, `rust-errors`, `tauri-build`, `cargo-release` (workstation-only queue-routed builds)
- **inadequate-test-coverage** → `test-driven-development`, `rust-best-practices`, `vue`
- **tooling-config** → `nx-monorepo`, `tauri-patterns`, `ts-library`
- **inadequate-research** → `implement-phase`, `spec`, `spec-phases`
- **regression** → `verification-before-completion`, `test-driven-development`

### State machine — `/lazy` and `/lazy-cloud` step order

After PHASES.md phases all-Complete, the state machine routes through:

| Step | Skill | Cloud? | Gated on |
|------|-------|--------|----------|
| 8 | `/retro` (via `retro-feature`) | Yes (docs-only) | phases Complete + no RETRO_DONE.md |
| 9 | `/mcp-test` | No — cloud writes `DEFERRED_NON_CLOUD.md` | RETRO_DONE.md present + no VALIDATED.md |
| 10 | `__mark_complete__` | Cloud only when workstation already produced VALIDATED.md | RETRO_DONE.md + (VALIDATED.md OR cloud DEFERRED_NON_CLOUD.md) |

`/retro` precedes `/mcp-test`: the implementation-time retrospective gate fires before runtime validation, so cloud sessions (which defer MCP) still complete the retro pass. The lazy state machine does not auto-loop retro — additional rounds are triggered only when `/retro` itself writes a follow-up plan.
