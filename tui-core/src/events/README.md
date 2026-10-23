# `tui-core/src/events/` — Tokio Asynchronous Event Multiplexer

> **Unified Event Architecture** combining interactive Crossterm events, POSIX SIGWINCH signals, PTY I/O, alarms, and timers.

---

## 1. Overview & Architecture

The `events` module provides the central asynchronous event loop (`EventLoop`) driven by Tokio. It merges input events from four disparate asynchronous sources into a single strongly-typed `AppEvent` stream:

```
+-----------------------------------------------------------------------------+
|                          EventLoop Multiplexer (Tokio)                      |
+-----------------------------------------------------------------------------+
|                               tokio::select!                                |
|   ├── Crossterm EventStream (Key strokes, Mouse actions, terminal events)    |
|   ├── POSIX SIGWINCH Signal Stream (SignalKind::window_change)              |
|   ├── Injected MPSC Channel (PTY output chunks, worker exits, alarms, quit) |
|   └── Periodic Tick Timer (MissedTickBehavior::Skip for smooth animations)  |
+-----------------------------------------------------------------------------+
                                      │
                                      ▼
                                AppEvent Stream
```

---

## 2. Files & Module Responsibilities

| File | Purpose |
|---|---|
| [`mod.rs`](file:///home/pluto/projects/mind/tui-core/src/events/mod.rs) | Public re-exports for the event subsystem (`EventLoop`, `AppEvent`, `AlarmEvent`). |
| [`types.rs`](file:///home/pluto/projects/mind/tui-core/src/events/types.rs) | Core event definitions: `AppEvent` enum (`Key`, `Mouse`, `Resize`, `PtyOutput`, `PtyExited`, `Alarm`, `IpcMessage`, `Tick`, `Quit`) and `AlarmEvent` structure. |
| [`event_loop.rs`](file:///home/pluto/projects/mind/tui-core/src/events/event_loop.rs) | Asynchronous multiplexer (`EventLoop`) implementing unified polling across Crossterm, POSIX SIGWINCH, internal MPSC channel, and tick intervals. |

---

## 3. Responsive Resizing & POSIX SIGWINCH Handling

1. **POSIX SIGWINCH Hooking**:
   - On Unix systems (`#[cfg(unix)]`), `EventLoop` registers a signal listener via `tokio::signal::unix::signal(SignalKind::window_change())`.
   - When the terminal emulator window geometry is altered by the user or window manager, the OS emits `SIGWINCH`.
   - The event loop catches the signal, queries the terminal dimensions via `crossterm::terminal::size()`, and yields `Some(AppEvent::Resize(rows, cols))`.

2. **Crossterm EventStream Coexistence**:
   - Concurrently, Crossterm's native `EventStream` listens for terminal events. If Crossterm produces `CrosstermEvent::Resize(cols, rows)`, it is translated to `AppEvent::Resize(rows, cols)`.
   - Downstream subsystems deduplicate identical dimensions to avoid redundant layout recalculations.

---

## 4. Injected Events & Thread Safety

External threads and asynchronous tasks can clone an MPSC sender using `event_loop.sender()`:
- PTY output readers inject raw byte chunks (`AppEvent::PtyOutput`).
- Process monitor tasks inject process exit codes (`AppEvent::PtyExited`).
- Swarm coordination agents inject coordinator alarms (`AppEvent::Alarm`).
- Lifecycle handlers can trigger clean application termination (`AppEvent::Quit`).
