---
name: cognito-infrastructure
description: USE WHEN debugging infrastructure issues, cookie problems, network topology, Azure resources, or request routing in Cognito Forms. USE WHEN investigating issues that behave differently between local development and deployed environments. Triggers on "infrastructure", "App Gateway", "Application Gateway", "CDN", "Load Balancer", "Azure", "cookie not working", "works locally but not in production", "request routing", "Set-Cookie", "bug9", "feature environment".
version: 1.0.0
---

# Cognito Forms Infrastructure

Reference for Cognito Forms Azure infrastructure, request topology, and debugging environment-specific issues.

## Request Topology

### Production (`www.cognitoforms.com`)

```
Browser → Application Gateway (agcognitoformsprod) → App Service
                                                      ↓
                                                     CDN (for static assets only)
```

- **DNS**: `www.cognitoforms.com` → `agcognitoformsprod.eastus.cloudapp.azure.com` (IP: `20.246.218.104`)
- **Application Gateway**: `agcognitoformsprod` - routes requests to App Service
- **CDN**: Only used for static assets (JS, images) - NOT in the main request path

### Feature Environments (`*.cognitoforms.dev`)

```
Browser → Application Gateway → App Service (cog-feature-{name})
```

- **Example**: `bug9.cognitoforms.dev` → App Gateway → `cog-feature-bug9.azurewebsites.net`
- **Direct App Service URL**: `cog-feature-{name}.azurewebsites.net`

### Local Development

```
Browser → IIS/localhost → Application
```

No Application Gateway or CDN involved.

## Testing Different Layers

### Bypass Application Gateway (Feature Environments)

Navigate directly to the App Service URL to bypass the Application Gateway:

```
https://cog-feature-{name}.azurewebsites.net/{path}
```

Example:
- Through gateway: `https://bug9.cognitoforms.dev/OrgName/FormName`
- Direct to App Service: `https://cog-feature-bug9.azurewebsites.net/OrgName/FormName`

If behavior differs between these two URLs, the issue is in the Application Gateway layer.

### DNS Lookup

Check what infrastructure serves a domain:

```powershell
nslookup bug9.cognitoforms.dev
nslookup www.cognitoforms.com
```

- `*.azurefd.net` → Azure Front Door
- `*.azureedge.net` → Azure CDN
- `*.cloudapp.azure.com` → Application Gateway or Load Balancer
- `*.azurewebsites.net` → Direct to App Service

## Azure Resources

### Finding Resources in Azure Portal

1. **App Services**: Search for `cog-feature-` or `cognito-prod`
2. **Application Gateway**: Search for `ag-cognitoforms` or the DNS name
3. **CDN Profiles**: `cognito-static` (production), `cognito-static-test` (dev/test)

### Key Resource Groups

- `feature-environments` - Feature environment App Services
- `cognito-production` - Production resources
- `cognito-devops` - DevOps/CI resources

### Subscriptions

- `Cognito Forms Production` - Production resources
- `Cognito Forms Dev/Test` - Development and testing resources

## Common Issues

### Cookie Domain Mismatch

**Problem**: `Request.Url.Host` returns the internal Azure hostname (e.g., `cog-feature-bug9.azurewebsites.net`) rather than the external hostname (e.g., `bug9.cognitoforms.dev`).

**Impact**: Cookies with explicit Domain set to the internal hostname are rejected by browsers.

**Solution**: Don't set explicit Domain on cookies - let the browser use the request's host.

### HAR Captures Missing Cookie Headers

**Problem**: Chrome HAR exports strip cookie-related headers for privacy reasons. Even when DevTools Network tab clearly shows `Set-Cookie` response headers and `Cookie` request headers, the exported HAR file will have:
- Empty `"cookies": []` arrays
- No `Set-Cookie` or `Cookie` header entries
- Raw string search for cookie names returns nothing

**Symptoms**:
- DevTools shows cookie being set
- HAR analyzer finds nothing
- `"cookies": []` throughout the HAR file

**Solution**: Use Fiddler, Wireshark, or browser extensions like "HAR Export Trigger" that preserve cookie data. For quick verification, use DevTools directly rather than HAR exports.

### Behavior Differs: Local vs Deployed

**Debugging steps**:
1. Test locally (no infrastructure) - establish baseline
2. Test direct to App Service (bypass App Gateway)
3. Test through full stack (App Gateway → App Service)
4. Compare results to isolate which layer causes the difference

## Application Gateway Notes

Per Azure documentation, Application Gateway:
- Sets certain headers (X-Forwarded-For, X-Forwarded-Proto, etc.)
- Does NOT set cookies by default
- May have custom rewrite rules configured

If cookies are being set unexpectedly, check:
1. **HTTP Settings** - Cookie-based affinity
2. **Rewrite rules** - Header/cookie modifications
3. **Backend settings** - Any custom policies

## Contacts

For infrastructure questions, reach out to `@system-team` in Slack.
