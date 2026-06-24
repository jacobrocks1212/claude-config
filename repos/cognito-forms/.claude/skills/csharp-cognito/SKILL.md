---
name: csharp-cognito
description: C# development patterns for the Cognito Forms codebase. Covers Autofac DI, Azure Table/Cosmos storage, MSTest testing, async/await, and nullable reference types. NOT .NET Core — most projects target net472/netstandard2.0.
triggers:
  - "*.cs"
  - "async Task"
  - "await"
  - "IStorageContext"
  - "IFormsService"
  - "Module<"
  - "[TestClass]"
  - "[TestMethod]"
  - "BaseService"
  - "CoreService"
---

# C# Development Patterns — Cognito Forms

## Platform

- **Cognito.Core**: net472 (default) / netstandard2.0 (NETCORE Debug), LangVersion 10
- **Cognito.Services**: net472 (default) / net10.0 (NETCORE Debug), LangVersion 10
- **Cognito** (business logic): netstandard2.0, LangVersion 8.0
- **Cognito.UnitTests / Cognito.Forms.UnitTests**: LangVersion 8.0
- **DI Container**: Autofac (NOT Microsoft.Extensions.DependencyInjection)
- **Storage**: Azure Table Storage + Cosmos DB via custom `IStorageContext` (NOT Entity Framework)
- **Test Framework**: MSTest (NOT xUnit)

## Naming Conventions

```csharp
// PascalCase for public members
public class PaymentService { }
public string CustomerName { get; set; }
public void ProcessPayment() { }

// _camelCase for private fields
private readonly ILogger<PaymentService> _logger;
private readonly IPaymentGateway _gateway;

// camelCase for parameters and locals
public async Task ProcessAsync(string orderId)
{
    var order = await _storageContext.Get<Order>(orderId);
}

// I prefix for interfaces
public interface IPaymentService { }
```

## Async/Await Patterns

```csharp
// WRONG - causes deadlocks
var result = GetDataAsync().Result;
GetDataAsync().Wait();

// CORRECT - always await
var result = await GetDataAsync();
```

```csharp
// Return Task for void operations
public async Task SaveAsync(Order order)
{
    await _storageContext.Store(order);
}

// Return Task<T> for operations with results
public async Task<Order?> GetByIdAsync(string id)
{
    return await _storageContext.Get<Order>(id);
}
```

## Dependency Injection (Autofac)

### Module Registration
```csharp
// In a Module class (e.g., CognitoCoreModule.cs)
public class CognitoCoreModule : Autofac.Module
{
    protected override void Load(ContainerBuilder builder)
    {
        builder.RegisterType<Module<IFormsService>>().SingleInstance();
        builder.RegisterType<Module<IPaymentService>>().SingleInstance();
    }
}
```

### Constructor Injection
```csharp
// Services take Module<T> for lazy resolution
public class FormsAdminController : ServiceController
{
    private readonly Module<IFormsService> _formsModule;

    public FormsAdminController(Module<IFormsService> formsModule)
    {
        _formsModule = formsModule;
    }
}

// Service base classes take IStorageContext or ICoreService
public class MyService : BaseService
{
    public MyService(IStorageContext storageContext) : base(storageContext) { }
}

// Modern pattern: OrgScopedService
public class MyOrgService : OrgScopedService
{
    public MyOrgService(IOrganizationContext orgContext) : base(orgContext) { }
}
```

## Data Access (IStorageContext)

There is NO Entity Framework in this codebase. Storage is Azure Table + Cosmos DB via custom abstractions.

```csharp
// Reading entities
var form = _storageContext.Get<Form>(formId);
var form = await _storageContext.GetAsync<Form>(formId);
var form = _storageContext.Get<Form>(formId, bypassCache: true); // skip cache

// Storing entities
_storageContext.Store(entity);

// Updating with concurrency
await _storageContext.UpdateAsync<Form>(formId, async form =>
{
    form.Name = "Updated";
});

// Batch operations (max 100 per batch)
_storageContext.BatchCreateOrUpdate<FormEntry>(entries);
```

## Nullable Reference Types

```csharp
public class Customer
{
    public string Id { get; set; } = string.Empty;
    public string? MiddleName { get; set; }
    public DateTime? DeletedAt { get; set; }
}

var order = await _storageContext.Get<Order>(id);
return order ?? throw new NotFoundException($"Order {id} not found");
```

## MSTest Testing

```csharp
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class MyServiceTests : BaseTest
{
    [TestMethod]
    public void MethodName_Scenario_ExpectedBehavior()
    {
        // Arrange
        var form = CreateTestForm();

        // Act
        var result = FormsService.ProcessForm(form);

        // Assert
        Assert.IsNotNull(result);
        Assert.AreEqual(expected, result.Status);
    }

    [DataTestMethod]
    [DataRow(0, false)]
    [DataRow(1, true)]
    [DataRow(100, true)]
    public void Validate_VariousCounts_ReturnsExpected(int count, bool expected)
    {
        var result = _validator.IsValid(count);
        Assert.AreEqual(expected, result);
    }
}
```

## TypeScript Type Auto-Generation

TypeScript server-types are generated from C# by TypeGen, which reflects over the **compiled** `Cognito.Services` assemblies (`bin/Cognito.Services.dll`, `Cognito.Core.dll`, `Cognito.dll`) — it does NOT parse source.

- Types implementing `IModelInstance` are automatically discovered and generated
- Types in the `allowedTypes` list in `CoreTypeScriptGenerationSpec.cs` are also generated
- Generated types go to `Cognito.Web.Client/libs/types/server-types/` and are **committed to source control**

Do NOT hand-edit or hand-create these files — TypeGen overwrites them.

### Regenerating after a server-model change — DON'T full-build for this

A Debug compile of `Cognito.Services` already regenerates the types: a `PostBuild` target in `Cognito.Services.csproj` runs `post-build.ps1`, which invokes `pnpm run typegen -UpdateInPlace`. So you do **not** need a full-solution build to refresh types.

- **Build targeted, not full.** After changing a C# type that exports to TypeScript, use `/msbuild -Project "Cognito.Services/Cognito.Services.csproj"` — it recompiles only `Cognito.Services` + its deps (`Cognito.Core`, `Cognito`) AND triggers the post-build regeneration. A bare full `/msbuild` just to refresh types wastes time compiling QueueJob, all test projects, SpecGen, marketing, etc.
- **The regen is async/detached.** `post-build.ps1` launches typegen via `Start-Process` with no `-Wait`, so the build returns *before* typegen finishes (and a typegen failure is swallowed silently). If you need to diff or commit the generated types **immediately** after building, force a synchronous, error-surfacing refresh:
  ```bash
  pwsh "Cognito.Web.Client/libs/types/typegen/generate-server-types.ps1" -UpdateInPlace
  ```
  This script runs `dotnet dotnet-typegen` (NOT `dotnet build`), so it is not subject to the build-queue hook. `-UpdateInPlace` rewrites files atomically and drops types that no longer exist. It still reflects over the compiled DLLs, so build `Cognito.Services` first if your C# change isn't compiled yet.
- **Commit the result.** `git status Cognito.Web.Client/libs/types/server-types/` and commit the regenerated files alongside your backend change. To discard an unwanted regen, revert only that path: `git checkout -- "Cognito.Web.Client/libs/types/server-types"` (never a repo-wide checkout/clean/reset).

## Critical Rules

1. **Never use .Result or .Wait()** — always await
2. **Use nullable reference types** — catch null issues at compile time
3. **No Entity Framework** — use IStorageContext for all data access
4. **Autofac for DI** — not builder.Services.AddScoped
5. **MSTest for tests** — [TestClass]/[TestMethod], not [Fact]/[Theory]
6. **Check LangVersion before using newer C# syntax** — most projects are C# 8.0
