use std::collections::HashMap;
use std::io::stdout;
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
    glyphs, GaugeLayout, QuotaGaugesWidget, SplitMode, SplitPanesWidget,
    StatusBarWidget, Theme, ThemeMode, WorkerListWidget,
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
    tui_core::benchmarks::run_full_benchmark_suite().await?;
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
    let mut theme = Theme::new(ThemeMode::TokyoNight);
    let hourly_quota = 85.0;
    let weekly_quota = 92.0;
    let mut cpu_usage = 18.5;
    let mem_mb = (2780, 8192);

    loop {
        let sessions = engine.sessions();
        let active_idx = engine.session_manager.active_index();
        let p = theme.palette();

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
                        Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD)
                    } else {
                        Style::default().fg(p.fg_muted)
                    };
                    let icon = if is_active { glyphs::POINTER } else { " " };
                    Line::from(vec![
                        Span::raw(format!(" {} {}:{}[Alt+{}] ", icon, s.id, s.slot_id, i + 1)),
                    ]).style(style)
                })
                .collect();

            let tabs_title = format!(" Mind TUI Engine [{}] ", theme.mode.label());
            let tabs = Tabs::new(tab_titles)
                .block(
                    Block::default()
                        .borders(Borders::ALL)
                        .border_style(theme.inactive_border_style())
                        .title(tabs_title),
                )
                .select(active_idx)
                .highlight_style(
                    Style::default()
                        .fg(p.accent_yellow)
                        .add_modifier(Modifier::UNDERLINED | Modifier::BOLD),
                );
            f.render_widget(tabs, header_chunks[0]);

            let top_gauges = QuotaGaugesWidget::new()
                .hourly_remaining(hourly_quota)
                .weekly_remaining(weekly_quota)
                .cpu_usage(cpu_usage)
                .memory(mem_mb.0, mem_mb.1)
                .theme(theme)
                .layout(GaugeLayout::Horizontal)
                .block(
                    Block::default()
                        .borders(Borders::ALL)
                        .border_style(theme.inactive_border_style())
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
                    .theme(theme)
                    .block(
                        Block::default()
                            .borders(Borders::ALL)
                            .border_style(theme.inactive_border_style())
                            .title(" Active Swarm Workers "),
                    );
                f.render_widget(worker_list, sidebar_chunks[0]);

                let side_gauges = QuotaGaugesWidget::new()
                    .hourly_remaining(hourly_quota)
                    .weekly_remaining(weekly_quota)
                    .cpu_usage(cpu_usage)
                    .memory(mem_mb.0, mem_mb.1)
                    .theme(theme)
                    .layout(GaugeLayout::Vertical)
                    .block(
                        Block::default()
                            .borders(Borders::ALL)
                            .border_style(theme.inactive_border_style())
                            .title(" Quota Monitor "),
                    );
                f.render_widget(side_gauges, sidebar_chunks[1]);

                // Split Panes in main area
                let split_panes = SplitPanesWidget::new(split_mode)
                    .sessions(sessions.clone())
                    .focused_index(active_idx)
                    .theme(theme);
                f.render_widget(split_panes, workspace_chunks[1]);
            } else {
                // Fullscreen Split Panes
                let split_panes = SplitPanesWidget::new(split_mode)
                    .sessions(sessions.clone())
                    .focused_index(active_idx)
                    .theme(theme);
                f.render_widget(split_panes, root_chunks[1]);
            }

            // 3. Status Bar at Bottom
            let active_session = engine.active_session();
            let model_name = active_session.as_ref().map(|s| s.model()).unwrap_or_else(|| "none".to_string());
            let hint_text = "Tab/Shift+Tab: Tab │ Alt+1-9: Worker │ F2/Alt+S: Split │ F1/Alt+B: Side │ F4/Alt+T: Theme │ PgUp/Dn: Scroll │ ^C: Int │ ^Q: Quit";
            let status_bar = if let Some(ref session) = active_session {
                StatusBarWidget::from_session(session, &model_name)
                    .split_mode(split_mode.label())
                    .theme(theme)
                    .custom_hint(hint_text)
            } else {
                StatusBarWidget::new("idle", "none")
                    .split_mode(split_mode.label())
                    .theme(theme)
                    .custom_hint(hint_text)
            };
            f.render_widget(status_bar, root_chunks[2]);
        })?;

        if let Some(event) = engine.next_event().await {
            match event {
                AppEvent::Key(key) => {
                    // Quit application: Ctrl+Q
                    if key.code == KeyCode::Char('q') && key.modifiers.contains(KeyModifiers::CONTROL) {
                        break;
                    }

                    // Direct worker selection: Alt+1 through Alt+9
                    if key.modifiers.contains(KeyModifiers::ALT) {
                        if let KeyCode::Char(c) = key.code {
                            if ('1'..='9').contains(&c) {
                                let target_idx = (c as usize) - ('1' as usize);
                                engine.session_manager.select_index(target_idx);
                                continue;
                            }
                        }
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

                    // Toggle Theme Mode: F4 or Alt+T
                    if key.code == KeyCode::F(4) || (key.code == KeyCode::Char('t') && key.modifiers.contains(KeyModifiers::ALT)) {
                        theme = Theme::new(theme.mode.next());
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

                    // Scrollback history: PageUp or Shift+Up
                    if key.code == KeyCode::PageUp || (key.code == KeyCode::Up && key.modifiers.contains(KeyModifiers::SHIFT)) {
                        if let Some(session) = engine.active_session() {
                            session.scroll_up(5);
                        }
                        continue;
                    }

                    // Scrollback history: PageDown or Shift+Down
                    if key.code == KeyCode::PageDown || (key.code == KeyCode::Down && key.modifiers.contains(KeyModifiers::SHIFT)) {
                        if let Some(session) = engine.active_session() {
                            session.scroll_down(5);
                        }
                        continue;
                    }

                    // Tab navigation: Tab / Shift+Tab / BackTab
                    if (key.code == KeyCode::Tab && key.modifiers.contains(KeyModifiers::SHIFT)) || key.code == KeyCode::BackTab {
                        engine.session_manager.prev_session();
                        continue;
                    } else if key.code == KeyCode::Tab {
                        engine.session_manager.next_session();
                        continue;
                    }

                    // Interrupt active worker: Ctrl+C
                    if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) {
                        engine.interrupt_active().ok();
                        continue;
                    }

                    // Worker input delivery (automatically resets scrollback offset)
                    if let KeyCode::Char(c) = key.code {
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

    engine.shutdown();
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen, cursor::Show)?;
    Ok(())
}
