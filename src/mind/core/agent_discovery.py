"""Dynamic System Agent Discovery and Slot Isolation for mind.

Discovers registered Antigravity agents installed on the host system and provisions
isolated multi-instance execution slots by:
1. Dynamic scanning:
   - Querying `agy agents` and `agy agent` CLI subcommands.
   - Inspecting local multi-account slot executables (%LOCALAPPDATA%\\agy\\bin on Windows).
   - Inspecting Linux/POSIX executable directories (/usr/local/bin, /usr/bin, ~/.local/bin).
   - Scanning Antigravity instance directories (~/.gemini/instances).
   - Scanning credential tokens (~/.gemini/tokens).
   - Checking standard PATH candidates (agy1..agy30).
2. Slot Isolation:
   - Configuring isolated environment variables: USERPROFILE, HOME, AGY_SLOT, AGY_INSTANCE_DIR.
   - Eliminating directory conflicts (ANTIGRAVITY_GEMINI_DIR, ANTIGRAVITY_APP_DATA_DIR).
   - Preventing nested slot home conflicts (real home resolution).
   - Creating slot file structures compatible with PowerShell agys functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

logger = logging.getLogger("mind.core.agent_discovery")


@dataclass
class SlotInfo:
    """Metadata representing an Antigravity worker slot and its isolated environment."""

    slot_id: int
    name: str  # e.g. "agy1"
    instance_dir: Path
    token_file: Path
    instance_token_file: Path
    has_token: bool
    email: str | None = None
    sources: list[str] = field(default_factory=list)


def parse_slot_id(identifier: str | int | None) -> int:
    """Extract slot integer index from an agent name, tab title, or slot string.

    Examples:
        'agy1' -> 1
        'Worker-2' -> 2
        'slot3' -> 3
        4 -> 4
    """
    if identifier is None:
        return 1
    if isinstance(identifier, int):
        return max(1, identifier)

    id_str = str(identifier).strip()
    match = re.search(r"\d+", id_str)
    if match:
        try:
            return max(1, int(match.group()))
        except ValueError:
            pass
    return 1


def get_real_user_home() -> Path:
    """Resolve the host machine's true user home directory, preventing nested instance paths.

    If an agent or parent process is already running within an isolated slot
    (where USERPROFILE or HOME points to ~/.gemini/instances/agy<N>), this function
    recovers the real user profile root to avoid generating nested paths like:
    ~/.gemini/instances/agy1/.gemini/instances/agy2.
    """
    # 1. Check explicit override or cached environment variable
    cached = os.environ.get("MIND_REAL_USER_HOME")
    if cached:
        cand = Path(cached)
        if cand.is_dir():
            return cand

    # 2. Check USERPROFILE and HOME for slot instance patterns to strip nested instance paths
    for var_name in ("USERPROFILE", "HOME"):
        val = os.environ.get(var_name)
        if val:
            norm = os.path.normpath(val)
            # Match .../.gemini/instances/agy<N> or .../instances/agy<N>
            m = re.match(
                r"^(.*?)(?:[\\/]\.gemini)?[\\/]instances[\\/]agy\d+$",
                norm,
                re.IGNORECASE,
            )
            if m and m.group(1):
                recovered = Path(m.group(1))
                if recovered.is_dir():
                    return recovered

    # 3. On Windows, check HOMEDRIVE + HOMEPATH
    if sys.platform == "win32":
        drive = os.environ.get("HOMEDRIVE")
        path = os.environ.get("HOMEPATH")
        if drive and path:
            candidate = Path(f"{drive}{path}")
            if candidate.is_dir():
                return candidate

    # 4. Fallback to standard Path.home()
    return Path.home()


def get_slot_instance_dir(slot: int | str, real_home: Path | None = None) -> Path:
    """Return the isolated instance directory path (~/.gemini/instances/agy<N>)."""
    slot_id = parse_slot_id(slot)
    home = real_home or get_real_user_home()
    return home / ".gemini" / "instances" / f"agy{slot_id}"


def get_slot_token_path(slot: int | str, real_home: Path | None = None) -> Path:
    """Return the central token file path (~/.gemini/tokens/agy<N>.token)."""
    slot_id = parse_slot_id(slot)
    home = real_home or get_real_user_home()
    return home / ".gemini" / "tokens" / f"agy{slot_id}.token"


def get_slot_instance_token_path(slot: int | str, real_home: Path | None = None) -> Path:
    """Return the slot's instance-local token path (~/.gemini/instances/agy<N>/token.json)."""
    return get_slot_instance_dir(slot, real_home) / "token.json"


def initialize_slot_instance(
    slot: int | str,
    real_home: Path | None = None,
) -> dict[str, Any]:
    """Initialize an isolated environment slot directory matching PowerShell agys conventions.

    Provisions:
    - ~/.gemini/instances/agy<N>/
    - ~/.gemini/instances/agy<N>/.gemini/antigravity-cli/conversations/
    - Migrates legacy token ~/.gemini/tokens/agy<N>.token to ~/.gemini/instances/agy<N>/token.json
    - Copies global settings.json into slot profile if not already present
    - Links .ssh for shared git credentials on host if present
    """
    slot_id = parse_slot_id(slot)
    home = real_home or get_real_user_home()
    slot_name = f"agy{slot_id}"
    instance_dir = get_slot_instance_dir(slot_id, home)

    gemini_dir = instance_dir / ".gemini"
    cli_dir = gemini_dir / "antigravity-cli"
    conv_dir = cli_dir / "conversations"

    tokens_root = home / ".gemini" / "tokens"
    legacy_token = tokens_root / f"{slot_name}.token"
    instance_token = instance_dir / "token.json"

    is_new = not instance_dir.exists()
    conv_dir.mkdir(parents=True, exist_ok=True)

    # 1. Automatically migrate legacy token if present
    if not instance_token.exists() and legacy_token.exists():
        try:
            content = legacy_token.read_bytes()
            instance_token.write_bytes(content)
        except Exception as err:
            logger.debug("Failed migrating legacy token for %s: %s", slot_name, err)

    # 2. Seed settings.json from global template if available
    global_settings = home / ".gemini" / "antigravity-cli" / "settings.json"
    instance_settings = cli_dir / "settings.json"
    if not instance_settings.exists() and global_settings.exists():
        try:
            instance_settings.write_bytes(global_settings.read_bytes())
        except Exception as err:
            logger.debug("Failed seeding settings for %s: %s", slot_name, err)

    # 3. Link .ssh directory for shared Git/SSH keys if available
    real_ssh = home / ".ssh"
    instance_ssh = instance_dir / ".ssh"
    if real_ssh.exists() and not instance_ssh.exists():
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["cmd", "/c", f'mklink /J "{instance_ssh}" "{real_ssh}"'],
                    capture_output=True,
                    timeout=2,
                )
            else:
                instance_ssh.symlink_to(real_ssh)
        except Exception:
            pass

    return {
        "slot_id": slot_id,
        "slot_name": slot_name,
        "instance_dir": instance_dir,
        "instance_token": instance_token,
        "legacy_token": legacy_token,
        "conversations_dir": conv_dir,
        "is_new": is_new,
    }


def build_slot_isolation_env(
    slot: int | str,
    base_env: dict[str, str] | None = None,
    auto_init: bool = True,
    instances_root: Path | None = None,
    tokens_root: Path | None = None,
    real_home: Path | None = None,
) -> dict[str, str]:
    """Construct sanitized environment variables for worker slot with instance isolation.

    Configures:
    - USERPROFILE: Path to isolated instance directory
    - HOME: Path to isolated instance directory
    - AGY_SLOT: String slot number (e.g. '1')
    - AGY_INSTANCE_DIR: Path to isolated instance directory
    - AGY_TOKEN_FILE: Path to slot token file

    Cleans conflicting directory overrides (ANTIGRAVITY_GEMINI_DIR, ANTIGRAVITY_APP_DATA_DIR).
    """
    slot_id = parse_slot_id(slot)
    home = real_home or get_real_user_home()

    inst_root = instances_root or (home / ".gemini" / "instances")
    tok_root = tokens_root or (home / ".gemini" / "tokens")

    instance_dir = inst_root / f"agy{slot_id}"
    token_file = tok_root / f"agy{slot_id}.token"

    if auto_init:
        try:
            initialize_slot_instance(slot=slot_id, real_home=home)
        except Exception as err:
            logger.debug("Auto-initialization of slot %s failed: %s", slot_id, err)

    env = dict(os.environ if base_env is None else base_env)

    # Core slot isolation environment variables
    env["AGY_SLOT"] = str(slot_id)
    env["USERPROFILE"] = str(instance_dir)
    env["HOME"] = str(instance_dir)
    env["AGY_INSTANCE_DIR"] = str(instance_dir)
    env["AGY_TOKEN_FILE"] = str(token_file)

    # Clean conflicting directory overrides that trigger auth loops or hijack config paths
    env.pop("ANTIGRAVITY_GEMINI_DIR", None)
    env.pop("ANTIGRAVITY_APP_DATA_DIR", None)

    return env


def discover_system_agents() -> list[str]:
    """Discover all available agy agents registered on the host system.

    Discovers registered agents by:
    1. Querying `agy agents` and `agy agent` subcommands via CLI.
    2. Inspecting local multi-account slot executables (%LOCALAPPDATA%\\agy\\bin on Windows).
    3. Inspecting Linux/POSIX executable directories (/usr/local/bin, /usr/bin, ~/.local/bin).
    4. Scanning Antigravity instance directories (~/.gemini/instances).
    5. Scanning credential tokens (~/.gemini/tokens).
    6. Checking standard PATH candidates (agy1..agy30).

    Returns:
        Naturally sorted, deduplicated list of agent identifiers (e.g. ['agy1', 'agy2', ...]).
    """
    discovered: set[str] = set()
    home = get_real_user_home()

    # 1. Try running `agy agents` or `agy agent` via subprocess
    for cmd in [["agy", "agents"], ["agy", "agent"]]:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.splitlines():
                    cleaned = line.strip()
                    if not cleaned or re.match(r"^[-=]+$", cleaned):
                        continue
                    if ":" in cleaned and not any(cleaned.startswith(p) for p in ("•", "*", "-", "|", ">")):
                        continue
                    cleaned = re.sub(r"^[•\*\-\>\s\|]+", "", cleaned).strip()
                    name = cleaned.split()[0] if cleaned else ""
                    if re.match(r"^[a-zA-Z0-9_\-]+$", name):
                        discovered.add(name)
        except Exception:
            pass

    # 2. Inspect %LOCALAPPDATA%\agy\bin on Windows for slot launchers (agy1.cmd, agy2.cmd, etc.)
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        local_bin = Path(local_app_data) / "agy" / "bin"
        if local_bin.exists():
            try:
                for f in local_bin.glob("agy*.cmd"):
                    discovered.add(f.stem)
                for f in local_bin.glob("agy*.bat"):
                    discovered.add(f.stem)
                for f in local_bin.glob("agy*.ps1"):
                    discovered.add(f.stem)
                for f in local_bin.glob("agy*.exe"):
                    if f.stem.lower() != "agy":
                        discovered.add(f.stem)
            except Exception:
                pass

    # 3. Inspect Linux/POSIX binary directories (/usr/local/bin, /usr/bin, ~/.local/bin)
    posix_bin_dirs = [
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        home / ".local" / "bin",
    ]
    for bin_dir in posix_bin_dirs:
        if bin_dir.exists():
            try:
                for item in bin_dir.glob("agy*"):
                    if item.is_file() and item.name.lower() != "agy":
                        discovered.add(item.name)
            except Exception:
                pass

    # 4. Inspect ~/.gemini/instances/ for multi-account instance folders
    instances_dir = home / ".gemini" / "instances"
    if instances_dir.exists():
        try:
            for item in instances_dir.iterdir():
                if item.is_dir() and item.name.startswith("agy"):
                    discovered.add(item.name)
        except Exception:
            pass

    # 5. Inspect ~/.gemini/tokens/ for slot token files
    tokens_dir = home / ".gemini" / "tokens"
    if tokens_dir.exists():
        try:
            for f in tokens_dir.glob("*.token"):
                discovered.add(f.stem)
        except Exception:
            pass

    # 6. Check PATH for standard slot executables (agy1..agy30)
    for i in range(1, 31):
        candidate = f"agy{i}"
        if shutil.which(candidate):
            discovered.add(candidate)

    # 7. Fallback defaults if no external agents discovered
    if not discovered:
        discovered.update(["agy1", "agy2", "agy3", "agy4"])

    # Natural sorting (agy1, agy2, ..., agy10)
    def _sort_key(name: str) -> tuple[int, str]:
        num_match = re.search(r"\d+", name)
        num = int(num_match.group()) if num_match else 9999
        return (num, name)

    return sorted(discovered, key=_sort_key)


def discover_agent_slots() -> list[SlotInfo]:
    """Discover all agents and return structured SlotInfo metadata."""
    from mind.core.auth.validator import AuthValidator

    validator = AuthValidator()
    home = get_real_user_home()
    agent_names = discover_system_agents()

    slots: list[SlotInfo] = []
    for name in agent_names:
        slot_id = parse_slot_id(name)
        inst_dir = get_slot_instance_dir(slot_id, home)
        central_tok = get_slot_token_path(slot_id, home)
        inst_tok = get_slot_instance_token_path(slot_id, home)

        sources: list[str] = []
        if inst_dir.exists():
            sources.append("instance_dir")
        if central_tok.exists():
            sources.append("central_token")
        if inst_tok.exists():
            sources.append("instance_token")
        if shutil.which(name):
            sources.append("path")

        has_tok = central_tok.exists() or inst_tok.exists()
        email: str | None = None
        target_tok = central_tok if central_tok.exists() else inst_tok
        if target_tok.exists():
            try:
                email = validator.extract_email(target_tok.read_bytes())
            except Exception:
                pass

        slots.append(
            SlotInfo(
                slot_id=slot_id,
                name=name,
                instance_dir=inst_dir,
                token_file=central_tok,
                instance_token_file=inst_tok,
                has_token=has_tok,
                email=email,
                sources=sources,
            )
        )

    return slots


def get_agent_preset_config(agent_name: str) -> dict[str, Any]:
    """Return default configuration hints for a discovered agent."""
    name_clean = agent_name.strip()
    return {
        "alias": name_clean,
        "assigned_agent": name_clean,
        "model": "gemini-3.8-flash-high",
        "cli_mode": "auto",
        "reasoning_effort": "high",
        "extra_flags": f"--agent {name_clean}",
        "instructions": f"Act as system worker agent {name_clean}. Execute terminal tasks autonomously.",
    }


def detect_agys_installed() -> bool:
    """Check if the PowerShell agys function or command is registered on the host."""
    if sys.platform != "win32":
        return False
    for shell in ["powershell", "pwsh"]:
        if shutil.which(shell):
            try:
                res = subprocess.run(
                    [shell, "-NoProfile", "-Command", "Get-Command agys -ErrorAction SilentlyContinue"],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                )
                if res.returncode == 0 and "agys" in res.stdout:
                    return True
            except Exception:
                pass
    return False


def generate_agys_command(
    slot: int | str,
    action: str = "run",
    extra_args: list[str] | None = None,
) -> list[str]:
    """Generate a PowerShell agys invocation command list."""
    slot_id = parse_slot_id(slot)
    args = [action, str(slot_id)]
    if extra_args:
        args.extend(extra_args)
    cmd_str = f"agys {' '.join(args)}"
    shell = "pwsh" if shutil.which("pwsh") else "powershell"
    return [shell, "-NoProfile", "-Command", cmd_str]


def verify_agys_compatibility(slot: int | str | None = None) -> dict[str, Any]:
    """Validate system compatibility with the central PowerShell agys functions."""
    home = get_real_user_home()
    instances_dir = home / ".gemini" / "instances"
    tokens_dir = home / ".gemini" / "tokens"

    slot_id = parse_slot_id(slot) if slot is not None else 1
    inst_dir = instances_dir / f"agy{slot_id}"
    inst_tok = inst_dir / "token.json"
    central_tok = tokens_dir / f"agy{slot_id}.token"

    synchronized = False
    if inst_tok.exists() and central_tok.exists():
        try:
            synchronized = inst_tok.read_bytes().strip() == central_tok.read_bytes().strip()
        except Exception:
            synchronized = False

    return {
        "powershell_available": bool(shutil.which("powershell") or shutil.which("pwsh")),
        "agys_detected": detect_agys_installed(),
        "real_home": str(home),
        "instances_root_exists": instances_dir.exists(),
        "tokens_root_exists": tokens_dir.exists(),
        "slot_id": slot_id,
        "instance_dir": str(inst_dir),
        "instance_dir_exists": inst_dir.exists(),
        "has_instance_token": inst_tok.exists(),
        "has_central_token": central_tok.exists(),
        "tokens_synchronized": synchronized,
    }
