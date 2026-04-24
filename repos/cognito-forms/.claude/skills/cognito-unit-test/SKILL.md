---
name: cognito-unit-test
description: Guides the creation of unit tests for Cognito Forms, using MSTest patterns, TestFiles organization, and the BaseTest infrastructure with Autofac DI.
version: 2.0.0
allowed-tools: ["Read", "Grep", "Glob", "Write"]
---

# Cognito Forms Unit Test Skill

## Test Project Structure

- **Unit tests**: `Cognito.UnitTests/`
- **Integration tests**: `Cognito.Forms.UnitTests/`
- **Test data**: `Cognito.Forms.UnitTests/TestFiles/`
- **Framework**: MSTest (`[TestClass]`, `[TestMethod]`, `[DataTestMethod]`)

## Test Infrastructure

Tests inherit from `BaseTest`, which provides a full Autofac DI container with `TestStore` (Azure Table test store) for realistic integration testing. This is NOT mock-based — services resolve against real DI registrations.

```csharp
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class MyServiceTests : BaseTest
{
    [TestMethod]
    public void MethodName_Scenario_ExpectedBehavior()
    {
        // Arrange — BaseTest provides FormsService, StorageContext, etc.
        var form = CreateTestForm();

        // Act
        var result = FormsService.ProcessForm(form);

        // Assert
        Assert.IsNotNull(result);
        Assert.AreEqual(expected, result.Status);
    }
}
```

### Overriding Services

Use `MockService<T>()` from `BaseTest` to replace specific DI registrations:

```csharp
[TestInitialize]
public void Setup()
{
    MockService<IEmailClient>(new TestEmailClient());
}
```

### Loading Test Organizations

Use the `[Org("OrgCode")]` attribute to load test data from `TestFiles/`:

```csharp
[Org("LinkedLookupTestOrg")]
[TestMethod]
public void SyncLookups_BidirectionalLink_UpdatesBothEntries()
{
    // Test org data loaded automatically
}
```

## Test Naming Convention

`MethodName_Scenario_ExpectedBehavior`

```csharp
[TestMethod]
public void SubmitEntry_WithValidData_ReturnsSuccess() { }

[TestMethod]
public void SubmitEntry_WithNullEntry_ReturnsValidationError() { }
```

## Running Tests

```bash
# Prefer the /mstest skill for filtered output
dotnet test Cognito.UnitTests/ --filter "ClassName~MyTestClass" --verbosity minimal
```
