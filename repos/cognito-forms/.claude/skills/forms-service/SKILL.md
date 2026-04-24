---
name: forms-service
description: Index and navigation aid for FormsService.cs (9,600+ lines). Invoke before editing FormsService.cs to find existing methods, avoid duplicates, and understand structure.
user_invocable: true
---

# FormsService.cs Index

USE WHEN editing `Cognito.Core/Services/Forms/FormsService.cs` - the main forms domain service (~9,600 lines, ~250 methods).

## Before Making Changes

1. **Check if the method already exists** - use the index below to search by verb or name
2. **Understand the organization** - methods are grouped into regions (Email Domains, Import, Entry Views, XmlCleanser)
3. **Follow existing patterns** - check similar methods for parameter conventions and naming

## Regenerating the Index

If FormsService.cs has changed significantly:
```bash
node ~/.claude/skills/forms-service/tools/generate-index.mjs
```

Pass `--repo-root=/path/to/repo` when working in a git worktree.

## Index Summary

<forms-service-index>
{{{read_file "~/.claude/skills/forms-service/forms-service-index.json"}}}
</forms-service-index>

## Quick Method Lookup

### By Verb Category

Use these categories to find methods by their operation type:
- **Create**: `CreateBlankForm`, `CreateFolder`, `CreateSharedLink`, `CreateEntryLink`...
- **Get**: `GetForm`, `GetEntry`, `GetFormCache`, `GetEmailDomain`...
- **Update**: `UpdateFormFeatures`, `UpdateEntryStatus`, `UpdateEntryData`...
- **Delete**: `DeleteForm`, `DeleteEntry`, `DeleteFolder`...
- **Store**: `StoreForm`, `StoreProfile`, `StoreFormCache`...
- **Save**: `SaveEntry`, `SaveForm`...
- **Assert**: Security assertions (6 overloads)
- **Validate**: `ValidateForm`, `ValidateAccessToken`, `ValidateFormPayment`...

### Regions

| Region | Lines | Purpose |
|--------|-------|---------|
| Email Domains | 477-800 | Custom email domain management |
| Import | 6223-6564 | Form/entry import functionality |
| Entry Views | 6566-8069 | Entry view definitions and queries |
| XmlCleanser | 8129-8181 | HTML/XML sanitization |

### Nested Types

| Type | Line | Kind |
|------|------|------|
| FormStorageSummary | 5038 | class |
| EntryAction | 9526 | enum |
| StorageSuffixes | 9533 | enum |
| EntryStatus | 9540 | class |
| JsonStatus | 9580 | enum |
| EntityJson | 9589 | class |
| CopyCancelledException | 9600 | class |
| SimpleFormMeta | 9605 | class |
| StoreFormResult | 9612 | class |

### Constructor Dependencies

FormsService takes these dependencies (useful for mocking in tests):
- `ICoreService coreService`
- `IStorageContext context`
- `ModuleConfigurationRef config`
- `IPaymentService paymentService`
- `IProfileService profileService`
- `IMemberProfileService memberService`
- `IPlansService plansService`

## Common Tasks

### Adding a New Method
1. Check if similar method exists using verb categories above
2. Place in appropriate region if applicable
3. Follow naming conventions: `VerbNoun` (e.g., `GetForm`, `CreateEntry`)
4. Add appropriate `Assert()` call for security if needed

### Finding Assert Overloads
Line 1004+: Multiple overloads for different security scenarios
- `Assert(SecurityTask task, FormRef form = null, bool throwException = true, bool honorLocked = true)`
- `Assert(SecurityTask task, FolderRef folder, ...)`
- `Assert(SecurityTask task, FormRef form, FolderRef folder, ...)`
- And more...

### Entry Operations
Key entry methods:
- `GetEntry(Form, entryNumber)` - Get single entry
- `SaveEntry(Form, FormEntry)` - Save entry changes
- `DeleteEntry(Form, FormEntry)` - Delete entry
- `CreateEntryLink(...)` - Generate entry access links
