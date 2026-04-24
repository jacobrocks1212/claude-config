# Data Modeling Guide

The data persistence layer in Cognito Forms uses **Azure Table Storage** and **Cosmos DB** via a custom Unit of Work pattern centered around the `IStorageContext` interface. There is NO Entity Framework in this codebase.

## 1. Entity Definition

- **POCOs**: Data models are standard C# classes (Form, FormEntry, Organization, etc.)
- **`IEntity` Interface**: All persistent entities implement `IEntity` (defined in `Cognito.Amender/`), which requires a `string Id` property
- **Location**: Core entities are in `Cognito.Core/Model/`, organized by domain (Forms/, Payment/, AI/, Plans/)

## 2. Storage Architecture

```
IStorageContext (unit-of-work interface)
  └── StorageContext (implementation)
        ├── EntityStore (JSON serialization, encryption, revision transforms)
        ├── Repository<T> (Cosmos DB with retry logic, ETag concurrency)
        └── AzureStore (Azure Table Storage)
```

- All entities are partitioned by organization
- `EntityStore` handles JSON serialization with custom converters, revision transforms, and automatic encryption/decryption
- `Repository<T>` provides Cosmos DB access with exponential backoff retry (max 30 retries) and ETag-based concurrency

## 3. CRUD Operations

```csharp
// Read
var entity = storageContext.Get<T>(id);
var entity = await storageContext.GetAsync<T>(id);
var entity = storageContext.Get<T>(id, bypassCache: true);
var cached = storageContext.TryGetFromCache<T>(id);

// Write
storageContext.Store(entity);
storageContext.CreateOrUpdate<T>(entity);
await storageContext.BatchCreateOrUpdate<T>(entities); // max 100 per batch

// Update with concurrency
await storageContext.UpdateAsync<T>(id, async entity =>
{
    entity.Property = newValue;
});

// Query (prefer GetAll/GetRange over Query which is [Obsolete])
var all = storageContext.GetAll<T>();
var range = storageContext.GetRange<T>(startId, endId);
```

## 4. Caching

- `EntityCache` uses `ConcurrentDictionary<Type, ITypeCache>` for per-type caching
- Per-type cache threshold triggers flush on query operations
- Use `bypassCache: true` on `Get<T>` for fresh reads when needed
- Use `TryGetFromCache<T>()` for cache-only lookups (no storage hit)

## 5. Naming and Property Conventions

- **Class Names**: PascalCase (Form, FormEntry, UserFolderMeta)
- **Property Names**: PascalCase (FirstName, CreatedDate, IsArchived)
- **Primary Key**: `string Id` property on all entities
- **Auditing**: Most entities include `Created` and `Modified` timestamps
