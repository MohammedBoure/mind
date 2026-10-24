use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use tui_core::session::identity::IdentityDiscovery;
use tui_core::session::session_store::SessionWorkerConfig;
use tui_core::session::SessionManager;
use tui_core::ui::{
    AgentConfigModal, AgentConfigModalAction, BottomBar, TabConfigEntry,
};

#[test]
fn test_agys_multi_instance_launcher_detection_and_command() {
    let agys_path = IdentityDiscovery::find_agys_binary();
    assert!(
        agys_path.is_some(),
        "Expected IdentityDiscovery to locate host agys launcher at ~/.local/bin/agys"
    );

    let path = agys_path.unwrap();
    assert!(path.is_file(), "Located agys launcher must be a file: {:?}", path);

    let manager = SessionManager::new();
    assert!(manager.auto_spawn_agy());

    // Verify coordinator resolves to `agys 1`
    let coord_cfg = SessionWorkerConfig {
        id: "coordinator".to_string(),
        slot_id: "agy1".to_string(),
        role: "Lead Orchestrator".to_string(),
        model: "gemini-3.8-flash-high".to_string(),
        task: None,
        command: None,
        args: None,
        env: None,
    };
    let (cmd, args) = manager.resolve_worker_command(&coord_cfg, "bash");
    assert!(cmd.ends_with("agys"), "Coordinator command must be agys: {}", cmd);
    assert_eq!(args, vec!["1".to_string()], "Coordinator argument must be slot 1");

    // Verify worker 1 resolves to `agys 11`
    let w1_cfg = SessionWorkerConfig {
        id: "worker-1".to_string(),
        slot_id: "agy11".to_string(),
        role: "Backend Logic".to_string(),
        model: "gemini-3.8-flash-high".to_string(),
        task: None,
        command: None,
        args: None,
        env: None,
    };
    let (cmd11, args11) = manager.resolve_worker_command(&w1_cfg, "bash");
    assert!(cmd11.ends_with("agys"), "Worker 1 command must be agys: {}", cmd11);
    assert_eq!(args11, vec!["11".to_string()], "Worker 1 argument must be slot 11");

    // Verify worker 2 resolves to `agys 51`
    let w2_cfg = SessionWorkerConfig {
        id: "worker-2".to_string(),
        slot_id: "agy51".to_string(),
        role: "Frontend".to_string(),
        model: "gemini-3.8-flash-high".to_string(),
        task: None,
        command: None,
        args: None,
        env: None,
    };
    let (cmd51, args51) = manager.resolve_worker_command(&w2_cfg, "bash");
    assert!(cmd51.ends_with("agys"), "Worker 2 command must be agys: {}", cmd51);
    assert_eq!(args51, vec!["51".to_string()], "Worker 2 argument must be slot 51");
}

#[test]
fn test_agent_config_modal_workflow() {
    let tabs = vec![
        TabConfigEntry::new("coordinator", "Coordinator", "agy1", "Lead Orchestrator", "gemini-3.8-flash-high", true),
        TabConfigEntry::new("worker-1", "Tab 1 (worker-1)", "agy11", "Backend Logic", "gemini-3.8-flash-high", false),
        TabConfigEntry::new("worker-2", "Tab 2 (worker-2)", "agy51", "Frontend & UI", "gemini-3.8-flash-high", false),
    ];

    let mut modal = AgentConfigModal::new(tabs);
    assert_eq!(modal.tabs.len(), 3);
    assert_eq!(modal.selected_tab_index, 0);

    // Navigate to Tab 1 (worker-1)
    modal.handle_key(&KeyEvent::new(KeyCode::Down, KeyModifiers::NONE));
    assert_eq!(modal.selected_tab_index, 1);
    assert_eq!(modal.current_tab().unwrap().tab_id, "worker-1");
    assert_eq!(modal.current_tab().unwrap().slot_id, "agy11");

    // Cycle agy slot using Space or Right
    modal.handle_key(&KeyEvent::new(KeyCode::Right, KeyModifiers::NONE));
    let new_slot = modal.current_tab().unwrap().slot_id.clone();
    assert_ne!(new_slot, "agy11", "Slot should have changed after cycle");

    // Press Ctrl+R to Save and Restart
    let action = modal.handle_key(&KeyEvent::new(KeyCode::Char('r'), KeyModifiers::CONTROL));
    match action {
        AgentConfigModalAction::Save { tab_id, new_slot_id, restart, .. } => {
            assert_eq!(tab_id, "worker-1");
            assert_eq!(new_slot_id, new_slot);
            assert!(restart, "Expected restart=true on Ctrl+R");
        }
        _ => panic!("Expected Save action with restart"),
    }

    // Press 'a' to Save & Restart All
    modal.open();
    let action_all = modal.handle_key(&KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
    assert_eq!(action_all, AgentConfigModalAction::RestartAll);
}

#[test]
fn test_bottom_bar_includes_shortcuts_and_settings_pills() {
    let normal_pills = BottomBar::normal_action_pills();
    assert!(
        normal_pills.iter().any(|p| p.key == "?" && (p.label.contains("Help") || p.label.contains("Shortcuts"))),
        "Normal pills must contain [?] Help or Shortcuts"
    );
    assert!(
        normal_pills.iter().any(|p| p.key == "e" && p.label.contains("Settings")),
        "Normal pills must contain [e] Settings"
    );
    assert!(
        normal_pills.iter().any(|p| p.key == "r" && p.label.contains("Restart")),
        "Normal pills must contain [r] Restart"
    );

    let pty_pills = BottomBar::pty_action_pills();
    assert!(
        pty_pills.iter().any(|p| p.key == "Ctrl+E" && p.label.contains("Settings")),
        "PTY pills must contain [Ctrl+E] Settings"
    );
    assert!(
        pty_pills.iter().any(|p| p.key == "Ctrl+R" && p.label.contains("Restart")),
        "PTY pills must contain [Ctrl+R] Restart"
    );
    assert!(
        pty_pills.iter().any(|p| p.key == "?" && (p.label.contains("Help") || p.label.contains("Shortcuts"))),
        "PTY pills must contain [?] Help or Shortcuts"
    );
}

#[tokio::test]
async fn test_session_manager_reassign_and_restart() {
    let manager = SessionManager::new();
    let rows = 24;
    let cols = 80;

    // Spawn coordinator with slot 1
    let coord = manager.spawn_coordinator_auto(None, rows, cols).unwrap();
    assert_eq!(coord.slot_id, "agy1");

    // Spawn worker 1 with slot 11
    let w1 = manager.spawn_worker_auto("worker-1", "agy11", None, rows, cols).unwrap();
    assert_eq!(w1.slot_id, "agy11");

    // Reassign worker 1 metadata to slot 12 without restart
    manager.reassign_worker_slot("worker-1", "agy12").unwrap();

    // Restart worker 1 with slot 12
    let restarted = manager.restart_worker_with_slot("worker-1", "agy12", rows, cols).unwrap();
    assert_eq!(restarted.slot_id, "agy12");

    // Restart all sessions
    assert!(manager.restart_all_sessions(24, 80, 20, 80).is_ok());
}
