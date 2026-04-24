---
name: linked-lookups
description: Provides expert guidance on the Linked Lookups feature, including bidirectional syncing, the LinkedLookupService, synchronization limits (100/1000/10000), auto-create integration, and the synchronous processing flow.
version: 1.0.0
allowed-tools: ["Read", "Grep", "Glob"]
---

# Linked Lookups Feature Skill

This skill provides deep expertise on implementing and working with the Linked Lookups feature in Cognito Forms.

## Core Concept

Linked Lookups creates **bidirectional relationships** between lookup fields on different forms. When `FormA.LookupA` is linked to `FormB.LookupB`:
- Submitting `EntryA` with `LookupA = EntryB` automatically updates `EntryB.LookupB` to include `EntryA`
- Creates seamless two-way data relationships

## Critical Requirements

### Synchronous Processing
- All linked lookup syncing **MUST occur synchronously**
- Entry submission blocks until entire cascading chain completes
- Required for referential integrity and data consistency
- Enables subsequent operations (like auto-create) to see synced state

### Integration with Auto-Create Entries
- Both features work together in the same synchronous submission flow
- **Processing order**:
  1. Entry's linked lookup updates (may modify entry content)
  2. Entry's auto-create entries based on final content
  3. Newly created entries trigger their own linked lookup updates
  4. Cascades through multiple levels before submission completes

## Key Service Components

### LinkedLookupService

**Form-scoped methods:**
- `HandleLinkedLookupConfigurationChange(Form oldForm, Form newForm)` - Called after form save to detect and process linked lookup configuration changes

**Entry-scoped methods:**
- `SyncLinkedLookups(Form form, FormEntry submittingEntry, LinkedLookupSyncContext syncContext)` - Processes all linked lookups on a submitting entry

### LinkedLookupSyncContext

In-memory session object tracking state during cascading operations:

```csharp
{
    // Process-wide counter (max 10,000)
    int ProcessSyncOperationCount { get; set; }

    // Per-entry counters (max 1,000 per entry)
    Dictionary<int, int> EntrySyncOperationCounts { get; set; }

    // Entry updates for batching optimization
    Dictionary<int, List<Action<FormEntry>>> EntryUpdates { get; set; }

    // Increment counters and check limits
    bool TryIncrementSyncOperations(int entryId);

    // Add and apply entry updates
    void AddEntryUpdate(int entryId, Action<FormEntry> updateFunction);
    void ApplyUpdatesToEntry(int entryId, FormEntry entry);
}
```

## Limit System

### Field Entry Limit
- **100 entries maximum** per individual linked lookup field
- When 101st entry attempts to link:
  - Oldest entry (lowest entry number) removed if no user-defined strategy
  - Removed entry's corresponding linked field cleared
  - New entry added (FIFO removal)
  - All updates synchronous and atomic

### Sync Operations Limits
- **Per-entry limit**: 1,000 sync operations per individual entry
- **Process-wide limit**: 10,000 sync operations for entire cascading chain
- Sync operations = individual entry updates (not service calls)
- FIFO removal operations **included** in count
- **Abandonment behavior**: When limit reached, remaining operations abandoned (not failed)

### Limit Constants

```csharp
const int LINKED_LOOKUP_SYNCED_ENTRIES_LIMIT = 100;       // Per field
const int LINKED_LOOKUP_ENTRY_SYNC_LIMIT = 1000;          // Per entry
const int LINKED_LOOKUP_PROCESS_SYNC_LIMIT = 10000;       // Process-wide
```

## Integration Points

### FormsService.SubmitEntry()

```csharp
public SubmissionResult SubmitEntry(
    ref FormEntry formEntry,
    LinkedLookupSyncContext linkedLookupSyncContext = null)
{
    // ... existing submission logic ...

    if (!behavior.HasFlag(SubmissionBehavior.SuppressStorage))
    {
        // Store entry initially
        StoreEntry(formEntry);

        // Process linked lookups synchronously
        syncContext = LinkedLookupService.SyncLinkedLookups(
            form,
            formEntry,
            linkedLookupSyncContext
        );

        // Process auto-create entries with same sync context
        if (hasLinkedLookup && !behavior.HasFlag(SubmissionBehavior.SuppressCreateEntriesFromActions))
        {
            CreateEntriesFromActionsService.CreateEntries(
                formEntry,
                validPrefillConfigs,
                userId,
                linkedLookupSyncContext
            );
        }

        // Apply accumulated patches
        if (syncContext.HasUpdates(formEntry.Id))
        {
            syncContext.ApplyUpdatesToEntry(formEntry.Id, formEntry);
            StoreEntry(formEntry);
        }
    }

    return result;
}
```

### FormsService.SaveForm()

```csharp
public FormSaveStatus SaveForm(Form form, /* ... other params ... */)
{
    // ... existing save logic ...

    Form oldForm = null;
    if (!newForm)
    {
        oldForm = StorageContext.Get<Form>(form.Id, bypassCache: true);
    }

    // Store the form
    StorageContext.Store(form);

    // Handle linked lookup configuration changes
    LinkedLookupService.HandleLinkedLookupConfigurationChange(oldForm, form);

    return saveStatus;
}
```

## Data Model Changes

### FieldLookup Extension

```csharp
FieldLookup {
    string LinkedFieldPath,              // Path to linked field on target form
    string LinkedLookupRemovalStrategy   // User-defined removal strategy
}
```

## Processing Flow

1. User submits entry with linked lookup values
2. Entry stored initially
3. `LinkedLookupService.SyncLinkedLookups()` called
   - Detects modified linked lookups
   - Updates target entries
   - Enforces limits
   - Tracks operations in context
4. Auto-create entries processed (if applicable)
   - Uses same sync context
   - New entries trigger their own sync operations
5. Cascading continues until:
   - No more sync operations OR
   - Per-entry limit (1,000) reached OR
   - Process-wide limit (10,000) reached
6. All accumulated updates persisted
7. Original submission completes

## Optimization Strategy

### In-Memory Entry Management
- Keep updated entries in entity cache during process
- Perform multiple sync operations on cached entry
- Store final state at end (minimizes DB operations)

### Entry Update Tracking
- Record list of update delegates per entry
- Replay updates if entry needs to be re-fetched
- Ensures correct final state even if cache evicted

### Persistence Logic
```csharp
// For each updated entry at end of process:
if (entry in cache && not modified by concurrent process)
{
    Store(entry);  // One DB operation
}
else
{
    entry = Fetch(entry.Id);          // First DB op
    ApplyRecordedUpdates(entry);      // Replay all updates
    Store(entry);                      // Second DB op
}
```

## Feature Flag

```xml
<!-- Web.Local.config -->
<add key="LinkedLookups" value="true" />
```

Check flag before executing feature code:
```csharp
if (FeatureFlags.LinkedLookups)
{
    LinkedLookupService.SyncLinkedLookups(form, entry, context);
}
```

## Common Scenarios

### Basic Bidirectional Link
```csharp
// FormA.DropdownLookup links to FormB.CheckboxLookup
// User submits EntryB with DropdownLookup = EntryA
// Result: EntryA.CheckboxLookup updated to include EntryB
```

### Cascading Through Defaults
```csharp
// EntryB.LookupB updated to include EntryA
// Triggers default value rules on EntryB
// Defaults set EntryB.LookupC to EntryD
// Triggers sync for LookupC -> EntryD.LookupE updated
// Chain continues until no more sync operations
```

### Field Entry Overflow
```csharp
// EntryA.CheckboxLookup has 100 linked entries
// EntryB-101 submitted with DropdownLookup = EntryA
// Result:
//   - EntryB-1 (oldest) removed from EntryA.CheckboxLookup
//   - EntryB-1.DropdownLookup cleared
//   - EntryB-101 added to EntryA.CheckboxLookup
//   - All atomic in same operation
```

### Auto-Create Integration
```csharp
// FormA auto-creates EntryB on submission
// EntryB automatically has linked lookups set to point to EntryA
// Triggers SyncLinkedLookups for EntryB
// EntryA updated to reference EntryB
// Seamless two-way relationship established
```

## Error Prevention

- **Infinite loops**: Sync operations limit prevents runaway cascades
- **Concurrent modifications**: Use `bypassCache: true` when fetching for updates
- **Data consistency**: Synchronous processing ensures referential integrity
- **Performance**: Optimization strategy minimizes DB operations

## Testing Considerations

- Use `LinkedLookupTestOrg` from TestFiles
- Test limit enforcement (100/1000/10000)
- Test cascading scenarios
- Test auto-create integration
- Test FIFO removal behavior
- Mock `LinkedLookupSyncContext` for unit tests

## When to Reference Additional Files

- For complete feature specification, see `feature-spec.md`
- For implementation details and code examples, see `implementation-guide.md`

## When This Skill Activates

This skill should activate when you:
- Implement linked lookup functionality
- Work with `LinkedLookupService` or `LinkedLookupSyncContext`
- Debug linked lookup syncing issues
- Add features that integrate with linked lookups
- Modify entry submission flow related to linked lookups
- Write tests for linked lookup behavior
- Investigate performance issues with cascading updates
