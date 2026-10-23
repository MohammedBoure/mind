use std::time::Duration;
use crossterm::event::{Event as CrosstermEvent, EventStream};
use futures::StreamExt;
use tokio::sync::mpsc;
use tokio::time::{interval, Interval};
use tracing::warn;

use crate::events::types::AppEvent;

/// Central asynchronous event loop multiplexing terminal Crossterm inputs,
/// PTY stream notifications, MCP requests, and tick timers.
pub struct EventLoop {
    event_stream: EventStream,
    tx: mpsc::Sender<AppEvent>,
    rx: mpsc::Receiver<AppEvent>,
    tick_interval: Interval,
}

impl EventLoop {
    /// Create a new event loop with a default tick rate (e.g. 50ms).
    pub fn new(tick_ms: u64) -> Self {
        let (tx, rx) = mpsc::channel(256);
        let mut tick_interval = interval(Duration::from_millis(tick_ms.max(10)));
        tick_interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

        Self {
            event_stream: EventStream::new(),
            tx,
            rx,
            tick_interval,
        }
    }

    /// Obtain a cloneable sender to inject external events (PTY chunks, MCP calls, alarms)
    /// into this event loop.
    pub fn sender(&self) -> mpsc::Sender<AppEvent> {
        self.tx.clone()
    }

    /// Await and retrieve the next event in the stream.
    pub async fn next(&mut self) -> Option<AppEvent> {
        tokio::select! {
            // Crossterm terminal input event
            maybe_term_event = self.event_stream.next() => {
                match maybe_term_event {
                    Some(Ok(CrosstermEvent::Key(key))) => Some(AppEvent::Key(key)),
                    Some(Ok(CrosstermEvent::Mouse(mouse))) => Some(AppEvent::Mouse(mouse)),
                    Some(Ok(CrosstermEvent::Resize(cols, rows))) => Some(AppEvent::Resize(rows, cols)),
                    Some(Ok(_)) => None,
                    Some(Err(e)) => {
                        warn!("Crossterm event error: {}", e);
                        None
                    }
                    None => None,
                }
            }

            // Internal injected event (PTY output, IPC, alarm, quit)
            maybe_internal = self.rx.recv() => {
                maybe_internal
            }

            // Periodic tick timer
            _ = self.tick_interval.tick() => {
                Some(AppEvent::Tick)
            }
        }
    }
}
