# Prompt for integrating the SubscriptionBridge fixes into the original repository

You are integrating a prepared SubscriptionBridge patch ZIP into the original SubscriptionBridge repository. The original repository/ZIP is the source of truth for user work. The updated ZIP contains a set of fixes based on branch `main` at commit `a09a78738e63b388871d4cd25301bdc050914d6e`.

## Goal

Integrate the updated ZIP's implementation into the original repository without blindly replacing the entire project. Preserve any unrelated local work in the original repository, review the diff file by file, and commit the integration in multiple small, coherent commits. Use the original repository's current `main` as the working base unless the user explicitly directs otherwise.

## Required architecture

- OpenCode owns the agent loop, planning, tools, workspace/filesystem/shell operations, and executing tool calls.
- SubscriptionBridge's `/v1/chat/completions` path acts as a browser-backed model provider and OpenAI-compatible protocol adapter only.
- The bridge may translate the browser model's textual tool-call format into OpenAI `tool_calls`; it must not call `ToolExecutor` or run the bridge's native agent for OpenCode tool requests.
- Keep native SubscriptionBridge endpoints/features intact and separate.
- Use a visible browser/CDP session by default so the provider page can be inspected. Reuse the intended already-open provider tab for the first appropriate session; do not claim that headed mode means the existing tab is reused unless the code proves it.

## Integration workflow

1. Inspect `git status`, current branch, and latest commits in the original repository. Do not overwrite or discard pre-existing user changes.
2. Unpack the updated ZIP to a temporary directory. Compare original and updated source trees, including tests and docs. Use a three-way/diff review where possible and identify conflicts before applying changes.
3. Integrate only the intended fixes. Adapt to any original changes rather than blindly copying folders.
4. Run compile, targeted tests, and the full test suite after integration. If dependencies are unavailable, report the exact blocker and do not invent successful results.
5. Inspect final `git diff`, check for accidental secrets, generated files, stale ports/browser-mode settings, and changes unrelated to the request.
6. Make the commits below in order. Adjust file staging to ensure each commit contains only its described topic. If a concern spans a file changed in multiple topics, it is acceptable to stage that file in one commit, but avoid duplicate or incoherent commits.
7. Return a summary of all commits, checks and results, remaining limitations, and the exact manual live-browser smoke test needed.

## Suggested commit sequence

### Commit 1 — `fix: isolate browser sessions and reuse visible provider tabs`

Include stable conversation ownership, per-conversation serialization, isolated-session allocation, capacity/idle eviction behavior, reset-state cleanup, provider-aware page creation, CDP existing-tab reuse, browser-mode defaults, and adapter session lock handling. Add/update session-pool and Playwright manager tests.

### Commit 2 — `fix: validate browser tool calls against OpenAI schemas`

Include tool parser JSON-candidate handling, typed schema validation/coercion, required/enum checks, tool-name filtering, `tool_choice`, complete tool schema formatting, full system prompt preservation, standard tool-call IDs, stream tool-call handling, OpenAI model catalog separation, and API/protocol regression tests. The bridge must return tool calls to OpenCode but never execute them itself.

### Commit 3 — `fix: harden request handling and browser response behavior`

Include stable session-key selection, no raw prompt preview in logs, SSE provider error handling, temporary-image cleanup, safe remote image URL restrictions/size limits/redirect validation, and POSIX shell timeout process-group cleanup. Add tests for those behaviors.

### Commit 4 — `docs: document OpenCode provider workflow and verification`

Include `.env.example`/YAML port and mode alignment, updated OpenCode docs/README, a change report, and this integration prompt. Check that documented commands/ports match configuration.

## Permanent browser response-style system prompt

Ensure the provider system prompt includes an instruction equivalent to the following on every converted request, including requests that contain no explicit system message:

> Return the answer as concise plain text or ordinary Markdown. Do not generate or render an HTML page, JavaScript, CSS, an interactive widget, canvas, embedded app, artifact preview, or simulated UI. Do not describe a webpage or interactive result instead of answering the request. Avoid unnecessary preambles, disclaimers, self-talk, and commentary; answer directly. Do not claim that a tool was executed. When the task requires code changes, use the supplied tool-call format for tool arguments and keep the visible answer short. Only provide HTML/code in a normal answer when the user explicitly asks to see that code.

Keep this as an explicit, named constant (for example, `BROWSER_RESPONSE_STYLE_SYSTEM_PROMPT`) and add a test proving it is present in the provider system prompt. Do not put this only in documentation; it must be sent to the browser model.

## Required regression tests

- Complete OpenCode tool loop: initial user request -> browser-generated `tool_calls` -> OpenCode tool result -> follow-up browser response.
- Stable conversation identity across growing message history; distinct session IDs never mix.
- Concurrent operations on the same browser conversation are serialized.
- Reset clears session ownership and browser conversation state.
- CDP mode reuses the intended visible provider tab and isolates additional sessions.
- Typed function arguments: booleans, integer/number, arrays, nested objects, enums, required fields, multiline strings, quotes, backslashes, Unicode, and meaningful leading/trailing newlines.
- Unknown function names, malformed arguments, `tool_choice: none`, `required`, and forced named functions.
- Streaming tool-call chunks end with `finish_reason: tool_calls`; provider failures are not reported as normal successful completions.
- Remote image ingestion rejects loopback/private/link-local targets, bad redirects, unsupported schemes, credentials in URLs, and oversize content.
- Bash timeouts terminate child processes and do not hang due to inherited pipes.
- Model listing does not expose the bridge's native tool registry as provider tools.

## Acceptance criteria

1. All available tests pass without hiding failures, and compile/lint checks are reported accurately.
2. OpenCode is the only tool executor on the OpenCode-compatible path.
3. Tool-call responses conform to the OpenAI-compatible contract and respect the request's tool schema/choice.
4. Browser conversation state is isolated and deterministic, including reuse of the visible provider tab in CDP mode.
5. The browser model receives the permanent concise plain-text/Markdown response instruction.
6. The final report distinguishes automated unit/fake-provider verification from a live test requiring an authenticated browser.
7. Each commit is reviewable and independently described in the final report.
