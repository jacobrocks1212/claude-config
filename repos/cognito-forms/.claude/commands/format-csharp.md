# Format C# Files

Run `dotnet format` on all modified `.cs` files to apply .editorconfig rules (sort usings, fix style).

## Steps

1. Find all changed `.cs` files (staged + unstaged) using git:
```bash
git diff --name-only HEAD -- "*.cs"
```

2. Run `dotnet format` with `--include` for each changed file:
```bash
dotnet format "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.sln" --include <space-separated-file-list> --verbosity quiet
```

3. Report which files were formatted.

## Notes
- Only formats files that have been modified in the current working tree
- Uses the repo's `.editorconfig` for style rules
- Safe to run at any time — only touches changed files
