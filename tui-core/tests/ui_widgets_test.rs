use std::collections::HashMap;
use std::sync::Arc;
use ratatui::{
    backend::TestBackend,
    layout::Rect,
    style::{Color, Modifier},
    widgets::{Block, Borders, ListState, StatefulWidget},
    Terminal,
};

use tui_core::pty::buffer::ScreenBuffer;
use tui_core::session::worker::{WorkerSession, WorkerState};
use tui_core::ui::{
    AlertBadge, GaugeLayout, QuotaGaugesWidget, SplitMode, SplitPanesWidget,
    StatusBarWidget, TerminalScreenWidget, Theme, WorkerListItem, WorkerListWidget,
};

#[test]
fn test_ansi_matrix_cell_rendering_and_styling() {
    let mut buffer = ScreenBuffer::new(4, 30);

    // Row 0: Bold Green text
    buffer.process_bytes(b"\x1b[1;32mGREEN_BOLD\x1b[0m normal\r\n");
    // Row 1: TrueColor RGB (255, 100, 50) and Underline
    buffer.process_bytes(b"\x1b[4;38;2;255;100;50mRGB_UNDER\x1b[0m\r\n");
    // Row 2: 256-color palette (color index 208 orange) and italic
    buffer.process_bytes(b"\x1b[3;38;5;208mORANGE_ITALIC\x1b[0m\r\n");

    let backend = TestBackend::new(30, 4);
    let mut terminal = Terminal::new(backend).unwrap();

    terminal
        .draw(|f| {
            let widget = TerminalScreenWidget::from_buffer(&buffer)
                .show_cursor(true)
                .default_fg(Color::White);
            f.render_widget(widget, f.area());
        })
        .unwrap();

    let term_buf = terminal.backend().buffer();

    // Verify Row 0 cell: 'G' in GREEN_BOLD has bold modifier and green color
    let cell_g = &term_buf[(0, 0)];
    assert_eq!(cell_g.symbol(), "G");
    assert!(cell_g.modifier.contains(Modifier::BOLD));
    assert_eq!(cell_g.fg, Color::Indexed(2)); // ANSI Green is 2

    // Verify Row 1 cell: 'R' in RGB_UNDER has underline and RGB color
    let cell_r = &term_buf[(0, 1)];
    assert_eq!(cell_r.symbol(), "R");
    assert!(cell_r.modifier.contains(Modifier::UNDERLINED));
    assert_eq!(cell_r.fg, Color::Rgb(255, 100, 50));

    // Verify Row 2 cell: 'O' in ORANGE_ITALIC has italic and indexed color 208
    let cell_o = &term_buf[(0, 2)];
    assert_eq!(cell_o.symbol(), "O");
    assert!(cell_o.modifier.contains(Modifier::ITALIC));
    assert_eq!(cell_o.fg, Color::Indexed(208));
}

#[test]
fn test_dirty_frame_checking_mechanics() {
    let mut buffer = ScreenBuffer::new(10, 40);
    let v0 = buffer.version();
    assert_eq!(v0, 0);

    let widget0 = TerminalScreenWidget::from_buffer(&buffer);
    assert_eq!(widget0.version(), Some(0));
    assert!(!widget0.is_dirty(v0), "Buffer is not dirty relative to its own version");

    // Write no-op byte or text
    buffer.process_bytes(b"A");
    let v1 = buffer.version();
    assert_eq!(v1, 1);

    let widget1 = TerminalScreenWidget::from_buffer(&buffer);
    assert!(widget1.is_dirty(v0), "Widget must report dirty against old version 0");
    assert!(!widget1.is_dirty(v1), "Widget must NOT report dirty against current version 1");

    // Plain text source always reports dirty
    let text_widget = TerminalScreenWidget::from_plain_text("static text");
    assert!(text_widget.is_dirty(0));
    assert!(text_widget.is_dirty(999));
    assert_eq!(text_widget.version(), None);
}

#[test]
fn test_split_panes_all_modes_and_geometry() {
    let area = Rect::new(0, 0, 120, 60);

    // 1. Single Mode
    let single = SplitPanesWidget::new(SplitMode::Single);
    assert_eq!(single.compute_panes(area), vec![area]);
    assert_eq!(SplitMode::Single.label(), "1-PANE");

    // 2. Horizontal Mode
    let horiz = SplitPanesWidget::new(SplitMode::Horizontal).ratio(60, 40);
    let h_panes = horiz.compute_panes(area);
    assert_eq!(h_panes.len(), 2);
    assert_eq!(h_panes[0].width, 72); // 60% of 120
    assert_eq!(h_panes[1].width, 48); // 40% of 120
    assert_eq!(SplitMode::Horizontal.label(), "HORIZ-SPLIT");

    // 3. Vertical Mode
    let vert = SplitPanesWidget::new(SplitMode::Vertical).ratio(50, 50);
    let v_panes = vert.compute_panes(area);
    assert_eq!(v_panes.len(), 2);
    assert_eq!(v_panes[0].height, 30);
    assert_eq!(v_panes[1].height, 30);
    assert_eq!(SplitMode::Vertical.label(), "VERT-SPLIT");

    // 4. Grid Mode
    let grid = SplitPanesWidget::new(SplitMode::Grid);
    let g_panes = grid.compute_panes(area);
    assert_eq!(g_panes.len(), 4);
    for pane in &g_panes {
        assert_eq!(pane.width, 60);
        assert_eq!(pane.height, 30);
    }
    assert_eq!(SplitMode::Grid.label(), "2x2-GRID");

    // Cycle check
    assert_eq!(SplitMode::Single.next(), SplitMode::Horizontal);
    assert_eq!(SplitMode::Horizontal.next(), SplitMode::Vertical);
    assert_eq!(SplitMode::Vertical.next(), SplitMode::Grid);
    assert_eq!(SplitMode::Grid.next(), SplitMode::Single);
}

#[tokio::test]
async fn test_split_panes_render_grid_with_placeholders() {
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };
    let s1 = Arc::new(WorkerSession::spawn("w1", "agy1", shell, vec![], None, HashMap::new(), 10, 20).unwrap());
    let s2 = Arc::new(WorkerSession::spawn("w2", "agy2", shell, vec![], None, HashMap::new(), 10, 20).unwrap());

    let backend = TestBackend::new(100, 40);
    let mut terminal = Terminal::new(backend).unwrap();

    terminal
        .draw(|f| {
            // Render 2 sessions in a 4-pane Grid layout (panes 3 and 4 are placeholders)
            let widget = SplitPanesWidget::new(SplitMode::Grid)
                .sessions(vec![s1, s2])
                .focused_index(0);
            f.render_widget(widget, f.area());
        })
        .unwrap();

    let term_buf = terminal.backend().buffer();
    let mut full_text = String::new();
    for y in 0..40 {
        for x in 0..100 {
            full_text.push_str(term_buf[(x, y)].symbol());
        }
        full_text.push('\n');
    }

    assert!(full_text.contains("w1:agy1"), "Pane 0 should display worker 1");
    assert!(full_text.contains("w2:agy2"), "Pane 1 should display worker 2");
    assert!(full_text.contains("Empty Slot"), "Panes 2 and 3 should display Empty Slot placeholder");
}

#[test]
fn test_status_bar_comprehensive() {
    let backend = TestBackend::new(220, 1);
    let mut terminal = Terminal::new(backend).unwrap();

    // 1. Worker finished alert
    terminal
        .draw(|f| {
            let status_bar = StatusBarWidget::new("coordinator", "agy1")
                .pid(Some(4242))
                .model("claude-3-5-sonnet")
                .tokens(125_000, 200_000)
                .state(WorkerState::Running)
                .alert_badge(AlertBadge::WorkerFinished("Task complete".into()))
                .split_mode("HORIZ-SPLIT")
                .custom_hint("Tab: Next │ F2: Split");
            f.render_widget(status_bar, f.area());
        })
        .unwrap();

    let term_buf = terminal.backend().buffer();
    let line: String = (0..220).map(|x| term_buf[(x, 0)].symbol()).collect();
    assert!(line.contains("coordinator:agy1"));
    assert!(line.contains("PID: 4242"));
    assert!(line.contains("claude-3-5-sonnet"));
    assert!(line.contains("125.0k/200.0k"));
    assert!(line.contains("62.5%"));
    assert!(line.contains("Worker Finished"));
    assert!(line.contains("[SPLIT: HORIZ-SPLIT]"));

    // 2. Assistance needed alert
    terminal
        .draw(|f| {
            let status_bar = StatusBarWidget::new("worker-test", "agy5")
                .alert_badge(AlertBadge::AssistanceNeeded("Dependency missing".into()));
            f.render_widget(status_bar, f.area());
        })
        .unwrap();

    let line2: String = (0..220).map(|x| terminal.backend().buffer()[(x, 0)].symbol()).collect();
    assert!(line2.contains("Assistance Needed"));
    assert!(line2.contains("Dependency missing"));

    // 3. Custom badge with high token count (millions)
    terminal
        .draw(|f| {
            let status_bar = StatusBarWidget::new("worker-huge", "agy9")
                .tokens(2_500_000, 5_000_000)
                .alert_badge(AlertBadge::Custom("MAINTENANCE".into(), Theme::badge_worker_finished()));
            f.render_widget(status_bar, f.area());
        })
        .unwrap();

    let line3: String = (0..220).map(|x| terminal.backend().buffer()[(x, 0)].symbol()).collect();
    assert!(line3.contains("2.5M/5.0M"));
    assert!(line3.contains("[MAINTENANCE]"));
}

#[test]
fn test_quota_gauges_comprehensive() {
    let backend = TestBackend::new(120, 6);
    let mut terminal = Terminal::new(backend).unwrap();

    // 1. Horizontal Layout
    terminal
        .draw(|f| {
            let widget = QuotaGaugesWidget::new()
                .hourly_remaining(18.0) // Low (<20%) -> Red threshold
                .weekly_remaining(45.0) // Medium (20-50%) -> Yellow threshold
                .cpu_usage(88.5)        // High (>85%) -> Red threshold
                .memory(7500, 8192)     // High (>85%)
                .layout(GaugeLayout::Horizontal);
            f.render_widget(widget, f.area());
        })
        .unwrap();

    let mut text_h = String::new();
    for y in 0..6 {
        for x in 0..120 {
            text_h.push_str(terminal.backend().buffer()[(x, y)].symbol());
        }
    }
    assert!(text_h.contains("Hourly Quota"));
    assert!(text_h.contains("18% Left"));
    assert!(text_h.contains("Weekly Quota"));
    assert!(text_h.contains("45% Left"));
    assert!(text_h.contains("88.5%"));

    // 2. Vertical Layout
    terminal
        .draw(|f| {
            let widget = QuotaGaugesWidget::new()
                .hourly_remaining(95.0) // High (>50%) -> Green threshold
                .weekly_remaining(99.0)
                .cpu_usage(12.0)        // Low (<60%) -> Teal threshold
                .memory(2048, 16384)
                .layout(GaugeLayout::Vertical);
            f.render_widget(widget, f.area());
        })
        .unwrap();

    let mut text_v = String::new();
    for y in 0..6 {
        for x in 0..120 {
            text_v.push_str(terminal.backend().buffer()[(x, y)].symbol());
        }
    }
    assert!(text_v.contains("Hourly: 95%"));
    assert!(text_v.contains("Weekly: 99%"));
    assert!(text_v.contains("CPU: 12.0%"));
    assert!(text_v.contains("RAM: 12.5%"));
}

#[test]
fn test_worker_list_dynamic_interaction() {
    let items = vec![
        WorkerListItem {
            id: "coordinator".to_string(),
            slot_id: "agy1".to_string(),
            pid: Some(1001),
            state: WorkerState::Running,
            task: Some("Managing multi-agent swarm".to_string()),
            has_finished_alarm: false,
            has_help_alarm: false,
        },
        WorkerListItem {
            id: "worker-build".to_string(),
            slot_id: "agy2".to_string(),
            pid: Some(1002),
            state: WorkerState::Idle,
            task: Some("Cargo build release".to_string()),
            has_finished_alarm: true,
            has_help_alarm: false,
        },
        WorkerListItem {
            id: "worker-bench".to_string(),
            slot_id: "agy3".to_string(),
            pid: Some(1003),
            state: WorkerState::Interrupted,
            task: Some("Benchmark suite execution".to_string()),
            has_finished_alarm: false,
            has_help_alarm: true,
        },
        WorkerListItem {
            id: "worker-done".to_string(),
            slot_id: "agy4".to_string(),
            pid: None,
            state: WorkerState::Exited(Some(0)),
            task: None,
            has_finished_alarm: false,
            has_help_alarm: false,
        },
    ];

    let backend = TestBackend::new(80, 8);
    let mut terminal = Terminal::new(backend).unwrap();

    // Test StatefulWidget render with active selection
    let mut list_state = ListState::default();
    list_state.select(Some(1)); // Focus on worker-build

    terminal
        .draw(|f| {
            let widget = WorkerListWidget::new(items.clone())
                .block(Block::default().borders(Borders::ALL).title(" Agent Swarm "));
            StatefulWidget::render(widget, f.area(), f.buffer_mut(), &mut list_state);
        })
        .unwrap();

    let mut content = String::new();
    for y in 0..8 {
        for x in 0..80 {
            content.push_str(terminal.backend().buffer()[(x, y)].symbol());
        }
        content.push('\n');
    }

    eprintln!("RENDERED WORKER LIST CONTENT:\n{}", content);
    assert!(content.contains("coordinator:agy1"));
    assert!(content.contains("worker-build:agy2"));
    assert!(content.contains("worker-bench:agy3"));
    assert!(content.contains("worker-done:agy4"));
    assert!(content.contains("DONE"));
    assert!(content.contains("NEED HELP"));
}

#[test]
fn test_accessibility_themes_and_palettes() {
    use tui_core::ui::ThemeMode;

    let modes = [
        ThemeMode::TokyoNight,
        ThemeMode::HighContrastDark,
        ThemeMode::HighContrastLight,
        ThemeMode::ColorBlind,
    ];

    let backend = TestBackend::new(140, 5);
    let mut terminal = Terminal::new(backend).unwrap();

    for mode in modes {
        let theme = Theme::new(mode);
        let palette = theme.palette();

        assert_eq!(theme.mode, mode);
        assert!(!mode.label().is_empty());

        terminal
            .draw(|f| {
                let status_bar = StatusBarWidget::new("worker-1", "slot-1")
                    .theme(theme)
                    .alert_badge(AlertBadge::AssistanceNeeded("Critical issue".to_string()));
                f.render_widget(status_bar, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut rendered = String::new();
        for x in 0..140 {
            rendered.push_str(term_buf[(x, 0)].symbol());
        }
        assert!(rendered.contains("worker-1:slot-1"));
        if mode == ThemeMode::ColorBlind {
            assert!(rendered.contains("[!] Assistance Needed"));
        } else {
            assert!(rendered.contains("Assistance Needed"));
        }

        // Verify high-contrast / color-blind palette distinctness
        if mode == ThemeMode::HighContrastDark {
            assert_eq!(palette.bg_dark, Color::Rgb(0, 0, 0));
            assert_eq!(palette.fg_light, Color::Rgb(255, 255, 255));
        } else if mode == ThemeMode::HighContrastLight {
            assert_eq!(palette.bg_dark, Color::Rgb(255, 255, 255));
            assert_eq!(palette.fg_light, Color::Rgb(15, 15, 20));
        }
    }
}

#[tokio::test]
async fn test_split_panes_with_scrollback_rendering() {
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };
    let session = Arc::new(
        WorkerSession::spawn("scroll-test", "slot1", shell, vec![], None, HashMap::new(), 5, 40)
            .unwrap(),
    );

    // Push output lines to populate scrollback
    {
        let pty = session.pty.lock();
        let buf = pty.buffer();
        let mut b = buf.lock();
        b.process_bytes(b"line 1\r\nline 2\r\nline 3\r\nline 4\r\nline 5\r\nline 6\r\nline 7\r\nline 8");
    }

    assert!(session.pty.lock().buffer().lock().history_count() > 0);

    // Scroll up
    session.scroll_up(3);
    assert_eq!(session.scroll_offset(), 3);

    let backend = TestBackend::new(80, 10);
    let mut terminal = Terminal::new(backend).unwrap();

    terminal
        .draw(|f| {
            let widget = SplitPanesWidget::new(SplitMode::Single)
                .sessions(vec![session.clone()])
                .focused_index(0);
            f.render_widget(widget, f.area());
        })
        .unwrap();

    let term_buf = terminal.backend().buffer();
    let mut text = String::new();
    for y in 0..10 {
        for x in 0..80 {
            text.push_str(term_buf[(x, y)].symbol());
        }
        text.push('\n');
    }

    assert!(text.contains("SCROLL -3"));

    // Reset scroll on user input
    session.send_input("ls", true).unwrap();
    assert_eq!(session.scroll_offset(), 0);
}
