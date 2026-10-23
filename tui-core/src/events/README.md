# `tui-core/src/events/` — Tokio Asynchronous Event Multiplexer

This directory provides the unified Tokio event loop for combining interactive terminal Crossterm events, PTY output streams, alarms, and timers.

## Files

| File | Purpose |
|---|---|
| `mod.rs` | Public re-exports for the event subsystem (`EventLoop`, `AppEvent`, `AlarmEvent`). |
| `types.rs` | Application event definitions (`AppEvent`) covering Crossterm keys/mouse/resizing, PTY stream chunks, PTY process exits, alarms, and periodic tick events. |
| `event_loop.rs` | Asynchronous multiplexer (`EventLoop`) using `tokio::select!` over Crossterm's `EventStream`, an internal unbounded/bounded MPSC channel for external event injection, and a configurable millisecond tick interval. |
