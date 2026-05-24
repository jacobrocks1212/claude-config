### Repo map — AlgoBooth

Rust/Tauri desktop app with a TypeScript/Vue frontend and Web Audio. Nx workspace. Feature specs,
queue, and roadmap live under `docs/features/`.

Verified depth on internals is limited — the anchors below are starting points. **Verify each on
first read** (open the file, confirm the symbol/path) before stating it as fact in the orientation.

#### Frontend (TS/Vue)
- `src/` — Vue/TypeScript application. UI components in `src/components/` (per the `algobooth-ui` skill).
- Web Audio code lives in the frontend (per the `web-audio` skill) — audio runs through Web Audio API nodes.

#### Backend (Rust/Tauri)
- `src-tauri/` — the Rust crate (per the `tauri-patterns` skill). Entry typically
  `src-tauri/src/main.rs` *(verify on first read)*.
- **Tauri commands** (`#[tauri::command]`) form the Rust↔JS IPC boundary — this is the
  cross-language seam to trace.

#### Specs / workflow
- `docs/features/<feat>/SPEC.md`, `queue.json`, `ROADMAP.md` — the native home of the `/spec` +
  `/lazy` workflow. Read these to understand what's built, in progress, and planned.

#### Cross-language trace
UI event (Vue component in `src/components/`) → Tauri `invoke` IPC → Rust command handler in
`src-tauri/` → core Rust logic → result back across IPC → reactive UI update.

#### Tooling
- **tree-sitter MCP** covers the **frontend (TS/Vue/JS) only — not Rust.** Read Rust structure with
  `Read`/`Grep`; use tree-sitter (`get_file_structure`, `get_callers`, etc.) for the Vue/TS half.
- Do **not** run `tauri:dev` or `/mcp-test` (those launch the app — read-only onboarding).

#### Newcomer traps
- The cross-language boundary is the Tauri IPC: Rust `#[tauri::command]` ↔ JS `invoke`. Most
  "how does the UI do X" questions cross it.
- Audio timing and Web Audio node graphs.
- The queue-driven `docs/features` workflow — the codebase is organized around feature specs.
