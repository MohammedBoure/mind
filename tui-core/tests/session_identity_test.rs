use std::fs;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use tempfile::tempdir;

use tui_core::session::{
    Action, AgiConfig, IdentityDiscovery, SessionRecord, SessionStore, SessionWorkerConfig,
    ShortcutEngine,
};

#[test]
fn test_session_store_lifecycle_and_persistence() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let store = SessionStore::with_dir(tmp.path().join("sessions"));

    // 1. Initially empty
    let list = store.list_sessions().expect("List sessions");
    assert_eq!(list.len(), 0);

    // 2. Create and save a session
    let mut session = SessionRecord::new("test_swarm", "Automated QA and systems verification");
    session.add_worker(SessionWorkerConfig {
        id: "coordinator".to_string(),
        slot_id: "agy1".to_string(),
        role: "Lead Orchestrator".to_string(),
        model: "gemini-3.8-flash-high".to_string(),
        task: Some("Verification of session store".to_string()),
        command: None,
        args: None,
        env: None,
    });
    session.add_worker(SessionWorkerConfig {
        id: "worker-backend".to_string(),
        slot_id: "agy11".to_string(),
        role: "Backend Logic & Systems".to_string(),
        model: "gemini-3.8-flash-high".to_string(),
        task: Some("Storage engine testing".to_string()),
        command: None,
        args: None,
        env: None,
    });

    let saved_path = store.save_session(&session).expect("Save session");
    assert!(saved_path.is_file());
    assert_eq!(saved_path.file_name().unwrap(), "test_swarm.json");

    // 3. Load back from disk
    let loaded = store.get_session("test_swarm").expect("Get session").expect("Session exists");
    assert_eq!(loaded.name, "test_swarm");
    assert_eq!(loaded.agent_count, 2);
    assert_eq!(loaded.workers.len(), 2);
    assert_eq!(loaded.workers[0].slot_id, "agy1");
    assert_eq!(loaded.workers[1].slot_id, "agy11");

    // 4. Touch activity
    store.touch_activity("test_swarm", 10, 5).expect("Touch activity");
    let touched = store.get_session("test_swarm").unwrap().unwrap();
    assert_eq!(touched.total_steps, 10);
    assert_eq!(touched.total_interactions, 5);

    // 5. Create a second session with workers and check listing order
    let mut s2 = SessionRecord::new("alpha_session", "Alpha testing");
    s2.add_worker(SessionWorkerConfig {
        id: "worker-1".to_string(),
        slot_id: "agy2".to_string(),
        role: "Worker".to_string(),
        model: "gemini".to_string(),
        task: None,
        command: None,
        args: None,
        env: None,
    });
    store.save_session(&s2).expect("Save s2");
    let all = store.list_sessions().expect("List sessions");
    assert_eq!(all.len(), 2);

    // 6. Prune / clean
    let mut stale = SessionRecord::new("stale_session", "Old session");
    stale.active = false;
    stale.add_worker(SessionWorkerConfig {
        id: "worker-stale".to_string(),
        slot_id: "agy3".to_string(),
        role: "Worker".to_string(),
        model: "gemini".to_string(),
        task: None,
        command: None,
        args: None,
        env: None,
    });
    store.save_session(&stale).expect("Save stale");
    assert_eq!(store.list_sessions().unwrap().len(), 3);

    let cleaned = store.clean_sessions().expect("Clean sessions");
    assert_eq!(cleaned, 1);
    assert!(store.get_session("stale_session").unwrap().is_none());

    // 7. Delete explicitly
    let deleted = store.delete_session("test_swarm").expect("Delete session");
    assert!(deleted);
    assert!(store.get_session("test_swarm").unwrap().is_none());
}

#[test]
fn test_agent_slot_discovery_in_custom_directory() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let instances = tmp.path().join("agy-instances");
    fs::create_dir_all(&instances).unwrap();

    // Create mock agy42 slot (not in agent_assignments.json to test GEMINI.md parsing)
    let agy42_dir = instances.join("agy42");
    let gemini_dir = agy42_dir.join(".gemini");
    let cli_dir = gemini_dir.join("antigravity-cli");
    fs::create_dir_all(&cli_dir).unwrap();

    // Mock GEMINI.md
    fs::write(
        gemini_dir.join("GEMINI.md"),
        "# Role & Guidelines: Systems & Math Specialist (agy11 - agy50)\nSome rules here\n",
    )
    .unwrap();

    // Mock settings.json
    fs::write(
        cli_dir.join("settings.json"),
        r#"{"model": "Gemini 3.8 Flash (Low)"}"#,
    )
    .unwrap();

    // Mock token.json
    fs::write(
        agy42_dir.join("token.json"),
        r#"{"email": "agent42@test.com"}"#,
    )
    .unwrap();

    // Create mock agy52 slot
    let agy52_dir = instances.join("agy52");
    fs::create_dir_all(&agy52_dir).unwrap();

    let slots = IdentityDiscovery::discover_slots_in(&instances);
    assert_eq!(slots.len(), 2);

    let s42 = slots.iter().find(|s| s.slot_id == 42).expect("Slot 42 found");
    assert_eq!(s42.name, "agy42");
    assert_eq!(s42.role, "Systems & Math Specialist");
    assert_eq!(s42.model, "Gemini 3.8 Flash (Low)");
    assert_eq!(s42.email.as_deref(), Some("agent42@test.com"));
    assert!(s42.has_token);

    // Test environment isolation generation
    let env = IdentityDiscovery::build_slot_isolation_env(s42);
    assert_eq!(env.get("AGY_SLOT").unwrap(), "42");
    assert!(env.get("HOME").unwrap().ends_with("agy42"));
    assert!(env.get("USERPROFILE").unwrap().ends_with("agy42"));
    assert!(env.get("ANTIGRAVITY_APP_DATA_DIR").unwrap().contains("antigravity-cli"));
}

#[test]
fn test_real_system_agent_slots_discovery() {
    let slots = IdentityDiscovery::discover_slots();
    // System has /home/pluto/.local/share/agy-instances with agy1, agy11, agy51, agy100, agy151
    assert!(!slots.is_empty(), "Expected real agy instances to be discovered on host");
    assert!(slots.iter().any(|s| s.slot_id == 11), "Expected agy11 on host");
    assert!(slots.iter().any(|s| s.slot_id == 51), "Expected agy51 on host");

    let slot11 = IdentityDiscovery::find_slot("agy11").expect("find_slot agy11");
    assert_eq!(slot11.slot_id, 11);
    assert!(slot11.role.contains("Backend") || slot11.role.contains("Systems"));
}

#[test]
fn test_shortcut_engine_exact_python_parity() {
    let engine = ShortcutEngine::load_or_default();

    // 1. 'q' -> Quit
    let q_event = KeyEvent::new(KeyCode::Char('q'), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&q_event), Action::Quit);

    // 2. '?' -> Help
    let help_event = KeyEvent::new(KeyCode::Char('?'), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&help_event), Action::Help);

    // 3. Tab -> CycleFocus / NextTab
    let tab_event = KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE);
    assert_eq!(engine.resolve(&tab_event), Action::CycleFocus);

    // 4. Shift+Tab / BackTab -> CycleFocusReverse / PrevTab
    let backtab_event = KeyEvent::new(KeyCode::BackTab, KeyModifiers::NONE);
    assert_eq!(engine.resolve(&backtab_event), Action::CycleFocusReverse);

    // 5. m / Ctrl+M -> DirectiveModal
    let m_event = KeyEvent::new(KeyCode::Char('m'), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&m_event), Action::DirectiveModal);
    let ctrl_m_event = KeyEvent::new(KeyCode::Char('m'), KeyModifiers::CONTROL);
    assert_eq!(engine.resolve(&ctrl_m_event), Action::DirectiveModal);

    // 6. d / Ctrl+D -> DirectiveEditor
    let d_event = KeyEvent::new(KeyCode::Char('d'), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&d_event), Action::DirectiveEditor);
    let ctrl_d_event = KeyEvent::new(KeyCode::Char('d'), KeyModifiers::CONTROL);
    assert_eq!(engine.resolve(&ctrl_d_event), Action::DirectiveEditor);

    // 7. o / Ctrl+O -> OpenExternalEditor
    let o_event = KeyEvent::new(KeyCode::Char('o'), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&o_event), Action::OpenExternalEditor);
    let ctrl_o_event = KeyEvent::new(KeyCode::Char('o'), KeyModifiers::CONTROL);
    assert_eq!(engine.resolve(&ctrl_o_event), Action::OpenExternalEditor);

    // 8. s -> ToggleSplit
    let s_event = KeyEvent::new(KeyCode::Char('s'), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&s_event), Action::ToggleSplit);

    // 9. n -> NewWorker
    let n_event = KeyEvent::new(KeyCode::Char('n'), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&n_event), Action::NewWorker);

    // 10. Configurable Tab keys: 1..9
    let one_event = KeyEvent::new(KeyCode::Char('1'), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&one_event), Action::SelectTab(0));
    let five_event = KeyEvent::new(KeyCode::Char('5'), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&five_event), Action::SelectTab(4));

    // 11. Unmapped letter -> PassThrough
    let x_event = KeyEvent::new(KeyCode::Char('x'), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&x_event), Action::PassThrough);
}

#[test]
fn test_shortcut_engine_custom_toml_configuration() {
    let toml_content = r#"
[general]
theme = "high_contrast"
tick_rate_ms = 30
default_session = "custom_fleet"
default_model = "gemini-3.8-flash-high"

[shortcuts]
quit = ["Ctrl+X"]
help = ["F1"]
cycle_focus = ["F6"]
cycle_focus_reverse = ["F5"]
directive_modal = ["Ctrl+I"]
directive_editor = ["Ctrl+E"]
open_external_editor = ["Ctrl+O"]
toggle_split = ["Ctrl+S"]
new_worker = ["Ctrl+N"]
switch_tab_next = ["F6"]
switch_tab_prev = ["F5"]
tab_keys = ["F7", "F8", "F9"]
"#;

    let config: AgiConfig = toml::from_str(toml_content).expect("Parse custom toml");
    let engine = ShortcutEngine::new(config);

    assert_eq!(engine.config().general.theme, "high_contrast");
    assert_eq!(engine.config().general.tick_rate_ms, 30);
    assert_eq!(engine.config().general.default_session.as_deref(), Some("custom_fleet"));

    // Verify F1 triggers Help
    let f1_event = KeyEvent::new(KeyCode::F(1), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&f1_event), Action::Help);

    // Verify Ctrl+X triggers Quit
    let ctrl_x = KeyEvent::new(KeyCode::Char('x'), KeyModifiers::CONTROL);
    assert_eq!(engine.resolve(&ctrl_x), Action::Quit);

    // Verify F7 triggers SelectTab(0)
    let f7_event = KeyEvent::new(KeyCode::F(7), KeyModifiers::NONE);
    assert_eq!(engine.resolve(&f7_event), Action::SelectTab(0));
}
