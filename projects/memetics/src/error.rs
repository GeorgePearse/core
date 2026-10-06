#[derive(Debug, thiserror::Error)]
pub enum Error {
    /// A decision requiring configuration or human reconciliation, not a retry.
    #[error("{0}")]
    Blocked(String),
    #[error("{0}")]
    Invalid(String),
    #[error("GitHub HTTP {status}: {message}")]
    GitHub {
        status: u16,
        message: String,
        retry_after: i64,
    },
    #[error("{0}")]
    Other(String),
}

impl Error {
    pub fn retry_after(&self) -> Option<i64> {
        match self {
            Error::GitHub { retry_after, .. } => Some(*retry_after),
            _ => None,
        }
    }
}

pub fn blocked(message: impl Into<String>) -> Error {
    Error::Blocked(message.into())
}

pub fn invalid(message: impl Into<String>) -> Error {
    Error::Invalid(message.into())
}

pub fn other(message: impl Into<String>) -> Error {
    Error::Other(message.into())
}

macro_rules! convert {
    ($($t:ty),*) => {$(
        impl From<$t> for Error {
            fn from(e: $t) -> Self {
                Error::Other(e.to_string())
            }
        }
    )*};
}
convert!(
    rusqlite::Error,
    std::io::Error,
    serde_json::Error,
    reqwest::Error
);

pub type Result<T> = std::result::Result<T, Error>;
