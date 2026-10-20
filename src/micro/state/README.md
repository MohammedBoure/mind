# state/

State and data layer for the `micro` TUI.

## Files

| File           | Purpose                                                                                     |
|----------------|---------------------------------------------------------------------------------------------|
| `models.py`    | Domain dataclass models: `AgentInfo`, `SessionInfo`, `LogEntry`, `InterAgentMessage`, and related enums (`AgentRole`, `AgentStatus`, `MessagePriority`). |
| `mock_data.py` | Mock/placeholder data provider. Supplies sample sessions, agents, log streams, and interrupt messages for UI development. Replace with real backend connections. |
