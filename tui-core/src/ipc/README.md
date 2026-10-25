# `tui-core/src/ipc/` — Model Context Protocol (MCP) & JSON-RPC 2.0 Subsystem

This directory provides MCP client and embedded server implementations, bidirectional JSON-RPC 2.0 framing, and tool dispatching for multi-agent coordination.

## Files

| File | Purpose |
|---|---|
| `mod.rs` | Public exports for IPC and MCP components (`McpClient`, `EmbeddedMcpServer`, `McpBackend`, `JsonRpcRequest`, `JsonRpcResponse`, `McpTool`). |
| `types.rs` | Protocol types for JSON-RPC 2.0 (Request, Response, Error) and MCP Tool structures (`McpTool`, `McpTextContent`, `McpCallToolResult`, `WorkerSummary`). |
| `jsonrpc.rs` | Parsing, serialization, and error response creation for line-delimited and networked JSON-RPC streams. |
| `mcp_client.rs` | Async HTTP client connecting to `mind-mcp` (HTTP SSE or REST bridge on port 8765) exposing high-level calls (`list_workers`, `get_terminal_screen`, `send_terminal_input`, `interrupt_and_inject`, `check_account_quotas`, `notify_coordinator_worker_idle`, `notify_coordinator_help`, `check_coordinator_alarms`). |
| `mcp_server.rs` | Embedded high-performance MCP server (`EmbeddedMcpServer`) operating over standard input/output (stdio), native Tokio HTTP, and SSE streaming on port 8765. Implements standard MCP tools (`list_workers`, `get_terminal_screen`, `send_terminal_input`, etc.) via the `McpBackend` trait. |
