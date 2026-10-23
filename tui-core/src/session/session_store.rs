use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use serde::{Deserialize, Serialize};
use tracing::{debug, info};

use crate::error::{Result, TuiError};
use crate::session::identity::IdentityDiscovery;

/// Persistent worker definition inside a saved session.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SessionWorkerConfig {
    pub id: String,
    pub slot_id: String,
    pub role: String,
    pub model: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub task: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub command: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub args: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub env: Option<HashMap<String, String>>,
}

/// Persistent multi-agent session record.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SessionRecord {
    pub name: String,
    pub created_at: String,
    pub last_activity: String,
    pub agent_count: usize,
    pub goal: String,
    pub active: bool,
    pub total_steps: usize,
    pub total_interactions: usize,
    pub status: String,
    pub working_dir: String,
    pub workers: Vec<SessionWorkerConfig>,
    #[serde(default)]
    pub global_settings: HashMap<String, serde_json::Value>,
}

impl SessionRecord {
    /// Create a new session record with default ISO timestamps and active status.
    pub fn new(name: impl Into<String>, goal: impl Into<String>) -> Self {
        let now = now_iso();
        Self {
            name: name.into(),
            created_at: now.clone(),
            last_activity: now,
            agent_count: 0,
            goal: goal.into(),
            active: true,
            total_steps: 0,
            total_interactions: 0,
            status: "active".to_string(),
            working_dir: std::env::current_dir()
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_default(),
            workers: Vec::new(),
            global_settings: HashMap::new(),
        }
    }

    /// Add a worker agent configuration to this session.
    pub fn add_worker(&mut self, worker: SessionWorkerConfig) {
        self.workers.push(worker);
        self.agent_count = self.workers.len();
    }
}

/// Persistent Session Store saving and loading session records from `~/.mind/sessions/<name>.json`.
#[derive(Debug, Clone)]
pub struct SessionStore {
    base_dir: PathBuf,
}

impl Default for SessionStore {
    fn default() -> Self {
        Self::new()
    }
}

impl SessionStore {
    /// Initialize SessionStore targeting standard `~/.mind/sessions/` directory.
    pub fn new() -> Self {
        let home = IdentityDiscovery::get_real_user_home();
        let sessions_dir = home.join(".mind").join("sessions");
        let _ = fs::create_dir_all(&sessions_dir);
        Self {
            base_dir: sessions_dir,
        }
    }

    /// Initialize SessionStore with a custom directory (useful for unit tests and custom paths).
    pub fn with_dir(dir: PathBuf) -> Self {
        let _ = fs::create_dir_all(&dir);
        Self { base_dir: dir }
    }

    /// Get current storage base directory path.
    pub fn sessions_dir(&self) -> &Path {
        &self.base_dir
    }

    /// Path to a specific session JSON file.
    pub fn session_file_path(&self, name: &str) -> PathBuf {
        let clean = Self::sanitize_name(name);
        self.base_dir.join(format!("{}.json", clean))
    }

    /// Sanitize session name for safe filename usage.
    pub fn sanitize_name(name: &str) -> String {
        name.trim()
            .chars()
            .map(|c| if c.is_alphanumeric() || c == '-' || c == '_' { c } else { '_' })
            .collect()
    }

    /// Save a session record to `~/.mind/sessions/<name>.json` with atomic write semantics.
    pub fn save_session(&self, session: &SessionRecord) -> Result<PathBuf> {
        let path = self.session_file_path(&session.name);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }

        let json_text = serde_json::to_string_pretty(session)
            .map_err(TuiError::Serialization)?;

        // Write to temporary sibling file first then rename for atomic persistence
        let tmp_path = path.with_extension("tmp");
        fs::write(&tmp_path, json_text)?;
        fs::rename(&tmp_path, &path)?;

        debug!("Saved session '{}' to {}", session.name, path.display());
        Ok(path)
    }

    /// Load a session record by name.
    pub fn get_session(&self, name: &str) -> Result<Option<SessionRecord>> {
        let path = self.session_file_path(name);
        if !path.is_file() {
            return Ok(None);
        }

        let content = fs::read_to_string(&path)?;
        let record: SessionRecord = serde_json::from_str(&content)
            .map_err(TuiError::Serialization)?;
        Ok(Some(record))
    }

    /// List all persisted session records, sorted by `last_activity` descending.
    pub fn list_sessions(&self) -> Result<Vec<SessionRecord>> {
        let mut sessions = Vec::new();
        if !self.base_dir.is_dir() {
            return Ok(sessions);
        }

        for entry in fs::read_dir(&self.base_dir)?.flatten() {
            let path = entry.path();
            if path.is_file() && path.extension().and_then(|s| s.to_str()) == Some("json") {
                if let Ok(content) = fs::read_to_string(&path) {
                    if let Ok(record) = serde_json::from_str::<SessionRecord>(&content) {
                        sessions.push(record);
                    }
                }
            }
        }

        // Sort descending by last_activity ISO timestamp
        sessions.sort_by(|a, b| b.last_activity.cmp(&a.last_activity));
        Ok(sessions)
    }

    /// Delete a session by name. Returns true if file was found and removed.
    pub fn delete_session(&self, name: &str) -> Result<bool> {
        let path = self.session_file_path(name);
        if path.is_file() {
            fs::remove_file(path)?;
            info!("Deleted session '{}'", name);
            Ok(true)
        } else {
            Ok(false)
        }
    }

    /// Clean / prune all stale or inactive sessions. Returns count of deleted sessions.
    pub fn clean_sessions(&self) -> Result<usize> {
        let mut count = 0;
        let sessions = self.list_sessions()?;
        for s in sessions {
            // Delete if status is completed/inactive/stale
            if !s.active || s.status == "completed" || s.status == "inactive" || s.workers.is_empty() {
                if self.delete_session(&s.name)? {
                    count += 1;
                }
            }
        }
        info!("Cleaned {} inactive/empty sessions", count);
        Ok(count)
    }

    /// Touch session activity and update step/interaction metrics.
    pub fn touch_activity(&self, name: &str, steps_delta: usize, interactions_delta: usize) -> Result<()> {
        if let Some(mut session) = self.get_session(name)? {
            session.last_activity = now_iso();
            session.total_steps += steps_delta;
            session.total_interactions += interactions_delta;
            self.save_session(&session)?;
        }
        Ok(())
    }

    /// Create and provision a standard default session with discovered host agent slots.
    pub fn create_default_session(&self, name: &str) -> SessionRecord {
        let mut record = SessionRecord::new(
            name,
            "Multi-Agent AI Orchestration & Parallel Systems Engineering",
        );

        let discovered_slots = IdentityDiscovery::discover_slots();
        if discovered_slots.is_empty() {
            // Standard fallback slots
            record.add_worker(SessionWorkerConfig {
                id: "coordinator".to_string(),
                slot_id: "agy1".to_string(),
                role: "Lead Orchestrator".to_string(),
                model: "gemini-3.8-flash-high".to_string(),
                task: Some("Overseeing multi-agent fleet".to_string()),
                command: None,
                args: None,
                env: None,
            });
            record.add_worker(SessionWorkerConfig {
                id: "worker-backend".to_string(),
                slot_id: "agy11".to_string(),
                role: "Backend Logic & Systems".to_string(),
                model: "gemini-3.8-flash-high".to_string(),
                task: Some("Core systems & API architecture".to_string()),
                command: None,
                args: None,
                env: None,
            });
            record.add_worker(SessionWorkerConfig {
                id: "worker-frontend".to_string(),
                slot_id: "agy51".to_string(),
                role: "Frontend & UI/UX".to_string(),
                model: "gemini-3.8-flash-high".to_string(),
                task: Some("Widget rendering & visual polish".to_string()),
                command: None,
                args: None,
                env: None,
            });
        } else {
            // Populate workers from real discovered slots
            for slot in discovered_slots {
                let id = if slot.slot_id == 1 {
                    "coordinator".to_string()
                } else {
                    slot.name.clone()
                };

                record.add_worker(SessionWorkerConfig {
                    id,
                    slot_id: slot.name,
                    role: slot.role,
                    model: slot.model,
                    task: slot.task,
                    command: None,
                    args: None,
                    env: None,
                });
            }
        }

        record
    }
}

/// Helper returning current timestamp in ISO 8601 format.
fn now_iso() -> String {
    use std::time::SystemTime;
    let now = SystemTime::now();
    let duration = now.duration_since(SystemTime::UNIX_EPOCH).unwrap_or_default();
    let secs = duration.as_secs();
    // Simple format YYYY-MM-DDTHH:MM:SSZ
    let days = secs / 86400;
    let rem_secs = secs % 86400;
    let hours = rem_secs / 3600;
    let mins = (rem_secs % 3600) / 60;
    let s = rem_secs % 60;

    // Approximate year/month/day conversion from days since 1970-01-01
    let (year, month, day) = days_to_ymd(days);
    format!("{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z", year, month, day, hours, mins, s)
}

fn days_to_ymd(days: u64) -> (u64, u64, u64) {
    let mut d = days;
    let mut year = 1970;
    loop {
        let leap = if year % 4 == 0 && (year % 100 != 0 || year % 400 == 0) { 1 } else { 0 };
        let days_in_year = 365 + leap;
        if d >= days_in_year {
            d -= days_in_year;
            year += 1;
        } else {
            break;
        }
    }
    let leap = if year % 4 == 0 && (year % 100 != 0 || year % 400 == 0) { 1 } else { 0 };
    let month_days = [31, 28 + leap, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let mut month = 1;
    for &md in &month_days {
        if d >= md {
            d -= md;
            month += 1;
        } else {
            break;
        }
    }
    let day = d + 1;
    (year, month, day)
}
