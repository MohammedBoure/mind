use std::sync::Arc;
use serde_json::json;
use tui_core::ipc::jsonrpc::{parse_jsonrpc, serialize_request, serialize_response};
use tui_core::ipc::mcp_server::EmbeddedMcpServer;
use tui_core::ipc::types::{JsonRpcRequest, JsonRpcResponse};
use tui_core::session::SessionManager;

#[tokio::test]
async fn test_jsonrpc_serialization() {
    let req = JsonRpcRequest::new(1, "tools/list", None);
    let serialized = serialize_request(&req).expect("Failed to serialize");
    assert!(serialized.contains("tools/list"));

    let parsed = parse_jsonrpc(&serialized).expect("Failed to parse");
    assert_eq!(parsed["method"], "tools/list");

    let resp = JsonRpcResponse::ok(1, json!({"status": "ok"}));
    let resp_str = serialize_response(&resp).expect("Failed to serialize response");
    assert!(resp_str.contains("status"));
}

#[tokio::test]
async fn test_embedded_mcp_server_dispatch() {
    let manager = Arc::new(SessionManager::new());
    let server = EmbeddedMcpServer::new(manager);

    // Test initialize
    let init_req = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}"#;
    let resp = server.handle_message(init_req).await.expect("Expected response");
    assert!(resp.result.is_some());

    // Test tools/list
    let list_req = r#"{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}"#;
    let resp2 = server.handle_message(list_req).await.expect("Expected response");
    let result = resp2.result.expect("Expected result");
    let tools = result["tools"].as_array().expect("Tools array");
    assert!(tools.iter().any(|t| t["name"] == "list_workers"));
    assert!(tools.iter().any(|t| t["name"] == "get_terminal_screen"));
    assert!(tools.iter().any(|t| t["name"] == "send_terminal_input"));
}
