# `tui-core/tests/` — Automated Test Suite

This directory contains automated integration tests for `tui-core`.

## Files

| File | Purpose |
|---|---|
| `pty_test.rs` | Tests for virtual screen buffer emulation, ANSI sequence parsing, scrollback history retrieval, plain text extraction, and low-level PTY master process spawning. |
| `ipc_test.rs` | Tests for JSON-RPC 2.0 serialization/deserialization, MCP initialize and tool listing (`tools/list`), and MCP tool dispatching. |
| `session_test.rs` | Tests for `SessionManager` worker lifecycle, tab switching (`next_session`, `prev_session`, `active_index`), input dispatching, and screen text verification. |
