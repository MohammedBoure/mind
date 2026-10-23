# `tui-core/src/pty/` — Low-Level PTY Engine & Virtual Screen Buffer

> **PTY Systems Architecture & ANSI Emulation** for the compiled multi-agent TUI engine.
> Maintained by Systems & UX Polish Specialists using `portable-pty` and `vte`.

---

## 1. Overview & Architecture

The `pty` module encapsulates low-level pseudoterminal (PTY) master process spawning, non-blocking asynchronous stream reading, and a complete virtual ANSI terminal screen buffer (`ScreenBuffer`).

```
+-----------------------------------------------------------------------------+
|                          PTY Subsystem Architecture                         |
+-----------------------------------------------------------------------------+
|                                 PtyProcess                                  |
|   ├── PtyMaster (portable-pty)                                              |
|   │     ├── Child Process (bash / powershell)                               |
|   │     ├── Writer (stdin pass-through)                                     |
|   │     └── Background Reader Thread (8KB chunks via mpsc channel)          |
|   └── ScreenBuffer (vte::Parser)                                            |
|         ├── 2D Grid Cells (rows x cols)                                     |
|         ├── Scrollback Ring Buffer (capped at max_scrollback = 2000 lines)  |
|         ├── Version Counter (monotonic increment for O(1) dirty checking)   |
|         └── Dynamic Resizing (Zero clipping, zero tearing, history unroll)  |
+-----------------------------------------------------------------------------+
```

---

## 2. Files & Module Responsibilities

| File | Purpose |
|---|---|
| [`mod.rs`](file:///home/pluto/projects/mind/tui-core/src/pty/mod.rs) | Public exports (`PtyMaster`, `PtyProcess`, `ScreenBuffer`, `ScreenCell`, `CellColor`, `PtyConfig`). |
| [`buffer.rs`](file:///home/pluto/projects/mind/tui-core/src/pty/buffer.rs) | Virtual 2D character matrix and scrollback buffer with ANSI escape sequence parser (`vte::Parser`). Provides $O(1)$ version-tracked dirty checking, SGR color handling, dynamic resizing (`resize`), and scrollback viewport slice extraction (`viewport_cells`). |
| [`master.rs`](file:///home/pluto/projects/mind/tui-core/src/pty/master.rs) | Native PTY master handle using `portable-pty`. Manages child process spawning, non-blocking background I/O reading, stdin writing, Ctrl+C interrupt signals (`0x03`), window resizing (`resize`), and process lifecycle checks (`is_alive`, `kill`). |
| [`process.rs`](file:///home/pluto/projects/mind/tui-core/src/pty/process.rs) | High-level `PtyProcess` encapsulation combining `PtyMaster` and `ScreenBuffer` with an asynchronous Tokio consumer loop for immediate screen updates. |

---

## 3. Dynamic Terminal Resizing Architecture

The virtual screen buffer implements robust dynamic resizing (`ScreenBuffer::resize(new_rows, new_cols)`):

1. **Column Resizing**:
   - Expanding columns pads both active screen rows and scrollback history rows with `ScreenCell::default()`.
   - Shrinking columns truncates lines without memory reallocations.
   - Cursor horizontal position is safely clamped: `cursor_col = cursor_col.min(new_cols - 1)`.

2. **Row Shrinkage (Zero Character Clipping)**:
   - When the terminal height decreases, the engine calculates the extent of active content:
     `active_extent = (cursor_row + 1).max(last_active_row + 1)`.
   - If `active_extent > new_rows`, the overflow rows at the top of the viewport are shifted into `scrollback` history instead of being dropped.
   - Cursor vertical position is shifted proportionally: `cursor_row = cursor_row.saturating_sub(shift)`.
   - Active command prompts and recent output remain visible, eliminating clipping and text tearing.

3. **Row Expansion (History Restoration)**:
   - When the terminal height increases, lines from the back of `scrollback` history are restored into the top of the viewport (`cells.insert(0, restored_row)`).
   - Cursor position is updated to match the restored rows.
   - Any remaining deficit is padded with blank cells at the bottom.

4. **Memory Leak Prevention**:
   - `scrollback` is implemented as a `VecDeque<Vec<ScreenCell>>` strictly bounded by `max_scrollback` (2000 lines). Whenever capacity is reached, oldest lines are evicted via `pop_front()`.

---

## 4. Scrollback History Viewport (`viewport_cells`)

For interactive history viewing (`PageUp` / `PageDown`):
- `viewport_cells(scroll_offset, height)` calculates the visible line range between `scrollback` and `cells`.
- Translates absolute line indices into the active viewport with zero data distortion.
- Computes the relative cursor coordinate `(row, col)` if and only if the cursor falls within the scrolled viewport; otherwise returns `None` to conceal the cursor while reviewing past output.
