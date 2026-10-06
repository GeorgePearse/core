"""Async client for Jev (typesafe-ai/jev) on the Vercel AI Gateway, plus a deterministic fake for tests."""

import asyncio
import os
import time
from collections.abc import Callable
from typing import Any

import httpx

URL = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"
MODEL = "typesafe-ai/jev"
RETRY_DELAYS_S = (1.0, 4.0, 12.0)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

Questions = dict[str, dict[str, Any]]
Answers = dict[str, dict[str, Any]]


def boolean(
    instructions: str, true: str | None = None, false: str | None = None
) -> dict[str, Any]:
    q: dict[str, Any] = {"type": "boolean", "instructions": instructions}
    if true or false:
        q["criteria"] = {"true": true or "", "false": false or ""}
    return q


def choice(instructions: str, options: dict[str, str | None]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": options}


def _normalise(raw: dict[str, Any], confidence: float | None) -> dict[str, Any]:
    if raw.get("type") == "boolean":
        p = float(raw.get("probability") or 0.0)
        return {
            "choice": p >= 0.5,
            "p": p,
            "probabilities": {"true": p, "false": 1 - p},
            "confidence": None,
        }
    probs = {str(k): float(v) for k, v in (raw.get("probabilities") or {}).items()}
    pick = raw.get("choice")
    return {
        "choice": pick,
        "p": probs.get(pick, 0.0),
        "probabilities": probs,
        "confidence": confidence,
    }


class Jev:
    """Typed questions over one text state; returns {name: {choice, p, probabilities, confidence}}."""

    def __init__(
        self,
        api_key: str | None = None,
        concurrency: int = 12,
        budget_usd: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("AI_GATEWAY_API_KEY", "")
        self.budget_usd = budget_usd
        self.usd = 0.0
        self.calls = 0
        self.input_tokens = 0
        self.latencies: list[float] = []
        self.retries = 0
        self._sem = asyncio.Semaphore(concurrency)
        self._client = httpx.AsyncClient(timeout=60, transport=transport)

    async def ask(self, state: str, questions: Questions) -> Answers:
        if self.usd >= self.budget_usd:
            raise RuntimeError(
                f"Jev budget exhausted: ${self.usd:.4f} >= ${self.budget_usd}"
            )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "ai-gateway-auth-method": "api-key",
            "ai-gateway-protocol-version": "0.0.1",
            "ai-evaluation-model-specification-version": "4",
            "ai-model-id": MODEL,
        }
        body = {"state": state, "questions": questions}
        async with self._sem:
            for i, delay in enumerate((0.0, *RETRY_DELAYS_S)):
                await asyncio.sleep(delay)
                t0 = time.perf_counter()
                try:
                    r = await self._client.post(URL, headers=headers, json=body)
                except httpx.TransportError:
                    if i == len(RETRY_DELAYS_S):
                        raise
                    continue
                if r.status_code in RETRY_STATUSES and i < len(RETRY_DELAYS_S):
                    self.retries += 1
                    continue
                break
        self.latencies.append(time.perf_counter() - t0)
        if r.status_code != 200:
            raise RuntimeError(f"Jev HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        meta = data.get("providerMetadata") or {}
        self.calls += 1
        self.usd += float((meta.get("gateway") or {}).get("cost") or 0.0)
        self.input_tokens += int((data.get("usage") or {}).get("inputTokens") or 0)
        conf = (meta.get("typesafe") or {}).get("confidence") or {}
        return {
            name: _normalise(raw, conf.get(name))
            for name, raw in (data.get("answers") or {}).items()
        }

    async def aclose(self) -> None:
        await self._client.aclose()


class FakeJev(Jev):
    """Deterministic stand-in: `rule(state, name, question)` returns the chosen option (or bool) and its probability."""

    def __init__(
        self,
        rule: Callable[[str, str, dict[str, Any]], tuple[Any, float]] | None = None,
    ) -> None:
        self.rule = rule or first_mentioned
        self.usd = 0.0
        self.calls = 0
        self.input_tokens = 0
        self.latencies = []
        self.retries = 0
        self.budget_usd = float("inf")

    async def ask(self, state: str, questions: Questions) -> Answers:
        self.calls += 1
        self.latencies.append(0.0)
        out: Answers = {}
        for name, q in questions.items():
            pick, p = self.rule(state, name, q)
            if q["type"] == "boolean":
                out[name] = {
                    "choice": bool(pick),
                    "p": p,
                    "probabilities": {"true": p, "false": 1 - p},
                    "confidence": None,
                }
            else:
                rest = [k for k in q["criteria"] if k != pick]
                probs = {pick: p, **{k: (1 - p) / max(len(rest), 1) for k in rest}}
                out[name] = {
                    "choice": pick,
                    "p": p,
                    "probabilities": probs,
                    "confidence": p,
                }
        return out

    async def aclose(self) -> None:
        return None


def first_mentioned(state: str, name: str, q: dict[str, Any]) -> tuple[Any, float]:
    if q["type"] == "boolean":
        return True, 0.9
    low = state.lower()
    hits = [
        k
        for k in q["criteria"]
        if k != "none" and k.lower().removeprefix("new:") in low
    ]
    if hits:
        return min(hits, key=lambda k: low.index(k.lower().removeprefix("new:"))), 0.9
    return next(iter(q["criteria"])), 0.6
