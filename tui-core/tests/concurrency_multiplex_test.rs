use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use futures::future::join_all;
use tokio::time::sleep;

use tui_core::ipc::mcp_server::McpBackend;
use tui_core::session::manager::SessionManager;
use tui_core::session::worker::WorkerState;

#[tokio::test]
async fn test_concurrent_worker_spawn_and_lifecycle() {
    let manager = Arc::new(SessionManager::new());
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };

    // Concurrently spawn 8 worker sessions
    let spawn_futures = (0..8).map(|i| {
        let mgr = Arc::clone(&manager);
        let id = format!("worker-{}", i);
        let slot = format!("agy{}", i + 1);
        async move {
            mgr.spawn_session(&id, &slot, shell, vec![], None, HashMap::new(), 24, 80)
        }
    });

    let results = join_all(spawn_futures).await;
    for (i, res) in results.into_iter().enumerate() {
        assert!(res.is_ok(), "Worker {} must spawn successfully", i);
        let session = res.unwrap();
        assert!(session.pid().is_some());
        assert_eq!(*session.state.lock(), WorkerState::Running);
    }

    assert_eq!(manager.list_sessions().len(), 8);

    // Verify lookup by worker ID and slot ID
    assert!(manager.get_session("worker-3").is_some());
    assert!(manager.get_session("agy4").is_some());
}

#[tokio::test]
async fn test_concurrent_session_io_and_tab_switching() {
    let manager = Arc::new(SessionManager::new());
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };

    // Spawn 5 workers
    for i in 0..5 {
        manager
            .spawn_session(
                format!("agent-{}", i),
                format!("agy{}", i + 1),
                shell,
                vec![],
                None,
                HashMap::new(),
                24,
                80,
            )
            .expect("Spawn session");
    }

    assert_eq!(manager.list_sessions().len(), 5);

    // Concurrency Task 1: Continuous tab navigation cycling
    let mgr_cycle = Arc::clone(&manager);
    let cycle_handle = tokio::spawn(async move {
        for _ in 0..500 {
            mgr_cycle.next_session();
            let _ = mgr_cycle.active_index();
            mgr_cycle.prev_session();
            let _ = mgr_cycle.active_session();
        }
    });

    // Concurrency Task 2: Concurrent screen querying across all sessions
    let mgr_read = Arc::clone(&manager);
    let read_handle = tokio::spawn(async move {
        for _ in 0..100 {
            for session in mgr_read.list_sessions() {
                let _ = session.get_screen_text(10);
                let _ = session.version();
                let _ = session.is_idle_prompt();
            }
            sleep(Duration::from_millis(2)).await;
        }
    });

    // Concurrency Task 3: Concurrent input delivery to active session
    let mgr_write = Arc::clone(&manager);
    let write_handle = tokio::spawn(async move {
        for i in 0..50 {
            if let Some(active) = mgr_write.active_session() {
                let _ = active.send_input(&format!("echo CONCURRENCY_TICK_{}\n", i), false);
            }
            sleep(Duration::from_millis(5)).await;
        }
    });

    // Await all tasks; ensure no deadlocks occur under concurrent access
    let (r1, r2, r3) = tokio::join!(cycle_handle, read_handle, write_handle);
    assert!(r1.is_ok());
    assert!(r2.is_ok());
    assert!(r3.is_ok());
}

#[tokio::test]
async fn test_concurrent_mcp_alarms_and_injection() {
    let manager = Arc::new(SessionManager::new());
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };

    for i in 1..=4 {
        manager
            .spawn_session(
                format!("agy{}", i),
                format!("agy{}", i),
                shell,
                vec![],
                None,
                HashMap::new(),
                24,
                80,
            )
            .expect("Spawn worker");
    }

    // Fire concurrent alarm dispatches and directives through McpBackend
    let tasks = (1..=4).map(|i| {
        let mgr = Arc::clone(&manager);
        let worker_id = format!("agy{}", i);
        async move {
            let res_idle = mgr
                .notify_coordinator_worker_idle(&worker_id, "Build completed")
                .await;
            assert!(res_idle.is_ok());

            let res_help = mgr
                .notify_coordinator_help(&worker_id, "Quota warning", "HIGH")
                .await;
            assert!(res_help.is_ok());

            let res_inject = mgr
                .interrupt_and_inject(&worker_id, "coordinator", "Resume immediately", "CRITICAL")
                .await;
            assert!(res_inject.is_ok());
        }
    });

    join_all(tasks).await;

    // Verify all alarms arrived and can be drained
    let drained = manager.check_coordinator_alarms().await.expect("Drain alarms");
    assert_eq!(drained.len(), 12); // 4 workers * 3 events each = 12 alarms
}

#[tokio::test]
async fn test_concurrent_broadcast_resize() {
    let manager = Arc::new(SessionManager::new());
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };

    for i in 0..4 {
        manager
            .spawn_session(
                format!("resize-worker-{}", i),
                format!("agy{}", i + 1),
                shell,
                vec![],
                None,
                HashMap::new(),
                24,
                80,
            )
            .expect("Spawn session");
    }

    // Broadcast multiple resizes concurrently
    let mgr_clone = Arc::clone(&manager);
    let resize_handle = tokio::spawn(async move {
        for (r, c) in [(30, 100), (20, 70), (45, 120), (24, 80)] {
            mgr_clone.broadcast_resize(r, c);
            sleep(Duration::from_millis(5)).await;
        }
    });

    let _ = resize_handle.await;

    // Verify all sessions have final dimension
    for session in manager.list_sessions() {
        let buf = session.buffer();
        let guard = buf.lock();
        assert_eq!(guard.rows, 24);
        assert_eq!(guard.cols, 80);
    }
}

#[tokio::test]
async fn test_concurrent_worker_kill_and_cleanup() {
    let manager = Arc::new(SessionManager::new());
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };

    for i in 0..4 {
        manager
            .spawn_session(
                format!("kill-worker-{}", i),
                format!("agy{}", i + 1),
                shell,
                vec![],
                None,
                HashMap::new(),
                24,
                80,
            )
            .expect("Spawn session");
    }

    let sessions = manager.list_sessions();
    assert_eq!(sessions.len(), 4);

    // Concurrently terminate all workers
    let kill_futures = sessions.iter().map(|s| {
        let s_clone = Arc::clone(s);
        async move {
            let pty = s_clone.pty();
            let pty_lock = pty.lock();
            pty_lock.kill()
        }
    });

    let kill_results = join_all(kill_futures).await;
    for res in kill_results {
        assert!(res.is_ok());
    }

    sleep(Duration::from_millis(150)).await;

    // Verify sessions register as dead or exited
    for s in sessions {
        assert!(!s.is_alive());
        assert!(matches!(*s.state.lock(), WorkerState::Exited(_)));
    }
}
