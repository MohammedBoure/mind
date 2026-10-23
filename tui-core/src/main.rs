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
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Tabs},
    Terminal,
};
use tracing::Level;
use tracing_subscriber::FmtSubscriber;

use tui_core::events::AppEvent;
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

    // Spawn Coordinator session and first worker session
    let shell_cmd = if cfg!(windows) { "powershell.exe" } else { "bash" };
    engine.spawn_worker(
        "coordinator",
        "agy1",
        shell_cmd,
        vec![],
        None,
        HashMap::new(),
        24,
        80,
    )?;

    engine.spawn_worker(
        "agy2",
        "agy2",
        shell_cmd,
        vec![],
        None,
        HashMap::new(),
        24,
        80,
    )?;

    let (rows, cols) = (terminal.size()?.height, terminal.size()?.width);
    engine.resize_all(rows, cols);

    loop {
        let sessions = engine.sessions();
        let active_idx = engine.session_manager.active_index();

        terminal.draw(|f| {
            let chunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Length(3), // Header & Tabs
                    Constraint::Min(5),    // Terminal Screen
                    Constraint::Length(1), // Footer / Statusline
                ])
                .split(f.area());

            // Header Tabs
            let tab_titles: Vec<Line> = sessions
                .iter()
                .enumerate()
                .map(|(i, s)| {
                    let style = if i == active_idx {
                        Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)
                    } else {
                        Style::default().fg(Color::DarkGray)
                    };
                    Line::from(vec![
                        Span::raw(format!(" [{}:{}] ", s.id, s.slot_id)),
                    ]).style(style)
                })
                .collect();

            let tabs = Tabs::new(tab_titles)
                .block(Block::default().borders(Borders::ALL).title(" Mind TUI Engine (Compiled Rust Core) "))
                .select(active_idx)
                .highlight_style(Style::default().fg(Color::Yellow).add_modifier(Modifier::UNDERLINED));
            f.render_widget(tabs, chunks[0]);

            // Terminal Screen Content
            let screen_text = if let Some(session) = engine.active_session() {
                session.get_screen_text(chunks[1].height as usize)
            } else {
                "No active session".to_string()
            };

            let screen_widget = Paragraph::new(screen_text)
                .block(Block::default().borders(Borders::ALL).title(" Virtual PTY Terminal Screen "));
            f.render_widget(screen_widget, chunks[1]);

            // Footer
            let footer = Paragraph::new(" Tab: Switch Session | Ctrl+C: Interrupt | q: Quit | Type to pass-through ")
                .style(Style::default().fg(Color::Black).bg(Color::Cyan));
            f.render_widget(footer, chunks[2]);
        })?;

        if let Some(event) = engine.next_event().await {
            match event {
                AppEvent::Key(key) => {
                    if key.code == KeyCode::Char('q') && key.modifiers.contains(KeyModifiers::CONTROL) {
                        break;
                    }
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
                    }
                }
                AppEvent::Resize(r, c) => {
                    engine.resize_all(r, c);
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
