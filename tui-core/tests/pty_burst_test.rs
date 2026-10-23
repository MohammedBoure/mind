use std::collections::HashMap;
use std::time::Duration;
use tokio::time::sleep;

use tui_core::pty::buffer::ScreenBuffer;
use tui_core::pty::master::PtyConfig;
use tui_core::pty::process::PtyProcess;

#[tokio::test]
async fn test_screen_buffer_rapid_data_burst() {
    let mut buffer = ScreenBuffer::new(24, 80);
    let initial_version = buffer.version();
    assert_eq!(initial_version, 0);

    // Rapidly inject 2,000 bursts containing mixed ANSI escape sequences
    let mut prev_version = initial_version;
    for i in 0..2000 {
        let burst = format!(
            "\x1b[31;1mBurst #{}\x1b[0m \x1b[32mstatus=OK\x1b[0m [DATA: {:08x}]\r\n",
            i, i * 31337
        );
        buffer.process_bytes(burst.as_bytes());

        let current_version = buffer.version();
        assert!(
            current_version > prev_version,
            "Version must monotonically increase on burst {}",
            i
        );
        prev_version = current_version;
    }

    assert!(buffer.history_count() > 0, "Scrollback must have buffered past rows");
    let visible = buffer.get_visible_text();
    assert!(visible.contains("Burst #1999"), "Latest burst must appear on visible screen");
    assert!(visible.contains("status=OK"));

    // Verify plain text retrieval with limit
    let tail_lines = buffer.render_plain_text(5);
    let count = tail_lines.lines().count();
    assert!(count <= 5, "render_plain_text(5) must yield at most 5 lines");
    assert!(tail_lines.contains("Burst #1999"));
}

#[tokio::test]
async fn test_screen_buffer_utf8_split_chunks() {
    let mut buffer = ScreenBuffer::new(5, 40);

    // Arabic text (multi-byte UTF-8): "مرحبا بالعالم"
    let text = "مرحبا بالعالم";
    let bytes = text.as_bytes();

    // Feed bytes one-by-one to test split multibyte handling in parser
    for &b in bytes {
        buffer.process_bytes(&[b]);
    }
    buffer.process_bytes(b"\r\n");

    let visible = buffer.get_visible_text();
    // Verify non-empty and no panic occurred during fragmented ingestion
    assert!(!visible.trim().is_empty());

    // Emojis and Box Drawing characters
    let symbols = "🚀 Rust TUI │ ⚡ Multi-Agent Swarm │ 🦀 Ratatui\r\n";
    for chunk in symbols.as_bytes().chunks(3) {
        buffer.process_bytes(chunk);
    }
    let plain = buffer.render_plain_text(5);
    assert!(plain.contains("Rust TUI"));
    assert!(plain.contains("Multi-Agent Swarm"));
}

#[tokio::test]
async fn test_pty_event_loop_rapid_burst_stress() {
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };
    let burst_cmd = if cfg!(windows) {
        vec!["/c".into(), "for /L %i in (1,1,200) do @echo BURST_PACKET_%i".into()]
    } else {
        vec!["-c".into(), "for i in $(seq 1 300); do echo \"BURST_PACKET_$i\"; done".into()]
    };

    let config = PtyConfig {
        command: shell.to_string(),
        args: burst_cmd,
        cwd: None,
        env: HashMap::new(),
        rows: 24,
        cols: 80,
    };

    let pty = PtyProcess::spawn(config).expect("Spawn burst PTY");
    assert!(pty.pid().is_some());

    // Allow the background reader thread and async ingestion task to absorb the 300 packets
    let mut received_all = false;
    for _ in 0..40 {
        sleep(Duration::from_millis(50)).await;
        let text = pty.get_screen_text(20);
        if text.contains("BURST_PACKET_300") || (cfg!(windows) && text.contains("BURST_PACKET_200")) {
            received_all = true;
            break;
        }
    }

    assert!(received_all, "PTY async channel should have absorbed full burst stream");
    assert!(pty.version() > 0, "Buffer version must increment during burst ingestion");
}

#[tokio::test]
async fn test_pty_burst_with_interactive_interrupt() {
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };
    let long_loop_cmd = if cfg!(windows) {
        vec!["/c".into(), "for /L %i in (1,0,2) do @(echo RUNNING_LOOP & ping 127.0.0.1 -n 1 >nul)".into()]
    } else {
        vec!["-c".into(), "while true; do echo 'STREAMING_HEARTBEAT'; sleep 0.05; done".into()]
    };

    let config = PtyConfig {
        command: shell.to_string(),
        args: long_loop_cmd,
        cwd: None,
        env: HashMap::new(),
        rows: 24,
        cols: 80,
    };

    let pty = PtyProcess::spawn(config).expect("Spawn streaming PTY");

    // Wait until stream starts
    let mut started = false;
    for _ in 0..20 {
        sleep(Duration::from_millis(50)).await;
        let text = pty.get_screen_text(10);
        if text.contains("STREAMING_HEARTBEAT") || text.contains("RUNNING_LOOP") {
            started = true;
            break;
        }
    }
    assert!(started, "Stream should start outputting");

    // Send SIGINT / Ctrl+C interrupt
    pty.send_interrupt().expect("Send interrupt");
    sleep(Duration::from_millis(200)).await;

    let v_at_interrupt = pty.version();
    sleep(Duration::from_millis(200)).await;
    let v_after = pty.version();

    // After interruption, version updates should stabilize (no rapid stream updates)
    assert!(
        v_after.saturating_sub(v_at_interrupt) <= 2,
        "Stream should halt or settle immediately after SIGINT"
    );

    // Clean up
    let _ = pty.kill();
}

#[tokio::test]
async fn test_pty_burst_during_dynamic_resize() {
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };
    let config = PtyConfig {
        command: shell.to_string(),
        args: if cfg!(windows) {
            vec!["/c".into(), "for /L %i in (1,1,100) do @echo RESIZE_BURST_%i".into()]
        } else {
            vec!["-c".into(), "for i in $(seq 1 150); do echo \"RESIZE_BURST_$i\"; usleep 2000; done".into()]
        },
        cwd: None,
        env: HashMap::new(),
        rows: 24,
        cols: 80,
    };

    let mut pty = PtyProcess::spawn(config).expect("Spawn resize PTY");

    // Trigger rapid resizes while burst I/O is streaming
    for (r, c) in [(30, 100), (15, 60), (40, 120), (24, 80)] {
        pty.resize(r, c).expect("Resize should succeed during active I/O");
        sleep(Duration::from_millis(30)).await;
    }

    sleep(Duration::from_millis(200)).await;
    let text = pty.get_screen_text(10);
    assert!(!text.is_empty(), "PTY buffer should remain valid and active across resizes");
}
