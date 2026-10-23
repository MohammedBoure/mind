# `src/mind/cli/` — CLI Entrypoint & Commands

CLI layer for the `mind` TUI and embedded MCP server.

## Files

| File | Purpose |
|---|---|
| `main.py` | Click CLI entrypoint. Defines root `mind` commands: launching session picker with auto-provisioned MCP configuration, `new <session>` direct workspace entry, `mcp` stdio server, `register-mcp` for automatic provisioning and registration with `agy`, `usage` (or `-u` / `--usage`) for monitoring multi-slot account quotas, `doctor` for system health and compatibility checks, and `sessions` for listing and cleaning up temporary orchestration sessions. |
| `doctor.py` | Comprehensive System Health, Diagnostic & Compatibility Doctor (`run_all_doctor_checks`, `print_doctor_cli`). Inspects host OS, Python runtime, `agy` CLI binary, `agys` PowerShell multi-slot architecture, PTY subsystem (ConPTY / Unix openpty), dead-key and scancode translation, account slot discovery, token JWT validity, cross-process IPC mutex locking, and FastMCP server with registered tools. Supports Rich formatted tables, status badges, and structured JSON export. |
| `sessions.py` | CLI Session Management & Cleanup Suite (`list_sessions_cli`, `clean_sessions_cli`, `delete_session_cli`, `create_session_cli`). Inspects persistent sessions in `~/.mind/sessions.json` with activity telemetry, creates new sessions, deletes existing sessions, and prunes stale or old temporary sessions. |
