use crossterm::event::{KeyEvent, MouseEvent};
use serde::{Deserialize, Serialize};

/// Master application events dispatched through the Tokio event loop.
#[derive(Debug, Clone)]
pub enum AppEvent {
    /// Keyboard key event from terminal crossterm stream.
    Key(KeyEvent),

    /// Text pasted from terminal clipboard (bracketed paste).
    Paste(String),

    /// Mouse event (click, drag, scroll).
    Mouse(MouseEvent),

    /// Terminal resize event (rows, cols).
    Resize(u16, u16),

    /// Chunk of raw output data received from a worker's PTY.
    PtyOutput {
        session_id: String,
        data: Vec<u8>,
    },

    /// Notification that a worker PTY process has exited.
    PtyExited {
        session_id: String,
        exit_code: Option<u32>,
    },

    /// Alarm or idle notification from an agent (e.g. idle prompt reached or help needed).
    Alarm(AlarmEvent),

    /// Custom IPC action request.
    IpcMessage(String),

    /// Periodic tick event for timer-based animations, quota refreshes, or debouncers.
    Tick,

    /// Request to cleanly shutdown the TUI application.
    Quit,
}

/// Agent alarm event structure matching coordinator alarm pipeline specifications.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlarmEvent {
    pub worker_id: String,
    pub alarm_type: String, // "IDLE" | "HELP" | "INJECTED"
    pub message: String,
    pub timestamp: u64,
}
