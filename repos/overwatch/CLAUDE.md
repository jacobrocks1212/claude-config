# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Overwatch Is

Overwatch is Cognito Forms' internal admin, monitoring, and operations tool. It is a separate application that reaches into the main Cognito Forms product (via `CognitoClient`), its SQL database, Azure infrastructure, and a large set of third-party services (Stripe, Square, Mailchimp, Zendesk, Trello, GitHub, Azure DevOps, Microsoft Graph, Bing Ads) to give staff a single console for supporting customers, running background operations, monitoring health, and managing deployments/feature environments.

## Build & Run

All backend projects target **.NET 10** (except `fetchbingadstokens`, which is `netcoreapp6.0`). The solution file is `Cognito.Overwatch.slnx` (the newer XML `slnx` format).

```bash
# Restore + build the whole solution
dotnet build Cognito.Overwatch.slnx

# Run the web app (from repo root)
dotnet run --project src/overwatch.web

# Run the WebJob (background processor) locally
dotnet run --project src/overwatch.webjob
```

`ASPNETCORE_ENVIRONMENT` selects config. Recognized environments (each has an `appsettings.<Env>.json`): **Testing, Staging, Prodtest, Features, Production**. Secrets come from **Azure Key Vault** at runtime (`Security:VaultBaseUrl`), resolved via `DefaultAzureCredential` — so running locally against a real environment requires Azure auth. The connection string is read as `ConnectionString` or `Data:ConnectionString`.

### Frontend (Vue SPA)

The frontend lives in `src/overwatch.web/client-app/` (**Vue 2.7 + TypeScript**, Vue CLI, Element UI, ApexCharts, Monaco editor).

```bash
cd src/overwatch.web/client-app
npm install
npm run watch    # dev build + watch (writes into wwwroot/lib/pages)
npm run serve    # dev server with HMR
npm run build    # production build
npm run lint
```

Key detail: this is a **multi-page app, not a single SPA**. `vue.config.js` defines one entry per feature page (e.g. `user-admin`, `organization`, `feature-flags`, `data-modification-tool`, `performance-dashboard`). Builds output to `../wwwroot/lib/pages` with `filenameHashing: false`, and Razor views (`src/overwatch.web/Views/**`) mount each page by embedding the corresponding built bundle. When you add a page under `client-app/src/pages/`, you must also register it in `vue.config.js` and wire it into the serving Razor view/controller.

Legacy site-wide assets (jQuery/Foundation/SCSS) are still built via **gulp** (`gulpfile.js`) into `wwwroot/`.

## Tests

Tests are in `cognito.web.tests/` (project `overwatch.tests.csproj`) using **MSTest** (not xUnit). Coverage is currently minimal.

```bash
dotnet test cognito.web.tests/overwatch.tests.csproj

# Single test
dotnet test cognito.web.tests/overwatch.tests.csproj --filter "FullyQualifiedName~CryptoUtilTests"
```

## Architecture

Three deployables share the core `Overwatch` class library:

- **`src/Overwatch/`** — core library. Holds all data-access repositories (`Data/`), domain models (`Model/`), external service clients (`CognitoClient`, `AzureClient`, `DevOpsClient`, `SlackClient`, `MailchimpClient`), and the rules engine (`Model/Rule/`). Referenced by both web and webjob.
- **`src/overwatch.web/`** — ASP.NET Core MVC + SignalR admin UI. ~30 controllers (`Controllers/`), Razor views, the Vue MPA, and additional service clients under `Clients/`.
- **`src/overwatch.webjob/`** — Azure WebJob background processor. Consumes queue events from the Cognito product and runs scheduled timer tasks.
- **`src/fetchbingadstokens/`** — small standalone helper service for OAuth token refresh against the Bing Ads API.

### Data access — Dapper repositories

There is **no ORM/EF**. All DB access uses **Dapper** over raw SQL against `IDbConnection` (a scoped `SqlConnection`, DI-registered in `Startup.cs`/webjob `Program.cs`). Each repository has an `I<Name>Repository` interface + implementation in `src/Overwatch/Data/` and inherits the trivial `Repository` base. To add data access: write the SQL in a repository method, expose it on the interface, register the repo in DI. Match the existing hand-written-SQL style rather than introducing a query abstraction.

### WebJob event processing

The webjob is the integration backbone. Two mechanisms, both discovered via reflection at startup:

1. **Queue events** (`QueueTasks.cs`): Azure Storage Queue triggers (user/org/form/stripe/archive/overwatch queues). Incoming messages carry a `Type` (`Namespace.EventName, Assembly`); `QueueTasks` strips it to the class name and maps it to a handler. Handlers are classes in `Events/` decorated with `[CognitoEvent("Name")]`, extending `CognitoEvent : CognitoTask`, implementing `Handle()`. All `[CognitoEvent]` types are auto-registered in DI. **To handle a new product event, add a `[CognitoEvent]`-attributed class in `Events/` — no manual switch/registration needed.** But first read **Overwatch Sync** below: classic per-event handlers are being phased out, and if all you need is to mirror Cognito *entity state* (a new/changed column on an OW table that shadows a Cognito entity), that is sync's job — do **not** add a bespoke event handler for it.
2. **Timer tasks** (`TimerTasks/`): classes with `[TimerTrigger("cron")]` methods, discovered by the Azure WebJobs SDK. Cron format is Quartz-style 6-field (see the extensive reference comment in `TimerTasks.cs`). Grouped into subfolders by integration (Stripe, Zendesk, Azure, MailGun, Alert).

The **rules engine** (`Model/Rule/`) is loaded once at startup from the `ruleset`/`rules`/`ruletype` DB tables into a static `RuleContext.Current`, used to flag suspicious/fraudulent activity.

### Overwatch Sync (mirroring Cognito entity state)

Overwatch shadows core Cognito entities (organizations, members, web users, …) into its own SQL tables. The **preferred, going-forward mechanism** for keeping those tables in step with Cognito is **OW Sync**, and **classic per-event `[CognitoEvent]` handlers are being deliberately phased out** in favor of it. Canonical reference: the [Overwatch Sync Overview](https://dev.azure.com/cognitoforms/Cognito%20Forms/_wiki/wikis/Cognito%20Forms.wiki/15771/Overwatch-Sync-Overview) wiki.

What this means when you touch shadowed-entity data:

- **New mirrored columns provision and populate themselves via sync.** When a Cognito entity gains a field that should surface in Overwatch, OW Sync adds the matching column to the OW table and fills it automatically — you do **not** write a manual `src/scripts/` migration for it, and you do **not** add a `[CognitoEvent]` handler to stamp it. (Per the sync system owner; the auto-provisioning lives in the sync system, not in this repo.) There is a **reflection delay of ~7 minutes** before an upstream change appears in Overwatch — acceptable for entity-state mirroring; only reach for an event handler if you genuinely need near-instant reflection.
- **The in-repo `organization.synced` handler is the older/classic sync path, not the auto-provisioning one.** `Events/OrganizationSynced.cs` downloads a `SyncData` blob and upserts via `OrganizationRepository.CreateOrUpdateOrganization` / `CreateOrUpdateMembers` / `CreateOrUpdateWebUsers`. Those upserts use **hardcoded column lists** — they do **not** provision columns and do **not** pick up a new field just because you added it to the `Organization` model. Do not assume this path covers a new mirrored column; the auto-provisioning is the separate sync system in the wiki.
- **To surface a new synced column in the UI, you still edit Overwatch:** add the property to the `Model/` type and select it in the relevant `OrganizationRepository` query (the `select *` queries — `Get`/`GetByCode`/`GetExistingByCode` — pick it up for free). Sync owns the DB column and its data; Overwatch owns reading and rendering it.
- **Testing sync locally:** deploy your branch to the `sync` feature environment, or to `overwatch-testing` via `staging2`.

You still write `[CognitoEvent]` handlers for genuine *actions/signals* that are not entity-state mirroring (e.g. one-off operational events), and for the many existing handlers. The phase-out targets handlers whose only job is to copy Cognito entity fields into OW tables.

### Auth

Web auth is **Azure AD (OpenID Connect)** with cookie sessions (4h sliding). On every request the cookie principal is re-validated against the `IUserRepository` — if the DB user record was updated after the cookie was issued, the principal is rejected (forces re-login on permission changes). A global `AuthorizeFilter` requires authentication on all MVC endpoints by default.

## Database Migrations

SQL is applied by hand, not via a migration framework. `src/scripts/` holds **numbered, mostly work-item-prefixed** change scripts (e.g. `57195-add-jul-2026-pricing-tier.sql`, `52299-add-pull-request.sql`) applied in order; `stored-procedures/` holds procedure definitions. `sql/` at the repo root holds `schema.sql` (reference schema) plus ad-hoc backfill/diagnostic queries. When adding a schema change, add a new numbered script under `src/scripts/` following the `<workitem>-<description>.sql` convention and update `sql/schema.sql` if it's a structural change.

**Exception — columns that mirror a Cognito entity field:** do **not** write a manual migration for these. OW Sync provisions and populates them automatically (see **Overwatch Sync** above). Manual `src/scripts/` migrations are for Overwatch-owned tables/columns that sync does not manage.

## CI/CD

Azure DevOps pipelines. `pipeline-definitions/dry-pipeline-full.yml` is a thin wrapper that extends shared templates from the external `Pipeline.Templates` repo and takes an `environment` parameter (Testing/Staging/Prodtest/Features/Production). The actual build/deploy logic lives in those templates, not in this repo. Overwatch also manages deployments of the main product itself (`DeploymentController`, `BuildsController`, `GitClient`, real-time build progress over the `BuildProgressHub` SignalR hub).

## Conventions

- **This is an Azure DevOps repo**, not GitHub — PRs use `.azuredevops/pull_request_template.md`; the main branch is `main`.
- Backend follows the workspace-global C# conventions (PascalCase public, `_camelCase` private, nullable enabled, always `async/await`). Repositories return `Task<T>`.
- Frontend uses **double quotes** (enforced by ESLint), `vue/recommended`, and class-style components (`vue-property-decorator`).
- Secrets never live in `appsettings.*.json` in source — blanks there are filled from Key Vault at runtime.
