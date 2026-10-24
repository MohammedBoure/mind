use std::path::Path;
use tui_core::session::identity::{is_executable_binary, IdentityDiscovery};
use tui_core::session::session_store::SessionWorkerConfig;
use tui_core::session::shortcuts::AgiConfig;
use tui_core::session::{SessionManager, WorkerSession};

// ── 1. Detection of real agy binary ───────────────────────────────────

#[test]
fn test_find_agy_binary_detection() {
    let agy_path = IdentityDiscovery::find_agy_binary();
    assert!(
        agy_path.is_some(),
        "Expected IdentityDiscovery to locate real agy binary on host"
    );

    let path = agy_path.unwrap();
    assert!(path.is_file(), "Located agy path must be a regular file: {:?}", path);
    assert!(
        is_executable_binary(&path),
        "Located agy path must be executable: {:?}",
        path
    );

    // WorkerSession helper parity
    let worker_detected = WorkerSession::find_agy_binary();
    assert_eq!(worker_detected, Some(path));
    assert!(WorkerSession::is_agy_available());
}

// ── 2. Coordinator (Slot 1) Isolated Environment ─────────────────────

#[test]
fn test_coordinator_slot_1_environment_isolation() {
    // Test both "coordinator", "agy1", and "1"
    for slot_key in &["coordinator", "agy1", "1"] {
        let env = IdentityDiscovery::build_slot_env_by_id(slot_key);

        assert_eq!(
            env.get("AGY_SLOT").map(|s| s.as_str()),
            Some("1"),
            "Coordinator slot must have AGY_SLOT = 1 (key: {})",
            slot_key
        );

        let has_agys = IdentityDiscovery::find_agys_binary().is_some();
        let userprofile = env.get("USERPROFILE").expect("USERPROFILE must be set");
        let home = env.get("HOME").expect("HOME must be set");
        if has_agys {
            assert!(
                !home.is_empty(),
                "Coordinator HOME must be populated with host home for agys bwrap isolation"
            );
            assert!(
                !userprofile.is_empty(),
                "Coordinator USERPROFILE must be populated with host home for agys bwrap isolation"
            );
        } else {
            assert!(
                home.ends_with("agy1"),
                "Coordinator HOME must end with agy1 in direct fallback mode: {}",
                home
            );
            assert!(
                userprofile.ends_with("agy1"),
                "Coordinator USERPROFILE must end with agy1 in direct fallback mode: {}",
                userprofile
            );
        }

        let inst_dir = env.get("AGY_INSTANCE_DIR").expect("AGY_INSTANCE_DIR must be set");
        assert!(
            inst_dir.ends_with("agy1"),
            "Coordinator AGY_INSTANCE_DIR must end with agy1: {}",
            inst_dir
        );

        let real_home = env.get("MIND_REAL_USER_HOME").expect("MIND_REAL_USER_HOME must be set");
        assert!(
            !real_home.is_empty(),
            "Coordinator MIND_REAL_USER_HOME must be populated"
        );
    }
}

// ── 3. Worker Slots Isolated Environments ─────────────────────────────

#[test]
fn test_worker_slot_environment_isolation() {
    let test_slots = [
        ("agy11", "11"),
        ("agy51", "51"),
        ("agy100", "100"),
        ("agy151", "151"),
        ("42", "42"),
    ];

    for (slot_key, expected_id) in test_slots {
        let env = IdentityDiscovery::build_slot_env_by_id(slot_key);

        assert_eq!(
            env.get("AGY_SLOT").map(|s| s.as_str()),
            Some(expected_id),
            "Worker slot must have AGY_SLOT = {} (key: {})",
            expected_id,
            slot_key
        );

        let expected_suffix = format!("agy{}", expected_id);
        let has_agys = IdentityDiscovery::find_agys_binary().is_some();
        let userprofile = env.get("USERPROFILE").expect("USERPROFILE must be set");
        let home = env.get("HOME").expect("HOME must be set");
        if has_agys {
            assert!(!home.is_empty(), "Worker HOME must be populated with host home");
            assert!(!userprofile.is_empty(), "Worker USERPROFILE must be populated with host home");
        } else {
            assert!(
                home.ends_with(&expected_suffix),
                "Worker HOME must end with {}: {}",
                expected_suffix,
                home
            );
            assert!(
                userprofile.ends_with(&expected_suffix),
                "Worker USERPROFILE must end with {}: {}",
                expected_suffix,
                userprofile
            );
        }

        let inst_dir = env.get("AGY_INSTANCE_DIR").expect("AGY_INSTANCE_DIR must be set");
        assert!(
            inst_dir.ends_with(&expected_suffix),
            "Worker AGY_INSTANCE_DIR must end with {}: {}",
            expected_suffix,
            inst_dir
        );
    }
}

// ── 4. AgiConfig auto_spawn_agy option ────────────────────────────────

#[test]
fn test_agi_config_auto_spawn_option() {
    // 1. Default config must have auto_spawn_agy = true
    let default_config = AgiConfig::default();
    assert!(
        default_config.general.auto_spawn_agy,
        "default auto_spawn_agy must be true"
    );

    // 2. Deserializing TOML without auto_spawn_agy defaults to true
    let toml_without = r#"
[general]
theme = "tokyo_night"
tick_rate_ms = 50
default_model = "gemini-3.8-flash-high"
"#;
    let parsed_default: AgiConfig = toml::from_str(toml_without).expect("Parse TOML without auto_spawn_agy");
    assert!(
        parsed_default.general.auto_spawn_agy,
        "auto_spawn_agy must default to true when omitted"
    );

    // 3. Deserializing TOML with auto_spawn_agy = false
    let toml_false = r#"
[general]
theme = "tokyo_night"
tick_rate_ms = 50
default_model = "gemini-3.8-flash-high"
auto_spawn_agy = false
"#;
    let parsed_false: AgiConfig = toml::from_str(toml_false).expect("Parse TOML with auto_spawn_agy = false");
    assert!(
        !parsed_false.general.auto_spawn_agy,
        "auto_spawn_agy must parse false when configured"
    );
}

// ── 5. SessionManager Command Resolution ──────────────────────────────

#[test]
fn test_session_manager_command_resolution() {
    let mut config = AgiConfig::default();
    config.general.auto_spawn_agy = true;
    let manager = SessionManager::with_config(&config);
    assert!(manager.auto_spawn_agy());

    let fallback_shell = "bash";

    // 1. When auto_spawn_agy is true and command is None -> resolves to agy binary
    let w_default = SessionWorkerConfig {
        id: "worker1".to_string(),
        slot_id: "agy11".to_string(),
        role: "Backend".to_string(),
        model: "gemini".to_string(),
        task: None,
        command: None,
        args: None,
        env: None,
    };
    let (resolved_cmd, _) = manager.resolve_worker_command(&w_default, fallback_shell);
    assert!(
        resolved_cmd.ends_with("agy") || resolved_cmd.ends_with("agys"),
        "When auto_spawn_agy is true, resolved command must be agy or agys launcher: {}",
        resolved_cmd
    );

    // 2. When auto_spawn_agy is true and command is Some("agy") -> resolves to agy or agys binary
    let w_agy = SessionWorkerConfig {
        id: "worker2".to_string(),
        slot_id: "agy51".to_string(),
        role: "Frontend".to_string(),
        model: "gemini".to_string(),
        task: None,
        command: Some("agy".to_string()),
        args: None,
        env: None,
    };
    let (resolved_cmd_2, _) = manager.resolve_worker_command(&w_agy, fallback_shell);
    assert!(
        resolved_cmd_2.ends_with("agy") || resolved_cmd_2.ends_with("agys"),
        "When command is 'agy', resolved command must be agy or agys launcher: {}",
        resolved_cmd_2
    );

    // 3. When auto_spawn_agy is toggled to false -> resolves to fallback shell
    manager.set_auto_spawn_agy(false);
    assert!(!manager.auto_spawn_agy());

    let (resolved_fallback, _) = manager.resolve_worker_command(&w_default, fallback_shell);
    assert_eq!(
        resolved_fallback, fallback_shell,
        "When auto_spawn_agy is false, command must be fallback shell"
    );

    // 4. Custom explicit command is always preserved
    let w_custom = SessionWorkerConfig {
        id: "custom_worker".to_string(),
        slot_id: "agy1".to_string(),
        role: "Custom".to_string(),
        model: "gemini".to_string(),
        task: None,
        command: Some("python3 custom_script.py".to_string()),
        args: Some(vec!["--flag".to_string()]),
        env: None,
    };
    manager.set_auto_spawn_agy(true);
    let (resolved_custom, args) = manager.resolve_worker_command(&w_custom, fallback_shell);
    assert_eq!(resolved_custom, "python3 custom_script.py");
    assert_eq!(args, vec!["--flag".to_string()]);
}

// ── 6. Fallback Behavior When Binary Is Not Executable ────────────────

#[test]
fn test_fallback_behavior_when_binary_not_executable() {
    let non_executable = Path::new("/tmp/non_existent_fake_agy_binary_12345");
    assert!(
        !is_executable_binary(non_executable),
        "Non-existent path must not be executable"
    );
}
