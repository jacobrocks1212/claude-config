# Code Review Rules
> Generalized from PR feedback (50+ PRs reviewed by Cognito senior engineers)

---

## C# Architecture & Patterns

### Prefer Abstract Classes Over Lambda-Based Patterns
When implementing provider/strategy patterns with multiple implementations, use abstract classes with sealed private implementations rather than lambda-based patterns.

```csharp
// Preferred
public abstract class StripeEventContext
{
    public abstract string ProviderName { get; }
    public abstract string GetApiKey(PaymentAccount account, bool isLiveMode);

    public static readonly StripeEventContext Stripe = new StripeContext();
    public static readonly StripeEventContext CognitoPay = new CognitoPayContext();

    private sealed class StripeContext : StripeEventContext { /* ... */ }
    private sealed class CognitoPayContext : StripeEventContext { /* ... */ }
}

// Avoid
public class ProviderContext
{
    public Func<PaymentAccount, bool, string> GetApiKey { get; set; }
}
```

### Use Specific, Descriptive Class Names
Class names should indicate their purpose and scope. Avoid vague names like `ProviderContext` when something more specific like `StripeEventContext` or `PaymentProviderContext` is appropriate.

### Co-locate Interfaces With Implementations
Place interfaces in the same file as their primary implementation when there's a 1:1 relationship.

```csharp
// Single file: CognitoPayService.cs
public interface ICognitoPayService
{
    Task<PaymentAccount> CreateAccountAsync(string email);
}

public class CognitoPayService : ICognitoPayService
{
    // Implementation
}
```

### Avoid Default Values for DI Constructor Parameters
Never use default values for service constructor parameters. Register all dependencies in the DI container instead.

```csharp
// Correct
public CognitoPayService(
    IFeatureFlagService featureFlagService,
    IStripeServiceFactory stripeServiceFactory) { }

// Avoid
public CognitoPayService(
    IFeatureFlagService featureFlagService,
    IStripeServiceFactory stripeServiceFactory = null) { }
```

### Don't Inject Dependencies You Don't Use
If a class can accomplish its work using base class properties or simpler patterns, don't inject unnecessary services. Prefer using existing infrastructure (e.g., `Organization.GetStorageContext()` from `ServiceController`) over injecting `Module<IFormsService>` just to access storage.

```csharp
// Preferred - uses base class infrastructure directly
public class EntryRowsController : ServiceController
{
    // No constructor needed - uses Organization.GetStorageContext() from base
    public Task<ActionResult> GetEntryRows(string ids)
    {
        var storageContext = Organization.GetStorageContext();
        var index = storageContext.Get<CompositeEntryIndex>(entryId);
        // ...
    }
}

// Avoid - injecting unused dependencies
public class EntryRowsController : ServiceController
{
    readonly Module<IFormsService> formsModule;  // Never used!

    public EntryRowsController(Module<IFormsService> formsModule)
    {
        this.formsModule = formsModule;
    }
}
```

### Avoid Obsolete StorageContext.Query — Use GetAll/GetRange/Get Instead
`StorageContext.Query<T>()` is obsolete. Use `Get<T>(id)` for ID lookups, `GetRange<T>(prefix)` for prefix-based scans, or `GetAll<T>()` for full scans. Both `GetAll` and `GetRange` return `IAsyncEnumerable<T>` — iterate with `await foreach` and `.ConfigureAwait(false)`.

### Follow Modern DI Patterns
Avoid obsolete patterns like `ModuleFactory` and implicit dereferencing. Use constructor injection with properly registered dependencies.

### Reserve .Model Namespace for Entities Only
The `.Model` namespace should only contain actual entities, not DTOs, filter criteria, or other classes.

```csharp
// Avoid
namespace Cognito.Core.Model.Payment
{
    public class PaymentFilterCriteria { }  // Not an entity!
}

// Preferred
namespace Cognito.Core.CognitoPay
{
    public class PaymentFilterCriteria { }
}
```

### Group Related Classes in Domain-Specific Directories
Group filter criteria, paged results, and repositories together in domain-specific directories.

```
// Preferred structure
Cognito.Core/
  CognitoPay/
    PaymentFilterCriteria.cs
    PagedPaymentResult.cs
    PaymentRepository.cs
```

### Use Versioned Naming for New API Patterns
When creating new API patterns that differ from legacy, use versioned naming (v2) to disambiguate.

```csharp
// Avoid - vague naming
public class NewFormController { }

// Preferred - versioned naming
[Route("svc/form/v2")]
public class V2FormController { }
```

### Cache Service Instances in Controllers
Don't create new service instances on every request. Cache them as fields.

```csharp
// Avoid
public async Task<ActionResult> GetData()
{
    var service = new MyService();  // Created every request!
    return Ok(await service.GetDataAsync());
}

// Preferred
private MyService _service;
private MyService Service => _service ??= new MyService();
```

### Don't Expose Methods Publicly Just for Tests
If a method is only called from tests, don't make it public. Consider test-specific alternatives or internal access.

### Don't Add Test-Only Parameters to Service Methods
Avoid polluting service methods with parameters only used by tests. Work around in the test instead.

```csharp
// Avoid - test-only param
public Form GetFormByInternalName(string name, bool bypassCache = false) { }

// Preferred - handle in test
var formId = formsService.GetFormByInternalName(formInternalName).Id;
var form = StorageContext.Get<Form>(formId, bypassCache: true);
```

### Understand StorageContext Cache Behavior
`StorageContext.Get<T>()` caches by default. Use `bypassCache: true` when you need fresh data.

```csharp
// This returns cached data
var form = StorageContext.Get<Form>(id);

// This reloads from storage
var form = StorageContext.Get<Form>(id, bypassCache: true);
```

### Watch for Break Statements Hiding Subsequent Logic
Break statements in switch cases can accidentally skip logic that should run.

> "Seems like this could be missing stuff below due to the `break` statement?"

### Use Lazy Evaluation for Memory-Intensive Operations
Don't eagerly materialize collections when lazy evaluation works. Return `IEnumerable` instead of `List` for large datasets.

```csharp
// Avoid - loads all pages into memory
public List<Image> GetPageImages(Document doc)
{
    return doc.Pages.Select(p => p.RenderImage()).ToList();
}

// Preferred - one page at a time
public IEnumerable<Image> GetPageImages(Document doc)
{
    foreach (var page in doc.Pages)
        yield return page.RenderImage();
}
```

### Use Instance's Actual Type for Unregistration
When unregistering objects from pools/caches, use the instance's actual type to handle inheritance correctly.

```csharp
// Avoid - using passed type
public void Unregister(Type modelType, object instance) {
    pool[modelType].Remove(instance);  // Wrong if instance is a subtype!
}

// Preferred - using instance's actual type
public void Unregister(object instance) {
    pool[instance.GetType()].Remove(instance);
}
```

### Don't Delete Pool Entries When Objects Might Still Be Referenced
When objects can be referenced by old IDs, don't delete the pool entry - something may still hold a reference.

### Always Pair Subscribe/Unsubscribe for Event Handlers
When subscribing to events, always implement corresponding unsubscribe logic to prevent memory leaks.

```csharp
// Ensure both exist
path.SubscribePathChange(...);
// Later...
path.UnsubscribePathChange(...);  // Don't forget!
```

### Be Careful with Event Subscriptions on Cached/Reused Types
Event subscriptions on cached or reused types can cause memory leaks and data isolation issues.

---

## API Design

### Use Appropriate HTTP Methods
- `GET` for retrieving resources
- `POST` for creating resources or triggering actions
- Use singular nouns for single-resource endpoints (`/session` not `/sessions`)

### Use ProducesResponseType for Auto-Generated Types
Decorate controller actions with `[ProducesResponseType]` to enable auto-generated TypeScript types for the client.

```csharp
[HttpPost]
[Route("{id}/session")]
[ProducesResponseType(typeof(CreateSessionResponse), (int)HttpStatusCode.OK)]
public async Task<ActionResult> CreateSession(string id) { }
```

### Split Large Controllers by Domain
Break up controllers that handle multiple concerns to:
- Reduce merge conflicts between teams
- Improve maintainability
- Follow single responsibility principle

```
// Instead of one giant CognitoPayController:
CognitoPayAccountController.cs   // Account management
CognitoPayWebhookController.cs   // Webhook handling
```

### Use Async Suffix for Async Methods
All async methods should have the `Async` suffix.

```csharp
// Avoid
public async Task<File> UploadFile(Stream stream) { }

// Preferred
public async Task<File> UploadFileAsync(Stream stream) { }
```

### Add Defensive Null Checks Even When Types Suggest Non-Null
Add null guards even when the type specifies non-null - callers may not respect the contract.

```csharp
// Preferred - defensive
public async Task UploadAsync(FileInfo file)
{
    if (file?.Size == null) return;  // Guard against bad callers
    // ...
}
```

### Track TODOs as Engineering Bugs
Don't leave TODO comments in code. Track them as engineering bugs instead.

```csharp
// Avoid
// TODO: implement retry logic

// Preferred - create a bug/task and reference it
// See bug #12345 for retry logic implementation
```

### Don't Leave Commented-Out Code
Remove commented-out code. Use version control to recover old code if needed.

---

## Code Consistency

### Extract Magic Strings to Constants
Don't use magic strings - extract them to constants and reuse across related code.

```csharp
// Avoid
if (type == "Form") { }

// Preferred
public const string FormType = "Form";
if (type == FormType) { }
```

### Use Helper Methods Consistently
When a helper method exists (e.g., `GetRequestOptions`), use it consistently throughout the file rather than inline implementations in some places.

### Ensure Idempotency Keys Are Unique Per Request
When reusing request options objects, ensure idempotency keys are unique for each API call to avoid unintended behavior.

```csharp
// Each request gets its own idempotency key
var options = GetRequestOptions(account, token, Guid.NewGuid().ToString());
```

### Maintain Consistent Indentation
Don't mix spaces and tabs within a file. Follow the project's established convention.

### Keep Comments Accurate Through Iterations
When a function's scope or behavior changes during development, update its documentation to match. Don't leave stale comments from earlier iterations (e.g., "for new fields" on a function that now handles all fields).

### Match Edge Case Handling Between Client and Server
When implementing equivalent logic on client and server, ensure edge cases (empty strings, nulls, boundary values) are handled identically. Test both paths with the same inputs.

### Don't Load Data You'll Discard
When you can determine the final shape of a result early (e.g., only the first element is needed), truncate before expensive operations like network requests or DB queries, not after.

### Use the Most Specific API Available
Prefer specific methods over generic alternatives with casts. Before suggesting a "more specific" API, verify that it actually accepts the type you're passing and returns the type you need (e.g., `GetList()` only works with `ModelReferenceProperty`, not `ModelValueProperty`).

---

## Frontend (Vue/TypeScript)

### Don't Add Redundant Props
If data is already available through injection or context (e.g., session), don't create additional props that duplicate that data.

### Verify Props Exist Before Use
Don't reference props in templates that aren't defined in the component. Use data from the correct source.

### Use PropType for Function Props
When defining function props, use `PropType` for proper TypeScript typing.

```typescript
// Avoid - TS complains about Function type
props: {
  openExpressionBuilder: Function
}

// Preferred
import { PropType } from 'vue';
props: {
  openExpressionBuilder: {
    type: Function as PropType<(field: Field) => void>
  }
}
```

### Use toRef for Passing Reactive Props to Composables
When passing props to composables, use `toRef` so the composable receives a ref instead of a function.

```typescript
// Avoid
const result = useMyComposable(() => props.value);

// Preferred
import { toRef } from 'vue';
const result = useMyComposable(toRef(props, 'value'));
```

### Call Composables Synchronously — Never From Async Callbacks
Composables (`useXyz` functions) must be called synchronously in the component setup function or composable body. Never call them from inside async callbacks, `.then()` handlers, or event handlers — they may hook into the current component lifecycle, which is only available during synchronous setup. Store the result at the top level and reference it from callbacks.

```typescript
// Avoid — composable called inside async callback
export function useMyFeature() {
  const handleAction = async () => {
    await someAsyncWork();
    const state = useSomeState();
    state.onComplete?.();
  };
}

// Preferred — composable called synchronously
export function useMyFeature() {
  const state = useSomeState();
  const handleAction = async () => {
    await someAsyncWork();
    state.onComplete?.();
  };
}
```

### Watch All Relevant Props Consistently
When watching props in one component, ensure similar components watch the same props for consistency.

### Prefer Readable Positive Conditions Over Complex Negatives
Complex negative conditions are hard to follow. Use positive conditions or break into if statements.

```javascript
// Avoid - hard to follow
if (type != 'A' && type != 'B' && !(flag && type != 'C')) { }

// Preferred - explicit positive conditions
if (type === 'D' || type === 'E') { }

// Or use if statements for complex logic
if (type === 'A') return false;
if (type === 'B') return false;
// ...
```

---

## Dependencies

### Prefer Latest Stable Package Versions
Use the latest stable version of packages unless there's a documented reason not to. When using older versions, add a comment explaining why.

---

## Data Modeling

### Prefer Strongly Typed Properties Over JSON Strings
Question serialization choices. When possible, use strongly typed properties rather than storing data as JSON strings, which loses type safety and makes querying difficult.

---

## Security

### Sanitize All Imported HTML Content Server-Side
Any HTML content imported from external sources must go through the HTML sanitation filter server-side.

```csharp
// Always sanitize imported HTML
var sanitizedHtml = HtmlSanitizer.Sanitize(importedHtml);
```

---

## Patterns & Architecture

### Default to Established Patterns
When the codebase has an established pattern for a concern (e.g., `PropertyConverter` for serialization, `EntityPropertyConverter` for deserialization), default to using it. If a technical constraint prevents using the pattern, document the constraint clearly in a code comment or PR description.

### Avoid Unnecessary Wrapper Properties
Don't create wrapper properties, computed values, or indirection when direct property access works. Question whether additional layers are necessary—if a property is already reactive/tracked, binding to it directly is cleaner than wrapping it.

```javascript
// Avoid - unnecessary indirection
field.meta.addProperty({ name: "selectionTypeDisplayValue", type: String }).calculated({
    calculate: function () { return this.get_selectionType(); },
    onChangeOf: ["selectionType"]
});
// Template: {binding selectionTypeDisplayValue}

// Preferred - direct access
// Template: {binding selectionType}
```

---

## Dialog & Modal UI

### Handle All Dialog Dismissal Paths Consistently
When implementing cancel/revert behavior for dialogs, ensure all dismissal paths trigger the same logic:
- Cancel button
- X (close) button
- Escape key
- Overlay/backdrop click

Use the dialog's `cancel` callback (or equivalent) rather than button click handlers to ensure consistent behavior across all dismissal methods.

```javascript
// Preferred - cancel callback handles all dismissal paths
$.fn.dialog({
    cancel: function () {
        revertChanges();
    },
    buttons: [
        { label: "Cancel", isCancel: true },
        { label: "Confirm", autoClose: true }
    ]
});

// Avoid - only handles Cancel button click
$.fn.dialog({
    buttons: [
        {
            label: "Cancel",
            isCancel: true,
            click: function () { revertChanges(); }  // X button bypasses this!
        }
    ]
});
```

---

## Testing

### Verify Test Assertions Match Expected Behavior
Double-check that assertions actually test what they claim to test.

> "Is this assert right?"

### Keep Test Assertions Consistent
Don't mix `Throws` and `ThrowsExactly` without reason. Be consistent in assertion style.

### Question Parse Assumptions in Tests
If code assumes parsing will succeed, question whether that's always true.

> "I take it the assumption is that this _should_ successfully parse?"

### Assert.IsTrue Should Have a Message
Always provide a message to improve clarity in test results on failure.

```csharp
// Avoid
Assert.IsTrue(result.IsValid);

// Preferred
Assert.IsTrue(result.IsValid, "Expected result to be valid");
```

### Outer Class Shouldn't Be TestClass When Using Nested Classes
If using nested test classes, the outer class shouldn't have `[TestClass]` or tests will be duplicated.

### Address Root Cause, Not Just Symptoms
When fixing issues, fix the underlying problem rather than adding workarounds.

> "The above seems like a deeper problem that should be fixed, in addition to/in lieu of this change."

### Validate AI-Generated Content
AI-generated expressions, code, or content needs validation before use.

> "Should we do anything to check if the expressions are actually valid?"

---

## Pull Request Quality

### Document Root Cause, Not Just the Fix
When fixing bugs, explain what the actual issue was—not just what you changed. This helps reviewers understand whether the fix is correct and complete, and creates institutional knowledge for similar issues.

```markdown
// Avoid
"Changed binding from selectionTypeDisplayValue to selectionType"

// Preferred
"The binding wasn't updating because it referenced a non-reactive property.
Changed to bind directly to selectionType which is already ExoWeb-tracked."
```

---

## Code Organization

### Extract Large Code Additions Into Separate Modules
When adding significant amounts of code, consider pulling it into a separate file for organization. This applies especially to build.js additions.

> "There is a good bit of code being added here. What do you think about pulling it out into a separate module, if for no other reason than just organization?"

### Place Runtime Classes in Appropriate Folders
Classes used only at runtime by a service should live in the service folder, not in `Model/`. For example, `InitialSyncConfiguration` used by the sync process belongs in `Services/LinkedLookups`, not `Model`.

---

## Performance Optimization

### Validate Size Limits Before Allocating Memory
When accepting file uploads or large data, enforce size limits before reading into memory.

```csharp
// Avoid - reads entire file before checking size
var content = await stream.ReadAllBytesAsync();
if (content.Length > MaxSize) throw new Exception("Too large");

// Preferred - check size first
if (stream.Length > MaxSize) throw new Exception("Too large");
var content = await stream.ReadAllBytesAsync();
```

### Reuse HttpClient Instances
Don't create new HttpClient per request - it causes socket exhaustion. Use a shared instance.

```csharp
// Avoid
public async Task<string> FetchDataAsync(string url)
{
    using var client = new HttpClient();  // Socket exhaustion!
    return await client.GetStringAsync(url);
}

// Preferred - use shared client
public async Task<string> FetchDataAsync(string url)
{
    return await WebApplication.HttpClient.GetStringAsync(url);
}
```

### Use FastHasFlag for Flag Checks
When checking enum flags, use `behavior.FastHasFlag` instead of `HasFlag` for better performance.

```csharp
// Preferred
if (behavior.FastHasFlag(FieldBehavior.Required)) { }

// Avoid
if (behavior.HasFlag(FieldBehavior.Required)) { }
```

### Check Conditions After Await, Not Before
For race condition safety, check conditions after the await completes, not before.

```typescript
// Avoid - race condition
if (!isLoading) {
  await loadData();  // Another call could start here
}

// Preferred - check after await
await loadData();
if (isLoading) return;  // Check state after async operation
```

### Move Loop Invariants Outside the Loop
Don't compute the same value repeatedly inside a loop if it doesn't change.

```csharp
// Avoid
foreach (var item in items)
{
    var config = GetConfiguration();  // Same result every iteration!
    Process(item, config);
}

// Preferred
var config = GetConfiguration();
foreach (var item in items)
{
    Process(item, config);
}
```

### Resolve Lists as Late as Possible
When a list will be filtered or limited, delay resolution until after filtering to avoid loading data you'll discard.

> "Resolving the list should be done as late as possible, since it will load all the selected source entries."

### Avoid Unnecessary String Allocations
Use alternatives to methods like `string.Split` that allocate arrays.

```csharp
// Consider alternatives like:
entry.Form.Id  // Instead of parsing from a composite string
```

---

## Struct vs Class Decisions

### Use Struct for Value Types That Get Copied
If an object is just a bag of values that gets copied into another object, consider making it a struct.

```csharp
// If values always get copied:
public struct LinkedLookupCardinalityInfo
{
    public int SourceCount { get; set; }
    public int TargetCount { get; set; }
}

// Then copying is cleaner:
features.Update(linkedLookupInfo);  // Convenience method for struct copy
```

---

## Convenience Methods

### Add Null-Check Convenience Methods for Frequently Checked Properties
When a property is null-checked frequently throughout the codebase, add a convenience method.

```csharp
// If this pattern appears often:
if (field.LinkedLookupConfiguration != null) { }

// Add a convenience method:
public bool IsLinked() => LinkedLookupConfiguration != null;

// Then use:
if (field.IsLinked()) { }
```

---

## Async Patterns

### Never Use .Result or .Wait()
Always await async methods. Using `.Result` or `.Wait()` causes deadlocks.

```csharp
// WRONG - causes deadlocks
var result = GetDataAsync().Result;
GetDataAsync().Wait();

// CORRECT - always await
var result = await GetDataAsync();
```

### Always Pass CancellationToken
Enable graceful cancellation by accepting and passing CancellationToken.

```csharp
// Preferred
public async Task<Order?> GetByIdAsync(string id, CancellationToken cancellationToken = default)
{
    return await _context.Orders.FirstOrDefaultAsync(o => o.Id == id, cancellationToken);
}
```

### Use ConfigureAwait(false) in Library Code
In library code (not ASP.NET controllers), use ConfigureAwait(false) to avoid deadlocks.

```csharp
// In library/service code
var response = await _httpClient.GetAsync(url).ConfigureAwait(false);
```

### Don't Use async Keyword When Returning Task.CompletedTask
If a method is async for future-proofing but currently returns immediately, remove the `async` keyword and return `Task.CompletedTask` directly.

```csharp
// Avoid
public async Task ProcessAsync()
{
    // Currently no async work
    DoSomethingSynchronous();
}

// Preferred
public Task ProcessAsync()
{
    DoSomethingSynchronous();
    return Task.CompletedTask;
}
```

---

## Template & Binding Patterns (build.js/build.htm)

### Use Template Convert Instead of Extra Model Properties
Use inline `convert` in bindings instead of creating calculated model properties for simple transformations.

```html
<!-- Avoid - extra model property -->
<input vue:disabled="{binding canChangeSubType}" />
<!-- Where canChangeSubType is a calculated property that just negates another -->

<!-- Preferred - inline convert -->
<input vue:disabled="{ binding canChange, convert={{ canChange => !canChange }} }" />
```

### Omit Default Binding Source
The default binding source is `$dataItem`, so specifying it is unnecessary.

```html
<!-- Avoid - redundant source -->
<element vue:prop="{ binding myProp, source={{ $dataItem }} }" />

<!-- Preferred -->
<element vue:prop="{ binding myProp }" />
```

### Boolean Props Don't Need ='true'
Boolean properties in templates don't need explicit `='true'`.

```html
<!-- Avoid -->
<choice show-choice-images='true' />

<!-- Preferred -->
<choice show-choice-images />
```

---

## Input Validation

### Clamp Values to Expected Ranges
When accepting user input that has a valid range, clamp to that range on the server to handle invalid input gracefully.

```csharp
// For a 0-6 range:
var size = Math.Max(0, Math.Min(6, inputSize));
```

---

## Caching Strategy

### Question Caching for Multi-Context Scenarios
When caching data, consider whether the same item might be accessed in different contexts. For example, the same entry used via two different lookup fields with different sorting requirements.

> "I'm not sure about this caching strategy. Couldn't you have the same entry used via two different lookup fields with different sorting?"

---

## Redundant Code Detection

### Eliminate Redundant Methods That Duplicate Logic
If two methods do essentially the same thing (e.g., `GetField` and `GetFieldPath`), keep only the more general one.

> "`GetField` and `GetFieldPath` are redundant with each other. You only need the latter."

---

## Feature Flags

### Keep Changes Behind Feature Flags
Behavioral changes should be behind feature flags to enable rollback and gradual rollout.

> "It's good to keep things behind a flag to the extent possible."

### Reference Feature Flags for Post-Release Cleanup
When adding code that should be removed after a feature fully releases, reference the feature flag as a cleanup signal.

```csharp
// Reference the flag so this gets cleaned up when the flag is removed
// TODO: Remove when FeatureFlags.MyFeature is fully released
```

---

## Cross-Stack Consistency

### Match Server/Client Type Names
When a type exists on both server and client, use matching names to help discoverability.

```csharp
// Server
public class ExpressionBuilderPropertyMapping { }
```

```typescript
// Client - match the server name
interface ExpressionBuilderPropertyMapping { }  // NOT "PropertyMappingType"
```

---

## TypeScript Patterns

### Avoid `| any` in Union Types
Adding `| any` to a union pollutes the entire type to become `any`.

```typescript
// Avoid - entire type becomes any
type Config = string | number | any;

// Preferred - be specific
type Config = string | number | null;
```

---

## Encapsulation

### Keep Internal State Private
Don't expose internal state that shouldn't be managed externally.

> "It's nice to avoid people thinking they can/should manage this property externally."

---

## Event Handler Cleanup

### Clean Up Event Handlers to Prevent Memory Leaks
Store event handler references and remove them when no longer needed.

```javascript
// Store the handler
const handler = (e) => processEvent(e);
element.addEventListener('change', handler);

// Clean up later
element.removeEventListener('change', handler);
```

---

## Edge Cases

### Handle Deleted Items in Batch Operations
When iterating over items that might have been deleted, handle the case gracefully.

> "The most recent entry could have been deleted. Should we retry, or fall back to a less efficient alternative?"

### Consider Cross-Scope Edge Cases
When copying or moving items between scopes, ensure expressions and references remain valid.

> "Copying a field into a different scope doesn't seem to work right."

---

## Observability

### Log Telemetry When Hitting Limits
When implementing throttling or limits, log telemetry so you can monitor and adjust.

> "Should we log telemetry when this happens so we know we're hitting the limit and can adjust things if needed?"

---

## Configuration

### Start With Sensible Defaults, Not Unlimited
When adding new configuration, start with reasonable limits rather than unlimited.

> "Start without throttling or start with max concurrency 1 (or some reasonable amount, like 5)?"
