---
name: core-controller-endpoints
description: Provides guidance on creating, authenticating, and testing Core API controller endpoints in Cognito Forms — including the [OrgIdentifier] requirement, Overwatch token retrieval, required headers (X-Requested-By, Content-Length), local vs feature-environment auth flows, and common 401 troubleshooting. Use when adding endpoints under /core/api/, debugging Core API auth failures, or writing migrations that hit core controllers.
version: 1.0.0
---
# Core Controller Endpoints

## Overview

Core controller endpoints are internal API endpoints used for administrative operations, data migrations, and support tooling. They use a different authentication mechanism than the regular web API.

---

## Creating a Core Controller Endpoint

### 1. Inherit from BaseCoreController

```csharp
namespace Cognito.Services.Controllers.Core
{
    [RoutePrefix("core/api/organization/{orgId}")]
    public class MyCoreController : BaseCoreController
    {
        // ...
    }
}
```

### 2. Required: Add [OrgIdentifier] Attribute

**CRITICAL:** The `[OrgIdentifier]` attribute must be on the `orgId` parameter for authentication to work.

```csharp
// CORRECT - auth will work
[HttpPost]
[Route("my-endpoint")]
public async Task<ActionResult> MyEndpoint([OrgIdentifier] string orgId)

// WRONG - will return 400 BadRequest
[HttpPost]
[Route("my-endpoint")]
public async Task<ActionResult> MyEndpoint(string orgId)  // Missing [OrgIdentifier]!
```

The `JwtAuthorizeAttribute` uses this attribute to resolve the organization context during authentication (see `JwtAuthorizeAttribute.Framework.cs` / `JwtAuthorizeAttribute.Core.cs`).

### 3. Inject Dependencies

Common services for core controllers:

```csharp
public MyCoreController(
    ICoreService coreService,
    IDataModificationService dataModificationService,
    IErrorNotifier errorNotifier)
{
    this.coreService = coreService;
    this.dataModificationService = dataModificationService;
    this.errorNotifier = errorNotifier;
}
```

### 4. Get User Email from Request

```csharp
var user = ((Configuration.CoreRequestUser)HttpContext.User).Email;
```

---

## Testing Core Controller Endpoints

### Local Development

In Development mode, authentication is bypassed for local requests. No token needed.

```bash
curl -s -X POST "https://local.cognito.dev/core/api/organization/{orgId}/my-endpoint" \
  -H "Content-Type: application/json" \
  -H "Content-Length: 0" \
  -k
```

**Note:** Use `-k` flag to ignore SSL certificate verification for local HTTPS.

### Feature Environments (Sub-Production)

Feature environments require a valid core API token.

#### Step 1: Get Token from Overwatch

Navigate to the Overwatch instance for your target environment:
```
https://overwatch-features-{environment}.azurewebsites.net/op/token
```

Example for poseidon:
```
https://overwatch-features-poseidon.azurewebsites.net/op/token
```

#### Step 2: Make Request with Required Headers

```bash
curl -s -X POST "https://{environment}.cognitoforms.dev/core/api/organization/{orgId}/my-endpoint" \
  -H "Content-Type: application/json" \
  -H "Content-Length: 0" \
  -H "Authorization: {token}" \
  -H "X-Requested-By: overwatch"
```

**Required Headers:**
| Header | Value | Notes |
|--------|-------|-------|
| `Content-Type` | `application/json` | Standard |
| `Content-Length` | `0` | Required for POST with no body |
| `Authorization` | `{token}` | Token from Overwatch (no "Bearer" prefix) |
| `X-Requested-By` | `overwatch` | **Required** - identifies the token source |

### Postman Setup

1. **Method:** POST
2. **URL:** `https://{environment}.cognitoforms.dev/core/api/organization/{orgId}/my-endpoint`
3. **Headers:**
   - `Content-Type`: `application/json`
   - `Content-Length`: `0`
   - `Authorization`: `{token from Overwatch}`
   - `X-Requested-By`: `overwatch`

---

## Authentication Details

### Token Types (Don't Confuse Them!)

| Token Type | Source | Used For |
|------------|--------|----------|
| Web Session Token | Browser login | Regular web API (`/svc/...`) |
| Core API Token | Overwatch `/op/token` | Core API (`/core/api/...`) |

Core API tokens are signed with a KeyVault certificate and decoded by `Configuration.DecodeInternalToken()`.

### Why 401 Unauthorized?

Common causes:
1. **Missing `[OrgIdentifier]`** - Returns 400 BadRequest; add to `orgId` parameter
2. **Missing `X-Requested-By: overwatch`** - Add header
3. **Wrong token type** - Use Overwatch token, not browser session token
4. **Expired token** - Get fresh token from Overwatch
5. **Wrong environment** - Token must be from matching Overwatch instance

---

## Common Patterns

### Query and Update Entities

```csharp
var queryResult = await dataModificationService.QueryEntities(
    orgId,
    "Form",  // Entity type
    user,
    prefix: null,
    top: 100,
    continueAfterId: null
) as DataModificationQueryResult;

if (queryResult?.Status == System.Net.HttpStatusCode.OK)
{
    foreach (var entityJson in queryResult.Originals)
    {
        var entity = JObject.Parse(entityJson);
        // Modify entity...

        var updateResult = dataModificationService.UpdateEntity(
            orgId,
            "Form",
            entity.ToString(),
            user,
            "Migration reason"
        );
    }
}
```

### Dry Run Pattern

```csharp
[HttpPost]
[Route("my-migration")]
public async Task<ActionResult> MyMigration([OrgIdentifier] string orgId, bool dryRun = true)
{
    // ... process entities ...

    if (!dryRun)
    {
        // Actually save changes
        dataModificationService.UpdateEntity(...);
    }

    return Ok(new { DryRun = dryRun, Modified = count });
}
```

---

## Example: Complete Endpoint

```csharp
[HttpPost]
[Route("my-migration")]
public async Task<ActionResult> MyMigration([OrgIdentifier] string orgId, bool dryRun = true)
{
    if (string.IsNullOrWhiteSpace(orgId))
        return BadRequest("Organization ID is required");

    var org = coreService.GetOrganization(orgId);
    if (org == null)
        return NotFound("Organization not found");

    var user = ((Configuration.CoreRequestUser)HttpContext.User).Email;
    var result = new { OrgId = orgId, DryRun = dryRun, Modified = 0, Errors = 0 };

    try
    {
        // Migration logic here...
    }
    catch (Exception ex)
    {
        errorNotifier.SendErrorNotification(ex);
        return InternalServerError();
    }

    return Ok(result);
}
```

---

## Troubleshooting Checklist

- [ ] `[OrgIdentifier]` attribute on `orgId` parameter?
- [ ] Token from correct Overwatch instance?
- [ ] `X-Requested-By: overwatch` header included?
- [ ] `Content-Length: 0` header for POST with no body?
- [ ] Token not expired? (get fresh one)
- [ ] Endpoint deployed to target environment?
