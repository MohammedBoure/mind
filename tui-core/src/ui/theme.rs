use ratatui::style::{Color, Modifier, Style};

/// Tokyo Night color palette constants for default styling.
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
    // Color-blind safe badges (explicit symbols)
    pub const BADGE_CB_FINISHED: &str = "[⚡] Worker Finished";
    pub const BADGE_CB_ASSISTANCE: &str = "[!] Assistance Needed";
    pub const BADGE_CB_NORMAL: &str = "[OK] Normal";
}

/// Accessible theme modes supported across the entire TUI suite.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ThemeMode {
    /// Sleek, immersive Tokyo Night palette (default).
    #[default]
    TokyoNight,
    /// High-contrast dark theme optimized for low-vision users on dark screens.
    HighContrastDark,
    /// High-contrast light theme for bright environments and daylight visibility.
    HighContrastLight,
    /// Universal color-blind accessible palette (Protanopia / Deuteranopia safe).
    ColorBlind,
}

impl ThemeMode {
    /// Cycle to the next theme mode.
    pub fn next(self) -> Self {
        match self {
            Self::TokyoNight => Self::HighContrastDark,
            Self::HighContrastDark => Self::HighContrastLight,
            Self::HighContrastLight => Self::ColorBlind,
            Self::ColorBlind => Self::TokyoNight,
        }
    }

    /// Human-readable label for status bars and header breadcrumbs.
    pub fn label(self) -> &'static str {
        match self {
            Self::TokyoNight => "Tokyo Night",
            Self::HighContrastDark => "High Contrast Dark",
            Self::HighContrastLight => "High Contrast Light",
            Self::ColorBlind => "Color-Blind Accessible",
        }
    }
}

/// Concrete color palette definitions for a theme mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ThemePalette {
    pub bg_dark: Color,
    pub bg_surface: Color,
    pub bg_highlight: Color,
    pub fg_light: Color,
    pub fg_muted: Color,
    pub accent_blue: Color,
    pub accent_cyan: Color,
    pub accent_green: Color,
    pub accent_teal: Color,
    pub accent_orange: Color,
    pub accent_yellow: Color,
    pub accent_magenta: Color,
    pub accent_red: Color,
    pub badge_normal_fg: Color,
    pub badge_normal_bg: Color,
    pub badge_finished_fg: Color,
    pub badge_finished_bg: Color,
    pub badge_alert_fg: Color,
    pub badge_alert_bg: Color,
}

impl ThemePalette {
    /// Generate palette for given mode.
    pub fn for_mode(mode: ThemeMode) -> Self {
        match mode {
            ThemeMode::TokyoNight => Self {
                bg_dark: colors::BG_DARK,
                bg_surface: colors::BG_SURFACE,
                bg_highlight: colors::BG_HIGHLIGHT,
                fg_light: colors::FG_LIGHT,
                fg_muted: colors::FG_MUTED,
                accent_blue: colors::ACCENT_BLUE,
                accent_cyan: colors::ACCENT_CYAN,
                accent_green: colors::ACCENT_GREEN,
                accent_teal: colors::ACCENT_TEAL,
                accent_orange: colors::ACCENT_ORANGE,
                accent_yellow: colors::ACCENT_YELLOW,
                accent_magenta: colors::ACCENT_MAGENTA,
                accent_red: colors::ACCENT_RED,
                badge_normal_fg: colors::ACCENT_GREEN,
                badge_normal_bg: colors::BG_SURFACE,
                badge_finished_fg: colors::BG_DARK,
                badge_finished_bg: colors::ACCENT_YELLOW,
                badge_alert_fg: Color::White,
                badge_alert_bg: colors::ACCENT_RED,
            },
            ThemeMode::HighContrastDark => Self {
                bg_dark: Color::Rgb(0, 0, 0),
                bg_surface: Color::Rgb(20, 20, 20),
                bg_highlight: Color::Rgb(45, 45, 45),
                fg_light: Color::Rgb(255, 255, 255),
                fg_muted: Color::Rgb(180, 180, 180),
                accent_blue: Color::Rgb(100, 180, 255),
                accent_cyan: Color::Rgb(0, 255, 255),
                accent_green: Color::Rgb(0, 255, 0),
                accent_teal: Color::Rgb(0, 255, 200),
                accent_orange: Color::Rgb(255, 165, 0),
                accent_yellow: Color::Rgb(255, 255, 0),
                accent_magenta: Color::Rgb(255, 128, 255),
                accent_red: Color::Rgb(255, 60, 60),
                badge_normal_fg: Color::Rgb(0, 255, 0),
                badge_normal_bg: Color::Rgb(20, 20, 20),
                badge_finished_fg: Color::Black,
                badge_finished_bg: Color::Rgb(255, 255, 0),
                badge_alert_fg: Color::White,
                badge_alert_bg: Color::Rgb(255, 0, 0),
            },
            ThemeMode::HighContrastLight => Self {
                bg_dark: Color::Rgb(255, 255, 255),
                bg_surface: Color::Rgb(240, 242, 245),
                bg_highlight: Color::Rgb(220, 226, 235),
                fg_light: Color::Rgb(15, 15, 20),
                fg_muted: Color::Rgb(80, 85, 95),
                accent_blue: Color::Rgb(0, 70, 200),
                accent_cyan: Color::Rgb(0, 120, 180),
                accent_green: Color::Rgb(0, 130, 20),
                accent_teal: Color::Rgb(0, 125, 125),
                accent_orange: Color::Rgb(210, 80, 0),
                accent_yellow: Color::Rgb(180, 115, 0),
                accent_magenta: Color::Rgb(140, 0, 170),
                accent_red: Color::Rgb(200, 0, 0),
                badge_normal_fg: Color::Rgb(0, 130, 20),
                badge_normal_bg: Color::Rgb(230, 245, 230),
                badge_finished_fg: Color::Black,
                badge_finished_bg: Color::Rgb(255, 215, 0),
                badge_alert_fg: Color::White,
                badge_alert_bg: Color::Rgb(200, 0, 0),
            },
            ThemeMode::ColorBlind => Self {
                // Okabe-Ito universal design palette safe for Protanopia, Deuteranopia, and Tritanopia
                bg_dark: Color::Rgb(18, 22, 30),
                bg_surface: Color::Rgb(28, 35, 48),
                bg_highlight: Color::Rgb(40, 50, 70),
                fg_light: Color::Rgb(240, 245, 255),
                fg_muted: Color::Rgb(140, 155, 175),
                accent_blue: Color::Rgb(0, 114, 178),     // Strong Blue
                accent_cyan: Color::Rgb(86, 180, 233),    // Sky Blue
                accent_green: Color::Rgb(86, 180, 233),   // Replaced with Sky Blue to prevent green confusion
                accent_teal: Color::Rgb(86, 180, 233),
                accent_orange: Color::Rgb(230, 159, 0),   // Orange
                accent_yellow: Color::Rgb(240, 228, 66),  // Yellow / Amber
                accent_magenta: Color::Rgb(204, 121, 167),// Reddish Purple
                accent_red: Color::Rgb(213, 94, 0),       // Vermilion
                badge_normal_fg: Color::Rgb(86, 180, 233),
                badge_normal_bg: Color::Rgb(28, 35, 48),
                badge_finished_fg: Color::Black,
                badge_finished_bg: Color::Rgb(240, 228, 66),
                badge_alert_fg: Color::White,
                badge_alert_bg: Color::Rgb(213, 94, 0),
            },
        }
    }

    /// Active pane border style.
    pub fn active_border(&self) -> Style {
        Style::default().fg(self.accent_cyan).add_modifier(Modifier::BOLD)
    }

    /// Inactive pane border style.
    pub fn inactive_border(&self) -> Style {
        Style::default().fg(self.fg_muted)
    }

    /// Pane title style for focused pane.
    pub fn active_title(&self) -> Style {
        Style::default()
            .fg(self.accent_cyan)
            .bg(self.bg_surface)
            .add_modifier(Modifier::BOLD)
    }

    /// Pane title style for inactive pane.
    pub fn inactive_title(&self) -> Style {
        Style::default().fg(self.fg_muted)
    }

    /// Status bar root background & foreground style.
    pub fn status_bar(&self) -> Style {
        Style::default().fg(self.fg_light).bg(self.bg_surface)
    }

    /// Status bar segment pill: Active worker / slot.
    pub fn status_bar_worker(&self) -> Style {
        Style::default()
            .fg(self.bg_dark)
            .bg(self.accent_blue)
            .add_modifier(Modifier::BOLD)
    }

    /// Status bar segment: PID / Process info.
    pub fn status_bar_pid(&self) -> Style {
        Style::default().fg(self.accent_cyan).bg(self.bg_surface)
    }

    /// Status bar segment: AI Model indicator.
    pub fn status_bar_model(&self) -> Style {
        Style::default()
            .fg(self.accent_magenta)
            .bg(self.bg_surface)
            .add_modifier(Modifier::BOLD)
    }

    /// Status bar segment: Token status.
    pub fn status_bar_tokens(&self) -> Style {
        Style::default().fg(self.accent_teal).bg(self.bg_surface)
    }

    /// Visual alert badge: Worker Finished.
    pub fn badge_worker_finished(&self) -> Style {
        Style::default()
            .fg(self.badge_finished_fg)
            .bg(self.badge_finished_bg)
            .add_modifier(Modifier::BOLD)
    }

    /// Visual alert badge: Assistance Needed.
    pub fn badge_assistance_needed(&self) -> Style {
        Style::default()
            .fg(self.badge_alert_fg)
            .bg(self.badge_alert_bg)
            .add_modifier(Modifier::BOLD)
    }

    /// Default status badge when idle or healthy.
    pub fn badge_normal(&self) -> Style {
        Style::default().fg(self.badge_normal_fg).bg(self.badge_normal_bg)
    }

    /// Selected list item style.
    pub fn list_selected(&self) -> Style {
        Style::default()
            .fg(self.accent_cyan)
            .bg(self.bg_highlight)
            .add_modifier(Modifier::BOLD)
    }

    /// Normal list item style.
    pub fn list_normal(&self) -> Style {
        Style::default().fg(self.fg_light)
    }

    /// Gauge high-percentage (healthy / abundant) style.
    pub fn gauge_healthy(&self) -> Style {
        Style::default().fg(self.accent_green).bg(self.bg_surface)
    }

    /// Gauge medium-percentage (moderate) style.
    pub fn gauge_medium(&self) -> Style {
        Style::default().fg(self.accent_yellow).bg(self.bg_surface)
    }

    /// Gauge low-percentage (critical quota) style.
    pub fn gauge_critical(&self) -> Style {
        Style::default().fg(self.accent_red).bg(self.bg_surface)
    }
}

/// Configurable and accessible theme manager for UI widgets.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Theme {
    pub mode: ThemeMode,
}

impl Default for Theme {
    fn default() -> Self {
        Self {
            mode: ThemeMode::TokyoNight,
        }
    }
}

impl Theme {
    /// Create new theme instance with specified mode.
    pub const fn new(mode: ThemeMode) -> Self {
        Self { mode }
    }

    /// Access the concrete color palette for this theme.
    pub fn palette(&self) -> ThemePalette {
        ThemePalette::for_mode(self.mode)
    }

    /// Instance style helpers forwarding to the palette:
    pub fn active_border_style(&self) -> Style {
        self.palette().active_border()
    }
    pub fn inactive_border_style(&self) -> Style {
        self.palette().inactive_border()
    }
    pub fn active_title_style(&self) -> Style {
        self.palette().active_title()
    }
    pub fn inactive_title_style(&self) -> Style {
        self.palette().inactive_title()
    }
    pub fn status_bar_style(&self) -> Style {
        self.palette().status_bar()
    }
    pub fn status_bar_worker_style(&self) -> Style {
        self.palette().status_bar_worker()
    }
    pub fn status_bar_pid_style(&self) -> Style {
        self.palette().status_bar_pid()
    }
    pub fn status_bar_model_style(&self) -> Style {
        self.palette().status_bar_model()
    }
    pub fn status_bar_tokens_style(&self) -> Style {
        self.palette().status_bar_tokens()
    }
    pub fn badge_worker_finished_style(&self) -> Style {
        self.palette().badge_worker_finished()
    }
    pub fn badge_assistance_needed_style(&self) -> Style {
        self.palette().badge_assistance_needed()
    }
    pub fn badge_normal_style(&self) -> Style {
        self.palette().badge_normal()
    }
    pub fn list_selected_style(&self) -> Style {
        self.palette().list_selected()
    }
    pub fn list_normal_style(&self) -> Style {
        self.palette().list_normal()
    }
    pub fn gauge_healthy_style(&self) -> Style {
        self.palette().gauge_healthy()
    }
    pub fn gauge_medium_style(&self) -> Style {
        self.palette().gauge_medium()
    }
    pub fn gauge_critical_style(&self) -> Style {
        self.palette().gauge_critical()
    }
}

// Backward-compatible static methods (Tokyo Night default)
impl Theme {
    pub fn active_border() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).active_border()
    }
    pub fn inactive_border() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).inactive_border()
    }
    pub fn active_title() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).active_title()
    }
    pub fn inactive_title() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).inactive_title()
    }
    pub fn status_bar() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).status_bar()
    }
    pub fn status_bar_worker() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).status_bar_worker()
    }
    pub fn status_bar_pid() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).status_bar_pid()
    }
    pub fn status_bar_model() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).status_bar_model()
    }
    pub fn status_bar_tokens() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).status_bar_tokens()
    }
    pub fn badge_worker_finished() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).badge_worker_finished()
    }
    pub fn badge_assistance_needed() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).badge_assistance_needed()
    }
    pub fn badge_normal() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).badge_normal()
    }
    pub fn list_selected() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).list_selected()
    }
    pub fn list_normal() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).list_normal()
    }
    pub fn gauge_healthy() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).gauge_healthy()
    }
    pub fn gauge_medium() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).gauge_medium()
    }
    pub fn gauge_critical() -> Style {
        ThemePalette::for_mode(ThemeMode::TokyoNight).gauge_critical()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_theme_mode_cycling() {
        let mut mode = ThemeMode::TokyoNight;
        mode = mode.next();
        assert_eq!(mode, ThemeMode::HighContrastDark);
        mode = mode.next();
        assert_eq!(mode, ThemeMode::HighContrastLight);
        mode = mode.next();
        assert_eq!(mode, ThemeMode::ColorBlind);
        mode = mode.next();
        assert_eq!(mode, ThemeMode::TokyoNight);
    }

    #[test]
    fn test_theme_palettes_distinct() {
        let tokyo = Theme::new(ThemeMode::TokyoNight).palette();
        let hc_dark = Theme::new(ThemeMode::HighContrastDark).palette();
        let hc_light = Theme::new(ThemeMode::HighContrastLight).palette();
        let cb = Theme::new(ThemeMode::ColorBlind).palette();

        assert_ne!(tokyo.bg_dark, hc_dark.bg_dark);
        assert_ne!(hc_dark.bg_dark, hc_light.bg_dark);
        assert_ne!(tokyo.accent_green, cb.accent_green);
    }
}
