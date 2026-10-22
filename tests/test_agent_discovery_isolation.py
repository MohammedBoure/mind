"""Tests for Dynamic Agent Discovery and Slot Isolation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from mind.core.agent_discovery import (
    SlotInfo,
    build_slot_isolation_env,
    detect_agys_installed,
    discover_agent_slots,
    discover_system_agents,
    generate_agys_command,
    get_agent_preset_config,
    get_real_user_home,
    get_slot_instance_dir,
    get_slot_instance_token_path,
    get_slot_token_path,
    initialize_slot_instance,
    parse_slot_id,
    verify_agys_compatibility,
)
from mind.core.auth import TokenManager
import mind.core.credentials as credentials


def test_parse_slot_id() -> None:
    """Verify parsing slot indices from diverse formats."""
    assert parse_slot_id(1) == 1
    assert parse_slot_id(10) == 10
    assert parse_slot_id("agy1") == 1
    assert parse_slot_id("agy15") == 15
    assert parse_slot_id("Worker-3") == 3
    assert parse_slot_id("slot4") == 4
    assert parse_slot_id("coordinator") == 1
    assert parse_slot_id(None) == 1
    assert parse_slot_id("") == 1


def test_get_real_user_home_anti_nesting() -> None:
    """Verify that get_real_user_home resolves the real home and avoids nested instances."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_home = Path(tmp_dir) / "testuser"
        fake_home.mkdir(parents=True, exist_ok=True)

        # Simulate a process currently running inside an isolated slot
        nested_slot_path = fake_home / ".gemini" / "instances" / "agy1"
        nested_slot_path.mkdir(parents=True, exist_ok=True)

        with patch.dict(os.environ, {"USERPROFILE": str(nested_slot_path), "HOME": str(nested_slot_path)}, clear=False):
            resolved = get_real_user_home()
            # Must recover the root fake_home, not the nested agy1 directory!
            assert resolved.resolve() == fake_home.resolve()

            # Generating a slot instance for agy2 must not be nested inside agy1
            slot2_dir = get_slot_instance_dir(2)
            assert slot2_dir.resolve() == (fake_home / ".gemini" / "instances" / "agy2").resolve()


def test_initialize_slot_instance() -> None:
    """Verify initializing a slot directory structure matching PowerShell agys."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_home = Path(tmp_dir)
        tokens_dir = fake_home / ".gemini" / "tokens"
        tokens_dir.mkdir(parents=True, exist_ok=True)

        # Legacy token setup
        legacy_token = tokens_dir / "agy2.token"
        legacy_token.write_text('{"token": "secret_2"}', encoding="utf-8")

        # Global settings setup
        global_cli = fake_home / ".gemini" / "antigravity-cli"
        global_cli.mkdir(parents=True, exist_ok=True)
        (global_cli / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")

        res = initialize_slot_instance(slot=2, real_home=fake_home)
        assert res["slot_id"] == 2
        assert res["slot_name"] == "agy2"
        assert res["is_new"] is True

        instance_dir = res["instance_dir"]
        assert instance_dir.exists()
        assert (instance_dir / ".gemini" / "antigravity-cli" / "conversations").exists()

        # Token migrated to token.json
        instance_token = res["instance_token"]
        assert instance_token.exists()
        assert "secret_2" in instance_token.read_text(encoding="utf-8")

        # Settings copied
        slot_settings = instance_dir / ".gemini" / "antigravity-cli" / "settings.json"
        assert slot_settings.exists()
        assert "dark" in slot_settings.read_text(encoding="utf-8")


def test_build_slot_isolation_env() -> None:
    """Verify slot environment variables isolation and conflict removal."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_home = Path(tmp_dir)
        base_env = {
            "EXISTING_KEY": "kept_value",
            "ANTIGRAVITY_GEMINI_DIR": "override/path/bad",
            "ANTIGRAVITY_APP_DATA_DIR": "another/bad/path",
        }

        env = build_slot_isolation_env(
            slot="agy3",
            base_env=base_env,
            auto_init=True,
            real_home=fake_home,
        )

        assert env["EXISTING_KEY"] == "kept_value"
        assert env["AGY_SLOT"] == "3"

        expected_inst_dir = str(fake_home / ".gemini" / "instances" / "agy3")
        assert env["USERPROFILE"] == expected_inst_dir
        assert env["HOME"] == expected_inst_dir
        assert env["AGY_INSTANCE_DIR"] == expected_inst_dir
        assert env["AGY_TOKEN_FILE"].endswith("agy3.token")

        # Broken overrides stripped
        assert "ANTIGRAVITY_GEMINI_DIR" not in env
        assert "ANTIGRAVITY_APP_DATA_DIR" not in env


def test_token_manager_and_credentials_facade_integration() -> None:
    """Verify TokenManager and credentials.setup_slot_env produce complete slot isolation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_home = Path(tmp_dir)
        instances_dir = fake_home / ".gemini" / "instances"
        tokens_dir = fake_home / ".gemini" / "tokens"

        mgr = TokenManager(instances_dir=instances_dir, tokens_dir=tokens_dir)
        env = mgr.build_slot_environment(slot=1, base_env={"BASE": "1"})

        assert env["BASE"] == "1"
        assert env["AGY_SLOT"] == "1"
        assert env["USERPROFILE"] == str(instances_dir / "agy1")
        assert env["HOME"] == str(instances_dir / "agy1")
        assert env["AGY_INSTANCE_DIR"] == str(instances_dir / "agy1")
        assert env["AGY_TOKEN_FILE"] == str(tokens_dir / "agy1.token")

        # Legacy credentials facade
        facade_env = credentials.setup_slot_env(slot=2, base_env={"FA_BASE": "2"})
        assert facade_env["FA_BASE"] == "2"
        assert facade_env["AGY_SLOT"] == "2"
        assert "USERPROFILE" in facade_env
        assert "HOME" in facade_env
        assert "AGY_INSTANCE_DIR" in facade_env
        assert "ANTIGRAVITY_GEMINI_DIR" not in facade_env


def test_discover_system_agents_subcommands() -> None:
    """Verify parsing output from agy agents CLI subcommand."""
    mock_stdout = """
Registered Agents:
--------------------------------
• agy1       (Main Assistant)
• agy2       (Worker Agent)
| agy3       (Reviewer)
* agy4       (Tester)
================================
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_stdout)
        with patch.dict(os.environ, {"LOCALAPPDATA": ""}):
            with tempfile.TemporaryDirectory() as tmp_dir:
                with patch("mind.core.agent_discovery.get_real_user_home", return_value=Path(tmp_dir)):
                    agents = discover_system_agents()
                    assert "agy1" in agents
                    assert "agy2" in agents
                    assert "agy3" in agents
                    assert "agy4" in agents


def test_discover_system_agents_localappdata_and_linux() -> None:
    """Verify discovery from Windows LOCALAPPDATA bin and Linux POSIX directories."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        local_bin = root / "agy" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        (local_bin / "agy5.cmd").write_text("", encoding="utf-8")
        (local_bin / "agy6.exe").write_text("", encoding="utf-8")
        (local_bin / "agy.exe").write_text("", encoding="utf-8")  # Main binary, ignored

        with patch.dict(os.environ, {"LOCALAPPDATA": str(root)}):
            with patch("mind.core.agent_discovery.get_real_user_home", return_value=root):
                with patch("subprocess.run", side_effect=Exception("No agy in PATH")):
                    agents = discover_system_agents()
                    assert "agy5" in agents
                    assert "agy6" in agents
                    assert "agy" not in agents


def test_discover_system_agents_instances_and_tokens() -> None:
    """Verify discovery from instances and tokens directories with natural sorting."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_home = Path(tmp_dir)
        inst_dir = fake_home / ".gemini" / "instances"
        tok_dir = fake_home / ".gemini" / "tokens"
        inst_dir.mkdir(parents=True, exist_ok=True)
        tok_dir.mkdir(parents=True, exist_ok=True)

        (inst_dir / "agy1").mkdir()
        (inst_dir / "agy10").mkdir()
        (inst_dir / "agy2").mkdir()
        (tok_dir / "agy3.token").write_text("tok", encoding="utf-8")

        with patch("mind.core.agent_discovery.get_real_user_home", return_value=fake_home):
            with patch("subprocess.run", side_effect=Exception("No agy in PATH")):
                with patch.dict(os.environ, {"LOCALAPPDATA": ""}):
                    agents = discover_system_agents()
                    assert "agy1" in agents
                    assert "agy2" in agents
                    assert "agy3" in agents
                    assert "agy10" in agents
                    # Verify natural sorting: agy2 must come BEFORE agy10
                    assert agents.index("agy2") < agents.index("agy10")


def test_discover_system_agents_fallback() -> None:
    """Verify fallback to defaults if no system agents are found."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_home = Path(tmp_dir)
        with patch("mind.core.agent_discovery.get_real_user_home", return_value=fake_home):
            with patch("subprocess.run", side_effect=Exception("No CLI")):
                with patch.dict(os.environ, {"LOCALAPPDATA": ""}):
                    with patch("shutil.which", return_value=None):
                        agents = discover_system_agents()
                        assert agents == ["agy1", "agy2", "agy3", "agy4"]


def test_discover_agent_slots_metadata() -> None:
    """Verify discover_agent_slots returns detailed SlotInfo objects."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_home = Path(tmp_dir)
        tokens_dir = fake_home / ".gemini" / "tokens"
        tokens_dir.mkdir(parents=True, exist_ok=True)

        # Create token with test email in JWT
        import base64
        claims = json.dumps({"email": "slot1@google.com", "exp": 2000000000})
        b64_claims = base64.urlsafe_b64encode(claims.encode("utf-8")).decode("utf-8").rstrip("=")
        jwt = f"eyJhbGciOiJIUzI1NiJ9.{b64_claims}.sig"
        (tokens_dir / "agy1.token").write_text(json.dumps({"id_token": jwt}), encoding="utf-8")

        with patch("mind.core.agent_discovery.get_real_user_home", return_value=fake_home):
            with patch("mind.core.agent_discovery.discover_system_agents", return_value=["agy1", "agy2"]):
                slots = discover_agent_slots()
                assert len(slots) == 2

                s1 = slots[0]
                assert isinstance(s1, SlotInfo)
                assert s1.slot_id == 1
                assert s1.name == "agy1"
                assert s1.has_token is True
                assert s1.email == "slot1@google.com"

                s2 = slots[1]
                assert s2.slot_id == 2
                assert s2.name == "agy2"
                assert s2.has_token is False
                assert s2.email is None


def test_get_agent_preset_config() -> None:
    """Verify preset configuration dictionary structure."""
    cfg = get_agent_preset_config("agy3")
    assert cfg["alias"] == "agy3"
    assert cfg["assigned_agent"] == "agy3"
    assert "--agent agy3" in cfg["extra_flags"]
    assert "gemini" in cfg["model"]


def test_agys_powershell_helpers() -> None:
    """Verify PowerShell agys compatibility and command generation."""
    cmd = generate_agys_command(slot=2, action="login")
    assert "agys login 2" in cmd[-1]

    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_home = Path(tmp_dir)
        (fake_home / ".gemini" / "instances" / "agy1").mkdir(parents=True)
        (fake_home / ".gemini" / "tokens").mkdir(parents=True)

        tok_data = b'{"token": "sync_token"}'
        (fake_home / ".gemini" / "instances" / "agy1" / "token.json").write_bytes(tok_data)
        (fake_home / ".gemini" / "tokens" / "agy1.token").write_bytes(tok_data)

        with patch("mind.core.agent_discovery.get_real_user_home", return_value=fake_home):
            report = verify_agys_compatibility(slot=1)
            assert report["slot_id"] == 1
            assert report["instance_dir_exists"] is True
            assert report["has_instance_token"] is True
            assert report["has_central_token"] is True
            assert report["tokens_synchronized"] is True


def test_discover_system_agents_agys_registry_and_isolation() -> None:
    """Verify dynamic discovery from agys -l output and ~/.local/share/agy-instances."""
    mock_agys_l = """
==========================================================================================
                              AGY Multi-Instance Registry                                 
==========================================================================================
INSTANCE   | AUTH STATUS  | ACCOUNT / EMAIL              | STORAGE  | LOCATION
------------------------------------------------------------------------------------------
agy1       | Logged In    | user1@gmail.com              | 20M      | /path/agy1
agy2       | Logged In    | user2@gmail.com              | 22M      | /path/agy2
agy3       | Logged In    | user3@gmail.com              | 118M     | /path/agy3
agy11      | Logged In    | user1@gmail.com              | 17M      | /path/agy11
agy51      | Logged In    | user1@gmail.com              | 17M      | /path/agy51
agy100     | Logged In    | user1@gmail.com              | 17M      | /path/agy100
agy151     | Logged In    | user1@gmail.com              | 17M      | /path/agy151
==========================================================================================
"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_home = Path(tmp_dir)
        agys_instances = fake_home / ".local" / "share" / "agy-instances"
        agys_instances.mkdir(parents=True, exist_ok=True)
        for slot in ["agy1", "agy2", "agy3", "agy11", "agy51", "agy100", "agy151"]:
            (agys_instances / slot).mkdir()

        # Posix bin containing agys orchestrator binary itself (should NOT be included as an agent!)
        local_bin = fake_home / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        (local_bin / "agys").write_text("#!/bin/bash", encoding="utf-8")

        with patch("mind.core.agent_discovery.get_real_user_home", return_value=fake_home):
            with patch("shutil.which", side_effect=lambda cmd: str(local_bin / "agys") if cmd == "agys" else None):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout=mock_agys_l)
                    with patch.dict(os.environ, {"AGY_INSTANCES_DIR": str(agys_instances)}):
                        agents = discover_system_agents()

                        # Must discover all agys instances
                        assert "agy1" in agents
                        assert "agy2" in agents
                        assert "agy3" in agents
                        assert "agy11" in agents
                        assert "agy51" in agents
                        assert "agy100" in agents
                        assert "agy151" in agents

                        # Tool name "agys" must NOT be treated as an agent
                        assert "agys" not in agents
                        assert "agy" not in agents

                        # Must be naturally sorted
                        expected = ["agy1", "agy2", "agy3", "agy11", "agy51", "agy100", "agy151"]
                        assert agents == expected


@pytest.mark.asyncio
async def test_select_worker_modal_lifecycle() -> None:
    """Verify SelectWorkerModal displays options and filters properly."""
    from mind.ui.select_worker_modal import SelectWorkerModal
    from textual.app import App

    class TestApp(App):
        def compose(self):
            yield SelectWorkerModal(current_assigned=["agy1", "agy2"])

    app = TestApp()
    async with app.run_test() as pilot:
        modal = app.query_one(SelectWorkerModal)
        assert modal is not None
        opt_list = modal.query_one("#worker-options-list")
        assert opt_list is not None
        assert opt_list.option_count >= 1


def test_token_manager_resolves_agys_instance_tokens() -> None:
    """Verify TokenManager finds instance tokens in agys multi-instance directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_home = Path(tmp_dir)
        agys_instances = fake_home / ".local" / "share" / "agy-instances"
        agys_instances.mkdir(parents=True, exist_ok=True)
        slot11_dir = agys_instances / "agy11"
        slot11_dir.mkdir()
        slot11_tok = slot11_dir / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
        slot11_tok.parent.mkdir(parents=True, exist_ok=True)
        slot11_tok.write_text("token-slot-11", encoding="utf-8")

        with patch("mind.core.agent_discovery.get_real_user_home", return_value=fake_home):
            with patch.dict(os.environ, {"AGY_INSTANCES_DIR": str(agys_instances)}):
                mgr = TokenManager()
                assert mgr.get_instance_dir(11) == slot11_dir
                assert mgr.get_instance_token_path(11) == slot11_tok


def test_agent_config_modal_tab_selection_and_persistence() -> None:
    """Verify AgentConfigModal preselects Tab 1 and persists assigned_agent reliably."""
    from mind.core.terminal_manager import TerminalManager
    from mind.ui.agent_config_modal import AgentConfigModal

    mgr = TerminalManager.get_instance()
    # Ensure clean state with Coordinator and Worker 1
    coord = mgr.create_worker("coordinator", role="coordinator", assigned_agent="agy1", autostart=False)
    worker1 = mgr.create_worker("1", role="worker", assigned_agent="agy2", autostart=False)

    # 1. Opening modal for default_target="1" must preselect Tab 1, not Coordinator
    modal = AgentConfigModal(default_target="1")
    target_opt = next(opt for opt in modal.options if opt.key == "target_worker")
    assert "Tab 1:" in target_opt.value
    assert "Coordinator:" not in target_opt.value

    # System agent option must show current worker agent (agy2)
    sys_opt = next(opt for opt in modal.options if opt.key == "system_agent")
    assert sys_opt.value == "agy2"

    # 2. Change system agent to agy11 and save & close
    sys_opt.set_value("agy11")
    modal.action_save_and_close()

    # Worker session in TerminalManager MUST now have assigned_agent="agy11"
    assert worker1.assigned_agent == "agy11"
    assert worker1.name == "agy11"
    assert worker1.profile.assigned_agent == "agy11"

    # 3. Reopening modal for Tab 1 MUST now show agy11 preserved
    modal2 = AgentConfigModal(default_target="1")
    target_opt2 = next(opt for opt in modal2.options if opt.key == "target_worker")
    sys_opt2 = next(opt for opt in modal2.options if opt.key == "system_agent")
    assert "Tab 1:" in target_opt2.value
    assert sys_opt2.value == "agy11"

