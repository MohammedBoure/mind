//! Visual widget components for the compiled TUI core architecture.
//!
//! Provides Tokyo-Night themed Ratatui widgets:
//! - [`SplitPanesWidget`]: Flexible split layout widget (horizontal, vertical, grid, single).
//! - [`StatusBarWidget`]: High-density status bar with model, PID, token status, and alert badges.
//! - [`QuotaGaugesWidget`]: Real-time progress gauges for hourly/weekly quotas, CPU, and RAM.
//! - [`WorkerListWidget`]: Navigable worker session list with status icons and indicators.
//! - [`TerminalScreenWidget`]: Zero-overhead character matrix renderer with dirty-frame checking.
//! - [`Theme`]: Tokyo Night color palette and standard typography styles.

pub mod directive_editor;
pub mod directive_modal;
pub mod gauges;
pub mod help_modal;
pub mod new_worker_modal;
pub mod session_picker;
pub mod split_panes;
pub mod status_bar;
pub mod terminal_screen;
pub mod theme;
pub mod worker_list;

pub use directive_editor::{DirectiveEditorAction, DirectiveEditorModal};
pub use directive_modal::{DirectiveModal, DirectiveModalAction, DirectivePriority};
pub use gauges::{GaugeLayout, QuotaGaugesWidget};
pub use help_modal::{HelpModal, ShortcutEntry};
pub use new_worker_modal::{NewWorkerModal, NewWorkerModalAction};
pub use session_picker::{SessionPickerAction, SessionPickerScreen};
pub use split_panes::{SplitMode, SplitPanesWidget};
pub use status_bar::{AlertBadge, StatusBarWidget};
pub use terminal_screen::{
    cell_bg_to_ratatui, cell_color_to_ratatui, TerminalScreenWidget, TerminalSource,
};
pub use theme::{colors, glyphs, Theme, ThemeMode, ThemePalette};
pub use worker_list::{WorkerListItem, WorkerListWidget};
