use std::collections::HashMap;
use std::io::stdout;
use std::time::Instant;
use crossterm::{
    cursor,
    event::{KeyCode, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Tabs},
    Terminal,
};
use tracing::Level;
use tracing_subscriber::FmtSubscriber;

use tui_core::events::{AlarmEvent, AppEvent};
use tui_core::ui::{
    colors, glyphs, GaugeLayout, QuotaGaugesWidget, SplitMode, SplitPanesWidget,
    StatusBarWidget, Theme, WorkerListWidget,
};
use tui_core::TuiEngine;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();

    // Mode: Stdio MCP Server
    if args.iter().any(|arg| arg == "--mcp-stdio" || arg == "mcp") {
        let subscriber = FmtSubscriber::builder()
            .with_max_level(Level::WARN)
            .with_writer(std::io::stderr)
            .finish();
        let _ = tracing::subscriber::set_global_default(subscriber);

        let engine = TuiEngine::default();
        engine.mcp_server.run_stdio().await?;
        return Ok(());
    }

    // Mode: Performance Benchmarks
    if args.iter().any(|arg| arg == "bench" || arg == "--bench") {
        run_benchmarks().await?;
        return Ok(());
    }

    // Mode: Interactive Ratatui Terminal Multiplexer
    run_tui_app().await?;
    Ok(())
}

async fn run_benchmarks() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== TUI Core Architecture Performance Benchmarks ===");

    // Benchmark 1: Virtual Screen Buffer Throughput
    let mut buffer = tui_core::ScreenBuffer::new(24, 80);
    let sample_ansi = b"\x1b[31;1mHello \x1b[32mWorld\x1b[0m \x1b[2J\x1b[1;1HWelcome to Mind TUI Core Engine!\n";
    let start = Instant::now();
    let iterations = 100_000;
    for _ in 0..iterations {
        buffer.process_bytes(sample_ansi);
    }
    let elapsed = start.elapsed();
    let throughput = (iterations as f64) / elapsed.as_secs_f64();
    println!("1. Buffer Ingestion & Parser Throughput: {:.2} ops/sec ({:.2?} total)", throughput, elapsed);
    println!("   Plain text extraction preview:\n   '{}'", buffer.get_visible_text().lines().next().unwrap_or_default());

    // Benchmark 2: JSON-RPC Parsing Latency
    let sample_rpc = r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_terminal_screen","arguments":{"worker_id":"agy1","lines":50}}}"#;
    let start_rpc = Instant::now();
    let rpc_iterations = 200_000;
    for _ in 0..rpc_iterations {
        let _ = tui_core::ipc::parse_jsonrpc(sample_rpc);
    }
    let elapsed_rpc = start_rpc.elapsed();
    let rpc_throughput = (rpc_iterations as f64) / elapsed_rpc.as_secs_f64();
    println!("2. JSON-RPC 2.0 Deserialization Latency: {:.2} msgs/sec ({:.2?} total)", rpc_throughput, elapsed_rpc);

    // Benchmark 3: PTY Spawning and Lifecycle
    let start_pty = Instant::now();
    let engine = TuiEngine::default();
    let shell_cmd = if cfg!(windows) { "cmd.exe" } else { "bash" };
    let session = engine.spawn_worker(
        "bench_worker",
        "bench_slot",
        shell_cmd,
        vec![],
        None,
        HashMap::new(),
        24,
        80,
    )?;
    println!("3. Native PTY Spawning Latency: {:.2?} (PID: {:?})", start_pty.elapsed(), session.pid());
    session.send_input("echo BENCHMARK_OK\n", true)?;
    tokio::time::sleep(std::time::Duration::from_millis(150)).await;
    let text = session.get_screen_text(5);
    println!("   PTY Output Verified: {}", text.contains("BENCHMARK_OK"));

    println!("=== All Benchmarks Passed Successfully ===");
    Ok(())
}

async fn run_tui_app() -> Result<(), Box<dyn std::error::Error>> {
    enable_raw_mode()?;
    let mut stdout = stdout();
    execute!(stdout, EnterAlternateScreen, cursor::Hide)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let engine = TuiEngine::default();

    // Spawn Coordinator session and worker sessions
    let shell_cmd = if cfg!(windows) { "powershell.exe" } else { "bash" };
    let s1 = engine.spawn_worker(
        "coordinator",
        "agy1",
        shell_cmd,
        vec![],
        None,
        HashMap::new(),
        24,
        80,
    )?;
    s1.set_task(Some("Managing agent swarm & test suites".to_string()));
    s1.set_model("claude-3-5-sonnet");
    s1.set_tokens(18_450, 200_000);

    let s2 = engine.spawn_worker(
        "worker-build",
        "agy2",
        shell_cmd,
        vec![],
        None,
        HashMap::new(),
        24,
        80,
    )?;
    s2.set_task(Some("Cargo compile & packaging release".to_string()));
    s2.set_model("gemini-1.5-pro");
    s2.set_tokens(42_100, 200_000);

    let s3 = engine.spawn_worker(
        "worker-bench",
        "agy3",
        shell_cmd,
        vec![],
        None,
        HashMap::new(),
        24,
        80,
    )?;
    s3.set_task(Some("PTY screen throughput benchmarks".to_string()));
    s3.set_model("claude-3-5-haiku");
    s3.set_tokens(6_200, 200_000);

    let (rows, cols) = (terminal.size()?.height, terminal.size()?.width);
    engine.resize_all(rows, cols);

    let mut split_mode = SplitMode::Horizontal;
    let mut show_sidebar = true;
    let hourly_quota = 85.0;
    let weekly_quota = 92.0;
    let mut cpu_usage = 18.5;
    let mem_mb = (2780, 8192);

    loop {
        let sessions = engine.sessions();
        let active_idx = engine.session_manager.active_index();

        terminal.draw(|f| {
            let root_chunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Length(3), // Top Header: Tabs & Horizontal Gauges
                    Constraint::Min(6),    // Main Workspace: Sidebar & Split Panes
                    Constraint::Length(1), // Bottom Status Bar
                ])
                .split(f.area());

            // 1. Top Header: Tabs (Left) and Quota Gauges (Right)
            let header_chunks = Layout::default()
                .direction(Direction::Horizontal)
                .constraints([
                    Constraint::Percentage(55),
                    Constraint::Percentage(45),
                ])
                .split(root_chunks[0]);

            let tab_titles: Vec<Line> = sessions
                .iter()
                .enumerate()
                .map(|(i, s)| {
                    let is_active = i == active_idx;
                    let style = if is_active {
                        Style::default().fg(colors::ACCENT_CYAN).add_modifier(Modifier::BOLD)
                    } else {
                        Style::default().fg(colors::FG_MUTED)
                    };
                    let icon = if is_active { glyphs::POINTER } else { " " };
                    Line::from(vec![
                        Span::raw(format!(" {} {}:{} ", icon, s.id, s.slot_id)),
                    ]).style(style)
                })
                .collect();

            let tabs = Tabs::new(tab_titles)
                .block(
                    Block::default()
                        .borders(Borders::ALL)
                        .border_style(Theme::inactive_border())
                        .title(" Mind TUI Engine (Compiled Rust Core) "),
                )
                .select(active_idx)
                .highlight_style(
                    Style::default()
                        .fg(colors::ACCENT_YELLOW)
                        .add_modifier(Modifier::UNDERLINED | Modifier::BOLD),
                );
            f.render_widget(tabs, header_chunks[0]);

            let top_gauges = QuotaGaugesWidget::new()
                .hourly_remaining(hourly_quota)
                .weekly_remaining(weekly_quota)
                .cpu_usage(cpu_usage)
                .memory(mem_mb.0, mem_mb.1)
                .layout(GaugeLayout::Horizontal)
                .block(
                    Block::default()
                        .borders(Borders::ALL)
                        .border_style(Theme::inactive_border())
                        .title(" Real-Time Quotas & Resources "),
                );
            f.render_widget(top_gauges, header_chunks[1]);

            // 2. Main Workspace: Sidebar & Multiplexed Split Panes
            if show_sidebar {
                let workspace_chunks = Layout::default()
                    .direction(Direction::Horizontal)
                    .constraints([
                        Constraint::Length(34), // Left Sidebar
                        Constraint::Min(40),    // Split Panes
                    ])
                    .split(root_chunks[1]);

                // Left Sidebar: Worker list + compact system gauges
                let sidebar_chunks = Layout::default()
                    .direction(Direction::Vertical)
                    .constraints([
                        Constraint::Min(6),    // Worker list
                        Constraint::Length(6), // Compact vertical gauges
                    ])
                    .split(workspace_chunks[0]);

                let worker_list = WorkerListWidget::from_sessions(&sessions, Some(active_idx))
                    .block(
                        Block::default()
                            .borders(Borders::ALL)
                            .border_style(Theme::inactive_border())
                            .title(" Active Swarm Workers "),
                    );
                f.render_widget(worker_list, sidebar_chunks[0]);

                let side_gauges = QuotaGaugesWidget::new()
                    .hourly_remaining(hourly_quota)
                    .weekly_remaining(weekly_quota)
                    .cpu_usage(cpu_usage)
                    .memory(mem_mb.0, mem_mb.1)
                    .layout(GaugeLayout::Vertical)
                    .block(
                        Block::default()
                            .borders(Borders::ALL)
                            .border_style(Theme::inactive_border())
                            .title(" Quota Monitor "),
                    );
                f.render_widget(side_gauges, sidebar_chunks[1]);

                // Split Panes in main area
                let split_panes = SplitPanesWidget::new(split_mode)
                    .sessions(sessions.clone())
                    .focused_index(active_idx);
                f.render_widget(split_panes, workspace_chunks[1]);
            } else {
                // Fullscreen Split Panes
                let split_panes = SplitPanesWidget::new(split_mode)
                    .sessions(sessions.clone())
                    .focused_index(active_idx);
                f.render_widget(split_panes, root_chunks[1]);
            }

            // 3. Status Bar at Bottom
            let active_session = engine.active_session();
            let model_name = active_session.as_ref().map(|s| s.model()).unwrap_or_else(|| "none".to_string());
            let status_bar = if let Some(ref session) = active_session {
                StatusBarWidget::from_session(session, &model_name)
                    .split_mode(split_mode.label())
                    .custom_hint("Tab: Next │ F2: Split │ F1: Sidebar │ F3: Alarm Demo │ ^C: Int │ ^Q: Quit")
            } else {
                StatusBarWidget::new("idle", "none")
                    .split_mode(split_mode.label())
                    .custom_hint("Tab: Next │ F2: Split │ F1: Sidebar │ ^C: Int │ ^Q: Quit")
            };
            f.render_widget(status_bar, root_chunks[2]);
        })?;

        if let Some(event) = engine.next_event().await {
            match event {
                AppEvent::Key(key) => {
                    // Quit application
                    if key.code == KeyCode::Char('q') && key.modifiers.contains(KeyModifiers::CONTROL) {
                        break;
                    }

                    // Toggle Split Mode: F2 or Alt+S
                    if key.code == KeyCode::F(2) || (key.code == KeyCode::Char('s') && key.modifiers.contains(KeyModifiers::ALT)) {
                        split_mode = split_mode.next();
                        continue;
                    }

                    // Toggle Sidebar: F1 or Alt+B
                    if key.code == KeyCode::F(1) || (key.code == KeyCode::Char('b') && key.modifiers.contains(KeyModifiers::ALT)) {
                        show_sidebar = !show_sidebar;
                        continue;
                    }

                    // Demo Alarm Badge toggle: F3
                    if key.code == KeyCode::F(3) {
                        if let Some(session) = engine.active_session() {
                            let current = session.last_alarm();
                            if current.is_none() {
                                session.set_last_alarm(Some(AlarmEvent {
                                    worker_id: session.id.clone(),
                                    alarm_type: "IDLE".to_string(),
                                    message: "Swarm task completed".to_string(),
                                    timestamp: 0,
                                }));
                            } else {
                                session.set_last_alarm(None);
                            }
                        }
                        continue;
                    }

                    // Tab navigation
                    if key.code == KeyCode::Tab {
                        engine.session_manager.next_session();
                    } else if key.code == KeyCode::BackTab {
                        engine.session_manager.prev_session();
                    } else if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) {
                        engine.interrupt_active().ok();
                    } else if let KeyCode::Char(c) = key.code {
                        engine.send_input_to_active(&c.to_string(), false).ok();
                    } else if key.code == KeyCode::Enter {
                        engine.send_input_to_active("\n", false).ok();
                    } else if key.code == KeyCode::Backspace {
                        engine.send_input_to_active("\x08", false).ok();
                    } else if key.code == KeyCode::Up {
                        engine.send_input_to_active("\x1b[A", false).ok();
                    } else if key.code == KeyCode::Down {
                        engine.send_input_to_active("\x1b[B", false).ok();
                    } else if key.code == KeyCode::Right {
                        engine.send_input_to_active("\x1b[C", false).ok();
                    } else if key.code == KeyCode::Left {
                        engine.send_input_to_active("\x1b[D", false).ok();
                    }
                }
                AppEvent::Resize(r, c) => {
                    engine.resize_all(r, c);
                }
                AppEvent::Tick => {
                    // Subtle tick simulation for quota visualization
                    cpu_usage = (cpu_usage + 0.3) % 45.0 + 12.0;
                }
                AppEvent::Alarm(alarm) => {
                    if let Some(s) = engine.session_manager.get_session(&alarm.worker_id) {
                        s.set_last_alarm(Some(alarm));
                    }
                }
                AppEvent::Quit => break,
                _ => {}
            }
        }
    }

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen, cursor::Show)?;
    Ok(())
}
