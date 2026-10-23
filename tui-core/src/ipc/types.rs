use serde::{Deserialize, Serialize};
use serde_json::Value;

/// JSON-RPC 2.0 Request object.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    pub id: Value,
    pub method: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub params: Option<Value>,
}

impl JsonRpcRequest {
    pub fn new(id: impl Into<Value>, method: impl Into<String>, params: Option<Value>) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            id: id.into(),
            method: method.into(),
            params,
        }
    }
}

/// JSON-RPC 2.0 Response object.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcResponse {
    pub jsonrpc: String,
    pub id: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<JsonRpcError>,
}

impl JsonRpcResponse {
    pub fn ok(id: impl Into<Value>, result: Value) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            id: id.into(),
            result: Some(result),
            error: None,
        }
    }

    pub fn err(id: impl Into<Value>, error: JsonRpcError) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            id: id.into(),
            result: None,
            error: Some(error),
        }
    }
}

/// JSON-RPC 2.0 Error object.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcError {
    pub code: i64,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

impl JsonRpcError {
    pub fn new(code: i64, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            data: None,
        }
    }

    pub fn invalid_params(msg: impl Into<String>) -> Self {
        Self::new(-32602, msg)
    }

    pub fn method_not_found(msg: impl Into<String>) -> Self {
        Self::new(-32601, msg)
    }

    pub fn internal(msg: impl Into<String>) -> Self {
        Self::new(-32603, msg)
    }
}

/// Model Context Protocol (MCP) Tool definition.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpTool {
    pub name: String,
    pub description: Option<String>,
    #[serde(rename = "inputSchema")]
    pub input_schema: Value,
}

/// MCP Text content piece.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpTextContent {
    #[serde(rename = "type")]
    pub content_type: String,
    pub text: String,
}

impl McpTextContent {
    pub fn text(t: impl Into<String>) -> Self {
        Self {
            content_type: "text".to_string(),
            text: t.into(),
        }
    }
}

/// MCP Tool call response result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpCallToolResult {
    pub content: Vec<McpTextContent>,
    #[serde(rename = "isError", skip_serializing_if = "Option::is_none")]
    pub is_error: Option<bool>,
}

impl McpCallToolResult {
    pub fn ok(text: impl Into<String>) -> Self {
        Self {
            content: vec![McpTextContent::text(text)],
            is_error: None,
        }
    }

    pub fn error(text: impl Into<String>) -> Self {
        Self {
            content: vec![McpTextContent::text(text)],
            is_error: Some(true),
        }
    }
}

/// Agent / Worker profile details.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkerSummary {
    pub worker_id: String,
    pub slot_id: String,
    pub task: Option<String>,
    pub status: String,
    pub is_alive: bool,
    pub pid: Option<u32>,
    pub buffer_version: u64,
}
