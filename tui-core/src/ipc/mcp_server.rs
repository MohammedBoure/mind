use std::sync::Arc;
use async_trait::async_trait;
use serde_json::{json, Value};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tracing::info;

use crate::error::{Result, TuiError};
use crate::ipc::jsonrpc::{create_error_response, parse_jsonrpc, serialize_response};
use crate::ipc::types::{
    JsonRpcError, JsonRpcResponse, McpCallToolResult, McpTool, WorkerSummary,
};

/// Trait defining the core backend capabilities exposed via MCP tools.
#[async_trait]
pub trait McpBackend: Send + Sync {
    async fn list_workers(&self) -> Result<Vec<WorkerSummary>>;
    async fn get_terminal_screen(&self, worker_id: &str, lines: usize) -> Result<String>;
    async fn send_terminal_input(&self, worker_id: &str, text: &str, press_enter: bool) -> Result<String>;
    async fn interrupt_and_inject(
        &self,
        worker_id: &str,
        sender_id: &str,
        message: &str,
        priority: &str,
    ) -> Result<String>;
    async fn check_account_quotas(&self, slot: &str) -> Result<Value>;
    async fn notify_coordinator_worker_idle(&self, worker_id: &str, status_summary: &str) -> Result<String>;
    async fn notify_coordinator_help(&self, worker_id: &str, reason: &str, priority: &str) -> Result<String>;
    async fn check_coordinator_alarms(&self) -> Result<Vec<Value>>;
    async fn get_agent_profile(&self, agent_id: &str) -> Result<Value>;
}

/// Embedded Model Context Protocol (MCP) server handling JSON-RPC 2.0 requests over stdio, HTTP, and SSE.
#[derive(Clone)]
pub struct EmbeddedMcpServer {
    backend: Arc<dyn McpBackend>,
}

impl EmbeddedMcpServer {
    pub fn new(backend: Arc<dyn McpBackend>) -> Self {
        Self { backend }
    }

    /// List tools supported by this MCP server.
    pub fn get_tools(&self) -> Vec<McpTool> {
        vec![
            McpTool {
                name: "list_workers".to_string(),
                description: Some("Inspect active worker tabs, agent IDs, and process status.".to_string()),
                input_schema: json!({ "type": "object", "properties": {} }),
            },
            McpTool {
                name: "get_terminal_screen".to_string(),
                description: Some("Read rendered clean text from any worker terminal.".to_string()),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "worker_id": { "type": "string" },
                        "lines": { "type": "integer", "default": 50 }
                    },
                    "required": ["worker_id"]
                }),
            },
            McpTool {
                name: "send_terminal_input".to_string(),
                description: Some("Send input or commands directly to a worker terminal. By default, executes immediately by pressing Enter.".to_string()),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "worker_id": { "type": "string", "description": "Worker ID, slot ID (e.g. 'agy11'), or tab number" },
                        "text": { "type": "string", "description": "The command or prompt text to send" },
                        "press_enter": { "type": "boolean", "default": true, "description": "Press Enter immediately to submit and execute the prompt (default: true)" }
                    },
                    "required": ["worker_id", "text"]
                }),
            },
            McpTool {
                name: "interrupt_and_inject".to_string(),
                description: Some("Send SIGINT (Ctrl+C) to pause ongoing actions and inject directives.".to_string()),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "worker_id": { "type": "string" },
                        "sender_id": { "type": "string", "default": "coordinator" },
                        "message": { "type": "string" },
                        "priority": { "type": "string", "default": "high" }
                    },
                    "required": ["worker_id", "message"]
                }),
            },
            McpTool {
                name: "check_account_quotas".to_string(),
                description: Some("Inspect account quota consumption, hourly/weekly steps.".to_string()),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "slot": { "type": "string", "default": "" }
                    }
                }),
            },
            McpTool {
                name: "notify_coordinator_worker_idle".to_string(),
                description: Some("Dispatch immediate wake-up alarm to coordinator on worker completion.".to_string()),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "worker_id": { "type": "string" },
                        "status_summary": { "type": "string", "default": "" }
                    },
                    "required": ["worker_id"]
                }),
            },
            McpTool {
                name: "notify_coordinator_help".to_string(),
                description: Some("Dispatch urgent assistance alarm to coordinator.".to_string()),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "worker_id": { "type": "string" },
                        "reason": { "type": "string" },
                        "priority": { "type": "string", "default": "high" }
                    },
                    "required": ["worker_id", "reason"]
                }),
            },
            McpTool {
                name: "check_coordinator_alarms".to_string(),
                description: Some("Inspect queued wake-up alarms and worker completion events.".to_string()),
                input_schema: json!({ "type": "object", "properties": {} }),
            },
            McpTool {
                name: "get_agent_profile".to_string(),
                description: Some("Query agent role, principles, instructions, and config.".to_string()),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "agent_id": { "type": "string" }
                    },
                    "required": ["agent_id"]
                }),
            },
        ]
    }

    /// Process a single incoming JSON-RPC 2.0 message string.
    pub async fn handle_message(&self, raw: &str) -> Option<JsonRpcResponse> {
        let val: Value = match parse_jsonrpc(raw) {
            Ok(v) => v,
            Err(e) => {
                return Some(create_error_response(Value::Null, -32700, format!("Parse error: {}", e)));
            }
        };

        let id = val.get("id").cloned().unwrap_or(Value::Null);
        let method = match val.get("method").and_then(Value::as_str) {
            Some(m) => m,
            None => {
                return Some(create_error_response(id, -32600, "Missing 'method' string"));
            }
        };

        let params = val.get("params").cloned().unwrap_or(Value::Null);

        if method.starts_with("notifications/") {
            return None;
        }

        match method {
            "initialize" => {
                Some(JsonRpcResponse::ok(id, json!({
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": { "listChanged": false },
                        "prompts": { "listChanged": false },
                        "resources": { "subscribe": false, "listChanged": false }
                    },
                    "serverInfo": {
                        "name": "mind-mcp-engine",
                        "version": "0.1.0"
                    }
                })))
            }
            "tools/list" => {
                let tools = self.get_tools();
                Some(JsonRpcResponse::ok(id, json!({ "tools": tools })))
            }
            "tools/call" => {
                let tool_name = params.get("name").and_then(Value::as_str).unwrap_or_default();
                let arguments = params.get("arguments").cloned().unwrap_or(json!({}));
                let res = self.dispatch_tool(tool_name, arguments).await;
                match res {
                    Ok(tool_result) => Some(JsonRpcResponse::ok(id, serde_json::to_value(tool_result).unwrap_or(Value::Null))),
                    Err(e) => Some(JsonRpcResponse::ok(id, serde_json::to_value(McpCallToolResult::error(e.to_string())).unwrap_or(Value::Null))),
                }
            }
            "resources/list" => Some(JsonRpcResponse::ok(id, json!({ "resources": [] }))),
            "prompts/list" => Some(JsonRpcResponse::ok(id, json!({ "prompts": [] }))),
            "ping" => Some(JsonRpcResponse::ok(id, json!({}))),
            _ => Some(JsonRpcResponse::err(id, JsonRpcError::method_not_found(format!("Unknown method: {}", method)))),
        }
    }

    /// Dispatch a named tool invocation to the backend.
    pub async fn dispatch_tool(&self, name: &str, args: Value) -> Result<McpCallToolResult> {
        match name {
            "list_workers" => {
                let workers = self.backend.list_workers().await?;
                let text = serde_json::to_string_pretty(&workers)?;
                Ok(McpCallToolResult::ok(text))
            }
            "get_terminal_screen" => {
                let worker_id = args.get("worker_id").and_then(Value::as_str).unwrap_or_default();
                let lines = args.get("lines").and_then(Value::as_u64).unwrap_or(50) as usize;
                let screen = self.backend.get_terminal_screen(worker_id, lines).await?;
                Ok(McpCallToolResult::ok(screen))
            }
            "send_terminal_input" => {
                let worker_id = args.get("worker_id").and_then(Value::as_str).unwrap_or_default();
                let text = args.get("text").and_then(Value::as_str).unwrap_or_default();
                let press_enter = args.get("press_enter").and_then(Value::as_bool).unwrap_or(true);
                let res = self.backend.send_terminal_input(worker_id, text, press_enter).await?;
                Ok(McpCallToolResult::ok(res))
            }
            "interrupt_and_inject" => {
                let worker_id = args.get("worker_id").and_then(Value::as_str).unwrap_or_default();
                let sender_id = args.get("sender_id").and_then(Value::as_str).unwrap_or("coordinator");
                let message = args.get("message").and_then(Value::as_str).unwrap_or_default();
                let priority = args.get("priority").and_then(Value::as_str).unwrap_or("high");
                let res = self.backend.interrupt_and_inject(worker_id, sender_id, message, priority).await?;
                Ok(McpCallToolResult::ok(res))
            }
            "check_account_quotas" => {
                let slot = args.get("slot").and_then(Value::as_str).unwrap_or_default();
                let quotas = self.backend.check_account_quotas(slot).await?;
                let text = serde_json::to_string_pretty(&quotas)?;
                Ok(McpCallToolResult::ok(text))
            }
            "notify_coordinator_worker_idle" => {
                let worker_id = args.get("worker_id").and_then(Value::as_str).unwrap_or_default();
                let status_summary = args.get("status_summary").and_then(Value::as_str).unwrap_or_default();
                let res = self.backend.notify_coordinator_worker_idle(worker_id, status_summary).await?;
                Ok(McpCallToolResult::ok(res))
            }
            "notify_coordinator_help" => {
                let worker_id = args.get("worker_id").and_then(Value::as_str).unwrap_or_default();
                let reason = args.get("reason").and_then(Value::as_str).unwrap_or_default();
                let priority = args.get("priority").and_then(Value::as_str).unwrap_or("high");
                let res = self.backend.notify_coordinator_help(worker_id, reason, priority).await?;
                Ok(McpCallToolResult::ok(res))
            }
            "check_coordinator_alarms" => {
                let alarms = self.backend.check_coordinator_alarms().await?;
                let text = serde_json::to_string_pretty(&alarms)?;
                Ok(McpCallToolResult::ok(text))
            }
            "get_agent_profile" => {
                let agent_id = args.get("agent_id").and_then(Value::as_str).unwrap_or_default();
                let profile = self.backend.get_agent_profile(agent_id).await?;
                let text = serde_json::to_string_pretty(&profile)?;
                Ok(McpCallToolResult::ok(text))
            }
            _ => Err(TuiError::Ipc(format!("Tool '{}' not implemented", name))),
        }
    }

    /// Run the MCP server over standard input and output streams.
    pub async fn run_stdio(&self) -> Result<()> {
        info!("Starting embedded MCP server in stdio mode");
        let stdin = tokio::io::stdin();
        let mut stdout = tokio::io::stdout();
        let mut reader = BufReader::new(stdin).lines();

        while let Some(line) = reader.next_line().await? {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            if let Some(resp) = self.handle_message(line).await {
                let json_str = serialize_response(&resp)?;
                stdout.write_all(json_str.as_bytes()).await?;
                stdout.write_all(b"\n").await?;
                stdout.flush().await?;
            }
        }

        Ok(())
    }

    /// Run the embedded MCP server over HTTP and SSE on the specified address (e.g. "127.0.0.1:8765").
    pub async fn run_http(&self, bind_addr: &str) -> Result<()> {
        let listener = tokio::net::TcpListener::bind(bind_addr).await?;
        info!("Embedded MCP HTTP/SSE server listening on {}", bind_addr);

        let (sse_tx, _) = tokio::sync::broadcast::channel::<String>(100);
        let sse_tx = Arc::new(sse_tx);

        loop {
            let (mut socket, _) = match listener.accept().await {
                Ok(conn) => conn,
                Err(e) => {
                    tracing::warn!("MCP accept error: {}", e);
                    continue;
                }
            };

            let server_backend = Arc::clone(&self.backend);
            let sse_broadcast = Arc::clone(&sse_tx);

            tokio::spawn(async move {
                let (reader, mut writer) = socket.split();
                let mut buf_reader = BufReader::new(reader);
                let mut line = String::new();

                // Read request line
                if buf_reader.read_line(&mut line).await.unwrap_or(0) == 0 {
                    return;
                }

                let (method, path) = {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if parts.len() < 2 {
                        return;
                    }
                    (parts[0].to_string(), parts[1].to_string())
                };

                // Read headers
                let mut content_length: usize = 0;
                loop {
                    line.clear();
                    if buf_reader.read_line(&mut line).await.unwrap_or(0) == 0 {
                        break;
                    }
                    if line == "\r\n" || line == "\n" {
                        break;
                    }
                    if line.to_lowercase().starts_with("content-length:") {
                        if let Some(val_str) = line.split(':').nth(1) {
                            content_length = val_str.trim().parse::<usize>().unwrap_or(0);
                        }
                    }
                }

                // Handle CORS preflight
                if method == "OPTIONS" {
                    let resp = "HTTP/1.1 204 No Content\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET, POST, OPTIONS\r\nAccess-Control-Allow-Headers: *\r\n\r\n";
                    let _ = writer.write_all(resp.as_bytes()).await;
                    return;
                }

                // Route 1: GET /sse -> Server-Sent Events stream for Antigravity
                if method == "GET" && (path == "/sse" || path.starts_with("/sse?") || path.starts_with("/sse/")) {
                    let mut rx = sse_broadcast.subscribe();
                    let init_header = "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\nConnection: keep-alive\r\nAccess-Control-Allow-Origin: *\r\n\r\nevent: endpoint\r\ndata: /message?session_id=1\r\n\r\n";
                    if writer.write_all(init_header.as_bytes()).await.is_err() {
                        return;
                    }

                    loop {
                        tokio::select! {
                            msg = rx.recv() => {
                                match msg {
                                    Ok(data) => {
                                        let chunk = format!("event: message\ndata: {}\n\n", data);
                                        if writer.write_all(chunk.as_bytes()).await.is_err() {
                                            break;
                                        }
                                    }
                                    Err(_) => break,
                                }
                            }
                            _ = tokio::time::sleep(tokio::time::Duration::from_secs(15)) => {
                                if writer.write_all(b": keepalive\n\n").await.is_err() {
                                    break;
                                }
                            }
                        }
                    }
                    return;
                }

                // Route 2: POST /message or POST /api/call-tool or POST /
                if method == "POST" {
                    let mut body_bytes = vec![0u8; content_length];
                    if content_length > 0 {
                        use tokio::io::AsyncReadExt;
                        if buf_reader.read_exact(&mut body_bytes).await.is_err() {
                            return;
                        }
                    }
                    let body_str = String::from_utf8_lossy(&body_bytes);

                    if path.starts_with("/api/call-tool") {
                        let mcp_srv = EmbeddedMcpServer::new(server_backend);
                        let val: Value = serde_json::from_str(&body_str).unwrap_or(Value::Null);
                        let tool_name = val.get("name").and_then(Value::as_str).unwrap_or("");
                        let args = val.get("arguments").cloned().unwrap_or(json!({}));
                        match mcp_srv.dispatch_tool(tool_name, args).await {
                            Ok(res) => {
                                let res_val = json!({
                                    "success": true,
                                    "result": res.content.first().map(|c| c.text.clone()).unwrap_or_default()
                                });
                                let body = res_val.to_string();
                                let resp = format!(
                                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: {}\r\n\r\n{}",
                                    body.len(),
                                    body
                                );
                                let _ = writer.write_all(resp.as_bytes()).await;
                            }
                            Err(e) => {
                                let res_val = json!({ "success": false, "error": e.to_string() });
                                let body = res_val.to_string();
                                let resp = format!(
                                    "HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: {}\r\n\r\n{}",
                                    body.len(),
                                    body
                                );
                                let _ = writer.write_all(resp.as_bytes()).await;
                            }
                        }
                        return;
                    }

                    // Otherwise JSON-RPC message over HTTP/SSE
                    let mcp_srv = EmbeddedMcpServer::new(server_backend);
                    if let Some(resp) = mcp_srv.handle_message(&body_str).await {
                        let json_str = serialize_response(&resp).unwrap_or_default();
                        let _ = sse_broadcast.send(json_str.clone());
                        let resp_http = format!(
                            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: {}\r\n\r\n{}",
                            json_str.len(),
                            json_str
                        );
                        let _ = writer.write_all(resp_http.as_bytes()).await;
                    } else {
                        let resp_http = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: 2\r\n\r\n{}\r\n";
                        let _ = writer.write_all(resp_http.as_bytes()).await;
                    }
                    return;
                }

                // Default health check for GET / or GET /health
                let health_body = json!({ "status": "ok", "service": "mind-mcp", "port": 8765 }).to_string();
                let resp = format!(
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: {}\r\n\r\n{}",
                    health_body.len(),
                    health_body
                );
                let _ = writer.write_all(resp.as_bytes()).await;
            });
        }
    }
}
