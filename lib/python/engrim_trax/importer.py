"""Idempotent submit of Mappings and Edges through the trackinizer client SDK, with a persisted id map."""

import json
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from engrim_trax.classify import Mapping
from engrim_trax.edges import Edge
from engrim_trax.records import Record

NAMESPACE = uuid.UUID("3b0c2f4a-9c1e-4e4b-9a6d-0e5a7c2d1f03")


def record_key(record_id: int) -> uuid.UUID:
    """Deterministic idempotency key, so a re-run against the same server replays even without the id map."""
    return uuid.uuid5(NAMESPACE, f"engrim-trax:memory:{record_id}")


class TraxClient(Protocol):
    """The slice of `trackinizer.client.Client` the importer uses."""

    def submit(self, kind: Any, body: Any) -> uuid.UUID: ...
    def add_edge(self, from_id: uuid.UUID, to_id: uuid.UUID, edge_kind: str, *, actor: str, **kw: Any) -> Any: ...
    def log_metrics(self, experiment_id: uuid.UUID, points: Sequence[Any]) -> Any: ...


class IdMap:
    """`engrim_id -> inquiry uuid`, applied edges, logged metrics and session state, persisted as JSON."""

    def __init__(self, path: str | Path | None) -> None:
        self.path = Path(path) if path else None
        self.data: dict[str, Any] = {"records": {}, "edges": {}, "metrics": {}, "sessions": {}, "dropped_edges": 0}
        if self.path and self.path.exists():
            self.data.update(json.loads(self.path.read_text()))

    def save(self) -> None:
        if self.path:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=0, sort_keys=True))
            tmp.replace(self.path)

    def get(self, record_id: int) -> uuid.UUID | None:
        v = self.data["records"].get(str(record_id))
        return uuid.UUID(v) if v else None

    def put(self, record_id: int, inquiry_id: uuid.UUID) -> None:
        self.data["records"][str(record_id)] = str(inquiry_id)

    @staticmethod
    def edge_key(e: Edge) -> str:
        return f"{e.src}|{e.kind}|{e.dst}"

    @property
    def records(self) -> dict[str, str]:
        return self.data["records"]


def submit_body(m: Mapping, owner: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": m.title,
        "description": m.description,
        "owner": owner,
        "labels": m.labels,
        "status": m.status,
        "idempotency_key": str(record_key(m.record_id)),
    }
    body.update(m.fields)
    return body


class Importer:
    """Submits records oldest-first, then edges; everything already in the id map is skipped."""

    def __init__(self, client: TraxClient, idmap: IdMap, actor: str = "george", owner: str = "george") -> None:
        self.client = client
        self.idmap = idmap
        self.actor = actor
        self.owner = owner
        self.stats: dict[str, int] = {
            "submitted": 0,
            "skipped": 0,
            "edges_created": 0,
            "edges_existing": 0,
            "edges_skipped": 0,
            "edges_unresolved": 0,
            "edges_failed": 0,
            "metrics_logged": 0,
        }

    def submit_records(self, records: list[Record], mappings: dict[int, Mapping]) -> None:
        for r in records:
            m = mappings.get(r.id)
            if m is None:
                continue
            if self.idmap.get(r.id) is not None:
                self.stats["skipped"] += 1
                continue
            new_id = self.client.submit(m.kind, submit_body(m, self.owner))
            self.idmap.put(r.id, new_id)
            self.stats["submitted"] += 1
            if self.stats["submitted"] % 100 == 0:
                self.idmap.save()
        self.idmap.save()

    def submit_metrics(self, mappings: dict[int, Mapping]) -> None:
        from trackinizer.wire.wire_metrics import MetricPoint

        for m in mappings.values():
            if m.kind != "Experiment" or not m.metrics or str(m.record_id) in self.idmap.data["metrics"]:
                continue
            exp_id = self.idmap.get(m.record_id)
            if exp_id is None:
                continue
            points = [MetricPoint(key=k[:120], step=0, value=v) for k, v in m.metrics]
            self.client.log_metrics(exp_id, points)
            self.idmap.data["metrics"][str(m.record_id)] = len(points)
            self.stats["metrics_logged"] += len(points)
        self.idmap.save()

    def submit_edges(self, edges: list[Edge]) -> None:
        from trackinizer.client.errors import ClientError

        for e in edges:
            key = self.idmap.edge_key(e)
            if key in self.idmap.data["edges"]:
                self.stats["edges_skipped"] += 1
                continue
            src, dst = self.idmap.get(e.src), self.idmap.get(e.dst)
            if src is None or dst is None:
                self.stats["edges_unresolved"] += 1
                continue
            kw: dict[str, Any] = {"actor": self.actor, "note": e.note}
            if e.valence is not None:
                kw["valence"] = e.valence
            try:
                w = self.client.add_edge(src, dst, e.kind, **kw)
            except ClientError as err:
                self.stats["edges_failed"] += 1
                self.idmap.data["edges"][key] = f"failed: {str(err)[:120]}"
                continue
            self.stats["edges_created" if getattr(w, "created", True) else "edges_existing"] += 1
            self.idmap.data["edges"][key] = "ok"
        self.idmap.save()
