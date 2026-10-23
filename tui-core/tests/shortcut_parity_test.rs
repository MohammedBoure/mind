use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use tui_core::session::shortcuts::{Action, AgiConfig, KeyBinding, ShortcutEngine};

#[test]
fn test_key_binding_parser_comprehensive() {
    // Single character
    let kb_q = KeyBinding::parse("q").expect("parse q");
    assert_eq!(kb_q.code, KeyCode::Char('q'));
    assert_eq!(kb_q.modifiers, KeyModifiers::NONE);

    // Ctrl modifier
    let kb_ctrl_m = KeyBinding::parse("Ctrl+M").expect("parse Ctrl+M");
    assert_eq!(kb_ctrl_m.code, KeyCode::Char('m'));
    assert_eq!(kb_ctrl_m.modifiers, KeyModifiers::CONTROL);

    // Shift modifier
    let kb_shift_tab = KeyBinding::parse("Shift+Tab").expect("parse Shift+Tab");
    assert_eq!(kb_shift_tab.code, KeyCode::Tab);
    assert_eq!(kb_shift_tab.modifiers, KeyModifiers::SHIFT);

    // BackTab
    let kb_backtab = KeyBinding::parse("BackTab").expect("parse BackTab");
    assert_eq!(kb_backtab.code, KeyCode::BackTab);
    assert!(kb_backtab.modifiers.contains(KeyModifiers::SHIFT));

    // Special keys
    assert_eq!(KeyBinding::parse("Esc").unwrap().code, KeyCode::Esc);
    assert_eq!(KeyBinding::parse("Enter").unwrap().code, KeyCode::Enter);
    assert_eq!(KeyBinding::parse("Space").unwrap().code, KeyCode::Char(' '));
    assert_eq!(KeyBinding::parse("Backspace").unwrap().code, KeyCode::Backspace);
    assert_eq!(KeyBinding::parse("Delete").unwrap().code, KeyCode::Delete);
    assert_eq!(KeyBinding::parse("F12").unwrap().code, KeyCode::F(12));
    assert_eq!(KeyBinding::parse("PageUp").unwrap().code, KeyCode::PageUp);
    assert_eq!(KeyBinding::parse("PageDown").unwrap().code, KeyCode::PageDown);

    // Multiple modifiers: Ctrl+Alt+Delete
    let multi = KeyBinding::parse("Ctrl+Alt+Delete").expect("parse multi");
    assert_eq!(multi.code, KeyCode::Delete);
    assert!(multi.modifiers.contains(KeyModifiers::CONTROL));
    assert!(multi.modifiers.contains(KeyModifiers::ALT));

    // Invalid string
    assert!(KeyBinding::parse("").is_none());
    assert!(KeyBinding::parse("UnknownKeyName").is_none());
}

#[test]
fn test_python_parity_all_primary_shortcuts() {
    let engine = ShortcutEngine::load_or_default();

    // 1. Quit: 'q' and 'Ctrl+Q'
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('q'), KeyModifiers::NONE)),
        Action::Quit
    );
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('q'), KeyModifiers::CONTROL)),
        Action::Quit
    );

    // 2. Help: '?'
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('?'), KeyModifiers::NONE)),
        Action::Help
    );
    // Shift+'?' (since ? is shift+/ on most keyboards)
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('?'), KeyModifiers::SHIFT)),
        Action::Help
    );

    // 3. Tab cycling / focus: Tab and F6
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE)),
        Action::CycleFocus
    );
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::F(6), KeyModifiers::NONE)),
        Action::NextTab
    );

    // 4. Reverse Tab / focus: Shift+Tab, BackTab, F5
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::BackTab, KeyModifiers::NONE)),
        Action::CycleFocusReverse
    );
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Tab, KeyModifiers::SHIFT)),
        Action::CycleFocusReverse
    );
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::F(5), KeyModifiers::NONE)),
        Action::PrevTab
    );

    // 5. Directive modal: 'm' and 'Ctrl+M'
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('m'), KeyModifiers::NONE)),
        Action::DirectiveModal
    );
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('m'), KeyModifiers::CONTROL)),
        Action::DirectiveModal
    );

    // 6. In-app directive editor: 'd' and 'Ctrl+D'
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('d'), KeyModifiers::NONE)),
        Action::DirectiveEditor
    );
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('d'), KeyModifiers::CONTROL)),
        Action::DirectiveEditor
    );

    // 7. Open external editor: 'o' and 'Ctrl+O'
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('o'), KeyModifiers::NONE)),
        Action::OpenExternalEditor
    );
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('o'), KeyModifiers::CONTROL)),
        Action::OpenExternalEditor
    );

    // 8. Toggle split view: 's'
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('s'), KeyModifiers::NONE)),
        Action::ToggleSplit
    );

    // 9. New worker provisioning modal: 'n'
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('n'), KeyModifiers::NONE)),
        Action::NewWorker
    );

    // 10. Direct tab selection: '1'..='9'
    for i in 1..=9 {
        let ch = char::from_digit(i, 10).unwrap();
        assert_eq!(
            engine.resolve(&KeyEvent::new(KeyCode::Char(ch), KeyModifiers::NONE)),
            Action::SelectTab((i - 1) as usize)
        );
    }
}

#[test]
fn test_unmapped_keys_pass_through_transparently() {
    let engine = ShortcutEngine::load_or_default();

    // Standard characters not in default command set must yield PassThrough
    for ch in ['a', 'b', 'c', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'p', 'r', 't', 'u', 'v', 'w', 'x', 'y', 'z'] {
        assert_eq!(
            engine.resolve(&KeyEvent::new(KeyCode::Char(ch), KeyModifiers::NONE)),
            Action::PassThrough,
            "Character '{}' should pass through to terminal PTY",
            ch
        );
    }

    // Enter, Backspace, Arrow keys must yield PassThrough
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE)),
        Action::PassThrough
    );
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Backspace, KeyModifiers::NONE)),
        Action::PassThrough
    );
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Up, KeyModifiers::NONE)),
        Action::PassThrough
    );
}

#[test]
fn test_custom_toml_shortcut_remapping_and_conflict_free() {
    let custom_toml = r#"
[general]
theme = "dracula"
tick_rate_ms = 40
default_session = "custom_qa"
default_model = "claude-3-7-sonnet"

[shortcuts]
quit = ["Ctrl+C", "Ctrl+D"]
help = ["F1"]
cycle_focus = ["Tab"]
cycle_focus_reverse = ["Shift+Tab"]
directive_modal = ["Ctrl+Space"]
directive_editor = ["F4"]
open_external_editor = ["F3"]
toggle_split = ["F2"]
new_worker = ["Ctrl+T"]
switch_tab_next = ["PageDown"]
switch_tab_prev = ["PageUp"]
tab_keys = ["F1", "F2", "F3", "F4", "F5"]
"#;

    let config: AgiConfig = toml::from_str(custom_toml).expect("Parse custom TOML");
    let engine = ShortcutEngine::new(config);

    // Verify overridden quit shortcuts
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('c'), KeyModifiers::CONTROL)),
        Action::Quit
    );
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('d'), KeyModifiers::CONTROL)),
        Action::Quit
    );

    // Verify 'q' is now pass-through since it was unmapped from Quit
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('q'), KeyModifiers::NONE)),
        Action::PassThrough
    );

    // Verify custom tab switching with PageUp / PageDown
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::PageDown, KeyModifiers::NONE)),
        Action::NextTab
    );
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::PageUp, KeyModifiers::NONE)),
        Action::PrevTab
    );

    // Verify custom new worker with Ctrl+T
    assert_eq!(
        engine.resolve(&KeyEvent::new(KeyCode::Char('t'), KeyModifiers::CONTROL)),
        Action::NewWorker
    );
}
