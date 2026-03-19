# Claude Models (Anthropic)

Available Claude models via OpenRouter and native Anthropic API.

---

## Opus 4.6

```
claude-opus-4-6
```

**Capabilities:**
- Latest and most capable Claude model (2026)
- Superior reasoning, coding, and complex task handling
- 200K token context window
- 128K output tokens

**Use Cases:**
- Complex analysis and synthesis
- Multi-step problem solving
- Architectural design
- High-stakes content creation
- BMAD agent orchestration

**Pricing Tier:** Premium (highest cost)

---

## Sonnet 4.6

```
claude-sonnet-4-6
```

**Capabilities:**
- Balance of intelligence and speed
- Excellent coding capabilities
- Strong multimodal (vision) support
- 200K token context window

**Use Cases:**
- General development tasks
- Code generation and review
- Image analysis
- Content writing
- QA and testing

**Pricing Tier:** Standard (moderate cost)

---

## Haiku 4.5

```
claude-haiku-4-5-20251001
```

**Capabilities:**
- Fastest Claude model
- Cost-effective for simple tasks
- Good reasoning capabilities
- 200K token context window

**Use Cases:**
- Quick lookups and answers
- Simple text processing
- Low-cost automation
- High-volume repetitive tasks

**Pricing Tier:** Economy (lowest cost)

---

## Model Selection Guide

| Task Type | Recommended Model | Notes |
|-----------|------------------|-------|
| Complex analysis / architecture | Opus 4.6 | Most capable reasoning |
| General coding / dev work | Sonnet 4.6 | Best balance |
| Quick / simple tasks | Haiku 4.5 | Fastest and cheapest |
| Image analysis | Sonnet 4.6 | Strong vision support |
| BMAD agents | Sonnet 4.6 or Opus 4.6 | Depends on complexity |

---

## Available via

- **Native Anthropic:** Direct API via `ANTHROPIC_API_KEY`
- **OpenRouter:** Via `anthropic/claude-opus-4-6`, `anthropic/claude-sonnet-4-6`, `anthropic/claude-haiku-4-5`

---

## Default Model

When dispatching via model-dispatch without specifying a model:
- **Claude native:** Uses your default Claude settings
- **OpenRouter:** Defaults to `claude-sonnet-4-6` for cost/performance balance
