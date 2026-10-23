use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::Widget,
};

use crate::session::worker::{WorkerSession, WorkerState};
use crate::ui::theme::{colors, glyphs, Theme};

/// Visual alert badge types displayed on the status bar.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AlertBadge {
    /// Normal operation / idle ready.
    None,
    /// Worker completed its assigned task.
    WorkerFinished(String),
    /// Worker requires intervention or assistance.
    AssistanceNeeded(String),
    /// Custom status message.
    Custom(String, Style),
}

/// Sleek, Tokyo-Night styled status bar widget displaying active worker ID,
/// slot ID, PID, model, token status, and visual alert badges.
pub struct StatusBarWidget<'a> {
    worker_id: &'a str,
    slot_id: &'a str,
    pid: Option<u32>,
    model: &'a str,
    token_used: u64,
    token_total: u64,
    state: WorkerState,
    alert_badge: AlertBadge,
    split_mode: Option<&'a str>,
    custom_hint: Option<&'a str>,
}

impl<'a> StatusBarWidget<'a> {
    /// Create new status bar widget with mandatory worker metadata.
    pub fn new(worker_id: &'a str, slot_id: &'a str) -> Self {
        Self {
            worker_id,
            slot_id,
            pid: None,
            model: "claude-3-5-sonnet",
            token_used: 0,
            token_total: 200_000,
            state: WorkerState::Running,
            alert_badge: AlertBadge::None,
            split_mode: None,
            custom_hint: None,
        }
    }

    /// Construct status bar widget directly from a `WorkerSession`.
    pub fn from_session(session: &'a WorkerSession, model: &'a str) -> Self {
        let (used, total) = session.tokens();
        let state = session.state.lock().clone();
        let pid = session.pid();

        let alert_badge = if let Some(alarm) = session.last_alarm() {
            match alarm.alarm_type.as_str() {
                "IDLE" => AlertBadge::WorkerFinished(alarm.message),
                "HELP" => AlertBadge::AssistanceNeeded(alarm.message),
                _ => AlertBadge::Custom(alarm.message, Theme::status_bar_tokens()),
            }
        } else if matches!(state, WorkerState::Idle) {
            AlertBadge::WorkerFinished("Idle Prompt".to_string())
        } else {
            AlertBadge::None
        };

        Self {
            worker_id: &session.id,
            slot_id: &session.slot_id,
            pid,
            model,
            token_used: used,
            token_total: total,
            state,
            alert_badge,
            split_mode: None,
            custom_hint: None,
        }
    }

    /// Set PID.
    pub fn pid(mut self, pid: Option<u32>) -> Self {
        self.pid = pid;
        self
    }

    /// Set AI Model name.
    pub fn model(mut self, model: &'a str) -> Self {
        self.model = model;
        self
    }

    /// Set token usage (used, total).
    pub fn tokens(mut self, used: u64, total: u64) -> Self {
        self.token_used = used;
        self.token_total = total;
        self
    }

    /// Set operational state.
    pub fn state(mut self, state: WorkerState) -> Self {
        self.state = state;
        self
    }

    /// Set alert badge.
    pub fn alert_badge(mut self, badge: AlertBadge) -> Self {
        self.alert_badge = badge;
        self
    }

    /// Set split mode label (e.g. "SINGLE", "HORIZ", "VERT", "GRID").
    pub fn split_mode(mut self, mode: &'a str) -> Self {
        self.split_mode = Some(mode);
        self
    }

    /// Custom keyboard shortcut hint.
    pub fn custom_hint(mut self, hint: &'a str) -> Self {
        self.custom_hint = Some(hint);
        self
    }

    /// Helper to format tokens into a human-readable abbreviation (e.g. 18.5k).
    fn format_tokens(tokens: u64) -> String {
        if tokens >= 1_000_000 {
            format!("{:.1}M", tokens as f64 / 1_000_000.0)
        } else if tokens >= 1_000 {
            format!("{:.1}k", tokens as f64 / 1_000.0)
        } else {
            tokens.to_string()
        }
    }
}

impl<'a> Widget for StatusBarWidget<'a> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        if area.width == 0 || area.height == 0 {
            return;
        }

        // Fill background
        for x in area.left()..area.right() {
            let cell = &mut buf[(x, area.top())];
            cell.set_style(Theme::status_bar());
            cell.set_char(' ');
        }

        let mut left_spans: Vec<Span> = Vec::new();

        // 1. Worker & Slot Pill
        let state_icon = match self.state {
            WorkerState::Spawning => glyphs::IDLE,
            WorkerState::Running => glyphs::RUNNING,
            WorkerState::Idle => glyphs::IDLE,
            WorkerState::Interrupted => glyphs::INTERRUPTED,
            WorkerState::Exited(_) => glyphs::EXITED,
        };

        left_spans.push(Span::styled(
            format!(" {} {}:{} ", state_icon, self.worker_id, self.slot_id),
            Theme::status_bar_worker(),
        ));
        left_spans.push(Span::raw(" "));

        // 2. PID
        let pid_text = match self.pid {
            Some(p) => format!(" PID: {} ", p),
            None => " PID: -- ".to_string(),
        };
        left_spans.push(Span::styled(pid_text, Theme::status_bar_pid()));
        left_spans.push(Span::styled(format!(" {} ", glyphs::SEPARATOR), Style::default().fg(colors::FG_MUTED)));

        // 3. Model Identifier
        left_spans.push(Span::styled(
            format!(" 🤖 {} ", self.model),
            Theme::status_bar_model(),
        ));
        left_spans.push(Span::styled(format!(" {} ", glyphs::SEPARATOR), Style::default().fg(colors::FG_MUTED)));

        // 4. Token Usage Status
        let used_str = Self::format_tokens(self.token_used);
        let total_str = Self::format_tokens(self.token_total);
        let pct = if self.token_total > 0 {
            (self.token_used as f64 / self.token_total as f64) * 100.0
        } else {
            0.0
        };
        left_spans.push(Span::styled(
            format!(" 📊 Tokens: {}/{} ({:.1}%) ", used_str, total_str, pct),
            Theme::status_bar_tokens(),
        ));

        // 5. Visual Alert Badges (⚡ Worker Finished or 🚨 Assistance Needed)
        match &self.alert_badge {
            AlertBadge::WorkerFinished(msg) => {
                left_spans.push(Span::raw(" "));
                left_spans.push(Span::styled(
                    format!(" {} {} ", glyphs::BADGE_WORKER_FINISHED, msg.chars().take(20).collect::<String>()),
                    Theme::badge_worker_finished(),
                ));
            }
            AlertBadge::AssistanceNeeded(msg) => {
                left_spans.push(Span::raw(" "));
                left_spans.push(Span::styled(
                    format!(" {} {} ", glyphs::BADGE_ASSISTANCE_NEEDED, msg.chars().take(20).collect::<String>()),
                    Theme::badge_assistance_needed(),
                ));
            }
            AlertBadge::Custom(msg, style) => {
                left_spans.push(Span::raw(" "));
                left_spans.push(Span::styled(format!(" [{}] ", msg), *style));
            }
            AlertBadge::None => {}
        }

        // 6. Right side: Split Mode and Navigation Shortcuts
        let mut right_spans: Vec<Span> = Vec::new();
        if let Some(mode) = self.split_mode {
            right_spans.push(Span::styled(
                format!(" [SPLIT: {}] ", mode),
                Style::default().fg(colors::ACCENT_MAGENTA).add_modifier(Modifier::BOLD),
            ));
        }

        let hint = self
            .custom_hint
            .unwrap_or("Tab: Next Session │ Alt+S: Split │ ^C: Int │ ^Q: Quit");
        right_spans.push(Span::styled(
            format!(" {} ", hint),
            Style::default().fg(colors::FG_MUTED),
        ));

        let left_line = Line::from(left_spans);
        let left_len = left_line.width() as u16;

        // Render left side
        buf.set_line(area.x, area.y, &left_line, area.width);

        // Render right side if enough space
        let right_line = Line::from(right_spans);
        let right_len = right_line.width() as u16;
        if area.width > left_len + right_len + 2 {
            let right_x = area.x + area.width - right_len;
            buf.set_line(right_x, area.y, &right_line, right_len);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;

    #[test]
    fn test_status_bar_rendering_with_badges() {
        let backend = TestBackend::new(120, 1);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                let status_bar = StatusBarWidget::new("worker1", "agy2")
                    .pid(Some(9999))
                    .model("claude-3-5-sonnet")
                    .tokens(12500, 200000)
                    .alert_badge(AlertBadge::WorkerFinished("Build finished".into()))
                    .split_mode("HORIZ");

                f.render_widget(status_bar, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let content: String = (0..120).map(|x| term_buf[(x, 0)].symbol()).collect();
        assert!(content.contains("worker1:agy2"));
        assert!(content.contains("PID: 9999"));
        assert!(content.contains("claude-3-5-sonnet"));
        assert!(content.contains("Worker Finished"));
    }

    #[test]
    fn test_status_bar_alert_assistance_needed() {
        let backend = TestBackend::new(120, 1);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                let status_bar = StatusBarWidget::new("worker-dbg", "agy3")
                    .alert_badge(AlertBadge::AssistanceNeeded("Port blocked".into()));

                f.render_widget(status_bar, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let content: String = (0..120).map(|x| term_buf[(x, 0)].symbol()).collect();
        assert!(content.contains("Assistance Needed"));
    }
}
