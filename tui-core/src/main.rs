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
    widgets::{Block, Borders, Clear, Paragraph, Tabs},
    Terminal,
};
use tracing::Level;
use tracing_subscriber::FmtSubscriber;

use tui_core::events::AppEvent;
use tui_core::session::{Action, SessionStore};
use tui_core::ui::{
    glyphs, GaugeLayout, QuotaGaugesWidget, SplitMode, SplitPanesWidget,
    StatusBarWidget, Theme, ThemeMode, WorkerListWidget,
};
use tui_core::TuiEngine;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    let subcmd = args.get(1).map(|s| s.as_str()).unwrap_or("");

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

    // Mode: Sessions CLI Management (`agi sessions`, `agi sessions --clean`)
    if subcmd == "sessions" || args.iter().any(|a| a == "sessions") {
        let is_clean = args.iter().any(|a| a == "--clean");
        handle_sessions_cli(is_clean)?;
        return Ok(());
    }

    // Mode: Create New Session (`agi new <name>`)
    if subcmd == "new" {
        let session_name = args.get(2).map(|s| s.as_str()).unwrap_or("session_1");
        run_tui_app(Some(session_name.to_string())).await?;
        return Ok(());
    }

    // Mode: Interactive Ratatui Terminal Multiplexer (`agi` or `agi run`)
    let run_session = if subcmd == "run" {
        args.get(2).cloned()
    } else {
        None
    };
    run_tui_app(run_session).await?;
    Ok(())
}

fn handle_sessions_cli(clean: bool) -> Result<(), Box<dyn std::error::Error>> {
    let store = SessionStore::new();
    if clean {
        let deleted = store.clean_sessions()?;
        println!("Cleaned {} inactive/empty session(s).", deleted);
    }

    let sessions = store.list_sessions()?;
    if sessions.is_empty() {
        println!("No saved sessions found in {}.", store.sessions_dir().display());
        println!("Use 'agi new <name>' to create and launch a new multi-agent session.");
        return Ok(());
    }

    println!("\n{:<22} {:<10} {:<12} {:<24} {:<30}", "SESSION NAME", "STATUS", "WORKERS", "LAST ACTIVE", "GOAL");
    println!("{}", "-".repeat(100));
    for s in sessions {
        let workers_str = format!("{} workers", s.agent_count);
        let goal_snippet = if s.goal.len() > 28 {
            format!("{}...", &s.goal[..25])
        } else {
            s.goal.clone()
        };
        println!("{:<22} {:<10} {:<12} {:<24} {:<30}", s.name, s.status.to_uppercase(), workers_str, s.last_activity, goal_snippet);
    }
    println!();
    Ok(())
}

async fn run_benchmarks() -> Result<(), Box<dyn std::error::Error>> {
    tui_core::benchmarks::run_full_benchmark_suite().await?;
    Ok(())
}

async fn run_tui_app(session_name: Option<String>) -> Result<(), Box<dyn std::error::Error>> {
    enable_raw_mode()?;
    let mut stdout = stdout();
    execute!(stdout, EnterAlternateScreen, cursor::Hide)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let engine = TuiEngine::default();
    let shell_cmd = if cfg!(windows) { "powershell.exe" } else { "bash" };
    let (rows, cols) = (terminal.size()?.height, terminal.size()?.width);

    // Resolve target session name (explicit arg > config default > most recent > "default")
    let target_name = session_name
        .or_else(|| engine.shortcut_engine.config().general.default_session.clone())
        .unwrap_or_else(|| {
            let list = engine.session_manager.store().list_sessions().unwrap_or_default();
            list.first().map(|s| s.name.clone()).unwrap_or_else(|| "default".to_string())
        });

    // Restore existing session or provision new default with real discovered slots
    if engine.session_manager.store().get_session(&target_name)?.is_some() {
        let _ = engine.session_manager.load_and_restore_session(&target_name, shell_cmd, rows, cols);
    } else {
        let _ = engine.session_manager.create_and_launch_session(&target_name, shell_cmd, rows, cols);
    }

    engine.resize_all(rows, cols);

    let mut split_mode = SplitMode::Horizontal;
    let mut show_sidebar = true;
    let mut show_help_modal = false;
    let mut active_modal_notice: Option<String> = None;
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
                    Constraint::Length(3), // Header & Tabs
                    Constraint::Min(8),    // Body (Panes + Sidebar)
                    Constraint::Length(2), // Status Bar
                ])
                .split(f.area());

            // Header Tabs with Tokyo Night styling
            let tab_titles: Vec<Line> = sessions
                .iter()
                .enumerate()
                .map(|(i, s)| {
                    let is_active = i == active_idx;
                    let style = if is_active {
                        Style::default().fg(p.accent_cyan).bg(p.bg_highlight).add_modifier(Modifier::BOLD)
                    } else {
                        Style::default().fg(p.fg_muted).bg(p.bg_surface)
                    };
                    let indicator = if is_active { glyphs::POINTER } else { " " };
                    Line::from(vec![
                        Span::raw(format!(" {} {}:{} ", indicator, s.id, s.slot_id)),
                    ]).style(style)
                })
                .collect();

            let session_title = format!(" AGI Session: {} ", engine.session_manager.current_session_name().unwrap_or_else(|| target_name.clone()));
            let tabs = Tabs::new(tab_titles)
                .block(
                    Block::default()
                        .borders(Borders::ALL)
                        .border_style(Style::default().fg(p.accent_blue))
                        .title(session_title)
                )
                .select(active_idx)
                .highlight_style(Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD));
            f.render_widget(tabs, root_chunks[0]);

            // Body Layout
            let body_chunks = if show_sidebar {
                Layout::default()
                    .direction(Direction::Horizontal)
                    .constraints([
                        Constraint::Min(30),   // Terminal Viewport
                        Constraint::Length(32), // Worker List & Quota Sidebar
                    ])
                    .split(root_chunks[1])
            } else {
                Layout::default()
                    .direction(Direction::Horizontal)
                    .constraints([Constraint::Percentage(100)])
                    .split(root_chunks[1])
            };

            // Terminal Viewport
            let split_widget = SplitPanesWidget::new(split_mode)
                .sessions(sessions.clone())
                .focused_index(active_idx);
            f.render_widget(split_widget, body_chunks[0]);

            // Sidebar
            if show_sidebar && body_chunks.len() > 1 {
                let sidebar_chunks = Layout::default()
                    .direction(Direction::Vertical)
                    .constraints([
                        Constraint::Min(10),   // Worker List
                        Constraint::Length(9), // Quota Gauges
                    ])
                    .split(body_chunks[1]);

                let mut list_state = ratatui::widgets::ListState::default();
                list_state.select(Some(active_idx));
                let worker_list = WorkerListWidget::from_sessions(&sessions, Some(active_idx)).theme(theme);
                f.render_stateful_widget(worker_list, sidebar_chunks[0], &mut list_state);

                let gauges = QuotaGaugesWidget::new()
                    .hourly_remaining(hourly_quota)
                    .weekly_remaining(weekly_quota)
                    .cpu_usage(cpu_usage)
                    .memory(mem_mb.0, mem_mb.1)
                    .layout(GaugeLayout::Horizontal);
                f.render_widget(gauges, sidebar_chunks[1]);
            }

            // Status Bar
            let active_worker = engine.active_session();
            let model_name = active_worker.as_ref().map(|w| w.model()).unwrap_or_else(|| "gemini-3.8-flash-high".to_string());
            let status_bar = if let Some(ref w) = active_worker {
                let mut sb = StatusBarWidget::from_session(w, &model_name).theme(theme);
                if let Some(notice) = &active_modal_notice {
                    sb = sb.alert_badge(tui_core::ui::AlertBadge::Custom(notice.clone(), ratatui::style::Color::Yellow.into()));
                }
                sb
            } else {
                StatusBarWidget::new("none", "0").theme(theme)
            };
            f.render_widget(status_bar, root_chunks[2]);

            // Optional Shortcuts Help Overlay Modal
            if show_help_modal {
                let area = f.area();
                let modal_width = 64.min(area.width.saturating_sub(4));
                let modal_height = 18.min(area.height.saturating_sub(4));
                let modal_area = ratatui::layout::Rect::new(
                    (area.width.saturating_sub(modal_width)) / 2,
                    (area.height.saturating_sub(modal_height)) / 2,
                    modal_width,
                    modal_height,
                );

                f.render_widget(Clear, modal_area);

                let help_text = vec![
                    Line::from(vec![Span::styled(" AGI TUI Shortcuts (Configurable via ~/.config/mind/agi.toml) ", Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD))]),
                    Line::from(""),
                    Line::from("  q / Ctrl+Q       Quit application & persist session"),
                    Line::from("  ?                Toggle this shortcuts help modal"),
                    Line::from("  Tab / Shift+Tab  Cycle worker tab / pane focus"),
                    Line::from("  1..9 / F5..F8    Configurable fast tab jump keys"),
                    Line::from("  m / Ctrl+M       Directive Injection Modal"),
                    Line::from("  d / Ctrl+D       In-app Directive Editor Modal"),
                    Line::from("  o / Ctrl+O       Open directive in external system editor"),
                    Line::from("  s                Toggle split layout (Horizontal <-> Vertical)"),
                    Line::from("  n                Dynamically provision & spawn next agent slot"),
                    Line::from("  b                Toggle worker metadata & quota sidebar"),
                    Line::from("  F4 / Alt+T       Cycle theme (TokyoNight <-> Solarized <-> HighContrast)"),
                    Line::from("  PageUp / Down    Scrollback terminal history navigation"),
                    Line::from(""),
                    Line::from(vec![Span::styled("  Press '?' or 'Esc' to dismiss this modal ", Style::default().fg(p.accent_blue))]),
                ];

                let modal = Paragraph::new(help_text)
                    .block(Block::default().borders(Borders::ALL).border_style(Style::default().fg(p.accent_cyan)).title(" Help: Keyboard Shortcuts "));
                f.render_widget(modal, modal_area);
            }
        })?;

        if let Some(event) = engine.next_event().await {
            match event {
                AppEvent::Key(key) => {
                    // Help modal dismissal with Esc or ?
                    if show_help_modal && (key.code == KeyCode::Esc || key.code == KeyCode::Char('?')) {
                        show_help_modal = false;
                        continue;
                    }

                    // Resolve key through ShortcutEngine
                    let action = engine.shortcut_engine.resolve(&key);

                    match action {
                        Action::Quit => break,
                        Action::Help => {
                            show_help_modal = !show_help_modal;
                            continue;
                        }
                        Action::ToggleSplit => {
                            split_mode = split_mode.next();
                            continue;
                        }
                        Action::NewWorker => {
                            let count = engine.sessions().len();
                            let next_slot_id = match count {
                                0 => "agy1",
                                1 => "agy11",
                                2 => "agy51",
                                3 => "agy100",
                                4 => "agy151",
                                n => format!("agy{}", n + 1).leak(),
                            };
                            let _ = engine.spawn_worker(
                                format!("worker-{}", count + 1),
                                next_slot_id,
                                shell_cmd,
                                vec![],
                                None,
                                HashMap::new(),
                                rows,
                                cols,
                            );
                            active_modal_notice = Some(format!("Spawned {}", next_slot_id));
                            continue;
                        }
                        Action::DirectiveModal => {
                            active_modal_notice = Some("Directive Injection Modal (m)".to_string());
                            continue;
                        }
                        Action::DirectiveEditor => {
                            active_modal_notice = Some("Directive Editor Modal (d)".to_string());
                            continue;
                        }
                        Action::OpenExternalEditor => {
                            active_modal_notice = Some("Opening external editor (o)".to_string());
                            continue;
                        }
                        Action::NextTab | Action::CycleFocus => {
                            engine.session_manager.next_session();
                            continue;
                        }
                        Action::PrevTab | Action::CycleFocusReverse => {
                            engine.session_manager.prev_session();
                            continue;
                        }
                        Action::SelectTab(idx) => {
                            engine.session_manager.select_index(idx);
                            continue;
                        }
                        Action::ScrollUp => {
                            if let Some(s) = engine.active_session() {
                                s.scroll_up(5);
                            }
                            continue;
                        }
                        Action::ScrollDown => {
                            if let Some(s) = engine.active_session() {
                                s.scroll_down(5);
                            }
                            continue;
                        }
                        Action::PassThrough => {
                            // Extra UI shortcuts
                            if key.code == KeyCode::Char('b') {
                                show_sidebar = !show_sidebar;
                                continue;
                            }
                            if key.code == KeyCode::F(4) || (key.code == KeyCode::Char('t') && key.modifiers.contains(KeyModifiers::ALT)) {
                                theme = Theme::new(theme.mode.next());
                                continue;
                            }

                            // Interrupt active worker: Ctrl+C
                            if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) {
                                engine.interrupt_active().ok();
                                active_modal_notice = Some("SIGINT Interrupt (Ctrl+C)".to_string());
                                continue;
                            }

                            // Worker input delivery
                            if let KeyCode::Char(c) = key.code {
                                engine.send_input_to_active(&c.to_string(), false).ok();
                                active_modal_notice = None;
                            } else if key.code == KeyCode::Enter {
                                engine.send_input_to_active("\n", false).ok();
                                active_modal_notice = None;
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
                    }
                }
                AppEvent::Resize(r, c) => {
                    engine.resize_all(r, c);
                }
                AppEvent::Tick => {
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

    // Persist current session state before exit
    let _ = engine.session_manager.save_current_session();
    engine.shutdown();
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen, cursor::Show)?;
    Ok(())
}
