from __future__ import annotations

from subscription_bridge.memory.codebase_indexer import CodebaseIndexer
from subscription_bridge.memory.retriever import Retriever
from subscription_bridge.tools.base import Tool, ToolResult


class CodebaseSearchTool(Tool):
    name = "codebase_search"
    description = (
        "Search the indexed codebase using semantic, keyword, and symbol search. "
        "Run 'bridge codebase index .' first to build the index."
    )
    input_schema = {"query": "string", "top_k": "int (optional, default 10)"}

    async def run(self, arguments: dict) -> ToolResult:
        query = str(arguments.get("query", ""))
        top_k = int(arguments.get("top_k", 10))
        workspace = str(arguments.get("workspace", "."))

        if not query:
            return ToolResult(name=self.name, success=False, error="query argument is required")

        indexer = CodebaseIndexer(workspace=workspace)
        index_data = indexer.load_existing()

        if index_data is None:
            return ToolResult(
                name=self.name,
                success=True,
                output=(
                    "No codebase index found. Run `bridge codebase index .` first. "
                    "Without an index, try using the grep tool for text search."
                ),
                metadata={"indexed": False, "query": query},
            )

        retriever = Retriever()
        results = retriever.retrieve(query, index_data, top_k=top_k)

        if not results:
            return ToolResult(
                name=self.name,
                success=True,
                output="No matching results found in the codebase index.",
                metadata={"indexed": True, "query": query, "results": 0},
            )

        lines: list[str] = [f"Found {len(results)} results for {query!r}:", ""]
        for i, r in enumerate(results, 1):
            loc = f"{r.file_path}:{r.start_line}-{r.end_line}" if r.start_line else r.file_path
            syms = f" [{', '.join(r.symbols[:5])}]" if r.symbols else ""
            lines.append(f"{i}. {loc} (score={r.score}, type={r.match_type}){syms}")
            preview = r.preview[:150].replace("\n", " ") if r.preview else ""
            if preview:
                lines.append(f"   {preview}")
            lines.append("")

        return ToolResult(
            name=self.name,
            success=True,
            output="\n".join(lines),
            metadata={"indexed": True, "query": query, "results": len(results)},
        )
