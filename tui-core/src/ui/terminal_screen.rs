use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Color, Modifier, Style},
    widgets::{Block, Widget},
};

use crate::pty::buffer::{CellColor, ScreenBuffer, ScreenCell};
use crate::ui::theme::colors;

/// Convert low-level PTY `CellColor` to Ratatui `Color`.
pub fn cell_color_to_ratatui(color: CellColor, default_fg: Color) -> Color {
    match color {
        CellColor::Reset => default_fg,
        CellColor::Ansi(code) => Color::Indexed(code),
        CellColor::Rgb(r, g, b) => Color::Rgb(r, g, b),
    }
}

/// Convert low-level PTY `CellColor` to Ratatui background `Color`.
pub fn cell_bg_to_ratatui(color: CellColor, default_bg: Color) -> Color {
    match color {
        CellColor::Reset => default_bg,
        CellColor::Ansi(code) => Color::Indexed(code),
        CellColor::Rgb(r, g, b) => Color::Rgb(r, g, b),
    }
}

/// Source data for terminal screen rendering.
pub enum TerminalSource<'a> {
    /// Direct cell matrix from `ScreenBuffer`.
    Cells {
        cells: &'a [Vec<ScreenCell>],
        cursor: Option<(usize, usize)>,
        version: u64,
    },
    /// Owned cell matrix slice (e.g. from history scrollback slice).
    OwnedCells {
        cells: Vec<Vec<ScreenCell>>,
        cursor: Option<(usize, usize)>,
        version: u64,
    },
    /// Clean plain text fallback.
    PlainText(&'a str),
}

/// High-efficiency Ratatui widget that renders the ANSI character matrix (`ScreenCell`)
/// or text buffer with dirty-frame checking and cursor rendering.
pub struct TerminalScreenWidget<'a> {
    source: TerminalSource<'a>,
    block: Option<Block<'a>>,
    show_cursor: bool,
    scroll_offset: usize,
    default_fg: Color,
    default_bg: Color,
}

impl<'a> TerminalScreenWidget<'a> {
    /// Create widget directly from a `ScreenBuffer` reference.
    pub fn from_buffer(buffer: &'a ScreenBuffer) -> Self {
        Self {
            source: TerminalSource::Cells {
                cells: buffer.cells(),
                cursor: Some((buffer.cursor_row, buffer.cursor_col)),
                version: buffer.version(),
            },
            block: None,
            show_cursor: true,
            scroll_offset: 0,
            default_fg: colors::FG_LIGHT,
            default_bg: Color::Reset,
        }
    }

    /// Create widget from raw cells matrix slice.
    pub fn from_cells(cells: &'a [Vec<ScreenCell>], cursor: Option<(usize, usize)>, version: u64) -> Self {
        Self {
            source: TerminalSource::Cells {
                cells,
                cursor,
                version,
            },
            block: None,
            show_cursor: cursor.is_some(),
            scroll_offset: 0,
            default_fg: colors::FG_LIGHT,
            default_bg: Color::Reset,
        }
    }

    /// Create widget from owned cells matrix (e.g. when scrolling through history scrollback).
    pub fn from_owned_cells(cells: Vec<Vec<ScreenCell>>, cursor: Option<(usize, usize)>, version: u64) -> Self {
        Self {
            source: TerminalSource::OwnedCells {
                cells,
                cursor,
                version,
            },
            block: None,
            show_cursor: cursor.is_some(),
            scroll_offset: 0,
            default_fg: colors::FG_LIGHT,
            default_bg: Color::Reset,
        }
    }

    /// Create widget from plain text string.
    pub fn from_plain_text(text: &'a str) -> Self {
        Self {
            source: TerminalSource::PlainText(text),
            block: None,
            show_cursor: false,
            scroll_offset: 0,
            default_fg: colors::FG_LIGHT,
            default_bg: Color::Reset,
        }
    }

    /// Wrap the terminal viewport with a decorative block / border.
    pub fn block(mut self, block: Block<'a>) -> Self {
        self.block = Some(block);
        self
    }

    /// Toggle cursor visibility.
    pub fn show_cursor(mut self, show: bool) -> Self {
        self.show_cursor = show;
        self
    }

    /// Set vertical scroll offset (for history viewing).
    pub fn scroll_offset(mut self, offset: usize) -> Self {
        self.scroll_offset = offset;
        self
    }

    /// Set default foreground color.
    pub fn default_fg(mut self, color: Color) -> Self {
        self.default_fg = color;
        self
    }

    /// Set default background color.
    pub fn default_bg(mut self, color: Color) -> Self {
        self.default_bg = color;
        self
    }

    /// Extract current buffer version if available.
    pub fn version(&self) -> Option<u64> {
        match &self.source {
            TerminalSource::Cells { version, .. } => Some(*version),
            TerminalSource::OwnedCells { version, .. } => Some(*version),
            TerminalSource::PlainText(_) => None,
        }
    }

    /// Helper for dirty-frame checking: Returns true if the current version
    /// is newer than `cached_version`.
    pub fn is_dirty(&self, cached_version: u64) -> bool {
        match &self.source {
            TerminalSource::Cells { version, .. } => *version != cached_version,
            TerminalSource::OwnedCells { version, .. } => *version != cached_version,
            TerminalSource::PlainText(_) => true,
        }
    }
}

impl<'a> Widget for TerminalScreenWidget<'a> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let render_area = match self.block {
            Some(ref b) => {
                let inner = b.inner(area);
                b.clone().render(area, buf);
                inner
            }
            None => area,
        };

        if render_area.width == 0 || render_area.height == 0 {
            return;
        }

        match self.source {
            TerminalSource::Cells { cells, cursor, .. } => {
                Self::render_cells(cells, cursor, self.scroll_offset, self.show_cursor, self.default_fg, self.default_bg, render_area, buf);
            }
            TerminalSource::OwnedCells { ref cells, cursor, .. } => {
                Self::render_cells(cells, cursor, self.scroll_offset, self.show_cursor, self.default_fg, self.default_bg, render_area, buf);
            }
            TerminalSource::PlainText(text) => {
                let lines: Vec<&str> = text.lines().skip(self.scroll_offset).collect();
                for (r_idx, line) in lines.iter().take(render_area.height as usize).enumerate() {
                    let y = render_area.y + r_idx as u16;
                    let chars: Vec<char> = line.chars().take(render_area.width as usize).collect();

                    for (c_idx, &ch) in chars.iter().enumerate() {
                        let x = render_area.x + c_idx as u16;
                        let target_cell = &mut buf[(x, y)];
                        target_cell.set_char(ch);
                        target_cell.set_fg(self.default_fg);
                        target_cell.set_bg(self.default_bg);
                    }
                }
            }
        }
    }
}

impl<'a> TerminalScreenWidget<'a> {
    #[allow(clippy::too_many_arguments)]
    fn render_cells(
        cells: &[Vec<ScreenCell>],
        cursor: Option<(usize, usize)>,
        scroll_offset: usize,
        show_cursor: bool,
        default_fg: Color,
        default_bg: Color,
        render_area: Rect,
        buf: &mut Buffer,
    ) {
        let total_rows = cells.len();
        let start_row = scroll_offset.min(total_rows.saturating_sub(1));
        let visible_rows = (total_rows - start_row).min(render_area.height as usize);

        for (r_idx, row) in cells.iter().skip(start_row).take(visible_rows).enumerate() {
            let y = render_area.y + r_idx as u16;
            let visible_cols = row.len().min(render_area.width as usize);

            for (c_idx, cell) in row.iter().take(visible_cols).enumerate() {
                let x = render_area.x + c_idx as u16;

                let fg = cell_color_to_ratatui(cell.fg, default_fg);
                let bg = cell_bg_to_ratatui(cell.bg, default_bg);

                let mut modifier = Modifier::empty();
                if cell.bold {
                    modifier |= Modifier::BOLD;
                }
                if cell.dim {
                    modifier |= Modifier::DIM;
                }
                if cell.italic {
                    modifier |= Modifier::ITALIC;
                }
                if cell.underline {
                    modifier |= Modifier::UNDERLINED;
                }

                let target_cell = &mut buf[(x, y)];
                target_cell.set_char(cell.c);
                target_cell.set_fg(fg);
                target_cell.set_bg(bg);
                target_cell.set_style(Style::default().fg(fg).bg(bg).add_modifier(modifier));
            }
        }

        // Render cursor if requested and within viewport bounds
        if show_cursor {
            if let Some((cur_row, cur_col)) = cursor {
                if cur_row >= start_row && cur_row < start_row + visible_rows {
                    let cur_y = render_area.y + (cur_row - start_row) as u16;
                    if (cur_col as u16) < render_area.width {
                        let cur_x = render_area.x + cur_col as u16;
                        let cursor_cell = &mut buf[(cur_x, cur_y)];
                        cursor_cell.set_style(
                            Style::default()
                                .fg(colors::BG_DARK)
                                .bg(colors::ACCENT_CYAN)
                                .add_modifier(Modifier::BOLD | Modifier::REVERSED),
                        );
                    }
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

    #[test]
    fn test_terminal_screen_widget_cell_rendering() {
        let mut buffer = ScreenBuffer::new(5, 20);
        buffer.process_bytes(b"\x1b[32mAntigravity\x1b[0m TUI");

        let backend = TestBackend::new(20, 5);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                let widget = TerminalScreenWidget::from_buffer(&buffer);
                f.render_widget(widget, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let first_char = term_buf[(0, 0)].symbol();
        assert_eq!(first_char, "A");
    }

    #[test]
    fn test_dirty_frame_checking() {
        let mut buffer = ScreenBuffer::new(5, 20);
        let v0 = buffer.version();
        let widget = TerminalScreenWidget::from_buffer(&buffer);
        assert!(!widget.is_dirty(v0));

        buffer.process_bytes(b"A");
        let widget_dirty = TerminalScreenWidget::from_buffer(&buffer);
        assert!(widget_dirty.is_dirty(v0));
    }
}
