pub mod jsonrpc;
pub mod mcp_client;
pub mod mcp_server;
pub mod types;

pub use jsonrpc::{create_error_response, parse_jsonrpc, serialize_request, serialize_response};
pub use mcp_client::McpClient;
pub use mcp_server::{EmbeddedMcpServer, McpBackend};
pub use types::{
    JsonRpcError, JsonRpcRequest, JsonRpcResponse, McpCallToolResult, McpTextContent, McpTool,
    WorkerSummary,
};
