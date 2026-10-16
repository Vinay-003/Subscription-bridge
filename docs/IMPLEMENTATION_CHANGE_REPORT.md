# SubscriptionBridge implementation report

## Scope and baseline

- Repository: `Subscription-bridge`
- Baseline branch: `main`
- Baseline commit: `a09a78738e63b388871d4cd25301bdc050914d6e`
- Intent: make the OpenAI-compatible gateway usable as a browser-backed custom provider for OpenCode while leaving the native SubscriptionBridge agent endpoints available separately.

## Result

The gateway path is designed around this ownership boundary:

1. OpenCode owns the agent loop, planning, workspace/file/shell tools, and actual tool execution.
2. SubscriptionBridge normalizes OpenAI-compatible requests, routes a request to the configured browser-backed provider, translates browser output into `tool_calls` when appropriate, and returns a compatible response.
3. The browser provides model inference through its visible UI. SubscriptionBridge does not execute OpenCode's requested tools from `/v1/chat/completions`.

The bridge still needs to convert a browser model's textual tool request into the OpenAI `tool_calls` shape. That conversion is protocol adaptation, not a second agent runtime.

## What changed

### Browser conversation identity and tab ownership

- Added stable owner tracking independent of the transient busy/current-run state.
- Serialized operations for a single browser conversation to avoid overlapping writes into one page.
- Added isolated conversation acquisition so unrelated sessions are not silently assigned another idle conversation.
- Added idle-session eviction at capacity rather than borrowing an active session; the pool reports an error if every slot is busy.
- Reset now clears browser conversation ownership, active-conversation state, and selected model state.
- In CDP mode, the page manager reuses an eligible already-open provider tab for the first session and creates separate tabs for additional isolated sessions.
- Aligned provider page creation with the provider name and corrected `create_session()` paths to release the acquisition lock.

### OpenAI-compatible request and response handling

- Session identity prefers host-supplied `x-opencode-session`, `x-opencode-session-id`, or `x-session-id` headers. The fallback is based on the full system prompt and initial user prompt rather than a short, truncated message prefix.
- Removed request-body/prompt previews from ordinary request logs.
- Respected `tool_choice: "none"` and pass the request tool definitions and `tool_choice` through parsing and streaming paths.
- Ensure generated tool-call IDs are present and unique.
- Removed SubscriptionBridge's own native-tool list from `/v1/models`; OpenCode receives its own request tool definitions and owns execution.
- Provider errors in streaming mode are emitted as SSE error objects instead of being disguised as a successful assistant answer.
- Temporary image files are cleaned up after the response path.

### Tool-call parsing and message conversion

- Added schema-aware filtering: unknown function names are rejected when tools were supplied in the request, forced tool selection is honored, arguments are checked against the declared JSON schema, and required properties are checked.
- Recursively normalizes common sentinel-format values to their declared types: booleans, integers, numbers, objects, arrays, nested properties, enum values, and required fields.
- Fixed the JSON candidate deduplication path so candidates are actually retained and evaluated rather than all being dropped.
- Preserved complete tool schemas in browser prompts instead of truncating each schema to a fixed character limit.
- Preserved full system/developer guidance rather than aggressively replacing a long OpenCode system prompt with a shortened prompt.
- Added specific formatting guidance when tool use is required or a particular tool is selected.

### Persistent browser response-style prompt

Added `BROWSER_RESPONSE_STYLE_SYSTEM_PROMPT` to the provider system instructions. It asks the browser model to answer directly in concise plain text or ordinary Markdown; not to generate HTML pages, JavaScript/CSS interfaces, interactive widgets, canvases, embedded apps, simulated UIs, or artifact previews; to avoid unnecessary preambles/disclaimers/self-commentary; and to use the supplied tool-call format when code changes require tools. HTML/code remains allowed when explicitly requested in the normal answer.

This prompt is defined in `src/subscription_bridge/api/openai/message_converter.py` and is included in every converted provider system prompt (including the no-system-message case).

### Image and process reliability

- Restricts remote image ingestion to public HTTP(S) URLs; rejects local/private/loopback/link-local addresses, local hostnames, credentials in URLs, non-image content types, oversized responses, and redirects to blocked destinations.
- Fixes shell command timeout cleanup on POSIX by starting the command in its own session and killing the process group on timeout. This prevents child processes from keeping pipes open after the parent shell is killed.

### Configuration and documentation

- Aligned browser mode configuration to CDP in `.env.example`, so copying the example no longer overrides the YAML default with managed mode.
- Aligned the configured API port with the documented/OpenCode port (`8787`).
- Updated the OpenCode documentation and README to make the tool ownership boundary explicit and explain how browser-backed tool requests are translated.

## Tests and verification

### Passed

- Python source/test compilation: `python -m compileall -q src tests`
- Targeted regression and relevant unit suites: **144 passed**
- Full test suite on the final working tree: **482 passed** in 29.82 seconds.
- `git diff --check`

Test command used:

```bash
PYTHONPATH=/tmp/subscriptionbridge-test-stubs:src pytest -q
```

The audit container did not have the `structlog` dependency installed and the package index was not reachable. To run tests, a minimal `structlog` compatibility stub was created outside the repository at `/tmp/subscriptionbridge-test-stubs/`. No stub or testing workaround was added to the project. The successful test run therefore validates repository behavior under that shim, but does not validate the installed production `structlog` package itself.

### Not verified in this environment

- A live OpenCode smoke test against a manually logged-in ChatGPT/Gemini browser session was not possible because the environment does not contain the user's authenticated browser/CDP session.
- Browser provider UI selectors and login/session expiration behavior remain subject to live validation. The Playwright manager and provider logic are covered by unit tests/fakes but not a live logged-in session.
- Ruff and mypy were not run because those executables are not available in the environment.

## Important operational notes

- If the client sends one of the supported session headers, it is used as the stable conversation identity. Otherwise, a deterministic identity is derived from the system prompt and first user message. Clients which may start two simultaneous sessions with identical initial prompts should pass a unique stable session header to guarantee isolation.
- Streaming is still simulated after the browser response has completed; it does not make browser UI generation itself incremental. Errors are reported in the SSE stream.
- A textual tool call may still be impossible to recover if the browser model returns a completely unrelated response or invents malformed content. In that case the bridge rejects the malformed call rather than executing an unknown function.

## Suggested live smoke test after deployment

1. Launch Chrome with remote debugging enabled, sign in to the selected provider, and leave the provider tab visible.
2. Start SubscriptionBridge in CDP mode and verify it attaches to/reuses the expected visible provider tab.
3. Configure OpenCode with the bridge's OpenAI-compatible base URL and a bridge model ID.
4. Ask OpenCode to inspect a local file, make a small edit, and run a test. Confirm that OpenCode's own file/shell tools execute, not SubscriptionBridge's native agent tools.
5. Continue through at least two tool-call/result turns; verify context is preserved.
6. Start a second OpenCode session with an unrelated task; verify the browser history and responses do not cross over.
7. Repeat with streaming enabled and verify `tool_calls` finish reasons and provider error reporting.
