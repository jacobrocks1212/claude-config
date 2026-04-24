## Linked Lookups Feature

### Core Feature Description
Linked Lookups creates a **bidirectional relationship** between lookup fields on different forms. When two lookups are linked (e.g., `FormA.LookupA` <-> `FormB.LookupB`), submitting an entry on `FormA` such that `EntryA.LookupA` points to `EntryB` will automatically trigger an update to `EntryB` so that `EntryB.LookupB` points back to `EntryA`.

***

## Critical Processing Requirements

### Synchronous Processing
* The "syncing" process (updating `EntryB.LookupB` to point back to `EntryA`) **MUST occur synchronously**.
* `EntryA`'s submission must be blocked until the entire linked lookup syncing process completes.
* This is required because `FormB` might have additional linked lookups that default based on the sync, which could result in subsequent updates back to `EntryA`.
* The entire chain of linked lookup updates must complete before the original submission is considered successful.

### Integration with Auto-Create Entries
* The Auto-Create Entries feature already exists and is currently asynchronous (queue-based).
* A synchronous implementation of Auto-Create Entries has been developed and will be used.
* Both Linked Lookups and Auto-Create Entries need to work together in the same synchronous submission flow.
* **Processing Order**: When `EntryA` is submitted:
    a. `EntryA`'s linked lookup updates happen synchronously (may modify `EntryA`'s content).
    b. `EntryA`'s auto-create entries happen synchronously based on `EntryA`'s final content after LL syncing.
    c. Any newly created entries from auto-create can trigger their own linked lookup updates synchronously.
    d. This can cascade through multiple levels before `EntryA`'s submission completes.

***

## Syncing Logic and Data Flow

### Linked Lookup Syncing Process
* When `EntryB` is submitted with `B.DropdownLookup` pointing to `EntryA`:
    a. `EntryB` already has its lookup field set to point to `EntryA` (set during submission).
    b. The only sync operation needed is updating `EntryA.CheckboxLookup` to include `EntryB`.
    c. This creates the bidirectional relationship.
* The sync is **unidirectional per operation**: the source entry points to the target, then the target gets updated to include the source.

### Cascading Through Standard Field Defaults
* Cascading linked lookup updates are driven by **standard field defaults/calculations** that occur during the normal entry submission process.
* When `EntryB.LookupB` gets updated to include `EntryA`, this triggers standard field defaults on `EntryB`.
* These defaults may set other lookup fields on `EntryB`, which then trigger their own linked lookup syncing operations.
* **Circular Modification Scenarios**: Updates may circle back to require additional changes to previously processed entries.

### Service Architecture
* **Single service call design**: `LinkedLookupService.SyncLinkedLookups(FormEntry submittingEntry)`
* One service call processes all linked lookup fields on the submitting entry at once.
* Handles all LL fields on the submitting entry in a single operation.

### Auto-Create Integration with Linked Lookups
* When `FormA` auto-creates `EntryB`, the newly created `EntryB` automatically has its linked lookup fields set to point back to `EntryA`.
* This triggers the same `SyncLinkedLookups` process for the newly created `EntryB`.
* Creates seamless integration between both features.

***

## Entry Limitation System


### Per-Field Entry Limit
* Maximum of **100** linked entries per individual linked lookup field.
* The limit applies **per field**, not per form or across all fields.
* **Constant**: `LINKED_LOOKUP_SYNCED_ENTRIES_LIMIT = 100`.

***

### Per-Field Overflow Behavior
* When the 101st entry attempts to link to a field already at the 100-entry limit, the following FIFO strategy is used:
    a. The **oldest entry** (lowest entry number) is automatically unlinked and removed.
    b. The removed entry's corresponding linked field is cleared.
    c. The new entry is added to the field.
    d. All updates happen synchronously within the same transaction.
* This is a **FIFO** (First-In-First-Out) removal strategy based on the entry number.
* **Removal does not trigger additional sync operations**: Clearing the oldest entry's linked field is part of the same atomic operation and does not count toward the sync operations limit.

***

### Per-Field Example Scenario
* **Form**: `FormA.CheckboxLookup` (linked to `FormB.DropdownLookup`)
* **Current state**: `EntryB-1`, `EntryB-2`, ..., `EntryB-100` are selected (at limit).
* **Action**: `EntryB-101` is submitted with `DropdownLookup = EntryA`.
* **Result**:
    * Remove `EntryB-1` from `FormA.CheckboxLookup` (oldest).
    * Clear `EntryB-1.DropdownLookup` (it no longer points to `EntryA`).
    * Add `EntryB-101` to `FormA.CheckboxLookup`.
    * Set `EntryB-101.DropdownLookup = EntryA`.

***

### Sync Operations Limitation
* A **two-tiered limit system** prevents runaway cascading scenarios:
    a. **Process-wide limit**: A maximum of `10,000` sync operations for the entire cascading chain initiated by a single manual entry submission.
    b. **Per-entry limit**: A maximum of `1,000` sync operations per individual entry submission (including auto-created entries).
* **Constants**: `LINKED_LOOKUP_PROCESS_SYNC_LIMIT = 10000` and `LINKED_LOOKUP_ENTRY_SYNC_LIMIT = 1000`.
* Sync operations are counted as **individual entry updates**, not service calls. If one `SyncLinkedLookups` call updates 5 different entries, that counts as 5 operations toward both limits.
* FIFO removal operations **are included** in the sync operations count.
* **Abandonment behavior**: When a limit is reached, subsequent sync operations are **abandoned** (not failed). This allows the submission to complete successfully with partial syncing.

***

### Sync Operations Example Scenario
1. A manual submission of `EntryA` with `LookupA` pointing to `EntryB` starts the process-wide counter.
2. **Sync**: `EntryB.LookupB` is updated to include `EntryA` (1 sync op for `EntryA`, 1 process-wide).
3. `EntryB` triggers the auto-creation of `EntryC` (a new entry submission starts with 0 sync ops for `EntryC`).
4. **Sync**: `EntryC.LookupD` is updated to include `EntryB` (1 sync op for `EntryC`, 2 process-wide).
5. Cascading continues until either:
    * No more sync operations are triggered, OR
    * Any single entry reaches `1,000` sync operations (that entry's syncing stops), OR
    * The process-wide limit of `10,000` sync operations is reached (all syncing stops).

***

### Multiple Linked Lookups Per Form Scenario
* A single form can have multiple linked lookup fields.
* When one linked lookup gets synced, it can trigger defaults or calculations on other linked lookups on the same form.
* The **per-entry limit** (`1,000` sync ops) prevents any single entry from consuming all available process-wide sync operations.
* The **process-wide limit** (`10,000` sync ops) provides an absolute ceiling across all entries in the cascading chain.
* Without these dual limits, complex forms with multiple interconnected linked lookups could create infinite or near-infinite cascading updates.

### Optimization Strategy to Reduce DB Operations

Linked Lookups, combined with auto-created entries and default value rules, can yield many (up to 10000) entry updates. We do not want to perform a DB operation for each update. To facilitate this, we'll be implementing the following strategy.  
  
**Prioritize Keeping Updated Entries in Memory**  

When an entry submission triggers a LL sync operation on `LinkedEntry`, we will fetch `LinkedEntry` from storage (first DB op), and perform that sync operation on `LinkedEntry` in memory. This will trigger default value rules to execute on `LinkedEntry` (which can trigger additional LL sync operations). If the capacity of the entity cache allows, we will keep `LinkedEntry` in memory for the duration of the entire process. If a subsequent sync operation (e.g. from an auto-created entry submission) needs to be performed against `LinkedEntry`, then we can perform that operation against the cached (in-memory) `LinkedEntry`, preventing the need to fetch `LinkedEntry` from storage again. When the entire process completes, we can simply store the in-memory `LinkedEntry` (second DB op).  
  
**Track Entry Updates from Sync Operations**  

We cannot guarantee that all entries updated by sync operations will fit in the in-memory entity cache, or guarantee that a cached entry has not been modified by a concurrent process (e.g. another user). For that reason, we need a mechanism to "replay" entry updates that resulted from sync operations, in case we need to fetch an entry from storage again. That mechanism will be a recorded list of update delegates (functions) that can be applied, in order, to the initial state of the entry. At any point in the process, if we need to perform a sync operation against an entry that is no longer in-memory, we can re-fetch the entry from storage and apply the updates in order, returning the entry to its most up-to-date state. These entry updates will be tracked in a dictionary (one list of updates per entry) on `LinkedLookupSyncContext`**.**  
  
**Persisting Sync Operation Entry Updates**  
At the end of the process, once all auto-created entries have been submitted, and all LL sync operations have been performed, we can commit all updated entries to storage. For each updated `LinkedEntry`, we can persist the updates using the following logic:  
*   If `LinkedEntry` still exists in-memory, and has not been modified by a concurrent process, we can simply store `LinkedEntry` (one DB op)
*   Else (`LinkedEntry` has been flushed from the entity cache or has been modified by a concurrent process), we will...
    *   Fetch `LinkedEntry` from storage (first DB op)
    *   Iteratively execute the recorded entry updates, in order, against our new, in-memory `LinkedEntry` (allowing default values to run for each update)
    *   And store `LinkedEntry` after all updates have been performed

***

## Technical Integration Points

### Existing Codebase Elements
* `FormsService.SubmitEntry()` - Main entry submission process.
* `AutoCreateEntriesService` - Handles auto-create entries logic.
* `FieldLookup` class - Current lookup field configuration.
* `SUBMISSION_ATTEMPT_LIMIT` constant (1000) - Reference for linked lookup limit implementation.

### Feature Flag Configuration
* Add a single `LinkedLookups` feature flag to `Web.Local.config`.
* The feature flag controls the entire Linked Lookups feature.
* Follow the existing pattern for feature flag implementation.
* Enable controlled rollout and testing.

***

## Processing Flow
1.  A user submits an entry with linked lookup values.
2.  Store the entry initially.
3.  Process linked lookup syncing via `LinkedLookupService.SyncLinkedLookups()`.
4.  Process auto-create entries synchronously based on the entry's final content after LL syncing.
5.  Any new entries trigger their own linked lookup processing.
6.  Store operations occur as needed for referential integrity.
7.  Cascading continues until all updates complete or limits are reached.
8.  The original submission completes successfully.

***

## Error Handling Requirements
* Infinite loop prevention through the sync operations limit (**primary safeguard**).
* Enforcement of the 100-entry limit with proper overflow handling.
* Enforcement of the sync operations limit with proper overflow handling.

***

## Implementation Architecture

**Model Changes**  
New field path property added to `FieldLookup` to track the field on the source form this lookup is linked to.  

```
FieldLookup {  
   string LinkedFieldPath  
}
```

**LinkedLookupService**  
Service responsible for managing LL relationships between lookup fields across forms. Handles detection of LL configuration changes during form saves (establishing/clearing links and queuing initial sync), and performs synchronous entry-level sync operations during submissions to maintain bidirectional consistency. Enforces field entry limits (100 per field with user-defined overflow priority) and sync operation limits (1,000 per entry, 10,000 per process) to prevent runaway cascading scenarios.  
```
{  
    // Handles all linked lookup configuration changes when a form is saved  
    void HandleLinkedLookupConfigurationChange(Form oldForm, Form newForm);  
      
    // private List<FieldLookup> DetectNewLinkedLookups(Form oldForm, Form newForm);  
    // private List<FieldLookup> DetectUnlinkedLookups(Form oldForm, Form newForm);  
    // private void EstablishLink(FieldLookup sourceLookup);  
    // private void ClearLink(FieldLookup sourceLookup);  
    // private void QueueInitialSync(Form form, FieldLookup newlyLinkedLookup);  
    // private void SyncAllEntries(Form sourceForm, FieldLookup newlyLinkedLookup);  
  
    // Performs all necessary sync operations for linked lookups on a submitting entry  
    void SyncLinkedLookups(Form form, FormEntry submittingEntry, LinkedLookupSyncContext syncContext = null);  
      
    // private LinkedLookupSyncContext CreateSyncContext();  
    // private List<FieldLookup> DetectModifiedLinkedLookups(Form form, FormEntry submittingEntry);  
    // private void SyncIndividualLookup(FieldLookup sourceLookup, FormEntry submittingEntry, LinkedLookupSyncContext syncContext);  
    // private void EnforceFieldEntryLimit(FormEntry targetEntry, FieldLookup targetField, FormEntry newEntry);  
    // private FormEntry GetLinkedEntryToRemove(FormEntry targetEntry, FieldLookup targetField);  
  }
```

**LinkedLookupSyncContext**  
In-memory session object that tracks state during a single entry submission's cascading LL operations. Maintains sync operation counters for limit enforcement, accumulates a single `JsonPatchDocument` patch per entry for batching sync operations, and coordinates the synchronous processing chain across multiple entry submissions (including auto-created entries). Passed as a param through recursive `FormsService.SubmitEntry` and `AutoCreateEntriesService.CreateEntries` calls, then destroyed when the original submission completes.  
```
{  
    // Tracks sync operations across the entire process (max 10,000)  
    int ProcessSyncOperationCount { get; set; }  
  
    // Tracks sync operations per individual entry (max 1,000 per entry)  
    Dictionary<int, int> EntrySyncOperationCounts { get; set; }  
  
    // Tracks a list of entry updates per entry for batching optimization  
    Dictionary<int, List<Action<FormEntry>>>> Entry { get; set; }  
  
    // Constructor initializes collections  
    LinkedLookupSyncContext();  
  
    // Increments sync operation counters and returns true if limits allow the operation  
    bool TryIncrementSyncOperations(int entryId);  
  
    // Adds an update function for an entry  
    public void AddEntryUpdate(int entryId, Action<FormEntry> updateFunction)  
  
    // Applies all updates to an entry with proper ModelEventScope handling  
    public void ApplyUpdatesToEntry(int entryId, FormEntry entry)  
  }
```

Usage Example (`FormsService.SubmitEntry`)  
```
public SubmissionResult SubmitEntry(ref FormEntry formEntry, /* ... parameters ... */,   
 LinkedLookupSyncContext linkedLookupSyncContext = null)  
  {  
      // ... existing SubmitEntry logic ...  
  
      if (!behavior.HasFlag(SubmissionBehavior.SuppressStorage))  
      {  
          // Store the entry initially  
          var storeResult = StoreEntry(formEntry, /* ... other parameters ... */);  
          if (storeResult.Status != SubmissionResultStatus.Success)  
              return storeResult;  
  
          // Process linked lookups synchronously  
          // If no LinkedLookupSyncContext provided (i.e. this is the top-level/initial entry submission),  
          // then the service method will create and return one  
          syncContext = LinkedLookupService.SyncLinkedLookups(form, formEntry, linkedLookupSyncContext);  
  
          // Process auto-create entries synchronously  
          if (hasLinkedLookup && !behavior.FastHasFlag(SubmissionBehavior.SuppressCreateEntriesFromActions) && validPrefillConfigs.Any())  
              AutoCreateEntriesService.CreateEntries(formEntry, validPrefillConfigs, userId, linkedLookupSyncContext);  
          else  
            // Existing asynchronous auto-create entries behavior  
  
          // Apply patch for this entry  
          if (syncContext.GetEntryPatches().ContainsKey(formEntry.Id))  
          {  
              syncContext.ApplyPatchToEntry(formEntry.Id, formEntry);  
              StoreEntry(formEntry, /* ... parameters ... */);  
          }  
      }  
  
      // ...  
  }
```

Usage Example (`FormsService.SaveForm`)  
```
public FormSaveStatus SaveForm(Form form, string folderId = null, FormCopyMode copyMode = 0, string templateId = null, CopyFormSourceInfo additionalInfo = null, bool logAuditLog = true)  
  {  
      // ... existing SaveForm logic ...  
  
      var saveStatus = new FormSaveStatus();  
      Form oldForm = null;  
  
      if (!newForm)  
      {  
          oldForm = StorageContext.Get<Form>(form.Id, bypassCache: true);  
  
          // ...   
      }  
  
      // ...   
  
      // Store the form  
      if (string.IsNullOrEmpty(form.Id))  
          StorageContext.Store(form);  
      else  
          StorageContext.CreateOrUpdate<Form>(form.Id, (_) => form);  
  
      // Handle linked lookup configuration changes after form is saved  
      // For new forms, oldForm will be null and the service will treat all linked lookups as new  
      LinkedLookupService.HandleLinkedLookupConfigurationChange(oldForm, form);  
  
      // ...  
  
      return saveStatus;  
  }
```

**Linked Lookup Service**

Public Methods
--------------

### **HandleLinkedLookupConfigurationChange** (Form-scoped)
```
public void HandleLinkedLookupConfigurationChange(Form oldForm, Form newForm)  
  {  
      // Detect newly linked lookups (or all lookups w/ LinkedFieldPath if oldForm is null)  
      var newLinkedLookups = DetectNewLinkedLookups(oldForm, newForm);  
  
      // Process newly linked lookups  
      foreach (var newLinkedLookup in newLinkedLookups)  
      {  
          // Establish bidirectional link by setting LinkedFieldPath on target lookup  
          EstablishLink(newLinkedLookup);  
  
          // Queue initial sync message to sync existing entries  
          QueueInitialSync(newForm, newLinkedLookup);  
      }  
        
      // Detect lookups that are no longer linked (only relevant for existing forms)  
      var unlinkedLookups = oldForm != null ? DetectUnlinkedLookups(oldForm, newForm) : new List<FieldLookup>();  
  
      // Process unlinked lookups  
      foreach (var unlinkedLookup in unlinkedLookups)  
      {  
          // Clear LinkedFieldPath on the target lookup to break bidirectional link  
          ClearLink(unlinkedLookup);  
      }  
  }
```

### **SyncLinkedLookups** (Entry-scoped)
```
public LinkedLookupSyncContext SyncLinkedLookups(Form form, FormEntry submittingEntry, LinkedLookupSyncContext syncContext = null)  
  {  
      // Create sync context if not provided (this is the root call)  
      if (syncContext == null)  
          syncContext = CreateSyncContext();  
  
      // Detect which linked lookup fields have been modified on the submitting entry  
      var modifiedLinkedLookups = DetectModifiedLinkedLookups(form, submittingEntry);  
  
      if (!modifiedLinkedLookups.Any())  
          return syncContext;  
  
      // Process each modified linked lookup field  
      foreach (var modifiedLookup in modifiedLinkedLookups)  
      {  
          // Try to increment sync operations - this handles limit checking internally  
          if (syncContext.TryIncrementSyncOperations(submittingEntry.Id))  
              SyncIndividualLookup(modifiedLookup, submittingEntry, syncContext);  
                
          // If limits exceeded, abandon remaining sync operations  
          else  
              break;  
      }  
  
      return syncContext;  
  }
```

Private Methods
---------------

### SyncAllEntries (Initial sync)
```
private void SyncAllEntries(Form sourceForm, FieldLookup newlyLinkedLookup)  
  {  
      // Get the target form using the FieldLookup.Source (FormId of the looked-up form)  
      var targetForm = StorageContext.Get<Form>(targetForm.Id);  
      if (targetForm == null)  
          return;  
  
      // Get the target lookup field using the LinkedFieldPath (actual field path to the linked field)  
      // Navigate through targetForm.Fields to find field matching newlyLinkedLookup.LinkedFieldPath  
      // Handle nested field paths (e.g., "Section.Field" or "RepeatingSection[0].Field")  
      // Return the FieldLookup object that corresponds to the linked field  
      var targetLookupField = GetFieldLookupFromForm(targetForm, newlyLinkedLookup.LinkedFieldPath);  
      if (targetLookupField == null)  
          return;  
  
      // Get all entries from the source form that have values in the newly linked lookup field  
      // Query for entries where:  
      // - FormId matches sourceForm.Id  
      // - The field specified by newlyLinkedLookup has a non-null/non-empty value  
      // - Extract the lookup value(s) from each entry's field data  
      var sourceEntries = GetEntriesWithLookupValues(sourceForm, newlyLinkedLookup);  
  
      if (!sourceEntries.Any())  
          return;  
  
      // Build a dictionary mapping target entry IDs to lists of source entries that reference them  
      // For each sourceEntry in sourceEntries:  
      // - Get the lookup field value (could be single ID or array of IDs for checkbox lookups)  
      // - For each target entry ID in the lookup value:  
      //   - Add the sourceEntry to the list of entries that reference this target ID  
      // - Return Dictionary<int, List<FormEntry>> where key = target entry ID, value = source entries that reference it  
      var targetToSourceMapping = BuildTargetToSourceMapping(sourceEntries, newlyLinkedLookup);  
  
      // Process each target entry that is referenced by source entries  
      foreach (var targetEntryId in targetToSourceMapping.Keys)  
      {  
          var referencingSourceEntries = targetToSourceMapping[targetEntryId];  
  
          // Prioritize updating the most recent record if multiple entries reference the same target  
          var prioritizedSourceEntry = GetMostRecentEntry(referencingSourceEntries);  
  
          // Get the target entry that needs to be updated  
          var targetEntry = StorageContext.Get<FormEntry>(targetEntryId);  
          if (targetEntry == null)  
              continue;  
  
          // Get current value of the target lookup field  
          var currentTargetLookupValue = GetFieldValue(targetEntry, targetLookupField);  
  
          // Update the target lookup field to include reference back to the prioritized source entry  
          // TODO: Based on targetLookupField type (dropdown vs checkbox):  
          // - For dropdown: set value to prioritizedSourceEntry.Id  
          // - For checkbox: add prioritizedSourceEntry.Id to existing array (if not already present)  
          // - Handle the case where adding this entry would exceed the 100-entry limit  
          // - Return the updated lookup value  
          var updatedTargetLookupValue = AddSourceEntryToTargetLookup(  
              currentTargetLookupValue,  
              prioritizedSourceEntry,  
              targetLookupField);  
  
          // Apply the update to the target entry  
          SetFieldValue(targetEntry, targetLookupField, updatedTargetLookupValue);  
  
          // Enforce field entry limit (100 entries max) with FIFO removal  
          EnforceFieldEntryLimit(targetEntry, targetLookupField, prioritizedSourceEntry);  
  
          // Store the updated target entry  
          StorageContext.Store(targetEntry);  
  
          // Run default value calculations on the target entry in case the lookup update  
          // triggers additional field calculations that could cascade further  
          RunDefaultValueCalculations(targetForm, targetEntry);  
      }  
  }
```

## Optimization Strategy to Reduce DB Operations

Linked Lookups, combined with auto-created entries and default value rules, can yield many (up to 10000) entry updates. We do not want to perform a DB operation for each update. To facilitate this, we'll be implementing the following strategy.  
  
**Prioritize Keeping Updated Entries in Memory**  
When an entry submission triggers a LL sync operation on `LinkedEntry`, we will fetch `LinkedEntry` from storage (first DB op), and perform that sync operation on `LinkedEntry` in memory. This will trigger default value rules to execute on `LinkedEntry` (which can trigger additional LL sync operations). If the capacity of the entity cache allows, we will keep `LinkedEntry` in memory for the duration of the entire process. If a subsequent sync operation (e.g. from an auto-created entry submission) needs to be performed against `LinkedEntry`, then we can perform that operation against the cached (in-memory) `LinkedEntry`, preventing the need to fetch `LinkedEntry` from storage again. When the entire process completes, we can simply store the in-memory `LinkedEntry` (second DB op).  
  
**Track Entry Updates from Sync Operations**  
We cannot guarantee that all entries updated by sync operations will fit in the in-memory entity cache, or guarantee that a cached entry has not been modified by a concurrent process (e.g. another user). For that reason, we need a mechanism to "replay" entry updates that resulted from sync operations, in case we need to fetch an entry from storage again. That mechanism will be a recorded list of update delegates (functions) that can be applied, in order, to the initial state of the entry. At any point in the process, if we need to perform a sync operation against an entry that is no longer in-memory, we can re-fetch the entry from storage and apply the updates in order, returning the entry to its most up-to-date state. These entry updates will be tracked in a dictionary (one list of updates per entry) on `LinkedLookupSyncContext`**.**  
  
**Persisting Sync Operation Entry Updates**  
At the end of the process, once all auto-created entries have been submitted, and all LL sync operations have been performed, we can commit all updated entries to storage. For each updated `LinkedEntry`, we can persist the updates using the following logic:  
*   If `LinkedEntry` still exists in-memory, and has not been modified by a concurrent process, we can simply store `LinkedEntry` (one DB op)
*   Else (`LinkedEntry` has been flushed from the entity cache or has been modified by a concurrent process), we will...
    *   Fetch `LinkedEntry` from storage (first DB op)
    *   Iteratively execute the recorded entry updates, in order, against our new, in-memory `LinkedEntry` (allowing default values to run for each update)
    *   And store `LinkedEntry` after all updates have been performed

### Data Flow Synchronization
* Synchronous processing ensures all linked lookup updates complete before the submission finishes.
* Auto-create entries integration maintains the synchronous flow.
* Cascading updates are handled within the same synchronous process with operation counting.
* Database optimization is achieved through strategic batching without breaking the synchronous requirement.
* Proper limit enforcement at both per-field and per-submission levels.
* **Circular Modification Support**: System designed to handle cases where cascading updates circle back to modify previously processed entries.

This synchronous, cascading system ensures data consistency while preventing runaway processes through established limits (both per-field entry limits and per-submission sync operation limits), proper error handling, and optimized database operations. The system accounts for circular modification scenarios and integrates seamlessly with standard field defaults/calculations that drive the cascading behavior.