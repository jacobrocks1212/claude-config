---
name: har-analysis
description: USE WHEN analyzing HAR (HTTP Archive) files — network requests, cookies, headers, API calls. Triggers on 'HAR', 'network capture', 'analyze requests'.
version: 2.0.0
---

# HAR File Analysis

Comprehensive tool for analyzing HTTP Archive (HAR) files to debug network requests, headers, cookies, API responses, and errors.

## Script Location

```
C:\Users\JacobMadsen\.claude\scripts\analyze_har.py
```

## Usage

```bash
python "C:\Users\JacobMadsen\.claude\scripts\analyze_har.py" <har-file> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--summary` | Show request summary table (default if no option specified) |
| `--search <term>` | Search all request/response bodies for a term |
| `--url <pattern>` | Filter requests by URL pattern (substring match) |
| `--json <pattern>` | Pretty-print JSON responses matching URL pattern |
| `--errors` | Show only error responses (4xx, 5xx) |
| `--body <pattern>` | Show request bodies (POST/PUT) matching URL pattern |
| `--headers <pattern>` | Show headers for requests matching URL pattern |
| `--cookie <name>` | Search for specific cookie (detailed cookie analysis) |
| `--verbose, -v` | Show more detail in output |

### Examples

```bash
# Show summary of all requests
python analyze_har.py capture.har --summary

# Find all error responses
python analyze_har.py capture.har --errors

# Search for any occurrence of "api_key" in bodies
python analyze_har.py capture.har --search "api_key"

# View JSON responses from API calls
python analyze_har.py capture.har --json "/api/"

# See what's being POSTed to login
python analyze_har.py capture.har --body "/login"

# Inspect headers for specific endpoint
python analyze_har.py capture.har --headers "/api/users"

# Detailed cookie analysis
python analyze_har.py capture.har --cookie "session_id"

# Combine filters
python analyze_har.py capture.har --url "/api/" --errors --verbose
```

### Backward Compatibility

Legacy usage is still supported:
```bash
python analyze_har.py <har-file> <cookie-name>
```

## Feature Details

### Request Summary (`--summary`)
Displays a table of all requests with:
- Request index, method, status code
- Response size (human-readable)
- Content-Type
- URL (truncated)
- Status breakdown by category (2xx, 3xx, 4xx, 5xx)

### Body Search (`--search`)
Searches through ALL request and response bodies for a term:
- Case-insensitive matching
- Shows context around matches
- Useful for finding API keys, tokens, specific data

### Error Detection (`--errors`)
Filters to only show 4xx and 5xx responses:
- Shows status code and status text
- Displays URL and content-type
- Preview of error response body

### JSON Viewer (`--json`)
Pretty-prints JSON responses:
- Auto-detects JSON by content-type or body structure
- Properly formatted with indentation
- Truncated output (use `--verbose` for full)

### Request Body Viewer (`--body`)
Shows POST/PUT/PATCH request bodies:
- Auto-formats JSON bodies
- Useful for debugging form submissions and API calls

### Headers Viewer (`--headers`)
Shows all request and response headers for matching URLs:
- Full header names and values
- Useful for debugging auth, CORS, caching issues

### Cookie Analysis (`--cookie`)
Detailed cookie-specific analysis (original functionality):
- Set-Cookie response headers
- Cookie request headers
- Cookies arrays in HAR structure
- Raw search throughout HAR file

## Critical Limitations

### Chrome HAR Exports Strip Cookie Data

Chrome's "Save all as HAR with content" export **strips cookie-related headers for privacy**. This is the most common issue when analyzing cookies.

**Symptoms:**
- DevTools shows `Set-Cookie` headers, but HAR doesn't
- Empty `"cookies": []` arrays
- Cookie analysis finds nothing

**Workarounds:**
- Use **Fiddler** with HTTPS decryption
- Use **Wireshark** for packet-level analysis
- Inspect directly in DevTools (don't export)
- Use `curl -v` for specific requests

### Response Bodies May Be Missing

Some HAR exports don't include response body content, especially for:
- Large responses
- Binary content (images, files)
- Streaming responses

### Client-Side Cookies Not Captured

HAR only captures HTTP traffic. JavaScript `document.cookie` operations won't appear.

## When to Use This Script

**Good for:**
- Analyzing API request/response patterns
- Finding specific data in network traffic
- Debugging error responses
- Reviewing request headers (Auth, Content-Type)
- Inspecting what's being POSTed to forms/APIs
- Understanding request flow and timing

**Not reliable for:**
- Cookie analysis (Chrome strips them)
- Client-side JavaScript behavior
- Real-time debugging (use DevTools instead)

## Alternative Tools

| Tool | Best For |
|------|----------|
| **Fiddler** | Complete HTTP capture including cookies |
| **Wireshark** | Packet-level analysis |
| **curl -v** | Single request debugging |
| **DevTools** | Real-time inspection |
| **Postman** | API testing and inspection |

## Example Output

### Summary
```
================================================================================
REQUEST SUMMARY
================================================================================
Total requests: 42

Status breakdown: 2xx: 38 | 3xx: 2 | 4xx: 2

   # Method Status       Size Type                      URL
--------------------------------------------------------------------------------
   0 GET    200  [OK]    15.2 KB text/html                 https://example.com/
   1 GET    200  [OK]     2.3 KB application/javascript    https://example.com/app.js
   2 POST   401  [!!]      128 B application/json          https://example.com/api/login
...
```

### Error Output
```
================================================================================
ERROR RESPONSES (4xx/5xx)
================================================================================
Found 2 error response(s):

#2 [!!] 401 Unauthorized
  POST https://example.com/api/login
  Content-Type: application/json
  Response: {"error": "Invalid credentials"}

#15 [XX] 500 Internal Server Error
  GET https://example.com/api/data
  Content-Type: text/html
  Response: <!DOCTYPE html><html><head><title>Error</title>...
```
