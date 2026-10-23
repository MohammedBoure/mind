use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use serde::{Deserialize, Serialize};
use tracing::debug;

/// Metadata representing an Antigravity worker slot and its isolated environment.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AgentSlot {
    pub slot_id: u32,
    pub name: String,
    pub instance_dir: PathBuf,
    pub role: String,
    pub model: String,
    pub task: Option<String>,
    pub has_token: bool,
    pub email: Option<String>,
    pub is_active: bool,
}

impl AgentSlot {
    /// Create a new AgentSlot descriptor.
    pub fn new(
        slot_id: u32,
        name: impl Into<String>,
        instance_dir: PathBuf,
        role: impl Into<String>,
        model: impl Into<String>,
        task: Option<String>,
        has_token: bool,
        email: Option<String>,
    ) -> Self {
        Self {
            slot_id,
            name: name.into(),
            instance_dir,
            role: role.into(),
            model: model.into(),
            task,
            has_token,
            email,
            is_active: true,
        }
    }
}

/// Dynamic discovery engine for host `agy[x]` agent slots under `~/.local/share/agy-instances/agy[x]`.
pub struct IdentityDiscovery;

impl IdentityDiscovery {
    /// Resolve the root directory where `agy-instances` reside.
    pub fn get_instances_dir() -> PathBuf {
        if let Ok(dir) = std::env::var("AGY_INSTANCES_DIR") {
            let p = PathBuf::from(dir);
            if p.is_dir() {
                return p;
            }
        }

        let home = Self::get_real_user_home();
        let primary = home.join(".local").join("share").join("agy-instances");
        if primary.is_dir() {
            return primary;
        }

        // Secondary fallback
        let fallback = home.join(".gemini").join("instances");
        if fallback.is_dir() {
            return fallback;
        }

        primary
    }

    /// Resolve true host user home directory, escaping any slot-nested instance paths.
    pub fn get_real_user_home() -> PathBuf {
        if let Ok(real) = std::env::var("MIND_REAL_USER_HOME") {
            let p = PathBuf::from(real);
            if p.is_dir() {
                return p;
            }
        }

        if let Ok(home) = std::env::var("HOME") {
            let p = PathBuf::from(home);
            // If already pointing inside an agy-instances directory, resolve the parent root
            let s = p.to_string_lossy();
            if let Some(idx) = s.find("/.local/share/agy-instances") {
                let recovered = PathBuf::from(&s[..idx]);
                if recovered.is_dir() {
                    return recovered;
                }
            }
            if p.is_dir() {
                return p;
            }
        }

        PathBuf::from("/home/pluto")
    }

    /// Discover all available agent slots installed on the system.
    pub fn discover_slots() -> Vec<AgentSlot> {
        let instances_dir = Self::get_instances_dir();
        Self::discover_slots_in(&instances_dir)
    }

    /// Discover slots located in a specific directory (useful for testing and custom mounts).
    pub fn discover_slots_in(dir: &Path) -> Vec<AgentSlot> {
        let mut slots = Vec::new();
        if !dir.is_dir() {
            debug!("Instances directory '{}' does not exist", dir.display());
            return slots;
        }

        let assignments = Self::load_workspace_assignments();

        if let Ok(entries) = fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if !path.is_dir() {
                    continue;
                }

                let filename = entry.file_name();
                let name = filename.to_string_lossy().to_string();

                if let Some(slot_id) = Self::parse_slot_id(&name) {
                    let (role, model, task, has_token, email) = Self::inspect_slot(&path, slot_id, &assignments);
                    slots.push(AgentSlot::new(
                        slot_id,
                        name,
                        path,
                        role,
                        model,
                        task,
                        has_token,
                        email,
                    ));
                }
            }
        }

        slots.sort_by_key(|s| s.slot_id);
        slots
    }

    /// Find slot by ID or name (e.g. 11 or "agy11").
    pub fn find_slot(id_or_name: &str) -> Option<AgentSlot> {
        let slots = Self::discover_slots();
        let target_id = Self::parse_slot_id(id_or_name);

        slots.into_iter().find(|s| {
            s.name.eq_ignore_ascii_case(id_or_name)
                || target_id.map(|tid| tid == s.slot_id).unwrap_or(false)
        })
    }

    /// Parse slot integer index from name like "agy11", "Worker-51", or "100".
    pub fn parse_slot_id(s: &str) -> Option<u32> {
        let digits: String = s.chars().filter(|c| c.is_ascii_digit()).collect();
        if digits.is_empty() {
            None
        } else {
            digits.parse::<u32>().ok()
        }
    }

    /// Build isolated environment variables for spawning an agent process in a slot.
    pub fn build_slot_isolation_env(slot: &AgentSlot) -> HashMap<String, String> {
        let mut env = HashMap::new();
        let inst_str = slot.instance_dir.to_string_lossy().to_string();

        env.insert("USERPROFILE".to_string(), inst_str.clone());
        env.insert("HOME".to_string(), inst_str.clone());
        env.insert("AGY_SLOT".to_string(), slot.slot_id.to_string());
        env.insert("AGY_INSTANCE_DIR".to_string(), inst_str.clone());
        env.insert(
            "ANTIGRAVITY_APP_DATA_DIR".to_string(),
            slot.instance_dir.join(".gemini").join("antigravity-cli").to_string_lossy().to_string(),
        );

        let real_home = Self::get_real_user_home().to_string_lossy().to_string();
        env.insert("MIND_REAL_USER_HOME".to_string(), real_home);

        env
    }

    /// Inspect an individual slot directory to extract role, model, token status, and email.
    fn inspect_slot(
        slot_dir: &Path,
        slot_id: u32,
        assignments: &HashMap<String, (String, Option<String>)>,
    ) -> (String, String, Option<String>, bool, Option<String>) {
        // 1. Role & Task: Check workspace agent_assignments.json first
        let slot_name = format!("agy{}", slot_id);
        let mut role = assignments
            .get(&slot_name)
            .or_else(|| assignments.get(&slot_id.to_string()))
            .map(|(r, _)| r.clone());

        let task = assignments
            .get(&slot_name)
            .or_else(|| assignments.get(&slot_id.to_string()))
            .and_then(|(_, t)| t.clone());

        // Fallback role detection from .gemini/GEMINI.md
        if role.is_none() {
            let gemini_md = slot_dir.join(".gemini").join("GEMINI.md");
            if gemini_md.is_file() {
                if let Ok(content) = fs::read_to_string(gemini_md) {
                    for line in content.lines() {
                        let trimmed = line.trim();
                        if trimmed.starts_with("# Role & Guidelines:") || trimmed.starts_with("# Role:") {
                            let extracted = trimmed
                                .trim_start_matches("# Role & Guidelines:")
                                .trim_start_matches("# Role:")
                                .trim();
                            // e.g. "Backend Logic & Systems Engineer (agy11 - agy50)" -> strip parenthesized range
                            let clean_role = if let Some(idx) = extracted.find('(') {
                                extracted[..idx].trim().to_string()
                            } else {
                                extracted.to_string()
                            };
                            if !clean_role.is_empty() {
                                role = Some(clean_role);
                                break;
                            }
                        }
                    }
                }
            }
        }

        // Domain heuristic based on slot ID ranges
        let final_role = role.unwrap_or_else(|| match slot_id {
            1 => "Primary Coordinator & Lead Orchestrator".to_string(),
            2..=10 => "Systems & Architecture".to_string(),
            11..=50 => "Backend Logic, Systems & Math".to_string(),
            51..=100 => "Frontend & UI/UX Auditing".to_string(),
            101..=150 => "Testing, Verification & Gatekeepers".to_string(),
            151..=200 => "Finishing, Polish & UX Optimization".to_string(),
            _ => format!("Autonomous Worker (Slot {})", slot_id),
        });

        // 2. Model: Read from .gemini/antigravity-cli/settings.json
        let mut model = "gemini-3.8-flash-high".to_string();
        let settings_json = slot_dir.join(".gemini").join("antigravity-cli").join("settings.json");
        if settings_json.is_file() {
            if let Ok(content) = fs::read_to_string(&settings_json) {
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                    if let Some(m) = val.get("model").and_then(|v| v.as_str()) {
                        model = m.to_string();
                    }
                }
            }
        }

        // 3. Token presence & Email extraction
        let token_file = slot_dir.join("token.json");
        let oauth_token = slot_dir.join(".gemini").join("antigravity-cli").join("antigravity-oauth-token");
        let has_token = token_file.is_file() || oauth_token.is_file();

        let mut email = None;
        if token_file.is_file() {
            if let Ok(content) = fs::read_to_string(&token_file) {
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                    if let Some(e) = val.get("email").and_then(|v| v.as_str()) {
                        email = Some(e.to_string());
                    } else if let Some(id_token) = val.get("id_token").and_then(|v| v.as_str()) {
                        email = Self::extract_email_from_jwt(id_token);
                    }
                }
            }
        }

        (final_role, model, task, has_token, email)
    }

    /// Extract email claim from JWT id_token without external crypto dependencies.
    fn extract_email_from_jwt(jwt: &str) -> Option<String> {
        let parts: Vec<&str> = jwt.split('.').collect();
        if parts.len() < 2 {
            return None;
        }

        let payload_b64 = parts[1];
        // Standard base64 URL-safe decoding with padding
        let mut s = payload_b64.replace('-', "+").replace('_', "/");
        while s.len() % 4 != 0 {
            s.push('=');
        }

        // Simple manual or byte decode for standard JSON payload
        if let Ok(decoded_bytes) = simple_b64_decode(&s) {
            if let Ok(payload_str) = String::from_utf8(decoded_bytes) {
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&payload_str) {
                    if let Some(em) = val.get("email").and_then(|v| v.as_str()) {
                        return Some(em.to_string());
                    }
                }
            }
        }

        None
    }

    /// Load agent roles and tasks from root `agent_assignments.json` if available.
    fn load_workspace_assignments() -> HashMap<String, (String, Option<String>)> {
        let mut map = HashMap::new();
        let candidates = [
            PathBuf::from("agent_assignments.json"),
            PathBuf::from("../agent_assignments.json"),
        ];

        for p in candidates {
            if p.is_file() {
                if let Ok(content) = fs::read_to_string(&p) {
                    if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                        if let Some(assignments) = val.get("assignments").and_then(|v| v.as_array()) {
                            for item in assignments {
                                let agent_id = item.get("agent_id").and_then(|v| v.as_str()).unwrap_or_default();
                                let role = item.get("role").and_then(|v| v.as_str()).unwrap_or("Autonomous Worker");
                                let task = item.get("scope").and_then(|v| v.as_str()).map(ToString::to_string);
                                if !agent_id.is_empty() {
                                    map.insert(agent_id.to_string(), (role.to_string(), task));
                                }
                            }
                        }
                    }
                }
                break;
            }
        }

        map
    }
}

/// Fallback base64 decoder for JWT claim extraction.
fn simple_b64_decode(input: &str) -> std::result::Result<Vec<u8>, ()> {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = Vec::new();
    let mut buf: u32 = 0;
    let mut bits = 0;

    for &b in input.as_bytes() {
        if b == b'=' {
            break;
        }
        let val = match TABLE.iter().position(|&x| x == b) {
            Some(idx) => idx as u32,
            None => continue,
        };
        buf = (buf << 6) | val;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((buf >> bits) as u8);
        }
    }

    Ok(out)
}
