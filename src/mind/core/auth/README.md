# `src/mind/core/auth/` — Modular Authentication & Credential Management

This directory provides modular authentication validation, token claim extraction, secure keyring backend abstractions, cross-process concurrency locking, and slot credential lifecycle coordination across Windows and Linux.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Package exports for models, backends, validator, manager, and locking primitives. |
| `models.py` | Data models (`TokenClaims`, `ValidationResult`), status enums (`TokenStatus`), `CredentialBackend` protocol, and exception hierarchy (`AuthError`, `TokenValidationError`, `TokenExpiredError`, `KeyringStorageError`, `LockTimeoutError`, `VaultEncryptionError`). |
| `validator.py` | `AuthValidator` implementation providing UTF-8 and UTF-16 BOM sanitization, raw JWT parsing, JSON schema unpacking, identity claims extraction (`email`, `account`, `sub`), and expiration validation. |
| `backends.py` | Cross-platform credential storage implementations: `WindowsCredentialBackend` (Advapi32 Windows Credential Manager `gemini:antigravity`), `LinuxKeyringBackend` (SecretService via `keyring` / `secret-tool`), `LinuxFileVaultBackend` (encrypted vault with strict `chmod 0600` permissions inside `~/.gemini/tokens/`), `MockCredentialBackend` (in-memory for testing), and `get_default_backend()` factory. |
| `lock.py` | `CrossProcessCredentialLock` providing inter-process synchronization using `Global\AgyCredentialMutex` / `Local\AgyCredentialMutex` on Windows and `fcntl.flock` on `.credential.lock` with timeout retries on Linux to prevent worker race conditions. |
| `manager.py` | `TokenManager` coordinating slot token file paths, bidirectional Dual-Sync between isolated instance paths (`~/.gemini/instances/agy<N>/token.json`) and central token paths (`~/.gemini/tokens/agy<N>.token`), atomic persistence with `chmod 0600`, keyring restoration under lock, and environment variable isolation (`USERPROFILE` / `HOME` slot isolation). |
