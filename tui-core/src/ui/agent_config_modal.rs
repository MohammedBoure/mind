use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Paragraph, Widget},
};

use crate::session::identity::{AgentSlot, IdentityDiscovery};
use crate::ui::theme::Theme;

/// Tokyo Night colors for AgentConfigModal.
mod config_colors {
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
    pub const BORDER_ACTIVE: Color = Color::Rgb(122, 162, 247);   // #7aa2f7
}

/// A tab configuration entry in the settings modal.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TabConfigEntry {
    pub tab_id: String,
    pub title: String,
    pub slot_id: String,
    pub role: String,
    pub model: String,
    pub is_coordinator: bool,
}

impl TabConfigEntry {
    pub fn new(
        tab_id: impl Into<String>,
        title: impl Into<String>,
        slot_id: impl Into<String>,
        role: impl Into<String>,
        model: impl Into<String>,
        is_coordinator: bool,
    ) -> Self {
        Self {
            tab_id: tab_id.into(),
            title: title.into(),
            slot_id: slot_id.into(),
            role: role.into(),
            model: model.into(),
            is_coordinator,
        }
    }
}

/// Resulting action from user interaction with AgentConfigModal.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AgentConfigModalAction {
    /// Save configuration changes (optionally restarting the child PTY with the new slot).
    Save {
        tab_id: String,
        new_slot_id: String,
        new_role: String,
        restart: bool,
    },
    /// Save all changes and restart all tabs (Coordinator and all Workers).
    RestartAll,
    /// Dismiss modal without saving.
    Cancel,
    /// Internal key handled without closing.
    None,
}

/// Interactive in-app Agent & Tab Configuration Modal (matching Python `AgentConfigModal`):
/// - Displays all active tabs (Primary Coordinator and interactive worker tabs).
/// - Shows current `agy` slot assignment, role, model, and authentication status per tab.
/// - Allows cycling through all available `agy` slots (agy1..agy200) using Left/Right/h/l/Space.
/// - `Enter` or `Ctrl+S` saves configuration.
/// - `Ctrl+R` saves configuration AND restarts the tab with the newly assigned `agy` slot.
/// - `Esc` or `q` closes modal.
#[derive(Debug, Clone)]
pub struct AgentConfigModal {
    pub tabs: Vec<TabConfigEntry>,
    pub available_slots: Vec<AgentSlot>,
    pub selected_tab_index: usize,
    pub is_open: bool,
    pub status_message: Option<String>,
    pub theme: Theme,
}

impl Default for AgentConfigModal {
    fn default() -> Self {
        Self::new(Vec::new())
    }
}

impl AgentConfigModal {
    /// Initialize with current running tabs and discovered host slots.
    pub fn new(tabs: Vec<TabConfigEntry>) -> Self {
        let mut slots = IdentityDiscovery::discover_slots();
        if slots.is_empty() {
            // Provide standard slots if host directory is empty
            for id in &[1, 11, 51, 100, 151] {
                slots.push(AgentSlot::new(
                    *id,
                    format!("agy{}", id),
                    IdentityDiscovery::get_instances_dir().join(format!("agy{}", id)),
                    match id {
                        1 => "Lead Orchestrator".to_string(),
                        11 => "Backend Logic & Systems".to_string(),
                        51 => "Frontend & Interface Auditor".to_string(),
                        100 => "Quality Gatekeeper & Testing".to_string(),
                        _ => "Autonomous Worker Agent".to_string(),
                    },
                    "gemini-3.8-flash-high".to_string(),
                    None,
                    true,
                    None,
                ));
            }
        }
        slots.sort_by_key(|s| s.slot_id);

        Self {
            tabs,
            available_slots: slots,
            selected_tab_index: 0,
            is_open: true,
            status_message: None,
            theme: Theme::default(),
        }
    }

    /// Set theme.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.theme = theme;
        self
    }

    /// Open or reset modal.
    pub fn open(&mut self) {
        self.is_open = true;
        self.status_message = None;
    }

    /// Close modal.
    pub fn close(&mut self) {
        self.is_open = false;
    }

    /// Currently highlighted tab configuration entry.
    pub fn current_tab(&self) -> Option<&TabConfigEntry> {
        self.tabs.get(self.selected_tab_index)
    }

    /// Currently highlighted tab configuration entry mutably.
    pub fn current_tab_mut(&mut self) -> Option<&mut TabConfigEntry> {
        self.tabs.get_mut(self.selected_tab_index)
    }

    /// Move tab selection up.
    pub fn prev_tab(&mut self) {
        if !self.tabs.is_empty() {
            if self.selected_tab_index == 0 {
                self.selected_tab_index = self.tabs.len() - 1;
            } else {
                self.selected_tab_index -= 1;
            }
        }
    }

    /// Move tab selection down.
    pub fn next_tab(&mut self) {
        if !self.tabs.is_empty() {
            self.selected_tab_index = (self.selected_tab_index + 1) % self.tabs.len();
        }
    }

    /// Find index in `available_slots` matching current tab's slot_id.
    fn current_slot_index(&self) -> usize {
        let cur_slot_id = self
            .current_tab()
            .map(|t| t.slot_id.clone())
            .unwrap_or_default();
        let parsed = IdentityDiscovery::parse_slot_id(&cur_slot_id);

        self.available_slots
            .iter()
            .position(|s| {
                s.name.eq_ignore_ascii_case(&cur_slot_id)
                    || parsed.map(|p| p == s.slot_id).unwrap_or(false)
            })
            .unwrap_or(0)
    }

    /// Cycle slot forward (Right / l / Space).
    pub fn cycle_slot_next(&mut self) {
        if self.available_slots.is_empty() || self.tabs.is_empty() {
            return;
        }
        let cur_idx = self.current_slot_index();
        let next_idx = (cur_idx + 1) % self.available_slots.len();
        let new_slot = self.available_slots[next_idx].clone();

        if let Some(tab) = self.current_tab_mut() {
            tab.slot_id = new_slot.name.clone();
            tab.role = new_slot.role.clone();
            tab.model = new_slot.model.clone();
        }
        self.status_message = Some(format!("Assigned to {} ({})", new_slot.name, new_slot.role));
    }

    /// Cycle slot backward (Left / h).
    pub fn cycle_slot_prev(&mut self) {
        if self.available_slots.is_empty() || self.tabs.is_empty() {
            return;
        }
        let cur_idx = self.current_slot_index();
        let prev_idx = if cur_idx == 0 {
            self.available_slots.len() - 1
        } else {
            cur_idx - 1
        };
        let new_slot = self.available_slots[prev_idx].clone();

        if let Some(tab) = self.current_tab_mut() {
            tab.slot_id = new_slot.name.clone();
            tab.role = new_slot.role.clone();
            tab.model = new_slot.model.clone();
        }
        self.status_message = Some(format!("Assigned to {} ({})", new_slot.name, new_slot.role));
    }

    /// Handle keyboard navigation and actions.
    pub fn handle_key(&mut self, key: &KeyEvent) -> AgentConfigModalAction {
        if !self.is_open {
            return AgentConfigModalAction::None;
        }

        // Close / Cancel: Esc or 'q'
        if key.code == KeyCode::Esc || key.code == KeyCode::Char('q') {
            self.close();
            return AgentConfigModalAction::Cancel;
        }

        // Save & Restart All Tabs: 'a', 'A', or Ctrl+A
        if key.code == KeyCode::Char('a')
            || key.code == KeyCode::Char('A')
            || ((key.code == KeyCode::Char('a') || key.code == KeyCode::Char('A'))
                && key.modifiers.contains(KeyModifiers::CONTROL))
        {
            self.close();
            return AgentConfigModalAction::RestartAll;
        }

        // Save & Restart Active Tab: Enter, 'r', 'R', or Ctrl+R
        if key.code == KeyCode::Enter
            || key.code == KeyCode::Char('r')
            || key.code == KeyCode::Char('R')
            || ((key.code == KeyCode::Char('r') || key.code == KeyCode::Char('R'))
                && key.modifiers.contains(KeyModifiers::CONTROL))
        {
            if let Some(tab) = self.current_tab() {
                let action = AgentConfigModalAction::Save {
                    tab_id: tab.tab_id.clone(),
                    new_slot_id: tab.slot_id.clone(),
                    new_role: tab.role.clone(),
                    restart: true,
                };
                self.close();
                return action;
            }
        }

        // Save Only (Without Restart): 's', 'S', or Ctrl+S
        if key.code == KeyCode::Char('s')
            || key.code == KeyCode::Char('S')
            || ((key.code == KeyCode::Char('s') || key.code == KeyCode::Char('S'))
                && key.modifiers.contains(KeyModifiers::CONTROL))
        {
            if let Some(tab) = self.current_tab() {
                let action = AgentConfigModalAction::Save {
                    tab_id: tab.tab_id.clone(),
                    new_slot_id: tab.slot_id.clone(),
                    new_role: tab.role.clone(),
                    restart: false,
                };
                self.close();
                return action;
            }
        }

        // Navigate Tabs: Up / Down / j / k / Tab / BackTab
        match key.code {
            KeyCode::Up | KeyCode::Char('k') => {
                self.prev_tab();
                return AgentConfigModalAction::None;
            }
            KeyCode::Down | KeyCode::Char('j') | KeyCode::Tab => {
                self.next_tab();
                return AgentConfigModalAction::None;
            }
            KeyCode::BackTab => {
                self.prev_tab();
                return AgentConfigModalAction::None;
            }
            // Cycle Slot: Left / Right / h / l / Space
            KeyCode::Left | KeyCode::Char('h') => {
                self.cycle_slot_prev();
                return AgentConfigModalAction::None;
            }
            KeyCode::Right | KeyCode::Char('l') | KeyCode::Char(' ') => {
                self.cycle_slot_next();
                return AgentConfigModalAction::None;
            }
            _ => AgentConfigModalAction::None,
        }
    }
}

impl Widget for AgentConfigModal {
    fn render(self, area: Rect, buf: &mut Buffer) {
        (&self).render(area, buf);
    }
}

impl Widget for &AgentConfigModal {
    fn render(self, area: Rect, buf: &mut Buffer) {
        if !self.is_open || area.width < 40 || area.height < 12 {
            return;
        }

        // Centered modal dimensions: 86 cols x 24 rows (or clamped to screen)
        let modal_width = 86.min(area.width.saturating_sub(4));
        let modal_height = 24.min(area.height.saturating_sub(2));
        let x = area.x + (area.width.saturating_sub(modal_width)) / 2;
        let y = area.y + (area.height.saturating_sub(modal_height)) / 2;
        let modal_area = Rect::new(x, y, modal_width, modal_height);

        // Clear underlying area
        Clear.render(modal_area, buf);

        // Main Dialog Block with Tokyo Night styled borders
        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(
                Style::default()
                    .fg(config_colors::BORDER_ACTIVE)
                    .add_modifier(Modifier::BOLD),
            )
            .style(Style::default().bg(config_colors::BG_SURFACE))
            .title(Span::styled(
                " ⚙ Agent & Tab Settings — Assign agy per Tab (e / Esc to close) ",
                Style::default()
                    .fg(config_colors::TITLE_CYAN)
                    .add_modifier(Modifier::BOLD),
            ));

        let inner = block.inner(modal_area);
        block.render(modal_area, buf);

        // Subdivide inner area: Main Body (min 15) | Divider & Controls Footer (3)
        let main_layout = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Min(12),   // Two-column settings view
                Constraint::Length(3), // Action bar footer
            ])
            .split(inner);

        // Two-column layout: Left (Tabs List, width 30) | Right (Slot Details, remaining)
        let cols_layout = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Length(30),
                Constraint::Min(35),
            ])
            .split(main_layout[0]);

        // ── Left Column: Tabs List ──────────────────────────────────
        let mut tab_lines = Vec::new();
        tab_lines.push(Line::from(vec![
            Span::styled(
                " SELECT TAB",
                Style::default()
                    .fg(config_colors::ACCENT_MAGENTA)
                    .add_modifier(Modifier::BOLD),
            ),
        ]));
        tab_lines.push(Line::from(""));

        for (idx, tab) in self.tabs.iter().enumerate() {
            let is_selected = idx == self.selected_tab_index;
            let cursor = if is_selected { "> " } else { "  " };

            let label = if tab.is_coordinator {
                format!("{}Coordinator ({})", cursor, tab.slot_id)
            } else {
                format!("{}{}: {}", cursor, tab.title, tab.slot_id)
            };

            let style = if is_selected {
                Style::default()
                    .fg(config_colors::ACCENT_CYAN)
                    .bg(config_colors::BG_HIGHLIGHT)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(config_colors::FG_LIGHT)
            };

            tab_lines.push(Line::from(vec![Span::styled(label, style)]));
        }

        let tabs_block = Block::default()
            .borders(Borders::RIGHT)
            .border_style(Style::default().fg(config_colors::FG_MUTED));
        let tabs_inner = tabs_block.inner(cols_layout[0]);
        tabs_block.render(cols_layout[0], buf);

        let tabs_paragraph = Paragraph::new(tab_lines);
        tabs_paragraph.render(tabs_inner, buf);

        // ── Right Column: Selected Tab Configuration Details ────────
        let mut detail_lines = Vec::new();
        if let Some(tab) = self.current_tab() {
            detail_lines.push(Line::from(vec![
                Span::styled(
                    " TAB DETAILS & AGY ASSIGNMENT",
                    Style::default()
                        .fg(config_colors::ACCENT_MAGENTA)
                        .add_modifier(Modifier::BOLD),
                ),
            ]));
            detail_lines.push(Line::from(""));

            // Tab ID & Type
            detail_lines.push(Line::from(vec![
                Span::styled("  Target Tab:        ", Style::default().fg(config_colors::FG_MUTED)),
                Span::styled(
                    if tab.is_coordinator {
                        "Primary Coordinator (Left Pane)"
                    } else {
                        &tab.title
                    },
                    Style::default()
                        .fg(config_colors::FG_LIGHT)
                        .add_modifier(Modifier::BOLD),
                ),
            ]));

            // Interactive Assigned agy Slot Picker
            detail_lines.push(Line::from(vec![
                Span::styled("  Assigned Slot:     ", Style::default().fg(config_colors::FG_MUTED)),
                Span::styled(
                    format!("◀  {}  ▶", tab.slot_id),
                    Style::default()
                        .fg(config_colors::ACCENT_YELLOW)
                        .bg(config_colors::BG_HIGHLIGHT)
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled("  (←/→ or Space to cycle)", Style::default().fg(config_colors::FG_MUTED)),
            ]));

            // Role
            detail_lines.push(Line::from(vec![
                Span::styled("  Agent Role:        ", Style::default().fg(config_colors::FG_MUTED)),
                Span::styled(
                    &tab.role,
                    Style::default()
                        .fg(config_colors::ACCENT_CYAN)
                        .add_modifier(Modifier::BOLD),
                ),
            ]));

            // Model
            detail_lines.push(Line::from(vec![
                Span::styled("  AI Model:          ", Style::default().fg(config_colors::FG_MUTED)),
                Span::styled(&tab.model, Style::default().fg(config_colors::FG_LIGHT)),
            ]));

            // Launch Mode
            let agys_detected = IdentityDiscovery::find_agys_binary().is_some();
            let mode_desc = if agys_detected {
                "agys (Multi-Instance Container Isolation · bwrap)"
            } else {
                "agy (Standard System CLI)"
            };
            detail_lines.push(Line::from(vec![
                Span::styled("  Launch Engine:     ", Style::default().fg(config_colors::FG_MUTED)),
                Span::styled(mode_desc, Style::default().fg(config_colors::ACCENT_GREEN)),
            ]));

            // Authentication Status
            let cur_slot_info = IdentityDiscovery::find_slot(&tab.slot_id);
            let auth_status = if let Some(ref s) = cur_slot_info {
                if s.has_token {
                    Span::styled(
                        format!("● Logged In ({})", s.email.as_deref().unwrap_or("Active token")),
                        Style::default().fg(config_colors::ACCENT_GREEN).add_modifier(Modifier::BOLD),
                    )
                } else {
                    Span::styled("○ Logged Out", Style::default().fg(config_colors::ACCENT_YELLOW))
                }
            } else {
                Span::styled("● Configured", Style::default().fg(config_colors::ACCENT_CYAN))
            };

            detail_lines.push(Line::from(vec![
                Span::styled("  Auth Status:       ", Style::default().fg(config_colors::FG_MUTED)),
                auth_status,
            ]));

            // Directory Location
            if let Some(ref s) = cur_slot_info {
                let path_str = s.instance_dir.to_string_lossy().to_string();
                detail_lines.push(Line::from(vec![
                    Span::styled("  Storage Path:      ", Style::default().fg(config_colors::FG_MUTED)),
                    Span::styled(
                        path_str,
                        Style::default().fg(config_colors::FG_MUTED),
                    ),
                ]));
            }

            // Transient feedback notice
            if let Some(ref notice) = self.status_message {
                detail_lines.push(Line::from(""));
                detail_lines.push(Line::from(vec![
                    Span::styled(
                        format!("  ✓ {}", notice),
                        Style::default().fg(config_colors::ACCENT_GREEN).add_modifier(Modifier::BOLD),
                    ),
                ]));
            }
        }

        let detail_paragraph = Paragraph::new(detail_lines);
        detail_paragraph.render(cols_layout[1], buf);

        // ── Bottom Action Footer ────────────────────────────────────
        let footer_lines = vec![
            Line::from(vec![
                Span::styled(" [↑/↓/Tab] ", Style::default().fg(config_colors::ACCENT_CYAN).add_modifier(Modifier::BOLD)),
                Span::styled("Tab  ", Style::default().fg(config_colors::FG_LIGHT)),
                Span::styled("[←/→/Space] ", Style::default().fg(config_colors::ACCENT_YELLOW).add_modifier(Modifier::BOLD)),
                Span::styled("Change agy  ", Style::default().fg(config_colors::FG_LIGHT)),
                Span::styled("[Enter/r] ", Style::default().fg(config_colors::ACCENT_GREEN).add_modifier(Modifier::BOLD)),
                Span::styled("Save & Restart  ", Style::default().fg(config_colors::FG_LIGHT)),
                Span::styled("[s] ", Style::default().fg(config_colors::ACCENT_CYAN).add_modifier(Modifier::BOLD)),
                Span::styled("Save Only  ", Style::default().fg(config_colors::FG_LIGHT)),
                Span::styled("[a] ", Style::default().fg(config_colors::ACCENT_MAGENTA).add_modifier(Modifier::BOLD)),
                Span::styled("Restart All  ", Style::default().fg(config_colors::FG_LIGHT)),
                Span::styled("[Esc] ", Style::default().fg(config_colors::FG_MUTED).add_modifier(Modifier::BOLD)),
                Span::styled("Cancel", Style::default().fg(config_colors::FG_LIGHT)),
            ]),
        ];

        let footer_block = Block::default()
            .borders(Borders::TOP)
            .border_style(Style::default().fg(config_colors::FG_MUTED));
        let footer_inner = footer_block.inner(main_layout[1]);
        footer_block.render(main_layout[1], buf);

        let footer_paragraph = Paragraph::new(footer_lines);
        footer_paragraph.render(footer_inner, buf);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_agent_config_modal_initialization_and_cycling() {
        let tabs = vec![
            TabConfigEntry::new("coordinator", "Coordinator", "agy1", "Lead Orchestrator", "gemini-3.8-flash-high", true),
            TabConfigEntry::new("worker-1", "Worker-1", "agy11", "Backend Logic", "gemini-3.8-flash-high", false),
        ];
        let mut modal = AgentConfigModal::new(tabs);
        assert_eq!(modal.tabs.len(), 2);
        assert_eq!(modal.selected_tab_index, 0);

        // Navigate tabs
        modal.next_tab();
        assert_eq!(modal.selected_tab_index, 1);
        modal.prev_tab();
        assert_eq!(modal.selected_tab_index, 0);

        // Cycle slot
        let initial_slot = modal.current_tab().unwrap().slot_id.clone();
        modal.cycle_slot_next();
        let changed_slot = modal.current_tab().unwrap().slot_id.clone();
        assert_ne!(initial_slot, changed_slot);

        modal.cycle_slot_prev();
        assert_eq!(modal.current_tab().unwrap().slot_id, initial_slot);
    }

    #[test]
    fn test_agent_config_modal_key_handling() {
        let tabs = vec![
            TabConfigEntry::new("coordinator", "Coordinator", "agy1", "Lead Orchestrator", "gemini-3.8-flash-high", true),
        ];
        let mut modal = AgentConfigModal::new(tabs);

        // Cancel on Esc
        let key_esc = KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE);
        let action = modal.handle_key(&key_esc);
        assert_eq!(action, AgentConfigModalAction::Cancel);
        assert!(!modal.is_open);

        // Save & Restart on Enter
        modal.open();
        let key_enter = KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE);
        let action = modal.handle_key(&key_enter);
        match action {
            AgentConfigModalAction::Save { tab_id, new_slot_id, restart, .. } => {
                assert_eq!(tab_id, "coordinator");
                assert_eq!(new_slot_id, "agy1");
                assert!(restart);
            }
            _ => panic!("Expected Save & Restart action"),
        }

        // Save only on 's'
        modal.open();
        let key_s = KeyEvent::new(KeyCode::Char('s'), KeyModifiers::NONE);
        let action = modal.handle_key(&key_s);
        match action {
            AgentConfigModalAction::Save { tab_id, new_slot_id, restart, .. } => {
                assert_eq!(tab_id, "coordinator");
                assert_eq!(new_slot_id, "agy1");
                assert!(!restart);
            }
            _ => panic!("Expected Save only action"),
        }

        // Save & Restart on Ctrl+R
        modal.open();
        let key_ctrl_r = KeyEvent::new(KeyCode::Char('r'), KeyModifiers::CONTROL);
        let action = modal.handle_key(&key_ctrl_r);
        match action {
            AgentConfigModalAction::Save { restart, .. } => {
                assert!(restart);
            }
            _ => panic!("Expected Save with restart"),
        }

        // Restart all on 'a'
        modal.open();
        let key_a = KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE);
        let action = modal.handle_key(&key_a);
        assert_eq!(action, AgentConfigModalAction::RestartAll);
    }
}
