use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use async_trait::async_trait;
use parking_lot::Mutex;
use serde_json::{json, Value};
use tracing::warn;

use crate::error::{Result, TuiError};
use crate::events::types::AlarmEvent;
use crate::ipc::mcp_server::McpBackend;
use crate::ipc::types::WorkerSummary;
use crate::session::worker::{WorkerSession, WorkerState};

/// Central manager orchestrating multi-agent PTY sessions, active tab switching,
/// coordinator alarm routing, and MCP bridge tools.
pub struct SessionManager {
    sessions: Arc<Mutex<Vec<Arc<WorkerSession>>>>,
    active_index: Arc<Mutex<usize>>,
    alarms: Arc<Mutex<Vec<AlarmEvent>>>,
}

impl Default for SessionManager {
    fn default() -> Self {
        Self::new()
    }
}

impl SessionManager {
    /// Initialize an empty session manager.
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(Mutex::new(Vec::new())),
            active_index: Arc::new(Mutex::new(0)),
            alarms: Arc::new(Mutex::new(Vec::new())),
        }
    }

    /// Spawn and register a new worker session.
    pub fn spawn_session(
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
        let session = Arc::new(WorkerSession::spawn(
            id, slot_id, command, args, cwd, env, rows, cols,
        )?);

        let mut list = self.sessions.lock();
        list.push(Arc::clone(&session));
        Ok(session)
    }

    /// Retrieve all registered sessions in order.
    pub fn list_sessions(&self) -> Vec<Arc<WorkerSession>> {
        self.sessions.lock().clone()
    }

    /// Find session by worker ID or slot ID.
    pub fn get_session(&self, id: &str) -> Option<Arc<WorkerSession>> {
        let list = self.sessions.lock();
        list.iter()
            .find(|s| s.id == id || s.slot_id == id)
            .cloned()
    }

    /// Get currently active (focused) worker session.
    pub fn active_session(&self) -> Option<Arc<WorkerSession>> {
        let list = self.sessions.lock();
        if list.is_empty() {
            return None;
        }
        let idx = *self.active_index.lock();
        list.get(idx).cloned().or_else(|| list.first().cloned())
    }

    /// Get index of currently active session.
    pub fn active_index(&self) -> usize {
        *self.active_index.lock()
    }

    /// Switch focus to session at specified index.
    pub fn select_index(&self, index: usize) -> bool {
        let list = self.sessions.lock();
        if index < list.len() {
            *self.active_index.lock() = index;
            true
        } else {
            false
        }
    }

    /// Switch focus to next session tab.
    pub fn next_session(&self) {
        let list = self.sessions.lock();
        if !list.is_empty() {
            let mut idx = self.active_index.lock();
            *idx = (*idx + 1) % list.len();
        }
    }

    /// Switch focus to previous session tab.
    pub fn prev_session(&self) {
        let list = self.sessions.lock();
        if !list.is_empty() {
            let mut idx = self.active_index.lock();
            *idx = if *idx == 0 { list.len() - 1 } else { *idx - 1 };
        }
    }

    /// Broadcast terminal resize geometry across all active PTY instances.
    pub fn broadcast_resize(&self, rows: u16, cols: u16) {
        let list = self.sessions.lock();
        for session in list.iter() {
            if let Err(e) = session.resize(rows, cols) {
                warn!("Failed to resize session '{}': {}", session.id, e);
            }
        }
    }

    /// Push an alarm event into the coordinator queue.
    pub fn push_alarm(&self, alarm: AlarmEvent) {
        self.alarms.lock().push(alarm);
    }
}

#[async_trait]
impl McpBackend for SessionManager {
    async fn list_workers(&self) -> Result<Vec<WorkerSummary>> {
        let list = self.sessions.lock();
        Ok(list.iter().map(|s| s.summary()).collect())
    }

    async fn get_terminal_screen(&self, worker_id: &str, lines: usize) -> Result<String> {
        let session = self
            .get_session(worker_id)
            .ok_or_else(|| TuiError::SessionNotFound(worker_id.to_string()))?;
        Ok(session.get_screen_text(lines))
    }

    async fn send_terminal_input(&self, worker_id: &str, text: &str, press_enter: bool) -> Result<String> {
        let session = self
            .get_session(worker_id)
            .ok_or_else(|| TuiError::SessionNotFound(worker_id.to_string()))?;
        session.send_input(text, press_enter)?;
        Ok(format!("Input delivered to worker '{}'", worker_id))
    }

    async fn interrupt_and_inject(
        &self,
        worker_id: &str,
        sender_id: &str,
        message: &str,
        priority: &str,
    ) -> Result<String> {
        let session = self
            .get_session(worker_id)
            .ok_or_else(|| TuiError::SessionNotFound(worker_id.to_string()))?;

        session.send_interrupt()?;

        // Short asynchronous pause to let the prompt settle cleanly
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;

        let directive = format!("[DIRECTIVE from {} (priority: {})]: {}\n", sender_id, priority, message);
        session.send_input(&directive, true)?;

        self.push_alarm(AlarmEvent {
            worker_id: worker_id.to_string(),
            alarm_type: "INJECTED".to_string(),
            message: format!("Directive injected from {}", sender_id),
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
        });

        Ok(format!("Interrupt and directive successfully delivered to '{}'", worker_id))
    }

    async fn check_account_quotas(&self, slot: &str) -> Result<Value> {
        let list = self.sessions.lock();
        let slots: Vec<String> = if slot.is_empty() {
            list.iter().map(|s| s.slot_id.clone()).collect()
        } else {
            vec![slot.to_string()]
        };

        let mut results = Vec::new();
        for s in slots {
            results.push(json!({
                "slot": s,
                "hourly_remaining": 100,
                "weekly_remaining": 2000,
                "status": "NORMAL",
                "progress_bar": "[██████████] 100%"
            }));
        }

        Ok(json!(results))
    }

    async fn notify_coordinator_worker_idle(&self, worker_id: &str, status_summary: &str) -> Result<String> {
        self.push_alarm(AlarmEvent {
            worker_id: worker_id.to_string(),
            alarm_type: "IDLE".to_string(),
            message: status_summary.to_string(),
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
        });

        if let Some(session) = self.get_session(worker_id) {
            *session.state.lock() = WorkerState::Idle;
        }

        Ok(format!("Coordinator notified: worker '{}' is IDLE", worker_id))
    }

    async fn notify_coordinator_help(&self, worker_id: &str, reason: &str, priority: &str) -> Result<String> {
        self.push_alarm(AlarmEvent {
            worker_id: worker_id.to_string(),
            alarm_type: "HELP".to_string(),
            message: format!("[Priority {}] {}", priority, reason),
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
        });

        Ok(format!("Coordinator alerted: assistance needed for '{}'", worker_id))
    }

    async fn check_coordinator_alarms(&self) -> Result<Vec<Value>> {
        let mut list = self.alarms.lock();
        let drained: Vec<Value> = list
            .drain(..)
            .map(|a| serde_json::to_value(a).unwrap_or(Value::Null))
            .collect();
        Ok(drained)
    }

    async fn get_agent_profile(&self, agent_id: &str) -> Result<Value> {
        let session = self.get_session(agent_id);
        let task = session.and_then(|s| s.task.lock().clone());

        Ok(json!({
            "agent_id": agent_id,
            "role": "Autonomous Worker Agent",
            "task": task.unwrap_or_else(|| "General task processing".to_string()),
            "status": "ACTIVE",
            "instance_dir": format!("~/.local/share/agy-instances/{}", agent_id)
        }))
    }
}
