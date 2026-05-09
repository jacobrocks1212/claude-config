## Mount-Site Verification (MANDATORY for new files)

After reviewing subagent output, verify that every NEW file created is actually imported/used somewhere in the codebase.

### Protocol

For each **new file** created by a subagent in this batch:

1. **Grep for imports:** Search the codebase for `import ... from '{new-file-path}'` or `require('{new-file-path}')` (TS/JS) or `mod {module_name}` / `use {crate}::{module}` (Rust)
2. **Check for mount-site:** If the file exports a composable (`use*`), component, plugin, or class, confirm it is **called/mounted** somewhere — not just importable
3. **Flag orphans:** If zero imports found AND the file exports callable code → flag as:

   > ⚠️ **Orphaned module:** `{path}` — created but never imported or mounted. Must be wired into the app before marking as complete.

4. **Verdict impact:** If any orphaned modules found, the review verdict MUST be `NEEDS-REWORK` unless the file is explicitly documented as consumed by a later batch in the same phase.

### Exceptions (do NOT flag)

- Type definition files (`*.d.ts`, `types/*.ts`) — consumed by the type system, not imports
- Test files — consumed by the test runner
- Config files (`.eslintrc`, `Cargo.toml`, etc.) — consumed by tooling
- Files explicitly marked in the plan as "consumed in Batch N+1"

### Common Patterns to Catch

| Pattern | Example | Fix |
|---------|---------|-----|
| Composable created but not mounted | `useVisualStateTelemetry.ts` exists, nothing calls `useVisualStateTelemetry()` | Mount in App.vue or relevant view |
| Plugin created but not installed | `telemetryPlugin` exported, not in `pinia.use()` | Add to main.ts |
| Rust module created but not declared | `telemetry.rs` exists, no `pub mod telemetry;` in parent | Add mod declaration |
| Wrapper created but callsites not migrated | `tauri-invoke.ts` wraps invoke, old imports remain | Migrate all import sites |
