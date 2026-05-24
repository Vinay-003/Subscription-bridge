# Graph Report - subscription-bridge  (2026-05-24)

## Corpus Check
- 135 files · ~55,627 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1669 nodes · 2779 edges · 100 communities (85 shown, 15 thin omitted)
- Extraction: 74% EXTRACTED · 24% INFERRED · 0% AMBIGUOUS · INFERRED: 664 edges (avg confidence: 0.74)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f044094b`
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
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
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
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 99|Community 99]]

## God Nodes (most connected - your core abstractions)
1. `SessionPool` - 40 edges
2. `GeminiProviderAdapter` - 36 edges
3. `AgentState` - 32 edges
4. `chat_completions()` - 31 edges
5. `CodebaseIndexer` - 30 edges
6. `FakeProviderAdapter` - 28 edges
7. `run()` - 24 edges
8. `ToolResult` - 23 edges
9. `validate_attachment_path()` - 22 edges
10. `parse_agent_action()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `fake_provider()` --calls--> `FakeProviderAdapter`  [INFERRED]
  tests/unit/test_fake_provider.py → src/subscription_bridge/providers/fake.py
- `test_fake_provider_send_prompt()` --calls--> `ProviderRequest`  [INFERRED]
  tests/unit/test_fake_provider.py → src/subscription_bridge/providers/base.py
- `store()` --calls--> `VectorStore`  [INFERRED]
  tests/unit/test_vector_store.py → src/subscription_bridge/memory/vector_store.py
- `sample_chunks()` --calls--> `DocumentChunk`  [INFERRED]
  tests/unit/test_vector_store.py → src/subscription_bridge/memory/models.py
- `pool()` --calls--> `SessionPool`  [INFERRED]
  tests/unit/test_session_pool.py → src/subscription_bridge/browser/session_pool.py

## Communities (100 total, 15 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (79): AskRequest, AskResponse, CodebaseIndexRequest, CodebaseIndexResponse, CodebaseSearchRequest, CodebaseSearchResponse, CodebaseStatsResponse, ErrorResponse (+71 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (62): ParserError, AttachmentInfo, classify_attachment(), _classify_extension(), detect_extension(), load_upload_config(), UploadConfig, validate_attachment_path() (+54 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (29): AgentRuntime, _auto_read_files(), _find_file_refs(), AgentError, DangerousCommandError, MaxStepsExceededError, ProviderResponseError, ToolExecutionError (+21 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (42): ABC, _get_agent_registry(), PathTraversalError, Tool, Tool, ToolCall, ToolResult, BashTool (+34 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (27): AgentState, AgentStatus, Observation, StepRecord, AgentMode, PlanState, TodoItem, TodoStatus (+19 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (27): check_composer_visible(), check_gemini_reachable(), check_gemini_ready(), check_login_indicator(), check_provider_health(), check_temporary_chat(), navigate_to_fresh_chat(), navigate_to_gemini() (+19 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (45): parse_agent_action(), _parse_clarification(), _parse_final(), _parse_tool_call(), _regex_extract_action(), _try_direct_parse(), _try_parse_alternative_formats(), build_repair_prompt() (+37 more)

### Community 7 - "Community 7"
Cohesion: 0.05
Nodes (42): Agent Runtime Layer, Browser Runtime Layer, CLI/API Layer, Context Builder Layer, JSON Parser, PlaywrightManager, ProviderAdapter, Provider Layer (+34 more)

### Community 8 - "Community 8"
Cohesion: 0.05
Nodes (5): SelectorLoadError, SelectorRegistry, _validate(), registry(), registry()

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (32): browser_doctor(), codebase_index(), codebase_search(), codebase_stats(), _ensure_browser(), _ensure_browser_async(), _ensure_gemini_provider(), _ensure_gemini_provider_async() (+24 more)

### Community 10 - "Community 10"
Cohesion: 0.05
Nodes (39): code:bash (bridge server --host 127.0.0.1 --port 8787), code:bash (curl -X POST http://127.0.0.1:8787/run \), code:json ({), code:json ({), code:json ({), code:json ({), code:json ({), code:json ({) (+31 more)

### Community 11 - "Community 11"
Cohesion: 0.06
Nodes (35): Architecture, CDP Mode (only way that works), CLI Commands, code:mermaid (flowchart TB), code:bash (curl http://127.0.0.1:8787/health), code:bash (# Install), code:bash (google-chrome \), code:bash (chmod +x ~/start-bridge.sh) (+27 more)

### Community 12 - "Community 12"
Cohesion: 0.11
Nodes (32): _attachment_spinner_count(), build_browser_context(), build_local_image_paths(), collect_upload_images_from_dir(), discover_prompt_jobs(), download_to_temp(), _format_sort_key(), get_all_image_srcs() (+24 more)

### Community 13 - "Community 13"
Cohesion: 0.11
Nodes (22): clear_composer(), compact_prompt_compare(), find_composer(), focus_composer(), format_integrity(), get_composer_text(), normalize_prompt_compare(), paste_via_clipboard() (+14 more)

### Community 14 - "Community 14"
Cohesion: 0.1
Nodes (23): main(), _get_log_format(), _get_log_level(), get_logger(), setup_logging(), StructuredLogger, test_browser_config_default_cdp_url(), test_browser_config_default_mode() (+15 more)

### Community 15 - "Community 15"
Cohesion: 0.08
Nodes (33): FastAPI Server, Browser Runtime, FakeProvider, Gemini Uploads Config, Logging Configuration, Memory System, SubscriptionBridge, Design Assessment Task (+25 more)

### Community 16 - "Community 16"
Cohesion: 0.11
Nodes (9): AppDependencies, create_app(), PlaywrightLaunchError, PlaywrightManager, _verify_cdp_reachable(), test_playwright_manager_cdp_not_reachable(), test_playwright_manager_create_page_before_start(), test_playwright_manager_init() (+1 more)

### Community 17 - "Community 17"
Cohesion: 0.15
Nodes (26): clear_composer_keyboard(), click_send_and_confirm(), _compact_prompt_compare(), find_composer(), focus_composer(), format_prompt_integrity(), generation_in_progress(), get_composer_text() (+18 more)

### Community 18 - "Community 18"
Cohesion: 0.08
Nodes (3): gemini_page_factory(), GeminiLocator, GeminiPageWithFiles

### Community 19 - "Community 19"
Cohesion: 0.14
Nodes (18): test_get_env_actual(), test_get_env_default(), test_load_providers_config(), test_load_selector_config_chatgpt(), test_load_selector_config_gemini(), test_load_selector_config_not_found(), test_load_tool_permissions(), test_tool_permissions_has_deny_commands() (+10 more)

### Community 20 - "Community 20"
Cohesion: 0.12
Nodes (23): _capture_download_from_click(), _click_download_control_js(), click_exact_image_and_download(), _configure_download_dir(), _default_chrome_download_dirs(), _download_control_available(), download_generated_image(), infer_ext_from_src() (+15 more)

### Community 21 - "Community 21"
Cohesion: 0.12
Nodes (13): _clean_assistant_text(), _composer_is_empty(), extract_latest_assistant_text(), generation_in_progress(), _sleep(), submission_activity_report(), wait_for_response_complete(), wait_for_send_confirmation() (+5 more)

### Community 22 - "Community 22"
Cohesion: 0.1
Nodes (5): SessionPoolError, SessionState, TabSession, Exception, GeminiError

### Community 23 - "Community 23"
Cohesion: 0.16
Nodes (20): chunk_file(), detect_language(), extract_imports(), extract_symbols(), is_binary(), skip_dir(), test_chunk_basic_text(), test_chunk_binary_skipped() (+12 more)

### Community 24 - "Community 24"
Cohesion: 0.1
Nodes (4): DownloadError, DownloadManager, _sleep(), manager()

### Community 25 - "Community 25"
Cohesion: 0.1
Nodes (4): FakePage, tab_session(), test_tab_session_close(), test_tab_session_ensure_alive_closed()

### Community 26 - "Community 26"
Cohesion: 0.13
Nodes (14): _extract_model_variant(), GeminiProviderAdapter, CompleteGeminiPage, test_adapter_without_attachments_still_works(), gemini_page_factory(), test_adapter_create_session(), test_adapter_creation(), test_adapter_health_check() (+6 more)

### Community 27 - "Community 27"
Cohesion: 0.18
Nodes (15): test_retry_async_eventual_success(), test_retry_async_exhausted(), test_retry_async_helper(), test_retry_async_success(), test_retry_base_exception_passthrough(), test_retry_config_custom(), test_retry_config_defaults(), test_retry_custom_exception_types() (+7 more)

### Community 28 - "Community 28"
Cohesion: 0.1
Nodes (4): FakePage, _page_factory(), pool(), test_close_session()

### Community 29 - "Community 29"
Cohesion: 0.15
Nodes (14): HashEmbeddingProvider, test_embed_query(), test_hash_embedding_deterministic(), test_hash_embedding_different_inputs(), test_hash_embedding_dim(), test_hash_embedding_empty_text(), test_hash_embedding_normalized(), test_hash_embedding_texts() (+6 more)

### Community 30 - "Community 30"
Cohesion: 0.18
Nodes (18): test_redact_secret_access_token(), test_redact_secret_api_key(), test_redact_secret_empty(), test_redact_secret_noop(), test_redact_secret_password(), test_redact_url_credentials(), test_redact_url_credentials_empty(), test_redact_url_credentials_no_creds() (+10 more)

### Community 31 - "Community 31"
Cohesion: 0.1
Nodes (19): author, dependencies, autoprefixer, framer-motion, lucide-react, next, postcss, react (+11 more)

### Community 32 - "Community 32"
Cohesion: 0.19
Nodes (12): CodebaseIndexer, IndexData, IndexMetadata, test_index_creates_data(), test_index_saves_chunks(), test_index_saves_embeddings(), test_index_skips_git(), test_index_skips_node_modules() (+4 more)

### Community 33 - "Community 33"
Cohesion: 0.2
Nodes (17): test_config_dir(), test_ensure_dir_creates(), test_ensure_dir_existing(), test_expand_user_path(), test_expand_user_path_relative(), test_get_config_path_found(), test_get_config_path_not_found(), test_project_root() (+9 more)

### Community 34 - "Community 34"
Cohesion: 0.18
Nodes (10): LoginTimeoutError, _sleep(), wait_for_login(), wait_for_url_contains(), FakeElement, FakePage, test_check_login_indicator_empty_selectors(), test_check_login_indicator_found() (+2 more)

### Community 35 - "Community 35"
Cohesion: 0.22
Nodes (16): CodeSymbol, build_symbol_index(), _extract_js_ts(), _extract_python(), _extract_python_imports(), _extract_regex(), extract_symbols_from_file(), test_build_symbol_index() (+8 more)

### Community 36 - "Community 36"
Cohesion: 0.11
Nodes (17): CDP Mode (Recommended for Development), code:yaml (browser:), code:bash (export BRIDGE_CHROME_PATH=/usr/bin/google-chrome), code:block3 (http://127.0.0.1:9333), code:bash (google-chrome \), code:bash (chromium \), code:bash (/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chro), code:powershell (& "C:\Program Files\Google\Chrome\Application\chrome.exe" `) (+9 more)

### Community 37 - "Community 37"
Cohesion: 0.11
Nodes (17): App section, Browser section, code:yaml (app:), code:yaml (browser:), code:yaml (memory:), code:yaml (gemini:), code:yaml (providers:), code:yaml (bash:) (+9 more)

### Community 40 - "Community 40"
Cohesion: 0.14
Nodes (16): _active_window_title(), click_attach_button_near_composer(), _click_attach_menu_button_only(), _click_upload_files_menu_item(), _native_dialog_choose_file(), _native_file_dialog_active(), _open_upload_file_chooser(), Click the visible attachment/add-files control closest to the composer. (+8 more)

### Community 42 - "Community 42"
Cohesion: 0.18
Nodes (3): ProviderAdapter, ProviderResponse, FakeProviderAdapter

### Community 43 - "Community 43"
Cohesion: 0.21
Nodes (10): _async_sleep(), _detect_model_label(), _normalize_variant(), _switch_model_variant(), _variant_aliases(), _variant_select_labels(), ModelSwitchPage, test_detect_model_label_reads_visible_text() (+2 more)

### Community 44 - "Community 44"
Cohesion: 0.13
Nodes (14): A. Setup, B. Fake Provider Demo, C. Codebase Memory Demo, code:bash (# 1. Create and activate virtual environment), code:bash (# List configured providers), code:bash (# Index the workspace (117 files, ~158 chunks, ~6s)), code:bash (# 1. Start Chrome with remote debugging on port 9333), code:bash (# Summarize a text file) (+6 more)

### Community 46 - "Community 46"
Cohesion: 0.14
Nodes (13): code:json ({), code:json ({), code:bash (# 1. Start the SubscriptionBridge server), code:json ({), Compaction Config, Known Limitations, Model Reference, OpenCode Configuration (+5 more)

### Community 47 - "Community 47"
Cohesion: 0.23
Nodes (5): create_embedding_provider(), EmbeddingProvider, SentenceTransformerEmbeddingProvider, test_create_default_provider(), test_create_invalid_fallback()

### Community 48 - "Community 48"
Cohesion: 0.17
Nodes (4): ProviderRegistry, test_registry_empty_route(), test_registry_register(), test_registry_unregister()

### Community 49 - "Community 49"
Cohesion: 0.2
Nodes (8): collect_button_diagnostics(), default_unsafe_words(), dismiss_overlays(), make_bad_words_check(), safe_click_labels(), _sleep(), test_default_unsafe_words(), test_make_bad_words_check_script()

### Community 50 - "Community 50"
Cohesion: 0.18
Nodes (3): fake_provider(), test_fake_provider_failure_rate(), test_fake_provider_send_prompt()

### Community 53 - "Community 53"
Cohesion: 0.22
Nodes (10): assert_not_temporary_chat(), gemini_app_ready(), goto_gemini_app(), navigate_to_fresh_chat(), page_heading_looks_temporary(), Navigate to Gemini without failing only because the SPA never fires full load., Navigate to a fresh Gemini chat using URL Stability Locks to defeat SPA race con, _url_is_base_app() (+2 more)

### Community 54 - "Community 54"
Cohesion: 0.22
Nodes (3): _cosine_similarity(), VectorStore, test_save_load()

### Community 56 - "Community 56"
Cohesion: 0.22
Nodes (9): _describe_input_attrs(), _dispatch_file_input_events_via_cdp(), _find_file_input_across_frames(), _find_file_input_anywhere(), open_attachment_ui(), Find an existing file input. Hidden inputs are OK for set_input_files()., Open the + / attachment menu only.      Important: do NOT click the "Upload file, Assign files to an existing Gemini file input through CDP.      Gemini usually c (+1 more)

### Community 58 - "Community 58"
Cohesion: 0.22
Nodes (8): Architecture (6 Layers), Code Quality, code:bash (# Install), Commands, Implementation Phases, Key Patterns, Project Overview, SubscriptionBridge - Coding Agent Guide

### Community 59 - "Community 59"
Cohesion: 0.32
Nodes (8): create_image_tool_selected(), dismiss_open_overlays(), pro_model_selected(), _safe_click_js(), safe_click_labels(), select_create_image_tool(), select_model_and_tool_if_requested(), select_pro_model()

### Community 60 - "Community 60"
Cohesion: 0.54
Nodes (7): DocumentChunk, _make_index(), test_retrieve_empty_index(), test_retrieve_returned_fields(), test_retrieve_returns_results(), test_retrieve_symbol_boost(), test_retrieve_top_k_respected()

### Community 64 - "Community 64"
Cohesion: 0.25
Nodes (7): architecture, flow, layers, project, providers, status, version

### Community 65 - "Community 65"
Cohesion: 0.38
Nodes (6): ProviderRequest, test_scripted_resets(), test_scripted_responses_in_order(), test_scripted_responses_repeat_last(), test_fake_provider_json_response(), test_registry_provider_works_through_registry()

### Community 66 - "Community 66"
Cohesion: 0.47
Nodes (6): click_send_button(), find_enabled_send_button(), _locator_rect(), _send_button_action(), _send_button_diagnostics(), wait_until_send_enabled()

### Community 68 - "Community 68"
Cohesion: 0.4
Nodes (4): Checklist, Content, Purpose, Sample Document

### Community 69 - "Community 69"
Cohesion: 0.5
Nodes (4): _image_candidates(), Return visible generated-image candidates.      Use an arrow function for Playwr, response_completed_with_media(), wait_for_generated_image()

## Knowledge Gaps
- **181 isolated node(s):** `Best-effort permissions needed for clipboard paste in CDP/visible Chrome.`, `Best-effort configure Chrome's download directory.      This matters when attach`, `Open/switch to the tab that will own this prompt.`, `Navigate to Gemini without failing only because the SPA never fires full load.`, `Navigate to a fresh Gemini chat using URL Stability Locks to defeat SPA race con` (+176 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GeminiProviderAdapter` connect `Community 26` to `Community 1`, `Community 65`, `Community 67`, `Community 5`, `Community 39`, `Community 9`, `Community 42`, `Community 43`, `Community 45`, `Community 16`, `Community 18`, `Community 52`, `Community 22`, `Community 61`, `Community 63`?**
  _High betweenness centrality (0.187) - this node is a cross-community bridge._
- **Why does `UploadError` connect `Community 1` to `Community 26`, `Community 22`?**
  _High betweenness centrality (0.126) - this node is a cross-community bridge._
- **Why does `test_wait_for_uploads_settles_timeout()` connect `Community 1` to `Community 12`?**
  _High betweenness centrality (0.112) - this node is a cross-community bridge._
- **Are the 27 inferred relationships involving `SessionPool` (e.g. with `FakePage` and `GeminiPageWithFiles`) actually correct?**
  _`SessionPool` has 27 INFERRED edges - model-reasoned connections that need verification._
- **Are the 25 inferred relationships involving `GeminiProviderAdapter` (e.g. with `GeminiPageWithFiles` and `GeminiLocator`) actually correct?**
  _`GeminiProviderAdapter` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `AgentState` (e.g. with `AgentMode` and `PlanState`) actually correct?**
  _`AgentState` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `chat_completions()` (e.g. with `ChatCompletionRequest` and `ChatCompletionResponse`) actually correct?**
  _`chat_completions()` has 8 INFERRED edges - model-reasoned connections that need verification._