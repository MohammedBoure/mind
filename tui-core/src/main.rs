use std::io::stdout;
use std::sync::Arc;
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

use tui_core::events::AppEvent;
use tui_core::session::{Action, IdentityDiscovery, SessionStore};
use tui_core::ui::{
    glyphs, DirectiveEditorAction, DirectiveEditorModal, DirectiveModal, DirectiveModalAction,
    GaugeLayout, HelpModal, NewWorkerModal, NewWorkerModalAction, QuotaGaugesWidget,
    SessionPickerAction, SessionPickerScreen, SplitMode, SplitPanesWidget, StatusBarWidget, Theme,
    ThemeMode, WorkerListWidget,
};
use tui_core::{McpBackend, TuiEngine};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum AppScreen {
    Multiplexer,
    SessionPicker,
}

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

    // Mode: Interactive Session Picker Screen (`agi picker`, `agi --picker`)
    if subcmd == "picker" || args.iter().any(|a| a == "--picker") {
        run_tui_app(None, true).await?;
        return Ok(());
    }

    // Mode: Create New Session (`agi new <name>`)
    if subcmd == "new" {
        let session_name = args.get(2).map(|s| s.as_str()).unwrap_or("session_1");
        run_tui_app(Some(session_name.to_string()), false).await?;
        return Ok(());
    }

    // Mode: Interactive Ratatui Terminal Multiplexer (`agi` or `agi run`)
    let run_session = if subcmd == "run" {
        args.get(2).cloned()
    } else {
        None
    };
    run_tui_app(run_session, false).await?;
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

async fn run_tui_app(session_name: Option<String>, start_in_picker: bool) -> Result<(), Box<dyn std::error::Error>> {
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

    let mut current_screen = if start_in_picker {
        AppScreen::SessionPicker
    } else {
        AppScreen::Multiplexer
    };

    let mut split_mode = SplitMode::Horizontal;
    let mut show_sidebar = true;
    let mut active_modal_notice: Option<String> = None;
    let mut theme = Theme::new(ThemeMode::TokyoNight);
    let hourly_quota = 85.0;
    let weekly_quota = 92.0;
    let mut cpu_usage = 18.5;
    let mem_mb = (2780, 8192);

    let mut session_picker = SessionPickerScreen::new(engine.session_manager.store()).theme(theme);
    let mut help_modal: Option<HelpModal> = None;
    let mut directive_modal: Option<DirectiveModal> = None;
    let mut directive_editor_modal: Option<DirectiveEditorModal> = None;
    let mut new_worker_modal: Option<NewWorkerModal> = None;

    loop {
        let sessions = engine.sessions();
        let active_idx = engine.session_manager.active_index();
        let p = theme.palette();

        terminal.draw(|f| {
            if current_screen == AppScreen::SessionPicker {
                f.render_widget(&session_picker, f.area());
                return;
            }

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

            // Overlays: Render any active modal on top
            if let Some(ref modal) = help_modal {
                f.render_widget(modal, f.area());
            } else if let Some(ref modal) = directive_modal {
                f.render_widget(modal, f.area());
            } else if let Some(ref modal) = directive_editor_modal {
                f.render_widget(modal, f.area());
            } else if let Some(ref modal) = new_worker_modal {
                f.render_widget(modal, f.area());
            }
        })?;

        if let Some(event) = engine.next_event().await {
            match event {
                AppEvent::Key(key) => {
                    // 1. Session Picker Screen key handling
                    if current_screen == AppScreen::SessionPicker {
                        match session_picker.handle_key(&key) {
                            SessionPickerAction::Open(rec) => {
                                let _ = engine.session_manager.load_and_restore_session(&rec.name, shell_cmd, rows, cols);
                                current_screen = AppScreen::Multiplexer;
                                active_modal_notice = Some(format!("Opened session '{}'", rec.name));
                            }
                            SessionPickerAction::Create(new_name) => {
                                let _ = engine.session_manager.create_and_launch_session(&new_name, shell_cmd, rows, cols);
                                current_screen = AppScreen::Multiplexer;
                                active_modal_notice = Some(format!("Created session '{}'", new_name));
                            }
                            SessionPickerAction::Delete(deleted_name) => {
                                active_modal_notice = Some(format!("Deleted session '{}'", deleted_name));
                            }
                            SessionPickerAction::Exit => {
                                if engine.sessions().is_empty() {
                                    break;
                                } else {
                                    current_screen = AppScreen::Multiplexer;
                                }
                            }
                            SessionPickerAction::None => {}
                        }
                        continue;
                    }

                    // 2. Help Modal key handling
                    if let Some(ref mut modal) = help_modal {
                        if modal.handle_key(&key) {
                            help_modal = None;
                        }
                        continue;
                    }

                    // 3. Directive Modal key handling
                    if let Some(ref mut modal) = directive_modal {
                        match modal.handle_key(&key) {
                            DirectiveModalAction::Submit { worker_id, message, priority } => {
                                directive_modal = None;
                                let mgr = Arc::clone(&engine.session_manager);
                                let wid = worker_id.clone();
                                tokio::spawn(async move {
                                    let priority_str = priority.as_str().to_string();
                                    let _ = mgr.interrupt_and_inject(&wid, "operator", &message, &priority_str).await;
                                });
                                active_modal_notice = Some(format!("Directive ({:?}) sent to {}", priority, worker_id));
                            }
                            DirectiveModalAction::Cancel => {
                                directive_modal = None;
                            }
                            DirectiveModalAction::None => {}
                        }
                        continue;
                    }

                    // 4. In-App Directive Editor Modal key handling
                    if let Some(ref mut modal) = directive_editor_modal {
                        match modal.handle_key(&key) {
                            DirectiveEditorAction::Save(content) => {
                                let target_id = modal.worker_id.clone();
                                if let Some(worker) = engine.session_manager.get_session(&target_id) {
                                    *worker.task.lock() = Some(content.clone());
                                    let _ = worker.send_input(&content, true);
                                }
                                directive_editor_modal = None;
                                active_modal_notice = Some(format!("Directives saved for {}", target_id));
                            }
                            DirectiveEditorAction::Cancel => {
                                directive_editor_modal = None;
                            }
                            DirectiveEditorAction::None => {}
                        }
                        continue;
                    }

                    // 5. New Worker Modal key handling
                    if let Some(ref mut modal) = new_worker_modal {
                        match modal.handle_key(&key) {
                            NewWorkerModalAction::Spawn(slot) => {
                                let count = engine.sessions().len() + 1;
                                let worker_name = format!("worker-{}", count);
                                let slot_str = format!("agy{}", slot.slot_id);
                                let isolation_env = IdentityDiscovery::build_slot_isolation_env(&slot);
                                let _ = engine.spawn_worker(
                                    worker_name,
                                    slot_str,
                                    shell_cmd,
                                    vec![],
                                    None,
                                    isolation_env,
                                    rows,
                                    cols,
                                );
                                new_worker_modal = None;
                                active_modal_notice = Some(format!("Spawned agent slot agy{}", slot.slot_id));
                            }
                            NewWorkerModalAction::Cancel => {
                                new_worker_modal = None;
                            }
                            NewWorkerModalAction::None => {}
                        }
                        continue;
                    }

                    // 6. Fast session picker switch hotkey (Ctrl+P)
                    if (key.code == KeyCode::Char('p') || key.code == KeyCode::Char('P')) && key.modifiers.contains(KeyModifiers::CONTROL) {
                        session_picker.refresh();
                        current_screen = AppScreen::SessionPicker;
                        continue;
                    }

                    // 7. Resolve shortcuts in multiplexer mode
                    let action = engine.shortcut_engine.resolve(&key);

                    match action {
                        Action::Quit => break,
                        Action::Help => {
                            help_modal = Some(HelpModal::new(theme));
                            continue;
                        }
                        Action::ToggleSplit => {
                            split_mode = split_mode.next();
                            continue;
                        }
                        Action::NewWorker => {
                            new_worker_modal = Some(NewWorkerModal::default().theme(theme));
                            continue;
                        }
                        Action::DirectiveModal => {
                            if let Some(active_worker) = engine.active_session() {
                                directive_modal = Some(
                                    DirectiveModal::new(
                                        active_worker.id.clone(),
                                        active_worker.slot_id.clone(),
                                        active_worker.role(),
                                    ).theme(theme)
                                );
                            }
                            continue;
                        }
                        Action::DirectiveEditor => {
                            if let Some(active_worker) = engine.active_session() {
                                let existing_task = active_worker.task.lock().clone().unwrap_or_default();
                                directive_editor_modal = Some(
                                    DirectiveEditorModal::new(
                                        active_worker.id.clone(),
                                        active_worker.slot_id.clone(),
                                        active_worker.role(),
                                        &existing_task,
                                    ).theme(theme)
                                );
                            }
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
                                session_picker = session_picker.theme(theme);
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
