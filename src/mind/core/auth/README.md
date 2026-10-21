# `src/mind/core/auth/` — Modular Authentication & Credential Management

This directory provides modular authentication validation, token claim extraction, secure keyring backend abstractions, cross-process concurrency locking, and slot credential lifecycle coordination.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Package exports for models, backends, validator, manager, and locking primitives. |
| `models.py` | Data models (`TokenClaims`, `ValidationResult`), status enums (`TokenStatus`), `CredentialBackend` protocol, and exception hierarchy. |
| `validator.py` | `AuthValidator` implementation providing BOM sanitization, JSON schema unpacking, JWT claim decoding, and expiration validation. |
| `backends.py` | Credential storage implementations including `WindowsCredentialBackend` (Advapi32) and `MockCredentialBackend` (in-memory for testing). |
| `lock.py` | `CrossProcessCredentialLock` providing inter-process Win32 mutex and file lock synchronization. |
| `manager.py` | `TokenManager` coordinating slot token file paths, atomic persistence (dual-sync with `~/.gemini/instances/` and `~/.gemini/tokens/`), keyring restoration, and environment variable isolation (`USERPROFILE` / `HOME` slot isolation). |
