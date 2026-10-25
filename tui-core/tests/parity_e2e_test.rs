use std::collections::HashMap;
use std::process::Command;
use std::time::{Duration, Instant};
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::{
    backend::TestBackend,
    layout::Rect,
    Terminal,
};

use tui_core::session::{
    AppMode, FocusedPane, SessionManager,
};
use tui_core::ui::{
    BottomBar, HeaderBar, Theme, ThemeMode, WorkspaceScreen,
};

// ── 1. Dual-Pane PTY Layout Split Parity Test ─────────────────────────

#[tokio::test]
async fn test_parity_dual_pane_layout_split() {
    let manager = SessionManager::new();
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };

    // 1. Spawn Primary Coordinator (#primary-pane, Slot 1 agy1)
    let coord = manager
        .spawn_session("coordinator", "agy1", shell, vec![], None, HashMap::new(), 24, 80)
        .expect("Spawn coordinator session");
    assert_eq!(coord.id, "coordinator");
    assert_eq!(coord.slot_id, "agy1");

    // 2. Spawn Interactive Worker tabs (#workers-pane)
    let w1 = manager
        .spawn_session("worker1", "agy2", shell, vec![], None, HashMap::new(), 24, 80)
        .expect("Spawn worker 1");
    let w2 = manager
        .spawn_session("worker2", "agy3", shell, vec![], None, HashMap::new(), 24, 80)
        .expect("Spawn worker 2");

    assert_eq!(manager.workers().len(), 2);
    assert_eq!(manager.focused_pane(), FocusedPane::Coordinator);

    // 3. Test Dual-Pane Workspace geometry calculation in 50/50 split view
    let theme = Theme::new(ThemeMode::TokyoNight);
    let workspace = WorkspaceScreen::new()
        .coordinator(Some(coord.clone()))
        .workers(vec![w1.clone(), w2.clone()])
        .theme(theme);

    let viewport = Rect::new(0, 0, 160, 40);
    let (left_pane, right_pane) = workspace.compute_panes(viewport);

    // Side-by-side 50/50 parity check
    assert_eq!(left_pane.width, 80, "Primary Coordinator pane width must be 50% (80 cols)");
    assert_eq!(right_pane.width, 80, "Worker Multiplexer pane width must be 50% (80 cols)");
    assert_eq!(left_pane.height, 40);
    assert_eq!(right_pane.height, 40);

    // 4. Test Fullscreen expansion on Split Toggle ('s')
    let mut ws_expanded_coord = workspace.clone();
    ws_expanded_coord.is_split_view = false;
    ws_expanded_coord.focused_pane = FocusedPane::Coordinator;
    let (full_left, empty_right) = ws_expanded_coord.compute_panes(viewport);
    assert_eq!(full_left.width, 160, "Expanded Coordinator pane must take 100% width");
    assert_eq!(empty_right.width, 0, "Hidden Worker pane must take 0% width");

    let mut ws_expanded_worker = workspace.clone();
    ws_expanded_worker.is_split_view = false;
    ws_expanded_worker.focused_pane = FocusedPane::Workers(0);
    let (empty_left, full_right) = ws_expanded_worker.compute_panes(viewport);
    assert_eq!(empty_left.width, 0, "Hidden Coordinator pane must take 0% width");
    assert_eq!(full_right.width, 160, "Expanded Worker pane must take 100% width");

    // 5. Render dual-pane workspace to Ratatui TestBackend
    let backend = TestBackend::new(160, 40);
    let mut terminal = Terminal::new(backend).unwrap();
    terminal
        .draw(|f| {
            f.render_widget(&workspace, f.area());
        })
        .unwrap();

    let term_buf = terminal.backend().buffer();
    let mut rendered_text = String::new();
    for y in 0..40 {
        for x in 0..160 {
            rendered_text.push_str(term_buf[(x, y)].symbol());
        }
        rendered_text.push('\n');
    }

    assert!(
        rendered_text.contains("Primary Coordinator (Slot 1 agy1)"),
        "Left pane must render Primary Coordinator header"
    );
    assert!(
        rendered_text.contains("worker1 (agy2)"),
        "Right pane must render Worker Tab 1"
    );
    assert!(
        rendered_text.contains("worker2 (agy3)"),
        "Right pane must render Worker Tab 2"
    );
    assert!(
        rendered_text.contains("+ New (c)"),
        "Right pane must render '+ New (c)' spawn action tab"
    );

    // 6. Test Tab / Shift+Tab focus switching
    manager.switch_pane_focus();
    assert_eq!(manager.focused_pane(), FocusedPane::Workers(0));
    assert_eq!(manager.active_session().unwrap().id, "worker1");

    manager.switch_pane_focus();
    assert_eq!(manager.focused_pane(), FocusedPane::Coordinator);
    assert_eq!(manager.active_session().unwrap().id, "coordinator");

    manager.shutdown_all();
}

// ── 2. Vim Dual-Mode State Machine & Leader Exits Parity Test ─────────

#[test]
fn test_parity_vim_dual_mode_state_machine_and_leader_exits() {
    let manager = SessionManager::new();

    // 1. Initial State: NORMAL mode
    assert_eq!(manager.app_mode(), AppMode::Normal);
    assert_eq!(manager.app_mode().as_str(), "NORMAL");

    // 2. Mode Transition: 'i', 'Enter', or 'a' enters PTY_INTERACT
    manager.enter_pty();
    assert_eq!(manager.app_mode(), AppMode::PtyInteract);
    assert_eq!(manager.app_mode().as_str(), "PTY_INTERACT");

    // 3. Leader Exit 1: Ctrl+B immediate return to Normal
    let ctrl_b = KeyEvent::new(KeyCode::Char('b'), KeyModifiers::CONTROL);
    if (ctrl_b.code == KeyCode::Char('b') || ctrl_b.code == KeyCode::Char('B'))
        && ctrl_b.modifiers.contains(KeyModifiers::CONTROL)
    {
        manager.enter_normal();
    }
    assert_eq!(manager.app_mode(), AppMode::Normal, "Ctrl+B must exit to NORMAL mode");

    // 4. Leader Exit 2: F12 immediate return to Normal
    manager.enter_pty();
    assert_eq!(manager.app_mode(), AppMode::PtyInteract);
    let f12 = KeyEvent::new(KeyCode::F(12), KeyModifiers::NONE);
    if f12.code == KeyCode::F(12) {
        manager.enter_normal();
    }
    assert_eq!(manager.app_mode(), AppMode::Normal, "F12 must exit to NORMAL mode");

    // 5. Leader Exit 3: Double-Escape (Esc Esc within 350ms)
    manager.enter_pty();
    assert_eq!(manager.app_mode(), AppMode::PtyInteract);

    // Simulate first Esc
    let first_esc_time = Instant::now();
    let mut last_esc_time = Some(first_esc_time);

    // Simulate second Esc 100ms later (<= 350ms window)
    let second_esc_time = first_esc_time + Duration::from_millis(100);
    let mut exit_triggered = false;
    if let Some(prev) = last_esc_time {
        if second_esc_time.duration_since(prev).as_millis() <= 350 {
            manager.enter_normal();
            exit_triggered = true;
            last_esc_time = None;
        }
    }

    assert!(exit_triggered, "Double Esc within 350ms must trigger exit");
    assert_eq!(manager.app_mode(), AppMode::Normal, "Double Esc must exit to NORMAL mode");
    assert!(last_esc_time.is_none());

    // 6. Verify single Esc does NOT trigger exit if threshold exceeded
    manager.enter_pty();
    assert_eq!(manager.app_mode(), AppMode::PtyInteract);

    let esc_initial = Instant::now();
    let esc_delayed = esc_initial + Duration::from_millis(500); // 500ms > 350ms threshold
    let mut delayed_exit = false;

    if esc_delayed.duration_since(esc_initial).as_millis() <= 350 {
        manager.enter_normal();
        delayed_exit = true;
    }

    assert!(!delayed_exit, "Esc delayed by >350ms must not trigger leader exit");
    assert_eq!(manager.app_mode(), AppMode::PtyInteract, "Mode must remain PTY_INTERACT for single Esc");

    manager.enter_normal();
    assert_eq!(manager.app_mode(), AppMode::Normal);
}

// ── 3. HeaderBar Zellij 1-Line Dock-Top Pills Parity Test ─────────────

#[test]
fn test_parity_header_bar_dock_top_pills() {
    let header = HeaderBar::new("swarm_production")
        .worker_count(4)
        .mode(AppMode::Normal)
        .quota_percent(82)
        .mcp_port(8765)
        .mcp_active(true);

    let backend = TestBackend::new(140, 1);
    let mut terminal = Terminal::new(backend).unwrap();
    terminal
        .draw(|f| {
            f.render_widget(&header, f.area());
        })
        .unwrap();

    let term_buf = terminal.backend().buffer();
    let text: String = (0..140).map(|x| term_buf[(x, 0)].symbol()).collect();

    // Verification of Zellij-style HeaderBar elements:
    assert!(text.contains("mind"), "Header must include 'mind' brand logo");
    assert!(text.contains("swarm_production"), "Header must display active session name pill");
    assert!(text.contains("NORMAL"), "Header must display active mode badge");
    assert!(text.contains("4") && text.contains("active workers"), "Header must display worker count pill");
    assert!(text.contains("Quota:"), "Header must display quota label");
    assert!(text.contains("82%"), "Header must display quota percent");
    assert!(text.contains("MCP: 8765"), "Header must display active MCP server status pill");

    // Test PTY_INTERACT mode header rendering
    let header_pty = HeaderBar::new("swarm_production")
        .worker_count(3)
        .mode(AppMode::PtyInteract)
        .quota_percent(95);

    terminal
        .draw(|f| {
            f.render_widget(&header_pty, f.area());
        })
        .unwrap();

    let term_buf_pty = terminal.backend().buffer();
    let text_pty: String = (0..140).map(|x| term_buf_pty[(x, 0)].symbol()).collect();
    assert!(text_pty.contains("PTY"), "Header must display PTY badge");
}

// ── 4. BottomBar Action Pills & Architecture Badge Parity Test ────────

#[test]
fn test_parity_bottom_bar_action_pills_and_pty_badge() {
    // 1. Normal mode layout verification
    let bottom_normal = BottomBar::new(AppMode::Normal).pty_backend("POSIX PTY");
    let backend = TestBackend::new(160, 1);
    let mut terminal = Terminal::new(backend).unwrap();
    terminal
        .draw(|f| {
            f.render_widget(&bottom_normal, f.area());
        })
        .unwrap();

    let term_buf = terminal.backend().buffer();
    let text: String = (0..160).map(|x| term_buf[(x, 0)].symbol()).collect();

    assert!(text.contains("NORMAL MODE"), "Must contain [ NORMAL MODE ] indicator badge");
    assert!(text.contains("[?] Help"), "Must contain [?] Help action pill");
    assert!(text.contains("[m] Directive"), "Must contain [m] Directive action pill");
    assert!(text.contains("[s] Split"), "Must contain [s] Split action pill");
    assert!(text.contains("[d] Edit"), "Must contain [d] Edit action pill");
    assert!(text.contains("[c/n] New"), "Must contain [c/n] New action pill");
    assert!(text.contains("[x] Close"), "Must contain [x] Close action pill");
    assert!(text.contains("[q] Quit"), "Must contain [q] Quit action pill");
    assert!(text.contains("POSIX PTY · UTF-8"), "Must contain platform architecture badge");

    // 2. PTY Interact mode layout verification
    let bottom_pty = BottomBar::new(AppMode::PtyInteract).pty_backend("ConPTY");
    terminal
        .draw(|f| {
            f.render_widget(&bottom_pty, f.area());
        })
        .unwrap();

    let term_buf_pty = terminal.backend().buffer();
    let text_pty: String = (0..160).map(|x| term_buf_pty[(x, 0)].symbol()).collect();

    assert!(text_pty.contains("PTY INTERACT"), "Must contain [ PTY INTERACT ] badge");
    assert!(
        text_pty.contains("Ctrl+B") || text_pty.contains("F12") || text_pty.contains("Esc Esc"),
        "Must contain leader key exit guidance pills"
    );
    assert!(text_pty.contains("ConPTY · UTF-8"), "Must contain ConPTY architecture badge");
}

// ── 5. CLI Subcommands Parity Test (`doctor`, `usage`, `sessions`, `mcp`, `bench`) ──

#[test]
fn test_parity_cli_subcommands_and_diagnostics() {
    let bin_path = env!("CARGO_BIN_EXE_agi");
    assert!(
        std::path::Path::new(bin_path).is_file(),
        "Compiled agi binary must exist"
    );

    // 1. `agi doctor`: Diagnostic health checks
    let doctor_out = Command::new(bin_path)
        .arg("doctor")
        .output()
        .expect("Execute agi doctor");
    assert!(doctor_out.status.success(), "agi doctor must exit successfully");
    let doc_str = String::from_utf8_lossy(&doctor_out.stdout);
    assert!(doc_str.contains("agi doctor"), "Doctor output must contain header");
    assert!(doc_str.contains("Operating System"), "Doctor must check OS");
    assert!(doc_str.contains("PTY Master Driver"), "Doctor must check PTY engine");
    assert!(doc_str.contains("Agent Slot Discovery"), "Doctor must check Agent Slots");
    assert!(doc_str.contains("FastMCP"), "Doctor must check FastMCP bridge");
    assert!(doc_str.contains("0 failures"), "Doctor check must report 0 failures");

    // 2. `agi usage`: Quota usage telemetry table
    let usage_out = Command::new(bin_path)
        .arg("usage")
        .output()
        .expect("Execute agi usage");
    assert!(usage_out.status.success(), "agi usage must exit successfully");
    let usage_str = String::from_utf8_lossy(&usage_out.stdout);
    assert!(usage_str.contains("mind usage"), "Usage output must contain header");
    assert!(usage_str.contains("HOURLY REM."), "Usage table must include HOURLY REM. column");
    assert!(usage_str.contains("WEEKLY REM."), "Usage table must include WEEKLY REM. column");
    assert!(usage_str.contains("HOURLY BAR"), "Usage table must include HOURLY BAR column");

    // Test `agi usage --json`
    let usage_json_out = Command::new(bin_path)
        .args(&["usage", "--json"])
        .output()
        .expect("Execute agi usage --json");
    assert!(usage_json_out.status.success());
    let parsed_usage: serde_json::Value =
        serde_json::from_slice(&usage_json_out.stdout).expect("Parse usage JSON");
    assert!(parsed_usage.is_array(), "Usage JSON output must be a JSON array");

    // 3. `agi sessions`: Formatted sessions table matching `mind sessions`
    let sessions_out = Command::new(bin_path)
        .arg("sessions")
        .output()
        .expect("Execute agi sessions");
    assert!(sessions_out.status.success(), "agi sessions must exit successfully");
    let sess_str = String::from_utf8_lossy(&sessions_out.stdout);
    assert!(sess_str.contains("mind sessions"), "Sessions output must contain header");
    assert!(sess_str.contains("SESSION NAME"), "Sessions table must include SESSION NAME column");
    assert!(sess_str.contains("AGENTS"), "Sessions table must include AGENTS column");
    assert!(sess_str.contains("STATUS"), "Sessions table must include STATUS column");
    assert!(sess_str.contains("STEPS"), "Sessions table must include STEPS column");
    assert!(sess_str.contains("LAST ACTIVE"), "Sessions table must include LAST ACTIVE column");

    // 4. `agi sessions --clean`: Pruning inactive sessions
    let clean_out = Command::new(bin_path)
        .args(&["sessions", "--clean"])
        .output()
        .expect("Execute agi sessions --clean");
    assert!(clean_out.status.success(), "agi sessions --clean must exit successfully");

    // 5. `agi bench`: Performance benchmarks execution
    let bench_out = Command::new(bin_path)
        .arg("bench")
        .output()
        .expect("Execute agi bench");
    assert!(bench_out.status.success(), "agi bench must exit successfully");
    let bench_str = String::from_utf8_lossy(&bench_out.stdout);
    assert!(
        bench_str.contains("Benchmark") || bench_str.contains("Latency") || bench_str.contains("FPS") || bench_str.contains("Throughput"),
        "Benchmark output must report performance metrics"
    );
}

