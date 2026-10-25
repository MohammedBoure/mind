use reqwest::Client;
use serde_json::{json, Value};
use tracing::debug;

use crate::error::{Result, TuiError};
use crate::ipc::types::WorkerSummary;

/// Asynchronous client for interacting with the `mind-mcp` orchestration server.
#[derive(Debug, Clone)]
pub struct McpClient {
    base_url: String,
    http_client: Client,
}

impl McpClient {
    /// Create a new MCP client connecting to the given base URL (default: http://127.0.0.1:8765).
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
            http_client: Client::builder()
                .timeout(std::time::Duration::from_secs(10))
                .build()
                .unwrap_or_default(),
        }
    }

    /// Invoke a generic tool on the MCP bridge via HTTP POST `/api/call-tool`.
    pub async fn call_tool(&self, tool: &str, arguments: Value) -> Result<Value> {
        let url = format!("{}/api/call-tool", self.base_url.trim_end_matches('/'));
        let payload = json!({
            "name": tool,
            "arguments": arguments,
        });

        debug!("Calling MCP tool '{}' at {}", tool, url);
        let resp = self
            .http_client
            .post(&url)
            .json(&payload)
            .send()
            .await
            .map_err(TuiError::Http)?;

        if !resp.status().is_success() {
            let status = resp.status();
            let err_text = resp.text().await.unwrap_or_default();
            return Err(TuiError::Ipc(format!("MCP tool call failed ({status}): {err_text}")));
        }

        let body: Value = resp.json().await.map_err(TuiError::Http)?;
        if body.get("success").and_then(Value::as_bool) == Some(false) {
            let err = body.get("error").and_then(Value::as_str).unwrap_or("Unknown MCP error");
            return Err(TuiError::Ipc(err.to_string()));
        }

        Ok(body.get("result").cloned().unwrap_or(Value::Null))
    }

    /// Inspect active workers and their process metadata.
    pub async fn list_workers(&self) -> Result<Vec<WorkerSummary>> {
        let res = self.call_tool("list_workers", json!({})).await?;
        serde_json::from_value(res).map_err(TuiError::Serialization)
    }

    /// Fetch rendered clean text from a worker's virtual terminal buffer.
    pub async fn get_terminal_screen(&self, worker_id: &str, lines: usize) -> Result<String> {
        let res = self
            .call_tool(
                "get_terminal_screen",
                json!({ "worker_id": worker_id, "lines": lines }),
            )
            .await?;
        Ok(res.as_str().unwrap_or_default().to_string())
    }

    /// Send raw keystrokes or command to a worker's stdin.
    pub async fn send_terminal_input(&self, worker_id: &str, text: &str, press_enter: bool) -> Result<String> {
        let res = self
            .call_tool(
                "send_terminal_input",
                json!({ "worker_id": worker_id, "text": text, "press_enter": press_enter }),
            )
            .await?;
        Ok(res.as_str().unwrap_or_default().to_string())
    }

    /// Safely interrupt worker with SIGINT and inject priority directive.
    pub async fn interrupt_and_inject(
        &self,
        worker_id: &str,
        sender_id: &str,
        message: &str,
        priority: &str,
    ) -> Result<String> {
        let res = self
            .call_tool(
                "interrupt_and_inject",
                json!({
                    "worker_id": worker_id,
                    "sender_id": sender_id,
                    "message": message,
                    "priority": priority
                }),
            )
            .await?;
        Ok(res.as_str().unwrap_or_default().to_string())
    }

    /// Check quota consumption for slots.
    pub async fn check_account_quotas(&self, slot: &str) -> Result<Value> {
        self.call_tool("check_account_quotas", json!({ "slot": slot, "as_json": true })).await
    }

    /// Notify coordinator that a worker has transitioned to IDLE prompt.
    pub async fn notify_coordinator_worker_idle(&self, worker_id: &str, status_summary: &str) -> Result<String> {
        let res = self
            .call_tool(
                "notify_coordinator_worker_idle",
                json!({ "worker_id": worker_id, "status_summary": status_summary }),
            )
            .await?;
        Ok(res.as_str().unwrap_or_default().to_string())
    }

    /// Dispatch urgent help notification from worker to coordinator.
    pub async fn notify_coordinator_help(&self, worker_id: &str, reason: &str, priority: &str) -> Result<String> {
        let res = self
            .call_tool(
                "notify_coordinator_help",
                json!({ "worker_id": worker_id, "reason": reason, "priority": priority }),
            )
            .await?;
        Ok(res.as_str().unwrap_or_default().to_string())
    }

    /// Check queued coordinator alarms.
    pub async fn check_coordinator_alarms(&self) -> Result<Vec<Value>> {
        let res = self.call_tool("check_coordinator_alarms", json!({})).await?;
        Ok(res.as_array().cloned().unwrap_or_default())
    }
}
