//! Modal for provisioning new worker agent slots.
//!
//! Re-exports [`SelectWorkerModal`] and [`SelectWorkerModalAction`] for seamless
//! slot selection and agent spawning matching Python `mind`.

pub use crate::ui::select_worker_modal::{
    SelectWorkerModal, SelectWorkerModalAction,
};

/// Type alias for [`SelectWorkerModal`] providing backward compatibility.
pub type NewWorkerModal = SelectWorkerModal;

/// Type alias for [`SelectWorkerModalAction`] providing backward compatibility.
pub type NewWorkerModalAction = SelectWorkerModalAction;
