"""Frozen registry of record types with named roles, induced once from the engrim corpus."""

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT = Path(__file__).with_name("schema.json")


@dataclass(frozen=True)
class Role:
    name: str
    kind: str
    description: str


@dataclass(frozen=True)
class RecordType:
    name: str
    description: str
    roles: tuple[Role, ...]
    key: tuple[str, ...]
    value: str | None


@dataclass(frozen=True)
class Schema:
    types: dict[str, RecordType]

    @classmethod
    def load(cls, path: str | Path = DEFAULT) -> "Schema":
        raw = json.loads(Path(path).read_text())
        return cls(
            {
                t["name"]: RecordType(
                    t["name"],
                    t["description"],
                    tuple(
                        Role(r["name"], r["kind"], r["description"]) for r in t["roles"]
                    ),
                    tuple(t["key"]),
                    t.get("value"),
                )
                for t in raw["types"]
            }
        )

    def options(self) -> dict[str, str]:
        return {name: t.description for name, t in self.types.items()}
