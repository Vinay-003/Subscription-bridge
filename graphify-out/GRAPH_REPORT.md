# Graph Report - subscription-bridge  (2026-05-31)

## Corpus Check
- 136 files · ~56,434 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1706 nodes · 2869 edges · 95 communities (76 shown, 19 thin omitted)
- Extraction: 74% EXTRACTED · 25% INFERRED · 0% AMBIGUOUS · INFERRED: 707 edges (avg confidence: 0.74)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `107d9d27`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 94|Community 94]]

## God Nodes (most connected - your core abstractions)
1. `parse_agent_action()` - 40 edges
2. `SessionPool` - 40 edges
3. `GeminiProviderAdapter` - 36 edges
4. `AgentState` - 32 edges
5. `chat_completions()` - 31 edges
6. `CodebaseIndexer` - 30 edges
7. `FakeProviderAdapter` - 28 edges
8. `run()` - 24 edges
9. `ToolResult` - 23 edges
10. `validate_attachment_path()` - 22 edges

## Surprising Connections (you probably didn't know these)
- `fake_provider()` --calls--> `FakeProviderAdapter`  [INFERRED]
  tests/unit/test_fake_provider.py → src/subscription_bridge/providers/fake.py
- `test_registry_provider_works_through_registry()` --calls--> `ProviderRequest`  [INFERRED]
  tests/unit/test_registry.py → src/subscription_bridge/providers/base.py
- `pool()` --calls--> `SessionPool`  [INFERRED]
  tests/unit/test_session_pool.py → src/subscription_bridge/browser/session_pool.py
- `test_wait_for_uploads_settles_timeout()` --calls--> `wait_for_uploads_to_settle()`  [INFERRED]
  tests/unit/test_gemini_upload.py → geminiautomation.py
- `test_fake_provider_send_prompt()` --calls--> `ProviderRequest`  [INFERRED]
  tests/unit/test_fake_provider.py → src/subscription_bridge/providers/base.py

## Communities (95 total, 19 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (79): AskRequest, AskResponse, CodebaseIndexRequest, CodebaseIndexResponse, CodebaseSearchRequest, CodebaseSearchResponse, CodebaseStatsResponse, ErrorResponse (+71 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (62): ParserError, AttachmentInfo, classify_attachment(), _classify_extension(), detect_extension(), load_upload_config(), UploadConfig, validate_attachment_path() (+54 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (41): AgentRuntime, _auto_read_files(), _find_file_refs(), AgentState, AgentStatus, Observation, StepRecord, AgentMode (+33 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (67): _build_candidates(), _normalize_arguments(), parse_agent_action(), _parse_clarification(), _parse_final(), _parse_tool_call(), _plain_text_fallback(), _regex_extract_action() (+59 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (48): chunk_file(), detect_language(), extract_imports(), extract_symbols(), is_binary(), skip_dir(), CodebaseIndexer, CodeSymbol (+40 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (31): create_embedding_provider(), EmbeddingProvider, HashEmbeddingProvider, SentenceTransformerEmbeddingProvider, DocumentChunk, SearchResult, Retriever, _cosine_similarity() (+23 more)

### Community 6 - "Community 6"
Cohesion: 0.05
Nodes (17): BrowserContextManager, ContextManagerError, DownloadError, DownloadManager, _sleep(), LoginTimeoutError, _sleep(), wait_for_login() (+9 more)

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (26): check_composer_visible(), check_gemini_reachable(), check_gemini_ready(), check_login_indicator(), check_temporary_chat(), navigate_to_fresh_chat(), navigate_to_gemini(), _sleep() (+18 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (24): ProviderRegistry, test_get_env_actual(), test_get_env_default(), test_load_providers_config(), test_load_selector_config_chatgpt(), test_load_selector_config_gemini(), test_load_selector_config_not_found(), test_load_tool_permissions() (+16 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (31): _get_workspace_from_pwd(), ToolExecutor, _workspace_from_opencode_active_session(), test_bash_runs_in_configured_workspace(), test_executor_default_workspace_is_cwd(), test_executor_normalizes_workspace(), test_executor_path_traversal_still_blocked(), test_executor_uses_configured_workspace() (+23 more)

### Community 10 - "Community 10"
Cohesion: 0.05
Nodes (5): SelectorLoadError, SelectorRegistry, _validate(), registry(), registry()

### Community 11 - "Community 11"
Cohesion: 0.06
Nodes (42): Agent Runtime Layer, Browser Runtime Layer, CLI/API Layer, Context Builder Layer, JSON Parser, PlaywrightManager, ProviderAdapter, Provider Layer (+34 more)

### Community 12 - "Community 12"
Cohesion: 0.08
Nodes (32): browser_doctor(), codebase_index(), codebase_search(), codebase_stats(), _ensure_browser(), _ensure_browser_async(), _ensure_gemini_provider(), _ensure_gemini_provider_async() (+24 more)

### Community 13 - "Community 13"
Cohesion: 0.05
Nodes (39): code:bash (bridge server --host 127.0.0.1 --port 8787), code:bash (curl -X POST http://127.0.0.1:8787/run \), code:json ({), code:json ({), code:json ({), code:json ({), code:json ({), code:json ({) (+31 more)

### Community 14 - "Community 14"
Cohesion: 0.09
Nodes (36): assert_not_temporary_chat(), _attachment_spinner_count(), build_browser_context(), build_local_image_paths(), collect_upload_images_from_dir(), discover_prompt_jobs(), download_to_temp(), _format_sort_key() (+28 more)

### Community 15 - "Community 15"
Cohesion: 0.06
Nodes (35): Architecture, CDP Mode (only way that works), CLI Commands, code:mermaid (flowchart TB), code:bash (curl http://127.0.0.1:8787/health), code:bash (# Install), code:bash (google-chrome \), code:bash (chmod +x ~/start-bridge.sh) (+27 more)

### Community 16 - "Community 16"
Cohesion: 0.11
Nodes (22): clear_composer(), compact_prompt_compare(), find_composer(), focus_composer(), format_integrity(), get_composer_text(), normalize_prompt_compare(), paste_via_clipboard() (+14 more)

### Community 17 - "Community 17"
Cohesion: 0.1
Nodes (23): main(), _get_log_format(), _get_log_level(), get_logger(), setup_logging(), StructuredLogger, test_browser_config_default_cdp_url(), test_browser_config_default_mode() (+15 more)

### Community 18 - "Community 18"
Cohesion: 0.08
Nodes (33): FastAPI Server, Browser Runtime, FakeProvider, Gemini Uploads Config, Logging Configuration, Memory System, SubscriptionBridge, Design Assessment Task (+25 more)

### Community 19 - "Community 19"
Cohesion: 0.09
Nodes (10): AppDependencies, create_app(), PlaywrightLaunchError, PlaywrightManager, _verify_cdp_reachable(), check_provider_health(), test_playwright_manager_cdp_not_reachable(), test_playwright_manager_create_page_before_start() (+2 more)

### Community 20 - "Community 20"
Cohesion: 0.14
Nodes (13): ABC, _get_agent_registry(), PathTraversalError, Tool, Tool, ToolCall, ToolResult, FileEditTool (+5 more)

### Community 21 - "Community 21"
Cohesion: 0.08
Nodes (4): gemini_page_factory(), GeminiLocator, GeminiPageWithFiles, test_adapter_without_attachments_still_works()

### Community 22 - "Community 22"
Cohesion: 0.12
Nodes (22): BashTool, FileReadTool, FileWriteTool, registry(), test_bash_dangerous_command_rm_rf(), test_bash_dangerous_command_sudo(), test_bash_empty_command(), test_bash_success() (+14 more)

### Community 23 - "Community 23"
Cohesion: 0.15
Nodes (26): clear_composer_keyboard(), click_send_and_confirm(), _compact_prompt_compare(), find_composer(), focus_composer(), format_prompt_integrity(), generation_in_progress(), get_composer_text() (+18 more)

### Community 24 - "Community 24"
Cohesion: 0.12
Nodes (23): _capture_download_from_click(), _click_download_control_js(), click_exact_image_and_download(), _configure_download_dir(), _default_chrome_download_dirs(), _download_control_available(), download_generated_image(), infer_ext_from_src() (+15 more)

### Community 25 - "Community 25"
Cohesion: 0.12
Nodes (13): _clean_assistant_text(), _composer_is_empty(), extract_latest_assistant_text(), generation_in_progress(), _sleep(), submission_activity_report(), wait_for_response_complete(), wait_for_send_confirmation() (+5 more)

### Community 26 - "Community 26"
Cohesion: 0.12
Nodes (13): _extract_model_variant(), ProviderRequest, fake_provider(), test_scripted_resets(), test_scripted_responses_in_order(), test_scripted_responses_repeat_last(), test_fake_provider_failure_rate(), test_fake_provider_json_response() (+5 more)

### Community 27 - "Community 27"
Cohesion: 0.18
Nodes (15): test_retry_async_eventual_success(), test_retry_async_exhausted(), test_retry_async_helper(), test_retry_async_success(), test_retry_base_exception_passthrough(), test_retry_config_custom(), test_retry_config_defaults(), test_retry_custom_exception_types() (+7 more)

### Community 28 - "Community 28"
Cohesion: 0.16
Nodes (14): collect_button_diagnostics(), _async_sleep(), _click_send_button(), _detect_model_label(), GeminiError, _normalize_variant(), _switch_model_variant(), _variant_aliases() (+6 more)

### Community 29 - "Community 29"
Cohesion: 0.1
Nodes (19): author, dependencies, autoprefixer, framer-motion, lucide-react, next, postcss, react (+11 more)

### Community 31 - "Community 31"
Cohesion: 0.2
Nodes (17): test_config_dir(), test_ensure_dir_creates(), test_ensure_dir_existing(), test_expand_user_path(), test_expand_user_path_relative(), test_get_config_path_found(), test_get_config_path_not_found(), test_project_root() (+9 more)

### Community 32 - "Community 32"
Cohesion: 0.11
Nodes (17): CDP Mode (Recommended for Development), code:yaml (browser:), code:bash (export BRIDGE_CHROME_PATH=/usr/bin/google-chrome), code:block3 (http://127.0.0.1:9333), code:bash (google-chrome \), code:bash (chromium \), code:bash (/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chro), code:powershell (& "C:\Program Files\Google\Chrome\Application\chrome.exe" `) (+9 more)

### Community 33 - "Community 33"
Cohesion: 0.11
Nodes (17): App section, Browser section, code:yaml (app:), code:yaml (browser:), code:yaml (memory:), code:yaml (gemini:), code:yaml (providers:), code:yaml (bash:) (+9 more)

### Community 38 - "Community 38"
Cohesion: 0.17
Nodes (8): GeminiProviderAdapter, CompleteGeminiPage, gemini_page_factory(), test_adapter_create_session(), test_adapter_creation(), test_adapter_health_check(), test_adapter_reset_chat(), test_adapter_session_lifecycle()

### Community 39 - "Community 39"
Cohesion: 0.2
Nodes (6): AgentError, DangerousCommandError, MaxStepsExceededError, ProviderResponseError, ToolExecutionError, ToolNotFoundError

### Community 40 - "Community 40"
Cohesion: 0.15
Nodes (15): _active_window_title(), click_attach_button_near_composer(), _click_attach_menu_button_only(), _click_upload_files_menu_item(), _native_dialog_choose_file(), _native_file_dialog_active(), _open_upload_file_chooser(), Click the visible attachment/add-files control closest to the composer. (+7 more)

### Community 41 - "Community 41"
Cohesion: 0.13
Nodes (14): A. Setup, B. Fake Provider Demo, C. Codebase Memory Demo, code:bash (# 1. Create and activate virtual environment), code:bash (# List configured providers), code:bash (# Index the workspace (117 files, ~158 chunks, ~6s)), code:bash (# 1. Start Chrome with remote debugging on port 9333), code:bash (# Summarize a text file) (+6 more)

### Community 44 - "Community 44"
Cohesion: 0.14
Nodes (13): code:json ({), code:json ({), code:bash (# 1. Start the SubscriptionBridge server), code:json ({), Compaction Config, Known Limitations, Model Reference, OpenCode Configuration (+5 more)

### Community 47 - "Community 47"
Cohesion: 0.22
Nodes (7): default_unsafe_words(), dismiss_overlays(), make_bad_words_check(), safe_click_labels(), _sleep(), test_default_unsafe_words(), test_make_bad_words_check_script()

### Community 49 - "Community 49"
Cohesion: 0.27
Nodes (7): CodebaseSearchTool, test_empty_query(), test_no_index_returns_helpful_message(), test_with_index_no_matches(), test_with_index_returns_results(), test_codebase_search_empty_query(), test_codebase_search_no_index()

### Community 50 - "Community 50"
Cohesion: 0.22
Nodes (9): _describe_input_attrs(), _dispatch_file_input_events_via_cdp(), _find_file_input_across_frames(), _find_file_input_anywhere(), open_attachment_ui(), Find an existing file input. Hidden inputs are OK for set_input_files()., Open the + / attachment menu only.      Important: do NOT click the "Upload file, Assign files to an existing Gemini file input through CDP.      Gemini usually c (+1 more)

### Community 52 - "Community 52"
Cohesion: 0.22
Nodes (8): Architecture (6 Layers), Code Quality, code:bash (# Install), Commands, Implementation Phases, Key Patterns, Project Overview, SubscriptionBridge - Coding Agent Guide

### Community 53 - "Community 53"
Cohesion: 0.32
Nodes (8): create_image_tool_selected(), dismiss_open_overlays(), pro_model_selected(), _safe_click_js(), safe_click_labels(), select_create_image_tool(), select_model_and_tool_if_requested(), select_pro_model()

### Community 55 - "Community 55"
Cohesion: 0.25
Nodes (3): FakePage, _page_factory(), test_close_session()

### Community 58 - "Community 58"
Cohesion: 0.25
Nodes (7): architecture, flow, layers, project, providers, status, version

### Community 59 - "Community 59"
Cohesion: 0.33
Nodes (7): gemini_app_ready(), goto_gemini_app(), navigate_to_fresh_chat(), Navigate to Gemini without failing only because the SPA never fires full load., Navigate to a fresh Gemini chat using URL Stability Locks to defeat SPA race con, _url_is_base_app(), wait_for_manual_login()

### Community 60 - "Community 60"
Cohesion: 0.29
Nodes (5): GrepTool, test_grep_empty_query(), test_grep_finds_matches(), test_grep_include_pattern(), test_grep_no_matches()

### Community 61 - "Community 61"
Cohesion: 0.47
Nodes (6): click_send_button(), find_enabled_send_button(), _locator_rect(), _send_button_action(), _send_button_diagnostics(), wait_until_send_enabled()

### Community 64 - "Community 64"
Cohesion: 0.4
Nodes (4): Checklist, Content, Purpose, Sample Document

### Community 65 - "Community 65"
Cohesion: 0.5
Nodes (4): _image_candidates(), Return visible generated-image candidates.      Use an arrow function for Playwr, response_completed_with_media(), wait_for_generated_image()

## Knowledge Gaps
- **181 isolated node(s):** `Best-effort permissions needed for clipboard paste in CDP/visible Chrome.`, `Best-effort configure Chrome's download directory.      This matters when attach`, `Open/switch to the tab that will own this prompt.`, `Navigate to Gemini without failing only because the SPA never fires full load.`, `Navigate to a fresh Gemini chat using URL Stability Locks to defeat SPA race con` (+176 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GeminiProviderAdapter` connect `Community 38` to `Community 1`, `Community 35`, `Community 7`, `Community 42`, `Community 43`, `Community 12`, `Community 46`, `Community 19`, `Community 21`, `Community 57`, `Community 26`, `Community 28`, `Community 30`, `Community 63`?**
  _High betweenness centrality (0.195) - this node is a cross-community bridge._
- **Why does `UploadError` connect `Community 1` to `Community 38`, `Community 28`, `Community 6`?**
  _High betweenness centrality (0.126) - this node is a cross-community bridge._
- **Why does `ProviderRequest` connect `Community 26` to `Community 0`, `Community 38`, `Community 8`, `Community 42`, `Community 51`, `Community 21`, `Community 57`, `Community 28`?**
  _High betweenness centrality (0.115) - this node is a cross-community bridge._
- **Are the 34 inferred relationships involving `parse_agent_action()` (e.g. with `test_direct_tool_call()` and `test_direct_final()`) actually correct?**
  _`parse_agent_action()` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 27 inferred relationships involving `SessionPool` (e.g. with `FakePage` and `GeminiPageWithFiles`) actually correct?**
  _`SessionPool` has 27 INFERRED edges - model-reasoned connections that need verification._
- **Are the 25 inferred relationships involving `GeminiProviderAdapter` (e.g. with `GeminiPageWithFiles` and `GeminiLocator`) actually correct?**
  _`GeminiProviderAdapter` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `AgentState` (e.g. with `AgentMode` and `PlanState`) actually correct?**
  _`AgentState` has 18 INFERRED edges - model-reasoned connections that need verification._