# Linked Lookups Implementation Guide

This guide provides a high-level overview of the implementation. **Always read the actual source code** for current signatures and behavior — the codebase is the source of truth.

## Service Architecture

### LinkedLookupService

```
LinkedLookupService : OrgScopedService
```

**Key methods (consult source for exact signatures):**
- Configuration change handling (called from SaveForm path)
  - Detect newly linked / unlinked lookups
  - Establish or clear bidirectional links
  - Queue initial sync for newly linked lookups
- Entry sync (called from SubmitEntry path)
  - Detect modified linked lookup fields on submitting entry
  - Sync individual lookups to target entries
  - Enforce per-field entry limit (FIFO overflow)

**Key file:** `Cognito.Core/Services/LinkedLookups/LinkedLookupService.cs`

### LinkedLookupSyncContext

In-memory session object tracking state during cascading sync operations.

**Key members:**
- `ProcessSyncOperationCount` — tracks total ops across cascade
- `EntrySyncOperationCounts` — per-entry op tracking (string keys)
- `TryIncrementSyncOperations(string entryId)` — returns `SyncOperationResult` enum (not bool)
- Entry update tracking for batched persistence

**Key file:** `Cognito.Core/Services/LinkedLookups/LinkedLookupSyncContext.cs`

### Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `LINKED_LOOKUP_SYNCED_ENTRIES_LIMIT` | 100 | Max linked entries per field |
| `LINKED_LOOKUP_PROCESS_SYNC_LIMIT` | 10,000 | Process-wide cascade limit |
| `LINKED_LOOKUP_ENTRY_SYNC_LIMIT` | 1,000 | Per-entry sync op limit |

## Integration Points

### SaveForm Path
`FormsService.SaveForm()` calls linked lookup configuration change handling after storing the form. This detects new/removed links and queues initial sync.

### SubmitEntry Path
`FormsService.SubmitEntry()` calls sync after storing the entry. The sync context is passed through recursive calls including `AutoCreateEntriesService.CreateEntries()`.

### UpdateLookups
Called from the SaveForm path (not SubmitEntry). Also called from `FormRestoreService` and `FormGenerationService`.

## Optimization Strategy

The system minimizes DB operations through:
1. **In-memory caching** — Fetched entries stay in entity cache for reuse during cascade
2. **Update replay** — Entry updates recorded as delegate lists, replayed if cache evicts an entry
3. **Batched persistence** — All updated entries committed to storage at end of process

## Testing

Tests use `BaseTest` with `[Org("OrgCode")]` attribute pattern. See `Cognito.Forms.UnitTests` for linked lookup test examples. Do not use `Mock<IStorageContext>` — the test infrastructure provides real DI via Autofac with `TestStore`.
