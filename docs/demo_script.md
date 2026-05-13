# SubscriptionBridge — Demo Script

## A. Setup

```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install package with dev dependencies
pip install -e ".[dev]"

# 3. Install Playwright browsers
playwright install chromium

# 4. Run tests to verify everything works
pytest tests/ -v
```

---

## B. Fake Provider Demo

```bash
# List configured providers
bridge provider list

# Send a text prompt to the fake provider
bridge ask "Hello, what can you do?" --provider fake

# Request JSON response
bridge ask "Return JSON with project_name and version" --provider fake --json

# Run a simulated agent tool loop
bridge run "Read README.md and summarize it" --provider fake -w .
```

**What to explain**: The fake provider returns deterministic JSON responses. The `bridge run` command demonstrates a 2-step agent loop: `tool_call(file_read)` → observation → `final(answer)`.

---

## C. Codebase Memory Demo

```bash
# Index the workspace (117 files, ~158 chunks, ~6s)
bridge codebase index .

# Search the indexed codebase
bridge codebase search "provider adapter" -w . -k 5

# Show index statistics
bridge codebase stats -w .
```

**What to explain**: The codebase indexer chunks files by line ranges, extracts symbols/imports, and generates hash embeddings. The retriever combines semantic (cosine similarity), keyword (term overlap), and symbol (exact/substring) scoring.

---

## D. Browser/Gemini Demo

```bash
# 1. Start Chrome with remote debugging on port 9333
google-chrome \
  --remote-debugging-port=9333 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check

# 2. Navigate to https://gemini.google.com/app and log in manually

# 3. Run browser diagnostics
bridge browser doctor

# 4. Check Gemini health
bridge provider health gemini

# 5. Send a text prompt to Gemini
bridge ask "Say hello in JSON format" --provider gemini
```

**What to explain**: The browser runtime manages Playwright sessions. The Gemini provider navigates to a fresh chat, inserts the prompt with integrity verification, waits for send confirmation, extracts the response, and returns it.

---

## E. Gemini File Prompting Demo

```bash
# Summarize a text file
bridge ask "Summarize this file" --provider gemini --file examples/files/sample.txt

# Compare multiple files
bridge ask "Compare these files" --provider gemini \
  --file examples/files/sample.txt \
  --file examples/files/sample.json

# Describe an image
bridge ask "What's in this image" --provider gemini --file examples/files/sample.png
```

**What to explain**: File paths are validated (size, sensitivity, type classification) and uploaded to Gemini via Playwright's `set_input_files`. Unknown extensions are allowed by default.

---

## F. API Demo

```bash
# Start the API server
bridge server --host 127.0.0.1 --port 8787

# In another terminal:

# Health check
curl http://127.0.0.1:8787/health

# Ask the fake provider
curl -X POST http://127.0.0.1:8787/ask \
  -H "Content-Type: application/json" \
  -d '{"provider":"fake","prompt":"Say hello"}'

# Run the agent
curl -X POST http://127.0.0.1:8787/run \
  -H "Content-Type: application/json" \
  -d '{"provider":"fake","task":"test task","workspace":".","max_steps":5}'

# Search the codebase
curl -X POST http://127.0.0.1:8787/codebase/search \
  -H "Content-Type: application/json" \
  -d '{"workspace":".","query":"provider adapter","top_k":5}'
```

**What to explain**: The FastAPI server wraps all CLI functionality in typed HTTP endpoints. Docs at http://127.0.0.1:8787/docs.

---

## G. Closing

**Limitations to mention:**
- Browser UIs are less stable than official APIs
- Selectors may break if provider UI changes
- Manual login required per session
- Hash embeddings are not state-of-the-art
- Real Gemini tests require manual Chrome/e2e

**Future work to mention:**
- OpenCode compatibility (OpenAI-compatible API)
- ChatGPT and Claude provider adapters
- Stronger semantic embeddings
- Streaming responses
- Web dashboard
