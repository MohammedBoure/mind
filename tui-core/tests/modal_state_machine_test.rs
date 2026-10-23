use std::sync::Arc;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use tempfile::tempdir;

use tui_core::session::identity::AgentSlot;
use tui_core::session::session_store::{SessionRecord, SessionStore};
use tui_core::ui::{
    DirectiveEditorAction, DirectiveEditorModal, DirectiveModal, DirectiveModalAction,
    DirectivePriority, HelpModal, NewWorkerModal, NewWorkerModalAction, SessionPickerAction,
    SessionPickerScreen, Theme, ThemeMode,
};

#[test]
fn test_help_modal_state_transitions() {
    let theme = Theme::new(ThemeMode::TokyoNight);
    let mut modal = HelpModal::new(theme);
    assert!(modal.is_open());

    // Non-closing key or Esc closes
    let esc = KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE);
    assert!(modal.handle_key(&esc));
    assert!(!modal.is_open());

    // Reopen and close
    modal.open();
    assert!(modal.is_open());
    modal.close();
    assert!(!modal.is_open());
}

#[test]
fn test_directive_modal_priority_cycling_and_text_input() {
    let mut modal = DirectiveModal::new("worker-math", "agy11", "Systems Engineer");
    assert_eq!(modal.priority, DirectivePriority::Normal);
    assert_eq!(modal.message, "");

    // 1. Cycle priority through all 4 levels: Normal -> High -> Critical -> Low -> Normal
    let tab = KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE);
    modal.handle_key(&tab);
    assert_eq!(modal.priority, DirectivePriority::High);

    modal.handle_key(&tab);
    assert_eq!(modal.priority, DirectivePriority::Critical);

    modal.handle_key(&tab);
    assert_eq!(modal.priority, DirectivePriority::Low);

    modal.handle_key(&tab);
    assert_eq!(modal.priority, DirectivePriority::Normal);

    // 2. Text input typing
    for c in "Hot-reload config".chars() {
        let action = modal.handle_key(&KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE));
        assert_eq!(action, DirectiveModalAction::None);
    }
    assert_eq!(modal.message, "Hot-reload config");

    // 3. Backspace
    let backspace = KeyEvent::new(KeyCode::Backspace, KeyModifiers::NONE);
    modal.handle_key(&backspace);
    assert_eq!(modal.message, "Hot-reload confi");

    modal.handle_key(&KeyEvent::new(KeyCode::Char('g'), KeyModifiers::NONE));
    assert_eq!(modal.message, "Hot-reload config");

    // 4. Submit via Enter
    modal.priority = DirectivePriority::Critical;
    let enter = KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE);
    let submit_action = modal.handle_key(&enter);
    assert_eq!(
        submit_action,
        DirectiveModalAction::Submit {
            worker_id: "worker-math".to_string(),
            message: "Hot-reload config".to_string(),
            priority: DirectivePriority::Critical,
        }
    );
    assert!(!modal.is_open);

    // 5. Cancel via Esc on a fresh open modal
    let mut modal2 = DirectiveModal::new("worker-math", "agy11", "Systems Engineer");
    let esc = KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE);
    let cancel_action = modal2.handle_key(&esc);
    assert_eq!(cancel_action, DirectiveModalAction::Cancel);
    assert!(!modal2.is_open);
}

#[test]
fn test_directive_editor_multiline_editing_and_navigation() {
    let initial_content = "Line 1\nLine 2";
    let mut editor = DirectiveEditorModal::new(
        "worker-frontend",
        "agy51",
        "Frontend Engineer",
        initial_content,
    );

    assert_eq!(editor.lines.len(), 2);
    assert_eq!(editor.cursor_row, 0);
    assert_eq!(editor.cursor_col, 0);

    // 1. Navigate Down
    let down = KeyEvent::new(KeyCode::Down, KeyModifiers::NONE);
    editor.handle_key(&down);
    assert_eq!(editor.cursor_row, 1);

    // 2. Move to end of Line 2
    let end = KeyEvent::new(KeyCode::End, KeyModifiers::NONE);
    editor.handle_key(&end);
    assert_eq!(editor.cursor_col, 6);

    // 3. Press Enter to insert a new line
    let enter = KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE);
    editor.handle_key(&enter);
    assert_eq!(editor.lines.len(), 3);
    assert_eq!(editor.cursor_row, 2);
    assert_eq!(editor.cursor_col, 0);

    // 4. Type text on Line 3
    for c in "Line 3 appended".chars() {
        editor.handle_key(&KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE));
    }
    assert_eq!(editor.lines[2], "Line 3 appended");

    // 5. Move Left and Home
    let home = KeyEvent::new(KeyCode::Home, KeyModifiers::NONE);
    editor.handle_key(&home);
    assert_eq!(editor.cursor_col, 0);

    // 6. Up and Backspace line merge
    editor.handle_key(&KeyEvent::new(KeyCode::Up, KeyModifiers::NONE));
    assert_eq!(editor.cursor_row, 1);
    editor.handle_key(&home);
    assert_eq!(editor.cursor_col, 0);

    // Backspace at col 0 of row 1 merges Line 2 with Line 1
    editor.handle_key(&KeyEvent::new(KeyCode::Backspace, KeyModifiers::NONE));
    assert_eq!(editor.lines.len(), 2);
    assert_eq!(editor.lines[0], "Line 1Line 2");

    // 7. Save via Ctrl+S
    let save = KeyEvent::new(KeyCode::Char('s'), KeyModifiers::CONTROL);
    let save_action = editor.handle_key(&save);
    match save_action {
        DirectiveEditorAction::Save(content) => {
            assert!(content.contains("Line 1Line 2"));
            assert!(content.contains("Line 3 appended"));
        }
        _ => panic!("Expected DirectiveEditorAction::Save"),
    }
    assert!(!editor.is_open);

    // 8. Cancel via Esc on a fresh open editor
    let mut editor2 = DirectiveEditorModal::new("worker-frontend", "agy51", "Frontend Engineer", "Some task");
    let esc = KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE);
    assert_eq!(editor2.handle_key(&esc), DirectiveEditorAction::Cancel);
    assert!(!editor2.is_open);
}

#[test]
fn test_new_worker_modal_slot_selection_and_spawning() {
    let slots = vec![
        AgentSlot::new(
            11,
            "agy11",
            std::path::PathBuf::from("/tmp/agy11"),
            "Backend Systems",
            "gemini-3.8-flash-high",
            Some("Task 11".to_string()),
            true,
            Some("11@test.com".to_string()),
        ),
        AgentSlot::new(
            51,
            "agy51",
            std::path::PathBuf::from("/tmp/agy51"),
            "Frontend UI",
            "gemini-3.8-flash-high",
            Some("Task 51".to_string()),
            true,
            Some("51@test.com".to_string()),
        ),
        AgentSlot::new(
            100,
            "agy100",
            std::path::PathBuf::from("/tmp/agy100"),
            "Testing Engineer",
            "gemini-3.8-flash-high",
            Some("Task 100".to_string()),
            true,
            Some("100@test.com".to_string()),
        ),
    ];

    let mut modal = NewWorkerModal::new(slots.clone());
    assert_eq!(modal.selected_index, 0);

    // 1. Navigate Down
    let down = KeyEvent::new(KeyCode::Down, KeyModifiers::NONE);
    modal.handle_key(&down);
    assert_eq!(modal.selected_index, 1);

    modal.handle_key(&down);
    assert_eq!(modal.selected_index, 2);

    // Clamping / wrapping at bottom
    modal.handle_key(&down);
    assert_eq!(modal.selected_index, 2);

    // 2. Navigate Up
    let up = KeyEvent::new(KeyCode::Up, KeyModifiers::NONE);
    modal.handle_key(&up);
    assert_eq!(modal.selected_index, 1);

    // 3. Enter spawns selected slot
    let enter = KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE);
    let action = modal.handle_key(&enter);
    assert_eq!(action, NewWorkerModalAction::Spawn(slots[1].clone()));
    assert!(!modal.is_open);

    // 4. Cancel via Esc on a fresh modal
    let mut modal2 = NewWorkerModal::new(slots);
    let esc = KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE);
    assert_eq!(modal2.handle_key(&esc), NewWorkerModalAction::Cancel);
    assert!(!modal2.is_open);
}

#[test]
fn test_session_picker_screen_navigation_and_actions() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let store = Arc::new(SessionStore::with_dir(tmp.path().join("sessions")));

    let s1 = SessionRecord::new("alpha_test", "First session");
    let s2 = SessionRecord::new("beta_test", "Second session");
    store.save_session(&s1).unwrap();
    store.save_session(&s2).unwrap();

    let mut picker = SessionPickerScreen::new(Arc::clone(&store));
    assert_eq!(picker.sessions.len(), 2);
    assert_eq!(picker.selected_index, 0);

    // 1. Navigate Down
    let down = KeyEvent::new(KeyCode::Down, KeyModifiers::NONE);
    picker.handle_key(&down);
    assert_eq!(picker.selected_index, 1);

    // 2. Press Enter to Open selected session
    let enter = KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE);
    let open_action = picker.handle_key(&enter);
    match open_action {
        SessionPickerAction::Open(rec) => {
            assert!(rec.name == "alpha_test" || rec.name == "beta_test");
        }
        _ => panic!("Expected SessionPickerAction::Open"),
    }

    // 3. Press 'n' to enter new session creation
    let n_key = KeyEvent::new(KeyCode::Char('n'), KeyModifiers::NONE);
    let _ = picker.handle_key(&n_key);
    assert!(picker.is_creating);

    // Type new session name "gamma_session" and press Enter
    for c in "gamma_session".chars() {
        picker.handle_key(&KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE));
    }
    assert_eq!(picker.new_session_input, "gamma_session");

    let create_action = picker.handle_key(&enter);
    assert_eq!(create_action, SessionPickerAction::Create("gamma_session".to_string()));

    // 4. Delete session with 'd'
    picker.refresh();
    picker.selected_index = 0;
    let d_key = KeyEvent::new(KeyCode::Char('d'), KeyModifiers::NONE);
    let delete_action = picker.handle_key(&d_key);
    match delete_action {
        SessionPickerAction::Delete(deleted) => {
            assert!(!deleted.is_empty());
        }
        _ => panic!("Expected SessionPickerAction::Delete"),
    }

    // 5. Exit picker with Esc
    let esc = KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE);
    assert_eq!(picker.handle_key(&esc), SessionPickerAction::Exit);
}
