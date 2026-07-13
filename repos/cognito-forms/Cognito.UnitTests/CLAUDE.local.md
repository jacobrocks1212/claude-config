# Cognito.UnitTests — Unit Test Project

## Gotchas
- **Static Autofac container**: `diContainer` is static, shared across all tests. Per-test isolation uses `diScope` (lifetime scope).
- Tests run concurrently on different threads — use `EnsureIsolatedTestQueue()` to avoid queue cross-contamination.
- `ModuleFactory.CoreService` is reset per test — do NOT cache references across tests.
- `TestContext.Properties` drives test store behavior (auto-save, test directory).

## Indexing Test Performance
Tests in the `EntryIndexService` / `PersonSubmissionIndexing` area are pathologically slow if written naively (the class once took ~11 min; the fixes below cut it to ~1 min — PR #17028). Two rules:

- **Force an immediate schema rebuild after mutating a form's index schema — never leave it to `StorageContext.Store(form)` alone.** Storing a form whose change affects the index schema (`SubmitterPersonSettings`, `Format`, field-mapping paths, etc.) does NOT invalidate the schema synchronously; the production path debounces (~8 s) before rebuild, and `EnsureValidIndex` then polls on a `Task.Delay(10000)` retry loop, so every such store costs seconds of real wall time in-test. After storing, call `IndexService.InvalidateIndex(form, rebuildFacets: true, rebuildLinkAssignments: false)` to invalidate/rebuild immediately and bypass the debounce. Wrap the pair in a `StoreFormAndRebuildSchema(form)` helper and use it in place of bare `StorageContext.Store(form)` for any schema-affecting change.
- **Disable auto-create in tests that don't exercise it.** A form left with `SubmitterPersonSettings.CreateNewPersonEntries = true` / a set `AutoCreateActionId` does extra person-entry creation + indexing and creates lock contention that slows unrelated assertions. If a test submits entries but isn't testing auto-create, call `DisableAutoCreate(form)` during arrange.

## BaseTest Architecture
All test classes inherit `BaseTest`: DI scope management (`diScope`), test fixtures (`TestOrg`, `TestUser`, `AdminSession`, `PublicSession`), service mocking, queue helpers.

Lifecycle: `[TestInitialize] Initialize()` creates `diScope`, sets up `HttpContext.Current`, flushes `CoreService`, loads `TestOrg` per `[Org]`, logs in per `[User]`, applies `[FeatureFlag]` overrides. `[TestCleanup] Cleanup()` flushes `CoreService`, disposes `diScope`.

## Service Mocking
- `MockService<IPaymentService>()` — interface mock, automatically registered in DI.
- `RegisterService<IMyService>(instance)` or `RegisterService<IMyService>(ctx => new FakeMyService(ctx.Resolve<IDep>()))` — direct registration.
- `TestServiceRegistry` (`IRegistrationSource`) allows overriding services AFTER the DI scope is created; overrides resolve last.
- `GetService<T>()` returns the override if registered; `GetService<T>(ignoreOverrides: true)` returns the real impl; `GetService<T>(someOrg)` resolves org-scoped.

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
Isolate first with `EnsureIsolatedTestQueue()`, run the enqueueing code, then `await ProcessQueue(queue)`.

## Key Files
| File | Purpose |
|------|---------|
| `BaseTest.cs` | Abstract base for all tests; defines test fixture ID constants (`TestOrgId`, `TestUserId`, ...) |
| `TestFiles/` | JSON fixtures for TestStore entities |
| `Attributes/` | Test attributes (Org, User, FeatureFlag, etc.) |
| `_snapshots/` | Snapshot files for Snapper assertions (co-located with tests) |

## Snapshot Testing
Uses the **Snapper** library (`using Snapper;`) with `ShouldMatchSnapshot()`.
- Snapshots live in `_snapshots/` beside the test file: `ServiceTests/Indexing/_snapshots/TestClassName_TestMethodName.json`.
- Update all on a run: set the `UpdateSnapshots=true` environment variable for the test run. Update one test programmatically: `result.ShouldMatchSnapshot(SnapshotSettings.New().UpdateSnapshots(true))`.
- `Utilities/SnapshotUtilities.cs` normalizes dynamic values: `NormalizeIds()`, `NormalizeDateTimes()`, `NormalizeGuids()`.
