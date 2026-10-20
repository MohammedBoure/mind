"""Dynamic System Agent Discovery for mind.

Discovers registered Antigravity agents installed on the host system by:
1. Querying `agy agents` / `agy agent list` CLI command.
2. Inspecting local multi-account slot executables (%LOCALAPPDATA%\\agy\\bin).
3. Scanning Antigravity instance directories (~/.gemini/instances).
4. Scanning credential tokens (~/.gemini/tokens).
5. Inspecting project-local and global custom agent definitions.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


def discover_system_agents() -> list[str]:
    """Discover all available agy agents registered on the host system.
    
    Returns:
        Sorted, deduplicated list of agent identifiers (e.g. ['agy1', 'agy2', 'agy3', ...]).
    """
    discovered: set[str] = set()

    # 1. Try running `agy agents` or `agy agent list` via subprocess
    for cmd in [["agy", "agents"], ["agy", "agent", "list"]]:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.splitlines():
                    cleaned = line.strip()
                    if not cleaned or cleaned.startswith(("#", "-", "=", "*")):
                        continue
                    name = cleaned.split()[0]
                    if re.match(r"^[a-zA-Z0-9_\-]+$", name):
                        discovered.add(name)
        except Exception:
            pass

    # 2. Inspect %LOCALAPPDATA%\agy\bin for slot launchers (agy1.cmd, agy2.cmd, etc.)
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        local_bin = Path(local_app_data) / "agy" / "bin"
        if local_bin.exists():
            for f in local_bin.glob("agy*.cmd"):
                discovered.add(f.stem)
            for f in local_bin.glob("agy*.exe"):
                if f.stem != "agy":
                    discovered.add(f.stem)

    # 3. Inspect ~/.gemini/instances/ for multi-account instance folders
    instances_dir = Path(os.path.expanduser("~/.gemini/instances"))
    if instances_dir.exists():
        try:
            for item in instances_dir.iterdir():
                if item.is_dir() and item.name.startswith("agy"):
                    discovered.add(item.name)
        except Exception:
            pass

    # 4. Inspect ~/.gemini/tokens/ for slot token files
    tokens_dir = Path(os.path.expanduser("~/.gemini/tokens"))
    if tokens_dir.exists():
        try:
            for f in tokens_dir.glob("*.token"):
                discovered.add(f.stem)
        except Exception:
            pass

    # 5. Check PATH for standard slot executables (agy1..agy20)
    for i in range(1, 21):
        candidate = f"agy{i}"
        if shutil.which(candidate):
            discovered.add(candidate)

    # 6. Fallback defaults if no external agents discovered
    if not discovered:
        discovered.update(["agy1", "agy2", "agy3", "agy4"])

    # Natural sorting (agy1, agy2, ..., agy10)
    def _sort_key(name: str) -> tuple[int, str]:
        num_match = re.search(r"\d+", name)
        num = int(num_match.group()) if num_match else 9999
        return (num, name)

    return sorted(discovered, key=_sort_key)


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
