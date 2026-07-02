# Cognito.Core — Domain Layer

## Gotchas
- Check project's .csproj for LangVersion before using newer C# syntax
- **Dual-target framework**: Builds `net472` by default, `netstandard2.0` for NETCORE Debug configuration. Use `#if NETCOREAPP` for conditional compilation.
- Service **interfaces** live here; implementations are in `Cognito/` or `Cognito.Services/`
- SDK-style csproj auto-includes files — do NOT add `<Compile>` items manually

## Organization = Tenant Root
Most operations are org-scoped. `Organization` is the partition key for storage and the root of the entity graph.

## Model Hierarchy
```
Model/
  Forms/       Form, FormEntry, FormDefinition, EntryView, EntryIndexSchema,
               FormEntryIndex, CompositeEntryIndex, EntryEmailNotification
  Payment/     PaymentAccount, Order, LineItem, TransactionFee, Payment
  AI/          ChatHistory, Conversation
  Plans/       Metric, SubscriptionStatistics
  Member/      (member profiles)
  Profile/     (user profiles)
```

### Key Entity Patterns
- Custom attributes drive behavior: `[Id()]`, `[FileRef]`, `[EnableRules]`, `[Overwatch()]`, `[FormBasedEntity()]` (defined in `Cognito/` and `Cognito.Amender/`, applied to entities here)
- Reference wrappers: `FormRef`, `FormEntryRef`, `PaymentAccountRef` (generic `Reference<T>`)
- Interfaces: `IEntity`, `IModelEntity` (defined in `Cognito.Amender/`), `IEncryptable`, `IFlushable` (defined in `Cognito/`)
- Revision system for schema evolution — breaking changes must include a revision migration

## Services (Interfaces)
```
Services/
  Forms/       IFormsService, IEntryIndexService, IBulkDownloadService,
               IFormEntryExportService, IFormSessionService
  Forms/AI/    IFormGenerationService, PromptProvider, BaseLLMService
  Payment/     IPaymentService, IStripeServiceFactory, IPaymentServiceProvider
  Plans/       IPlansService
  LinkedLookups/  (complex multi-form lookup sync)
```
- `IFormsService` extends `IModuleService<FormsConfiguration>`
- AI services use Liquid templates from `Services/Forms/AI/Prompts/`

## DI Registration
- `DependencyInjection/CognitoCoreModule.cs` — Autofac `Module`
- Registers `Module<IFormsService>`, `Module<IPaymentService>`, etc. as singletons
- Factory delegates: `CoreServiceFactory(IComponentContext ctx)`
- Conditional registration: GemBox vs Aspose for document merge (feature flag)
- AI/LLM SDK integrations registered here (Azure OpenAI, etc.)
- **Convention-scan determinism gotcha:** `RegisterCoreServices` assembly-scans the `Cognito.Core.Services` namespace `.AsImplementedInterfaces()`. If two types in that namespace implement the *same* interface, a single-instance resolve of that interface is **nondeterministic** (last-registration-wins on scan order, silently). To force a deterministic default, exclude the non-default impl from the scan with `.Except<TOther>()` **and** register the chosen default explicitly after `RegisterCoreServices(builder)`. Precedent: `.Except<CoreService>()`.

## FieldInfoGenerator Token Semantics

`Services/FieldInfoGenerator.cs` generates `FieldInfo` tokens for the frontend field picker and Identify Submitter system.

### Field Properties (server-side)
- **`Id`** — dotted numeric index path. Every container (section, table, lookup) prepends its field `Index` + `"."`. Top-level field at Index 3 gets `Id = "3"`. A field at Index 5 inside a section at Index 2 gets `Id = "2.5"`. The dot indicates container nesting of any kind, NOT specifically person-field nesting.
- **`InternalName`** — the field's own name from `field.InternalName`. Never dotted on the server side.
- **`Path`** — logical dotted path from `GetLogicalPath()` (e.g., `"Section.PersonField"`). Uses InternalName segments.
- **`Scope`** — space-delimited ancestor internal names (e.g., `"OuterSection InnerSection"`). Includes the field's own InternalName if it is a container.
- **`ScopeId`** — dot-delimited ancestor list indexes (for repeating sections/tables).

### Important: `InternalName` is rewritten on the client side
`convertFieldInfosToTokens` in `Cognito.Services/Views/Shared/build.js` overwrites `InternalName` to equal the server's `Path` for non-container fields. See `Cognito.Services/CLAUDE.local.md` for details. Always check whether you are reading server-side or client-side token semantics.

## DataTransfer/
DTOs for external service communication (Stripe/Square/CognitoPay models, Plans billing data). Not domain entities.

## FormsService.cs — MANDATORY Skill Invocation

**BEFORE editing `Services/Forms/FormsService.cs`, you MUST invoke the `/forms-service` skill.**

FormsService.cs is a large god object. The skill provides:
- Method index organized by verb (Get, Create, Update, Delete, Assert, Validate...)
- Region locations (Email Domains, Import, Entry Views, XmlCleanser)
- Nested types (EntryAction, StoreFormResult, etc.)
- Constructor dependencies for test mocking

This prevents duplicate method creation and helps navigate the large file efficiently.

## Infrastructure/
`Plans/` (tax ID config), `Forms/`, `Member/` — helper/utility classes supporting the domain.

---

## Maintaining This Document

Update this file when:
- Adding new architectural patterns or service hierarchies
- Discovering non-obvious gotchas that would trip up future developers
- Renaming or restructuring directories/files mentioned here

Do NOT add: version numbers, line numbers, test counts, or other specifics that change frequently.
