### Repo map — Cognito Forms

Multi-tenant form builder. **Backend:** C# on .NET Framework 4.7.2 (SDK-style csproj), Azure.
**Frontend:** Vue 2.7 Composition API + TypeScript, Nx monorepo (pnpm).

#### Backend layers & entry points
Dependency flow: `Cognito.Services` / `Cognito.Queue*` → `Cognito` → `Cognito.Core`.

- `Cognito.Core/` — domain models, interfaces, service contracts. Zero intra-project deps (C# 10).
- `Cognito/` — business logic. `CoreService` is the service-hierarchy root; data access via
  `StorageContext`; Autofac `Module<T>` DI (C# 8).
- `Cognito.Services/` — ASP.NET MVC controllers + Web API; `BaseController` (shared behavior,
  JSON serialization); routing/auth. **This is the HTTP entry point** (C# 10).
- `Cognito.Queue*/` (`Cognito.QueueJob` / `QueueService` / `QueueWorker`) — background jobs/workers.

#### Frontend entry points
Build chain: `model.js → vuemodel → element-ui → client/spa` (first builds slow; Nx caches).

- `Cognito.Web.Client/apps/spa` (`cognito-spa`) — form builder / admin. `GlobalState`, composables, Element UI.
- `Cognito.Web.Client/apps/client` (`cognito-client`) — form rendering for end users.
- libs: `model.js` (reactive entity/type/property/rule framework, ExoModel-based), `vuemodel`
  (Vue 2 reactivity bridge for model.js), `element-ui` (forked), `types` (generated from server),
  `api`, `utils`.

#### Read these first
- **Backend:** the relevant controller in `Cognito.Services` → its `CoreService`/domain service in
  `Cognito` → `StorageContext` for persistence.
- **Frontend:** the entity definition in `model.js` → the `vuemodel` bridge → the Vue
  component/composable in `apps/spa` or `apps/client`.

#### Request trace
HTTP → `Cognito.Services` controller (`BaseController`) → `Cognito` service (CoreService hierarchy)
→ `StorageContext` → JSON response. Storage: Azure Table (primary entities), Blob (files/large data),
Cosmos (query-heavy), Redis (caching/rate-limiting). Background work → queue → `Cognito.Queue*` worker.

#### Tooling
- **tree-sitter MCP** covers C#/TS/Vue — use `get_file_structure` before opening large files;
  `find_symbol_usages` / `get_callers` / `get_callees` for blast radius.
- **`FormsService.cs` is 9,600+ lines** — consult the `forms-service` index skill before reading it.
- Do **not** run `/msbuild` or `/mstest` (read-only onboarding).

#### Navigation aids (not substitutes for the code)
Domain skills: `cognito-auth`, `cognito-payments`, `cognito-entry-indexing`, `cognito-expressions`,
`linked-lookups`, `cognito-storage`, `cognito-queue-jobs`, `cognito-person-fields`. Also
`knowledge/architecture-overview.md` and per-directory `CLAUDE.local.md` files.

#### Newcomer traps
- The model.js↔backend seam runs through ExoWeb/ExoModel — trace it deliberately.
- Vue **2.7** Composition API, **not** Vue 3 (`ref()` preferred over `reactive()` for primitives).
- C# `LangVersion` varies per project (most are 8; `Cognito.Core` and `Cognito.Services` are 10).
- SDK-style csproj auto-includes `.cs` files — no manual `Compile` items.
- Two test projects: `Cognito.UnitTests` (unit/MSTest — most service/unit tests) vs.
  `Cognito.Forms.UnitTests` (Selenium/browser integration).
