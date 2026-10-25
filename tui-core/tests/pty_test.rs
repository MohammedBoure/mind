use std::collections::HashMap;
use tui_core::pty::buffer::ScreenBuffer;
use tui_core::pty::master::PtyConfig;
use tui_core::pty::process::PtyProcess;

#[tokio::test]
async fn test_virtual_screen_buffer_ansi_parsing() {
    let mut buffer = ScreenBuffer::new(10, 40);
    assert_eq!(buffer.version(), 0);

    // Write text with ANSI colors and cursor positioning
    buffer.process_bytes(b"\x1b[1;31mHELLO\x1b[0m \x1b[32mWORLD\x1b[0m\r\n");
    assert!(buffer.version() > 0);

    let text = buffer.get_visible_text();
    assert!(text.contains("HELLO WORLD"));

    // Move cursor and write on row 2
    buffer.process_bytes(b"\x1b[2;5HMIND_TUI");
    let text2 = buffer.get_visible_text();
    assert!(text2.contains("MIND_TUI"));
}

#[tokio::test]
async fn test_screen_buffer_scrollback_and_plain_text() {
    let mut buffer = ScreenBuffer::new(3, 20);
    for i in 1..=10 {
        buffer.process_bytes(format!("Line {}\r\n", i).as_bytes());
    }

    assert!(buffer.history_count() > 0);
    let plain = buffer.render_plain_text(5);
    assert!(plain.contains("Line 10"));
}

#[tokio::test]
async fn test_pty_process_spawn_and_io() {
    let shell = if cfg!(windows) { "cmd.exe" } else { "bash" };
    let config = PtyConfig {
        command: shell.to_string(),
        args: if cfg!(windows) {
            vec!["/c".into(), "echo PTY_TEST_OK".into()]
        } else {
            vec!["-c".into(), "echo PTY_TEST_OK; sleep 0.1".into()]
        },
        cwd: None,
        env: HashMap::new(),
        rows: 24,
        cols: 80,
    };

    let pty = PtyProcess::spawn(config).expect("Failed to spawn PTY");
    assert!(pty.pid().is_some());

    // Allow process to finish writing output
    tokio::time::sleep(std::time::Duration::from_millis(300)).await;

    let output = pty.get_screen_text(10);
    assert!(output.contains("PTY_TEST_OK"));
}
