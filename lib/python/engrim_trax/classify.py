"""Jev decides the trackinizer kind and typed fields of each engrim record; answers are cached to JSONL."""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from memtype.jev import Jev, boolean, choice
from memtype.store import ACCEPT, REVIEW

from engrim_trax.records import (
    Record,
    arxiv_id,
    clauses,
    metric_pairs,
    shas,
    truncate,
    urls,
)

QUESTION_SET = "v1"
TITLE_MAX = 160
MAX_OPTIONS = 254

KINDS: dict[str, str | None] = {
    "Issue": "work to pursue or in flight: a task, a dispatched agent session, a PR awaiting review or merge, "
    "a build, deploy or data run in progress, a blocked or waiting workstream",
    "Belief": "a proposition: a fact, a decision, a preference, feedback on how to work, a trap or rule; "
    "something that is true or false",
    "Experiment": "a measured comparison or run: explicit numbers produced by a stated method, arms compared, "
    "metrics reported",
    "WebResult": "a reference to a web page, doc, dashboard, repository or service URL",
    "Paper": "an arXiv or academic paper reference",
    "CodeChange": "a bare reference to one git commit by SHA",
    "AgentSession": "a captured agent CLI session transcript, or the handle of one",
}
KIND_HINT = (
    "Hints from engrim conventions, not rules: 'state' rows that describe a dispatched session or a PR in "
    "flight are usually Issues; 'fact' rows are Beliefs unless they report a measured comparison with numbers "
    "and a method, which is an Experiment; 'decision' rows are Beliefs (the decision is the judgement) unless "
    "they define work to do, then Issues; 'feedback' and 'user' rows are Beliefs; 'reference' rows with a URL "
    "are WebResults, Papers when they cite an arXiv or academic paper, CodeChanges when they are a bare commit."
)
DEFAULT_KIND = {
    "state": "Issue",
    "fact": "Belief",
    "decision": "Belief",
    "feedback": "Belief",
    "user": "Belief",
    "reference": "WebResult",
}
ISSUE_KINDS: dict[str, str | None] = {
    "feature": "a new capability or an improvement to build",
    "bug": "a defect, breakage or regression to fix",
    "task": "a chore, migration, data run, dispatch, review or other work item",
    "question": "something to find out or decide",
}
PRIORITIES: dict[str, str | None] = {
    "p0": "blocking production or George right now",
    "p1": "high: needed this week",
    "p2": "normal, the default",
    "p3": "low",
    "p4": "someday or nice to have",
    "unknown": "the text gives no sense of urgency",
}
PRIORITY_VALUE = {"p0": 0, "p1": 10, "p2": 20, "p3": 30, "p4": 40}
JUDGEMENTS: dict[str, str | None] = {
    "proven": "stated as established, verified, measured or confirmed",
    "disproven": "stated as false, retracted, or shown wrong",
    "unproven": "a hypothesis, plan, preference or claim stated without verification",
    "undecidable": "cannot be settled on the information available",
}


def state_text(r: Record) -> str:
    return (
        f"engrim memory record #{r.id}\n"
        f"engrim type: {r.type}\nengrim status: {r.status}\ntags: {', '.join(r.tags) or '-'}\n"
        f"project: {r.project_name}\nrecorded: {r.ts}\n\nsummary: {r.summary}\n"
        + (f"\ndetail: {r.detail[:2400]}\n" if r.detail else "")
    )


def pair_text(a: Record, b: Record) -> str:
    return f"RECORD A (older, {a.ts}, engrim {a.type}):\n{a.text}\n\nRECORD B (newer, {b.ts}, engrim {b.type}):\n{b.text}\n"


def title_candidates(summary: str) -> dict[str, str | None]:
    return {c: None for c in clauses(summary, TITLE_MAX)[: MAX_OPTIONS - 1]}


def kind_questions(r: Record) -> dict[str, dict[str, Any]]:
    q: dict[str, dict[str, Any]] = {
        "kind": choice(f"Which trackinizer record kind best fits this engrim memory record? {KIND_HINT}", KINDS),
        "finished": boolean(
            "If the record describes work (a task, PR, dispatched session, build, deploy, data run), is that "
            "work already finished: merged, delivered, landed, completed?"
        ),
        "abandoned": boolean(
            "If the record describes work, was it dropped, abandoned, or blocked with no path forward, "
            "rather than completed?"
        ),
        "issue_kind": choice("Read the record as a work item. Which category fits it best?", ISSUE_KINDS),
        "priority": choice("How urgent is the work the record describes?", PRIORITIES),
        "judgement": choice(
            "Read the record as a proposition. What verdict does the record itself give on it?", JUDGEMENTS
        ),
        "true_now": boolean(
            "Is the proposition stated by this record true and still valid as written (not marked stale, "
            "superseded or contradicted within its own text)?"
        ),
        "measured": boolean(
            "Does the record report a measured result or comparison with explicit numbers and the method "
            "that produced them?"
        ),
    }
    if len(r.summary) > TITLE_MAX:
        cands = title_candidates(r.summary)
        if len(cands) > 1:
            q["title"] = choice("Which clause best serves as a short one-line title for the whole record?", cands)
    return q


def experiment_questions(r: Record) -> dict[str, dict[str, Any]]:
    opts: dict[str, str | None] = {c: None for c in clauses(r.text)[: MAX_OPTIONS - 1]}
    opts["none"] = "no clause states this"
    q: dict[str, dict[str, Any]] = {
        "outcome": choice("Which clause states the measured result in one line?", opts),
        "config": choice(
            "Which clause describes the setup, arms or configuration that was compared or run?", opts
        ),
    }
    pairs = metric_pairs(r.text)
    if pairs:
        listed = ", ".join(f"{k}={v:g}" for k, v in pairs[:12])
        q["metrics_ok"] = boolean(
            f"Are these explicit metric name/value pairs results measured by this experiment: {listed}?"
        )
    return q


SUPERSEDE_Q = {
    "corrected": boolean(
        "Is record B the corrected or updated version of record A: the same subject, with B replacing what A "
        "states?"
    )
}
EVIDENCE_Q = {
    "bears": boolean("Does record A provide evidence that bears on whether the claim in record B is true?"),
    "supports": boolean(
        "Does record A support the claim in record B (true) rather than contradict it (false)?"
    ),
}


@dataclass
class Mapping:
    """The Jev-decided trackinizer row for one engrim record."""

    record_id: int
    kind: str
    kind_p: float
    band: str
    title: str
    description: str
    labels: list[str]
    status: str
    fields: dict[str, Any] = field(default_factory=dict)
    metrics: list[tuple[str, float]] = field(default_factory=list)
    measured_p: float = 0.0
    answers: dict[str, Any] = field(default_factory=dict)


def band_of(p: float) -> str:
    return "accept" if p >= ACCEPT else "review" if p >= REVIEW else "fallback"


def _pick(ans: dict[str, Any], name: str, default: str) -> str:
    a = ans.get(name)
    return str(a["choice"]) if a and a["p"] >= REVIEW else default


def _p(ans: dict[str, Any], name: str) -> float:
    a = ans.get(name)
    return float(a["p"]) if a else 0.0


def provenance(r: Record, kind: str, p: float, band: str) -> str:
    lines = [
        "---",
        f"engrim id: {r.id} | type: {r.type} | status: {r.status} | ts: {r.ts}",
        f"project: {r.project} | source: {r.source or '-'} | origin_agent: {r.origin_agent or '-'}",
        f"tags: {', '.join(r.tags) or '-'}",
    ]
    if r.links:
        lines.append("links: " + " ".join(r.links))
    lines.append(f"jev kind: {kind} p={p:.2f} ({band}); question set {QUESTION_SET}")
    return "\n".join(lines)


def decide(r: Record, ans: dict[str, Any], exp: dict[str, Any] | None = None) -> Mapping:
    """Turn Jev's answers into a Mapping; the fallback kind is the engrim type's default."""
    kind_a = ans["kind"]
    p = float(kind_a["p"])
    band = band_of(p)
    default = DEFAULT_KIND.get(r.type, "Belief")
    if default == "WebResult" and not urls(r.text):
        default = "Belief"
    kind = str(kind_a["choice"]) if band != "fallback" else default
    labels = list(r.tags) + ["engrim", f"engrim:{r.type}", f"project:{r.project_name}"]
    if band == "review":
        labels.append("jev:low-confidence")
    elif band == "fallback":
        labels.append("jev:fallback")
    if r.status == "superseded":
        labels.append("engrim:superseded")
    if r.type in {"feedback", "user"} and r.type not in labels:
        labels.append(r.type)
    labels = list(dict.fromkeys(x for x in labels if x))

    title = r.summary
    if len(title) > TITLE_MAX:
        title = _pick(ans, "title", "") or truncate(r.summary, TITLE_MAX)
    description = r.text + "\n\n" + provenance(r, str(kind_a["choice"]), p, band)

    status = "active"
    fields: dict[str, Any] = {}
    metrics: list[tuple[str, float]] = []
    if kind == "Issue":
        if _p(ans, "finished") >= REVIEW:
            status = "complete"
        elif _p(ans, "abandoned") >= REVIEW:
            status = "abandoned"
        fields["issue_kind"] = [_pick(ans, "issue_kind", "task")]
        pr = _pick(ans, "priority", "unknown")
        if pr in PRIORITY_VALUE:
            fields["priority"] = PRIORITY_VALUE[pr]
    elif kind == "Belief":
        fields["judgement"] = _pick(ans, "judgement", "unproven")
        fields["confidence"] = round(_p(ans, "true_now"), 3)
    elif kind == "Experiment":
        exp = exp or {}
        outcome = _pick(exp, "outcome", "none")
        config = _pick(exp, "config", "none")
        if outcome != "none":
            fields["outcome"] = outcome
        if config != "none":
            fields["config"] = {"setup": config}
        if _p(exp, "metrics_ok") >= ACCEPT:
            metrics = metric_pairs(r.text)
        status = "complete" if _p(ans, "measured") >= REVIEW else "active"
    elif kind == "WebResult":
        found = urls(r.text)
        if found:
            fields["url"] = found[0]
    elif kind == "Paper":
        ax = arxiv_id(r.text)
        found = urls(r.text)
        if ax:
            fields["source"] = f"arXiv:{ax}"
        elif found:
            fields["source"] = found[0]
    elif kind == "CodeChange":
        found = shas(r.text)
        if found:
            fields["sha"] = found[0]
    elif kind == "AgentSession":
        fields["cli"] = r.origin_agent or "claude"
    return Mapping(
        record_id=r.id,
        kind=kind,
        kind_p=p,
        band=band,
        title=title,
        description=description,
        labels=labels,
        status=status,
        fields=fields,
        metrics=metrics,
        measured_p=_p(ans, "measured"),
        answers=ans,
    )


class Classifier:
    """Asks Jev once per record (plus one more for Experiments), caching every answer to a JSONL file."""

    def __init__(self, jev: Jev, cache_path: str | Path | None, concurrency_batch: int = 64) -> None:
        self.jev = jev
        self.cache_path = Path(cache_path) if cache_path else None
        self.batch = concurrency_batch
        self.cache: dict[str, dict[str, Any]] = {}
        self.cache_hits = 0
        if self.cache_path and self.cache_path.exists():
            for line in self.cache_path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.cache[row["key"]] = row["answers"]

    async def ask(self, key: str, state: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        if key in self.cache:
            self.cache_hits += 1
            return self.cache[key]
        ans = await self.jev.ask(state, questions)
        self.cache[key] = ans
        if self.cache_path:
            with self.cache_path.open("a") as fh:
                fh.write(json.dumps({"key": key, "answers": ans}) + "\n")
        return ans

    def _key(self, r: Record, stage: str) -> str:
        return f"{QUESTION_SET}:{stage}:{r.id}:{r.content_hash()}"

    async def classify_one(self, r: Record) -> Mapping:
        ans = await self.ask(self._key(r, "kind"), state_text(r), kind_questions(r))
        exp = None
        kind = str(ans["kind"]["choice"]) if band_of(float(ans["kind"]["p"])) != "fallback" else None
        if kind == "Experiment":
            exp = await self.ask(self._key(r, "experiment"), state_text(r), experiment_questions(r))
        return decide(r, ans, exp)

    async def classify(self, records: list[Record]) -> dict[int, Mapping]:
        out: dict[int, Mapping] = {}
        for k in range(0, len(records), self.batch):
            chunk = records[k : k + self.batch]
            for m in await asyncio.gather(*(self.classify_one(r) for r in chunk)):
                out[m.record_id] = m
        return out

    async def corrected(self, a: Record, b: Record) -> float:
        key = f"{QUESTION_SET}:supersede:{a.id}:{b.id}:{a.content_hash()}:{b.content_hash()}"
        return float((await self.ask(key, pair_text(a, b), SUPERSEDE_Q))["corrected"]["p"])

    async def evidence(self, src: Record, tgt: Record) -> tuple[float, float]:
        key = f"{QUESTION_SET}:evidence:{src.id}:{tgt.id}:{src.content_hash()}:{tgt.content_hash()}"
        # Jev sees the older record as A; here the evidence (src) is newer, so A = claim (tgt), B = evidence.
        state = (
            f"RECORD A (the evidence, {src.ts}, engrim {src.type}):\n{src.text}\n\n"
            f"RECORD B (the claim, {tgt.ts}, engrim {tgt.type}):\n{tgt.text}\n"
        )
        ans = await self.ask(key, state, EVIDENCE_Q)
        return float(ans["bears"]["p"]), float(ans["supports"]["p"])
