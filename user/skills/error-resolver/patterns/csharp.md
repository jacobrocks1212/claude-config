# C# / .NET 8 Error Patterns

Common error patterns and resolutions for C# .NET 8, Entity Framework Core, and Azure services.

## Async/Await Errors

### Pattern: Deadlock from .Result or .Wait()

```
Error: Application hangs or deadlocks
Context: Calling .Result or .Wait() on async methods
```

**Root Cause**: Synchronously blocking on async code causes deadlock.

**Bad Code**:
```csharp
// NEVER do this - causes deadlock
public string GetData()
{
    var result = GetDataAsync().Result;  // DEADLOCK
    return result;
}

public void ProcessData()
{
    ProcessDataAsync().Wait();  // DEADLOCK
}
```

**Fix**:
```csharp
// Always use async/await
public async Task<string> GetDataAsync()
{
    var result = await GetDataAsync();
    return result;
}

// If you MUST call sync (rare), use proper pattern
public string GetDataSync()
{
    return Task.Run(() => GetDataAsync()).GetAwaiter().GetResult();
}
```

### Pattern: async void Exception Handling

```
Error: Unhandled exception crashes application
Context: async void method throws exception
```

**Root Cause**: Exceptions in async void methods cannot be caught.

**Bad Code**:
```csharp
// async void - exceptions are unobservable
private async void OnButtonClick(object sender, EventArgs e)
{
    await ProcessDataAsync();  // Exception here crashes app
}
```

**Fix**:
```csharp
// Use async Task for testability and error handling
private async Task OnButtonClickAsync()
{
    try
    {
        await ProcessDataAsync();
    }
    catch (Exception ex)
    {
        _logger.LogError(ex, "Error processing data");
    }
}

// For event handlers, wrap in try-catch
private async void OnButtonClick(object sender, EventArgs e)
{
    try
    {
        await OnButtonClickAsync();
    }
    catch (Exception ex)
    {
        // Handle at boundary
    }
}
```

## Nullable Reference Type Errors

### Pattern: NullReferenceException

```
Error: System.NullReferenceException: Object reference not set to an instance of an object.
```

**Root Cause**: Accessing member on null object.

**Prevention with Nullable Reference Types**:
```csharp
// Enable in .csproj
<Nullable>enable</Nullable>

// Proper null handling
public string? Name { get; set; }  // Nullable

public void Process(User? user)
{
    // Null check required
    if (user is null)
        throw new ArgumentNullException(nameof(user));

    // Or use null-conditional
    var name = user?.Name ?? "Unknown";

    // Pattern matching
    if (user is { Name: var name })
    {
        Console.WriteLine(name);
    }
}
```

### Pattern: CS8618 - Non-nullable property not initialized

```
Warning CS8618: Non-nullable property 'Name' must contain a non-null value when exiting constructor.
```

**Fix Options**:
```csharp
// Option 1: Initialize in declaration
public string Name { get; set; } = string.Empty;

// Option 2: Use required keyword (.NET 7+)
public required string Name { get; set; }

// Option 3: Initialize in constructor
public class User
{
    public string Name { get; set; }

    public User(string name)
    {
        Name = name;
    }
}

// Option 4: Use null-forgiving (last resort)
public string Name { get; set; } = null!;
```

## Entity Framework Core Errors

### Pattern: DbContext Disposed Exception

```
Error: System.ObjectDisposedException: Cannot access a disposed object.
Object name: 'DbContext'.
```

**Root Cause**: Lazy loading or deferred execution after context disposal.

**Bad Code**:
```csharp
public IEnumerable<User> GetUsers()
{
    using var context = new AppDbContext();
    return context.Users;  // Deferred execution - context disposed before enumeration
}
```

**Fix**:
```csharp
// Materialize query before returning
public async Task<List<User>> GetUsersAsync()
{
    await using var context = new AppDbContext();
    return await context.Users.ToListAsync();  // Materialized
}

// Or use proper DI scoping
public class UserService
{
    private readonly AppDbContext _context;

    public UserService(AppDbContext context)
    {
        _context = context;  // Scoped by DI container
    }

    public async Task<List<User>> GetUsersAsync()
    {
        return await _context.Users.ToListAsync();
    }
}
```

### Pattern: Tracking Issues - Entity Already Tracked

```
Error: The instance of entity type 'User' cannot be tracked because another instance
with the same key value for {'Id'} is already being tracked.
```

**Fix**:
```csharp
// Option 1: Use AsNoTracking for read-only queries
var users = await _context.Users
    .AsNoTracking()
    .ToListAsync();

// Option 2: Detach before attaching
var existingEntry = _context.ChangeTracker
    .Entries<User>()
    .FirstOrDefault(e => e.Entity.Id == user.Id);

if (existingEntry != null)
{
    existingEntry.State = EntityState.Detached;
}

_context.Users.Update(user);

// Option 3: Use separate context for updates
await using var updateContext = await _contextFactory.CreateDbContextAsync();
updateContext.Users.Update(user);
await updateContext.SaveChangesAsync();
```

### Pattern: Lazy Loading Navigation Property is Null

```
Error: NullReferenceException when accessing navigation property
Context: user.Orders is null even though data exists
```

**Root Cause**: Navigation property not loaded.

**Fix**:
```csharp
// Option 1: Eager loading with Include
var user = await _context.Users
    .Include(u => u.Orders)
    .FirstOrDefaultAsync(u => u.Id == userId);

// Option 2: Explicit loading
var user = await _context.Users.FindAsync(userId);
await _context.Entry(user)
    .Collection(u => u.Orders)
    .LoadAsync();

// Option 3: Projection
var userDto = await _context.Users
    .Where(u => u.Id == userId)
    .Select(u => new UserDto
    {
        Id = u.Id,
        Name = u.Name,
        OrderCount = u.Orders.Count()
    })
    .FirstOrDefaultAsync();
```

### Pattern: Concurrency Conflict

```
Error: DbUpdateConcurrencyException: Database operation expected to affect 1 row(s)
but actually affected 0 row(s).
```

**Fix**:
```csharp
// Add concurrency token
public class User
{
    public int Id { get; set; }
    public string Name { get; set; }

    [ConcurrencyCheck]
    public DateTime LastModified { get; set; }

    // Or use RowVersion
    [Timestamp]
    public byte[] RowVersion { get; set; }
}

// Handle in update
try
{
    await _context.SaveChangesAsync();
}
catch (DbUpdateConcurrencyException ex)
{
    var entry = ex.Entries.Single();
    var databaseValues = await entry.GetDatabaseValuesAsync();

    if (databaseValues == null)
    {
        // Entity was deleted
        throw new EntityNotFoundException();
    }

    // Refresh with database values
    entry.OriginalValues.SetValues(databaseValues);

    // Retry or notify user of conflict
}
```

## Dependency Injection Errors

### Pattern: Unable to resolve service

```
Error: System.InvalidOperationException: Unable to resolve service for type
'IUserService' while attempting to activate 'UserController'.
```

**Fix**:
```csharp
// Ensure service is registered in Program.cs
builder.Services.AddScoped<IUserService, UserService>();

// Check for missing dependencies in the chain
builder.Services.AddScoped<IUserRepository, UserRepository>();
builder.Services.AddScoped<IEmailService, EmailService>();

// For generic services
builder.Services.AddScoped(typeof(IRepository<>), typeof(Repository<>));
```

### Pattern: Captive Dependency

```
Warning: Singleton service depends on Scoped service
```

**Root Cause**: Longer-lived service capturing shorter-lived dependency.

**Bad Code**:
```csharp
// Singleton captures Scoped - BAD
public class SingletonService
{
    private readonly ScopedService _scoped;  // Will be stale!

    public SingletonService(ScopedService scoped)
    {
        _scoped = scoped;
    }
}
```

**Fix**:
```csharp
// Use IServiceScopeFactory
public class SingletonService
{
    private readonly IServiceScopeFactory _scopeFactory;

    public SingletonService(IServiceScopeFactory scopeFactory)
    {
        _scopeFactory = scopeFactory;
    }

    public async Task DoWorkAsync()
    {
        using var scope = _scopeFactory.CreateScope();
        var scopedService = scope.ServiceProvider.GetRequiredService<ScopedService>();
        await scopedService.ProcessAsync();
    }
}
```

## HTTP/API Errors

### Pattern: HttpClient Socket Exhaustion

```
Error: System.Net.Sockets.SocketException: Only one usage of each socket address
(protocol/network address/port) is normally permitted.
```

**Root Cause**: Creating new HttpClient instances instead of reusing.

**Bad Code**:
```csharp
// NEVER do this
public async Task<string> GetDataAsync()
{
    using var client = new HttpClient();  // Creates new socket each time
    return await client.GetStringAsync("https://api.example.com/data");
}
```

**Fix**:
```csharp
// Use IHttpClientFactory
builder.Services.AddHttpClient<IApiClient, ApiClient>(client =>
{
    client.BaseAddress = new Uri("https://api.example.com");
    client.DefaultRequestHeaders.Add("Accept", "application/json");
});

// Or named clients
builder.Services.AddHttpClient("ExternalApi", client =>
{
    client.BaseAddress = new Uri("https://api.example.com");
});

// Usage
public class ApiClient : IApiClient
{
    private readonly HttpClient _httpClient;

    public ApiClient(HttpClient httpClient)
    {
        _httpClient = httpClient;  // Managed by factory
    }

    public async Task<string> GetDataAsync()
    {
        return await _httpClient.GetStringAsync("/data");
    }
}
```

## Azure-Specific Errors

### Pattern: Azure SQL Transient Errors

```
Error: SqlException: A transport-level error has occurred
Error: SqlException: Resource ID: X. The request limit for the database is Y and has been reached.
```

**Fix with Retry Policy**:
```csharp
// Use Polly for resilience
builder.Services.AddDbContext<AppDbContext>(options =>
{
    options.UseSqlServer(connectionString, sqlOptions =>
    {
        sqlOptions.EnableRetryOnFailure(
            maxRetryCount: 5,
            maxRetryDelay: TimeSpan.FromSeconds(30),
            errorNumbersToAdd: null);
    });
});

// Or with Polly directly
builder.Services.AddHttpClient<IApiClient, ApiClient>()
    .AddTransientHttpErrorPolicy(policy =>
        policy.WaitAndRetryAsync(3, retryAttempt =>
            TimeSpan.FromSeconds(Math.Pow(2, retryAttempt))));
```

### Pattern: Azure Blob Storage Access Denied

```
Error: Azure.RequestFailedException: This request is not authorized to perform this operation.
Status: 403 (Server failed to authenticate the request)
```

**Diagnosis**:
1. Check connection string or Managed Identity
2. Verify RBAC roles assigned
3. Check SAS token expiration
4. Verify container/blob exists

**Fix**:
```csharp
// Using Managed Identity (recommended)
builder.Services.AddSingleton(x =>
{
    var blobServiceClient = new BlobServiceClient(
        new Uri($"https://{storageAccountName}.blob.core.windows.net"),
        new DefaultAzureCredential());
    return blobServiceClient;
});

// Ensure proper RBAC role
// az role assignment create --assignee <app-object-id> \
//   --role "Storage Blob Data Contributor" \
//   --scope /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<storage>
```

## Common Validation Errors

### Pattern: Model State Invalid

```csharp
// Proper validation handling
[HttpPost]
public async Task<IActionResult> Create([FromBody] CreateUserRequest request)
{
    if (!ModelState.IsValid)
    {
        return BadRequest(new ValidationProblemDetails(ModelState));
    }

    // Process request
}

// Data annotations
public class CreateUserRequest
{
    [Required(ErrorMessage = "Name is required")]
    [StringLength(100, MinimumLength = 2)]
    public string Name { get; set; } = string.Empty;

    [Required]
    [EmailAddress(ErrorMessage = "Invalid email format")]
    public string Email { get; set; } = string.Empty;

    [Range(18, 120, ErrorMessage = "Age must be between 18 and 120")]
    public int Age { get; set; }
}
```

## Debug Commands for .NET

```powershell
# Check .NET version
dotnet --version
dotnet --list-sdks
dotnet --list-runtimes

# Restore packages
dotnet restore

# Check for package vulnerabilities
dotnet list package --vulnerable

# Check outdated packages
dotnet list package --outdated

# Clear NuGet cache
dotnet nuget locals all --clear

# Check EF Core migrations
dotnet ef migrations list

# Generate SQL script from migrations
dotnet ef migrations script

# Analyze assembly dependencies
dotnet publish -c Release
ildasm YourAssembly.dll
```

## Cognito Forms Specific

### Build and Test Commands

```powershell
# NEVER use dotnet build/run directly
# Use project-specific PowerShell scripts instead

# Run unit tests
cd Cognito.Forms.UnitTests
dotnet test --filter "Category!=Integration"
```

### Common Project Patterns

```csharp
// Use project-standard async patterns
public async Task<Result<T>> ExecuteAsync<T>(Func<Task<T>> action)
{
    try
    {
        var result = await action();
        return Result<T>.Success(result);
    }
    catch (ValidationException ex)
    {
        return Result<T>.Failure(ex.Errors);
    }
    catch (Exception ex)
    {
        _logger.LogError(ex, "Unexpected error");
        return Result<T>.Failure("An unexpected error occurred");
    }
}
```
