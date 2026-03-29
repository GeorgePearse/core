import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


WORD_PATTERN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{2,}")


@dataclass
class ALMAMemoryEntry:
    generation: int
    memory_type: str  # success | failure
    patch_type: str
    patch_name: str
    patch_description: str
    score_delta: float
    combined_score: float
    summary: str
    keywords: List[str]


class ALMAMemorySystem:
    """ALMA-inspired long-term memory for evolutionary code agents.

    This stores structured mutation outcomes and retrieves relevant, concise
    memories to ground future patch generation.
    """

    def __init__(
        self,
        enabled: bool = False,
        max_entries: int = 256,
        max_retrievals: int = 4,
        min_success_delta: float = 0.0,
    ):
        self.enabled = enabled
        self.max_entries = max(1, max_entries)
        self.max_retrievals = max(1, max_retrievals)
        self.min_success_delta = min_success_delta
        self.entries: List[ALMAMemoryEntry] = []

    def observe_outcome(
        self,
        generation: int,
        parent_score: float,
        child_score: float,
        correct: bool,
        patch_type: Optional[str],
        patch_name: Optional[str],
        patch_description: Optional[str],
        diff_summary: Any,
        text_feedback: Optional[str],
        error_message: Optional[str],
    ) -> None:
        """Capture one mutation episode as durable memory."""
        if not self.enabled:
            return

        score_delta = child_score - parent_score
        is_success = correct and score_delta >= self.min_success_delta
        memory_type = "success" if is_success else "failure"

        summary_parts: List[str] = []
        if patch_description:
            summary_parts.append(patch_description.strip())
        if diff_summary:
            summary_parts.append(self._compact_text(diff_summary, 180))
        if text_feedback:
            summary_parts.append(self._compact_text(text_feedback, 180))
        if error_message:
            summary_parts.append(self._compact_text(error_message, 180))
        summary = " | ".join(part for part in summary_parts if part)[:500]

        keywords = self._extract_keywords(
            " ".join(
                [
                    str(patch_type or ""),
                    str(patch_name or ""),
                    str(patch_description or ""),
                    str(diff_summary or ""),
                    str(text_feedback or ""),
                    str(error_message or ""),
                ]
            )
        )

        entry = ALMAMemoryEntry(
            generation=generation,
            memory_type=memory_type,
            patch_type=patch_type or "unknown",
            patch_name=patch_name or "",
            patch_description=patch_description or "",
            score_delta=score_delta,
            combined_score=child_score,
            summary=summary,
            keywords=keywords,
        )
        self.entries.append(entry)
        self._trim_entries()

    def build_prompt_context(
        self,
        current_generation: int,
        parent_code: str,
        parent_feedback: Optional[str],
    ) -> Optional[str]:
        """Retrieve memory snippets relevant to current parent context."""
        if not self.enabled or not self.entries:
            return None

        context_keywords = self._extract_keywords(
            f"{parent_code[:2000]} {str(parent_feedback or '')}"
        )
        scored: List[tuple[float, ALMAMemoryEntry]] = []
        for entry in self.entries:
            overlap = len(set(context_keywords) & set(entry.keywords))
            recency_bonus = 1.0 / (1.0 + max(0, current_generation - entry.generation))
            impact = abs(entry.score_delta)
            score = (2.0 * overlap) + recency_bonus + impact
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [entry for _, entry in scored[: self.max_retrievals]]
        if not selected:
            return None

        success_entries = [e for e in selected if e.memory_type == "success"]
        failure_entries = [e for e in selected if e.memory_type == "failure"]
        lines: List[str] = ["# ALMA Long-Term Memory"]
        if success_entries:
            lines.append("## Reuse These Successful Patterns")
            for item in success_entries:
                lines.append(
                    f"- {item.patch_type} `{item.patch_name or 'unnamed'}` "
                    f"(delta {item.score_delta:+.4f}): {item.summary or 'No summary.'}"
                )
        if failure_entries:
            lines.append("## Avoid These Failure Patterns")
            for item in failure_entries:
                lines.append(
                    f"- {item.patch_type} `{item.patch_name or 'unnamed'}` "
                    f"(delta {item.score_delta:+.4f}): {item.summary or 'No summary.'}"
                )
        return "\n".join(lines)

    def save_state(self, path: str) -> None:
        if not self.enabled:
            return
        payload = {
            "enabled": self.enabled,
            "max_entries": self.max_entries,
            "max_retrievals": self.max_retrievals,
            "min_success_delta": self.min_success_delta,
            "entries": [asdict(entry) for entry in self.entries],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def load_state(self, path: str) -> bool:
        if not self.enabled:
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return False

        loaded_entries: List[ALMAMemoryEntry] = []
        for item in payload.get("entries", []):
            try:
                loaded_entries.append(ALMAMemoryEntry(**item))
            except TypeError:
                continue
        self.entries = loaded_entries
        self._trim_entries()
        return True

    def _trim_entries(self) -> None:
        if len(self.entries) <= self.max_entries:
            return
        self.entries.sort(
            key=lambda x: (abs(x.score_delta), x.generation),
            reverse=True,
        )
        self.entries = self.entries[: self.max_entries]

    def _extract_keywords(self, text: str) -> List[str]:
        if not text:
            return []
        words = [w.lower() for w in WORD_PATTERN.findall(text)]
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "into",
            "code",
            "patch",
            "generation",
            "score",
            "delta",
            "result",
            "error",
        }
        unique = []
        seen = set()
        for word in words:
            if word in stopwords or word in seen:
                continue
            seen.add(word)
            unique.append(word)
        return unique[:30]

    def _compact_text(self, obj: Any, max_len: int) -> str:
        if obj is None:
            return ""
        text = str(obj).replace("\n", " ").strip()
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."
