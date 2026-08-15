"""Shared data models for SecondSelf."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CaptureType = Literal["note", "link", "file"]
CaptureSource = Literal["cli", "stdin", "path"]
ParaCategory = Literal["Projects", "Areas", "Resources", "Archives"]

PARA_CATEGORIES: tuple[str, ...] = ("Projects", "Areas", "Resources", "Archives")


@dataclass
class CaptureMeta:
    id: str
    timestamp: str
    type: CaptureType
    source: CaptureSource
    original_filename: str | None = None
    content_hash: str | None = None

    @property
    def folder_id(self) -> str:
        """Full capture folder name: {date}_{id}."""
        date_part = self.timestamp[:10]
        return f"{date_part}_{self.id}"


@dataclass
class CaptureResult:
    id: str
    path: str
    type: CaptureType


@dataclass
class RawCapture:
    """A raw capture item loaded from disk."""

    folder_id: str
    meta: CaptureMeta
    path: str
    content_path: str | None = None


@dataclass
class WikiNote:
    id: str
    raw_id: str
    para: ParaCategory
    tags: list[str]
    summary: str
    created: str
    links: list[str]
    body: str
    path: str = ""


@dataclass
class GraphNode:
    id: str
    label: str
    para: str
    tags: list[str]
    summary: str
    content_preview: str
    group: str


@dataclass
class GraphEdge:
    source: str
    target: str
    weight: float = 1.0
    type: str = "semantic"


@dataclass
class AskSource:
    id: str
    summary: str
    relevance_score: float
    para: str


@dataclass
class AskResult:
    answer: str
    sources: list[AskSource] = field(default_factory=list)


@dataclass
class IndexState:
    raw_processed: dict[str, dict] = field(default_factory=dict)
    embeddings_version: str = "all-MiniLM-L6-v2"
    last_graph_build: str | None = None
    wiki_embeddings: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "raw_processed": self.raw_processed,
            "embeddings_version": self.embeddings_version,
            "last_graph_build": self.last_graph_build,
            "wiki_embeddings": self.wiki_embeddings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> IndexState:
        return cls(
            raw_processed=data.get("raw_processed", {}),
            embeddings_version=data.get("embeddings_version", "all-MiniLM-L6-v2"),
            last_graph_build=data.get("last_graph_build"),
            wiki_embeddings=data.get("wiki_embeddings", {}),
        )
