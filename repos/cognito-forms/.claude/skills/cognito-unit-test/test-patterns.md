# Unit Test Patterns and Anti-Patterns

## Testing Anti-Patterns to Avoid

### 1. Testing Implementation Instead of Behavior

**Anti-pattern:**
```csharp
[TestMethod]
public void SubmitEntry_CallsStorageContextStore()
{
    // Bad - testing implementation detail
    var entry = CreateTestEntry();

    _formsService.SubmitEntry(ref entry);

    // e.g. verifying implementation details like storage calls
}
```

**Better approach:**
```csharp
[TestMethod]
public void SubmitEntry_ValidEntry_PersistsEntryData()
{
    // Good - testing behavior
    var entry = CreateTestEntry();
    entry.Data["Name"] = "John Doe";

    var result = FormsService.SubmitEntry(entry);

    Assert.AreEqual(SubmissionResultStatus.Success, result.Status);
    // Verify the entry can be retrieved with correct data
    var retrievedEntry = GetStoredEntry(entry.Id);
    Assert.AreEqual("John Doe", retrievedEntry.Data["Name"]);
}
```

### 2. Overly Complex Test Setup

**Anti-pattern:** Manually constructing complex mock setups instead of using the test infrastructure.

**Better approach:** Inherit from `BaseTest`, use `[Org("OrgCode")]` to load test data, and use `MockService<T>` for service mocks. The Autofac DI container handles wiring.

### 3. Testing Multiple Scenarios in One Test

**Anti-pattern:**
```csharp
[TestMethod]
public void SubmitEntry_VariousScenarios_ReturnsCorrectStatus()
{
    // Bad - testing multiple things
    var validEntry = CreateValidEntry();
    var result1 = FormsService.SubmitEntry(validEntry);
    Assert.AreEqual(SubmissionResultStatus.Success, result1.Status);

    var invalidEntry = CreateInvalidEntry();
    var result2 = FormsService.SubmitEntry(invalidEntry);
    Assert.AreEqual(SubmissionResultStatus.ValidationError, result2.Status);

    FormEntry nullEntry = null;
    var result3 = FormsService.SubmitEntry(nullEntry);
    Assert.AreEqual(SubmissionResultStatus.ValidationError, result3.Status);
}
```

**Better approach:**
```csharp
[TestMethod]
public void SubmitEntry_ValidEntry_ReturnsSuccess()
{
    var entry = CreateValidEntry();

    var result = FormsService.SubmitEntry(entry);

    Assert.AreEqual(SubmissionResultStatus.Success, result.Status);
}

[TestMethod]
public void SubmitEntry_InvalidEntry_ReturnsValidationError()
{
    var entry = CreateInvalidEntry();

    var result = FormsService.SubmitEntry(entry);

    Assert.AreEqual(SubmissionResultStatus.ValidationError, result.Status);
}

[TestMethod]
public void SubmitEntry_NullEntry_ReturnsValidationError()
{
    FormEntry entry = null;

    var result = FormsService.SubmitEntry(entry);

    Assert.AreEqual(SubmissionResultStatus.ValidationError, result.Status);
}
```

### 4. Not Cleaning Up State

**Anti-pattern:**
```csharp
[TestMethod]
public void SubmitEntry_WithFeatureEnabled_ProcessesCorrectly()
{
    // Bad - modifies global state without cleanup
    FeatureFlags.LinkedLookups = true;

    var result = FormsService.SubmitEntry(entry);

    Assert.AreEqual(SubmissionResultStatus.Success, result.Status);
    // Missing cleanup - affects other tests!
}
```

**Better approach:**
```csharp
[TestMethod]
public void SubmitEntry_WithFeatureEnabled_ProcessesCorrectly()
{
    // Good - cleanup in finally
    var originalValue = FeatureFlags.LinkedLookups;
    try
    {
        FeatureFlags.LinkedLookups = true;

        var result = FormsService.SubmitEntry(entry);

        Assert.AreEqual(SubmissionResultStatus.Success, result.Status);
    }
    finally
    {
        FeatureFlags.LinkedLookups = originalValue;
    }
}
```

### 5. Hardcoded Test Data

**Anti-pattern:**
```csharp
[TestMethod]
public void ProcessForm_ExistingForm_UpdatesCorrectly()
{
    // Bad - hardcoded, fragile
    var form = _mockStorageContext.Object.Get<Form>("hardcoded-id-123");

    var result = _formsService.ProcessForm(form);

    Assert.IsNotNull(result);
}
```

**Better approach:**
```csharp
[TestMethod]
public void ProcessForm_ExistingForm_UpdatesCorrectly()
{
    // Good - use test data builders or TestFiles
    var form = CreateTestForm();
    SetupFormStorage(form);

    var result = _formsService.ProcessForm(form);

    Assert.IsNotNull(result);
}

private Form CreateTestForm()
{
    return new Form
    {
        Id = Guid.NewGuid().ToString(),
        Name = "Test Form",
        // ... other properties
    };
}
```

## Effective Testing Patterns

### 1. Arrange-Act-Assert (AAA) Pattern

```csharp
[TestMethod]
public void SyncLinkedLookups_NewLink_UpdatesTargetEntry()
{
    // Arrange - Setup test data and dependencies
    var sourceEntry = CreateTestEntry();
    var targetEntry = CreateTestEntry();
    var syncContext = new LinkedLookupSyncContext();
    SetupStorageForSync(sourceEntry, targetEntry);

    // Act - Execute the method under test
    _linkedLookupService.SyncLinkedLookups(
        form,
        sourceEntry,
        syncContext
    );

    // Assert - Verify the expected outcome
    var updatedTarget = GetStoredEntry(targetEntry.Id);
    Assert.IsTrue(TargetContainsSourceReference(updatedTarget, sourceEntry));
}
```

### 2. Test Data Builders

```csharp
public class FormBuilder
{
    private Form _form = new Form();

    public FormBuilder WithId(string id)
    {
        _form.Id = id;
        return this;
    }

    public Form Build()
    {
        return _form;
    }
}

// Usage in tests
[TestMethod]
public void SaveForm_WithLinkedLookup_EstablishesLink()
{
    var form = new FormBuilder()
        .WithId("test-form-1")
        .Build();

    var result = _formsService.SaveForm(form);

    Assert.AreEqual(FormSaveStatus.Success, result.Status);
}
```

### 3. Parameterized Tests

```csharp
[DataTestMethod]
[DataRow(0, SubmissionResultStatus.ValidationError)]
[DataRow(1, SubmissionResultStatus.Success)]
[DataRow(100, SubmissionResultStatus.Success)]
[DataRow(101, SubmissionResultStatus.LimitExceeded)]
public void ValidateEntryCount_VariousCounts_ReturnsCorrectStatus(int count, SubmissionResultStatus expectedStatus)
{
    var form = CreateFormWithEntryLimit(100);

    var result = _validator.ValidateEntryCount(form, count);

    Assert.AreEqual(expectedStatus, result.Status);
}
```

### 4. Testing Exceptions

```csharp
[TestMethod]
public void ProcessEntry_InvalidOperation_ThrowsException()
{
    // Arrange
    var entry = CreateInvalidEntry();

    // Act & Assert
    Assert.ThrowsException<InvalidOperationException>(() =>
    {
        _service.ProcessEntry(entry);
    });
}
```

### 5. Async Test Patterns

```csharp
[TestMethod]
public async Task SubmitEntryAsync_ValidEntry_CompletesSuccessfully()
{
    // Arrange
    var entry = CreateTestEntry();
    SetupAsyncStorage();

    // Act
    var result = await _formsService.SubmitEntryAsync(entry);

    // Assert
    Assert.AreEqual(SubmissionResultStatus.Success, result.Status);
}
```