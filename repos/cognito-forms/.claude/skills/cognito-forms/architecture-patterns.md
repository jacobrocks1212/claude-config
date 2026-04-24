# Cognito Forms Architecture Patterns

This document provides detailed architectural patterns used in the Cognito Forms codebase.

## Service Layer Architecture

### ModuleService Pattern

Services inherit from the generic `ModuleService<TService, TConfiguration>` class. This is the primary architectural pattern for services in the backend. This class itself inherits from `BaseService`, providing access to a logger, the current user, and the organization.

-   `TService`: The service interface (e.g., `IFormsService`).
-   `TConfiguration`: The module-specific configuration class (e.g., `FormsConfiguration`).

This base class provides each service with its strongly-typed configuration and an `IStorageContext` for data operations.

```csharp
// Correct Pattern: Inheriting from ModuleService
public class FormsService : ModuleService<IFormsService, FormsConfiguration>, IFormsService
{
    public FormsService(ICoreService coreService, IStorageContext context, ModuleConfigurationRef config, ...)
        : base(coreService, context, config)
    {
        // The base constructor handles dependency setup.
    }

    // Service methods...
}
```

### Service Dependencies

Common dependencies injected into a service's constructor:
- `ICoreService` - Provides access to core application-wide services.
- `IStorageContext` - Scoped data persistence context.
- `ModuleConfigurationRef` - A reference to the service's specific configuration.
- Other services as needed (e.g., `IPaymentService`, `IProfileService`).

## Data Persistence Patterns

### StorageContext Operations

**Fetching Data:**
```csharp
// Get single entity
var entity = StorageContext.Get<EntityType>(id);

// Get with cache bypass (for updates)
var entity = StorageContext.Get<EntityType>(id, bypassCache: true);
```

**Storing Data:**
```csharp
// Store new or updated entity
StorageContext.Store(entity);

// Atomic update with function
StorageContext.CreateOrUpdate<EntityType>(id, (existing) => {
    // Modify existing
    return existing;
});
```

### Entity Cache Considerations

- Default behavior caches entities within the current `StorageContext` scope.
- Use `bypassCache: true` when fetching an entity that you intend to update, to ensure you are modifying the most recent version.

## Submission Flow Architecture

### Entry Submission Pattern

The `FormsService.SubmitEntry()` method follows this flow:

1. **Validation** - Checks entry data validity and user permissions.
2. **Storage** - The `StoreEntry` method is called to persist the entry data.
3. **Post-processing** - A series of synchronous tasks are executed after the entry is stored, including `LinkedLookupService.SyncLinkedLookups` and `CreateEntriesFromActionsService.CreateEntries`.
4. **Return result** - A `SubmissionResult` object is returned with the status and any errors.

### Submission Behavior Flags

Use the `SubmissionBehavior` enum to control flow:
- `SuppressStorage` - Skip storing the entry.
- `SuppressNotifications` - Skip sending email notifications.
- `SuppressCreateEntriesFromActions` - Skip the auto-create entries logic.

## Queue Processing Architecture

### Background Jobs

- `Cognito.QueueJob/` - The worker process project containing job processors and handlers.
- `Cognito.QueueService/` - A Windows Service that hosts and runs the `Cognito.QueueJob` process.

### Queue vs Synchronous

**Use queues for:**
- Email notifications
- Document generation
- Long data exports
- Scheduled tasks

**Use synchronous for:**
- Data integrity requirements
- User-facing operations that require immediate feedback
- Cascading data updates
