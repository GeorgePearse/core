"""Small supervised encoders with portable weights and explicit training receipts."""

import time
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from sklearn.base import BaseEstimator, ClassifierMixin


class TrainingConfig(BaseModel):
    """Bound the work and keep all consequential hyperparameters in the ledger."""

    model_config = ConfigDict(extra="forbid")
    epochs: int = Field(default=4, ge=1, le=30)
    batch_size: int = Field(default=32, ge=1, le=128)
    learning_rate: float = Field(default=0.0003, gt=0, le=0.01)
    max_length: int = Field(default=96, ge=8, le=512)
    initialization: Literal["pretrained", "random"] = "pretrained"


class FineTunedClassifier(ClassifierMixin, BaseEstimator):
    """Train all encoder weights; serialize tensors and tokenizer for offline CPU use."""

    def __init__(
        self,
        model_id: str,
        seed: int = 42,
        epochs: int = 4,
        batch_size: int = 32,
        learning_rate: float = 0.0003,
        max_length: int = 96,
        initialization: str = "pretrained",
    ) -> None:
        self.model_id = model_id
        self.seed = seed
        self.epochs = epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.max_length = max_length
        self.initialization = initialization

    def fit(self, X: list[str], y: list[str]) -> "FineTunedClassifier":
        """Fit on supplied training rows only, without validation-driven stopping."""
        import torch
        from huggingface_hub import model_info
        from transformers import (
            AutoConfig,
            AutoModelForSequenceClassification,
            AutoTokenizer,
            set_seed,
        )

        torch.set_num_threads(2)
        set_seed(self.seed)
        self.classes_, labels = np.unique(y, return_inverse=True)
        self.revision_ = model_info(self.model_id).sha
        loaded = time.perf_counter()
        tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            revision=self.revision_,
            use_fast=True,
            trust_remote_code=False,
        )
        config = AutoConfig.from_pretrained(
            self.model_id,
            revision=self.revision_,
            num_labels=len(self.classes_),
            trust_remote_code=False,
        )
        if self.initialization == "pretrained":
            model = AutoModelForSequenceClassification.from_pretrained(
                self.model_id,
                revision=self.revision_,
                config=config,
                trust_remote_code=False,
            )
        else:
            model = AutoModelForSequenceClassification.from_config(config)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        encoded = tokenizer(
            X,
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt",
        )
        labels = torch.tensor(labels, dtype=torch.long)
        load_seconds = time.perf_counter() - loaded
        optimizer = torch.optim.AdamW(
            model.parameters(), lr=self.learning_rate, weight_decay=0.01
        )
        generator = torch.Generator().manual_seed(self.seed)
        history = []
        if device == "cuda":
            torch.cuda.synchronize()
        started = time.perf_counter()
        model.train()
        for epoch in range(self.epochs):
            epoch_start = time.perf_counter()
            loss_sum = 0.0
            for indices in torch.randperm(len(X), generator=generator).split(
                self.batch_size
            ):
                optimizer.zero_grad(set_to_none=True)
                output = model(
                    **{k: v[indices].to(device) for k, v in encoded.items()},
                    labels=labels[indices].to(device),
                )
                output.loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                loss_sum += float(output.loss.detach().cpu()) * len(indices)
            if device == "cuda":
                torch.cuda.synchronize()
            history.append(
                {
                    "epoch": epoch + 1,
                    "train_loss": loss_sum / len(X),
                    "seconds": time.perf_counter() - epoch_start,
                }
            )
        train_seconds = time.perf_counter() - started
        self.training_receipt_ = {
            "model_id": self.model_id,
            "revision": self.revision_,
            "initialization": self.initialization,
            "device": device,
            "gpu": torch.cuda.get_device_name() if device == "cuda" else None,
            "parameters": sum(p.numel() for p in model.parameters()),
            "trainable_parameters": sum(
                p.numel() for p in model.parameters() if p.requires_grad
            ),
            "train_examples": len(X),
            "train_seconds": train_seconds,
            "load_and_tokenize_seconds": load_seconds,
            "epochs": history,
            "torch": torch.__version__,
        }
        model.cpu().eval()
        self.config_ = model.config.to_dict()
        self.weights_ = {
            k: v.detach().numpy().copy() for k, v in model.state_dict().items()
        }
        self.tokenizer_json_ = tokenizer.backend_tokenizer.to_str()
        self.special_tokens_ = {
            k: str(v)
            for k, v in tokenizer.special_tokens_map.items()
            if isinstance(v, str)
        }
        self.runtime_ = (model, tokenizer)
        return self

    def _runtime(self) -> tuple[Any, Any]:
        import torch
        from tokenizers import Tokenizer
        from transformers import (
            AutoConfig,
            AutoModelForSequenceClassification,
            PreTrainedTokenizerFast,
        )

        torch.set_num_threads(2)
        if not hasattr(self, "runtime_"):
            config = dict(self.config_)
            kind = config.pop("model_type")
            model = AutoModelForSequenceClassification.from_config(
                AutoConfig.for_model(kind, **config)
            )
            model.load_state_dict(
                {k: torch.from_numpy(v) for k, v in self.weights_.items()}
            )
            model.eval()
            tokenizer = PreTrainedTokenizerFast(
                tokenizer_object=Tokenizer.from_str(self.tokenizer_json_),
                **self.special_tokens_,
            )
            self.runtime_ = (model, tokenizer)
        return self.runtime_

    def predict_proba(self, X: list[str]) -> np.ndarray:
        """Run warm inference on CPU, including tokenization; requires no network."""
        import torch

        model, tokenizer = self._runtime()
        outputs = []
        with torch.inference_mode():
            for offset in range(0, len(X), self.batch_size):
                batch = tokenizer(
                    X[offset : offset + self.batch_size],
                    truncation=True,
                    padding=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                outputs.append(model(**batch).logits.softmax(-1).numpy())
        return np.concatenate(outputs)

    def __getstate__(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "runtime_"}
