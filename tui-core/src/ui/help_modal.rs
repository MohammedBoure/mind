use crossterm::event::{KeyCode, KeyEvent};
use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Paragraph, Widget},
};

use crate::ui::theme::Theme;

/// Keyboard shortcut category for the help reference modal.
#[derive(Debug, Clone)]
pub struct ShortcutEntry {
    pub key: &'static str,
    pub description: &'static str,
}

/// Accessible shortcuts help modal matching Python Mind shortcuts and `agi.toml`.
#[derive(Debug, Clone)]
pub struct HelpModal {
    theme: Theme,
    is_open: bool,
}

impl Default for HelpModal {
    fn default() -> Self {
        Self::new(Theme::default())
    }
}

impl HelpModal {
    /// Create new shortcuts help modal.
    pub fn new(theme: Theme) -> Self {
        Self {
            theme,
            is_open: true,
        }
    }

    /// Check if the modal is currently open.
    pub fn is_open(&self) -> bool {
        self.is_open
    }

    /// Open or reopen the modal.
    pub fn open(&mut self) {
        self.is_open = true;
    }

    /// Close the modal.
    pub fn close(&mut self) {
        self.is_open = false;
    }

    /// Handle keyboard input. Returns true if modal should be closed.
    pub fn handle_key(&mut self, key: &KeyEvent) -> bool {
        match key.code {
            KeyCode::Esc | KeyCode::Char('?') | KeyCode::Char('q') => {
                self.close();
                true
            }
            _ => false,
        }
    }

    /// Set theme.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.theme = theme;
        self
    }
}

impl Widget for HelpModal {
    fn render(self, area: Rect, buf: &mut Buffer) {
        (&self).render(area, buf);
    }
}

impl Widget for &HelpModal {
    fn render(self, area: Rect, buf: &mut Buffer) {
        if !self.is_open || area.width < 30 || area.height < 10 {
            return;
        }

        let p = self.theme.palette();

        // Compute centered popup geometry
        let modal_width = 72.min(area.width.saturating_sub(4));
        let modal_height = 22.min(area.height.saturating_sub(2));
        let x = area.x + (area.width.saturating_sub(modal_width)) / 2;
        let y = area.y + (area.height.saturating_sub(modal_height)) / 2;
        let modal_area = Rect::new(x, y, modal_width, modal_height);

        // Clear underlying terminal screen
        Clear.render(modal_area, buf);

        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD))
            .style(Style::default().bg(p.bg_surface))
            .title(Span::styled(
                " Keyboard Shortcuts Reference (? / Esc to close) ",
                Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD),
            ));

        let inner = block.inner(modal_area);
        block.render(modal_area, buf);

        let sections = vec![
            ("SWARM NAVIGATION & TABS", vec![
                ShortcutEntry { key: "Tab", description: "Focus next worker tab / pane" },
                ShortcutEntry { key: "Shift+Tab", description: "Focus previous worker tab / pane" },
                ShortcutEntry { key: "1..9", description: "Fast tab jump to worker #1..#9" },
            ]),
            ("DIRECTIVES & INSTRUCTIONS", vec![
                ShortcutEntry { key: "m / Ctrl+M", description: "Open Directive Injection Modal" },
                ShortcutEntry { key: "d / Ctrl+D", description: "Open In-app Directive Editor Modal" },
                ShortcutEntry { key: "o / Ctrl+O", description: "Open directive in system editor ($EDITOR)" },
            ]),
            ("LAYOUT & SESSIONS", vec![
                ShortcutEntry { key: "s", description: "Cycle split layout (Single -> Horiz -> Vert -> Grid)" },
                ShortcutEntry { key: "n", description: "Add new agent worker tab modal" },
                ShortcutEntry { key: "p / Ctrl+P", description: "Launch interactive Session Picker screen" },
                ShortcutEntry { key: "b", description: "Toggle worker list and resource sidebar" },
            ]),
            ("TERMINAL & APPLICATION", vec![
                ShortcutEntry { key: "PageUp/Down", description: "Scrollback history navigation" },
                ShortcutEntry { key: "F4 / Alt+T", description: "Cycle theme (TokyoNight, HighContrast, ColorBlind)" },
                ShortcutEntry { key: "Ctrl+C", description: "Send SIGINT interrupt to active worker" },
                ShortcutEntry { key: "q / Ctrl+Q", description: "Quit application & persist session state" },
            ]),
        ];

        let mut lines = Vec::new();

        for (section_title, entries) in sections {
            lines.push(Line::from(vec![
                Span::styled(
                    format!("  {}  ", section_title),
                    Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD),
                ),
            ]));

            for entry in entries {
                lines.push(Line::from(vec![
                    Span::styled(format!("    {:<16}", entry.key), Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD)),
                    Span::styled(entry.description, Style::default().fg(p.fg_light)),
                ]));
            }
            lines.push(Line::from(""));
        }

        lines.push(Line::from(vec![
            Span::styled(
                "  Configurable via ~/.config/mind/agi.toml or ~/.mind/config.toml",
                Style::default().fg(p.fg_muted).add_modifier(Modifier::ITALIC),
            ),
        ]));

        let paragraph = Paragraph::new(lines).style(Style::default().bg(p.bg_surface));
        paragraph.render(inner, buf);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;

    #[test]
    fn test_help_modal_open_close_keys() {
        let mut modal = HelpModal::default();
        assert!(modal.is_open());

        let esc = KeyEvent::new(KeyCode::Esc, crossterm::event::KeyModifiers::NONE);
        assert!(modal.handle_key(&esc));
        assert!(!modal.is_open());

        modal.open();
        let question = KeyEvent::new(KeyCode::Char('?'), crossterm::event::KeyModifiers::NONE);
        assert!(modal.handle_key(&question));
        assert!(!modal.is_open());

        modal.open();
        let q_key = KeyEvent::new(KeyCode::Char('q'), crossterm::event::KeyModifiers::NONE);
        assert!(modal.handle_key(&q_key));
        assert!(!modal.is_open());
    }

    #[test]
    fn test_help_modal_rendering() {
        let modal = HelpModal::default();
        let backend = TestBackend::new(80, 24);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                f.render_widget(modal, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut text = String::new();
        for y in 0..24 {
            for x in 0..80 {
                text.push_str(term_buf[(x, y)].symbol());
            }
        }

        assert!(text.contains("Keyboard Shortcuts"));
        assert!(text.contains("Directive Injection"));
        assert!(text.contains("Directive Editor"));
        assert!(text.contains("Cycle split layout"));
    }
}
