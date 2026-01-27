# LLM Memory Classifier

The LLM Memory Classifier automatically reclassifies captured memories into more precise types using AI models.

## Overview

When memories are captured (via hooks), they receive an initial type based on the capture context. The classifier then analyzes the content and may reclassify to a more accurate type.

**Example**: A PostToolUse capture initially typed as `implementation` might be reclassified to `error_fix` if the content describes fixing a bug.

## Architecture

```
Memory Captured → Queue → Classifier Worker → Reclassified Memory
                           ↓
                    Rule-Based Check (fast, free)
                           ↓
                    LLM Classification (if no rule match)
                           ↓
                    Provider Chain: Primary → Fallback(s)
```

## Configuration

All settings are in `docker/.env`:

### Provider Selection

```bash
# Primary provider (required)
# Options: ollama, openrouter, claude, openai
MEMORY_CLASSIFIER_PRIMARY_PROVIDER=ollama

# Fallback providers (comma-separated, optional)
# Used when primary fails (timeout, rate limit, error)
MEMORY_CLASSIFIER_FALLBACK_PROVIDERS=openrouter
```

### Provider Settings

#### Ollama (Local, Free)

```bash
# URL for Ollama API
# - Docker Desktop (Windows/Mac): http://host.docker.internal:11434
# - Native Linux Docker: http://172.17.0.1:11434
# - WSL2: http://host.docker.internal:11434
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Model to use (must be pulled first: ollama pull <model>)
OLLAMA_MODEL=sam860/LFM2:2.6b

# Recommended models:
#   sam860/LFM2:2.6b     - Fast, good for classification
#   llama3.2:3b          - Good quality
#   phi3:mini            - Good reasoning
#   mistral:7b           - Balanced
```

#### OpenRouter (Cloud, Pay-per-use)

```bash
# Get API key at: https://openrouter.ai/keys
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Model to use
OPENROUTER_MODEL=mistralai/devstral-2512:free

# Recommended models:
#   google/gemma-2-9b-it:free        - Free tier, good quality
#   mistralai/devstral-2512:free     - Free tier, fast
#   mistralai/mistral-7b-instruct    - Cheap, reliable
#   anthropic/claude-3-haiku         - High quality, paid
```

#### Anthropic Claude (Cloud, High Quality)

```bash
# Get API key at: https://console.anthropic.com/
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# Model to use
ANTHROPIC_MODEL=claude-3-haiku-20240307

# Recommended models:
#   claude-3-haiku-20240307          - Fast, cheapest
#   claude-3-5-sonnet-20241022       - Best quality/cost ratio
```

#### OpenAI (Cloud)

```bash
# Get API key at: https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-your-key-here

# Model to use
OPENAI_MODEL=gpt-4o-mini

# Recommended models:
#   gpt-4o-mini                      - Cheapest, good quality
#   gpt-4o                           - Best quality
```

### Classification Settings

```bash
# Enable/disable classifier (default: true)
MEMORY_CLASSIFIER_ENABLED=true

# Confidence threshold for reclassification (0.0-1.0)
# Higher = more conservative reclassification
MEMORY_CLASSIFIER_CONFIDENCE_THRESHOLD=0.7

# Confidence for rule-based matches (usually higher)
MEMORY_CLASSIFIER_RULE_CONFIDENCE=0.85

# Minimum content length to classify (skip short content)
MEMORY_CLASSIFIER_MIN_CONTENT_LENGTH=20

# Request timeout in seconds
MEMORY_CLASSIFIER_TIMEOUT=30

# Max output tokens for LLM response
MEMORY_CLASSIFIER_MAX_TOKENS=500

# Max input chars to send to LLM (truncates long content)
MEMORY_CLASSIFIER_MAX_INPUT_CHARS=4000
```

## Setup Guide

### 1. Choose Your Provider

| Provider | Cost | Speed | Quality | Best For |
|----------|------|-------|---------|----------|
| **Ollama** | Free | Medium | Good | Development, privacy |
| **OpenRouter** | Free/Cheap | Fast | Good | Fallback, testing |
| **Claude** | Paid | Medium | Excellent | Production |
| **OpenAI** | Paid | Fast | Excellent | Production |

### 2. Configure Primary Provider

**For Ollama (recommended for development):**

```bash
# 1. Install Ollama: https://ollama.ai
# 2. Pull a model
ollama pull sam860/LFM2:2.6b

# 3. Configure docker/.env
MEMORY_CLASSIFIER_PRIMARY_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=sam860/LFM2:2.6b
```

**For OpenRouter:**

```bash
# 1. Get API key from https://openrouter.ai/keys
# 2. Configure docker/.env
MEMORY_CLASSIFIER_PRIMARY_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=google/gemma-2-9b-it:free
```

### 3. Configure Fallback (Optional but Recommended)

```bash
# If primary fails, try these in order
MEMORY_CLASSIFIER_FALLBACK_PROVIDERS=openrouter,claude
```

### 4. Apply Changes

```bash
# Restart classifier worker to pick up new settings
docker compose -f docker/docker-compose.yml restart classifier-worker

# Watch logs to verify
docker logs -f memory-classifier-worker 2>&1 | grep -E "classification|provider"
```

## Monitoring

### Check Classifier Status

```bash
# View recent classifications
docker logs memory-classifier-worker --tail 50

# Check which provider is being used
docker logs memory-classifier-worker 2>&1 | grep "attempting_classification"

# Check for fallback events
docker logs memory-classifier-worker 2>&1 | grep "fallback"
```

### Grafana Dashboard

The "Classifier Health" dashboard shows:
- Classifications per minute
- Provider success/failure rates
- Latency by provider
- Token consumption

Access at: http://localhost:23000 (with `--profile monitoring`)

### Prometheus Metrics

| Metric | Description |
|--------|-------------|
| `memory_classifier_requests_total` | Total classification requests |
| `memory_classifier_latency_seconds` | Classification latency |
| `memory_classifier_fallback_total` | Fallback events |
| `bmad_tokens_consumed_total{operation="classification"}` | Tokens used |

## Troubleshooting

### Ollama Not Connecting

**Symptom**: `provider_unavailable` or `connection refused`

**Solutions**:

1. Check Ollama is running:
   ```bash
   curl http://localhost:11434/api/tags
   ```

2. Verify Docker can reach host:
   ```bash
   # From inside container
   docker exec memory-classifier-worker curl http://host.docker.internal:11434/api/tags
   ```

3. For WSL2, ensure Ollama binds to all interfaces:
   ```bash
   OLLAMA_HOST=0.0.0.0 ollama serve
   ```

### OpenRouter Not Working

**Symptom**: `openrouter_http_error` or 401 errors

**Solutions**:

1. Verify API key is set:
   ```bash
   docker exec memory-classifier-worker env | grep OPENROUTER_API_KEY
   ```

2. Test API key directly:
   ```bash
   curl https://openrouter.ai/api/v1/chat/completions \
     -H "Authorization: Bearer $OPENROUTER_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model": "google/gemma-2-9b-it:free", "messages": [{"role": "user", "content": "Hi"}]}'
   ```

3. Check model availability at https://openrouter.ai/models

### Fallback Never Triggers

**This is normal!** Fallback only triggers when primary provider FAILS.

If you want to test fallback:

```bash
# Temporarily use OpenRouter as primary
MEMORY_CLASSIFIER_PRIMARY_PROVIDER=openrouter
docker compose -f docker/docker-compose.yml restart classifier-worker
```

### Classification Taking Too Long

**Solutions**:

1. Reduce timeout:
   ```bash
   MEMORY_CLASSIFIER_TIMEOUT=15
   ```

2. Use faster model:
   ```bash
   OLLAMA_MODEL=sam860/LFM2:2.6b  # Smaller, faster
   ```

3. Reduce input size:
   ```bash
   MEMORY_CLASSIFIER_MAX_INPUT_CHARS=2000
   ```

## Memory Types

The classifier can assign these types:

### code-patterns Collection
- `implementation` - How features/components were built
- `error_fix` - Errors encountered and solutions
- `refactor` - Refactoring patterns applied
- `file_pattern` - File or module-specific patterns

### conventions Collection
- `rule` - Hard rules (MUST follow)
- `guideline` - Soft guidelines (SHOULD follow)
- `port` - Port configuration rules
- `naming` - Naming conventions
- `structure` - File/folder structure conventions

### discussions Collection
- `decision` - Architectural/design decisions
- `session` - Session summaries
- `blocker` - Blockers and resolutions
- `preference` - User preferences
- `user_message` - User prompts
- `agent_response` - Agent responses

## Advanced Configuration

### Circuit Breaker

Protects against cascading failures:

```python
# In src/memory/classifier/circuit_breaker.py
FAILURE_THRESHOLD = 5      # Failures before opening
RESET_TIMEOUT = 60         # Seconds before retry
HALF_OPEN_ATTEMPTS = 3     # Test requests when half-open
```

### Rate Limiting

Prevents overwhelming providers:

```python
# In src/memory/classifier/rate_limiter.py
REQUESTS_PER_MINUTE = 60   # Max requests
BURST_SIZE = 10            # Burst allowance
```

### Skip Types

Some types are never reclassified:

```python
# In src/memory/classifier/config.py
SKIP_RECLASSIFICATION_TYPES = {"session", "error_fix"}
```

## Related Documentation

- [README.md](../README.md) - Project overview
- [CONFIGURATION.md](CONFIGURATION.md) - Full configuration reference
- [prometheus-queries.md](prometheus-queries.md) - Metrics queries
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - General troubleshooting
