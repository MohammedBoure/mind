use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Style},
    widgets::{Block, Gauge, LineGauge, Widget},
};

use crate::ui::theme::colors;

/// Layout arrangement for quota gauges.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GaugeLayout {
    /// Gauges arranged side-by-side in horizontal columns.
    Horizontal,
    /// Gauges stacked vertically in rows (ideal for sidebar panels).
    Vertical,
}

/// Real-time progress gauges for quota consumption (hourly remaining,
/// weekly remaining, CPU and memory indicators).
pub struct QuotaGaugesWidget<'a> {
    hourly_remaining: f64, // 0.0 to 100.0
    weekly_remaining: f64, // 0.0 to 100.0
    cpu_usage: f64,        // 0.0 to 100.0
    memory_usage: f64,     // 0.0 to 100.0
    memory_mb: (u64, u64), // (used_mb, total_mb)
    layout: GaugeLayout,
    block: Option<Block<'a>>,
}

impl<'a> Default for QuotaGaugesWidget<'a> {
    fn default() -> Self {
        Self::new()
    }
}

impl<'a> QuotaGaugesWidget<'a> {
    /// Create new real-time gauges widget with sensible defaults.
    pub fn new() -> Self {
        Self {
            hourly_remaining: 85.0,
            weekly_remaining: 92.0,
            cpu_usage: 18.5,
            memory_usage: 34.0,
            memory_mb: (2780, 8192),
            layout: GaugeLayout::Horizontal,
            block: None,
        }
    }

    /// Set hourly quota remaining percentage (0.0 to 100.0).
    pub fn hourly_remaining(mut self, pct: f64) -> Self {
        self.hourly_remaining = pct.clamp(0.0, 100.0);
        self
    }

    /// Set weekly quota remaining percentage (0.0 to 100.0).
    pub fn weekly_remaining(mut self, pct: f64) -> Self {
        self.weekly_remaining = pct.clamp(0.0, 100.0);
        self
    }

    /// Set CPU utilization percentage (0.0 to 100.0).
    pub fn cpu_usage(mut self, pct: f64) -> Self {
        self.cpu_usage = pct.clamp(0.0, 100.0);
        self
    }

    /// Set Memory utilization metrics.
    pub fn memory(mut self, used_mb: u64, total_mb: u64) -> Self {
        self.memory_mb = (used_mb, total_mb);
        let pct = if total_mb > 0 {
            (used_mb as f64 / total_mb as f64) * 100.0
        } else {
            0.0
        };
        self.memory_usage = pct.clamp(0.0, 100.0);
        self
    }

    /// Set layout arrangement.
    pub fn layout(mut self, layout: GaugeLayout) -> Self {
        self.layout = layout;
        self
    }

    /// Attach container block/border.
    pub fn block(mut self, block: Block<'a>) -> Self {
        self.block = Some(block);
        self
    }

    /// Helper to pick color for quota remaining:
    /// High remaining (>50%) = Green, Moderate (20-50%) = Yellow, Low (<20%) = Red.
    fn quota_color(pct: f64) -> Color {
        if pct >= 50.0 {
            colors::ACCENT_GREEN
        } else if pct >= 20.0 {
            colors::ACCENT_YELLOW
        } else {
            colors::ACCENT_RED
        }
    }

    /// Helper for resource usage:
    /// Low usage (<60%) = Cyan/Teal, Moderate (60-85%) = Orange, High (>85%) = Red.
    fn usage_color(pct: f64) -> Color {
        if pct < 60.0 {
            colors::ACCENT_TEAL
        } else if pct < 85.0 {
            colors::ACCENT_ORANGE
        } else {
            colors::ACCENT_RED
        }
    }
}

impl<'a> Widget for QuotaGaugesWidget<'a> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let render_area = match self.block {
            Some(ref b) => {
                let inner = b.inner(area);
                b.clone().render(area, buf);
                inner
            }
            None => area,
        };

        if render_area.width < 10 || render_area.height == 0 {
            return;
        }

        match self.layout {
            GaugeLayout::Horizontal => {
                // Split horizontally into 4 column gauges
                let chunks = Layout::default()
                    .direction(Direction::Horizontal)
                    .constraints([
                        Constraint::Ratio(1, 4),
                        Constraint::Ratio(1, 4),
                        Constraint::Ratio(1, 4),
                        Constraint::Ratio(1, 4),
                    ])
                    .split(render_area);

                // 1. Hourly Remaining Gauge
                let h_color = Self::quota_color(self.hourly_remaining);
                let h_gauge = Gauge::default()
                    .block(Block::default().title(" Hourly Quota "))
                    .gauge_style(Style::default().fg(h_color).bg(colors::BG_DARK))
                    .percent(self.hourly_remaining.round() as u16)
                    .label(format!("{:.0}% Left", self.hourly_remaining));
                h_gauge.render(chunks[0], buf);

                // 2. Weekly Remaining Gauge
                let w_color = Self::quota_color(self.weekly_remaining);
                let w_gauge = Gauge::default()
                    .block(Block::default().title(" Weekly Quota "))
                    .gauge_style(Style::default().fg(w_color).bg(colors::BG_DARK))
                    .percent(self.weekly_remaining.round() as u16)
                    .label(format!("{:.0}% Left", self.weekly_remaining));
                w_gauge.render(chunks[1], buf);

                // 3. CPU Usage Gauge
                let c_color = Self::usage_color(self.cpu_usage);
                let c_gauge = Gauge::default()
                    .block(Block::default().title(" CPU Usage "))
                    .gauge_style(Style::default().fg(c_color).bg(colors::BG_DARK))
                    .percent(self.cpu_usage.round() as u16)
                    .label(format!("{:.1}%", self.cpu_usage));
                c_gauge.render(chunks[2], buf);

                // 4. Memory Usage Gauge
                let m_color = Self::usage_color(self.memory_usage);
                let (used_mb, total_mb) = self.memory_mb;
                let m_gauge = Gauge::default()
                    .block(Block::default().title(" Memory "))
                    .gauge_style(Style::default().fg(m_color).bg(colors::BG_DARK))
                    .percent(self.memory_usage.round() as u16)
                    .label(format!("{:.0}MB / {:.0}MB", used_mb, total_mb));
                m_gauge.render(chunks[3], buf);
            }
            GaugeLayout::Vertical => {
                // Stack vertically (e.g. for sidebar)
                let chunks = Layout::default()
                    .direction(Direction::Vertical)
                    .constraints([
                        Constraint::Length(1), // Hourly
                        Constraint::Length(1), // Weekly
                        Constraint::Length(1), // CPU
                        Constraint::Length(1), // Memory
                        Constraint::Min(0),
                    ])
                    .split(render_area);

                // Hourly Line Gauge
                let h_color = Self::quota_color(self.hourly_remaining);
                let h_gauge = LineGauge::default()
                    .block(Block::default().title(format!(" Hourly: {:.0}% ", self.hourly_remaining)))
                    .filled_style(Style::default().fg(h_color))
                    .unfilled_style(Style::default().fg(colors::BG_DARK))
                    .ratio(self.hourly_remaining / 100.0);
                h_gauge.render(chunks[0], buf);

                // Weekly Line Gauge
                let w_color = Self::quota_color(self.weekly_remaining);
                let w_gauge = LineGauge::default()
                    .block(Block::default().title(format!(" Weekly: {:.0}% ", self.weekly_remaining)))
                    .filled_style(Style::default().fg(w_color))
                    .unfilled_style(Style::default().fg(colors::BG_DARK))
                    .ratio(self.weekly_remaining / 100.0);
                w_gauge.render(chunks[1], buf);

                // CPU Line Gauge
                let c_color = Self::usage_color(self.cpu_usage);
                let c_gauge = LineGauge::default()
                    .block(Block::default().title(format!(" CPU: {:.1}% ", self.cpu_usage)))
                    .filled_style(Style::default().fg(c_color))
                    .unfilled_style(Style::default().fg(colors::BG_DARK))
                    .ratio(self.cpu_usage / 100.0);
                c_gauge.render(chunks[2], buf);

                // Memory Line Gauge
                let m_color = Self::usage_color(self.memory_usage);
                let m_gauge = LineGauge::default()
                    .block(Block::default().title(format!(" RAM: {:.1}% ", self.memory_usage)))
                    .filled_style(Style::default().fg(m_color))
                    .unfilled_style(Style::default().fg(colors::BG_DARK))
                    .ratio(self.memory_usage / 100.0);
                m_gauge.render(chunks[3], buf);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;

    #[test]
    fn test_horizontal_gauges_render() {
        let backend = TestBackend::new(100, 3);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                let widget = QuotaGaugesWidget::new()
                    .hourly_remaining(75.0)
                    .weekly_remaining(90.0)
                    .cpu_usage(45.0)
                    .memory(4096, 16384)
                    .layout(GaugeLayout::Horizontal);

                f.render_widget(widget, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut text = String::new();
        for y in 0..3 {
            for x in 0..100 {
                text.push_str(term_buf[(x, y)].symbol());
            }
        }
        assert!(text.contains("Hourly"));
        assert!(text.contains("Weekly"));
        assert!(text.contains("CPU"));
    }

    #[test]
    fn test_vertical_gauges_render() {
        let backend = TestBackend::new(40, 6);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                let widget = QuotaGaugesWidget::new()
                    .hourly_remaining(15.0) // critical
                    .weekly_remaining(88.0)
                    .layout(GaugeLayout::Vertical);

                f.render_widget(widget, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut text = String::new();
        for y in 0..6 {
            for x in 0..40 {
                text.push_str(term_buf[(x, y)].symbol());
            }
        }
        assert!(text.contains("Hourly: 15%"));
    }
}
