use std::sync::Arc;
use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, List, ListItem, ListState, StatefulWidget, Widget},
};

use crate::session::worker::{WorkerSession, WorkerState};
use crate::ui::theme::{glyphs, Theme};

/// Item representation for a worker entry in the dynamic list.
#[derive(Debug, Clone)]
pub struct WorkerListItem {
    pub id: String,
    pub slot_id: String,
    pub pid: Option<u32>,
    pub state: WorkerState,
    pub task: Option<String>,
    pub has_finished_alarm: bool,
    pub has_help_alarm: bool,
}

impl From<&WorkerSession> for WorkerListItem {
    fn from(s: &WorkerSession) -> Self {
        let (has_finished, has_help) = if let Some(alarm) = s.last_alarm() {
            (alarm.alarm_type == "IDLE", alarm.alarm_type == "HELP")
        } else {
            (false, false)
        };

        Self {
            id: s.id.clone(),
            slot_id: s.slot_id.clone(),
            pid: s.pid(),
            state: s.state.lock().clone(),
            task: s.task.lock().clone(),
            has_finished_alarm: has_finished,
            has_help_alarm: has_help,
        }
    }
}

/// Dynamic, navigable worker session list widget with status icons and indicators.
pub struct WorkerListWidget<'a> {
    items: Vec<WorkerListItem>,
    selected_index: Option<usize>,
    block: Option<Block<'a>>,
    highlight_style: Style,
    theme: Theme,
}

impl<'a> WorkerListWidget<'a> {
    /// Create new worker list from raw items.
    pub fn new(items: Vec<WorkerListItem>) -> Self {
        let theme = Theme::default();
        Self {
            items,
            selected_index: None,
            block: None,
            highlight_style: theme.list_selected_style(),
            theme,
        }
    }

    /// Construct worker list directly from active worker sessions.
    pub fn from_sessions(sessions: &[Arc<WorkerSession>], selected_index: Option<usize>) -> Self {
        let items: Vec<WorkerListItem> = sessions.iter().map(|s| WorkerListItem::from(s.as_ref())).collect();
        let theme = Theme::default();
        Self {
            items,
            selected_index,
            block: None,
            highlight_style: theme.list_selected_style(),
            theme,
        }
    }

    /// Set active theme for colors and highlights.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.highlight_style = theme.list_selected_style();
        self.theme = theme;
        self
    }

    /// Attach container block/border.
    pub fn block(mut self, block: Block<'a>) -> Self {
        self.block = Some(block);
        self
    }

    /// Set custom selection highlight style.
    pub fn highlight_style(mut self, style: Style) -> Self {
        self.highlight_style = style;
        self
    }

    /// Build internal `ListItem`s with accessible icons, colors, and badges.
    fn build_list_items(&self) -> Vec<ListItem<'a>> {
        let p = self.theme.palette();
        self.items
            .iter()
            .enumerate()
            .map(|(idx, item)| {
                let is_selected = self.selected_index == Some(idx);
                let mut spans = Vec::new();

                // 1. Selector pointer
                if is_selected {
                    spans.push(Span::styled(
                        format!("{} ", glyphs::POINTER),
                        Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD),
                    ));
                } else {
                    spans.push(Span::raw("  "));
                }

                // 2. Status icon
                let (icon, icon_style) = if item.has_help_alarm {
                    (glyphs::ALERT, Style::default().fg(p.accent_red).add_modifier(Modifier::BOLD))
                } else if item.has_finished_alarm {
                    (glyphs::FINISHED, Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD))
                } else {
                    match item.state {
                        WorkerState::Spawning => (glyphs::IDLE, Style::default().fg(p.accent_blue)),
                        WorkerState::Running => (glyphs::RUNNING, Style::default().fg(p.accent_green)),
                        WorkerState::Idle => (glyphs::IDLE, Style::default().fg(p.fg_muted)),
                        WorkerState::Interrupted => (glyphs::INTERRUPTED, Style::default().fg(p.accent_orange)),
                        WorkerState::Exited(_) => (glyphs::EXITED, Style::default().fg(p.fg_muted)),
                    }
                };

                spans.push(Span::styled(format!("{} ", icon), icon_style));

                // 3. Worker ID & Slot ID
                let name_style = if is_selected {
                    Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(p.fg_light)
                };
                spans.push(Span::styled(format!("{}:{} ", item.id, item.slot_id), name_style));

                // 4. PID badge
                if let Some(pid) = item.pid {
                    spans.push(Span::styled(
                        format!("({}) ", pid),
                        Style::default().fg(p.fg_muted),
                    ));
                }

                // 5. Task snippet or alert badge
                if item.has_help_alarm {
                    let badge = if self.theme.mode == crate::ui::theme::ThemeMode::ColorBlind {
                        "[!] NEED HELP"
                    } else {
                        "[🚨 NEED HELP]"
                    };
                    spans.push(Span::styled(
                        badge,
                        Style::default().fg(p.accent_red).add_modifier(Modifier::BOLD),
                    ));
                } else if item.has_finished_alarm {
                    let badge = if self.theme.mode == crate::ui::theme::ThemeMode::ColorBlind {
                        "[⚡] DONE"
                    } else {
                        "[⚡ DONE]"
                    };
                    spans.push(Span::styled(
                        badge,
                        Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD),
                    ));
                } else if let Some(ref t) = item.task {
                    let preview: String = t.chars().take(22).collect();
                    spans.push(Span::styled(
                        format!("\"{}\"", preview),
                        Style::default().fg(p.accent_teal),
                    ));
                }

                let line = Line::from(spans);
                let item_style = if is_selected {
                    self.highlight_style
                } else {
                    self.theme.list_normal_style()
                };

                ListItem::new(line).style(item_style)
            })
            .collect()
    }
}

impl<'a> Widget for WorkerListWidget<'a> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let list_items = self.build_list_items();
        let mut list = List::new(list_items);

        if let Some(block) = self.block {
            list = list.block(block);
        }

        Widget::render(list, area, buf);
    }
}

impl<'a> StatefulWidget for WorkerListWidget<'a> {
    type State = ListState;

    fn render(self, area: Rect, buf: &mut Buffer, state: &mut Self::State) {
        let list_items = self.build_list_items();
        let mut list = List::new(list_items).highlight_style(self.highlight_style);

        if let Some(block) = self.block {
            list = list.block(block);
        }

        StatefulWidget::render(list, area, buf, state);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;
    use ratatui::widgets::Borders;
    use ratatui::Terminal;

    #[test]
    fn test_worker_list_widget_render() {
        let items = vec![
            WorkerListItem {
                id: "coordinator".to_string(),
                slot_id: "agy1".to_string(),
                pid: Some(101),
                state: WorkerState::Running,
                task: Some("Managing build swarm".to_string()),
                has_finished_alarm: false,
                has_help_alarm: false,
            },
            WorkerListItem {
                id: "worker-bench".to_string(),
                slot_id: "agy2".to_string(),
                pid: Some(102),
                state: WorkerState::Idle,
                task: None,
                has_finished_alarm: true,
                has_help_alarm: false,
            },
        ];

        let backend = TestBackend::new(60, 4);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                let widget = WorkerListWidget::new(items)
                    .block(Block::default().borders(Borders::ALL).title(" Workers "));
                f.render_widget(widget, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut content = String::new();
        for y in 0..4 {
            for x in 0..60 {
                content.push_str(term_buf[(x, y)].symbol());
            }
            content.push('\n');
        }
        assert!(content.contains("coordinator:agy1"));
        assert!(content.contains("worker-bench:agy2"));
        assert!(content.contains("DONE"));
    }
}
