use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use async_trait::async_trait;
use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tracing::warn;

use crate::error::{Result, TuiError};
use crate::events::types::AlarmEvent;
use crate::ipc::mcp_server::McpBackend;
use crate::ipc::types::WorkerSummary;
use crate::session::identity::IdentityDiscovery;
use crate::session::session_store::{SessionRecord, SessionStore, SessionWorkerConfig};
use crate::session::shortcuts::{AgiConfig, ShortcutEngine};
use crate::session::worker::{WorkerSession, WorkerState};

/// Pane focus tracking between Primary Coordinator terminal and Worker tab multiplexer.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FocusedPane {
    Coordinator,
    Workers(usize),
}

/// Dual Vim-style modal states for interactive terminal workspace.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AppMode {
    Normal,
    PtyInteract,
}

impl AppMode {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Normal => "NORMAL",
            Self::PtyInteract => "PTY_INTERACT",
        }
    }
}

/// Central manager orchestrating multi-agent PTY sessions, dual-pane architecture,
/// active worker tab switching, vim modal state engine, coordinator alarm routing,
/// and MCP bridge tools.
pub struct SessionManager {
    sessions: Arc<Mutex<Vec<Arc<WorkerSession>>>>,
    coordinator: Arc<Mutex<Option<Arc<WorkerSession>>>>,
    workers: Arc<Mutex<Vec<Arc<WorkerSession>>>>,
    focused_pane: Arc<Mutex<FocusedPane>>,
    app_mode: Arc<Mutex<AppMode>>,
    alarms: Arc<Mutex<Vec<AlarmEvent>>>,
    store: Arc<SessionStore>,
    current_session_name: Arc<Mutex<Option<String>>>,
    auto_spawn_agy: Arc<Mutex<bool>>,
}

impl Default for SessionManager {
    fn default() -> Self {
        Self::new()
    }
}

impl SessionManager {
    /// Initialize a session manager with default session store and configuration.
    pub fn new() -> Self {
        let config = ShortcutEngine::load_or_default();
        Self::with_config(config.config())
    }

    /// Initialize session manager with a custom session store and default configuration.
    pub fn with_store(store: SessionStore) -> Self {
        let config = ShortcutEngine::load_or_default();
        Self::with_store_and_config(store, config.config())
    }

    /// Initialize session manager with custom configuration.
    pub fn with_config(config: &AgiConfig) -> Self {
        Self::with_store_and_config(SessionStore::new(), config)
    }

    /// Initialize session manager with custom session store and custom configuration.
    pub fn with_store_and_config(store: SessionStore, config: &AgiConfig) -> Self {
        Self {
            sessions: Arc::new(Mutex::new(Vec::new())),
            coordinator: Arc::new(Mutex::new(None)),
            workers: Arc::new(Mutex::new(Vec::new())),
            focused_pane: Arc::new(Mutex::new(FocusedPane::Coordinator)),
            app_mode: Arc::new(Mutex::new(AppMode::Normal)),
            alarms: Arc::new(Mutex::new(Vec::new())),
            store: Arc::new(store),
            current_session_name: Arc::new(Mutex::new(None)),
            auto_spawn_agy: Arc::new(Mutex::new(config.general.auto_spawn_agy)),
        }
    }

    /// Whether automatic spawning of real agy CLI inside PTY terminals is enabled.
    pub fn auto_spawn_agy(&self) -> bool {
        *self.auto_spawn_agy.lock()
    }

    /// Set automatic spawning of real agy CLI.
    pub fn set_auto_spawn_agy(&self, enabled: bool) {
        *self.auto_spawn_agy.lock() = enabled;
    }

    /// Resolve effective command and arguments for a session worker.
    /// If `auto_spawn_agy` is enabled and no custom non-agy command was requested,
    /// attempts to locate executable `agys` multi-instance container or `agy` binary,
    /// falling back to system shell.
    pub fn resolve_worker_command(
        &self,
        w_cfg: &SessionWorkerConfig,
        fallback_shell: &str,
    ) -> (String, Vec<String>) {
        if let Some(ref explicit_cmd) = w_cfg.command {
            if explicit_cmd != "agy" && explicit_cmd != "agys" && !explicit_cmd.is_empty() {
                return (explicit_cmd.clone(), w_cfg.args.clone().unwrap_or_default());
            }
        }

        if self.auto_spawn_agy() {
            let slot_num = IdentityDiscovery::parse_slot_id(&w_cfg.slot_id)
                .unwrap_or(if w_cfg.slot_id == "coordinator" { 1 } else { 1 });
            if let Some(agys_bin) = IdentityDiscovery::find_agys_binary() {
                let mut args = vec![slot_num.to_string()];
                if let Some(ref extra) = w_cfg.args {
                    args.extend(extra.clone());
                }
                return (agys_bin.to_string_lossy().to_string(), args);
            }

            if let Some(agy_bin) = IdentityDiscovery::find_agy_binary() {
                let mut args = vec!["--model".to_string(), "gemini-3.8-flash-high".to_string()];
                if let Some(ref extra) = w_cfg.args {
                    args.extend(extra.clone());
                }
                return (agy_bin.to_string_lossy().to_string(), args);
            }
        }

        (
            fallback_shell.to_string(),
            w_cfg.args.clone().unwrap_or_default(),
        )
    }

    /// Spawn dedicated coordinator session with automatic agy spawning or fallback shell.
    pub fn spawn_coordinator_auto(
        &self,
        fallback_shell: Option<&str>,
        rows: u16,
        cols: u16,
    ) -> Result<Arc<WorkerSession>> {
        let shell = fallback_shell.unwrap_or(if cfg!(windows) { "powershell.exe" } else { "bash" });
        let cmd = if self.auto_spawn_agy() { "agy" } else { shell };
        self.spawn_session("coordinator", "agy1", cmd, vec![], None, HashMap::new(), rows, cols)
    }

    /// Spawn a worker session with automatic agy spawning or fallback shell.
    pub fn spawn_worker_auto(
        &self,
        id: impl Into<String>,
        slot_id: impl Into<String>,
        fallback_shell: Option<&str>,
        rows: u16,
        cols: u16,
    ) -> Result<Arc<WorkerSession>> {
        let shell = fallback_shell.unwrap_or(if cfg!(windows) { "powershell.exe" } else { "bash" });
        let cmd = if self.auto_spawn_agy() { "agy" } else { shell };
        self.spawn_session(id, slot_id, cmd, vec![], None, HashMap::new(), rows, cols)
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

    // ── Dedicated Coordinator & Worker Pane Accessors ──────────────

    /// Get dedicated Primary Coordinator session.
    pub fn coordinator(&self) -> Option<Arc<WorkerSession>> {
        self.coordinator.lock().clone()
    }

    /// Assign dedicated Primary Coordinator session.
    pub fn set_coordinator(&self, session: Arc<WorkerSession>) {
        *self.coordinator.lock() = Some(Arc::clone(&session));
        let mut list = self.sessions.lock();
        list.retain(|s| s.id != session.id && s.id != "coordinator");
        list.insert(0, Arc::clone(&session));
    }

    /// Get ordered list of interactive worker sessions.
    pub fn workers(&self) -> Vec<Arc<WorkerSession>> {
        self.workers.lock().clone()
    }

    /// Add a new interactive worker session to the workers pane.
    pub fn add_worker(&self, session: Arc<WorkerSession>) {
        self.workers.lock().push(Arc::clone(&session));
        let mut list = self.sessions.lock();
        if !list.iter().any(|s| s.id == session.id) {
            list.push(Arc::clone(&session));
        }
    }

    /// Remove a worker session by ID.
    pub fn remove_worker(&self, id: &str) -> Option<Arc<WorkerSession>> {
        let mut workers = self.workers.lock();
        let pos = workers.iter().position(|w| w.id == id || w.slot_id == id);
        let removed = pos.map(|idx| workers.remove(idx));
        drop(workers);

        let mut list = self.sessions.lock();
        list.retain(|s| s.id != id && s.slot_id != id);
        drop(list);

        removed
    }

    // ── Pane Focus & Dual Vim-Style State Machine ───────────────────

    /// Retrieve active pane focus (Coordinator vs Workers(index)).
    pub fn focused_pane(&self) -> FocusedPane {
        *self.focused_pane.lock()
    }

    /// Set active pane focus.
    pub fn set_focused_pane(&self, pane: FocusedPane) {
        *self.focused_pane.lock() = pane;
    }

    /// Toggle/Switch focus between Primary Coordinator and active Worker pane (Tab / Shift+Tab).
    pub fn switch_pane_focus(&self) {
        let mut pane = self.focused_pane.lock();
        *pane = match *pane {
            FocusedPane::Coordinator => {
                let workers = self.workers.lock();
                if !workers.is_empty() {
                    FocusedPane::Workers(0)
                } else {
                    FocusedPane::Coordinator
                }
            }
            FocusedPane::Workers(_) => FocusedPane::Coordinator,
        };
    }

    /// Alias for switch_pane_focus.
    pub fn toggle_pane_focus(&self) {
        self.switch_pane_focus();
    }

    /// Jump directly to worker tab #1..#9 in the workers pane ('1'..'9').
    pub fn jump_worker_tab(&self, tab_num: usize) -> bool {
        let workers = self.workers.lock();
        if tab_num >= 1 && tab_num <= workers.len() {
            *self.focused_pane.lock() = FocusedPane::Workers(tab_num - 1);
            true
        } else {
            false
        }
    }

    /// Cycle worker tabs to the right in the workers pane ('l').
    pub fn next_worker_tab(&self) {
        let workers = self.workers.lock();
        if workers.is_empty() {
            return;
        }
        let mut pane = self.focused_pane.lock();
        let cur = match *pane {
            FocusedPane::Workers(idx) => idx,
            FocusedPane::Coordinator => 0,
        };
        let next = (cur + 1) % workers.len();
        *pane = FocusedPane::Workers(next);
    }

    /// Cycle worker tabs to the left in the workers pane ('h').
    pub fn prev_worker_tab(&self) {
        let workers = self.workers.lock();
        if workers.is_empty() {
            return;
        }
        let mut pane = self.focused_pane.lock();
        let cur = match *pane {
            FocusedPane::Workers(idx) => idx,
            FocusedPane::Coordinator => 0,
        };
        let prev = if cur == 0 { workers.len() - 1 } else { cur - 1 };
        *pane = FocusedPane::Workers(prev);
    }

    /// Get active Vim-style application mode.
    pub fn app_mode(&self) -> AppMode {
        *self.app_mode.lock()
    }

    /// Set application mode (Normal vs PtyInteract).
    pub fn set_app_mode(&self, mode: AppMode) {
        *self.app_mode.lock() = mode;
    }

    /// Enter PTY_INTERACT (Insert) mode.
    pub fn enter_pty(&self) {
        self.set_app_mode(AppMode::PtyInteract);
    }

    /// Enter NORMAL (Command) mode.
    pub fn enter_normal(&self) {
        self.set_app_mode(AppMode::Normal);
    }

    /// Terminate and close active worker tab in the workers pane ('x').
    pub fn close_active_worker(&self) -> Result<Option<Arc<WorkerSession>>> {
        let target_id = {
            let pane = *self.focused_pane.lock();
            match pane {
                FocusedPane::Workers(idx) => {
                    let workers = self.workers.lock();
                    workers.get(idx).map(|w| w.id.clone())
                }
                FocusedPane::Coordinator => None,
            }
        };

        if let Some(id) = target_id {
            let removed = self.remove_worker(&id);
            if let Some(ref w) = removed {
                let _ = w.kill();
            }
            let workers_len = self.workers.lock().len();
            let mut pane = self.focused_pane.lock();
            if workers_len == 0 {
                *pane = FocusedPane::Coordinator;
            } else {
                match *pane {
                    FocusedPane::Workers(idx) if idx >= workers_len => {
                        *pane = FocusedPane::Workers(workers_len - 1);
                    }
                    _ => {}
                }
            }
            Ok(removed)
        } else {
            Ok(None)
        }
    }

    // ── Session Restoration & Lifecycle ────────────────────────────

    /// Load and restore a session from persistent storage into running worker tabs.
    pub fn load_and_restore_session(
        &self,
        name: &str,
        default_cmd: &str,
        rows: u16,
        cols: u16,
    ) -> Result<SessionRecord> {
        let mut session_record = self
            .store
            .get_session(name)?
            .ok_or_else(|| TuiError::SessionNotFound(format!("Session '{}' does not exist", name)))?;

        session_record.sync_configs();

        // Clear currently running sessions
        self.sessions.lock().clear();
        *self.coordinator.lock() = None;
        self.workers.lock().clear();
        *self.focused_pane.lock() = FocusedPane::Coordinator;

        let half_cols = (cols / 2).saturating_sub(2).max(10);
        let coord_rows = rows.saturating_sub(4).max(5);
        let worker_rows = rows.saturating_sub(7).max(5);

        for (idx, w_cfg) in session_record.workers.iter().enumerate() {
            let (cmd, args) = self.resolve_worker_command(w_cfg, default_cmd);
            let env = w_cfg.env.clone().unwrap_or_default();
            let cwd = if !session_record.working_dir.is_empty() {
                let p = PathBuf::from(&session_record.working_dir);
                if p.is_dir() { Some(p) } else { std::env::current_dir().ok() }
            } else {
                std::env::current_dir().ok()
            };

            let (p_rows, p_cols) = if idx == 0 {
                (coord_rows, half_cols)
            } else {
                (worker_rows, half_cols)
            };

            let worker = self.spawn_session(
                &w_cfg.id,
                &w_cfg.slot_id,
                cmd,
                args,
                cwd,
                env,
                p_rows,
                p_cols,
            )?;

            worker.set_role(&w_cfg.role);
            worker.set_model(&w_cfg.model);
            worker.set_task(w_cfg.task.clone());

            if idx == 0 {
                worker.set_role("coordinator");
            }
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

        record.workers.clear();

        if let Some(coord) = self.coordinator() {
            record.workers.push(SessionWorkerConfig {
                id: coord.id.clone(),
                slot_id: coord.slot_id.clone(),
                role: coord.role(),
                model: coord.model(),
                task: coord.task.lock().clone(),
                command: None,
                args: None,
                env: None,
            });
        }

        for w in self.workers() {
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
        record.sync_configs();

        let path = self.store.save_session(&record)?;
        Ok(Some(path))
    }

    /// Spawn and register a new session (routes to coordinator or workers).
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
        let id_str = id.into();
        let slot_str = slot_id.into();
        let cmd_str = command.into();

        let (final_cmd, final_args) = if cmd_str == "agy"
            || cmd_str == "agys"
            || cmd_str == "auto"
            || (cmd_str.is_empty() && self.auto_spawn_agy())
        {
            let slot_num = IdentityDiscovery::parse_slot_id(&slot_str).unwrap_or(if slot_str == "coordinator" { 1 } else { 1 });
            if let Some(agys_bin) = IdentityDiscovery::find_agys_binary() {
                let mut full_args = vec![slot_num.to_string()];
                full_args.extend(args);
                (agys_bin.to_string_lossy().to_string(), full_args)
            } else if let Some(agy_bin) = IdentityDiscovery::find_agy_binary() {
                let mut full_args = vec!["--model".to_string(), "gemini-3.8-flash-high".to_string()];
                full_args.extend(args);
                (agy_bin.to_string_lossy().to_string(), full_args)
            } else {
                let fallback = if cfg!(windows) { "powershell.exe" } else { "bash" };
                (fallback.to_string(), vec![])
            }
        } else {
            (cmd_str, args)
        };

        let effective_cwd = cwd.or_else(|| std::env::current_dir().ok());

        let session = Arc::new(WorkerSession::spawn(
            id_str.clone(),
            slot_str.clone(),
            final_cmd,
            final_args,
            effective_cwd,
            env,
            rows,
            cols,
        )?);

        let mut coord_guard = self.coordinator.lock();
        let is_coordinator = id_str == "coordinator" || slot_str == "agy1" || coord_guard.is_none();

        if is_coordinator && coord_guard.is_none() {
            *coord_guard = Some(Arc::clone(&session));
            let mut list = self.sessions.lock();
            list.insert(0, Arc::clone(&session));
        } else if id_str == "coordinator" || slot_str == "agy1" {
            *coord_guard = Some(Arc::clone(&session));
            let mut list = self.sessions.lock();
            list.retain(|s| s.id != "coordinator" && s.slot_id != "agy1");
            list.insert(0, Arc::clone(&session));
        } else {
            self.workers.lock().push(Arc::clone(&session));
            self.sessions.lock().push(Arc::clone(&session));
        }

        Ok(session)
    }

    /// Reassign a worker (or coordinator) to a new agy slot ID and restart its PTY process.
    pub fn restart_worker_with_slot(
        &self,
        worker_id: &str,
        new_slot_id: &str,
        rows: u16,
        cols: u16,
    ) -> Result<Arc<WorkerSession>> {
        let is_coord = worker_id == "coordinator" || worker_id == "agy1";

        if is_coord {
            if let Some(old) = self.coordinator() {
                let _ = old.kill();
            }
            let new_session = self.spawn_session(
                "coordinator",
                new_slot_id,
                "agy",
                vec![],
                None,
                HashMap::new(),
                rows,
                cols,
            )?;
            let _ = self.save_current_session();
            Ok(new_session)
        } else {
            let (target_id, orig_idx) = {
                let workers = self.workers.lock();
                let idx_opt = workers.iter().position(|w| w.id == worker_id || w.slot_id == worker_id);
                if let Some(idx) = idx_opt {
                    let old = workers[idx].clone();
                    let tid = old.id.clone();
                    let _ = old.kill();
                    (tid, idx)
                } else {
                    return Err(TuiError::WorkerNotFound(format!("Worker '{}' not found", worker_id)));
                }
            };

            // Remove old session from tracking
            self.remove_worker(&target_id);

            // Spawn replacement session
            let new_session = self.spawn_session(
                target_id.clone(),
                new_slot_id,
                "agy",
                vec![],
                None,
                HashMap::new(),
                rows,
                cols,
            )?;

            // Re-order worker to original index if needed
            let mut workers = self.workers.lock();
            if let Some(cur_pos) = workers.iter().position(|w| w.id == target_id) {
                if cur_pos != orig_idx && orig_idx < workers.len() {
                    let w = workers.remove(cur_pos);
                    workers.insert(orig_idx, w);
                }
            }

            let _ = self.save_current_session();
            Ok(new_session)
        }
    }

    /// Restart all sessions (coordinator and workers) with their current assigned agy slots.
    pub fn restart_all_sessions(
        &self,
        coord_rows: u16,
        coord_cols: u16,
        worker_rows: u16,
        worker_cols: u16,
    ) -> Result<()> {
        if let Some(coord) = self.coordinator() {
            let slot = coord.slot_id.clone();
            let _ = self.restart_worker_with_slot("coordinator", &slot, coord_rows, coord_cols);
        }
        let workers: Vec<(String, String)> = self.workers().iter().map(|w| (w.id.clone(), w.slot_id.clone())).collect();
        for (id, slot) in workers {
            let _ = self.restart_worker_with_slot(&id, &slot, worker_rows, worker_cols);
        }
        Ok(())
    }

    /// Update assigned agy slot metadata without restarting the current PTY process.
    pub fn reassign_worker_slot(&self, worker_id: &str, new_slot_id: &str) -> Result<()> {
        let is_coord = worker_id == "coordinator" || worker_id == "agy1";
        let slot_info = IdentityDiscovery::find_slot(new_slot_id);

        if is_coord {
            if let Some(coord) = self.coordinator() {
                if let Some(ref s) = slot_info {
                    *coord.role.lock() = s.role.clone();
                    *coord.model.lock() = s.model.clone();
                }
            }
        } else {
            let workers = self.workers.lock();
            if let Some(worker) = workers.iter().find(|w| w.id == worker_id || w.slot_id == worker_id) {
                if let Some(ref s) = slot_info {
                    *worker.role.lock() = s.role.clone();
                    *worker.model.lock() = s.model.clone();
                }
            }
        }
        let _ = self.save_current_session();
        Ok(())
    }

    /// Retrieve all registered sessions in order (coordinator first, then workers).
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
        let pane = self.focused_pane();
        match pane {
            FocusedPane::Coordinator => {
                if let Some(coord) = self.coordinator() {
                    return Some(coord);
                }
                self.sessions.lock().first().cloned()
            }
            FocusedPane::Workers(idx) => {
                let workers = self.workers();
                if let Some(w) = workers.get(idx) {
                    return Some(Arc::clone(w));
                }
                if let Some(w) = workers.first() {
                    return Some(Arc::clone(w));
                }
                self.coordinator().or_else(|| self.sessions.lock().first().cloned())
            }
        }
    }

    /// Get linear index of currently active session for backward compatibility.
    pub fn active_index(&self) -> usize {
        let pane = self.focused_pane();
        match pane {
            FocusedPane::Coordinator => 0,
            FocusedPane::Workers(idx) => {
                if self.coordinator().is_some() {
                    idx + 1
                } else {
                    idx
                }
            }
        }
    }

    /// Switch focus to session at specified index for backward compatibility.
    pub fn select_index(&self, index: usize) -> bool {
        let total = self.sessions.lock().len();
        if index >= total {
            return false;
        }

        if index == 0 && self.coordinator().is_some() {
            *self.focused_pane.lock() = FocusedPane::Coordinator;
            true
        } else {
            let worker_idx = if self.coordinator().is_some() {
                index.saturating_sub(1)
            } else {
                index
            };
            let workers_len = self.workers.lock().len();
            if worker_idx < workers_len {
                *self.focused_pane.lock() = FocusedPane::Workers(worker_idx);
                true
            } else {
                false
            }
        }
    }

    /// Switch focus to next session tab.
    pub fn next_session(&self) {
        let list = self.sessions.lock();
        if list.is_empty() {
            return;
        }
        let cur = self.active_index();
        let next = (cur + 1) % list.len();
        drop(list);
        self.select_index(next);
    }

    /// Switch focus to previous session tab.
    pub fn prev_session(&self) {
        let list = self.sessions.lock();
        if list.is_empty() {
            return;
        }
        let cur = self.active_index();
        let prev = if cur == 0 { list.len() - 1 } else { cur - 1 };
        drop(list);
        self.select_index(prev);
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

    /// Resize panes according to their specific layout geometry:
    /// - Coordinator gets dedicated `(coord_rows, coord_cols)`
    /// - All Workers get dedicated `(worker_rows, worker_cols)`
    pub fn resize_panes(&self, coord_rows: u16, coord_cols: u16, worker_rows: u16, worker_cols: u16) {
        if let Some(coord) = self.coordinator() {
            if let Err(e) = coord.resize(coord_rows, coord_cols) {
                warn!("Failed to resize coordinator PTY: {}", e);
            }
        }
        let workers = self.workers();
        for worker in workers.iter() {
            if let Err(e) = worker.resize(worker_rows, worker_cols) {
                warn!("Failed to resize worker '{}' PTY: {}", worker.id, e);
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
