use std::sync::Arc;
use parking_lot::Mutex;
use tokio::sync::mpsc;
use tracing::debug;

use crate::error::Result;
use crate::pty::buffer::ScreenBuffer;
use crate::pty::master::{PtyConfig, PtyMaster};

/// High-level PTY process handle unifying low-level master I/O and virtual screen emulation.
pub struct PtyProcess {
    master: PtyMaster,
    buffer: Arc<Mutex<ScreenBuffer>>,
}

impl PtyProcess {
    /// Spawn a new PTY process with an associated virtual screen buffer and async ingestion loop.
    pub fn spawn(config: PtyConfig) -> Result<Self> {
        let (output_tx, mut output_rx) = mpsc::channel::<Vec<u8>>(256);
        let rows = config.rows as usize;
        let cols = config.cols as usize;

        let buffer = Arc::new(Mutex::new(ScreenBuffer::new(rows, cols)));
        let master = PtyMaster::spawn(config, output_tx)?;

        let buffer_clone = Arc::clone(&buffer);

        // Spawn async consumer task to update virtual screen buffer
        tokio::spawn(async move {
            debug!("Starting PTY buffer update consumer task");
            while let Some(chunk) = output_rx.recv().await {
                let mut buf = buffer_clone.lock();
                buf.process_bytes(&chunk);
            }
            debug!("PTY output channel closed, consumer terminating");
        });

        Ok(Self { master, buffer })
    }

    /// Write raw text string to terminal stdin.
    pub fn write_str(&self, text: &str) -> Result<()> {
        self.master.write_all(text.as_bytes())
    }

    /// Write byte slice to terminal stdin.
    pub fn write_bytes(&self, bytes: &[u8]) -> Result<()> {
        self.master.write_all(bytes)
    }

    /// Send SIGINT / Ctrl+C interrupt (0x03) to child.
    pub fn send_interrupt(&self) -> Result<()> {
        self.master.send_interrupt()
    }

    /// Resize terminal geometry across both PTY master and screen buffer.
    pub fn resize(&mut self, rows: u16, cols: u16) -> Result<()> {
        self.master.resize(rows, cols)?;
        let mut buf = self.buffer.lock();
        buf.resize(rows as usize, cols as usize);
        Ok(())
    }

    /// Get rendered plain ANSI-free screen text (useful for MCP screen inspection).
    pub fn get_screen_text(&self, max_lines: usize) -> String {
        let buf = self.buffer.lock();
        buf.render_plain_text(max_lines)
    }

    /// Get current visible screen rows as clean text.
    pub fn get_visible_text(&self) -> String {
        let buf = self.buffer.lock();
        buf.get_visible_text()
    }

    /// Current version counter of the screen buffer for O(1) dirty caching.
    pub fn version(&self) -> u64 {
        let buf = self.buffer.lock();
        buf.version()
    }

    /// Access reference to the thread-safe virtual screen buffer.
    pub fn buffer(&self) -> Arc<Mutex<ScreenBuffer>> {
        Arc::clone(&self.buffer)
    }

    /// Check if child process is still alive.
    pub fn is_alive(&self) -> bool {
        self.master.is_alive()
    }

    /// Process ID of the child process.
    pub fn pid(&self) -> Option<u32> {
        self.master.pid()
    }

    /// Terminate child process.
    pub fn kill(&self) -> Result<()> {
        self.master.kill()
    }
}
