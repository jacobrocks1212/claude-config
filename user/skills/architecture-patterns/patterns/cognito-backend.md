# Cognito Forms Backend Architecture Patterns

This document provides architecture patterns specific to the Cognito Forms .NET backend.

## Project Structure

```
Cognito Forms/
├── Cognito.Core/              # Domain models, interfaces, business logic
├── Cognito.Services/          # Web API, controllers, services
├── Cognito/                   # Shared utilities, helpers
├── Cognito.QueueJob/          # Background job processing
├── Cognito.QueueService/      # Queue message handlers
├── Cognito.Forms.UnitTests/   # xUnit tests
├── Cognito.UnitTests/         # Additional unit tests
└── Dependencies/              # Third-party dependencies
```

## Layer Responsibilities

### Cognito.Core (Domain Layer)

```csharp
// Domain models - pure C# classes, no framework dependencies
public class Form
{
    public Guid Id { get; private set; }
    public string Name { get; private set; }
    public OrganizationId OrganizationId { get; private set; }
    public IReadOnlyList<Field> Fields => _fields.AsReadOnly();

    private readonly List<Field> _fields = new();

    // Domain behavior
    public Result AddField(Field field)
    {
        if (_fields.Count >= MaxFields)
            return Result.Failure("Maximum field limit reached");

        _fields.Add(field);
        return Result.Success();
    }
}

// Domain interfaces
public interface IFormRepository
{
    Task<Form?> GetByIdAsync(Guid id, CancellationToken ct = default);
    Task<IReadOnlyList<Form>> GetByOrganizationAsync(Guid orgId, CancellationToken ct = default);
    Task SaveAsync(Form form, CancellationToken ct = default);
}

// Domain services
public interface IFormValidationService
{
    Task<ValidationResult> ValidateAsync(Form form, CancellationToken ct = default);
}
```

### Cognito.Services (Application Layer)

```csharp
// Application services orchestrate domain logic
public class FormService : IFormService
{
    private readonly IFormRepository _formRepository;
    private readonly IFormValidationService _validationService;
    private readonly IEventPublisher _eventPublisher;

    public FormService(
        IFormRepository formRepository,
        IFormValidationService validationService,
        IEventPublisher eventPublisher)
    {
        _formRepository = formRepository;
        _validationService = validationService;
        _eventPublisher = eventPublisher;
    }

    public async Task<Result<FormDto>> CreateFormAsync(
        CreateFormCommand command,
        CancellationToken ct = default)
    {
        // Validation
        var validationResult = await _validationService.ValidateAsync(command, ct);
        if (!validationResult.IsValid)
            return Result<FormDto>.Failure(validationResult.Errors);

        // Domain logic
        var form = Form.Create(command.Name, command.OrganizationId);

        // Persistence
        await _formRepository.SaveAsync(form, ct);

        // Events
        await _eventPublisher.PublishAsync(new FormCreatedEvent(form.Id), ct);

        return Result<FormDto>.Success(FormDto.FromDomain(form));
    }
}
```

### Controllers (Presentation Layer)

```csharp
[ApiController]
[Route("api/[controller]")]
public class FormsController : ControllerBase
{
    private readonly IFormService _formService;

    public FormsController(IFormService formService)
    {
        _formService = formService;
    }

    [HttpPost]
    [ProducesResponseType(typeof(FormDto), StatusCodes.Status201Created)]
    [ProducesResponseType(typeof(ProblemDetails), StatusCodes.Status400BadRequest)]
    public async Task<IActionResult> Create(
        [FromBody] CreateFormRequest request,
        CancellationToken ct)
    {
        var command = new CreateFormCommand(request.Name, User.GetOrganizationId());
        var result = await _formService.CreateFormAsync(command, ct);

        return result.Match(
            success: dto => CreatedAtAction(nameof(Get), new { id = dto.Id }, dto),
            failure: errors => BadRequest(new ValidationProblemDetails(errors))
        );
    }

    [HttpGet("{id:guid}")]
    [ProducesResponseType(typeof(FormDto), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Get(Guid id, CancellationToken ct)
    {
        var result = await _formService.GetFormAsync(id, ct);

        return result.Match(
            success: dto => Ok(dto),
            failure: _ => NotFound()
        );
    }
}
```

## Common Patterns

### Result Pattern for Error Handling

```csharp
// In Cognito.Core
public class Result<T>
{
    public bool IsSuccess { get; }
    public T? Value { get; }
    public IReadOnlyList<string> Errors { get; }

    private Result(bool isSuccess, T? value, IReadOnlyList<string>? errors)
    {
        IsSuccess = isSuccess;
        Value = value;
        Errors = errors ?? Array.Empty<string>();
    }

    public static Result<T> Success(T value) =>
        new(true, value, null);

    public static Result<T> Failure(params string[] errors) =>
        new(false, default, errors);

    public static Result<T> Failure(IEnumerable<string> errors) =>
        new(false, default, errors.ToList());

    public TResult Match<TResult>(
        Func<T, TResult> success,
        Func<IReadOnlyList<string>, TResult> failure) =>
        IsSuccess ? success(Value!) : failure(Errors);
}
```

### Repository Pattern with EF Core

```csharp
// Generic repository interface
public interface IRepository<T> where T : class
{
    Task<T?> GetByIdAsync(Guid id, CancellationToken ct = default);
    Task<IReadOnlyList<T>> GetAllAsync(CancellationToken ct = default);
    Task AddAsync(T entity, CancellationToken ct = default);
    Task UpdateAsync(T entity, CancellationToken ct = default);
    Task DeleteAsync(T entity, CancellationToken ct = default);
}

// EF Core implementation
public class EfRepository<T> : IRepository<T> where T : class
{
    protected readonly AppDbContext Context;
    protected readonly DbSet<T> DbSet;

    public EfRepository(AppDbContext context)
    {
        Context = context;
        DbSet = context.Set<T>();
    }

    public virtual async Task<T?> GetByIdAsync(Guid id, CancellationToken ct = default)
    {
        return await DbSet.FindAsync(new object[] { id }, ct);
    }

    public virtual async Task<IReadOnlyList<T>> GetAllAsync(CancellationToken ct = default)
    {
        return await DbSet.AsNoTracking().ToListAsync(ct);
    }

    public virtual async Task AddAsync(T entity, CancellationToken ct = default)
    {
        await DbSet.AddAsync(entity, ct);
        await Context.SaveChangesAsync(ct);
    }

    public virtual async Task UpdateAsync(T entity, CancellationToken ct = default)
    {
        DbSet.Update(entity);
        await Context.SaveChangesAsync(ct);
    }

    public virtual async Task DeleteAsync(T entity, CancellationToken ct = default)
    {
        DbSet.Remove(entity);
        await Context.SaveChangesAsync(ct);
    }
}
```

### Unit of Work Pattern

```csharp
public interface IUnitOfWork : IDisposable
{
    IFormRepository Forms { get; }
    IEntryRepository Entries { get; }
    IOrganizationRepository Organizations { get; }

    Task<int> SaveChangesAsync(CancellationToken ct = default);
    Task BeginTransactionAsync(CancellationToken ct = default);
    Task CommitTransactionAsync(CancellationToken ct = default);
    Task RollbackTransactionAsync(CancellationToken ct = default);
}

public class UnitOfWork : IUnitOfWork
{
    private readonly AppDbContext _context;
    private IDbContextTransaction? _transaction;

    public IFormRepository Forms { get; }
    public IEntryRepository Entries { get; }
    public IOrganizationRepository Organizations { get; }

    public UnitOfWork(
        AppDbContext context,
        IFormRepository forms,
        IEntryRepository entries,
        IOrganizationRepository organizations)
    {
        _context = context;
        Forms = forms;
        Entries = entries;
        Organizations = organizations;
    }

    public async Task<int> SaveChangesAsync(CancellationToken ct = default)
    {
        return await _context.SaveChangesAsync(ct);
    }

    public async Task BeginTransactionAsync(CancellationToken ct = default)
    {
        _transaction = await _context.Database.BeginTransactionAsync(ct);
    }

    public async Task CommitTransactionAsync(CancellationToken ct = default)
    {
        if (_transaction is null) return;

        await _context.SaveChangesAsync(ct);
        await _transaction.CommitAsync(ct);
        await _transaction.DisposeAsync();
        _transaction = null;
    }

    public async Task RollbackTransactionAsync(CancellationToken ct = default)
    {
        if (_transaction is null) return;

        await _transaction.RollbackAsync(ct);
        await _transaction.DisposeAsync();
        _transaction = null;
    }

    public void Dispose()
    {
        _transaction?.Dispose();
        _context.Dispose();
    }
}
```

### Event-Driven Patterns

```csharp
// Domain events
public interface IDomainEvent
{
    Guid Id { get; }
    DateTime OccurredAt { get; }
}

public record FormCreatedEvent(Guid FormId) : IDomainEvent
{
    public Guid Id { get; } = Guid.NewGuid();
    public DateTime OccurredAt { get; } = DateTime.UtcNow;
}

public record EntrySubmittedEvent(Guid EntryId, Guid FormId) : IDomainEvent
{
    public Guid Id { get; } = Guid.NewGuid();
    public DateTime OccurredAt { get; } = DateTime.UtcNow;
}

// Event publisher
public interface IEventPublisher
{
    Task PublishAsync<TEvent>(TEvent @event, CancellationToken ct = default)
        where TEvent : IDomainEvent;
}

// Event handler
public interface IEventHandler<TEvent> where TEvent : IDomainEvent
{
    Task HandleAsync(TEvent @event, CancellationToken ct = default);
}
```

### Queue Processing (Cognito.QueueJob / Cognito.QueueService)

```csharp
// Queue message
public record ProcessEntryMessage
{
    public Guid EntryId { get; init; }
    public Guid FormId { get; init; }
    public string Action { get; init; } = string.Empty;
}

// Queue handler
public class EntryProcessingHandler : IQueueMessageHandler<ProcessEntryMessage>
{
    private readonly IEntryService _entryService;
    private readonly ILogger<EntryProcessingHandler> _logger;

    public EntryProcessingHandler(
        IEntryService entryService,
        ILogger<EntryProcessingHandler> logger)
    {
        _entryService = entryService;
        _logger = logger;
    }

    public async Task HandleAsync(
        ProcessEntryMessage message,
        CancellationToken ct = default)
    {
        _logger.LogInformation(
            "Processing entry {EntryId} for form {FormId}",
            message.EntryId, message.FormId);

        try
        {
            await _entryService.ProcessAsync(message.EntryId, ct);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex,
                "Failed to process entry {EntryId}", message.EntryId);
            throw; // Let queue handle retry
        }
    }
}
```

## Testing Patterns

### Unit Test Structure (xUnit + AAA Pattern)

```csharp
public class FormServiceTests
{
    private readonly Mock<IFormRepository> _formRepositoryMock;
    private readonly Mock<IFormValidationService> _validationServiceMock;
    private readonly Mock<IEventPublisher> _eventPublisherMock;
    private readonly FormService _sut;

    public FormServiceTests()
    {
        _formRepositoryMock = new Mock<IFormRepository>();
        _validationServiceMock = new Mock<IFormValidationService>();
        _eventPublisherMock = new Mock<IEventPublisher>();

        _sut = new FormService(
            _formRepositoryMock.Object,
            _validationServiceMock.Object,
            _eventPublisherMock.Object);
    }

    [Fact]
    public async Task CreateFormAsync_WithValidCommand_ReturnsSuccess()
    {
        // Arrange
        var command = new CreateFormCommand("Test Form", Guid.NewGuid());
        _validationServiceMock
            .Setup(x => x.ValidateAsync(It.IsAny<CreateFormCommand>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(ValidationResult.Success);

        // Act
        var result = await _sut.CreateFormAsync(command);

        // Assert
        Assert.True(result.IsSuccess);
        Assert.NotNull(result.Value);
        Assert.Equal("Test Form", result.Value.Name);

        _formRepositoryMock.Verify(
            x => x.SaveAsync(It.IsAny<Form>(), It.IsAny<CancellationToken>()),
            Times.Once);

        _eventPublisherMock.Verify(
            x => x.PublishAsync(It.IsAny<FormCreatedEvent>(), It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task CreateFormAsync_WithInvalidCommand_ReturnsFailure()
    {
        // Arrange
        var command = new CreateFormCommand("", Guid.NewGuid()); // Invalid - empty name
        _validationServiceMock
            .Setup(x => x.ValidateAsync(It.IsAny<CreateFormCommand>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(ValidationResult.Failure("Name is required"));

        // Act
        var result = await _sut.CreateFormAsync(command);

        // Assert
        Assert.False(result.IsSuccess);
        Assert.Contains("Name is required", result.Errors);

        _formRepositoryMock.Verify(
            x => x.SaveAsync(It.IsAny<Form>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }
}
```

### Integration Test Pattern

```csharp
public class FormsControllerIntegrationTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client;
    private readonly WebApplicationFactory<Program> _factory;

    public FormsControllerIntegrationTests(WebApplicationFactory<Program> factory)
    {
        _factory = factory.WithWebHostBuilder(builder =>
        {
            builder.ConfigureServices(services =>
            {
                // Replace real DB with in-memory
                services.RemoveAll<DbContextOptions<AppDbContext>>();
                services.AddDbContext<AppDbContext>(options =>
                    options.UseInMemoryDatabase("TestDb"));
            });
        });

        _client = _factory.CreateClient();
    }

    [Fact]
    public async Task CreateForm_WithValidData_Returns201()
    {
        // Arrange
        var request = new CreateFormRequest { Name = "Integration Test Form" };
        var content = new StringContent(
            JsonSerializer.Serialize(request),
            Encoding.UTF8,
            "application/json");

        // Act
        var response = await _client.PostAsync("/api/forms", content);

        // Assert
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var responseBody = await response.Content.ReadAsStringAsync();
        var form = JsonSerializer.Deserialize<FormDto>(responseBody);
        Assert.NotNull(form);
        Assert.Equal("Integration Test Form", form.Name);
    }
}
```

## Dependency Injection Setup

```csharp
// Program.cs or Startup.cs
public static class ServiceCollectionExtensions
{
    public static IServiceCollection AddCognitoServices(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        // Database
        services.AddDbContext<AppDbContext>(options =>
            options.UseSqlServer(
                configuration.GetConnectionString("DefaultConnection"),
                sqlOptions => sqlOptions.EnableRetryOnFailure()));

        // Repositories
        services.AddScoped<IFormRepository, FormRepository>();
        services.AddScoped<IEntryRepository, EntryRepository>();
        services.AddScoped<IOrganizationRepository, OrganizationRepository>();

        // Unit of Work
        services.AddScoped<IUnitOfWork, UnitOfWork>();

        // Services
        services.AddScoped<IFormService, FormService>();
        services.AddScoped<IEntryService, EntryService>();
        services.AddScoped<IFormValidationService, FormValidationService>();

        // Event handling
        services.AddScoped<IEventPublisher, EventPublisher>();

        return services;
    }
}
```

## Azure Integration Patterns

### Azure Blob Storage

```csharp
public class AzureBlobStorageService : IFileStorageService
{
    private readonly BlobServiceClient _blobServiceClient;
    private readonly string _containerName;

    public AzureBlobStorageService(
        BlobServiceClient blobServiceClient,
        IOptions<StorageOptions> options)
    {
        _blobServiceClient = blobServiceClient;
        _containerName = options.Value.ContainerName;
    }

    public async Task<string> UploadAsync(
        Stream stream,
        string fileName,
        string contentType,
        CancellationToken ct = default)
    {
        var container = _blobServiceClient.GetBlobContainerClient(_containerName);
        await container.CreateIfNotExistsAsync(cancellationToken: ct);

        var blobName = $"{Guid.NewGuid()}/{fileName}";
        var blobClient = container.GetBlobClient(blobName);

        await blobClient.UploadAsync(
            stream,
            new BlobHttpHeaders { ContentType = contentType },
            cancellationToken: ct);

        return blobClient.Uri.ToString();
    }
}
```

### Azure Service Bus Queue

```csharp
public class AzureServiceBusQueueService : IQueueService
{
    private readonly ServiceBusClient _client;
    private readonly string _queueName;

    public AzureServiceBusQueueService(
        ServiceBusClient client,
        IOptions<ServiceBusOptions> options)
    {
        _client = client;
        _queueName = options.Value.QueueName;
    }

    public async Task SendAsync<T>(T message, CancellationToken ct = default)
    {
        await using var sender = _client.CreateSender(_queueName);

        var serviceBusMessage = new ServiceBusMessage(
            JsonSerializer.SerializeToUtf8Bytes(message))
        {
            ContentType = "application/json"
        };

        await sender.SendMessageAsync(serviceBusMessage, ct);
    }
}
```
