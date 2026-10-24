use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Widget},
};

use crate::session::identity::{AgentSlot, IdentityDiscovery};
use crate::ui::theme::{glyphs, Theme};

/// Tokyo Night colors for SelectWorkerModal.
mod modal_colors {
    use ratatui::style::Color;

    pub const TITLE_CYAN: Color = Color::Rgb(122, 162, 247);      // #7aa2f7
    pub const ACCENT_CYAN: Color = Color::Rgb(125, 207, 255);     // #7dcfff
    pub const ACCENT_GREEN: Color = Color::Rgb(158, 206, 106);    // #9ece6a
    pub const ACCENT_YELLOW: Color = Color::Rgb(224, 175, 104);   // #e0af68
    pub const ACCENT_MAGENTA: Color = Color::Rgb(187, 154, 247);  // #bb9af7
    pub const FG_LIGHT: Color = Color::Rgb(192, 202, 245);        // #c0caf5
    pub const FG_MUTED: Color = Color::Rgb(86, 95, 137);          // #565f89
    pub const BG_SURFACE: Color = Color::Rgb(36, 40, 59);         // #24283b
    pub const BG_HIGHLIGHT: Color = Color::Rgb(41, 46, 66);       // #292e42
}

/// Resulting action from user interaction with SelectWorkerModal.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SelectWorkerModalAction {
    /// User selected a slot to spawn / assign.
    Spawn(AgentSlot),
    /// Cancel and close modal without selection.
    Cancel,
    /// Key handled internally without closing.
    None,
}

/// Modal dialog for selecting an agy instance slot (1..200) with interactive search filter
/// matching Python `mind` `SelectWorkerModal`:
/// - Filter search input (`Filter agy instances (e.g. agy11, email)...`)
/// - Up/Down/j/k navigation
/// - Live filtering by slot id, role, model, or email
/// - Enter to select / spawn, Esc to cancel
#[derive(Debug, Clone)]
pub struct SelectWorkerModal {
    pub slots: Vec<AgentSlot>,
    pub filter_query: String,
    pub selected_index: usize,
    pub is_open: bool,
    pub theme: Theme,
}

impl Default for SelectWorkerModal {
    fn default() -> Self {
        Self::new(IdentityDiscovery::discover_slots())
    }
}

impl SelectWorkerModal {
    /// Initialize with list of discovered agent slots.
    pub fn new(slots: Vec<AgentSlot>) -> Self {
        Self {
            slots,
            filter_query: String::new(),
            selected_index: 0,
            is_open: true,
            theme: Theme::default(),
        }
    }

    /// Refresh slots list from disk.
    pub fn refresh_slots(&mut self) {
        self.slots = IdentityDiscovery::discover_slots();
        self.clamp_selection();
    }

    /// Open or reset modal.
    pub fn open(&mut self) {
        self.refresh_slots();
        self.filter_query.clear();
        self.selected_index = 0;
        self.is_open = true;
    }

    /// Close modal.
    pub fn close(&mut self) {
        self.is_open = false;
    }

    /// Get list of slots matching current filter query.
    pub fn filtered_slots(&self) -> Vec<&AgentSlot> {
        let q = self.filter_query.trim().to_lowercase();
        if q.is_empty() {
            return self.slots.iter().collect();
        }

        self.slots
            .iter()
            .filter(|s| {
                let slot_str = format!("agy{}", s.slot_id).to_lowercase();
                let name_match = s.name.to_lowercase().contains(&q);
                let slot_match = slot_str.contains(&q);
                let role_match = s.role.to_lowercase().contains(&q);
                let model_match = s.model.to_lowercase().contains(&q);
                let email_match = s.email.as_ref().map(|e| e.to_lowercase().contains(&q)).unwrap_or(false);

                name_match || slot_match || role_match || model_match || email_match
            })
            .collect()
    }

    /// Ensure selected index stays within filtered slot bounds.
    fn clamp_selection(&mut self) {
        let count = self.filtered_slots().len();
        if count == 0 {
            self.selected_index = 0;
        } else if self.selected_index >= count {
            self.selected_index = count - 1;
        }
    }

    /// Handle keyboard navigation and interactive search filter typing.
    pub fn handle_key(&mut self, key: &KeyEvent) -> SelectWorkerModalAction {
        if !self.is_open {
            return SelectWorkerModalAction::None;
        }

        // Cancel / Dismiss on Esc
        if key.code == KeyCode::Esc {
            self.close();
            return SelectWorkerModalAction::Cancel;
        }

        // Confirm Selection on Enter
        if key.code == KeyCode::Enter {
            let filtered = self.filtered_slots();
            if let Some(slot) = filtered.get(self.selected_index) {
                let chosen = (*slot).clone();
                self.close();
                return SelectWorkerModalAction::Spawn(chosen);
            } else {
                self.close();
                return SelectWorkerModalAction::Cancel;
            }
        }

        // Navigation Up (Up arrow or Alt+k / Ctrl+p)
        if key.code == KeyCode::Up
            || (key.code == KeyCode::Char('p') && key.modifiers.contains(KeyModifiers::CONTROL))
        {
            if self.selected_index > 0 {
                self.selected_index -= 1;
            }
            return SelectWorkerModalAction::None;
        }

        // Navigation Down (Down arrow or Alt+j / Ctrl+n)
        if key.code == KeyCode::Down
            || (key.code == KeyCode::Char('n') && key.modifiers.contains(KeyModifiers::CONTROL))
        {
            let count = self.filtered_slots().len();
            if count > 0 && self.selected_index + 1 < count {
                self.selected_index += 1;
            }
            return SelectWorkerModalAction::None;
        }

        // 'j' and 'k' without modifiers: only navigate if not typing or if filter input handled
        if key.modifiers.is_empty() {
            if key.code == KeyCode::Char('k') && self.filter_query.is_empty() {
                if self.selected_index > 0 {
                    self.selected_index -= 1;
                }
                return SelectWorkerModalAction::None;
            }
            if key.code == KeyCode::Char('j') && self.filter_query.is_empty() {
                let count = self.filtered_slots().len();
                if count > 0 && self.selected_index + 1 < count {
                    self.selected_index += 1;
                }
                return SelectWorkerModalAction::None;
            }
        }

        // Text editing for search filter input
        match key.code {
            KeyCode::Backspace => {
                self.filter_query.pop();
                self.clamp_selection();
                SelectWorkerModalAction::None
            }
            KeyCode::Char(c) if !key.modifiers.contains(KeyModifiers::CONTROL) && !key.modifiers.contains(KeyModifiers::ALT) => {
                self.filter_query.push(c);
                self.clamp_selection();
                SelectWorkerModalAction::None
            }
            _ => SelectWorkerModalAction::None,
        }
    }

    /// Set theme.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.theme = theme;
        self
    }
}

impl Widget for SelectWorkerModal {
    fn render(self, area: Rect, buf: &mut Buffer) {
        (&self).render(area, buf);
    }
}

impl Widget for &SelectWorkerModal {
    fn render(self, area: Rect, buf: &mut Buffer) {
        if !self.is_open || area.width < 35 || area.height < 8 {
            return;
        }

        let p = self.theme.palette();

        // Geometry: clean centered modal popup
        let modal_width = 86.min(area.width.saturating_sub(4));
        let modal_height = 20.min(area.height.saturating_sub(2));
        let x = area.x + (area.width.saturating_sub(modal_width)) / 2;
        let y = area.y + (area.height.saturating_sub(modal_height)) / 2;
        let modal_area = Rect::new(x, y, modal_width, modal_height);

        Clear.render(modal_area, buf);

        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(modal_colors::TITLE_CYAN).add_modifier(Modifier::BOLD))
            .style(Style::default().bg(modal_colors::BG_SURFACE))
            .title(Span::styled(
                " Provision New Agent Worker Slot / Select Worker Agent Slot (Enter to spawn, Esc to cancel) ",
                Style::default().fg(modal_colors::TITLE_CYAN).add_modifier(Modifier::BOLD),
            ));

        let inner = block.inner(modal_area);
        block.render(modal_area, buf);

        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(1), // Subtitle
                Constraint::Length(2), // Search Filter Input Box
                Constraint::Length(1), // Table Column Headers
                Constraint::Min(4),    // Slot Rows List
                Constraint::Length(1), // Footer Keybinding Hints
            ])
            .split(inner);

        // 1. Subtitle
        let subtitle_line = Line::from(vec![
            Span::styled(
                "  Choose an installed agy instance slot to assign as this worker's runtime environment",
                Style::default().fg(modal_colors::FG_MUTED),
            ),
        ]);
        buf.set_line(chunks[0].x, chunks[0].y, &subtitle_line, chunks[0].width);

        // 2. Search Filter Input Box
        let filter_display = if self.filter_query.is_empty() {
            "Filter agy instances (e.g. agy11, email)..."
        } else {
            &self.filter_query
        };

        let filter_style = if self.filter_query.is_empty() {
            Style::default().fg(modal_colors::FG_MUTED).add_modifier(Modifier::ITALIC)
        } else {
            Style::default().fg(modal_colors::ACCENT_CYAN).add_modifier(Modifier::BOLD)
        };

        let search_box = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(modal_colors::ACCENT_CYAN))
            .title(Span::styled(" Search Filter ", Style::default().fg(modal_colors::ACCENT_CYAN)));

        let search_inner = search_box.inner(chunks[1]);
        search_box.render(chunks[1], buf);

        let search_line = Line::from(vec![
            Span::styled(" 🔍 ", Style::default().fg(modal_colors::ACCENT_CYAN)),
            Span::styled(filter_display, filter_style),
            Span::styled("█", Style::default().fg(modal_colors::ACCENT_CYAN)),
        ]);
        buf.set_line(search_inner.x, search_inner.y, &search_line, search_inner.width);

        // 3. Table Column Headers
        let header_line = Line::from(vec![
            Span::raw("   "),
            Span::styled(format!("{:<10}", "SLOT"), Style::default().fg(modal_colors::ACCENT_YELLOW).add_modifier(Modifier::BOLD)),
            Span::styled(format!("{:<24}", "ROLE"), Style::default().fg(modal_colors::ACCENT_YELLOW).add_modifier(Modifier::BOLD)),
            Span::styled(format!("{:<20}", "MODEL"), Style::default().fg(modal_colors::ACCENT_YELLOW).add_modifier(Modifier::BOLD)),
            Span::styled(format!("{:<12}", "STATUS"), Style::default().fg(modal_colors::ACCENT_YELLOW).add_modifier(Modifier::BOLD)),
            Span::styled("EMAIL / ACCOUNT", Style::default().fg(modal_colors::ACCENT_YELLOW).add_modifier(Modifier::BOLD)),
        ]);
        buf.set_line(chunks[2].x, chunks[2].y, &header_line, chunks[2].width);

        // 4. Slot Rows List
        let filtered = self.filtered_slots();
        let view_height = chunks[3].height as usize;
        let start_idx = if self.selected_index >= view_height {
            self.selected_index - view_height + 1
        } else {
            0
        };

        if filtered.is_empty() {
            let empty_line = Line::from(vec![
                Span::styled(
                    "  No matching agy instances found.",
                    Style::default().fg(modal_colors::FG_MUTED).add_modifier(Modifier::ITALIC),
                ),
            ]);
            buf.set_line(chunks[3].x, chunks[3].y, &empty_line, chunks[3].width);
        } else {
            for (idx, slot) in filtered.iter().skip(start_idx).take(view_height).enumerate() {
                let actual_idx = start_idx + idx;
                let is_selected = actual_idx == self.selected_index;
                let current_y = chunks[3].y + idx as u16;

                let row_bg = if is_selected {
                    modal_colors::BG_HIGHLIGHT
                } else {
                    p.bg_surface
                };

                // Clear background row
                for x in chunks[3].left()..chunks[3].right() {
                    let cell = &mut buf[(x, current_y)];
                    cell.set_style(Style::default().bg(row_bg));
                    cell.set_char(' ');
                }

                let pointer = if is_selected {
                    Span::styled(
                        format!(" {} ", glyphs::POINTER),
                        Style::default().fg(modal_colors::ACCENT_CYAN).add_modifier(Modifier::BOLD),
                    )
                } else {
                    Span::raw("   ")
                };

                let slot_str = format!("agy{}", slot.slot_id);
                let role_snippet = if slot.role.len() > 22 {
                    format!("{}...", &slot.role[..19])
                } else {
                    slot.role.clone()
                };

                let model_snippet = if slot.model.len() > 18 {
                    format!("{}...", &slot.model[..15])
                } else {
                    slot.model.clone()
                };

                let status_span = if slot.has_token {
                    Span::styled(
                        "● Ready     ",
                        Style::default().fg(modal_colors::ACCENT_GREEN).add_modifier(Modifier::BOLD),
                    )
                } else {
                    Span::styled(
                        "○ Unauth    ",
                        Style::default().fg(modal_colors::FG_MUTED),
                    )
                };

                let email_str = slot.email.as_deref().unwrap_or("(Local Profile)");

                let name_style = if is_selected {
                    Style::default().fg(modal_colors::ACCENT_CYAN).add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(modal_colors::TITLE_CYAN)
                };

                let row_line = Line::from(vec![
                    pointer,
                    Span::styled(format!("{:<10}", slot_str), name_style),
                    Span::styled(format!("{:<24}", role_snippet), Style::default().fg(modal_colors::FG_LIGHT)),
                    Span::styled(format!("{:<20}", model_snippet), Style::default().fg(modal_colors::ACCENT_MAGENTA)),
                    status_span,
                    Span::styled(email_str, Style::default().fg(modal_colors::FG_MUTED)),
                ]);

                buf.set_line(chunks[3].x, current_y, &row_line, chunks[3].width);
            }
        }

        // 5. Footer Hints
        let footer_line = Line::from(vec![
            Span::styled(
                "  [Enter] Spawn Selected Slot  │  [Type] Filter Query  │  [↑/↓] Navigate  │  [Esc] Cancel",
                Style::default().fg(modal_colors::FG_MUTED),
            ),
        ]);
        buf.set_line(chunks[4].x, chunks[4].y, &footer_line, chunks[4].width);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;

    #[test]
    fn test_select_worker_modal_filtering_and_navigation() {
        let slots = vec![
            AgentSlot::new(1, "agy1", PathBuf::from("/tmp/agy1"), "Lead Coordinator", "gemini-3.8-flash-high", None, true, Some("lead@mind.org".into())),
            AgentSlot::new(11, "agy11", PathBuf::from("/tmp/agy11"), "Backend Specialist", "gemini-3.8-flash-high", None, true, Some("backend@mind.org".into())),
            AgentSlot::new(51, "agy51", PathBuf::from("/tmp/agy51"), "Frontend Engineer", "gemini-3.8-flash-high", None, true, Some("frontend@mind.org".into())),
            AgentSlot::new(100, "agy100", PathBuf::from("/tmp/agy100"), "Testing Auditor", "gemini-3.8-flash-high", None, true, Some("test@mind.org".into())),
        ];

        let mut modal = SelectWorkerModal::new(slots);
        assert_eq!(modal.filtered_slots().len(), 4);

        // 1. Filter by "51"
        for c in "51".chars() {
            modal.handle_key(&KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE));
        }
        assert_eq!(modal.filtered_slots().len(), 1);
        assert_eq!(modal.filtered_slots()[0].slot_id, 51);

        // 2. Clear filter with backspace
        modal.handle_key(&KeyEvent::new(KeyCode::Backspace, KeyModifiers::NONE));
        modal.handle_key(&KeyEvent::new(KeyCode::Backspace, KeyModifiers::NONE));
        assert_eq!(modal.filtered_slots().len(), 4);

        // 3. Filter by role "Back"
        for c in "Back".chars() {
            modal.handle_key(&KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE));
        }
        assert_eq!(modal.filtered_slots().len(), 1);
        assert_eq!(modal.filtered_slots()[0].slot_id, 11);

        // 4. Select on Enter
        let action = modal.handle_key(&KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE));
        match action {
            SelectWorkerModalAction::Spawn(slot) => {
                assert_eq!(slot.slot_id, 11);
            }
            _ => panic!("Expected SelectWorkerModalAction::Spawn"),
        }
        assert!(!modal.is_open);
    }

    #[test]
    fn test_select_worker_modal_rendering() {
        let slots = vec![
            AgentSlot::new(1, "agy1", PathBuf::from("/tmp/agy1"), "Lead Coordinator", "gemini-3.8-flash-high", None, true, None),
            AgentSlot::new(51, "agy51", PathBuf::from("/tmp/agy51"), "Frontend Engineer", "gemini-3.8-flash-high", None, true, None),
        ];

        let modal = SelectWorkerModal::new(slots);
        let backend = TestBackend::new(100, 22);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                f.render_widget(&modal, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut content = String::new();
        for y in 0..22 {
            for x in 0..100 {
                content.push_str(term_buf[(x, y)].symbol());
            }
        }

        assert!(content.contains("Select Worker Agent Slot"));
        assert!(content.contains("Search Filter"));
        assert!(content.contains("agy1"));
        assert!(content.contains("agy51"));
        assert!(content.contains("Frontend Engineer"));
    }
}
