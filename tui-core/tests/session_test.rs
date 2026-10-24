use std::collections::HashMap;
use tui_core::session::SessionManager;

#[tokio::test]
async fn test_session_manager_lifecycle_and_switching() {
    let manager = SessionManager::new();
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };

    let s1 = manager
        .spawn_session("coordinator", "agy1", shell, vec![], None, HashMap::new(), 24, 80)
        .expect("Spawn session 1");
    let _s2 = manager
        .spawn_session("worker1", "agy2", shell, vec![], None, HashMap::new(), 24, 80)
        .expect("Spawn session 2");

    assert_eq!(manager.list_sessions().len(), 2);
    assert_eq!(manager.active_index(), 0);

    // Switch next session
    manager.next_session();
    assert_eq!(manager.active_index(), 1);
    assert_eq!(manager.active_session().unwrap().id, "worker1");

    // Cycle back
    manager.next_session();
    assert_eq!(manager.active_index(), 0);
    assert_eq!(manager.active_session().unwrap().id, "coordinator");

    // Test send input
    s1.send_input("echo HELLO_SESSION\n", true).expect("Send input");
    tokio::time::sleep(std::time::Duration::from_millis(300)).await;
    assert!(s1.get_screen_text(5).contains("HELLO_SESSION"));

    // Test direct index selection (Alt+1, Alt+2)
    assert!(manager.select_index(1));
    assert_eq!(manager.active_index(), 1);
    assert_eq!(manager.active_session().unwrap().id, "worker1");

    assert!(manager.select_index(0));
    assert_eq!(manager.active_index(), 0);
    assert_eq!(manager.active_session().unwrap().id, "coordinator");

    assert!(!manager.select_index(99)); // Out of bounds
    assert_eq!(manager.active_index(), 0);

    // Test previous session (Shift+Tab)
    manager.prev_session();
    assert_eq!(manager.active_index(), 1);
    manager.prev_session();
    assert_eq!(manager.active_index(), 0);

    // Test broadcast resize propagation
    manager.broadcast_resize(35, 100);
    for session in manager.list_sessions() {
        let pty = session.pty.lock();
        let buf = pty.buffer();
        let b = buf.lock();
        assert_eq!(b.rows, 35);
        assert_eq!(b.cols, 100);
    }

    // Clean shutdown of all sessions
    manager.shutdown_all();
}

#[tokio::test]
async fn test_dual_pane_coordinator_worker_architecture_and_modal_state() {
    use tui_core::session::{AppMode, FocusedPane};

    let manager = SessionManager::new();
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };

    // 1. Initial State: Mode is NORMAL, focused on Coordinator
    assert_eq!(manager.app_mode(), AppMode::Normal);
    assert_eq!(manager.focused_pane(), FocusedPane::Coordinator);

    // 2. Spawn Coordinator (slot 1 / agy1)
    let coord = manager
        .spawn_session("coordinator", "agy1", shell, vec![], None, HashMap::new(), 24, 80)
        .expect("Spawn coordinator");
    assert_eq!(coord.id, "coordinator");
    assert!(manager.coordinator().is_some());
    assert_eq!(manager.coordinator().unwrap().id, "coordinator");

    // 3. Spawn Worker tabs
    let w1 = manager
        .spawn_session("worker1", "agy2", shell, vec![], None, HashMap::new(), 24, 80)
        .expect("Spawn worker1");
    let w2 = manager
        .spawn_session("worker2", "agy3", shell, vec![], None, HashMap::new(), 24, 80)
        .expect("Spawn worker2");
    let w3 = manager
        .spawn_session("worker3", "agy4", shell, vec![], None, HashMap::new(), 24, 80)
        .expect("Spawn worker3");

    assert_eq!(manager.workers().len(), 3);
    assert_eq!(w1.id, "worker1");
    assert_eq!(w2.id, "worker2");
    assert_eq!(w3.id, "worker3");

    // Initially focused on coordinator
    assert_eq!(manager.focused_pane(), FocusedPane::Coordinator);
    assert_eq!(manager.active_session().unwrap().id, "coordinator");

    // 4. Tab / Shift+Tab switches active pane focus between Coordinator and Worker pane
    manager.switch_pane_focus();
    assert_eq!(manager.focused_pane(), FocusedPane::Workers(0));
    assert_eq!(manager.active_session().unwrap().id, "worker1");

    manager.switch_pane_focus();
    assert_eq!(manager.focused_pane(), FocusedPane::Coordinator);
    assert_eq!(manager.active_session().unwrap().id, "coordinator");

    // 5. '1'..'9': Fast jumps to worker tab #1..#9 in the workers pane
    assert!(manager.jump_worker_tab(2));
    assert_eq!(manager.focused_pane(), FocusedPane::Workers(1));
    assert_eq!(manager.active_session().unwrap().id, "worker2");

    assert!(manager.jump_worker_tab(3));
    assert_eq!(manager.focused_pane(), FocusedPane::Workers(2));
    assert_eq!(manager.active_session().unwrap().id, "worker3");

    assert!(!manager.jump_worker_tab(99)); // Out of bounds
    assert_eq!(manager.focused_pane(), FocusedPane::Workers(2));

    // 6. 'h' / 'l': Cycles worker tabs in workers pane left / right
    manager.prev_worker_tab(); // 'h': 2 -> 1
    assert_eq!(manager.focused_pane(), FocusedPane::Workers(1));
    assert_eq!(manager.active_session().unwrap().id, "worker2");

    manager.prev_worker_tab(); // 'h': 1 -> 0
    assert_eq!(manager.focused_pane(), FocusedPane::Workers(0));
    assert_eq!(manager.active_session().unwrap().id, "worker1");

    manager.next_worker_tab(); // 'l': 0 -> 1
    assert_eq!(manager.focused_pane(), FocusedPane::Workers(1));
    assert_eq!(manager.active_session().unwrap().id, "worker2");

    // 7. Dual Vim-Style Mode State Machine (NORMAL vs PTY_INTERACT)
    manager.enter_pty();
    assert_eq!(manager.app_mode(), AppMode::PtyInteract);
    assert_eq!(manager.app_mode().as_str(), "PTY_INTERACT");

    manager.enter_normal();
    assert_eq!(manager.app_mode(), AppMode::Normal);
    assert_eq!(manager.app_mode().as_str(), "NORMAL");

    // 8. Close active worker tab ('x')
    let closed = manager.close_active_worker().expect("Close worker");
    assert!(closed.is_some());
    assert_eq!(closed.unwrap().id, "worker2");
    assert_eq!(manager.workers().len(), 2);

    manager.shutdown_all();
}
