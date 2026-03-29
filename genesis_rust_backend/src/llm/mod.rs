use anyhow::{anyhow, Context, Result};
use reqwest::Client;
use serde::{Deserialize, Serialize};

use crate::config::EvolutionConfig;

#[derive(Debug, Clone, Default)]
pub struct LlmResponse {
    pub content: String,
    pub cost: f64,
    pub thought: String,
}

pub trait LlmClient: Send + Sync {
    fn query(
        &self,
        user_msg: &str,
        system_msg: &str,
    ) -> impl std::future::Future<Output = Result<LlmResponse>> + Send;
}

pub fn build_llm_client(cfg: &EvolutionConfig) -> Result<Box<dyn LlmClientDyn>> {
    match cfg.llm_backend.as_str() {
        "openai" => Ok(Box::new(OpenAiClient::new(cfg)?)),
        _ => Ok(Box::new(MockLlmClient)),
    }
}

pub trait LlmClientDyn: Send + Sync {
    fn query_dyn(
        &self,
        user_msg: &str,
        system_msg: &str,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<LlmResponse>> + Send + '_>>;
}

#[derive(Debug, Clone, Default)]
pub struct MockLlmClient;

impl LlmClientDyn for MockLlmClient {
    fn query_dyn(
        &self,
        user_msg: &str,
        _system_msg: &str,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<LlmResponse>> + Send + '_>> {
        let code = format!(
            "<NAME>mock-patch</NAME>\n<DESCRIPTION>Mock mutation</DESCRIPTION>\n```python\n# mutated\n{}\n```",
            user_msg.lines().take(3).collect::<Vec<_>>().join("\n")
        );
        Box::pin(async move {
            Ok(LlmResponse {
                content: code,
                cost: 0.0,
                thought: "mock-thought".to_string(),
            })
        })
    }
}

#[derive(Debug, Clone)]
pub struct OpenAiClient {
    http: Client,
    base_url: String,
    model: String,
    api_key: String,
}

impl OpenAiClient {
    pub fn new(cfg: &EvolutionConfig) -> Result<Self> {
        let api_key = cfg
            .openai_api_key
            .clone()
            .ok_or_else(|| anyhow!("openai_api_key is required when llm_backend=openai"))?;
        Ok(Self {
            http: Client::new(),
            base_url: cfg.openai_base_url.clone(),
            model: cfg.openai_model.clone(),
            api_key,
        })
    }
}

impl LlmClientDyn for OpenAiClient {
    fn query_dyn(
        &self,
        user_msg: &str,
        system_msg: &str,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<LlmResponse>> + Send + '_>> {
        let url = format!(
            "{}/v1/chat/completions",
            self.base_url.trim_end_matches('/')
        );
        let req = OpenAiChatRequest {
            model: self.model.clone(),
            messages: vec![
                OpenAiMessage {
                    role: "system".to_string(),
                    content: system_msg.to_string(),
                },
                OpenAiMessage {
                    role: "user".to_string(),
                    content: user_msg.to_string(),
                },
            ],
            temperature: Some(0.7),
        };

        let http = self.http.clone();
        let api_key = self.api_key.clone();

        Box::pin(async move {
            let resp = http
                .post(url)
                .bearer_auth(&api_key)
                .json(&req)
                .send()
                .await
                .with_context(|| "openai request failed")?
                .error_for_status()
                .with_context(|| "openai non-success response")?
                .json::<OpenAiChatResponse>()
                .await
                .with_context(|| "failed to decode openai response")?;

            let content = resp
                .choices
                .first()
                .map(|c| c.message.content.clone())
                .unwrap_or_default();

            Ok(LlmResponse {
                content,
                cost: 0.0,
                thought: String::new(),
            })
        })
    }
}

#[derive(Debug, Clone, Serialize)]
struct OpenAiChatRequest {
    model: String,
    messages: Vec<OpenAiMessage>,
    #[serde(skip_serializing_if = "Option::is_none")]
    temperature: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct OpenAiMessage {
    role: String,
    content: String,
}

#[derive(Debug, Clone, Deserialize)]
struct OpenAiChatResponse {
    choices: Vec<OpenAiChoice>,
}

#[derive(Debug, Clone, Deserialize)]
struct OpenAiChoice {
    message: OpenAiMessage,
}
