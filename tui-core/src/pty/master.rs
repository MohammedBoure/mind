use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use parking_lot::Mutex;
use portable_pty::{CommandBuilder, MasterPty, NativePtySystem, PtySize, PtySystem};
use tokio::sync::mpsc;
use tracing::{debug, info};

use crate::error::{Result, TuiError};

/// Configuration options for spawning a PTY child process.
#[derive(Debug, Clone)]
pub struct PtyConfig {
    pub command: String,
    pub args: Vec<String>,
    pub cwd: Option<PathBuf>,
    pub env: HashMap<String, String>,
    pub rows: u16,
    pub cols: u16,
}

impl Default for PtyConfig {
    fn default() -> Self {
        Self {
            command: if cfg!(windows) { "powershell.exe".to_string() } else { "bash".to_string() },
            args: Vec::new(),
            cwd: None,
            env: HashMap::new(),
            rows: 24,
            cols: 80,
        }
    }
}

/// Low-level PTY master handle encapsulating PTY system, writer, and process lifecycle.
pub struct PtyMaster {
    master: Box<dyn MasterPty + Send>,
    writer: Arc<Mutex<Box<dyn Write + Send>>>,
    child: Arc<Mutex<Box<dyn portable_pty::Child + Send + Sync>>>,
    pid: Option<u32>,
    alive: Arc<AtomicBool>,
}

impl PtyMaster {
    /// Spawn a child process inside a new native PTY master instance.
    ///
    /// Launches an asynchronous stream reader delivering chunks via `output_tx`.
    pub fn spawn(
        config: PtyConfig,
        output_tx: mpsc::Sender<Vec<u8>>,
    ) -> Result<Self> {
        let pty_system = NativePtySystem::default();
        let size = PtySize {
            rows: config.rows.max(1),
            cols: config.cols.max(1),
            pixel_width: 0,
            pixel_height: 0,
        };

        let pair = pty_system
            .openpty(size)
            .map_err(|e| TuiError::Pty(format!("Failed to open native PTY: {}", e)))?;

        let mut cmd = CommandBuilder::new(&config.command);
        for arg in &config.args {
            cmd.arg(arg);
        }
        if let Some(cwd) = &config.cwd {
            cmd.cwd(cwd);
        }
        for (k, v) in &config.env {
            cmd.env(k, v);
        }

        let child = pair
            .slave
            .spawn_command(cmd)
            .map_err(|e| TuiError::Pty(format!("Failed to spawn child command '{}': {}", config.command, e)))?;

        let pid = child.process_id();
        info!("Spawned PTY child process '{}' (PID: {:?})", config.command, pid);

        let mut reader = pair
            .master
            .try_clone_reader()
            .map_err(|e| TuiError::Pty(format!("Failed to clone PTY reader: {}", e)))?;

        let writer = pair
            .master
            .take_writer()
            .map_err(|e| TuiError::Pty(format!("Failed to take PTY writer: {}", e)))?;

        let alive = Arc::new(AtomicBool::new(true));
        let alive_clone = Arc::clone(&alive);

        // Spawn high-throughput background thread for PTY reading to avoid any async IO stalls
        std::thread::Builder::new()
            .name("pty-reader-loop".to_string())
            .spawn(move || {
                let mut buffer = [0u8; 8192];
                loop {
                    match reader.read(&mut buffer) {
                        Ok(0) => {
                            debug!("PTY reader reached EOF (child exited)");
                            alive_clone.store(false, Ordering::SeqCst);
                            break;
                        }
                        Ok(n) => {
                            let chunk = buffer[..n].to_vec();
                            if output_tx.blocking_send(chunk).is_err() {
                                debug!("PTY receiver disconnected, exiting reader thread");
                                break;
                            }
                        }
                        Err(e) => {
                            debug!("PTY read error: {}", e);
                            alive_clone.store(false, Ordering::SeqCst);
                            break;
                        }
                    }
                }
                alive_clone.store(false, Ordering::SeqCst);
            })
            .map_err(|e| TuiError::Pty(format!("Failed to spawn reader thread: {}", e)))?;

        Ok(Self {
            master: pair.master,
            writer: Arc::new(Mutex::new(writer)),
            child: Arc::new(Mutex::new(child)),
            pid,
            alive,
        })
    }

    /// Write raw byte stream to child stdin.
    pub fn write_all(&self, data: &[u8]) -> Result<()> {
        let mut writer = self.writer.lock();
        writer
            .write_all(data)
            .map_err(|e| TuiError::Pty(format!("PTY write error: {}", e)))?;
        writer
            .flush()
            .map_err(|e| TuiError::Pty(format!("PTY flush error: {}", e)))?;
        Ok(())
    }

    /// Send SIGINT / Ctrl+C interrupt (ASCII 0x03) to the running process.
    pub fn send_interrupt(&self) -> Result<()> {
        debug!("Sending interrupt (0x03 / SIGINT) to PTY");
        self.write_all(&[0x03])
    }

    /// Resize the virtual terminal dimensions.
    pub fn resize(&self, rows: u16, cols: u16) -> Result<()> {
        let size = PtySize {
            rows: rows.max(1),
            cols: cols.max(1),
            pixel_width: 0,
            pixel_height: 0,
        };
        self.master
            .resize(size)
            .map_err(|e| TuiError::Pty(format!("PTY resize error: {}", e)))
    }

    /// Check if child process is still running.
    pub fn is_alive(&self) -> bool {
        if !self.alive.load(Ordering::SeqCst) {
            return false;
        }
        let mut child = self.child.lock();
        match child.try_wait() {
            Ok(Some(_status)) => {
                self.alive.store(false, Ordering::SeqCst);
                false
            }
            Ok(None) => true,
            Err(_) => {
                self.alive.store(false, Ordering::SeqCst);
                false
            }
        }
    }

    /// Process ID of the spawned child, if available.
    pub fn pid(&self) -> Option<u32> {
        self.pid
    }

    /// Terminate the child process.
    pub fn kill(&self) -> Result<()> {
        let mut child = self.child.lock();
        child
            .kill()
            .map_err(|e| TuiError::Pty(format!("Failed to kill PTY child: {}", e)))?;
        self.alive.store(false, Ordering::SeqCst);
        Ok(())
    }
}
