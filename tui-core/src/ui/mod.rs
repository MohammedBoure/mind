//! Visual widget components for the compiled TUI core architecture.
//!
//! Provides Tokyo-Night themed Ratatui widgets:
//! - [`SplitPanesWidget`]: Flexible split layout widget (horizontal, vertical, grid, single).
//! - [`StatusBarWidget`]: High-density status bar with model, PID, token status, and alert badges.
//! - [`QuotaGaugesWidget`]: Real-time progress gauges for hourly/weekly quotas, CPU, and RAM.
//! - [`WorkerListWidget`]: Navigable worker session list with status icons and indicators.
//! - [`TerminalScreenWidget`]: Zero-overhead character matrix renderer with dirty-frame checking.
//! - [`Theme`]: Tokyo Night color palette and standard typography styles.

pub mod gauges;
pub mod split_panes;
pub mod status_bar;
pub mod terminal_screen;
pub mod theme;
pub mod worker_list;

pub use gauges::{GaugeLayout, QuotaGaugesWidget};
pub use split_panes::{SplitMode, SplitPanesWidget};
pub use status_bar::{AlertBadge, StatusBarWidget};
pub use terminal_screen::{
    cell_bg_to_ratatui, cell_color_to_ratatui, TerminalScreenWidget, TerminalSource,
};
pub use theme::{colors, glyphs, Theme};
pub use worker_list::{WorkerListItem, WorkerListWidget};
