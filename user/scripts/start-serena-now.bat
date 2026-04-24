@echo off
start "Serena MCP" cmd /k uvx --from "git+https://github.com/oraios/serena" serena start-mcp-server --project "C:\Users\JacobMadsen\source\repos\Cognito Forms" --transport streamable-http --host 127.0.0.1 --port 8765 --enable-web-dashboard True --open-web-dashboard False
