from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from subscription_bridge.memory.chunker import chunk_file, is_binary, skip_dir
from subscription_bridge.memory.embeddings import EmbeddingProvider, create_embedding_provider
from subscription_bridge.memory.models import IndexData, IndexMetadata
from subscription_bridge.memory.symbol_graph import extract_symbols_from_file
from subscription_bridge.memory.vector_store import VectorStore


class CodebaseIndexer:
    def __init__(
        self,
        workspace: str = ".",
        index_dir: str | Path | None = None,
        embedding_provider: str = "hash",
        max_lines: int = 160,
        overlap: int = 20,
    ) -> None:
        self._workspace = Path(workspace).expanduser().resolve()
        self._index_dir = (
            Path(index_dir).expanduser().resolve()
            if index_dir
            else self._workspace / ".subscription_bridge" / "index"
        )
        self._embedding_provider_name = embedding_provider
        self._embedding: EmbeddingProvider = create_embedding_provider(embedding_provider)
        self._max_lines = max_lines
        self._overlap = overlap
        self._store = VectorStore()

    def index(self) -> IndexData:
        files = self._collect_files()

        all_chunks: list[Any] = []
        all_symbols: list[Any] = []
        file_count = 0

        for file_path in files:
            chunks = chunk_file(
                file_path,
                self._workspace,
                max_lines=self._max_lines,
                overlap=self._overlap,
            )
            if chunks:
                all_chunks.extend(chunks)
                file_count += 1

            syms = extract_symbols_from_file(file_path)
            all_symbols.extend(syms)

        if all_chunks:
            texts = [c.text for c in all_chunks]
            embeddings = self._embedding.embed_texts(texts)
            self._store.add(all_chunks, embeddings)

        metadata = IndexMetadata(
            workspace_root=str(self._workspace),
            indexed_at=time.time(),
            file_count=file_count,
            chunk_count=len(all_chunks),
            embedding_provider=self._embedding_provider_name,
            embedding_dim=self._embedding.dim,
            version="1",
        )

        data = IndexData(
            metadata=metadata,
            chunks=all_chunks,
            embeddings=[],
            symbols=all_symbols,
        )

        self._save(data)
        return data

    def load_existing(self) -> IndexData | None:
        try:
            self._store.load(self._index_dir)
        except (FileNotFoundError, Exception):
            return None

        metadata_path = self._index_dir / "metadata.json"
        symbols_path = self._index_dir / "symbols.json"

        if not metadata_path.exists():
            return None

        import json
        meta_dict = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = IndexMetadata(**meta_dict)

        symbols: list[Any] = []
        if symbols_path.exists():
            symbols_data = json.loads(symbols_path.read_text(encoding="utf-8"))
            from subscription_bridge.memory.models import CodeSymbol
            symbols = [CodeSymbol(**s) for s in symbols_data]

        return IndexData(
            metadata=metadata,
            chunks=list(self._store._chunks),
            embeddings=[],
            symbols=symbols,
        )

    def _save(self, data: IndexData) -> None:
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._store.save(self._index_dir)

        import json

        meta_dict = {
            "workspace_root": data.metadata.workspace_root,
            "indexed_at": data.metadata.indexed_at,
            "file_count": data.metadata.file_count,
            "chunk_count": data.metadata.chunk_count,
            "embedding_provider": data.metadata.embedding_provider,
            "embedding_dim": data.metadata.embedding_dim,
            "version": data.metadata.version,
        }
        (self._index_dir / "metadata.json").write_text(
            json.dumps(meta_dict), encoding="utf-8"
        )

        syms_data = [
            {
                "name": s.name,
                "symbol_type": s.symbol_type,
                "file_path": s.file_path,
                "line": s.line,
                "parent": getattr(s, "parent", ""),
            }
            for s in data.symbols
        ]
        (self._index_dir / "symbols.json").write_text(
            json.dumps(syms_data), encoding="utf-8"
        )

    def _collect_files(self) -> list[Path]:
        files: list[Path] = []
        if not self._workspace.exists():
            return files

        for entry in self._workspace.rglob("*"):
            if entry.is_dir():
                if skip_dir(entry.name):
                    continue
                rel_str = str(entry.relative_to(self._workspace))
                skip_parts = {".git", "node_modules", "__pycache__", ".venv"}
                if any(p in rel_str.split("/") for p in skip_parts):
                    continue
            if entry.is_file() and not is_binary(entry):
                rel = entry.relative_to(self._workspace)
                parts = list(rel.parts)
                if any(skip_dir(p) for p in parts):
                    continue
                files.append(entry)

        return files

    @property
    def store(self) -> VectorStore:
        return self._store

    @property
    def index_dir(self) -> Path:
        return self._index_dir

    @property
    def workspace(self) -> Path:
        return self._workspace
