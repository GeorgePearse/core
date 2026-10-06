"""FastAPI app for live and replay agentic-vision run viewing."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import dspy
import uvicorn
from agentic_vision.instance_segmentation import InstanceSegmentationAnnotator
from agentic_vision.viewer_runtime import (
    AgenticVisionRunRecorder,
    JsonObject,
    get_viewer_artifact_path,
    list_viewer_runs,
    load_viewer_events,
    load_viewer_run,
)
from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from viewer_api.config import get_settings
from viewer_api.image_sources import materialize_image_source

router = APIRouter(prefix="/agentic-vision-viewer", tags=["agentic-vision-viewer"])


class StartAgenticVisionViewerRunRequest(BaseModel):
    """Payload used to launch a new viewer-backed segmentation run."""

    frame_uri: str = Field(description="Image source. Supports local paths, http(s) URLs, and gs:// URIs.")
    dataset_name: str | None = None
    run_label: str | None = None
    max_iters: int = Field(default=16, ge=1, le=40)
    sam3_handler_name: str = "premier_sam3"


def _get_runs_dir() -> str:
    """Return the configured viewer-runs directory."""
    return get_settings().agentic_vision_viewer_runs_dir


def _get_run_or_404(run_id: str) -> JsonObject:
    """Load run metadata or raise 404."""
    try:
        return load_viewer_run(_get_runs_dir(), run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}") from exc


def _run_agentic_vision_viewer_job(request: StartAgenticVisionViewerRunRequest, run_id: str) -> None:
    """Materialize the image, run the annotator, and persist viewer artifacts."""
    settings = get_settings()
    recorder = AgenticVisionRunRecorder(_get_runs_dir(), run_id)
    recorder.update_status("running")

    temp_path: str | None = None
    try:
        recorder.emit_event(
            "run_started",
            status="running",
            message="Queued agentic-vision run",
            payload={
                "frame_uri": request.frame_uri,
                "dataset_name": request.dataset_name,
                "max_iters": request.max_iters,
                "sam3_handler_name": request.sam3_handler_name,
            },
        )

        temp_path = materialize_image_source(request.frame_uri)
        if not settings.dashscope_api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is required to run live viewer jobs.")

        lm = dspy.LM(
            f"openai/{settings.qwen_model}",
            api_key=settings.dashscope_api_key,
            api_base=settings.dashscope_api_base,
            max_tokens=4096,
            temperature=0.2,
        )
        annotator = InstanceSegmentationAnnotator(
            max_iters=request.max_iters,
            dataset_name=request.dataset_name,
            sam3_handler_name=request.sam3_handler_name,
        )

        with dspy.context(lm=lm):
            annotator(
                image=dspy.Image(temp_path),
                frame_uri=request.frame_uri,
                viewer_recorder=recorder,
            )
    except Exception as exc:
        logger.exception(f"Agentic-vision viewer run failed | run_id={run_id}")
        if recorder.metadata.get("status") != "failed":
            recorder.update_status("failed", error=str(exc))
            recorder.emit_event(
                "run_failed",
                status="error",
                message="Background viewer run failed",
                payload={"error": str(exc)},
            )
    finally:
        if temp_path is not None:
            temp_file_path = Path(temp_path)
            if temp_file_path.exists():
                temp_file_path.unlink(missing_ok=True)


@router.post("/runs", status_code=202)
def start_agentic_vision_viewer_run(
    request: StartAgenticVisionViewerRunRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, object]:
    """Create and queue a new segmentation run for live viewing."""
    recorder = AgenticVisionRunRecorder.create(
        root_dir=_get_runs_dir(),
        frame_uri=request.frame_uri,
        dataset_name=request.dataset_name,
        run_label=request.run_label,
        max_iters=request.max_iters,
        sam3_handler_name=request.sam3_handler_name,
    )
    background_tasks.add_task(_run_agentic_vision_viewer_job, request, recorder.run_id)
    return {"run_id": recorder.run_id, "status": recorder.metadata["status"]}


@router.get("/runs")
def get_agentic_vision_viewer_runs() -> dict[str, object]:
    """List recent viewer runs."""
    return {"runs": list_viewer_runs(_get_runs_dir())}


@router.get("/runs/{run_id}")
def get_agentic_vision_viewer_run(run_id: str) -> JsonObject:
    """Fetch run metadata for one viewer run."""
    return _get_run_or_404(run_id)


@router.get("/runs/{run_id}/events")
def get_agentic_vision_viewer_events(run_id: str, after_sequence: int = 0) -> dict[str, object]:
    """Return persisted events for one run."""
    _get_run_or_404(run_id)
    return {"events": load_viewer_events(_get_runs_dir(), run_id, after_sequence=after_sequence)}


@router.get("/runs/{run_id}/stream")
async def stream_agentic_vision_viewer_events(run_id: str, request: Request, after_sequence: int = 0) -> StreamingResponse:
    """Stream run events over Server-Sent Events."""
    _get_run_or_404(run_id)

    async def _event_stream() -> AsyncIterator[str]:
        last_sequence = after_sequence
        while True:
            if await request.is_disconnected():
                break

            events = load_viewer_events(_get_runs_dir(), run_id, after_sequence=last_sequence)
            for event in events:
                sequence_value = event.get("sequence", last_sequence)
                if isinstance(sequence_value, int):
                    last_sequence = sequence_value
                yield f"id: {last_sequence}\n"
                yield f"event: {event.get('event_type', 'message')}\n"
                yield f"data: {json.dumps(event)}\n\n"

            run = load_viewer_run(_get_runs_dir(), run_id)
            run_status = run.get("status")
            if run_status in {"completed", "failed"} and not events:
                terminal_payload = {"run_id": run_id, "status": run_status}
                yield "event: run_terminal\n"
                yield f"data: {json.dumps(terminal_payload)}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.get("/runs/{run_id}/artifacts/{artifact_id}")
def get_agentic_vision_viewer_artifact(run_id: str, artifact_id: str) -> FileResponse:
    """Serve one stored overlay artifact."""
    _get_run_or_404(run_id)
    try:
        artifact_path = get_viewer_artifact_path(_get_runs_dir(), run_id, artifact_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}") from exc
    return FileResponse(artifact_path)


def create_app() -> FastAPI:
    """Create the standalone viewer FastAPI app."""
    settings = get_settings()
    app = FastAPI(title="Agentic Vision Viewer API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Simple health check endpoint."""
        return {"status": "ok"}

    app.include_router(router)
    return app


app = create_app()


def run() -> None:
    """Run the standalone viewer API with uvicorn."""
    settings = get_settings()
    uvicorn.run("viewer_api.app:app", host=settings.api_host, port=settings.api_port, reload=False)


if __name__ == "__main__":
    run()
