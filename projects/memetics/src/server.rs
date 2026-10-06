//! Local dashboard, authenticated registration API, and signed GitHub wakeups.

use crate::db::{Store, now};
use crate::engine::Engine;
use crate::error::{Error, Result, invalid};
use axum::Router;
use axum::body::{Body, to_bytes};
use axum::extract::{Request, State};
use axum::http::{HeaderMap, Method, header};
use axum::response::Response;
use hmac::{Hmac, Mac};
use rusqlite::params;
use serde_json::{Value, json};
use sha2::Sha256;
use std::sync::Arc;
use std::sync::mpsc;
use std::time::Duration;
use tokio::net::TcpListener;

pub const PAGE: &str = r#"<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Memetics listeners</title><style>body{font:16px system-ui;max-width:1150px;margin:3rem auto;padding:0 1rem;background:#10151d;color:#dde7f1}h1{color:#9ff0cc}input,button{font:inherit;padding:.5rem;background:#202b39;color:inherit;border:1px solid #425268;border-radius:5px}section{overflow-x:auto}table{border-collapse:collapse;width:100%;margin-bottom:2rem}th,td{text-align:left;padding:.65rem;border-bottom:1px solid #314051;overflow-wrap:anywhere}a{color:#9ff0cc}small{color:#aebdcd}#error{color:#ffb8b8}pre{white-space:pre-wrap}details{margin:1rem 0}</style>
<h1>Memetics</h1><p>Standing upstream interests. Shared updates. Implementation pull requests.</p>
<label>API token <input id="token" type="password" autocomplete="off" placeholder="Only needed if configured"></label> <button id="refresh">Refresh</button>
<p id="error" role="alert"></p><small id="updated"></small><main id="status"></main>
<script>
const token=document.querySelector('#token'); token.value=sessionStorage.getItem('memetics-token')||'';
function table(title,rows,keys){const section=document.createElement('section');const h=document.createElement('h2');h.textContent=title;section.append(h);if(!rows.length){const p=document.createElement('p');p.textContent='None yet';section.append(p);return section;}const t=document.createElement('table');const header=t.insertRow();keys.forEach(k=>{const th=document.createElement('th');th.textContent=k;header.append(th)});rows.forEach(row=>{const tr=t.insertRow();keys.forEach(k=>{const td=tr.insertCell();td.textContent=row[k]??'—';if(k==='url'&&String(row[k]).startsWith('https://github.com/')){const a=document.createElement('a');a.href=row[k];a.textContent='Open PR';td.replaceChildren(a)}})});section.append(t);return section;}
async function refresh(){try{sessionStorage.setItem('memetics-token',token.value);const r=await fetch('/api/status',{headers:token.value?{Authorization:'Bearer '+token.value}:{}});if(!r.ok)throw Error('Status request failed: '+r.status);const s=await r.json();document.querySelector('#status').replaceChildren(table('Listeners',s.listeners,['id','enabled','observed','adopted']),table('Shared upstream watches',s.sources,['repo','ref','polls','error']),table('Jobs',s.jobs,['id','listener_id','status','attempts','reason']),table('Pull requests',s.proposals,['listener_id','state','url']));document.querySelector('#updated').textContent='Updated '+new Date().toLocaleTimeString()+' · '+s.cache.changes+' cached changes · '+s.cache.blobs+' indexed blobs';document.querySelector('#error').textContent='';}catch(e){document.querySelector('#error').textContent=e.message}}
document.querySelector('#refresh').onclick=refresh;refresh();setInterval(refresh,10000);
</script></html>"#;

struct App {
    store: Store,
    api_token: String,
    webhook_secret: String,
}

fn same(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

fn send(status: u16, body: impl Into<Body>, content_type: &str) -> Response {
    Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, content_type)
        .header(header::CACHE_CONTROL, "no-store")
        .header("X-Content-Type-Options", "nosniff")
        .body(body.into())
        .unwrap()
}

fn json_response(status: u16, data: Value) -> Response {
    send(status, data.to_string(), "application/json")
}

impl App {
    fn authorized(&self, headers: &HeaderMap, write: bool) -> bool {
        if self.api_token.is_empty() {
            return !write;
        }
        let given = headers
            .get(header::AUTHORIZATION)
            .map(|v| v.as_bytes())
            .unwrap_or_default();
        same(given, format!("Bearer {}", self.api_token).as_bytes())
    }

    fn get(&self, path: &str, headers: &HeaderMap) -> Result<Response> {
        match path {
            "/" => return Ok(send(200, PAGE, "text/html; charset=utf-8")),
            "/health" => return Ok(json_response(200, json!({"status": "ok"}))),
            _ => {}
        }
        if !self.authorized(headers, false) {
            return Ok(json_response(401, json!({"error": "API token required"})));
        }
        if path == "/api/status" {
            return Ok(json_response(200, self.store.status()?));
        }
        if let Some(id) = path
            .strip_prefix("/api/jobs/")
            .filter(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()))
        {
            let job = self.store.one(
                "SELECT * FROM jobs WHERE id=?",
                [id.parse::<i64>().unwrap_or(-1)],
            )?;
            return Ok(match job {
                Some(job) => json_response(200, Value::Object(job)),
                None => json_response(404, json!({"error": "unknown job"})),
            });
        }
        Ok(json_response(404, json!({"error": "not found"})))
    }

    fn post(&self, path: &str, headers: &HeaderMap, raw: &[u8]) -> Result<Response> {
        let webhook = path == "/webhooks/github";
        if webhook {
            let mut mac = Hmac::<Sha256>::new_from_slice(self.webhook_secret.as_bytes())
                .expect("any key length");
            mac.update(raw);
            let expected = format!("sha256={}", hex::encode(mac.finalize().into_bytes()));
            let given = headers
                .get("X-Hub-Signature-256")
                .map(|v| v.as_bytes())
                .unwrap_or_default();
            if self.webhook_secret.is_empty() || !same(expected.as_bytes(), given) {
                return Ok(json_response(
                    401,
                    json!({"error": "invalid webhook signature"}),
                ));
            }
        }
        let data: Value = serde_json::from_slice(raw).map_err(|e| invalid(e.to_string()))?;
        if webhook {
            let event_id = headers
                .get("X-GitHub-Delivery")
                .and_then(|v| v.to_str().ok())
                .unwrap_or_default();
            if event_id.is_empty() || event_id.len() > 200 {
                return Err(invalid("missing or invalid delivery id"));
            }
            let mut conn = self.store.connect()?;
            let tx = conn.transaction()?;
            let inserted = tx.execute(
                "INSERT OR IGNORE INTO events VALUES(?,?)",
                params![event_id, now()],
            )?;
            let push = headers.get("X-GitHub-Event").is_some_and(|v| v == "push");
            if inserted > 0 && push {
                let reference = data["ref"].as_str().unwrap_or_default();
                let reference = reference.strip_prefix("refs/heads/").unwrap_or(reference);
                let repo = data["repository"]["full_name"].as_str().unwrap_or_default();
                tx.execute(
                    "UPDATE sources SET next_poll=0 WHERE lower(repo)=lower(?) AND ref=?",
                    params![repo, reference],
                )?;
            }
            tx.commit()?;
            return Ok(json_response(
                202,
                json!({"accepted": true, "duplicate": inserted == 0}),
            ));
        }
        if path == "/api/listeners" {
            let listeners = data["listeners"].as_array().filter(|l| !l.is_empty());
            let (Some(1), Some(listeners)) = (data["version"].as_i64(), listeners) else {
                return Err(invalid(
                    "version 1 manifest with nonempty listeners required",
                ));
            };
            return Ok(json_response(
                201,
                json!({"listeners": self.store.register(listeners)?}),
            ));
        }
        let parts: Vec<&str> = path.split('/').collect();
        if let [
            "",
            "api",
            "listeners",
            listener,
            action @ ("pause" | "resume"),
        ] = parts.as_slice()
        {
            let enabled = *action == "resume";
            self.store.enable(listener, enabled)?;
            return Ok(json_response(
                200,
                json!({"listener": listener, "enabled": enabled}),
            ));
        }
        if path.starts_with("/api/listeners/")
            && (path.ends_with("/pause") || path.ends_with("/resume"))
        {
            return Err(invalid("invalid listener path"));
        }
        Ok(json_response(404, json!({"error": "not found"})))
    }
}

async fn handle(State(app): State<Arc<App>>, request: Request) -> Response {
    let path = request.uri().path().to_string();
    let method = request.method().clone();
    let headers = request.headers().clone();
    let result = if method == Method::GET {
        app.get(&path, &headers)
    } else if method == Method::POST {
        let length: usize = headers
            .get(header::CONTENT_LENGTH)
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.parse().ok())
            .unwrap_or(0);
        if !(1..=1_000_000).contains(&length) {
            return json_response(413, json!({"error": "body must contain 1-1000000 bytes"}));
        }
        if path != "/webhooks/github" && !app.authorized(&headers, true) {
            return json_response(
                401,
                json!({"error": "write API requires MEMETICS_API_TOKEN"}),
            );
        }
        match to_bytes(request.into_body(), 1_000_000).await {
            Ok(raw) => app.post(&path, &headers, &raw),
            Err(_) => {
                return json_response(413, json!({"error": "body must contain 1-1000000 bytes"}));
            }
        }
    } else {
        return json_response(501, json!({"error": "unsupported method"}));
    };
    match result {
        Ok(response) => response,
        Err(Error::Invalid(message)) => json_response(400, json!({"error": message})),
        Err(e) => json_response(500, json!({"error": e.to_string()})),
    }
}

pub fn router(store: Store, api_token: &str, webhook_secret: &str) -> Router {
    let app = Arc::new(App {
        store,
        api_token: api_token.into(),
        webhook_secret: webhook_secret.into(),
    });
    Router::new().fallback(handle).with_state(app)
}

pub async fn make_server(
    store: Store,
    host: &str,
    port: u16,
    api_token: &str,
    webhook_secret: &str,
) -> Result<(TcpListener, Router)> {
    if !["127.0.0.1", "localhost", "::1"].contains(&host) && api_token.is_empty() {
        return Err(invalid(
            "MEMETICS_API_TOKEN is required when listening beyond localhost",
        ));
    }
    let listener = TcpListener::bind((host, port)).await?;
    Ok((listener, router(store, api_token, webhook_secret)))
}

pub fn serve(store: Store, engine: Engine, host: &str, port: u16, interval: u64) -> Result<()> {
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()?;
    let api_token = std::env::var("MEMETICS_API_TOKEN").unwrap_or_default();
    let secret = std::env::var("MEMETICS_WEBHOOK_SECRET").unwrap_or_default();
    let (listener, app) = runtime.block_on(make_server(store, host, port, &api_token, &secret))?;
    let (stop, stopped) = mpsc::channel::<()>();
    let worker = std::thread::spawn(move || {
        loop {
            if let Err(e) = engine.tick(1, false) {
                println!("{}", json!({"worker_error": e.to_string()}));
                tracing::warn!(error = %e, "worker tick failed");
            }
            if stopped.recv_timeout(Duration::from_secs(interval))
                != Err(mpsc::RecvTimeoutError::Timeout)
            {
                return;
            }
        }
    });
    println!(
        "Memetics dashboard: http://{host}:{}",
        listener.local_addr()?.port()
    );
    let served = runtime.block_on(async {
        axum::serve(listener, app)
            .with_graceful_shutdown(async {
                let _ = tokio::signal::ctrl_c().await;
            })
            .await
    });
    let _ = stop.send(());
    let _ = worker.join();
    served.map_err(Error::from)
}
