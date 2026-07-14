# Cognito — Application/Business Logic Layer

## Gotchas
- **C# 8.0** (LangVersion 8.0) — no records, no init-only, no target-typed new, no and/or/not patterns
- `ModuleFactory.GetModuleService()` is `[Obsolete]` — use `Module<T>` DI pattern instead
- `ModuleFactory.CoreService` is a static ambient property (HttpContext.Items or AsyncLocal fallback) — avoid in new code
- If deserialized JSON doesn't start with `{`, it's encrypted — `EntityStore` decrypts automatically
- **Overwatch integration convention:** new Cognito columns surface in Overwatch via OW **sync** (`[Overwatch]` attribute mirroring — the column is added automatically, ~7-min delay); classic `CognitoEvent`s are being **phased out** — consult the OW team before adding a new classic event (source: OW team / George Perez, Slack 2026-07-10)
- Org-archive retention (`CoreService.PurgeOrganization` → `DeleteAllProjectEntities`) is **attribute-driven**: entity/config types marked `[RetainOnArchive]` (`Cognito.Helpers.Attributes`) survive the archive purge, discovered by reflection. Grep the attribute, not a `retainable*EntityTypeNames` string array (those were removed). `retainableModuleCodes` is a *separate* mechanism (module teardown-skip, keyed on `Module.Code`) — not the entity retention set. Fail-closed: under the CognitoPay flag, an empty attributed set aborts the purge (`PurgeOrganizationException`) rather than hard-deleting
- **Durable-decision ordering on the purge path (load-bearing for retry safety).** `PurgeOrganization` stamps `DateArchived` + persists the org (`ReplaceAsync`) **after** the module teardown loop (so the `Plans`→Stripe cancel has already run — billing-stop preserved, no double-cancel on the +1h re-purge) but **before** `DeleteAllProjectEntitiesAsync` flips the retained accounts to `Inactive`. This makes the top-of-method idempotency guard (`DateArchived != null → return`) authoritative on a queue redelivery: a mid-archive failure can never re-derive `archive` from the mutated `PaymentAccount.Status` and hard-delete retained data. The stamp is deliberately NOT inside a swallow-catch (it lives in `PurgeOrganization`, not `DeleteOrganization`) so a failed stamp write propagates → queue retries. General rule: never derive a destructive/retain decision from state the same operation mutates — stamp the durable marker first.
- **Org-fetch accessors fail-safe on archived orgs (default-EXCLUDE).** The single-org accessors — `ICoreService.GetOrganization`/`GetOrganizationAsync`/`GetOrganizationByCode`/`GetOrganizationByPublicKey` (and the parallel `IOrganizationService.GetOrganization` / `IOrganizationCodeService.GetOrganizationByCode`) — return **null by default** for an archived org (`DateArchived != null`), so unaudited callers fail safe exactly as a hard-delete used to. Pass `includeArchived: true` ONLY at genuine-shell boundaries (support impersonation, auth revalidation). Note the `ICoreService` opt-ins are **overloads** (`GetOrganization(id, bypassCache, includeArchived)` needs an explicit `bypassCache`), not a 3rd default param — a default param broke Moq expression trees (CS0854). **Ref-based resolution is deliberately OUTSIDE this fail-safe surface:** both `StorageContext.Get(orgRef)` (the `Reference<Organization>` overload) AND the `[Obsolete]` implicit `Organization(OrganizationRef)` operator opt in (`includeArchived: true`) to preserve current-tenant behavior — only the direct id/code/key string calls default-exclude.

## Service Hierarchy
- `BaseService` → `CoreService` (god-service). Ctor patterns: `(IStorageContext)`, `(ICoreService)`, `(Organization)`. Provides `StorageContext`, `Serialize()`, `DecryptToken()`.
- `OrgScopedService` (`Services/OrgScopedService.cs`, takes `IOrganizationContext` → `.StorageContext`, `.Organization`) → `OrgUserScopedService` (adds user context) → concrete services. Newer pattern — prefer over BaseService for org-scoped work.
- `ModuleService<TService, TConfiguration>` — base for module services (Forms, Payment, etc.); interface `IModuleService<TConfiguration>`

## Data Layer (`Data/`)
- `StorageContext` — unit-of-work with context-scoped caching: `Get<T>`, `Store<T>`, `CreateOrUpdate<T>`, `BatchCreateOrUpdate<T>`. Batch limit: 100 operations (`EntityStore.MaxBatchOperationCount`).
- `EntityCache` uses `ConcurrentDictionary<Type, ITypeCache>` — per-type size threshold triggers flush on query. Cache bypass: `Get<T>(id, bypassCache: true)` for fresh reads, `TryGetFromCache<T>()` for cache-only lookups.
- `EntityStore<T>` — JSON serialization with custom converters, revision transforms, encryption; `AzureStore<T>` is its only production implementation. `Repository<T>` — Cosmos DB with retry logic (exponential backoff, max 30 retries, ETag concurrency). `IFileStore`/`AzureFileStore` — blob abstraction. `JsonUtility.Serialize()`/`Deserialize()` for general use.

## Storage topology (Table vs Cosmos — where things ACTUALLY live)

The recurring confusion ("is this in Table Storage, Cosmos, both?") comes from treating `StorageContext` as a multi-backend router. It is not. The two backends are reached by **different APIs** and hold **disjoint** entity sets:

- **`StorageContext` (`IStorageContext`) → Azure Table Storage, unconditionally.** Every `Get<T>`/`Store<T>`/`CreateOrUpdate<T>`/`Purge` funnels through `StoreFactory.GetEntityStore<T>()`, which is fixed to `AzureStore<T>` at construction (`Configuration.StoreTypes`). There is NO per-type Table-vs-Cosmos dispatch inside `StorageContext`. If you access a type through `IStorageContext`, it lives in **Table Storage** (with Blob side-tables for >64 KB payload offload, autonumber id counters, and file attachments).
- **Cosmos → only via an injected `IRepository<T>`/`Repository<T>` subclass, never through `StorageContext`.** `ICosmosEntity` is the generic *constraint* on `Repository<T>`, not a routing switch. To know a type's home, ask: *is it accessed via an `IRepository<T>` (e.g. `IOrderRepository`, `IIndexRepository`)?* → Cosmos. Otherwise → Table. No type is in both.

**Three separate Cosmos ACCOUNTS** (distinct connection strings + database names in config under `storage/…`, resolved by distinct `CosmosClient` subclasses via `CosmosClientFactory` — not databases within one account):

| Cosmos account | Config / client | Entities (container, partition key) |
|---|---|---|
| Main (`cognitoIndexes`) | `CosmosOptions` / `CosmosClient`(+`BulkCosmosClient`) | `CompositeEntryIndex` (`FormEntryIndex`, key = org+form) · `EntryDependency` (`EntryReferences`, hierarchical org+form) |
| Audit log | `AuditLogCosmosOptions` / `AuditLogCosmosClient` | `OrganizationAuditLogEntry` |
| CognitoPay | `CognitoPayCosmosOptions` / `CognitoPayCosmosClient` | `CognitoOrder` (`Order`) · `CognitoPayment` (`Payment`) · `CognitoDispute` (`Dispute`) — all `OrgScopedRepository`, key = `Organization.Id`; `CognitoPayout` (`Payout`), key = **`ProviderAccountId`** |

**"All entities partitioned by organization" is FALSE — three counterexample classes:**
- `[UseIdPartition]` (Table): partitioned by the entity's own id, not the org, so they are cross-org/global tables and `StorageContext` blocks org-scoped ops on them (`ThrowIfIdPartitioned<T>`). Examples: `EmailIndex`, `VerificationCode`, `ScheduledQueueMessage`, `RenewedSession`, `SessionRenewalToken`, `TaxInformation`, `LlmPricing`.
- Main-Cosmos indexes use a composite **org+form** partition key, not org alone.
- `CognitoPayout` (CognitoPay Cosmos) is partitioned by **`ProviderAccountId`**.

**Purge reach (load-bearing for org-delete / archive).** `CoreService.DeleteAllProjectEntities` → `orgStorageContext.Purge(type)` touches **Table Storage only** (plus the blob side-effects `AzureStore` owns). It does NOT reach ANY Cosmos data. Cosmos is purged separately via `Repository<T>.PurgePartition` (→ `DeleteAllItemsByPartitionKeyStreamAsync`): the main-Cosmos index/dependency data is purged by the `PurgeCosmosData` queue handler per form partition; the **CognitoPay Cosmos is never swept by the org-delete flow at all** (Order/Payment/Dispute/Payout survive org deletion by topology). This is why CognitoPay read-model data must be reasoned about as "retained unless explicitly purged," the inverse of Table-backed entities.

## DI
- `ModuleFactory` — legacy reflection-based service discovery by namespace convention (`Cognito.{Module}.Services` or `Cognito.Core.Services.{Module}`)
- `Module<T>` — modern DI pattern, registered as SingleInstance in Autofac

## ExoWeb/
Legacy JS framework bridge — JS expression translation and ExoModel JSON serialization helpers. The ExoModel types (`ModelType`, `ModelInstance`, etc.) are defined in `Public/ExoModel/`, not here.

Maintenance: record non-obvious gotchas and pattern/structure changes here; do NOT add version numbers, line numbers, or test counts.
