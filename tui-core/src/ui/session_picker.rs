use std::sync::Arc;
use crossterm::event::{KeyCode, KeyEvent};
use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Widget},
};

use crate::session::session_store::{SessionRecord, SessionStore};
use crate::ui::theme::{glyphs, Theme};

/// Actions dispatched by the interactive session picker screen.
#[derive(Debug, Clone, PartialEq)]
pub enum SessionPickerAction {
    /// Open the selected session.
    Open(SessionRecord),
    /// Create a new session with the specified name.
    Create(String),
    /// A session was deleted.
    Delete(String),
    /// User exited/cancelled the session picker.
    Exit,
    /// Key was handled internally.
    None,
}

/// Interactive Session Picker screen listing saved sessions from persistent storage.
#[derive(Debug, Clone)]
pub struct SessionPickerScreen {
    pub store: Arc<SessionStore>,
    pub sessions: Vec<SessionRecord>,
    pub selected_index: usize,
    pub is_creating: bool,
    pub new_session_input: String,
    pub status_message: Option<String>,
    pub theme: Theme,
}

impl SessionPickerScreen {
    /// Initialize SessionPickerScreen querying the given session store.
    pub fn new(store: Arc<SessionStore>) -> Self {
        let sessions = store.list_sessions().unwrap_or_default();
        Self {
            store,
            sessions,
            selected_index: 0,
            is_creating: false,
            new_session_input: String::new(),
            status_message: None,
            theme: Theme::default(),
        }
    }

    /// Refresh the session list from disk.
    pub fn refresh(&mut self) {
        self.sessions = self.store.list_sessions().unwrap_or_default();
        if self.selected_index >= self.sessions.len() && !self.sessions.is_empty() {
            self.selected_index = self.sessions.len() - 1;
        }
    }

    /// Handle keyboard input on the session picker screen.
    pub fn handle_key(&mut self, key: &KeyEvent) -> SessionPickerAction {
        // Mode 1: Creating a new session inline
        if self.is_creating {
            match key.code {
                KeyCode::Esc => {
                    self.is_creating = false;
                    self.new_session_input.clear();
                    return SessionPickerAction::None;
                }
                KeyCode::Enter => {
                    let name = self.new_session_input.trim().to_string();
                    self.is_creating = false;
                    self.new_session_input.clear();
                    if !name.is_empty() {
                        return SessionPickerAction::Create(name);
                    } else {
                        return SessionPickerAction::None;
                    }
                }
                KeyCode::Char(c) => {
                    self.new_session_input.push(c);
                    return SessionPickerAction::None;
                }
                KeyCode::Backspace => {
                    self.new_session_input.pop();
                    return SessionPickerAction::None;
                }
                _ => return SessionPickerAction::None,
            }
        }

        // Mode 2: Browsing and managing sessions
        match key.code {
            KeyCode::Esc | KeyCode::Char('q') => SessionPickerAction::Exit,
            KeyCode::Enter => {
                if let Some(session) = self.sessions.get(self.selected_index) {
                    SessionPickerAction::Open(session.clone())
                } else {
                    SessionPickerAction::None
                }
            }
            KeyCode::Char('n') => {
                self.is_creating = true;
                self.new_session_input.clear();
                SessionPickerAction::None
            }
            KeyCode::Char('d') => {
                if let Some(session) = self.sessions.get(self.selected_index) {
                    let name = session.name.clone();
                    if let Ok(deleted) = self.store.delete_session(&name) {
                        if deleted {
                            self.status_message = Some(format!("Deleted session '{}'", name));
                            self.refresh();
                            return SessionPickerAction::Delete(name);
                        }
                    }
                }
                SessionPickerAction::None
            }
            KeyCode::Up | KeyCode::Char('k') => {
                if self.selected_index > 0 {
                    self.selected_index -= 1;
                }
                SessionPickerAction::None
            }
            KeyCode::Down | KeyCode::Char('j') => {
                if !self.sessions.is_empty() && self.selected_index + 1 < self.sessions.len() {
                    self.selected_index += 1;
                }
                SessionPickerAction::None
            }
            _ => SessionPickerAction::None,
        }
    }

    /// Set theme.
    pub fn theme(mut self, theme: Theme) -> Self {
        self.theme = theme;
        self
    }
}

impl Widget for SessionPickerScreen {
    fn render(self, area: Rect, buf: &mut Buffer) {
        (&self).render(area, buf);
    }
}

impl Widget for &SessionPickerScreen {
    fn render(self, area: Rect, buf: &mut Buffer) {
        if area.width < 40 || area.height < 10 {
            return;
        }

        let p = self.theme.palette();

        let block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD))
            .style(Style::default().bg(p.bg_dark))
            .title(Span::styled(
                " Mind Multi-Agent Session Picker ",
                Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD),
            ));

        let inner = block.inner(area);
        block.render(area, buf);

        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(2), // Subtitle & info banner
                Constraint::Length(1), // Table header
                Constraint::Min(5),    // Session list table
                Constraint::Length(1), // Footer hotkey guide
            ])
            .split(inner);

        // 1. Subtitle & storage location
        let subtitle_spans = vec![
            Span::styled("  Persistent Swarm Sessions in ", Style::default().fg(p.fg_muted)),
            Span::styled(self.store.sessions_dir().to_string_lossy().to_string(), Style::default().fg(p.accent_teal)),
        ];
        buf.set_line(chunks[0].x, chunks[0].y, &Line::from(subtitle_spans), chunks[0].width);

        if let Some(ref msg) = self.status_message {
            let msg_line = Line::from(vec![
                Span::styled(format!("  ⚡ {}", msg), Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)),
            ]);
            buf.set_line(chunks[0].x, chunks[0].y + 1, &msg_line, chunks[0].width);
        }

        // 2. Table Header
        let header_line = Line::from(vec![
            Span::styled("   ", Style::default()),
            Span::styled(format!("{:<20}", "SESSION NAME"), Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)),
            Span::styled(format!("{:<10}", "WORKERS"), Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)),
            Span::styled(format!("{:<10}", "STATUS"), Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)),
            Span::styled(format!("{:<15}", "INTERACTIONS"), Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)),
            Span::styled(format!("{:<22}", "LAST ACTIVITY"), Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)),
            Span::styled("MISSION GOAL", Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)),
        ]);
        buf.set_line(chunks[1].x, chunks[1].y, &header_line, chunks[1].width);

        // 3. Session rows
        let view_height = chunks[2].height as usize;
        let start_idx = if self.selected_index >= view_height {
            self.selected_index - view_height + 1
        } else {
            0
        };

        if self.sessions.is_empty() {
            let empty_line = Line::from(vec![
                Span::styled("  No saved sessions found. Press 'n' to create and launch a new session.", Style::default().fg(p.fg_muted).add_modifier(Modifier::ITALIC)),
            ]);
            buf.set_line(chunks[2].x, chunks[2].y, &empty_line, chunks[2].width);
        } else {
            for (idx, session) in self.sessions.iter().skip(start_idx).take(view_height).enumerate() {
                let actual_idx = start_idx + idx;
                let is_selected = actual_idx == self.selected_index;
                let current_y = chunks[2].y + idx as u16;

                let row_bg = if is_selected { p.bg_highlight } else { p.bg_dark };

                // Fill background
                for x in chunks[2].left()..chunks[2].right() {
                    let cell = &mut buf[(x, current_y)];
                    cell.set_style(Style::default().bg(row_bg));
                    cell.set_char(' ');
                }

                let pointer = if is_selected {
                    Span::styled(format!(" {} ", glyphs::POINTER), Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD))
                } else {
                    Span::raw("   ")
                };

                let name_style = if is_selected {
                    Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(p.fg_light)
                };

                let status_style = if session.active {
                    Style::default().fg(p.accent_green).add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(p.fg_muted)
                };

                let workers_str = format!("{} agents", session.workers.len().max(session.agent_count));
                let interactions_str = format!("{} steps", session.total_interactions.max(session.total_steps));
                let date_str = session.last_activity.chars().take(19).collect::<String>();
                let goal_snippet = if session.goal.len() > 30 {
                    format!("{}...", &session.goal[..27])
                } else {
                    session.goal.clone()
                };

                let row_line = Line::from(vec![
                    pointer,
                    Span::styled(format!("{:<20}", session.name), name_style),
                    Span::styled(format!("{:<10}", workers_str), Style::default().fg(p.accent_blue)),
                    Span::styled(format!("{:<10}", session.status.to_uppercase()), status_style),
                    Span::styled(format!("{:<15}", interactions_str), Style::default().fg(p.accent_teal)),
                    Span::styled(format!("{:<22}", date_str), Style::default().fg(p.fg_muted)),
                    Span::styled(goal_snippet, Style::default().fg(p.fg_light)),
                ]);

                buf.set_line(chunks[2].x, current_y, &row_line, chunks[2].width);
            }
        }

        // 4. Footer guide
        let footer_line = Line::from(vec![
            Span::styled("  [Enter] Open Session  │  [n] New Session  │  [d] Delete Session  │  [↑/↓] Navigate  │  [q/Esc] Exit", Style::default().fg(p.fg_muted)),
        ]);
        buf.set_line(chunks[3].x, chunks[3].y, &footer_line, chunks[3].width);

        // Optional Dialog overlay when creating a new session
        if self.is_creating {
            let dialog_width = 54.min(area.width.saturating_sub(4));
            let dialog_height = 7;
            let dx = area.x + (area.width.saturating_sub(dialog_width)) / 2;
            let dy = area.y + (area.height.saturating_sub(dialog_height)) / 2;
            let dialog_area = Rect::new(dx, dy, dialog_width, dialog_height);

            Clear.render(dialog_area, buf);

            let dialog_block = Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD))
                .style(Style::default().bg(p.bg_surface))
                .title(Span::styled(" Create New Multi-Agent Session ", Style::default().fg(p.accent_yellow).add_modifier(Modifier::BOLD)));

            let d_inner = dialog_block.inner(dialog_area);
            dialog_block.render(dialog_area, buf);

            let d_chunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Length(1), // Prompt label
                    Constraint::Length(2), // Input field
                    Constraint::Length(1), // Hints
                ])
                .split(d_inner);

            buf.set_line(d_chunks[0].x, d_chunks[0].y, &Line::from("  Enter name for the new session:"), d_chunks[0].width);

            let input_display = Line::from(vec![
                Span::styled("  > ", Style::default().fg(p.accent_cyan).add_modifier(Modifier::BOLD)),
                Span::styled(&self.new_session_input, Style::default().fg(p.fg_light).add_modifier(Modifier::BOLD)),
                Span::styled("█", Style::default().fg(p.accent_cyan)),
            ]);
            buf.set_line(d_chunks[1].x, d_chunks[1].y, &input_display, d_chunks[1].width);

            let d_hints = Line::from(vec![
                Span::styled("  [Enter] Confirm  │  [Esc] Cancel", Style::default().fg(p.fg_muted)),
            ]);
            buf.set_line(d_chunks[2].x, d_chunks[2].y, &d_hints, d_chunks[2].width);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crossterm::event::KeyModifiers;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;
    use tempfile::tempdir;

    #[test]
    fn test_session_picker_navigation_and_actions() {
        let tmp = tempdir().unwrap();
        let store = Arc::new(SessionStore::with_dir(tmp.path().to_path_buf()));

        let s1 = SessionRecord::new("mission_alpha", "Build multi-agent core");
        let s2 = SessionRecord::new("mission_beta", "Verify benchmarks");
        store.save_session(&s1).unwrap();
        store.save_session(&s2).unwrap();

        let mut picker = SessionPickerScreen::new(Arc::clone(&store));
        assert_eq!(picker.sessions.len(), 2);
        assert_eq!(picker.selected_index, 0);

        // Move down
        let down = KeyEvent::new(KeyCode::Down, KeyModifiers::NONE);
        picker.handle_key(&down);
        assert_eq!(picker.selected_index, 1);

        // Open selected
        let enter = KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE);
        let action = picker.handle_key(&enter);
        match action {
            SessionPickerAction::Open(rec) => {
                assert!(rec.name == "mission_alpha" || rec.name == "mission_beta");
            }
            _ => panic!("Expected Open action"),
        }

        // Test creation prompt
        let n_key = KeyEvent::new(KeyCode::Char('n'), KeyModifiers::NONE);
        picker.handle_key(&n_key);
        assert!(picker.is_creating);

        for c in "mission_gamma".chars() {
            picker.handle_key(&KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE));
        }
        assert_eq!(picker.new_session_input, "mission_gamma");

        let submit_create = picker.handle_key(&enter);
        match submit_create {
            SessionPickerAction::Create(name) => {
                assert_eq!(name, "mission_gamma");
            }
            _ => panic!("Expected Create action"),
        }
        assert!(!picker.is_creating);

        // Test delete
        let d_key = KeyEvent::new(KeyCode::Char('d'), KeyModifiers::NONE);
        let del_action = picker.handle_key(&d_key);
        assert!(matches!(del_action, SessionPickerAction::Delete(_)));
    }

    #[test]
    fn test_session_picker_render() {
        let tmp = tempdir().unwrap();
        let store = Arc::new(SessionStore::with_dir(tmp.path().to_path_buf()));
        let s1 = SessionRecord::new("deep_space", "Voyager telemetry analysis");
        store.save_session(&s1).unwrap();

        let picker = SessionPickerScreen::new(store);
        let backend = TestBackend::new(100, 24);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal
            .draw(|f| {
                f.render_widget(picker, f.area());
            })
            .unwrap();

        let term_buf = terminal.backend().buffer();
        let mut text = String::new();
        for y in 0..24 {
            for x in 0..100 {
                text.push_str(term_buf[(x, y)].symbol());
            }
        }

        assert!(text.contains("Session Picker"));
        assert!(text.contains("deep_space"));
        assert!(text.contains("Voyager telemetry"));
    }
}
