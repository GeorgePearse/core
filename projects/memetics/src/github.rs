//! Small GitHub API boundary; credentials never enter model or test subprocesses.

use crate::error::{Error, Result, other};
use crate::git::{clean_env, run_with_timeout};
use base64::Engine as _;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use reqwest::Method;
use reqwest::blocking::Client;
use reqwest::header::HeaderMap;
use serde_json::{Value, json};
use std::process::Command;
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub trait GitHubApi: Send + Sync {
    fn token(&self) -> Result<String>;
    /// Returns `(sha, etag)`; `sha` is `None` when the conditional request was not modified.
    fn head(
        &self,
        repo: &str,
        reference: &str,
        etag: Option<&str>,
    ) -> Result<(Option<String>, Option<String>)>;
    fn metadata(&self, repo: &str) -> Result<Value>;
    fn remote(&self, repo: &str) -> String;
    fn pull(&self, repo: &str, number: i64) -> Result<Value>;
    fn find_pull(&self, repo: &str, branch: &str) -> Result<Option<Value>>;
    fn create_pull(
        &self,
        repo: &str,
        branch: &str,
        base: &str,
        title: &str,
        body: &str,
    ) -> Result<Value>;
    fn update_pull(&self, repo: &str, number: i64, body: &str) -> Result<Value>;
}

pub struct AppConfig {
    pub app_id: String,
    pub key_file: String,
    pub installation_id: String,
}

type Signer = Box<dyn Fn(&[u8], &str) -> Result<Vec<u8>> + Send + Sync>;

pub struct GitHub {
    pub api_base: String,
    pub app: Option<AppConfig>,
    pub signer: Signer,
    token: Mutex<Option<String>>,
    app_token: Mutex<Option<(String, f64)>>,
    client: Client,
}

fn unix_now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

/// Percent-encode like Python's `urllib.parse.quote(value, safe='')`.
pub fn quote(value: &str) -> String {
    value
        .bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'_' | b'.' | b'-' | b'~' => {
                (b as char).to_string()
            }
            _ => format!("%{b:02X}"),
        })
        .collect()
}

pub fn retry_delay(headers: &HeaderMap, now: i64) -> i64 {
    let header = |name: &str| headers.get(name).and_then(|v| v.to_str().ok());
    let mut delay = header("retry-after")
        .and_then(|v| v.parse().ok())
        .unwrap_or(60);
    if header("x-ratelimit-remaining") == Some("0") {
        let reset: i64 = header("x-ratelimit-reset")
            .and_then(|v| v.parse().ok())
            .unwrap_or(0);
        delay = delay.max(reset - now + 1);
    }
    delay
}

fn openssl_sign(message: &[u8], key_file: &str) -> Result<Vec<u8>> {
    let mut command = Command::new("openssl");
    command
        .args(["dgst", "-sha256", "-sign", key_file])
        .env_clear()
        .envs(clean_env());
    let out = run_with_timeout(&mut command, Duration::from_secs(15), Some(message))?;
    if out.code != Some(0) {
        return Err(other("openssl signing of the GitHub App JWT failed"));
    }
    Ok(out.stdout)
}

impl GitHub {
    pub fn new(token: Option<String>) -> Self {
        let client = Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(30))
            .build()
            .expect("HTTP client builds");
        GitHub {
            api_base: "https://api.github.com".into(),
            app: None,
            signer: Box::new(openssl_sign),
            token: Mutex::new(token),
            app_token: Mutex::new(None),
            client,
        }
    }

    pub fn from_env() -> Self {
        let mut github = GitHub::new(None);
        if let Ok(app_id) = std::env::var("MEMETICS_GITHUB_APP_ID")
            && !app_id.is_empty()
        {
            github.app = Some(AppConfig {
                app_id,
                key_file: std::env::var("MEMETICS_GITHUB_APP_KEY_FILE").unwrap_or_default(),
                installation_id: std::env::var("MEMETICS_GITHUB_INSTALLATION_ID")
                    .unwrap_or_default(),
            });
        }
        github
    }

    pub fn installation_token(&self, app: &AppConfig) -> Result<String> {
        if !app.installation_id.chars().all(|c| c.is_ascii_digit())
            || app.installation_id.is_empty()
        {
            return Err(Error::Invalid(
                "GitHub installation ID must be numeric".into(),
            ));
        }
        if app.key_file.is_empty() {
            return Err(other("MEMETICS_GITHUB_APP_KEY_FILE is required"));
        }
        let now = unix_now() as i64;
        let header = URL_SAFE_NO_PAD.encode(json!({"alg": "RS256", "typ": "JWT"}).to_string());
        let payload = URL_SAFE_NO_PAD
            .encode(json!({"iat": now - 60, "exp": now + 540, "iss": app.app_id}).to_string());
        let message = format!("{header}.{payload}");
        let signature = (self.signer)(message.as_bytes(), &app.key_file)?;
        let jwt = format!("{message}.{}", URL_SAFE_NO_PAD.encode(signature));
        let response = self
            .client
            .post(format!(
                "{}/app/installations/{}/access_tokens",
                self.api_base, app.installation_id
            ))
            .header("Authorization", format!("Bearer {jwt}"))
            .header("Accept", "application/vnd.github+json")
            .header("User-Agent", "memetics/0.1")
            .body("{}")
            .send()?;
        let status = response.status();
        if !status.is_success() {
            return Err(other(format!(
                "GitHub App token request failed: HTTP {}",
                status.as_u16()
            )));
        }
        let data: Value = response.json()?;
        data["token"]
            .as_str()
            .map(String::from)
            .ok_or_else(|| other("GitHub App token missing"))
    }

    pub fn request(
        &self,
        method: Method,
        path: &str,
        data: Option<&Value>,
        etag: Option<&str>,
    ) -> Result<(Option<Value>, Option<String>)> {
        let mut request = self
            .client
            .request(method, format!("{}{}", self.api_base, path))
            .header("Authorization", format!("Bearer {}", self.token()?))
            .header("Accept", "application/vnd.github+json")
            .header("X-GitHub-Api-Version", "2022-11-28")
            .header("User-Agent", "memetics/0.1");
        if let Some(tag) = etag {
            request = request.header("If-None-Match", tag);
        }
        if let Some(body) = data {
            request = request
                .header("Content-Type", "application/json")
                .body(body.to_string());
        }
        let response = request.send()?;
        let status = response.status();
        if status.as_u16() == 304 {
            return Ok((None, etag.map(String::from)));
        }
        let headers = response.headers().clone();
        let body = response.bytes()?;
        if !status.is_success() {
            // GitHub error responses contain no credentials, but do not echo request headers.
            let message: String = String::from_utf8_lossy(&body).chars().take(1000).collect();
            return Err(Error::GitHub {
                status: status.as_u16(),
                message,
                retry_after: retry_delay(&headers, unix_now() as i64),
            });
        }
        let tag = headers
            .get("etag")
            .and_then(|v| v.to_str().ok())
            .map(String::from);
        let value = if body.is_empty() {
            None
        } else {
            Some(serde_json::from_slice(&body)?)
        };
        Ok((value, tag))
    }

    fn get(&self, path: &str) -> Result<Value> {
        Ok(self
            .request(Method::GET, path, None, None)?
            .0
            .unwrap_or(Value::Null))
    }
}

impl GitHubApi for GitHub {
    fn token(&self) -> Result<String> {
        if let Some(app) = &self.app {
            let mut cached = self.app_token.lock().unwrap();
            match cached.as_ref() {
                Some((token, expires)) if unix_now() < *expires => return Ok(token.clone()),
                _ => {
                    let token = self.installation_token(app)?;
                    *cached = Some((token.clone(), unix_now() + 3000.0));
                    return Ok(token);
                }
            }
        }
        let mut token = self.token.lock().unwrap();
        if token.is_none() {
            let from_env = ["MEMETICS_GITHUB_TOKEN", "GH_TOKEN"]
                .iter()
                .filter_map(|k| std::env::var(k).ok())
                .find(|v| !v.is_empty());
            *token = Some(match from_env {
                Some(value) => value,
                None => {
                    let mut command = Command::new("gh");
                    command.args(["auth", "token"]);
                    let out = run_with_timeout(&mut command, Duration::from_secs(15), None)
                        .map_err(|_| other("Set MEMETICS_GITHUB_TOKEN or authenticate gh"))?;
                    if out.code != Some(0) {
                        return Err(other("Set MEMETICS_GITHUB_TOKEN or authenticate gh"));
                    }
                    String::from_utf8_lossy(&out.stdout).trim().to_string()
                }
            });
        }
        Ok(token.clone().unwrap())
    }

    fn head(
        &self,
        repo: &str,
        reference: &str,
        etag: Option<&str>,
    ) -> Result<(Option<String>, Option<String>)> {
        let (data, tag) = self.request(
            Method::GET,
            &format!("/repos/{repo}/commits/{}", quote(reference)),
            None,
            etag,
        )?;
        Ok((data.and_then(|d| d["sha"].as_str().map(String::from)), tag))
    }

    fn metadata(&self, repo: &str) -> Result<Value> {
        self.get(&format!("/repos/{repo}"))
    }

    fn remote(&self, repo: &str) -> String {
        format!("https://github.com/{repo}.git")
    }

    fn pull(&self, repo: &str, number: i64) -> Result<Value> {
        self.get(&format!("/repos/{repo}/pulls/{number}"))
    }

    fn find_pull(&self, repo: &str, branch: &str) -> Result<Option<Value>> {
        let owner = repo.split('/').next().unwrap_or_default();
        let head = quote(&format!("{owner}:{branch}"));
        let values = self.get(&format!(
            "/repos/{repo}/pulls?state=all&head={head}&per_page=100"
        ))?;
        Ok(values.as_array().and_then(|v| v.first().cloned()))
    }

    fn create_pull(
        &self,
        repo: &str,
        branch: &str,
        base: &str,
        title: &str,
        body: &str,
    ) -> Result<Value> {
        let data =
            json!({"head": branch, "base": base, "title": title, "body": body, "draft": true});
        Ok(self
            .request(
                Method::POST,
                &format!("/repos/{repo}/pulls"),
                Some(&data),
                None,
            )?
            .0
            .unwrap_or(Value::Null))
    }

    fn update_pull(&self, repo: &str, number: i64, body: &str) -> Result<Value> {
        let data = json!({"body": body});
        Ok(self
            .request(
                Method::PATCH,
                &format!("/repos/{repo}/pulls/{number}"),
                Some(&data),
                None,
            )?
            .0
            .unwrap_or(Value::Null))
    }
}
