"""Small local estimators; external encoders are pinned and lazy-loaded."""

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TRAINABLE = {
    "bert_tiny": "google/bert_uncased_L-2_H-128_A-2",
    "bert_tiny_random": "google/bert_uncased_L-2_H-128_A-2",
    "bert_mini": "google/bert_uncased_L-4_H-256_A-4",
    "electra_small": "google/electra-small-discriminator",
}

ENCODERS = {
    "potion_2m": ("static", "minishlab/potion-base-2M"),
    "potion_8m": ("static", "minishlab/potion-base-8M"),
    "minilm_l3": ("transformer", "sentence-transformers/paraphrase-MiniLM-L3-v2"),
    "minilm_l6": ("transformer", "sentence-transformers/all-MiniLM-L6-v2"),
}
TEXT_CANDIDATES = ["tfidf_word", "tfidf_char", *ENCODERS, *TRAINABLE]
NUMERIC_CANDIDATES = ["linear", "hist_gradient_boosting"]


class TextEncoder(TransformerMixin, BaseEstimator):
    """Store the resolved encoder revision alongside each fitted classifier."""

    def __init__(self, kind: str, model_id: str, revision: str | None = None) -> None:
        self.kind = kind
        self.model_id = model_id
        self.revision = revision

    def _load(self) -> Any:
        if not hasattr(self, "encoder_"):
            from huggingface_hub import model_info

            if not hasattr(self, "revision_"):
                self.revision_ = self.revision or model_info(self.model_id).sha
            if self.kind == "static":
                from model2vec import StaticModel

                self.encoder_ = StaticModel.from_pretrained(
                    self.model_id, revision=self.revision_
                )
            else:
                import torch
                from sentence_transformers import SentenceTransformer

                torch.set_num_threads(2)

                self.encoder_ = SentenceTransformer(
                    self.model_id,
                    revision=self.revision_,
                    device="cpu",
                    trust_remote_code=False,
                )
        return self.encoder_

    def fit(self, X: list[str], y: Any = None) -> "TextEncoder":
        """The pretrained representation is fixed; only the downstream head fits."""
        self._load()
        return self

    def transform(self, X: list[str]) -> np.ndarray:
        """Encode on CPU with bounded batches for contextual models."""
        model = self._load()
        if self.kind == "static":
            return model.encode(X)
        return model.encode(
            X, batch_size=32, show_progress_bar=False, normalize_embeddings=True
        )

    def __getstate__(self) -> dict[str, Any]:
        # The immutable upstream revision is persisted; don't pickle torch modules.
        return {k: v for k, v in self.__dict__.items() if k != "encoder_"}


def build(name: str, mode: str, seed: int, training: dict | None = None) -> Any:
    """Construct a bounded candidate with no access to evaluation labels."""
    if name in TRAINABLE and mode == "text":
        from modelmode.finetune import FineTunedClassifier

        options = dict(training or {})
        if name.endswith("_random"):
            options["initialization"] = "random"
        return FineTunedClassifier(TRAINABLE[name], seed=seed, **options)
    if name == "dummy":
        return DummyClassifier(strategy="prior")
    classifier = LogisticRegression(C=4.0, max_iter=500, random_state=seed)
    if mode == "text":
        if name in ENCODERS:
            return Pipeline(
                [("encoder", TextEncoder(*ENCODERS[name])), ("classifier", classifier)]
            )
        if name in {"tfidf_word", "tfidf_char"}:
            vectorizer = TfidfVectorizer(
                analyzer="word" if name == "tfidf_word" else "char_wb",
                ngram_range=(1, 2) if name == "tfidf_word" else (3, 5),
                max_features=30_000,
                sublinear_tf=True,
                strip_accents="unicode",
            )
            return Pipeline([("vectorizer", vectorizer), ("classifier", classifier)])
    elif name == "linear":
        return Pipeline([("scale", StandardScaler()), ("classifier", classifier)])
    elif name == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(
            max_iter=100, max_leaf_nodes=15, random_state=seed
        )
    raise ValueError(f"Unsupported {mode} candidate: {name}")


def catalog() -> dict[str, Any]:
    """Let the supervising model discover methods without importing torch."""
    return {
        "text": TEXT_CANDIDATES,
        "features": NUMERIC_CANDIDATES,
        "baseline": "dummy (always included)",
        "encoders": {
            name: {
                "kind": kind,
                "model_id": model,
                "extra": "static" if kind == "static" else "transformers",
            }
            for name, (kind, model) in ENCODERS.items()
        },
        "trainable": {
            name: {
                "model_id": model,
                "extra": "train",
                "method": "full-weight classification fine-tuning or random initialization",
            }
            for name, model in TRAINABLE.items()
        },
        "execution": [
            "local CPU",
            "modal: one T4 GPU, requires deployment and Modal credentials",
        ],
    }
