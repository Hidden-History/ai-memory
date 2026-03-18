# Ollama Cloud Models

Available models for model-dispatch. The default model is **`glm-5:cloud`**.

---

## Default

```
glm-5:cloud
```

Used when no model is specified in the dispatch prompt.

---

## Model Catalog

### Coding Models

Best for code generation, implementation, refactoring, and debugging.

| Model | Notes |
|-------|-------|
| `qwen3-coder-next:cloud` | Latest Qwen coder, strong on multi-file generation |
| `qwen3-coder:480b-cloud` | Large Qwen coder (480B), deep code understanding |

### General Purpose (Large)

Best for complex reasoning, planning, architecture, and in-depth analysis.

| Model | Notes |
|-------|-------|
| `qwen3.5:397b-cloud` | 397B parameter Qwen, strong general reasoning |
| `mistral-large-3:675b-cloud` | Mistral's largest model (675B), broad capability |
| `deepseek-v3.2:cloud` | DeepSeek V3.2, strong on technical tasks |

### General Purpose (Medium)

Balanced performance and speed. Good default choice for most tasks.

| Model | Notes |
|-------|-------|
| `glm-5:cloud` | **Default** — GLM-5, reliable all-rounder |
| `glm-4.7:cloud` | GLM-4.7, previous generation |
| `minimax-m2.5:cloud` | MiniMax M2.5, good general performance |
| `minimax-m2:cloud` | MiniMax M2, previous generation |
| `kimi-k2.5:cloud` | Kimi K2.5, strong on Chinese and English tasks |

### Vision Models

Best for image analysis, visual understanding, and multimodal tasks.

| Model | Notes |
|-------|-------|
| `qwen3-vl:235b-cloud` | Qwen 235B vision-language model |
| `qwen3-vl:235b-instruct-cloud` | Instruction-tuned variant, better at following directions |

### Thinking / Reasoning Models

Best for deep reasoning, multi-step problem solving, and chain-of-thought tasks.

| Model | Notes |
|-------|-------|
| `kimi-k2-thinking:cloud` | Kimi with explicit reasoning chain, good for complex analysis |

### Small / Fast Models

Best for quick tasks, simple lookups, and low-latency operations.

| Model | Notes |
|-------|-------|
| `ministral-3:14b-cloud` | Mistral 14B, fast and capable |
| `ministral-3:8b-cloud` | Mistral 8B, fastest option |
| `gpt-oss:20b-cloud` | Open GPT 20B, lightweight |

### Open GPT Models

GPT-compatible open models.

| Model | Notes |
|-------|-------|
| `gpt-oss:120b-cloud` | Open GPT 120B, strong general reasoning |
| `gpt-oss:20b-cloud` | Open GPT 20B, fast and lightweight |

---

## Model Selection Guide

When dispatching, choose models based on the task:

| Task Type | Recommended Category | Top Pick |
|-----------|---------------------|----------|
| Code implementation / refactoring | Coding | `qwen3-coder-next:cloud` |
| Architecture / planning / analysis | General (Large) | `qwen3.5:397b-cloud` |
| General dev work / default | General (Medium) | `glm-5:cloud` |
| Image analysis | Vision | `qwen3-vl:235b-cloud` |
| Complex reasoning / math | Thinking | `kimi-k2-thinking:cloud` |
| Quick lookup / simple task | Small/Fast | `ministral-3:8b-cloud` |
| BMAD agent work | General (Medium) | `glm-5:cloud` |

---

## All Models (Quick Reference)

```
qwen3-coder-next:cloud
qwen3-coder:480b-cloud
qwen3.5:397b-cloud
mistral-large-3:675b-cloud
deepseek-v3.2:cloud
glm-5:cloud
glm-4.7:cloud
minimax-m2.5:cloud
minimax-m2:cloud
kimi-k2.5:cloud
qwen3-vl:235b-cloud
qwen3-vl:235b-instruct-cloud
kimi-k2-thinking:cloud
ministral-3:14b-cloud
ministral-3:8b-cloud
gpt-oss:120b-cloud
gpt-oss:20b-cloud
```
