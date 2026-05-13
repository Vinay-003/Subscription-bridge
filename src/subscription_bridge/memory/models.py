from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentChunk:
    file_path: str
    language: str = ""
    start_line: int = 0
    end_line: int = 0
    text: str = ""
    chunk_id: str = ""
    symbols: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    file_hash: str = ""


@dataclass
class CodeSymbol:
    name: str
    symbol_type: str = ""
    file_path: str = ""
    line: int = 0
    parent: str = ""


@dataclass
class IndexMetadata:
    workspace_root: str = ""
    indexed_at: float = 0.0
    file_count: int = 0
    chunk_count: int = 0
    embedding_provider: str = "hash"
    embedding_dim: int = 384
    version: str = "1"


@dataclass
class SearchResult:
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    score: float = 0.0
    match_type: str = ""
    preview: str = ""
    symbols: list[str] = field(default_factory=list)
    chunk_id: str = ""


@dataclass
class IndexData:
    metadata: IndexMetadata = field(default_factory=IndexMetadata)
    chunks: list[DocumentChunk] = field(default_factory=list)
    embeddings: list[list[float]] = field(default_factory=list)
    symbols: list[CodeSymbol] = field(default_factory=list)
    documents: dict[str, list[int]] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "workspace_root": self.metadata.workspace_root,
            "indexed_at": self.metadata.indexed_at,
            "file_count": self.metadata.file_count,
            "chunk_count": self.metadata.chunk_count,
            "symbol_count": len(self.symbols),
            "embedding_provider": self.metadata.embedding_provider,
            "embedding_dim": self.metadata.embedding_dim,
        }
