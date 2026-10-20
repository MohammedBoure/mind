"""Tests for credential isolation, token persistence, and slot management."""

import json
import os
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest
from textual import events

from mind.core.credentials import (
    CrossProcessCredentialLock,
    extract_email_from_token,
    get_slot_token_path,
    restore_slot_credential,
    setup_slot_env,
)
from mind.core.terminal_manager import TerminalManager, WorkerSession
from mind.ui.terminal_tab import TerminalScreenWidget


def test_extract_email_from_token_plain_and_bom():
    """Verify email extraction works on plain JSON and UTF-8 BOM tokens."""
    payload_json = json.dumps({
        "token": {"access_token": "mock_access_token"},
        "id_token": "header.eyJlbWFpbCI6ICJ1c2VyMUBnbWFpbC5jb20iLCAibmFtZSI6ICJVc2VyIDEifQ==.signature",
    })
    # Plain text
    assert extract_email_from_token(payload_json) == "user1@gmail.com"

    # Bytes with UTF-8 BOM
    bom_bytes = b"\xef\xbb\xbf" + payload_json.encode("utf-8")
    assert extract_email_from_token(bom_bytes) == "user1@gmail.com"

    # Invalid / empty returns None
    assert extract_email_from_token("") is None
    assert extract_email_from_token("not a json") is None


def test_get_slot_token_path():
    """Verify slot token path computation."""
    path = get_slot_token_path(1)
    assert path.name == "agy1.token"
    assert path.parent == Path.home() / ".gemini" / "tokens"


def test_setup_slot_env():
    """Verify slot environment variables and removal of broken directory overrides."""
    slot = 3
    base_env = {"EXISTING_VAR": "val123", "ANTIGRAVITY_GEMINI_DIR": "old/path"}
    env = setup_slot_env(slot, base_env=base_env)

    assert env["EXISTING_VAR"] == "val123"
    assert env["AGY_SLOT"] == "3"
    assert env["AGY_TOKEN_FILE"].endswith("agy3.token")
    assert "ANTIGRAVITY_GEMINI_DIR" not in env
    assert "ANTIGRAVITY_APP_DATA_DIR" not in env


def test_worker_session_slot_deduction():
    """Verify WorkerSession accurately deduces slot numbers from names, roles, and IDs."""
    # 1. Coordinator defaults to slot 1
    session_coord = WorkerSession(worker_id="coordinator", name="Primary-Coordinator", role="coordinator")
    assert session_coord.get_slot_id() == 1
    assert session_coord.assigned_agent == "agy1"

    # 2. Worker 1 defaults to agy1 / slot 1
    session_1 = WorkerSession(worker_id="1", name="Worker-1")
    assert session_1.get_slot_id() == 1
    assert session_1.assigned_agent == "agy1"

    # 3. Worker 2 defaults to agy2 / slot 2
    session_2 = WorkerSession(worker_id="2", name="Worker-2")
    assert session_2.get_slot_id() == 2
    assert session_2.assigned_agent == "agy2"

    # 4. Explicit assigned agent overrides
    session_custom = WorkerSession(worker_id="tab-x", name="Worker-X", assigned_agent="agy5")
    assert session_custom.get_slot_id() == 5
    assert session_custom.assigned_agent == "agy5"


def test_terminal_manager_create_worker_auto_slots():
    """Verify TerminalManager populates default assigned_agent and slot isolation."""
    mgr = TerminalManager()
    w1 = mgr.create_worker(worker_id="1", name="Worker-1", autostart=False)
    assert w1.assigned_agent == "agy1"
    assert w1.get_slot_id() == 1

    w2 = mgr.create_worker(worker_id="2", name="Worker-2", autostart=False)
    assert w2.assigned_agent == "agy2"
    assert w2.get_slot_id() == 2


def test_cross_process_credential_lock():
    """Test entering and exiting cross process credential lock without exceptions."""
    with CrossProcessCredentialLock() as lock:
        assert lock is not None


def test_graceful_shutdown_preserves_tokens():
    """Verify terminate and stop_all do not delete or modify saved slot token files."""
    token_file = Path.home() / ".gemini" / "tokens" / "agy1.token"
    existing_content = token_file.read_bytes() if token_file.exists() else None

    mgr = TerminalManager()
    w = mgr.create_worker(worker_id="test-term-1", autostart=False)
    w.terminate()
    mgr.stop_all()

    if existing_content is not None:
        assert token_file.exists()
        assert token_file.read_bytes() == existing_content


def test_modifier_and_scancode_filtering():
    """Verify standalone shift/modifiers and rogue 0xE0 / 'à' scancodes are filtered."""
    session = WorkerSession(worker_id="test-filter")
    written = []
    session.write = lambda text, press_enter=False: written.append(text)

    widget = TerminalScreenWidget(worker_session=session)
    widget.mode = "PTY_INTERACT"

    # 1. Shift key alone should NOT write anything
    ev_shift = events.Key("shift", "shift")
    widget.on_key(ev_shift)
    assert len(written) == 0

    # 2. Rogue 'à' from scancode prefix 0xE0 should be ignored when key is not 'à'
    ev_rogue = events.Key("shift", "à")
    widget.on_key(ev_rogue)
    assert len(written) == 0

    # 3. Legitimate 'à' character typed directly should be written
    ev_legit = events.Key("à", "à")
    widget.on_key(ev_legit)
    assert written == ["à"]
    written.clear()

    # 4. Clipboard paste with Ctrl+V strips rogue 0xE0
    with patch("mind.ui.terminal_tab.get_clipboard_text", return_value="\xe0hello world"):
        ev_paste = events.Key("ctrl+v", "")
        widget.on_key(ev_paste)
        assert written == ["hello world"]
