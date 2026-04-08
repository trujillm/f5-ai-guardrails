# Frontend Changes

## F5 AI Guardrails Integration

Added support for routing chat requests through the F5 AI Guardrails moderator endpoint with API token authentication.

### What changed

**`start.sh`** (new)
- Startup script that handles `uv sync`, venv validation, and Streamlit launch
- Auto-detects `LLAMA_STACK_ENDPOINT` from OpenShift route if not set
- Falls back to `http://llamastack:8321` for in-cluster use

**`pyproject.toml`**
- Added `openai` and `httpx` dependencies for guardrail endpoint communication

**`llama_stack_ui/distribution/ui/modules/api.py`**
- Added `create_openai_client()` method for creating OpenAI-compatible clients with HTTPS/TLS support
- `create_client_with_url()` now accepts optional `api_token` and disables TLS verification for HTTPS endpoints

**`llama_stack_ui/distribution/ui/page/distribution/models.py`** (Settings page)
- Replaced single "XC URL" field with two sections:
  - Models are fetched from the default LlamaStack endpoint (`LLAMA_STACK_ENDPOINT` env var)
  - Optional **Endpoint URL** and **API Token** fields for F5 AI Guardrails
- Shows chat routing status (direct LlamaStack vs guardrail proxy)

**`llama_stack_ui/distribution/ui/page/playground/chat.py`** (Chat page)
- Two chat inference paths:
  - **Direct mode**: Uses `LlamaStackClient.inference.chat_completion()` via `/v1/inference/chat-completion`
  - **Guardrail mode**: Uses `OpenAI.chat.completions.create()` via `/chat/completions` on the moderator proxy
- Vector DBs and tool groups always fetched from the direct LlamaStack client
- Fixed `vector_dbs.list()` to use the configured client instead of hardcoded default

### Architecture

```
Direct mode:    Frontend --> LlamaStack --> vLLM model
Guardrail mode: Frontend --> F5 AI Guardrails (scan) --> LlamaStack --> vLLM model
```

The guardrail proxy only exposes `/chat/completions` (OpenAI-compatible), not the full LlamaStack API. This is why two separate clients are needed: a LlamaStack client for API operations and an OpenAI client for chat inference through the guardrail.
