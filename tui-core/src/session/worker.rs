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
    pub slot_id: String,
    pub task: Arc<Mutex<Option<String>>>,
    pub state: Arc<Mutex<WorkerState>>,
    pub model: Arc<Mutex<String>>,
    pub token_usage: Arc<Mutex<(u64, u64)>>,
    pub last_alarm: Arc<Mutex<Option<AlarmEvent>>>,
    pub pty: Arc<Mutex<PtyProcess>>,
    pub scroll_offset: Arc<Mutex<usize>>,
}

impl WorkerSession {
    /// Spawn a new worker session with dedicated PTY process.
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

        let config = PtyConfig {
            command: command.into(),
            args,
            cwd,
            env,
            rows,
            cols,
        };

        info!("Spawning worker session '{}' (slot: {})", id, slot_id);
        let pty = PtyProcess::spawn(config)?;

        Ok(Self {
            id,
            slot_id,
            task: Arc::new(Mutex::new(None)),
            state: Arc::new(Mutex::new(WorkerState::Running)),
            model: Arc::new(Mutex::new("claude-3-5-sonnet".to_string())),
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
        pty.write_str(text)?;
        if press_enter {
            pty.write_bytes(b"\n")?;
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

    /// Set model identifier for this worker session (e.g. "claude-3-5-sonnet").
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
