use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::Widget,
};

use crate::session::AppMode;
use crate::ui::theme::Theme;

/// Tokyo Night colors specific to the multi-segment BottomBar.
mod bottom_colors {
    use ratatui::style::Color;

    pub const BG_BAR: Color = Color::Rgb(22, 22, 30);         // #16161e (Tokyo Night Night)
    pub const MODE_NORMAL_BG: Color = Color::Rgb(224, 175, 104); // #e0af68 (Warm Gold/Amber)
    pub const MODE_PTY_BG: Color = Color::Rgb(122, 162, 247);    // #7aa2f7 (Tokyo Night Blue)
    pub const MODE_TEXT_FG: Color = Color::Rgb(26, 27, 38);      // #1a1b26 (Tokyo Night Deep)
    pub const PILL_KEY_FG: Color = Color::Rgb(122, 162, 247);    // #7aa2f7 (Accent Blue)
    pub const PILL_LABEL_FG: Color = Color::Rgb(121, 130, 169);  // #7982a9 (Muted / Comment)
    pub const NOTICE_FG: Color = Color::Rgb(224, 175, 104);      // #e0af68 (Warm Gold)
    pub const ARCH_FG: Color = Color::Rgb(192, 202, 245);        // #c0caf5 (Tokyo Night Crisp)
}

/// Dynamic action pill representation in the bottom bar.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActionPill {
    pub key: String,
    pub label: String,
}

impl ActionPill {
    pub fn new(key: impl Into<String>, label: impl Into<String>) -> Self {
        Self {
            key: key.into(),
            label: label.into(),
        }
    }
}

/// Interactive multi-segment BottomBar widget (1-line dock-bottom layout)
/// matching Python `mind` `BottomBar`:
/// - 1. Left: Mode indicator `[ NORMAL MODE ]` vs `[ PTY INTERACT ]`
/// - 2. Center: Dynamic action pills (`[?] Help`, `[m] Directive`, `[s] Split`,
///              `[d] Edit`, `[c/n] New`, `[x] Close`, `[q] Quit`)
/// - 3. Right: Platform architecture badge `POSIX PTY · UTF-8` / `ConPTY · UTF-8`
#[derive(Debug, Clone)]
pub struct BottomBar {
    pub mode: AppMode,
    pub active_notice: Option<String>,
    pub pty_backend: String,
    pub theme: Theme,
}

impl Default for BottomBar {
    fn default() -> Self {
        let default_backend = if cfg!(windows) {
            "ConPTY"
        } else {
            "POSIX PTY"
        };
        Self::new(AppMode::Normal).pty_backend(default_backend)
    }
}

impl BottomBar {
    /// Create new BottomBar with specified application mode.
    pub fn new(mode: AppMode) -> Self {
        let default_backend = if cfg!(windows) {
            "ConPTY"
        } else {
            "POSIX PTY"
        };
        Self {
            mode,
            active_notice: None,
            pty_backend: default_backend.to_string(),
            theme: Theme::default(),
        }
    }

    /// Set mode.
    pub fn mode(mut self, mode: AppMode) -> Self {
        self.mode = mode;
        self
    }

    /// Set transient status notice or alert message.
    pub fn notice(mut self, notice: Option<String>) -> Self {
        self.active_notice = notice;
        self
    }

    /// Set PTY platform backend string (e.g. `POSIX PTY` or `ConPTY`).
    pub fn pty_backend(mut self, backend: impl Into<String>) -> Self {
        self.pty_backend = backend.into();
        self
    }

    /// Set theme.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.theme = theme;
        self
    }

    /// Build normal mode action pills matching Python `mind`:
    /// `[?] Help`, `[m] Directive`, `[s] Split`, `[d] Edit`, `[c/n] New`, `[x] Close`, `[q] Quit`
    pub fn normal_action_pills() -> Vec<ActionPill> {
        vec![
            ActionPill::new("?", "Help"),
            ActionPill::new("m", "Directive"),
            ActionPill::new("s", "Split"),
            ActionPill::new("d", "Edit"),
            ActionPill::new("c/n", "New"),
            ActionPill::new("x", "Close"),
            ActionPill::new("q", "Quit"),
            ActionPill::new("i", "Type"),
            ActionPill::new("1..9", "Jump"),
            ActionPill::new("h/l", "Tabs"),
            ActionPill::new("y", "Copy"),
        ]
    }

    /// Build PTY interact mode action pills matching Python `mind`:
    /// `[Esc Esc / Ctrl+B] Outer Normal`, `[Ctrl+C] Interrupt`, `[Ctrl+M] Inject`, `[Ctrl+D] Directive`, `[Ctrl+Shift+C] Copy`, `[?] Help`
    pub fn pty_action_pills() -> Vec<ActionPill> {
        vec![
            ActionPill::new("Esc Esc / Ctrl+B", "Outer Normal"),
            ActionPill::new("Ctrl+C", "Interrupt"),
            ActionPill::new("Ctrl+M", "Inject"),
            ActionPill::new("Ctrl+D", "Directive"),
            ActionPill::new("Ctrl+Shift+C", "Copy"),
            ActionPill::new("F12", "Normal"),
            ActionPill::new("?", "Help"),
        ]
    }
}

impl Widget for BottomBar {
    fn render(self, area: Rect, buf: &mut Buffer) {
        (&self).render(area, buf);
    }
}

impl Widget for &BottomBar {
    fn render(self, area: Rect, buf: &mut Buffer) {
        if area.width == 0 || area.height == 0 {
            return;
        }

        let bg_color = bottom_colors::BG_BAR;

        // Fill background row with #16161e
        for x in area.left()..area.right() {
            let cell = &mut buf[(x, area.top())];
            cell.set_style(Style::default().bg(bg_color).fg(bottom_colors::ARCH_FG));
            cell.set_char(' ');
        }

        let mut left_spans: Vec<Span> = Vec::new();

        // 1. Left Segment: Modal indicator badge
        match self.mode {
            AppMode::Normal => {
                left_spans.push(Span::styled(
                    " [ NORMAL MODE ] ",
                    Style::default()
                        .fg(bottom_colors::MODE_TEXT_FG)
                        .bg(bottom_colors::MODE_NORMAL_BG)
                        .add_modifier(Modifier::BOLD),
                ));
            }
            AppMode::PtyInteract => {
                left_spans.push(Span::styled(
                    " [ PTY INTERACT ] ",
                    Style::default()
                        .fg(bottom_colors::MODE_TEXT_FG)
                        .bg(bottom_colors::MODE_PTY_BG)
                        .add_modifier(Modifier::BOLD),
                ));
            }
        }
        left_spans.push(Span::styled(" ", Style::default().bg(bg_color)));

        // 2. Center Segment: Notice alert OR dynamic action pills
        if let Some(notice) = &self.active_notice {
            left_spans.push(Span::styled(
                format!(" ● {} ", notice),
                Style::default()
                    .fg(bottom_colors::NOTICE_FG)
                    .bg(bottom_colors::BG_BAR)
                    .add_modifier(Modifier::BOLD),
            ));
        } else {
            let pills = match self.mode {
                AppMode::Normal => BottomBar::normal_action_pills(),
                AppMode::PtyInteract => BottomBar::pty_action_pills(),
            };

            for pill in pills {
                left_spans.push(Span::styled(
                    format!("[{}] ", pill.key),
                    Style::default()
                        .fg(bottom_colors::PILL_KEY_FG)
                        .bg(bg_color)
                        .add_modifier(Modifier::BOLD),
                ));
                left_spans.push(Span::styled(
                    format!("{}  ", pill.label),
                    Style::default()
                        .fg(bottom_colors::PILL_LABEL_FG)
                        .bg(bg_color),
                ));
            }
        }

        // 3. Right Segment: PTY Platform & Encoding status pill
        let arch_str = format!("{} · UTF-8", self.pty_backend);
        let right_spans = vec![
            Span::styled(
                format!(" {} ", arch_str),
                Style::default()
                    .fg(bottom_colors::ARCH_FG)
                    .bg(Color::Rgb(36, 40, 59))
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(" ", Style::default().bg(bg_color)),
        ];

        let left_line = Line::from(left_spans);
        let right_line = Line::from(right_spans);
        let right_len = right_line.width() as u16;

        // 1. Render right side architecture badge on far right edge
        if area.width >= right_len {
            let right_x = area.x + area.width - right_len;
            buf.set_line(right_x, area.y, &right_line, right_len);
        }

        // 2. Render left side mode badge and action pills in remaining space
        let max_left = area.width.saturating_sub(right_len + 1);
        buf.set_line(area.x, area.y, &left_line, max_left);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;

    #[test]
    fn test_bottom_bar_normal_mode_action_pills() {
        let backend = TestBackend::new(140, 1);
        let mut terminal = Terminal::new(backend).unwrap();

        let bar = BottomBar::new(AppMode::Normal).pty_backend("POSIX PTY");

        terminal
            .draw(|f| {
                f.render_widget(&bar, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let content: String = (0..140).map(|x| term_buf[(x, 0)].symbol()).collect();

        assert!(content.contains("NORMAL MODE"), "Must contain mode indicator");
        assert!(content.contains("[?]"), "Must contain help pill");
        assert!(content.contains("[m]"), "Must contain directive pill");
        assert!(content.contains("[s]"), "Must contain split pill");
        assert!(content.contains("[d]"), "Must contain edit pill");
        assert!(content.contains("[c/n]"), "Must contain new pill");
        assert!(content.contains("[x]"), "Must contain close pill");
        assert!(content.contains("[q]"), "Must contain quit pill");
        assert!(content.contains("POSIX PTY · UTF-8"), "Must contain platform arch");
    }

    #[test]
    fn test_bottom_bar_pty_mode_action_pills() {
        let backend = TestBackend::new(160, 1);
        let mut terminal = Terminal::new(backend).unwrap();

        let bar = BottomBar::new(AppMode::PtyInteract).pty_backend("ConPTY");

        terminal
            .draw(|f| {
                f.render_widget(&bar, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let content: String = (0..160).map(|x| term_buf[(x, 0)].symbol()).collect();

        assert!(content.contains("PTY INTERACT"), "Must contain PTY mode indicator");
        assert!(content.contains("Esc Esc / Ctrl+B"), "Must contain outer normal exit pill");
        assert!(content.contains("Ctrl+C"), "Must contain interrupt pill");
        assert!(content.contains("ConPTY · UTF-8"), "Must contain ConPTY badge");
    }
}
