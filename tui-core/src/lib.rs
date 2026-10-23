pub mod error;
pub mod events;
pub mod ipc;
pub mod pty;
pub mod session;
pub mod ui;

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use parking_lot::Mutex;

pub use error::{Result, TuiError};
pub use events::{AlarmEvent, AppEvent, EventLoop};
pub use ipc::{
    EmbeddedMcpServer, JsonRpcError, JsonRpcRequest, JsonRpcResponse, McpBackend, McpCallToolResult,
    McpClient, McpTool, WorkerSummary,
};
pub use pty::{CellColor, PtyConfig, PtyMaster, PtyProcess, ScreenBuffer, ScreenCell};
pub use session::{SessionManager, WorkerSession, WorkerState};
pub use ui::{
    AlertBadge, GaugeLayout, QuotaGaugesWidget, SplitMode, SplitPanesWidget, StatusBarWidget,
    TerminalScreenWidget, Theme, WorkerListItem, WorkerListWidget,
};

/// High-performance compiled TUI core engine binding PTY master processes,
/// Tokio event loop, and Model Context Protocol (MCP) bridge.
pub struct TuiEngine {
    pub session_manager: Arc<SessionManager>,
    pub event_loop: Arc<Mutex<EventLoop>>,
    pub mcp_client: McpClient,
    pub mcp_server: Arc<EmbeddedMcpServer>,
}

impl Default for TuiEngine {
    fn default() -> Self {
        Self::new(50, "http://127.0.0.1:8765")
    }
}

impl TuiEngine {
    /// Initialize a new TUI engine instance with specified tick interval and MCP bridge URL.
    pub fn new(tick_ms: u64, mcp_url: impl Into<String>) -> Self {
        let session_manager = Arc::new(SessionManager::new());
        let event_loop = Arc::new(Mutex::new(EventLoop::new(tick_ms)));
        let mcp_client = McpClient::new(mcp_url);
        let mcp_server = Arc::new(EmbeddedMcpServer::new(Arc::clone(&session_manager) as Arc<dyn McpBackend>));

        Self {
            session_manager,
            event_loop,
            mcp_client,
            mcp_server,
        }
    }

    /// Spawn a new worker session inside the engine.
    pub fn spawn_worker(
        &self,
        id: impl Into<String>,
        slot_id: impl Into<String>,
        command: impl Into<String>,
        args: Vec<String>,
        cwd: Option<PathBuf>,
        env: HashMap<String, String>,
        rows: u16,
        cols: u16,
    ) -> Result<Arc<WorkerSession>> {
        self.session_manager
            .spawn_session(id, slot_id, command, args, cwd, env, rows, cols)
    }

    /// Retrieve the currently active / focused worker session.
    pub fn active_session(&self) -> Option<Arc<WorkerSession>> {
        self.session_manager.active_session()
    }

    /// Retrieve all managed worker sessions.
    pub fn sessions(&self) -> Vec<Arc<WorkerSession>> {
        self.session_manager.list_sessions()
    }

    /// Send input to the currently active worker session.
    pub fn send_input_to_active(&self, text: &str, press_enter: bool) -> Result<()> {
        if let Some(session) = self.active_session() {
            session.send_input(text, press_enter)
        } else {
            Err(TuiError::SessionNotFound("No active session".to_string()))
        }
    }

    /// Send SIGINT interrupt (Ctrl+C) to the currently active worker.
    pub fn interrupt_active(&self) -> Result<()> {
        if let Some(session) = self.active_session() {
            session.send_interrupt()
        } else {
            Err(TuiError::SessionNotFound("No active session".to_string()))
        }
    }

    /// Await the next event from the unified Tokio event loop.
    pub async fn next_event(&self) -> Option<AppEvent> {
        let mut loop_lock = self.event_loop.lock();
        loop_lock.next().await
    }

    /// Broadcast terminal dimensions update across all PTY sessions.
    pub fn resize_all(&self, rows: u16, cols: u16) {
        self.session_manager.broadcast_resize(rows, cols);
    }
}
