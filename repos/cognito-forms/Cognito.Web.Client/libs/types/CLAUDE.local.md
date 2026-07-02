# @cognitoforms/types — Generated TypeScript Types

## Gotchas
- **Generated types are COMMITTED to source control** — unlike typical codegen that's gitignored, these files are tracked. This ensures frontend builds don't depend on backend being buildable.
- Regeneration requires a built `Cognito.Services` project (needs `Cognito.dll`).
- After backend model changes, you MUST regenerate types AND commit the changes.

## Regeneration Workflow

### When to Regenerate
Regenerate when you modify:
- C# model classes in `Cognito.Core/Model/`
- DTOs in `Cognito.Core/DataTransfer/`
- Any class decorated with `[ExportToTypeScript]`

### How to Regenerate
```powershell
cd Cognito.Web.Client/libs/types/typegen
./generate-server-types.ps1
```

Options:
- `-clean` — Removes existing `server-types/` before generating
- `-UpdateInPlace` — Updates existing files, removes types that no longer exist

### After Regeneration
```bash
git status Cognito.Web.Client/libs/types/server-types/
# Review changes, then commit alongside your backend changes
```

## Type Generation Details

### TypeGen Configuration
- Config: `typegen/typegen.config.json`
- Uses [TypeGen](https://github.com/jburzynski/TypeGen) (.NET tool)
- Scans assemblies for `[ExportToTypeScript]` decorated types

### Import Path Correction
`typegen/correct-import-paths.ps1` fixes relative imports after generation.

## Directory Structure
```
libs/types/
├── server-types/           # Generated TypeScript interfaces
│   ├── core/              # Cognito.Core types
│   │   ├── model/         # Domain models
│   │   └── data-transfer/ # DTOs
│   └── *.ts               # Top-level types
├── typegen/               # Generation scripts
│   ├── generate-server-types.ps1
│   ├── correct-import-paths.ps1
│   └── typegen.config.json
└── package.json           # Nx project config
```

## Coordination with Backend

When making backend model changes:
1. Make C# changes in `Cognito.Core`
2. Build `Cognito.Services` (ensures `Cognito.dll` is up to date)
3. Run `generate-server-types.ps1`
4. Review generated changes
5. Commit both backend and generated type changes together

---

## Maintaining This Document

Update this file when:
- Adding new architectural patterns or service hierarchies
- Discovering non-obvious gotchas that would trip up future developers
- Renaming or restructuring directories/files mentioned here

Do NOT add: version numbers, line numbers, test counts, or other specifics that change frequently.
