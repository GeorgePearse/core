use axum::Router;
use axum::http::StatusCode;
use axum::routing::post;
use base64::Engine as _;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use memetics::error::Error;
use memetics::github::{AppConfig, GitHub, GitHubApi, retry_delay};
use memetics::model::{Adapter, Model, Tools};
use serde_json::{Value, json};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};

/// Serve `router` on a background runtime and return its base URL.
fn spawn(router: Router) -> String {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    listener.set_nonblocking(true).unwrap();
    std::thread::spawn(move || {
        let runtime = tokio::runtime::Runtime::new().unwrap();
        runtime.block_on(async move {
            let listener = tokio::net::TcpListener::from_std(listener).unwrap();
            axum::serve(listener, router).await.unwrap();
        });
    });
    url
}

#[test]
fn app_jwt_and_cached_installation_token() {
    let seen = Arc::new(Mutex::new(Vec::<String>::new()));
    let record = seen.clone();
    let url = spawn(Router::new().route(
        "/app/installations/456/access_tokens",
        post(move |headers: axum::http::HeaderMap| {
            let record = record.clone();
            async move {
                record
                    .lock()
                    .unwrap()
                    .push(headers["authorization"].to_str().unwrap().to_string());
                axum::Json(json!({"token": "installation-secret"}))
            }
        }),
    ));
    let signs = Arc::new(AtomicUsize::new(0));
    let counter = signs.clone();
    let mut client = GitHub::new(None);
    client.api_base = url;
    client.app = Some(AppConfig {
        app_id: "123".into(),
        key_file: "/private/key.pem".into(),
        installation_id: "456".into(),
    });
    client.signer = Box::new(move |_, _| {
        counter.fetch_add(1, Ordering::SeqCst);
        Ok(b"signature".to_vec())
    });
    assert_eq!(client.token().unwrap(), "installation-secret");
    assert_eq!(client.token().unwrap(), "installation-secret");
    assert_eq!(signs.load(Ordering::SeqCst), 1);
    let auth = seen.lock().unwrap()[0].clone();
    let jwt = auth.split_whitespace().nth(1).unwrap();
    let payload: Value = serde_json::from_slice(
        &URL_SAFE_NO_PAD
            .decode(jwt.split('.').nth(1).unwrap())
            .unwrap(),
    )
    .unwrap();
    assert_eq!(payload["iss"], "123");
    assert!(payload["exp"].as_i64().unwrap() - payload["iat"].as_i64().unwrap() <= 600);
    assert!(!jwt.contains("installation-secret"));
}

#[test]
fn rate_limit_reset_controls_retry() {
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert("x-ratelimit-remaining", "0".parse().unwrap());
    headers.insert("x-ratelimit-reset", "1500".parse().unwrap());
    assert_eq!(retry_delay(&headers, 1000), 501);
    let reset = (std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs()
        + 500)
        .to_string();
    let url = spawn(Router::new().fallback(move || {
        let reset = reset.clone();
        async move {
            (
                StatusCode::FORBIDDEN,
                [
                    ("x-ratelimit-remaining", "0".to_string()),
                    ("x-ratelimit-reset", reset),
                ],
                "limited",
            )
        }
    }));
    let mut client = GitHub::new(Some("test-token".into()));
    client.api_base = url;
    match client.head("owner/repo", "main", None) {
        Err(Error::GitHub {
            status: 403,
            retry_after,
            ..
        }) => assert!((500..=502).contains(&retry_after), "{retry_after}"),
        other => panic!("expected a rate-limit error, got {other:?}"),
    }
}

struct NoTools;

impl Tools for NoTools {
    fn charge(&mut self) -> memetics::error::Result<()> {
        Ok(())
    }
    fn read_upstream(&mut self, _: &str) -> memetics::error::Result<String> {
        unreachable!()
    }
    fn read_destination(&mut self, _: &str) -> memetics::error::Result<String> {
        unreachable!()
    }
    fn search_destination(&mut self, _: &str) -> memetics::error::Result<String> {
        unreachable!()
    }
    fn validate(&mut self, _: &Value) -> memetics::error::Result<Value> {
        unreachable!()
    }
}

#[test]
fn model_rejects_incomplete_output() {
    let payload = Arc::new(Mutex::new(Value::Null));
    let record = payload.clone();
    let url = spawn(Router::new().route(
        "/chat/completions",
        post(move |axum::Json(body): axum::Json<Value>| {
            let record = record.clone();
            async move {
                *record.lock().unwrap() = body;
                axum::Json(json!({"choices": [{"finish_reason": "length"}]}))
            }
        }),
    ));
    let model = Model::new(&url, "test", "sentinel-model-key-12345");
    let error = model
        .adapt(&json!({"listener": "fixture"}), &mut NoTools)
        .unwrap_err();
    assert!(
        matches!(&error, Error::Blocked(m) if m.contains("did not complete")),
        "{error}"
    );
    let sent = payload.lock().unwrap().to_string();
    assert!(!sent.contains("sentinel-model-key-12345"));
    assert!(payload.lock().unwrap().get("tools").is_none());
}
