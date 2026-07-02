# Cognito — Application/Business Logic Layer

## Gotchas
- **C# 8.0** (LangVersion 8.0) — no records, no init-only, no target-typed new, no pattern matching with and/or/not
- `ModuleFactory.GetModuleService()` is `[Obsolete]` — use `Module<T>` DI pattern instead
- `ModuleFactory.CoreService` is a static ambient property (HttpContext.Items or AsyncLocal fallback) — avoid in new code
- If deserialized JSON doesn't start with `{`, it's encrypted — `EntityStore` decrypts automatically

## Service Hierarchy
```
BaseService (takes IStorageContext)
  └── CoreService (god-service, extends BaseService)

OrgScopedService (takes IOrganizationContext)
  └── OrgUserScopedService (adds user context)
      └── Concrete services (LinkedLookupServiceBase, etc.)
```

### BaseService
- Constructor patterns: `(IStorageContext)`, `(ICoreService)`, `(Organization)`
- Provides `StorageContext`, `Serialize()`, `DecryptToken()`

### OrgScopedService
- `orgContext.StorageContext`, `orgContext.Organization`
- Newer pattern — prefer over BaseService for org-scoped work

### ModuleService<TService, TConfiguration>
- Base for module services (Forms, Payment, etc.)
- `IModuleService<TConfiguration>` interface

## Data Layer
```
Data/
  IStorageContext    Unit-of-work with context-scoped caching
  StorageContext     Implementation — Get<T>, Store<T>, CreateOrUpdate<T>, BatchCreateOrUpdate<T>
  EntityStore        JSON serialization with custom converters, revision transforms, encryption
  Repository<T>     Cosmos DB with retry logic (exponential backoff, max 30 retries, ETag concurrency)
  AzureStore         Azure Table Storage
  IFileStore         Blob abstraction (AzureFileStore, TestFileStore)
```

### Storage Patterns
- `EntityCache` uses `ConcurrentDictionary<Type, ITypeCache>` — per-type size threshold triggers flush on query
- Batch limit: 100 operations (`EntityStore.MaxBatchOperationCount`)
- All entities partitioned by organization
- `JsonUtility.Serialize()` / `Deserialize()` for general use
- Cache bypass: `StorageContext.Get<T>(id, bypassCache: true)` for fresh reads, `TryGetFromCache<T>()` for cache-only lookups

## DI
- `ModuleFactory` — legacy reflection-based service discovery by namespace convention (`Cognito.{Module}.Services` or `Cognito.Core.Services.{Module}`)
- `Module<T>` — modern DI pattern, registered as SingleInstance in Autofac
- `WebAppModule.cs` — web-layer Autofac registration

## ExoWeb/
Legacy JS framework bridge — contains JS expression translation and ExoModel JSON serialization helpers. The ExoModel types (`ModelType`, `ModelInstance`, etc.) are defined in `Public/ExoModel/`, not here.

## Key Files
| File | Purpose |
|------|---------|
| `BaseService.cs` | Root service base class |
| `CoreService.cs` | Main god-service |
| `ModuleFactory.cs` | Legacy service discovery (obsolete) |
| `ModuleService.cs` | Module service base |
| `Services/OrgScopedService.cs` | Modern org-scoped base |
| `Data/StorageContext.cs` | Unit-of-work implementation |
| `Data/EntityStore.cs` | Serialization + revision transforms |

---

## Maintaining This Document

Update this file when:
- Adding new architectural patterns or service hierarchies
- Discovering non-obvious gotchas that would trip up future developers
- Renaming or restructuring directories/files mentioned here

Do NOT add: version numbers, line numbers, test counts, or other specifics that change frequently.
