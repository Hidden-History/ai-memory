# Claude Models (Anthropic)

Available Claude models via OpenRouter and native Anthropic API.

**`last_verified: 2026-07-29`** — this catalog is a hand-maintained reference value with no runtime source of truth. Re-verify it against the models actually dispatchable before trusting a tier, and update this date when you do. A catalog that omits the model doing the dispatching is not an authority (TD-845).

---

## Opus 5

```
claude-opus-5
```

**Capabilities:**
- Latest and most capable Claude model (2026)
- Superior reasoning, coding, and complex task handling
- Extended context available (`claude-opus-5[1m]`)

**Use Cases:**
- Complex analysis and synthesis
- Multi-step problem solving
- Architectural design
- High-stakes content creation
- BMAD agent orchestration — **the default Opus for review and architecture dispatches**

**Pricing Tier:** Premium (highest cost)

---

## Opus 4.8

```
claude-opus-4-8
```

**Capabilities:**
- Superior reasoning, coding, and complex task handling
- 200K token context window
- 128K output tokens

**Use Cases:**
- Complex analysis and synthesis
- Multi-step problem solving
- Architectural design
- High-stakes content creation
- BMAD agent orchestration — superseded by Opus 5 for new review/architecture dispatches

**Pricing Tier:** Premium (highest cost)

---

## Opus 4.7

```
claude-opus-4-7
```

**Capabilities:**
- Superior reasoning, coding, and complex task handling
- 200K token context window
- 128K output tokens

**Use Cases:**
- Complex analysis and synthesis
- Multi-step problem solving
- Architectural design
- High-stakes content creation
- BMAD agent orchestration — superseded; prefer Opus 5

**Pricing Tier:** Premium (highest cost)

---

## Opus 4.6

```
claude-opus-4-6
```

**Capabilities:**
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

## Sonnet 5

```
claude-sonnet-5
```

**Capabilities:**
- Balance of intelligence and speed
- Excellent coding capabilities
- Strong multimodal (vision) support

**Use Cases:**
- General development tasks
- Code generation and review
- Image analysis
- Content writing
- QA and testing
- BMAD agent orchestration — **the default Sonnet for the Sonnet half of a dual review**

**Pricing Tier:** Standard (moderate cost)

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
- Superseded by Sonnet 5 for new dispatches

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
| Complex analysis / architecture (review) | Opus 5 | Newest; use for reviewer and architecture dispatches |
| Complex analysis / architecture | Opus 4.8 | Still available; prior preferred Opus |
| Complex analysis / architecture | Opus 4.7 / 4.6 | Still available |
| General coding / dev work | Sonnet 5 | Best balance |
| Quick / simple tasks | Haiku 4.5 | Fastest and cheapest |
| Image analysis | Sonnet 5 | Strong vision support |
| BMAD agents | Sonnet 5 or Opus 5 | Depends on complexity |
| Dual review (the project's correctness gate) | Opus 5 **and** Sonnet 5 | Always mix tiers — never two of the same |

---

## Available via

- **Native Anthropic:** Direct API via `ANTHROPIC_API_KEY`
- **OpenRouter:** Via `anthropic/claude-opus-5`, `anthropic/claude-opus-4-8`, `anthropic/claude-opus-4-7`, `anthropic/claude-opus-4-6`, `anthropic/claude-sonnet-5`, `anthropic/claude-sonnet-4-6`, `anthropic/claude-haiku-4-5`

---

## Default Model

When dispatching via model-dispatch without specifying a model:
- **Claude native:** Uses your default Claude settings
- **OpenRouter:** Defaults to `claude-sonnet-5` for cost/performance balance

---

## On a catalog miss

If a dispatch names a model absent from this catalog, **fall back explicitly and out loud** — state the substitution and why. **Never silently select the newest listed model instead**: that is the exact failure this catalog produced for both tiers of every dual review between PM #407 and PM #420 (TD-845).
