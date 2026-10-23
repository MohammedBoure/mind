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
