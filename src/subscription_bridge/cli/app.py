from __future__ import annotations

import asyncio
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from subscription_bridge import __app_name__, __version__
from subscription_bridge.browser import (
    PlaywrightLaunchError,
    PlaywrightManager,
    SelectorLoadError,
    SelectorRegistry,
    SessionPool,
)
from subscription_bridge.core import AgentRuntime, Task
from subscription_bridge.logging.logger import setup_logging
from subscription_bridge.memory.codebase_indexer import CodebaseIndexer
from subscription_bridge.memory.retriever import Retriever
from subscription_bridge.providers import FakeProviderAdapter, ProviderRegistry
from subscription_bridge.providers.base import ProviderRequest
from subscription_bridge.providers.gemini import GeminiProviderAdapter
from subscription_bridge.tools import (
    BashTool,
    CodebaseSearchTool,
    FileEditTool,
    FileReadTool,
    FileWriteTool,
    GitDiffTool,
    GlobTool,
    GrepTool,
    PatchTool,
    ToolRegistry,
)
from subscription_bridge.utils.config import load_config
from subscription_bridge.utils.paths import get_debug_dir

console = Console()
app = typer.Typer(
    name="bridge",
    help="SubscriptionBridge - Local agent runtime for browser-based LLMs",
    no_args_is_help=True,
)
provider_app = typer.Typer(help="Manage provider adapters")
session_app = typer.Typer(help="Manage browser sessions")
codebase_app = typer.Typer(help="Manage codebase indexing and search")
browser_app = typer.Typer(help="Browser diagnostics and management")
app.add_typer(provider_app, name="provider")
app.add_typer(session_app, name="session")
app.add_typer(codebase_app, name="codebase")
app.add_typer(browser_app, name="browser")

_registry: ProviderRegistry | None = None
_selector_registry: SelectorRegistry | None = None
_session_pool: SessionPool | None = None
_playwright_manager: PlaywrightManager | None = None


def _get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
        _registry.register(FakeProviderAdapter())
    return _registry


def _get_selector_registry() -> SelectorRegistry:
    global _selector_registry
    if _selector_registry is None:
        _selector_registry = SelectorRegistry()
    return _selector_registry


def _ensure_browser() -> PlaywrightManager:
    global _playwright_manager, _session_pool
    if _playwright_manager is None:
        config = load_config()
        browser_config = config.get("browser", {})
        _playwright_manager = PlaywrightManager(config)
        from subscription_bridge.utils.async_utils import run_async
        run_async(_playwright_manager.start())
        max_sessions = int(browser_config.get("max_sessions", 3))
        ttl = float(browser_config.get("session_ttl_seconds", 600))
        _session_pool = SessionPool(max_sessions=max_sessions, session_ttl_seconds=ttl)
    return _playwright_manager


def _get_session_pool() -> SessionPool:
    global _session_pool
    if _session_pool is None:
        config = load_config()
        browser_config = config.get("browser", {})
        max_sessions = int(browser_config.get("max_sessions", 3))
        ttl = float(browser_config.get("session_ttl_seconds", 600))
        _session_pool = SessionPool(max_sessions=max_sessions, session_ttl_seconds=ttl)
    return _session_pool


def _ensure_gemini_provider() -> GeminiProviderAdapter:
    registry = _get_registry()
    if "gemini" in registry:
        existing = registry.get("gemini")
        return existing  # type: ignore[return-value]

    pm = _ensure_browser()
    pool = _get_session_pool()

    async def _page_factory() -> Any:
        return await pm.create_page()

    adapter = GeminiProviderAdapter(
        session_pool=pool,
        page_factory=_page_factory,
    )
    registry.register(adapter)
    return adapter


def _ensure_chatgpt_provider() -> Any:
    from subscription_bridge.providers.chatgpt import ChatGPTProviderAdapter

    registry = _get_registry()
    if "chatgpt" in registry:
        existing = registry.get("chatgpt")
        return existing

    pm = _ensure_browser()
    pool = _get_session_pool()

    async def _page_factory() -> Any:
        return await pm.create_page()

    adapter = ChatGPTProviderAdapter(
        session_pool=pool,
        page_factory=_page_factory,
    )
    registry.register(adapter)
    return adapter


def _cleanup_global_browser() -> None:
    global _playwright_manager, _session_pool

    async def _cleanup() -> None:
        global _playwright_manager, _session_pool
        if _session_pool is not None:
            await _session_pool.close_all()
            _session_pool = None
        if _playwright_manager is not None:
            await _playwright_manager.stop()
            _playwright_manager = None

        from subscription_bridge.api.server import app
        deps = getattr(app.state, "deps", None)
        if deps is not None:
            await deps.shutdown()

    has_browser = _playwright_manager is not None or _session_pool is not None
    if has_browser:
        try:
            asyncio.run(_cleanup())
        except Exception:
            pass

    if not has_browser:
        from subscription_bridge.api.server import app
        if hasattr(app.state, "deps") and app.state.deps is not None:
            try:
                asyncio.run(_cleanup())
            except Exception:
                pass


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    log_format: str | None = typer.Option(
        None, "--log-format", help="Log format (json or console)"
    ),
) -> None:
    setup_logging(level="DEBUG" if verbose else None, fmt=log_format)


@app.command()
def version() -> None:
    console.print(f"[bold]{__app_name__}[/bold] version [green]{__version__}[/green]")


@app.command()
def ask(
    prompt: str = typer.Argument(..., help="The prompt to send"),
    provider: str = typer.Option(
        "fake", "--provider", "-p", help="Provider to use"
    ),
    system: str | None = typer.Option(
        None, "--system", "-s", help="System prompt"
    ),
    json_mode: bool = typer.Option(
        False, "--json", "-j", help="Request JSON response"
    ),
    files: list[str] = typer.Option(
        [], "--file", "-f", help="File to attach (repeatable)"
    ),
) -> None:
    config = load_config()
    default_provider = config.get("app", {}).get("default_provider", "fake")
    provider_name = provider or default_provider

    async def _do_ask() -> None:
        from subscription_bridge.providers.base import ProviderAdapter

        gemini_adapter: GeminiProviderAdapter | None = None
        chatgpt_adapter: Any | None = None
        generic_adapter: ProviderAdapter | None = None

        if provider_name == "gemini":
            try:
                gemini_adapter = _ensure_gemini_provider()
            except PlaywrightLaunchError as e:
                console.print(f"[red]Browser error:[/red] {e}")
                console.print("\n[bold]Manual Chrome launch command:[/bold]")
                _print_launch_command("http://127.0.0.1:9333")
                raise typer.Exit(code=1) from e
        elif provider_name == "chatgpt":
            try:
                chatgpt_adapter = _ensure_chatgpt_provider()
            except PlaywrightLaunchError as e:
                console.print(f"[red]Browser error:[/red] {e}")
                raise typer.Exit(code=1) from e
        else:
            registry = _get_registry()
            try:
                generic_adapter = registry.get(provider_name)
            except KeyError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(code=1) from e

        if files and provider_name not in ("gemini", "chatgpt"):
            console.print("[yellow]Note:[/yellow] --files are only processed by gemini/chatgpt providers. "
                          "They will be ignored.")

        if files and provider_name == "gemini":
            from pathlib import Path
            missing = [f for f in files if not Path(f).expanduser().exists()]
            if missing:
                console.print(f"[red]File(s) not found:[/red] {', '.join(missing)}")
                raise typer.Exit(code=1)

        request = ProviderRequest(
            run_id="cli-ask",
            prompt=prompt,
            system_prompt=system,
            require_json=json_mode,
            attachments=files if files else None,
        )

        console.print(f"[dim]Sending to provider:[/dim] [cyan]{provider_name}[/cyan]")
        if files:
            console.print(f"[dim]Attachments:[/dim] {len(files)} file(s)")

        if gemini_adapter is not None:
            response = await gemini_adapter.send_prompt(request)
        elif chatgpt_adapter is not None:
            response = await chatgpt_adapter.send_prompt(request)
        elif generic_adapter is not None:
            response = await generic_adapter.send_prompt(request)
        else:
            console.print("[red]No provider adapter available[/red]")
            raise typer.Exit(code=1)

        if response.success:
            console.print(Panel(response.text, title="Response", border_style="green"))
        else:
            if response.error:
                console.print(f"[red]Provider error:[/red] {response.error}")
            raise typer.Exit(code=1)

    asyncio.run(_do_ask())


@provider_app.command("list")
def provider_list() -> None:
    registry = _get_registry()
    providers = registry.list_providers()

    table = Table(title="Configured Providers")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Enabled", justify="center")
    table.add_column("Capabilities")
    table.add_column("Priority")

    for p in providers:
        enabled_str = "[green]✓[/green]" if p["enabled"] else "[red]✗[/red]"
        caps = ", ".join(p["capabilities"])
        table.add_row(p["name"], enabled_str, caps, str(p["priority"]))

    console.print(table)


@provider_app.command("health")
def provider_health(
    name: str = typer.Argument(..., help="Provider name to check")
) -> None:
    async def _do_health() -> None:
        from subscription_bridge.providers.base import ProviderAdapter

        console.print(f"[dim]Checking health of[/dim] [cyan]{name}[/cyan]...")

        if name == "gemini":
            try:
                gemini_adapter = _ensure_gemini_provider()
                health = await gemini_adapter.detailed_health()
                status = health.get("status", "unknown")
                detail = health.get("detail", "")
                checks = health.get("checks", {})

                if status == "ready":
                    console.print(f"[green]✓[/green] [bold]{name}[/bold] is ready")
                elif status == "needs_login":
                    console.print(f"[yellow]![/yellow] [bold]{name}[/bold] needs manual login: {detail}")
                elif status == "degraded":
                    console.print(f"[yellow]![/yellow] [bold]{name}[/bold] is degraded: {detail}")
                else:
                    console.print(f"[red]✗[/red] [bold]{name}[/bold] is {status}: {detail}")

                console.print(f"  Reachable: {checks.get('reachable', False)}")
                console.print(f"  App page: {checks.get('app_page', False)}")
                console.print(f"  Composer ready: {checks.get('composer_ready', False)}")
                console.print(f"  Temporary chat: {checks.get('temporary_chat', False)}")
            except PlaywrightLaunchError as e:
                console.print(f"[red]✗[/red] Browser error: {e}")
                raise typer.Exit(code=1) from e
            except Exception as e:
                console.print(f"[red]✗[/red] Health check error: {e}")
                raise typer.Exit(code=1) from e
        else:
            registry = _get_registry()
            try:
                generic_adapter: ProviderAdapter = registry.get(name)
            except KeyError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(code=1) from e
            ok = await generic_adapter.health_check()
            if ok:
                console.print(f"[green]✓[/green] [bold]{name}[/bold] is healthy")
            else:
                console.print(f"[red]✗[/red] [bold]{name}[/bold] is not healthy")
                raise typer.Exit(code=1)

    asyncio.run(_do_health())


@session_app.command("list")
def session_list() -> None:
    pool = _get_session_pool()
    sessions = pool.list_sessions()

    if not sessions:
        console.print("[dim]No active sessions[/dim]")
        return

    table = Table(title="Active Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Provider", style="green")
    table.add_column("State")
    table.add_column("Run ID", style="dim")
    table.add_column("Age (s)", justify="right")
    table.add_column("Idle (s)", justify="right")

    for s in sessions:
        age = f"{s['age_seconds']:.0f}"
        idle = f"{s['idle_seconds']:.0f}"
        run = s["current_run_id"] or "-"
        table.add_row(
            s["session_id"][:16],
            s["provider_name"],
            s["state"],
            run,
            age,
            idle,
        )
    console.print(table)


@session_app.command("reset")
def session_reset(
    session_id: str = typer.Argument(..., help="Session ID to reset"),
) -> None:
    pool = _get_session_pool()
    session = pool.get_session(session_id)
    if session is None:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise typer.Exit(code=1)

    async def _do_reset() -> None:
        console.print(f"[dim]Resetting session:[/dim] [cyan]{session_id}[/cyan]")
        await pool.reset(session_id)
        console.print(f"[green]✓[/green] Session [bold]{session_id[:16]}[/bold] reset")

    asyncio.run(_do_reset())


def _get_agent_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(FileEditTool())
    registry.register(GrepTool())
    registry.register(BashTool())
    registry.register(GitDiffTool())
    registry.register(PatchTool())
    registry.register(GlobTool())
    registry.register(CodebaseSearchTool())
    return registry


async def _ensure_browser_async() -> PlaywrightManager:
    global _playwright_manager, _session_pool
    if _playwright_manager is None:
        config = load_config()
        browser_config = config.get("browser", {})
        _playwright_manager = PlaywrightManager(config)
        await _playwright_manager.start()
        max_sessions = int(browser_config.get("max_sessions", 3))
        ttl = float(browser_config.get("session_ttl_seconds", 600))
        _session_pool = SessionPool(max_sessions=max_sessions, session_ttl_seconds=ttl)
    return _playwright_manager


async def _ensure_gemini_provider_async() -> GeminiProviderAdapter:
    from typing import cast as _cast
    registry = _get_registry()
    if "gemini" in registry:
        existing = _cast(GeminiProviderAdapter, registry.get("gemini"))
        return existing

    pm = await _ensure_browser_async()
    pool = _get_session_pool()

    async def _page_factory() -> Any:
        return await pm.create_page()

    adapter = GeminiProviderAdapter(
        session_pool=pool,
        page_factory=_page_factory,
    )
    registry.register(adapter)
    return adapter


@app.command("run")
def run_task(
    task: str = typer.Argument(..., help="Task description for the agent"),
    provider: str = typer.Option("fake", "--provider", "-p", help="Provider to use"),
    repo_path: str = typer.Option(".", "--repo", "-r", help="Repository path"),
    max_steps: int = typer.Option(10, "--max-steps", "-m", help="Maximum agent steps"),
    workspace: str = typer.Option(".", "--workspace", "-w", help="Working directory"),
) -> None:
    console.print(
        Panel(
            f"[bold]Task:[/bold] {task}\n"
            f"[bold]Provider:[/bold] {provider}\n"
            f"[bold]Workspace:[/bold] {workspace}\n"
            f"[bold]Max Steps:[/bold] {max_steps}",
            title="Agent Run",
            border_style="blue",
        )
    )

    tool_registry = _get_agent_registry()

    async def _do_run() -> None:
        from subscription_bridge.providers.base import ProviderAdapter as _ProviderAdapter

        provider_adapter: _ProviderAdapter
        if provider == "fake":
            provider_adapter = FakeProviderAdapter(scripted_responses=[
                '{"type":"tool_call","thought":"Need to read README",'
                '"tool_name":"file_read","arguments":{"path":"README.md"}}',
                '{"type":"final","thought":"Read README successfully",'
                '"answer":"README.md contains project documentation about SubscriptionBridge."}',
            ])
        elif provider == "gemini":
            try:
                provider_adapter = await _ensure_gemini_provider_async()
            except PlaywrightLaunchError as e:
                console.print(f"[red]Browser error:[/red] {e}")
                return
        elif provider == "chatgpt":
            try:
                provider_adapter = _ensure_chatgpt_provider()
            except PlaywrightLaunchError as e:
                console.print(f"[red]Browser error:[/red] {e}")
                return
        else:
            reg = _get_registry()
            try:
                provider_adapter = reg.get(provider)
            except KeyError as e:
                console.print(f"[red]Error:[/red] {e}")
                return

        runtime = AgentRuntime(provider=provider_adapter, tool_registry=tool_registry, max_steps=max_steps)
        console.print("[dim]Starting agent run...[/dim]")
        agent_task = Task(text=task, workspace=workspace, provider=provider, max_steps=max_steps)
        result = await runtime.run(agent_task)

        if result.success:
            console.print(f"\n[green]✓[/green] Run completed in {result.total_elapsed:.1f}s")
            console.print(Panel(result.answer, title="Answer", border_style="green"))
        elif result.needs_clarification:
            console.print(f"\n[yellow]?[/yellow] Clarification needed: {result.question}")
        else:
            console.print(f"\n[red]✗[/red] Run failed: {result.error}")

        console.print(f"[dim]Steps: {result.steps}/{result.max_steps} | "
                      f"Run ID: {result.run_id}[/dim]")

    asyncio.run(_do_run())


@app.command("server")
def start_server(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind address"),
    port: int = typer.Option(8787, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes"),
    log_level: str = typer.Option("info", "--log-level", help="Log level"),
    provider: str = typer.Option(
        None, "--provider", "-P",
        help="Provider to initialize: gemini, chatgpt, or both (prompts if not set)",
    ),
) -> None:
    import uvicorn

    chosen = provider
    if chosen is None:
        console.print()
        console.print("[bold]Which provider do you want to use?[/bold]")
        console.print("  [cyan]1[/cyan]  Gemini  (gemini.google.com)")
        console.print("  [cyan]2[/cyan]  ChatGPT (chatgpt.com)")
        console.print("  [cyan]3[/cyan]  Both")
        console.print()
        choice = input("Enter 1, 2, or 3 [default: 1]: ").strip() or "1"
        if choice == "2":
            chosen = "chatgpt"
        elif choice == "3":
            chosen = "both"
        else:
            chosen = "gemini"
        console.print()

    providers_to_init = []
    if chosen == "both":
        providers_to_init = ["gemini", "chatgpt"]
    elif chosen in ("gemini", "chatgpt"):
        providers_to_init = [chosen]
    else:
        console.print(f"[red]Unknown provider:[/red] {chosen}")
        raise typer.Exit(code=1)

    console.print(f"[dim]Initializing provider(s):[/dim] [cyan]{', '.join(providers_to_init)}[/cyan]")
    for pname in providers_to_init:
        if pname == "gemini":
            try:
                _ensure_gemini_provider()
                console.print("  [green]✓[/green] Gemini ready")
            except PlaywrightLaunchError as e:
                console.print(f"  [red]✗[/red] Gemini: {e}")
                _print_launch_command("http://127.0.0.1:9333")
        elif pname == "chatgpt":
            try:
                _ensure_chatgpt_provider()
                console.print("  [green]✓[/green] ChatGPT ready")
            except PlaywrightLaunchError as e:
                console.print(f"  [red]✗[/red] ChatGPT: {e}")

    console.print()
    console.print(f"[dim]API server starting on[/dim] [cyan]{host}:{port}[/cyan]")
    console.print(f"[dim]Docs:[/dim] [cyan]http://{host}:{port}/docs[/cyan]")
    console.print()

    try:
        uvicorn.run(
            "subscription_bridge.api.server:app",
            host=host,
            port=port,
            reload=reload,
            log_level=log_level,
        )
    finally:
        _cleanup_global_browser()


@app.command("stop")
def stop_server(
    port: int = typer.Option(8787, "--port", "-p", help="Port to find server on"),
) -> None:
    import os
    import signal
    import subprocess
    import time as _time

    console.print(f"[dim]Looking for bridge server on port {port}...[/dim]")

    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pids = []

    if not pids:
        console.print(f"[yellow]No server found on port {port}[/yellow]")
        return

    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGINT)
            console.print(f"[dim]Sent SIGINT to PID {pid} for graceful shutdown[/dim]")
        except (ProcessLookupError, PermissionError) as e:
            console.print(f"[red]Could not signal PID {pid}: {e}[/red]")

    _time.sleep(2.0)

    for pid in pids:
        try:
            os.kill(int(pid), 0)
            os.kill(int(pid), signal.SIGKILL)
            console.print(f"[yellow]Force-killed PID {pid}[/yellow]")
        except (ProcessLookupError, PermissionError):
            pass

    console.print(f"[green]Stopped server on port {port}[/green]")


@codebase_app.command("index")
def codebase_index(
    path: str = typer.Argument(".", help="Repository path to index"),
) -> None:
    import time as _time

    start = _time.monotonic()
    console.print(f"[dim]Indexing codebase at:[/dim] [cyan]{path}[/cyan]")

    indexer = CodebaseIndexer(workspace=path)
    data = indexer.index()
    elapsed = _time.monotonic() - start

    summary = data.summary()
    table = Table(title="Index Complete")
    table.add_column("Metric", style="cyan")
    table.add_column("Value")
    table.add_row("Workspace", summary["workspace_root"])
    table.add_row("Files indexed", str(summary["file_count"]))
    table.add_row("Chunks created", str(summary["chunk_count"]))
    table.add_row("Symbols extracted", str(summary["symbol_count"]))
    table.add_row("Embedding provider", summary["embedding_provider"])
    table.add_row("Duration", f"{elapsed:.1f}s")
    console.print(table)
    console.print(f"[dim]Index saved to:[/dim] {indexer.index_dir}")


@codebase_app.command("search")
def codebase_search(
    query: str = typer.Argument(..., help="Search query"),
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace directory"),
    top_k: int = typer.Option(10, "--top-k", "-k", help="Number of results"),
) -> None:
    console.print(f"[dim]Searching for:[/dim] [cyan]{query}[/cyan]")

    indexer = CodebaseIndexer(workspace=workspace)
    index_data = indexer.load_existing()

    if index_data is None:
        console.print("[yellow]No codebase index found. Run 'bridge codebase index .' first.[/yellow]")
        return

    retriever = Retriever()
    results = retriever.retrieve(query, index_data, top_k=top_k)

    if not results:
        console.print("[dim]No matching results found.[/dim]")
        return

    table = Table(title=f"Search Results for {query!r}")
    table.add_column("#", justify="right", style="dim")
    table.add_column("File", style="cyan")
    table.add_column("Lines", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Type")
    table.add_column("Symbols", style="green")

    for i, r in enumerate(results, 1):
        loc = f"{r.start_line}-{r.end_line}" if r.start_line else "-"
        syms = ", ".join(r.symbols[:3]) if r.symbols else "-"
        table.add_row(str(i), r.file_path, loc, str(r.score), r.match_type, syms)

    console.print(table)

    if results:
        console.print("\n[dim]Top result preview:[/dim]")
        top = results[0]
        preview = top.preview[:200] if top.preview else ""
        if preview:
            console.print(f"  {preview}")


@codebase_app.command("stats")
def codebase_stats(
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace directory"),
) -> None:
    indexer = CodebaseIndexer(workspace=workspace)
    index_data = indexer.load_existing()

    if index_data is None:
        console.print("[yellow]No codebase index found. Run 'bridge codebase index .' first.[/yellow]")
        return

    summary = index_data.summary()
    table = Table(title="Codebase Index Stats")
    table.add_column("Metric", style="cyan")
    table.add_column("Value")
    table.add_row("Workspace", summary["workspace_root"])
    table.add_row("Indexed at", _fmt_time(summary["indexed_at"]))
    table.add_row("Files indexed", str(summary["file_count"]))
    table.add_row("Chunks", str(summary["chunk_count"]))
    table.add_row("Symbols", str(summary["symbol_count"]))
    table.add_row("Embedding provider", summary["embedding_provider"])
    table.add_row("Embedding dimension", str(summary["embedding_dim"]))
    console.print(table)
    console.print(f"[dim]Index location: {indexer.index_dir}[/dim]")


def _fmt_time(t: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")


@browser_app.command("doctor")
def browser_doctor() -> None:
    config = load_config()
    browser_config = config.get("browser", {})
    mode = str(browser_config.get("mode", "managed"))
    cdp_url = str(browser_config.get("cdp_url", "http://127.0.0.1:9333"))

    console.print(Panel("Browser Environment Check", border_style="blue"))
    ok = True

    # Check config loads
    console.print(f"  [bold]Browser mode:[/bold] {mode}")
    console.print(f"  [bold]CDP URL:[/bold] {cdp_url if mode == 'cdp' else '(managed mode)'}")

    # Check debug dir
    debug_dir = get_debug_dir()
    console.print(f"  [bold]Debug dir:[/bold] {debug_dir}")
    if debug_dir.exists():
        console.print("    [green]✓[/green] exists and writable")
    else:
        console.print("    [red]✗[/red] does not exist")
        ok = False

    # Check selector YAMLs
    registry = _get_selector_registry()
    providers_to_check = ["gemini", "chatgpt", "claude"]
    for pname in providers_to_check:
        try:
            data = registry.load(pname)
            console.print(f"  [bold]Selectors ({pname}):[/bold] loaded ({len(data.get('selectors', {}))} keys)")
        except SelectorLoadError as e:
            console.print(f"    [red]✗[/red] {e}")
            ok = False

    # Validate selector shapes
    for pname in providers_to_check:
        try:
            data = registry.load(pname)
            issues = SelectorRegistry.validate_config_shape(data)
            if issues:
                for key, msgs in issues.items():
                    for msg in msgs:
                        console.print(f"    [yellow]⚠[/yellow] {msg}")
        except Exception:
            pass

    if mode == "cdp":
        console.print(f"\n  [bold]CDP connectivity:[/bold] testing {cdp_url}")
        try:
            PlaywrightManager._verify_cdp_reachable(cdp_url)
            console.print("    [green]✓[/green] port is reachable")
        except PlaywrightLaunchError as e:
            console.print(f"    [red]✗[/red] {e}")
            ok = False
            console.print("\n  [bold]Manual launch command:[/bold]")
            _print_launch_command(cdp_url)

    # Check max_sessions
    max_sessions = int(browser_config.get("max_sessions", 3))
    console.print(f"  [bold]Max sessions:[/bold] {max_sessions}")

    # Check download timeout
    dl_timeout = int(browser_config.get("download_timeout_seconds", 180))
    console.print(f"  [bold]Download timeout:[/bold] {dl_timeout}s")

    if ok:
        console.print("\n[green bold]✓[/green bold] Browser environment looks good")
    else:
        console.print("\n[red bold]✗[/red bold] Some checks failed. Fix the issues above.")
        raise typer.Exit(code=1)


def _print_launch_command(cdp_url: str) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(cdp_url)
    port = parsed.port or 9333
    profile = "~/.subscription-bridge/chrome-profile"

    commands = {
        "Linux (Google Chrome)": (
            f"google-chrome \\\n"
            f"  --remote-debugging-port={port} \\\n"
            f"  --user-data-dir=\"{profile}\" \\\n"
            f"  --no-first-run \\\n"
            f"  --no-default-browser-check"
        ),
        "Linux (Chromium)": (
            f"chromium \\\n"
            f"  --remote-debugging-port={port} \\\n"
            f"  --user-data-dir=\"{profile}\" \\\n"
            f"  --no-first-run \\\n"
            f"  --no-default-browser-check"
        ),
        "macOS": (
            f"/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\\n"
            f"  --remote-debugging-port={port} \\\n"
            f"  --user-data-dir=\"{profile}\" \\\n"
            f"  --no-first-run \\\n"
            f"  --no-default-browser-check"
        ),
        "Windows PowerShell": (
            f'& "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" `\n'
            f"  --remote-debugging-port={port} `\n"
            f'  --user-data-dir="$env:USERPROFILE\\.subscription-bridge\\chrome-profile" `\n'
            f"  --no-first-run `\n"
            f"  --no-default-browser-check"
        ),
    }

    for os_name, cmd in commands.items():
        console.print(f"  [bold]{os_name}:[/bold]")
        console.print(f"    [dim]{cmd}[/dim]")
        console.print("")
