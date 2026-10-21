"""Unit and integration tests for the high-performance async PTY engine."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time

import psutil
import pytest

from mind.core.pty_process import (
    BasePtyProcess,
    WindowsInputSanitizer,
    reap_process_tree,
    spawn_pty,
)


# ── 1. Windows Scancode & Dead-Key Sanitizer Tests ───────────────────

def test_windows_scancode_translation() -> None:
    """Test mapping of Windows 0xE0 and 0x00 scancodes to ANSI escape sequences."""
    sanitizer = WindowsInputSanitizer()

    # Arrow keys
    assert sanitizer.sanitize_input("\xe0H") == "\x1b[A"
    assert sanitizer.sanitize_input("\xe0P") == "\x1b[B"
    assert sanitizer.sanitize_input("\xe0K") == "\x1b[D"
    assert sanitizer.sanitize_input("\xe0M") == "\x1b[C"

    # Navigation keys
    assert sanitizer.sanitize_input("\xe0G") == "\x1b[H"
    assert sanitizer.sanitize_input("\xe0O") == "\x1b[F"
    assert sanitizer.sanitize_input("\xe0I") == "\x1b[5~"
    assert sanitizer.sanitize_input("\xe0Q") == "\x1b[6~"
    assert sanitizer.sanitize_input("\xe0R") == "\x1b[2~"
    assert sanitizer.sanitize_input("\xe0S") == "\x1b[3~"

    # Function keys (0x00 and 0xE0)
    assert sanitizer.sanitize_input("\x00;") == "\x1bOP"
    assert sanitizer.sanitize_input("\x00<") == "\x1bOQ"
    assert sanitizer.sanitize_input("\xe0\x85") == "\x1b[23~"
    assert sanitizer.sanitize_input("\xe0\x86") == "\x1b[24~"

    # Ctrl + Arrows
    assert sanitizer.sanitize_input("\xe0s") == "\x1b[1;5D"
    assert sanitizer.sanitize_input("\xe0t") == "\x1b[1;5C"


def test_windows_dead_keys_and_stray_bytes() -> None:
    """Test filtering of stray 0xE0 bytes, dead-key null characters, and output leaks."""
    sanitizer = WindowsInputSanitizer()

    # Fast-path for clean text
    clean_text = "git status --short\r\n"
    assert sanitizer.sanitize_input(clean_text) == clean_text

    # Isolated or trailing stray 0xE0 bytes
    assert sanitizer.sanitize_input("\xe0") == ""
    assert sanitizer.sanitize_input("cmd\xe0") == "cmd"

    # Dead-key null markers
    assert sanitizer.sanitize_input("\x00") == ""
    assert sanitizer.sanitize_input("alpha\x00beta") == "alphabeta"

    # Stray scancode prefix followed by normal character
    assert sanitizer.sanitize_input("\xe0X") == "X"

    # Output leak sanitization
    assert sanitizer.clean_output("Prompt>\xe0H") == "Prompt>"
    assert sanitizer.clean_output("Line\x00Break") == "LineBreak"
    assert sanitizer.clean_output("Trailing\xe0") == "Trailing"


# ── 2. PTY Spawning & Lifecycle Tests ────────────────────────────────

def test_spawn_pty_basic_lifecycle() -> None:
    """Test spawning a PTY process, receiving output chunk, and clean termination."""
    output_chunks: list[str] = []

    def on_output(chunk: str) -> None:
        output_chunks.append(chunk)

    cmd = (
        ["cmd.exe", "/c", "echo PTY_LIFECYCLE_OK"]
        if sys.platform == "win32"
        else ["bash", "-c", "echo PTY_LIFECYCLE_OK"]
    )

    proc = spawn_pty(
        command=cmd,
        columns=80,
        lines=24,
        on_output=on_output,
    )

    assert proc.pid is not None
    assert proc.pid > 0

    # Allow sufficient time for ConPTY initialization and named pipe drain on Windows
    proc.wait(timeout=10.0)
    full_output = "".join(output_chunks)
    assert "PTY_LIFECYCLE_OK" in full_output
    proc.terminate()
    assert not proc.is_alive()


def test_pty_output_listeners() -> None:
    """Test dynamic registration and removal of output event listeners."""
    listener_chunks: list[str] = []

    def listener(chunk: str) -> None:
        listener_chunks.append(chunk)

    cmd = (
        ["cmd.exe", "/c", "echo LISTENER_TEST_OK"]
        if sys.platform == "win32"
        else ["bash", "-c", "echo LISTENER_TEST_OK"]
    )

    proc = spawn_pty(command=cmd, columns=80, lines=24)
    proc.add_output_listener(listener)

    proc.wait(timeout=10.0)
    assert any("LISTENER_TEST_OK" in c for c in listener_chunks)
    proc.remove_output_listener(listener)
    proc.terminate()


# ── 3. Event-Driven Async Streams (<1ms) ─────────────────────────────

def test_pty_async_stream() -> None:
    """Test event-driven async streaming of PTY output without polling."""
    async def _run() -> None:
        cmd = (
            ["cmd.exe", "/c", "echo ASYNC_STREAM_CHUNK"]
            if sys.platform == "win32"
            else ["bash", "-c", "echo ASYNC_STREAM_CHUNK"]
        )

        proc = spawn_pty(command=cmd, columns=80, lines=24)
        collected: list[str] = []

        async for chunk in proc.stream():
            collected.append(chunk)
            if "ASYNC_STREAM_CHUNK" in "".join(collected):
                break

        full_text = "".join(collected)
        assert "ASYNC_STREAM_CHUNK" in full_text
        proc.terminate()

    asyncio.run(_run())


# ── 4. Safe Signals, Interrupt, and Zombie Process Prevention ────────

def test_safe_interrupt_and_zombie_prevention() -> None:
    """Test SIGINT / Ctrl+C propagation and psutil recursive tree termination."""
    cmd = (
        ["cmd.exe", "/c", "ping 127.0.0.1 -n 10 > nul"]
        if sys.platform == "win32"
        else ["bash", "-c", "sleep 10"]
    )

    proc = spawn_pty(command=cmd, columns=80, lines=24)
    time.sleep(0.3)

    assert proc.is_alive()
    target_pid = proc.pid
    assert target_pid is not None
    assert psutil.pid_exists(target_pid)

    # Test send_interrupt
    proc.send_interrupt()
    time.sleep(0.1)

    # Test graceful recursive termination
    proc.terminate(timeout=1.0)
    time.sleep(0.2)

    assert not proc.is_alive()

    # Verify no orphan or zombie processes remain
    if psutil.pid_exists(target_pid):
        try:
            p = psutil.Process(target_pid)
            assert p.status() != psutil.STATUS_ZOMBIE, f"Process {target_pid} left as zombie"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def test_reap_process_tree_utility() -> None:
    """Test reap_process_tree helper terminates child processes directly."""
    cmd = (
        ["cmd.exe", "/c", "ping 127.0.0.1 -n 5 > nul"]
        if sys.platform == "win32"
        else ["sleep", "5"]
    )

    sub = subprocess.Popen(cmd)
    pid = sub.pid
    time.sleep(0.2)

    assert sub.poll() is None
    reap_process_tree(pid, timeout=1.0)
    time.sleep(0.2)

    assert sub.poll() is not None
