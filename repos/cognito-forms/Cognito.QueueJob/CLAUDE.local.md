# Cognito.QueueJob — Background Job Processing

## Gotchas
- **DequeueCount off-by-one for delayed queues**: Messages re-added to delayed queues get a new ID, resetting DequeueCount. `CognitoQueueProcessor` compensates by decrementing `MaxDequeueCount` for delayed queues.
- Azure WebJobs SDK handles message lifecycle — do NOT manually delete messages on success.
- `TaskContext.EnsureInitialized()` must be called before processing.

## Queue Architecture
- Queues: `default`, `emails(-delayed)`, `webhooks(-delayed)`, `scheduled`, `organization-events`, `user-events`, `form-events`, `stripe-events`, `indexing` (entry index updates), `background` (low-priority).
- Processor hierarchy: `QueueProcessor` (Azure WebJobs SDK base) → `CognitoQueueProcessor` (abstract) → `Base2ExponentialBackoffQueueProcessor` (2^n-second retry delays), `AdaptiveTimeoutQueueProcessor` (custom timeout per message type/history), `PoisonQueueProcessor`.
- After `MaxDequeueCount` failures, messages move to `{queue-name}-poison` for manual inspection.

## IMessageHandler Pattern
Adding a new message type:
1. Define a message class implementing `IQueueMessage` (in `Cognito.Core` or `Cognito`).
2. Create a handler implementing `IMessageHandler<TMessage>` — auto-registered via assembly scanning in `QueueJobModule`.
3. For org context: the message additionally implements `IOrganizationScopedMessage` (requires `OrganizationId`); `QueueMessageOrganizationContext` then provides `IOrganizationContext` to the handler automatically.

## Key Files
| File | Purpose |
|------|---------|
| `Program.cs` | Entry point, WebJobs host setup |
| `CognitoQueueProcessor.cs` | Base processor with retry/poison logic |
| `QueueJobProcessor.cs` | Main job execution |
| `DependencyInjection/QueueJobModule.cs` | Registers `IMessageHandler<T>` impls (assembly-scanned), processors, telemetry |
| `QueueMessageOrganizationContext.cs` | Org context for handlers |
| `QueueNameResolver.cs` | Resolves queue names from config |
