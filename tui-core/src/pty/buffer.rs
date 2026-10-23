use std::collections::VecDeque;
use vte::{Params, Parser, Perform};

/// Cell color representation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum CellColor {
    #[default]
    Reset,
    Ansi(u8),
    Rgb(u8, u8, u8),
}

/// An individual cell on the virtual terminal screen grid.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ScreenCell {
    pub c: char,
    pub fg: CellColor,
    pub bg: CellColor,
    pub bold: bool,
    pub dim: bool,
    pub italic: bool,
    pub underline: bool,
}

impl Default for ScreenCell {
    fn default() -> Self {
        Self {
            c: ' ',
            fg: CellColor::Reset,
            bg: CellColor::Reset,
            bold: false,
            dim: false,
            italic: false,
            underline: false,
        }
    }
}

/// Virtual screen buffer with in-memory ANSI state machine and scrollback history.
#[derive(Debug)]
pub struct ScreenBuffer {
    pub rows: usize,
    pub cols: usize,
    pub cursor_row: usize,
    pub cursor_col: usize,
    cells: Vec<Vec<ScreenCell>>,
    scrollback: VecDeque<Vec<ScreenCell>>,
    max_scrollback: usize,
    current_fg: CellColor,
    current_bg: CellColor,
    current_bold: bool,
    current_dim: bool,
    current_italic: bool,
    current_underline: bool,
    version: u64,
}

impl ScreenBuffer {
    pub fn new(rows: usize, cols: usize) -> Self {
        let rows = rows.max(1);
        let cols = cols.max(1);
        let cells = vec![vec![ScreenCell::default(); cols]; rows];
        Self {
            rows,
            cols,
            cursor_row: 0,
            cursor_col: 0,
            cells,
            scrollback: VecDeque::new(),
            max_scrollback: 2000,
            current_fg: CellColor::Reset,
            current_bg: CellColor::Reset,
            current_bold: false,
            current_dim: false,
            current_italic: false,
            current_underline: false,
            version: 0,
        }
    }

    /// Monotonically increasing version counter for O(1) dirty checking.
    pub fn version(&self) -> u64 {
        self.version
    }

    /// Mark buffer state as modified.
    fn touch(&mut self) {
        self.version = self.version.wrapping_add(1);
    }

    /// Process incoming raw byte slice from PTY master stream.
    pub fn process_bytes(&mut self, bytes: &[u8]) {
        let mut parser = Parser::new();
        parser.advance(self, bytes);
        self.touch();
    }

    /// Resize the virtual screen dimensions.
    ///
    /// Preserves content and prevents text tearing or character clipping:
    /// - Column shrinkage truncates cells; column expansion pads with default blank cells.
    /// - Row shrinkage shifts overflow rows from the top of the viewport into scrollback history,
    ///   preserving active command lines and output while capping at `max_scrollback` to prevent memory leaks.
    /// - Row expansion pulls recent lines from scrollback back into the viewport if available.
    pub fn resize(&mut self, new_rows: usize, new_cols: usize) {
        let new_rows = new_rows.max(1);
        let new_cols = new_cols.max(1);
        if new_rows == self.rows && new_cols == self.cols {
            return;
        }

        // 1. Column adjustment across current cells
        for row in &mut self.cells {
            if new_cols > self.cols {
                row.resize(new_cols, ScreenCell::default());
            } else if new_cols < self.cols {
                row.truncate(new_cols);
            }
        }

        // Column adjustment across scrollback history
        for row in &mut self.scrollback {
            if new_cols > self.cols {
                row.resize(new_cols, ScreenCell::default());
            } else if new_cols < self.cols {
                row.truncate(new_cols);
            }
        }

        // 2. Row adjustment
        if new_rows < self.rows {
            // Viewport is shrinking vertically.
            // Find lowest active row to keep cursor and active content in view without clipping.
            let last_active = self
                .cells
                .iter()
                .rposition(|row| row.iter().any(|c| c.c != ' ' && c.c != '\0'))
                .unwrap_or(0);
            let active_extent = (self.cursor_row + 1).max(last_active + 1);

            if active_extent > new_rows {
                let shift = (active_extent - new_rows).min(self.cells.len());
                for _ in 0..shift {
                    let top = self.cells.remove(0);
                    if self.scrollback.len() >= self.max_scrollback {
                        self.scrollback.pop_front();
                    }
                    self.scrollback.push_back(top);
                }
                self.cursor_row = self.cursor_row.saturating_sub(shift);
            }

            // Truncate any remaining excess blank rows at the bottom
            self.cells.truncate(new_rows);
            while self.cells.len() < new_rows {
                self.cells.push(vec![ScreenCell::default(); new_cols]);
            }
        } else if new_rows > self.rows {
            // Viewport is expanding vertically.
            // Pull lines from recent scrollback into the top of the viewport if available.
            let deficit = new_rows - self.cells.len();
            let pull_count = deficit.min(self.scrollback.len());

            for _ in 0..pull_count {
                if let Some(restored_row) = self.scrollback.pop_back() {
                    self.cells.insert(0, restored_row);
                }
            }
            self.cursor_row = (self.cursor_row + pull_count).min(new_rows.saturating_sub(1));

            // Pad remaining bottom space with blank lines
            while self.cells.len() < new_rows {
                self.cells.push(vec![ScreenCell::default(); new_cols]);
            }
        }

        self.rows = new_rows;
        self.cols = new_cols;
        self.cursor_row = self.cursor_row.min(new_rows.saturating_sub(1));
        self.cursor_col = self.cursor_col.min(new_cols.saturating_sub(1));
        self.touch();
    }

    /// Retrieve rows for rendering in a viewport with given `scroll_offset` (0 = live screen bottom)
    /// and `height`. Also returns relative cursor coordinate `(row, col)` if visible in the viewport.
    pub fn viewport_cells(
        &self,
        scroll_offset: usize,
        height: usize,
    ) -> (Vec<Vec<ScreenCell>>, Option<(usize, usize)>) {
        let history_len = self.scrollback.len();
        let total_lines = history_len + self.rows;
        let view_height = height.min(self.rows).max(1);
        let max_offset = history_len;
        let clamped_offset = scroll_offset.min(max_offset);

        let end_idx = total_lines.saturating_sub(clamped_offset);
        let start_idx = end_idx.saturating_sub(view_height);

        let mut result = Vec::with_capacity(view_height);
        for idx in start_idx..end_idx {
            if idx < history_len {
                result.push(self.scrollback[idx].clone());
            } else {
                let screen_r = idx - history_len;
                if screen_r < self.cells.len() {
                    result.push(self.cells[screen_r].clone());
                } else {
                    result.push(vec![ScreenCell::default(); self.cols]);
                }
            }
        }

        // Relative cursor position if cursor falls within [start_idx, end_idx)
        let cursor_abs_idx = history_len + self.cursor_row;
        let rel_cursor = if clamped_offset == 0 {
            if self.cursor_row < view_height {
                Some((self.cursor_row, self.cursor_col))
            } else {
                None
            }
        } else if cursor_abs_idx >= start_idx && cursor_abs_idx < end_idx {
            Some((cursor_abs_idx - start_idx, self.cursor_col))
        } else {
            None
        };

        (result, rel_cursor)
    }

    /// Move cursor down by 1 line, scrolling the screen buffer if reaching bottom.
    fn linefeed(&mut self) {
        if self.cursor_row + 1 >= self.rows {
            // Push top row to scrollback
            if !self.cells.is_empty() {
                let top_row = self.cells.remove(0);
                if self.scrollback.len() >= self.max_scrollback {
                    self.scrollback.pop_front();
                }
                self.scrollback.push_back(top_row);
                self.cells.push(vec![ScreenCell::default(); self.cols]);
            }
        } else {
            self.cursor_row += 1;
        }
    }

    /// Carriage return: move cursor to the first column.
    fn carriage_return(&mut self) {
        self.cursor_col = 0;
    }

    /// Render visible screen and optional scrollback as clean ANSI-free text.
    /// Trailing blank lines are stripped so `max_lines` returns the most recent active lines.
    /// If `max_lines` is 0, renders the full scrollback + visible screen.
    pub fn render_plain_text(&self, max_lines: usize) -> String {
        let mut all_lines: Vec<String> = Vec::new();

        // 1. Scrollback history
        for row in &self.scrollback {
            all_lines.push(Self::row_to_plain_text(row));
        }

        // 2. Current screen cells
        for row in &self.cells {
            all_lines.push(Self::row_to_plain_text(row));
        }

        // 3. Filter out consecutive trailing empty lines
        while let Some(last) = all_lines.last() {
            if last.is_empty() {
                all_lines.pop();
            } else {
                break;
            }
        }

        // 4. Return last `max_lines`
        if max_lines > 0 && all_lines.len() > max_lines {
            let drain_count = all_lines.len() - max_lines;
            all_lines.drain(0..drain_count);
        }

        all_lines.join("\n")
    }

    /// Extract visible screen rows as clean plain text.
    pub fn get_visible_text(&self) -> String {
        self.cells
            .iter()
            .map(|row| Self::row_to_plain_text(row))
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// Get current cells slice for rendering in TUI widgets (e.g. Ratatui).
    pub fn cells(&self) -> &[Vec<ScreenCell>] {
        &self.cells
    }

    /// Get total count of scrollback history lines.
    pub fn history_count(&self) -> usize {
        self.scrollback.len()
    }

    fn row_to_plain_text(row: &[ScreenCell]) -> String {
        let s: String = row.iter().map(|cell| cell.c).collect();
        s.trim_end().to_string()
    }
}

impl Perform for ScreenBuffer {
    fn print(&mut self, c: char) {
        if self.cursor_row < self.rows && self.cursor_col < self.cols {
            self.cells[self.cursor_row][self.cursor_col] = ScreenCell {
                c,
                fg: self.current_fg,
                bg: self.current_bg,
                bold: self.current_bold,
                dim: self.current_dim,
                italic: self.current_italic,
                underline: self.current_underline,
            };
            self.cursor_col += 1;
            if self.cursor_col >= self.cols {
                self.cursor_col = 0;
                self.linefeed();
            }
        }
    }

    fn execute(&mut self, byte: u8) {
        match byte {
            b'\n' => self.linefeed(),
            b'\r' => self.carriage_return(),
            b'\t' => {
                let tab_stop = 8;
                let next_col = ((self.cursor_col / tab_stop) + 1) * tab_stop;
                self.cursor_col = next_col.min(self.cols.saturating_sub(1));
            }
            0x08 => {
                // Backspace
                self.cursor_col = self.cursor_col.saturating_sub(1);
            }
            _ => {}
        }
    }

    fn hook(&mut self, _params: &Params, _intermediates: &[u8], _ignore: bool, _action: char) {}
    fn put(&mut self, _byte: u8) {}
    fn unhook(&mut self) {}
    fn osc_dispatch(&mut self, _params: &[&[u8]], _bell_terminated: bool) {}
    fn esc_dispatch(&mut self, _intermediates: &[u8], _ignore: bool, _byte: u8) {}

    fn csi_dispatch(&mut self, params: &Params, _intermediates: &[u8], _ignore: bool, action: char) {
        let p: Vec<u16> = params.iter().map(|sub| sub[0]).collect();
        match action {
            'H' | 'f' => {
                // Cursor position (1-based: row, col)
                let r = p.first().copied().unwrap_or(1).max(1) as usize - 1;
                let c = p.get(1).copied().unwrap_or(1).max(1) as usize - 1;
                self.cursor_row = r.min(self.rows.saturating_sub(1));
                self.cursor_col = c.min(self.cols.saturating_sub(1));
            }
            'A' => {
                // Cursor up
                let n = p.first().copied().unwrap_or(1).max(1) as usize;
                self.cursor_row = self.cursor_row.saturating_sub(n);
            }
            'B' => {
                // Cursor down
                let n = p.first().copied().unwrap_or(1).max(1) as usize;
                self.cursor_row = (self.cursor_row + n).min(self.rows.saturating_sub(1));
            }
            'C' => {
                // Cursor forward
                let n = p.first().copied().unwrap_or(1).max(1) as usize;
                self.cursor_col = (self.cursor_col + n).min(self.cols.saturating_sub(1));
            }
            'D' => {
                // Cursor backward
                let n = p.first().copied().unwrap_or(1).max(1) as usize;
                self.cursor_col = self.cursor_col.saturating_sub(n);
            }
            'J' => {
                // Erase in display
                let mode = p.first().copied().unwrap_or(0);
                match mode {
                    0 => {
                        // Clear from cursor to end of screen
                        for c in self.cursor_col..self.cols {
                            if self.cursor_row < self.rows {
                                self.cells[self.cursor_row][c] = ScreenCell::default();
                            }
                        }
                        for r in (self.cursor_row + 1)..self.rows {
                            for c in 0..self.cols {
                                self.cells[r][c] = ScreenCell::default();
                            }
                        }
                    }
                    1 => {
                        // Clear from beginning of screen to cursor
                        for r in 0..self.cursor_row {
                            for c in 0..self.cols {
                                self.cells[r][c] = ScreenCell::default();
                            }
                        }
                        for c in 0..=self.cursor_col.min(self.cols.saturating_sub(1)) {
                            if self.cursor_row < self.rows {
                                self.cells[self.cursor_row][c] = ScreenCell::default();
                            }
                        }
                    }
                    2 | 3 => {
                        // Clear complete display
                        for row in &mut self.cells {
                            for cell in row {
                                *cell = ScreenCell::default();
                            }
                        }
                    }
                    _ => {}
                }
            }
            'K' => {
                // Erase in line
                let mode = p.first().copied().unwrap_or(0);
                if self.cursor_row < self.rows {
                    match mode {
                        0 => {
                            // Clear from cursor to line end
                            for c in self.cursor_col..self.cols {
                                self.cells[self.cursor_row][c] = ScreenCell::default();
                            }
                        }
                        1 => {
                            // Clear from start to cursor
                            for c in 0..=self.cursor_col.min(self.cols.saturating_sub(1)) {
                                self.cells[self.cursor_row][c] = ScreenCell::default();
                            }
                        }
                        2 => {
                            // Clear entire line
                            for c in 0..self.cols {
                                self.cells[self.cursor_row][c] = ScreenCell::default();
                            }
                        }
                        _ => {}
                    }
                }
            }
            'm' => {
                // SGR - Select Graphic Rendition
                if p.is_empty() {
                    self.reset_sgr();
                } else {
                    let mut i = 0;
                    while i < p.len() {
                        match p[i] {
                            0 => self.reset_sgr(),
                            1 => self.current_bold = true,
                            2 => self.current_dim = true,
                            3 => self.current_italic = true,
                            4 => self.current_underline = true,
                            22 => {
                                self.current_bold = false;
                                self.current_dim = false;
                            }
                            23 => self.current_italic = false,
                            24 => self.current_underline = false,
                            30..=37 => self.current_fg = CellColor::Ansi((p[i] - 30) as u8),
                            38 => {
                                // Extended foreground
                                if i + 2 < p.len() && p[i + 1] == 5 {
                                    self.current_fg = CellColor::Ansi(p[i + 2] as u8);
                                    i += 2;
                                } else if i + 4 < p.len() && p[i + 1] == 2 {
                                    self.current_fg = CellColor::Rgb(
                                        p[i + 2] as u8,
                                        p[i + 3] as u8,
                                        p[i + 4] as u8,
                                    );
                                    i += 4;
                                }
                            }
                            39 => self.current_fg = CellColor::Reset,
                            40..=47 => self.current_bg = CellColor::Ansi((p[i] - 40) as u8),
                            48 => {
                                // Extended background
                                if i + 2 < p.len() && p[i + 1] == 5 {
                                    self.current_bg = CellColor::Ansi(p[i + 2] as u8);
                                    i += 2;
                                } else if i + 4 < p.len() && p[i + 1] == 2 {
                                    self.current_bg = CellColor::Rgb(
                                        p[i + 2] as u8,
                                        p[i + 3] as u8,
                                        p[i + 4] as u8,
                                    );
                                    i += 4;
                                }
                            }
                            49 => self.current_bg = CellColor::Reset,
                            90..=97 => self.current_fg = CellColor::Ansi((p[i] - 90 + 8) as u8),
                            100..=107 => self.current_bg = CellColor::Ansi((p[i] - 100 + 8) as u8),
                            _ => {}
                        }
                        i += 1;
                    }
                }
            }
            _ => {}
        }
    }
}

impl ScreenBuffer {
    fn reset_sgr(&mut self) {
        self.current_fg = CellColor::Reset;
        self.current_bg = CellColor::Reset;
        self.current_bold = false;
        self.current_dim = false;
        self.current_italic = false;
        self.current_underline = false;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resize_shrink_preserves_content_in_scrollback() {
        let mut buf = ScreenBuffer::new(5, 20);
        buf.process_bytes(b"line 1\r\nline 2\r\nline 3\r\nline 4\r\nline 5");
        assert_eq!(buf.history_count(), 0);

        // Shrink from 5 rows to 3 rows
        buf.resize(3, 20);
        assert_eq!(buf.rows, 3);
        // Top 2 lines should have been pushed to scrollback
        assert_eq!(buf.history_count(), 2);

        let rendered = buf.render_plain_text(0);
        assert!(rendered.contains("line 1"));
        assert!(rendered.contains("line 5"));
    }

    #[test]
    fn test_resize_expand_restores_from_scrollback() {
        let mut buf = ScreenBuffer::new(3, 20);
        buf.process_bytes(b"line 1\r\nline 2\r\nline 3\r\nline 4\r\nline 5");
        // Due to linefeeds, lines 1 and 2 are in scrollback
        assert_eq!(buf.history_count(), 2);

        // Expand to 5 rows
        buf.resize(5, 20);
        assert_eq!(buf.rows, 5);
        // Both lines restored from scrollback into the viewport
        assert_eq!(buf.history_count(), 0);
        let visible = buf.get_visible_text();
        assert!(visible.contains("line 1"));
        assert!(visible.contains("line 5"));
    }

    #[test]
    fn test_resize_column_padding_and_truncation() {
        let mut buf = ScreenBuffer::new(3, 10);
        buf.process_bytes(b"1234567890");
        assert_eq!(buf.cells[0].len(), 10);

        // Expand columns
        buf.resize(3, 20);
        assert_eq!(buf.cols, 20);
        assert_eq!(buf.cells[0].len(), 20);
        assert_eq!(buf.cells[0][0].c, '1');
        assert_eq!(buf.cells[0][15].c, ' ');

        // Shrink columns
        buf.resize(3, 5);
        assert_eq!(buf.cols, 5);
        assert_eq!(buf.cells[0].len(), 5);
        assert_eq!(buf.cells[0][4].c, '5');
    }

    #[test]
    fn test_viewport_cells_with_scrollback() {
        let mut buf = ScreenBuffer::new(3, 20);
        buf.process_bytes(b"first\r\nsecond\r\nthird\r\nfourth\r\nfifth");
        // Viewport at bottom (offset = 0)
        let (live_cells, cursor) = buf.viewport_cells(0, 3);
        assert_eq!(live_cells.len(), 3);
        assert!(cursor.is_some());

        // Scrolled up into history (offset = 2)
        let (hist_cells, _) = buf.viewport_cells(2, 3);
        assert_eq!(hist_cells.len(), 3);
        let s: String = hist_cells[0].iter().map(|c| c.c).collect();
        assert!(s.contains("first"));
    }
}
