use std::fs;
use tempfile::tempdir;

use tui_core::session::identity::{AgentSlot, IdentityDiscovery};

#[test]
fn test_slot_id_parsing() {
    assert_eq!(IdentityDiscovery::parse_slot_id("agy1"), Some(1));
    assert_eq!(IdentityDiscovery::parse_slot_id("agy11"), Some(11));
    assert_eq!(IdentityDiscovery::parse_slot_id("agy51"), Some(51));
    assert_eq!(IdentityDiscovery::parse_slot_id("agy100"), Some(100));
    assert_eq!(IdentityDiscovery::parse_slot_id("agy151"), Some(151));
    assert_eq!(IdentityDiscovery::parse_slot_id("Worker-42"), Some(42));
    assert_eq!(IdentityDiscovery::parse_slot_id("99"), Some(99));
    assert_eq!(IdentityDiscovery::parse_slot_id("coordinator"), None);
    assert_eq!(IdentityDiscovery::parse_slot_id(""), None);
}

#[test]
fn test_slot_discovery_role_precedence_and_heuristics() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let instances = tmp.path().join("instances");
    fs::create_dir_all(&instances).unwrap();

    // Slot 1: Primary Coordinator (heuristic fallback)
    let s1_dir = instances.join("agy1");
    fs::create_dir_all(&s1_dir).unwrap();

    // Slot 25: Role extracted from .gemini/GEMINI.md
    let s25_dir = instances.join("agy25");
    let s25_gemini = s25_dir.join(".gemini");
    fs::create_dir_all(&s25_gemini).unwrap();
    fs::write(
        s25_gemini.join("GEMINI.md"),
        "# Role & Guidelines: Core Math & Compiler Engineer (agy25 - agy30)\nGuidelines here.\n",
    )
    .unwrap();

    // Slot 75: Role from domain heuristic range (51..=100)
    let s75_dir = instances.join("agy75");
    fs::create_dir_all(&s75_dir).unwrap();

    // Slot 125: Role from domain heuristic range (101..=150)
    let s125_dir = instances.join("agy125");
    fs::create_dir_all(&s125_dir).unwrap();

    // Slot 175: Role from domain heuristic range (151..=200)
    let s175_dir = instances.join("agy175");
    fs::create_dir_all(&s175_dir).unwrap();

    let slots = IdentityDiscovery::discover_slots_in(&instances);
    assert_eq!(slots.len(), 5);

    // Verify Slot 1
    let slot1 = slots.iter().find(|s| s.slot_id == 1).unwrap();
    assert!(slot1.role.contains("Coordinator") || slot1.role.contains("Orchestrator"));

    // Verify Slot 25 (from GEMINI.md, stripping trailing parenthesized range)
    let slot25 = slots.iter().find(|s| s.slot_id == 25).unwrap();
    assert_eq!(slot25.role, "Core Math & Compiler Engineer");

    // Verify Slot 75 heuristic (Frontend & UI/UX Auditing)
    let slot75 = slots.iter().find(|s| s.slot_id == 75).unwrap();
    assert!(slot75.role.contains("Frontend"));

    // Verify Slot 125 heuristic (Testing, Verification & Gatekeepers)
    let slot125 = slots.iter().find(|s| s.slot_id == 125).unwrap();
    assert!(slot125.role.contains("Testing") || slot125.role.contains("Verification") || slot125.role.contains("Gatekeeper"));

    // Verify Slot 175 heuristic (Finishing, Polish & UX Optimization)
    let slot175 = slots.iter().find(|s| s.slot_id == 175).unwrap();
    assert!(slot175.role.contains("Polish") || slot175.role.contains("Finishing") || slot175.role.contains("UX"));
}

#[test]
fn test_slot_settings_model_and_token_extraction() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let instances = tmp.path().join("instances");
    let slot_dir = instances.join("agy33");
    let cli_dir = slot_dir.join(".gemini").join("antigravity-cli");
    fs::create_dir_all(&cli_dir).unwrap();

    // 1. Model in settings.json
    fs::write(
        cli_dir.join("settings.json"),
        r#"{"model": "claude-3-7-sonnet"}"#,
    )
    .unwrap();

    // 2. Token in token.json with direct email
    fs::write(
        slot_dir.join("token.json"),
        r#"{"email": "agent33@mind.ai"}"#,
    )
    .unwrap();

    let slots = IdentityDiscovery::discover_slots_in(&instances);
    assert_eq!(slots.len(), 1);
    let s = &slots[0];
    assert_eq!(s.slot_id, 33);
    assert_eq!(s.model, "claude-3-7-sonnet");
    assert!(s.has_token);
    assert_eq!(s.email.as_deref(), Some("agent33@mind.ai"));
}

#[test]
fn test_slot_jwt_email_extraction() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let instances = tmp.path().join("instances");
    let slot_dir = instances.join("agy88");
    fs::create_dir_all(&slot_dir).unwrap();

    // JWT with payload: {"email":"jwt_agent@google.com","sub":"12345"}
    // Base64URL for {"email":"jwt_agent@google.com","sub":"12345"}:
    // eyJlbWFpbCI6Imp3dF9hZ2VudEBnb29nbGUuY29tIiwic3ViIjoiMTIzNDUifQ
    let mock_jwt = "header.eyJlbWFpbCI6Imp3dF9hZ2VudEBnb29nbGUuY29tIiwic3ViIjoiMTIzNDUifQ.signature";

    fs::write(
        slot_dir.join("token.json"),
        format!(r#"{{"id_token": "{}"}}"#, mock_jwt),
    )
    .unwrap();

    let slots = IdentityDiscovery::discover_slots_in(&instances);
    assert_eq!(slots.len(), 1);
    let s = &slots[0];
    assert_eq!(s.email.as_deref(), Some("jwt_agent@google.com"));
    assert!(s.has_token);
}

#[test]
fn test_slot_environment_isolation_builder() {
    let instance_path = std::path::PathBuf::from("/opt/agy-instances/agy77");
    let slot = AgentSlot::new(
        77,
        "agy77",
        instance_path.clone(),
        "Specialist",
        "gemini-3.8-flash-high",
        Some("Build harness".to_string()),
        true,
        Some("agy77@test.com".to_string()),
    );

    let env = IdentityDiscovery::build_slot_isolation_env(&slot);

    // Verify key isolation variables
    assert_eq!(env.get("AGY_SLOT").unwrap(), "77");
    let has_agys = IdentityDiscovery::find_agys_binary().is_some();
    if has_agys {
        assert_eq!(
            env.get("HOME").unwrap(),
            &IdentityDiscovery::get_real_user_home().to_string_lossy().to_string()
        );
        assert_eq!(
            env.get("USERPROFILE").unwrap(),
            &IdentityDiscovery::get_real_user_home().to_string_lossy().to_string()
        );
    } else {
        assert_eq!(env.get("HOME").unwrap(), "/opt/agy-instances/agy77");
        assert_eq!(env.get("USERPROFILE").unwrap(), "/opt/agy-instances/agy77");
        assert_eq!(
            env.get("ANTIGRAVITY_APP_DATA_DIR").unwrap(),
            "/opt/agy-instances/agy77/.gemini/antigravity-cli"
        );
    }
    assert_eq!(env.get("AGY_INSTANCE_DIR").unwrap(), "/opt/agy-instances/agy77");
    assert!(env.contains_key("MIND_REAL_USER_HOME"));
}

#[test]
fn test_host_real_slot_lookup() {
    let slots = IdentityDiscovery::discover_slots();
    assert!(!slots.is_empty(), "Host must have at least one real slot");

    // Test find_slot by numeric string or agy prefix
    if let Some(first) = slots.first() {
        let by_name = IdentityDiscovery::find_slot(&first.name);
        assert!(by_name.is_some());
        assert_eq!(by_name.unwrap().slot_id, first.slot_id);

        let by_id = IdentityDiscovery::find_slot(&first.slot_id.to_string());
        assert!(by_id.is_some());
        assert_eq!(by_id.unwrap().name, first.name);
    }
}
