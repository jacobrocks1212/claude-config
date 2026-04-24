# Cognito Forms Coding Standards

## C# Coding Standards

### Naming Conventions

**Classes and Methods:**
```csharp
public class FormSubmissionService  // PascalCase
{
    public SubmissionResult SubmitEntry(FormEntry entry)  // PascalCase
    {
        // Implementation
    }

    private void ProcessInternalLogic()  // PascalCase for private methods too
    {
        // Implementation
    }
}
```

**Parameters and Local Variables:**
```csharp
public void ProcessForm(Form formData, string userId)  // camelCase
{
    int entryCount = 0;  // camelCase
    var submissionResult = new SubmissionResult();  // camelCase
}
```

**Constants:**
```csharp
public const int LINKED_LOOKUP_LIMIT = 100;  // UPPER_CASE
private const string DEFAULT_TEMPLATE_ID = "template-001";  // UPPER_CASE
```

**Private Fields:**
```csharp
private readonly StorageContext _storageContext;  // _camelCase with underscore prefix
private int _retryCount;
```

### Code Organization

**File Structure:**
1. Using statements
2. Namespace declaration
3. Class declaration
4. Public constants
5. Private fields
6. Constructor(s)
7. Public methods
8. Private methods

**Method Length:**
- Keep methods focused and under 50 lines when possible
- Extract complex logic into private helper methods
- Use descriptive method names that indicate purpose

### Comments and Documentation

**XML Documentation:**
```csharp
/// <summary>
/// Submits a form entry and processes all related actions
/// </summary>
/// <param name="formEntry">The entry to submit</param>
/// <param name="userId">ID of the user submitting</param>
/// <returns>Result indicating success or failure with details</returns>
public SubmissionResult SubmitEntry(FormEntry formEntry, string userId)
{
    // Implementation
}
```

**Inline Comments:**
- Focus on "why" not "what"
- Explain business logic and decisions
- Document non-obvious behaviors
- Avoid stating the obvious

```csharp
// Good: Explains WHY
// Process linked lookups synchronously to ensure referential integrity
// before auto-create entries run
LinkedLookupService.SyncLinkedLookups(form, formEntry, syncContext);

// Bad: States the OBVIOUS
// Call the SyncLinkedLookups method
LinkedLookupService.SyncLinkedLookups(form, formEntry, syncContext);
```

### Error Handling

**Use Result Objects:**
```csharp
// Good
public SubmissionResult ValidateEntry(FormEntry entry)
{
    if (entry == null)
        return new SubmissionResult
        {
            Status = SubmissionResultStatus.ValidationError,
            ErrorMessage = "Entry cannot be null"
        };

    return new SubmissionResult { Status = SubmissionResultStatus.Success };
}

// Avoid throwing for expected errors
public void ValidateEntry(FormEntry entry)
{
    if (entry == null)
        throw new ArgumentNullException(nameof(entry));  // Only for unexpected conditions
}
```

**Exception Handling:**
```csharp
try
{
    // Operation that might fail
    ProcessPayment(entry);
}
catch (PaymentException ex)
{
    // Log with context
    _logger.LogError(ex, "Payment processing failed for entry {EntryId}", entry.Id);

    // Return user-friendly error
    return new SubmissionResult
    {
        Status = SubmissionResultStatus.PaymentFailed,
        ErrorMessage = "Payment could not be processed. Please try again."
    };
}
```

### Async/Await Patterns

**Async Methods:**
```csharp
// Proper async signature
public async Task<SubmissionResult> SubmitEntryAsync(FormEntry entry)
{
    await SomeAsyncOperation();
    return result;
}

// Don't block on async
// Bad
var result = SomeAsyncMethod().Result;  // Avoid

// Good
var result = await SomeAsyncMethod();
```

**Synchronous When Appropriate:**
- Use synchronous methods when no I/O is involved
- Don't add async just for the sake of it
- Clearly distinguish sync vs async in method names if both exist

## TypeScript/Vue.js Standards

### Naming Conventions

**Components:**
```typescript
// PascalCase for component names
export default defineComponent({
    name: 'FormSubmissionPanel',
    // ...
});
```

**Variables and Functions:**
```typescript
// camelCase
const entryCount = ref(0);
const userId = computed(() => props.user?.id);

function processFormData() {
    // Implementation
}
```

**Constants:**
```typescript
// UPPER_CASE
const MAX_ENTRIES = 100;
const DEFAULT_TIMEOUT = 5000;
```

### Component Organization

**Script Setup Order:**
1. Imports
2. Props
3. Emits
4. Composables/Hooks
5. Reactive state
6. Computed properties
7. Methods
8. Lifecycle hooks

### Type Safety

**Use Types:**
```typescript
// Good
interface FormEntry {
    id: string;
    formId: string;
    data: Record<string, unknown>;
}

function submitEntry(entry: FormEntry): Promise<SubmissionResult> {
    // Implementation
}

// Avoid 'any'
function processData(data: any) {  // Bad
    // ...
}
```

## General Best Practices

### SOLID Principles

**Single Responsibility:**
- Each class should have one reason to change
- Services should focus on a specific domain

**Open/Closed:**
- Open for extension, closed for modification
- Use interfaces and inheritance appropriately

**Dependency Inversion:**
- Depend on abstractions, not concretions
- Inject dependencies rather than creating them

### DRY (Don't Repeat Yourself)

- Extract repeated logic into helper methods
- Use shared utilities for common operations
- Create reusable components in frontend

### Performance Considerations

**Database Operations:**
- Minimize round trips
- Use appropriate caching
- Bypass cache when fetching for updates
- Batch operations when possible

**Frontend Performance:**
- Lazy load components where appropriate
- Use computed properties for derived state
- Avoid unnecessary re-renders

### Security

**Input Validation:**
- Validate at API boundaries
- Sanitize user input
- Use parameterized queries

**Authentication/Authorization:**
- Check permissions before operations
- Don't expose sensitive data in errors
- Log security-relevant events

## Code Review Checklist

Before submitting code:
- [ ] Follows naming conventions
- [ ] Has appropriate comments
- [ ] Handles errors properly
- [ ] Includes unit tests
- [ ] No commented-out code
- [ ] No debug logging left in
- [ ] Feature flags used appropriately
- [ ] No hardcoded values that should be configurable
- [ ] Async/await used correctly
- [ ] Database operations optimized
