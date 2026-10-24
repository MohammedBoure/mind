use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::Widget,
};

use crate::session::AppMode;
use crate::ui::theme::{glyphs, Theme};

/// Tokyo Night colors specific to the Zellij-style top header bar.
mod bar_colors {
    use ratatui::style::Color;

    pub const BG_HEADER: Color = Color::Rgb(22, 22, 30);      // #16161e (Tokyo Night Night)
    pub const BRAND_LOGO: Color = Color::Rgb(122, 162, 247);   // #7aa2f7 (Bold Cyan/Blue)
    pub const SESSION_FG: Color = Color::Rgb(125, 207, 255);   // #7dcfff (Cyan)
    pub const SESSION_BG: Color = Color::Rgb(36, 40, 59);      // #24283b
    pub const WORKER_COUNT: Color = Color::Rgb(224, 175, 104); // #e0af68 (Warm Gold/Amber)
    pub const QUOTA_FILL: Color = Color::Rgb(158, 206, 106);   // #9ece6a (Green)
    pub const QUOTA_BG: Color = Color::Rgb(31, 35, 53);        // #1f2335
    pub const MCP_ACTIVE: Color = Color::Rgb(158, 206, 106);   // #9ece6a (Green)
    pub const MCP_INACTIVE: Color = Color::Rgb(86, 95, 137);   // #565f89
    pub const FG_MUTED: Color = Color::Rgb(86, 95, 137);       // #565f89
    pub const FG_LIGHT: Color = Color::Rgb(192, 202, 245);     // #c0caf5
}

/// Zellij-style streamlined top HeaderBar widget (1-line dock-top layout)
/// matching Python `mind` `HeaderBar` pixel-for-pixel:
/// - Brand Logo: `mind` (bold cyan `#7aa2f7`)
/// - Session Name: active session in `#7dcfff`
/// - Quota Pill: `[████████░░]` progress bar + percentage / remaining steps
/// - MCP Status: `● MCP: 8765` (green dot `#9ece6a`)
/// - Worker telemetry: `X active workers` in `#e0af68`
#[derive(Debug, Clone)]
pub struct HeaderBar {
    pub session_name: String,
    pub worker_count: usize,
    pub mode: AppMode,
    pub quota_percent: u8,
    pub quota_text_override: Option<String>,
    pub mcp_port: u16,
    pub mcp_active: bool,
    pub theme: Theme,
}

impl Default for HeaderBar {
    fn default() -> Self {
        Self::new("default")
    }
}

impl HeaderBar {
    /// Create a new HeaderBar with default session name.
    pub fn new(session_name: impl Into<String>) -> Self {
        Self {
            session_name: session_name.into(),
            worker_count: 2,
            mode: AppMode::Normal,
            quota_percent: 85,
            quota_text_override: None,
            mcp_port: 8765,
            mcp_active: true,
            theme: Theme::default(),
        }
    }

    /// Set session name.
    pub fn session_name(mut self, name: impl Into<String>) -> Self {
        self.session_name = name.into();
        self
    }

    /// Set active worker count telemetry.
    pub fn worker_count(mut self, count: usize) -> Self {
        self.worker_count = count;
        self
    }

    /// Set modal operation mode.
    pub fn mode(mut self, mode: AppMode) -> Self {
        self.mode = mode;
        self
    }

    /// Set quota percentage (0..=100).
    pub fn quota_percent(mut self, pct: u8) -> Self {
        self.quota_percent = pct.min(100);
        self
    }

    /// Set custom quota text (e.g. `"[████████░░] 85%"`).
    pub fn quota_text(mut self, text: impl Into<String>) -> Self {
        self.quota_text_override = Some(text.into());
        self
    }

    /// Set MCP server port.
    pub fn mcp_port(mut self, port: u16) -> Self {
        self.mcp_port = port;
        self
    }

    /// Set MCP active status indicator.
    pub fn mcp_active(mut self, active: bool) -> Self {
        self.mcp_active = active;
        self
    }

    /// Set active UI theme.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.theme = theme;
        self
    }

    /// Render quota progress bar string (e.g. `[████████░░] 80%`).
    pub fn render_quota_bar(percent: u8, width: usize) -> String {
        let total_blocks = width.max(4);
        let filled = (percent as usize * total_blocks) / 100;
        let empty = total_blocks.saturating_sub(filled);
        format!("[{}{}] {}%", "█".repeat(filled), "░".repeat(empty), percent)
    }
}

impl Widget for HeaderBar {
    fn render(self, area: Rect, buf: &mut Buffer) {
        (&self).render(area, buf);
    }
}

impl Widget for &HeaderBar {
    fn render(self, area: Rect, buf: &mut Buffer) {
        if area.width == 0 || area.height == 0 {
            return;
        }

        let bg_color = bar_colors::BG_HEADER;

        // Fill background row with #16161e
        for x in area.left()..area.right() {
            let cell = &mut buf[(x, area.top())];
            cell.set_style(Style::default().bg(bg_color).fg(bar_colors::FG_LIGHT));
            cell.set_char(' ');
        }

        // Left Segment: Brand Logo + Session Name + Mode Badge
        let mut left_spans: Vec<Span> = Vec::new();

        // 1. Brand Logo: "mind" (bold cyan/blue #7aa2f7)
        left_spans.push(Span::styled(" ", Style::default().bg(bg_color)));
        left_spans.push(Span::styled(
            "mind",
            Style::default()
                .fg(bar_colors::BRAND_LOGO)
                .bg(bg_color)
                .add_modifier(Modifier::BOLD),
        ));
        left_spans.push(Span::styled(" ", Style::default().bg(bg_color)));

        // 2. Active Session Pill: [dim/cyan session_name]
        left_spans.push(Span::styled(
            format!(" {} ", self.session_name),
            Style::default()
                .fg(bar_colors::SESSION_FG)
                .bg(bar_colors::SESSION_BG)
                .add_modifier(Modifier::BOLD),
        ));
        left_spans.push(Span::styled(" ", Style::default().bg(bg_color)));

        // 3. Modal Indicator Badge
        let mode_span = match self.mode {
            AppMode::Normal => Span::styled(
                " NORMAL ",
                Style::default()
                    .fg(Color::Black)
                    .bg(bar_colors::WORKER_COUNT)
                    .add_modifier(Modifier::BOLD),
            ),
            AppMode::PtyInteract => Span::styled(
                " PTY ",
                Style::default()
                    .fg(Color::Black)
                    .bg(bar_colors::BRAND_LOGO)
                    .add_modifier(Modifier::BOLD),
            ),
        };
        left_spans.push(mode_span);

        // Right Segment: Worker Count + Quota Pill + MCP Status
        let mut right_spans: Vec<Span> = Vec::new();

        // 4. Worker Telemetry: "[X active workers]"
        right_spans.push(Span::styled(
            format!(" {} ", self.worker_count),
            Style::default()
                .fg(bar_colors::WORKER_COUNT)
                .bg(bar_colors::SESSION_BG)
                .add_modifier(Modifier::BOLD),
        ));
        right_spans.push(Span::styled(
            "active workers ",
            Style::default().fg(bar_colors::FG_MUTED).bg(bg_color),
        ));

        // 5. Quota Pill: "[████████░░] 85%"
        let quota_bar_str = match &self.quota_text_override {
            Some(custom) => custom.clone(),
            None => HeaderBar::render_quota_bar(self.quota_percent, 10),
        };

        right_spans.push(Span::styled(
            "Quota: ",
            Style::default().fg(bar_colors::FG_MUTED).bg(bg_color),
        ));
        right_spans.push(Span::styled(
            format!(" {} ", quota_bar_str),
            Style::default()
                .fg(bar_colors::QUOTA_FILL)
                .bg(bar_colors::QUOTA_BG)
                .add_modifier(Modifier::BOLD),
        ));
        right_spans.push(Span::styled(" ", Style::default().bg(bg_color)));

        // 6. MCP Health Status Indicator: "● MCP: 8765"
        let mcp_dot_color = if self.mcp_active {
            bar_colors::MCP_ACTIVE
        } else {
            bar_colors::MCP_INACTIVE
        };

        right_spans.push(Span::styled(
            format!(" {} MCP: ", glyphs::RUNNING),
            Style::default()
                .fg(mcp_dot_color)
                .bg(bar_colors::QUOTA_BG)
                .add_modifier(Modifier::BOLD),
        ));
        right_spans.push(Span::styled(
            format!("{} ", self.mcp_port),
            Style::default()
                .fg(bar_colors::FG_LIGHT)
                .bg(bar_colors::QUOTA_BG),
        ));
        right_spans.push(Span::styled(" ", Style::default().bg(bg_color)));

        let left_line = Line::from(left_spans);
        let left_len = left_line.width() as u16;

        let right_line = Line::from(right_spans);
        let right_len = right_line.width() as u16;

        // Render left side
        buf.set_line(area.x, area.y, &left_line, area.width);

        // Render right side if space permits
        if area.width > left_len + right_len {
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
    fn test_header_bar_render_elements() {
        let backend = TestBackend::new(120, 1);
        let mut terminal = Terminal::new(backend).unwrap();

        let header = HeaderBar::new("test_session")
            .worker_count(3)
            .mode(AppMode::Normal)
            .quota_percent(80)
            .mcp_port(8765)
            .mcp_active(true);

        terminal
            .draw(|f| {
                f.render_widget(&header, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let content: String = (0..120).map(|x| term_buf[(x, 0)].symbol()).collect();

        assert!(content.contains("mind"), "Header must include 'mind' brand logo");
        assert!(content.contains("test_session"), "Header must display session name");
        assert!(content.contains("NORMAL"), "Header must display mode");
        assert!(content.contains("3"), "Header must display worker count");
        assert!(content.contains("active workers"), "Header must display telemetry text");
        assert!(content.contains("8765"), "Header must display MCP port");
        assert!(content.contains("Quota:"), "Header must display Quota label");
        assert!(content.contains("80%"), "Header must display quota percent");
    }

    #[test]
    fn test_quota_bar_generation() {
        let bar100 = HeaderBar::render_quota_bar(100, 10);
        assert_eq!(bar100, "[██████████] 100%");

        let bar50 = HeaderBar::render_quota_bar(50, 10);
        assert_eq!(bar50, "[█████░░░░░] 50%");

        let bar0 = HeaderBar::render_quota_bar(0, 10);
        assert_eq!(bar0, "[░░░░░░░░░░] 0%");
    }
}
