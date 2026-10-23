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
use crate::session::session_store::{SessionRecord, SessionStore, SessionWorkerConfig};
use crate::session::worker::{WorkerSession, WorkerState};

/// Central manager orchestrating multi-agent PTY sessions, active tab switching,
/// coordinator alarm routing, and MCP bridge tools.
pub struct SessionManager {
    sessions: Arc<Mutex<Vec<Arc<WorkerSession>>>>,
    active_index: Arc<Mutex<usize>>,
    alarms: Arc<Mutex<Vec<AlarmEvent>>>,
    store: Arc<SessionStore>,
    current_session_name: Arc<Mutex<Option<String>>>,
}

impl Default for SessionManager {
    fn default() -> Self {
        Self::new()
    }
}

impl SessionManager {
    /// Initialize an empty session manager with default session store.
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(Mutex::new(Vec::new())),
            active_index: Arc::new(Mutex::new(0)),
            alarms: Arc::new(Mutex::new(Vec::new())),
            store: Arc::new(SessionStore::new()),
            current_session_name: Arc::new(Mutex::new(None)),
        }
    }

    /// Initialize session manager with a custom session store.
    pub fn with_store(store: SessionStore) -> Self {
        Self {
            sessions: Arc::new(Mutex::new(Vec::new())),
            active_index: Arc::new(Mutex::new(0)),
            alarms: Arc::new(Mutex::new(Vec::new())),
            store: Arc::new(store),
            current_session_name: Arc::new(Mutex::new(None)),
        }
    }

    /// Access reference to underlying persistent SessionStore.
    pub fn store(&self) -> Arc<SessionStore> {
        Arc::clone(&self.store)
    }

    /// Name of currently active session, if any.
    pub fn current_session_name(&self) -> Option<String> {
        self.current_session_name.lock().clone()
    }

    /// Set name of currently active session.
    pub fn set_current_session_name(&self, name: Option<String>) {
        *self.current_session_name.lock() = name;
    }

    /// Load and restore a session from persistent storage into running worker tabs.
    pub fn load_and_restore_session(
        &self,
        name: &str,
        default_cmd: &str,
        rows: u16,
        cols: u16,
    ) -> Result<SessionRecord> {
        let session_record = self
            .store
            .get_session(name)?
            .ok_or_else(|| TuiError::SessionNotFound(format!("Session '{}' does not exist", name)))?;

        // Clear currently running sessions
        self.sessions.lock().clear();
        *self.active_index.lock() = 0;

        for w_cfg in &session_record.workers {
            let cmd = w_cfg.command.as_deref().unwrap_or(default_cmd);
            let args = w_cfg.args.clone().unwrap_or_default();
            let env = w_cfg.env.clone().unwrap_or_default();

            let worker = self.spawn_session(
                &w_cfg.id,
                &w_cfg.slot_id,
                cmd,
                args,
                None,
                env,
                rows,
                cols,
            )?;

            worker.set_role(&w_cfg.role);
            worker.set_model(&w_cfg.model);
            worker.set_task(w_cfg.task.clone());
        }

        *self.current_session_name.lock() = Some(name.to_string());
        let _ = self.store.touch_activity(name, 0, 1);

        Ok(session_record)
    }

    /// Create, persist, and launch a new multi-agent session.
    pub fn create_and_launch_session(
        &self,
        name: &str,
        default_cmd: &str,
        rows: u16,
        cols: u16,
    ) -> Result<SessionRecord> {
        let record = self.store.create_default_session(name);
        self.store.save_session(&record)?;
        self.load_and_restore_session(name, default_cmd, rows, cols)
    }

    /// Save state of current running workers into the persistent session file.
    pub fn save_current_session(&self) -> Result<Option<PathBuf>> {
        let name = match self.current_session_name() {
            Some(n) => n,
            None => return Ok(None),
        };

        let mut record = self
            .store
            .get_session(&name)?
            .unwrap_or_else(|| SessionRecord::new(&name, ""));

        let current_workers = self.list_sessions();
        record.workers.clear();

        for w in &current_workers {
            record.workers.push(SessionWorkerConfig {
                id: w.id.clone(),
                slot_id: w.slot_id.clone(),
                role: w.role(),
                model: w.model(),
                task: w.task.lock().clone(),
                command: None,
                args: None,
                env: None,
            });
        }
        record.agent_count = record.workers.len();

        let path = self.store.save_session(&record)?;
        Ok(Some(path))
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

    /// Gracefully terminate and clean up all running worker PTY sessions.
    pub fn shutdown_all(&self) {
        let list = self.sessions.lock();
        for session in list.iter() {
            let _ = session.kill();
        }
    }

    /// Push an alarm event into the coordinator queue and update the target session.
    pub fn push_alarm(&self, alarm: AlarmEvent) {
        if let Some(session) = self.get_session(&alarm.worker_id) {
            session.set_last_alarm(Some(alarm.clone()));
        }
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
