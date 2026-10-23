use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Widget},
};

use crate::ui::theme::Theme;

/// Resulting action from user interaction with the in-app directive editor.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DirectiveEditorAction {
    /// Save updated instructions/directives.
    Save(String),
    /// Cancel and close editor without saving.
    Cancel,
    /// Unhandled / internal navigation.
    None,
}

/// In-app multiline directive & instruction editor modal.
#[derive(Debug, Clone)]
pub struct DirectiveEditorModal {
    pub worker_id: String,
    pub slot_id: String,
    pub role: String,
    pub lines: Vec<String>,
    pub cursor_row: usize,
    pub cursor_col: usize,
    pub scroll_offset: usize,
    pub is_open: bool,
    pub theme: Theme,
}

impl DirectiveEditorModal {
    /// Create new in-app directive editor initialized with existing instructions or GEMINI.md template.
    pub fn new(
        worker_id: impl Into<String>,
        slot_id: impl Into<String>,
        role: impl Into<String>,
        initial_content: &str,
    ) -> Self {
        let lines: Vec<String> = if initial_content.is_empty() {
            vec![
                "# Worker Directives & Mission Guidelines".to_string(),
                "".to_string(),
                "- Role: Execute assigned tasks with high quality".to_string(),
                "- Guardrails: Never touch protected branches (main)".to_string(),
                "- Verification: Run all unit and integration tests".to_string(),
            ]
        } else {
            initial_content.lines().map(|s| s.to_string()).collect()
        };

        Self {
            worker_id: worker_id.into(),
            slot_id: slot_id.into(),
            role: role.into(),
            lines,
            cursor_row: 0,
            cursor_col: 0,
            scroll_offset: 0,
            is_open: true,
            theme: Theme::default(),
        }
    }

    /// Read raw full content string.
    pub fn content(&self) -> String {
        self.lines.join("\n")
    }

    /// Open or reset the editor with new content.
    pub fn open(&mut self, content: &str) {
        self.lines = content.lines().map(|s| s.to_string()).collect();
        if self.lines.is_empty() {
            self.lines.push(String::new());
        }
        self.cursor_row = 0;
        self.cursor_col = 0;
        self.scroll_offset = 0;
        self.is_open = true;
    }

    /// Close the editor.
    pub fn close(&mut self) {
        self.is_open = false;
    }

    /// Handle keyboard input inside the multiline editor.
    pub fn handle_key(&mut self, key: &KeyEvent) -> DirectiveEditorAction {
        if !self.is_open {
            return DirectiveEditorAction::None;
        }

        // Cancel / Dismiss on Esc
        if key.code == KeyCode::Esc {
            self.close();
            return DirectiveEditorAction::Cancel;
        }

        // Save on Ctrl+S or Ctrl+Enter
        if (key.code == KeyCode::Char('s') && key.modifiers.contains(KeyModifiers::CONTROL))
            || (key.code == KeyCode::Enter && key.modifiers.contains(KeyModifiers::CONTROL))
        {
            self.close();
            return DirectiveEditorAction::Save(self.content());
        }

        // Multiline editing
        match key.code {
            KeyCode::Enter => {
                if self.cursor_row < self.lines.len() {
                    let current = &self.lines[self.cursor_row];
                    let col = self.cursor_col.min(current.len());
                    let before = current[..col].to_string();
                    let after = current[col..].to_string();

                    self.lines[self.cursor_row] = before;
                    self.lines.insert(self.cursor_row + 1, after);
                    self.cursor_row += 1;
                    self.cursor_col = 0;
                }
                DirectiveEditorAction::None
            }
            KeyCode::Char(c) => {
                if self.cursor_row < self.lines.len() {
                    let line = &mut self.lines[self.cursor_row];
                    let col = self.cursor_col.min(line.len());
                    line.insert(col, c);
                    self.cursor_col += 1;
                }
                DirectiveEditorAction::None
            }
            KeyCode::Backspace => {
                if self.cursor_col > 0 {
                    if self.cursor_row < self.lines.len() {
                        let line = &mut self.lines[self.cursor_row];
                        if self.cursor_col <= line.len() {
                            line.remove(self.cursor_col - 1);
                            self.cursor_col -= 1;
                        }
                    }
                } else if self.cursor_row > 0 {
                    // Join with previous line
                    let current = self.lines.remove(self.cursor_row);
                    self.cursor_row -= 1;
                    let prev_len = self.lines[self.cursor_row].len();
                    self.lines[self.cursor_row].push_str(&current);
                    self.cursor_col = prev_len;
                }
                DirectiveEditorAction::None
            }
            KeyCode::Delete => {
                if self.cursor_row < self.lines.len() {
                    let line_len = self.lines[self.cursor_row].len();
                    if self.cursor_col < line_len {
                        self.lines[self.cursor_row].remove(self.cursor_col);
                    } else if self.cursor_row + 1 < self.lines.len() {
                        // Join with next line
                        let next = self.lines.remove(self.cursor_row + 1);
                        self.lines[self.cursor_row].push_str(&next);
                    }
                }
                DirectiveEditorAction::None
            }
            KeyCode::Up => {
                if self.cursor_row > 0 {
                    self.cursor_row -= 1;
                    let len = self.lines[self.cursor_row].len();
                    self.cursor_col = self.cursor_col.min(len);
                }
                DirectiveEditorAction::None
            }
            KeyCode::Down => {
                if self.cursor_row + 1 < self.lines.len() {
                    self.cursor_row += 1;
                    let len = self.lines[self.cursor_row].len();
                    self.cursor_col = self.cursor_col.min(len);
                }
                DirectiveEditorAction::None
            }
            KeyCode::Left => {
                if self.cursor_col > 0 {
                    self.cursor_col -= 1;
                } else if self.cursor_row > 0 {
                    self.cursor_row -= 1;
                    self.cursor_col = self.lines[self.cursor_row].len();
                }
                DirectiveEditorAction::None
            }
            KeyCode::Right => {
                let len = self.lines.get(self.cursor_row).map(|l| l.len()).unwrap_or(0);
                if self.cursor_col < len {
                    self.cursor_col += 1;
                } else if self.cursor_row + 1 < self.lines.len() {
                    self.cursor_row += 1;
                    self.cursor_col = 0;
                }
                DirectiveEditorAction::None
            }
            KeyCode::Home => {
                self.cursor_col = 0;
                DirectiveEditorAction::None
            }
            KeyCode::End => {
                if let Some(line) = self.lines.get(self.cursor_row) {
                    self.cursor_col = line.len();
                }
                DirectiveEditorAction::None
            }
            KeyCode::PageUp => {
                self.cursor_row = self.cursor_row.saturating_sub(10);
                let len = self.lines.get(self.cursor_row).map(|l| l.len()).unwrap_or(0);
                self.cursor_col = self.cursor_col.min(len);
                DirectiveEditorAction::None
            }
            KeyCode::PageDown => {
                self.cursor_row = (self.cursor_row + 10).min(self.lines.len().saturating_sub(1));
                let len = self.lines.get(self.cursor_row).map(|l| l.len()).unwrap_or(0);
                self.cursor_col = self.cursor_col.min(len);
                DirectiveEditorAction::None
            }
            _ => DirectiveEditorAction::None,
        }
    }

    /// Set theme.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.theme = theme;
        self
    }
}

impl Widget for DirectiveEditorModal {
    fn render(mut self, area: Rect, buf: &mut Buffer) {
        if !self.is_open || area.width < 40 || area.height < 10 {
            return;
        }

        let p = self.theme.palette();

        // Modal geometry
        let modal_width = 82.min(area.width.saturating_sub(4));
        let modal_height = 24.min(area.height.saturating_sub(2));
        let x = area.x + (area.width.saturating_sub(modal_width)) / 2;
        let y = area.y + (area.height.saturating_sub(modal_height)) / 2;
        let modal_area = Rect::new(x, y, modal_width, modal_height);

        Clear.render(modal_area, buf);

        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD))
            .style(Style::default().bg(p.bg_surface))
            .title(Span::styled(
                format!(" In-app Directive Editor: {} [{}] ({}) ", self.worker_id, self.slot_id, self.role),
                Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD),
            ));

        let inner = block.inner(modal_area);
        block.render(modal_area, buf);

        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Min(5),    // Textarea area
                Constraint::Length(1), // Footer statusline
            ])
            .split(inner);

        let view_height = chunks[0].height as usize;

        // Auto-scroll to follow cursor
        if self.cursor_row < self.scroll_offset {
            self.scroll_offset = self.cursor_row;
        } else if self.cursor_row >= self.scroll_offset + view_height {
            self.scroll_offset = self.cursor_row - view_height + 1;
        }

        // Render visible text lines with line numbers
        for i in 0..view_height {
            let line_idx = self.scroll_offset + i;
            let current_y = chunks[0].y + i as u16;

            if line_idx < self.lines.len() {
                let is_current_line = line_idx == self.cursor_row;
                let line_num_str = format!("{:>3} │ ", line_idx + 1);

                let line_num_style = if is_current_line {
                    Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(p.fg_muted)
                };

                let text = &self.lines[line_idx];
                let mut spans = vec![Span::styled(line_num_str, line_num_style)];

                if is_current_line {
                    let col = self.cursor_col.min(text.len());
                    let (before, after) = text.split_at(col);
                    spans.push(Span::styled(before, Style::default().fg(p.fg_light)));
                    spans.push(Span::styled("█", Style::default().fg(p.accent_cyan)));
                    spans.push(Span::styled(after, Style::default().fg(p.fg_light)));
                } else {
                    spans.push(Span::styled(text, Style::default().fg(p.fg_light)));
                }

                let line = Line::from(spans);
                buf.set_line(chunks[0].x, current_y, &line, chunks[0].width);
            }
        }

        // Footer statusline
        let footer_spans = vec![
            Span::styled(
                format!(" Line {}/{}, Col {} ", self.cursor_row + 1, self.lines.len().max(1), self.cursor_col + 1),
                Style::default().fg(p.accent_blue).add_modifier(Modifier::BOLD),
            ),
            Span::styled(" │ ", Style::default().fg(p.fg_muted)),
            Span::styled("[Ctrl+S] Save Directives", Style::default().fg(p.accent_green).add_modifier(Modifier::BOLD)),
            Span::styled(" │ ", Style::default().fg(p.fg_muted)),
            Span::styled("[Esc] Cancel", Style::default().fg(p.accent_red)),
        ];
        let footer_line = Line::from(footer_spans);
        buf.set_line(chunks[1].x, chunks[1].y, &footer_line, chunks[1].width);
    }
}

impl Widget for &DirectiveEditorModal {
    fn render(self, area: Rect, buf: &mut Buffer) {
        self.clone().render(area, buf);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;

    #[test]
    fn test_directive_editor_multiline_editing() {
        let mut editor = DirectiveEditorModal::new(
            "agy11",
            "11",
            "Backend Systems",
            "line 1\nline 2",
        );

        assert_eq!(editor.lines.len(), 2);
        assert_eq!(editor.cursor_row, 0);

        // Move down and edit line 2
        let down = KeyEvent::new(KeyCode::Down, KeyModifiers::NONE);
        editor.handle_key(&down);
        assert_eq!(editor.cursor_row, 1);

        // Move to end of line 2 and type "! edited"
        let end = KeyEvent::new(KeyCode::End, KeyModifiers::NONE);
        editor.handle_key(&end);
        for c in "! edited".chars() {
            let key = KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE);
            editor.handle_key(&key);
        }
        assert_eq!(editor.lines[1], "line 2! edited");

        // Insert new line with Enter
        let enter = KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE);
        editor.handle_key(&enter);
        assert_eq!(editor.lines.len(), 3);
        assert_eq!(editor.cursor_row, 2);

        // Save with Ctrl+S
        let save_key = KeyEvent::new(KeyCode::Char('s'), KeyModifiers::CONTROL);
        let action = editor.handle_key(&save_key);
        match action {
            DirectiveEditorAction::Save(content) => {
                assert!(content.contains("line 1"));
                assert!(content.contains("line 2! edited"));
            }
            _ => panic!("Expected Save action"),
        }
    }

    #[test]
    fn test_directive_editor_render() {
        let editor = DirectiveEditorModal::new(
            "agy51",
            "51",
            "Frontend Lead",
            "Task: Build modals\nVerification: Pass tests",
        );

        let backend = TestBackend::new(90, 26);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                f.render_widget(editor, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut text = String::new();
        for y in 0..26 {
            for x in 0..90 {
                text.push_str(term_buf[(x, y)].symbol());
            }
        }

        assert!(text.contains("Directive Editor"));
        assert!(text.contains("Build modals"));
        assert!(text.contains("Pass tests"));
        assert!(text.contains("Save Directives"));
    }
}
