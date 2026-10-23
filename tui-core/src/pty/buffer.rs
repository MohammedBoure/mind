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
    pub fn resize(&mut self, new_rows: usize, new_cols: usize) {
        let new_rows = new_rows.max(1);
        let new_cols = new_cols.max(1);
        if new_rows == self.rows && new_cols == self.cols {
            return;
        }

        let mut new_cells = vec![vec![ScreenCell::default(); new_cols]; new_rows];
        let copy_rows = self.rows.min(new_rows);
        let copy_cols = self.cols.min(new_cols);

        for r in 0..copy_rows {
            for c in 0..copy_cols {
                new_cells[r][c] = self.cells[r][c];
            }
        }

        self.rows = new_rows;
        self.cols = new_cols;
        self.cells = new_cells;
        self.cursor_row = self.cursor_row.min(new_rows.saturating_sub(1));
        self.cursor_col = self.cursor_col.min(new_cols.saturating_sub(1));
        self.touch();
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
