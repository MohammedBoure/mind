use std::sync::Arc;
use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    text::Span,
    widgets::{Block, Borders, Widget},
};

use crate::session::worker::WorkerSession;
use crate::ui::terminal_screen::TerminalScreenWidget;
use crate::ui::theme::{colors, glyphs, Theme};

/// Multiplexing layout mode for split terminal panes.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum SplitMode {
    /// Full screen view of the currently focused single worker terminal.
    #[default]
    Single,
    /// Side-by-side horizontal split (Left and Right).
    Horizontal,
    /// Stacked vertical split (Top and Bottom).
    Vertical,
    /// Quad multiplexer 2x2 grid (Top-Left, Top-Right, Bottom-Left, Bottom-Right).
    Grid,
}

impl SplitMode {
    /// Toggle to next split mode in cycle (Single -> Horizontal -> Vertical -> Grid -> Single).
    pub fn next(self) -> Self {
        match self {
            Self::Single => Self::Horizontal,
            Self::Horizontal => Self::Vertical,
            Self::Vertical => Self::Grid,
            Self::Grid => Self::Single,
        }
    }

    /// Human-readable label for status bars and header breadcrumbs.
    pub fn label(self) -> &'static str {
        match self {
            Self::Single => "1-PANE",
            Self::Horizontal => "HORIZ-SPLIT",
            Self::Vertical => "VERT-SPLIT",
            Self::Grid => "2x2-GRID",
        }
    }
}

/// Flexible split layout widget for multiplexing multiple worker terminals
/// with active pane highlighting and Tokyo Night styling.
pub struct SplitPanesWidget<'a> {
    sessions: Vec<Arc<WorkerSession>>,
    focused_index: usize,
    mode: SplitMode,
    left_ratio: u16,
    right_ratio: u16,
    show_cursor: bool,
    _marker: std::marker::PhantomData<&'a ()>,
}

impl<'a> SplitPanesWidget<'a> {
    /// Create new split panes widget with specified layout mode.
    pub fn new(mode: SplitMode) -> Self {
        Self {
            sessions: Vec::new(),
            focused_index: 0,
            mode,
            left_ratio: 50,
            right_ratio: 50,
            show_cursor: true,
            _marker: std::marker::PhantomData,
        }
    }

    /// Provide managed worker sessions for multiplexing.
    pub fn sessions(mut self, sessions: Vec<Arc<WorkerSession>>) -> Self {
        self.sessions = sessions;
        self
    }

    /// Set currently active / focused session index.
    pub fn focused_index(mut self, index: usize) -> Self {
        self.focused_index = index;
        self
    }

    /// Set layout mode.
    pub fn mode(mut self, mode: SplitMode) -> Self {
        self.mode = mode;
        self
    }

    /// Custom horizontal/vertical split ratio (e.g. 60, 40).
    pub fn ratio(mut self, first: u16, second: u16) -> Self {
        self.left_ratio = first;
        self.right_ratio = second;
        self
    }

    /// Toggle cursor display within the focused pane.
    pub fn show_cursor(mut self, show: bool) -> Self {
        self.show_cursor = show;
        self
    }

    /// Calculate sub-rectangles based on current `SplitMode` and terminal area.
    pub fn compute_panes(&self, area: Rect) -> Vec<Rect> {
        if area.width == 0 || area.height == 0 {
            return Vec::new();
        }

        match self.mode {
            SplitMode::Single => vec![area],
            SplitMode::Horizontal => {
                let chunks = Layout::default()
                    .direction(Direction::Horizontal)
                    .constraints([
                        Constraint::Percentage(self.left_ratio),
                        Constraint::Percentage(self.right_ratio),
                    ])
                    .split(area);
                vec![chunks[0], chunks[1]]
            }
            SplitMode::Vertical => {
                let chunks = Layout::default()
                    .direction(Direction::Vertical)
                    .constraints([
                        Constraint::Percentage(self.left_ratio),
                        Constraint::Percentage(self.right_ratio),
                    ])
                    .split(area);
                vec![chunks[0], chunks[1]]
            }
            SplitMode::Grid => {
                let v_chunks = Layout::default()
                    .direction(Direction::Vertical)
                    .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
                    .split(area);

                let top_chunks = Layout::default()
                    .direction(Direction::Horizontal)
                    .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
                    .split(v_chunks[0]);

                let bottom_chunks = Layout::default()
                    .direction(Direction::Horizontal)
                    .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
                    .split(v_chunks[1]);

                vec![top_chunks[0], top_chunks[1], bottom_chunks[0], bottom_chunks[1]]
            }
        }
    }

    /// Render a single pane into the target rectangle.
    fn render_single_pane(
        &self,
        pane_idx: usize,
        session_idx: usize,
        area: Rect,
        buf: &mut Buffer,
    ) {
        let is_focused = session_idx == self.focused_index;

        let (border_style, title_style) = if is_focused {
            (Theme::active_border(), Theme::active_title())
        } else {
            (Theme::inactive_border(), Theme::inactive_title())
        };

        if let Some(session) = self.sessions.get(session_idx) {
            let focus_badge = if is_focused {
                format!(" {} FOCUS ", glyphs::POINTER)
            } else {
                format!(" Pane #{} ", pane_idx + 1)
            };

            let pid_text = match session.pid() {
                Some(p) => format!("(PID: {})", p),
                None => "(no pid)".to_string(),
            };

            let title = format!(" [{}│ {}:{} {}] ", focus_badge, session.id, session.slot_id, pid_text);

            let block = Block::default()
                .borders(Borders::ALL)
                .border_style(border_style)
                .title(Span::styled(title, title_style));

            let inner = block.inner(area);
            block.render(area, buf);

            // Render terminal content using TerminalScreenWidget
            let buf_lock = session.buffer();
            let screen_buffer = buf_lock.lock();

            let terminal_widget = TerminalScreenWidget::from_buffer(&screen_buffer)
                .show_cursor(is_focused && self.show_cursor);

            terminal_widget.render(inner, buf);
        } else {
            // Empty / placeholder pane
            let title = format!(" [ Pane #{} │ Empty Slot ] ", pane_idx + 1);
            let block = Block::default()
                .borders(Borders::ALL)
                .border_style(Theme::inactive_border())
                .title(Span::styled(title, Theme::inactive_title()));

            let inner = block.inner(area);
            block.render(area, buf);

            let empty_text = "No worker attached to this slot.\nPress Tab to switch or spawn via MCP.";
            let widget = TerminalScreenWidget::from_plain_text(empty_text)
                .default_fg(colors::FG_MUTED);
            widget.render(inner, buf);
        }
    }
}

impl<'a> Widget for SplitPanesWidget<'a> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let panes = self.compute_panes(area);
        if panes.is_empty() {
            return;
        }

        match self.mode {
            SplitMode::Single => {
                // Single focused pane
                self.render_single_pane(0, self.focused_index, panes[0], buf);
            }
            SplitMode::Horizontal | SplitMode::Vertical => {
                // Two panes
                // Pane 0: Active focused session
                // Pane 1: Next session in tab list, or session 1
                let second_idx = if self.sessions.len() > 1 {
                    if self.focused_index == 0 { 1 } else { 0 }
                } else {
                    1 // Will render placeholder
                };

                self.render_single_pane(0, self.focused_index, panes[0], buf);
                self.render_single_pane(1, second_idx, panes[1], buf);
            }
            SplitMode::Grid => {
                // Quad panes: 0, 1, 2, 3
                for (pane_idx, &pane_rect) in panes.iter().enumerate() {
                    self.render_single_pane(pane_idx, pane_idx, pane_rect, buf);
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;
    use std::collections::HashMap;

    #[test]
    fn test_split_mode_cycle() {
        let mut mode = SplitMode::Single;
        mode = mode.next();
        assert_eq!(mode, SplitMode::Horizontal);
        mode = mode.next();
        assert_eq!(mode, SplitMode::Vertical);
        mode = mode.next();
        assert_eq!(mode, SplitMode::Grid);
        mode = mode.next();
        assert_eq!(mode, SplitMode::Single);
    }

    #[test]
    fn test_split_panes_geometry() {
        let widget = SplitPanesWidget::new(SplitMode::Horizontal);
        let area = Rect::new(0, 0, 100, 50);
        let panes = widget.compute_panes(area);
        assert_eq!(panes.len(), 2);
        assert_eq!(panes[0].width, 50);
        assert_eq!(panes[1].width, 50);

        let grid_widget = SplitPanesWidget::new(SplitMode::Grid);
        let grid_panes = grid_widget.compute_panes(area);
        assert_eq!(grid_panes.len(), 4);
    }

    #[tokio::test]
    async fn test_split_panes_render_single() {
        let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };
        let session = Arc::new(
            WorkerSession::spawn("s1", "slot1", shell, vec![], None, HashMap::new(), 10, 30)
                .unwrap(),
        );

        let backend = TestBackend::new(80, 24);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                let widget = SplitPanesWidget::new(SplitMode::Single)
                    .sessions(vec![session])
                    .focused_index(0);
                f.render_widget(widget, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut text = String::new();
        for y in 0..5 {
            for x in 0..80 {
                text.push_str(term_buf[(x, y)].symbol());
            }
        }
        assert!(text.contains("s1:slot1"));
        assert!(text.contains("FOCUS"));
    }
}
