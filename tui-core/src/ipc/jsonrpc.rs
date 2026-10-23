use serde_json::Value;

use crate::error::{Result, TuiError};
use crate::ipc::types::{JsonRpcError, JsonRpcRequest, JsonRpcResponse};

/// Parse an incoming raw JSON-RPC 2.0 message string.
pub fn parse_jsonrpc(line: &str) -> Result<serde_json::Value> {
    serde_json::from_str(line).map_err(TuiError::Serialization)
}

/// Serialize a JSON-RPC response to a single-line JSON string suitable for line-delimited stdio.
pub fn serialize_response(resp: &JsonRpcResponse) -> Result<String> {
    serde_json::to_string(resp).map_err(TuiError::Serialization)
}

/// Serialize a JSON-RPC request to a single-line JSON string.
pub fn serialize_request(req: &JsonRpcRequest) -> Result<String> {
    serde_json::to_string(req).map_err(TuiError::Serialization)
}

/// Create a standard error response.
pub fn create_error_response(id: Value, code: i64, message: impl Into<String>) -> JsonRpcResponse {
    JsonRpcResponse::err(id, JsonRpcError::new(code, message))
}
