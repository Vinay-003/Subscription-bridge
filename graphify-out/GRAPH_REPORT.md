# Graph Report - .  (2026-05-13)

## Corpus Check
- Corpus is ~49,348 words - fits in a single context window. You may not need a graph.

## Summary
- 1362 nodes · 2333 edges · 79 communities (68 shown, 11 thin omitted)
- Extraction: 72% EXTRACTED · 25% INFERRED · 0% AMBIGUOUS · INFERRED: 590 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_CLI & API App Entry|CLI & API App Entry]]
- [[_COMMUNITY_Gemini File Attachments|Gemini File Attachments]]
- [[_COMMUNITY_API RequestResponse Models|API Request/Response Models]]
- [[_COMMUNITY_Codebase Indexing & Chunking|Codebase Indexing & Chunking]]
- [[_COMMUNITY_Codebase Search & Embeddings|Codebase Search & Embeddings]]
- [[_COMMUNITY_Provider Adapter Layer|Provider Adapter Layer]]
- [[_COMMUNITY_Gemini Health Checks|Gemini Health Checks]]
- [[_COMMUNITY_Browser Context Manager|Browser Context Manager]]
- [[_COMMUNITY_Architecture Concepts|Architecture Concepts]]
- [[_COMMUNITY_Selector Registry|Selector Registry]]
- [[_COMMUNITY_JSON Parsing|JSON Parsing]]
- [[_COMMUNITY_Gemini Prompt IO|Gemini Prompt IO]]
- [[_COMMUNITY_CLI Main & Logging|CLI Main & Logging]]
- [[_COMMUNITY_App Architecture Overview|App Architecture Overview]]
- [[_COMMUNITY_Gemini Automation Script|Gemini Automation Script]]
- [[_COMMUNITY_API Dependencies|API Dependencies]]
- [[_COMMUNITY_Gemini Automation Prompts|Gemini Automation Prompts]]
- [[_COMMUNITY_Gemini Automation Downloads|Gemini Automation Downloads]]
- [[_COMMUNITY_Config & Config Tests|Config & Config Tests]]
- [[_COMMUNITY_Tab Session Tests|Tab Session Tests]]
- [[_COMMUNITY_Agent State|Agent State]]
- [[_COMMUNITY_Session Pool Tests|Session Pool Tests]]
- [[_COMMUNITY_Gemini Response Reader|Gemini Response Reader]]
- [[_COMMUNITY_Retry Utilities|Retry Utilities]]
- [[_COMMUNITY_Security Utilities|Security Utilities]]
- [[_COMMUNITY_Path Utilities|Path Utilities]]
- [[_COMMUNITY_Async Utils|Async Utils]]
- [[_COMMUNITY_Gemini Automation Uploads|Gemini Automation Uploads]]
- [[_COMMUNITY_Gemini Adapter Core|Gemini Adapter Core]]
- [[_COMMUNITY_Gemini Automation Attachments|Gemini Automation Attachments]]
- [[_COMMUNITY_Gemini Adapter Test Mocks|Gemini Adapter Test Mocks]]
- [[_COMMUNITY_Tool Executor|Tool Executor]]
- [[_COMMUNITY_Error Types|Error Types]]
- [[_COMMUNITY_Gemini Adapter File Tests|Gemini Adapter File Tests]]
- [[_COMMUNITY_Gemini Adapter Send Prompt|Gemini Adapter Send Prompt]]
- [[_COMMUNITY_Agent Runtime|Agent Runtime]]
- [[_COMMUNITY_Session Pool|Session Pool]]
- [[_COMMUNITY_Tab Session|Tab Session]]
- [[_COMMUNITY_UI Guard|UI Guard]]
- [[_COMMUNITY_Gemini File Test Mocks|Gemini File Test Mocks]]
- [[_COMMUNITY_Loop Controller|Loop Controller]]
- [[_COMMUNITY_Planner|Planner]]
- [[_COMMUNITY_Session Pool Metrics|Session Pool Metrics]]
- [[_COMMUNITY_Gemini Adapter Mocks|Gemini Adapter Mocks]]
- [[_COMMUNITY_Tool Registry|Tool Registry]]
- [[_COMMUNITY_Gemini Automation File Input|Gemini Automation File Input]]
- [[_COMMUNITY_Gemini Adapter Test Pages|Gemini Adapter Test Pages]]
- [[_COMMUNITY_Gemini Automation Send Button|Gemini Automation Send Button]]
- [[_COMMUNITY_Gemini Automation Browser Build|Gemini Automation Browser Build]]
- [[_COMMUNITY_Gemini Automation Response Wait|Gemini Automation Response Wait]]
- [[_COMMUNITY_Message Model|Message Model]]
- [[_COMMUNITY_README Future & Limitations|README Future & Limitations]]
- [[_COMMUNITY_App Config YAML|App Config YAML]]
- [[_COMMUNITY_Browser Setup Docs|Browser Setup Docs]]

## God Nodes (most connected - your core abstractions)
1. `SessionPool` - 36 edges
2. `GeminiProviderAdapter` - 33 edges
3. `CodebaseIndexer` - 30 edges
4. `FakeProviderAdapter` - 28 edges
5. `run()` - 24 edges
6. `AgentState` - 24 edges
7. `validate_attachment_path()` - 22 edges
8. `Retriever` - 20 edges
9. `HashEmbeddingProvider` - 20 edges
10. `AgentRuntime` - 20 edges

## Surprising Connections (you probably didn't know these)
- `pool()` --calls--> `SessionPool`  [INFERRED]
  tests/unit/test_session_pool.py → src/subscription_bridge/browser/session_pool.py
- `fake_provider()` --calls--> `FakeProviderAdapter`  [INFERRED]
  tests/unit/test_fake_provider.py → src/subscription_bridge/providers/fake.py
- `test_fake_provider_send_prompt()` --calls--> `ProviderRequest`  [INFERRED]
  tests/unit/test_fake_provider.py → src/subscription_bridge/providers/base.py
- `test_fake_provider_json_response()` --calls--> `ProviderRequest`  [INFERRED]
  tests/unit/test_fake_provider.py → src/subscription_bridge/providers/base.py
- `test_load_providers_config()` --calls--> `load_providers_config()`  [INFERRED]
  tests/unit/test_config.py → src/subscription_bridge/utils/config.py

## Communities (79 total, 11 thin omitted)

### Community 0 - "CLI & API App Entry"
Cohesion: 0.05
Nodes (52): ABC, browser_doctor(), codebase_stats(), _ensure_browser(), _ensure_gemini_provider(), _fmt_time(), _get_agent_registry(), _get_registry() (+44 more)

### Community 1 - "Gemini File Attachments"
Cohesion: 0.07
Nodes (52): AttachmentInfo, classify_attachment(), _classify_extension(), detect_extension(), load_upload_config(), UploadConfig, validate_attachment_path(), validate_attachments() (+44 more)

### Community 2 - "API Request/Response Models"
Cohesion: 0.06
Nodes (59): AskRequest, AskResponse, CodebaseIndexRequest, CodebaseIndexResponse, CodebaseSearchRequest, CodebaseSearchResponse, CodebaseStatsResponse, ErrorResponse (+51 more)

### Community 3 - "Codebase Indexing & Chunking"
Cohesion: 0.06
Nodes (49): codebase_index(), chunk_file(), detect_language(), extract_imports(), extract_symbols(), is_binary(), skip_dir(), CodebaseIndexer (+41 more)

### Community 4 - "Codebase Search & Embeddings"
Cohesion: 0.06
Nodes (32): codebase_search(), create_embedding_provider(), EmbeddingProvider, HashEmbeddingProvider, SentenceTransformerEmbeddingProvider, DocumentChunk, SearchResult, Retriever (+24 more)

### Community 5 - "Provider Adapter Layer"
Cohesion: 0.05
Nodes (16): ProviderAdapter, ProviderRequest, FakeProviderAdapter, ProviderRegistry, fake_provider(), test_scripted_resets(), test_scripted_responses_in_order(), test_scripted_responses_repeat_last() (+8 more)

### Community 6 - "Gemini Health Checks"
Cohesion: 0.06
Nodes (27): check_composer_visible(), check_gemini_reachable(), check_gemini_ready(), check_login_indicator(), check_provider_health(), check_temporary_chat(), navigate_to_fresh_chat(), navigate_to_gemini() (+19 more)

### Community 7 - "Browser Context Manager"
Cohesion: 0.05
Nodes (17): BrowserContextManager, ContextManagerError, DownloadError, DownloadManager, _sleep(), LoginTimeoutError, _sleep(), wait_for_login() (+9 more)

### Community 8 - "Architecture Concepts"
Cohesion: 0.05
Nodes (42): Agent Runtime Layer, Browser Runtime Layer, CLI/API Layer, Context Builder Layer, JSON Parser, PlaywrightManager, ProviderAdapter, Provider Layer (+34 more)

### Community 9 - "Selector Registry"
Cohesion: 0.05
Nodes (5): SelectorLoadError, SelectorRegistry, _validate(), registry(), registry()

### Community 10 - "JSON Parsing"
Cohesion: 0.1
Nodes (35): parse_agent_action(), _parse_clarification(), _parse_final(), _parse_tool_call(), _try_direct_parse(), build_repair_prompt(), extract_first_json(), fix_smart_quotes() (+27 more)

### Community 11 - "Gemini Prompt IO"
Cohesion: 0.11
Nodes (21): clear_composer(), compact_prompt_compare(), find_composer(), focus_composer(), format_integrity(), get_composer_text(), normalize_prompt_compare(), paste_via_clipboard() (+13 more)

### Community 12 - "CLI Main & Logging"
Cohesion: 0.1
Nodes (23): main(), _get_log_format(), _get_log_level(), get_logger(), setup_logging(), StructuredLogger, test_browser_config_default_cdp_url(), test_browser_config_default_mode() (+15 more)

### Community 13 - "App Architecture Overview"
Cohesion: 0.08
Nodes (33): FastAPI Server, Browser Runtime, FakeProvider, Gemini Uploads Config, Logging Configuration, Memory System, SubscriptionBridge, Design Assessment Task (+25 more)

### Community 14 - "Gemini Automation Script"
Cohesion: 0.11
Nodes (29): assert_not_temporary_chat(), _attachment_spinner_count(), build_local_image_paths(), create_image_tool_selected(), discover_prompt_jobs(), dismiss_open_overlays(), download_to_temp(), _format_sort_key() (+21 more)

### Community 15 - "API Dependencies"
Cohesion: 0.11
Nodes (9): AppDependencies, create_app(), PlaywrightLaunchError, PlaywrightManager, _verify_cdp_reachable(), test_playwright_manager_cdp_not_reachable(), test_playwright_manager_create_page_before_start(), test_playwright_manager_init() (+1 more)

### Community 16 - "Gemini Automation Prompts"
Cohesion: 0.15
Nodes (26): clear_composer_keyboard(), click_send_and_confirm(), _compact_prompt_compare(), find_composer(), focus_composer(), format_prompt_integrity(), generation_in_progress(), get_composer_text() (+18 more)

### Community 17 - "Gemini Automation Downloads"
Cohesion: 0.12
Nodes (23): _capture_download_from_click(), _click_download_control_js(), click_exact_image_and_download(), _configure_download_dir(), _default_chrome_download_dirs(), _download_control_available(), download_generated_image(), infer_ext_from_src() (+15 more)

### Community 18 - "Config & Config Tests"
Cohesion: 0.18
Nodes (18): test_get_env_actual(), test_get_env_default(), test_load_providers_config(), test_load_selector_config_chatgpt(), test_load_selector_config_gemini(), test_load_selector_config_not_found(), test_load_tool_permissions(), test_tool_permissions_has_deny_commands() (+10 more)

### Community 19 - "Tab Session Tests"
Cohesion: 0.1
Nodes (4): FakePage, tab_session(), test_tab_session_close(), test_tab_session_ensure_alive_closed()

### Community 20 - "Agent State"
Cohesion: 0.13
Nodes (11): AgentState, Observation, StepRecord, test_add_observation_increments_steps(), test_complete(), test_exceed_max_steps(), test_fail(), test_initial_state() (+3 more)

### Community 21 - "Session Pool Tests"
Cohesion: 0.1
Nodes (4): FakePage, _page_factory(), pool(), test_close_session()

### Community 22 - "Gemini Response Reader"
Cohesion: 0.13
Nodes (11): _composer_is_empty(), extract_latest_assistant_text(), generation_in_progress(), _sleep(), submission_activity_report(), wait_for_response_complete(), wait_for_send_confirmation(), FakeElement (+3 more)

### Community 23 - "Retry Utilities"
Cohesion: 0.18
Nodes (15): test_retry_async_eventual_success(), test_retry_async_exhausted(), test_retry_async_helper(), test_retry_async_success(), test_retry_base_exception_passthrough(), test_retry_config_custom(), test_retry_config_defaults(), test_retry_custom_exception_types() (+7 more)

### Community 24 - "Security Utilities"
Cohesion: 0.17
Nodes (18): test_redact_secret_access_token(), test_redact_secret_api_key(), test_redact_secret_empty(), test_redact_secret_noop(), test_redact_secret_password(), test_redact_url_credentials(), test_redact_url_credentials_empty(), test_redact_url_credentials_no_creds() (+10 more)

### Community 25 - "Path Utilities"
Cohesion: 0.2
Nodes (17): test_config_dir(), test_ensure_dir_creates(), test_ensure_dir_existing(), test_expand_user_path(), test_expand_user_path_relative(), test_get_config_path_found(), test_get_config_path_not_found(), test_project_root() (+9 more)

### Community 26 - "Async Utils"
Cohesion: 0.18
Nodes (14): test_gather_with_concurrency(), test_gather_with_concurrency_empty(), test_gather_with_concurrency_respects_limit(), test_gather_with_concurrency_return_exceptions(), test_operation_timeout_error_repr(), test_run_sync_with_timeout_expires(), test_run_sync_with_timeout_success(), test_run_with_timeout_custom_message() (+6 more)

### Community 27 - "Gemini Automation Uploads"
Cohesion: 0.12
Nodes (17): collect_upload_images_from_dir(), get_all_image_srcs(), is_blankish_url(), load_starting_prompt(), open_prompt_tab(), parse_args(), parse_image_source_file(), prepend_starting_prompt() (+9 more)

### Community 29 - "Gemini Adapter Core"
Cohesion: 0.17
Nodes (9): GeminiProviderAdapter, CompleteGeminiPage, gemini_page_factory(), test_adapter_create_session(), test_adapter_creation(), test_adapter_health_check(), test_adapter_reset_chat(), test_adapter_send_prompt_fails_without_browser() (+1 more)

### Community 30 - "Gemini Automation Attachments"
Cohesion: 0.14
Nodes (16): _active_window_title(), click_attach_button_near_composer(), _click_attach_menu_button_only(), _click_upload_files_menu_item(), _native_dialog_choose_file(), _native_file_dialog_active(), _open_upload_file_chooser(), Click the visible attachment/add-files control closest to the composer. (+8 more)

### Community 32 - "Tool Executor"
Cohesion: 0.14
Nodes (5): ToolExecutor, registry(), test_executor_catches_exception(), test_executor_runs_tool(), test_executor_unknown_tool()

### Community 33 - "Error Types"
Cohesion: 0.22
Nodes (7): AgentError, DangerousCommandError, MaxStepsExceededError, ParserError, ProviderResponseError, ToolExecutionError, ToolNotFoundError

### Community 34 - "Gemini Adapter File Tests"
Cohesion: 0.14
Nodes (3): gemini_page_factory(), GeminiPageWithFiles, test_adapter_without_attachments_still_works()

### Community 35 - "Gemini Adapter Send Prompt"
Cohesion: 0.18
Nodes (4): _async_sleep(), GeminiError, ProviderAdapter, ProviderResponse

### Community 36 - "Agent Runtime"
Cohesion: 0.43
Nodes (11): AgentRuntime, Task, _scripted_provider(), test_runtime_clarification(), test_runtime_final_answer_direct(), test_runtime_max_steps_exceeded(), test_runtime_parser_failure_handled(), test_runtime_provider_failure() (+3 more)

### Community 40 - "UI Guard"
Cohesion: 0.2
Nodes (6): default_unsafe_words(), make_bad_words_check(), safe_click_labels(), _sleep(), test_default_unsafe_words(), test_make_bad_words_check_script()

### Community 42 - "Loop Controller"
Cohesion: 0.23
Nodes (3): LoopController, Planner, RunResult

### Community 43 - "Planner"
Cohesion: 0.29
Nodes (8): build_observation_context(), build_system_prompt(), build_user_prompt(), test_observation_context_empty(), test_system_prompt_empty_tools(), test_system_prompt_includes_tools(), test_user_prompt_includes_task(), test_user_prompt_with_observations()

### Community 44 - "Session Pool Metrics"
Cohesion: 0.2
Nodes (4): SessionPoolError, SessionState, AgentStatus, StrEnum

### Community 47 - "Gemini Automation File Input"
Cohesion: 0.22
Nodes (9): _describe_input_attrs(), _dispatch_file_input_events_via_cdp(), _find_file_input_across_frames(), _find_file_input_anywhere(), open_attachment_ui(), Find an existing file input. Hidden inputs are OK for set_input_files()., Open the + / attachment menu only.      Important: do NOT click the "Upload file, Assign files to an existing Gemini file input through CDP.      Gemini usually c (+1 more)

### Community 50 - "Gemini Automation Send Button"
Cohesion: 0.47
Nodes (6): click_send_button(), find_enabled_send_button(), _locator_rect(), _send_button_action(), _send_button_diagnostics(), wait_until_send_enabled()

### Community 51 - "Gemini Automation Browser Build"
Cohesion: 0.5
Nodes (4): build_browser_context(), grant_gemini_permissions(), Best-effort permissions needed for clipboard paste in CDP/visible Chrome., resolve_browser_binary()

### Community 52 - "Gemini Automation Response Wait"
Cohesion: 0.5
Nodes (4): _image_candidates(), Return visible generated-image candidates.      Use an arrow function for Playwr, response_completed_with_media(), wait_for_generated_image()

## Knowledge Gaps
- **64 isolated node(s):** `Best-effort permissions needed for clipboard paste in CDP/visible Chrome.`, `Best-effort configure Chrome's download directory.      This matters when attach`, `Open/switch to the tab that will own this prompt.`, `Navigate to Gemini without failing only because the SPA never fires full load.`, `Navigate to a fresh Gemini chat using URL Stability Locks to defeat SPA race con` (+59 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GeminiProviderAdapter` connect `Gemini Adapter Core` to `CLI & API App Entry`, `Gemini File Attachments`, `Gemini Adapter File Tests`, `Gemini Adapter Send Prompt`, `Provider Adapter Layer`, `Gemini Health Checks`, `Session Pool`, `Tab Session`, `Gemini File Test Mocks`, `Gemini Adapter Mocks`, `API Dependencies`, `Gemini Adapter Test Pages`, `Gemini Adapter Test Mocks`?**
  _High betweenness centrality (0.174) - this node is a cross-community bridge._
- **Why does `ProviderRequest` connect `Provider Adapter Layer` to `API Request/Response Models`, `Gemini Adapter Send Prompt`, `Gemini Adapter File Tests`, `Loop Controller`, `Gemini Adapter Core`?**
  _High betweenness centrality (0.103) - this node is a cross-community bridge._
- **Why does `SessionPool` connect `Session Pool` to `CLI & API App Entry`, `Gemini Adapter File Tests`, `Gemini Adapter Send Prompt`, `Tab Session`, `Gemini File Test Mocks`, `Session Pool Metrics`, `Gemini Adapter Mocks`, `API Dependencies`, `Gemini Adapter Test Pages`, `Session Pool Tests`, `Gemini Adapter Core`, `Gemini Adapter Test Mocks`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **Are the 24 inferred relationships involving `SessionPool` (e.g. with `FakePage` and `GeminiPageWithFiles`) actually correct?**
  _`SessionPool` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 22 inferred relationships involving `GeminiProviderAdapter` (e.g. with `GeminiPageWithFiles` and `GeminiLocator`) actually correct?**
  _`GeminiProviderAdapter` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `CodebaseIndexer` (e.g. with `EmbeddingProvider` and `IndexData`) actually correct?**
  _`CodebaseIndexer` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `FakeProviderAdapter` (e.g. with `ProviderAdapter` and `ProviderRequest`) actually correct?**
  _`FakeProviderAdapter` has 16 INFERRED edges - model-reasoned connections that need verification._