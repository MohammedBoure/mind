use thiserror::Error;

/// Core error types for the TUI engine and IPC/MCP subsystems.
#[derive(Debug, Error)]
pub enum TuiError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("PTY error: {0}")]
    Pty(String),

    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),

    #[error("IPC / MCP protocol error: {0}")]
    Ipc(String),

    #[error("Session not found: {0}")]
    SessionNotFound(String),

    #[error("Worker not found: {0}")]
    WorkerNotFound(String),

    #[error("Channel closed or disconnected")]
    ChannelClosed,

    #[error("Process not running: {0}")]
    ProcessNotRunning(String),

    #[error("HTTP request error: {0}")]
    Http(#[from] reqwest::Error),

    #[error("Internal error: {0}")]
    Internal(String),
}

pub type Result<T> = std::result::Result<T, TuiError>;
