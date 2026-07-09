# Cognito.Core — Domain Layer

## Gotchas
- **Dual-target framework**: builds `net472` by default, `netstandard2.0` for NETCORE Debug configuration. Use `#if NETCOREAPP` for conditional compilation.
- Service **interfaces** live here; implementations are in `Cognito/` or `Cognito.Services/`
- **Flush per-iteration entity loads in long rebuild/batch loops.** When a loop calls `StorageContext.Get<T>(id)` per iteration (e.g. `Get<FormEntry>` in `EntryIndexService.ResolveFieldMappingBatchAsync`, or the `BulkDownloadService`/`TaskReminderService` loops), the `IStorageContext` cache retains every loaded entity for the life of the context — over a full-form rebuild that is an unbounded memory leak. Read what you need off the entity, then `StorageContext.Flush(entry);` on the **same iteration**, including the early-`continue` paths where the entity was already loaded. Streaming the lightweight `CompositeEntryIndex` via `Query`/`GetRange` and reading only its properties does NOT need a flush — the rule is specifically about per-iteration `Get<T>` of heavy entities.

## Organization = Tenant Root
Most operations are org-scoped. `Organization` is the partition key for storage and the root of the entity graph.

## Entity Patterns
- Custom attributes drive behavior: `[Id()]`, `[FileRef]`, `[EnableRules]`, `[Overwatch()]`, `[FormBasedEntity()]` — defined in `Cognito/` and `Cognito.Amender/`, applied to entities here
- Interfaces: `IEntity`, `IModelEntity` defined in `Cognito.Amender/`; `IEncryptable`, `IFlushable` in `Cognito/`. Reference wrappers (`FormRef`, `FormEntryRef`, …) are generic `Reference<T>`.
- Revision system for schema evolution — breaking entity changes must include a revision migration

## Services
- `IFormsService` extends `IModuleService<FormsConfiguration>`
- AI services use Liquid templates from `Services/Forms/AI/Prompts/`

## DI Registration — `DependencyInjection/CognitoCoreModule.cs` (Autofac Module)
- Registers `Module<IFormsService>`, `Module<IPaymentService>`, etc. as singletons; factory delegates via `CoreServiceFactory(IComponentContext ctx)`; conditional GemBox vs Aspose registration (feature flag)
- **Convention-scan determinism gotcha:** `RegisterCoreServices` assembly-scans the `Cognito.Core.Services` namespace `.AsImplementedInterfaces()`. If two types in that namespace implement the *same* interface, a single-instance resolve of that interface is **nondeterministic** (last-registration-wins on scan order, silently). To force a deterministic default, exclude the non-default impl from the scan with `.Except<TOther>()` **and** register the chosen default explicitly after `RegisterCoreServices(builder)`. Precedent: `.Except<CoreService>()`.

## FieldInfoGenerator Token Semantics
`Services/FieldInfoGenerator.cs` generates `FieldInfo` tokens for the frontend field picker and Identify Submitter system. Server-side properties:
- **`Id`** — dotted numeric index path; every container (section, table, lookup) prepends its field `Index` + `"."` (field at Index 5 inside a section at Index 2 → `"2.5"`). The dot indicates container nesting of ANY kind, NOT specifically person-field nesting.
- **`InternalName`** — the field's own name from `field.InternalName`. Never dotted on the server side.
- **`Path`** — logical dotted path from `GetLogicalPath()` (e.g. `"Section.PersonField"`), InternalName segments.
- **`Scope`** — space-delimited ancestor internal names (includes the field's own InternalName if it is a container); **`ScopeId`** — dot-delimited ancestor list indexes (for repeating sections/tables).
- **`InternalName` is rewritten on the client side:** `convertFieldInfosToTokens` in `Cognito.Services/Views/Shared/build.js` overwrites it to equal the server's `Path` for non-container fields — see `Cognito.Services/CLAUDE.local.md`. Always check whether you are reading server-side or client-side token semantics.

## FormsService.cs — MANDATORY Skill Invocation
**BEFORE editing `Services/Forms/FormsService.cs` (a large god object), you MUST invoke the `/forms-service` skill** — method index by verb, region locations, nested types, and constructor dependencies for test mocking. Prevents duplicate method creation and aids navigation.

Maintenance: record non-obvious gotchas and pattern/structure changes here; do NOT add version numbers, line numbers, or test counts.
