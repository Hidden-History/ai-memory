# Providers Reference

Canonical provider list for model-dispatch. All providers use the OpenAI chat completions API.

---

## Provider Config

Each provider has a record in `~/.config/claude-code-router/providers.json`:
- `baseUrl` — ANTHROPIC_BASE_URL to set for Claude Code
- `keyFile` — token file path (relative to home)
- `defaultModel` — install-time default model ID
- `emptyApiKey` — if true, ANTHROPIC_API_KEY must be set to "" (OpenRouter requirement)

---

## Providers

### openrouter
- **Base URL**: `https://openrouter.ai/api`
- **Token file**: `~/.openrouter-token`
- **API key note**: Requires `ANTHROPIC_API_KEY=""` (OpenRouter does not accept Anthropic keys)
- **Default model**: `anthropic/claude-sonnet-4-6`
- **Top models**: anthropic/claude-opus-4-6, openai/gpt-4o, google/gemini-2.0-flash, meta-llama/llama-4-maverick
- **List all**: `python3 scripts/openrouter-api/list-models.py --category coding`

### ollama
- **Base URL (cloud)**: `https://ollama.com`
- **Base URL (local)**: `http://localhost:11434`
- **Token file**: `~/.ollama-token`
- **Default model**: `glm-5:cloud`
- **Top models (cloud)**: qwen3-coder-next:cloud, qwen3.5:397b-cloud, qwen3-vl:235b-cloud
- **Top models (local)**: llama3.1, codellama, mistral

### gemini
- **CLI**: `gemini` (native Gemini CLI via `@google/gemini-cli`)
- **Install**: `npm install -g @google/gemini-cli`
- **Auth**: Google account (handled by Gemini CLI login flow — not the API key in `~/.gemini-token`)
- **Billing plan**: Uses your Google account's Gemini plan (separate from API free tier)
- **Model selection**: Managed by Gemini CLI interactively — no `--model` flag needed
- **Top models**: gemini-2.5-pro, gemini-2.5-flash, gemini-2.0-flash
- **Note**: Unlike other providers, Gemini does NOT route through Claude Code. The `gemini` CLI launches directly in a tmux pane and Claude manages the pane. The Gemini API key (`~/.gemini-token`) is only used for direct API calls via api-dispatch, not for CLI dispatch.

### deepseek
- **Base URL**: `https://api.deepseek.com`
- **Token file**: `~/.deepseek-token`
- **Default model**: `deepseek-chat`
- **Top models**: deepseek-chat (V3), deepseek-reasoner (R1)

### groq
- **Base URL**: `https://api.groq.com/openai`
- **Token file**: `~/.groq-token`
- **Default model**: `llama-4-scout-17b-16e-instruct`
- **Top models**: llama-4-scout-17b-16e-instruct, llama-4-maverick-17b-128e-instruct, qwen-qwq-32b, gemma2-9b-it

### cerebras
- **Base URL**: `https://api.cerebras.ai/v1`
- **Token file**: `~/.cerebras-token`
- **Default model**: `llama3.1-70b`
- **Top models**: llama3.1-70b, llama3.3-70b, qwen-3b

### mistral
- **Base URL**: `https://api.mistral.ai/v1`
- **Token file**: `~/.mistral-token`
- **Default model**: `mistral-large-2411`
- **Top models**: mistral-large-2411, codestral-2501, mistral-small-2501

### openai
- **Base URL**: `https://api.openai.com/v1`
- **Token file**: `~/.openai-token`
- **Default model**: `gpt-4o`
- **Top models**: gpt-4o, gpt-4o-mini, o1, o3-mini

### vertex-ai
- **Base URL**: `https://aiplatform.googleapis.com/v1/publishers/google/models`
- **Token file**: `~/.vertex-token`
- **Default model**: `claude-sonnet-4-5@anthropic`
- **Top models**: claude-opus-4-6@anthropic, claude-sonnet-4-5@anthropic, gemini-2.0-flash
- **Auth note**: Requires Google Cloud credentials (gcloud auth). Token file should contain OAuth2 Bearer token.

### siliconflow
- **Base URL**: `https://api.siliconflow.cn/v1`
- **Token file**: `~/.siliconflow-token`
- **Default model**: `Qwen/Qwen2.5-72B-Instruct`
- **Top models**: Qwen/Qwen2.5-72B-Instruct, deepseek-ai/DeepSeek-V3, meta-llama/Meta-Llama-3.1-70B-Instruct

---

## Adding a Custom Provider

1. Add an entry to `~/.config/claude-code-router/providers.json`
2. Create a token file at the specified keyFile path
3. Run `validate-setup.sh` to confirm the new provider is detected
4. Use "use [provider-name]" in your dispatch request
