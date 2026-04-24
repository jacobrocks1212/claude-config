# Common Pitfalls and Gotchas

This document catalogs common mistakes and gotchas in the Cognito Forms codebase to help avoid them.

## Database and Storage

### Forgetting to Store

**Problem:**
```csharp
// Bad - changes never persisted
var form = StorageContext.Get<Form>(formId);
form.Name = "Updated Name";
// Missing: StorageContext.Store(form);
```

**Solution:**
```csharp
// Good - always store after modifications
var form = StorageContext.Get<Form>(formId, bypassCache: true);
form.Name = "Updated Name";
StorageContext.Store(form);
```

## Async/Await Mistakes

### Blocking on Async

**Problem:**
```csharp
// Bad - blocks the thread
var result = SomeAsyncMethod().Result;
var data = AnotherAsyncMethod().GetAwaiter().GetResult();
```

**Solution:**
```csharp
// Good - use await
var result = await SomeAsyncMethod();
var data = await AnotherAsyncMethod();
```

### Async Void

**Problem:**
```csharp
// Bad - can't await, swallows exceptions
public async void ProcessData()
{
    await SomeOperation();
}
```

**Solution:**
```csharp
// Good - use async Task
public async Task ProcessData()
{
    await SomeOperation();
}

// Only use async void for event handlers
private async void OnButtonClick(object sender, EventArgs e)
{
    try
    {
        await ProcessData();
    }
    catch (Exception ex)
    {
        // Handle exception
    }
}
```

## Null Reference Issues

### Null Entry or Form

**Problem:**
```csharp
// Bad - no null check
public void ProcessEntry(FormEntry entry)
{
    var formId = entry.FormId;  // NullReferenceException if entry is null
}
```

**Solution:**
```csharp
// Good - validate input
public SubmissionResult ProcessEntry(FormEntry entry)
{
    if (entry == null)
        return new SubmissionResult
        {
            Status = SubmissionResultStatus.ValidationError,
            ErrorMessage = "Entry cannot be null"
        };

    var formId = entry.FormId;
    // Continue processing
}
```

### Navigation Property Not Loaded

**Problem:**
```csharp
// Bad - assuming related data is loaded
var form = StorageContext.Get<Form>(formId);
var organization = form.Organization;  // Might be null if not loaded
var orgName = organization.Name;  // NullReferenceException!
```

**Solution:**
```csharp
// Good - explicitly load related data or handle null
var form = StorageContext.Get<Form>(formId);
var orgId = form.OrganizationId;  // Use the ID directly
var organization = StorageContext.Get<Organization>(orgId);
```

## Submission Flow Issues

### Forgetting Feature Flags

**Problem:**
```csharp
// Bad - new feature always runs
public void SubmitEntry(FormEntry entry)
{
    // New feature code runs for everyone
    ProcessNewFeature(entry);
}
```

**Solution:**
```csharp
// Good - guard with feature flag
public void SubmitEntry(FormEntry entry)
{
    if (FeatureFlags.NewFeature)
    {
        ProcessNewFeature(entry);
    }
}
```

### Modifying Entry After Storage

**Problem:**
```csharp
// Bad - changes made after storage are lost
StorageContext.Store(formEntry);
formEntry.Status = "Completed";  // This change is never saved!
```

**Solution:**
```csharp
// Good - either modify before storage or store again
formEntry.Status = "Completed";
StorageContext.Store(formEntry);

// Or
StorageContext.Store(formEntry);
// ... later ...
formEntry.Status = "Completed";
StorageContext.Store(formEntry);  // Store again with changes
```

### Ignoring Submission Behavior Flags

**Problem:**
```csharp
// Bad - ignores SuppressStorage flag
public void SubmitEntry(FormEntry entry, SubmissionBehavior behavior)
{
    StorageContext.Store(entry);  // Stores even when suppressed!
}
```

**Solution:**
```csharp
// Good - check flags
public void SubmitEntry(FormEntry entry, SubmissionBehavior behavior)
{
    if (!behavior.HasFlag(SubmissionBehavior.SuppressStorage))
    {
        StorageContext.Store(entry);
    }
}
```

## Context and State Management

### Not Passing Context Objects

**Problem:**
```csharp
// Bad - creating new context for each recursive call
public void ProcessEntry(FormEntry entry)
{
    var syncContext = new LinkedLookupSyncContext();  // Loses state!
    // Process
    ProcessRelatedEntry(relatedEntry);  // New context created again
}
```

**Solution:**
```csharp
// Good - pass context through calls
public void ProcessEntry(FormEntry entry, LinkedLookupSyncContext syncContext = null)
{
    if (syncContext == null)
        syncContext = new LinkedLookupSyncContext();

    // Process
    ProcessRelatedEntry(relatedEntry, syncContext);  // Pass same context
}
```

### Modifying Shared State Without Synchronization

**Problem:**
```csharp
// Bad - concurrent access to shared state
private int _processCount = 0;

public void ProcessEntry(FormEntry entry)
{
    _processCount++;  // Race condition in concurrent scenarios!
}
```

**Solution:**
```csharp
// Good - use thread-safe increment or local state
public void ProcessEntry(FormEntry entry, ProcessContext context)
{
    context.IncrementProcessCount();  // Thread-safe
}
```

## Infinite Loop Prevention

### Missing Limit Checks

**Problem:**
```csharp
// Bad - no protection against infinite recursion
public void SyncLinkedLookups(FormEntry entry)
{
    var relatedEntry = GetRelatedEntry(entry);
    SyncLinkedLookups(relatedEntry);  // Infinite loop possible!
}
```

**Solution:**
```csharp
// Good - enforce limits
public void SyncLinkedLookups(FormEntry entry, SyncContext context)
{
    if (!context.TryIncrementOperations(entry.Id))
    {
        // Limit reached, abandon remaining operations
        return;
    }

    var relatedEntry = GetRelatedEntry(entry);
    if (relatedEntry != null)
    {
        SyncLinkedLookups(relatedEntry, context);
    }
}
```

## Field Path Navigation

### Hardcoding Field Paths

**Problem:**
```csharp
// Bad - fragile, breaks if structure changes
var value = entry.Data["Section1"]["Field2"];
```

**Solution:**
```csharp
// Good - use field path utilities
var fieldPath = "Section1.Field2";
var value = GetFieldValue(entry, fieldPath);
```

### Not Handling Nested Fields

**Problem:**
```csharp
// Bad - assumes flat structure
public object GetFieldValue(FormEntry entry, string fieldName)
{
    return entry.Data[fieldName];  // Fails for "Section.Field"
}
```

**Solution:**
```csharp
// Good - handle nested paths
public object GetFieldValue(FormEntry entry, string fieldPath)
{
    var pathParts = fieldPath.Split('.');
    object current = entry.Data;

    foreach (var part in pathParts)
    {
        if (current is IDictionary<string, object> dict)
            current = dict[part];
        else
            return null;
    }

    return current;
}
```

## Testing Mistakes

### Not Using TestFiles

**Problem:**
```csharp
// Bad - hardcoded test data
[Test]
public void TestFormSubmission()
{
    var form = new Form { Id = "123", Name = "Test" };
    // ...
}
```

**Solution:**
```csharp
// Good - use TestFiles organization data
[Test]
public void TestFormSubmission()
{
    LoadOrganization("TestOrg");
    var form = GetForm("TestFormId");
    // ...
}
```

### Not Cleaning Up Test State

**Problem:**
```csharp
// Bad - test state leaks to other tests
[Test]
public void TestFeature()
{
    FeatureFlags.MyFeature = true;
    // Test logic
    // Missing: FeatureFlags.MyFeature = false;
}
```

**Solution:**
```csharp
// Good - clean up in teardown or try-finally
[Test]
public void TestFeature()
{
    var originalValue = FeatureFlags.MyFeature;
    try
    {
        FeatureFlags.MyFeature = true;
        // Test logic
    }
    finally
    {
        FeatureFlags.MyFeature = originalValue;
    }
}
```

## Frontend Pitfalls

### Reactivity Issues in Vue

**Problem:**
```javascript
// Bad - loses reactivity
const state = reactive({ count: 0 });
let count = state.count;  // No longer reactive
count++;  // Doesn't update state
```

**Solution:**
```javascript
// Good - maintain reactivity
const state = reactive({ count: 0 });
state.count++;  // Updates reactive state

// Or use toRefs
const { count } = toRefs(state);
count.value++;
```

### Not Handling API Errors

**Problem:**
```javascript
// Bad - assumes success
async function submitForm() {
    const result = await api.submitEntry(entry);
    showSuccess();  // What if it failed?
}
```

**Solution:**
```javascript
// Good - handle errors
async function submitForm() {
    try {
        const result = await api.submitEntry(entry);
        if (result.status === 'Success') {
            showSuccess();
        } else {
            showError(result.errorMessage);
        }
    } catch (error) {
        showError('Failed to submit form. Please try again.');
        console.error(error);
    }
}
```

## Performance Pitfalls

### N+1 Query Problem

**Problem:**
```csharp
// Bad - one query per entry
var form = StorageContext.Get<Form>(formId);
foreach (var entryId in form.EntryIds)
{
    var entry = StorageContext.Get<FormEntry>(entryId);  // N queries
    ProcessEntry(entry);
}
```

**Solution:**
```csharp
// Good - batch fetch
var form = StorageContext.Get<Form>(formId);
var entries = StorageContext.GetMany<FormEntry>(form.EntryIds);  // 1 query
foreach (var entry in entries)
{
    ProcessEntry(entry);
}
```

### Unnecessary Re-computation

**Problem:**
```javascript
// Bad - computes on every access
function getFormattedData() {
    return expensiveComputation(rawData);
}

// Called in template multiple times
```

**Solution:**
```javascript
// Good - use computed property
const formattedData = computed(() => {
    return expensiveComputation(rawData.value);
});
```
