use hmac::{Hmac, Mac};
use memetics::db::{Store, int};
use memetics::server::make_server;
use serde_json::{Value, json};
use sha2::Sha256;

async fn start(store: &Store) -> String {
    let (listener, app) = make_server(store.clone(), "127.0.0.1", 0, "test-token", "secret")
        .await
        .unwrap();
    let url = format!("http://127.0.0.1:{}", listener.local_addr().unwrap().port());
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    url
}

#[tokio::test]
async fn dashboard_and_api_auth() {
    let tmp = tempfile::tempdir().unwrap();
    let store = Store::open(tmp.path()).unwrap();
    let url = start(&store).await;
    let client = reqwest::Client::new();
    let page = client.get(&url).send().await.unwrap();
    assert_eq!(page.status(), 200);
    assert!(page.text().await.unwrap().contains("Memetics"));
    assert_eq!(
        client
            .get(format!("{url}/api/status"))
            .send()
            .await
            .unwrap()
            .status(),
        401
    );
    let status = client
        .get(format!("{url}/api/status"))
        .bearer_auth("test-token")
        .send()
        .await
        .unwrap();
    assert_eq!(status.status(), 200);
    assert_eq!(
        status.json::<Value>().await.unwrap()["listeners"],
        json!([])
    );
    let write = client
        .post(format!("{url}/api/listeners/x/pause"))
        .body("{}")
        .send()
        .await
        .unwrap();
    assert_eq!(write.status(), 401);
    let unknown = client
        .post(format!("{url}/api/listeners/x/pause"))
        .bearer_auth("test-token")
        .body("{}")
        .send()
        .await
        .unwrap();
    assert_eq!(unknown.status(), 400);
}

#[tokio::test]
async fn webhook_signature_dedup_and_wakeup() {
    let tmp = tempfile::tempdir().unwrap();
    let store = Store::open(tmp.path()).unwrap();
    store
        .execute(
            "INSERT INTO sources(id,repo,ref,next_poll) VALUES(?,?,?,?)",
            rusqlite::params!["source", "Owner/Repo", "main", 9999999999.0],
        )
        .unwrap();
    let url = format!("{}/webhooks/github", start(&store).await);
    let body =
        json!({"repository": {"full_name": "owner/repo"}, "ref": "refs/heads/main"}).to_string();
    let mut mac = Hmac::<Sha256>::new_from_slice(b"secret").unwrap();
    mac.update(body.as_bytes());
    let signature = format!("sha256={}", hex::encode(mac.finalize().into_bytes()));
    let client = reqwest::Client::new();
    let signed = || {
        client
            .post(&url)
            .header("X-GitHub-Delivery", "one")
            .header("X-GitHub-Event", "push")
            .header("X-Hub-Signature-256", &signature)
            .body(body.clone())
    };
    assert_eq!(
        client
            .post(&url)
            .body(body.clone())
            .send()
            .await
            .unwrap()
            .status(),
        401
    );
    let first = signed().send().await.unwrap();
    assert_eq!(first.status(), 202);
    assert_eq!(first.json::<Value>().await.unwrap()["duplicate"], false);
    let source = store
        .one("SELECT next_poll FROM sources", [])
        .unwrap()
        .unwrap();
    assert_eq!(source["next_poll"].as_f64(), Some(0.0));
    let second = signed().send().await.unwrap();
    assert_eq!(second.json::<Value>().await.unwrap()["duplicate"], true);
    assert_eq!(
        int(
            &store
                .one("SELECT count(*) n FROM events", [])
                .unwrap()
                .unwrap(),
            "n"
        ),
        1
    );
}

#[tokio::test]
async fn remote_bind_requires_token() {
    let tmp = tempfile::tempdir().unwrap();
    let store = Store::open(tmp.path()).unwrap();
    assert!(make_server(store, "0.0.0.0", 0, "", "").await.is_err());
}
