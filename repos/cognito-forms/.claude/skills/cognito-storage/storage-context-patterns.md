# StorageContext Usage Patterns

The `IStorageContext` interface is the primary gateway for all database operations in the application. It implements a **Unit of Work** and **Repository** pattern, abstracting away the underlying Entity Framework implementation. It should be resolved from the dependency injection container in any service that needs to access data.

## 1. Getting an Instance (Dependency Injection)

Request an `IStorageContext` instance in the constructor of your service. The DI container will provide a context that is scoped to the current request or operation.

```csharp
public class MyService
{
    private readonly IStorageContext storageContext;

    public MyService(IStorageContext storageContext)
    {
        this.storageContext = storageContext;
    }
}
```

## 2. Reading Data

### Getting a Single Entity by ID

Use the `Get<T>(id)` or `GetAsync<T>(id)` method to retrieve a single entity by its primary key. The context maintains an in-memory cache, so repeated calls for the same entity within the same context will not result in extra database queries.

```csharp
// Synchronous fetch
var form = storageContext.Get<Form>("form-id-123");

// Asynchronous fetch
var user = await storageContext.GetAsync<User>("user-id-456");
```

### Querying Entities

Use the `Query<T>()` method to get an `IQueryable<T>` that you can use with LINQ to build more complex queries. The query is not executed against the database until you enumerate the results (e.g., by calling `.ToList()`, `.FirstOrDefault()`, etc.).

```csharp
// Find all forms in a specific folder that are not archived
var formsInFolder = storageContext.Query<Form>()
    .Where(f => f.FolderId == "folder-id-789" && !f.IsArchived)
    .OrderBy(f => f.Name)
    .ToList();
```

## 3. Writing Data (Unit of Work)

The `StorageContext` acts as a Unit of Work. Changes you make to entities are tracked in memory and are only persisted to the database when the unit of work is committed.

### Adding a New Entity

Use the `Create<T>(entity)` or `CreateAsync<T>(entity)` method.

```csharp
var newUser = new User { Id = "new-user-id", Name = "John Doe" };
await storageContext.CreateAsync(newUser);
// Note: At this point, the user is tracked but not yet saved to the database.
```

### Updating an Existing Entity

Use the `Update<T>(id, updateAction)` or `UpdateAsync<T>(id, updateAction)` methods. This pattern ensures you are working with the most current version of the entity.

```csharp
await storageContext.UpdateAsync<User>("user-id-456", user => 
{
    user.LastName = "Smith";
    return Task.CompletedTask;
});
```

### Deleting an Entity

Use the `Delete<T>(id)` method.

```csharp
storageContext.Delete<Form>("form-id-to-delete");
```

### Committing Changes

**This is the most critical step.** The underlying `StoreFactory` and `EntityStore` implementations handle the actual saving. In a typical service method, all the read and write operations are performed, and then a higher-level service or application layer is responsible for committing the entire unit of work, which often happens implicitly at the end of a request.

## 4. Common Pitfalls

-   **Forgetting to Commit**: If your changes are not being saved, ensure that the unit of work is being committed somewhere up the call stack.
-   **N+1 Queries**: When querying for a list of entities and then accessing a related navigation property on each one in a loop, you can create an N+1 query problem. Use EF's `.Include()` method within your LINQ query to eagerly load related data if this is supported by the underlying `IQueryable` implementation.
-   **Modifying Entities Outside the Context**: Do not hold onto entity instances outside the scope of the request. Fetch the entity from the current `StorageContext`, modify it, and let the context handle saving.