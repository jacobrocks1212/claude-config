### Repo map — generic (no repo-specific override found)

You are onboarding into a repository that has no tailored `onboarding-repo-map.md`. Discover
the anchors from the code itself, framework-agnostically:

- **Classify the repo** from its manifests: `package.json` (+ `nx.json` / `turbo.json` / `pnpm-workspace.yaml` → monorepo), `*.csproj` / `*.sln`, `Cargo.toml`, `go.mod`, `pyproject.toml` / `setup.py`, `pom.xml` / `build.gradle`, `Gemfile`, `composer.json`.
- **Find entry points** by convention: `main`/`index`/`app`/`server`/`cmd` files; framework boot files (Rails `config/`, Spring `@SpringBootApplication`, Next.js `app/`/`pages/` + `middleware`, Django `urls.py`/`wsgi.py`, Tauri `src-tauri/`); package `exports`/`bin` fields; CLI command registries; queue/worker entrypoints.
- **Trace one real path** end-to-end before generalizing: a request, command, event, or function call from entry → handler → core logic → persistence/side-effect → output.
- **Map boundaries**: directory layout usually signals layers (`controllers`/`handlers` = presentation, `services`/`domain` = application, `repositories`/`models`/`db` = persistence, `utils`/`shared` = cross-cutting).
- **Spot generated/dead code**: `*.generated.*`, `dist/`/`build/`, lockfiles, vendored deps — note them as "looks important but isn't authored here."

Use **Explore** subagents to map large repos in parallel. Use the **tree-sitter MCP** tools
(`get_file_structure`, `find_symbol_usages`, `get_callers`, `get_callees`) for C#/TS/TSX/Vue/JS/JSX
structure before opening large files; for other languages use `Read`/`Grep`. Stay read-only.
