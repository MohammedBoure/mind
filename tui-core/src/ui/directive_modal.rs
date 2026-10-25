use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Widget},
};

use crate::ui::theme::Theme;

/// Priority level for an injected operator directive.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum DirectivePriority {
    Low,
    #[default]
    Normal,
    High,
    Critical,
}

impl DirectivePriority {
    /// Canonical string identifier for MCP and prompt framing.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Low => "LOW",
            Self::Normal => "NORMAL",
            Self::High => "HIGH",
            Self::Critical => "CRITICAL",
        }
    }

    /// Human-friendly display label.
    pub fn label(&self) -> &'static str {
        match self {
            Self::Low => "1: Low",
            Self::Normal => "2: Normal",
            Self::High => "3: High",
            Self::Critical => "4: Critical",
        }
    }

    /// Cycle to next priority.
    pub fn next(&self) -> Self {
        match self {
            Self::Low => Self::Normal,
            Self::Normal => Self::High,
            Self::High => Self::Critical,
            Self::Critical => Self::Low,
        }
    }

    /// Cycle to previous priority.
    pub fn prev(&self) -> Self {
        match self {
            Self::Low => Self::Critical,
            Self::Normal => Self::Low,
            Self::High => Self::Normal,
            Self::Critical => Self::High,
        }
    }

    /// Color representing this priority.
    pub fn color(&self) -> Color {
        match self {
            Self::Low => Color::Rgb(115, 218, 202),     // Teal
            Self::Normal => Color::Rgb(122, 162, 247),  // Blue
            Self::High => Color::Rgb(224, 175, 104),    // Yellow/Amber
            Self::Critical => Color::Rgb(247, 118, 142),// Red
        }
    }
}

/// Action resulting from user interaction with the directive modal.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DirectiveModalAction {
    /// User submitted the directive.
    Submit {
        worker_id: String,
        message: String,
        priority: DirectivePriority,
    },
    /// User cancelled / closed the modal.
    Cancel,
    /// Key was handled internally without closing.
    None,
}

/// Directive Injection Modal allowing operators to type and send prioritized directives.
#[derive(Debug, Clone)]
pub struct DirectiveModal {
    pub worker_id: String,
    pub slot_id: String,
    pub role: String,
    pub message: String,
    pub cursor_pos: usize,
    pub priority: DirectivePriority,
    pub is_open: bool,
    pub theme: Theme,
}

impl DirectiveModal {
    /// Initialize a directive modal targeted at a specific worker.
    pub fn new(worker_id: impl Into<String>, slot_id: impl Into<String>, role: impl Into<String>) -> Self {
        Self {
            worker_id: worker_id.into(),
            slot_id: slot_id.into(),
            role: role.into(),
            message: String::new(),
            cursor_pos: 0,
            priority: DirectivePriority::Normal,
            is_open: true,
            theme: Theme::default(),
        }
    }

    /// Open or reset the modal.
    pub fn open(&mut self) {
        self.message.clear();
        self.cursor_pos = 0;
        self.is_open = true;
    }

    /// Close the modal.
    pub fn close(&mut self) {
        self.is_open = false;
    }

    /// Handle key event inside directive modal.
    pub fn handle_key(&mut self, key: &KeyEvent) -> DirectiveModalAction {
        if !self.is_open {
            return DirectiveModalAction::None;
        }

        // Cancel / Dismiss on Esc
        if key.code == KeyCode::Esc {
            self.close();
            return DirectiveModalAction::Cancel;
        }

        // Submit on Enter
        if key.code == KeyCode::Enter {
            let msg = self.message.trim().to_string();
            if !msg.is_empty() {
                self.close();
                return DirectiveModalAction::Submit {
                    worker_id: self.worker_id.clone(),
                    message: msg,
                    priority: self.priority,
                };
            } else {
                self.close();
                return DirectiveModalAction::Cancel;
            }
        }

        // Priority cycling via Tab or Up/Down
        if key.code == KeyCode::Tab {
            if key.modifiers.contains(KeyModifiers::SHIFT) {
                self.priority = self.priority.prev();
            } else {
                self.priority = self.priority.next();
            }
            return DirectiveModalAction::None;
        }

        if key.code == KeyCode::BackTab {
            self.priority = self.priority.prev();
            return DirectiveModalAction::None;
        }

        // Fast priority selector via Alt+1..4 or Ctrl+1..4
        if key.modifiers.contains(KeyModifiers::ALT) || key.modifiers.contains(KeyModifiers::CONTROL) {
            match key.code {
                KeyCode::Char('1') => { self.priority = DirectivePriority::Low; return DirectiveModalAction::None; }
                KeyCode::Char('2') => { self.priority = DirectivePriority::Normal; return DirectiveModalAction::None; }
                KeyCode::Char('3') => { self.priority = DirectivePriority::High; return DirectiveModalAction::None; }
                KeyCode::Char('4') => { self.priority = DirectivePriority::Critical; return DirectiveModalAction::None; }
                _ => {}
            }
        }

        // Text editing
        match key.code {
            KeyCode::Char(c) => {
                self.message.insert(self.cursor_pos, c);
                self.cursor_pos += 1;
                DirectiveModalAction::None
            }
            KeyCode::Backspace => {
                if self.cursor_pos > 0 && self.cursor_pos <= self.message.len() {
                    self.cursor_pos -= 1;
                    self.message.remove(self.cursor_pos);
                }
                DirectiveModalAction::None
            }
            KeyCode::Delete => {
                if self.cursor_pos < self.message.len() {
                    self.message.remove(self.cursor_pos);
                }
                DirectiveModalAction::None
            }
            KeyCode::Left => {
                if self.cursor_pos > 0 {
                    self.cursor_pos -= 1;
                }
                DirectiveModalAction::None
            }
            KeyCode::Right => {
                if self.cursor_pos < self.message.len() {
                    self.cursor_pos += 1;
                }
                DirectiveModalAction::None
            }
            KeyCode::Home => {
                self.cursor_pos = 0;
                DirectiveModalAction::None
            }
            KeyCode::End => {
                self.cursor_pos = self.message.len();
                DirectiveModalAction::None
            }
            _ => DirectiveModalAction::None,
        }
    }

    /// Set theme.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.theme = theme;
        self
    }
}

impl Widget for DirectiveModal {
    fn render(self, area: Rect, buf: &mut Buffer) {
        (&self).render(area, buf);
    }
}

impl Widget for &DirectiveModal {
    fn render(self, area: Rect, buf: &mut Buffer) {
        if !self.is_open || area.width < 30 || area.height < 8 {
            return;
        }

        let p = self.theme.palette();

        // Modal geometry
        let modal_width = 72.min(area.width.saturating_sub(4));
        let modal_height = 13.min(area.height.saturating_sub(2));
        let x = area.x + (area.width.saturating_sub(modal_width)) / 2;
        let y = area.y + (area.height.saturating_sub(modal_height)) / 2;
        let modal_area = Rect::new(x, y, modal_width, modal_height);

        Clear.render(modal_area, buf);

        let border_color = self.priority.color();
        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(border_color).add_modifier(Modifier::BOLD))
            .style(Style::default().bg(p.bg_surface))
            .title(Span::styled(
                format!(" Directive Injection: {} [{}] ", self.worker_id, self.slot_id),
                Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD),
            ));

        let inner = block.inner(modal_area);
        block.render(modal_area, buf);

        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(1), // Target summary
                Constraint::Length(2), // Priority selector
                Constraint::Length(3), // Input box
                Constraint::Length(1), // Key hints
                Constraint::Min(0),
            ])
            .split(inner);

        // 1. Target summary
        let target_line = Line::from(vec![
            Span::styled("  Target: ", Style::default().fg(p.fg_muted)),
            Span::styled(format!("{}:{}", self.worker_id, self.slot_id), Style::default().fg(p.accent_blue).add_modifier(Modifier::BOLD)),
            Span::styled(format!(" ({})", self.role), Style::default().fg(p.accent_teal)),
        ]);
        buf.set_line(chunks[0].x, chunks[0].y, &target_line, chunks[0].width);

        // 2. Priority selector pills
        let priorities = [
            DirectivePriority::Low,
            DirectivePriority::Normal,
            DirectivePriority::High,
            DirectivePriority::Critical,
        ];

        let mut prio_spans = vec![Span::styled("  Priority: ", Style::default().fg(p.fg_muted))];
        for prio in &priorities {
            let is_selected = *prio == self.priority;
            let style = if is_selected {
                Style::default()
                    .fg(p.bg_dark)
                    .bg(prio.color())
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default()
                    .fg(prio.color())
                    .bg(p.bg_dark)
            };
            prio_spans.push(Span::styled(format!(" [{}] ", prio.label()), style));
            prio_spans.push(Span::raw(" "));
        }
        let prio_line = Line::from(prio_spans);
        buf.set_line(chunks[1].x, chunks[1].y, &prio_line, chunks[1].width);

        // 3. Directive input box
        let input_block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(p.accent_blue))
            .title(Span::styled(" Directive Message ", Style::default().fg(p.accent_cyan)));

        let input_inner = input_block.inner(chunks[2]);
        input_block.render(chunks[2], buf);

        let display_text = if self.message.is_empty() {
            vec![
                Span::styled("Type urgent directive for active worker...", Style::default().fg(p.fg_muted).add_modifier(Modifier::ITALIC)),
                Span::styled("█", Style::default().fg(p.accent_cyan)),
            ]
        } else {
            let (before, after) = self.message.split_at(self.cursor_pos.min(self.message.len()));
            vec![
                Span::styled(before, Style::default().fg(p.fg_light)),
                Span::styled("█", Style::default().fg(p.accent_cyan)),
                Span::styled(after, Style::default().fg(p.fg_light)),
            ]
        };
        let input_line = Line::from(display_text);
        buf.set_line(input_inner.x, input_inner.y, &input_line, input_inner.width);

        // 4. Instructions footer
        let footer_line = Line::from(vec![
            Span::styled("  [Enter] Submit Directive  │  [Tab] Cycle Priority  │  [Esc] Cancel", Style::default().fg(p.fg_muted)),
        ]);
        buf.set_line(chunks[3].x, chunks[3].y, &footer_line, chunks[3].width);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;

    #[test]
    fn test_directive_modal_priority_cycle() {
        let mut modal = DirectiveModal::new("worker1", "agy11", "Backend Specialist");
        assert_eq!(modal.priority, DirectivePriority::Normal);

        let tab = KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE);
        modal.handle_key(&tab);
        assert_eq!(modal.priority, DirectivePriority::High);

        modal.handle_key(&tab);
        assert_eq!(modal.priority, DirectivePriority::Critical);

        modal.handle_key(&tab);
        assert_eq!(modal.priority, DirectivePriority::Low);
    }

    #[test]
    fn test_directive_modal_text_editing_and_submit() {
        let mut modal = DirectiveModal::new("worker2", "agy51", "Frontend Lead");

        // Type "STOP AND BUILD"
        for c in "STOP AND BUILD".chars() {
            let key = KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE);
            modal.handle_key(&key);
        }
        assert_eq!(modal.message, "STOP AND BUILD");
        assert_eq!(modal.cursor_pos, 14);

        // Backspace
        let bs = KeyEvent::new(KeyCode::Backspace, KeyModifiers::NONE);
        modal.handle_key(&bs);
        assert_eq!(modal.message, "STOP AND BUIL");

        // Submit
        let enter = KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE);
        let action = modal.handle_key(&enter);
        match action {
            DirectiveModalAction::Submit { worker_id, message, priority } => {
                assert_eq!(worker_id, "worker2");
                assert_eq!(message, "STOP AND BUIL");
                assert_eq!(priority, DirectivePriority::Normal);
            }
            _ => panic!("Expected submit action"),
        }
    }

    #[test]
    fn test_directive_modal_render() {
        let mut modal = DirectiveModal::new("coordinator", "agy1", "Lead Orchestrator");
        modal.message = "Prioritize Rust ratatui build".to_string();

        let backend = TestBackend::new(80, 20);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                f.render_widget(modal, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut text = String::new();
        for y in 0..20 {
            for x in 0..80 {
                text.push_str(term_buf[(x, y)].symbol());
            }
        }

        assert!(text.contains("Directive Injection"));
        assert!(text.contains("coordinator"));
        assert!(text.contains("Priority"));
        assert!(text.contains("Prioritize Rust ratatui build"));
    }
}
