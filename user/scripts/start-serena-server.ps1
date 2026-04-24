# Start Serena MCP server as a persistent HTTP service
# Run this before starting Claude Code for faster startup

$ErrorActionPreference = "Stop"

$project = "C:\Users\JacobMadsen\source\repos\Cognito Forms"
$port = 8765

Write-Host "Starting Serena MCP server for: $project" -ForegroundColor Cyan
Write-Host "Port: $port" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Run Serena with Streamable HTTP transport (modern MCP standard)
uvx --from "git+https://github.com/oraios/serena" serena start-mcp-server `
    --project "$project" `
    --transport streamable-http `
    --host 127.0.0.1 `
    --port $port `
    --enable-web-dashboard $true `
    --open-web-dashboard $false
