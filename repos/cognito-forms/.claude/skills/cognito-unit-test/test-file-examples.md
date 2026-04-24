# TestFiles Examples and Usage

## TestFiles Directory Structure

The TestFiles directory (`Cognito.Forms.UnitTests/TestFiles/`) contains organization data used for integration testing. Each organization has its own directory with JSON files representing stored entities.

### Common Files in Each Organization

**ThumbprintIndex.json** — Index of all entities and their versions, used to track which entities exist and their revision hashes.

**FormsProfile.json** — User-level form permission profile (FormRole, FolderRole, WorkflowRoleAssignment). NOT an org-level forms list.

## Using TestFiles in Tests

Tests inherit from `BaseTest`, which provides Autofac DI with a `TestStore` backed by the TestFiles directory. The `[Org("OrgCode")]` attribute loads an organization's test data.

```csharp
[TestClass]
public class MyIntegrationTests : BaseTest
{
    [Org("LinkedLookupTestOrg")]
    [TestMethod]
    public void MyTest_Scenario_ExpectedResult()
    {
        // BaseTest provides FormsService, StorageContext, etc. via DI
        // Test org data is loaded automatically from TestFiles/LinkedLookupTestOrg/
        var form = FormsService.GetForm(formId);
        // ...
    }
}
```

## TestFiles Best Practices

1. **Use existing test organizations when possible** — creating new orgs adds maintenance burden
2. **Document custom organizations** if you must create one — explain what forms/entries it contains and why
3. **Don't hardcode entity IDs** — reference them via test constants or load them dynamically
