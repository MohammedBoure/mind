# `src/micro/cli/` — CLI Entrypoint & Commands

CLI layer for the `mind` / `micro` TUI and embedded MCP server.

## Files

| File | Purpose |
|---|---|
| `main.py` | Click CLI entrypoint. Defines root `mind` / `micro` commands: launching session picker, `new <session>` direct workspace entry, `mcp` stdio server, and `register-mcp` for automatic registration with `agy`. |
