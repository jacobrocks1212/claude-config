from mcp.shared.memory import create_connected_server_and_client_session

from servers.work_logging_mcp.server import mcp

EXPECTED_TOOLS = {
    "get_kb_index",
    "get_kb_topic",
    "read_work_log",
    "read_features",
    "evaluate_topic_match",
    "write_managed_block",
    "calculate_hash",
    "get_study_context",
    "work_log_append",
    "import_artifacts",
    "synthesize_features",
    "generate_vault",
}


async def test_server_lists_all_tools() -> None:
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.list_tools()
        tool_names = {t.name for t in result.tools}
        assert tool_names == EXPECTED_TOOLS


async def test_kb_index_has_no_required_params() -> None:
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.list_tools()
        tool = next(t for t in result.tools if t.name == "get_kb_index")
        assert tool.inputSchema.get("required", []) == []


async def test_work_log_append_has_required_params() -> None:
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.list_tools()
        tool = next(t for t in result.tools if t.name == "work_log_append")
        required = set(tool.inputSchema.get("required", []))
        assert required >= {"skill", "project", "title", "summary", "files_modified"}
