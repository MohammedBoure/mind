use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use tracing::info;

use crate::error::Result;
use crate::events::types::AlarmEvent;
use crate::ipc::types::WorkerSummary;
use crate::pty::buffer::ScreenBuffer;
use crate::pty::master::PtyConfig;
use crate::pty::process::PtyProcess;
use crate::session::identity::IdentityDiscovery;

/// Current operational state of a worker agent process.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum WorkerState {
    Spawning,
    Running,
    Idle,
    Interrupted,
    Exited(Option<u32>),
}

/// Managed worker session encapsulating its PTY process, virtual buffer, and metadata.
pub struct WorkerSession {
    pub id: String,
    pub worker_name: Arc<Mutex<String>>,
    pub slot_id: String,
    pub role: Arc<Mutex<String>>,
    pub task: Arc<Mutex<Option<String>>>,
    pub state: Arc<Mutex<WorkerState>>,
    pub model: Arc<Mutex<String>>,
    pub token_usage: Arc<Mutex<(u64, u64)>>,
    pub last_alarm: Arc<Mutex<Option<AlarmEvent>>>,
    pub pty: Arc<Mutex<PtyProcess>>,
    pub scroll_offset: Arc<Mutex<usize>>,
}

impl WorkerSession {
    /// Discover host agy executable binary across system paths.
    pub fn find_agy_binary() -> Option<PathBuf> {
        IdentityDiscovery::find_agy_binary()
    }

    /// Check if agy binary is executable on this system.
    pub fn is_agy_available() -> bool {
        IdentityDiscovery::find_agy_binary().is_some()
    }

    /// Spawn a new worker session with dedicated PTY process and dynamic slot identity linking.
    pub fn spawn(
        id: impl Into<String>,
        slot_id: impl Into<String>,
        command: impl Into<String>,
        args: Vec<String>,
        cwd: Option<PathBuf>,
        env: HashMap<String, String>,
        rows: u16,
        cols: u16,
    ) -> Result<Self> {
        let id = id.into();
        let slot_id = slot_id.into();
        let command_str = command.into();

        // 1. Resolve command: if "agy" or "auto", resolve via find_agy_binary with fallback shell
        let (resolved_cmd, resolved_args) = if command_str == "agy" || command_str == "auto" {
            if let Some(agy_bin) = IdentityDiscovery::find_agy_binary() {
                (agy_bin.to_string_lossy().to_string(), args)
            } else {
                let fallback = if cfg!(windows) { "powershell.exe" } else { "bash" };
                (fallback.to_string(), vec![])
            }
        } else {
            (command_str, args)
        };

        // 2. Discover host slot metadata
        let discovered_slot = IdentityDiscovery::find_slot(&slot_id);
        let default_role = discovered_slot
            .as_ref()
            .map(|s| s.role.clone())
            .unwrap_or_else(|| match slot_id.as_str() {
                "coordinator" | "agy1" | "1" => "Lead Orchestrator".to_string(),
                "agy11" | "11" => "Backend Logic & Systems".to_string(),
                "agy51" | "51" => "Frontend & UI/UX".to_string(),
                "agy100" | "100" => "Testing & Verification".to_string(),
                "agy151" | "151" => "Polish & Ergonomics".to_string(),
                _ => "Autonomous Worker Agent".to_string(),
            });
        let default_model = discovered_slot
            .as_ref()
            .map(|s| s.model.clone())
            .unwrap_or_else(|| "gemini-3.8-flash-high".to_string());
        let default_task = discovered_slot.as_ref().and_then(|s| s.task.clone());

        // 3. Build & merge slot isolation environment (guaranteeing USERPROFILE, HOME, AGY_SLOT, AGY_INSTANCE_DIR)
        let mut final_env = env;
        let isolation = IdentityDiscovery::build_slot_env_by_id(&slot_id);
        for (k, v) in isolation {
            final_env.entry(k).or_insert(v);
        }

        let config = PtyConfig {
            command: resolved_cmd,
            args: resolved_args,
            cwd,
            env: final_env,
            rows,
            cols,
        };

        info!("Spawning worker session '{}' (slot: {}, role: {})", id, slot_id, default_role);
        let pty = PtyProcess::spawn(config)?;

        Ok(Self {
            worker_name: Arc::new(Mutex::new(id.clone())),
            id,
            slot_id,
            role: Arc::new(Mutex::new(default_role)),
            task: Arc::new(Mutex::new(default_task)),
            state: Arc::new(Mutex::new(WorkerState::Running)),
            model: Arc::new(Mutex::new(default_model)),
            token_usage: Arc::new(Mutex::new((12_450, 200_000))),
            last_alarm: Arc::new(Mutex::new(None)),
            pty: Arc::new(Mutex::new(pty)),
            scroll_offset: Arc::new(Mutex::new(0)),
        })
    }

    /// Deliver text directly to worker stdin with optional carriage return / Enter.
    /// Resets scroll offset to live view (0).
    pub fn send_input(&self, text: &str, press_enter: bool) -> Result<()> {
        self.reset_scroll();
        let pty = self.pty.lock();
        if !text.is_empty() {
            pty.write_str(text)?;
        }
        if press_enter {
            // A 30ms debounce ensures interactive terminal line editors (e.g. readline/rustyline/ink)
            // finish buffering and redrawing before receiving the Enter submission.
            std::thread::sleep(std::time::Duration::from_millis(30));
            pty.write_bytes(b"\r")?;
        }
        *self.state.lock() = WorkerState::Running;
        Ok(())
    }

    /// Send SIGINT / Ctrl+C interrupt (0x03) to worker process.
    pub fn send_interrupt(&self) -> Result<()> {
        let pty = self.pty.lock();
        pty.send_interrupt()?;
        *self.state.lock() = WorkerState::Interrupted;
        Ok(())
    }

    /// Resize the worker's PTY geometry and virtual screen buffer.
    pub fn resize(&self, rows: u16, cols: u16) -> Result<()> {
        let mut pty = self.pty.lock();
        pty.resize(rows, cols)
    }

    /// Scroll up in terminal history by `delta` lines.
    pub fn scroll_up(&self, delta: usize) {
        let max_history = {
            let pty = self.pty.lock();
            let buf = pty.buffer();
            let count = buf.lock().history_count();
            count
        };
        let mut offset = self.scroll_offset.lock();
        *offset = (*offset + delta).min(max_history);
    }

    /// Scroll down in terminal history towards live output by `delta` lines.
    pub fn scroll_down(&self, delta: usize) {
        let mut offset = self.scroll_offset.lock();
        *offset = offset.saturating_sub(delta);
    }

    /// Reset scroll offset to live view (0).
    pub fn reset_scroll(&self) {
        *self.scroll_offset.lock() = 0;
    }

    /// Current scroll offset (0 = live view at bottom).
    pub fn scroll_offset(&self) -> usize {
        *self.scroll_offset.lock()
    }

    /// Terminate the underlying child PTY process.
    pub fn kill(&self) -> Result<()> {
        let pty = self.pty.lock();
        pty.kill()
    }

    /// Read clean ANSI-free rendered text from the worker's screen buffer.
    pub fn get_screen_text(&self, max_lines: usize) -> String {
        let pty = self.pty.lock();
        pty.get_screen_text(max_lines)
    }

    /// Read only visible screen rows.
    pub fn get_visible_text(&self) -> String {
        let pty = self.pty.lock();
        pty.get_visible_text()
    }

    /// Current version of the screen buffer for $O(1)$ dirty rendering.
    pub fn version(&self) -> u64 {
        let pty = self.pty.lock();
        pty.version()
    }

    /// Check if the worker child process is still running.
    pub fn is_alive(&self) -> bool {
        let pty = self.pty.lock();
        let alive = pty.is_alive();
        if !alive {
            let mut st = self.state.lock();
            if !matches!(*st, WorkerState::Exited(_)) {
                *st = WorkerState::Exited(None);
            }
        }
        alive
    }

    /// Process ID of the child.
    pub fn pid(&self) -> Option<u32> {
        let pty = self.pty.lock();
        pty.pid()
    }

    /// Detect if the worker terminal screen is currently resting at an interactive IDLE prompt.
    /// Examines recent non-empty lines for typical shell and `agy` prompt markers.
    pub fn is_idle_prompt(&self) -> bool {
        let text = self.get_visible_text();
        let last_non_empty = text
            .lines()
            .map(str::trim)
            .filter(|l| !l.is_empty())
            .next_back()
            .unwrap_or_default();

        let idle_markers = [
            ">", "$", "%", "#", ">>>", "(agy)", "mind>",
            "❯", "➜", "Choice:", "Press Enter",
        ];

        for marker in idle_markers {
            if last_non_empty.ends_with(marker) || last_non_empty == marker {
                return true;
            }
        }

        false
    }

    /// Generate serializable worker summary metadata for MCP reporting.
    pub fn summary(&self) -> WorkerSummary {
        let pty = self.pty.lock();
        let alive = pty.is_alive();
        let status = match *self.state.lock() {
            WorkerState::Spawning => "SPAWNING",
            WorkerState::Running => if alive { "RUNNING" } else { "STOPPED" },
            WorkerState::Idle => "IDLE",
            WorkerState::Interrupted => "INTERRUPTED",
            WorkerState::Exited(_) => "EXITED",
        };

        WorkerSummary {
            worker_id: self.id.clone(),
            slot_id: self.slot_id.clone(),
            task: self.task.lock().clone(),
            status: status.to_string(),
            is_alive: alive,
            pid: pty.pid(),
            buffer_version: pty.version(),
        }
    }

    /// Set current active task description for this worker.
    pub fn set_task(&self, task: Option<String>) {
        *self.task.lock() = task;
    }

    /// Access reference to the thread-safe virtual screen buffer.
    pub fn buffer(&self) -> Arc<Mutex<ScreenBuffer>> {
        let pty = self.pty.lock();
        pty.buffer()
    }

    /// Access reference to the inner PTY process handle.
    pub fn pty(&self) -> Arc<Mutex<PtyProcess>> {
        Arc::clone(&self.pty)
    }

    /// Retrieve the worker's operational role.
    pub fn role(&self) -> String {
        self.role.lock().clone()
    }

    /// Set the worker's operational role.
    pub fn set_role(&self, role: impl Into<String>) {
        *self.role.lock() = role.into();
    }

    /// Retrieve human-friendly worker name.
    pub fn worker_name(&self) -> String {
        self.worker_name.lock().clone()
    }

    /// Set human-friendly worker name.
    pub fn set_worker_name(&self, name: impl Into<String>) {
        *self.worker_name.lock() = name.into();
    }

    /// Set model identifier for this worker session (e.g. "gemini-3.8-flash-high").
    pub fn set_model(&self, model: impl Into<String>) {
        *self.model.lock() = model.into();
    }

    /// Get current model identifier.
    pub fn model(&self) -> String {
        self.model.lock().clone()
    }

    /// Set token usage metrics (used, total).
    pub fn set_tokens(&self, used: u64, total: u64) {
        *self.token_usage.lock() = (used, total);
    }

    /// Get token usage metrics (used, total).
    pub fn tokens(&self) -> (u64, u64) {
        *self.token_usage.lock()
    }

    /// Record or clear the most recent alarm event for this worker.
    pub fn set_last_alarm(&self, alarm: Option<AlarmEvent>) {
        *self.last_alarm.lock() = alarm;
    }

    /// Retrieve the most recent alarm event for this worker.
    pub fn last_alarm(&self) -> Option<AlarmEvent> {
        self.last_alarm.lock().clone()
    }
}
