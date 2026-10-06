//! Error types for tsrs

use thiserror::Error;

/// Result type for tsrs operations
pub type Result<T> = std::result::Result<T, TsrsError>;

/// Errors that can occur during tree-shaking operations
#[derive(Error, Debug)]
pub enum TsrsError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Invalid venv path: {0}")]
    InvalidVenvPath(String),

    #[error("Failed to parse Python file: {0}")]
    ParseError(String),

    #[error("Failed to analyze venv: {0}")]
    AnalysisError(String),

    #[error("JSON error: {0}")]
    JsonError(#[from] serde_json::Error),

    #[error("Invalid metadata: {0}")]
    InvalidMetadata(String),
}
