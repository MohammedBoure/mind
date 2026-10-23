# `tui-core/src/pty/` — Low-Level PTY Engine & Virtual Screen Buffer

This directory provides cross-platform pseudoterminal (PTY) master process execution, non-blocking I/O streaming, and virtual screen matrix emulation.

## Files

| File | Purpose |
|---|---|
| `mod.rs` | Public exports for PTY components (`PtyMaster`, `PtyProcess`, `ScreenBuffer`, `ScreenCell`, `CellColor`, `PtyConfig`). |
| `buffer.rs` | Virtual 2D character matrix and scrollback buffer with ANSI escape sequence parser (`vte::Parser`). Provides $O(1)$ version-tracked dirty checking, SGR color handling, and clean plain text export for MCP screen inspection (`render_plain_text`, `get_visible_text`). |
| `master.rs` | Low-level PTY master event loop using `portable-pty`. Handles native PTY creation, non-blocking background I/O reading, stdin writing, Ctrl+C interrupt signals (0x03), terminal resizing, and child process status monitoring. |
| `process.rs` | High-level `PtyProcess` encapsulation combining `PtyMaster` and `ScreenBuffer` with an asynchronous Tokio consumer loop for immediate screen updates. |
