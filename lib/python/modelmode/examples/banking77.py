"""Reproducible small intent benchmark; run from the installed package environment."""

import argparse
import csv
import hashlib
import io
import json
import urllib.request
from pathlib import Path

from sklearn.model_selection import train_test_split

from modelmode import Workspace
from modelmode.data import input_key
from modelmode.storage import write

COMMIT = "57ec275d8078af65b7731c2a98be812d844a6d6b"
BASE = f"https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/{COMMIT}/banking_data"


def dataset(
    root: Path, classes: int = 12, label_offset: int = 0
) -> tuple[list[dict], dict]:
    """Use the first alphabetic intents, remove duplicates, preserve official test."""
    loaded = {}
    receipts = {}
    for split in ("train", "test"):
        url = f"{BASE}/{split}.csv"
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read()
        (root / f"{split}.csv").write_bytes(raw)
        receipts[split] = {"url": url, "sha256": hashlib.sha256(raw).hexdigest()}
        loaded[split] = list(csv.DictReader(io.StringIO(raw.decode())))
    labels = sorted({r["category"] for r in loaded["train"]})[
        label_offset : label_offset + classes
    ]
    rows = []
    used = set()
    dropped = []
    # Test takes priority when an official train row duplicates a test input.
    for split in ("test", "train"):
        for i, source in enumerate(loaded[split]):
            if source["category"] not in labels:
                continue
            row = {
                "id": f"banking77-{split}-{i}",
                "text": source["text"],
                "label": source["category"],
                "split": split,
            }
            key = input_key(row)
            if key in used:
                dropped.append(row["id"])
                continue
            used.add(key)
            rows.append(row)
    train = [r for r in rows if r["split"] == "train"]
    _, validation = train_test_split(
        train, test_size=0.2, random_state=42, stratify=[r["label"] for r in train]
    )
    for row in validation:
        row["split"] = "validation"
    receipt = {
        "source": receipts,
        "commit": COMMIT,
        "classes": labels,
        "removed_duplicate_ids": dropped,
        "selection": f"Alphabetic training labels {label_offset + 1}–{label_offset + classes}, fixed before evaluation",
        "license": "CC BY 4.0",
    }
    write(root / "dataset-receipt.json", receipt)
    return rows, receipt


def main() -> None:
    """Run a matched search and materialize its result for the HTML report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--execution", choices=["local", "modal"], default="modal")
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--classes", type=int, default=12)
    parser.add_argument("--no-final-test", action="store_true")
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    rows, receipt = dataset(args.root, args.classes)
    workspace = Workspace(args.root)
    data = workspace.create_dataset("BANKING77 bounded intent benchmark", rows)
    run = workspace.learn(
        data["dataset_id"],
        candidates=[
            "tfidf_word",
            "tfidf_char",
            "bert_tiny_random",
            "bert_tiny",
            "bert_mini",
        ],
        execution=args.execution,
        budget_seconds=900,
        training={"epochs": args.epochs},
    )
    print(json.dumps({"run_id": run["run_id"], "dataset": data}), flush=True)
    done = workspace.wait(run["run_id"], timeout=950)
    write(
        args.root / "benchmark.json",
        {"dataset": data, "provenance": receipt, "run": done},
    )
    if done["status"] != "succeeded":
        raise RuntimeError(done)
    if not args.no_final_test:
        final = workspace.evaluate(run["run_id"])
        capability = workspace.publish(
            run["run_id"], "banking_intent", abstain_below=0.8
        )
        predictions = workspace.predict(
            "banking_intent",
            [
                "How old do I need to be to open an account?",
                "How do I activate my new card?",
                "The ATM did not give me cash",
            ],
        )
        write(
            args.root / "benchmark.json",
            {
                "dataset": data,
                "provenance": receipt,
                "run": done,
                "test": final,
                "capability": capability,
                "demo": predictions,
            },
        )
    print(json.dumps(done, indent=2), flush=True)


if __name__ == "__main__":
    main()
