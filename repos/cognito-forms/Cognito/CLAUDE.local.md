# Cognito — Application/Business Logic Layer

## Gotchas
- **C# 8.0** (LangVersion 8.0) — no records, no init-only, no target-typed new, no and/or/not patterns
- `ModuleFactory.GetModuleService()` is `[Obsolete]` — use `Module<T>` DI pattern instead
- `ModuleFactory.CoreService` is a static ambient property (HttpContext.Items or AsyncLocal fallback) — avoid in new code
- If deserialized JSON doesn't start with `{`, it's encrypted — `EntityStore` decrypts automatically

## Service Hierarchy
- `BaseService` → `CoreService` (god-service). Ctor patterns: `(IStorageContext)`, `(ICoreService)`, `(Organization)`. Provides `StorageContext`, `Serialize()`, `DecryptToken()`.
- `OrgScopedService` (`Services/OrgScopedService.cs`, takes `IOrganizationContext` → `.StorageContext`, `.Organization`) → `OrgUserScopedService` (adds user context) → concrete services. Newer pattern — prefer over BaseService for org-scoped work.
- `ModuleService<TService, TConfiguration>` — base for module services (Forms, Payment, etc.); interface `IModuleService<TConfiguration>`

## Data Layer (`Data/`)
- `StorageContext` — unit-of-work with context-scoped caching: `Get<T>`, `Store<T>`, `CreateOrUpdate<T>`, `BatchCreateOrUpdate<T>`. Batch limit: 100 operations (`EntityStore.MaxBatchOperationCount`).
- `EntityCache` uses `ConcurrentDictionary<Type, ITypeCache>` — per-type size threshold triggers flush on query. Cache bypass: `Get<T>(id, bypassCache: true)` for fresh reads, `TryGetFromCache<T>()` for cache-only lookups.
- `EntityStore` — JSON serialization with custom converters, revision transforms, encryption. `Repository<T>` — Cosmos DB with retry logic (exponential backoff, max 30 retries, ETag concurrency). `IFileStore` — blob abstraction.
- All entities partitioned by organization; `JsonUtility.Serialize()`/`Deserialize()` for general use

## DI
- `ModuleFactory` — legacy reflection-based service discovery by namespace convention (`Cognito.{Module}.Services` or `Cognito.Core.Services.{Module}`)
- `Module<T>` — modern DI pattern, registered as SingleInstance in Autofac

## ExoWeb/
Legacy JS framework bridge — JS expression translation and ExoModel JSON serialization helpers. The ExoModel types (`ModelType`, `ModelInstance`, etc.) are defined in `Public/ExoModel/`, not here.

Maintenance: record non-obvious gotchas and pattern/structure changes here; do NOT add version numbers, line numbers, or test counts.
