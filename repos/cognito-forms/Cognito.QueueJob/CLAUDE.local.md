# Cognito.QueueJob — Background Job Processing

## Gotchas
- **DequeueCount off-by-one for delayed queues**: Messages re-added to delayed queues get a new ID, resetting DequeueCount. `CognitoQueueProcessor` compensates by decrementing `MaxDequeueCount` for delayed queues.
- Azure WebJobs SDK handles message lifecycle — do NOT manually delete messages on success.
- `TaskContext.EnsureInitialized()` must be called before processing.

## Queue Architecture

### Queue Types
| Queue Name | Purpose |
|------------|---------|
| `default` | General background tasks |
| `emails` / `emails-delayed` | Email dispatch |
| `webhooks` / `webhooks-delayed` | Webhook delivery with retry |
| `scheduled` | Time-scheduled tasks |
| `organization-events` | Org-level event processing |
| `user-events` | User-level event processing |
| `form-events` | Form-level event processing |
| `stripe-events` | Stripe webhook processing |
| `indexing` | Entry index updates |
| `background` | Low-priority background work |

### Processor Hierarchy
```
QueueProcessor (Azure WebJobs SDK base)
  └── CognitoQueueProcessor (abstract)
        ├── Base2ExponentialBackoffQueueProcessor  — 2^n second retry
        ├── AdaptiveTimeoutQueueProcessor          — Custom timeout logic
        └── PoisonQueueProcessor                   — Handles poison messages
```

## IMessageHandler Pattern

### Adding a New Message Type
1. Define message class implementing `IQueueMessage` (in `Cognito.Core` or `Cognito`)
2. Create handler implementing `IMessageHandler<TMessage>`
3. Handler is auto-registered via assembly scanning in `QueueJobModule`

```csharp
// Message (in Cognito or Cognito.Core)
public class MyTaskMessage : IQueueMessage
{
    public string OrgId { get; set; }
    public string Data { get; set; }
}

// Handler (in Cognito or Cognito.Core)
public class MyTaskHandler : IMessageHandler<MyTaskMessage>
{
    public async Task Handle(MyTaskMessage message)
    {
        // Process message
    }
}
```

### Org-Scoped Messages
Implement `IOrganizationScopedMessage` for messages that need org context:
```csharp
public class MyOrgTaskMessage : IQueueMessage, IOrganizationScopedMessage
{
    public string OrganizationId { get; set; }  // Required by interface
}
```
The `QueueMessageOrganizationContext` automatically provides `IOrganizationContext` to handlers.

## Retry Strategies

### Base2ExponentialBackoffQueueProcessor
Delays: 2s, 4s, 8s, 16s, 32s... (2^n seconds)

### AdaptiveTimeoutQueueProcessor
Custom timeout logic based on message type and history.

### Poison Queue Handling
After `MaxDequeueCount` failures, messages are moved to `{queue-name}-poison` for manual inspection.

## DI Registration
`DependencyInjection/QueueJobModule.cs` registers:
- `IMessageHandler<T>` implementations (auto-scanned from assemblies)
- Queue processors
- Telemetry initializers

## Key Files
| File | Purpose |
|------|---------|
| `Program.cs` | Entry point, WebJobs host setup |
| `CognitoQueueProcessor.cs` | Base processor with retry/poison logic |
| `QueueJobProcessor.cs` | Main job execution |
| `QueueMessageOrganizationContext.cs` | Org context for handlers |
| `QueueNameResolver.cs` | Resolves queue names from config |

---

## Maintaining This Document

Update this file when:
- Adding new architectural patterns or service hierarchies
- Discovering non-obvious gotchas that would trip up future developers
- Renaming or restructuring directories/files mentioned here

Do NOT add: version numbers, line numbers, test counts, or other specifics that change frequently.
