# `src/mind/mcp/` — High-Performance Async Model Context Protocol (MCP) Server

This directory contains the embedded MCP server (`mind-mcp`) that exposes lightweight, asyncio-native orchestration tools for the primary coordinator agent to inspect worker terminal screens, inject prioritized interrupts, deliver direct inputs, monitor account quotas, coordinate tasks across multiple agents, provide vision perception capabilities for Vision LLMs, and execute biologically authentic human-like mouse interactions using PyTorch AI models and kinematic shaping.

## Architectural Role & Scope

The `mind-mcp` package functions as the central bridge between external AI agents (such as Antigravity CLI instances, LLM orchestrators, and Vision models) and the internal `mind` runtime. It implements:
1. **Agent Coordination & Terminal Telemetry:** Real-time terminal screen scraping, process supervision, quota monitoring, and prioritized directive injection.
2. **Vision-Language Perception & Screen Capture:** High-fidelity screen capture equipped with a calibrated numbered coordinate grid overlay designed specifically for Vision-Language Models (e.g., Gemini Vision, Claude 3.5 Sonnet, GPT-4o) and automated mouse controllers.
3. **AI Natural Human Mouse Interaction:** Integration of `NaturaleMouseEvent` / `human_mouse_engine`, generating authentic, human-like cursor trajectories powered by trained PyTorch GRU neural networks and biomechanical neuromuscular kinematic filtering.
4. **Headless & CI Resilience:** Multi-tier graceful fallback ensuring that when no physical display server or X11/Wayland socket is reachable, simulated desktop canvases and virtual mouse coordinate tracking operate without raising unhandled exceptions or crashing the MCP server.

---

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Public exports for MCP server creation (`create_mcp_server`, `get_default_mcp_server`, `reset_default_mcp_server`), natural mouse controller (`NaturalMouseController`, `get_natural_mouse_controller`, `reset_natural_mouse_controller`, `is_headless_environment`), background daemon runner (`MCPServerRunner`, `start_background_mcp_server`, `stop_background_mcp_server`), screen buffer cache (`TerminalScreenCache`), vision capture utilities (`capture_screen_with_grid`, `get_screen_geometry`, `draw_coordinate_grid`, `capture_raw_screen`, `generate_mock_screen`, `encode_vision_capture`), and stdio entrypoints (`run_stdio_mcp_server`, `run_stdio_mcp_server_async`). |
| `server.py` | FastMCP server definition exposing 16 async MCP tools for terminal control, inter-agent signaling, quota tracking, vision grid capture, and natural human mouse movements. |
| `runner.py` | Dual-transport execution runner supporting: (1) local HTTP SSE server (`uvicorn.Server` on `127.0.0.1:8765`) running fully asynchronously in background without blocking the main application lifecycle (`wait_for_ready=False`), (2) automatic provisioning and persistence of `mind-mcp` across orchestrator instances (`provision_mcp_config`), and (3) Standard I/O (stdio) transport for direct pairing with Antigravity CLI (`mind mcp` / `agy.exe mcp add mind-mcp`). |
| `natural_mouse.py` | High-level AI Natural Mouse Controller wrapping `NaturaleMouseEvent/human_mouse_engine` and offering safe fallbacks for headless Linux environments, persistent virtual cursor tracking, and pure-Python minimum-jerk kinematics modeling. |
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
    - Captures screen frames and overlays a calibrated numbered coordinate grid.
    - Specifically designed for Vision LLMs to perceive interface layouts and extract exact (X, Y) pixel coordinates.
    - Returns structured payload containing base64 data URL (`data:image/jpeg;base64,...`) or saved file path, screen dimensions, calibration metadata, and headless status.
11. **`get_screen_geometry()`**
    - Inspects display hardware geometry, active monitor viewports (left, top, width, height, primary status), resolution, display server identifier, and headless status.
12. **`natural_mouse_move(target_x, target_y, duration_ms=None)`**
    - Moves cursor smoothly from its current coordinates to `(target_x, target_y)` along an authentic human trajectory.
    - Employs trained PyTorch neural networks (or pure-Python minimum-jerk kinematics) conditioned on Fitts's Law duration allocation, Savitzky-Golay filtering, neuromuscular onset inertia, and continuous Ornstein-Uhlenbeck micro-tremors.
    - Returns move telemetry, step count, distance, and duration.
13. **`natural_mouse_click(target_x, target_y, button="left", clicks=1)`**
    - Naturally targets `(target_x, target_y)` and performs authentic human click(s) with realistic inter-click timing (~60–120ms).
    - Supports `'left'`, `'right'`, and `'middle'` mouse buttons.
14. **`natural_mouse_sequence(coordinates, delay_between=0.2, click_targets=False)`**
    - Executes multi-target waypoint sequences with continuous kinematic momentum chaining, avoiding unnatural sharp corners.
    - Accepts coordinate lists in multiple flexible formats: `[[x, y], ...]`, `[(x, y), ...]`, or `[{"x": x, "y": y}, ...]`.
15. **`get_mouse_position()`**
    - Retrieves current cursor coordinates `{"x": float, "y": float, "dry_run": bool, "mode": str}`.
    - Returns live OS coordinates when connected to a display server, or tracked virtual coordinates in headless mode.

---

## Natural Mouse Kinematics & Modeling

### Biomechanical Pipeline
1. **Fitts's Law Step Allocation:**
   $$T = T_{\text{base}} + k \cdot \log_2\left(1 + \frac{D}{W_{\text{ref}}}\right)$$
   Short reaches (~200px) complete naturally in ~250–350ms; long reaches (~1000px) scale smoothly to ~650–850ms.
2. **Flash & Hogan Minimum-Jerk Kinematics:**
   $$s(\tau) = 10\tau^3 - 15\tau^4 + 6\tau^5 \quad \text{where } \tau = \frac{t}{T}$$
   Guarantees zero starting and ending jerk ($\frac{da}{dt} = 0$), continuous acceleration profiles, and elimination of robotic velocity plateaus.
3. **Neuromuscular Onset Ramp & Tremor:**
   - Quintic smoothstep onset modeling motor unit recruitment latency.
   - Continuous 8–12 Hz Ornstein-Uhlenbeck (OU) micro-tremor process with ballistic speed suppression.

---

## Vision Grid Overlay & Calibration Specifications

### Coordinate Calibration Model
The coordinate grid overlay maintains **1:1 pixel fidelity** with the physical screen viewport:
- Origin `(0, 0)` is located at the top-left corner of the display.
- Pixel coordinate `(X, Y)` identified by a Vision model directly matches the physical target position for mouse dispatch tools (`natural_mouse_move(x, y)` or `natural_mouse_click(x, y)`).
- Axes rulers are drawn directly as an alpha-blended overlay without altering or cropping underlying screen coordinates.

---

## Headless & Multi-Tier Fallback Flow

```
[Tool Invocation: Mouse Movement / Click / Screen Capture]
                         │
                         ▼
             [Check Display Environment]
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
 [Display Available]             [Headless Linux / No Display]
  - Query OS cursor position      - Persistent Virtual Cursor (x, y)
  - Execute via PyAutoGUI/X11     - Pure Simulation / Dry-Run
  - Live OS click dispatch        - Fast-Path Kinematics Execution
  - Real screen frame grab        - Mock Canvas Generation
```

---

## Dependencies & Environment Variables

### Python Dependencies
- `torch >= 2.0.0`: PyTorch deep learning framework for neural trajectory models (optional; pure kinematic fallback engages if unavailable).
- `mss >= 10.0.0`: High-speed cross-platform screen grabber.
- `pillow >= 10.0.0`: Image processing, TrueType font rendering, and RGBA compositing.
- `pyautogui >= 0.9.54`: OS-level mouse cursor positioning and click dispatch (falls back gracefully in headless environments).
- `mcp >= 1.2.0`: Model Context Protocol server definitions.
- `uvicorn >= 0.31.0`: Async ASGI/SSE server runner.

### Environment Variables
- `DISPLAY`: X11 display socket (e.g., `:0`).
- `WAYLAND_DISPLAY`: Wayland display socket (e.g., `wayland-0`).
- In headless environments where neither variable is set, all tools operate seamlessly in simulation mode without crashing.
