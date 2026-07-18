from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EmbeddedChunk:
    id: str
    vector: list[float]
    payload: dict[str, Any]