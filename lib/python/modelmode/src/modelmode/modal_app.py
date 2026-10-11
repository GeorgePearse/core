"""Deploy once: modal deploy -m modelmode.modal_app. One shared T4 worker."""

from pathlib import Path

import modal

APP_NAME = "modelmode"
app = modal.App(APP_NAME)
cache = modal.Volume.from_name("modelmode-hf-cache", create_if_missing=True)
artifacts = modal.Volume.from_name("modelmode-artifacts", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.8.0",
        "transformers==4.57.1",
        "huggingface-hub==0.36.0",
        "scikit-learn==1.7.1",
        "numpy==2.2.6",
        "scipy==1.15.3",
        "joblib==1.5.2",
        "pydantic==2.12.5",
        "threadpoolctl==3.6.0",
    )
    .env(
        {
            "HF_HOME": "/cache",
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2",
            "TOKENIZERS_PARALLELISM": "false",
            "HF_HUB_DISABLE_TELEMETRY": "1",
        }
    )
    .add_local_python_source("modelmode", copy=True)
)


@app.function(
    image=image,
    gpu="T4",
    cpu=2,
    memory=8192,
    max_containers=1,
    min_containers=0,
    scaledown_window=60,
    timeout=3600,
    retries=0,
    volumes={"/cache": cache, "/artifacts": artifacts},
)
def train(payload: dict) -> dict:
    """Persist remote receipts and return only this run's verified model artifacts."""
    import time

    from modelmode.storage import identifier, implementation_hash, read, write
    from modelmode.worker import fit

    if payload["state"].get("implementation_sha256") != implementation_hash():
        raise ValueError(
            "Redeploy Modal worker to match the installed ModelMode implementation"
        )
    run_id = identifier(payload["state"]["run_id"])
    data = payload["data"]
    if any(row["split"] not in {"train", "validation"} for row in data["rows"]):
        raise ValueError("Remote training must never receive test examples")
    root = Path("/artifacts")
    path = root / "runs" / run_id
    write(path / "state.json", payload["state"])
    started = time.perf_counter()
    try:
        fit(root, run_id, data_override=data)
        state = read(path / "state.json")
        state["remote_seconds"] = time.perf_counter() - started
        write(path / "state.json", state)
        files = {}
        for candidate in state["candidates"]:
            if candidate["status"] == "succeeded":
                for suffix in ("joblib", "validation.json"):
                    filename = f"{candidate['name']}.{suffix}"
                    files[filename] = (path / filename).read_bytes()
        return {"state": state, "files": files}
    finally:
        artifacts.commit()
        cache.commit()
