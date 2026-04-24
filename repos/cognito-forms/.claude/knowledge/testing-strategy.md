# Testing Strategy

## Test Project Topology

| Project | Type | Purpose |
|---------|------|---------|
| `Cognito.UnitTests` | Unit | Fast, isolated tests with mocks |
| `Cognito.Forms.UnitTests` | Integration | Tests with real StorageContext, TestFiles |

### When to Use Which

**Unit Tests (`Cognito.UnitTests`)**
- Testing pure business logic
- Testing individual methods in isolation
- When dependencies can be easily mocked
- Fast feedback during development

**Integration Tests (`Cognito.Forms.UnitTests`)**
- Testing data access patterns
- Testing StorageContext interactions
- Verifying serialization/deserialization
- Testing complex workflows end-to-end

## Test Framework

Both projects use **MSTest** with the following patterns:

### Test Class Structure

```csharp
[TestClass]
public class MyServiceTests
{
    private Mock<IDependency> _mockDependency;
    private MyService _sut;

    [TestInitialize]
    public void Setup()
    {
        _mockDependency = new Mock<IDependency>();
        _sut = new MyService(_mockDependency.Object);
    }

    [TestMethod]
    public async Task MethodName_Scenario_ExpectedBehavior()
    {
        // Arrange
        _mockDependency.Setup(x => x.DoSomething()).Returns(expected);

        // Act
        var result = await _sut.MethodUnderTest();

        // Assert
        Assert.AreEqual(expected, result);
    }
}
```

### AAA Pattern

- **Arrange**: Set up test data and mocks
- **Act**: Execute the method under test
- **Assert**: Verify the results

### Naming Convention

```
MethodName_Scenario_ExpectedBehavior
```

Examples:
- `CreateForm_WithValidData_ReturnsNewForm`
- `GetEntry_WhenNotFound_ThrowsNotFoundException`
- `CalculateTotal_WithDiscounts_AppliesDiscountCorrectly`

## Backend Test Patterns

### Mocking Dependencies

```csharp
// Use MockService<T> for mocking service dependencies
var mockFormsService = new MockService<IFormsService>();

// For integration tests, prefer BaseTest with real Autofac DI
// over manual Mock<IStorageContext> - the TestStore handles storage
```

### Integration Tests with TestFiles

```csharp
[TestClass]
public class FormServiceIntegrationTests : BaseTest
{
    // BaseTest provides Autofac DI container with TestStore
    // Use [Org("OrgCode")] attribute to load test org data

    [TestMethod]
    [Org("TestOrg")]
    public void MyTest_Scenario_Expected()
    {
        // Test data loaded via [Org] attribute from TestFiles/
        var service = Resolve<IFormsService>();
        // ...
    }
}
```

### TestFiles Directory

`Cognito.Forms.UnitTests/TestFiles/` contains JSON fixtures organized by org:
- `TestOrg/` — General purpose test data
- `PaymentTests/` — Payment-specific scenarios
- `WorkflowMidnight/` — Workflow test scenarios

## Frontend Test Patterns

### Jest Configuration

Tests run with Jest via Nx:

```bash
npx nx test <project> -- --testPathPattern="<pattern>"
```

### Component Testing

```typescript
import { mount } from '@vue/test-utils';
import MyComponent from './MyComponent.vue';

describe('MyComponent', () => {
  it('renders correctly', () => {
    const wrapper = mount(MyComponent, {
      propsData: { title: 'Test' }  // Vue 2: propsData, not props
    });
    expect(wrapper.text()).toContain('Test');
  });
});
```

### model.js Testing

```typescript
import { Model, Type } from '@cognitoforms/model.js';

describe('Entity', () => {
  let model: Model;
  let type: Type;

  beforeEach(() => {
    model = new Model();
    type = model.addType('TestEntity', { /* schema */ });
  });

  it('creates entity with default values', async () => {
    const entity = await type.create();
    expect(entity.meta.isNew).toBe(true);
  });
});
```

## Running Tests

### Backend

```bash
# All tests in a project
dotnet test "Cognito.UnitTests\Cognito.UnitTests.csproj"

# Filtered by class
dotnet test --filter "ClassName~FormsService"

# Filtered by name
dotnet test --filter "Name~CreateForm"

# Prefer skill for filtered output
/mstest
```

### Frontend

```bash
# Specific project
npx nx test cognito-spa

# Pattern match
npx nx test cognito-client -- --testPathPattern="Payment"

# Prefer skill for filtered output
/nxtest
```

## Test Coverage

- Unit tests: Focus on business logic coverage
- Integration tests: Focus on critical paths
- Frontend: Component and composable testing

## Common Pitfalls

1. **Missing async/await**: Always use async test methods for async code
2. **Shared state**: Reset mocks in `[TestInitialize]`
3. **Flaky tests**: Avoid timing-dependent tests
4. **Over-mocking**: Don't mock what you're testing
5. **Missing cleanup**: Dispose resources in `[TestCleanup]`
