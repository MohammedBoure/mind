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

/// Accessible shortcuts help modal matching Python Mind Textual `HelpModal`:
/// - Vim-like Modal Architecture (Normal Mode vs PTY Mode)
/// - Mode Switching & Leader Controls (`Esc Esc`, `Ctrl+B`, `F12`)
/// - Normal Mode Navigation & Tab Controls (`1..9`, `h/l`, `c`, `x`, `s`, `Tab`)
/// - Inter-Agent & Directive Injection (`m`, `d`, `o`, `Ctrl+C`)
/// - Tokyo Night palette styling
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
        let modal_width = 82.min(area.width.saturating_sub(4));
        let modal_height = 24.min(area.height.saturating_sub(2));
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
                " Keyboard Shortcuts Reference — Mind Vim Modal Shortcuts (? / Esc / q to close) ",
                Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD),
            ));

        let inner = block.inner(modal_area);
        block.render(modal_area, buf);

        let sections = vec![
            ("VIM-LIKE MODAL ARCHITECTURE", vec![
                ShortcutEntry { key: "NORMAL Mode", description: "Vim Command mode (single-key shortcuts, no modifiers needed)" },
                ShortcutEntry { key: "PTY Mode", description: "Insert mode (raw keystrokes stream directly to agy.exe stdin)" },
            ]),
            ("MODE SWITCHING & LEADER CONTROLS", vec![
                ShortcutEntry { key: "i / Enter / a", description: "Enter PTY Insert mode from NORMAL mode" },
                ShortcutEntry { key: "Esc Esc / Ctrl+B", description: "Return to NORMAL mode from PTY (bare Esc passes to agy vim prompt)" },
                ShortcutEntry { key: "F12 / Ctrl+]", description: "Dedicated leader keys to return to NORMAL mode" },
            ]),
            ("SWARM NAVIGATION & TABS (NORMAL MODE)", vec![
                ShortcutEntry { key: "1..9", description: "Jump directly to Worker tab N" },
                ShortcutEntry { key: "h / l", description: "Switch to previous / next worker tab" },
                ShortcutEntry { key: "e / Ctrl+E", description: "Open Agent & Tab Settings (Assign agy slot per tab)" },
                ShortcutEntry { key: "r / Ctrl+R", description: "Restart active tab PTY with currently assigned agy slot" },
                ShortcutEntry { key: "c / n", description: "Spawn a new worker agent tab" },
                ShortcutEntry { key: "x", description: "Terminate and close active worker tab" },
                ShortcutEntry { key: "s", description: "Toggle split layout (Side-by-side 50/50 vs Fullscreen)" },
                ShortcutEntry { key: "Tab", description: "Toggle focus between Primary Coordinator & Worker PTY" },
            ]),
            ("DIRECTIVES & INSTRUCTIONS", vec![
                ShortcutEntry { key: "m / Ctrl+M", description: "Open Directive Injection Modal (NORMAL / Any mode)" },
                ShortcutEntry { key: "d / Ctrl+D", description: "Open In-App Directive Modal Editor (NORMAL / Any mode)" },
                ShortcutEntry { key: "o / Ctrl+O", description: "Open Directive in System Default Editor ($EDITOR)" },
                ShortcutEntry { key: "Ctrl+C", description: "Send immediate interrupt signal (SIGINT) to active Worker" },
            ]),
            ("CLIPBOARD & GENERAL", vec![
                ShortcutEntry { key: "y", description: "Yank / copy focused pane selection or terminal buffer" },
                ShortcutEntry { key: "Ctrl+Shift+C", description: "Copy selection or terminal buffer to OS clipboard" },
                ShortcutEntry { key: "?", description: "Toggle this help screen" },
                ShortcutEntry { key: "q", description: "Quit application and cleanly terminate worker processes" },
                ShortcutEntry { key: "Escape", description: "Close modal / return to workspace" },
            ]),
        ];

        let mut lines = Vec::new();

        for (section_title, entries) in sections {
            lines.push(Line::from(vec![
                Span::styled(
                    format!("  {}  ", section_title),
                    Style::default().fg(p.accent_magenta).add_modifier(Modifier::BOLD),
                ),
            ]));

            for entry in entries {
                lines.push(Line::from(vec![
                    Span::styled(format!("    {:<18}", entry.key), Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD)),
                    Span::styled(entry.description, Style::default().fg(p.fg_light)),
                ]));
            }
            lines.push(Line::from(""));
        }

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
        let backend = TestBackend::new(90, 26);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                f.render_widget(modal, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut content = String::new();
        for y in 0..26 {
            for x in 0..90 {
                content.push_str(term_buf[(x, y)].symbol());
            }
        }

        assert!(content.contains("Mind Vim Modal Shortcuts"));
        assert!(content.contains("NORMAL Mode"));
        assert!(content.contains("Esc Esc / Ctrl+B"));
        assert!(content.contains("F12"));
        assert!(content.contains("Directive"));
    }
}
