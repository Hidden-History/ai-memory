# Contributing to AI Memory Module

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.10+ (required for async + match statements)
- Docker 20.10+ (for Qdrant + embedding service)
- Git

### Local Development

```bash
# 1. Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/ai-memory.git
cd ai-memory

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# 3. Install development dependencies
pip install -e ".[dev]"

# 4. Start Docker services
docker compose -f docker/docker-compose.yml up -d

# 5. Run tests to verify setup
pytest tests/
```

## Coding Conventions

Follow these conventions strictly:

### Python (PEP 8)

| Element | Convention | Example |
|---------|------------|---------|
| Files | `snake_case.py` | `memory_store.py` |
| Functions | `snake_case()` | `store_memory()` |
| Classes | `PascalCase` | `MemoryStore` |
| Constants | `UPPER_SNAKE` | `DEFAULT_PORT` |

### Qdrant Payload Fields

Always use `snake_case` for payload fields:

```python
# CORRECT
{"content_hash": "...", "group_id": "...", "source_hook": "..."}

# WRONG
{"contentHash": "...", "groupId": "...", "sourceHook": "..."}
```

### Structured Logging

Use structured logging with extras dict, never f-strings:

```python
# CORRECT
logger.info("memory_stored", extra={"memory_id": mid, "type": "implementation"})

# WRONG
logger.info(f"Stored memory {mid}")
```

### Hook Exit Codes

- `0`: Success (normal completion)
- `1`: Non-blocking error (graceful degradation)
- `2`: Blocking error (rare - only when intentionally blocking Claude)

## Pull Request Process

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the coding conventions above

3. **Write tests** for all new functionality:
   ```bash
   pytest tests/ -v
   ```

4. **Ensure all tests pass** before submitting:
   ```bash
   pytest tests/
   ```

5. **Submit a pull request** with:
   - Clear description of changes
   - Reference to any related issues
   - Screenshots/examples if applicable

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_storage.py -v

# Run integration tests only
pytest tests/integration/ -v

# Run with coverage
pytest tests/ --cov=src/memory
```

### Test Location

- Unit tests: `tests/`
- Integration tests: `tests/integration/`
- Fixtures: `tests/conftest.py`

## Project Structure

```
ai-memory/
├── src/memory/          # Core Python modules
├── .claude/
│   ├── hooks/scripts/   # Hook implementations
│   └── skills/          # Skill definitions
├── docker/              # Docker Compose and service configs
├── scripts/             # Installation and management scripts
├── tests/               # pytest test suite
└── docs/                # Additional documentation
```

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/Hidden-History/ai-memory/issues)
- **Documentation**: See [README.md](README.md), [INSTALL.md](INSTALL.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

---

**Thank you for contributing!**
