"""Tests for credential isolation, token persistence, and slot management."""

import json
import os
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

from mind.core.credentials import (
    CrossProcessCredentialLock,
    extract_email_from_token,
    get_slot_token_path,
    restore_slot_credential,
    setup_slot_env,
)
from mind.core.terminal_manager import TerminalManager, WorkerSession


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


def test_setup_slot_env(tmp_path):
    """Verify slot environment variables and directory isolation."""
    slot = 3
    base_env = {"EXISTING_VAR": "val123"}
    env = setup_slot_env(slot, base_env=base_env)

    assert env["EXISTING_VAR"] == "val123"
    assert env["AGY_SLOT"] == "3"
    assert env["AGY_TOKEN_FILE"].endswith("agy3.token")
    assert "instances" in env["ANTIGRAVITY_GEMINI_DIR"]
    assert "agy3" in env["ANTIGRAVITY_GEMINI_DIR"]
    assert "antigravity-cli" in env["ANTIGRAVITY_APP_DATA_DIR"]


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
