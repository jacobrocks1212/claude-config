### Cognito Forms Quality Gates

Prefer the filtered skill commands for cleaner output:
- C# changes → `/msbuild` (build), `/mstest` (tests)
- Frontend changes → `/nxbuild` (build), `/nxtest` (tests)
- Mixed → run all four in sequence

If running raw commands instead of skills:
- Build: `dotnet build "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.sln" -verbosity:minimal`
- Test: `dotnet test "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.UnitTests\Cognito.UnitTests.csproj" --verbosity minimal`
- Frontend: `cd "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.Web.Client" && npx nx test <project>`
