use std::collections::HashMap;
use std::fs;
use std::path::Path;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use serde::{Deserialize, Serialize};
use tracing::debug;

use crate::session::identity::IdentityDiscovery;

/// Semantic TUI actions mapped from keyboard events.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Action {
    Quit,
    Help,
    CycleFocus,
    CycleFocusReverse,
    DirectiveModal,
    DirectiveEditor,
    OpenExternalEditor,
    ToggleSplit,
    NewWorker,
    NextTab,
    PrevTab,
    SelectTab(usize),
    ScrollUp,
    ScrollDown,
    PassThrough,
}

/// Key combination parsed from configuration strings.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct KeyBinding {
    pub code: KeyCode,
    pub modifiers: KeyModifiers,
}

impl KeyBinding {
    pub fn new(code: KeyCode, modifiers: KeyModifiers) -> Self {
        Self { code, modifiers }
    }

    /// Parse human-readable key string like "q", "Ctrl+M", "Shift+Tab", "F5", "Esc".
    pub fn parse(s: &str) -> Option<Self> {
        let parts: Vec<&str> = s.split('+').map(str::trim).collect();
        let mut modifiers = KeyModifiers::NONE;

        if parts.is_empty() {
            return None;
        }

        for part in &parts[..parts.len() - 1] {
            match part.to_lowercase().as_str() {
                "ctrl" | "control" => modifiers |= KeyModifiers::CONTROL,
                "alt" => modifiers |= KeyModifiers::ALT,
                "shift" => modifiers |= KeyModifiers::SHIFT,
                _ => {}
            }
        }

        let key_str = parts.last().unwrap();
        let code = match key_str.to_lowercase().as_str() {
            "tab" => KeyCode::Tab,
            "backtab" => {
                modifiers |= KeyModifiers::SHIFT;
                KeyCode::BackTab
            }
            "esc" | "escape" => KeyCode::Esc,
            "enter" | "return" => KeyCode::Enter,
            "space" => KeyCode::Char(' '),
            "backspace" => KeyCode::Backspace,
            "delete" | "del" => KeyCode::Delete,
            "up" => KeyCode::Up,
            "down" => KeyCode::Down,
            "left" => KeyCode::Left,
            "right" => KeyCode::Right,
            "pageup" | "pgup" => KeyCode::PageUp,
            "pagedown" | "pgdn" => KeyCode::PageDown,
            "home" => KeyCode::Home,
            "end" => KeyCode::End,
            s if s.starts_with('f') && s.len() > 1 => {
                if let Ok(n) = s[1..].parse::<u8>() {
                    KeyCode::F(n)
                } else {
                    return None;
                }
            }
            s if s.len() == 1 => {
                let ch = s.chars().next().unwrap();
                KeyCode::Char(ch)
            }
            _ => return None,
        };

        Some(Self { code, modifiers })
    }

    /// Match against an incoming Crossterm KeyEvent.
    pub fn matches(&self, event: &KeyEvent) -> bool {
        if self.code == KeyCode::BackTab && event.code == KeyCode::BackTab {
            return true;
        }
        if self.code == KeyCode::Tab && self.modifiers.contains(KeyModifiers::SHIFT) && event.code == KeyCode::BackTab {
            return true;
        }

        // Match normalized character
        match (self.code, event.code) {
            (KeyCode::Char(c1), KeyCode::Char(c2)) => {
                c1.to_ascii_lowercase() == c2.to_ascii_lowercase()
                    && self.modifiers_match(event.modifiers)
            }
            (c1, c2) => c1 == c2 && self.modifiers_match(event.modifiers),
        }
    }

    fn modifiers_match(&self, actual: KeyModifiers) -> bool {
        // Disregard SHIFT if char is uppercase or special like '?'
        if let KeyCode::Char(c) = self.code {
            if c.is_ascii_uppercase() || !c.is_alphanumeric() {
                let norm_actual = actual & !KeyModifiers::SHIFT;
                let norm_expected = self.modifiers & !KeyModifiers::SHIFT;
                return norm_actual == norm_expected;
            }
        }
        self.modifiers == actual
    }
}

/// Shortcut key configurations serializable to `agi.toml`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShortcutConfig {
    pub quit: Vec<String>,
    pub help: Vec<String>,
    pub cycle_focus: Vec<String>,
    pub cycle_focus_reverse: Vec<String>,
    pub directive_modal: Vec<String>,
    pub directive_editor: Vec<String>,
    pub open_external_editor: Vec<String>,
    pub toggle_split: Vec<String>,
    pub new_worker: Vec<String>,
    pub switch_tab_next: Vec<String>,
    pub switch_tab_prev: Vec<String>,
    pub tab_keys: Vec<String>,
}

impl Default for ShortcutConfig {
    fn default() -> Self {
        Self {
            quit: vec!["q".to_string(), "Ctrl+Q".to_string()],
            help: vec!["?".to_string()],
            cycle_focus: vec!["Tab".to_string()],
            cycle_focus_reverse: vec!["Shift+Tab".to_string(), "BackTab".to_string()],
            directive_modal: vec!["m".to_string(), "Ctrl+M".to_string()],
            directive_editor: vec!["d".to_string(), "Ctrl+D".to_string()],
            open_external_editor: vec!["o".to_string(), "Ctrl+O".to_string()],
            toggle_split: vec!["s".to_string()],
            new_worker: vec!["n".to_string()],
            switch_tab_next: vec!["Tab".to_string(), "F6".to_string()],
            switch_tab_prev: vec!["Shift+Tab".to_string(), "BackTab".to_string(), "F5".to_string()],
            tab_keys: (1..=9).map(|i| i.to_string()).collect(),
        }
    }
}

/// General settings section in `agi.toml`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneralConfig {
    pub theme: String,
    pub tick_rate_ms: u64,
    pub default_session: Option<String>,
    pub default_model: String,
}

impl Default for GeneralConfig {
    fn default() -> Self {
        Self {
            theme: "tokyo_night".to_string(),
            tick_rate_ms: 50,
            default_session: None,
            default_model: "gemini-3.8-flash-high".to_string(),
        }
    }
}

/// Root AGI configuration mapping `~/.config/mind/agi.toml` and `~/.mind/config.toml`.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AgiConfig {
    pub general: GeneralConfig,
    pub shortcuts: ShortcutConfig,
}

/// Configurable keyboard shortcut resolution engine.
#[derive(Debug, Clone)]
pub struct ShortcutEngine {
    config: AgiConfig,
    bindings: Vec<(KeyBinding, Action)>,
    #[allow(dead_code)]
    tab_bindings: HashMap<KeyBinding, usize>,
}

impl Default for ShortcutEngine {
    fn default() -> Self {
        Self::load_or_default()
    }
}

impl ShortcutEngine {
    /// Initialize with custom configuration.
    pub fn new(config: AgiConfig) -> Self {
        let mut bindings = Vec::new();
        let mut tab_bindings = HashMap::new();

        macro_rules! register {
            ($field:expr, $action:expr) => {
                for key_str in &$field {
                    if let Some(kb) = KeyBinding::parse(key_str) {
                        bindings.push((kb, $action));
                    }
                }
            };
        }

        register!(config.shortcuts.quit, Action::Quit);
        register!(config.shortcuts.help, Action::Help);
        register!(config.shortcuts.cycle_focus, Action::CycleFocus);
        register!(config.shortcuts.cycle_focus_reverse, Action::CycleFocusReverse);
        register!(config.shortcuts.directive_modal, Action::DirectiveModal);
        register!(config.shortcuts.directive_editor, Action::DirectiveEditor);
        register!(config.shortcuts.open_external_editor, Action::OpenExternalEditor);
        register!(config.shortcuts.toggle_split, Action::ToggleSplit);
        register!(config.shortcuts.new_worker, Action::NewWorker);
        register!(config.shortcuts.switch_tab_next, Action::NextTab);
        register!(config.shortcuts.switch_tab_prev, Action::PrevTab);

        // Map tab keys (e.g. "1" -> SelectTab(0), "2" -> SelectTab(1))
        for (idx, key_str) in config.shortcuts.tab_keys.iter().enumerate() {
            if let Some(kb) = KeyBinding::parse(key_str) {
                tab_bindings.insert(kb.clone(), idx);
                bindings.push((kb, Action::SelectTab(idx)));
            }
        }

        Self {
            config,
            bindings,
            tab_bindings,
        }
    }

    /// Load from `~/.config/mind/agi.toml` or `~/.mind/config.toml`, falling back to built-in defaults.
    pub fn load_or_default() -> Self {
        let home = IdentityDiscovery::get_real_user_home();
        let candidates = [
            home.join(".config").join("mind").join("agi.toml"),
            home.join(".mind").join("config.toml"),
        ];

        for path in &candidates {
            if path.is_file() {
                if let Ok(content) = fs::read_to_string(path) {
                    if let Ok(config) = toml::from_str::<AgiConfig>(&content) {
                        debug!("Loaded AGI shortcuts from {}", path.display());
                        return Self::new(config);
                    }
                }
            }
        }

        // If not found, write documented default to ~/.config/mind/agi.toml
        let default_config = AgiConfig::default();
        let default_path = home.join(".config").join("mind").join("agi.toml");
        if let Some(parent) = default_path.parent() {
            let _ = fs::create_dir_all(parent);
            if let Ok(toml_str) = toml::to_string_pretty(&default_config) {
                let _ = fs::write(&default_path, toml_str);
            }
        }

        Self::new(default_config)
    }

    /// Load from a specific file path.
    pub fn load_from_file(path: &Path) -> Option<Self> {
        if path.is_file() {
            if let Ok(content) = fs::read_to_string(path) {
                if let Ok(config) = toml::from_str::<AgiConfig>(&content) {
                    return Some(Self::new(config));
                }
            }
        }
        None
    }

    /// Resolve an incoming Crossterm KeyEvent into a semantic Action.
    pub fn resolve(&self, event: &KeyEvent) -> Action {
        for (binding, action) in &self.bindings {
            if binding.matches(event) {
                return *action;
            }
        }
        Action::PassThrough
    }

    /// Access reference to the active configuration.
    pub fn config(&self) -> &AgiConfig {
        &self.config
    }
}
