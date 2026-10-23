use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use tracing::info;

use crate::error::Result;
use crate::ipc::types::WorkerSummary;
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
    pty: Arc<Mutex<PtyProcess>>,
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
            pty: Arc::new(Mutex::new(pty)),
        })
    }

    /// Deliver text directly to worker stdin with optional carriage return / Enter.
    pub fn send_input(&self, text: &str, press_enter: bool) -> Result<()> {
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
            .last()
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
}
