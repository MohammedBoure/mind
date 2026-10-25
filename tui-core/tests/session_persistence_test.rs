use std::collections::HashMap;
use tempfile::tempdir;

use tui_core::session::session_store::{SessionRecord, SessionStore, SessionWorkerConfig};

#[test]
fn test_session_record_construction_and_serialization() {
    let mut record = SessionRecord::new("swarm_core", "Core architecture verification");
    assert_eq!(record.name, "swarm_core");
    assert_eq!(record.goal, "Core architecture verification");
    assert!(record.active);
    assert_eq!(record.status, "active");
    assert_eq!(record.agent_count, 0);
    assert!(record.workers.is_empty());

    let mut custom_env = HashMap::new();
    custom_env.insert("MIND_TEST_VAR".to_string(), "TRUE".to_string());

    record.add_worker(SessionWorkerConfig {
        id: "coordinator".to_string(),
        slot_id: "agy1".to_string(),
        role: "Lead Orchestrator".to_string(),
        model: "gemini-3.8-flash-high".to_string(),
        task: Some("Supervising fleet".to_string()),
        command: Some("bash".to_string()),
        args: Some(vec!["-i".to_string()]),
        env: Some(custom_env),
    });

    assert_eq!(record.agent_count, 1);
    assert_eq!(record.workers.len(), 1);

    // Verify JSON serialization round-trip
    let json_text = serde_json::to_string_pretty(&record).expect("Serialize session record");
    assert!(json_text.contains("\"name\": \"swarm_core\""));
    assert!(json_text.contains("\"slot_id\": \"agy1\""));
    assert!(json_text.contains("\"MIND_TEST_VAR\": \"TRUE\""));

    let deserialized: SessionRecord = serde_json::from_str(&json_text).expect("Deserialize session record");
    assert_eq!(record, deserialized);
}

#[test]
fn test_session_store_atomic_file_operations_and_sanitization() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let store = SessionStore::with_dir(tmp.path().join("sessions"));

    // 1. Name sanitization
    assert_eq!(SessionStore::sanitize_name("my session 1"), "my_session_1");
    assert_eq!(SessionStore::sanitize_name("alpha/beta:v1.0"), "alpha_beta_v1_0");
    assert_eq!(SessionStore::sanitize_name("swarm-test_2026"), "swarm-test_2026");

    // 2. Atomic save
    let session = SessionRecord::new("mission critical", "Zero corruption test");
    let saved_path = store.save_session(&session).expect("Save session");
    assert!(saved_path.is_file());
    assert_eq!(saved_path.file_name().unwrap(), "mission_critical.json");

    // Temporary sibling file (.tmp) must be cleaned up / renamed
    let tmp_sibling = saved_path.with_extension("tmp");
    assert!(!tmp_sibling.exists(), "Temporary write file should not remain after rename");

    // 3. Load back
    let loaded = store.get_session("mission critical").expect("Load session").expect("Session exists");
    assert_eq!(loaded.name, "mission critical");
    assert_eq!(loaded.goal, "Zero corruption test");
}

#[test]
fn test_session_store_activity_tracking_and_metrics() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let store = SessionStore::with_dir(tmp.path().join("sessions"));

    let session = SessionRecord::new("metric_tracker", "Measure interactions");
    store.save_session(&session).expect("Save session");

    // Initial metrics
    let s0 = store.get_session("metric_tracker").unwrap().unwrap();
    assert_eq!(s0.total_steps, 0);
    assert_eq!(s0.total_interactions, 0);
    let _initial_timestamp = s0.last_activity.clone();

    // Increment activity metrics
    store.touch_activity("metric_tracker", 25, 12).expect("Touch activity");
    let s1 = store.get_session("metric_tracker").unwrap().unwrap();
    assert_eq!(s1.total_steps, 25);
    assert_eq!(s1.total_interactions, 12);

    // Another increment
    store.touch_activity("metric_tracker", 5, 3).expect("Second touch activity");
    let s2 = store.get_session("metric_tracker").unwrap().unwrap();
    assert_eq!(s2.total_steps, 30);
    assert_eq!(s2.total_interactions, 15);
    assert!(!s2.last_activity.is_empty());
}

#[test]
fn test_session_store_listing_and_sorting() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let store = SessionStore::with_dir(tmp.path().join("sessions"));

    let mut s1 = SessionRecord::new("sess_early", "Early session");
    s1.last_activity = "2026-10-23T10:00:00Z".to_string();
    store.save_session(&s1).unwrap();

    let mut s2 = SessionRecord::new("sess_late", "Late session");
    s2.last_activity = "2026-10-23T20:00:00Z".to_string();
    store.save_session(&s2).unwrap();

    let mut s3 = SessionRecord::new("sess_mid", "Mid session");
    s3.last_activity = "2026-10-23T15:00:00Z".to_string();
    store.save_session(&s3).unwrap();

    let list = store.list_sessions().expect("List sessions");
    assert_eq!(list.len(), 3);
    // Must be sorted descending by last_activity
    assert_eq!(list[0].name, "sess_late");
    assert_eq!(list[1].name, "sess_mid");
    assert_eq!(list[2].name, "sess_early");
}

#[test]
fn test_session_store_deletion_and_pruning_clean() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let store = SessionStore::with_dir(tmp.path().join("sessions"));

    // 1. Active session with workers -> should NOT be pruned
    let mut s_active = SessionRecord::new("active_swarm", "Active fleet");
    s_active.active = true;
    s_active.status = "active".to_string();
    s_active.add_worker(SessionWorkerConfig {
        id: "worker-1".to_string(),
        slot_id: "agy1".to_string(),
        role: "Worker".to_string(),
        model: "gemini".to_string(),
        task: None,
        command: None,
        args: None,
        env: None,
    });
    store.save_session(&s_active).unwrap();

    // 2. Inactive session -> SHOULD be pruned
    let mut s_inactive = SessionRecord::new("inactive_swarm", "Old fleet");
    s_inactive.active = false;
    s_inactive.status = "inactive".to_string();
    s_inactive.add_worker(SessionWorkerConfig {
        id: "worker-2".to_string(),
        slot_id: "agy2".to_string(),
        role: "Worker".to_string(),
        model: "gemini".to_string(),
        task: None,
        command: None,
        args: None,
        env: None,
    });
    store.save_session(&s_inactive).unwrap();

    // 3. Completed session -> SHOULD be pruned
    let mut s_completed = SessionRecord::new("completed_swarm", "Done fleet");
    s_completed.active = true;
    s_completed.status = "completed".to_string();
    s_completed.add_worker(SessionWorkerConfig {
        id: "worker-3".to_string(),
        slot_id: "agy3".to_string(),
        role: "Worker".to_string(),
        model: "gemini".to_string(),
        task: None,
        command: None,
        args: None,
        env: None,
    });
    store.save_session(&s_completed).unwrap();

    // 4. Session with 0 workers -> SHOULD be pruned
    let s_empty = SessionRecord::new("empty_swarm", "No workers");
    store.save_session(&s_empty).unwrap();

    assert_eq!(store.list_sessions().unwrap().len(), 4);

    // Run clean pruning
    let cleaned_count = store.clean_sessions().expect("Clean sessions");
    assert_eq!(cleaned_count, 3, "Expected 3 sessions to be pruned");

    let remaining = store.list_sessions().unwrap();
    assert_eq!(remaining.len(), 1);
    assert_eq!(remaining[0].name, "active_swarm");

    // Explicit deletion of remaining session
    let deleted = store.delete_session("active_swarm").expect("Delete session");
    assert!(deleted);
    assert!(store.get_session("active_swarm").unwrap().is_none());
    assert_eq!(store.list_sessions().unwrap().len(), 0);

    // Deleting non-existent session returns false
    let not_found = store.delete_session("non_existent").unwrap();
    assert!(!not_found);
}

#[test]
fn test_default_session_provisioning() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let store = SessionStore::with_dir(tmp.path().join("sessions"));

    let default_session = store.create_default_session("default_test");
    assert_eq!(default_session.name, "default_test");
    assert!(!default_session.workers.is_empty(), "Default session should have workers");
    assert!(default_session.workers.iter().any(|w| w.slot_id.contains("agy1")));

    let saved = store.save_session(&default_session).expect("Save default session");
    assert!(saved.is_file());
}

#[test]
fn test_find_by_working_dir_and_project_session_isolation() {
    let tmp = tempdir().expect("Failed to create tempdir");
    let store = SessionStore::with_dir(tmp.path().join("sessions"));

    let project_dir_a = tmp.path().join("project_alpha");
    let project_dir_b = tmp.path().join("project_beta");
    std::fs::create_dir_all(&project_dir_a).unwrap();
    std::fs::create_dir_all(&project_dir_b).unwrap();

    let session_a = store.create_default_session_for_dir("project_alpha", &project_dir_a);
    store.save_session(&session_a).unwrap();

    let session_b = store.create_default_session_for_dir("project_beta", &project_dir_b);
    store.save_session(&session_b).unwrap();

    // Verify lookup by working dir returns distinct sessions
    let found_a = store.find_by_working_dir(&project_dir_a).unwrap();
    assert!(found_a.is_some());
    assert_eq!(found_a.unwrap().name, "project_alpha");

    let found_b = store.find_by_working_dir(&project_dir_b).unwrap();
    assert!(found_b.is_some());
    assert_eq!(found_b.unwrap().name, "project_beta");

    // Non-existent directory returns None
    let other_dir = tmp.path().join("other_project");
    assert!(store.find_by_working_dir(&other_dir).unwrap().is_none());
}
