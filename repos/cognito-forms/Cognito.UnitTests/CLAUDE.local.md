# Cognito.UnitTests — Unit Test Project

## Gotchas
- **Static Autofac container**: `diContainer` is static, shared across all tests. Per-test isolation uses `diScope` (lifetime scope).
- Tests run concurrently on different threads — use `EnsureIsolatedTestQueue()` to avoid queue cross-contamination.
- `ModuleFactory.CoreService` is reset per test — do NOT cache references across tests.
- `TestContext.Properties` drives test store behavior (auto-save, test directory).

## BaseTest Architecture

### Inheritance Pattern
```
BaseTest (abstract)
  └── Your test class
```
All test classes inherit `BaseTest` which provides:
- DI scope management via `diScope`
- Test fixtures: `TestOrg`, `TestUser`, `AdminSession`, `PublicSession`
- Service mocking via `MockService<T>()`
- Queue processing helpers

### Lifecycle
```
[TestInitialize] Initialize()
  → Creates diScope
  → Sets up HttpContext.Current
  → Flushes CoreService
  → Loads TestOrg based on [Org] attribute
  → Logs in user based on [User] attribute
  → Applies [FeatureFlag] overrides

[TestCleanup] Cleanup()
  → Flushes CoreService
  → Disposes diScope
```

## Service Mocking

### MockService<T>() — Interface Mocking
```csharp
var mockPayment = MockService<IPaymentService>();
mockPayment.Setup(p => p.ProcessPayment(...)).Returns(...);
// Service is automatically registered in DI
```

### RegisterService<T>() — Direct Registration
```csharp
RegisterService<IMyService>(new FakeMyService());
// Or with factory:
RegisterService<IMyService>(ctx => new FakeMyService(ctx.Resolve<IDep>()));
```

### TestServiceRegistry Pattern
`TestServiceRegistry` implements `IRegistrationSource` to allow overriding services after the DI scope is created. Overrides registered via `MockService<T>()` or `RegisterService<T>()` are resolved last.

### GetService<T>() — Resolution
```csharp
var service = GetService<IFormsService>();                    // Gets override if registered
var realService = GetService<IFormsService>(ignoreOverrides: true);  // Gets real impl
var orgService = GetService<IFormsService>(someOrg);          // Org-scoped resolution
```

## Test Attributes

| Attribute | Purpose |
|-----------|---------|
| `[Org("OrgCode")]` | Sets TestOrg to specific organization |
| `[User("username")]` | Logs in as specific user |
| `[User(null)]` | Tests anonymous/unauthenticated scenario |
| `[SessionType(KeyType.Public)]` | Uses public session instead of admin |
| `[FeatureFlag(FeatureFlags.X, true)]` | Enables feature flag for test |
| `[TestStore(EnableAutoSave = true)]` | Configures TestStore auto-save behavior |
| `[TestFileStore(CanStoreFiles = true)]` | Enables file storage in tests |

## Queue Testing

```csharp
// Isolate queue to avoid cross-test contamination
var queue = EnsureIsolatedTestQueue();

// Execute code that enqueues messages...

// Process queued messages
await ProcessQueue(queue);
```

## Common Test IDs
```csharp
protected const string TestOrgId = "d4f559e4-efdc-4431-9ccb-1d6ef949146f";
protected const string TestUserId = "91da6154-e4e2-43c2-a03a-880620e52682";
// See BaseTest.cs for full list of test fixture IDs
```

## Key Files
| File | Purpose |
|------|---------|
| `BaseTest.cs` | Abstract base for all tests |
| `TestFiles/` | JSON fixtures for TestStore entities |
| `Attributes/` | Test attributes (Org, User, FeatureFlag, etc.) |
| `_snapshots/` | Snapshot files for Snapper assertions (co-located with tests) |

## Snapshot Testing

Uses the **Snapper** library (`using Snapper;`) with `ShouldMatchSnapshot()` extension method.

### Updating Snapshots

To update snapshots when tests fail due to expected changes, set the `UpdateSnapshots` environment variable:
```bash
UpdateSnapshots=true dotnet test "Cognito.UnitTests/Cognito.UnitTests.csproj" --filter "Name~TestName" --no-build
```

Or update a single test programmatically:
```csharp
result.ShouldMatchSnapshot(SnapshotSettings.New().UpdateSnapshots(true));
```

### Snapshot File Location
Snapshots are stored in `_snapshots/` folders alongside test files:
- `ServiceTests/Indexing/_snapshots/TestClassName_TestMethodName.json`

### Utilities
`Utilities/SnapshotUtilities.cs` provides normalization methods for:
- `NormalizeIds()` — Replace dynamic IDs with stable values
- `NormalizeDateTimes()` — Replace DateTime values
- `NormalizeGuids()` — Replace GUIDs

---

## Maintaining This Document

Update this file when:
- Adding new architectural patterns or service hierarchies
- Discovering non-obvious gotchas that would trip up future developers
- Renaming or restructuring directories/files mentioned here

Do NOT add: version numbers, line numbers, test counts, or other specifics that change frequently.
