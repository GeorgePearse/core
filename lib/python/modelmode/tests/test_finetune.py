"""Offline gradient updates and exact artifact reload for the neural backend."""

from pathlib import Path
from types import SimpleNamespace

import joblib
import numpy as np
import pytest

pytest.importorskip("torch")
pytest.importorskip("transformers")


def test_full_weights_train_and_reload_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch
    from transformers import (
        BertConfig,
        BertForSequenceClassification,
        BertTokenizerFast,
    )

    from modelmode.finetune import FineTunedClassifier

    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    vocab = checkpoint / "vocab.txt"
    vocab.write_text(
        "\n".join(
            [
                "[PAD]",
                "[UNK]",
                "[CLS]",
                "[SEP]",
                "[MASK]",
                "payment",
                "delivery",
                "request",
            ]
        )
    )
    tokenizer = BertTokenizerFast(vocab_file=str(vocab))
    tokenizer.save_pretrained(checkpoint)
    initial = BertForSequenceClassification(
        BertConfig(
            vocab_size=8,
            hidden_size=16,
            num_hidden_layers=1,
            num_attention_heads=2,
            intermediate_size=32,
            num_labels=2,
        )
    )
    initial.save_pretrained(checkpoint)
    monkeypatch.setattr(
        "huggingface_hub.model_info", lambda _: SimpleNamespace(sha="test-revision")
    )
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    model = FineTunedClassifier(
        str(checkpoint), epochs=2, batch_size=2, learning_rate=0.01, max_length=16
    )
    X = ["payment request", "delivery request"] * 4
    model.fit(X, ["payment", "delivery"] * 4)
    name = "bert.embeddings.word_embeddings.weight"
    assert not np.array_equal(model.weights_[name], initial.state_dict()[name].numpy())
    assert (
        model.training_receipt_["trainable_parameters"]
        == model.training_receipt_["parameters"]
    )
    assert len(model.training_receipt_["epochs"]) == 2
    artifact = tmp_path / "model.joblib"
    joblib.dump(model, artifact)
    restored = joblib.load(artifact)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    # Any accidental download when reconstructing would fail even if cache exists.
    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        lambda *a, **kw: pytest.fail("Unexpected network dependency"),
    )
    np.testing.assert_allclose(
        model.predict_proba(X), restored.predict_proba(X), atol=1e-7
    )
