# @cognitoforms/types — Generated TypeScript Types

## Gotchas
- **Generated types are COMMITTED to source control** — unlike typical codegen that's gitignored. This ensures frontend builds don't depend on backend being buildable.
- Regeneration requires a built `Cognito.Services` project (needs `Cognito.dll`) — build backend first.
- After backend model changes, you MUST regenerate types AND commit them alongside the backend changes.

## Regeneration Workflow

Regenerate when you modify C# model classes in `Cognito.Core/Model/`, DTOs in `Cognito.Core/DataTransfer/`, or any class decorated with `[ExportToTypeScript]`.

```powershell
cd Cognito.Web.Client/libs/types/typegen
./generate-server-types.ps1
```

Options:
- `-clean` — Removes existing `server-types/` before generating
- `-UpdateInPlace` — Updates existing files, removes types that no longer exist

After regeneration: `git status Cognito.Web.Client/libs/types/server-types/`, review, commit with the backend changes.

## Type Generation Details
- Config: `typegen/typegen.config.json`; uses [TypeGen](https://github.com/jburzynski/TypeGen) (.NET tool), scans assemblies for `[ExportToTypeScript]` types
- `typegen/correct-import-paths.ps1` fixes relative imports after generation
- Output layout: `server-types/core/{model,data-transfer}/` mirrors Cognito.Core; generation scripts live in `typegen/`
