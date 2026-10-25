# `src/mind/mcp/` — High-Performance Async Model Context Protocol (MCP) Server

This directory contains the embedded MCP server (`mind-mcp`) that exposes lightweight, asyncio-native orchestration tools for the primary coordinator agent to inspect worker terminal screens, inject prioritized interrupts, deliver direct inputs, monitor account quotas, coordinate tasks across multiple agents, provide vision perception capabilities for Vision LLMs, and execute biologically authentic human-like mouse and keyboard interactions using PyTorch AI models, xdotool, and kinematic shaping.

## Architectural Role & Scope

The `mind-mcp` package functions as the central bridge between external AI agents (such as Antigravity CLI instances, LLM orchestrators, and Vision models) and the internal `mind` runtime. It implements:
1. **Agent Coordination & Terminal Telemetry:** Real-time terminal screen scraping, process supervision, quota monitoring, and prioritized directive injection.
2. **Vision-Language Perception & Screen Capture:** High-fidelity screen capture equipped with a calibrated numbered coordinate grid overlay designed specifically for Vision-Language Models (e.g., Gemini Vision, Claude 3.5 Sonnet, GPT-4o) and automated mouse controllers.
3. **AI Natural Human Mouse Interaction:** Integration of `NaturaleMouseEvent` / `human_mouse_engine`, generating authentic, human-like cursor trajectories powered by trained PyTorch GRU neural networks and biomechanical neuromuscular kinematic filtering. Executes real cursor movement and clicks via `xdotool` or `pyautogui` when a display server is reachable (`DISPLAY=:0`).
4. **Natural Keyboard Interaction & Full Unicode/Arabic Support:** Human-cadence typing with realistic keystroke jitter (~60–90 WPM), individual key pressing, hotkey execution, and seamless Arabic/Unicode text injection via Linux X11 clipboard (`xclip`) and `xdotool`.
5. **Headless & CI Resilience:** Multi-tier graceful fallback ensuring that when no physical display server or X11/Wayland socket is reachable, simulated desktop canvases and virtual mouse/keyboard coordinate tracking operate without raising unhandled exceptions or crashing the MCP server.

---

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Public exports for MCP server creation (`create_mcp_server`, `get_default_mcp_server`, `reset_default_mcp_server`), keyboard controller (`KeyboardController`, `get_keyboard_controller`, `reset_keyboard_controller`), natural mouse controller (`NaturalMouseController`, `get_natural_mouse_controller`, `reset_natural_mouse_controller`, `is_headless_environment`), background daemon runner (`MCPServerRunner`, `start_background_mcp_server`, `stop_background_mcp_server`), screen buffer cache (`TerminalScreenCache`), vision capture utilities (`capture_screen_with_grid`, `get_screen_geometry`, `draw_coordinate_grid`, `capture_raw_screen`, `generate_mock_screen`, `encode_vision_capture`), and stdio entrypoints (`run_stdio_mcp_server`, `run_stdio_mcp_server_async`). |
| `server.py` | FastMCP server definition exposing 19 async MCP tools for terminal control, inter-agent signaling, quota tracking, vision grid capture, natural human mouse movements, and keyboard input. |
| `runner.py` | Dual-transport execution runner supporting: (1) local HTTP SSE server (`uvicorn.Server` on `127.0.0.1:8765`) running fully asynchronously in background without blocking the main application lifecycle (`wait_for_ready=False`), (2) automatic provisioning and persistence of `mind-mcp` across orchestrator instances (`provision_mcp_config`), and (3) Standard I/O (stdio) transport for direct pairing with Antigravity CLI (`mind mcp` / `agy.exe mcp add mind-mcp`). |
| `keyboard.py` | High-level Keyboard Controller supporting natural typing cadence, keystroke jitter, Arabic character normalization, seamless Unicode injection via `xclip` and `xdotool`, single-key presses, and multi-key hotkey combinations with headless simulation fallback. |
| `natural_mouse.py` | High-level AI Natural Mouse Controller wrapping `NaturaleMouseEvent/human_mouse_engine` and driving live cursors via `xdotool` or `pyautogui` along neural/Savitzky-Golay trajectory waypoints, with persistent virtual cursor tracking and pure-Python minimum-jerk kinematics fallback. |
| `vision_capture.py` | Dedicated vision perception module providing cross-platform frame capture (via `mss` and `PIL.ImageGrab`), calibrated numbered coordinate grid rendering (X/Y rulers, tick marks, intersection crosshairs, coordinate badges), headless mock canvas generation, and flexible encoding (base64 Data URLs and cached files). |
| `NaturaleMouseEvent/` | AI-powered Natural Mouse Trajectory Engine package containing trained PyTorch neural network checkpoints (`models/production_mouse_model.pth`, `human_mouse_engine/human_mouse_model.pt`) and execution engine (`human_mouse_engine/`). |

---

## Exposed MCP Tools

1. **`list_workers()`**
   - Returns operational status, PIDs, tasks, and linked slot/account identities (`slot_id`, `assigned_agent`, `linked_account`, `token_status`, `quota_status`, `hourly_remaining`, `weekly_remaining`).
2. **`get_terminal_screen(worker_id, lines=50)`**
   - Reads clean, ANSI-free rendered text from any worker's virtual terminal buffer (use `lines=0` to retrieve the entire buffer including full scrollback history uncapped).
   - Utilizes `TerminalScreenCache` to provide instant $O(1)$ responses when buffer version is unchanged.
3. **`send_terminal_input(worker_id, text, press_enter=True)`**
   - Dispatches raw commands and keystrokes directly to the target worker process stdin.
4. **`interrupt_and_inject(worker_id, sender_id, message, priority='high')`**
   - Emits an immediate `SIGINT` / `Ctrl+C` interrupt signal to pause the target `agy` agent safely, allows prompt to stabilize asynchronously without blocking the event loop, and writes formatted priority directives.
5. **`check_account_quotas(slot='', as_json=False, hourly_limit=None, weekly_limit=None)`**
   - Inspects hourly and weekly quota consumption for one or all slots, calculating remaining steps and graphic progress bars (`[████████░░] 80%`).
6. **`get_agent_profile(agent_id)`**
   - Returns agent configuration, role, principles, local `./agent` configs, and instructions.
7. **`notify_coordinator_worker_idle(worker_id, status_summary)`**
   - Emits an idle completion alarm event to the primary coordinator.
8. **`notify_coordinator_help(worker_id, reason, priority='high')`**
   - Dispatches an urgent assistance request from a worker agent to the coordinator.
9. **`check_coordinator_alarms()`**
   - Retrieves queued alarm events and notifications for the coordinator.
10. **`capture_screen_with_grid(grid_step=100, show_axes=True, output_format="base64", quality=85, monitor=0, image_format="jpeg", show_badges=True)`**
    - Captures screen frames and overlays a calibrated numbered coordinate grid for Vision LLMs.
11. **`get_screen_geometry()`**
    - Inspects display hardware geometry, active monitor viewports, resolution, display server identifier, and headless status.
12. **`natural_mouse_move(target_x, target_y, duration_ms=None)`**
    - Moves cursor smoothly from current coordinates to `(target_x, target_y)` along an authentic human trajectory.
    - Connects directly to trained PyTorch neural networks in `human_mouse_engine` and glides the cursor on `DISPLAY=:0` via `xdotool` or `pyautogui`.
13. **`natural_mouse_click(target_x, target_y, button="left", clicks=1)`**
    - Naturally reaches `(target_x, target_y)` and performs authentic human click(s) with realistic inter-click timing (~60–120ms).
14. **`natural_mouse_sequence(coordinates, delay_between=0.2, click_targets=False)`**
    - Executes multi-target waypoint sequences with continuous kinematic momentum chaining.
15. **`get_mouse_position()`**
    - Retrieves current cursor coordinates `{"x": float, "y": float, "dry_run": bool, "mode": str}` from active display server or tracked virtual state.
16. **`keyboard_type(text, wpm=75, natural_delay=True)`**
    - Types text with authentic human cadence and keystroke jitter (~60–90 WPM, 60–120ms between characters).
    - Fully supports Arabic and Unicode text, injecting seamlessly into focused windows via Linux X11 clipboard (`xclip`) and `xdotool`.
17. **`keyboard_press(key)`**
    - Presses an individual keyboard key (e.g. `'Return'`, `'Tab'`, `'Escape'`, `'BackSpace'`, `'space'`, `'Up'`, `'Down'`).
18. **`keyboard_hotkey(keys)`**
    - Triggers hotkey combinations (e.g. `['ctrl', 'c']`, `['alt', 'tab']`, `['ctrl', 'shift', 't']`).

---

## Keyboard Input & Unicode/Arabic Cadence

### Cadence & Keystroke Jitter
- Standard word pacing ($1 \text{ word} = 5 \text{ characters}$):
  $$t_{\text{base}} = \frac{60}{5 \times \text{WPM}} \text{ seconds}$$
- Jittered interval $t_i = t_{\text{base}} \times \mathcal{U}(0.7, 1.3)$ with cognitive pauses on word boundaries and punctuation (+40–180ms).

### Arabic & Unicode Engine
- Enforces prompt character mapping rules: converts Arabic character "٩" (U+0669) to Arabic letter "ج".
- When running on Linux X11 (`DISPLAY=:0`), injects Unicode text via `xclip -selection clipboard -t UTF8_STRING` and dispatches `ctrl+v`, bypassing X11 keyboard layout mismatches while preserving full UTF-8 character fidelity.

---

## Dependencies & Environment Variables

### Python Dependencies
- `torch >= 2.0.0`: PyTorch deep learning framework for neural trajectory models.
- `mss >= 10.0.0`: High-speed cross-platform screen grabber.
- `pillow >= 10.0.0`: Image processing, TrueType font rendering, and RGBA compositing.
- `mcp >= 1.2.0`: Model Context Protocol server definitions.
- `uvicorn >= 0.31.0`: Async ASGI/SSE server runner.

### System Utilities
- `xdotool`: X11 automation tool for mouse motion, clicking, key presses, and hotkeys.
- `xclip`: X11 clipboard utility for lossless Unicode/Arabic text injection.
- `DISPLAY`: X11 display socket (e.g. `:0`). Auto-detected from `/tmp/.X11-unix/X0` when running in subshells.
