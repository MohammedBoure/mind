use ratatui::style::{Color, Modifier, Style};

/// Tokyo Night color palette constants.
pub mod colors {
    use super::Color;

    /// Primary background (Tokyo Night Night) #1a1b26
    pub const BG_DARK: Color = Color::Rgb(26, 27, 38);
    /// Secondary container surface #24283b
    pub const BG_SURFACE: Color = Color::Rgb(36, 40, 59);
    /// Highlight / selection surface #292e42
    pub const BG_HIGHLIGHT: Color = Color::Rgb(41, 46, 66);

    /// Crisp primary foreground text #c0caf5
    pub const FG_LIGHT: Color = Color::Rgb(192, 202, 245);
    /// Muted / disabled / comment foreground #565f89
    pub const FG_MUTED: Color = Color::Rgb(86, 95, 137);

    /// Tokyo Night Accent Blue #7aa2f7
    pub const ACCENT_BLUE: Color = Color::Rgb(122, 162, 247);
    /// Tokyo Night Accent Cyan #7dcfff
    pub const ACCENT_CYAN: Color = Color::Rgb(125, 207, 255);
    /// Tokyo Night Accent Green #9ece6a
    pub const ACCENT_GREEN: Color = Color::Rgb(158, 206, 106);
    /// Tokyo Night Accent Teal #73daca
    pub const ACCENT_TEAL: Color = Color::Rgb(115, 218, 202);
    /// Tokyo Night Accent Orange #ff9e64
    pub const ACCENT_ORANGE: Color = Color::Rgb(255, 158, 100);
    /// Tokyo Night Accent Yellow #e0af68
    pub const ACCENT_YELLOW: Color = Color::Rgb(224, 175, 104);
    /// Tokyo Night Accent Magenta #bb9af7
    pub const ACCENT_MAGENTA: Color = Color::Rgb(187, 154, 247);
    /// Tokyo Night Accent Red (Alert) #f7768e
    pub const ACCENT_RED: Color = Color::Rgb(247, 118, 142);
}

/// Standard glyphs and symbols across all UI widgets.
pub mod glyphs {
    pub const RUNNING: &str = "●";
    pub const IDLE: &str = "○";
    pub const FINISHED: &str = "⚡";
    pub const ALERT: &str = "🚨";
    pub const INTERRUPTED: &str = "⏸";
    pub const EXITED: &str = "⏹";
    pub const POINTER: &str = "▶";
    pub const SEPARATOR: &str = "│";
    pub const BULLET: &str = "·";
    pub const BADGE_WORKER_FINISHED: &str = "⚡ Worker Finished";
    pub const BADGE_ASSISTANCE_NEEDED: &str = "🚨 Assistance Needed";
    pub const BADGE_NORMAL: &str = "✓ Normal";
}

/// Pre-configured Tokyo Night styles for widgets.
pub struct Theme;

impl Theme {
    /// Active pane border style (glowing cyan / bold).
    pub fn active_border() -> Style {
        Style::default()
            .fg(colors::ACCENT_CYAN)
            .add_modifier(Modifier::BOLD)
    }

    /// Inactive pane border style (muted).
    pub fn inactive_border() -> Style {
        Style::default().fg(colors::FG_MUTED)
    }

    /// Pane title style for focused pane.
    pub fn active_title() -> Style {
        Style::default()
            .fg(colors::ACCENT_CYAN)
            .bg(colors::BG_SURFACE)
            .add_modifier(Modifier::BOLD)
    }

    /// Pane title style for inactive pane.
    pub fn inactive_title() -> Style {
        Style::default().fg(colors::FG_MUTED)
    }

    /// Status bar root background & foreground style.
    pub fn status_bar() -> Style {
        Style::default()
            .fg(colors::FG_LIGHT)
            .bg(colors::BG_SURFACE)
    }

    /// Status bar segment pill: Active worker / slot.
    pub fn status_bar_worker() -> Style {
        Style::default()
            .fg(colors::BG_DARK)
            .bg(colors::ACCENT_BLUE)
            .add_modifier(Modifier::BOLD)
    }

    /// Status bar segment: PID / Process info.
    pub fn status_bar_pid() -> Style {
        Style::default()
            .fg(colors::ACCENT_CYAN)
            .bg(colors::BG_SURFACE)
    }

    /// Status bar segment: AI Model indicator.
    pub fn status_bar_model() -> Style {
        Style::default()
            .fg(colors::ACCENT_MAGENTA)
            .bg(colors::BG_SURFACE)
            .add_modifier(Modifier::BOLD)
    }

    /// Status bar segment: Token status.
    pub fn status_bar_tokens() -> Style {
        Style::default()
            .fg(colors::ACCENT_TEAL)
            .bg(colors::BG_SURFACE)
    }

    /// Visual alert badge: Worker Finished (amber / yellow glow).
    pub fn badge_worker_finished() -> Style {
        Style::default()
            .fg(colors::BG_DARK)
            .bg(colors::ACCENT_YELLOW)
            .add_modifier(Modifier::BOLD)
    }

    /// Visual alert badge: Assistance Needed (critical red alert).
    pub fn badge_assistance_needed() -> Style {
        Style::default()
            .fg(Color::White)
            .bg(colors::ACCENT_RED)
            .add_modifier(Modifier::BOLD)
    }

    /// Default status badge when idle or healthy.
    pub fn badge_normal() -> Style {
        Style::default()
            .fg(colors::ACCENT_GREEN)
            .bg(colors::BG_SURFACE)
    }

    /// Selected list item style.
    pub fn list_selected() -> Style {
        Style::default()
            .fg(colors::ACCENT_CYAN)
            .bg(colors::BG_HIGHLIGHT)
            .add_modifier(Modifier::BOLD)
    }

    /// Normal list item style.
    pub fn list_normal() -> Style {
        Style::default().fg(colors::FG_LIGHT)
    }

    /// Gauge high-percentage (healthy / abundant) style.
    pub fn gauge_healthy() -> Style {
        Style::default().fg(colors::ACCENT_GREEN).bg(colors::BG_SURFACE)
    }

    /// Gauge medium-percentage (moderate) style.
    pub fn gauge_medium() -> Style {
        Style::default().fg(colors::ACCENT_YELLOW).bg(colors::BG_SURFACE)
    }

    /// Gauge low-percentage (critical quota) style.
    pub fn gauge_critical() -> Style {
        Style::default().fg(colors::ACCENT_RED).bg(colors::BG_SURFACE)
    }
}
