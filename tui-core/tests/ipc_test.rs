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

#[tokio::test]
async fn test_embedded_mcp_http_and_sse_server() {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpStream;

    let manager = Arc::new(SessionManager::new());
    let server = EmbeddedMcpServer::new(manager);

    let test_addr = "127.0.0.1:18765";
    tokio::spawn(async move {
        let _ = server.run_http(test_addr).await;
    });

    // Wait briefly for the server to bind
    tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;

    // 1. Test GET /health
    let mut stream = TcpStream::connect(test_addr).await.expect("Connect to test HTTP server");
    stream.write_all(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n").await.unwrap();

    let mut buf = vec![0u8; 1024];
    let n = stream.read(&mut buf).await.unwrap();
    let resp = String::from_utf8_lossy(&buf[..n]);
    assert!(resp.contains("200 OK"));
    assert!(resp.contains("mind-mcp"));

    // 2. Test POST /message with initialize
    let mut stream = TcpStream::connect(test_addr).await.expect("Connect to test HTTP server");
    let init_body = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}"#;
    let post_req = format!(
        "POST /message HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: {}\r\nContent-Type: application/json\r\n\r\n{}",
        init_body.len(),
        init_body
    );
    stream.write_all(post_req.as_bytes()).await.unwrap();

    let mut buf = vec![0u8; 2048];
    let n = stream.read(&mut buf).await.unwrap();
    let post_resp = String::from_utf8_lossy(&buf[..n]);
    assert!(post_resp.contains("200 OK"));
    assert!(post_resp.contains("mind-mcp-engine"));

    // 3. Test POST /message with tools/list
    let mut stream = TcpStream::connect(test_addr).await.expect("Connect to test HTTP server");
    let list_body = r#"{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}"#;
    let post_req = format!(
        "POST /message HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: {}\r\nContent-Type: application/json\r\n\r\n{}",
        list_body.len(),
        list_body
    );
    stream.write_all(post_req.as_bytes()).await.unwrap();

    let mut buf = vec![0u8; 4096];
    let n = stream.read(&mut buf).await.unwrap();
    let list_resp = String::from_utf8_lossy(&buf[..n]);
    assert!(list_resp.contains("200 OK"));
    assert!(list_resp.contains("list_workers"));
    assert!(list_resp.contains("send_terminal_input"));

    // 4. Test GET /sse stream connection and endpoint event
    let mut sse_stream = TcpStream::connect(test_addr).await.expect("Connect SSE stream");
    sse_stream.write_all(b"GET /sse HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n").await.unwrap();

    let mut sse_buf = vec![0u8; 1024];
    let n = sse_stream.read(&mut sse_buf).await.unwrap();
    let sse_resp = String::from_utf8_lossy(&sse_buf[..n]);
    assert!(sse_resp.contains("text/event-stream"));
    assert!(sse_resp.contains("event: endpoint"));
    assert!(sse_resp.contains("data: /message?session_id=1"));
}
