# Infrastructure & Deployment

How Cognito Forms is hosted, built, deployed, and how its static assets are served/cached. Compiled from the `Cognito.Infra` IaC repo, the ADO build pipelines, and the application repo's config. Focus areas that recur in feature work: the CDN, the static-library vendoring pattern, and the edge/caching model.

> Sibling repo worth cloning for reference: `cognitoforms/Cognito.Infra` (Bicep/ARM IaC — Front Door, App Gateway, WAF, VMSS, App Service, CosmosDB, AI Search). Clone it to `~/source/repos/Cognito.Infra`. Pipeline step logic lives in a **separate** ADO repo, `Pipeline.Templates` (not on GitHub).

## Edge topology (Azure Front Door → App Gateway → VMSS/IIS)

- **Azure Front Door Premium** profile `fd-cognitoforms` (prod) / `fd-cognitoforms-npe` (staging), defined in `Cognito.Infra/Cognito.FrontDoor/`. One AFD endpoint per environment.
- **Single origin group, single origin, single route** (`patternsToMatch: /*`). Front Door fronts the **application's own web tier** — there is *no* separate static-asset origin behind this Front Door. The origin hostname is `<env>.cognitoforms.com` (e.g. `cs-prod.cognitoforms.com`).
- Public custom domains on the prod route: `cognitoforms.com`, `www.cognitoforms.com`, `services.cognitoforms.com` (bare apex 301-redirects to `www`). The auto-generated `*.azurefd.net` hostname is disabled (`linkToDefaultDomain: Disabled`).
- **App Gateway (WAF_v2)** (`Cognito.Infra/Cognito.AppGateway/`, `Cognito.WAF/`) is the reverse proxy in front of the **VMSS** backend pools; `cs-<env>.cognitoforms.com` resolves to it. (The DNS wiring for `cs-<env>` is managed outside `Cognito.Infra`.)
- The app is deployed to VMSS instances as a **web-deploy zip** (`cogw-<commit>.zip`) pulled from a per-environment Azure Storage blob container and expanded into `D:\cognito-services`, which becomes the IIS site's physical path (`Cognito.Infra/Cognito.VMSS/scripts/cogw-install.ps1`). That blob container is a **deployment staging location**, not a Front Door origin.
- `Cognito.AppService/` (Azure App Service, .NET Framework) and `Mcp.AppService/` are separate hosts used for autotest/other environments and the MCP service — they do **not** front main production traffic.

### Edge caching model (no CDN purge anywhere)

Front Door route rulesets (`Cognito.FrontDoor/`):
- **`legacyCaching`** — paths beginning `/content/`, `/scripts/`, `/include/`, `/robots.txt` get compression + `queryStringCachingBehavior: UseQueryString` + a **1-day TTL** (`OverrideIfOriginMissing`). This is the dedicated app-tier static-asset cache rule.
- **`cachehash`** — when the query string contains `cachehash`, cache behavior defers to the origin's own `Cache-Control` (`HonorOrigin`). This is the app's cache-bust convention for hashed/versioned bundles: append `?cachehash=<value>` for long-lived, key-varied caching.
- There is **no `az cdn endpoint purge` / cache-invalidation step in any pipeline.** Cache-busting is achieved entirely by **immutable, version-named paths** (and the `cachehash` query string). Do not look for or add a purge step.

## Two first-party static-serving mechanisms

There are **two distinct** ways first-party static assets are served. They are easy to confuse — they are different origins with different mechanics.

### 1. The static CDN — `static.cognitoforms.com` (the vendoring target)

- A **separate** blob-backed CDN, *not* the `fd-cognitoforms` Front Door above. Backed by storage account `cognitocdn` (prod) / `cognitotestcdn` (test), container `cdn`, fronted by a classic Azure CDN profile (`cognito-cdn.azureedge.net` per DNS) configured outside `Cognito.Infra`.
- Config key: **`clientsideConfigUrlOrigin`** in the `<cognito>` config section (`Cognito/Configuration.cs`, `Cognito.Services/Web.config` + per-env `Web.Azure *.config` overrides). `StaticLibrariesUrl` is derived as `clientsideConfigUrlOrigin + "/lib/"`.
- **There are only two static-CDN origins across all environments — a prod one and a shared test one** (verified against `Pipeline.Templates/variables/Cognito/<Env>-variables.yml` `AZURE_CDN_STORAGE` + `Web.Azure *.config` `clientsideConfigUrlOrigin`):

  | Environments | `clientsideConfigUrlOrigin` | `AZURE_CDN_STORAGE` |
  |---|---|---|
  | Production, Prodtest | `https://static.cognitoforms.com` | `cognitocdn` |
  | **all others** — Features, FeaturesVMSS, Staging, Staging2, Staging2WUS, LoadTesting, AutoTest | `https://static-test.cognitoforms.com` | `cognitotestcdn` |

- **Consequence (non-obvious):** feature environments do **not** have their own per-env static CDN — they share `static-test.cognitoforms.com` / `cognitotestcdn` with Staging2. But `uploadStaticLibraries` is gated to **Production + Staging2 only** (see pipeline section), so on the test side **only the Staging2 leg ever publishes to `cognitotestcdn`**. A feature-env deploy never uploads static libraries. Therefore a newly-vendored `/lib/<name>@<version>/` asset is **unusable in feature envs until a Staging2 deploy publishes it** (and unusable in prod until a Production deploy does). Feature envs then read it from the shared test CDN with no per-feature-env upload. Production (`cognitocdn`) and the test CDN (`cognitotestcdn`) are distinct storage accounts under distinct subscriptions (`Cognito Forms Prod` vs `Cognito Forms Dev/Test`) — a Staging2 deploy cannot touch a Production asset.
- Logical paths under that origin (assembled in `Cognito/ClientSideConfigurationInjection.cs`):
  - `/app/` — SPA (`apps/spa`) build output ("the cdn container for the SPA is called app")
  - `/form/` — client (end-user form runtime, `apps/client`) build output
  - `/content/` — general content
  - `/api-reference/` — versioned OpenAPI/OData JSON
  - **`/lib/` — vendored third-party library files**, exposed to the client as `StaticLibrariesUrl` (`= clientsideConfigUrlOrigin + "/lib/"`)

### 2. App-tier static — `www.cognitoforms.com/scripts/` (same-origin)

- Ordinary IIS-served paths (`/scripts/`, `/content/`, `/include/`) on the same VMSS web tier that serves the app, behind the `fd-cognitoforms` Front Door. Same origin as the app.
- Rides the `cogw-<commit>.zip` web-deploy package (i.e. whatever the backend build emits into those folders). Cache-busted via the `legacyCaching` 1-day rule or `?cachehash=`.

**Which to use:** for vendoring a third-party library, mechanism 1 (`/lib/`) is the endorsed, purpose-built path (see below). Mechanism 2 is same-origin (no CORS) but mixes assets into the app package and needs IIS MIME config for novel extensions.

## Vendoring a third-party JS/WASM library first-party (the Scalar pattern)

The supported, already-shipped way to serve a third-party library from our own CDN (precedent: `@scalar/api-reference`, commit `833be5bf872`, "Use Versioned API Docs"). Copy this pattern rather than adding runtime third-party-CDN loads (`esm.sh`/`jsdelivr`) or bundler-vendoring (adding npm deps + normal `import()` + emitting via the frontend asset pipeline — that approach was explicitly rejected).

1. **Check the built distribution into source control** under `Cognito.Services/Content/<lib>/`, with the **filename/folder = the exact CDN path segment**, versioned — e.g. `Content/scalar/scalar@1.32.1`. Version-named paths are immutable, which is what makes cache invalidation a non-issue.
2. **Register it in the csproj** so it lands in build output:
   ```xml
   <ItemGroup>
     <Content Include="Content\scalar\**\*" CopyToOutputDirectory="PreserveNewest" />
   </ItemGroup>
   ```
   (`Cognito.Services/Cognito.Services.csproj`)
3. **Release publishes it — but the staging whitelist is a hardcoded list, NOT a glob.** The `DRY - Cognito Forms` pipeline's `uploadStaticLibraries` step (`Pipeline.Templates/templates/deploy/uploadApiReferenceAssets.yml`, invoked from `deploymentPrep.yml`, gated to **Production + Staging2**) copies **only the library folders named in an explicit array** into the staged `lib/` dir, then `azcopy`s (MSI auth) each versioned folder to `cdn/lib/<name>`, **skipping any version that already exists**. No engineer-run upload, no purge. **A newly-vendored library will silently 404 in deployed envs until its folder name is added to that array** — it is not auto-discovered. (The embedpdf work extended the array from a single `Content/scalar` to `@("scalar","embedpdf")` on `Pipeline.Templates` branch `inno/publish-embedpdf-static-library`; that generalization is the pattern to copy for the next library.)
4. **Reference it at runtime** via the server-injected config, not a hardcoded URL:
   - Server injects `window.CognitoConfiguration` (including `StaticLibrariesUrl`) into the HTML head (`Cognito/ClientSideConfigurationInjection.cs::InjectConfigurationIntoStream`).
   - Client reads it via `Cognito.Web.Client/libs/utils/clientside-configuration.ts` (typed in `libs/types/server-types/client-side-configuration-injection.ts`).
   - Precedent usage: `apps/spa/src/components/integrations/ApiReference.vue` — `script.src = \`${CognitoConfiguration.StaticLibrariesUrl}scalar@1.32.1\``.

> `vue@2.7.15` (`vueScriptUrl` config key → hardcoded absolute `static.cognitoforms.com/lib/vue@2.7.15/vue.min.js`, same URL in every env) is the **older, manually-managed** precedent. Prefer the Scalar pattern (per-environment via `StaticLibrariesUrl`) for anything new.

### Gotchas when vendoring for ESM `import()` / WASM (vs a classic `<script>`)

Scalar loads via a classic `<script src>` tag. A library loaded via ESM dynamic `import()` or a `WebAssembly` fetch has extra requirements that Scalar does not exercise:
- **Cross-origin.** `static.cognitoforms.com` is a *different origin* from the app (`www.cognitoforms.com`), so a cross-origin module `import()` and a cross-origin `.wasm` fetch require **CORS/`Access-Control-Allow-Origin`** on the CDN. (First-party, so we control it — unlike the blob-redirect CORS trap; but it must be set.) Loading as a classic global-assigning `<script>` avoids module-CORS; or use the same-origin app-tier `/scripts/` mechanism to sidestep CORS entirely.
- **`.wasm` content-type.** `WebAssembly.instantiateStreaming` needs `Content-Type: application/wasm`; a wrong type makes it reject with a `TypeError`. `azcopy`'s extension-based auto-detection does **not** reliably tag `.wasm` (it lands as `application/octet-stream`), so the `uploadStaticLibraries` step cannot be trusted to set it — the embedpdf work adds an explicit post-upload pass that re-`azcopy`s every `*.wasm` with `--content-type application/wasm`. (Empirical confirmation on the deployed CDN response header is a still-pending runtime gate, not yet observed.) There is **no** `.wasm` MIME mapping in `Cognito.Services/Web.config`'s `staticContent`, so the same-origin `/scripts/` mechanism would need one added.

## Build & deploy pipeline (Azure DevOps, project "Cognito Forms")

| Pipeline | Def ID | Role |
|---|---|---|
| **DRY - Cognito Forms** | 198 | The real build + deploy pipeline (Cognito.Services + `apps/spa`/`client`/`marketing`). Runs many times/day across Staging/Staging2/Prodtest/Production/Features. |
| Main-CI | 165 | PR-validation build only (no deploy). |
| Prerender | 193 | Re-renders marketing/support HTML into the CDN blob without a full redeploy. |
| Cognito.Infra | 205 | Infra (IaC) pipeline. |
| Azure Resource Deployment | 208 | Generic ARM/infra deploy. |

- The application repo's `pipeline-definitions/*.yml` are **thin wrappers** — each `extends` a template from the separate ADO Git repo **`Pipeline.Templates`** (`resources.repositories`, alias `@templates`, default `ref: main`). All real step logic (build, CDN upload, App Service/VMSS deploy) lives there, not in the app repo.
- **Testing a `Pipeline.Templates` change without merging to `main`:** in the Run dialog, override the `templates` resource repository's branch (Run pipeline → Resources → the `templates` repo → pick your feature branch). The run then extends your branch's templates instead of `main`. The chosen ref is visible in the run's `resources.repositories.templates.refName` (via `pipelines_get_run`) — worth confirming there, since a forgotten override silently runs `main` and appears to "not pick up" your change. `DRY - Cognito Forms` run parameters: `environment` (Staging/Staging2/Staging2WUS/Prodtest/Production/Features/FeaturesVMSS/LoadTesting), `enablePrerender`, `latestBuildMode`, `swapSlots`.
- The CSP is set in `Cognito.Services/Infrastructure/RequestLifecycleFlow.cs` (moved there from `WebApplication.cs`), and is **disabled in Development** — the classic cause of "works locally, fails deployed". `script-src` is currently a permissive `https://*` wildcard; a tightening to an explicit host allowlist has been discussed, which is the forcing function that makes first-party asset hosting (either mechanism above) the durable choice over third-party CDNs.

## Frontend build output

- `apps/spa`: **rspack** (`apps/spa/rspack.config.mts`) → `dist/assets/`, `[name].[contenthash].js`, `publicPath: 'auto'`; `vue` injected as an external `<script src>` (from `webpack.constants.mts`); static files copied via `CopyRspackPlugin`.
- `apps/client`: **webpack** (`webpack.common.js`/`webpack.prod.js`), `publicPath` from `FORM_ASSET_URL` (= CDN origin + `/form/`); `vue` is a webpack `externals` entry.
- Neither frontend build emits `.wasm` or has a wasm `asset/resource` rule today.

## Resolved: does `uploadStaticLibraries` auto-discover new libraries?

**No.** The prior open question (glob-a-directory vs. Scalar-specific) is settled by reading `Pipeline.Templates/templates/deploy/uploadApiReferenceAssets.yml`: the step copies only the folders in a **hardcoded array** into the staged `lib/`, so a new vendored library needs its folder name added to that array (see the vendoring section, step 3). A new `Content/<lib>/` folder does **not** auto-publish with zero pipeline changes.

Maintenance: record non-obvious infra/deployment facts and structure changes here; do NOT add line numbers, exact version pins that will drift, or per-run counts.
