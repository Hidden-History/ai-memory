# Best Practices Templates

This directory contains JSON template files for seeding the `best_practices` collection with useful shared memories.

## File Format

Each JSON file contains an array of best practice templates validated against the `BestPracticeTemplate` Pydantic model.

### Required Fields

- **content** (string, 10-2000 chars): The best practice text
- **domain** (string, 2-50 chars): Technology domain (python, docker, git, typescript, etc.)

### Optional Fields

- **type** (enum): Category - "pattern" (default), "antipattern", "tip", "security", or "performance"
- **importance** (enum): Priority level - "medium" (default), "high", or "low"
- **tags** (array of strings): Searchable tags (max 10 tags, each max 50 chars)
- **source** (string, HTTP(S) URL): Optional reference URL

## Example Template

```json
{
  "content": "Always use type hints in Python function signatures for better IDE support",
  "type": "pattern",
  "domain": "python",
  "importance": "high",
  "tags": ["python", "type-hints", "best-practice"],
  "source": "https://docs.python.org/3/library/typing.html"
}
```

## Security Validation

Templates are validated with security checks to prevent:

- **Script injection**: No `<script>` tags allowed
- **Code execution**: `eval()` only allowed in negative context (e.g., "Never use eval()")
- **Template injection**: No `{{` or `{%` (Jinja2 syntax)
- **Protocol injection**: No `javascript:` URLs
- **Tag injection**: Tags cannot contain `<`, `>`, `{`, `}`, `;`
- **Invalid URLs**: Source must be valid HTTP(S) URL

## Normalization

Templates are automatically normalized:

- **Content**: Whitespace stripped
- **Domain**: Converted to lowercase
- **Tags**: Converted to lowercase, deduplicated
- **Source**: Whitespace stripped

## Usage

### Seed from default directory

```bash
python3 scripts/memory/seed_best_practices.py
```

### Seed from custom directory

```bash
python3 scripts/memory/seed_best_practices.py --templates-dir /path/to/templates
```

### Dry run (validate without seeding)

```bash
python3 scripts/memory/seed_best_practices.py --dry-run
```

### Verbose logging

```bash
python3 scripts/memory/seed_best_practices.py -v
```

## Adding New Templates

1. Create a new `.json` file in this directory (e.g., `typescript-patterns.json`)
2. Follow the JSON format shown above
3. Validate with dry-run: `python3 scripts/memory/seed_best_practices.py --dry-run`
4. Seed: `python3 scripts/memory/seed_best_practices.py`

## Security Notes

- Templates are stored in `best_practices` collection with `group_id: "shared"`
- Never include API keys, passwords, or secrets in templates
- Use `.env` or Docker Secrets for actual secrets management
- All templates validated by Pydantic before insertion

## References

- **Pydantic validation**: `src/memory/template_models.py`
- **Seeding script**: `scripts/memory/seed_best_practices.py`
- **Story documentation**: `_bmad-output/implementation-artifacts/7-5-best-practices-seeding.md`
