use crossterm::event::{KeyCode, KeyEvent};
use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Widget},
};

use crate::session::identity::{AgentSlot, IdentityDiscovery};
use crate::ui::theme::{glyphs, Theme};

/// Resulting action from user interaction with the new worker modal.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NewWorkerModalAction {
    /// Spawn a new worker session linked to the chosen agent slot.
    Spawn(AgentSlot),
    /// Cancel and close modal without spawning.
    Cancel,
    /// Key handled internally without closing.
    None,
}

/// Modal listing available host agent slots for dynamic provisioning.
#[derive(Debug, Clone)]
pub struct NewWorkerModal {
    pub slots: Vec<AgentSlot>,
    pub selected_index: usize,
    pub is_open: bool,
    pub theme: Theme,
}

impl Default for NewWorkerModal {
    fn default() -> Self {
        Self::new(IdentityDiscovery::discover_slots())
    }
}

impl NewWorkerModal {
    /// Initialize with discovered slots.
    pub fn new(slots: Vec<AgentSlot>) -> Self {
        Self {
            slots,
            selected_index: 0,
            is_open: true,
            theme: Theme::default(),
        }
    }

    /// Refresh slot list from disk.
    pub fn refresh_slots(&mut self) {
        self.slots = IdentityDiscovery::discover_slots();
        if self.selected_index >= self.slots.len() && !self.slots.is_empty() {
            self.selected_index = self.slots.len() - 1;
        }
    }

    /// Open modal and reset selection.
    pub fn open(&mut self) {
        self.refresh_slots();
        self.selected_index = 0;
        self.is_open = true;
    }

    /// Close modal.
    pub fn close(&mut self) {
        self.is_open = false;
    }

    /// Handle keyboard navigation.
    pub fn handle_key(&mut self, key: &KeyEvent) -> NewWorkerModalAction {
        if !self.is_open {
            return NewWorkerModalAction::None;
        }

        match key.code {
            KeyCode::Esc | KeyCode::Char('q') => {
                self.close();
                NewWorkerModalAction::Cancel
            }
            KeyCode::Enter => {
                if let Some(slot) = self.slots.get(self.selected_index) {
                    let chosen = slot.clone();
                    self.close();
                    NewWorkerModalAction::Spawn(chosen)
                } else {
                    self.close();
                    NewWorkerModalAction::Cancel
                }
            }
            KeyCode::Up | KeyCode::Char('k') => {
                if self.selected_index > 0 {
                    self.selected_index -= 1;
                }
                NewWorkerModalAction::None
            }
            KeyCode::Down | KeyCode::Char('j') => {
                if !self.slots.is_empty() && self.selected_index + 1 < self.slots.len() {
                    self.selected_index += 1;
                }
                NewWorkerModalAction::None
            }
            _ => NewWorkerModalAction::None,
        }
    }

    /// Set theme.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.theme = theme;
        self
    }
}

impl Widget for NewWorkerModal {
    fn render(self, area: Rect, buf: &mut Buffer) {
        (&self).render(area, buf);
    }
}

impl Widget for &NewWorkerModal {
    fn render(self, area: Rect, buf: &mut Buffer) {
        if !self.is_open || area.width < 35 || area.height < 8 {
            return;
        }

        let p = self.theme.palette();

        // Geometry
        let modal_width = 80.min(area.width.saturating_sub(4));
        let modal_height = 18.min(area.height.saturating_sub(2));
        let x = area.x + (area.width.saturating_sub(modal_width)) / 2;
        let y = area.y + (area.height.saturating_sub(modal_height)) / 2;
        let modal_area = Rect::new(x, y, modal_width, modal_height);

        Clear.render(modal_area, buf);

        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD))
            .style(Style::default().bg(p.bg_surface))
            .title(Span::styled(
                " Provision New Agent Worker Slot (Enter to spawn, Esc to cancel) ",
                Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD),
            ));

        let inner = block.inner(modal_area);
        block.render(modal_area, buf);

        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(1), // Table Header
                Constraint::Min(4),    // Slot list
                Constraint::Length(1), // Footer
            ])
            .split(inner);

        // 1. Table Header
        let header_line = Line::from(vec![
            Span::styled("   ", Style::default()),
            Span::styled(format!("{:<10}", "SLOT"), Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)),
            Span::styled(format!("{:<26}", "ROLE"), Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)),
            Span::styled(format!("{:<22}", "MODEL"), Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)),
            Span::styled("STATUS", Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)),
        ]);
        buf.set_line(chunks[0].x, chunks[0].y, &header_line, chunks[0].width);

        // 2. Slot rows
        let view_height = chunks[1].height as usize;
        let start_idx = if self.selected_index >= view_height {
            self.selected_index - view_height + 1
        } else {
            0
        };

        if self.slots.is_empty() {
            let empty_line = Line::from(vec![
                Span::styled("  No host agent slots discovered under ~/.local/share/agy-instances/", Style::default().fg(p.fg_muted).add_modifier(Modifier::ITALIC)),
            ]);
            buf.set_line(chunks[1].x, chunks[1].y, &empty_line, chunks[1].width);
        } else {
            for (idx, slot) in self.slots.iter().skip(start_idx).take(view_height).enumerate() {
                let actual_idx = start_idx + idx;
                let is_selected = actual_idx == self.selected_index;
                let current_y = chunks[1].y + idx as u16;

                let row_bg = if is_selected { p.bg_highlight } else { p.bg_surface };

                // Fill background
                for x in chunks[1].left()..chunks[1].right() {
                    let cell = &mut buf[(x, current_y)];
                    cell.set_style(Style::default().bg(row_bg));
                    cell.set_char(' ');
                }

                let pointer = if is_selected {
                    Span::styled(format!(" {} ", glyphs::POINTER), Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD))
                } else {
                    Span::raw("   ")
                };

                let slot_str = format!("agy{}", slot.slot_id);
                let role_snippet = if slot.role.len() > 24 {
                    format!("{}...", &slot.role[..21])
                } else {
                    slot.role.clone()
                };

                let model_snippet = if slot.model.len() > 20 {
                    format!("{}...", &slot.model[..17])
                } else {
                    slot.model.clone()
                };

                let status_span = if slot.has_token {
                    Span::styled("✓ READY", Style::default().fg(p.accent_green).add_modifier(Modifier::BOLD))
                } else {
                    Span::styled("● ACTIVE", Style::default().fg(p.accent_teal))
                };

                let name_style = if is_selected {
                    Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(p.fg_light)
                };

                let row_line = Line::from(vec![
                    pointer,
                    Span::styled(format!("{:<10}", slot_str), name_style),
                    Span::styled(format!("{:<26}", role_snippet), Style::default().fg(p.fg_light)),
                    Span::styled(format!("{:<22}", model_snippet), Style::default().fg(p.accent_magenta)),
                    status_span,
                ]);

                buf.set_line(chunks[1].x, current_y, &row_line, chunks[1].width);
            }
        }

        // 3. Footer hints
        let footer_line = Line::from(vec![
            Span::styled("  [Enter] Spawn Selected Slot  │  [↑/↓] Navigate  │  [Esc] Cancel", Style::default().fg(p.fg_muted)),
        ]);
        buf.set_line(chunks[2].x, chunks[2].y, &footer_line, chunks[2].width);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;
    use std::path::PathBuf;

    #[test]
    fn test_new_worker_modal_navigation_and_selection() {
        let slots = vec![
            AgentSlot::new(1, "agy1", PathBuf::from("/tmp/agy1"), "Lead Orchestrator", "gemini-3.8-flash-high", None, true, None),
            AgentSlot::new(11, "agy11", PathBuf::from("/tmp/agy11"), "Backend Specialist", "gemini-3.8-flash-high", None, true, None),
            AgentSlot::new(51, "agy51", PathBuf::from("/tmp/agy51"), "Frontend Engineer", "gemini-3.8-flash-high", None, true, None),
        ];

        let mut modal = NewWorkerModal::new(slots);
        assert_eq!(modal.selected_index, 0);

        // Down
        let down = KeyEvent::new(KeyCode::Down, crossterm::event::KeyModifiers::NONE);
        modal.handle_key(&down);
        assert_eq!(modal.selected_index, 1);

        modal.handle_key(&down);
        assert_eq!(modal.selected_index, 2);

        // Enter to select agy51
        let enter = KeyEvent::new(KeyCode::Enter, crossterm::event::KeyModifiers::NONE);
        let action = modal.handle_key(&enter);
        match action {
            NewWorkerModalAction::Spawn(slot) => {
                assert_eq!(slot.slot_id, 51);
                assert_eq!(slot.role, "Frontend Engineer");
            }
            _ => panic!("Expected Spawn action"),
        }
    }

    #[test]
    fn test_new_worker_modal_render() {
        let slots = vec![
            AgentSlot::new(11, "agy11", PathBuf::from("/tmp/agy11"), "Backend Specialist", "gemini-3.8-flash-high", None, true, None),
        ];

        let modal = NewWorkerModal::new(slots);
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

        assert!(text.contains("Provision New Agent Worker Slot"));
        assert!(text.contains("agy11"));
        assert!(text.contains("Backend Specialist"));
    }
}
