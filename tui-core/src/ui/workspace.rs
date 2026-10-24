use std::sync::Arc;
use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Tabs, Widget},
};

use crate::session::{AppMode, FocusedPane};
use crate::session::worker::WorkerSession;
use crate::ui::terminal_screen::TerminalScreenWidget;
use crate::ui::theme::{glyphs, Theme};

/// Tokyo Night palette constants for dual-pane workspace styling.
mod workspace_colors {
    use ratatui::style::Color;

    pub const BORDER_ACTIVE: Color = Color::Rgb(122, 162, 247);    // #7aa2f7 (Prominent Accent Blue)
    pub const BORDER_FOCUSED_CYAN: Color = Color::Rgb(125, 207, 255); // #7dcfff (Cyan)
    pub const BORDER_MUTED: Color = Color::Rgb(86, 95, 137);       // #565f89 (Subtle Muted)
    pub const BG_TAB_ACTIVE: Color = Color::Rgb(41, 46, 66);       // #292e42
    pub const FG_MUTED: Color = Color::Rgb(121, 130, 169);         // #7982a9
    pub const ACCENT_YELLOW: Color = Color::Rgb(224, 175, 104);    // #e0af68
}

/// Metadata item for WorkerTabBar display.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorkerTabItem {
    pub id: String,
    pub slot_id: String,
    pub name: String,
}

impl WorkerTabItem {
    pub fn new(id: impl Into<String>, slot_id: impl Into<String>, name: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            slot_id: slot_id.into(),
            name: name.into(),
        }
    }
}

/// Top Tab Bar widget for the Worker Multiplexer pane (`WorkerTabBar`),
/// displaying interactive worker tabs `1..9` and `+ New (c)` action badge.
#[derive(Debug, Clone)]
pub struct WorkerTabBar {
    pub tabs: Vec<WorkerTabItem>,
    pub selected_index: usize,
    pub is_focused: bool,
    pub theme: Theme,
}

impl Default for WorkerTabBar {
    fn default() -> Self {
        Self::new(Vec::new(), 0, false)
    }
}

impl WorkerTabBar {
    /// Create new WorkerTabBar.
    pub fn new(tabs: Vec<WorkerTabItem>, selected_index: usize, is_focused: bool) -> Self {
        Self {
            tabs,
            selected_index,
            is_focused,
            theme: Theme::default(),
        }
    }

    /// Set theme.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.theme = theme;
        self
    }
}

impl Widget for WorkerTabBar {
    fn render(self, area: Rect, buf: &mut Buffer) {
        (&self).render(area, buf);
    }
}

impl Widget for &WorkerTabBar {
    fn render(self, area: Rect, buf: &mut Buffer) {
        if area.width == 0 || area.height == 0 {
            return;
        }

        let border_style = if self.is_focused {
            Style::default()
                .fg(workspace_colors::BORDER_ACTIVE)
                .add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(workspace_colors::BORDER_MUTED)
        };

        let mut tab_titles: Vec<Line> = self
            .tabs
            .iter()
            .enumerate()
            .map(|(idx, item)| {
                let is_active = idx == self.selected_index;
                let num = idx + 1;
                let prefix = if is_active { glyphs::POINTER } else { " " };
                let label = format!(" {}{}: {} ({}) ", prefix, num, item.name, item.slot_id);

                if is_active {
                    Line::from(Span::styled(
                        label,
                        Style::default()
                            .fg(workspace_colors::BORDER_FOCUSED_CYAN)
                            .bg(workspace_colors::BG_TAB_ACTIVE)
                            .add_modifier(Modifier::BOLD),
                    ))
                } else {
                    Line::from(Span::styled(
                        label,
                        Style::default().fg(workspace_colors::FG_MUTED),
                    ))
                }
            })
            .collect();

        // Append `[ + New (c) ]` action tab
        tab_titles.push(Line::from(Span::styled(
            " + New (c) ",
            Style::default().fg(workspace_colors::ACCENT_YELLOW),
        )));

        let tabs_widget = Tabs::new(tab_titles)
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .border_style(border_style)
                    .title(Span::styled(
                        " Interactive Workers [1..9 / h / l] ",
                        border_style,
                    )),
            )
            .select(self.selected_index);

        tabs_widget.render(area, buf);
    }
}

/// Dual-Pane Workspace layout screen (`WorkspaceScreen`) matching Python `mind`
/// `WorkspaceScreen` pixel-for-pixel:
/// - Left Pane (`#primary-pane`): Dedicated Primary Coordinator PTY (Slot 1 `agy1`). Stays visible side-by-side.
/// - Right Pane (`#workers-pane`): Worker Multiplexer with top `WorkerTabBar` (tabs `1..9`) and active worker PTY below.
/// - Focus Visuals: Active pane gets prominent Tokyo Night accent border (`#7aa2f7` / `#7dcfff`); inactive pane has muted border.
/// - Split Layout Modes: Side-by-side (50/50) vs Fullscreen expansion toggle on `s` key.
#[derive(Clone)]
pub struct WorkspaceScreen {
    pub is_split_view: bool,
    pub focused_pane: FocusedPane,
    pub mode: AppMode,
    pub coordinator: Option<Arc<WorkerSession>>,
    pub workers: Vec<Arc<WorkerSession>>,
    pub theme: Theme,
}

impl Default for WorkspaceScreen {
    fn default() -> Self {
        Self {
            is_split_view: true,
            focused_pane: FocusedPane::Coordinator,
            mode: AppMode::Normal,
            coordinator: None,
            workers: Vec::new(),
            theme: Theme::default(),
        }
    }
}

impl WorkspaceScreen {
    /// Create new WorkspaceScreen.
    pub fn new() -> Self {
        Self::default()
    }

    /// Set split view mode (true for 50/50 dual-pane side-by-side, false for fullscreen focused pane).
    pub fn split_view(mut self, is_split: bool) -> Self {
        self.is_split_view = is_split;
        self
    }

    /// Set focused pane.
    pub fn focused_pane(mut self, focused: FocusedPane) -> Self {
        self.focused_pane = focused;
        self
    }

    /// Set mode.
    pub fn mode(mut self, mode: AppMode) -> Self {
        self.mode = mode;
        self
    }

    /// Set Primary Coordinator worker session.
    pub fn coordinator(mut self, coord: Option<Arc<WorkerSession>>) -> Self {
        self.coordinator = coord;
        self
    }

    /// Set interactive worker sessions list.
    pub fn workers(mut self, workers: Vec<Arc<WorkerSession>>) -> Self {
        self.workers = workers;
        self
    }

    /// Set theme.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.theme = theme;
        self
    }

    /// Calculate sub-rectangles for dual-pane workspace: Left (`#primary-pane`) and Right (`#workers-pane`).
    pub fn compute_panes(&self, area: Rect) -> (Rect, Rect) {
        if area.width == 0 || area.height == 0 {
            return (Rect::default(), Rect::default());
        }

        if self.is_split_view {
            // Side-by-side (50/50)
            let chunks = Layout::default()
                .direction(Direction::Horizontal)
                .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
                .split(area);
            (chunks[0], chunks[1])
        } else {
            // Fullscreen expansion toggle on `s`
            match self.focused_pane {
                FocusedPane::Coordinator => {
                    let chunks = Layout::default()
                        .direction(Direction::Horizontal)
                        .constraints([Constraint::Percentage(100), Constraint::Percentage(0)])
                        .split(area);
                    (chunks[0], chunks[1])
                }
                FocusedPane::Workers(_) => {
                    let chunks = Layout::default()
                        .direction(Direction::Horizontal)
                        .constraints([Constraint::Percentage(0), Constraint::Percentage(100)])
                        .split(area);
                    (chunks[0], chunks[1])
                }
            }
        }
    }
}

impl Widget for WorkspaceScreen {
    fn render(self, area: Rect, buf: &mut Buffer) {
        (&self).render(area, buf);
    }
}

impl Widget for &WorkspaceScreen {
    fn render(self, area: Rect, buf: &mut Buffer) {
        if area.width == 0 || area.height == 0 {
            return;
        }

        let (left_rect, right_rect) = self.compute_panes(area);

        // ── 1. Left Pane: Dedicated Primary Coordinator PTY (#primary-pane) ──
        if left_rect.width > 0 && left_rect.height > 0 {
            let is_coord_focused = self.focused_pane == FocusedPane::Coordinator;
            let coord_border_style = if is_coord_focused {
                Style::default()
                    .fg(workspace_colors::BORDER_FOCUSED_CYAN)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(workspace_colors::BORDER_MUTED)
            };

            let coord_title = if is_coord_focused {
                " 👑 Primary Coordinator (Slot 1 agy1) [FOCUSED] "
            } else {
                " 👑 Primary Coordinator (Slot 1 agy1) "
            };

            let coord_block = Block::default()
                .borders(Borders::ALL)
                .border_style(coord_border_style)
                .title(Span::styled(coord_title, coord_border_style));

            if let Some(ref coord) = self.coordinator {
                let pty = coord.pty.lock();
                let b = pty.buffer();
                let lock_guard = b.lock();
                let screen_widget = TerminalScreenWidget::from_buffer(&lock_guard)
                    .block(coord_block)
                    .show_cursor(is_coord_focused && self.mode == AppMode::PtyInteract);
                screen_widget.render(left_rect, buf);
            } else {
                let empty_coord = Paragraph::new("\n  Coordinator PTY initializing (Slot 1 agy1)...")
                    .block(coord_block)
                    .style(Style::default().fg(workspace_colors::FG_MUTED));
                empty_coord.render(left_rect, buf);
            }
        }

        // ── 2. Right Pane: Worker Multiplexer (#workers-pane) ────────────────
        if right_rect.width > 0 && right_rect.height > 0 {
            let is_worker_pane_focused = matches!(self.focused_pane, FocusedPane::Workers(_));
            let worker_idx = match self.focused_pane {
                FocusedPane::Workers(idx) => idx,
                FocusedPane::Coordinator => 0,
            };

            // Split right pane vertically: Top Tab Bar (Length 3) + Active Worker Viewport (Rest)
            let worker_subchunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Length(3), // Top Tab Bar
                    Constraint::Min(4),    // Active Worker Viewport
                ])
                .split(right_rect);

            // Render WorkerTabBar
            let tab_items: Vec<WorkerTabItem> = self
                .workers
                .iter()
                .map(|w| {
                    WorkerTabItem::new(
                        w.id.clone(),
                        w.slot_id.clone(),
                        w.worker_name(),
                    )
                })
                .collect();

            let tab_bar = WorkerTabBar::new(tab_items, worker_idx, is_worker_pane_focused)
                .theme(self.theme);
            tab_bar.render(worker_subchunks[0], buf);

            // Render Active Worker PTY Viewport
            let worker_view_border_style = if is_worker_pane_focused {
                Style::default()
                    .fg(workspace_colors::BORDER_ACTIVE)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(workspace_colors::BORDER_MUTED)
            };

            let worker_view_block = Block::default()
                .borders(Borders::ALL)
                .border_style(worker_view_border_style);

            if let Some(active_w) = self.workers.get(worker_idx) {
                let pty = active_w.pty.lock();
                let b = pty.buffer();
                let lock_guard = b.lock();
                let screen_widget = TerminalScreenWidget::from_buffer(&lock_guard)
                    .block(worker_view_block)
                    .show_cursor(is_worker_pane_focused && self.mode == AppMode::PtyInteract);
                screen_widget.render(worker_subchunks[1], buf);
            } else {
                let placeholder = Paragraph::new(
                    "\n  No active worker agents running.\n  Press 'c' or 'n' to spawn a new worker agent.",
                )
                .block(worker_view_block)
                .style(Style::default().fg(workspace_colors::FG_MUTED));
                placeholder.render(worker_subchunks[1], buf);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;

    #[test]
    fn test_dual_pane_workspace_geometry_and_split_toggle() {
        let area = Rect::new(0, 0, 100, 40);

        // 1. Side-by-side 50/50 split
        let screen_split = WorkspaceScreen::new()
            .split_view(true)
            .focused_pane(FocusedPane::Coordinator);

        let (left, right) = screen_split.compute_panes(area);
        assert_eq!(left.width, 50, "Left pane must be 50% width");
        assert_eq!(right.width, 50, "Right pane must be 50% width");

        // 2. Fullscreen Coordinator expansion on 's'
        let screen_full_coord = WorkspaceScreen::new()
            .split_view(false)
            .focused_pane(FocusedPane::Coordinator);

        let (left_c, right_c) = screen_full_coord.compute_panes(area);
        assert_eq!(left_c.width, 100, "Coordinator must be 100% width when focused in fullscreen");
        assert_eq!(right_c.width, 0, "Workers must be 0% width");

        // 3. Fullscreen Worker expansion on 's'
        let screen_full_worker = WorkspaceScreen::new()
            .split_view(false)
            .focused_pane(FocusedPane::Workers(0));

        let (left_w, right_w) = screen_full_worker.compute_panes(area);
        assert_eq!(left_w.width, 0, "Coordinator must be 0% width");
        assert_eq!(right_w.width, 100, "Workers must be 100% width when focused in fullscreen");
    }

    #[test]
    fn test_worker_tab_bar_rendering() {
        let backend = TestBackend::new(100, 3);
        let mut terminal = Terminal::new(backend).unwrap();

        let tabs = vec![
            WorkerTabItem::new("1", "agy11", "Worker-1"),
            WorkerTabItem::new("2", "agy51", "Worker-2"),
        ];
        let tab_bar = WorkerTabBar::new(tabs, 0, true);

        terminal
            .draw(|f| {
                f.render_widget(&tab_bar, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut content = String::new();
        for y in 0..3 {
            for x in 0..100 {
                content.push_str(term_buf[(x, y)].symbol());
            }
        }

        assert!(content.contains("Interactive Workers"), "Must render tab title");
        assert!(content.contains("Worker-1"), "Must render first worker");
        assert!(content.contains("Worker-2"), "Must render second worker");
        assert!(content.contains("+ New (c)"), "Must render spawn action");
    }
}
